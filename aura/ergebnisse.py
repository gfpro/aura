# aura/ergebnisse.py — Daten für die Ansicht «Ergebnisse» (Startseite). Version 20261011v54
# Liest nur, was jeder Lauf ohnehin schreibt: workflows\<name>\laeufe\<Zeit>\protokoll.json. Keine eigene Datenhaltung
# ausser data\ergebnisse.json (Zeitpunkt «zuletzt angesehen» für die Anzeige «n neu»).
import json
from datetime import datetime
from pathlib import Path

def _seen_path():
    from .config import DATA
    return Path(DATA) / "ergebnisse.json"

def gesehen():
    try: return json.loads(_seen_path().read_text(encoding="utf-8")).get("gesehen", "")
    except Exception: return ""

def als_gesehen():
    try:
        p = _seen_path(); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"gesehen": datetime.now().strftime("%Y%m%d_%H%M%S")}), encoding="utf-8")
    except Exception: pass

def laeufe(wf_dir, limit=30):
    """Neueste Läufe aller Workflow-Pakete: [{workflow, path, zeit, ordner, status, error, seconds, meldungen, files,
    pruefungen, neu}] – neueste zuerst."""
    seen, out = gesehen(), []
    for p in Path(wf_dir).glob("*/laeufe/*/protokoll.json"):
        out.append((p.parent.name, p))
    out.sort(key=lambda x: x[0], reverse=True)
    res = []
    for stamp, p in out[:limit]:
        try: d = json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        try: zeit = datetime.strptime(stamp, "%Y%m%d_%H%M%S").strftime("%d.%m. %H:%M")
        except ValueError: zeit = stamp
        files = [f for f in d.get("files") or [] if Path(f).exists()]
        res.append({"workflow": d.get("workflow", p.parent.parent.parent.name), "path": d.get("path") or str(p.parent.parent.parent / "workflow.json"),
                    "zeit": zeit, "stamp": stamp, "ordner": str(p.parent), "status": d.get("status", "?"), "error": d.get("error"),
                    "seconds": d.get("seconds", 0), "meldungen": d.get("meldungen") or [], "files": files,
                    "pruefungen": d.get("pruefungen") or [], "neu": stamp > seen})
    return res

def anzahl_neu(wf_dir): return sum(1 for r in laeufe(wf_dir, 50) if r["neu"])
