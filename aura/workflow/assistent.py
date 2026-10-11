# aura/workflow/assistent.py — «Workflow beschreiben»: Beschreibung -> Bauplan -> Workflow. Version 20261011v64c (v64c: Word-Vorlage über den Feldplan – nur Fakten ans Modell)
#
# Aufteilung (bewusst): AURA liest Bausteine «[…]» und eindeutige Wörter selbst (zuverlässig). Das Sprachmodell füllt nur,
# was danach noch fehlt (Ergebnis, Regeln aus Fliesstext, eine Rückfrage) – aus fester Auswahl. Den Workflow baut immer
# Python nach festen Mustern, damit er gültig ist. Korrekturen danach im Reiter «Schritte».
# Muster: Prüfbericht (Dokumente gegen Regeln) · Zusammenfassung/Text (aus Dateien, Terminen, Mails, Wissen) ·
#         Word-Vorlage ausfüllen. Auslöser: beim Start (Dateien) oder Zeitplan.
import copy, re

ZEITRAUM_LABEL = {"heute": "heute", "morgen": "morgen", "naechste_7": "nächste 7 Tage", "naechste_30": "nächste 30 Tage",
                  "letzte_7": "letzte 7 Tage", "letzte_30": "letzte 30 Tage", "diese_woche": "diese Woche"}
ERGEBNISSE = {"pruefbericht": "Prüfbericht", "zusammenfassung": "Zusammenfassung", "word": "Word-Vorlage ausfüllen",
              "meldung": "Anzeige in AURA", "mail": "Mail an mich", "datei": "Datei"}

# Bausteine für die Liste rechts: (Gruppe, Text im Feld, Hilfe)
BAUSTEINE = [
    ("Wann", "beim Start mit Dateien", "Beim Start wählt man Dateien aus."),
    ("Wann", "werktags um 08:00", "Zeitplan; Uhrzeit im Text änderbar, z.B. «werktags um 07:30»."),
    ("Wann", "täglich um 08:00", "Zeitplan an allen Tagen."),
    ("Wann", "montags um 08:00", "Zeitplan einmal pro Woche."),
    ("Zeitraum", "heute", ""), ("Zeitraum", "morgen", ""), ("Zeitraum", "nächste 7 Tage", ""), ("Zeitraum", "nächste 30 Tage", ""),
    ("Zeitraum", "letzte 7 Tage", ""), ("Zeitraum", "letzte 30 Tage", ""), ("Zeitraum", "diese Woche", ""),
    ("Woraus", "meine Termine", "Outlook-Kalender (wie in AURA abgeglichen)."),
    ("Woraus", "meine Mails", "Outlook-Mails (wie in AURA abgeglichen)."),
    ("Woraus", "hochgeladene Dateien", "Dokumente, die beim Start gewählt werden."),
    ("Woraus", "Wissen", "Dokumente im Reiter «Wissen» dieses Workflows (Richtlinien, Vorlagen …)."),
    ("Verarbeiten", "zu jedem Termin", "z.B. «… zu jedem Termin die passenden [meine Mails]»."),
    ("Verarbeiten", "Regeln:", "Danach je Zeile eine Regel, z.B. «- Jede Quelle steht im Literaturverzeichnis»."),
    ("Ergebnis", "Prüfbericht", "Liste: was erfüllt ist und was nicht, mit Fundstellen."),
    ("Ergebnis", "Zusammenfassung", "Text, den das Sprachmodell schreibt."),
    ("Ergebnis", "Word-Vorlage ausfüllen", "Eine Word-Vorlage mit Werten aus den Unterlagen füllen (Datei unten wählen)."),
    ("Ergebnis", "Anzeige in AURA", "Das Ergebnis erscheint auf der Startseite unter «Ergebnisse» (Standard)."),
    ("Ergebnis", "Mail an mich", "Outlook-Mail an die eigene Adresse, als Entwurf."),
    ("Ergebnis", "Datei", "Das Ergebnis wird zusätzlich als Datei gespeichert (zum Weitergeben)."),
    ("Form", "als Stichpunkte", "Kurze Aufzählung (Standard)."),
    ("Form", "als Text", "Kurzer Fliesstext in Absätzen."),
    ("Form", "als Tabelle", "Stichpunkte plus Tabellen der Daten (z.B. alle Termine mit Zeit, Ort, Überschneidungen)."),
]

_ZEIT = re.compile(r"(täglich|taeglich|werktags|jeden tag|montags|dienstags|mittwochs|donnerstags|freitags|samstags|sonntags)"
                   r"\s*(?:um\s*)?(\d{1,2})(?:[:.](\d{2}))?\s*(?:uhr)?", re.I)
_TAG = {"montags": ["mo"], "dienstags": ["di"], "mittwochs": ["mi"], "donnerstags": ["do"], "freitags": ["fr"],
        "samstags": ["sa"], "sonntags": ["so"], "werktags": "werktags"}

FORMEN = {"stichpunkte": "Stichpunkte", "text": "Text", "tabelle": "Tabelle"}

def leer_plan():
    return {"ausloeser": "manuell", "zeitplan": None, "dateien": False, "kalender": None, "mails": None, "je_termin": False,
            "wissen": False, "ergebnis": [], "vorlage": None, "regeln": [], "anweisung": "", "fragen": [], "form": "stichpunkte"}

def _zr(s):
    s = s.lower().replace("ä", "ae")
    for k, v in ZEITRAUM_LABEL.items():
        if v.lower().replace("ä", "ae") == s: return k
    m = re.search(r"(naechste|kommende|letzte|vergangene)n?\s+(\d+)\s+tag", s)
    if m: return ("naechste_" if m.group(1) in ("naechste", "kommende") else "letzte_") + ("7" if int(m.group(2)) <= 7 else "30")
    if "naechste woche" in s or "kommende woche" in s: return "naechste_7"
    if "diese woche" in s: return "diese_woche"
    return {"heute": "heute", "morgen": "morgen"}.get(s.strip())

def lesen(text):
    """Deterministisch: Bausteine «[…]» und eindeutige Wörter -> Bauplan. Kein Sprachmodell."""
    p = leer_plan()
    low = re.sub(r"\[[^\]]*\]", lambda m: " " * len(m.group(0)), text).lower()   # v62: Wörter in Bausteinen nicht doppelt lesen
    toks = [(m.start(), m.group(1).strip()) for m in re.finditer(r"\[([^\]]+)\]", text)]
    quellen = []                                                      # (Position, "kalender"|"mails") für Zeiträume
    def quelle(pos, q):
        if q == "kalender" and p["kalender"] is None: p["kalender"] = {"zeitraum": None}
        if q == "mails" and p["mails"] is None: p["mails"] = {"zeitraum": None}
        quellen.append((pos, q))
    for pos, t in toks:
        tl = t.lower()
        if tl == "beim start mit dateien" or tl == "hochgeladene dateien": p["dateien"] = True
        elif tl == "meine termine": quelle(pos, "kalender")
        elif tl == "meine mails": quelle(pos, "mails")
        elif tl == "wissen" or tl.startswith("wissen:"): p["wissen"] = True
        elif tl == "zu jedem termin": p["je_termin"] = True
        elif tl.startswith("word-vorlage"): p["ergebnis"].append("word")
        elif tl == "meldung in aura": p["ergebnis"].append("meldung")
        elif tl.startswith("als "): p["form"] = {"als text": "text", "als tabelle": "tabelle"}.get(tl, "stichpunkte")
        else:
            for k, v in ERGEBNISSE.items():
                if tl == v.lower() and k not in p["ergebnis"]: p["ergebnis"].append(k)
    for pos, q in [(m.start(), "kalender") for m in re.finditer(r"termin|kalender|sitzung", low)] + \
                  [(m.start(), "mails") for m in re.finditer(r"\bmails?\b|e-mails?|nachrichten", low)]:
        if not any(abs(pos - x) < 20 and q == y for x, y in quellen): quelle(pos, q)
    if re.search(r"zu jedem termin|je termin|pro termin", low): p["je_termin"] = True
    # Zeiträume: an die nächste Quelle davor binden, sonst an die danach
    for pos, t in toks + [(m.start(), m.group(0)) for m in re.finditer(r"(?:nächste|kommende|letzte|vergangene)n?\s+\d+\s+tage?|nächste woche|kommende woche|diese woche|\bheute\b|\bmorgen\b", low)]:
        z = _zr(t)
        if not z or not quellen: continue
        quellen.sort()
        vor = [q for q in quellen if q[0] < pos]; q = (vor[-1] if vor else min(quellen, key=lambda q: q[0]))[1]
        ziel = p["kalender"] if q == "kalender" else p["mails"]
        if ziel is not None and ziel["zeitraum"] is None: ziel["zeitraum"] = z
    if not any(t.lower().startswith("als ") for _, t in toks):          # v62: Form aus dem Text
        if re.search(r"tabelle|tabellarisch", low): p["form"] = "tabelle"
        elif re.search(r"fliesstext|fließtext|als text|in sätzen|prosa", low): p["form"] = "text"
    m = _ZEIT.search(text)
    if m:
        w = m.group(1).lower(); h, mi = int(m.group(2)), int(m.group(3) or 0)
        p["ausloeser"] = "zeitplan"; p["zeitplan"] = {"tage": _TAG.get(w, "taeglich"), "zeit": f"{h:02d}:{mi:02d}"}
    for k, wort in (("pruefbericht", r"prüf|kontroll|überprüf"), ("zusammenfassung", r"zusammenfass|überblick|übersicht|briefing"),
                    ("word", r"vorlage .*ausfüll|formular .*ausfüll|ausfüllen")):
        if k not in p["ergebnis"] and re.search(wort, low) and not (k == "pruefbericht" and p["ergebnis"]): p["ergebnis"].append(k)
    if re.search(r"dokument|datei|unterlagen|arbeit\b|pdf|word", low) and p["ausloeser"] == "manuell": p["dateien"] = True
    if "pruefbericht" in p["ergebnis"] or "word" in p["ergebnis"]: p["dateien"] = True
    # Regeln: Zeilen mit -, •, * oder Nummer
    p["regeln"] = [re.sub(r"^\s*(?:[-•*]|\d+[.)])\s*", "", l).strip() for l in text.splitlines()
                   if re.match(r"^\s*(?:[-•*]|\d+[.)])\s+\S", l)]
    rest = "\n".join(l for l in text.splitlines() if not re.match(r"^\s*(?:[-•*]|\d+[.)])\s+\S", l))
    # v63: Was AURA selbst umsetzt (Zeitplan, Ausgabeziel, Form), gehört nicht in den Auftrag ans Modell
    weg = {t.lower() for g, t, _ in BAUSTEINE if g in ("Wann", "Form")} | {"anzeige in aura", "mail an mich", "datei", "meldung in aura"}
    a = re.sub(r"\[([^\]]+)\]", lambda m: "" if m.group(1).strip().lower() in weg or _ZEIT.fullmatch(m.group(1).strip())
               else m.group(1), rest)
    a = _ZEIT.sub("", a)
    a = re.sub(r"\bals (?:stichpunkte|text|tabelle)\b", "", a, flags=re.I).replace("Regeln:", "")
    a = re.sub(r"[ \t]+([,.;:])", r"\1", re.sub(r"[ \t]{2,}", " ", a))
    a = re.sub(r"\s*\b(?:per|via|an|in|als|und per)\b(?=\s*(?:[,.;!]|$))", "", a, flags=re.I | re.M)
    a = re.sub(r"(?:\s*(?:,|\bund\b|\boder\b))+\s*([.!]|$)", r"\1", a, flags=re.M)   # «… zeigen und .» -> «… zeigen.»
    p["anweisung"] = "\n".join(l.strip() for l in a.splitlines() if l.strip(" ,.;:-")).strip()
    return p

def rueckfragen(p):
    """Was fehlt? [(feld, frage)] – die Oberfläche markiert diese Felder."""
    out = []
    if not p["ergebnis"]: out.append(("ergebnis", "Was soll herauskommen?"))
    if p["ausloeser"] == "zeitplan" and not (p["zeitplan"] or {}).get("zeit"): out.append(("zeit", "Um welche Uhrzeit?"))
    if p["ausloeser"] == "zeitplan" and p["dateien"]:
        out.append(("dateien", "Ein Zeitplan-Lauf kann keine Dateien abfragen – Dateien ins «Wissen» legen oder Auslöser «beim Start»."))
    if p["kalender"] is not None and not p["kalender"]["zeitraum"]: out.append(("kalender", "Termine aus welchem Zeitraum?"))
    if p["mails"] is not None and not p["mails"]["zeitraum"]: out.append(("mails", "Mails aus welchem Zeitraum?"))
    if "pruefbericht" in p["ergebnis"] and not p["regeln"]: out.append(("regeln", "Nach welchen Regeln prüfen? (eine pro Zeile)"))
    if "word" in p["ergebnis"] and not p["vorlage"]: out.append(("vorlage", "Welche Word-Vorlage?"))
    if not (p["dateien"] or p["kalender"] or p["mails"] or p["wissen"]): out.append(("woraus", "Woraus soll AURA die Angaben nehmen?"))
    if p["ergebnis"] and all(e in ("datei", "mail", "meldung") for e in p["ergebnis"]) and p["dateien"] and not (p["kalender"] or p["mails"]):
        out.append(("ergebnis", "Was soll mit den Dokumenten geschehen: Zusammenfassung, Prüfbericht oder Vorlage ausfüllen?"))
    return out

# ----------------------------------------------------------------------------- Sprachmodell (nur für Lücken)
def llm_felder():
    return [{"name": "ergebnis", "auswahl": ["Prüfbericht", "Zusammenfassung", "Word-Vorlage ausfüllen", "unklar"], "max_tokens": 8,
             "hint": "was am Ende herauskommen soll"},
            {"name": "regeln", "max_tokens": 220, "verlaengern": False,
             "hint": "Anforderungen oder Regeln aus der Beschreibung, je eine Zeile mit «- » am Anfang; sonst: keine"},
            {"name": "rueckfrage", "max_tokens": 50, "verlaengern": False,
             "hint": "EINE kurze Rückfrage, falls etwas Wichtiges fehlt; sonst: keine"}]

def llm_prompt(text):
    return ("Ein Benutzer beschreibt einen Arbeitsablauf, den ein Programm automatisch ausführen soll.\n"
            f"BESCHREIBUNG:\n{text}\n\nBestimme die verlangten Angaben.")

def llm_mischen(p, r):
    p = copy.deepcopy(p)
    e = {"Prüfbericht": "pruefbericht", "Zusammenfassung": "zusammenfassung", "Word-Vorlage ausfüllen": "word"}.get(r.get("ergebnis", ""))
    if e and not p["ergebnis"]: p["ergebnis"].append(e)
    if not p["regeln"]:
        rg = [re.sub(r"^\s*[-•*]\s*", "", l).strip() for l in str(r.get("regeln", "")).splitlines()]
        p["regeln"] = [x for x in rg if x and x.lower().rstrip(".") not in ("keine", "unklar", "keine angabe in den unterlagen")]
    f = str(r.get("rueckfrage", "")).strip()
    if f and f.lower().rstrip(".") not in ("keine", "unklar", "keine angabe in den unterlagen"): p["fragen"] = [f]
    return p

# ----------------------------------------------------------------------------- Workflow bauen
def _kurz(v):
    """v58: Fürs Sprachmodell die knappe Fassung (termine.kurz / mails.kurz), angehängt wird die vollständige."""
    return {"termine.text": "termine.kurz", "mails.text": "mails.kurz"}.get(v, v)

def _slug(t, used):
    t = t.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("é", "e"), ("è", "e")): t = t.replace(a, b)
    b = re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:28] or "feld"
    if b[0].isdigit(): b = "f_" + b
    s, n = b, 2
    while s in used: s = f"{b}_{n}"; n += 1
    used.add(s); return s

def bauen(p, name, vorlage=None, vorlage_felder=None, feldplan=None):
    """Bauplan -> workflow.json (dict). vorlage: 'vorlagen/<datei>.docx', vorlage_felder: docx_fill.analyze(...).
    v64c: feldplan (feldplan.py) -> Vorlage-Schritte aus feldplan_bau (sparsam, mit Budgetprüfung)."""
    wf = {"name": name, "description": "Erstellt mit «Workflow beschreiben». Korrekturen im Reiter «Schritte».",
          "beschreibung_original": p.get("_text", ""), "knowledge": [{"sammlung": "eigen"}] if p["wissen"] else [],
          "inputs": [], "steps": []}
    S = wf["steps"]; daten = []
    if p["ausloeser"] == "zeitplan" and p["zeitplan"]: wf["zeitplan"] = p["zeitplan"]
    if p["dateien"] and p["ausloeser"] != "zeitplan":
        wf["inputs"].append({"id": "dokumente", "type": "files", "label": "Dokumente", "ext": [".pdf", ".docx", ".txt", ".md"]})
        if "pruefbericht" not in p["ergebnis"] or len(p["ergebnis"]) > 1:
            S.append({"id": "dateien", "type": "extract", "label": "Dokumente lesen", "files": "{{input.dokumente}}", "max_chars": 20000})
            daten.append(("DOKUMENTE", "dateien.text"))
    if p["kalender"] is not None:
        S.append({"id": "termine", "type": "kalender", "label": "Termine holen", "zeitraum": p["kalender"]["zeitraum"] or "heute"})
        daten.append(("TERMINE", "termine.text"))
    if p["mails"] is not None:
        z = p["mails"]["zeitraum"] or "letzte_7"
        if p["je_termin"] and p["kalender"] is not None:
            S.append({"id": "mails", "type": "fuer_jedes", "label": "Mails zu jedem Termin", "liste": "{{termine.termine}}",
                      "schritt": {"type": "mails", "zeitraum": z, "suche": "{{item.titel}}", "max": 3}})
        else:
            S.append({"id": "mails", "type": "mails", "label": "Mails holen", "zeitraum": z, "max": 15})
        daten.append(("MAILS", "mails.text"))
    if p["wissen"]:
        S.append({"id": "wissen", "type": "rag", "label": "Wissen durchsuchen", "collection": "eigen", "k": 6, "max_chars": 8000,
                  "query": (p["anweisung"] + " " + " ".join(p["regeln"]))[:500] or name})
        daten.append(("WISSEN", "wissen.text"))
    if "pruefbericht" in p["ergebnis"]:
        st = {"id": "pl", "type": "pruefliste", "label": "Prüfliste", "files": "{{input.dokumente}}",
              "punkte": [{"art": "frage", "name": r[:60], "frage": f"Ist diese Anforderung im Text erfüllt: {r}",
                          "schwere": "Hinweis", "quelle": "Beschreibung des Workflows"} for r in p["regeln"]]}
        if p["wissen"]: st["kontext"] = "{{wissen.text}}"
        S.append(st)
    if "word" in p["ergebnis"] and vorlage and feldplan:              # v64c
        from . import feldplan_bau as FB
        neu, info = FB.schritte(feldplan, vorlage, name, "dateien.text", FB.DOK_ZEICHEN)
        for s in S:
            if s["id"] == "dateien": s["max_chars"] = FB.DOK_ZEICHEN
        if p["wissen"] and info["pins"]: next(s for s in S if s["id"] == "wissen")["pin"] = info["pins"]
        S.extend(neu); wf["offene_regeln"] = info["offene_regeln"]
        wf["feldplan"] = {"vorlage": vorlage, "modellfelder": info["modellfelder"], "schritte": info["schritte"]}
    elif "word" in p["ergebnis"] and vorlage:
        used, fields, mapping = set(), [], {}
        for f in vorlage_felder or []:
            n = _slug(f["key"], used); x = {"name": n, "label": f["key"]}
            if f["typ"] == "kontrollkaestchen": x.update(auswahl=["ja", "nein"], max_tokens=3, hint=f"Trifft «{f['key']}» zu?")
            elif f["optionen"]: x.update(auswahl=f["optionen"] + ["unklar"], max_tokens=30, hint=f"Auswahl für «{f['key']}»")
            elif f["typ"] == "datum": x.update(max_tokens=12, hint=f"Datum für «{f['key']}» (TT.MM.JJJJ); fehlt es: keine")
            else: x.update(max_tokens=120, hint=f"Angabe für «{f['key']}» aus den Unterlagen")
            if f["typ"] != "kontrollkaestchen" and not f["optionen"]: x["wenn_leer"] = "[ergänzen]"
            fields.append(x); mapping[f["key"]] = "{{werte." + n + "}}"
        S.append({"id": "werte", "type": "llm", "label": "Werte für die Vorlage erfassen",
                  "system": "Du erfasst Angaben aus Unterlagen für ein Formular. Nur was in den Unterlagen steht; Schweizer Schreibweise.",
                  "prompt": (p["anweisung"] + "\n\n" if p["anweisung"] else "") + "\n\n".join(f"{k}:\n{{{{{v}}}}}" for k, v in daten),
                  "fields": fields})
        S.append({"id": "word", "type": "word_vorlage", "label": "Vorlage ausfüllen", "vorlage": vorlage, "felder": mapping,
                  "name": name, "platzhalter": ["[ergänzen]"]})
    # v57: Nur ein Ausgabeziel gewählt (Anzeige/Mail/Datei) ohne Prüfbericht/Vorlage = Zusammenfassung dorthin
    nur_ziel = daten and not any(e in p["ergebnis"] for e in ("pruefbericht", "word", "zusammenfassung"))
    if "zusammenfassung" in p["ergebnis"] or nur_ziel:
        # v54: Das Modell schreibt nur das Kurzfazit (schnell); die vollständigen Listen hängt AURA selbst an.
        extra = [("ÜBERSCHNEIDUNGEN (berechnet)", "termine.ueberschneidungen")] if p["kalender"] is not None else []
        S.append({"id": "text", "type": "llm", "label": "Kurzfazit schreiben",
                  "system": "Du bist ein sachlicher Assistent. Verwende nur die gegebenen Daten. Schweizer Schreibweise, kurz und klar.",
                  "prompt": f"AUFTRAG:\n{p['anweisung'] or 'Fasse die Daten zusammen.'}\n\n"
                            + "\n\n".join(f"{k}:\n{{{{{_kurz(v)}}}}}" for k, v in daten + extra)
                            + ("\n\nSchreibe einen kurzen Fliesstext (2–3 Absätze, keine Aufzählung): Schwerpunkte, Überschneidungen, "
                               "was vorzubereiten ist. Gib die Daten NICHT vollständig wieder." if p.get("form") == "text" else
                               "\n\nSchreibe höchstens 5 kurze Stichpunkte: Schwerpunkte, Überschneidungen, was vorzubereiten ist. "
                               "Gib die Daten NICHT vollständig wieder (keine Tabelle)" + (" – die Tabellen hängt AURA selbst an."
                                                                                           if p.get("form") == "tabelle" else "."))
                            + " Nur was aus den Daten ersichtlich ist; keine allgemeinen Ratschläge, keine erfundenen Aufgaben."
                              " Ausgabe, Form und Zeitplan regelt AURA – erwähne sie nicht.",
                  "max_new": 350})
        anhang = "".join(f"\n\n{k}\n{{{{{v}}}}}" for k, v in daten if k in ("TERMINE", "MAILS"))
        S.append({"id": "bericht", "type": "template", "label": "Ergebnis zusammensetzen", "html": False,
                  "text": "{{text.text}}" + anhang})
        out = [e for e in p["ergebnis"] if e in ("meldung", "mail", "datei")] or ["meldung"]
        tab = {k: "{{" + v.replace(".text", ".tabelle") + "}}" for k, v in daten if k in ("TERMINE", "MAILS")}   # v59
        tab = {k.capitalize(): v for k, v in tab.items() if not (k == "MAILS" and p["je_termin"])} if p.get("form") == "tabelle" else {}
        fm = p.get("form", "stichpunkte")
        if "meldung" in out: S.append({"id": "anzeige", "type": "meldung", "label": "Anzeige in AURA", "text": "{{text.text}}",
                                       "titel": name, "form": fm, "tabellen": tab})
        if "mail" in out: S.append({"id": "mail", "type": "mail_an_mich", "label": "Mail an mich (Entwurf)", "text": "{{text.text}}",
                                    "form": fm, "tabellen": tab,
                                    "betreff": name, "senden": False})
        if "datei" in out: S.append({"id": "datei", "type": "file_out", "label": "Datei speichern", "content": "{{bericht.text}}",
                                     "name": name, "format": "md", "open": False})
    if not S: S.append({"id": "dateien", "type": "extract", "label": "Dokumente lesen", "files": "{{input.dokumente}}"})
    return wf

def zusammenfassung(p):
    """Klartext «Ich habe verstanden» für die Oberfläche."""
    L = []
    L.append("Auslöser: " + (f"Zeitplan, {p['zeitplan']['tage'] if isinstance(p['zeitplan']['tage'], str) else ', '.join(p['zeitplan']['tage'])} "
                             f"um {p['zeitplan']['zeit']}" if p["ausloeser"] == "zeitplan" and p["zeitplan"] else "beim Start"))
    q = []
    if p["dateien"]: q.append("Dateien beim Start")
    if p["kalender"] is not None: q.append(f"Termine ({ZEITRAUM_LABEL.get(p['kalender']['zeitraum'], '?')})")
    if p["mails"] is not None: q.append(f"Mails ({ZEITRAUM_LABEL.get(p['mails']['zeitraum'], '?')})" + (" zu jedem Termin" if p["je_termin"] else ""))
    if p["wissen"]: q.append("Wissen")
    L.append("Woraus: " + (", ".join(q) or "?"))
    L.append("Ergebnis: " + (", ".join(ERGEBNISSE[e] for e in p["ergebnis"]) or "?") + f" · Form: {FORMEN.get(p.get('form'), 'Stichpunkte')}")
    if p["regeln"]: L.append("Regeln: " + "; ".join(p["regeln"]))
    return L
