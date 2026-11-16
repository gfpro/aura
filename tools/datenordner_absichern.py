# tools/datenordner_absichern.py — NTFS-Rechte von data\, logs\, workflows\, wissen\ auf «nur ich + SYSTEM + Administratoren»
# setzen. Version 20261116v249 (v249: Rückgabewert 1 bei Fehlern; wird jetzt mit ausgeliefert). Nur Windows. Keine Daten werden verschoben oder gelöscht.
# Aufruf:  py tools\datenordner_absichern.py            -> zeigt, was geschehen würde (nichts wird geändert)
#          py tools\datenordner_absichern.py --setzen   -> sichert die bisherigen Rechte und setzt die neuen
#          py tools\datenordner_absichern.py --zurueck <Sicherungsdatei>   -> alte Rechte wiederherstellen (Rollback)
# Hintergrund: Ordner direkt unter C:\ erben oft «Authentifizierte Benutzer: Ändern» – andere Konten auf demselben Gerät
# könnten dann Datenbank, Logs und Läufe lesen. SIDs statt Gruppennamen (sprachunabhängig).
import getpass, os, subprocess, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORDNER = ["data", "logs", "workflows", "wissen"]
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)

def _icacls(*args):
    return subprocess.run(["icacls", *args], capture_output=True, text=True, creationflags=FLAGS)

def main(a):
    if os.name != "nt": print("Nur unter Windows."); return 1
    user = f"{os.environ.get('USERDOMAIN', '')}\\{getpass.getuser()}".lstrip("\\")
    ziele = [ROOT / o for o in ORDNER if (ROOT / o).is_dir()]
    if a[:1] == ["--zurueck"] and len(a) == 2:
        r = _icacls(str(ROOT), "/restore", a[1]); print(r.stdout or r.stderr); return r.returncode
    print(f"Benutzer: {user}\nOrdner: " + ", ".join(str(z) for z in ziele))
    if a[:1] != ["--setzen"]: print("Probelauf – mit --setzen ausführen."); return 0
    bak = ROOT / "_sicherung" / f"acl_{datetime.now():%Y%m%d_%H%M%S}.txt"; bak.parent.mkdir(exist_ok=True)
    for z in ziele:                                       # icacls /save je Ordner (relativ zu ROOT, für /restore)
        r = _icacls(str(z), "/save", str(bak.with_name(bak.stem + f"_{z.name}.txt")), "/t", "/c")
        if r.returncode: print(f"Sicherung fehlgeschlagen für {z}: {r.stderr.strip()} – nichts geändert."); return 1
    fehler = 0
    for z in ziele:
        r = _icacls(str(z), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F", "/t", "/c")
        fehler += r.returncode != 0
        print(f"{z.name}: {'ok' if r.returncode == 0 else 'FEHLER ' + (r.stderr or r.stdout).strip()}")
    print(f"Rollback: py tools\\datenordner_absichern.py --zurueck {bak.parent}\\{bak.stem}_<ordner>.txt")
    return 1 if fehler else 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
