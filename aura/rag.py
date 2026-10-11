# aura/rag.py — hybride Suche: BM25 (SQLite FTS5) + Vektoren (e5), kombiniert per Reciprocal Rank Fusion.
import operator, re
from datetime import date, timedelta
from array import array

RRF_K = 60

def _mo(d): return d - timedelta(d.weekday())
def _eom(d): return (d.replace(day=28) + timedelta(4)).replace(day=1) - timedelta(1)

class Retriever:
    def __init__(self):
        self.ids, self.mat, self.H = [], None, 1024      # Vektor-Cache (alle Chunks mit Vektor)

    def invalidate(self): self.mat = None

    def _load(self, conn):
        ids, mat = [], array("f"); self.pos = {}
        for cid, blob in conn.execute("SELECT id, vec FROM chunks WHERE vec IS NOT NULL ORDER BY id"):
            ids.append(cid); mat.frombytes(blob)
        self.ids, self.mat = ids, mat; self.pos = {c: i for i, c in enumerate(ids)}
        if ids: self.H = len(mat) // len(ids)

    # Frage-Typ -> Textstellen, die innerhalb einer gefundenen Mail bevorzugt werden (statt nur des aehnlichsten Stuecks)
    _MON = "januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember"
    FACETS = [(r"\bfrist\w*|\bdeadline\w*|\bbis wann\b|\bstichtag\w*|\btermin(e|lich)?\b.*\b(abgabe|eingabe|antwort)",
               r"spätestens|spaetestens|\bfrist|deadline|stichtag|\bbis (zum |am |spätestens )?\d{1,2}\.\s?(\d{1,2}\.|" + _MON + ")"
               r"|\bab dem \d{1,2}\.")]

    def facet(self, question):
        q = question.lower()
        for qrx, crx in self.FACETS:
            if re.search(qrx, q): return re.compile(crx, re.I)
        return None

    def bm25(self, conn, query, n=50, items=None):
        terms = re.findall(r"\w+", query.lower())
        if not terms: return []
        q = " OR ".join('"%s"' % t for t in terms)
        if items is None:
            return [r[0] for r in conn.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?", (q, n))]
        inl = ",".join(str(int(i)) for i in items)
        return [r[0] for r in conn.execute(
            f"SELECT f.rowid FROM chunks_fts f JOIN chunks c ON c.id = f.rowid WHERE chunks_fts MATCH ? "
            f"AND c.item_id IN ({inl}) ORDER BY bm25(chunks_fts) LIMIT ?", (q, n))]

    def vector(self, conn, qvec, n=50, items=None):
        if self.mat is None: self._load(conn)
        if not self.ids or qvec is None: return []
        H, mv = self.H, memoryview(self.mat)
        if items is None: idx = range(len(self.ids))
        else:
            inl = ",".join(str(int(i)) for i in items)
            idx = [self.pos[c] for (c,) in conn.execute(f"SELECT id FROM chunks WHERE item_id IN ({inl})") if c in self.pos]
        sc = {i: sum(map(operator.mul, qvec, mv[i * H:(i + 1) * H])) for i in idx}
        return [self.ids[i] for i in sorted(sc, key=sc.get, reverse=True)[:n]]

    STOP = {"welche", "welcher", "mails", "mail", "hast", "habe", "haben", "von", "der", "die", "das", "und", "mir",
            "mich", "geschrieben", "zuletzt", "was", "wer", "wie", "wann", "ist", "sind", "eine", "einen", "zum", "zur",
            "thema", "alle", "nachrichten", "gesendet", "bekommen", "erhalten", "dem", "den", "des", "ich", "du"}

    def author_items(self, conn, question):
        """Erkennt Personennamen in der Frage (Absender/Organisator). Liefert passende item-IDs oder None."""
        names = []
        for w in re.findall(r"[^\W\d_]{3,}", question):
            if w.lower() in self.STOP: continue
            n = conn.execute("SELECT COUNT(DISTINCT author) FROM items WHERE author LIKE ?", (f"%{w}%",)).fetchone()[0]
            if 1 <= n <= 20: names.append(w)
        if not names: return None
        sql = " AND ".join("author LIKE ?" for _ in names)
        ids = [r[0] for r in conn.execute(f"SELECT id FROM items WHERE {sql} ORDER BY ts DESC LIMIT 500",
                                           [f"%{w}%" for w in names])]
        return (ids, names) if ids else None

    # ---------------------------------------------------------------- Zeit- und Absicht-Erkennung
    TIME = [  # (Muster, Funktion heute -> (von, bis inkl.), Bezeichnung)
        (r"\bübermorgen\b|\buebermorgen\b", lambda d: (d + timedelta(2), d + timedelta(2)), "übermorgen"),
        (r"\bheute\b", lambda d: (d, d), "heute"),
        (r"\bgestern\b", lambda d: (d - timedelta(1), d - timedelta(1)), "gestern"),
        (r"\bmorgen\b", lambda d: (d + timedelta(1), d + timedelta(1)), "morgen"),
        (r"\b(nächste[nrm]?|naechste[nrm]?|kommende[nrm]?) woche\b", lambda d: (_mo(d) + timedelta(7), _mo(d) + timedelta(13)), "nächste Woche"),
        (r"\b(letzte[nrm]?|vergangene[nrm]?|vorige[nrm]?) woche\b", lambda d: (_mo(d) - timedelta(7), _mo(d) - timedelta(1)), "letzte Woche"),
        (r"\b(diese[nrm]?|aktuelle[nrm]?) woche\b|\bdie woche\b", lambda d: (_mo(d), _mo(d) + timedelta(6)), "diese Woche"),
        (r"\b(diese[nrm]?|aktuelle[nrm]?) monat\b", lambda d: (d.replace(day=1), _eom(d)), "diesen Monat"),
    ]
    RECENT = r"\b(letzte[snmr]?|neueste[snmr]?|jüngste[snmr]?|aktuellste[snmr]?|zuletzt)\b"
    CAL = r"\b(termin\w*|kalender\w*|sitzung\w*|meeting\w*|besprechung\w*|agenda)\b"

    def intent(self, conn, question, today=None):
        """Erkennt Zeitraum, 'neueste zuerst' und Termin-Fragen. Liefert dict oder None."""
        q = question.lower(); d = today or date.today(); out = {}
        for rx, fn, label in self.TIME:
            m = re.search(rx, q)
            if m:
                a, b = fn(d); out["range"] = (a.isoformat(), (b + timedelta(1)).isoformat(), label)
                q = q[:m.start()] + q[m.end():]; break
        if re.search(self.RECENT, q): out["recent"] = True
        if re.search(self.CAL, q): out["source"] = "outlook_calendar"
        return out or None

    def filter_items(self, conn, intent, items=None, limit=2000):
        """Objekt-IDs passend zu Zeitraum/Quelle (und optional Vorauswahl items)."""
        where, args = [], []
        if intent.get("range"): where.append("ts >= ? AND ts < ?"); args += intent["range"][:2]
        if intent.get("source"): where.append("source = ?"); args.append(intent["source"])
        if items is not None: where.append("id IN (%s)" % ",".join(str(int(i)) for i in items) if items else "0")
        if not where: return items
        order = "ts DESC" if intent.get("recent") or not intent.get("range") else "ts ASC"
        return [r[0] for r in conn.execute(f"SELECT id FROM items WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ?",
                                           args + [limit])]

    def item_hits(self, conn, items, k):
        """Erstes Textstueck je Objekt, in der Reihenfolge von items."""
        hits = []
        for iid in items[:k]:
            r = conn.execute("SELECT c.id, c.text, i.id, i.source, i.title, i.ts, i.author FROM chunks c JOIN items i "
                             "ON i.id = c.item_id WHERE c.item_id = ? ORDER BY c.ord LIMIT 1", (iid,)).fetchone()
            if r: hits.append({"chunk_id": r[0], "text": r[1], "item_id": r[2], "source": r[3], "title": r[4] or "",
                               "ts": r[5] or "", "author": r[6] or "", "score": 0.0})
        return hits

    def search(self, conn, query, qvec=None, k=6, mode="hybrid", per_item=1, items=None, prefer=None):
        """mode: bm25 | vector | hybrid. items = nur in diesen Objekten suchen (z.B. Absender-Filter).
        Liefert Treffer-Dicts, pro Objekt hoechstens per_item Stuecke."""
        lists = []
        if mode in ("bm25", "hybrid"): lists.append(self.bm25(conn, query, items=items))
        if mode in ("vector", "hybrid"): lists.append(self.vector(conn, qvec, items=items))
        if items and not any(lists):                   # nichts Passendes: die neuesten Objekte dieser Person
            inl = ",".join(str(int(i)) for i in items[:k])
            lists.append([r[0] for r in conn.execute(f"SELECT c.id FROM chunks c JOIN items i ON i.id = c.item_id "
                                                     f"WHERE c.item_id IN ({inl}) AND c.ord = 0 ORDER BY i.ts DESC")])
        score = {}
        for lst in lists:
            for rank, cid in enumerate(lst): score[cid] = score.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        hits, per = [], {}
        for cid in sorted(score, key=score.get, reverse=True):
            r = conn.execute("SELECT c.text, i.id, i.source, i.title, i.ts, i.author FROM chunks c "
                             "JOIN items i ON i.id = c.item_id WHERE c.id = ?", (cid,)).fetchone()
            if not r or per.get(r[1], 0) >= per_item: continue
            per[r[1]] = per.get(r[1], 0) + 1
            hits.append({"chunk_id": cid, "text": r[0], "item_id": r[1], "source": r[2], "title": r[3] or "",
                         "ts": r[4] or "", "author": r[5] or "", "score": score[cid]})
            if len(hits) >= k: break
        if prefer:                                     # z.B. Frist-Frage: Stelle mit Datum/«spätestens» derselben Mail nehmen
            for h in hits:
                if prefer.search(h["text"]): continue
                for cid, text in conn.execute("SELECT id, text FROM chunks WHERE item_id = ? ORDER BY ord", (h["item_id"],)):
                    if prefer.search(text): h["chunk_id"], h["text"] = cid, text; break
        return hits
