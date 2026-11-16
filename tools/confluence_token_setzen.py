# tools/confluence_token_setzen.py — Confluence-Token verschlüsselt speichern (Windows DPAPI). Version 20261116v249
# Aufruf:  py tools\confluence_token_setzen.py             -> fragt den Token ab (Eingabe bleibt unsichtbar) und speichert ihn
#          py tools\confluence_token_setzen.py --loeschen  -> entfernt den gespeicherten Token
# Der Token liegt danach nur verschlüsselt in data\confluence_token.dpapi (nur dein Windows-Konto kann ihn lesen).
# Er wird nie im Klartext auf die Festplatte geschrieben und nicht angezeigt.
import getpass, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from aura.config import DATA                                          # noqa: E402
from aura import geheim                                               # noqa: E402

ZIEL, ALT = DATA / "confluence_token.dpapi", DATA / "confluence_token.txt"

def main(a):
    if a[:1] == ["--loeschen"]:
        for p in (ZIEL, ALT):
            if p.exists(): p.unlink(); print("Gelöscht:", p.name)
        return 0
    if a: print("Aufruf: py tools\\confluence_token_setzen.py [--loeschen]"); return 1
    t = getpass.getpass("Confluence-Token (Eingabe unsichtbar, Enter = Abbruch): ").strip()
    if not t: print("Abgebrochen – nichts geändert."); return 1
    try: geheim.speichern(ZIEL, t)
    except Exception as e: print(f"Nicht gespeichert ({type(e).__name__}: {e})."); return 1
    if ALT.exists(): ALT.unlink(); print("Alte Klartextdatei confluence_token.txt entfernt.")
    print(f"Gespeichert: {ZIEL}"); return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
