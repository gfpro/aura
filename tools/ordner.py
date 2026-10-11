# ordner.py - listet die Ordnerstruktur von C:\aura (nur Namen und Groessen, keine Inhalte).
# Aendert nichts. Ergebnis: C:\aura\tools\ordner.txt
import os
from pathlib import Path

ROOT = Path(r"C:\aura")
OUT = ROOT / "tools" / "ordner.txt"
WEG = {"__pycache__", ".git"}                                  # ganz weglassen
KURZ = {"vendor", "models", "laeufe", "kvcache", "_geloescht", "_sicherung",
        "wf_runs", "outputs", "eingaben", "wheels"}            # nur Unterordner mit Grösse, keine Dateien
MAX_DATEIEN = 40

def groesse(p):
    n = s = 0
    for d, _, fs in os.walk(p):
        for f in fs:
            try: s += os.path.getsize(os.path.join(d, f)); n += 1
            except OSError: pass
    return n, s

def gr(s):
    return f"{s / 1e6:.1f} MB" if s >= 1e6 else f"{s / 1e3:.0f} KB"

L = []
def zeige(p, tiefe):
    ein = "  " * tiefe
    try: alle = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    except OSError as e: L.append(f"{ein}[nicht lesbar: {e}]"); return
    for e in alle:
        if not e.is_dir() or e.name in WEG: continue
        n, s = groesse(e)
        L.append(f"{ein}{e.name}\\   ({n} Dateien, {gr(s)})")
        if e.name in KURZ:
            for u in sorted(x for x in e.iterdir() if x.is_dir()):
                un, us = groesse(u); L.append(f"{ein}  {u.name}\\   ({un} Dateien, {gr(us)})")
        else:
            zeige(e, tiefe + 1)
    dateien = [e for e in alle if e.is_file()]
    for f in dateien[:MAX_DATEIEN]:
        try: L.append(f"{ein}{f.name}   ({gr(f.stat().st_size)})")
        except OSError: L.append(f"{ein}{f.name}")
    if len(dateien) > MAX_DATEIEN: L.append(f"{ein}… {len(dateien) - MAX_DATEIEN} weitere Dateien")

L.append(f"{ROOT}\\")
zeige(ROOT, 1)
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"Fertig: {OUT} ({len(L)} Zeilen)")
