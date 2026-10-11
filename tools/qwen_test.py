# tools/qwen_test.py — Version 20261006v01  (AURA)
# Prueft das Sprachmodell auf diesem Rechner in drei Stufen:
#   1) Schicht 0 auf der GPU vs. reine Python-Rechnung (Prefill- UND Decode-Pfad)
#   2) ganzes Modell: kurze Frage, Antwort + Tempo
# Aufruf:  py tools\qwen_test.py [models\Qwen3-4B]      (AURA vorher schliessen oder pausieren)
import math, operator, sys, time
from array import array
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path[:0] = [str(ROOT), str(ROOT / "vendor")]
from aura.llm.bpe_tokenizer import BPETokenizer, StreamDecoder
from aura.llm import qwen as Q

MODEL = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "models" / "Qwen3-4B"

def f32(eng, k):
    a = array("f"); a.frombytes(eng.st.f32(k)); return a

def cpu_layer0(eng, x, T):
    """Referenz in reinem Python: Residualstrom nach Schicht 0 fuer das LETZTE Token."""
    H, I, NH, NKV, eps = eng.H, eng.I, eng.NH, eng.NKV, eng.eps; p = "model.layers.0."
    def mat(n):
        w = f32(eng, p + n + ".weight"); IN = len(w) // eng.st.shape(p + n + ".weight")[0]
        return [w[o * IN:(o + 1) * IN] for o in range(len(w) // IN)]
    lin = lambda rows, v: [sum(map(operator.mul, r, v)) for r in rows]
    def rms(v, g): r = 1 / math.sqrt(sum(a * a for a in v) / len(v) + eps); return [a * r * b for a, b in zip(v, g)]
    theta = eng.cfg.get("rope_theta", 1e6); inv = [1 / theta ** (2 * i / 128) for i in range(64)]
    def rope(v, g, pos):
        v = rms(v, g); out = list(v)
        for i in range(64):
            c, s = math.cos(pos * inv[i]), math.sin(pos * inv[i]); out[i] = v[i] * c - v[i + 64] * s; out[i + 64] = v[i + 64] * c + v[i] * s
        return out
    rows = [list(x[t * H:(t + 1) * H]) for t in range(T)]
    ln1 = f32(eng, p + "input_layernorm.weight"); qn = f32(eng, p + "self_attn.q_norm.weight"); kn = f32(eng, p + "self_attn.k_norm.weight")
    Wk, Wv = mat("self_attn.k_proj"), mat("self_attn.v_proj")
    K, V = [], []
    for t in range(T):
        xn = rms(rows[t], ln1); k = lin(Wk, xn); v = lin(Wv, xn)
        K.append([y for h in range(NKV) for y in rope(k[h * 128:(h + 1) * 128], kn, t)]); V.append(v)
    del Wk, Wv
    t = T - 1; xn = rms(rows[t], ln1); q = lin(mat("self_attn.q_proj"), xn); att = []
    for h in range(NH):
        qh = rope(q[h * 128:(h + 1) * 128], qn, t); kv = h // (NH // NKV)
        sc = [sum(map(operator.mul, qh, K[j][kv * 128:(kv + 1) * 128])) / math.sqrt(128) for j in range(T)]
        m = max(sc); e = [math.exp(s - m) for s in sc]; z = sum(e)
        att += [sum(e[j] * V[j][kv * 128 + d] for j in range(T)) / z for d in range(128)]
    h1 = [a + b for a, b in zip(rows[t], lin(mat("self_attn.o_proj"), att))]
    xn = rms(h1, f32(eng, p + "post_attention_layernorm.weight"))
    gt = lin(mat("mlp.gate_proj"), xn); upv = lin(mat("mlp.up_proj"), xn)
    hh = [g / (1 + math.exp(-g)) * u for g, u in zip(gt, upv)]
    return [a + b for a, b in zip(h1, lin(mat("mlp.down_proj"), hh))]

def compare(name, a, b):
    md = max(abs(u - v) for u, v in zip(a, b)); cos = sum(u * v for u, v in zip(a, b)) / (
        math.sqrt(sum(u * u for u in a)) * math.sqrt(sum(v * v for v in b)))
    ok = cos > 0.9999; print(f"  [{'OK' if ok else 'ABW.'}] {name}: Kosinus {cos:.6f}, max. Abweichung {md:.2e}"); return ok

def stage1(tok):
    print("=== 1: Schicht 0 - GPU vs. CPU ===")
    eng = Q.Qwen3Engine(MODEL, layers=1, maxT=64)
    ids = tok.encode("Der Zuschlag für GEVER wurde erteilt.")[:8]; T = len(ids); H = eng.H
    x = array("f"); x.frombytes(eng.embed_rows(ids))
    t0 = time.perf_counter(); ref = cpu_layer0(eng, x, T); print(f"  CPU-Referenz ({T} Tokens): {time.perf_counter() - t0:.1f} s")
    eng.forward(ids, 0, want_logits=False)                        # Prefill-Pfad (Kachel-Kernel)
    r = eng.g.read(eng.R, T * H); ok = compare("Prefill-Pfad", r[(T - 1) * H:], ref)
    eng.forward(ids[:-1], 0, want_logits=False); eng.forward(ids[-1:], T - 1, want_logits=False)   # Decode-Pfad
    r = eng.g.read(eng.R, H); ok &= compare("Decode-Pfad ", r, ref)
    del eng; return ok

def stage2(tok):
    print("\n=== 2: ganzes Modell ===")
    t0 = time.perf_counter()
    eng = Q.Qwen3Engine(MODEL, progress=lambda m, *a: print("\r  " + m + " " * 10, end=""))
    print(f"\n  geladen in {time.perf_counter() - t0:.0f} s")
    stop = {tok.added["<|im_end|>"], tok.added["<|endoftext|>"]}
    for q in ("Was ist die Hauptstadt der Schweiz? Antworte in einem Satz.",):
        ids = tok.encode(f"<|im_start|>user\n{q}<|im_end|>\n<|im_start|>assistant\n")
        t0 = time.perf_counter(); logits = eng.prefill(ids); t1 = time.perf_counter()
        print(f"  Frage: {q}\n  Antwort: ", end="", flush=True)
        dec, pos, n = StreamDecoder(tok), len(ids), 0
        while n < 60:
            tid = Q.sample(logits, 0)
            if tid in stop: break
            print(dec.push(tid), end="", flush=True); n += 1
            logits = eng.forward([tid], pos); pos += 1
        dt = time.perf_counter() - t1
        print(f"\n  Kontext {len(ids)} Tokens in {t1 - t0:.1f} s | Antwort {n} Tokens in {dt:.1f} s = {n / dt:.2f} Tokens/s")
    long_ids = tok.encode("Bericht. " * 400)[:1024]                # Prefill-Tempo fuer einen RAG-Kontext
    t0 = time.perf_counter(); eng.prefill(long_ids); dt = time.perf_counter() - t0
    print(f"  Prefill-Tempo: {len(long_ids)} Tokens in {dt:.1f} s ({len(long_ids) / dt:.0f} Tokens/s)")

if __name__ == "__main__":
    tok = BPETokenizer(MODEL / "tokenizer.json")
    try:
        if stage1(tok): stage2(tok)
        else: print("\nAbweichung in Schicht 0 - Stufe 2 uebersprungen. Bitte Ausgabe zurueckmelden.")
    except Exception as e:
        import traceback; traceback.print_exc()
    input("\nEnter zum Schliessen...")
