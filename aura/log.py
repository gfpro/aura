# aura/log.py — Ablauf-Log in logs\aura.log (max. 3 x 1 MB, aelteste wird ueberschrieben). Version 20261019v107
# Enthaelt KEINE Fragetexte und keine Mail-Inhalte, nur Ablauf, Zeiten, Kennzahlen und Fehler mit Zeilennummer.
# v107: mem() schreibt Fehler ins Log statt sie zu verschlucken; Handle-Typen explizit.
# v106: mem() schreibt Speicherwerte: DIAG mem phase=... ws_gb commit_gb peak_gb ram_pct sys_commit_gb sys_limit_gb
# v44: Ort logs\ (vorher data\, wird beim Start einmalig verschoben); diag() schreibt Kennzahlen als eine Zeile:
#      2026-10-10 11:02:13 INFO    [worker] DIAG llm_json modell=Qwen3.5-4B eingabe=9136 cache=3714 prefill_s=394 ...
import logging, logging.handlers, sys, threading
from .config import ROOT, DB_PATH

LOG_DIR = ROOT / "logs"
LOG_PATH = LOG_DIR / "aura.log"
_log = None

def _umziehen():
    """v44: alte Logs aus data\\ nach logs\\ verschieben (nur wenn dort noch keins liegt)."""
    for f in sorted(DB_PATH.parent.glob("aura.log*")):
        z = LOG_DIR / f.name
        try:
            if not z.exists(): f.replace(z)
        except OSError: pass

def get():
    global _log
    if _log: return _log
    _log = logging.getLogger("aura"); _log.setLevel(logging.INFO); _log.propagate = False
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True); _umziehen()
        h = logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(threadName)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
        _log.addHandler(h)
    except Exception:
        _log.addHandler(logging.NullHandler())          # Log darf AURA nie am Starten hindern
    # Unbehandelte Fehler (Hauptthread und andere Threads) ebenfalls ins Log
    sys.excepthook = lambda t, v, tb: _log.error("Unbehandelter Fehler", exc_info=(t, v, tb))
    threading.excepthook = lambda a: _log.error(f"Unbehandelter Fehler in Thread {a.thread.name if a.thread else '?'}",
                                                exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    return _log

def _fmt(v):
    if isinstance(v, bool) or v is None: return str(v)
    if isinstance(v, float): return f"{v:.2f}" if abs(v) < 100 else f"{v:.0f}"
    if isinstance(v, (list, tuple)): return ",".join(map(str, v)) or "-"
    return str(v).replace(" ", "_") or "-"

def diag(was, **werte):
    """v44: Kennzahlen als eine Zeile «DIAG <was> k=v k=v», leicht zu vergleichen. Darf nie einen Fehler werfen."""
    try: get().info("DIAG %s %s", was, " ".join(f"{k}={_fmt(v)}" for k, v in werte.items()))
    except Exception: pass

def _mem():
    """v106: Speicher dieses Prozesses und des Systems (Windows, nur ctypes). Leeres dict, wenn nicht verfuegbar."""
    import ctypes, ctypes.wintypes as w
    class PMC(ctypes.Structure):
        _fields_ = [("cb", w.DWORD), ("PageFaultCount", w.DWORD)] + [(n, ctypes.c_size_t) for n in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", w.DWORD), ("dwMemoryLoad", w.DWORD)] + [(n, ctypes.c_ulonglong) for n in (
            "ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile", "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual")]
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentProcess.restype = w.HANDLE
    k.K32GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(PMC), w.DWORD]; k.K32GetProcessMemoryInfo.restype = w.BOOL
    k.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MS)]; k.GlobalMemoryStatusEx.restype = w.BOOL
    pm = PMC(); pm.cb = ctypes.sizeof(pm)
    if not k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(pm), pm.cb):
        return dict(fehler=f"GetProcessMemoryInfo_{ctypes.get_last_error()}")
    ms = MS(); ms.dwLength = ctypes.sizeof(ms); k.GlobalMemoryStatusEx(ctypes.byref(ms))
    g = lambda b: round(b / 1e9, 2)
    return dict(ws_gb=g(pm.WorkingSetSize), commit_gb=g(pm.PrivateUsage), peak_gb=g(pm.PeakWorkingSetSize),
                ram_pct=ms.dwMemoryLoad, ram_frei_gb=g(ms.ullAvailPhys),
                sys_commit_gb=g(ms.ullTotalPageFile - ms.ullAvailPageFile), sys_limit_gb=g(ms.ullTotalPageFile))

def mem(phase, **extra):
    """v106: eine Zeile «DIAG mem phase=... ws_gb=... commit_gb=...». Darf nie einen Fehler werfen."""
    try: werte = _mem()
    except Exception as e: werte = dict(fehler=f"{type(e).__name__}:{e}")
    diag("mem", phase=phase, **werte, **extra)
