# tools/suche_test.py — Version 20261016v101 (v101: Weg «chat» nutzt Retriever.plan wie der Chat; alter Weg als «chat_alt») (AURA)
# Misst die Suche mit eigenen Testfragen: Steht die richtige Mail unter den ersten 3 bzw. 8 Treffern?
# Eingabe:  eval\fragen.txt   Zeilen «Frage | Betreff der richtigen Mail | Antwort (optional, wird ignoriert)»
# Ausgabe:  tools\suche_test.txt (und Kurzfassung in der Konsole)
# Aufruf:   AURA schliessen, dann  cd /d C:\aura  und  py tools\suche_test.py
# Gemessen werden vier Wege: nur Woerter (BM25), nur Vektoren, hybrid, hybrid mit den Filtern wie im Chat.
import re, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from aura import db
from aura.config import MODELS, load_settings
from aura.engine.embedder import Embedder
from aura.rag import Retriever

PRE = re.compile(r"^\s*((aw|wg|re|fw|fwd|antw|weiterl)\s*:\s*)+", re.I)
def norm(t): return re.sub(r"\s+", " ", PRE.sub("", (t or "").lower())).strip(" .")

def passt(soll, titel):
    a, b = norm(soll), norm(titel)
    return a == b or (len(a) >= 15 and (a in b or b in a))

def lesen(p):
    out = []
    for z in p.read_text(encoding="utf-8-sig").splitlines():
        t = [x.strip() for x in z.split("|")]
        if len(t) < 2 or not t[0] or t[0].lower() == "frage": continue
        out.append((t[0], t[1]))
    return out

def main():
    f = ROOT / "eval" / "fragen.txt"
    if not f.exists(): print(f"Fehlt: {f}"); return
    fragen = lesen(f); s = load_settings(); conn = db.connect(); R = Retriever()
    emb = Embedder(MODELS / s["embed_model"]); ok = emb.available()[0]
    print(f"{len(fragen)} Fragen · Vektoren: {'ja' if ok else 'NEIN (nur BM25)'} · Modell {s['embed_model']}")
    titel = {norm(t) for (t,) in conn.execute("SELECT title FROM items")}
    wege = ["bm25", "vektor", "hybrid", "chat_alt", "chat"] if ok else ["bm25"]
    erg = {w: {"top3": 0, "top8": 0, "mrr": 0.0} for w in wege}; zeilen = []; t_suche = {w: 0.0 for w in wege}
    for i, (q, soll) in enumerate(fragen, 1):
        da = any(passt(soll, t) for t in titel)
        qv = emb.query(q) if ok else None
        zeilen.append(f"\n[{i}] {q}\n    soll: {soll}" + ("" if da else "   !! Betreff nicht in der Datenbank"))
        for w in wege:
            t0 = time.perf_counter()
            if w in ("chat", "chat_alt"):                              # wie job_ask: Filter, Facette, Aktualitaet
                if w == "chat":
                    pl = R.plan(conn, q); it, items, boost = pl["intent"], pl["items"], pl["boost"]
                else:                                                   # bis v100: harte Filter
                    who = R.author_items(conn, q); items = who[0] if who else None; boost = None
                    it = R.intent(conn, q)
                    if it: items = R.filter_items(conn, it, items)
                rw = float(s.get("recency_weight", 0.01)) * (3 if it and it.get("recent") else 1)
                if it and items is not None and (it.get("recent") or (it.get("range") and len(items) <= 8)):
                    hits = R.item_hits(conn, items, 8)
                else:
                    hits = R.search(conn, q, qv, k=8, mode="hybrid", items=items, prefer=R.facet(q), recency=rw, boost=boost,
                                    half_days=int(s.get("recency_half_days", 180)), quote_weight=float(s.get("zitat_gewicht", 0.8)))
            else:
                hits = R.search(conn, q, qv, k=8, mode={"vektor": "vector"}.get(w, w))
            t_suche[w] += time.perf_counter() - t0
            rang = next((r for r, h in enumerate(hits, 1) if passt(soll, h["title"])), None)
            if rang:
                erg[w]["top8"] += 1; erg[w]["mrr"] += 1 / rang
                if rang <= 3: erg[w]["top3"] += 1
            erste = hits[0]["title"][:70] if hits else "-"
            zeilen.append(f"    {w:<7} Rang {rang or '-':<3} (1.: {erste})")
        print(f"  {i}/{len(fragen)}", end="\r")
    n = len(fragen); kopf = [f"Suche-Test {time.strftime('%d.%m.%Y %H:%M')} · {n} Fragen · Embedding {s['embed_model']}", ""]
    kopf.append(f"{'Weg':<8}{'Top 3':>8}{'Top 8':>8}{'MRR':>7}{'ms/Frage':>10}")
    for w in wege:
        e = erg[w]; kopf.append(f"{w:<8}{e['top3']:>5}/{n:<2}{e['top8']:>5}/{n:<2}{e['mrr'] / n:>7.2f}{t_suche[w] / n * 1000:>10.0f}")
    kopf.append("\nHinweis: Bei 30 Fragen sind Unterschiede von 1-2 Treffern Zufall.")
    out = "\n".join(kopf + zeilen)
    (ROOT / "tools" / "suche_test.txt").write_text(out, encoding="utf-8")
    print("\n" + "\n".join(kopf)); print(f"\nDetails: {ROOT / 'tools' / 'suche_test.txt'}")

if __name__ == "__main__": main()
