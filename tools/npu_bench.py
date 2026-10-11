# tools/npu_bench.py — (a) bietet onnxruntime.dll (System32) DirectML an?  (b) FP16-GEMM ueber DirectML: NPU vs. GPU.
# Nur System-DLLs (ctypes), aendert nichts.  AURA vorher schliessen.
# Aufruf in C:\aura:  python tools\npu_bench.py     -> Ausgabe auch in tools\npu_bench.txt
import ctypes, os, random, struct, time
from ctypes import c_void_p, c_uint32, c_uint64, c_int, c_long, c_size_t, c_float, POINTER, byref, sizeof

OUT = []
def p(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); OUT.append(s)
SYS32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
def hx(hr): return f"0x{hr & 0xFFFFFFFF:08X}"

# ================================================================ (a) onnxruntime.dll
p("== (a) onnxruntime.dll aus System32")
try:
    ort = ctypes.WinDLL(os.path.join(SYS32, "onnxruntime.dll"))
    for fn in ("OrtGetApiBase", "OrtSessionOptionsAppendExecutionProvider_DML", "OrtSessionOptionsAppendExecutionProvider_CPU"):
        p(f"  Export {fn:48s}", "ja" if hasattr(ort, fn) else "nein")
    class OrtApiBase(ctypes.Structure):
        _fields_ = [("GetApi", ctypes.CFUNCTYPE(c_void_p, c_uint32)), ("GetVersionString", ctypes.CFUNCTYPE(ctypes.c_char_p))]
    ort.OrtGetApiBase.restype = POINTER(OrtApiBase)
    base = ort.OrtGetApiBase().contents
    p("  Version:", base.GetVersionString().decode())
    ok = [v for v in range(1, 25) if base.GetApi(v)]
    p("  unterstuetzte API-Versionen:", f"{min(ok)}..{max(ok)}" if ok else "keine")
except Exception as e: p("  nicht moeglich:", e)

# ================================================================ COM-Hilfen
class GUID(ctypes.Structure):
    _fields_ = [("a", c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]
def guid(s):
    h = s.replace("-", ""); g = GUID(int(h[:8], 16), int(h[8:12], 16), int(h[12:16], 16))
    for i in range(8): g.d[i] = int(h[16 + 2 * i:18 + 2 * i], 16)
    return g
def m(obj, idx, restype, *argtypes):
    vt = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    return lambda *a: ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(vt[idx])(obj, *a)
IUNK = None
FALLBACK = set()
def make(fn, key, *args):
    """DML-Objekt erzeugen; bei E_NOINTERFACE (IID falsch?) mit IUnknown wiederholen - gleiches Objekt, Primaer-vtable."""
    out = c_void_p(); hr = fn(*args, byref(IID[key]), byref(out))
    if hr & 0xFFFFFFFF == 0x80004002:
        FALLBACK.add(key); hr = fn(*args, byref(IUNK), byref(out))
    hr_ok(hr, key); return out
def hr_ok(hr, what):
    if hr: raise OSError(f"{what} fehlgeschlagen {hx(hr)}")

IID = {k: guid(v) for k, v in {
    "fac": "78ee5945-c36e-4b13-a669-005dd11c0f06", "list": "526c7776-40e9-459b-b711-f32ad76dfc28",
    "adapter": "f0db4c7f-fe5a-42a2-bd62-f2a6cf6fc83e", "ml": "b71b0d41-1088-422f-a27c-0250b7d3a988",
    "dev": "189819f1-1db6-4b57-be54-1821339b85f7", "queue": "0ec870a6-5d7e-4c22-8cfc-5baae07616ed",
    "alloc": "6102dee4-af59-4b09-b999-b44d73f09b24", "cl": "5b160d0f-ac1b-4185-8ba8-b3ae42a5a455",
    "fence": "0a753dcf-c4d8-4b91-adf6-be5a60d95a76", "res": "696442be-a72e-4059-bc79-5b5c98040fad",
    "heap": "8efb471d-616c-4f49-90f7-127bb763fa51", "dml": "6dbd6437-96fd-423f-a98c-ae5e7c2a573f",
    "op": "26caae7a-3081-4633-9581-226fbe57695f", "cop": "6b15e56a-bf5c-4902-92d8-da3a650afea4",
    "init": "427c1113-435c-469c-8676-4d5dd072f813", "rec": "e6857a76-2e3e-4fdd-bff4-5d2ba10fb453",
    "bt": "29c687dc-de74-4e3b-ab00-1168f2fc3cfc"}.items()}
IUNK = guid("00000000-0000-0000-c000-000000000046")

# ---- D3D12-Strukturen
class HeapProps(ctypes.Structure):
    _fields_ = [("Type", c_int), ("CPUPage", c_int), ("Pool", c_int), ("Create", c_uint32), ("Visible", c_uint32)]
class ResDesc(ctypes.Structure):
    _fields_ = [("Dim", c_int), ("Align", c_uint64), ("Width", c_uint64), ("Height", c_uint32), ("Depth", ctypes.c_uint16),
                ("Mips", ctypes.c_uint16), ("Format", c_int), ("SCount", c_uint32), ("SQual", c_uint32),
                ("Layout", c_int), ("Flags", c_int)]
class QueueDesc(ctypes.Structure): _fields_ = [("Type", c_int), ("Prio", c_int), ("Flags", c_int), ("Node", c_uint32)]
class HeapDesc(ctypes.Structure): _fields_ = [("Type", c_int), ("Num", c_uint32), ("Flags", c_int), ("Node", c_uint32)]
class Barrier(ctypes.Structure):   # UAV-Barriere (Type=2), Union auf 24 Byte aufgefuellt
    _fields_ = [("Type", c_int), ("Flags", c_int), ("res", c_void_p), ("pad", c_uint64 * 2)]
# ---- DirectML-Strukturen
class BufTensor(ctypes.Structure):
    _fields_ = [("DataType", c_int), ("Flags", c_int), ("DimCount", c_uint32), ("Sizes", POINTER(c_uint32)),
                ("Strides", c_void_p), ("Total", c_uint64), ("Align", c_uint32)]
class TensorDesc(ctypes.Structure): _fields_ = [("Type", c_int), ("Desc", c_void_p)]
class GemmDesc(ctypes.Structure):
    _fields_ = [("A", c_void_p), ("B", c_void_p), ("C", c_void_p), ("Out", c_void_p), ("TA", c_int), ("TB", c_int),
                ("Alpha", c_float), ("Beta", c_float), ("Act", c_void_p)]
class OpDesc(ctypes.Structure): _fields_ = [("Type", c_int), ("Desc", c_void_p)]
class BindProps(ctypes.Structure): _fields_ = [("Desc", c_uint32), ("Temp", c_uint64), ("Pers", c_uint64)]
class BTDesc(ctypes.Structure):
    _fields_ = [("Disp", c_void_p), ("Cpu", c_size_t), ("Gpu", c_uint64), ("Size", c_uint32)]
class BufBinding(ctypes.Structure): _fields_ = [("Buf", c_void_p), ("Off", c_uint64), ("Size", c_uint64)]
class BindDesc(ctypes.Structure): _fields_ = [("Type", c_int), ("Desc", c_void_p)]

d3d = ctypes.WinDLL(os.path.join(SYS32, "d3d12.dll"))
dmldll = ctypes.WinDLL(os.path.join(SYS32, "DirectML.dll"))
dxc = ctypes.WinDLL(os.path.join(SYS32, "dxcore.dll"))
k32 = ctypes.windll.kernel32

def adapters():
    fac, lst = c_void_p(), c_void_p()
    hr_ok(dxc.DXCoreCreateAdapterFactory(byref(IID["fac"]), byref(fac)), "DXCore")
    hr_ok(m(fac, 3, c_long, c_uint32, c_void_p, c_void_p, c_void_p)(1, byref(IID["ml"]), byref(IID["list"]), byref(lst)), "AdapterList")
    out = []
    for i in range(m(lst, 4, c_uint32)()):
        ad = c_void_p(); m(lst, 3, c_long, c_uint32, c_void_p, c_void_p)(i, byref(IID["adapter"]), byref(ad))
        sz = c_size_t(); m(ad, 7, c_long, c_int, POINTER(c_size_t))(2, byref(sz))
        b = ctypes.create_string_buffer(max(sz.value, 1)); m(ad, 6, c_long, c_int, c_size_t, c_void_p)(2, sz.value, b)
        name = b.value.decode(errors="replace")
        if "Basic Render" not in name: out.append((name, ad))
    return out

class Ctx:
    """D3D12-Geraet + Compute-Queue + DirectML auf einem Adapter."""
    def __init__(self, ad):
        self.dev = c_void_p()
        for fl in (0xB000, 0x1000, 0x100):               # 11_0, 1_0_CORE, 1_0_GENERIC (NPU)
            if d3d.D3D12CreateDevice(ad, fl, byref(IID["dev"]), byref(self.dev)) == 0: break
        else: raise OSError("D3D12CreateDevice")
        D = self.dev
        self.q, self.al, self.cl, self.fe = c_void_p(), c_void_p(), c_void_p(), c_void_p()
        hr_ok(m(D, 8, c_long, c_void_p, c_void_p, c_void_p)(byref(QueueDesc(2, 0, 0, 0)), byref(IID["queue"]), byref(self.q)), "Queue")
        hr_ok(m(D, 9, c_long, c_int, c_void_p, c_void_p)(2, byref(IID["alloc"]), byref(self.al)), "Allocator")
        hr_ok(m(D, 12, c_long, c_uint32, c_int, c_void_p, c_void_p, c_void_p, c_void_p)(
            0, 2, self.al, None, byref(IID["cl"]), byref(self.cl)), "CommandList")
        hr_ok(m(D, 36, c_long, c_uint64, c_int, c_void_p, c_void_p)(0, 0, byref(IID["fence"]), byref(self.fe)), "Fence")
        self.fv = 0; self.ev = k32.CreateEventW(None, False, False, None)
        self.dml = c_void_p()
        hr_ok(dmldll.DMLCreateDevice(D, 0, byref(IID["dml"]), byref(self.dml)), "DMLCreateDevice")
        self.open = True

    def buf(self, size, kind=1, uav=True):            # kind: 1 DEFAULT, 2 UPLOAD, 3 READBACK
        r = c_void_p(); st = {1: 0, 2: 0xAC3, 3: 0x400}[kind]
        desc = ResDesc(1, 0, max(size, 4), 1, 1, 1, 0, 1, 0, 1, 4 if (uav and kind == 1) else 0)
        hr_ok(m(self.dev, 27, c_long, c_void_p, c_int, c_void_p, c_int, c_void_p, c_void_p, c_void_p)(
            byref(HeapProps(kind, 0, 0, 1, 1)), 0, byref(desc), st, None, byref(IID["res"]), byref(r)), f"Buffer {size}")
        return r

    def run(self):
        """Liste schliessen, ausfuehren, warten, neu oeffnen. Rueckgabe: GPU-Wartezeit in s."""
        hr_ok(m(self.cl, 9, c_long)(), "Close")
        arr = (c_void_p * 1)(self.cl); t = time.perf_counter()
        m(self.q, 10, None, c_uint32, c_void_p)(1, arr)
        self.fv += 1; m(self.q, 14, c_long, c_void_p, c_uint64)(self.fe, self.fv)
        if m(self.fe, 8, c_uint64)() < self.fv:
            m(self.fe, 9, c_long, c_uint64, c_void_p)(self.fv, self.ev); k32.WaitForSingleObject(self.ev, 120000)
        dt = time.perf_counter() - t
        r = m(self.dml, 15, c_long)()
        if r: raise OSError(f"Geraet entfernt {hx(r)}")
        hr_ok(m(self.al, 8, c_long)(), "Allocator.Reset"); hr_ok(m(self.cl, 10, c_long, c_void_p, c_void_p)(self.al, None), "Reset")
        return dt

    def copy(self, dst, src, size): m(self.cl, 15, None, c_void_p, c_uint64, c_void_p, c_uint64, c_uint64)(dst, 0, src, 0, size)
    def map(self, r): ptr = c_void_p(); hr_ok(m(r, 8, c_long, c_uint32, c_void_p, c_void_p)(0, None, byref(ptr)), "Map"); return ptr
    def unmap(self, r): m(r, 9, None, c_uint32, c_void_p)(0, None)

def tensor(sizes, keep):
    s = (c_uint32 * 4)(*sizes); n = 1
    for x in sizes: n *= x
    bt = BufTensor(2, 0, 4, s, None, (n * 2 + 3) & ~3, 0); td = TensorDesc(1, ctypes.cast(byref(bt), c_void_p))
    keep += [s, bt, td]; return td, (n * 2 + 3) & ~3

def gemm(cx, M, K, N, reps):
    keep = []
    tA, sA = tensor((1, 1, M, K), keep); tB, sB = tensor((1, 1, K, N), keep); tO, sO = tensor((1, 1, M, N), keep)
    gd = GemmDesc(ctypes.cast(byref(tA), c_void_p), ctypes.cast(byref(tB), c_void_p), None, ctypes.cast(byref(tO), c_void_p),
                  0, 0, 1.0, 0.0, None)
    od = OpDesc(54, ctypes.cast(byref(gd), c_void_p))                  # 54 = DML_OPERATOR_GEMM
    op = make(m(cx.dml, 8, c_long, c_void_p, c_void_p, c_void_p), "op", byref(od))
    cop = make(m(cx.dml, 9, c_long, c_void_p, c_int, c_void_p, c_void_p), "cop", op, 1)
    ops = (c_void_p * 1)(cop)
    ini = make(m(cx.dml, 10, c_long, c_uint32, c_void_p, c_void_p, c_void_p), "init", 1, ops)
    pi, po = BindProps(), BindProps()
    m(ini, 8, c_void_p, c_void_p)(byref(pi)); m(cop, 8, c_void_p, c_void_p)(byref(po))
    nd = max(pi.Desc, po.Desc, 1)
    heap = c_void_p()
    hr_ok(m(cx.dev, 14, c_long, c_void_p, c_void_p, c_void_p)(byref(HeapDesc(0, nd, 1, 0)), byref(IID["heap"]), byref(heap)), "DescHeap")
    cpu, gpu = c_size_t(), c_uint64()
    m(heap, 9, c_void_p, c_void_p)(byref(cpu)); m(heap, 10, c_void_p, c_void_p)(byref(gpu))
    heaps = (c_void_p * 1)(heap)
    rec = make(m(cx.dml, 11, c_long, c_void_p, c_void_p), "rec")
    btd = BTDesc(ini, cpu.value, gpu.value, nd)
    bt = make(m(cx.dml, 12, c_long, c_void_p, c_void_p, c_void_p), "bt", byref(btd))
    pers = cx.buf(po.Pers) if po.Pers else None
    temp = cx.buf(max(pi.Temp, po.Temp)) if max(pi.Temp, po.Temp) else None
    def bind(slot_fn, r, size):
        bb = BufBinding(r, 0, size); bd = BindDesc(1, ctypes.cast(byref(bb), c_void_p)); keep.extend([bb, bd])
        m(bt, slot_fn, None, c_void_p)(byref(bd))
    if pers:                                                           # Initializer-Ausgabe = persistenter Speicher
        bb = BufBinding(pers, 0, po.Pers); bd = BindDesc(1, ctypes.cast(byref(bb), c_void_p)); keep += [bb, bd]
        m(bt, 9, None, c_uint32, c_void_p)(1, byref(bd))
    if temp and pi.Temp: bind(10, temp, max(pi.Temp, po.Temp))
    m(cx.cl, 28, None, c_uint32, c_void_p)(1, heaps)
    m(rec, 8, None, c_void_p, c_void_p, c_void_p)(cx.cl, ini, bt); cx.run()
    # Daten: Zufallsmuster (P Werte, periodisch wiederholt) in FP16 - schnell auch fuer grosse Matrizen
    P = 4093; pa = struct.unpack(f"<{P}e", struct.pack(f"<{P}e", *[random.uniform(-1, 1) for _ in range(P)]))
    pb = struct.unpack(f"<{P}e", struct.pack(f"<{P}e", *[random.uniform(-1, 1) for _ in range(P)]))
    bA, bB, bO = cx.buf(sA), cx.buf(sB), cx.buf(sO)
    uA, uB, rb = cx.buf(sA, 2), cx.buf(sB, 2), cx.buf(sO, 3)
    for u, pat, n in ((uA, pa, M * K), (uB, pb, K * N)):
        blk = struct.pack(f"<{P}e", *pat); raw = (blk * (n // P + 1))[:n * 2]
        ptr = cx.map(u); ctypes.memmove(ptr, raw, len(raw)); cx.unmap(u)
    cx.copy(bA, uA, sA); cx.copy(bB, uB, sB); cx.run()
    # Operator binden
    btd2 = BTDesc(cop, cpu.value, gpu.value, nd); m(bt, 12, c_long, c_void_p)(byref(btd2))
    ins = (BindDesc * 3)(); bbs = [BufBinding(bA, 0, sA), BufBinding(bB, 0, sB)]
    ins[0] = BindDesc(1, ctypes.cast(byref(bbs[0]), c_void_p)); ins[1] = BindDesc(1, ctypes.cast(byref(bbs[1]), c_void_p))
    ins[2] = BindDesc(0, None); keep += [ins, bbs]
    m(bt, 8, None, c_uint32, c_void_p)(3, ins)
    ob = BufBinding(bO, 0, sO); od2 = BindDesc(1, ctypes.cast(byref(ob), c_void_p)); keep += [ob, od2]
    m(bt, 9, None, c_uint32, c_void_p)(1, byref(od2))
    if temp and po.Temp: bind(10, temp, max(pi.Temp, po.Temp))
    if pers: bind(11, pers, po.Pers)
    uav = Barrier(2, 0, None)
    def record(n):
        m(cx.cl, 28, None, c_uint32, c_void_p)(1, heaps)
        for _ in range(n):
            m(rec, 8, None, c_void_p, c_void_p, c_void_p)(cx.cl, cop, bt)
            m(cx.cl, 26, None, c_uint32, c_void_p)(1, byref(uav))
    record(2); cx.run()                                                # Aufwaermen
    record(reps); dt = cx.run()
    tflops = 2.0 * M * N * K * reps / dt / 1e12
    # Kontrolle: 32 Stichproben gegen Python
    cx.copy(rb, bO, sO); cx.run(); ptr = cx.map(rb)
    raw = ctypes.string_at(ptr, M * N * 2); cx.unmap(rb)
    err = 0.0
    for _ in range(32):
        i, j = random.randrange(M), random.randrange(N)
        ref = sum(pa[(i * K + k) % P] * pb[(k * N + j) % P] for k in range(K))
        got = struct.unpack_from("<e", raw, (i * N + j) * 2)[0]
        err = max(err, abs(got - ref) / (abs(ref) + 1.0))
    return dt / reps * 1000, tflops, err

SHAPES = [("1024x1024x1024", 1024, 1024, 1024, 20),
          ("e5-FFN 512x1024x4096", 512, 1024, 4096, 20),
          ("Qwen-4B Prefill 1024x2560x9728", 1024, 2560, 9728, 5)]
p("\n== (b) FP16-GEMM ueber DirectML (System32)")
try: ads = adapters()
except Exception as e: ads = []; p("Adapter nicht lesbar:", e)
for name, ad in ads:
    p(f"\n-- {name}")
    try: cx = Ctx(ad)
    except Exception as e: p("   Geraet nicht moeglich:", e); continue
    for label, M, K, N, reps in SHAPES:
        try:
            ms, tf, err = gemm(cx, M, K, N, reps)
            p(f"   {label:32s} {ms:8.2f} ms   {tf:5.2f} TFLOPS   rel. Fehler {err:.4f}" + ("  <- FALSCH?" if err > 0.05 else ""))
        except Exception as e: p(f"   {label:32s} FEHLER: {e}")

if FALLBACK: p("\nHinweis: IUnknown-Ersatz fuer", ", ".join(sorted(FALLBACK)))
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "npu_bench.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(OUT))
p("\nGespeichert: tools\\npu_bench.txt")
