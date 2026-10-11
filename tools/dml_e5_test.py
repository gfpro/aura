# tools/dml_e5_test.py — Etappe 1: e5 ueber DirectML.  A) Schicht 0 gegen Python-Referenz,
# B) ganzes Modell gegen das heutige AURA-Embedding (Kosinus), C) Tempo.   AURA vorher schliessen.
# Aufruf in C:\aura:  python tools\dml_e5_test.py     -> Ausgabe auch in tools\dml_e5_test.txt
import math, operator, os, sys, time, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "vendor")]
OUT = []
def p(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); OUT.append(s)
def save():
    with open(os.path.join(ROOT, "tools", "dml_e5_test.txt"), "w", encoding="utf-8") as f: f.write("\n".join(OUT))

from aura.config import MODELS, load_settings
from aura.engine import dml
from aura.engine.e5_dml import E5DML
from aura.engine.tokenizer import XLMRTokenizer

MD = MODELS / load_settings()["embed_model"]
TEXT = "Der Zuschlag für den Vertrag «Weiterentwicklung GEVER armasuisse» wurde am 28. September erteilt."
def cos(a, b):
    return sum(u * v for u, v in zip(a, b)) / (math.sqrt(sum(u * u for u in a)) * math.sqrt(sum(v * v for v in b)) or 1)

def cpu_layer0(st, H, I, NH, eps, x, T, check):
    """Referenz in reinem Python (aus engine/layer_test.py)."""
    D = H // NH; pre = "encoder.layer.0."
    def W(n):
        w = st.floats(pre + n + ".weight"); b = st.floats(pre + n + ".bias"); no = len(b); ni = len(w) // no
        return [w[o * ni:(o + 1) * ni] for o in range(no)], b
    def lin(row, Wb): rows, b = Wb; return [sum(map(operator.mul, row, r)) + b[o] for o, r in enumerate(rows)]
    def ln(a, r, n):
        g = st.floats(pre + n + ".weight"); b = st.floats(pre + n + ".bias")
        y = [u + v for u, v in zip(a, r)]; mu = sum(y) / H; var = sum((v - mu) ** 2 for v in y) / H
        s = 1 / math.sqrt(var + eps); return [(v - mu) * s * g[k] + b[k] for k, v in enumerate(y)]
    rows = [list(x[t * H:(t + 1) * H]) for t in range(T)]
    Wq, Wk, Wv = W("attention.self.query"), W("attention.self.key"), W("attention.self.value")
    K = [lin(r, Wk) for r in rows]; V = [lin(r, Wv) for r in rows]
    Wo, Wi, Wf = W("attention.output.dense"), W("intermediate.dense"), W("output.dense")
    out = {}
    for t in check:
        q = lin(rows[t], Wq); a = [0.0] * H
        for h in range(NH):
            sl = slice(h * D, (h + 1) * D)
            sc = [sum(map(operator.mul, q[sl], K[j][sl])) / math.sqrt(D) for j in range(T)]
            mx = max(sc); e = [math.exp(v - mx) for v in sc]; z = sum(e)
            for d in range(D): a[h * D + d] = sum(e[j] * V[j][h * D + d] for j in range(T)) / z
        x1 = ln(lin(a, Wo), rows[t], "attention.output.LayerNorm")
        hh = [0.5 * v * (1 + math.erf(v / math.sqrt(2))) for v in lin(x1, Wi)]
        out[t] = ln(lin(hh, Wf), x1, "output.LayerNorm")
    return out

def main():
    tok = None                                           # Tokenizer erwartet die Datei tokenizer.json (nicht den Ordner)
    for arg in ((MD / "tokenizer.json",), (MD,), ()):
        try: tok = XLMRTokenizer(*arg); break
        except (TypeError, OSError): continue
    if tok is None: raise RuntimeError("Tokenizer nicht ladbar")
    ids = tok.encode("passage: " + TEXT); T = len(ids)
    dev = dml.Device(); p(f"Adapter: {dev.name} | Modell: {MD.name} | {T} Tokens")
    p("\n== 0) Operator-Selbsttest")
    if not dml.selftest(dev, p): p("Selbsttest nicht bestanden - Abbruch."); return

    # ---------------------------------------------------------------- A) Schicht 0
    p("\n== A) Schicht 0: DirectML gegen Python-Referenz")
    e1 = E5DML(MD, dev, progress=lambda s: None); e1.load(layers=1)
    y = e1.hidden(ids)
    st, H = e1.st, e1.H
    x = []                                                   # Eingang der Schicht 0 = LayerNorm(Embedding) in FP32
    for i, tid in enumerate(ids):
        w = st.floats("embeddings.word_embeddings.weight", tid * H, H)
        q = st.floats("embeddings.position_embeddings.weight", (e1.pad + 1 + i) * H, H)
        r = [w[k] + q[k] + e1.type0[k] for k in range(H)]; mu = sum(r) / H
        var = sum((v - mu) ** 2 for v in r) / H; s = 1 / math.sqrt(var + e1.eps)
        g = st.floats("embeddings.LayerNorm.weight"); b = st.floats("embeddings.LayerNorm.bias")
        x.extend((r[k] - mu) * s * g[k] + b[k] for k in range(H))
    t0 = time.perf_counter(); ref = cpu_layer0(st, H, e1.I, e1.NH, e1.eps, x, T, [1, T - 1])
    p(f"   (Referenz in {time.perf_counter() - t0:.0f} s)")
    okA = True
    for t, r in ref.items():
        md = max(abs(u - v) for u, v in zip(y[t], r)); c = cos(y[t], r); good = c > 0.9999; okA &= good
        p(f"   [{'OK' if good else 'ABW.'}] Token {t}: max. Abweichung {md:.3f}, Kosinus {c:.6f}")
    save()
    if not okA: p("Schicht 0 weicht ab - B/C uebersprungen."); return

    # ---------------------------------------------------------------- B) ganzes Modell
    p("\n== B) ganzes Modell (24 Schichten)")
    e = E5DML(MD, dev, progress=lambda s: None); e.load()
    p(f"   Gewichte geladen in {e.load_s:.0f} s")
    v = e.vector(ids); p(f"   Rechenplan fuer {T} Tokens erstellt in {e.timing['plan']:.1f} s")
    try:
        from aura.engine.embedder import Embedder
        old = Embedder(MD); old.load()
        cands = {"passage(TEXT)": old.passage(TEXT), "passage('passage: '+TEXT)": old.passage("passage: " + TEXT)}
        for k, w in cands.items(): p(f"   Kosinus zu heutigem AURA-Embedding, {k}: {cos(v, w):.6f}")
    except Exception as ex:
        old = None; p("   Vergleich mit heutigem Embedder nicht moeglich:", repr(ex))
    save()

    # ---------------------------------------------------------------- C) Tempo
    p("\n== C) Tempo (je 3 Laeufe nach dem Aufwaermen)")
    for n in (T, 150, 512):
        ids_n = (tok.encode("passage: " + (TEXT + " ") * 40))[:n] if n != T else ids
        e.vector(ids_n)                                          # Plan erstellen + aufwaermen
        tm = []
        for _ in range(3):
            t0 = time.perf_counter(); e.vector(ids_n); tm.append((time.perf_counter() - t0, dict(e.timing)))
        best = min(tm, key=lambda z: z[0])
        parts = "  ".join(f"{k} {v * 1000:.0f} ms" for k, v in best[1].items() if k != "plan")
        line = f"   {len(ids_n):4d} Tokens: DirectML {best[0]:.3f} s  ({parts})"
        if old is not None:
            txt = tok.decode(ids_n[1:-1]) if hasattr(tok, "decode") else None
            if txt:
                old.passage(txt); t0 = time.perf_counter(); old.passage(txt); line += f" | heute {time.perf_counter() - t0:.3f} s"
        p(line); save()

if __name__ == "__main__":
    try: main()
    except Exception:
        p("FEHLER:\n" + traceback.format_exc())
    save(); p("\nGespeichert: tools\\dml_e5_test.txt")
