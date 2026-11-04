# aura/llm/apertus.py — Version 20261103v165  (AURA)
# Native Engine fuer Apertus 1.5 (nur Textteil) auf DirectX 11. Immer int8-Gewichte und fp16-KV-Cache.
# Aufbau: 32 x [RMSNorm, Q/K-Norm + RoPE llama3, Attention 32 Q / 8 KV Koepfe a 128, RMSNorm, up_proj, xIELU, down_proj].
# Referenz: transformers/models/apertus/modeling_apertus.py (1.0; apertus1p5 ist nicht veroeffentlicht).
# Kein rekurrenter Zustand: Vorspann-Cache und Ruecksprung brauchen nur den KV-Cache.
# Selbsttest: neue Kernels gegen Python, Abbruch bei Abweichung.
import json, math, random, struct, time
from array import array
from pathlib import Path
from ..engine.gpu import GPU
from .qwen import (K_LINEAR2, K_MATVEC, K_MATVEC_T, K_RMS, K_COPY, K_COPY16, K_QUANT, K_MV8, K_MVT8, K_SOFTMAX, K_QKROPE,
                   k_linear8, k_gemm16, ShardedSafeTensors, CHUNK, LMH_ROWS, SMAX_MB)
from .qwen35 import Qwen35Engine, K_LIN8V, K_MVT8B, MAXT, NS_MAX, SPLIT_T

P = "model.language_model."
D = 128

# xIELU in place (Parameter nach softplus). expm1 nahe 0 als Reihe, sonst Ausloeschung in fp32.
K_XIELU = r"""
cbuffer C:register(b0){ uint N; uint STRIDE; float AP; float AN; float BETA; float EPSV; uint P1; uint P2; };
RWStructuredBuffer<float> X:register(u0);
[numthreads(256,1,1)]
void main(uint3 d:SV_DispatchThreadID){
  for(uint i=d.x;i<N;i+=STRIDE){ float x=X[i], y;
    if(x>0) y=AP*x*x+BETA*x;
    else { float m=min(x,EPSV); float e=(m>-0.001)?m*(1.0+m*(0.5+m/6.0)):exp(m)-1.0; y=(e-x)*AN+BETA*x; }
    X[i]=y; }
}"""

# Attention 128, 4 Q-Koepfe je KV-Kopf, fp16-KV (uint = 2 Werte), Online-Softmax in Bloecken zu 128 Positionen.
K_ATTN = r"""
cbuffer C:register(b0){ uint POS0; uint L; uint NH; uint NKV; uint T0; uint P1; uint P2; uint P3; };
RWStructuredBuffer<float> Q:register(u0); RWStructuredBuffer<uint> K:register(u1);
RWStructuredBuffer<uint> V:register(u2); RWStructuredBuffer<float> PO:register(u3);
RWStructuredBuffer<float> ML:register(u4);
groupshared float q[4][128]; groupshared float sc[4][128]; groupshared float rm[4][128];
[numthreads(128,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint s=g.x, kvh=g.y, t=g.z, i=l.x, KH=NKV*64, Pz=POS0+T0+t, h, j, k, a;
  uint jb=s*L, je=min(jb+L, Pz+1), so=(t*%(NS)d+s)*NH;
  [unroll] for(h=0;h<4;h++) q[h][i]=Q[((T0+t)*NH+kvh*4+h)*128+i];
  GroupMemoryBarrierWithGroupSync();
  float m[4], ls[4], acc[4];
  [unroll] for(h=0;h<4;h++){ m[h]=-1e30; ls[h]=0; acc[h]=0; }
  for(uint b0=jb;b0<je;b0+=128){
    uint n=min(128,je-b0); float d[4]; [unroll] for(h=0;h<4;h++) d[h]=0;
    if(i<n){ uint rb=(b0+i)*KH+kvh*64;
      for(k=0;k<64;k++){ uint u=K[rb+k]; float k0=f16tof32(u&0xffff), k1=f16tof32(u>>16);
        [unroll] for(h=0;h<4;h++) d[h]+=q[h][2*k]*k0+q[h][2*k+1]*k1; } }
    [unroll] for(h=0;h<4;h++){ float v=(i<n)?d[h]*0.08838834764831845:-1e30; sc[h][i]=v; rm[h][i]=v; }
    GroupMemoryBarrierWithGroupSync();
    for(a=64;a>0;a>>=1){ if(i<a){ [unroll] for(h=0;h<4;h++) rm[h][i]=max(rm[h][i],rm[h][i+a]); } GroupMemoryBarrierWithGroupSync(); }
    [unroll] for(h=0;h<4;h++){ float bm=max(m[h],rm[h][0]); float f=exp(m[h]-bm); acc[h]*=f; ls[h]*=f; m[h]=bm; }
    [unroll] for(h=0;h<4;h++) sc[h][i]=(i<n)?exp(sc[h][i]-m[h]):0;
    GroupMemoryBarrierWithGroupSync();
    for(j=0;j<n;j++){ uint u=V[(b0+j)*KH+kvh*64+(i>>1)]; float v=f16tof32((i&1)?(u>>16):(u&0xffff));
      [unroll] for(h=0;h<4;h++){ float pr=sc[h][j]; ls[h]+=pr; acc[h]+=pr*v; } }
    GroupMemoryBarrierWithGroupSync();
  }
  [unroll] for(h=0;h<4;h++){ uint qh=kvh*4+h; PO[(so+qh)*128+i]=acc[h];
    if(i==0){ ML[(so+qh)*2]=m[h]; ML[(so+qh)*2+1]=ls[h]; } }
}""" % dict(NS=NS_MAX)

K_MERGE = r"""
cbuffer C:register(b0){ uint NS; uint NH; uint T0; uint P1; };
RWStructuredBuffer<float> PO:register(u0); RWStructuredBuffer<float> ML:register(u1); RWStructuredBuffer<float> O:register(u2);
[numthreads(128,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint h=g.x, t=g.y, i=l.x, s, b=t*%(NS)d; float M=-1e30, num=0, den=0;
  for(s=0;s<NS;s++) M=max(M, ML[((b+s)*NH+h)*2]);
  for(s=0;s<NS;s++){ float f=exp(ML[((b+s)*NH+h)*2]-M); num+=f*PO[((b+s)*NH+h)*128+i]; den+=f*ML[((b+s)*NH+h)*2+1]; }
  O[(T0+t)*NH*128+h*128+i]=num/den;
}""" % dict(NS=NS_MAX)

def softplus(x): return math.log1p(math.exp(x))

def llama3_freqs(c):
    """Inverse Frequenzen wie transformers _compute_llama3_parameters."""
    r = c["rope_parameters"]; base, dim = r["rope_theta"], D
    inv = [1.0 / base ** (i / dim) for i in range(0, dim, 2)]
    f, lo_f, hi_f, old = r["factor"], r["low_freq_factor"], r["high_freq_factor"], r["original_max_position_embeddings"]
    lw, hw = old / lo_f, old / hi_f; out = []
    for v in inv:
        w = 2 * math.pi / v; ll = v / f if w > lw else v
        if hw <= w <= lw:
            sf = (old / w - lo_f) / (hi_f - lo_f); ll = (1 - sf) * ll / f + sf * ll
        out.append(ll)
    return out

class ApertusEngine(Qwen35Engine):
    def __init__(self, model_dir, progress=lambda *a: None, maxT=MAXT):
        self.dir = Path(model_dir)
        full = json.loads((self.dir / "config.json").read_text(encoding="utf-8"))
        c = self.cfg = full.get("text_config", full)
        self.H, self.I, self.L = c["hidden_size"], c["intermediate_size"], c["num_hidden_layers"]
        self.NH, self.NKV, self.D = c["num_attention_heads"], c["num_key_value_heads"], D
        self.eps, self.V = c.get("rms_norm_eps", 1e-5), c["output_vocab_size"]
        if self.H // self.NH != D or self.NH // self.NKV != 4 or self.H % 128 or self.I % 128 or not c.get("qk_norm"):
            raise ValueError("Apertus-Engine erwartet head_dim 128, 4 Q- je KV-Kopf und qk_norm")
        self.maxT = min(maxT, MAXT)
        self.st = st = ShardedSafeTensors(self.dir)
        g = self.g = GPU(); sh = g._shader
        H, I, C = self.H, self.I, CHUNK
        self.kv16 = True; self.q8 = True; self.q4 = False
        self.k_lin2, self.k_mv, self.k_mt, self.k_rms, self.k_copy = sh(K_LINEAR2), sh(K_MATVEC), sh(K_MATVEC_T), sh(K_RMS), sh(K_COPY)
        self.k_copy16, self.k_rope, self.k_xielu = sh(K_COPY16), sh(K_QKROPE), sh(K_XIELU)
        self.k_attn, self.k_merge = sh(K_ATTN), sh(K_MERGE)
        self.k_quant, self.k_mv8, self.k_mvt8, self.k_lin8 = sh(K_QUANT), sh(K_MV8), sh(K_MVT8), sh(k_linear8(4, 4))
        self.k_lin8v = self.k_mvt8b = self.k_gemm = None
        try: self.k_lin8v = sh(K_LIN8V)
        except Exception as e: progress(f"Einlesen v8 nicht verfuegbar: {e}")
        try: self.k_mvt8b = sh(K_MVT8B)
        except Exception as e: progress(f"Kleine Bloecke b nicht verfuegbar: {e}")
        try: self.k_gemm = (sh(k_gemm16(False)), sh(k_gemm16(True)), sh(K_SOFTMAX))
        except Exception as e: progress(f"Attention gemm nicht verfuegbar: {e}")
        self.small8 = "mvt8"; self.small4 = "mt4"; self.lin_kernel = "q44"; self.small_kernel = "mt"
        self.pre_kernel = "gemm" if self.k_gemm else "split"; self.dec_kernel = "split"
        self.attn_kernel = "attn128"; self.prof = None; self.split_on = True; self.snap_at = 0
        self.tag = self.dir.name + "-int8-kv16-apertus"
        self.lmh_rows = min(LMH_ROWS, max(64, 120_000_000 // (H * 2) // 64 * 64))
        self.stg = g.buffer(max(self.lmh_rows * H, I * H) // 2)
        up = lambda k: self._quant(st.raw(k), *st.shape(k)[:2])
        upf = lambda k: (lambda b: g.buffer(len(b) // 4, b))(st.f32(k))
        def one(k):
            a = array("f"); a.frombytes(st.f32(k)); return a[0]
        self.w = []
        for l in range(self.L):
            p = P + "layers.%d." % l; a = p + "self_attn."; progress(f"Lade Sprachmodell: Schicht {l + 1}/{self.L}", l, self.L)
            d = {n: up(a + n + ".weight") for n in ("q_proj", "k_proj", "v_proj", "o_proj")}
            d["up_proj"], d["down_proj"] = up(p + "mlp.up_proj.weight"), up(p + "mlp.down_proj.weight")
            d["q_norm"], d["k_norm"] = upf(a + "q_norm.weight"), upf(a + "k_norm.weight")
            d["in_norm"], d["ff_norm"] = upf(p + "attention_layernorm.weight"), upf(p + "feedforward_layernorm.weight")
            f = p + "mlp.act_fn."; beta = one(f + "beta")
            d["act"] = (softplus(one(f + "alpha_p")), beta + softplus(one(f + "alpha_n")), beta, one(f + "eps"))
            self.w.append(d)
        self.norm = upf(P + "norm.weight")
        progress("Lade Sprachmodell: Ausgabeschicht", self.L, self.L)
        self.row_bytes = H * 2; hr = st.raw("lm_head.weight"); self.lmh = []
        for r0 in range(0, self.V, self.lmh_rows):
            r1 = min(self.V, r0 + self.lmh_rows)
            self.lmh.append((r0, r1, self._quant(hr[r0 * self.row_bytes: r1 * self.row_bytes], r1 - r0, H)))
        g.free(self.stg); self.stg = None
        self.emb_raw = bytes(st.raw(P + "embed_tokens.weight")[:self.V * self.row_bytes])   # nur Text-Tokens (spart ~1,1 GB)
        del hr
        self._release_files(progress)
        cs = array("f")
        self.inv = inv = llama3_freqs(c)
        for p_ in range(self.maxT):
            for f in inv: cs.append(math.cos(p_ * f)); cs.append(math.sin(p_ * f))
        self.cs = g.buffer(len(cs), cs.tobytes())
        QD, KD = self.NH * D, self.NKV * D
        self.R, self.X, self.O = g.buffer(C * H), g.buffer(C * H), g.buffer(C * H)
        self.QKV, self.A, self.K, self.Vb = g.buffer(C * QD), g.buffer(C * QD), g.buffer(C * KD), g.buffer(C * KD)
        self.Up = g.buffer(C * I)
        self.full = list(range(self.L)); self.lin = []
        kvn = self.maxT * KD // 2
        self.kc = {l: g.buffer(kvn) for l in self.full}; self.vc = {l: g.buffer(kvn) for l in self.full}
        self.PO, self.ML = g.buffer(SPLIT_T * NS_MAX * self.NH * D), g.buffer(SPLIT_T * NS_MAX * self.NH * 2)
        if self.k_gemm:
            self.nb = max(1, min(self.NH, SMAX_MB * 1_000_000 // (C * self.maxT * 4)))
            self.S = g.buffer(self.nb * C * self.maxT)
        self.logits = g.buffer(self.V)
        self.kv_ids, self.reused, self.spos, self.snap = [], 0, 0, None

    # ---- kein rekurrenter Zustand
    def _reset_state(self): self.spos = 0
    def _snapshot(self): pass
    def _seek(self, p): pass

    def _attn(self, l, T, pos0, force=None):
        mode = force or ("gemm" if (T >= 64 and self.k_gemm and self.pre_kernel == "gemm") else "split"); g = self.g
        if mode == "gemm":
            kt, kn, ks = self.k_gemm; N = pos0 + T; QD, KD = self.NH * D, self.NKV * D
            for h0 in range(0, self.NH, self.nb):
                nz = min(self.nb, self.NH - h0)
                g._run(kt, struct.pack("<16I", T, N, D, QD, KD, N, h0, 4, D, 0, D, 0, T * N, 0, 0, 0),
                       [self.QKV, self.kc[l], self.S], ((N + 63) // 64, (T + 127) // 128, nz))
                g._run(ks, struct.pack("<4I", T, N, N, pos0), [self.S], (T, nz, 1))
                g._run(kn, struct.pack("<16I", T, D, N, N, KD, QD, h0, 4, 0, T * N, D, D, 0, 0, 0, 0),
                       [self.S, self.vc[l], self.A], (2, (T + 127) // 128, nz))
        else:
            for t0 in range(0, T, SPLIT_T):
                tt = min(SPLIT_T, T - t0); n = pos0 + t0 + tt
                L = max(128, (-(-n // NS_MAX) + 127) // 128 * 128) if self.split_on and mode != "one" and n >= 512 else n
                ns = -(-n // L)
                g._run(self.k_attn, struct.pack("<8I", pos0, L, self.NH, self.NKV, t0, 0, 0, 0),
                       [self.QKV, self.kc[l], self.vc[l], self.PO, self.ML], (ns, self.NKV, tt))
                g._run(self.k_merge, struct.pack("<4I", ns, self.NH, t0, 0), [self.PO, self.ML, self.A], (self.NH, tt, 1))
        self._tick("attention")

    def layer(self, l, T, pos0, first):
        w, g, H, I, KD = self.w[l], self.g, self.H, self.I, self.NKV * D
        self._rms(self.O, self.R, w["in_norm"], self.X, T, add=not first)
        self._lin(self.X, w["q_proj"], self.QKV, T, H, self.NH * D)
        self._lin(self.X, w["k_proj"], self.K, T, H, KD)
        self._lin(self.X, w["v_proj"], self.Vb, T, H, KD)
        g._run(self.k_rope, struct.pack("<IIIf", T, self.NH, pos0, self.eps), [self.QKV, w["q_norm"], self.cs], (T, self.NH, 1))
        g._run(self.k_rope, struct.pack("<IIIf", T, self.NKV, pos0, self.eps), [self.K, w["k_norm"], self.cs], (T, self.NKV, 1))
        self._copykv(self.K, self.kc[l], T * KD, pos0 * KD); self._copykv(self.Vb, self.vc[l], T * KD, pos0 * KD)
        self._attn(l, T, pos0)
        self._lin(self.A, w["o_proj"], self.O, T, self.NH * D, H)
        self._rms(self.O, self.R, w["ff_norm"], self.X, T, add=True)
        self._lin(self.X, w["up_proj"], self.Up, T, H, I)
        self._act(self.Up, T * I, w["act"]); self._tick("andere")
        self._lin(self.Up, w["down_proj"], self.O, T, I, H)

    def _act(self, b, n, a):
        groups = min((n + 255) // 256, 65535)
        self.g._run(self.k_xielu, struct.pack("<2I4f2I", n, groups * 256, *a, 0, 0), [b], (groups, 1, 1))

    def save_kv(self, path, n):
        KD = self.NKV * D; p = Path(path); p.parent.mkdir(parents=True, exist_ok=True); tmp = p.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            hd = json.dumps({"modell": self.tag, "L": self.L, "kd": KD, "ids": self.kv_ids[:n]}).encode()
            f.write(struct.pack("<I", len(hd)) + hd)
            for l in self.full:
                for b in (self.kc[l], self.vc[l]): f.write(self.g.read(b, n * KD // 2).tobytes())
        tmp.replace(p)

    def load_kv(self, path):
        KD = self.NKV * D
        with open(path, "rb") as f:
            hd = json.loads(f.read(struct.unpack("<I", f.read(4))[0])); n = len(hd["ids"])
            bad = hd.get("modell") != self.tag or hd.get("L") != self.L or hd.get("kd") != KD or n >= self.maxT
            if not bad:
                for l in self.full:
                    for b in (self.kc[l], self.vc[l]): self.g.write(b, f.read(n * KD * 2))
        if bad:
            try: Path(path).unlink()
            except Exception: pass
            return 0
        self.kv_ids = list(hd["ids"]); self.spos = n; return n

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
        progress("Sprachmodell: Selbsttest Apertus-Kernels ...")
        # 1) xIELU
        a = self.w[0]["act"]; x = rv(4096, 3.0) + [0.0, -1e-7, 1e-7, -2e-3, -30.0]; n = len(x)
        g.write(self.Up, fb(x)); self._act(self.Up, n, a); got = g.read(self.Up, n)
        res["xielu_diff"] = rel([a[0] * v * v + a[2] * v if v > 0 else (math.expm1(min(v, a[3])) - v) * a[1] + a[2] * v for v in x], got)
        # 2) Q-Norm + RoPE
        T, NHD, p0 = 2, 3, 5; xq = rv(T * NHD * D); qw = rv(D); qwb = g.buffer(D, fb(qw))
        g.write(self.QKV, fb(xq))
        g._run(self.k_rope, struct.pack("<IIIf", T, NHD, p0, self.eps), [self.QKV, qwb, self.cs], (T, NHD, 1))
        got = g.read(self.QKV, T * NHD * D); ref = []
        for t in range(T):
            for h in range(NHD):
                b0 = (t * NHD + h) * D; seg = xq[b0:b0 + D]; r = 1 / math.sqrt(sum(v * v for v in seg) / D + self.eps)
                y = [seg[i] * r * qw[i] for i in range(D)]
                for i in range(64):
                    f = (p0 + t) * self.inv[i]; c_, s_ = math.cos(f), math.sin(f); u, v = y[i], y[i + 64]
                    y[i], y[i + 64] = u * c_ - v * s_, v * c_ + u * s_
                ref += y
        res["rope_diff"] = rel(ref, got); g.free(qwb)
        # 3) Attention gegen Python (erste Kopfgruppe), Split-K gegen ein Teilstueck
        l0 = 0; KD = self.NKV * D; QD = self.NH * D; T, pos0 = 3, 597; N = pos0 + T
        q = rv(T * QD); kk = rv(N * KD); vv = rv(N * KD)
        self._kvw(self.kc[l0], fb(kk)); self._kvw(self.vc[l0], fb(vv)); g.write(self.QKV, fb(q)); out = {}
        for mode in ("split", "one"):
            self._attn(l0, T, pos0, force=mode); out[mode] = g.read(self.A, T * QD)
        ref, gg = [], []
        for t in range(T):
            Pz = pos0 + t
            for h in range(4):
                qb = (t * self.NH + h) * D; qv = q[qb:qb + D]
                sc = [sum(qv[d] * kk[j * KD + d] for d in range(D)) * D ** -0.5 for j in range(Pz + 1)]
                m = max(sc); e = [math.exp(s - m) for s in sc]; zs = sum(e)
                ref += [sum(e[j] * vv[j * KD + d] for j in range(Pz + 1)) / zs for d in range(D)]
                gg += out["split"][qb:qb + D]
        res["attn_diff"] = rel(ref, gg); res["attn_split_one"] = rel(out["split"], out["one"])
        if self.k_gemm:
            T2, p2 = 64, 512; g.write(self.QKV, fb(rv(T2 * QD)))
            self._kvw(self.kc[l0], fb(rv((p2 + T2) * KD))); self._kvw(self.vc[l0], fb(rv((p2 + T2) * KD)))
            for mode in ("split", "gemm"):
                self._attn(l0, T2, p2, force=mode); out[mode] = g.read(self.A, T2 * QD)
            res["gemm_diff"] = rel(out["split"], out["gemm"])
            if res["gemm_diff"] > 1e-3: self.pre_kernel = "split"
        for k_, tol in (("xielu_diff", 1e-4), ("rope_diff", 1e-4), ("attn_diff", 2e-2), ("attn_split_one", 1e-3)):
            if res[k_] > tol: raise RuntimeError(f"Apertus-Selbsttest: {k_} = {res[k_]:.1e} (Grenze {tol:.0e}) - Kernel rechnet falsch")
        # 4) Tempo Schreiben: Split-K gegen ein Teilstueck
        Pd = min(self.maxT, 8192) - 1; blk = fb(rv(KD * 512)); full = (blk * ((Pd + 1) // 512 + 1))[:(Pd + 1) * KD * 4]
        self._kvw(self.kc[l0], full); self._kvw(self.vc[l0], full); g.write(self.QKV, fb(rv(QD)))
        res["dec_split"] = timed(lambda: self._attn(l0, 1, Pd, force="split"))
        res["dec_one"] = timed(lambda: self._attn(l0, 1, Pd, force="one"))
        self.split_on = res["dec_split"] <= res["dec_one"]; self.dec_kernel = "split" if self.split_on else "one"
        # 5) int8-Varianten: v8 und b nur, wenn gleich und schneller
        H, I = self.H, self.I; up = self.w[0]["up_proj"]
        def alt(name, ref_k, new_k, T):
            g.write(self.X, fb(rv(T * H))); o = []; ts = []
            for k in (ref_k, new_k):
                setattr(self, name, k); self._lin(self.X, up, self.Up, T, H, I); o.append(g.read(self.Up, T * I))
                ts.append(timed(lambda: self._lin(self.X, up, self.Up, T, H, I), 2))
            ok = rel(o[0], o[1]) < 1e-4 and ts[1] < ts[0]; setattr(self, name, new_k if ok else ref_k)
        if self.k_lin8v: alt("lin_kernel", "q44", "v8", 200)
        if self.k_mvt8b: alt("small8", "mvt8", "b", 10)
        self.small_kernel = self.small8
        progress(f"Apertus-Selbsttest ok: xIELU {res['xielu_diff']:.0e}, RoPE {res['rope_diff']:.0e}, Attention {res['attn_diff']:.0e}, "
                 f"gemm {res.get('gemm_diff', 0):.0e}; Schreiben {Pd + 1} Pos. {min(res['dec_split'], res['dec_one']) * 1000:.2f} ms")
        self.kv_ids = []; self._reset_state(); self.bench = res
        return res
