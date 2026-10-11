# tools/npu_test.py — prueft, ob und wie die NPU nutzbar ist. Nur lesen, aendert nichts, nur System-DLLs (ctypes).
# Aufruf in C:\aura:  python tools\npu_test.py      -> Ausgabe auch in tools\npu_test.txt
import ctypes, os, subprocess, sys, winreg
from ctypes import wintypes as W

OUT = []
def p(*a):
    s = " ".join(str(x) for x in a); print(s); OUT.append(s)

SYS32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")

# ---------------------------------------------------------------- 1. System
def reg(path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k: return winreg.QueryValueEx(k, name)[0]
    except OSError: return "?"
p("== 1. System")
p("CPU      :", reg(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString").strip())
cv = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
p("Windows  :", reg(cv, "ProductName"), reg(cv, "DisplayVersion"), f"Build {reg(cv, 'CurrentBuild')}.{reg(cv, 'UBR')}")
p("Python   :", sys.version.split()[0], "64-Bit" if sys.maxsize > 2**32 else "32-Bit")

# ---------------------------------------------------------------- 2. DLL-Versionen
def file_version(path):
    if not os.path.exists(path): return None
    ver = ctypes.WinDLL("version")
    n = ver.GetFileVersionInfoSizeW(path, None)
    if not n: return "vorhanden (keine Versionsinfo)"
    buf = ctypes.create_string_buffer(n)
    ver.GetFileVersionInfoW(path, 0, n, buf)
    pt, ln = ctypes.c_void_p(), ctypes.c_uint()
    ver.VerQueryValueW(buf, "\\", ctypes.byref(pt), ctypes.byref(ln))
    ms, ls = ctypes.cast(pt, ctypes.POINTER(ctypes.c_uint32 * 13)).contents[2:4]
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
p("\n== 2. DLLs in System32")
for d in ("DirectML.dll", "d3d12.dll", "dxcore.dll", "onnxruntime.dll", "Windows.AI.MachineLearning.dll",
          "Microsoft.AI.MachineLearning.dll", "intel_npu_umd.dll"):
    p(f"{d:34s}", file_version(os.path.join(SYS32, d)) or "-- fehlt")

# ---------------------------------------------------------------- 3. Geraete (PnP)
p("\n== 3. PnP-Klasse ComputeAccelerator (NPU)")
try:
    r = subprocess.run(["pnputil", "/enum-devices", "/class", "ComputeAccelerator"], capture_output=True,
                       text=True, timeout=30, errors="replace")
    lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    p("\n".join(lines[-12:]) if lines else f"(keine Ausgabe, Code {r.returncode})")
except Exception as e: p("pnputil nicht moeglich:", e)

# ---------------------------------------------------------------- COM-Hilfen
class GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]
def guid(s):
    h = s.replace("-", ""); g = GUID(int(h[:8], 16), int(h[8:12], 16), int(h[12:16], 16))
    for i in range(8): g.d[i] = int(h[16 + 2 * i:18 + 2 * i], 16)
    return g
def com(obj, idx, restype, *argtypes):
    """Methode Nr. idx aus der vtable von obj (c_void_p) als aufrufbare Funktion."""
    vt = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    f = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vt[idx])
    return lambda *a: f(obj, *a)
def hx(hr): return f"0x{hr & 0xFFFFFFFF:08X}"

IID_FACTORY = guid("78ee5945-c36e-4b13-a669-005dd11c0f06")
IID_LIST    = guid("526c7776-40e9-459b-b711-f32ad76dfc28")
IID_ADAPTER = guid("f0db4c7f-fe5a-42a2-bd62-f2a6cf6fc83e")
ATTR = {"D3D11_GRAPHICS": guid("8c47866b-7583-450d-f0f0-6bada895af4b"),
        "D3D12_GRAPHICS": guid("0c9ece4d-2f6e-4f01-8c96-e89e331b47b1"),
        "D3D12_CORE_COMPUTE": guid("248e2800-a793-4724-abaa-23a6de1be090"),
        "D3D12_GENERIC_ML": guid("b71b0d41-1088-422f-a27c-0250b7d3a988"),
        "D3D12_GENERIC_MEDIA": guid("8eb2c848-82f6-4b49-aa87-aecfcf0174c6")}
IID_D3D12DEVICE = guid("189819f1-1db6-4b57-be54-1821339b85f7")
IID_DMLDEVICE   = guid("6dbd6437-96fd-423f-a98c-ae5e7c2a573f")
FL = {"1_0_GENERIC": 0x100, "1_0_CORE": 0x1000, "11_0": 0xB000}
DML_LEVELS = [0x1000, 0x2000, 0x2100, 0x3000, 0x3100, 0x4000, 0x4100, 0x5000, 0x5100, 0x5200, 0x6000, 0x6100,
              0x6200, 0x6300, 0x6400]

# ---------------------------------------------------------------- 4. DXCore: welche Adapter, welche Faehigkeiten
p("\n== 4. DXCore-Adapter")
adapters = []
try:
    dx = ctypes.WinDLL(os.path.join(SYS32, "dxcore.dll"))
    fac = ctypes.c_void_p()
    hr = dx.DXCoreCreateAdapterFactory(ctypes.byref(IID_FACTORY), ctypes.byref(fac))
    if hr: raise OSError(f"DXCoreCreateAdapterFactory {hx(hr)}")
    for filt in ("D3D12_GENERIC_ML", "D3D12_CORE_COMPUTE"):
        lst = ctypes.c_void_p()
        hr = com(fac, 3, ctypes.c_long, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
            1, ctypes.byref(ATTR[filt]), ctypes.byref(IID_LIST), ctypes.byref(lst))
        if hr: p(f"Filter {filt}: nicht unterstuetzt ({hx(hr)})"); continue
        n = com(lst, 4, ctypes.c_uint32)()
        p(f"Filter {filt}: {n} Adapter")
        for i in range(n):
            ad = ctypes.c_void_p()
            if com(lst, 3, ctypes.c_long, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p)(
                    i, ctypes.byref(IID_ADAPTER), ctypes.byref(ad)): continue
            getsize = com(ad, 7, ctypes.c_long, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t))
            getprop = com(ad, 6, ctypes.c_long, ctypes.c_int, ctypes.c_size_t, ctypes.c_void_p)
            sz = ctypes.c_size_t(); getsize(2, ctypes.byref(sz))
            desc = ctypes.create_string_buffer(max(sz.value, 1)); getprop(2, sz.value, desc)
            drv = ctypes.c_uint64(); getprop(1, 8, ctypes.byref(drv))
            dv = drv.value; dvs = f"{dv >> 48}.{(dv >> 32) & 0xFFFF}.{(dv >> 16) & 0xFFFF}.{dv & 0xFFFF}"
            mem = {}
            for k, pid in (("dediziert", 7), ("geteilt", 9)):
                m = ctypes.c_uint64(); getprop(pid, 8, ctypes.byref(m)); mem[k] = m.value / 2**30
            sup = [a for a, g in ATTR.items() if com(ad, 4, ctypes.c_bool, ctypes.c_void_p)(ctypes.byref(g))]
            name = desc.value.decode(errors="replace")
            p(f"  [{i}] {name} | Treiber {dvs} | {mem['dediziert']:.1f} GB ded. / {mem['geteilt']:.1f} GB geteilt")
            p(f"      kann: {', '.join(sup)}")
            if name not in [a[0] for a in adapters]: adapters.append((name, ad, sup))
except Exception as e: p("DXCore nicht moeglich:", e)

# ---------------------------------------------------------------- 5. Entscheidender Test: D3D12 + System-DirectML auf jedem Adapter
p("\n== 5. D3D12-Geraet + DirectML (System32) je Adapter")
try:
    d3d = ctypes.WinDLL(os.path.join(SYS32, "d3d12.dll"))
    dml = ctypes.WinDLL(os.path.join(SYS32, "DirectML.dll")) if os.path.exists(os.path.join(SYS32, "DirectML.dll")) else None
    p("DMLCreateDevice1 vorhanden:", bool(dml and hasattr(dml, "DMLCreateDevice1")))
    for name, ad, sup in adapters:
        dev, used = ctypes.c_void_p(), None
        for fl in ("11_0", "1_0_CORE", "1_0_GENERIC"):
            if d3d.D3D12CreateDevice(ad, FL[fl], ctypes.byref(IID_D3D12DEVICE), ctypes.byref(dev)) == 0: used = fl; break
        if not used: p(f"  {name}: D3D12-Geraet NICHT erstellbar"); continue
        line = f"  {name}: D3D12 ok (Feature-Level {used})"
        if not dml: p(line + " | DirectML.dll fehlt"); continue
        dd = ctypes.c_void_p()
        hr = dml.DMLCreateDevice(dev, 0, ctypes.byref(IID_DMLDEVICE), ctypes.byref(dd))
        if hr: p(line + f" | DMLCreateDevice FEHLER {hx(hr)}"); continue
        arr = (ctypes.c_int * len(DML_LEVELS))(*DML_LEVELS)
        class Q(ctypes.Structure): _fields_ = [("n", ctypes.c_uint32), ("lv", ctypes.c_void_p)]
        q, res = Q(len(DML_LEVELS), ctypes.cast(arr, ctypes.c_void_p)), ctypes.c_int()
        hr = com(dd, 7, ctypes.c_long, ctypes.c_int, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p)(
            1, ctypes.sizeof(q), ctypes.byref(q), 4, ctypes.byref(res))
        lvl = f"{res.value >> 12}.{(res.value >> 8) & 0xF}" if hr == 0 else f"? ({hx(hr)})"
        p(line + f" | DirectML OK, max. Feature-Level {lvl}")
except Exception as e: p("D3D12/DirectML-Test nicht moeglich:", e)

# ---------------------------------------------------------------- 6. Windows ML / App-Runtime
p("\n== 6. Windows ML / Windows App Runtime")
wa = r"C:\Program Files\WindowsApps"
try:
    hits = sorted({d.split("_")[0] for d in os.listdir(wa) if d.startswith(("Microsoft.WindowsAppRuntime",
                   "Microsoft.Windows.AI", "Microsoft.WindowsMLRuntime", "MicrosoftWindows.Client.AI"))})
    p("\n".join(hits) or "keine passenden Pakete")
except Exception as e: p(f"{wa} nicht lesbar ({type(e).__name__}) - normal ohne Admin")

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "npu_test.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(OUT))
p("\nGespeichert: tools\\npu_test.txt")
