# aura/workflow/pruefliste.py — Baustein «pruefliste»: Dokumente gegen Prüfpunkte prüfen. Version 20261011v53
#
# v53: NUR NOCH ALLGEMEINE REGELN, kein Fachinhalt im Code. Was geprüft wird, legt der Benutzer fest (Reiter «Prüfliste»)
#      oder bringt es als Paket mit (JSON in C:\aura\pruefpakete\, z.B. «APA 7 Beispiel.json»).
#      Regeln: enthaelt, enthaelt_nicht, muster_in_abschnitt, reihenfolge, laenge, gliederung_wie_vorlage
#      + Fragen ans Sprachmodell (ja/nein/unklar mit Beleg). Alte APA-Regeln (v50/v51) werden beim Lesen umgestellt.
# Muster-Schreibweise für Anfänger: {Name} = Wort mit Grossbuchstabe (danach darf bis zum nächsten Musterteil weiterer
#      Text folgen, z.B. «& Meier»), {Jahr} = 4 Ziffern (+Buchstabe), {Zahl}, {Wort}, {Text}; alles andere wörtlich.
# Ergebnis: _pruefliste (für den Prüfbericht), fehler, hinweise, ok, nicht_pruefbar, _warnungen.
import json, re, zipfile
from pathlib import Path
from .nodes import node, read_file, _llm
from .expr import as_text

SCHWERE = ("Fehler", "Hinweis")
MAX_DETAILS = 8


# ----------------------------------------------------------------------------- Word lesen (mit Überschriften)
def _heading_styles(z):
    """styleIds, die Überschriften sind (Name «heading»/«Überschrift» oder Gliederungsebene)."""
    try: xml = z.read("word/styles.xml").decode("utf-8", "replace")
    except KeyError: return set()
    out = set()
    for m in re.finditer(r'<w:style\b[^>]*w:styleId="([^"]+)"[^>]*>(.*?)</w:style>', xml, re.S):
        sid, body = m.group(1), m.group(2)
        nm = re.search(r'<w:name w:val="([^"]+)"', body)
        if re.search(r"<w:outlineLvl ", body) or (nm and re.match(r"(heading|überschrift)\s*\d", nm.group(1), re.I)): out.add(sid)
    return out

def docx_paragraphs(path):
    """[(ist_ueberschrift, text)] eines Word-Dokuments."""
    import html
    with zipfile.ZipFile(path) as z:
        hs = _heading_styles(z); xml = z.read("word/document.xml").decode("utf-8", "replace")
    out = []
    for para in re.split(r"</w:p>", xml):
        st = re.search(r'<w:pStyle w:val="([^"]+)"', para)
        h = bool(st and (st.group(1) in hs or re.match(r"(heading|berschrift)\d", st.group(1), re.I))) or "<w:outlineLvl " in para
        para = re.sub(r"<w:tab/>", "\t", para); para = re.sub(r"<w:br/>", "\n", para)
        t = re.sub(r"[ \t\u00a0]+", " ", "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", para))).strip()
        if t: out.append((h, html.unescape(t)))
    return out

def read_doc(f):
    if Path(f).suffix.lower() == ".docx":
        return "\n".join(("## " + t) if h else t for h, t in docx_paragraphs(f))
    return re.sub(r"[ \t\u00a0]+", " ", read_file(f))

# ----------------------------------------------------------------------------- Text zerlegen

def section(text, name, max_chars=10000):
    """Abschnitt ab der Überschrift, die «name» enthält, bis zur nächsten Überschrift. Word: Überschriften aus den
    Formatvorlagen («## »). PDF/Text: nummerierte kurze Zeilen; Zeilen mit Seitenzahl am Ende (Inhaltsverzeichnis)
    zählen nicht. Mehrere Treffer: der letzte mit Inhalt. Ohne Treffer: None."""
    if not name: return text[:max_chars]
    if re.search(r"^## ", text, re.M):
        head = re.compile(rf"^## [^\n]*{re.escape(name)}[^\n]*$", re.I | re.M); nxt = re.compile(r"^## ", re.M)
    else:
        head = re.compile(rf"^[ \t]*(?:\d+(?:\.\d+)*\.?[ \t]+)?[^\n]{{0,40}}{re.escape(name)}[^\n]{{0,60}}(?<!\d)$", re.I | re.M)
        nxt = re.compile(r"^[ \t]*\d+(?:\.\d+)*\.?[ \t]+[A-ZÄÖÜ][^\n]{2,80}(?<!\d)$", re.M)
    best = None
    for m in head.finditer(text):
        rest = text[m.end():]; n = nxt.search(rest)
        sec = text[m.start():m.end() + (n.start() if n else len(rest))]
        if len(sec.strip()) > len(m.group(0)) + 80: best = sec
    return best[:max_chars] if best else None

def _key(s):
    s = s.lower()
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss"), ("é", "e"), ("è", "e")): s = s.replace(a, b)
    return re.sub(r"[^a-z0-9 ]", "", s).strip()

def _kurz(s, n=90):
    s = re.sub(r"\s+", " ", s).strip(); return s if len(s) <= n else s[:n] + " …"

def _bereich(doc, pk):
    """Text des Abschnitts (oder ganzer Text). None = Abschnitt nicht gefunden."""
    ab = str(pk.get("abschnitt", "")).strip()
    return (section(doc["text"], ab, 10 ** 7) if ab else doc["text"]), ab

def _woerter(pk):
    return [w.strip() for w in as_text(pk.get("wert", "")).split("|") if w.strip()]

_PH = {"Name": r"([A-ZÄÖÜ][\w'’\-]+)[^,;()\[\]\n]{0,60}?", "Jahr": r"(\d{4}[a-z]?)", "Zahl": r"(\d+)",
       "Wort": r"(\w+)", "Text": r"([^\n]{1,80}?)"}
def muster_regex(m):
    """«{Name}, {Jahr}» -> Regex mit Gruppen. Leerzeichen dürfen fehlen oder mehrfach sein."""
    out, pos = [], 0
    for x in re.finditer(r"\{(\w+)\}", m):
        out.append(re.escape(m[pos:x.start()]).replace(r"\ ", r"\s*")); pos = x.end()
        out.append(_PH.get(x.group(1).capitalize(), re.escape(x.group(0))))
    out.append(re.escape(m[pos:]).replace(r"\ ", r"\s*"))
    return re.compile("".join(out))

# ----------------------------------------------------------------------------- allgemeine Regeln
# fn(doc, punkt, ctx) -> (ok: True/False/None, details); None = nicht prüfbar.
REGELN = {}
def regel(rid, titel, beschreibung, wert="", abschnitt="", schwere="Hinweis"):
    """wert/abschnitt: Hilfetext für die Felder «Was genau» und «Abschnitt» («» = Feld nicht nötig)."""
    def deco(fn):
        fn.titel, fn.beschreibung, fn.wert, fn.abschnitt, fn.schwere = titel, beschreibung, wert, abschnitt, schwere
        REGELN[rid] = fn; return fn
    return deco

_AB = "Optional: nur in diesem Abschnitt (Wort aus der Überschrift). Leer = ganzes Dokument."

@regel("enthaelt", "Kommt vor", "Jedes der Wörter oder Sätze muss vorkommen.",
       wert="Wörter oder Sätze, mehrere durch | getrennt, z.B. «Selbstständigkeitserklärung | Abstract»", abschnitt=_AB)
def r_enthaelt(doc, p, ctx):
    t, ab = _bereich(doc, p); ws = _woerter(p)
    if t is None: return None, [f"Abschnitt «{ab}» nicht gefunden."]
    if not ws: return None, ["Unter «Was genau» ist nichts angegeben."]
    miss = [w for w in ws if w.lower() not in t.lower()]
    return (not miss), [f"Fehlt: «{w}»" for w in miss] or ["Alles gefunden: " + ", ".join(ws)]

@regel("enthaelt_nicht", "Kommt nicht vor", "Keines der Wörter darf vorkommen; Fundstellen werden gezeigt.",
       wert="Wörter, mehrere durch | getrennt, z.B. «doi: | TODO | xxx»", abschnitt=_AB)
def r_nicht(doc, p, ctx):
    t, ab = _bereich(doc, p); ws = _woerter(p)
    if t is None: return None, [f"Abschnitt «{ab}» nicht gefunden."]
    if not ws: return None, ["Unter «Was genau» ist nichts angegeben."]
    det = []
    for w in ws:
        for m in list(re.finditer(re.escape(w), t, re.I))[:5]:
            det.append(f"«{w}»: …{_kurz(t[max(0, m.start() - 40):m.end() + 40], 100)}…")
    return (not det), det or ["Nichts gefunden: " + ", ".join(ws)]

@regel("muster_in_abschnitt", "Jede Fundstelle steht auch im Abschnitt",
       "Sucht im übrigen Text alle Stellen nach dem Muster und prüft, ob ihre Werte in einer Zeile des Abschnitts stehen. "
       "Beispiel: Muster «{Name}, {Jahr}» und Abschnitt «Literaturverzeichnis» = jede zitierte Quelle steht im Verzeichnis.",
       wert="Muster, z.B. «{Name}, {Jahr}» oder «{Name} ({Jahr})». Platzhalter: {Name} {Jahr} {Zahl} {Wort} {Text}",
       abschnitt="Pflicht: Abschnitt, in dem die Werte stehen müssen, z.B. «Literaturverzeichnis».", schwere="Fehler")
def r_muster(doc, p, ctx):
    t, ab = _bereich(doc, p); m = as_text(p.get("wert", "")).strip()
    if not ab or not m: return None, ["«Was genau» (Muster) und «Abschnitt» angeben."]
    if t is None: return None, [f"Abschnitt «{ab}» nicht gefunden."]
    rx = muster_regex(m); rest = doc["text"].replace(t, " ")
    zeilen = [_key(z) for z in t.splitlines() if z.strip()]
    miss, seen = [], set()
    for x in rx.finditer(rest):
        vals = tuple(_key(g) for g in x.groups() if g)
        if not vals or vals in seen: continue
        seen.add(vals)
        if not any(all(v in z for v in vals) for z in zeilen): miss.append(f"«{_kurz(x.group(0), 70)}»")
    if not seen: return None, [f"Keine Stelle nach dem Muster «{m}» gefunden."]
    return (not miss), ([f"{len(seen)} Stellen geprüft, {len(miss)} nicht im Abschnitt «{ab}»:"] + miss) if miss \
        else [f"{len(seen)} Stellen geprüft – alle im Abschnitt «{ab}»."]

@regel("reihenfolge", "Abschnitt alphabetisch geordnet", "Die Zeilen (Einträge) des Abschnitts müssen alphabetisch sortiert sein.",
       abschnitt="Pflicht: z.B. «Literaturverzeichnis» oder «Glossar».")
def r_reihe(doc, p, ctx):
    t, ab = _bereich(doc, p)
    if not ab: return None, ["Unter «Abschnitt» angeben, welcher Abschnitt sortiert sein muss."]
    if t is None: return None, [f"Abschnitt «{ab}» nicht gefunden."]
    z = [l.strip().lstrip("#").strip() for l in t.splitlines()[1:] if len(l.strip()) > 3]
    bad = [f"«{_kurz(z[i], 50)}» steht nach «{_kurz(z[i - 1], 50)}»" for i in range(1, len(z)) if _key(z[i]) < _key(z[i - 1])]
    return (not bad), bad or [f"{len(z)} Einträge in alphabetischer Reihenfolge."]

@regel("laenge", "Länge in Wörtern", "Zählt die Wörter im Abschnitt (ohne Überschrift).",
       wert="z.B. «höchstens 250» oder «mindestens 1000»", abschnitt=_AB)
def r_laenge(doc, p, ctx):
    t, ab = _bereich(doc, p)
    if t is None: return None, [f"Abschnitt «{ab}» nicht gefunden."]
    m = re.search(r"(höchstens|max\w*|mindestens|min\w*)\D*(\d[\d']*)", as_text(p.get("wert", "")), re.I)
    if not m: return None, ["Unter «Was genau» z.B. «höchstens 250» angeben."]
    n = len(re.findall(r"\w+", "\n".join(t.splitlines()[1:] if ab else t.splitlines())))
    g = int(m.group(2).replace("'", "")); hoch = m.group(1).lower().startswith(("h", "max"))
    ok = n <= g if hoch else n >= g
    return ok, [f"{n} Wörter ({'höchstens' if hoch else 'mindestens'} {g} verlangt)."]

_PLATZHALTER = re.compile(r"^h\d\b|titel$|untertitel|uebertitel|übertitel|abschnitttitel|lorem|xxx|überschrift|platzhalter|"
                         r"\bebene\s*\d", re.I)
def _vorlage_headings(path):
    """Überschriften der Vorlage ohne Platzhalter wie «H1 Einleitung Uebertitel» (die gibt die Vorlage nur als Muster vor)."""
    out = []
    for h, t in docx_paragraphs(path):
        t = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", t)
        if h and 3 <= len(t) <= 80 and not _PLATZHALTER.search(t) and t not in out: out.append(t)
    return out

@regel("gliederung_wie_vorlage", "Gliederung wie die Vorlage",
       "Liest die Überschriften einer Word-Vorlage (Reiter «Wissen» oder «Vorlage») und prüft, ob jede im Dokument vorkommt. "
       "Platzhalter wie «H1 Übertitel» werden übergangen.", wert="Optional: Dateiname der Vorlage. Leer = Datei mit «vorlage» im Namen.")
def r_gliederung(doc, p, ctx):
    name = as_text(p.get("wert", "")).strip(); c = []
    for wd in (Path(ctx.wf_dir) / "wissen", Path(ctx.wf_dir) / "vorlagen"):
        c += [wd / name] if name else sorted(x for x in wd.glob("*.docx") if "vorlage" in x.name.lower())
    c = [x for x in c if x.is_file()]
    if not c: return None, ["Keine Word-Vorlage gefunden (Dateiname mit «vorlage» oder unter «Was genau» angeben)."]
    try: hs = _vorlage_headings(c[0])
    except Exception as e: return None, [f"Vorlage {c[0].name} nicht lesbar: {e}"]
    if not hs: return None, [f"In {c[0].name} keine festen Überschriften gefunden (nur Platzhalter)."]
    low = _key(" ".join(l[3:] for l in doc["text"].splitlines() if l.startswith("## ")) or doc["text"])
    miss = [h for h in hs if _key(h) not in low]
    return (not miss), ([f"Vorlage {c[0].name}: {len(hs)} Überschriften, {len(miss)} fehlen:"] + miss) if miss \
        else [f"Alle {len(hs)} Überschriften der Vorlage {c[0].name} vorhanden."]

# v50/v51-Regeln (APA im Code) -> allgemeine Regeln; None = entfällt (Punkt meldet «bitte löschen»)
ALT = {"apa_zitat_im_verzeichnis": {"regel": "muster_in_abschnitt", "wert": "{Name}, {Jahr}", "abschnitt": "Literaturverzeichnis"},
       "apa_alphabetisch": {"regel": "reihenfolge", "abschnitt": "Literaturverzeichnis"},
       "apa_doi": {"regel": "enthaelt_nicht", "wert": "doi:"}, "kapitel_wie_vorlage": {"regel": "gliederung_wie_vorlage"},
       "text_enthaelt": {"regel": "enthaelt"}, "apa_verzeichnis_zitiert": None, "apa_jahr_im_eintrag": None,
       "apa_direktzitat_seite": None, "apa_et_al": None, "apa_klammer_und": None}

def pakete():
    """Pakete = JSON-Dateien in C:\\aura\\pruefpakete\\: {"name", "quelle", "beschreibung", "punkte": [...]}."""
    out = {}
    try:
        from ..config import ROOT
        for f in sorted((ROOT / "pruefpakete").glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                out[d.get("name") or f.stem] = {"quelle": d.get("quelle", ""), "beschreibung": d.get("beschreibung", ""),
                                                "punkte": d.get("punkte", []), "datei": f.name}
            except Exception as e: out[f"{f.stem} (fehlerhaft: {e})"] = {"quelle": "", "punkte": [], "datei": f.name}
    except Exception: pass
    return out

def katalog(): return [(rid, f.titel, f.beschreibung, f.schwere) for rid, f in REGELN.items()]

def normalize(pk):
    pk = dict(pk); art = pk.get("art", "regel")
    if art == "regel" and pk.get("regel") in ALT:
        neu = ALT[pk["regel"]]
        if neu is None: pk["_entfallen"] = True
        else:
            for k, v in neu.items():
                if k == "regel" or not pk.get(k): pk[k] = v
    if art == "regel" and pk.get("regel") in REGELN:
        f = REGELN[pk["regel"]]; pk.setdefault("name", f.titel); pk.setdefault("schwere", f.schwere)
    pk.setdefault("name", pk.get("regel") or _kurz(pk.get("frage", "Prüfpunkt"), 50)); pk.setdefault("schwere", "Hinweis")
    return pk

def quelle(pk):
    return normalize(pk).get("quelle") or ("eigene Frage" if pk.get("art") == "frage" else "")

def validate(st):
    errs = []
    for i, pk in enumerate(st.get("punkte") or []):
        w = f"Schritt {st.get('id')}, Prüfpunkt {i + 1}"
        if not isinstance(pk, dict): errs.append(f"{w}: muss ein Objekt sein"); continue
        art = pk.get("art", "regel")
        if art == "regel" and pk.get("regel") not in REGELN and pk.get("regel") not in ALT:
            errs.append(f"{w}: unbekannte Regel «{pk.get('regel')}» (erlaubt: {', '.join(REGELN)})")
        elif art == "frage" and not str(pk.get("frage", "")).strip(): errs.append(f"{w}: «frage» fehlt")
        elif art not in ("regel", "frage"): errs.append(f"{w}: art muss «regel» oder «frage» sein")
        if pk.get("schwere") and pk["schwere"] not in SCHWERE: errs.append(f"{w}: schwere muss {' oder '.join(SCHWERE)} sein")
    if not st.get("punkte"): errs.append(f"Schritt {st.get('id')}: Prüfliste ist leer – im Reiter «Prüfliste» Punkte hinzufügen")
    return errs

# ----------------------------------------------------------------------------- Frage ans Sprachmodell
SYSTEM = ("Du prüfst ein Dokument. Beantworte die Frage nur auf Grundlage des Textes. "
          "«ja» nur, wenn der Text es ausdrücklich zeigt; sonst «nein» oder «unklar».")

def _frage(doc, pk, state, ctx, kontext=""):
    ab = str(pk.get("abschnitt", "")).strip(); mc = int(pk.get("max_zeichen", 10000))
    sec = section(doc["text"], ab, mc)
    if sec is None: return None, [f"Abschnitt «{ab}» nicht gefunden – Frage nicht gestellt."]
    ctx.progress(f"Prüfliste: Frage «{pk.get('name')}» an das Sprachmodell ({len(sec)} Zeichen{', Abschnitt ' + ab if ab else ''}) …")
    mass = f"MASSSTAB (aus dem Wissen):\n{kontext[:6000]}\n\n" if kontext else ""
    p = {"system": SYSTEM, "vorspann": f"{mass}TEXT{' (Abschnitt ' + ab + ')' if ab else ''}:\n{sec}\n",
         "prompt": f"FRAGE: {pk['frage']}", "beleg_text": sec,
         "fields": [{"name": "antwort", "auswahl": ["ja", "nein", "unklar"], "beleg": True, "neutral": ["nein"],
                     "max_tokens": 4, "label": pk.get("name")},
                    {"name": "begruendung", "hint": "ein kurzer Satz", "max_tokens": 60, "verlaengern": False}]}
    r = _llm(p, state, ctx); a = r.get("antwort", "unklar")
    det = [r.get("begruendung", "")] + ([f"Beleg: «{_kurz(r.get('antwort_beleg', ''), 200)}»"] if a == "ja" else [])
    det += r.get("_hinweise") or []
    return {"ja": True, "nein": False}.get(a), [d for d in det if d]

# ----------------------------------------------------------------------------- Baustein
@node("pruefliste", "Dokumente gegen Prüfpunkte prüfen. Parameter: files, punkte [{name, art: regel|frage, regel, wert, "
                    "abschnitt, frage, schwere, quelle}], kontext (optional, z.B. {{wissen.text}} für Fragen).")
def n_pruefliste(p, state, ctx):
    files = p.get("files") or []
    if isinstance(files, str): files = [files]
    if not files: raise RuntimeError("Keine Datei zum Prüfen")
    doc = {"text": "\n\n".join(read_doc(f) for f in files)}
    ctx.progress(f"Prüfliste: {len(doc['text'])} Zeichen gelesen")
    res, warn = [], []
    punkte = [normalize(x) for x in p.get("punkte") or []]
    for i, pk in enumerate(punkte):
        if ctx.cancelled(): break
        try:
            if pk.get("_entfallen"): ok, det = None, ["Diese Regel gibt es seit v53 nicht mehr (Fachinhalt gehört nicht in den Code) – Punkt löschen."]
            elif pk.get("art", "regel") == "regel":
                ctx.progress(f"Prüfliste {i + 1}/{len(punkte)}: {pk['name']}")
                ok, det = REGELN[pk["regel"]](doc, pk, ctx)
            else: ok, det = _frage(doc, pk, state, ctx, as_text(p.get("kontext", "")))
        except Exception as e:
            if type(e).__name__ in ("Cancelled", "DeviceLost"): raise
            ok, det = None, [f"Prüfung fehlgeschlagen: {type(e).__name__}: {e}"]
        res.append({"name": pk["name"], "art": pk.get("art", "regel"), "schwere": pk["schwere"], "ok": ok, "quelle": quelle(pk),
                    "details": det[:MAX_DETAILS + 1] + ([f"… und {len(det) - MAX_DETAILS - 1} weitere"] if len(det) > MAX_DETAILS + 1 else [])})
        if ok is False: warn.append(f"✗ {pk['name']} ({pk['schwere']})")
    n_f = sum(1 for r in res if r["ok"] is False and r["schwere"] == "Fehler")
    n_h = sum(1 for r in res if r["ok"] is False and r["schwere"] != "Fehler")
    n_o = sum(1 for r in res if r["ok"] is None)
    if n_o: warn.append(f"{n_o} Punkt(e) nicht prüfbar – Details im Prüfbericht")
    return {"_pruefliste": res, "fehler": n_f, "hinweise": n_h, "nicht_pruefbar": n_o,
            "ok": sum(1 for r in res if r["ok"]), "_warnungen": warn}

def bericht(res):
    """Zeilen für Pruefbericht.txt."""
    sym = {True: "✓", False: "✗", None: "?"}
    L = []
    for r in res:
        L.append(f"  {sym[r['ok']]} {r['name']}  [{r['schwere'] if r['ok'] is False else ('erfüllt' if r['ok'] else 'nicht prüfbar')}]"
                 + ("  (Sprachmodell)" if r["art"] == "frage" else ""))
        if r.get("quelle"): L.append(f"      Herkunft: {r['quelle']}")
        L += [f"      {d}" for d in r["details"]]
    return L
