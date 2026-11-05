# aura/graph.py — Metadaten-Graph (Zusammenhänge). Version 20261105v207
# Rein deterministisch, ohne Sprachmodell: liest nur Metadaten aus aura.db (nur lesend) und schreibt data\graph.db.
# graph.db ist jederzeit ersetzbar. Nur abfolge_items() wirkt auf den Chat, und nur mit Schalter «graph_suche».
# Kanten: schrieb, empfing, organisierte, nahm_teil, bearbeitete (Person ↔ Objekt),
#         gleiche_konversation, gleicher_titel, zeitlich_nah (Objekt ↔ Objekt).
import json, os, re, sqlite3, threading, time
from collections import defaultdict
from datetime import date, timedelta
from .config import DATA, DB_PATH

GRAPH_PATH = DATA / "graph.db"
MAIL, TERMIN, NOTIZ = "outlook_mail", "outlook_calendar", "onenote"
PERSON_QUELLEN = {MAIL: ("schrieb", "empfing"), TERMIN: ("organisierte", "nahm_teil"), NOTIZ: ("bearbeitete", None),
                  "confluence": ("bearbeitete", None), "folder_docs": ("erstellte", None)}   # v201, v206
ART_TEXT = {"schrieb": "schrieb", "empfing": "empfing", "organisierte": "organisierte", "nahm_teil": "nahm teil", "empfing_cc": "empfing in CC", "optional": "optional eingeladen",
            "bearbeitete": "bearbeitete", "erstellte": "erstellte", "gleiche_seite": "gleiche Seite (besucht)", "gleiche_konversation": "gleiche Konversation",
            "gleicher_titel": "gleicher Titel", "zeitlich_nah": "ähnlicher Titel, zeitlich nah"}
MAX_WORT_DF, MAX_NAH_JE_OBJEKT, NAH_TAGE, TITEL_TAGE = 30, 5, 14, 30
RANDLIMIT_PERSON = 40                       # Personen mit mehr Kanten werden in Stufe 2 nicht weiter aufgeklappt
STOP = set("aber alle auch beim damit dass dein diese einer eines heute nicht noch oder sich sind unsere wegen werden wird zwischen "
           "avec dans pour sont votre about from have that this with your meeting termin sitzung besprechung einladung".split())
PRE = re.compile(r"^\s*((aw|wg|re|fw|fwd|antw|weiterl|tr|rv|i|r)\s*:\s*)+", re.I)

def titel_norm(t): return re.sub(r"\s+", " ", PRE.sub("", (t or "").lower())).strip(" .")

def tag(ts):
    try: return date.fromisoformat((ts or "")[:10])
    except ValueError: return None

def person_key(n):
    if " " not in n.strip() and "." in n and "@" not in n: n = n.replace(".", " ")   # v195: gregor.stoeckli
    n = re.sub(r"<[^>]*>|\([^)]*\)|[\"']", " ", n or "").replace(",", " ")
    teile = sorted(x for x in n.lower().split() if "@" not in x and len(x) > 1)
    return " ".join(teile)

def zusammenfassen(pers):
    """v195: «Gian Franco Prozzillo» und «Prozzillo Gian Franco ARMASUISSE» sind eine Person, wenn die kürzere Form
    mindestens zwei Wörter hat und nur in genau einer längeren Form vorkommt. Liefert {alter Schlüssel: neuer Schlüssel}."""
    wort, teile = defaultdict(set), {k: set(k.split()) for k in pers}
    for k, t in teile.items():
        for w in t: wort[w].add(k)
    zu = {}
    for k, t in teile.items():
        if len(t) < 2: continue
        obere = set.intersection(*(wort[w] for w in t)) - {k}
        lang = [o for o in obere if not any(teile[o] < teile[x] for x in obere)]    # nur die vollständigste Form
        if len(lang) == 1: zu[k] = lang[0]
    return zu

def personen(text):
    out = {}
    for n in re.split(r"[;\r\n]+", text or ""):
        n = re.sub(r"\s+", " ", re.sub(r"<[^>]*>|[\"']", " ", n)).strip()
        k = person_key(n)
        if k and n: out.setdefault(k, n)
    return out

def woerter(t): return {w for w in re.findall(r"[^\W\d_]{5,}", titel_norm(t)) if w not in STOP}

def _stempel(c):
    return "|".join(str(x) for x in c.execute("SELECT count(*), max(id), max(ts), sum(length(meta)) FROM items").fetchone())

def aktuell():
    """True, wenn graph.db zum heutigen Stand von aura.db passt."""
    if not GRAPH_PATH.exists() or not DB_PATH.exists(): return False
    a, g = sqlite3.connect(DB_PATH, timeout=5), sqlite3.connect(GRAPH_PATH, timeout=5)
    try: return g.execute("SELECT v FROM info WHERE k='stempel'").fetchone()[0] == _stempel(a)
    except (sqlite3.Error, TypeError): return False
    finally: a.close(); g.close()

_sperre = threading.Lock()                                           # v202: nur ein Aufbau gleichzeitig

def aufbauen(db_path=None, ziel=None):
    """Baut den Graphen neu und ersetzt graph.db erst am Schluss. Liefert (Knoten, Kanten)."""
    with _sperre:
        ziel = ziel or GRAPH_PATH; tmp = f"{ziel}.{os.getpid()}.neu"
        try:
            if os.path.exists(tmp): os.remove(tmp)
            return _aufbauen(db_path, ziel, tmp)
        finally:
            if os.path.exists(tmp): os.remove(tmp)

def _aufbauen(db_path, ziel, tmp):
    a = sqlite3.connect(db_path or DB_PATH, timeout=30)
    rows = a.execute("SELECT id, source, title, author, recipients, ts, meta FROM items").fetchall()
    stempel = _stempel(a); a.close()
    knoten, kanten, pers = [], set(), {}
    tage, gruppen, titelg, wort = {}, defaultdict(list), defaultdict(list), defaultdict(set)
    quelle, titel_von = {}, {}
    cf_id, cf_titel, edge = {}, {}, []                               # v207: Edge-Besuche ↔ Confluence-Seiten
    adresse = defaultdict(set)                                       # v201: gleiche Absenderadresse = gleiche Person
    for iid, src, titel, autor, empf, ts, meta in rows:
        nid = f"i{iid}"; knoten.append((nid, src, titel or "(ohne Titel)", ts or "", iid))
        tage[nid] = tag(ts); quelle[nid] = src; titel_von[nid] = titel or ""
        if src in PERSON_QUELLEN:
            a1, a2 = PERSON_QUELLEN[src]
            for k, n in personen(autor).items(): pers.setdefault(k, n); kanten.add((f"p{k}", nid, a1))
            if a2:
                try: mt = json.loads(meta or "{}")
                except ValueError: mt = {}
                if "to" in mt:                                       # v203: To/CC bzw. Pflicht/optional mit Adresse
                    for art, l in ((a2, mt["to"]), ("empfing_cc" if src == MAIL else "optional", mt.get("cc") or [])):
                        for e in l:
                            k = person_key(e.get("n", ""))
                            if not k: continue
                            pers.setdefault(k, e["n"]); kanten.add((nid, f"p{k}", art))
                            if e.get("a"): adresse[e["a"]].add(k)
                else:
                    for k, n in personen(empf).items(): pers.setdefault(k, n); kanten.add((nid, f"p{k}", a2))
        if src == "edge_history":
            try: edge.append((nid, json.loads(meta or "{}").get("url") or "", titel or ""))
            except ValueError: pass
        if src == "confluence":
            try: pid = str(json.loads(meta or "{}").get("page_id") or "")
            except ValueError: pid = ""
            if pid: cf_id[pid] = nid
            cf_titel[titel_norm(titel)] = nid
        if src == "confluence":                                      # v206: Ersteller der Seite
            try: von = json.loads(meta or "{}").get("erstellt_von")
            except ValueError: von = ""
            for k, n in personen(von).items(): pers.setdefault(k, n); kanten.add((f"p{k}", nid, "erstellte"))
        if src == MAIL:
            try: kid = json.loads(meta or "{}").get("conversation_id")
            except ValueError: kid = ""
            if kid: gruppen[kid].append(nid)
            try: ad = (json.loads(meta or "{}").get("sender_addr") or "").strip().lower()
            except ValueError: ad = ""
            if "@" in ad: adresse[ad].update(personen(autor))
        if src in (MAIL, TERMIN) and titel_norm(titel): titelg[titel_norm(titel)].append(nid)
        for w in woerter(titel): wort[w].add(nid)
    for nid, url, titel in edge:
        m = re.search(r"(?:pageId=|/pages/)(\d+)", url)
        z = cf_id.get(m.group(1)) if m else None
        if not z and re.search(r"\s-\sConfluence\s*$", titel):
            t = re.sub(r"^\W+", "", re.sub(r"\s-\sConfluence\s*$", "", titel))
            z = cf_titel.get(titel_norm(t)) or cf_titel.get(titel_norm(t.rsplit(" - ", 1)[0]))
        if z: kanten.add((nid, z, "gleiche_seite"))
    zeit = lambda n: tage[n] or date.min
    for g in gruppen.values():
        g.sort(key=zeit)
        kanten.update((x, y, "gleiche_konversation") for x, y in zip(g, g[1:]))
    for g in titelg.values():
        mails = [n for n in g if quelle[n] == MAIL and tage[n]]
        for t in (n for n in g if quelle[n] == TERMIN and tage[n]):
            m = min(mails, key=lambda n: abs((tage[n] - tage[t]).days), default=None)
            if m and abs((tage[m] - tage[t]).days) <= TITEL_TAGE: kanten.add((m, t, "gleicher_titel"))
    paare = defaultdict(int)
    for g in wort.values():
        if 2 <= len(g) <= MAX_WORT_DF:
            s = sorted(g)
            for i, x in enumerate(s):
                for y in s[i + 1:]:
                    if quelle[x] != quelle[y] and tage[x] and tage[y] and abs((tage[x] - tage[y]).days) <= NAH_TAGE:
                        paare[(x, y)] += 1
    je = defaultdict(list)
    for (x, y), n in paare.items():
        if n >= 2:
            d = abs((tage[x] - tage[y]).days); je[x].append((-n, d, y)); je[y].append((-n, d, x))
    for x, l in je.items():
        for _, _, y in sorted(l)[:MAX_NAH_JE_OBJEKT]: kanten.add((min(x, y), max(x, y), "zeitlich_nah"))
    zu = zusammenfassen(pers)
    for ks in adresse.values():                                      # v201: Adresse ist sicherer als der Namensvergleich
        ks = sorted((k for k in ks if k in pers), key=len, reverse=True)
        for k in ks[1:]: zu[k] = ks[0]
        if len(ks) > 1: zu.pop(ks[0], None)
    try:                                                             # v198: Personen aus dem Glossar gelten sicher
        from . import glossar
        for e in glossar.laden():
            if e.get("typ", "").lower() != "person": continue
            t = set(person_key(e["bedeutung"]).split())
            gl = sorted((k for k in pers if len(t) >= 2 and t <= set(k.split())), key=len, reverse=True)
            for k in gl[1:]: zu[k] = gl[0]
            if gl: zu.pop(gl[0], None)
    except Exception: pass
    for k in list(zu):                                               # v201: Ketten a -> b -> c auflösen
        seen = {k}
        while zu[k] in zu and zu[k] not in seen: seen.add(zu[k]); zu[k] = zu[zu[k]]
    zu = {k: v for k, v in zu.items() if k != v}
    for k, haupt in zu.items():                                      # v195: kürzester Name wird angezeigt
        if len(pers[k]) < len(pers[haupt]): pers[haupt] = pers[k]
    um = lambda n: f"p{zu[n[1:]]}" if n.startswith("p") and n[1:] in zu else n
    kanten = {(um(a), um(b), art) for a, b, art in kanten}
    knoten += [(f"p{k}", "person", n, "", None) for k, n in pers.items() if k not in zu]
    g = sqlite3.connect(tmp)
    g.executescript("""CREATE TABLE knoten(id TEXT PRIMARY KEY, typ TEXT, titel TEXT, ts TEXT, item_id INTEGER);
        CREATE TABLE kanten(von TEXT, nach TEXT, art TEXT, PRIMARY KEY(von, nach, art)) WITHOUT ROWID;
        CREATE INDEX ix_nach ON kanten(nach); CREATE INDEX ix_typ ON knoten(typ);
        CREATE TABLE info(k TEXT PRIMARY KEY, v TEXT);""")
    g.executemany("INSERT INTO knoten VALUES(?,?,?,?,?)", knoten)
    g.executemany("INSERT INTO kanten VALUES(?,?,?)", sorted(kanten))
    g.execute("INSERT INTO info VALUES('stempel', ?)", (stempel,)); g.commit(); g.close()
    os.replace(tmp, ziel)
    return len(knoten), len(kanten)

def nachfuehren():
    """v200: Baut den Graphen neu, wenn er nicht zur Datenbank passt. Fehler bleiben ohne Folgen für den Chat."""
    try:
        if not aktuell(): aufbauen()
    except (OSError, sqlite3.Error): pass

def _lesen(pfad=None):
    """v191: Nur lesend öffnen. Eine fehlende Datei gibt einen Fehler, statt eine leere graph.db anzulegen."""
    return sqlite3.connect(f"file:{pfad or GRAPH_PATH}?mode=ro", uri=True, timeout=5)

def suchen(text, quellen=None, limit=40, pfad=None):
    """Sucht Personen und Objekte über den Titel. Personen zuerst, dann die neuesten Objekte."""
    c = _lesen(pfad)
    try:
        args = [f"%{text.strip()}%"]; f = ""
        if quellen is not None:
            f = f" AND typ IN ({','.join('?' * (len(quellen) + 1))})"; args += ["person", *quellen]
        r = c.execute(f"SELECT id, typ, titel, ts, item_id FROM knoten WHERE titel LIKE ?{f} "   # v207: Edge zuletzt, Titel nur einmal
                      "ORDER BY typ <> 'person', typ = 'edge_history', ts DESC LIMIT ?", (*args, limit * 10)).fetchall()
        out, seen = [], set()
        for x in r:
            k = (x[1] == "edge_history", titel_norm(x[2]))
            if k not in seen: seen.add(k); out.append(dict(zip(("id", "typ", "titel", "ts", "item_id"), x)))
        return out[:limit]
    finally: c.close()

def umgebung(start, tiefe=1, quellen=None, tage=None, max_nachbarn=24, max_zweit=6, pfad=None):
    """Liefert (knoten, kanten) um einen Startknoten. Der Start bleibt immer sichtbar; Filter gelten für die Nachbarn."""
    c = _lesen(pfad); grenze = (date.today() - timedelta(days=tage)).isoformat() if tage else ""
    def k(i):
        r = c.execute("SELECT id, typ, titel, ts, item_id FROM knoten WHERE id=?", (i,)).fetchone()
        return dict(zip(("id", "typ", "titel", "ts", "item_id"), r)) if r else None
    def nachbarn(i):
        rows = c.execute("SELECT nach, art, 1 FROM kanten WHERE von=? UNION ALL SELECT von, art, 0 FROM kanten WHERE nach=?", (i, i)).fetchall()
        return rows
    def erlaubt(n):
        if n["typ"] == "person": return True
        return (quellen is None or n["typ"] in quellen) and (not grenze or (n["ts"] or "")[:10] >= grenze)
    try:
        s = k(start)
        if not s: return {}, []
        knoten, kanten, rand = {start: dict(s, stufe=0)}, set(), [start]
        for stufe in (1, 2)[:max(1, min(2, tiefe))]:
            neu = []
            for i in rand:
                rows = nachbarn(i)
                if stufe == 2 and knoten[i]["typ"] == "person" and len(rows) > RANDLIMIT_PERSON: continue
                kand = [(k(n), n, art, vor) for n, art, vor in rows]
                kand = [x for x in kand if x[0] and erlaubt(x[0])]
                kand.sort(key=lambda x: (x[0]["typ"] != "person", x[0]["ts"] or ""), reverse=False)
                pers = [x for x in kand if x[0]["typ"] == "person"]
                heute = date.today().isoformat() + " 99"                 # v195: Vergangenes zuerst, sonst nur Serien der Zukunft
                obj = [x for x in kand if x[0]["typ"] != "person"]
                alt = sorted((x for x in obj if (x[0]["ts"] or "") <= heute), key=lambda x: x[0]["ts"] or "", reverse=True)
                obj = alt + sorted((x for x in obj if (x[0]["ts"] or "") > heute), key=lambda x: x[0]["ts"])
                limit = max_nachbarn if stufe == 1 else max_zweit
                halb = max(limit // 2, limit - len(obj))
                for n, nid, art, vor in pers[:halb] + obj[:limit - min(len(pers), halb)]:
                    if nid not in knoten: knoten[nid] = dict(n, stufe=stufe); neu.append(nid)
                    kanten.add((i, nid, art) if vor else (nid, i, art))
            rand = neu
        return knoten, sorted(kanten)
    finally: c.close()

# ---- v190: Abfolgefragen («Welcher Termin folgte nach der Mail von X?»)
ABFOLGE = re.compile(r"\b(folgte|gefolgt|fand\b.{0,12}\bnach|nach\s+(dem|der|den|diesem|dieser)\b.{0,40}\b(e-?mail|mail|nachricht)\w*|danach|daraufhin|im\s+anschluss)", re.I)
TERMINWORT = re.compile(r"\b(termin|sitzung|besprechung|meeting|treffen)\w*", re.I)
TEIL = r"(?:da|de|di|del|dos|van|von|der)"                      # v193: klein geschriebene Namensteile
GROSS = r"[A-ZÄÖÜ][\w'’-]+"
NAME = re.compile(rf"\b(?:von|mit|an)\s+(?:herrn?\s+|frau\s+)?({GROSS}(?:\s+(?:{TEIL}\s+)*{GROSS})?)")
DATUM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
MAX_TAGE, MAX_FOLGE = 60, 3

def ist_abfolge(frage): return bool(ABFOLGE.search(frage) and TERMINWORT.search(frage) and NAME.search(frage))

def _personen(c, name):
    """v193: Alle Wörter müssen als ganze Wörter passen. Sonst ohne das letzte Wort («Benito Termin»)."""
    w = [x for x in re.findall(r"[^\W_]+", name.lower()) if len(x) > 1]
    alle = [(r[0], set(r[0][1:].split())) for r in c.execute("SELECT id FROM knoten WHERE typ='person'")]
    while w:
        t = [i for i, teile in alle if set(w) <= teile]
        if t: return t
        w = w[:-1]
    return []

def abfolge(frage, pfad=None):
    """Liefert None (Regel greift nicht), {"ids": [Mail, Termine...]} oder {"mail": id, "ts": Datum, "ids": []} ohne Folgetermin.
    Deterministisch. Mit Datum gelten die Mails dieses Tags, ohne Datum nur die neueste Mail der Person."""
    if not ist_abfolge(frage): return None
    d = DATUM.search(frage); datum = f"{d[3]}-{int(d[2]):02d}-{int(d[1]):02d}" if d else ""
    try: c = _lesen(pfad)
    except sqlite3.Error: return None
    try:
        pers = set()
        for name in NAME.findall(frage):
            try:                                                     # v204: «Mail von BRF» über das Glossar
                from . import glossar
                e = next((x for x in glossar.laden() if x["begriff"] == name and x.get("typ", "").lower() == "person"), None)
            except Exception: e = None
            pers.update(_personen(c, e["bedeutung"] if e else name))
        if not pers or len(pers) > 5: return None
        marks = ",".join("?" * len(pers)); p = tuple(pers)
        rows = c.execute(f"""SELECT k.item_id, k.typ, k.ts FROM kanten e JOIN knoten k ON k.id = e.nach WHERE e.von IN ({marks})
            UNION SELECT k.item_id, k.typ, k.ts FROM kanten e JOIN knoten k ON k.id = e.von WHERE e.nach IN ({marks})""", p + p).fetchall()
        jetzt = time.strftime("%Y-%m-%d %H:%M")
        mails = sorted((r for r in rows if r[1] == MAIL and r[2] and r[2] <= jetzt and r[2].startswith(datum)), key=lambda r: r[2], reverse=True)
        if not mails: return None                                    # keine passende Mail: normale Suche
        termine = sorted((r for r in rows if r[1] == TERMIN and r[2]), key=lambda r: r[2])
        for m in mails if datum else mails[:1]:
            bis = (tag(m[2]) or date.min) + timedelta(days=MAX_TAGE)
            t = next((x for x in termine if x[2] > m[2] and (tag(x[2]) or date.max) <= bis), None)
            if t:
                gleich = [x[0] for x in termine if x[2] > m[2] and x[2][:10] == t[2][:10]]
                return {"ids": [m[0]] + gleich[:MAX_FOLGE]}
        return {"ids": [], "mail": mails[0][0], "ts": mails[0][2][:10]}
    except sqlite3.Error: return None
    finally: c.close()

def abfolge_items(frage, pfad=None):
    r = abfolge(frage, pfad)
    return r["ids"] if r else []


def _datum(ts):
    d = tag(ts)
    return (d.strftime("%d.%m.%Y") + (f", {ts[11:16]}" if len(ts) >= 16 else "")) if d else ts

def beschreiben(ids, pfad=None):
    """v205: Antwort auf eine Abfolgefrage direkt aus dem Graphen, ohne Sprachmodell. ids = [Mail, Termin, ...].
    Liefert (Text, Quellen)."""
    c = _lesen(pfad)
    try:
        qs, zeilen = [], []
        for n, iid in enumerate(ids):
            r = c.execute("SELECT id, typ, titel, ts FROM knoten WHERE item_id=?", (iid,)).fetchone()
            if not r: continue
            qs.append({"item_id": iid, "chunk_id": None, "source": r[1], "title": r[2], "ts": r[3], "author": "", "text": ""})
            if n == 0: zeilen.append(f"Nach der Mail «{r[2]}» vom {_datum(r[3])[:10]} folgte zeitlich:"); continue
            leute = [x[0] for x in c.execute("""SELECT DISTINCT k.titel FROM kanten e JOIN knoten k ON k.id IN (e.von, e.nach)
                WHERE (e.von=? OR e.nach=?) AND e.art IN ('organisierte', 'nahm_teil', 'optional') AND k.typ='person' ORDER BY k.titel""", (r[0], r[0]))]
            zeilen.append(f"• {_datum(r[3])} – {r[2]}")
            if leute: zeilen.append(f"  Teilnehmende: {', '.join(leute)}")
        if len(ids) > 2: zeilen.append("Am selben Tag folgten mehrere Termine.")
        zeilen.append("Ein inhaltlicher Bezug zur Mail ist damit nicht belegt.")
        return "\n".join(zeilen), qs
    finally: c.close()
