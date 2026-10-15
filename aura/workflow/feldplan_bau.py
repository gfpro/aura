# aura/workflow/feldplan_bau.py — Workflow-Schritte aus dem Feldplan bauen. Version 20261015v95 (v95: «Dokumente lesen» liest alle Datei-Eingaben, je mit Dokumentname; v64f: «keiner» = leer; Platzhalter in Begleitfeldern nur bei gewähltem Kästchen; v64e: Regeln dürfen bei Gruppen mehrere Kästchen ankreuzen; v64d: Regeln «Wenn … dann …» -> Schritt «regel», ohne Modell; v64c2: Begleitfelder nur abfragen, wenn ihr Kästchen gewählt ist)
#
# Nur Fakten (und noch offene Felder) gehen ans Sprachmodell; eine Kästchen-Gruppe ist EINE Auswahlfrage,
# die Kästchen setzt AURA danach selbst (eq). Fest -> Wert direkt, Manuell -> Platzhalter, Leer -> nichts,
# Abgeleitet -> Liste «offene_regeln» im Workflow (Grundlage wird Pflichtstelle im Wissen).
# Die Unterlagen stehen im «vorspann» (bei mehreren Modellschritten nur einmal eingelesen, Cache).
# Budget: Passt ein Schritt nicht ins Kontextfenster, verteilt AURA die Felder auf mehrere Schritte.
import re

MAX_T = 16384               # Kontextfenster des Modells (llmio: P.maxT)
ZEICHEN_JE_TOKEN = 2.5      # vorsichtig für Deutsch mit Qwen-Tokenizer (gemessen ~2.6–3)
DOK_ZEICHEN = 16000         # Höchstmenge Unterlagen (extract max_chars)
RESERVE_SYSTEM = 400        # System, Anweisung, JSON-Regeln
PLATZHALTER = "[ergänzen]"
NEUTRAL = ["keine", "keiner", "unklar", "Keine Angabe in den Unterlagen."]

def _tok(s): return int(len(s) / ZEICHEN_JE_TOKEN) + 1

def _slug(t, used):
    t = t.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("é", "e"), ("è", "e"), ("à", "a")): t = t.replace(a, b)
    b = re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:28] or "feld"
    if b[0].isdigit(): b = "f_" + b
    s, n = b, 2
    while s in used: s = f"{b}_{n}"; n += 1
    used.add(s); return s

def _q(s):
    """Text als Literal in einem Ausdruck."""
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"

def _eindeutig(opts):
    """Gleich lautende Optionen unterscheidbar machen («Dokumentation», «Dokumentation (2)»)."""
    out, seen = [], {}
    for o in opts:
        seen[o] = seen.get(o, 0) + 1
        out.append(o if seen[o] == 1 else f"{o} ({seen[o]})")
    return out

def _hint(e, zusatz=""):
    h = f"«{e['titel']}»" + (f" (Abschnitt {e['abschnitt']})" if e.get("abschnitt") and e["abschnitt"] != e["titel"] else "")
    wo = " – ".join(x for x in (e.get("quelle") and f"steht in: {e['quelle']}", e.get("hinweis")) if x)
    if wo: h += f"; {wo}"
    return h + (f"; {zusatz}" if zusatz else "")

def _len_opt(opts): return min(80, max([_tok(o) for o in opts] + [3]) + 4)

def planen(plan):
    """Feldplan -> (felder fürs Modell, zuordnung Vorlage->Ausdruck mit «@S» als Platzhalter für den Schrittnamen,
    offene_regeln, pins). Ausdrücke verwenden {{@S.name}}; ersetzt nach der Aufteilung auf Schritte."""
    used, felder, zuo, regeln, pins = set(), [], {}, [], []
    by_id = {e["id"]: e for e in plan["eintraege"]}
    grp_feld = {}                                                    # Kästchen-Nr -> (feldname, option)
    grp_opts = {}                                                    # feldname -> alle Antworten
    gewaehlt = {}                                                    # v64f: Kästchen-Nr -> Ausdruck «ist angekreuzt»
    pfad, rspec, used_r = {}, [], {"werte", "word", "dateien", "wissen"}   # v64d: Eintrag-ID -> Ausdruck des Werts
    for e in plan["eintraege"]:                                      # Regeln vorab benennen (dürfen sich aufeinander beziehen)
        if e["herkunft"] == "abgeleitet" and e.get("regeln"):
            pfad[e["id"]] = _slug("r " + e["titel"], used_r) + ".wert"; rspec.append(e)
    # 1) Gruppen und Kästchen zuerst (Begleitfelder brauchen deren Feldnamen)
    for e in plan["eintraege"]:
        if e.get("typ") != "kontrollkaestchen": continue
        h, opts = e["herkunft"], _eindeutig(e["optionen"])
        if h in ("fakt", "offen"):
            if e["art"] == "gruppe" and e.get("mehrfach"):
                for k, o, nr in zip(e["keys"], opts, e["nrs"]):
                    n = _slug(o, used)
                    felder.append({"name": n, "label": o, "auswahl": ["ja", "nein"], "max_tokens": 3, "_nr": nr,
                                   "hint": _hint(e, f"trifft «{o}» zu?")})
                    zuo[k] = "{{eq(@S." + n + ", 'ja')}}"; grp_feld[nr] = (n, "ja"); grp_opts[n] = ["ja", "nein"]
            elif e["art"] == "gruppe":
                n = _slug(e["titel"], used)
                felder.append({"name": n, "label": e["titel"], "auswahl": opts + ["keine", "unklar"], "max_tokens": _len_opt(opts),
                               "_nr": e["nrs"][0], "hint": _hint(e, "welche Option trifft zu? (eine)")})
                grp_opts[n] = opts + ["keine", "unklar"]; pfad[e["id"]] = "@S." + n
                for k, o, nr in zip(e["keys"], opts, e["nrs"]):
                    zuo[k] = "{{eq(@S." + n + ", " + _q(o) + ")}}"; grp_feld[nr] = (n, o); gewaehlt[nr] = f"eq(@S.{n}, {_q(o)})"
            else:                                                    # einzelnes Kästchen
                n = _slug(e["titel"], used)
                felder.append({"name": n, "label": e["titel"], "auswahl": ["ja", "nein"], "max_tokens": 3, "_nr": e["nrs"][0],
                               "hint": _hint(e, "trifft das zu?")})
                zuo[e["keys"][0]] = "{{eq(@S." + n + ", 'ja')}}"; grp_feld[e["nrs"][0]] = (n, "ja"); grp_opts[n] = ["ja", "nein"]
                pfad[e["id"]] = "@S." + n
        elif h == "fest" and e.get("wert"):
            w = e["wert"].strip(); pfad[e["id"]] = _q(w)
            for k, o in zip(e["keys"], opts if e["art"] == "gruppe" else ["ja"]):
                zuo[k] = (o.lower() == w.lower()) if e["art"] == "gruppe" else (w.lower() in ("ja", "x", "1", "true"))
        elif h == "abgeleitet" and e.get("regeln"):
            r = pfad[e["id"]]
            if e["art"] == "gruppe":                                 # v64e: je Option ein Ja/Nein der Regel (mehrere möglich)
                rid = r.split(".")[0]
                for i, (k, nr) in enumerate(zip(e["keys"], e["nrs"])):
                    zuo[k] = "{{" + rid + f".o{i}" + "}}"; gewaehlt[nr] = f"{rid}.o{i}"
            else: zuo[e["keys"][0]] = "{{eq(" + r + ", 'ja')}}"
        elif h == "abgeleitet":
            regeln.append({"titel": e["titel"], "nrs": e["nrs"], "regel": e.get("regel", ""), "wissen": e.get("wissen", "")})
    # 2) Einzelfelder
    for e in plan["eintraege"]:
        if e.get("typ") == "kontrollkaestchen": continue
        h, k = e["herkunft"], e["keys"][0]
        if h in ("fakt", "offen"):
            n = _slug(e["titel"], used); bed = grp_feld.get(e.get("zu")) if e.get("zu") else None
            zusatz = (f"nur angeben, wenn «{by_id.get('g' + str(e['zu']), {}).get('titel', 'das zugehörige Kästchen')}» zutrifft; sonst: keine"
                      if bed else "fehlt es: keine")
            if e.get("optionen"):
                f = {"name": n, "label": e["titel"], "auswahl": list(e["optionen"]) + ["unklar"], "max_tokens": _len_opt(e["optionen"]),
                     "hint": _hint(e, "Auswahl")}
                wert = "iif(isin(@S." + n + ", 'unklar', 'keine'), '', @S." + n + ")"
            elif e["typ"] == "datum":
                f = {"name": n, "label": e["titel"], "max_tokens": 14, "verlaengern": False, "hint": _hint(e, "Datum TT.MM.JJJJ; fehlt es: keine"),
                     "wenn_leer": PLATZHALTER, "leer_werte": NEUTRAL}
                wert = "@S." + n
            else:
                lang = re.search(r"beschr|bezeichnung|gegenstand|umfang|inhalt", e["titel"], re.I)
                f = {"name": n, "label": e["titel"], "max_tokens": 160 if lang else 50, "hint": _hint(e, zusatz),
                     "wenn_leer": "" if bed else PLATZHALTER, "leer_werte": NEUTRAL}
                wert = "@S." + n
            if bed:
                if wert == "@S." + n:                                # «keine/keiner/unklar» nie ins Dokument
                    wert = f"iif(isin(@S.{n}, 'keine', 'keiner', 'unklar', 'keine angabe in den unterlagen.'), '', @S.{n})"
                wert = f"iif(eq(@S.{bed[0]}, {_q(bed[1])}), {wert}, '')"
                # llmio: ist die Antwort des Kästchens/der Gruppe eine ANDERE Option, schreibt AURA «keiner» ohne Modell
                f["_skip_wenn"] = [bed[0], sorted({o.lower().rstrip(".") for o in grp_opts.get(bed[0], []) if o != bed[1]}
                                                  | {"keine", "unklar", "nein", ""})]
            f["_nr"] = e["nrs"][0]; felder.append(f); zuo[k] = "{{" + wert + "}}"; pfad[e["id"]] = "@S." + n
        elif h == "fest" and e.get("wert"): zuo[k] = e["wert"]; pfad[e["id"]] = _q(e["wert"])
        elif h == "manuell":
            ph = e.get("platzhalter") or PLATZHALTER
            if e.get("zu") in grp_feld: gewaehlt.setdefault(e["zu"], f"eq(@S.{grp_feld[e['zu']][0]}, {_q(grp_feld[e['zu']][1])})")
            zuo[k] = ("{{iif(" + gewaehlt[e["zu"]] + ", " + _q(ph) + ", '')}}") if e.get("zu") in gewaehlt else ph
        elif h == "abgeleitet" and e.get("regeln"):
            r = pfad[e["id"]]
            zuo[k] = ("{{" + r + "}}" if e.get("optionen") else "{{default(" + r + ", " + _q(PLATZHALTER) + ")}}")
        elif h == "abgeleitet":
            regeln.append({"titel": e["titel"], "nrs": e["nrs"], "regel": e.get("regel", ""), "wissen": e.get("wissen", "")})
    for r in regeln + [{"wissen": e.get("wissen", "")} for e in rspec]:
        for p in re.split(r"[;,]", r.get("wissen") or ""):
            if p.strip() and p.strip() not in pins: pins.append(p.strip())
    felder.sort(key=lambda f: f["_nr"])
    return felder, zuo, regeln, pins, rspec, pfad

# ----------------------------------------------------------------------------- Regeln (v64d)
OPS = {"=": "eq", "≠": "ne", "<": "lt", "≤": "le", ">": "gt", "≥": "ge", "enthält": "contains"}

def quellen(plan):
    """Mögliche Bedingungen für Regeln: [(id, anzeige, werte)] – Fakten, offene, feste und abgeleitete Einträge."""
    out = []
    for e in plan["eintraege"]:
        if e["herkunft"] in ("leer", "manuell") or (e["art"] == "gruppe" and e.get("mehrfach")): continue
        if e["herkunft"] == "abgeleitet" and not e.get("regeln"): continue
        nr = f"{e['nrs'][0]}–{e['nrs'][-1]}" if len(e["nrs"]) > 1 else str(e["nrs"][0])
        werte = _eindeutig(e["optionen"]) if e["art"] == "gruppe" else (["ja", "nein"] if e.get("typ") == "kontrollkaestchen"
                                                                           else list(e.get("optionen") or []))
        out.append((e["id"], f"{nr} · {e['titel'][:50]}", werte))
    return out

def ziel_werte(e):
    """Was eine Regel für diesen Eintrag setzen kann (leer = freier Text)."""
    if e["art"] == "gruppe": return _eindeutig(e["optionen"])
    if e.get("typ") == "kontrollkaestchen": return ["ja", "nein"]
    return list(e.get("optionen") or [])

def _bedingung(c, pfad):
    a = pfad.get(c.get("feld"))
    if a is None: return None
    op = OPS.get(c.get("op", "="), "eq"); w = _q(c.get("wert", ""))
    return f"not(eq({a}, {w}))" if op == "ne" else f"{op}({a}, {w})"

def dann_liste(d):
    """«dann» als Liste (v64e: bei Gruppen mehrere Optionen)."""
    if isinstance(d, list): return [x for x in d if x]
    return [d] if d else []

def regel_text(r, plan):
    """Lesbare Form: «Wenn Auftragswert < 150000 und … → Option + Option»."""
    t = {e["id"]: e["titel"][:40] for e in plan["eintraege"]}
    r = dict(r, dann=" + ".join(dann_liste(r.get("dann"))))
    w = " und ".join(f"{t.get(c.get('feld'), '?')} {c.get('op', '=')} {c.get('wert', '')}" for c in r.get("wenn") or [])
    return f"Wenn {w} → {r.get('dann', '')}" if w else f"Immer → {r.get('dann', '')}"

def regel_schritt(e, pfad, warn):
    sid = pfad[e["id"]].split(".")[0]; rg = []
    for i, r in enumerate(e.get("regeln") or []):
        bs = [_bedingung(c, pfad) for c in r.get("wenn") or []]
        if any(b is None for b in bs): warn.append(f"{e['titel'][:40]}: Regel {i + 1} verweist auf ein Feld ohne Wert – übersprungen"); continue
        wenn = bs[0] if len(bs) == 1 else ("and(" + ", ".join(bs) + ")" if bs else "true")
        rg.append({"name": f"{e['titel'][:40]} – Regel {i + 1}", "wenn": wenn, "dann": _dann(e, r.get("dann"))})
    return {"id": sid, "type": "regel", "label": f"Regel: {e['titel'][:50]}", "regeln": rg, "sonst": _dann(e, e.get("sonst", ""))}

def _dann(e, d):
    """Ergebnis einer Regel. Gruppe: wert = «A | B» und o<i> = true je angekreuzte Option; sonst wert = Text."""
    if e["art"] != "gruppe": return {"wert": " | ".join(dann_liste(d)) if isinstance(d, list) else (d or "")}
    ds, opts = dann_liste(d), _eindeutig(e["optionen"])
    out = {"wert": " | ".join(ds)}
    for i, o in enumerate(opts):
        if o in ds: out[f"o{i}"] = True
    return out

def _kosten(f):
    spec = f"- {f['name']}: {f.get('hint', '')}" + (" – genau eines von: " + " | ".join(f["auswahl"]) if f.get("auswahl") else "")
    return _tok(spec) + int(f.get("max_tokens", 250)) + 12

def aufteilen(felder, dok_zeichen=DOK_ZEICHEN, max_t=MAX_T):
    """Felder so auf Schritte verteilen, dass Eingabe + Antwort mit 10 % Luft ins Kontextfenster passen."""
    frei = int(max_t * 0.9) - _tok("x" * dok_zeichen) - RESERVE_SYSTEM
    if frei < 300: raise ValueError(f"Unterlagen ({dok_zeichen} Zeichen) füllen das Sprachmodell schon fast – max_chars senken")
    teile, akt, summe = [], [], 0
    for f in felder:
        c = _kosten(f)
        if akt and summe + c > frei: teile.append(akt); akt, summe = [], 0
        akt.append(f); summe += c
    if akt: teile.append(akt)
    return teile, frei

def schritte(plan, vorlage_rel, name, dok_var="dateien.text", dok_zeichen=DOK_ZEICHEN, max_t=MAX_T):
    """-> (liste von Schritten, info). Schritte: werte, werte_2 … (llm) + word (word_vorlage)."""
    felder, zuo, regeln, pins, rspec, pfad = planen(plan); warn = []
    teile, frei = aufteilen(felder, dok_zeichen, max_t) if felder else ([], 0)
    S, wo = [], {}
    for i, t in enumerate(teile):
        sid = "werte" if i == 0 else f"werte_{i + 1}"
        for f in t: wo[f["name"]] = sid
        S.append({"id": sid, "type": "llm", "label": "Angaben aus den Unterlagen erfassen" + (f" ({i + 1}/{len(teile)})" if len(teile) > 1 else ""),
                  "system": "Du erfasst Angaben aus Unterlagen für ein Formular. Nur was in den Unterlagen steht; nichts erfinden. "
                            "Schweizer Schreibweise.",
                  "vorspann": "UNTERLAGEN:\n{{" + dok_var + "}}",
                  "prompt": f"Fülle die Angaben für das Formular «{name}» aus den UNTERLAGEN oben. "
                            "Steht etwas nicht darin, schreibe «keine».",
                  "fields": [{k: v for k, v in f.items() if not k.startswith("_") or k == "_skip_wenn"} for f in t]})
    for e in rspec: S.append(regel_schritt(e, pfad, warn))
    def ersetze(v):
        if not isinstance(v, str): return v
        return re.sub(r"@S\.([a-z0-9_]+)", lambda m: f"{wo.get(m.group(1), 'werte')}.{m.group(1)}", v)
    mapping = {k: ersetze(v) for k, v in zuo.items()}
    for s in S:
        if s["type"] == "regel":
            for r in s["regeln"]: r["wenn"] = ersetze(r["wenn"])
    S.append({"id": "word", "type": "word_vorlage", "label": "Vorlage ausfüllen", "vorlage": vorlage_rel, "felder": mapping,
              "name": name, "platzhalter": [PLATZHALTER]})
    info = {"modellfelder": len(felder), "schritte": len(teile), "zuordnungen": len(mapping), "offene_regeln": regeln,
            "regelschritte": len(rspec), "regeln_n": sum(len(e.get("regeln") or []) for e in rspec), "warnungen": warn,
            "pins": pins, "budget_frei": frei,
            "geschaetzt": [sum(_kosten(f) for f in t) + _tok("x" * dok_zeichen) + RESERVE_SYSTEM for t in teile]}
    return S, info

# ----------------------------------------------------------------------------- bestehenden Workflow umbauen
def anwenden(wf, plan, vorlage_rel):
    """Ersetzt in einem bestehenden workflow.json (dict) die Vorlage-Schritte durch den Bau aus dem Feldplan.
    Bleibt: Eingaben, Lesen, Wissen, Prüfliste und Ausgaben. Rückgabe: (wf, info)."""
    steps = wf.setdefault("steps", [])
    ex = next((s for s in steps if s.get("type") == "extract"), None)
    if ex is None:
        fin = next((i["id"] for i in wf.get("inputs", []) if i.get("type") == "files"), None)
        if not fin:
            fin = "dokumente"; wf.setdefault("inputs", []).append({"id": fin, "type": "files", "label": "Dokumente",
                                                                   "ext": [".pdf", ".docx", ".txt", ".md"]})
        ex = {"id": "dateien", "type": "extract", "label": "Dokumente lesen", "files": "{{input." + fin + "}}"}
        steps.insert(0, ex)
    if sum(1 for i in wf.get("inputs", []) if i.get("type") == "files") > 1: ex["alle_eingaben"] = True    # v95
    ex["max_chars"] = min(int(ex.get("max_chars", DOK_ZEICHEN) or DOK_ZEICHEN), DOK_ZEICHEN)
    alt = [i for i, s in enumerate(steps) if (s.get("type") == "word_vorlage" and s.get("vorlage") == vorlage_rel)
           or (s.get("type") == "llm" and re.fullmatch(r"werte(_\d+)?", str(s.get("id", ""))))
           or (s.get("type") == "regel" and str(s.get("id", "")).startswith("r_"))]
    pos = alt[0] if alt else len(steps)
    for i in reversed(alt): del steps[i]
    pos = min(pos, len(steps))
    neu, info = schritte(plan, vorlage_rel, wf.get("name", "Formular"), ex["id"] + ".text", ex["max_chars"])
    ids = {s.get("id") for s in steps}
    for s in neu:
        if s["id"] in ids: raise ValueError(f"Schritt-ID «{s['id']}» gibt es schon – bitte im Reiter «Schritte» umbenennen")
    steps[pos:pos] = neu
    for s in steps:                                                  # Grundlagen der Regeln -> Pflichtstellen im Wissen
        if s.get("type") == "rag" and info["pins"]:
            p = s.get("pin") or []; p = [p] if isinstance(p, str) else list(p)
            s["pin"] = p + [x for x in info["pins"] if x not in p]
    wf["offene_regeln"] = info["offene_regeln"]
    wf["feldplan"] = {"vorlage": vorlage_rel, "modellfelder": info["modellfelder"], "schritte": info["schritte"]}
    return wf, info

def bericht(info):
    t = (f"{info['modellfelder']} Fragen ans Sprachmodell in {info['schritte']} Schritt(en), "
         f"{info['zuordnungen']} Vorlagenfelder zugeordnet.")
    if info["geschaetzt"]: t += f"\nGeschätzte Grösse je Schritt: {', '.join(f'{x:,}'.replace(',', chr(39)) for x in info['geschaetzt'])} von {MAX_T:,} Tokens.".replace(",", "'")
    if info.get("regelschritte"): t += f"\n{info['regeln_n']} Regel(n) in {info['regelschritte']} Entscheidungstabelle(n) – ohne Sprachmodell."
    for w in info.get("warnungen") or []: t += f"\n⚠ {w}"
    if info["offene_regeln"]:
        t += f"\n\n{len(info['offene_regeln'])} Regel(n) noch offen (Felder bleiben leer, bis die Regel umgesetzt ist):"
        for r in info["offene_regeln"][:8]:
            t += f"\n• {r['titel']}: {r['regel'] or '– noch keine Regel beschrieben –'}"
    if info["pins"]: t += f"\n\nPflichtstellen im Wissen ergänzt: {', '.join(info['pins'])}"
    return t
