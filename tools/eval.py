# tools/eval.py — misst die Suche: BM25 vs. Vektor vs. hybrid, mit eval\mail_eval.txt (wie mail_import v03).
#   py tools\eval.py
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path[:0] = [str(ROOT), str(ROOT / "vendor")]
from aura import db
from aura.config import MODELS, EVAL, load_settings
from aura.engine.embedder import Embedder
from aura.rag import Retriever

lines = [l for l in (EVAL / "mail_eval.txt").read_text(encoding="utf-8").splitlines()
         if l.strip() and not l.lstrip().startswith("#") and "|" in l]
conn = db.connect(); r = Retriever(); emb = Embedder(MODELS / load_settings()["embed_model"])
has_vec = emb.available()[0] and conn.execute("SELECT 1 FROM chunks WHERE vec IS NOT NULL LIMIT 1").fetchone()
cases = [(q.strip(), w.strip().lower(), emb.query(q.strip()) if has_vec else None) for q, w in (l.split("|", 1) for l in lines)]
for mode in (["bm25", "vector", "hybrid"] if has_vec else ["bm25"]):
    h3 = h8 = 0; rr = 0.0
    for q, want, qv in cases:
        subs = [h["title"].lower() for h in r.search(conn, q, qv, k=8, mode=mode)]
        rank = next((i + 1 for i, s in enumerate(subs) if want in s), 0)
        h3 += 0 < rank <= 3; h8 += rank > 0; rr += 1 / rank if rank else 0
    n = len(cases)
    print(f"{mode:7}  Top-3: {h3}/{n} | Top-8: {h8}/{n} | MRR: {rr / n:.2f}")
