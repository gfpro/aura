# aura/workflow/graph.py — Workflow als Bild lesen: Knoten, Spalten und Pfeile für die Leinwand. Version 20261031v148
# Reine Funktion ohne Oberfläche (testbar). Die Reihenfolge bleibt die Liste «steps» in der workflow.json; die Pfeile werden
# NICHT gespeichert, sondern aus den Verweisen {{schritt.wert}} (und «Nur wenn») abgeleitet. So gibt es keine zweite Wahrheit.
# Keine Fachinhalte – nur Bausteine.
import json, re
from . import schema as S

ALLGEMEIN = {"input", "item", "now", "workflow", "true", "false", "none", "and", "or", "not"}


def _text(step):
    return json.dumps({k: v for k, v in step.items() if k not in ("id", "label")}, ensure_ascii=False)


def _verweist(txt, name):
    return bool(re.search(rf"(?<![\w.]){re.escape(name)}\.", txt))


def _namen(step):
    """Alle Namen, auf die ein Schritt mit «name.» verweist (in {{ … }} und in «Nur wenn»)."""
    txt = _text(step); out = set()
    ohne = lambda x: re.sub(r"'[^']*'|\\\"[^\"]*?\\\"|\"[^\"]*\"", "", x)   # v148: Text in Anführungszeichen («Art. 21 Abs. 2») ist kein Verweis
    for inner in re.findall(r"\{\{(.*?)\}\}", txt, flags=re.S): out |= set(re.findall(r"(?<![\w.])([A-Za-z_]\w*)\.", ohne(inner)))
    if isinstance(step.get("when"), str): out |= set(re.findall(r"(?<![\w.])([A-Za-z_]\w*)\.", ohne(step["when"])))
    return out


def _kurz(v, n=60):
    s = re.sub(r"\s+", " ", v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)).strip()
    return s if len(s) <= n else s[:n] + " …"


def bauen(raw, state=None):
    """{'start': {...}, 'nodes': [...], 'edges': [...]} – Spalte = Tiefe im Datenfluss, Farbe = Gruppe (Holen/Verarbeiten/Ausgeben)."""
    steps = [s for s in raw.get("steps", []) if isinstance(s, dict) and s.get("id")]
    ids = [s["id"] for s in steps]; pos = {sid: i for i, sid in enumerate(ids)}
    inputs = [i.get("id") for i in raw.get("inputs", []) if isinstance(i, dict)]
    nodes, edges = [], []
    for i, s in enumerate(steps):
        meta = S.BAUSTEINE.get(s.get("type"), {})
        gruppe = meta.get("gruppe", "Verarbeiten")
        txt = _text(s); probleme = []
        for o in ids:
            if o != s["id"] and _verweist(txt, o):
                ok = pos[o] < i
                edges.append({"von": o, "nach": s["id"], "ok": ok})
                if not ok: probleme.append(f"verwendet «{o}», das erst später läuft")
        fremd = sorted(n for n in _namen(s) if n not in pos and n.lower() not in ALLGEMEIN)
        probleme += [f"unbekannter Wert «{n}.…»" for n in fremd]
        for inp in inputs:
            if inp and _verweist(txt, f"input.{inp}"):
                edges.append({"von": "_start", "nach": s["id"], "ok": True}); break
        for inp in re.findall(r"(?<![\w.])input\.([A-Za-z_]\w*)", txt):
            if inp not in inputs: probleme.append(f"Eingabe «{inp}» fehlt")
        haupt = next((s.get(f["key"]) for f in meta.get("felder", []) if f["typ"] in ("text", "textarea") and s.get(f["key"])), "")
        if state is None: status = "offen"
        elif s["id"] in state:
            v = state.get(s["id"]); status = "fehler" if isinstance(v, dict) and v.get("_fehler") else "ok"
        else: status = "nicht gelaufen"
        nodes.append({"id": s["id"], "index": i, "titel": s.get("label") or meta.get("titel", s.get("type")),
                      "baustein": meta.get("titel", s.get("type")), "typ": s.get("type"), "gruppe": gruppe,
                      "bahn": S.GRUPPEN.index(gruppe) if gruppe in S.GRUPPEN else 1, "spalte": i + 1, "zeile": 0,
                      "wenn": s.get("when") or "", "kurz": _kurz(haupt) if haupt else "", "status": status,
                      "probleme": list(dict.fromkeys(probleme)), "unbekannt": not meta})
    # Spalte = Tiefe im Datenfluss (1 + tiefste Quelle); Rückverweise zählen nicht. Zeile = Reihenfolge innerhalb der Spalte.
    tiefe = {}
    for nd in nodes:
        q = [tiefe[e["von"]] for e in edges if e["nach"] == nd["id"] and e["ok"] and e["von"] in tiefe]
        tiefe[nd["id"]] = 1 + max(q, default=0)
    zeilen = {}
    for nd in nodes:
        nd["spalte"] = tiefe[nd["id"]]; nd["zeile"] = zeilen.get(nd["spalte"], 0); zeilen[nd["spalte"]] = nd["zeile"] + 1
    zp = raw.get("zeitplan")
    start = {"id": "_start", "titel": "Start", "spalte": 0, "zeile": 0, "bahn": 0, "zeitplan": bool(zp),
             "eingaben": [i.get("label") or i.get("id") for i in raw.get("inputs", []) if isinstance(i, dict)]}
    return {"start": start, "nodes": nodes, "edges": edges}


def verwendet_von(graph, sid):
    return [e["nach"] for e in graph["edges"] if e["von"] == sid]


def verwendet(graph, sid):
    return [e["von"] for e in graph["edges"] if e["nach"] == sid]
