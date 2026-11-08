"""Test Acta-Nova-Suche ohne AURA-Oberflaeche.
Aufruf:  py tools\\actanova_suche.py <datei|inhalt|dossier|thema> "Suchbegriff"
Voraussetzung: Edge-Fenster (aus edge_test) offen und bei Acta Nova angemeldet.
Ausgabe: Konsole + tools\\actanova_suche.txt
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from aura.engine import actanova  # noqa: E402

LOG = []


def out(s=""):
    print(s)
    LOG.append(str(s))


def zeige(titel, block, gruppieren=False):
    if not block:
        return
    n = len(block["treffer"])
    out(f"\n=== {titel}: {n} auf Seite 1 (Gesamt: {block['anzahl']}{', weitere vorhanden' if block['weitere'] else ''}) ===")
    out("Spalten: " + " | ".join(k for k in block["kopf"] if k))
    if block["info"] == "keine" and not n:
        out("  keine Treffer")
    if gruppieren:
        for dossier, docs in actanova.nach_dossier(block["treffer"]).items():
            out(f"  [{len(docs)}] {dossier}")
            for d in docs[:5]:
                out(f"      - {d.get('Name', '?')} | {d.get('Federführung', '')} | {d.get('Status', '')}")
    else:
        for t in block["treffer"]:
            felder = {k: v for k, v in t.items() if not k.startswith("_")}
            out("  - " + " | ".join(f"{k}: {v}" for k, v in felder.items())[:300])


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    modus, begriff = sys.argv[1], " ".join(sys.argv[2:])
    erg = actanova.suche(modus, begriff)
    out(f"Modus: {modus} | Begriff: {begriff}")
    out("Ablauf: " + "; ".join(erg["protokoll"]))
    zeige("Dossiers", erg.get("dossiers"))
    zeige("Dokumente", erg.get("dokumente"), gruppieren=(modus == "thema"))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:
        out(f"[FEHLER] {type(e).__name__}: {e}")
    finally:
        (ROOT / "tools" / "actanova_suche.txt").write_text("\n".join(LOG), encoding="utf-8")
