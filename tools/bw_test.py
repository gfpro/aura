# tools/bw_test.py - v1 (20261014): Wie viel Speicherbandbreite schafft die GPU, und wie nah kommt K_MV8 heran?
# Aendert nichts an AURA. AURA vorher schliessen.  Aufruf:  py tools\bw_test.py
# 1) Lese-Test (Decke)  2) Matvec int8 in Varianten (Zeilen je Gruppe, X im Gruppenspeicher), Ergebnis gegen K_MV8
# 3) Kosten eines leeren Kernel-Aufrufs (Python + Treiber)
import os, sys, time, struct, random
sys.path.insert(0, r"C:\aura")
from array import array
from pathlib import Path
from aura.engine.gpu import GPU
from aura.llm.qwen import K_MV8, _I8

OUT_F = Path(r"C:\aura\tools\bw_test.txt"); zeilen = []
def log(s): print(s); zeilen.append(s)
g = GPU()

def timed(fn, reps):
    fn(); g.sync(); t = time.perf_counter()
    for _ in range(reps): fn()
    g.sync(); return (time.perf_counter() - t) / reps

# ---- 1) Lese-Test: 112 MB uint4 lesen
K_READ = r"""
cbuffer C:register(b0){ uint N; uint STRIDE; uint P1; uint P2; };
RWStructuredBuffer<uint4> W:register(u0); RWStructuredBuffer<uint> Y:register(u1);
[numthreads(256,1,1)]
void main(uint3 d:SV_DispatchThreadID){ uint4 a=0; for(uint i=d.x;i<N;i+=STRIDE) a^=W[i];
  if((a.x^a.y^a.z^a.w)==0x12345678u) Y[0]=a.x; }"""
n4 = 7_000_000; big = g.buffer(n4, os.urandom(n4 * 16), stride=16); y1 = g.buffer(4)
kr = g._shader(K_READ)
for groups in (512, 1024, 2048, 4096, 8192):
    s = timed(lambda: g._run(kr, struct.pack("<4I", n4, groups * 256, 0, 0), [big, y1], (groups, 1, 1)), 10)
    log(f"Lesen {n4 * 16 / 1e6:.0f} MB, {groups:5d} Gruppen: {n4 * 16 / s / 1e9:5.1f} GB/s")
g.free(big)

# ---- 2) Matvec int8, Form wie gate_proj (OUT 9728, IN 2560)
def k_mv8(R, shx):
    TPR = 256 // R
    xx = (lambda e: f"Xs[{e}]") if shx else (lambda e: f"X[XOFF+{e}]")
    dots = " + ".join(f"dot(i8(u.{c}), float4({', '.join(xx(f'k+{4 * n + m}') for m in range(4))}))"
                      for n, c in enumerate("xyzw"))
    load = ("for(uint kx=li;kx<IN;kx+=256) Xs[kx]=X[XOFF+kx]; GroupMemoryBarrierWithGroupSync();" if shx else "")
    return _I8 + r"""
cbuffer C:register(b0){ uint IN; uint YOFF; uint XOFF; uint OUT; };
RWStructuredBuffer<float> X:register(u0); RWStructuredBuffer<uint4> W:register(u1);
RWStructuredBuffer<float> Y:register(u2); RWStructuredBuffer<float> S:register(u3);
groupshared float red[256]; """ + ("groupshared float Xs[4096];" if shx else "") + r"""
[numthreads(256,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint li=l.x, j=li%TPR, o=g.x*RR+li/TPR, n16=IN/16; float acc=0;
  LOAD
  if(o<OUT){ uint wb=o*n16, sb=o*(IN/128);
    for(uint q=j;q<n16;q+=TPR){ uint4 u=W[wb+q]; uint k=q*16; float d=DOTS; acc+=d*S[sb+(q>>3)]; } }
  red[li]=acc; GroupMemoryBarrierWithGroupSync();
  for(uint a=TPR/2;a>0;a>>=1){ if(j<a) red[li]+=red[li+a]; GroupMemoryBarrierWithGroupSync(); }
  if(j==0&&o<OUT) Y[YOFF+o]=red[li];
}""".replace("TPR", str(TPR)).replace("RR", str(R)).replace("LOAD", load).replace("DOTS", dots)

OUT, IN = 9728, 2560; rnd = random.Random(1)
w8 = g.buffer(OUT * IN // 16, os.urandom(OUT * IN), stride=16)
sc = g.buffer(OUT * IN // 128, array("f", [0.01] * (OUT * IN // 128)).tobytes())
x = g.buffer(IN, array("f", [rnd.uniform(-1, 1) for _ in range(IN)]).tobytes())
y = g.buffer(OUT); nbytes = OUT * IN + OUT * IN // 128 * 4
cb = struct.pack("<4I", IN, 0, 0, OUT)
def rel(a, b): m = max(abs(v) for v in a) or 1; return max(abs(p - q) for p, q in zip(a, b)) / m

k0 = g._shader(K_MV8); s0 = timed(lambda: g._run(k0, cb, [x, w8, y, sc], ((OUT + 7) // 8, 1, 1)), 50)
ref = g.read(y, OUT); log(f"K_MV8 heute (8 Zeilen x 32 Threads): {s0 * 1000:.3f} ms = {nbytes / s0 / 1e9:5.1f} GB/s")
for R in (4, 8, 16, 32):
    for shx in (False, True):
        try: k = g._shader(k_mv8(R, shx))
        except Exception as e: log(f"R={R} shx={shx}: Kompilierfehler {e}"); continue
        s = timed(lambda: g._run(k, cb, [x, w8, y, sc], ((OUT + R - 1) // R, 1, 1)), 50)
        d = rel(ref, g.read(y, OUT))
        log(f"R={R:2d} ({256 // R:3d} Thr/Zeile) X {'Gruppensp.' if shx else 'global    '}: {s * 1000:.3f} ms = "
            f"{nbytes / s / 1e9:5.1f} GB/s  ({s0 / s:.2f}x)  Abw. {d:.1e}")

# ---- 3) Kosten je Kernel-Aufruf (pro Token ~36 Schichten x ~15 Aufrufe)
s = timed(lambda: g._run(kr, struct.pack("<4I", 0, 256, 0, 0), [w8, y1], (1, 1, 1)), 1000)
log(f"Leerer Kernel-Aufruf: {s * 1e6:.0f} us  -> ca. {s * 540 * 1000:.0f} ms je Token nur fuer Aufrufe")
OUT_F.write_text("\n".join(zeilen), encoding="utf-8"); print(f"\n-> {OUT_F}")
