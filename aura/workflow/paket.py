# aura/workflow/paket.py — Workflow-Pakete: ein Ordner je Workflow. Version 20261008v36
#   workflows\<name>\workflow.json   Schritte und Logik
#                    wissen\         Dokumente nur dieses Workflows (eingebettet, Sammlung «wf:<name>»)
#                    vorlagen\       Word-Vorlagen
#                    laeufe\<Zeit>\  Eingaben, Ergebnis, Zwischenstand, Protokoll je Lauf (NICHT eingebettet)
import json, shutil
from datetime import datetime
from pathlib import Path
from .. import db
from ..wissen import WF_DIR, WISSEN_DIR, Wissen, slugify

SKELETT = {
    "description": "",
    "knowledge": [{"sammlung": "eigen"}],
    "inputs": [{"id": "files", "type": "files", "label": "Eingabedateien", "ext": [".pdf", ".docx", ".txt", ".md"]}],
    "steps": [{"id": "txt", "type": "extract", "label": "Eingaben lesen", "files": "{{input.files}}", "max_chars": 18000}]}

def pakete():
    return sorted(p.parent for p in WF_DIR.glob("*/workflow.json"))

def create(title):
    name = slugify(title)
    if not name: raise ValueError("Bitte einen Namen mit Buchstaben oder Ziffern eingeben")
    d = WF_DIR / name
    if d.exists(): raise ValueError(f"Workflow «{name}» gibt es schon")
    for sub in ("wissen", "vorlagen", "laeufe"): (d / sub).mkdir(parents=True)
    (d / "workflow.json").write_text(json.dumps(dict(name=title.strip(), **SKELETT), ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "wissen" / "sammlung.json").write_text(json.dumps({"name": f"Wissen «{title.strip()}»", "im_chat": False,
                                                            "max_alter_monate": 12, "dokumente": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    return d

def add_template(pkg, path):
    pkg = Path(pkg); (pkg / "vorlagen").mkdir(exist_ok=True)
    t = pkg / "vorlagen" / Path(path).name
    if Path(path).resolve() != t.resolve(): shutil.copy2(path, t)
    return t

def delete(pkg, wissen=None):
    """Ganzen Workflow loeschen: Ordner (nach workflows\\_geloescht) und seine Wissensstuecke in wissen.db."""
    pkg = Path(pkg); name = f"wf:{pkg.name}"
    w = wissen or Wissen(lambda: None, lambda *a: None)
    w.conn.execute("DELETE FROM items WHERE source = ?", (name,)); w.conn.execute("DELETE FROM sync_state WHERE source = ?", (name,))
    w.conn.commit(); db.rebuild_fts(w.conn); w.R.invalidate()
    trash = WF_DIR / "_geloescht"; trash.mkdir(exist_ok=True)
    shutil.move(str(pkg), str(trash / f"{datetime.now():%Y%m%d_%H%M%S}_{pkg.name}"))

def migrate(old_json, name=None, sammlung=None, wissen=None, progress=print):
    """Einzeldatei-Workflow (workflows\\x.json + workflows\\vorlagen\\ + wissen\\<sammlung>) in ein Paket umziehen.
    Die eingebetteten Stuecke werden umgeschrieben, nicht neu berechnet."""
    old_json = Path(old_json); wf = json.loads(old_json.read_text(encoding="utf-8"))
    name = slugify(name or old_json.stem); d = WF_DIR / name
    if (d / "workflow.json").exists(): raise ValueError(f"Paket «{name}» gibt es schon")
    for sub in ("wissen", "vorlagen", "laeufe"): (d / sub).mkdir(parents=True, exist_ok=True)
    for st in wf.get("steps", []):                                   # Vorlagen mitnehmen
        for key in ("vorlage", "file"):
            v = st.get(key)
            if isinstance(v, str) and "{{" not in v:
                src = old_json.parent / v
                if src.is_file():
                    shutil.copy2(src, d / "vorlagen" / src.name); st[key] = f"vorlagen/{src.name}"
                    progress(f"Vorlage uebernommen: {src.name}")
    if sammlung:
        src = WISSEN_DIR / sammlung
        if not src.is_dir(): raise ValueError(f"Sammlung «{sammlung}» nicht gefunden ({src})")
        for f in src.iterdir():
            if f.is_file(): shutil.copy2(f, d / "wissen" / f.name)
        for k in wf.get("knowledge", []):
            if (k.get("sammlung") if isinstance(k, dict) else k) == sammlung:
                if isinstance(k, dict): k["sammlung"] = "eigen"
        wf["knowledge"] = [("eigen" if k == sammlung else k) for k in wf.get("knowledge", [])]
        for st in wf.get("steps", []):
            if st.get("collection") == sammlung: st["collection"] = "eigen"
        w = wissen or Wissen(lambda: None, lambda *a: None); new = f"wf:{name}"
        for iid, loc in w.conn.execute("SELECT id, location FROM items WHERE source = ?", (sammlung,)).fetchall():
            w.conn.execute("UPDATE items SET source = ?, location = ? WHERE id = ?",
                           (new, str(d / "wissen" / Path(loc).name) if loc else loc, iid))
        w.conn.execute("UPDATE sync_state SET source = ? WHERE source = ?", (new, sammlung))
        w.conn.commit(); w.R.invalidate()
        shutil.move(str(src), str(WISSEN_DIR / f"_umgezogen_{sammlung}"))
        progress(f"Sammlung «{sammlung}» in den Workflow umgezogen (ohne neues Einbetten)")
    (d / "workflow.json").write_text(json.dumps(wf, ensure_ascii=False, indent=1), encoding="utf-8")
    alt = WF_DIR / "_alt"; alt.mkdir(exist_ok=True); shutil.move(str(old_json), str(alt / old_json.name))
    progress(f"Workflow-Paket erstellt: {d}")
    return d
