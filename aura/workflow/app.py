# aura/workflow/app.py — verbindet die Engine mit AURA (Worker oder Kommandozeile). Version 20261008v28
from ..config import DATA, ROOT, MODELS
from .engine import Ctx

WF_DIR, OUT_DIR, RUNS_DIR = ROOT / "workflows", DATA / "outputs", DATA / "wf_runs"

def make_ctx(conn, settings, get_llm, get_embedder, retriever, progress, cancelled, on_text=None, wissen=None):
    from ..llm import discover
    labels = {i: l for i, l, _ in discover(MODELS)}

    def llm(bid=None):
        bid = bid or settings.get("llm")
        if not bid or bid == "extractive":
            raise RuntimeError("Dieser Workflow braucht ein Sprachmodell - bitte links ein Qwen-Modell wählen")
        if bid not in labels: raise RuntimeError(f"Sprachmodell {bid} nicht gefunden (vorhanden: {', '.join(labels)})")
        return get_llm(bid), bid, f"{labels[bid]} {bid}"

    def search(query, k=6, sources=None):
        items = None
        if sources:
            if isinstance(sources, str): sources = [sources]
            items = [r[0] for r in conn.execute(f"SELECT id FROM items WHERE source IN ({','.join('?' * len(sources))}) "
                                                "ORDER BY ts DESC LIMIT 20000", list(sources))]
            if not items: return []
        emb, qvec, mode = get_embedder(), None, "bm25"
        if emb is not None and emb.available()[0] and conn.execute("SELECT 1 FROM chunks WHERE vec IS NOT NULL LIMIT 1").fetchone():
            qvec, mode = emb.query(query), "hybrid"
        return retriever.search(conn, query, qvec, k=k, mode=mode, items=items)

    return Ctx(conn, settings, llm, search, WF_DIR, OUT_DIR, RUNS_DIR, progress, cancelled, on_text, wissen)
