# aura/workflow/feldplan.py — Feldplan einer Word-Vorlage: woher kommt jeder Wert? Version 20261011v64a2
#
# Grundlage für «Workflow beschreiben» mit Vorlage: zuerst die Vorlage verstehen, dann erst das Wissen.
# Ohne Sprachmodell (Sekunden): Abschnitte aus Überschriften, Kontrollkästchen-Gruppen aus Tabellen/Abschnitten,
# Begleitfelder (Text neben einem Kästchen), Herkunft per allgemeinen Formular-Heuristiken.
# Herkunft: fakt (steht in den Unterlagen) · abgeleitet (Regel nötig) · fest (immer gleich) · manuell (nur Mensch weiss es)
#           · leer (nicht nötig) · offen (noch unklar – prüft v64b mit dem Sprachmodell)
# Keine Fachinhalte: nur Form-Merkmale (Feldtyp, Code-Muster, Personen-/Datum-/Begründungsfelder).
import html, json, re, zipfile
from datetime import datetime
from pathlib import Path
from .docx_fill import analyze_xml, _plain

VERSION = 1
HERKUNFT = {"fakt": "Fakt aus Unterlagen", "abgeleitet": "Abgeleitet (Regel)", "fest": "Fest", "manuell": "Manuell",
            "leer": "Leer lassen", "offen": "Offen (prüfen)"}

_TAG = re.compile(r"<(/?)w:(tbl|tr|tc|p)(?=[\s>/])[^>]*?(/?)>")
_CODE = re.compile(r"^(?:[A-Z]\d{3,4}|\d{2,4})(?=\s)")          # «A0005 …», «1018 …», «02 …», «300 …»
_PERSON = re.compile(r"kurzzeichen|ersteller|unterschrift|visum|verantwortliche|leiter/?in|sachbearbeit|"
                     r"\bvorname\b|\bname\b|telefon|e-?mail|ort,? datum", re.I)
_FREI = re.compile(r"begründung|bemerkung|kommentar|erläuterung|stellungnahme", re.I)

# ----------------------------------------------------------------------------- Struktur der Vorlage
def _spans(x):
    """Absätze, Tabellenzeilen, Tabellen als (start, ende, tiefe) – verschachtelte Tabellen berücksichtigt."""
    out = {"p": [], "tr": [], "tbl": []}; st = []
    for m in _TAG.finditer(x):
        close, tag, selfc = m.group(1), m.group(2), m.group(3)
        if tag == "tc": continue
        if selfc: out[tag].append((m.start(), m.end(), len(st))); continue
        if not close: st.append((tag, m.start()))
        else:
            while st and st[-1][0] != tag: st.pop()
            if st: t, a = st.pop(); out[tag].append((a, m.end(), len(st)))
    for k in out: out[k].sort()
    return out

def _inner(spans, pos):
    """Innerster Bereich, der pos enthält (oder None)."""
    best = None
    for a, b, d in spans:
        if a > pos: break
        if a <= pos < b and (best is None or d > best[2]): best = (a, b, d)
    return best

def _outer(spans, pos):
    for a, b, d in spans:
        if a > pos: break
        if a <= pos < b and d == min(dd for aa, bb, dd in spans if aa <= pos < bb): return (a, b, d)
    return None

def _heading_styles(styles_xml):
    """styleId -> Ebene, für Formatvorlagen «heading N» / «Title» (sprachunabhängig über w:name)."""
    lv = {}
    for m in re.finditer(r'<w:style\b[^>]*w:styleId="([^"]+)"[^>]*>(.*?)</w:style>', styles_xml or "", re.S):
        sid, body = m.group(1), m.group(2)
        n = (re.search(r'<w:name w:val="([^"]*)"', body) or [None, ""])[1].lower()
        h = re.match(r"heading (\d)$", n)
        o = re.search(r'<w:outlineLvl w:val="(\d)"', body)
        if h: lv[sid] = int(h.group(1))
        elif o and int(o.group(1)) < 9: lv[sid] = int(o.group(1)) + 1
    return lv

def _abschnitte(x, spans, styles_xml):
    """[(pos, nummer, titel)] – Überschriften (mit Nummer 1, 1.1 …) und Seitenumbruch-Titel wie «Anhang 1: …»."""
    lv = _heading_styles(styles_xml); zaehler = [0] * 9; out = []
    tbls = spans["tbl"]
    for a, b, d in spans["p"]:
        p = x[a:b]
        t = re.sub(r"\s+", " ", _plain(p).replace("﻿", "")).strip()
        if not t or len(t) > 120: continue
        s = re.search(r'<w:pStyle w:val="([^"]+)"', p)
        o = re.search(r'<w:outlineLvl w:val="(\d)"', p)
        ebene = lv.get(s.group(1)) if s else None
        if ebene is None and o and int(o.group(1)) < 9: ebene = int(o.group(1)) + 1
        if ebene:
            zaehler[ebene - 1] += 1
            for i in range(ebene, 9): zaehler[i] = 0
            out.append((a, ".".join(str(z) for z in zaehler[:ebene] if z) or "", t)); continue
        if "<w:pageBreakBefore" in p and len(t) <= 80 and not _inner(tbls, a):     # z.B. «Anhang 1: Erfassungstabelle»
            out.append((a, "", t))
    return out

def _row_text(x, span):
    return re.sub(r"\s+", " ", _plain(x[span[0]:span[1]]).replace("﻿", "")).strip()

def struktur(x, styles_xml=""):
    """Felder aus docx_fill.analyze_xml plus abschnitt, tabelle, zeile, absatz, kontext, kopf (Zwischentitel)."""
    fields = analyze_xml(x); sp = _spans(x); ab = _abschnitte(x, sp, styles_xml)
    fpos = [f["start"] for f in fields]
    # Tabellenzeilen ohne Feld, aber mit Text = Kopfzeilen; sie trennen Gruppen innerhalb einer Tabelle
    kopf = []
    for a, b, d in sp["tr"]:
        if any(a <= p < b for p in fpos): continue
        t = _row_text(x, (a, b))
        if t and len(t) < 300: kopf.append((a, b, t))
    for f in fields:
        p = f["start"]
        h = [s for s in ab if s[0] < p]
        f["abschnitt"] = (f"{h[-1][1]} {h[-1][2]}".strip() if h else "Kopfteil")
        tb = _outer(sp["tbl"], p); f["tabelle"] = tb[0] if tb else None
        tr = _inner(sp["tr"], p); f["zeile"] = tr[0] if tr else None
        pa = _inner(sp["p"], p); f["absatz"] = pa[0] if pa else None
        f["kontext"] = (_row_text(x, tr) if tr else _row_text(x, pa) if pa else "")[:240]
        k = [t for a, b, t in kopf if tb and tb[0] <= a < p and (not h or a > h[-1][0])]
        f["kopf"] = _kopf_kurz(k[-1]) if k else ""
        f["kopf_n"] = len(k)
    return fields

def _kopf_kurz(t):
    """«Vertragstyp Vertragstyp Vertragstyp» -> «Vertragstyp»."""
    w = t.split(" "); n = len(w)
    for L in range(1, n // 2 + 1):
        if n % L == 0 and w[:L] * (n // L) == w: return " ".join(w[:L])
    return t if len(t) <= 60 else t[:60].rsplit(" ", 1)[0] + " …"

# ----------------------------------------------------------------------------- Feldplan
def _label(f):
    return re.sub(r"@\d+$", "", f["key"])

def _herkunft_feld(f):
    lab = _label(f)
    if _CODE.match(lab): return "abgeleitet", "Code-Muster in der Beschriftung"
    if _PERSON.search(lab): return "manuell", "Person/Kurzzeichen/Unterschrift"
    if f["typ"] == "datum": return "manuell", "Datum (z.B. Erstellung) – evtl. «fest: heute»"
    if _FREI.search(lab) and f["typ"] == "text": return "manuell", "Begründung/Bemerkung – Vorschlag später möglich"
    if f["typ"] in ("auswahl", "kombination"): return "offen", f"Auswahlliste mit {len(f['optionen'])} Werten"
    return "offen", ""

def erstellen(fields, vorlage=""):
    """fields: struktur(...). Ergebnis: dict mit «eintraege» (Gruppen und Einzelfelder in Dokumentreihenfolge)."""
    by_nr = {f["nr"]: f for f in fields}
    kb = [f for f in fields if f["typ"] == "kontrollkaestchen"]
    # Begleitfelder: Text-/Datumsfeld in derselben Tabellenzeile bzw. demselben Absatz wie ein Kästchen
    ort = lambda f: f["zeile"] if f["zeile"] is not None else f["absatz"]
    begleit = {}
    for o in {ort(f) for f in fields if ort(f) is not None}:
        ks = [k for k in kb if ort(k) == o]
        ts = [f for f in fields if f["typ"] != "kontrollkaestchen" and ort(f) == o and ks and f["start"] > ks[0]["start"]]
        if len(ks) > 1 and len(ks) == len(ts):                       # zwei Kästchen, zwei Felder: der Reihe nach
            for k, t in zip(ks, ts): begleit[t["nr"]] = k["nr"]
        else:
            for t in ts: begleit[t["nr"]] = [k for k in ks if k["start"] < t["start"]][-1]["nr"]
    # Gruppen: Kästchen im selben Abschnitt, in derselben Tabelle, zwischen denselben Kopfzeilen
    gruppen = {}
    for k in kb:
        gruppen.setdefault((k["abschnitt"], k["tabelle"], k["kopf_n"]), []).append(k)
    eintraege, erledigt = [], set()
    for f in fields:
        if f["nr"] in erledigt: continue
        if f["typ"] == "kontrollkaestchen":
            g = gruppen[(f["abschnitt"], f["tabelle"], f["kopf_n"])]
            nrs = [k["nr"] for k in g]; erledigt.update(nrs)
            labs = [_label(k) for k in g]
            if len(g) == 1:
                her, grund = _herkunft_feld(f)
                if her == "offen": grund = "einzelnes Kästchen (ja/nein)"
            elif all(_CODE.match(l) for l in labs): her, grund = "abgeleitet", "alle Optionen sind Codes"
            else: her, grund = "offen", f"{len(g)} Kästchen = eine Auswahl"
            bf = [n for n, k in begleit.items() if k in nrs]
            eintraege.append({"id": f"g{nrs[0]}", "art": "gruppe" if len(g) > 1 else "feld", "nrs": nrs, "keys": [k["key"] for k in g],
                              "abschnitt": f["abschnitt"], "titel": f["kopf"] or f["abschnitt"], "typ": "kontrollkaestchen",
                              "optionen": labs, "mehrfach": False, "begleitfelder": bf,
                              "herkunft": her, "grund": grund, "kontext": f["kontext"] if len(g) == 1 else ""})
            continue
        her, grund = _herkunft_feld(f)
        if f["nr"] in begleit:
            grund = (f"gehört zu Kästchen Nr. {begleit[f['nr']]}" + (f"; {grund}" if grund else ""))
        eintraege.append({"id": f"f{f['nr']}", "art": "feld", "nrs": [f["nr"]], "keys": [f["key"]], "abschnitt": f["abschnitt"],
                          "titel": _label(f), "typ": f["typ"], "optionen": f["optionen"],
                          "zu": begleit.get(f["nr"]), "herkunft": her, "grund": grund, "kontext": f["kontext"]})
    eintraege.sort(key=lambda e: e["nrs"][0])
    return {"version": VERSION, "vorlage": vorlage, "erstellt": datetime.now().isoformat(timespec="seconds"),
            "felder": len(fields), "eintraege": eintraege}

def zusammenfassung(plan):
    z = {}
    for e in plan["eintraege"]: z[e["herkunft"]] = z.get(e["herkunft"], 0) + 1
    n_g = sum(1 for e in plan["eintraege"] if e["art"] == "gruppe")
    teile = [f"{z[k]} {k}" for k in HERKUNFT if z.get(k)]
    return f"{plan['felder']} Vorlagenfelder → {len(plan['eintraege'])} Einträge ({n_g} Gruppen): " + " · ".join(teile)

# ----------------------------------------------------------------------------- Datei
def pfad(vorlage):
    p = Path(vorlage); return p.with_name(p.stem + ".feldplan.json")

def analysieren(vorlage, rel=""):
    with zipfile.ZipFile(vorlage) as z:
        x = z.read("word/document.xml").decode("utf-8")
        st = z.read("word/styles.xml").decode("utf-8") if "word/styles.xml" in z.namelist() else ""
    return erstellen(struktur(x, st), rel or Path(vorlage).name)

def laden(vorlage):
    p = pfad(vorlage)
    if not p.exists(): return None
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return None

def mischen(neu, alt):
    """Von Hand gesetzte Herkunft/Mehrfach aus dem alten Plan übernehmen (Abgleich über die Feldschlüssel)."""
    if not alt: return neu
    hand = {tuple(e["keys"]): e for e in alt.get("eintraege", []) if e.get("von_hand")}
    for e in neu["eintraege"]:
        h = hand.get(tuple(e["keys"]))
        if h:
            for k in ("herkunft", "mehrfach", "notiz", "wert", "quelle", "hinweis", "regel", "wissen", "platzhalter", "regeln", "sonst"):
                if k in h: e[k] = h[k]
            e["von_hand"] = True
    return neu

def speichern(vorlage, plan):
    p = pfad(vorlage); tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(p)
    return p

if __name__ == "__main__":                                            # py -m aura.workflow.feldplan <vorlage.docx>
    import sys
    pl = analysieren(sys.argv[1])
    for e in pl["eintraege"]:
        nr = f"{e['nrs'][0]}–{e['nrs'][-1]}" if len(e["nrs"]) > 1 else str(e["nrs"][0])
        print(f"{nr:>8} {e['herkunft']:<10} {e['art']:<6} {e['abschnitt'][:34]:<34} {e['titel'][:44]:<44} {e['grund']}")
    print("\n" + zusammenfassung(pl))
