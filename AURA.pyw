# AURA.pyw — Doppelklick startet AURA ohne Konsolenfenster.
import sys, traceback, datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / "vendor")]       # mitgelieferte Pakete (comtypes) zuerst

def crash(msg):
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "crash.log").open("a", encoding="utf-8").write(f"\n--- {datetime.datetime.now()}\n{msg}\n")
    try:
        import tkinter as tk; from tkinter import messagebox
        r = tk.Tk(); r.withdraw(); messagebox.showerror("AURA", msg[-1500:] + "\n\nDetails: logs\\crash.log")
    except Exception:
        pass

try:
    import tkinter  # noqa: F401
except Exception as e:
    crash(f"tkinter ist in dieser Python-Installation nicht verfuegbar: {e}"); sys.exit(1)
try:
    from aura.gui import main
    main()
except Exception:
    crash(traceback.format_exc())
