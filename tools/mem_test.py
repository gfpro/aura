# tools\mem_test.py  20261025v01
# Misst: (1) wie viel GPU-Puffer (D3D11) sich wirklich anlegen UND beschreiben laesst,
#        (2) Lesetempo SSD -> RAM und RAM -> GPU-Puffer.
# Aufruf:  py tools\mem_test.py [datei]   -> tools\mem_test.txt
# Ohne [datei] wird die groesste .safetensors-Datei unter C:\aura\models genommen.
import ctypes, os, sys, time, glob
from ctypes import c_void_p, c_uint, c_int, c_ulonglong, POINTER, byref, Structure, WINFUNCTYPE

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mem_test.txt")
_lines = []
def log(s=""):
    print(s); _lines.append(s)
    with open(OUT, "w", encoding="utf-8") as f: f.write("\n".join(_lines) + "\n")

def vt(obj, idx, *argt):
    p = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0][idx]
    fn = WINFUNCTYPE(c_int, c_void_p, *argt)(p)
    return lambda *a: fn(obj, *a)
def release(o):
    if o: vt(o, 2)()

class GUID(Structure):
    _fields_ = [("a", c_uint), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]
def guid(a, b, c, d): return GUID(a, b, c, (ctypes.c_ubyte * 8)(*d))
IID_F1 = guid(0x770aae78, 0xf26f, 0x4dba, [0xa8,0x29,0x25,0x3c,0x83,0xd1,0xb3,0x87])
IID_A3 = guid(0x645967a4, 0x1392, 0x4310, [0xa7,0x98,0x80,0x53,0xce,0x3e,0x93,0xfd])

class MEMINFO(Structure):
    _fields_ = [("Budget", c_ulonglong), ("Usage", c_ulonglong), ("Avail", c_ulonglong), ("Res", c_ulonglong)]
class BUFDESC(Structure):
    _fields_ = [("ByteWidth", c_uint), ("Usage", c_uint), ("Bind", c_uint), ("CPU", c_uint), ("Misc", c_uint), ("Stride", c_uint)]
class QDESC(Structure):
    _fields_ = [("Query", c_uint), ("Misc", c_uint)]

GB = 1024 ** 3; MB = 1024 ** 2
CHUNK = 256 * MB

def main():
    log("AURA mem_test v01  " + time.strftime("%d.%m.%Y %H:%M"))
    dxgi = ctypes.WinDLL("dxgi"); d3d = ctypes.WinDLL("d3d11")
    fac = c_void_p()
    if dxgi.CreateDXGIFactory1(byref(IID_F1), byref(fac)) != 0: log("FEHLER DXGI-Factory"); return
    ad = c_void_p(); vt(fac, 12, c_uint, POINTER(c_void_p))(0, byref(ad))      # EnumAdapters1
    ad3 = c_void_p(); vt(ad, 0, POINTER(GUID), POINTER(c_void_p))(byref(IID_A3), byref(ad3))
    def mem():
        m = MEMINFO()
        if ad3: vt(ad3, 14, c_uint, c_uint, POINTER(MEMINFO))(0, 0, byref(m))   # QueryVideoMemoryInfo
        return m
    m = mem()
    log(f"GPU-Budget {m.Budget/GB:.2f} GB, schon belegt {m.Usage/GB:.2f} GB")

    dev = c_void_p(); ctx = c_void_p(); fl = c_int()
    hr = d3d.D3D11CreateDevice(ad, 0, None, 0, None, 0, 7, byref(dev), byref(fl), byref(ctx))
    if hr != 0: log(f"FEHLER D3D11CreateDevice 0x{hr & 0xffffffff:08x}"); return
    create_buf = vt(dev, 3, POINTER(BUFDESC), c_void_p, POINTER(c_void_p))
    update = vt(ctx, 48, c_void_p, c_uint, c_void_p, c_void_p, c_uint, c_uint)
    flush = vt(ctx, 111)
    q = c_void_p(); vt(dev, 24, POINTER(QDESC), POINTER(c_void_p))(byref(QDESC(0, 0)), byref(q))
    end = vt(ctx, 28, c_void_p); getdata = vt(ctx, 29, c_void_p, c_void_p, c_uint, c_uint)
    def wait():
        end(q); flush(); r = c_int()
        while getdata(q, byref(r), 4, 0) != 0: pass

    src = (ctypes.c_ubyte * CHUNK)()
    ctypes.memset(src, 1, CHUNK)

    # ---------- Teil 1: Speicher ----------
    log("\n[1] GPU-Puffer anlegen und beschreiben (je 256 MB, Abbruch bei Fehler/Budget/24 GB)")
    bufs = []; t0 = time.time()
    while len(bufs) * CHUNK < 24 * GB:
        b = c_void_p()
        hr = create_buf(byref(BUFDESC(CHUNK, 0, 0x8 | 0x80, 0, 0x20, 0)), None, byref(b))
        if hr != 0: log(f"  CreateBuffer abgelehnt bei {len(bufs)*CHUNK/GB:.2f} GB (0x{hr & 0xffffffff:08x})"); break
        update(b, 0, None, src, 0, 0); wait()
        bufs.append(b)
        m = mem()
        if len(bufs) % 8 == 0: log(f"  {len(bufs)*CHUNK/GB:5.2f} GB  Nutzung {m.Usage/GB:.2f} / Budget {m.Budget/GB:.2f}  {time.time()-t0:.0f} s")
        if m.Budget and m.Usage > m.Budget: log(f"  Budget ueberschritten bei {len(bufs)*CHUNK/GB:.2f} GB"); break
    ok = len(bufs) * CHUNK
    log(f"  ERGEBNIS: {ok/GB:.2f} GB beschrieben in {time.time()-t0:.0f} s")

    # Rueckgriff-Test: ersten Puffer erneut beschreiben (ausgelagert? -> langsam)
    t = time.time(); update(bufs[0], 0, None, src, 0, 0); wait()
    log(f"  erneut schreiben 1. Puffer: {CHUNK/MB/(time.time()-t):.0f} MB/s")
    for b in bufs: release(b)
    bufs = []

    # ---------- Teil 2: Lesetempo ----------
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        files = glob.glob(r"C:\aura\models\**\*.safetensors", recursive=True)
        path = max(files, key=os.path.getsize) if files else None
    if not path: log("\n[2] keine Datei gefunden"); return
    size = os.path.getsize(path)
    log(f"\n[2] Datei {os.path.basename(path)} ({size/GB:.2f} GB)")
    buf = bytearray(64 * MB); mv = memoryview(buf)
    for name in ("1. Lesen (kalt, falls Datei seit Neustart unbenutzt)", "2. Lesen (Windows-Cache)"):
        t = time.time(); n = 0
        with open(path, "rb", buffering=0) as f:
            while True:
                k = f.readinto(mv)
                if not k: break
                n += k
        log(f"  {name}: {n/MB/(time.time()-t):.0f} MB/s")

    g = c_void_p(); create_buf(byref(BUFDESC(64 * MB, 0, 0x8 | 0x80, 0, 0x20, 0)), None, byref(g))
    cbuf = (ctypes.c_ubyte * (64 * MB)).from_buffer(buf)
    t = time.time(); n = 0
    with open(path, "rb", buffering=0) as f:
        while n < min(size, 4 * GB):
            k = f.readinto(mv)
            if not k: break
            update(g, 0, None, cbuf, 0, 0); n += k
    wait()
    log(f"  Datei -> GPU-Puffer (4 GB, wie Experten nachladen): {n/MB/(time.time()-t):.0f} MB/s")
    t = time.time()
    for _ in range(32): update(g, 0, None, cbuf, 0, 0)
    wait()
    log(f"  RAM -> GPU-Puffer: {32*64/(time.time()-t):.0f} MB/s")
    del cbuf; release(g)
    log("\nfertig")

if __name__ == "__main__":
    try: main()
    except Exception as e: log(f"ABBRUCH: {e!r}")
