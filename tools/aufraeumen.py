# aufraeumen.py - verschiebt alte Reste von C:\aura nach C:\aura\_sicherung\20261010\ (nichts wird geloescht).
# Ohne Zusatz: zeigt nur, was passieren wuerde. Mit --ausfuehren: verschiebt wirklich.
# Vorher AURA schliessen. Rueckgaengig: Ordner aus _sicherung im Explorer zurueckziehen.
import shutil, sys
from pathlib import Path

ROOT = Path(r"C:\aura")
ZIEL = ROOT / "_sicherung" / "20261010"
WEG = [
    "comtypes",                              # Doppel von vendor\comtypes
    "engine",                                # alte Vorversion von aura\engine
    "mails.db",
    "AURA_debug.bat.old",
    r"data\outputs",
    r"data\wf_runs",
    r"wissen\_umgezogen_beschaffungsrecht",  # liegt in workflows\verfahrensentscheid\wissen
    r"workflows\_alt",
    r"workflows\vorlagen",                  # alter Einzeldatei-Weg (Kurzprüfung, alte VE-Vorlage)
    r"workflows\dokument_kurzpruefung.json",
]

echt = "--ausfuehren" in sys.argv
for rel in WEG:
    q = ROOT / rel
    if not q.exists(): print(f"  fehlt schon:   {rel}"); continue
    if q.is_dir() and rel.startswith("data") and any(q.iterdir()):
        print(f"  NICHT leer, bleibt: {rel}"); continue
    z = ZIEL / rel
    if echt:
        z.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(q), str(z))
        print(f"  verschoben:    {rel}")
    else:
        print(f"  würde verschieben: {rel}")
print("Fertig." if echt else "\nNur Vorschau. Zum Ausführen:  py %USERPROFILE%\\Downloads\\aufraeumen.py --ausfuehren")
