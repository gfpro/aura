# aura/workflow/nodes.py — Bausteine (Schritt-Typen). Version 20261031v146 (v146: Parameter «rolle» im Baustein llm – Text einer freigegebenen Rolle vor dem Systemtext; v137: Verneinungsliste ohne «nicht anwendbar/entfällt/verzichtet»; v136: Feldoption verneinung_pruefen – Beleg mit Verneinung im Zitat oder im Folgesatz wird verworfen; v135: Feldoption min_sicherheit/unsicher_wert – unsichere Auswahl wird ersetzt statt verwendet; v132: Ausfuehrlichkeit je Workflow (knapp/normal/ausfuehrlich) fuer freie Antworten und Felder mit «ausfuehrlich_ok»; v96: unsichere Auswahlfelder -> Hinweis im Pruefbericht; v41: leer_werte, v43: vorspann; rag liefert text_pin/text_suche)
# v45: word_vorlage sucht nach dem Ausfuellen verbliebene Platzhalter (Parameter platzhalter) -> Warnungen/Pruefbericht.
# v49: Option beleg_nach (Zitat nach dem Wert, neutral -> «keiner» ohne Modell), Standard aus.
# v44: Feldoption vorschlag – Text geht NUR in den Pruefbericht (_vorschlaege), nie in das Ergebnis des Schritts.
# v40: Feldoptionen auswahl mit «wann», beleg, ohne_beleg, neutral, wenn_leer, verlaengern; Warnungen je Schritt in _warnungen.
# Jeder Baustein: fn(params, state, ctx) -> dict. params sind bereits ausgewertet ({{...}} ersetzt),
# ausser bei "template" (rendert selbst). Kein Baustein hat Netzzugriff (kommt in Patch 2 ueber http-Baustein mit Freigabeliste).
import html as _html, json, os, re, time, zipfile
from datetime import datetime
from pathlib import Path
from . import llmio
from .expr import html_escape, render, as_text, truthy, evaluate, resolve, num, belegt

NODES = {}
def node(name, doc):
    def deco(fn): fn.doc = doc; NODES[name] = fn; return fn
    return deco

# ----------------------------------------------------------------------------- Dateien lesen
def _docx(p):
    with zipfile.ZipFile(p) as z: xml = z.read("word/document.xml").decode("utf-8", "replace")
    paras = []
    for para in re.split(r"</w:p>", xml):
        para = re.sub(r"<w:tab/>", "\t", para); para = re.sub(r"<w:br/>", "\n", para)
        t = "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", para))
        if t.strip(): paras.append(_html.unescape(t))
    return "\n".join(paras)

def _strip_running(pages):
    """Kopf-/Fusszeilen entfernen, die auf vielen Seiten wiederkehren (Ziffern egal), z.B. «172.056.1  11 / 44»."""
    if len(pages) < 4: return [_tidy(t) for t in pages]
    key = lambda l: re.sub(r"\d+", "#", l.strip())
    count = {}
    for t in pages:
        ls = [l for l in t.splitlines() if l.strip()]
        for l in set(ls[:2] + ls[-2:]): count[key(l)] = count.get(key(l), 0) + 1
    rep = {k for k, n in count.items() if n >= 0.5 * len(pages)}
    out = []
    for t in pages:
        ls = t.splitlines(); edge = set(range(min(2, len(ls)))) | set(range(max(0, len(ls) - 2), len(ls)))
        out.append(_tidy("\n".join(l for i, l in enumerate(ls) if not (i in edge and key(l) in rep))))
    return out

_KEEP = "und|oder|bis|sowie|als|bzw|resp"
def _tidy(t):
    t = re.sub(r"^.*\.{6,}\s*\d+\s*$", "", t, flags=re.M)                  # Inhaltsverzeichnis-Zeilen
    return re.sub(rf"(\w)-\n(?!(?:{_KEEP})\b)([a-zäöü])", r"\1\2", t)        # Trennstriche am Zeilenende

def _pdf(p):
    # pypdf als unveraendertes Wheel (Zip) laden: kein Entpacken noetig, nichts kann beim Kopieren verloren gehen
    import sys
    from ..config import ROOT
    for w in sorted((ROOT / "vendor" / "wheels").glob("*.whl"), reverse=True):
        if str(w) not in sys.path: sys.path.insert(0, str(w))
    try: from pypdf import PdfReader
    except Exception as e:
        raise RuntimeError(f"pypdf laesst sich nicht laden ({type(e).__name__}: {e}) - vendor\\wheels pruefen")
    r = PdfReader(str(p))
    pages = _strip_running([(pg.extract_text() or "").strip() for pg in r.pages])
    txt = "\n\n".join(f"[Seite {i + 1}]\n{t}" for i, t in enumerate(pages) if t)
    if not txt.strip(): raise RuntimeError(f"{Path(p).name}: kein Text gefunden (gescanntes PDF? OCR gibt es noch nicht)")
    return txt

def read_file(p):
    p = Path(p); ext = p.suffix.lower()
    if ext in (".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm", ".eml"):
        t = p.read_text(encoding="utf-8", errors="replace")
        return re.sub(r"<[^>]+>", " ", t) if ext in (".html", ".htm") else t
    if ext == ".docx": return _docx(p)
    if ext == ".pdf": return _pdf(p)
    raise RuntimeError(f"Dateityp {ext} wird (noch) nicht unterstuetzt: {p.name}")

@node("extract", "Text aus Dateien (pdf, docx, txt, md, ...). Parameter: files, max_chars (gesamt, Standard 12000)")
def n_extract(p, state, ctx):
    files = p.get("files") or []
    if isinstance(files, str): files = [files]
    limit = int(p.get("max_chars", 12000)); parts, info, used = [], [], 0
    for f in files:
        ctx.progress(f"Lese {Path(f).name} ...")
        t = re.sub(r"[ \t ]+", " ", read_file(f)); t = re.sub(r"\n{3,}", "\n\n", t).strip()
        info.append({"name": Path(f).name, "chars": len(t)})
        parts.append(f"=== Dokument: {Path(f).name} ===\n{t}")
    text = "\n\n".join(parts); cut = len(text) > limit
    if cut: text = text[:limit] + f"\n[... gekuerzt: {len(text) - limit} von {len(text)} Zeichen weggelassen]"
    if cut: ctx.progress(f"Achtung: Dokumenttext gekuerzt auf {limit} Zeichen")
    return {"text": text, "files": info, "truncated": cut, "chars": len(text)}

# ----------------------------------------------------------------------------- Sprachmodell
FIELD_RULES = ("\n\nAntworte als JSON-Objekt mit genau diesen Feldern (alle Werte sind Text):\n{spec}\n"
               "Innerhalb der Werte keine doppelten Anfuehrungszeichen verwenden (stattdessen «»). "
               "Fehlt eine Information, das ausdruecklich so schreiben. Nichts erfinden.")

NEUTRAL = {"nein", "keine", "keiner", "unklar", "keine angabe in den unterlagen.", ""}

# v137: nur Wendungen, die die AUSNAHME selbst verneinen. Entfernt: «nicht anwendbar», «entfällt», «verzichtet» –
# «Das BöB ist nicht anwendbar» oder «Ausschreibung entfällt» BEJAHEN eine Ausnahme (Fehlalarm inhouse_bit).
VERNEINT = re.compile(r"liegt[^.]{0,60}nicht vor|kommt[^.]{0,40}nicht in frage|nicht erfüllt|"
                      r"bietet[^.]{0,60}nicht an|keine ausnahme|nicht beansprucht|abgelehnt|ist nicht gegeben|"
                      r"(?:ausnahme|voraussetzung)[^.]{0,40}besteht nicht", re.I)

def _verneint(zitat, quellen):
    """v136: Steht im Zitat oder im direkt folgenden Text (bis ca. 2 Sätze) eine Verneinung? Rückgabe: Fundstelle oder ''."""
    z = re.sub(r"\s+", " ", zitat or "").strip().lower(); q = re.sub(r"\s+", " ", quellen or "")
    if len(z) < 12: return ""
    i = q.lower().find(z[:80])
    fenster = z if i < 0 else q[i:i + len(z) + 260]
    m = VERNEINT.search(fenster)
    return m.group(0) if m else ""
LEER = "Keine Angabe in den Unterlagen."

def _prep_fields(fields, nach=False):
    """v40: Feldoptionen vereinheitlichen. auswahl darf ["wert", ...] oder [{"wert": ..., "wann": ...}] sein.
    beleg: true -> AURA legt davor ein Zitatfeld <name>_beleg an und prueft es nach dem Lauf gegen beleg_text.
    v49: beleg_nach (Feld oder Schritt, Standard aus) -> Zitatfeld NACH dem Wert; ist der Wert neutral,
    schreibt AURA «keiner» selbst ins Geruest (spart das Abschreiben von Formularfragen)."""
    out = []
    for f in fields:
        f = dict(f)
        if f.get("auswahl"):
            opts = [o if isinstance(o, str) else o.get("wert", "") for o in f["auswahl"]]
            f["_wann"] = {o.get("wert", ""): o.get("wann", "") for o in f["auswahl"] if isinstance(o, dict) and o.get("wann")}
            f["auswahl"] = opts
        if not f.get("beleg"): out.append(f); continue
        b = {"name": f["name"] + "_beleg", "max_tokens": int(f.get("beleg_tokens", 70)), "verlaengern": False,
             "hint": f"Beleg zu {f['name']}: wörtliches Zitat (ein Satz) aus den Unterlagen; ohne Beleg: keiner"}
        if f.get("beleg_nach", nach):                                   # v49
            b["_skip_wenn"] = (f["name"], sorted({x.rstrip(".") for x in NEUTRAL}
                                                  | {str(x).lower().rstrip(".") for x in f.get("neutral", [])}))
            out += [f, b]
        else: out += [b, f]
    return out

def _spec(f):
    h = f.get("hint", "")
    if f.get("auswahl"):
        if f.get("_wann"):
            h += (" – " if h else "") + "genau eines von:\n" + "\n".join(
                f"    · {o}" + (f" – {f['_wann'][o]}" if f["_wann"].get(o) else "") for o in f["auswahl"])
        else: h += (" – " if h else "") + "genau eines von: " + " | ".join(f["auswahl"])
    if f.get("zahl"): h += (" – " if h else "") + "nur die Zahl, ohne Text (unbekannt: 0)"
    return f"- {f['name']}: {h}".rstrip(": ")

@node("llm", "Sprachmodell. Parameter: prompt, system, max_new | fields [{name, hint, max_tokens, auswahl, zahl, beleg, "
             "ohne_beleg, beleg_nach, neutral, wenn_leer, verlaengern, vorschlag}], beleg_text, beleg_nach, vorspann (fester Anfang, wird gecacht), temperature, backend")
def n_llm(p, state, ctx):
    try: return _llm(p, state, ctx)
    except Exception as e:
        if type(e).__name__ != "DeviceLost": raise
        be = ctx.llm(p.get("backend") or state["workflow"].get("llm"))[0]   # GPU weg (Standby): einmal neu laden
        ctx.progress(f"GPU-Zuruecksetzung ({e}) - lade Sprachmodell neu und wiederhole den Schritt ...")
        be.unload(); be.load(); return _llm(p, state, ctx)

AUSF = {"knapp": (0.6, "Fasse dich kurz: nur das Wesentliche, ohne Ausschmückung."),
        "normal": (1.0, ""),
        "ausfuehrlich": (1.8, "Antworte ausführlich: nenne Zusammenhänge, Hintergründe und Einzelheiten aus den Unterlagen "
                              "(Daten, Personen, Beträge, Fristen). Erfinde nichts dazu.")}

def ausfuehrlichkeit(state, ctx):
    """v132: Stufe des Workflows (workflow.json: "ausfuehrlichkeit"), Standard «normal»."""
    a = (state.get("workflow") or {}).get("ausfuehrlichkeit")
    if a is None:
        try: a = json.loads((ctx.wf_dir / "workflow.json").read_text(encoding="utf-8")).get("ausfuehrlichkeit")
        except Exception: a = None
    a = str(a or "normal").lower().replace("ü", "ue")
    return a if a in AUSF else "normal"

def _llm(p, state, ctx):
    be, bid, label = ctx.llm(p.get("backend") or state["workflow"].get("llm"))
    stufe = ausfuehrlichkeit(state, ctx); fak, satz = AUSF[stufe]          # v132
    s = ctx.settings
    temp = float(p.get("temperature", 0.0)); pen = float(p.get("repetition_penalty", 1.05))
    system, prompt = as_text(p.get("system", "")), as_text(p.get("prompt", ""))
    if p.get("rolle"):                                                    # v146: Rolle aus C:\aura\rollen (nur freigegeben)
        from ..skills import rolle_text
        rt = rolle_text(p["rolle"])
        if not rt: raise ValueError(f"Rolle «{p['rolle']}» ist nicht freigegeben oder fehlt (Workflows › Skills & Rollen).")
        system = (rt + "\n\n" + system).strip()
    vorspann = as_text(p.get("vorspann", ""))                           # v43: fester Teil zuerst -> Cache
    think_off = "qwen3" in label.lower() and "instruct" not in label.lower()
    fields = p.get("fields")
    try: llmio.parts(be)
    except Exception as e:
        ctx.progress(f"Hinweis: Workflow-Schnittstelle zum Modell fehlt ({e}) - Ersatzweg ohne JSON-Zwang")
        if fields:
            names = [f["name"] for f in fields]
            txt = llmio.fallback_generate(be, s, system, prompt + "\n\nAntworte nur mit JSON mit den Feldern: "
                                          + ", ".join(names), None, ctx.cancelled)
            return dict(llmio.extract_json(txt, names), _raw=txt, _forced=False)
        return {"text": llmio.fallback_generate(be, s, system, prompt, None, ctx.cancelled)}
    if fields and stufe != "normal":                                   # v132: nur markierte Textfelder
        fields = [dict(f) for f in fields]
        for f in fields:
            if f.get("ausfuehrlich_ok") and not f.get("auswahl") and not f.get("zahl"):
                f["max_tokens"] = max(10, int(int(f.get("max_tokens", 250)) * fak))
                f["hint"] = (f.get("hint", "") + " – " + satz).strip(" –")
    if fields:
        fields = _prep_fields(fields, bool(p.get("beleg_nach", False)))
        spec = "\n".join(_spec(f) for f in fields)
        res, st = llmio.structured(be, system, prompt + FIELD_RULES.format(spec=spec), fields, temp, pen,
                                   on_field=lambda n, v, c: ctx.progress(f"Feld {n}: {len(v)} Zeichen" + ("" if c else " (Grenze erreicht)")),
                                   progress=ctx.progress, cancelled=ctx.cancelled, think_off=think_off, vorspann=vorspann)
        ctx.progress(f"JSON fertig: {st['in']} Tokens gelesen ({st.get('cache', 0)} aus Cache, {st['prefill_s']:.0f} s), "
                     f"{st['out']} geschrieben ({st['gen_s']:.0f} s)")
        warn = [f"Feld «{n}» zu lang für max_tokens – an der Satzgrenze gekürzt" for n in st.get("gekuerzt", [])]
        for n in st.get("verlaengert", []): ctx.progress(f"Feld {n}: über max_tokens hinaus bis zum Satzende geschrieben")
        for n, v in res.items():                                    # leere Werte (auch nur «») klar benennen
            if not re.sub(r"[\s«»\"'.\-–]", "", v): res[n] = LEER
            elif s.get("schweiz_ss", True): res[n] = v.replace("ß", "ss")  # Schweizer Schreibweise
        vorschlaege = {}                                            # v44: nur Pruefbericht, nie ins Dokument
        for f in fields:
            if f.get("vorschlag"):
                v = res.pop(f["name"], "")
                if v.strip().lower().rstrip(".") not in {x.rstrip(".") for x in NEUTRAL}: vorschlaege[f.get("label", f["name"])] = v
        from .docx_fill import match_option
        for f in fields:                                            # Auswahl- und Zahlfelder nachbearbeiten
            n, v = f["name"], res.get(f["name"], "")
            if f.get("auswahl"):
                o = match_option(v, f["auswahl"]); res[n + "_roh"] = v
                res[n] = o if o is not None else ("unklar" if "unklar" in f["auswahl"] else v)
            if f.get("zahl"): res[n + "_zahl"] = num(v)
        quellen = as_text(p.get("beleg_text")) or prompt               # v40: Belege nur gegen die Unterlagen pruefen
        if any(f.get("beleg") for f in fields) and not p.get("beleg_text"):
            warn.append("beleg_text fehlt im Schritt – Belege werden gegen den ganzen Prompt geprüft (auch Rechtstexte)")
        hinweise = []
        for f in fields:
            n = f["name"]
            if f.get("beleg"):
                v = res.get(n, ""); neutral = NEUTRAL | {str(x).lower() for x in f.get("neutral", [])}
                if v.strip().lower() in neutral: res[n + "_belegt"] = None
                else:
                    ok = belegt(res.get(n + "_beleg", ""), quellen); res[n + "_belegt"] = ok
                    vn = _verneint(res.get(n + "_beleg", ""), quellen) if ok and f.get("verneinung_pruefen") else ""
                    if vn:                                               # v136
                        res[n + "_belegt"] = False; res.setdefault(n + "_roh", v)
                        res[n] = f.get("ohne_beleg", f.get("wenn_leer") or "keine")
                        hinweise.append(f"{f.get('label', n)}: «{v[:80]}» – die Unterlagen verneinen das («{vn}») – auf «{res[n]}» gesetzt.")
                        ok = True
                    if not ok:
                        res.setdefault(n + "_roh", v)
                        res[n] = f.get("ohne_beleg", "unklar" if "unklar" in (f.get("auswahl") or []) else (f.get("wenn_leer") or LEER))
                        hinweise.append(f"{f.get('label', n)}: «{v[:80]}» ohne Beleg in den Unterlagen – verworfen.")
            leerw = {"", LEER.lower()} | {str(x).lower() for x in f.get("leer_werte", [])}
            if f.get("wenn_leer") and res.get(n, "").strip().lower().rstrip(".") in {x.rstrip(".") for x in leerw}:
                res[n] = f["wenn_leer"]
        lab = {f["name"]: f.get("label", f["name"]) for f in fields}       # v96: Auswahl mit geringer Sicherheit
        sich = {n: c for n, c in st.get("sicherheit", [])}; ersetzt = set()
        for f in fields:                                               # v135: Mindestsicherheit je Feld
            n, ms = f["name"], f.get("min_sicherheit")
            if ms is None or n not in sich or sich[n] >= float(ms): continue
            alt = f.get("unsicher_wert", "unklar")
            if str(res.get(n, "")).strip().lower() == str(alt).strip().lower(): continue
            res.setdefault(n + "_roh", res.get(n, "")); ersetzt.add(n)
            hinweise.append(f"{lab.get(n, n)}: Modell schwankte ({sich[n]:.0%} für «{res.get(n, '')}», verlangt "
                            f"{float(ms):.0%}) – auf «{alt}» gesetzt. Bitte in den Unterlagen prüfen.")
            res[n] = alt
        for n, v, c in st.get("unsicher", []):
            if n not in ersetzt and str(res.get(n, v)).strip().lower() != "unklar":
                hinweise.append(f"{lab.get(n, n)}: «{res.get(n, v)}» gewählt, aber das Modell war unsicher "
                                f"({c:.0%}) – bitte prüfen.")
        for h in hinweise: ctx.progress("Hinweis: " + h)
        return dict(res, _stats=st, _forced=True, _hinweise=hinweise, _warnungen=warn, _vorschlaege=vorschlaege)
    max_new = int(p.get("max_new", s.get("llm_max_new", 400)))
    if stufe != "normal" and p.get("ausfuehrlich_ok", True):            # v132: freie Antwort
        max_new = max(20, int(max_new * fak)); system = (system + "\n\n" + satz).strip()
    txt, st = llmio.generate(be, system, prompt, max_new, temp, pen,
                             on_text=ctx.on_text, progress=ctx.progress, cancelled=ctx.cancelled, think_off=think_off,
                             vorspann=vorspann)
    if s.get("schweiz_ss", True): txt = txt.replace("ß", "ss")
    ctx.progress(f"Antwort fertig: {st['in']} Tokens gelesen ({st['prefill_s']:.0f} s), {st['out']} geschrieben ({st['gen_s']:.0f} s)")
    return {"text": txt, "_stats": st, "_ausfuehrlichkeit": stufe}

# ----------------------------------------------------------------------------- AURA-Wissen
@node("rag", "Suche. Parameter: query, k (6); collection (Wissenssammlung[en]) + pin (Pflichtstellen, z.B. 'BöB Art. 21') "
           "oder sources (AURA-Quellen wie outlook_mail)")
def n_rag(p, state, ctx):
    q, k = as_text(p.get("query", "")), int(p.get("k", 6))
    coll = p.get("collection")
    if coll:
        pin = p.get("pin") or []
        hits = ctx.wissen.search(q, k, [coll] if isinstance(coll, str) else list(coll), [pin] if isinstance(pin, str) else pin)
        text = "\n\n".join(h.get("text", "") for h in hits)            # Stuecke tragen ihre Quelle selbst: [BöB Art. 21 · Stand ...]
        tp = "\n\n".join(h.get("text", "") for h in hits if h.get("pinned"))          # v43: fest (gleich bei jedem Lauf)
        ts = "\n\n".join(h.get("text", "") for h in hits if not h.get("pinned"))      # v43: abhaengig von der Suche
    else:
        hits = ctx.search(q, k, p.get("sources"))
        text = "\n\n".join(f"[{i + 1}] {h.get('ts', '')[:10]} · {h.get('title', '')}\n{h.get('text', '')}" for i, h in enumerate(hits))
        tp, ts = "", text
    limit = int(p.get("max_chars", 0) or 0)
    if limit and len(text) > limit: text = text[:limit] + "\n[... gekuerzt]"
    if limit and len(tp) > limit: tp = tp[:limit] + "\n[... gekuerzt]"
    if limit and len(ts) > max(0, limit - len(tp)): ts = ts[:max(0, limit - len(tp))] + ("\n[... gekuerzt]" if ts else "")
    return {"hits": hits, "text": text, "text_pin": tp, "text_suche": ts, "count": len(hits),
            "quellen": sorted({h.get("author") or h.get("title", "") for h in hits})}

# ----------------------------------------------------------------------------- Daten / Ausgabe
@node("set", "Werte festlegen/umformen. Parameter: values {name: wert oder {{ausdruck}}}")
def n_set(p, state, ctx): return dict(p.get("values") or {})

@node("template", "Text/HTML aus Vorlage. Parameter: file (relativ zu workflows\\) oder text, html (true: Werte escapen)")
def n_template(p, state, ctx):
    src = p.get("text")
    if src is None:
        f = Path(render(p["file"], state))
        if not f.is_absolute(): f = ctx.wf_dir / f
        src = f.read_text(encoding="utf-8")
    is_html = truthy(p.get("html", True))
    return {"text": render(src, state, escape=html_escape if is_html else as_text)}

@node("file_out", "Datei schreiben. Parameter: content, name (ohne Endung), format (doc|html|md|txt|json), open")
def n_file_out(p, state, ctx):
    fmt = str(p.get("format", "txt")).lower().lstrip(".")
    name = re.sub(r'[\\/:*?"<>|]+', "_", as_text(p.get("name") or "ergebnis")).strip()[:80] or "ergebnis"
    out = ctx.out_dir; out.mkdir(parents=True, exist_ok=True)
    path = out / f"{datetime.now():%Y%m%d_%H%M}_{name}.{fmt}"
    c = p.get("content")
    if fmt == "json" and not isinstance(c, str): c = json.dumps(c, ensure_ascii=False, indent=2)
    path.write_text(as_text(c), encoding="utf-8")
    ctx.progress(f"Gespeichert: {path}")
    if truthy(p.get("open", False)) and hasattr(os, "startfile"):
        try: os.startfile(str(path))
        except Exception as e: ctx.progress(f"Oeffnen fehlgeschlagen: {e}")
    return {"path": str(path)}

# ----------------------------------------------------------------------------- Regeln (Entscheidungstabelle)
@node("regel", "Entscheidungstabelle: regeln [{name, wenn: Ausdruck ohne {{}}, dann: {werte}}], sonst {werte}. "
               "Die erste zutreffende Regel gilt. Rechnen/Vergleichen gehoert hierher, nicht ins Sprachmodell.")
def n_regel(p, state, ctx):
    for i, r in enumerate(p.get("regeln") or []):
        if truthy(evaluate(r["wenn"], state)):
            out = resolve(dict(r.get("dann") or {}), state)
            out["_regel"] = r.get("name") or f"Regel {i + 1}"
            ctx.progress(f"Regel: {out['_regel']}")
            return out
    out = resolve(dict(p.get("sonst") or {}), state); out["_regel"] = "sonst"
    ctx.progress("Regel: keine traf zu (sonst)")
    return out

# ----------------------------------------------------------------------------- Word-Vorlage ausfuellen
@node("word_vorlage", "Word-Vorlage (.docx) ausfuellen. Parameter: vorlage (relativ zu workflows\\), felder {Feldname: Wert}, "
                      "name, open. Feldnamen: py tools\\wf_run.py --vorlage-felder <vorlage.docx>")
def n_word_vorlage(p, state, ctx):
    from .docx_fill import fill
    v = Path(as_text(p["vorlage"]))
    if not v.is_absolute(): v = ctx.wf_dir / v
    if not v.exists(): raise RuntimeError(f"Vorlage fehlt: {v}")
    name = re.sub(r'[\\/:*?"<>|]+', "_", as_text(p.get("name") or v.stem)).strip()[:80] or v.stem
    out = ctx.out_dir / f"{datetime.now():%Y%m%d_%H%M}_{name}.docx"
    vals = {k: (x if isinstance(x, bool) else ("" if x is None else x)) for k, x in (p.get("felder") or {}).items()}
    leer = []; n, unknown, warn = fill(v, out, vals, leer)
    pl = p.get("platzhalter")                                          # v45: verbliebene Platzhalter melden
    if pl is None: pl = []                                            # Standard: keine Suche (je Workflow festlegen)
    if pl:
        try: txt = _docx(out)
        except Exception as e: txt = ""; warn.append(f"Platzhalter-Suche nicht möglich ({type(e).__name__})")
        for x in ([pl] if isinstance(pl, str) else pl):
            c = txt.count(as_text(x))
            if c: warn.append(f"Platzhalter «{x}» {c}× im Dokument – vor der Abgabe ausfüllen")
    for u in unknown: ctx.progress(f"Achtung: Feld «{u}» gibt es in der Vorlage nicht")
    for w in warn: ctx.progress(f"Achtung: {w}")
    ctx.progress(f"Vorlage ausgefuellt: {n} Felder → {out}")
    if truthy(p.get("open", False)) and hasattr(os, "startfile"):
        try: os.startfile(str(out))
        except Exception as e: ctx.progress(f"Oeffnen fehlgeschlagen: {e}")
    if leer: ctx.progress(f"Vorlage: {len(leer)} zugeordnete Felder blieben leer")
    return {"path": str(out), "gefuellt": n, "unbekannt": unknown, "warnungen": warn, "leer": leer,
            "_warnungen": [f"Vorlage: {w}" for w in warn] + [f"Vorlage: Feld «{u}» gibt es nicht" for u in unknown]}
