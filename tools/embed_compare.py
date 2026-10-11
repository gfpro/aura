# tools/embed_compare.py — Etappe 2: neuer Embedder (DirectML, Laengenstufen) gegen die gespeicherten Vektoren
# in data\aura.db (berechnet mit der bisherigen Engine). Liest nur, schreibt nichts.  AURA vorher schliessen.
# Aufruf in C:\aura:  python tools\embed_compare.py [Anzahl, Standard 40]   -> auch tools\embed_compare.txt
import math, os, random, sqlite3, sys, time, traceback
from array import array
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "vendor")]
OUT = []
def p(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); OUT.append(s)

def main():
    from aura.config import DB_PATH, MODELS, load_settings
    from aura.engine.embedder import Embedder
    N = next((int(x) for x in sys.argv[1:] if x.isdigit()), 40)       # andere Argumente ignorieren
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    ids = [r[0] for r in con.execute("SELECT id FROM chunks WHERE vec IS NOT NULL")]
    pick = random.Random(7).sample(ids, min(N, len(ids)))
    rows = [con.execute("SELECT text, vec FROM chunks WHERE id = ?", (i,)).fetchone() for i in pick]
    emb = Embedder(MODELS / load_settings()["embed_model"])
    t0 = time.perf_counter(); emb.load(); p(f"Engine: {emb.kind} | geladen in {time.perf_counter() - t0:.1f} s | {len(rows)} Stuecke")
    if emb.kind != "dml": p("ACHTUNG: DirectML nicht aktiv (Grund im AURA-Log)")
    emb.passage("Aufwaermen")
    cs, tm, buckets = [], [], {}
    for text, vec in rows:
        old = array("f"); old.frombytes(vec)
        t = time.perf_counter(); new = emb.passage(text); tm.append(time.perf_counter() - t)
        c = sum(a * b for a, b in zip(new, old)) / (math.sqrt(sum(a * a for a in old)) or 1)
        cs.append(c)
        if emb.dml: b = emb.dml.timing["bucket"]; buckets[b] = buckets.get(b, 0) + 1
    cs.sort()
    p(f"Kosinus neu vs. gespeichert: min {cs[0]:.6f} | Median {cs[len(cs) // 2]:.6f} | Mittel {sum(cs) / len(cs):.6f}")
    p(f"  unter 0.999: {sum(c < 0.999 for c in cs)}   unter 0.99: {sum(c < 0.99 for c in cs)}")
    tm2 = sorted(tm)
    p(f"Zeit pro Stueck: Median {tm2[len(tm2) // 2]:.3f} s | Mittel {sum(tm) / len(tm):.3f} s | max {tm2[-1]:.3f} s"
      f"  (erste Nutzung einer Laengenstufe enthaelt deren Vorbereitung)")
    if buckets: p("Laengenstufen:", ", ".join(f"{k}: {v}x" for k, v in sorted(buckets.items())))
    rest = con.execute("SELECT COUNT(*) FROM chunks WHERE vec IS NULL").fetchone()[0]
    p(f"Noch ohne Vektor: {rest} Stuecke -> geschaetzt {rest * sum(tm) / len(tm) / 60:.0f} min")

if __name__ == "__main__":
    try: main()
    except Exception: p("FEHLER:\n" + traceback.format_exc())
    with open(os.path.join(ROOT, "tools", "embed_compare.txt"), "w", encoding="utf-8") as f: f.write("\n".join(OUT))
    p("\nGespeichert: tools\\embed_compare.txt")
