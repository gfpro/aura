# aura/rag.py — hybride Suche: BM25 (SQLite FTS5) + Vektoren (e5), kombiniert per Reciprocal Rank Fusion.
# v104: Treffer tragen die Empfaenger (recipients) fuer die Quellenzeile.
# v102: Bonus-Ranglisten mit halbem Gewicht (boost_weight 0,5).
# v101: plan(): Person und Quelle (z.B. «Kalender») nur noch als Bonus statt harter Filter – ausser bei Listenfragen
#       («zuletzt», «letzte Woche»). Gemessen: harte Filter verloren 4 von 30 Testfragen.
# v98: Vektorsuche auf der GPU (eigenes D3D11-Geraet, Bloecke zu 16384 Vektoren, Selbsttest gegen Python, sonst Rueckfall).
# v76: Personenfilter nur bei Hinweis («von X», «X schrieb»); vorher filterte z.B. «RSIT» nach Absendern.
# v73: Stuecke aus dem zitierten Mailverlauf zaehlen mit quote_weight (Standard 0,8) - das Original geht vor.
import heapq, operator, re, struct, time
from datetime import date, timedelta
from array import array
from .log import diag

RRF_K = 60
GPU_ROWS = 16384                                                    # v98: Vektoren je GPU-Puffer (16384 x 1024 x 4 B = 64 MB)

# v98: Skalarprodukt Frage x alle Vektoren. Eine Gruppe je Vektor, 256 Threads summieren ueber H.
K_SCORE = r"""
cbuffer C:register(b0){ uint N; uint H; uint P1; uint P2; };
RWStructuredBuffer<float> M:register(u0); RWStructuredBuffer<float> Q:register(u1); RWStructuredBuffer<float> S:register(u2);
groupshared float red[256];
[numthreads(256,1,1)]
void main(uint3 g:SV_GroupID, uint3 l:SV_GroupThreadID){
  uint r=g.x, i=l.x, k; float acc=0;
  if(r<N){ for(k=i;k<H;k+=256) acc+=Q[k]*M[r*H+k]; }
  red[i]=acc; GroupMemoryBarrierWithGroupSync();
  for(uint a=128;a>0;a>>=1){ if(i<a) red[i]+=red[i+a]; GroupMemoryBarrierWithGroupSync(); }
  if(i==0&&r<N) S[r]=red[0];
}"""

class GpuScores:
    """v98: alle Vektoren einmal in den Grafikspeicher; je Frage ein Durchgang statt 40'000 Python-Skalarprodukte."""
    def __init__(self, mat, H):
        from .engine.gpu import GPU
        self.g = g = GPU(); self.H = H; self.k = g._shader(K_SCORE); self.blocks = []
        n = len(mat) // H; mv = memoryview(mat).cast("B")
        for r0 in range(0, n, GPU_ROWS):
            r1 = min(n, r0 + GPU_ROWS)
            self.blocks.append((r0, r1, g.buffer((r1 - r0) * H, mv[r0 * H * 4:r1 * H * 4]), g.buffer(r1 - r0)))
        self.q = g.buffer(H)
    def scores(self, qvec):
        from array import array
        g = self.g; g.write(self.q, array("f", qvec).tobytes()); out = array("f")
        for r0, r1, m, sb in self.blocks:
            g._run(self.k, struct.pack("<4I", r1 - r0, self.H, 0, 0), [m, self.q, sb], (r1 - r0, 1, 1))
        for r0, r1, m, sb in self.blocks: out.extend(g.read(sb, r1 - r0))
        return out
    def close(self):
        try: self.g.close()
        except Exception: pass

def _mo(d): return d - timedelta(d.weekday())
def _eom(d): return (d.replace(day=28) + timedelta(4)).replace(day=1) - timedelta(1)

class Retriever:
    def __init__(self):
        self.ids, self.mat, self.H = [], None, 1024      # Vektor-Cache (alle Chunks mit Vektor)
        self.gpu, self.gpu_off = None, False             # v98

    def invalidate(self):
        self.mat = None
        if self.gpu: self.gpu.close(); self.gpu = None

    def _load(self, conn):
        ids, mat = [], array("f"); self.pos = {}
        for cid, blob in conn.execute("SELECT id, vec FROM chunks WHERE vec IS NOT NULL ORDER BY id"):
            ids.append(cid); mat.frombytes(blob)
        self.ids, self.mat = ids, mat; self.pos = {c: i for i, c in enumerate(ids)}
        if ids: self.H = len(mat) // len(ids)
        if ids and not self.gpu_off:                                    # v98: auf die GPU, mit Selbsttest
            try:
                t0 = time.perf_counter(); gs = GpuScores(mat, self.H)
                q = list(mat[:self.H]); got = gs.scores(q); mv = memoryview(mat); n = min(32, len(ids))
                ref = [sum(map(operator.mul, q, mv[i * self.H:(i + 1) * self.H])) for i in range(n)]
                if max(abs(a - b) for a, b in zip(ref, got[:n])) > 1e-4: raise RuntimeError("Abweichung im Selbsttest")
                self.gpu = gs; diag("suche_gpu", vektoren=len(ids), laden_s=time.perf_counter() - t0)
            except Exception as e:
                self.gpu = None; self.gpu_off = True; diag("suche_gpu", fehler=f"{type(e).__name__}:{e}", rueckfall="python")

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
        H, mv = self.H, memoryview(self.mat); t0 = time.perf_counter()
        if items is None: idx = range(len(self.ids))
        else:
            inl = ",".join(str(int(i)) for i in items)
            idx = [self.pos[c] for (c,) in conn.execute(f"SELECT id FROM chunks WHERE item_id IN ({inl})") if c in self.pos]
        allsc = None
        if self.gpu:                                                    # v98
            try: allsc = self.gpu.scores(qvec)
            except Exception as e:
                diag("suche_gpu", fehler=f"{type(e).__name__}:{e}", rueckfall="python"); self.gpu.close(); self.gpu = None
        if allsc is not None: best = heapq.nlargest(n, idx, key=allsc.__getitem__)
        else:
            sc = {i: sum(map(operator.mul, qvec, mv[i * H:(i + 1) * H])) for i in idx}
            best = sorted(sc, key=sc.get, reverse=True)[:n]
        diag("suche_vektor", weg="gpu" if allsc is not None else "python", vektoren=len(idx), ms=(time.perf_counter() - t0) * 1000)
        return [self.ids[i] for i in best]

    STOP = {"welche", "welcher", "mails", "mail", "hast", "habe", "haben", "von", "der", "die", "das", "und", "mir",
            "mich", "geschrieben", "zuletzt", "was", "wer", "wie", "wann", "ist", "sind", "eine", "einen", "zum", "zur",
            "thema", "alle", "nachrichten", "gesendet", "bekommen", "erhalten", "dem", "den", "des", "ich", "du",
            "wen", "wem", "wessen", "uns", "ihn", "ihm", "ihr", "ihnen", "sie", "ihm", "allen", "einem", "einer"}   # v101

    def author_items(self, conn, question):
        """Erkennt Personennamen in der Frage (Absender/Organisator). Liefert passende item-IDs oder None."""
        names = []
        cue = re.compile(r"\b(von|vom|mit|an|bei|für|fuer|durch|schrieb|sagte|meinte|mailte)\s+(?:herrn?\s+|frau\s+)?$", re.I)   # v76: nur mit Personen-Hinweis
        for m in re.finditer(r"[^\W\d_]{3,}", question):
            w = m.group(0)
            if w.lower() in self.STOP: continue
            after = question[m.end():m.end() + 25].lower()
            if not (cue.search(question[:m.start()]) or re.match(r"\s+(schrieb|geschrieben|gesagt|meint|mailte)", after)
                    or (names and question[m.start() - 1:m.start()] == " " and w[:1].isupper() and names[-1] in question[:m.start()][-30:])):
                continue                                                 # Themenwort wie «RSIT» ist keine Person
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
        for iid in (items or [])[:k]:                                   # v77: None = kein Filter
            r = conn.execute("SELECT c.id, c.text, i.id, i.source, i.title, i.ts, i.author FROM chunks c JOIN items i "
                             "ON i.id = c.item_id WHERE c.item_id = ? ORDER BY c.ord LIMIT 1", (iid,)).fetchone()
            if r: hits.append({"chunk_id": r[0], "text": r[1], "item_id": r[2], "source": r[3], "title": r[4] or "",
                               "ts": r[5] or "", "author": r[6] or "", "score": 0.0})
        return hits

    @staticmethod
    def _recency(conn, score, weight, half_days, today=None):
        """v64: Aktualitaetsbonus auf RRF-Werte: weight * 0,5^(Alter/half_days). weight 0 = aus.
        Platz 1 in beiden Listen ~0,033 - weight 0,01 hebt Neues, ohne Relevanz zu ueberstimmen."""
        if weight <= 0 or not score: return
        d0 = today or date.today(); ids = list(score)
        for i in range(0, len(ids), 500):
            part = ids[i:i + 500]
            for cid, ts in conn.execute("SELECT c.id, i.ts FROM chunks c JOIN items i ON i.id = c.item_id "
                                        f"WHERE c.id IN ({','.join('?' * len(part))})", part):
                try: age = max(0, (d0 - date.fromisoformat((ts or "")[:10])).days)
                except ValueError: continue
                score[cid] += weight * 0.5 ** (age / half_days)

    def plan(self, conn, question):
        """v101: Filter fuer eine Chatfrage. Rueckgabe {who, intent, items (harter Filter oder None), boost (Bonus-Objekte)}."""
        who = self.author_items(conn, question); it = dict(self.intent(conn, question) or {})
        listy = bool(it.get("recent") or it.get("range")); items, boost = None, []
        if who and listy: items = who[0]                                # «letzte Mails von X»: Liste dieser Person
        elif who: boost += who[0]                                       # sonst nur Bonus (Namen stehen oft nur im Text)
        if it.get("source") and not listy:                              # «M365 Kalender» = Thema, nicht nur Termine
            boost += [r[0] for r in conn.execute("SELECT id FROM items WHERE source = ? ORDER BY ts DESC LIMIT 500", (it["source"],))]
            it["soft_source"] = it.pop("source")
        if it.get("range") or it.get("source"): items = self.filter_items(conn, it, items)
        return {"who": who, "intent": it or None, "items": items, "boost": boost or None}

    def search(self, conn, query, qvec=None, k=6, mode="hybrid", per_item=1, items=None, prefer=None,
               recency=0.0, half_days=180, quote_weight=1.0, boost=None, boost_weight=0.5):
        """mode: bm25 | vector | hybrid. items = nur in diesen Objekten suchen (z.B. Absender-Filter).
        Liefert Treffer-Dicts, pro Objekt hoechstens per_item Stuecke."""
        lists = []                                                      # v102: (Rangliste, Gewicht)
        if mode in ("bm25", "hybrid"): lists.append((self.bm25(conn, query, items=items), 1.0))
        if mode in ("vector", "hybrid"): lists.append((self.vector(conn, qvec, items=items), 1.0))
        if boost and items is None:                                     # v101: Bonus = zusaetzliche Rangliste
            bw = float(boost_weight)                                    # v102: halbes Gewicht (Bonus, nicht Hauptbeleg)
            if mode in ("bm25", "hybrid"): lists.append((self.bm25(conn, query, items=boost), bw))
            if mode in ("vector", "hybrid"): lists.append((self.vector(conn, qvec, items=boost), bw))
        if items and not any(l for l, _ in lists):     # nichts Passendes: die neuesten Objekte dieser Person
            inl = ",".join(str(int(i)) for i in items[:k])
            lists.append(([r[0] for r in conn.execute(f"SELECT c.id FROM chunks c JOIN items i ON i.id = c.item_id "
                                                      f"WHERE c.item_id IN ({inl}) AND c.ord = 0 ORDER BY i.ts DESC")], 1.0))
        score = {}
        for lst, wgt in lists:
            for rank, cid in enumerate(lst): score[cid] = score.get(cid, 0.0) + wgt / (RRF_K + rank + 1)
        self._recency(conn, score, recency, max(1, half_days))
        if quote_weight < 1.0 and score:                                # v73
            ids = list(score)
            for i in range(0, len(ids), 500):
                part = ids[i:i + 500]
                for (cid,) in conn.execute(f"SELECT id FROM chunks WHERE zitat = 1 AND id IN ({','.join('?' * len(part))})", part):
                    score[cid] *= quote_weight
        hits, per = [], {}
        for cid in sorted(score, key=score.get, reverse=True):
            r = conn.execute("SELECT c.text, i.id, i.source, i.title, i.ts, i.author, i.recipients FROM chunks c "
                             "JOIN items i ON i.id = c.item_id WHERE c.id = ?", (cid,)).fetchone()
            if not r or per.get(r[1], 0) >= per_item: continue
            per[r[1]] = per.get(r[1], 0) + 1
            hits.append({"chunk_id": cid, "text": r[0], "item_id": r[1], "source": r[2], "title": r[3] or "",
                         "ts": r[4] or "", "author": r[5] or "", "recipients": r[6] or "", "score": score[cid]})   # v104
            if len(hits) >= k: break
        if prefer:                                     # z.B. Frist-Frage: Stelle mit Datum/«spätestens» derselben Mail nehmen
            for h in hits:
                if prefer.search(h["text"]): continue
                for cid, text in conn.execute("SELECT id, text FROM chunks WHERE item_id = ? ORDER BY ord", (h["item_id"],)):
                    if prefer.search(text): h["chunk_id"], h["text"] = cid, text; break
        return hits
