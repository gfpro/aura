# engine/gpu.py — Version 20261010v44  (AURA)  v44: zweiter Konstantenpuffer mit 16 Werten (64 Bytes)
# Native GPU-Engine fuer multilingual-e5-large: DirectX 11 Compute ueber ctypes, keine Installation.
# Bausteine: Linear(+GELU), Add+LayerNorm, Self-Attention. Batch = 1 Text, max. 512 Tokens.

import ctypes, struct, time
from array import array
from ctypes import POINTER, WINFUNCTYPE, byref, c_void_p, c_long, c_uint, c_size_t

_PROTO = {}
def _com(obj, idx, argtypes, *args, restype=c_long):
    key = (restype, tuple(argtypes))                       # Funktionsprototypen zwischenspeichern (spart Zeit pro Aufruf)
    proto = _PROTO.get(key) or _PROTO.setdefault(key, WINFUNCTYPE(restype, c_void_p, *argtypes))
    vtbl = ctypes.cast(obj, POINTER(c_void_p)).contents.value
    fn = ctypes.cast(vtbl, POINTER(c_void_p))[idx]
    return proto(fn)(obj, *args)

def _chk(hr, what):
    if hr < 0: raise RuntimeError("%s: HRESULT 0x%08X" % (what, hr & 0xFFFFFFFF))

class DeviceLost(RuntimeError):
    """Windows hat das GPU-Geraet zurueckgesetzt (Treiber-Reset, Ruhezustand, Bildschirmwechsel ...).
    Abhilfe: neues GPU-Objekt erzeugen und Gewichte neu laden (macht der Embedder automatisch)."""

_LOST = {0x887A0005: "Geraet entfernt", 0x887A0006: "GPU haengt (Timeout)", 0x887A0007: "Treiber-Reset (TDR)",
         0x887A0020: "interner Treiberfehler", 0x887A0021: "Treiber-Update/Neustart noetig"}

class _BD(ctypes.Structure):
    _fields_ = [("w", c_uint), ("usage", c_uint), ("bind", c_uint), ("cpu", c_uint), ("misc", c_uint), ("stride", c_uint)]
class _SD(ctypes.Structure):
    _fields_ = [("p", c_void_p), ("a", c_uint), ("b", c_uint)]
class _UD(ctypes.Structure):
    _fields_ = [("fmt", c_uint), ("dim", c_uint), ("first", c_uint), ("num", c_uint), ("flags", c_uint)]
class _QD(ctypes.Structure):
    _fields_ = [("q", c_uint), ("m", c_uint)]
class _MS(ctypes.Structure):
    _fields_ = [("p", c_void_p), ("r", c_uint), ("d", c_uint)]

_HLSL_LINEAR = r"""
cbuffer C:register(b0){ uint T; uint IN; uint OUT; uint FLAGS; };
RWStructuredBuffer<float> X:register(u0); RWStructuredBuffer<float> W:register(u1);
RWStructuredBuffer<float> Bv:register(u2); RWStructuredBuffer<float> Y:register(u3);
groupshared float As[16][17]; groupshared float Ws[16][17];
float erf_(float x){ float s=sign(x); x=abs(x); float t=1.0/(1.0+0.3275911*x);
  return s*(1.0-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*exp(-x*x)); }
[numthreads(16,16,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint o0=g.x*16, t0=g.y*16, tx=l.x, ty=l.y; float acc=0;
  for(uint k=0;k<IN;k+=16){
    uint kk=k+tx, t=t0+ty, o=o0+ty;
    As[ty][tx]=(t<T&&kk<IN)?X[t*IN+kk]:0;
    Ws[ty][tx]=(o<OUT&&kk<IN)?W[o*IN+kk]:0;
    GroupMemoryBarrierWithGroupSync();
    [unroll] for(uint j=0;j<16;j++) acc+=As[ty][j]*Ws[tx][j];
    GroupMemoryBarrierWithGroupSync();
  }
  uint t=t0+ty, o=o0+tx;
  if(t<T&&o<OUT){ float v=acc+Bv[o]; if(FLAGS&1) v=0.5*v*(1.0+erf_(v*0.70710678)); Y[t*OUT+o]=v; }
}"""

_HLSL_LN = r"""
cbuffer C:register(b0){ uint T; uint H; float EPS; uint PAD; };
RWStructuredBuffer<float> A:register(u0); RWStructuredBuffer<float> R:register(u1);
RWStructuredBuffer<float> G:register(u2); RWStructuredBuffer<float> Bv:register(u3);
RWStructuredBuffer<float> Y:register(u4);
groupshared float red[256];
[numthreads(256,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint t=g.x, i=l.x, k; float s=0;
  for(k=i;k<H;k+=256) s+=A[t*H+k]+R[t*H+k];
  red[i]=s; GroupMemoryBarrierWithGroupSync();
  for(uint a=128;a>0;a>>=1){ if(i<a) red[i]+=red[i+a]; GroupMemoryBarrierWithGroupSync(); }
  float mu=red[0]/H; GroupMemoryBarrierWithGroupSync();
  float v=0; for(k=i;k<H;k+=256){ float d=A[t*H+k]+R[t*H+k]-mu; v+=d*d; }
  red[i]=v; GroupMemoryBarrierWithGroupSync();
  for(uint b=128;b>0;b>>=1){ if(i<b) red[i]+=red[i+b]; GroupMemoryBarrierWithGroupSync(); }
  float r=rsqrt(red[0]/H+EPS);
  for(k=i;k<H;k+=256) Y[t*H+k]=(A[t*H+k]+R[t*H+k]-mu)*r*G[k]+Bv[k];
}"""

_HLSL_ATTN = r"""
cbuffer C:register(b0){ uint T; uint H; uint NH; uint D; };
RWStructuredBuffer<float> Q:register(u0); RWStructuredBuffer<float> K:register(u1);
RWStructuredBuffer<float> V:register(u2); RWStructuredBuffer<float> O:register(u3);
groupshared float q[64]; groupshared float s[512]; groupshared float red[64];
[numthreads(64,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint t=g.x, off=g.y*D, i=l.x, j, k, a;
  q[i]=Q[t*H+off+i]; GroupMemoryBarrierWithGroupSync();
  float sc=rsqrt((float)D), m=-1e30;
  for(j=i;j<T;j+=64){ float d=0; for(k=0;k<D;k++) d+=q[k]*K[j*H+off+k]; d*=sc; s[j]=d; m=max(m,d); }
  red[i]=m; GroupMemoryBarrierWithGroupSync();
  for(a=32;a>0;a>>=1){ if(i<a) red[i]=max(red[i],red[i+a]); GroupMemoryBarrierWithGroupSync(); }
  m=red[0]; GroupMemoryBarrierWithGroupSync();
  float z=0; for(j=i;j<T;j+=64){ float e=exp(s[j]-m); s[j]=e; z+=e; }
  red[i]=z; GroupMemoryBarrierWithGroupSync();
  for(a=32;a>0;a>>=1){ if(i<a) red[i]+=red[i+a]; GroupMemoryBarrierWithGroupSync(); }
  z=red[0];
  float acc=0; for(j=0;j<T;j++) acc+=s[j]*V[j*H+off+i];
  O[t*H+off+i]=acc/z;
}"""

class GPU:
    def __init__(self):
        self._objs = []                                            # alle COM-Objekte -> close() gibt sie frei
        self.d3d = ctypes.WinDLL("d3d11.dll"); self.comp = ctypes.WinDLL("D3DCompiler_47.dll")
        self.dev, self.ctx, fl = c_void_p(), c_void_p(), c_uint()
        _chk(self.d3d.D3D11CreateDevice(None, 1, None, 0, None, 0, 7, byref(self.dev), byref(fl), byref(self.ctx)), "D3D11CreateDevice")
        self.staging = {}                                          # Zuruecklese-Puffer je Groesse (wiederverwendet)
        self.cb = self._buf(_BD(16, 0, 0x4, 0, 0, 0), None)      # Konstantenpuffer (4 Werte)
        self.cb64 = self._buf(_BD(64, 0, 0x4, 0, 0, 0), None)    # v44: Konstantenpuffer (16 Werte)
        q = c_void_p()
        _chk(_com(self.dev, 24, [POINTER(_QD), POINTER(c_void_p)], byref(_QD(0, 0)), byref(q)), "CreateQuery")
        self.query = q; self._objs.append(q)
        self.k_lin = self._shader(_HLSL_LINEAR); self.k_ln = self._shader(_HLSL_LN); self.k_attn = self._shader(_HLSL_ATTN)

    def _ok(self, hr, what):
        h = hr & 0xFFFFFFFF
        if h in _LOST:
            r = _com(self.dev, 39, []) & 0xFFFFFFFF              # GetDeviceRemovedReason
            raise DeviceLost(f"{what}: {_LOST[h]} - Grund: {_LOST.get(r, hex(r))}")
        _chk(hr, what)

    def _buf(self, desc, init):
        b = c_void_p()
        sd = _SD(ctypes.addressof(init), 0, 0) if init is not None else None
        self._ok(_com(self.dev, 3, [POINTER(_BD), c_void_p, POINTER(c_void_p)], byref(desc),
                      byref(sd) if sd else None, byref(b)), "CreateBuffer")
        self._objs.append(b); return b

    def _shader(self, src):
        src = src.encode(); blob, err = c_void_p(), c_void_p()
        hr = self.comp.D3DCompile(src, c_size_t(len(src)), None, None, None, b"main", b"cs_5_0",
                                  c_uint(1 << 15), c_uint(0), byref(blob), byref(err))
        if hr < 0:
            msg = ctypes.string_at(_com(err, 3, [], restype=c_void_p)).decode(errors="replace") if err.value else ""
            raise RuntimeError("Shader-Fehler: " + msg)
        cs = c_void_p()
        _chk(_com(self.dev, 18, [c_void_p, c_size_t, c_void_p, POINTER(c_void_p)],
                  _com(blob, 3, [], restype=c_void_p), _com(blob, 4, [], restype=c_size_t), None, byref(cs)), "CreateComputeShader")
        for o in (blob, err):
            if o.value: _com(o, 2, [], restype=c_uint)
        self._objs.append(cs); return cs

    def close(self):
        """Gibt allen GPU-Speicher frei (sonst bleibt er bis zum Programmende belegt)."""
        if not getattr(self, "dev", None) or not self.dev.value: return
        try: _com(self.ctx, 110, [], restype=None); _com(self.ctx, 111, [], restype=None)   # ClearState, Flush
        except Exception: pass
        for o in reversed(self._objs):
            try:
                if o.value: _com(o, 2, [], restype=c_uint)
            except Exception: pass
        for o in (self.ctx, self.dev):
            try: _com(o, 2, [], restype=c_uint)
            except Exception: pass
        self._objs = []; self.staging = {}; self.dev = c_void_p(); self.ctx = c_void_p()

    def buffer(self, n, data=None):
        """GPU-Puffer fuer n Floats; data = bytes-artig (z.B. memoryview aus safetensors)."""
        init = (ctypes.c_char * (n * 4)).from_buffer_copy(data) if data is not None else None
        b = self._buf(_BD(n * 4, 0, 0x80, 0, 0x40, 4), init)
        v = c_void_p()
        self._ok(_com(self.dev, 8, [c_void_p, POINTER(_UD), POINTER(c_void_p)], b, byref(_UD(0, 1, 0, n, 0)), byref(v)), "CreateUAV")
        self._objs.append(v); return {"buf": b, "uav": v, "n": n}

    def write(self, b, data):
        """Schreibt data an den Anfang des Puffers (Box noetig, sonst liest D3D die volle Puffergroesse)."""
        box = (c_uint * 6)(0, 0, 0, len(data), 1, 1)
        _com(self.ctx, 48, [c_void_p, c_uint, c_void_p, c_void_p, c_uint, c_uint],
             b["buf"], 0, box, (ctypes.c_char * len(data)).from_buffer_copy(data), 0, 0)

    def read(self, b, n=None):
        n = n or b["n"]; full = b["n"]
        st = self.staging.get(full)
        if st is None: st = self.staging[full] = self._buf(_BD(full * 4, 3, 0, 0x20000, 0x40, 4), None)
        _com(self.ctx, 47, [c_void_p, c_void_p], st, b["buf"])
        m = _MS()
        self._ok(_com(self.ctx, 14, [c_void_p, c_uint, c_uint, c_uint, POINTER(_MS)], st, 0, 1, 0, byref(m)), "Map")
        out = array("f"); out.frombytes(ctypes.string_at(m.p, n * 4))
        _com(self.ctx, 15, [c_void_p, c_uint], st, 0)
        return out

    def _run(self, cs, cbytes, bufs, groups):
        cb = self.cb if len(cbytes) <= 16 else self.cb64            # v44: mehr als 4 Werte -> 64-Byte-Puffer
        if cb is self.cb64: cbytes = cbytes.ljust(64, b"\0")
        _com(self.ctx, 48, [c_void_p, c_uint, c_void_p, c_void_p, c_uint, c_uint],
             cb, 0, None, ctypes.c_char_p(cbytes), 0, 0)
        _com(self.ctx, 69, [c_void_p, c_void_p, c_uint], cs, None, 0)
        cbs = (c_void_p * 1)(cb.value)
        _com(self.ctx, 71, [c_uint, c_uint, c_void_p], 0, 1, cbs)
        uavs = (c_void_p * 8)(*([b["uav"].value for b in bufs] + [None] * (8 - len(bufs))))
        _com(self.ctx, 68, [c_uint, c_uint, c_void_p, c_void_p], 0, 8, uavs, None)
        _com(self.ctx, 41, [c_uint, c_uint, c_uint], *groups)

    def linear(self, x, w, b, y, T, IN, OUT, gelu=False):
        self._run(self.k_lin, struct.pack("<4I", T, IN, OUT, 1 if gelu else 0), [x, w, b, y],
                  ((OUT + 15) // 16, (T + 15) // 16, 1))
    def add_ln(self, a, r, g, b, y, T, H, eps):
        self._run(self.k_ln, struct.pack("<IIfI", T, H, eps, 0), [a, r, g, b, y], (T, 1, 1))
    def attention(self, q, k, v, o, T, H, NH):
        self._run(self.k_attn, struct.pack("<4I", T, H, NH, H // NH), [q, k, v, o], (T, NH, 1))

    def sync(self):
        _com(self.ctx, 28, [c_void_p], self.query); _com(self.ctx, 111, [])
        done = ctypes.c_int()
        while True:
            hr = _com(self.ctx, 29, [c_void_p, c_void_p, c_uint, c_uint], self.query, byref(done), 4, 0)
            if hr == 0: break
            if hr < 0: self._ok(hr, "GetData")             # Geraet verloren -> DeviceLost statt Endlosschleife

class Encoder:
    """multilingual-e5-large auf der GPU. Embedding-Schicht laeuft auf der CPU (siehe weights.py)."""
    NAMES = ["attention.self.query", "attention.self.key", "attention.self.value", "attention.output.dense",
             "attention.output.LayerNorm", "intermediate.dense", "output.dense", "output.LayerNorm"]

    def __init__(self, model, gpu=None, layers=None, maxT=512):
        self.m, self.g = model, gpu or GPU()
        c = model.cfg; self.H, self.I, self.NH = c["hidden_size"], c["intermediate_size"], c["num_attention_heads"]
        self.L = layers if layers is not None else c["num_hidden_layers"]
        self.eps = model.eps; self.maxT = maxT
        st, g = model.st, self.g
        self.w = []
        for l in range(self.L):
            p = f"encoder.layer.{l}."; d = {}
            for nm in self.NAMES:
                for part in ("weight", "bias"):
                    k = p + nm + "." + part
                    d[nm + "." + part] = g.buffer(len(st.raw(k)) // 4, st.raw(k))
            self.w.append(d)
        H, I = self.H, self.I
        self.x, self.q, self.k, self.v, self.a, self.o, self.x1, self.f = (g.buffer(maxT * H) for _ in range(8))
        self.h = g.buffer(maxT * I)

    def layer(self, l, T):
        g, w, H, I = self.g, self.w[l], self.H, self.I
        g.linear(self.x, w["attention.self.query.weight"], w["attention.self.query.bias"], self.q, T, H, H)
        g.linear(self.x, w["attention.self.key.weight"], w["attention.self.key.bias"], self.k, T, H, H)
        g.linear(self.x, w["attention.self.value.weight"], w["attention.self.value.bias"], self.v, T, H, H)
        g.attention(self.q, self.k, self.v, self.a, T, H, self.NH)
        g.linear(self.a, w["attention.output.dense.weight"], w["attention.output.dense.bias"], self.o, T, H, H)
        g.add_ln(self.o, self.x, w["attention.output.LayerNorm.weight"], w["attention.output.LayerNorm.bias"], self.x1, T, H, self.eps)
        g.linear(self.x1, w["intermediate.dense.weight"], w["intermediate.dense.bias"], self.h, T, H, I, gelu=True)
        g.linear(self.h, w["output.dense.weight"], w["output.dense.bias"], self.f, T, I, H)
        g.add_ln(self.f, self.x1, w["output.LayerNorm.weight"], w["output.LayerNorm.bias"], self.x, T, H, self.eps)

    def hidden(self, ids):
        """Letzte Schicht fuer alle Tokens: array('f') T*H."""
        T = min(len(ids), self.maxT); ids = ids[:T]
        self.g.write(self.x, self.m.embed(ids).tobytes())
        for l in range(self.L): self.layer(l, T)
        return self.g.read(self.x, T * self.H)

    def embed(self, ids):
        """e5-Satzvektor: Mittelwert ueber alle Tokens, dann L2-normiert (wie im Browser)."""
        hs = self.hidden(ids); H = self.H; T = len(hs) // H
        v = [sum(hs[t * H + k] for t in range(T)) / T for k in range(H)]
        n = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / n for x in v]
