# aura/llm/qwen35.py — Version 20261015v89  (AURA)
# v89: Schnappschuss am Vorspann-Ende (snap_at, von llmio gesetzt); save_kv nutzt ihn statt neu zu rechnen.
# v88: Native Engine fuer Qwen3.5 (Qwen3_5ForConditionalGeneration, nur Text-Teil) auf DirectX 11.
#   Aufbau: 24 x Gated-DeltaNet (lineare Attention, rekurrenter Zustand 128x128 je Kopf) + 8 x volle Attention
#   (head_dim 256, Ausgabe-Gate, RoPE nur auf 64 Dimensionen). Gewichte bf16 oder int8 (wie qwen.py).
#   Matrix-, Norm-, MLP- und int8-Kernels werden aus qwen.py uebernommen (bewaehrt); neu sind nur
#   Faltung, Delta-Regel, gegatete Norm, Q/K-Norm+RoPE 256, Attention 256 (Split-K) und Gate.
#   Selbsttest: jeder neue Kernel gegen eine Python-Rechnung (kleine Groessen), Abbruch bei Abweichung.
#   Rekurrenter Zustand: nur vorwaerts. Ruecksprung -> Schnappschuss (Ende des letzten Einlesens) oder Neuberechnung.
# Referenz: transformers/models/qwen3_5/modeling_qwen3_5.py

import json, math, random, struct, time
from array import array
from ctypes import c_void_p
from pathlib import Path
from ..engine.gpu import GPU, _com
from .qwen import (K_LINEAR2, K_MATVEC, K_MATVEC_T, K_RMS, K_SILUMUL, K_COPY, K_COPY16, K_QUANT, K_MV8, K_MVT8,
                   K_SOFTMAX, k_linear8, k_gemm, k_gemm16, kv16, ShardedSafeTensors, bf16_to_f32, common_prefix,
                   CHUNK, LMH_ROWS, SMALL_MAX, SMAX_MB)

MAXT = 32768
SPLIT_T = 16          # Attention in Tokenpaketen zu 16 (Split-K-Puffer)
NS_MAX = 128          # hoechstens so viele Teilstuecke je KV-Kopf
SPLIT_MIN = 512       # darunter ein Teilstueck
PRE_MIN = 64          # Einlesen: ab so vielen Tokens Attention per gemm
P = "model.language_model."

# ----------------------------------------------------------------------------- neue HLSL-Kernels
# Kausale Faltung (Breite 4) + SiLU, in place. Ein Thread je Kanal, laeuft ueber alle Tokens; Zustand = letzte 3 Eingaben.
K_CONV = r"""
cbuffer C:register(b0){ uint T; uint NC; uint P1; uint P2; };
RWStructuredBuffer<float> X:register(u0); RWStructuredBuffer<float> W:register(u1); RWStructuredBuffer<float> CS:register(u2);
[numthreads(256,1,1)]
void main(uint3 d:SV_DispatchThreadID){
  uint c=d.x; if(c>=NC) return;
  float w0=W[c*4], w1=W[c*4+1], w2=W[c*4+2], w3=W[c*4+3];
  float a=CS[c*3], b=CS[c*3+1], e=CS[c*3+2];
  for(uint t=0;t<T;t++){ float x=X[t*NC+c]; float y=w0*a+w1*b+w2*e+w3*x; a=b; b=e; e=x; X[t*NC+c]=y/(1.0+exp(-y)); }
  CS[c*3]=a; CS[c*3+1]=b; CS[c*3+2]=e;
}"""

# Gated Delta Rule. Gruppe = 64 Value-Spalten eines Value-Kopfs; jeder Thread haelt seine Zustandsspalte S[:,v].
# X-Zeile = [q 16x128 | k 16x128 | v 32x128]; Value-Kopf h nutzt Key-Kopf h/2 (repeat_interleave).
K_DELTA = r"""
cbuffer C:register(b0){ uint T; uint P1; uint P2; uint P3; };
RWStructuredBuffer<float> X:register(u0); RWStructuredBuffer<float> Ab:register(u1);
RWStructuredBuffer<float> Bb:register(u2); RWStructuredBuffer<float> AL:register(u3);
RWStructuredBuffer<float> DT:register(u4); RWStructuredBuffer<float> ST:register(u5);
RWStructuredBuffer<float> O:register(u6);
groupshared float qs[128]; groupshared float ks[128]; groupshared float rq[64]; groupshared float rk[64];
[numthreads(64,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint i=l.x, h=g.y, v=g.x*64+i, kh=h>>1, k, t, a;
  uint sb=h*16384+v; float s[128];
  [unroll] for(k=0;k<128;k++) s[k]=ST[sb+k*128];
  float An=-exp(AL[h]), dtb=DT[h];
  for(t=0;t<T;t++){
    uint rb=t*8192, qb=rb+kh*128, kb=rb+2048+kh*128;
    float q0=X[qb+i], q1=X[qb+64+i], k0=X[kb+i], k1=X[kb+64+i];
    rq[i]=q0*q0+q1*q1; rk[i]=k0*k0+k1*k1; GroupMemoryBarrierWithGroupSync();
    for(a=32;a>0;a>>=1){ if(i<a){ rq[i]+=rq[i+a]; rk[i]+=rk[i+a]; } GroupMemoryBarrierWithGroupSync(); }
    float nq=rsqrt(rq[0]+1e-6)*0.08838834764831845, nk=rsqrt(rk[0]+1e-6);
    qs[i]=q0*nq; qs[i+64]=q1*nq; ks[i]=k0*nk; ks[i+64]=k1*nk;
    GroupMemoryBarrierWithGroupSync();
    float x=Ab[t*32+h]+dtb; float sp=(x>20.0)?x:log(1.0+exp(x)); float gt=exp(An*sp);
    float beta=1.0/(1.0+exp(-Bb[t*32+h]));
    float vv=X[rb+4096+h*128+v], km=0;
    [unroll] for(k=0;k<128;k++){ s[k]*=gt; km+=s[k]*ks[k]; }
    float dl=(vv-km)*beta, o=0;
    [unroll] for(k=0;k<128;k++){ s[k]+=ks[k]*dl; o+=s[k]*qs[k]; }
    O[t*4096+h*128+v]=o;
    GroupMemoryBarrierWithGroupSync();
  }
  [unroll] for(k=0;k<128;k++) ST[sb+k*128]=s[k];
}"""

# RMSNorm je Kopf (128) mit Gewicht w (ohne +1), danach * SiLU(z). In place.
K_GNORM = r"""
cbuffer C:register(b0){ uint T; float EPS; uint P1; uint P2; };
RWStructuredBuffer<float> O:register(u0); RWStructuredBuffer<float> Z:register(u1); RWStructuredBuffer<float> W:register(u2);
groupshared float red[128];
[numthreads(128,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint i=l.x, base=(g.x*32+g.y)*128; float x=O[base+i];
  red[i]=x*x; GroupMemoryBarrierWithGroupSync();
  for(uint a=64;a>0;a>>=1){ if(i<a) red[i]+=red[i+a]; GroupMemoryBarrierWithGroupSync(); }
  float r=rsqrt(red[0]/128.0+EPS), z=Z[base+i];
  O[base+i]=x*r*W[i]*z/(1.0+exp(-z));
}"""

# Q/K-Norm (256, Gewicht bereits 1+w) und RoPE auf die ersten 64 Dimensionen (Paare i, i+32). Kopf-Abstand STRIDE.
K_QKROPE = r"""
cbuffer C:register(b0){ uint T; uint NHD; uint POS0; float EPS; uint STRIDE; uint P1; uint P2; uint P3; };
RWStructuredBuffer<float> X:register(u0); RWStructuredBuffer<float> G:register(u1); RWStructuredBuffer<float> CS:register(u2);
groupshared float red[256]; groupshared float xs[256];
[numthreads(256,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint t=g.x, h=g.y, i=l.x, base=(t*NHD+h)*STRIDE; float x=X[base+i];
  red[i]=x*x; GroupMemoryBarrierWithGroupSync();
  for(uint a=128;a>0;a>>=1){ if(i<a) red[i]+=red[i+a]; GroupMemoryBarrierWithGroupSync(); }
  float y=x*rsqrt(red[0]/256.0+EPS)*G[i]; xs[i]=y; GroupMemoryBarrierWithGroupSync();
  if(i<32){ uint p=(POS0+t)*32+i; float c=CS[2*p], s=CS[2*p+1], u=xs[i], w=xs[i+32];
    X[base+i]=u*c-w*s; X[base+i+32]=w*c+u*s; }
  else if(i>=64) X[base+i]=y;
}"""

# Attention head_dim 256, 4 Q-Koepfe je KV-Kopf, Online-Softmax in Bloecken zu 256 Positionen.
# Gruppe (s, kvh, t): Positionen [s*L, min((s+1)*L, P+1)); Token T0+t. Q-Kopf h liegt bei (tok*NH+h)*512.
K_ATTN = r"""
cbuffer C:register(b0){ uint POS0; uint L; uint NH; uint NKV; uint T0; uint P1; uint P2; uint P3; };
RWStructuredBuffer<float> Q:register(u0); RWStructuredBuffer<float> K:register(u1);
RWStructuredBuffer<float> V:register(u2); RWStructuredBuffer<float> PO:register(u3);
RWStructuredBuffer<float> ML:register(u4);
groupshared float q[4][256]; groupshared float sc[4][256];
[numthreads(256,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint s=g.x, kvh=g.y, t=g.z, i=l.x, G=NH/NKV, KD=NKV*256, P=POS0+T0+t, kb=kvh*256, h, j, k;
  uint jb=s*L, je=min(jb+L, P+1), so=(t*%(NS)d+s)*NH;
  for(h=0;h<G;h++) q[h][i]=Q[((T0+t)*NH+kvh*G+h)*512+i];
  GroupMemoryBarrierWithGroupSync();
  float m[4], ls[4], acc[4];
  [unroll] for(h=0;h<4;h++){ m[h]=-1e30; ls[h]=0; acc[h]=0; }
  for(uint b0=jb;b0<je;b0+=256){
    uint j0=b0+i, n=min(256,je-b0);
    float d[4]; [unroll] for(h=0;h<4;h++) d[h]=0;
    if(i<n){ for(k=0;k<256;k++){ float kv=K[j0*KD+kb+k]; [unroll] for(h=0;h<4;h++) if(h<G) d[h]+=q[h][k]*kv; } }
    [unroll] for(h=0;h<4;h++) sc[h][i]=(i<n)?d[h]*0.0625:-1e30;
    GroupMemoryBarrierWithGroupSync();
    [unroll] for(h=0;h<4;h++) if(h<G){ float bm=m[h]; for(j=0;j<n;j++) bm=max(bm,sc[h][j]);
      float f=exp(m[h]-bm); acc[h]*=f; ls[h]*=f; m[h]=bm; }
    GroupMemoryBarrierWithGroupSync();
    [unroll] for(h=0;h<4;h++) sc[h][i]=(i<n&&h<G)?exp(sc[h][i]-m[h]):0;
    GroupMemoryBarrierWithGroupSync();
    for(j=0;j<n;j++){ float v=V[(b0+j)*KD+kb+i];
      [unroll] for(h=0;h<4;h++) if(h<G){ float pr=sc[h][j]; ls[h]+=pr; acc[h]+=pr*v; } }
    GroupMemoryBarrierWithGroupSync();
  }
  for(h=0;h<G;h++){ uint qh=kvh*G+h; PO[(so+qh)*256+i]=acc[h];
    if(i==0){ ML[(so+qh)*2]=m[h]; ML[(so+qh)*2+1]=ls[h]; } }
}""" % dict(NS=NS_MAX)

K_MERGE = r"""
cbuffer C:register(b0){ uint NS; uint NH; uint T0; uint P1; };
RWStructuredBuffer<float> PO:register(u0); RWStructuredBuffer<float> ML:register(u1); RWStructuredBuffer<float> O:register(u2);
[numthreads(256,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint h=g.x, t=g.y, i=l.x, s, b=t*%(NS)d; float M=-1e30, num=0, den=0;
  for(s=0;s<NS;s++) M=max(M, ML[((b+s)*NH+h)*2]);
  for(s=0;s<NS;s++){ float f=exp(ML[((b+s)*NH+h)*2]-M); num+=f*PO[((b+s)*NH+h)*256+i]; den+=f*ML[((b+s)*NH+h)*2+1]; }
  O[(T0+t)*NH*256+h*256+i]=num/den;
}""" % dict(NS=NS_MAX)

# Ausgabe-Gate: A[e] *= sigmoid(Gate), Gate liegt hinter Q im selben Kopfblock (Abstand 512).
K_GATE = r"""
cbuffer C:register(b0){ uint N; uint STRIDE; uint P1; uint P2; };
RWStructuredBuffer<float> A:register(u0); RWStructuredBuffer<float> Q:register(u1);
[numthreads(256,1,1)]
void main(uint3 d:SV_DispatchThreadID){
  for(uint e=d.x;e<N;e+=STRIDE){ float z=Q[(e>>8)*512+256+(e&255)]; A[e]*=1.0/(1.0+exp(-z)); }
}"""

K_SOFTMAX256 = K_SOFTMAX.replace("0.08838834764831845", "0.0625")


class Qwen35Engine:
    def __init__(self, model_dir, progress=lambda *a: None, maxT=MAXT, int8=False, kv16_on=True):
        self.dir = Path(model_dir)
        full = json.loads((self.dir / "config.json").read_text(encoding="utf-8"))
        c = self.cfg = full.get("text_config", full)
        self.H, self.I, self.L = c["hidden_size"], c["intermediate_size"], c["num_hidden_layers"]
        self.NH, self.NKV, self.D = c["num_attention_heads"], c["num_key_value_heads"], c.get("head_dim", 256)
        self.eps, self.V = c.get("rms_norm_eps", 1e-6), c["vocab_size"]
        self.types = c["layer_types"]
        ok = (self.D == 256 and self.NH // self.NKV == 4 and c["linear_num_key_heads"] == 16 and c["linear_num_value_heads"] == 32
              and c["linear_key_head_dim"] == 128 and c["linear_value_head_dim"] == 128 and c["linear_conv_kernel_dim"] == 4
              and c.get("attn_output_gate", True))
        if not ok: raise ValueError("Qwen3.5-Engine erwartet die Masse von Qwen3.5-4B (head_dim 256, DeltaNet 16/32x128)")
        rp = c.get("rope_parameters") or {}
        self.rot = int(self.D * rp.get("partial_rotary_factor", 0.25)); self.theta = rp.get("rope_theta", 1e7)
        if self.rot != 64: raise ValueError("Qwen3.5-Engine erwartet RoPE auf 64 Dimensionen")
        self.maxT = min(maxT, MAXT)
        self.st = ShardedSafeTensors(self.dir)
        g = self.g = GPU()
        self.kv16 = bool(kv16_on); hk = (lambda s: kv16(s, "KV")) if self.kv16 else (lambda s: s)
        sh = g._shader
        self.k_lin2, self.k_mv, self.k_mt, self.k_rms = sh(K_LINEAR2), sh(K_MATVEC), sh(K_MATVEC_T), sh(K_RMS)
        self.k_silu, self.k_copy = sh(K_SILUMUL), sh(K_COPY)
        self.k_copy16 = sh(K_COPY16) if self.kv16 else None
        self.k_conv, self.k_delta, self.k_gnorm, self.k_rope = sh(K_CONV), sh(K_DELTA), sh(K_GNORM), sh(K_QKROPE)
        self.k_attn, self.k_merge, self.k_gate = sh(hk(K_ATTN)), sh(K_MERGE), sh(K_GATE)
        self.k_gemm = None
        try:
            gm = (sh(k_gemm16(False)), sh(k_gemm16(True))) if self.kv16 else (sh(k_gemm(False)), sh(k_gemm(True)))
            self.k_gemm = gm + (sh(K_SOFTMAX256),)
        except Exception as e: progress(f"Attention gemm nicht verfuegbar: {e}")
        self.q8 = False; self.stg = None
        H, I = self.H, self.I
        if int8:
            try:
                self.k_quant, self.k_mv8, self.k_mvt8 = sh(K_QUANT), sh(K_MV8), sh(K_MVT8)
                self.k_lin8 = sh(k_linear8(4, 4))
                self.stg = g.buffer(max(LMH_ROWS * H, I * H, 2 * self.NH * self.D * H, 8192 * H) // 2); self.q8 = True
            except Exception as e: progress(f"8-Bit-Kernels nicht verfuegbar ({e}) - lade mit bf16")
        self.lin_kernel = "q44" if self.q8 else "v2"; self.small_kernel = "mt"
        self.pre_kernel = "gemm" if self.k_gemm else "split"; self.dec_kernel = "split"
        self.attn_kernel = "attn256"; self.small_attn = "split"; self.prof = None
        self.tag = self.dir.name + ("-int8" if self.q8 else "") + ("-kv16" if self.kv16 else "") + "-q35"
        # ---- Gewichte
        st = self.st
        up_bf = lambda k: g.buffer(len(st.raw(k)) // 4, st.raw(k))
        up = (lambda k: self._quant(st.raw(k), *st.shape(k)[:2])) if self.q8 else up_bf
        upf = lambda k: (lambda b: g.buffer(len(b) // 4, b))(st.f32(k))
        def upf1(k):                                                 # RMSNorm mit (1 + w): Gewicht beim Laden anpassen
            a = array("f"); a.frombytes(st.f32(k)); a = array("f", [x + 1.0 for x in a]); return g.buffer(len(a), a.tobytes())
        self.w = []
        for l in range(self.L):
            p = P + "layers.%d." % l; progress(f"Lade Sprachmodell: Schicht {l + 1}/{self.L}", l, self.L)
            d = {n: up(p + "mlp." + n + ".weight") for n in ("gate_proj", "up_proj", "down_proj")}
            d["in_norm"] = upf1(p + "input_layernorm.weight"); d["post_norm"] = upf1(p + "post_attention_layernorm.weight")
            if self.types[l] == "linear_attention":
                a = p + "linear_attn."
                for n in ("in_proj_qkv", "in_proj_z", "in_proj_a", "in_proj_b", "out_proj"): d[n] = up(a + n + ".weight")
                d["conv"] = upf(a + "conv1d.weight"); d["A_log"] = upf(a + "A_log"); d["dt_bias"] = upf(a + "dt_bias")
                d["gnorm"] = upf(a + "norm.weight")
            else:
                a = p + "self_attn."
                for n in ("q_proj", "k_proj", "v_proj", "o_proj"): d[n] = up(a + n + ".weight")
                d["q_norm"] = upf1(a + "q_norm.weight"); d["k_norm"] = upf1(a + "k_norm.weight")
            self.w.append(d)
        self.norm = upf1(P + "norm.weight")
        emb = P + "embed_tokens.weight"; head = "lm_head.weight" if "lm_head.weight" in st else emb
        self.emb_raw = st.raw(emb); self.row_bytes = H * 2
        progress("Lade Sprachmodell: Ausgabeschicht", self.L, self.L)
        hr = st.raw(head); self.lmh = []
        for r0 in range(0, self.V, LMH_ROWS):
            r1 = min(self.V, r0 + LMH_ROWS); part = hr[r0 * self.row_bytes: r1 * self.row_bytes]
            self.lmh.append((r0, r1, self._quant(part, r1 - r0, H) if self.q8 else g.buffer((r1 - r0) * H // 2, part)))
        if self.q8: g.free(self.stg); self.stg = None
        # ---- RoPE-Tabelle (32 Frequenzen)
        inv = [1.0 / self.theta ** (2 * i / self.rot) for i in range(self.rot // 2)]
        cs = array("f")
        for p_ in range(self.maxT):
            for f in inv: cs.append(math.cos(p_ * f)); cs.append(math.sin(p_ * f))
        self.cs = g.buffer(len(cs), cs.tobytes())
        # ---- Arbeitspuffer
        C, QD, KD = CHUNK, self.NH * self.D, self.NKV * self.D
        self.R, self.X, self.O = g.buffer(C * H), g.buffer(C * H), g.buffer(C * H)
        self.QKV = g.buffer(C * 8192)                       # DeltaNet q|k|v bzw. volle Attention Q|Gate
        self.Z, self.A = g.buffer(C * 4096), g.buffer(C * QD)
        self.Ab, self.Bb = g.buffer(C * 32), g.buffer(C * 32)
        self.K, self.Vb = g.buffer(C * KD), g.buffer(C * KD)
        self.Gt, self.Up = g.buffer(C * I), g.buffer(C * I)
        self.full = [l for l in range(self.L) if self.types[l] == "full_attention"]
        self.lin = [l for l in range(self.L) if self.types[l] != "full_attention"]
        kvn = self.maxT * KD // (2 if self.kv16 else 1)
        self.kc = {l: g.buffer(kvn) for l in self.full}; self.vc = {l: g.buffer(kvn) for l in self.full}
        self.ST = {l: g.buffer(32 * 128 * 128) for l in self.lin}; self.CV = {l: g.buffer(8192 * 3) for l in self.lin}
        self.STs = {l: g.buffer(32 * 128 * 128) for l in self.lin}; self.CVs = {l: g.buffer(8192 * 3) for l in self.lin}
        self.PO, self.ML = g.buffer(SPLIT_T * NS_MAX * self.NH * 256), g.buffer(SPLIT_T * NS_MAX * self.NH * 2)
        if self.k_gemm:
            self.nb = max(1, min(self.NH, SMAX_MB * 1_000_000 // (C * self.maxT * 4)))
            self.S = g.buffer(self.nb * C * self.maxT)
        self.logits = g.buffer(self.V)
        self.kv_ids, self.reused = [], 0
        self.split_on = True; self.snap_at = 0
        self._reset_state()

    # ---- Zustand (rekurrent)
    def _reset_state(self):
        for l in self.lin:
            self.g.write(self.ST[l], bytes(32 * 128 * 128 * 4)); self.g.write(self.CV[l], bytes(8192 * 3 * 4))
        self.spos = 0; self.snap = None

    def _cp(self, dst, src): _com(self.g.ctx, 47, [c_void_p, c_void_p], dst["buf"], src["buf"])   # CopyResource

    def _snapshot(self):
        for l in self.lin: self._cp(self.STs[l], self.ST[l]); self._cp(self.CVs[l], self.CV[l])
        self.snap = (self.spos, list(self.kv_ids[:self.spos]))

    def _seek(self, p):
        """Bringt den rekurrenten Zustand auf Position p (Tokens 0..p-1 aus kv_ids)."""
        if p == self.spos: return
        if p < self.spos:
            sp = self.snap
            if sp and sp[0] <= p and self.kv_ids[:sp[0]] == sp[1]:
                for l in self.lin: self._cp(self.ST[l], self.STs[l]); self._cp(self.CV[l], self.CVs[l])
                self.spos = sp[0]
            else:
                self._reset_state()
        need = self.kv_ids[self.spos:p]
        if len(need) != p - self.spos or any(t is None for t in need):
            raise RuntimeError("Qwen3.5: Zustand fuer diese Position nicht rekonstruierbar (Tokens unbekannt)")
        for s in range(self.spos, p, CHUNK): self._block(self.kv_ids[s:min(p, s + CHUNK)], s, False)

    # ---- Bausteine
    def _quant(self, raw, OUT, IN):
        if IN % 128: return self.g.buffer(len(raw) // 4, raw)
        nb = OUT * IN // 128; g = self.g
        g.write(self.stg, raw)
        w8, sc = g.buffer(OUT * IN // 16, stride=16), g.buffer(nb)
        g._run(self.k_quant, struct.pack("<4I", nb, 0, 0, 0), [self.stg, w8, sc], ((nb + 63) // 64, 1, 1))
        g.sync(); return ("q8", w8, sc)

    def _lin(self, x, w, y, T, IN, OUT):
        g = self.g
        if isinstance(w, tuple):
            _, w8, sc = w
            if T == 1: g._run(self.k_mv8, struct.pack("<4I", IN, 0, 0, OUT), [x, w8, y, sc], ((OUT + 7) // 8, 1, 1))
            elif T <= SMALL_MAX:
                for t0 in range(0, T, 16):
                    g._run(self.k_mvt8, struct.pack("<4I", min(16, T - t0), IN, OUT, t0), [x, w8, y, sc], ((OUT + 31) // 32, 1, 1))
            else: g._run(self.k_lin8, struct.pack("<4I", T, IN, OUT, 0), [x, w8, y, sc], ((OUT + 63) // 64, (T + 63) // 64, 1))
        elif T == 1: g._run(self.k_mv, struct.pack("<4I", IN, 0, 0, 0), [x, w, y], (OUT, 1, 1))
        elif T <= SMALL_MAX:
            for t0 in range(0, T, 16):
                g._run(self.k_mt, struct.pack("<4I", min(16, T - t0), IN, OUT, t0), [x, w, y], ((OUT + 7) // 8, 1, 1))
        else: g._run(self.k_lin2, struct.pack("<4I", T, IN, OUT, 0), [x, w, y], ((OUT + 63) // 64, (T + 127) // 128, 1))
        self._tick("linear")

    def _rms(self, a, r, gw, y, T, add):
        self.g._run(self.k_rms, struct.pack("<IIfI", T, self.H, self.eps, 1 if add else 0), [a, r, gw, y], (T, 1, 1))

    def _copykv(self, src, dst, nfloats, dst_off):
        g = self.g
        if not self.kv16:
            groups = min((nfloats + 255) // 256, 65535)
            return g._run(self.k_copy, struct.pack("<4I", nfloats, dst_off, groups * 256, 0), [src, dst], (groups, 1, 1))
        n = nfloats // 2; groups = min((n + 255) // 256, 65535)
        g._run(self.k_copy16, struct.pack("<4I", n, dst_off // 2, groups * 256, 0), [src, dst], (groups, 1, 1))

    def _kvw(self, dst, data):
        if not self.kv16: return self.g.write(dst, data)
        step = CHUNK * self.NKV * self.D * 4
        for o in range(0, len(data), step):
            part = data[o:o + step]; self.g.write(self.K, part); self._copykv(self.K, dst, len(part) // 4, o // 4)

    def _tick(self, name):
        if self.prof is None: return
        self.g.sync(); now = time.perf_counter()
        self.prof[name] = self.prof.get(name, 0.0) + now - self.prof["_t"]; self.prof["_t"] = now

    def _attn(self, l, T, pos0, force=None):
        mode = force or ("gemm" if (T >= PRE_MIN and self.k_gemm and self.pre_kernel == "gemm") else "split")
        g = self.g
        if mode == "gemm":
            kt, kn, ks = self.k_gemm; N = pos0 + T; QS, QD, KD = self.NH * 512, self.NH * 256, self.NKV * 256
            for h0 in range(0, self.NH, self.nb):
                nz = min(self.nb, self.NH - h0)
                g._run(kt, struct.pack("<16I", T, N, 256, QS, KD, N, h0, 4, 512, 0, 256, 0, T * N, 0, 0, 0),
                       [self.QKV, self.kc[l], self.S], ((N + 63) // 64, (T + 127) // 128, nz))
                g._run(ks, struct.pack("<4I", T, N, N, pos0), [self.S], (T, nz, 1))
                g._run(kn, struct.pack("<16I", T, 256, N, N, KD, QD, h0, 4, 0, T * N, 256, 256, 0, 0, 0, 0),
                       [self.S, self.vc[l], self.A], (4, (T + 127) // 128, nz))
        else:
            for t0 in range(0, T, SPLIT_T):
                tt = min(SPLIT_T, T - t0); n = pos0 + t0 + tt
                if self.split_on and mode != "one" and n >= SPLIT_MIN:
                    L = max(128, (-(-n // NS_MAX) + 127) // 128 * 128)
                else: L = n
                ns = -(-n // L)
                g._run(self.k_attn, struct.pack("<8I", pos0, L, self.NH, self.NKV, t0, 0, 0, 0),
                       [self.QKV, self.kc[l], self.vc[l], self.PO, self.ML], (ns, self.NKV, tt))
                g._run(self.k_merge, struct.pack("<4I", ns, self.NH, t0, 0), [self.PO, self.ML, self.A], (self.NH, tt, 1))
        n = T * self.NH * 256; groups = min((n + 255) // 256, 65535)
        g._run(self.k_gate, struct.pack("<4I", n, groups * 256, 0, 0), [self.A, self.QKV], (groups, 1, 1))
        self._tick("attention")

    def _delta_layer(self, l, T):
        w, g, H = self.w[l], self.g, self.H
        self._lin(self.X, w["in_proj_qkv"], self.QKV, T, H, 8192)
        self._lin(self.X, w["in_proj_z"], self.Z, T, H, 4096)
        self._lin(self.X, w["in_proj_a"], self.Ab, T, H, 32)
        self._lin(self.X, w["in_proj_b"], self.Bb, T, H, 32)
        g._run(self.k_conv, struct.pack("<4I", T, 8192, 0, 0), [self.QKV, w["conv"], self.CV[l]], (32, 1, 1))
        g._run(self.k_delta, struct.pack("<4I", T, 0, 0, 0),
               [self.QKV, self.Ab, self.Bb, w["A_log"], w["dt_bias"], self.ST[l], self.A], (2, 32, 1))
        g._run(self.k_gnorm, struct.pack("<IfII", T, self.eps, 0, 0), [self.A, self.Z, w["gnorm"]], (T, 32, 1))
        self._tick("delta")
        self._lin(self.A, w["out_proj"], self.O, T, 4096, H)

    def _attn_layer(self, l, T, pos0):
        w, g, H, KD = self.w[l], self.g, self.H, self.NKV * 256
        self._lin(self.X, w["q_proj"], self.QKV, T, H, self.NH * 512)
        self._lin(self.X, w["k_proj"], self.K, T, H, KD)
        self._lin(self.X, w["v_proj"], self.Vb, T, H, KD)
        g._run(self.k_rope, struct.pack("<IIIfIIII", T, self.NH, pos0, self.eps, 512, 0, 0, 0), [self.QKV, w["q_norm"], self.cs], (T, self.NH, 1))
        g._run(self.k_rope, struct.pack("<IIIfIIII", T, self.NKV, pos0, self.eps, 256, 0, 0, 0), [self.K, w["k_norm"], self.cs], (T, self.NKV, 1))
        self._copykv(self.K, self.kc[l], T * KD, pos0 * KD); self._copykv(self.Vb, self.vc[l], T * KD, pos0 * KD)
        self._attn(l, T, pos0)
        self._lin(self.A, w["o_proj"], self.O, T, self.NH * 256, H)

    def layer(self, l, T, pos0, first):
        w, H, I = self.w[l], self.H, self.I
        self._rms(self.O, self.R, w["in_norm"], self.X, T, add=not first)
        if self.types[l] == "full_attention": self._attn_layer(l, T, pos0)
        else: self._delta_layer(l, T)
        self._rms(self.O, self.R, w["post_norm"], self.X, T, add=True)
        self._lin(self.X, w["gate_proj"], self.Gt, T, H, I)
        self._lin(self.X, w["up_proj"], self.Up, T, H, I)
        n = T * I; groups = min((n + 255) // 256, 65535)
        self.g._run(self.k_silu, struct.pack("<4I", n, groups * 256, 0, 0), [self.Gt, self.Up], (groups, 1, 1))
        self._tick("andere")
        self._lin(self.Gt, w["down_proj"], self.O, T, I, H)

    def embed_rows(self, ids):
        rb = self.row_bytes
        return b"".join(bf16_to_f32(self.emb_raw[t * rb:(t + 1) * rb]) for t in ids)

    def _block(self, ids, pos0, want_logits):
        T = len(ids)
        self.g.write(self.R, self.embed_rows(ids))
        for l in range(self.L):
            self.layer(l, T, pos0, first=(l == 0))
            if T > 1: self.g.sync()
        self.spos = pos0 + T
        self._rms(self.O, self.R, self.norm, self.X, T, add=True)
        if not want_logits: return None
        for r0, r1, wb in self.lmh:
            if isinstance(wb, tuple):
                self.g._run(self.k_mv8, struct.pack("<4I", self.H, r0, (T - 1) * self.H, r1 - r0), [self.X, wb[1], self.logits, wb[2]],
                            ((r1 - r0 + 7) // 8, 1, 1))
            else: self.g._run(self.k_mv, struct.pack("<4I", self.H, r0, (T - 1) * self.H, 0), [self.X, wb, self.logits], (r1 - r0, 1, 1))
        return self.g.read(self.logits, self.V)

    def forward(self, ids, pos0, want_logits=True):
        """Wie Qwen3Engine.forward. Liegt pos0 nicht am Ende des Zustands, wird er zuerst nachgefuehrt."""
        self._seek(pos0)
        kv = self.kv_ids[:pos0]
        self.kv_ids = kv + [None] * (pos0 - len(kv)) + list(ids)
        return self._block(ids, pos0, want_logits)

    def prefill(self, ids, progress=lambda *a: None, cancelled=lambda: False):
        c = min(common_prefix(self.kv_ids, ids), len(ids) - 1)
        self.reused = c
        if c: progress(f"Kontext: {c} von {len(ids)} Tokens aus dem Cache")
        logits = None; at = self.snap_at if c <= self.snap_at < len(ids) else 0; self.snap_at = 0
        cuts = sorted({*range(c, len(ids), CHUNK), *([at] if at > c else [])}) + [len(ids)]   # v89: Grenze am Vorspann-Ende
        snapped = False
        for s, e in zip(cuts, cuts[1:]):
            if cancelled(): return None
            if at and s == at and self.spos == at: self._snapshot(); snapped = True
            progress(f"Lese Kontext: {e}/{len(ids)} Tokens", s, len(ids))
            logits = self.forward(ids[s:e], s, want_logits=e == len(ids))
        if not snapped: self._snapshot()
        return logits

    def close(self): self.g.close()

    # ---- KV-Cache + Zustand eines festen Vorspanns
    def save_kv(self, path, n):
        sp = self.snap; use_snap = sp and sp[0] == n and self.kv_ids[:n] == sp[1] and self.spos != n   # v89
        if not use_snap: self._seek(n)
        KD = self.NKV * 256; p = Path(path); p.parent.mkdir(parents=True, exist_ok=True); tmp = p.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            hd = json.dumps({"modell": self.tag, "L": self.L, "kd": KD, "ids": self.kv_ids[:n]}).encode()
            f.write(struct.pack("<I", len(hd)) + hd)
            for l in self.full:
                for b in (self.kc[l], self.vc[l]): f.write(self.g.read(b, n * KD // (2 if self.kv16 else 1)).tobytes())
            for l in self.lin:
                st, cv = (self.STs[l], self.CVs[l]) if use_snap else (self.ST[l], self.CV[l])
                f.write(self.g.read(st).tobytes()); f.write(self.g.read(cv).tobytes())
        tmp.replace(p)

    def load_kv(self, path):
        KD = self.NKV * 256
        with open(path, "rb") as f:
            hd = json.loads(f.read(struct.unpack("<I", f.read(4))[0])); n = len(hd["ids"])
            bad = hd.get("modell") != self.tag or hd.get("L") != self.L or hd.get("kd") != KD or n >= self.maxT
            if not bad:
                for l in self.full:
                    for b in (self.kc[l], self.vc[l]): self.g.write(b, f.read(n * KD * (2 if self.kv16 else 4)))
                for l in self.lin:
                    self.g.write(self.ST[l], f.read(32 * 128 * 128 * 4)); self.g.write(self.CV[l], f.read(8192 * 3 * 4))
        if bad:
            try: Path(path).unlink()
            except Exception: pass
            return 0
        self.kv_ids = list(hd["ids"]); self.spos = n; self._snapshot(); return n

    # ---- Selbsttest: neue Kernels gegen Python
    def self_check(self, progress=lambda *a: None):
        rnd = random.Random(1); g = self.g; res = {}
        rv = lambda n, s=1.0: [rnd.uniform(-s, s) for _ in range(n)]
        fb = lambda v: array("f", v).tobytes()
        def rel(a, b):
            m = max(abs(x) for x in a) or 1.0
            return max(abs(x - y) for x, y in zip(a, b)) / m
        def timed(fn, reps=3):
            fn(); g.sync(); t0 = time.perf_counter()
            for _ in range(reps): fn()
            g.sync(); return (time.perf_counter() - t0) / reps
        sig = lambda x: 1 / (1 + math.exp(-x))
        progress("Sprachmodell: Selbsttest Qwen3.5-Kernels ...")
        bufs = {}
        def tmp(name, n, data=None):
            b = bufs.get(name) or bufs.setdefault(name, g.buffer(n))
            if data is not None: g.write(b, fb(data))
            return b
        # 1) Faltung + SiLU
        T, NC = 5, 8192
        x = rv(T * NC); w = rv(NC * 4, 0.5); cs = rv(NC * 3)
        g.write(self.QKV, fb(x)); wb = tmp("w", NC * 4, w); cb = tmp("cs", NC * 3, cs)
        g._run(self.k_conv, struct.pack("<4I", T, NC, 0, 0), [self.QKV, wb, cb], (32, 1, 1))
        got = g.read(self.QKV, T * NC); ref = []
        chans = list(range(64)) + list(range(NC - 64, NC))
        for c in chans:
            hist = cs[c * 3:c * 3 + 3]
            for t in range(T):
                xi = x[t * NC + c]; y = w[c * 4] * hist[0] + w[c * 4 + 1] * hist[1] + w[c * 4 + 2] * hist[2] + w[c * 4 + 3] * xi
                hist = hist[1:] + [xi]; ref.append((t * NC + c, y * sig(y)))
        res["conv_diff"] = rel([v for _, v in ref], [got[i] for i, _ in ref])
        # 2) Delta-Regel (Koepfe 0 und 1)
        T = 3; x = rv(T * 8192); ab = rv(T * 32); bb = rv(T * 32); al = rv(32, 1.0); dt = rv(32, 1.0); st = rv(32 * 16384, 0.1)
        g.write(self.QKV, fb(x)); g.write(self.Ab, fb(ab)); g.write(self.Bb, fb(bb))
        alb, dtb, stb = tmp("al", 32, al), tmp("dt", 32, dt), tmp("st", 32 * 16384, st)
        g._run(self.k_delta, struct.pack("<4I", T, 0, 0, 0), [self.QKV, self.Ab, self.Bb, alb, dtb, stb, self.A], (2, 32, 1))
        got = g.read(self.A, T * 4096); gst = g.read(stb); ref, rg, rs, gs = [], [], [], []
        for h in (0, 1):
            kh = h // 2; S = [st[h * 16384 + k * 128:h * 16384 + k * 128 + 128] for k in range(128)]
            for t in range(T):
                rb = t * 8192; q = x[rb + kh * 128: rb + kh * 128 + 128]; k_ = x[rb + 2048 + kh * 128: rb + 2048 + kh * 128 + 128]
                nq = 1 / math.sqrt(sum(a * a for a in q) + 1e-6) / math.sqrt(128); nk = 1 / math.sqrt(sum(a * a for a in k_) + 1e-6)
                q = [a * nq for a in q]; k_ = [a * nk for a in k_]
                xa = ab[t * 32 + h] + dt[h]; sp = xa if xa > 20 else math.log1p(math.exp(xa))
                gt = math.exp(-math.exp(al[h]) * sp); beta = sig(bb[t * 32 + h])
                for v in range(128):
                    col = [S[kk][v] * gt for kk in range(128)]
                    km = sum(col[kk] * k_[kk] for kk in range(128)); dl = (x[rb + 4096 + h * 128 + v] - km) * beta
                    col = [col[kk] + k_[kk] * dl for kk in range(128)]
                    for kk in range(128): S[kk][v] = col[kk]
                    rg.append(sum(col[kk] * q[kk] for kk in range(128))); ref.append(got[t * 4096 + h * 128 + v])
            for kk in range(128):
                rs.extend(S[kk]); gs.extend(gst[h * 16384 + kk * 128: h * 16384 + kk * 128 + 128])
        res["delta_diff"] = max(rel(rg, ref), rel(rs, gs))
        # 3) gegatete Norm
        T = 2; o = rv(T * 4096); z = rv(T * 4096); gw = rv(128)
        g.write(self.A, fb(o)); g.write(self.Z, fb(z)); gwb = tmp("gw", 128, gw)
        g._run(self.k_gnorm, struct.pack("<IfII", T, self.eps, 0, 0), [self.A, self.Z, gwb], (T, 32, 1))
        got = g.read(self.A, T * 4096); ref = []
        for blk in range(T * 32):
            seg = o[blk * 128:(blk + 1) * 128]; r = 1 / math.sqrt(sum(a * a for a in seg) / 128 + self.eps)
            ref += [seg[i] * r * gw[i] * z[blk * 128 + i] * sig(z[blk * 128 + i]) for i in range(128)]
        res["gnorm_diff"] = rel(ref, got)
        # 4) Q-Norm + RoPE (Abstand 512, Position 5)
        T, NHD, p0 = 2, 3, 5; xq = rv(T * NHD * 512); qw = rv(256)
        g.write(self.QKV, fb(xq)); qwb = tmp("qw", 256, qw)
        g._run(self.k_rope, struct.pack("<IIIfIIII", T, NHD, p0, self.eps, 512, 0, 0, 0), [self.QKV, qwb, self.cs], (T, NHD, 1))
        got = g.read(self.QKV, T * NHD * 512); ref, gg = [], []
        for t in range(T):
            for h in range(NHD):
                b0 = (t * NHD + h) * 512; seg = xq[b0:b0 + 256]; r = 1 / math.sqrt(sum(a * a for a in seg) / 256 + self.eps)
                y = [seg[i] * r * qw[i] for i in range(256)]
                for i in range(32):
                    f = (p0 + t) / self.theta ** (2 * i / 64); c_, s_ = math.cos(f), math.sin(f); u, v = y[i], y[i + 32]
                    y[i], y[i + 32] = u * c_ - v * s_, v * c_ + u * s_
                ref += y + xq[b0 + 256:b0 + 512]; gg += got[b0:b0 + 512]
        res["rope_diff"] = rel(ref, gg)
        # 5) Attention 256 + Gate gegen Python (Kopfgruppe 0), Split-K und ein Teilstueck
        l0 = self.full[0]; KD = self.NKV * 256; T, pos0 = 3, 597
        N = pos0 + T; q = rv(T * self.NH * 512); kk = rv(N * KD); vv = rv(N * KD)
        self._kvw(self.kc[l0], fb(kk)); self._kvw(self.vc[l0], fb(vv))
        out = {}
        for mode in ("split", "one"):
            g.write(self.QKV, fb(q)); self._attn(l0, T, pos0, force=mode); out[mode] = g.read(self.A, T * self.NH * 256)
        ref, gg = [], []
        for t in range(T):
            P_ = pos0 + t
            for h in range(4):
                qb = (t * self.NH + h) * 512; qv = q[qb:qb + 256]
                sc = [sum(qv[d] * kk[j * KD + d] for d in range(256)) / 16 for j in range(P_ + 1)]
                m = max(sc); e = [math.exp(s - m) for s in sc]; zs = sum(e)
                gate = [sig(q[qb + 256 + d]) for d in range(256)]
                ref += [sum(e[j] * vv[j * KD + d] for j in range(P_ + 1)) / zs * gate[d] for d in range(256)]
                gg += out["split"][t * self.NH * 256 + h * 256: t * self.NH * 256 + h * 256 + 256]
        res["attn_diff"] = rel(ref, gg); res["attn_split_one"] = rel(out["split"], out["one"])
        tol_a = 2e-2 if self.kv16 else 1e-3
        # gemm (Einlesen) gegen Split-K
        if self.k_gemm:
            T2, p2 = 64, 512; q2 = rv(T2 * self.NH * 512)
            self._kvw(self.kc[l0], fb(rv((p2 + T2) * KD))); self._kvw(self.vc[l0], fb(rv((p2 + T2) * KD)))
            for mode in ("split", "gemm"):
                g.write(self.QKV, fb(q2)); self._attn(l0, T2, p2, force=mode); out[mode] = g.read(self.A, T2 * self.NH * 256)
            res["gemm_diff"] = rel(out["split"], out["gemm"])
            if res["gemm_diff"] > 1e-3: self.pre_kernel = "split"
        for k_, tol in (("conv_diff", 1e-4), ("delta_diff", 1e-3), ("gnorm_diff", 1e-4), ("rope_diff", 1e-4),
                        ("attn_diff", tol_a), ("attn_split_one", 1e-3)):
            if res[k_] > tol: raise RuntimeError(f"Qwen3.5-Selbsttest: {k_} = {res[k_]:.1e} (Grenze {tol:.0e}) - Kernel rechnet falsch")
        # 6) Tempo Schreiben bei langem Kontext: Split-K gegen ein Teilstueck
        Pd = min(self.maxT, 8192) - 1; blk = fb(rv(KD * 512))
        full = (blk * ((Pd + 1) // 512 + 1))[:(Pd + 1) * KD * 4]
        self._kvw(self.kc[l0], full); self._kvw(self.vc[l0], full); g.write(self.QKV, fb(rv(self.NH * 512)))
        res["dec_split"] = timed(lambda: self._attn(l0, 1, Pd, force="split"))
        res["dec_one"] = timed(lambda: self._attn(l0, 1, Pd, force="one"))
        self.split_on = res["dec_split"] <= res["dec_one"]; self.dec_kernel = self.small_attn = "split" if self.split_on else "one"
        # 7) Tempo Delta-Regel (Schreiben, 1 Token)
        res["delta_1tok"] = timed(lambda: g._run(self.k_delta, struct.pack("<4I", 1, 0, 0, 0),
                                                 [self.QKV, self.Ab, self.Bb, alb, dtb, stb, self.A], (2, 32, 1)))
        for b in bufs.values(): g.free(b)
        progress(f"Qwen3.5-Selbsttest ok: Faltung {res['conv_diff']:.0e}, Delta {res['delta_diff']:.0e}, Norm {res['gnorm_diff']:.0e}, "
                 f"RoPE {res['rope_diff']:.0e}, Attention {res['attn_diff']:.0e}; Schreiben {Pd + 1} Pos.: split "
                 f"{res['dec_split'] * 1000:.2f} ms, eins {res['dec_one'] * 1000:.2f} ms -> {self.dec_kernel}; "
                 f"Delta 1 Token {res['delta_1tok'] * 1000:.2f} ms; Einlesen {self.pre_kernel}")
        self.kv_ids = []; self._reset_state()
        res["gflops_" + self.lin_kernel] = 0.0
        self.bench = res; return res
