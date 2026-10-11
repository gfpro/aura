# aura/engine/dml.py — Version 20261008v01  (AURA)
# DirectML ueber ctypes: nur System-DLLs (d3d12, dxcore, DirectML.dll in System32), kein pip.
# Bausteine: Geraet + Queue, Puffer, Operatoren (kompilieren, initialisieren, binden), Befehlslisten.
import ctypes, os, time
from ctypes import c_void_p, c_uint32, c_uint64, c_int, c_long, c_size_t, c_float, POINTER, byref

SYS32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
def hx(hr): return f"0x{hr & 0xFFFFFFFF:08X}"
def ok(hr, what):
    if hr: raise OSError(f"{what} fehlgeschlagen {hx(hr)}")

class GUID(ctypes.Structure):
    _fields_ = [("a", c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]
def guid(s):
    h = s.replace("-", ""); g = GUID(int(h[:8], 16), int(h[8:12], 16), int(h[12:16], 16))
    for i in range(8): g.d[i] = int(h[16 + 2 * i:18 + 2 * i], 16)
    return g
_FN = {}
def m(obj, idx, restype, *argtypes):
    """COM-Methode Nr. idx der vtable von obj."""
    key = (restype, argtypes)
    proto = _FN.get(key) or _FN.setdefault(key, ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes))
    vt = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    return lambda *a: proto(vt[idx])(obj, *a)

IID = {k: guid(v) for k, v in {
    "fac": "78ee5945-c36e-4b13-a669-005dd11c0f06", "list": "526c7776-40e9-459b-b711-f32ad76dfc28",
    "adapter": "f0db4c7f-fe5a-42a2-bd62-f2a6cf6fc83e", "ml": "b71b0d41-1088-422f-a27c-0250b7d3a988",
    "compute": "248e2800-a793-4724-abaa-23a6de1be090",
    "dev": "189819f1-1db6-4b57-be54-1821339b85f7", "queue": "0ec870a6-5d7e-4c22-8cfc-5baae07616ed",
    "alloc": "6102dee4-af59-4b09-b999-b44d73f09b24", "cl": "5b160d0f-ac1b-4185-8ba8-b3ae42a5a455",
    "fence": "0a753dcf-c4d8-4b91-adf6-be5a60d95a76", "res": "696442be-a72e-4059-bc79-5b5c98040fad",
    "heap": "8efb471d-616c-4f49-90f7-127bb763fa51", "dml": "6dbd6437-96fd-423f-a98c-ae5e7c2a573f",
    "unk": "00000000-0000-0000-c000-000000000046"}.items()}

# ---- D3D12
class HeapProps(ctypes.Structure):
    _fields_ = [("Type", c_int), ("CPUPage", c_int), ("Pool", c_int), ("Create", c_uint32), ("Visible", c_uint32)]
class ResDesc(ctypes.Structure):
    _fields_ = [("Dim", c_int), ("Align", c_uint64), ("Width", c_uint64), ("Height", c_uint32), ("Depth", ctypes.c_uint16),
                ("Mips", ctypes.c_uint16), ("Format", c_int), ("SCount", c_uint32), ("SQual", c_uint32),
                ("Layout", c_int), ("Flags", c_int)]
class QueueDesc(ctypes.Structure): _fields_ = [("Type", c_int), ("Prio", c_int), ("Flags", c_int), ("Node", c_uint32)]
class HeapDesc(ctypes.Structure): _fields_ = [("Type", c_int), ("Num", c_uint32), ("Flags", c_int), ("Node", c_uint32)]
class Barrier(ctypes.Structure): _fields_ = [("Type", c_int), ("Flags", c_int), ("res", c_void_p), ("pad", c_uint64 * 2)]
# ---- DirectML
F32, F16 = 1, 2
class BufTensor(ctypes.Structure):
    _fields_ = [("DataType", c_int), ("Flags", c_int), ("DimCount", c_uint32), ("Sizes", POINTER(c_uint32)),
                ("Strides", POINTER(c_uint32)), ("Total", c_uint64), ("Align", c_uint32)]
class TensorDesc(ctypes.Structure): _fields_ = [("Type", c_int), ("Desc", c_void_p)]
class ScaleBias(ctypes.Structure): _fields_ = [("Scale", c_float), ("Bias", c_float)]
class OpDesc(ctypes.Structure): _fields_ = [("Type", c_int), ("Desc", c_void_p)]
class BindProps(ctypes.Structure): _fields_ = [("Desc", c_uint32), ("Temp", c_uint64), ("Pers", c_uint64)]
class BTDesc(ctypes.Structure): _fields_ = [("Disp", c_void_p), ("Cpu", c_size_t), ("Gpu", c_uint64), ("Size", c_uint32)]
class BufBinding(ctypes.Structure): _fields_ = [("Buf", c_void_p), ("Off", c_uint64), ("Size", c_uint64)]
class BindDesc(ctypes.Structure): _fields_ = [("Type", c_int), ("Desc", c_void_p)]

# Operator-Nummern (DML_OPERATOR_TYPE) und Beschreibungs-Strukturen
OP = {"identity": 1, "add": 4, "multiply": 24, "softmax": 48, "gemm": 54, "cast": 61, "mvn": 73, "erf": 81}
def _s(*fields): return type("D", (ctypes.Structure,), {"_fields_": list(fields)})
P = c_void_p
DESC = {"identity": _s(("In", P), ("Out", P), ("SB", P)),
        "erf": _s(("In", P), ("Out", P), ("SB", P)),
        "add": _s(("A", P), ("B", P), ("Out", P)),
        "multiply": _s(("A", P), ("B", P), ("Out", P)),
        "softmax": _s(("In", P), ("Out", P)),
        "cast": _s(("In", P), ("Out", P)),
        "gemm": _s(("A", P), ("B", P), ("C", P), ("Out", P), ("TA", c_int), ("TB", c_int), ("Alpha", c_float),
                   ("Beta", c_float), ("Act", P)),
        "mvn": _s(("In", P), ("Scale", P), ("Bias", P), ("Out", P), ("Cross", c_int), ("NormVar", c_int),
                  ("Eps", c_float), ("Act", P))}

class T:
    """Tensor-Beschreibung (4D). strides=None -> dicht. Haelt alle ctypes-Objekte am Leben."""
    def __init__(self, sizes, strides=None, dtype=F16):
        self.sizes = tuple(sizes); self.dtype = dtype; es = 4 if dtype == F32 else 2
        if strides is None:
            st, acc = [], 1
            for s in reversed(self.sizes): st.insert(0, acc); acc *= s
            strides = None; span = acc
        else:
            span = sum((s - 1) * t for s, t in zip(self.sizes, strides)) + 1
        self.bytes = (span * es + 3) & ~3
        self._sz = (c_uint32 * 4)(*self.sizes)
        self._st = (c_uint32 * 4)(*strides) if strides is not None else None
        self._bt = BufTensor(dtype, 0, 4, self._sz, self._st, self.bytes, 0)
        self._td = TensorDesc(1, ctypes.cast(byref(self._bt), c_void_p))
    @property
    def ptr(self): return ctypes.cast(byref(self._td), c_void_p)

_d3d = _dml = _dxc = None
def _dlls():
    global _d3d, _dml, _dxc
    if _d3d is None:
        _d3d = ctypes.WinDLL(os.path.join(SYS32, "d3d12.dll")); _dml = ctypes.WinDLL(os.path.join(SYS32, "DirectML.dll"))
        _dxc = ctypes.WinDLL(os.path.join(SYS32, "dxcore.dll"))

def adapters(attr="compute"):
    """[(Name, IDXCoreAdapter)] mit Faehigkeit attr ('compute' = GPU, 'ml' = inkl. NPU)."""
    _dlls(); fac, lst = c_void_p(), c_void_p()
    ok(_dxc.DXCoreCreateAdapterFactory(byref(IID["fac"]), byref(fac)), "DXCore")
    ok(m(fac, 3, c_long, c_uint32, c_void_p, c_void_p, c_void_p)(1, byref(IID[attr]), byref(IID["list"]), byref(lst)), "Liste")
    out = []
    for i in range(m(lst, 4, c_uint32)()):
        ad = c_void_p(); m(lst, 3, c_long, c_uint32, c_void_p, c_void_p)(i, byref(IID["adapter"]), byref(ad))
        sz = c_size_t(); m(ad, 7, c_long, c_int, POINTER(c_size_t))(2, byref(sz))
        b = ctypes.create_string_buffer(max(sz.value, 1)); m(ad, 6, c_long, c_int, c_size_t, c_void_p)(2, sz.value, b)
        name = b.value.decode(errors="replace")
        if "Basic Render" not in name: out.append((name, ad))
    return out

class Buf:
    def __init__(self, res, size): self.res, self.size = res, size

class CmdList:
    def __init__(self, dev, track=None):
        self.al, self.cl = c_void_p(), c_void_p()
        ok(m(dev, 9, c_long, c_int, c_void_p, c_void_p)(2, byref(IID["alloc"]), byref(self.al)), "Allocator")
        ok(m(dev, 12, c_long, c_uint32, c_int, c_void_p, c_void_p, c_void_p, c_void_p)(
            0, 2, self.al, None, byref(IID["cl"]), byref(self.cl)), "CommandList")
        if track is not None: track += [self.al, self.cl]
        self.closed = False
    def reset(self):
        ok(m(self.al, 8, c_long)(), "Allocator.Reset"); ok(m(self.cl, 10, c_long, c_void_p, c_void_p)(self.al, None), "Reset")
        self.closed = False
    def close(self):
        if not self.closed: ok(m(self.cl, 9, c_long)(), "Close"); self.closed = True

class Op:
    """Kompilierter DirectML-Operator (eine Form). Mehrere Bindungen (z.B. je Schicht) moeglich."""
    def __init__(self, dev, kind, flags=1, **fields):
        self.dev, self.kind, self.keep = dev, kind, []
        d = DESC[kind]();
        for k, v in fields.items():
            if isinstance(v, T): self.keep.append(v); v = v.ptr
            elif isinstance(v, ScaleBias): self.keep.append(v); v = ctypes.cast(byref(v), c_void_p)
            setattr(d, k, v)
        od = OpDesc(OP[kind], ctypes.cast(byref(d), c_void_p)); self.keep += [d, od]
        op, self.cop, self.ini = c_void_p(), c_void_p(), c_void_p()
        D = dev.dml
        ok(m(D, 8, c_long, c_void_p, c_void_p, c_void_p)(byref(od), byref(IID["unk"]), byref(op)), f"{kind}: CreateOperator")
        ok(m(D, 9, c_long, c_void_p, c_int, c_void_p, c_void_p)(op, flags, byref(IID["unk"]), byref(self.cop)), f"{kind}: Compile")
        ops = (c_void_p * 1)(self.cop); self.keep.append(ops)
        ok(m(D, 10, c_long, c_uint32, c_void_p, c_void_p, c_void_p)(1, ops, byref(IID["unk"]), byref(self.ini)), f"{kind}: Init")
        dev._objs += [op, self.cop, self.ini]
        self.pi, self.po = BindProps(), BindProps()
        m(self.ini, 8, c_void_p, c_void_p)(byref(self.pi)); m(self.cop, 8, c_void_p, c_void_p)(byref(self.po))
        self.pers = dev.buffer(self.po.Pers) if self.po.Pers else None
        dev.need_temp(max(self.pi.Temp, self.po.Temp))
        self.initialized = False

    def _table(self, disp, nd):
        bt = c_void_p(); cpu, gpu = self.dev.descriptors(nd)
        d = BTDesc(disp, cpu, gpu, nd); self.keep.append(d)
        ok(m(self.dev.dml, 12, c_long, c_void_p, c_void_p, c_void_p)(byref(d), byref(IID["unk"]), byref(bt)), "BindingTable")
        self.dev._objs.append(bt); return bt

    def _bind1(self, bt, idx, buf, size=None):
        if buf is None: bd = BindDesc(0, None)
        else:
            bb = BufBinding(buf.res, 0, size or buf.size); self.keep.append(bb); bd = BindDesc(1, ctypes.cast(byref(bb), c_void_p))
        self.keep.append(bd); m(bt, idx, None, c_void_p)(byref(bd))

    def init(self):
        """Initialisierung (einmal pro Operator) auf der GPU ausfuehren."""
        if self.initialized: return
        bt = self._table(self.ini, max(self.pi.Desc, 1))
        if self.pers:
            bb = BufBinding(self.pers.res, 0, self.pers.size); bd = BindDesc(1, ctypes.cast(byref(bb), c_void_p))
            self.keep += [bb, bd]; m(bt, 9, None, c_uint32, c_void_p)(1, byref(bd))
        if self.pi.Temp: self._bind1(bt, 10, self.dev.temp)
        L = self.dev.oneshot(); self.dev.set_heap(L); self.dev.record(L, self.ini, bt); self.dev.run(L)
        self.initialized = True

    def bind(self, inputs, outputs):
        """inputs/outputs: Listen von Buf, (Buf, Offset in Bytes) oder None (optionaler Eingang).
        Rueckgabe: Bindung fuer Device.dispatch()."""
        self.init()
        bt = self._table(self.cop, max(self.po.Desc, 1))
        def arr(bufs):
            a = (BindDesc * len(bufs))()
            for i, b in enumerate(bufs):
                if b is None: a[i] = BindDesc(0, None); continue
                b, off = b if isinstance(b, tuple) else (b, 0)
                bb = BufBinding(b.res, off, b.size - off); self.keep.append(bb); a[i] = BindDesc(1, ctypes.cast(byref(bb), c_void_p))
            self.keep.append(a); return a
        a = arr(inputs); m(bt, 8, None, c_uint32, c_void_p)(len(inputs), a)
        o = arr(outputs); m(bt, 9, None, c_uint32, c_void_p)(len(outputs), o)
        if self.po.Temp: self._bind1(bt, 10, self.dev.temp)
        if self.pers: self._bind1(bt, 11, self.pers)
        return (self.cop, bt)

class Device:
    def __init__(self, adapter=None):
        _dlls(); self._objs = []                           # alle COM-Objekte -> close() gibt sie frei
        if adapter is None:
            ads = adapters("compute")
            if not ads: raise OSError("Kein DirectX-12-Grafikadapter gefunden")
            self.name, adapter = ads[0]
        else: self.name = "?"
        self.dev = c_void_p()
        for fl in (0xB000, 0x1000, 0x100):
            if _d3d.D3D12CreateDevice(adapter, fl, byref(IID["dev"]), byref(self.dev)) == 0: break
        else: raise OSError("D3D12CreateDevice fehlgeschlagen")
        self._objs.append(self.dev); D = self.dev; self.q, self.fe = c_void_p(), c_void_p()
        ok(m(D, 8, c_long, c_void_p, c_void_p, c_void_p)(byref(QueueDesc(2, 0, 0, 0)), byref(IID["queue"]), byref(self.q)), "Queue")
        ok(m(D, 36, c_long, c_uint64, c_int, c_void_p, c_void_p)(0, 0, byref(IID["fence"]), byref(self.fe)), "Fence")
        self.fv = 0; self.ev = ctypes.windll.kernel32.CreateEventW(None, False, False, None)
        self.dml = c_void_p()
        ok(_dml.DMLCreateDevice(D, 0, byref(IID["dml"]), byref(self.dml)), "DMLCreateDevice")
        self._objs += [self.q, self.fe, self.dml]
        # Deskriptor-Heap (gross genug fuer alle Bindungen eines Modells)
        self.nheap = 65536; self.heap = c_void_p()
        ok(m(D, 14, c_long, c_void_p, c_void_p, c_void_p)(byref(HeapDesc(0, self.nheap, 1, 0)), byref(IID["heap"]),
                                                            byref(self.heap)), "DescriptorHeap")
        cpu, gpu = c_size_t(), c_uint64()
        m(self.heap, 9, c_void_p, c_void_p)(byref(cpu)); m(self.heap, 10, c_void_p, c_void_p)(byref(gpu))
        self.cpu0, self.gpu0, self.inc, self.used = cpu.value, gpu.value, m(D, 15, c_uint32, c_int)(0), 0
        self.heaps = (c_void_p * 1)(self.heap)
        self.rec = c_void_p()
        ok(m(self.dml, 11, c_long, c_void_p, c_void_p)(byref(IID["unk"]), byref(self.rec)), "CommandRecorder")
        self._objs += [self.heap, self.rec]
        self.temp, self.temp_size = None, 0
        self._one = CmdList(self.dev, self._objs); self._one_used = False
        self.uav = Barrier(2, 0, None)

    # ---- Speicher
    def buffer(self, size, kind=1):
        """kind 1 = GPU (UAV), 2 = Upload, 3 = Readback."""
        r = c_void_p(); st = {1: 0, 2: 0xAC3, 3: 0x400}[kind]
        desc = ResDesc(1, 0, max(int(size), 4), 1, 1, 1, 0, 1, 0, 1, 4 if kind == 1 else 0)
        ok(m(self.dev, 27, c_long, c_void_p, c_int, c_void_p, c_int, c_void_p, c_void_p, c_void_p)(
            byref(HeapProps(kind, 0, 0, 1, 1)), 0, byref(desc), st, None, byref(IID["res"]), byref(r)), f"Puffer {size} B")
        self._objs.append(r); return Buf(r, max(int(size), 4))

    def close(self):
        """Alle D3D12/DirectML-Objekte freigeben (IUnknown::Release), neueste zuerst."""
        try: self.wait()
        except Exception: pass
        for o in reversed(self._objs):
            try:
                if o and o.value: m(o, 2, c_uint32)()
            except Exception: pass
        self._objs = []
        try: ctypes.windll.kernel32.CloseHandle(self.ev)
        except Exception: pass
    def need_temp(self, size):
        if size > self.temp_size:
            self.temp_size = int(size); self.temp = self.buffer(size)
    def descriptors(self, n):
        if self.used + n > self.nheap: raise OSError("Deskriptor-Heap voll")
        off = self.used; self.used += n
        return self.cpu0 + off * self.inc, self.gpu0 + off * self.inc
    def map(self, buf):
        p = c_void_p(); ok(m(buf.res, 8, c_long, c_uint32, c_void_p, c_void_p)(0, None, byref(p)), "Map"); return p.value
    def unmap(self, buf): m(buf.res, 9, None, c_uint32, c_void_p)(0, None)

    # ---- Befehle
    def oneshot(self):
        if self._one_used: self._one.reset()
        self._one_used = True; return self._one
    def set_heap(self, L): m(L.cl, 28, None, c_uint32, c_void_p)(1, self.heaps)
    def record(self, L, disp, bt, barrier=True):
        m(self.rec, 8, None, c_void_p, c_void_p, c_void_p)(L.cl, disp, bt)
        if barrier: m(L.cl, 26, None, c_uint32, c_void_p)(1, byref(self.uav))
    def dispatch(self, L, binding): self.record(L, *binding)
    def copy(self, L, dst, src, size, dst_off=0, src_off=0):
        m(L.cl, 15, None, c_void_p, c_uint64, c_void_p, c_uint64, c_uint64)(dst.res, dst_off, src.res, src_off, size)
    def run(self, L, wait=True):
        L.close(); arr = (c_void_p * 1)(L.cl)
        m(self.q, 10, None, c_uint32, c_void_p)(1, arr)
        self.fv += 1; m(self.q, 14, c_long, c_void_p, c_uint64)(self.fe, self.fv)
        if wait: self.wait()
    def wait(self):
        if m(self.fe, 8, c_uint64)() < self.fv:
            m(self.fe, 9, c_long, c_uint64, c_void_p)(self.fv, self.ev); ctypes.windll.kernel32.WaitForSingleObject(self.ev, 600000)
        r = m(self.dml, 15, c_long)()
        if r: raise OSError(f"GPU-Geraet entfernt {hx(r)} (z.B. Standby)")

    # ---- Daten hin und zurueck (ueber Zwischenpuffer)
    def upload(self, dst, data, off=0):
        n = len(data); up = self._staging(n, 2)
        p = self.map(up); ctypes.memmove(p, data, n); self.unmap(up)
        L = self.oneshot(); self.copy(L, dst, up, n, dst_off=off); self.run(L)
    def download(self, src, n):
        rb = self._staging(n, 3)
        L = self.oneshot(); self.copy(L, rb, src, n); self.run(L)
        p = self.map(rb); data = ctypes.string_at(p, n); self.unmap(rb); return data
    def _staging(self, n, kind):
        key = f"_st{kind}"; b = self.__dict__.get(key)
        if b is None or b.size < n: b = self.buffer(max(n, 1 << 20), kind); self.__dict__[key] = b
        return b

# ------------------------------------------------------------------ Selbsttest der Operatoren (v01b)
# Operator-Nummern sind aus dem Gedaechtnis rekonstruiert -> jede Operation wird an kleinen Zahlen gegen Python geprueft.
# Fuer softmax/erf werden Varianten probiert; die erste korrekte wird gemerkt (SOFTMAX, OP["erf"]).
import math as _math, struct as _struct
DESC["softmax1"] = _s(("In", P), ("Out", P), ("AxisCount", c_uint32), ("Axes", P))
SOFTMAX = None          # (Operatornummer, Form-Art) nach selftest()

def _run(dev, op, inputs, out_n):
    bufs = []
    for vals in inputs:
        b = dev.buffer(len(vals) * 2); dev.upload(b, _struct.pack(f"<{len(vals)}e", *vals)); bufs.append(b)
    o = dev.buffer(out_n * 2); bnd = op.bind(bufs, [o])
    L = dev.oneshot(); dev.set_heap(L); dev.dispatch(L, bnd); dev.run(L)
    return _struct.unpack(f"<{out_n}e", dev.download(o, out_n * 2))

def _close(a, b, tol=2e-2): return all(abs(x - y) <= tol * (1 + abs(y)) for x, y in zip(a, b))

def softmax_op(dev, B, n):
    """Softmax ueber die letzte Achse fuer B Zeilen zu n Werten, gemaess der im Selbsttest gefundenen Variante."""
    num, form = SOFTMAX
    if form == "B111": return Op(dev, "softmax", In=T((B, 1, 1, n)), Out=T((B, 1, 1, n)))
    if form == "11BT": return Op(dev, "softmax", In=T((1, 1, B, n)), Out=T((1, 1, B, n)))
    ax = (c_uint32 * 1)(3)
    op = Op(dev, "softmax1", In=T((1, 1, B, n)), Out=T((1, 1, B, n)), AxisCount=1, Axes=ctypes.cast(ax, c_void_p))
    op.keep.append(ax); return op

def selftest(dev, log=print):
    global SOFTMAX
    x = [(-1.5 + 0.37 * i) % 3 - 1.5 for i in range(8)]; y = [0.25 * ((i * 7) % 5) - 0.5 for i in range(8)]
    sh = (1, 1, 1, 8); res = {}
    def chk(name, fn):
        try: ok_ = fn(); res[name] = ok_; log(f"   Selbsttest {name:10s} {'OK' if ok_ else 'FALSCH'}")
        except OSError as e: res[name] = False; log(f"   Selbsttest {name:10s} Fehler: {e}")
    chk("add", lambda: _close(_run(dev, Op(dev, "add", A=T(sh), B=T(sh), Out=T(sh)), [x, y], 8), [a + b for a, b in zip(x, y)]))
    chk("multiply", lambda: _close(_run(dev, Op(dev, "multiply", A=T(sh), B=T(sh), Out=T(sh)), [x, y], 8), [a * b for a, b in zip(x, y)]))
    chk("identity", lambda: _close(_run(dev, Op(dev, "identity", In=T(sh), Out=T(sh), SB=ScaleBias(0.5, 0.5)), [x], 8),
                                    [0.5 * a + 0.5 for a in x]))
    want_erf = [_math.erf(a / _math.sqrt(2)) for a in x]
    for num in (81, 80, 82, 79, 83):
        OP["erf"] = num
        try:
            if _close(_run(dev, Op(dev, "erf", In=T(sh), Out=T(sh), SB=ScaleBias(1 / _math.sqrt(2), 0.0)), [x], 8), want_erf):
                log(f"   Selbsttest erf        OK (Nr. {num})"); res["erf"] = True; break
        except OSError: pass
    else: res["erf"] = False; log("   Selbsttest erf        keine Variante korrekt")
    B, Tn = 3, 8; z = [((i * 5) % 11) * 0.3 - 1.2 for i in range(B * Tn)]
    want = []
    for r in range(B):
        row = z[r * Tn:(r + 1) * Tn]; mx = max(row); e = [_math.exp(v - mx) for v in row]; s = sum(e); want += [v / s for v in e]
    for num, form in ((48, "B111"), (48, "11BT"), (158, "axes"), (157, "axes"), (159, "axes")):
        SOFTMAX = (num, form); OP["softmax"] = num if form != "axes" else OP["softmax"]; OP["softmax1"] = num
        try:
            if _close(_run(dev, softmax_op(dev, B, Tn), [z], B * Tn), want):
                log(f"   Selbsttest softmax    OK (Nr. {num}, {form})"); res["softmax"] = True; break
        except OSError as e: log(f"   (softmax Nr. {num}/{form}: {e})")
    else: res["softmax"] = False; SOFTMAX = None; log("   Selbsttest softmax    keine Variante korrekt")
    return all(res.values())
