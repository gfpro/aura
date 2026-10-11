# aura/workflow/schema.py — Beschreibung der Bausteine für den Schritt-Editor (Reiter «Schritte»). Version 20261011v62
#
# Jeder Baustein (Schritt-Typ) beschreibt hier seine Felder in Alltagssprache. Die Oberfläche baut daraus das Formular;
# ein neuer Baustein braucht nur einen Eintrag hier, keine Änderung an der Oberfläche.
# Feld: key (Parameter im workflow.json), label, typ, hilfe, standard, pflicht, optionen, wert_einfuegen
#   typ: text | textarea | zahl | ja_nein | auswahl | liste (Komma-getrennt -> Liste) | werte («name = wert» je Zeile -> dict)
#        | felder (Felder des Sprachmodells, eigener Editor) | json (fortgeschritten) | info (nur Hinweis)
#   optionen: Liste oder Name einer Quelle: "vorlagen" (Word-Dateien im Paket), "sammlungen", "quellen"
# ergebnis: was der Schritt liefert (für «Wert einfügen»); bei llm/set/regel kommen die eigenen Namen dazu.
# Keine Fachinhalte (kein APA, keine Beschaffung) – nur allgemeine Bausteine.

GRUPPEN = ("Holen", "Verarbeiten", "Ausgeben")

BAUSTEINE = {
    "extract": {
        "titel": "Dateien lesen", "gruppe": "Holen", "id": "dateien",
        "beschreibung": "Liest den Text aus Dateien (PDF, Word, Text), meist aus den Eingaben beim Start.",
        "felder": [
            {"key": "files", "label": "Dateien", "typ": "text", "standard": "{{input.files}}", "pflicht": True, "wert_einfuegen": True,
             "hilfe": "Meist die Eingabe beim Start: über «Wert einfügen» → Eingaben wählen."},
            {"key": "max_chars", "label": "Höchstens Zeichen", "typ": "zahl", "standard": 12000,
             "hilfe": "Längere Texte werden abgeschnitten. Das Sprachmodell verarbeitet etwa 20'000 Zeichen gut."}],
        "ergebnis": [("text", "der gelesene Text"), ("chars", "Anzahl Zeichen"), ("truncated", "ja, wenn gekürzt")]},
    "rag": {
        "titel": "Wissen durchsuchen", "gruppe": "Holen", "id": "wissen",
        "beschreibung": "Sucht passende Stellen im Wissen (Reiter «Wissen») oder in Mails, Kalender, Dokumenten.",
        "felder": [
            {"key": "query", "label": "Wonach suchen?", "typ": "textarea", "pflicht": True, "wert_einfuegen": True,
             "hilfe": "Suchbegriffe oder eine Frage. Werte aus früheren Schritten mit «Wert einfügen»."},
            {"key": "collection", "label": "In welchem Wissen?", "typ": "auswahl", "optionen": "sammlungen", "standard": "eigen",
             "hilfe": "«eigen» = Wissen dieses Workflows. Leer lassen und unten Quellen wählen, um in Mails usw. zu suchen."},
            {"key": "sources", "label": "Oder in AURA-Quellen", "typ": "liste", "optionen": "quellen",
             "hilfe": "Nur wenn oben kein Wissen gewählt ist: outlook_mail, outlook_calendar, edge_history, folder_docs."},
            {"key": "k", "label": "Anzahl Treffer", "typ": "zahl", "standard": 6},
            {"key": "pin", "label": "Immer mitgeben", "typ": "liste",
             "hilfe": "Stellen, die bei jedem Lauf dabei sein müssen, z.B. «BöB Art. 21» (durch Komma getrennt)."},
            {"key": "max_chars", "label": "Höchstens Zeichen", "typ": "zahl"}],
        "ergebnis": [("text", "alle Treffer als Text"), ("text_pin", "nur die festen Stellen"),
                     ("text_suche", "nur die Suchtreffer"), ("count", "Anzahl Treffer")]},
    "kalender": {
        "titel": "Termine holen", "gruppe": "Holen", "id": "termine",
        "beschreibung": "Holt Termine aus dem Outlook-Kalender (so wie in AURA abgeglichen).",
        "felder": [
            {"key": "zeitraum", "label": "Zeitraum", "typ": "auswahl", "optionen": ["heute", "morgen", "naechste_7", "naechste_30", "letzte_7", "letzte_30", "diese_woche"], "standard": "heute"},
            {"key": "max", "label": "Höchstens Termine", "typ": "zahl", "standard": 50}],
        "ergebnis": [("text", "die Termine als Liste"), ("termine", "die Termine einzeln (für «Für jedes»)"),
                     ("kurz", "knapp, fürs Sprachmodell"), ("ueberschneidungen", "Termine, die sich überlappen"), ("count", "Anzahl")]},
    "mails": {
        "titel": "Mails holen", "gruppe": "Holen", "id": "mails",
        "beschreibung": "Holt Mails aus dem Postfach (so wie in AURA abgeglichen), optional passend zu einem Suchbegriff.",
        "felder": [
            {"key": "zeitraum", "label": "Zeitraum", "typ": "auswahl", "optionen": ["heute", "morgen", "naechste_7", "naechste_30", "letzte_7", "letzte_30", "diese_woche"], "standard": "letzte_7"},
            {"key": "suche", "label": "Suchbegriff", "typ": "text", "wert_einfuegen": True,
             "hilfe": "Optional. In «Für jedes» z.B. {{item.titel}} = Betreff des Termins."},
            {"key": "max", "label": "Höchstens Mails", "typ": "zahl", "standard": 10},
            {"key": "filter", "label": "Rauschen weglassen", "typ": "ja_nein", "standard": True,
             "hilfe": "Ohne automatische Antworten, Newsletter und Digests."}],
        "ergebnis": [("text", "die Mails als Liste"), ("kurz", "knapp, fürs Sprachmodell"), ("mails", "die Mails einzeln"), ("count", "Anzahl")]},
    "fuer_jedes": {
        "titel": "Für jedes …", "gruppe": "Verarbeiten", "id": "jedes",
        "beschreibung": "Führt einen Baustein für jedes Element einer Liste aus, z.B. «Mails holen» für jeden Termin.",
        "felder": [
            {"key": "liste", "label": "Liste", "typ": "text", "pflicht": True, "wert_einfuegen": True,
             "hilfe": "z.B. {{termine.termine}}. Im Baustein unten steht das einzelne Element als {{item.…}}."},
            {"key": "schritt", "label": "Baustein je Element", "typ": "json", "pflicht": True,
             "standard": {"type": "mails", "zeitraum": "letzte_7", "suche": "{{item.titel}}", "max": 3},
             "hilfe": "Ein Baustein mit «type» und seinen Feldern (fortgeschritten)."},
            {"key": "max", "label": "Höchstens Elemente", "typ": "zahl", "standard": 20}],
        "ergebnis": [("text", "alle Ergebnisse als Text"), ("ergebnisse", "die Ergebnisse einzeln")]},
    "llm": {
        "titel": "Anweisung ans Sprachmodell", "gruppe": "Verarbeiten", "id": "modell",
        "beschreibung": "Das Sprachmodell liest Text und schreibt eine Antwort – frei oder in festen Feldern.",
        "felder": [
            {"key": "prompt", "label": "Anweisung", "typ": "textarea", "pflicht": True, "wert_einfuegen": True, "hoehe": 140,
             "hilfe": "Was soll das Modell tun? Den zu lesenden Text mit «Wert einfügen» hineinnehmen, z.B. den Text aus «Dateien lesen»."},
            {"key": "fields", "label": "Antwort in Feldern", "typ": "felder",
             "hilfe": "Optional: feste Felder (z.B. «auftragswert», «leistungsart»). Ohne Felder antwortet das Modell frei (Ergebnis «text»)."},
            {"key": "system", "label": "Rolle", "typ": "textarea", "hoehe": 60, "wert_einfuegen": True,
             "hilfe": "Optional: Wer ist das Modell? Z.B. «Du prüfst Beschaffungsunterlagen.»"},
            {"key": "vorspann", "label": "Fester Text davor", "typ": "textarea", "hoehe": 60, "wert_einfuegen": True,
             "hilfe": "Optional: Text, der bei jedem Lauf gleich ist (z.B. Richtlinie). Wird zwischengespeichert – schneller."},
            {"key": "beleg_text", "label": "Belege prüfen gegen", "typ": "text", "wert_einfuegen": True,
             "hilfe": "Nur bei Feldern mit «Beleg»: der Text, in dem die Zitate stehen müssen (meist der Text der Unterlagen)."},
            {"key": "max_new", "label": "Höchstens Wörter-Teile (Tokens)", "typ": "zahl",
             "hilfe": "Nur ohne Felder: Länge der Antwort. 400 ≈ eine halbe Seite."},
            {"key": "temperature", "label": "Kreativität (0 = genau)", "typ": "zahl", "standard": 0}],
        "ergebnis": [("text", "die Antwort (nur ohne Felder)")]},
    "set": {
        "titel": "Werte festlegen", "gruppe": "Verarbeiten", "id": "werte",
        "beschreibung": "Legt feste Werte fest oder setzt Werte zusammen – ohne Sprachmodell.",
        "felder": [
            {"key": "values", "label": "Werte", "typ": "werte", "pflicht": True, "wert_einfuegen": True,
             "hilfe": "Je Zeile «name = wert». Der Wert darf Werte aus früheren Schritten enthalten."}],
        "ergebnis": []},
    "regel": {
        "titel": "Entscheidungstabelle", "gruppe": "Verarbeiten", "id": "entscheid",
        "beschreibung": "Prüft Bedingungen der Reihe nach; die erste zutreffende Regel gilt. Rechnen und Vergleichen gehört hierher.",
        "felder": [
            {"key": "regeln", "label": "Regeln", "typ": "json", "pflicht": True, "standard": [],
             "hilfe": "Liste von {\"name\", \"wenn\", \"dann\": {…}}. Ein eigener Editor folgt; bis dahin hier als JSON."},
            {"key": "sonst", "label": "Sonst", "typ": "json", "standard": {}, "hilfe": "Werte, wenn keine Regel zutrifft."}],
        "ergebnis": [("_regel", "Name der zutreffenden Regel")]},
    "pruefliste": {
        "titel": "Prüfliste", "gruppe": "Verarbeiten", "id": "pl",
        "beschreibung": "Prüft Dokumente gegen Prüfpunkte (Regeln und Fragen). Die Punkte stehen im Reiter «Prüfliste».",
        "felder": [
            {"key": "files", "label": "Zu prüfende Dateien", "typ": "text", "standard": "{{input.files}}", "pflicht": True, "wert_einfuegen": True},
            {"key": "punkte", "label": "Prüfpunkte", "typ": "info", "hilfe": "Im Reiter «Prüfliste» bearbeiten."},
            {"key": "kontext", "label": "Massstab für Fragen", "typ": "text", "wert_einfuegen": True,
             "hilfe": "Optional, z.B. {{wissen.text}}: Das Sprachmodell sieht diesen Text bei jeder Frage als Massstab."}],
        "ergebnis": [("fehler", "Anzahl Fehler"), ("hinweise", "Anzahl Hinweise"), ("ok", "Anzahl erfüllt"),
                     ("nicht_pruefbar", "Anzahl nicht prüfbar")]},
    "word_vorlage": {
        "titel": "Word-Vorlage ausfüllen", "gruppe": "Ausgeben", "id": "word",
        "beschreibung": "Füllt eine Word-Vorlage (Reiter «Vorlage») mit Ergebnissen.",
        "felder": [
            {"key": "vorlage", "label": "Vorlage", "typ": "auswahl", "optionen": "vorlagen", "pflicht": True},
            {"key": "felder", "label": "Zuordnung", "typ": "json", "standard": {}, "wert_einfuegen": True,
             "hilfe": "{\"Feld in der Vorlage\": \"{{schritt.wert}}\"}. Die Feldnamen zeigt der Reiter «Vorlage»."},
            {"key": "name", "label": "Dateiname", "typ": "text", "wert_einfuegen": True},
            {"key": "platzhalter", "label": "Warnen bei Text", "typ": "liste",
             "hilfe": "Texte, die nach dem Ausfüllen nicht mehr im Dokument stehen dürfen, z.B. «Eintrag wählen»."},
            {"key": "open", "label": "Danach öffnen", "typ": "ja_nein", "standard": False}],
        "ergebnis": [("path", "Pfad der Datei"), ("gefuellt", "Anzahl ausgefüllte Felder")]},
    "template": {
        "titel": "Text zusammensetzen", "gruppe": "Ausgeben", "id": "text",
        "beschreibung": "Setzt einen Text aus festen Teilen und Ergebnissen zusammen (z.B. für einen Bericht).",
        "felder": [
            {"key": "text", "label": "Text", "typ": "textarea", "pflicht": True, "wert_einfuegen": True, "hoehe": 160},
            {"key": "html", "label": "Als HTML", "typ": "ja_nein", "standard": False}],
        "ergebnis": [("text", "der fertige Text")]},
    "meldung": {
        "titel": "Anzeige in AURA", "gruppe": "Ausgeben", "id": "meldung",
        "beschreibung": "Zeigt das Ergebnis auf der Startseite unter «Ergebnisse» – auch bei Läufen nach Zeitplan.",
        "felder": [
            {"key": "text", "label": "Text", "typ": "textarea", "pflicht": True, "wert_einfuegen": True},
            {"key": "titel", "label": "Titel", "typ": "text"},
            {"key": "form", "label": "Form", "typ": "auswahl", "optionen": ["stichpunkte", "text", "tabelle"], "standard": "stichpunkte",
             "hilfe": "stichpunkte = Aufzählung · text = Fliesstext · tabelle = Aufzählung plus Tabellen früherer Schritte (Termine, Mails …)."}],
        "ergebnis": []},
    "mail_an_mich": {
        "titel": "Mail an mich", "gruppe": "Ausgeben", "id": "mail",
        "beschreibung": "Legt das Ergebnis als Outlook-Mail an die eigene Adresse an – standardmässig nur als Entwurf.",
        "felder": [
            {"key": "text", "label": "Text", "typ": "textarea", "pflicht": True, "wert_einfuegen": True},
            {"key": "betreff", "label": "Betreff", "typ": "text", "wert_einfuegen": True},
            {"key": "form", "label": "Form", "typ": "auswahl", "optionen": ["stichpunkte", "text", "tabelle"], "standard": "stichpunkte",
             "hilfe": "stichpunkte = Aufzählung · text = Fliesstext · tabelle = Aufzählung plus Tabellen früherer Schritte (Termine, Mails …)."},
            {"key": "senden", "label": "Direkt senden", "typ": "ja_nein", "standard": False,
             "hilfe": "Aus = Entwurf im Ordner «Entwürfe» (empfohlen). Ein = wird sofort an die eigene Adresse gesendet."}],
        "ergebnis": [("an", "Adresse")]},
    "file_out": {
        "titel": "Datei speichern", "gruppe": "Ausgeben", "id": "datei",
        "beschreibung": "Speichert einen Text als Datei im Laufordner.",
        "felder": [
            {"key": "content", "label": "Inhalt", "typ": "textarea", "pflicht": True, "wert_einfuegen": True},
            {"key": "name", "label": "Dateiname (ohne Endung)", "typ": "text", "standard": "ergebnis", "wert_einfuegen": True},
            {"key": "format", "label": "Format", "typ": "auswahl", "optionen": ["txt", "md", "html", "doc", "json"], "standard": "txt"},
            {"key": "open", "label": "Danach öffnen", "typ": "ja_nein", "standard": False}],
        "ergebnis": [("path", "Pfad der Datei")]},
}

GEMEINSAM = [   # für jeden Schritt
    {"key": "label", "label": "Name des Schritts", "typ": "text", "hilfe": "So erscheint der Schritt in der Liste und im Bericht."},
    {"key": "when", "label": "Nur wenn", "typ": "text",
     "hilfe": "Optional: Bedingung ohne {{ }}, z.B. «vw.code == '400'». Leer = immer ausführen."}]

QUELLEN = ["outlook_mail", "outlook_calendar", "edge_history", "folder_docs"]

def titel(typ): return BAUSTEINE.get(typ, {}).get("titel", typ)

def ergebnis(step):
    """[(name, beschreibung)] dessen, was ein Schritt liefert – inkl. eigener Feldnamen."""
    typ = step.get("type"); out = list(BAUSTEINE.get(typ, {}).get("ergebnis", []))
    if typ == "llm" and step.get("fields"):
        out = []
        for f in step["fields"]:
            if not isinstance(f, dict) or not f.get("name") or f.get("vorschlag"): continue
            out.append((f["name"], f.get("label") or f.get("hint", "")[:60]))
            if f.get("zahl"): out.append((f["name"] + "_zahl", "als Zahl"))
    if typ == "set": out = [(k, "") for k in (step.get("values") or {})]
    if typ == "regel":
        ks = {k for r in step.get("regeln") or [] for k in (r.get("dann") or {})} | set(step.get("sonst") or {})
        out = [(k, "") for k in sorted(ks)] + out
    return out
