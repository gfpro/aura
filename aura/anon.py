# aura/anon.py — Anonymisator (Nachbau tiseR anon_module.py 20260908v02). Version 20261021v114
# v114: Excel-Import robust (Namensraum-Praefixe, ElementTree), CSV in ANSI/Windows-1252, Spalten Vorname/Nachname erkannt;
#       Nachname allein: Gross-/Kleinschreibung beachten (Typ «name») und abschaltbar; Hinweise zusammengefasst;
#       reflow(): PDF-Zeilenumbrueche und Silbentrennung fuer Anzeige und Ergebnis zusammenfuegen.
# Markiert schuetzenswerte Stellen; ersetzt wird erst nach Freigabe in der Oberflaeche (anon_gui.py). Nichts wird gespeichert,
# es gibt keine Zuordnungstabelle (nicht umkehrbar). Drei Quellen:
#   1. Strukturmuster  aura\anon_muster.json  (AHV, IBAN, Koordinaten ... mit Pruefziffern; darf ins Repo)
#   2. Begriffsliste   data\anon\begriffe.csv (Namen, Projekte, Standorte ...; NUR lokal, nie in Suche/Prompt/Export)
#   3. Sprachmodell    liefert nur eine LISTE von Namen je Fenster; uebernommen wird nur, was woertlich im Text steht.
import csv, json, re, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from .config import DATA

MUSTER = Path(__file__).with_name("anon_muster.json")
ORDNER = DATA / "anon"
BEGRIFFE = ORDNER / "begriffe.csv"
SPALTEN = ["Begriff", "Typ", "Ersatz", "Kategorie", "Gruppe"]
WINDOW_CHARS, WINDOW_OVER = 2500, 250                              # tiseR: 1400/200 (Browser-Modell); hier mehr Kontext

# Kategorien des gefuehrten Assistenten: (schluessel, titel, ersatz, frage, erklaerung, beispiel)
KATEGORIEN = [
    ("person", "Personen", "[PERSON]", "Welche Namen von Personen sollen nie nach aussen?",
     "Eine Person pro Zeile, z.B. «Sarah Muster». AURA erkennt auch die Outlook-Schreibweise «Muster Sarah» "
     "und den Nachnamen allein.", "Sarah Muster\nPeter Beispiel"),
    ("projekt", "Projekte und Vorhaben", "[PROJEKT]", "Welche Projekt- oder Vorhabennamen sind heikel?",
     "Ein Name pro Zeile. Auch Codenamen und Abkürzungen.", "Nordstern\nPROJEKT-X"),
    ("standort", "Gebäude und Standorte", "[STANDORT]", "Welche Gebäude, Anlagen oder Standorte sollen nicht genannt werden?",
     "Ein Name pro Zeile. Koordinaten (LV95, LV03, WGS84) erkennt AURA bereits selbst – hier nur die Namen.",
     "Anlage Seeblick\nGebäude 7 Thun"),
    ("partner", "Firmen und Partner", "[PARTNER]", "Welche Firmen, Lieferanten oder Partner sind sensibel?",
     "Ein Name pro Zeile, so wie er in Texten vorkommt.", "Muster AG\nBeispiel Systems GmbH"),
    ("system", "Systeme und Kürzel", "[SYSTEM]", "Welche Systemnamen oder internen Kürzel sollen verschwinden?",
     "Ein Begriff pro Zeile. Ab 5 Zeichen wird er auch mitten in Wörtern gefunden (z.B. «ABCDE» in «ABCDE-Server»), "
     "kürzere nur als ganzes Wort.", "SYSNAME\nXYZ-NET"),
]
KAT = {k[0]: k for k in KATEGORIEN}
# Nachnamen, die zugleich gewoehnliche Woerter sind: nie allein ersetzen (tiseR 7.2), nur Vor- + Nachname
NOMEN = {"koch", "bauer", "berger", "fischer", "schneider", "weber", "wagner", "becker", "keller", "graf", "frei", "wolf",
         "fuchs", "vogel", "meister", "könig", "koenig", "kaiser", "richter", "zimmermann", "kaufmann", "schmid", "schmidt",
         "müller", "mueller", "huber", "brunner", "steiner", "frey", "jung", "lang", "klein", "gross", "groß", "kurz", "lehmann",
         "hofmann", "baumann", "maurer", "wyss", "bach", "berg", "stein", "sommer", "winter", "fink", "hahn", "engel", "roth",
         "schwarz", "weiss", "braun", "neumann", "schuster", "schreiber", "wirth", "wirt", "zeller", "moser", "egger", "ammann",
         # v114: Herkunfts- und Alltagswoerter (z.B. «Schweizer Bevölkerung»)
         "schweizer", "berner", "zürcher", "zuercher", "basler", "luzerner", "walliser", "bündner", "glarner", "urner", "deutsch",
         "welsch", "bund", "staub", "ganz", "gut", "rast", "ruf", "hug", "sauter", "pfister", "senn", "probst", "vogt", "marti",
         "schaller", "kessler", "glaser", "wagner", "sigrist", "baur", "landolt", "furrer", "sutter", "stucki", "bürgi", "ernst",
         "heer", "hauser", "berner", "rüegg", "frank", "franz", "martin", "simon", "thomas", "werner", "walter", "peter", "paul"}

# ----------------------------------------------------------------------------- Pruefziffern (tiseR 4.3)
def chk_ean13(s):
    d = re.sub(r"\D", "", s)
    if len(d) != 13: return False
    tot = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(d[:12]))
    return (10 - tot % 10) % 10 == int(d[12])

def chk_iban(s):
    t = re.sub(r"[^A-Za-z0-9]", "", s).upper()
    if not 15 <= len(t) <= 34: return False
    t = t[4:] + t[:4]
    return int("".join(str(ord(c) - 55) if c.isalpha() else c for c in t)) % 97 == 1

def _en(s):
    p = re.split(r"[\s,/]+", s.strip())
    f = lambda x: float(re.sub(r"[^\d.]", "", x.replace("'", "")))
    return f(p[0]), f(p[-1])

def chk_lv95(s):
    try: e, n = _en(s); return 2480000 <= e <= 2840000 and 1070000 <= n <= 1300000
    except (ValueError, IndexError): return False

def chk_lv03(s):
    try: e, n = _en(s); return 480000 <= e <= 840000 and 70000 <= n <= 300000
    except (ValueError, IndexError): return False

CHECKS = {"ean13": chk_ean13, "iban": chk_iban, "lv95": chk_lv95, "lv03": chk_lv03}

# ----------------------------------------------------------------------------- Text
def normalize(t):
    """Zeilenenden \\r\\n/\\r -> \\n (tiseR 7.1). Zeichen ausserhalb der BMP (Emoji) -> \\ufffd, sonst verschieben sich
    die Positionen im Textfeld (Tk zaehlt sie doppelt)."""
    t = (t or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[\U00010000-\U0010FFFF]", "�", t)

# ----------------------------------------------------------------------------- Begriffsliste
def lade_begriffe():
    """Zeilen der Begriffsliste als dicts (Begriff, Typ, Ersatz, Kategorie, Gruppe). Fehlt die Datei: []."""
    if not BEGRIFFE.exists(): return []
    with open(BEGRIFFE, encoding="utf-8-sig", newline="") as f:
        rows = [{k: (r.get(k) or "").strip() for k in SPALTEN} for r in csv.DictReader(f, delimiter=";")]
    return [r for r in rows if r["Begriff"]]

def speichere_begriffe(rows):
    ORDNER.mkdir(parents=True, exist_ok=True)
    tmp = BEGRIFFE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SPALTEN, delimiter=";"); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in SPALTEN})
    tmp.replace(BEGRIFFE)

def zeilen_zu_begriffen(kat, lines, nachname_allein=True):
    """Assistent: Zeilen einer Kategorie -> Begriffs-Zeilen (Typ und Ersatz automatisch). Rueckgabe (rows, hinweise).
    v114: Nachname allein als Typ «name» (Gross-/Kleinschreibung zaehlt) und nur, wenn nachname_allein; Hinweise gesammelt."""
    k = KAT[kat]; rows, seen = [], set()
    kaputt, nomen, einzeln, kurz = [], [], [], []
    def add(begriff, typ, gruppe):
        key = (begriff.lower(), typ)
        if begriff and key not in seen:
            seen.add(key); rows.append({"Begriff": begriff, "Typ": typ, "Ersatz": k[2], "Kategorie": kat, "Gruppe": gruppe})
    for raw in lines:
        g = re.sub(r"\s+", " ", raw).strip(" ;,\t")
        if not g: continue
        if "\ufffd" in g: kaputt.append(g); continue                    # falsch gelesene Umlaute -> nicht verwenden
        if kat == "person":
            teile = g.split(" ")
            add(g, "wort", g)
            if len(teile) >= 2:
                add(" ".join(teile[1:] + teile[:1]), "wort", g)              # «Muster Sarah» (Outlook)
                nach = teile[-1]
                if not nachname_allein: pass
                elif nach.lower() in NOMEN: nomen.append(nach)
                elif len(nach) >= 4: add(nach, "name", g)
                else: kurz.append(nach)
            else: einzeln.append(g)
        elif kat == "system":
            if len(g) >= 5: add(g, "teil", g)
            else: add(g, "wort", g); kurz.append(g)
        else: add(g, "wort", g)
    def liste(xs, n=8):
        xs = sorted(set(xs)); return ", ".join(xs[:n]) + (f" und {len(xs) - n} weitere" if len(xs) > n else "")
    hinweise = []
    if kaputt: hinweise.append(f"{len(kaputt)} Einträge mit unlesbaren Zeichen (�) wurden weggelassen: {liste(kaputt, 5)}. "
                               "Liste bitte erneut übernehmen.")
    if nomen: hinweise.append(f"{len(set(nomen))} Nachnamen sind auch gewöhnliche Wörter ({liste(nomen)}) – sie werden nur "
                              "zusammen mit dem Vornamen ersetzt.")
    if einzeln: hinweise.append(f"{len(set(einzeln))} Personen ohne Vornamen ({liste(einzeln)}) – sie werden als ganzes Wort ersetzt, "
                                "auch wo sie gar keinen Namen meinen. Besser Vor- und Nachname erfassen.")
    if kurz: hinweise.append(f"{len(set(kurz))} sehr kurze Einträge ({liste(kurz)}) werden nur als ganzes Wort gefunden.")
    return rows, hinweise

def gruppen(rows, kat):
    """Fuer den Assistenten: die urspruenglichen Eingabezeilen einer Kategorie (je Gruppe einmal)."""
    out = []
    for r in rows:
        if r["Kategorie"] == kat:
            g = r["Gruppe"] or r["Begriff"]
            if g not in out: out.append(g)
    return out

ERSATZ_KAT = {v[2]: k for k, v in KAT.items()}

def _lesen(p):
    """Textdatei in UTF-8, sonst Windows-1252 (Excel speichert «CSV» meist so) – v114."""
    raw = Path(p).read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try: return raw.decode(enc)
        except UnicodeDecodeError: pass
    return raw.decode("latin-1")

VORNAME = re.compile(r"^(vorname|vornamen|first ?name|given ?name|prénom|prenom|nome)$", re.I)
NACHNAME = re.compile(r"^(nachname|name|familienname|last ?name|surname|family ?name|nom|cognome)$", re.I)
VOLL = re.compile(r"^(anzeigename|display ?name|vollständiger name|vollstaendiger name|person|mitarbeitende?r?|full ?name)$", re.I)

def importiere(path):
    """Datei -> (rows, lines). Tabellen mit Kopf «Begriff» (tiseR: Begriff | Typ | Ersatz, csv oder xlsx Blatt «_anon»)
    werden 1:1 uebernommen (rows). v114: Tabellen mit Spalten Vorname/Nachname (z.B. Admin-Verzeichnis) -> «Vorname Nachname».
    Sonst je Zeile ein Begriff (lines) fuer die aktuelle Seite."""
    p = Path(path); ext = p.suffix.lower()
    if ext == ".xlsx": table = _xlsx(p)
    elif ext in (".csv", ".tsv", ".txt"):
        txt = _lesen(p); first = txt.split("\n", 1)[0]
        d = "\t" if "\t" in first else (";" if ";" in first else ("," if "," in first and ext != ".txt" else None))
        table = [r for r in csv.reader(txt.splitlines(), delimiter=d)] if d else [[l] for l in txt.splitlines()]
    else:
        from .workflow.nodes import read_file
        return [], [l.strip() for l in normalize(read_file(p)).split("\n") if l.strip()]
    table = [[(c or "").strip() for c in r] for r in table if any((c or "").strip() for c in r)]
    if not table: return [], []
    head = [c.lower() for c in table[0]]
    if head[0] == "begriff":
        ix = {n: head.index(n) for n in ("begriff", "typ", "ersatz", "kategorie", "gruppe") if n in head}
        rows = []
        for r in table[1:]:
            get = lambda n: (r[ix[n]] if n in ix and ix[n] < len(r) else "")
            b = get("begriff")
            if not b: continue
            typ = get("typ").lower() or "wort"
            if typ not in ("wort", "teil", "regex", "name"): typ = "wort"
            ers = get("ersatz") or "[BEGRIFF]"
            kat = get("kategorie") or ERSATZ_KAT.get(ers, "eigene")
            rows.append({"Begriff": b, "Typ": typ, "Ersatz": ers, "Kategorie": kat if kat in KAT or kat == "eigene" else "eigene",
                         "Gruppe": get("gruppe") or b})
        return rows, []
    iv = next((i for i, h in enumerate(table[0]) if VORNAME.match(h)), None)
    inn = next((i for i, h in enumerate(table[0]) if NACHNAME.match(h)), None)
    ivo = next((i for i, h in enumerate(table[0]) if VOLL.match(h)), None)
    if iv is not None and inn is not None:
        cell = lambda r, i: r[i] if i < len(r) else ""
        return [], [f"{cell(r, iv)} {cell(r, inn)}".strip() for r in table[1:] if cell(r, inn)]
    if ivo is not None: return [], [r[ivo] for r in table[1:] if ivo < len(r) and r[ivo]]
    return [], [r[0] for r in table if r and r[0]]

def _ln(tag): return tag.rsplit("}", 1)[-1]                         # Element-Name ohne Namensraum

def _xlsx(p):
    """Blatt «_anon» (sonst das erste Blatt) einer .xlsx als Liste von Zeilen – ohne Zusatzbibliothek.
    v114: mit ElementTree, unabhaengig von Namensraum-Praefixen (z.B. «x:» in Exporten aus .NET-Programmen)."""
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        ss = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
                ss.append("".join(t.text or "" for t in si.iter() if _ln(t.tag) == "t"))
        target = None
        try:
            wb = ET.fromstring(z.read("xl/workbook.xml"))
            sheets = [(e.get("name"), next((v for k, v in e.attrib.items() if _ln(k) == "id"), None))
                      for e in wb.iter() if _ln(e.tag) == "sheet"]
            rels = {e.get("Id"): e.get("Target") for e in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).iter()
                    if _ln(e.tag) == "Relationship"}
            rid = next((r for n, r in sheets if n == "_anon"), sheets[0][1] if sheets else None)
            t = (rels.get(rid) or "").lstrip("/")
            if t: target = t if t.startswith("xl/") else "xl/" + t
        except Exception: target = None
        if target not in names:                                        # Rueckfall: erstes Arbeitsblatt im Archiv
            target = next((n for n in sorted(names) if n.startswith("xl/worksheets/") and n.endswith(".xml")), None)
        if not target: raise RuntimeError("keine Tabelle in der Excel-Datei gefunden")
        root = ET.fromstring(z.read(target))
    out = []
    for row in (e for e in root.iter() if _ln(e.tag) == "row"):
        cells = {}
        for c in (e for e in row if _ln(e.tag) == "c"):
            ref = re.match(r"([A-Z]+)", c.get("r") or "")
            col = 0
            for ch in (ref.group(1) if ref else chr(65 + len(cells))): col = col * 26 + ord(ch) - 64
            v = next((e.text for e in c if _ln(e.tag) == "v"), None)
            if c.get("t") == "s" and v is not None: val = ss[int(v)] if int(v) < len(ss) else ""
            elif c.get("t") == "inlineStr": val = "".join(t.text or "" for t in c.iter() if _ln(t.tag) == "t")
            else: val = v or ""
            cells[col - 1] = val
        if cells: out.append([cells.get(i, "") for i in range(max(cells) + 1)])
    return out

# ----------------------------------------------------------------------------- Darstellung (v114)
BULLET = re.compile(r"^\s*([•▪◦·\-–*]|\d{1,2}[.)]|[a-z][.)])\s+")
KOPF = re.compile(r"^\s*(\[Seite \d+\]|Abbildung \d|Tabelle \d|Kapitel \d|\d+(\.\d+)*\s+[A-ZÄÖÜ])")

def reflow(text):
    """PDF-Text lesbar machen: Silbentrennung «Forschungsas -\npekte» -> «Forschungsaspekte», Zeilen eines Absatzes
    zusammenfuegen. Absaetze, Aufzaehlungen, Seitenmarken und Ueberschriften bleiben. Inhalt wird nicht veraendert."""
    lines = text.split("\n")
    lens = sorted(len(l) for l in lines if l.strip())
    voll = lens[int(len(lens) * 0.8)] if lens else 80                # typische volle Zeilenlaenge
    out = []
    for l in lines:
        s = l.rstrip()
        if not out or not s.strip() or not out[-1].strip() or BULLET.match(s) or KOPF.match(s) or KOPF.match(out[-1]):
            out.append(s); continue
        prev = out[-1]
        m = re.search(r"(\w)\s?-$", prev)
        if m and s[:1].islower():                                      # Silbentrennung
            out[-1] = prev[:m.end(1)] + s.lstrip(); continue
        if re.search(r"[.:!?»\"]$", prev) and len(prev) < 0.75 * voll:  # kurze Zeile mit Satzende = Absatzende
            out.append(s); continue
        if len(prev) < 0.5 * voll and not re.search(r"[,;\-–(]$", prev):  # kurze Zeile ohne Fortsetzung = Ueberschrift
            out.append(s); continue
        out[-1] = prev + " " + s.lstrip()
    return "\n".join(out)

# ----------------------------------------------------------------------------- Regeln laden (tiseR 4.1/4.4)
def lade_regeln():
    """Rueckgabe (regeln, warnungen, stats). Fehler nie still: alles in warnungen."""
    rules, warn = [], []; n_m = n_b = 0
    try:
        cat = json.loads(MUSTER.read_text(encoding="utf-8"))
        for m in cat.get("muster", []):
            if not m.get("aktiv", True): continue
            try: rx = re.compile(m["regex"])
            except re.error as e: warn.append(f"Muster «{m.get('name')}»: ungültiger Ausdruck ({e}) – übersprungen"); continue
            chk = m.get("pruefung")
            if chk and chk not in CHECKS: warn.append(f"Muster «{m['name']}»: unbekannte Prüfung «{chk}» – ignoriert"); chk = None
            if m.get("beispiel") and not rx.search(m["beispiel"]):
                warn.append(f"Muster «{m['name']}» erkennt sein eigenes Beispiel nicht – bitte prüfen")
            rules.append({"rx": rx, "chk": chk, "name": m["name"], "ersatz": m.get("ersatz") or "[GESCHWAERZT]",
                          "quelle": "muster", "gruppe": None}); n_m += 1
    except Exception as e:
        warn.append(f"Musterkatalog nicht lesbar ({type(e).__name__}: {e})")
    try: begr = lade_begriffe()
    except Exception as e: begr = []; warn.append(f"Begriffsliste nicht lesbar ({type(e).__name__}: {e})")
    for r in begr:
        b, typ = r["Begriff"], (r["Typ"] or "wort").lower()
        try:
            if typ == "regex": rx = re.compile(b, re.I)
            elif typ == "teil": rx = re.compile(re.escape(b), re.I)
            elif typ == "name": rx = re.compile(r"(?<!\w)" + re.escape(b) + r"(?!\w)")          # v114: Gross/klein zaehlt
            else: rx = re.compile(r"(?<!\w)" + re.escape(b) + r"(?!\w)", re.I)
        except re.error as e: warn.append(f"Begriff «{b}»: ungültiger Ausdruck ({e}) – übersprungen"); continue
        rules.append({"rx": rx, "chk": None, "name": KAT.get(r["Kategorie"], (0, "Begriffsliste"))[1], "ersatz": r["Ersatz"] or "[BEGRIFF]",
                      "quelle": "begriff", "gruppe": (r["Kategorie"] or "eigene") + "|" + (r["Gruppe"] or b).lower()}); n_b += 1
    return rules, warn, {"muster_aktiv": n_m, "begriffe_aktiv": n_b}

# ----------------------------------------------------------------------------- Treffer (tiseR 5.2)
def finde(text, rules):
    raw = []
    for r in rules:
        for m in r["rx"].finditer(text):
            if m.end() <= m.start(): continue
            if r["chk"] and not CHECKS[r["chk"]](m.group(0)): continue
            raw.append({"start": m.start(), "end": m.end(), "text": m.group(0), "muster": r["name"], "ersatz": r["ersatz"],
                        "quelle": r["quelle"], "gruppe": r["gruppe"]})
    return aufloesen(raw)

def aufloesen(raw):
    """Bei Ueberlappung gewinnt der fruehere bzw. laengere Treffer."""
    raw.sort(key=lambda h: (h["start"], -(h["end"] - h["start"])))
    out, last = [], -1
    for h in raw:
        if h["start"] < last: continue
        out.append(h); last = h["end"]
    return out

def frei(hits, s, e):
    return not any(h["start"] < e and s < h["end"] for h in hits)

def alle_vorkommen(text, wort, hits, quelle, ersatz):
    """Alle woertlichen Vorkommen (gleiche Schreibweise, ganze Woerter) als neue Treffer, wo noch frei."""
    neu = []
    for m in re.finditer(r"(?<!\w)" + re.escape(wort) + r"(?!\w)", text):
        if frei(hits + neu, m.start(), m.end()):
            neu.append({"start": m.start(), "end": m.end(), "text": m.group(0), "muster": "Sprachmodell" if quelle == "llm" else "manuell",
                        "ersatz": ersatz, "quelle": quelle, "gruppe": quelle + "|" + wort.lower()})
    return neu

# ----------------------------------------------------------------------------- Sprachmodell (tiseR 5.3 / 6.1)
def fenster(text):
    wins, i, n = [], 0, len(text)
    while i < n:
        j = min(i + WINDOW_CHARS, n)
        if j < n:
            cut = max(text.rfind(". ", i + WINDOW_CHARS // 2, j), text.rfind("\n", i + WINDOW_CHARS // 2, j))
            if cut > i: j = cut + 1
        wins.append({"index": len(wins), "start": i, "text": text[i:j]})
        if j >= n: break
        i = max(j - WINDOW_OVER, i + 1)
    return wins

LLM_SYSTEM = ("Du findest Namen in Texten. Gib AUSSCHLIESSLICH eine Liste zurück: eine Zeile pro Name, genau so geschrieben "
              "wie im Text. Keine Erklärung, keine Nummerierung, keine Wiederholung des Textes. Gibt es keine Namen, schreibe: KEINE")
LLM_VORSPANN = ("Finde im folgenden Textausschnitt alle Namen von Personen (Vor- und/oder Nachnamen) sowie Namen von Firmen "
                "und Organisationen ausserhalb der Bundesverwaltung. Keine Funktionsbezeichnungen, keine Orte, keine Daten.")

def llm_namen(liste_text):
    """Antwort des Modells -> bereinigte Namen (Literal-Pruefung folgt separat)."""
    out = []
    for l in (liste_text or "").split("\n"):
        l = re.sub(r"^\s*(?:[-*•·]|\d+[.)])\s*", "", l).strip(" \t\"«»'.,;:")
        if not l or l.upper() == "KEINE" or len(l) > 60 or len(l) < 3 or ":" in l: continue
        if not any(c.isupper() for c in l): continue
        if l not in out: out.append(l)
    return out

# ----------------------------------------------------------------------------- Ersetzen (tiseR 6.2)
NUMMERIERT = re.compile(r"^\[(PERSON|NAME|PROJEKT|STANDORT|PARTNER|SYSTEM|BEGRIFF)\]$")

def ersetzen(text, hits):
    """Literal, von hinten nach vorne. Gleiche Gruppe = gleicher Platzhalter: [PERSON_1], [PERSON_2] ...
    (nur innerhalb dieses Textes; es wird keine Zuordnung gespeichert)."""
    on = sorted([h for h in hits if h.get("an", True)], key=lambda h: h["start"])
    nr, zaehler, ers = {}, {}, {}
    for h in on:
        m = NUMMERIERT.match(h["ersatz"])
        if not m: ers[id(h)] = h["ersatz"]; continue
        key = (m.group(1), h.get("gruppe") or h["text"].lower())
        if key not in nr: zaehler[m.group(1)] = zaehler.get(m.group(1), 0) + 1; nr[key] = zaehler[m.group(1)]
        ers[id(h)] = f"[{m.group(1)}_{nr[key]}]"
    for h in sorted(on, key=lambda h: h["start"], reverse=True):
        text = text[:h["start"]] + ers[id(h)] + text[h["end"]:]
    return text, len(on)
