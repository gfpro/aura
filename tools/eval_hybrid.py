# tools/eval_hybrid.py — Version 20261006v14  (AURA)
# Misst die Suche: BM25 vs. Vektor vs. hybrid vs. "app" (wie in der App: Personen-/Zeitfilter, Fristen-Bevorzugung).
# Testfragen: eval\fragen.txt   Aufruf:  py tools\eval_hybrid.py [Pfad\zu\fragen.txt]
# AURA vorher schliessen (GPU und Datenbank).
import re, sys, time
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "vendor")]
from aura import db
from aura.config import EVAL, MODELS, load_settings
from aura.rag import Retriever

K = 10
CUTS = (1, 4, 6, 10)          # 4 = was das Sprachmodell liest (llm_top_k), 6 = was die App anzeigt (top_k)

def parse(path):
    qs = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"): continue
        parts = [p.strip() for p in ln.split(";;")]
        if len(parts) < 2 or not parts[1]: print(f"  ignoriert (kein ;; Ziel): {ln[:50]}"); continue
        qs.append((parts[0], [p for p in parts[1:] if p]))
    return qs

def relevant(conn, targets):
    """Ziel = Teil des Betreffs, optional ' @JJJJ-MM-TT'. Alle passenden Objekte zaehlen als richtig."""
    ids = set()
    for t in targets:
        m = re.match(r"(.*?)\s*@\s*(\d{4}-\d{2}-\d{2})\s*$", t)
        title, day = (m.group(1), m.group(2)) if m else (t, None)
        sql, a = "SELECT id FROM items WHERE title LIKE ?", [f"%{title}%"]
        if day: sql += " AND substr(ts, 1, 10) = ?"; a.append(day)
        ids |= {r[0] for r in conn.execute(sql, a)}
    return ids

def app_hits(R, conn, q, qvec, mode):
    """Gleiche Auswahl wie worker.job_ask (aber k=10 statt top_k, damit Rang 7-10 sichtbar wird)."""
    who = R.author_items(conn, q); items = who[0] if who else None
    it = R.intent(conn, q) if hasattr(R, "intent") else None
    if it: items = R.filter_items(conn, it, items)
    if items is not None and not items: return []
    if it and (it.get("recent") or (it.get("range") and len(items) <= K)): return R.item_hits(conn, items, K)
    kw = {"prefer": R.facet(q)} if hasattr(R, "facet") else {}
    hits = R.search(conn, q, qvec, k=K, mode=mode, items=items, **kw)
    if it and it.get("range"): hits.sort(key=lambda h: h["ts"])
    return hits

def rank(hits, rel):
    for i, h in enumerate(hits):
        if h["item_id"] in rel: return i + 1
    return None

def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else EVAL / "fragen.txt"
    qs = parse(path)
    if not qs: sys.exit(f"Keine Testfragen in {path}")
    conn = db.connect(); R = Retriever(); s = load_settings()
    have_vec = conn.execute("SELECT 1 FROM chunks WHERE vec IS NOT NULL LIMIT 1").fetchone()
    emb = None
    if have_vec:
        from aura.engine.embedder import Embedder
        emb = Embedder(MODELS / s["embed_model"]); ok, why = emb.available()
        if ok: print("Lade Embedding-Modell ..."); emb.load()
        else: print(f"Embedding nicht verfuegbar: {why}"); emb = None
    modes = ["bm25"] + (["vector", "hybrid", "app"] if emb else ["app"])
    print(f"{len(qs)} Testfragen | Modi: {', '.join(modes)}\n")

    res = {m: [] for m in modes}; tsum = {m: 0.0 for m in modes}; rows = []; nores = []
    for n, (q, targets) in enumerate(qs, 1):
        rel = relevant(conn, targets)
        if not rel: nores.append(n); continue
        cov = conn.execute(f"SELECT COUNT(*), COUNT(vec) FROM chunks WHERE item_id IN ({','.join(map(str, rel))})").fetchone()
        qvec = emb.query(q) if emb else None
        row = {}
        for m in modes:
            t0 = time.perf_counter()
            hits = app_hits(R, conn, q, qvec, "hybrid" if emb else "bm25") if m == "app" \
                else R.search(conn, q, qvec, k=K, mode=m)
            tsum[m] += time.perf_counter() - t0
            row[m] = rank(hits, rel); res[m].append(row[m])
        rows.append((n, q, len(rel), cov, row))
        print(f"  {n:>2}: " + "  ".join(f"{m} {row[m] or '-':>2}" for m in modes)
              + f"   | Vektoren Ziel {cov[1]}/{cov[0]}")

    if nores: print(f"\nACHTUNG: Ziel nicht in der DB gefunden (Betreff pruefen): Nr. {nores}")
    out = [f"Eval {datetime.now():%d.%m.%Y %H:%M} | {path.name} | {len(rows)} Fragen gewertet", "",
           f"{'Modus':<8}" + "".join(f"{'Top-' + str(c):>8}" for c in CUTS) + f"{'MRR@10':>8}{'ms/Frage':>10}"]
    for m in modes:
        r = res[m]; N = len(r) or 1
        mrr = sum(1 / x for x in r if x) / N
        out.append(f"{m:<8}" + "".join(f"{sum(1 for x in r if x and x <= c):>5}/{len(r):<2}" for c in CUTS)
                   + f"{mrr:>8.2f}{tsum[m] / N * 1000:>10.0f}")
    out.append("\n(Vektor-Modus sieht nur Stuecke mit Vektor - bei unvollstaendiger Einbettung zu tief.)")
    print("\n" + "\n".join(out))
    EVAL.mkdir(exist_ok=True)
    f = EVAL / f"ergebnis_{datetime.now():%Y%m%d_%H%M}.txt"
    detail = ["", "Detail (mit Fragetext - vor dem Teilen schwaerzen):"] + [
        f"{n:>2}  " + " ".join(f"{m}={row[m] or '-'}" for m in modes) + f"  ziele={nr} vek={c[1]}/{c[0]}  {q}"
        for n, q, nr, c, row in rows]
    f.write_text("\n".join(out + detail), encoding="utf-8")
    print(f"\nGespeichert: {f}\n(Bildschirmausgabe enthaelt keine Fragetexte und kann geteilt werden.)")
    input("\nEnter zum Schliessen...")

if __name__ == "__main__":
    main()
