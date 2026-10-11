# aura/zeitplan.py — Workflows nach Zeitplan starten. Version 20261011v53
# Im workflow.json: "zeitplan": {"tage": "werktags" | "taeglich" | ["mo", "mi"], "zeit": "08:00"}.
# Läuft nur, solange AURA offen ist. Verpasste Läufe von HEUTE werden beim nächsten Takt nachgeholt
# (z.B. AURA um 09:12 gestartet -> Lauf von 08:00 sofort). Ältere verpasste Läufe werden nicht nachgeholt.
# Letzter Lauf je Workflow: data\zeitplan.json
import json
from datetime import datetime
from pathlib import Path

TAGE = ["mo", "di", "mi", "do", "fr", "sa", "so"]

def _tage(t):
    if t in (None, "", "taeglich", "täglich"): return set(range(7))
    if t == "werktags": return set(range(5))
    if isinstance(t, str): t = [x.strip() for x in t.split(",")]
    return {TAGE.index(x[:2].lower()) for x in t if x[:2].lower() in TAGE}

def pruefen(zp):
    errs = []
    if not isinstance(zp, dict): return ["zeitplan muss ein Objekt sein: {\"tage\": \"werktags\", \"zeit\": \"08:00\"}"]
    try: datetime.strptime(str(zp.get("zeit", "")), "%H:%M")
    except ValueError: errs.append("zeitplan: «zeit» als HH:MM angeben, z.B. 08:00")
    if not _tage(zp.get("tage")): errs.append("zeitplan: «tage» = werktags, taeglich oder z.B. [\"mo\", \"mi\"]")
    return errs

def beschreibung(zp):
    t = zp.get("tage", "taeglich")
    t = {"werktags": "werktags", "taeglich": "täglich", "täglich": "täglich"}.get(t, t) if isinstance(t, str) else ", ".join(t)
    return f"{t} um {zp.get('zeit', '?')}"

def _status_path():
    from .config import DATA
    return Path(DATA) / "zeitplan.json"

def _status():
    try: return json.loads(_status_path().read_text(encoding="utf-8"))
    except Exception: return {}

def faellig(workflows, now=None):
    """workflows: [{"path", "zeitplan"}] -> Pfade, die jetzt laufen sollen (und markiert sie als gestartet)."""
    now = now or datetime.now(); st = _status(); out = []
    for w in workflows:
        zp = w.get("zeitplan")
        if not zp or pruefen(zp) or now.weekday() not in _tage(zp.get("tage")): continue
        h, m = map(int, zp["zeit"].split(":")); soll = now.replace(hour=h, minute=m, second=0, microsecond=0)
        last = st.get(w["path"], "")
        if now >= soll and last < soll.strftime("%Y-%m-%d %H:%M"):
            out.append(w["path"]); st[w["path"]] = now.strftime("%Y-%m-%d %H:%M")
    if out:
        try:
            p = _status_path(); p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception: pass
    return out

def mit_zeitplan(wf_dir):
    """Alle Workflow-Pakete mit Zeitplan: [{"path", "name", "zeitplan"}]."""
    out = []
    for p in sorted(Path(wf_dir).glob("*/workflow.json")):
        try:
            wf = json.loads(p.read_text(encoding="utf-8"))
            if wf.get("zeitplan"): out.append({"path": str(p), "name": wf.get("name", p.parent.name), "zeitplan": wf["zeitplan"]})
        except Exception: pass
    return out

def naechster(zp, now=None):
    """Nächster Lauf (datetime) oder None."""
    from datetime import timedelta
    if not zp or pruefen(zp): return None
    now = now or datetime.now(); h, m = map(int, zp["zeit"].split(":")); tage = _tage(zp.get("tage"))
    for i in range(8):
        d = (now + timedelta(days=i)).replace(hour=h, minute=m, second=0, microsecond=0)
        if d.weekday() in tage and d > now: return d
    return None
