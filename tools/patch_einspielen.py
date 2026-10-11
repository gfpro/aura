# tools/patch_einspielen.py — Patch einspielen. Version 20261011v53
# Aufruf (AURA vorher schliessen):  cd /d C:\aura   und   py tools\patch_einspielen.py  [Datei.zip]
# Ohne Angabe: neuestes AURA_patch_*.zip in C:\aura. Ablauf:
#   1. vorhandene Dateien nach _sicherung\vor_<patch>\ kopieren
#   2. Schreibschutz entfernen, Dateien aus dem ZIP an die richtige Stelle schreiben (Pfade im ZIP = ab C:\aura)
#   3. Steht im ZIP «_entfernen.txt» (eine Datei pro Zeile, ab C:\aura), werden diese nach _sicherung\vor_<patch>\_entfernt\
#      verschoben – nichts wird gelöscht.
#   4. Kontrolle: jede Datei wird zurückgelesen und mit dem ZIP verglichen.
import os, shutil, stat, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def main():
    zips = [Path(sys.argv[1])] if len(sys.argv) > 1 else sorted(ROOT.glob("AURA_patch_*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips or not zips[-1].is_file(): print("Kein AURA_patch_*.zip in", ROOT); return 1
    zp = zips[-1]; bak = ROOT / "_sicherung" / f"vor_{zp.stem}"; print("Patch:", zp.name, "\nSicherung:", bak)
    fehler = 0
    with zipfile.ZipFile(zp) as z:
        names = [n for n in z.namelist() if not n.endswith("/") and n != "_entfernen.txt"]
        for n in names:
            ziel = ROOT / n
            if ziel.exists():
                (bak / n).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(ziel, bak / n)
                os.chmod(ziel, stat.S_IWRITE | stat.S_IREAD)
            ziel.parent.mkdir(parents=True, exist_ok=True)
            data = z.read(n)
            try: ziel.write_bytes(data)
            except PermissionError: print(f"  GESPERRT  {n}  (AURA oder ein Editor hat die Datei offen?)"); fehler += 1; continue
            ok = ziel.read_bytes() == data; fehler += not ok
            print(f"  {'ok       ' if ok else 'FEHLER   '} {n}")
        if "_entfernen.txt" in z.namelist():
            for n in z.read("_entfernen.txt").decode("utf-8").splitlines():
                n = n.strip()
                if not n or n.startswith("#"): continue
                q = ROOT / n
                if q.exists():
                    d = bak / "_entfernt" / n; d.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(q), str(d))
                    print(f"  entfernt  {n}  -> {d.relative_to(ROOT)}")
    print("Fertig." if not fehler else f"{fehler} Datei(en) nicht eingespielt – AURA schliessen und nochmals ausführen.")
    return 1 if fehler else 0

if __name__ == "__main__": sys.exit(main())
