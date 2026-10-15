# aura/workflow/zonen.py — Workflow in drei Bereichen lesen (rein · wissen/tun · raus). Version 20261015v91
# (v95: «Dokumente lesen» mit alle_eingaben liest jede Datei-Eingabe)
# (v93: Verweise auf Eingaben prüfen – fehlende Eingabe bzw. Eingabe, die kein Schritt liest = rot; verweise())
# (v91: Zählung der Hilfsdokumente robust; Vorlagen im Ordner auch ohne Schritt; Einträge tragen eine Aktion (4. Element))
# Reine Funktion ohne Oberfläche: liest eine workflow.json (dict) und liefert, was die Übersicht zeigt.
# Keine Fachinhalte – nur Bausteine. Fehlendes wird als «rot» markiert, damit die Oberfläche nachfragen kann.
import json, re
from pathlib import Path

AUSGABE = {"meldung": "Anzeige in AURA", "mail_an_mich": "Mail an mich (Entwurf)", "file_out": "Datei speichern"}


def _zr(z):
    try:
        from .assistent import ZEITRAUM_LABEL
        return ZEITRAUM_LABEL.get(z, z or "")
    except Exception: return z or ""


def _zeitplan_text(zp):
    try:
        from ..zeitplan import beschreibung
        return beschreibung(zp)
    except Exception:
        t = zp.get("tage"); return f"{t if isinstance(t, str) else ', '.join(t or [])} um {zp.get('zeit', '?')}"


def _kurz(t, n=90):
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[:n] + " …"


def _txt(x):
    if isinstance(x, str): return x
    if isinstance(x, dict): return x.get("titel") or x.get("feld") or x.get("name") or json.dumps(x, ensure_ascii=False)
    return str(x)


DOK_EXT = {".pdf", ".docx", ".doc", ".txt", ".md", ".html", ".htm"}

def _eigene_docs(pkg):
    """v91: Anzahl Dokumente im eigenen Wissen des Pakets (None = unbekannt).
    Zuerst sammlung.json (wo immer sie im Wissensordner liegt), sonst Dokumentdateien zählen."""
    if pkg is None: return None
    w = Path(pkg) / "wissen"
    if not w.is_dir(): return 0
    try:
        for sj in sorted(w.rglob("sammlung.json"), key=lambda x: len(x.parts)):
            if "_entfernt" in sj.parts: continue
            d = json.loads(sj.read_text(encoding="utf-8"))
            docs = d.get("dokumente") if isinstance(d, dict) else None
            if isinstance(docs, list) and docs: return len(docs)
        return sum(1 for f in w.rglob("*") if f.is_file() and f.suffix.lower() in DOK_EXT and "_entfernt" not in f.parts)
    except Exception: return None


def _vorlage_info(pkg, s):
    """(titel, unter, rot) für eine Word-Vorlage plus Zusatzpunkte aus dem Feldplan."""
    rel = s.get("vorlage") or ""; out = []
    p = (Path(pkg) / rel) if pkg is not None and rel else None
    if p is None or not p.is_file():
        return [("Vorlage fehlt", rel or "keine Vorlage gewählt", True)]
    n_map = len(s.get("felder") or {}); total = None
    try:
        from .docx_fill import analyze
        total = len(analyze(p))
    except Exception: pass
    out.append((f"Word-Vorlage {p.stem}", (f"{total} Felder · " if total is not None else "") + f"{n_map} zugeordnet", n_map == 0))
    try:
        from . import feldplan as FP
        plan = FP.laden(p) or {}
        ein = plan.get("eintraege") or []
        offen = sum(1 for e in ein if e.get("herkunft") == "offen")
        ohne = sum(1 for e in ein if e.get("herkunft") == "fakt" and not (e.get("quelle") or e.get("hinweis")))
        if offen: out.append((f"{offen} Felder: Herkunft offen", "unter «Felder zuordnen» festlegen", True))
        if ohne: out.append((f"{ohne} Felder ohne Angabe, wo sie stehen", "AURA sucht selbst – genauer mit Angabe", False))
    except Exception: pass
    return out


def verweise(raw):
    """v93: (fehlend, ungelesen, nutzer) – fehlend: {id: [Schritt-Namen]} = Schritte lesen eine Eingabe, die es nicht gibt;
    ungelesen: [id] Datei-Eingaben, die kein Schritt liest."""
    ids = {i.get("id") for i in raw.get("inputs") or []}; fehlend, gelesen = {}, set()
    alle = any(s.get("type") == "extract" and s.get("alle_eingaben") for s in raw.get("steps") or [])      # v95
    for s in raw.get("steps") or []:
        if s.get("type") == "extract" and s.get("alle_eingaben"): s = {k: v for k, v in s.items() if k != "files"}
        for m in set(re.findall(r"(?<![\w.])input\.(\w+)", json.dumps(s, ensure_ascii=False))):
            gelesen.add(m)
            if m not in ids: fehlend.setdefault(m, []).append(s.get("label") or s.get("id", "?"))
    ungelesen = [] if alle else [i.get("id") for i in raw.get("inputs") or [] if i.get("type") == "files" and i.get("id") not in gelesen]
    return fehlend, ungelesen


def analyse(raw, pkg=None):
    """raw = workflow.json als dict, pkg = Paketordner (oder None).
    Rückgabe: {"start", "rein", "wissen", "raus": [(titel, unter, rot)], "vorlagen": [rel], "fehlt": int}"""
    steps = raw.get("steps") or []; zp = raw.get("zeitplan")
    rein, wissen, raus, vorlagen = [], [], [], []
    start = "Start: " + (f"Zeitplan, {_zeitplan_text(zp)}" if zp else "manuell")
    # ① Was kommt rein?
    fehlend, ungelesen = verweise(raw)
    for n, i in enumerate(raw.get("inputs") or []):
        art = "Dateien" if i.get("type") == "files" else "Text"; los = i.get("id") in ungelesen
        rein.append((i.get("label") or i.get("id", "?"), f"{art}, {'freiwillig' if i.get('optional') else 'Pflicht'}"
                     + (" · wird von keinem Schritt gelesen" if los else ""), los, ("eingabe", i.get("id"))))
    for m, wer in fehlend.items():
        rein.append(("Schritt liest eine fehlende Eingabe", f"«{', '.join(wer[:2])}» liest «{m}» – diese Eingabe gibt es nicht mehr. "
                     "«Reparieren» verbindet den Schritt mit einer vorhandenen Eingabe.", True, ("repar", m)))
    for s in steps:
        t = s.get("type")
        if t == "kalender": rein.append(("Meine Termine", _zr(s.get("zeitraum")), False))
        elif t == "mails": rein.append(("Meine Mails", _zr(s.get("zeitraum")) + (f" · «{s['suche']}»" if s.get("suche") else ""), False))
        elif t == "fuer_jedes" and (s.get("schritt") or {}).get("type") == "mails":
            rein.append(("Meine Mails zu jedem Eintrag", _zr((s.get("schritt") or {}).get("zeitraum")), False))
    if not rein: rein.append(("Keine Eingabe", "Woraus soll AURA die Angaben nehmen?", True))
    if zp and any(i.get("type") == "files" and not i.get("optional") for i in raw.get("inputs") or []):
        rein.append(("Zeitplan und Pflicht-Dateien", "Ein Lauf nach Zeitplan kann keine Dateien abfragen", True))
    # ② Was soll AURA wissen und tun?
    pins = [p for s in steps if s.get("type") == "rag" for p in (s.get("pin") or [])]
    for k in raw.get("knowledge") or []:
        sam = k.get("sammlung", "")
        if sam == "eigen" or sam.startswith("wf:"):
            n = _eigene_docs(pkg)
            wissen.append(("Eigene Hilfsdokumente", "noch keine Dokumente abgelegt" if n == 0 else
                           (f"{n} Dokument{'e' if n != 1 else ''}" if n is not None else ""), n == 0))
        else: wissen.append((sam, "gemeinsame Sammlung", False))
    if pins: wissen.append(("Immer dabei", ", ".join(pins[:6]) + (" …" if len(pins) > 6 else ""), False))
    for s in steps:
        t = s.get("type"); lab = s.get("label") or ""
        if t == "llm":
            f = [x for x in s.get("fields") or [] if isinstance(x, dict) and x.get("name")]
            werte = [x.get("label") or x["name"] for x in f if not x.get("vorschlag")]
            vor = [x.get("label") or x["name"] for x in f if x.get("vorschlag")]
            if f:
                wissen.append((lab or "Herauslesen", f"{len(werte)} Werte: " + ", ".join(werte[:5]) + (" …" if len(werte) > 5 else ""), False))
                if vor: wissen.append(("Vorschläge (nur Prüfbericht)", ", ".join(vor[:4]), False))
            else: wissen.append((lab or "Text schreiben", _kurz(s.get("prompt", "").split("\n")[0], 80), False))
        elif t == "regel":
            r = s.get("regeln") or []
            wissen.append((lab or "Wenn … dann", f"{len(r)} Regel{'n' if len(r) != 1 else ''}" +
                           (f", z.B. «{_kurz(r[0].get('name', ''), 50)}»" if r and isinstance(r[0], dict) and r[0].get("name") else ""),
                           not r))
        elif t == "pruefliste":
            n = len(s.get("punkte") or [])
            wissen.append(("Prüfliste", f"{n} Prüfpunkte" if n else "noch keine Prüfpunkte", n == 0))
    off = raw.get("offene_regeln") or []
    if off: wissen.append((f"{len(off)} Regel{'n' if len(off) != 1 else ''} noch nicht umgesetzt",
                           ", ".join(_kurz(_txt(x), 40) for x in off[:3]), True))
    if not wissen: wissen.append(("Nichts zu tun", "weder Anweisung noch Regel", True))
    # ③ Was kommt raus?
    for s in steps:
        t = s.get("type")
        if t == "word_vorlage":
            raus += [x + (("vorlage", s.get("vorlage")),) for x in _vorlage_info(pkg, s)]
            if s.get("vorlage"): vorlagen.append(s["vorlage"])
        elif t in AUSGABE: raus.append((AUSGABE[t], s.get("label") if s.get("label") != AUSGABE[t] else "", False))
    if pkg is not None and (Path(pkg) / "vorlagen").is_dir():          # v91: hochgeladen, aber noch kein Schritt
        for f in sorted((Path(pkg) / "vorlagen").glob("*.docx")):
            rel = f"vorlagen/{f.name}"
            if rel not in vorlagen and not f.name.startswith("~$"):
                raus.append((f"Word-Vorlage {f.stem}", "hochgeladen, noch nicht verwendet – «Felder zuordnen …», dann bauen", True,
                             ("vorlage", rel)))
                vorlagen.append(rel)
    if not raus: raus.append(("Kein Ergebnis", "Was soll herauskommen? Z.B. «+ Vorlage hochladen …»", True))
    if any(s.get("type") in ("llm", "pruefliste", "word_vorlage") for s in steps) or raw.get("pruefungen"):
        raus.append(("Prüfbericht", "nur wenn es Hinweise gibt", False))
    norm = lambda z: [x if len(x) == 4 else (x[0], x[1], x[2], None) for x in z]
    rein, wissen, raus = norm(rein), norm(wissen), norm(raus)
    fehlt = sum(1 for z in (rein, wissen, raus) for x in z if x[2])
    return {"start": start, "rein": rein, "wissen": wissen, "raus": raus, "vorlagen": vorlagen, "fehlt": fehlt}
