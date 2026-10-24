# tools/spec_test.py - v114 (20261024: Modell aus Einstellungen, Qwen3.5): Lohnt Prompt Lookup? Aendert nichts an AURA.
# Aufruf (AURA vorher schliessen):  py tools\spec_test.py C:\pfad\unterlagen.txt
# A) Zeit fuer T = 1..16 Tokens (Matrix und ganze Schichten)  B) Simulation: wie viele Tokens Prompt Lookup getroffen haette
import sys, time
sys.path.insert(0, r"C:\aura")
from pathlib import Path
from aura.llm.native import NativeCausalLM
from aura.config import load_settings

MODELL = r"C:\aura\models\\" + str(load_settings().get("llm", "Qwen3-4B")).split(":")[-1]
OUT = Path(r"C:\aura\tools\spec_test.txt"); zeilen = []
def log(s): print(s); zeilen.append(s)

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")[:20000]
m = NativeCausalLM(MODELL); m.progress = lambda *a: None; m.load(); e = m.eng
if "3.5" in MODELL and not hasattr(e, "_seek"): log("WARNUNG: Qwen3.5-Ordner, aber nicht die Qwen3.5-Engine")
log(f"Engine {type(e).__name__}, Modell {MODELL}, Gewichte {'int8' if e.q8 else 'bf16'}, "
    f"KV {'fp16' if getattr(e, 'kv16', False) else 'fp32'}, kleine Bloecke: {getattr(e, 'small_kernel', '?')}, Schreiben: {getattr(e, 'dec_kernel', '?')}")

sysm = "Du bist AURA. Antworte auf Deutsch, ausfuehrlich und strukturiert, gestuetzt auf den Text. Zitiere wichtige Stellen woertlich."
prompt = (f"<|im_start|>system\n{sysm}<|im_end|>\n<|im_start|>user\nFasse den folgenden Text ausfuehrlich zusammen "
          f"und nenne die wichtigsten Anforderungen, Termine und Betraege.\n\n{text}<|im_end|>\n<|im_start|>assistant\n")
ids = m.tok.encode(prompt)[: e.maxT - 600]

# --- B) echte gierige Antwort erzeugen
t0 = time.perf_counter(); logits = e.prefill(ids); t1 = time.perf_counter()
out, pos = [], len(ids)
while len(out) < 400:
    tid = logits.index(max(logits))
    if tid in m.stop_ids: break
    out.append(tid); logits = e.forward([tid], pos); pos += 1
t2 = time.perf_counter()
s_tok = (t2 - t1) / max(1, len(out))
log(f"Eingabe {len(ids)} Tokens in {t1 - t0:.0f} s; Antwort {len(out)} Tokens, {s_tok * 1000:.0f} ms/Token")

# --- A) Zeiten fuer T Tokens am Ende desselben Kontexts
def timed(fn, reps=3):
    fn(); e.g.sync(); a = time.perf_counter()
    for _ in range(reps): fn()
    e.g.sync(); return (time.perf_counter() - a) / reps
w = e.w[0].get("mlp.gate_proj", e.w[0].get("gate_proj"))
zeit = {}
for T in (1, 2, 4, 8, 12, 16):
    try: lin = timed(lambda: e._lin(e.X, w, e.Gt, T, e.H, e.I)) if w is not None else float("nan")
    except Exception: lin = float("nan")
    fw = timed(lambda: e.forward(out[:T] if len(out) >= T else [out[0]] * T, len(ids), want_logits=False), 2)
    zeit[T] = fw
    log(f"T={T:2d}: gate_proj {lin * 1000:6.2f} ms | Schichten {fw * 1000:6.0f} ms ({fw / zeit[1]:.2f}x von T=1)")
lmh = timed(lambda: e.forward([out[0]], len(ids)), 2) - zeit[1]
log(f"Ausgabeschicht 1 Zeile: {lmh * 1000:.0f} ms (bei T Zeilen mit mvt8 geschaetzt aehnlich)")

# --- Simulation Prompt Lookup (n-Gramm 3, sonst 2), K Vorschlaege
def sim(K):
    ctx, i, schritte = list(ids), 0, 0
    while i < len(out):
        vor = []
        for n in (3, 2):
            if len(ctx) < n: continue
            tail = ctx[-n:]
            for j in range(len(ctx) - n - 1, -1, -1):
                if ctx[j:j + n] == tail: vor = ctx[j + n: j + n + K]; break
            if vor: break
        a = 0
        while a < len(vor) and i + a < len(out) and vor[a] == out[i + a]: a += 1
        neu = out[i: i + a + 1]; ctx += neu; i += len(neu); schritte += 1
    return schritte
for K in (2, 4, 8):
    st = sim(K); T = K + 1; T = min((t for t in zeit if t >= T), default=16)
    t_spec = st * (zeit[T] + lmh); t_norm = len(out) * (zeit[1] + lmh)
    log(f"K={K}: {len(out)} Tokens in {st} Schritten ({len(out) / st:.2f} Tok/Schritt) -> geschaetzt {t_norm / t_spec:.2f}x schneller")
OUT.write_text("\n".join(zeilen), encoding="utf-8"); m.unload()
print(f"\n-> {OUT}")
