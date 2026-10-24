# tools/prof_test.py - misst, wohin die Rechenzeit beim Einlesen, beim Geruest und beim Schreiben geht. Version 20261024v114 (v114: Qwen3.5-Engine automatisch, Modell aus Einstellungen)
# Aendert nichts. AURA vorher schliessen (sonst teilen sich zwei Programme die GPU).
# Aufruf:  py tools\prof_test.py            (Modell aus data\settings.json, z.B. Qwen3.5-4B)
#          py tools\prof_test.py Qwen3-4B   (anderes Modell)
# Ergebnis: C:\aura\tools\prof_test.txt  (dauert etwa 5-8 Minuten)
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from aura.config import load_settings

S = load_settings()
MODELL = sys.argv[1] if len(sys.argv) > 1 else str(S.get("llm", "Qwen3-4B")).split(":")[-1]
from aura.llm.qwen35 import Qwen35Engine as Engine                 # v118: nur noch Qwen3.5
OUT = ROOT / "tools" / "prof_test.txt"
L = []
def log(s): print(s, flush=True); L.append(s)

t0 = time.perf_counter()
INT8, KV16 = bool(S.get("llm_int8", False)), bool(S.get("llm_kv16", True))
e = Engine(ROOT / "models" / MODELL, progress=lambda *a: None, maxT=12288, int8=INT8, kv16_on=KV16)
try: b = e.self_check(lambda m: None) or {}
except Exception as ex: b = {}; print(f"self_check: {ex}")
log(f"Engine {type(e).__name__}, Modell {MODELL}, Gewichte {'int8' if e.q8 else 'bf16'}, KV {'fp16' if e.kv16 else 'fp32'}, geladen in {time.perf_counter() - t0:.0f} s")
lk = getattr(e, "lin_kernel", "?")
log(f"Kernel: Matrix {lk} ({b.get('gflops_' + lk, 0):.0f} GFLOPS), Attention Einlesen "
    f"{getattr(e, 'pre_kernel', getattr(e, 'attn_kernel', '?'))}, Attention Schreiben {getattr(e, 'dec_kernel', '?')}")
if "pre_gemm" in b: log(f"Selbsttest Einlesen ab Position {b['pre_pos']}: v2 {b['pre_v2'] * 1000:.0f} ms, gemm {b['pre_gemm'] * 1000:.0f} ms, "
                      f"Abweichung {b['pre_diff']:.1e}")
if "small_mt" in b: log(f"Selbsttest 10 Tokens: {lk} {b['small_v2'] * 1000:.1f} ms, mt {b['small_mt'] * 1000:.1f} ms, "
                        f"Abweichung {b['small_diff']:.1e} -> {getattr(e, 'small_kernel', '?')}")
for was, key, wahl in (("Schreiben", "dec_", getattr(e, "dec_kernel", "?")), ("Attention 10 Tokens", "sattn_", getattr(e, "small_attn", "?"))):
    vs = [k[len(key):] for k in b if k.startswith(key) and not k.startswith(key + "diff") and k != key + "pos"]
    if vs: log(f"Selbsttest {was}: " + ", ".join(f"{v} {b[key + v] * 1000:.1f} ms" for v in vs) + f" -> {wahl}")
if "lin8_q44" in b: log(f"Selbsttest Einlesen int8 (512 Tokens): q44 {b['lin8_q44'] * 1000:.0f} ms, v8 {b['lin8_v8'] * 1000:.0f} ms, "
                        f"Abweichung {b['lin8_diff']:.1e} -> {lk}")
if "small8_cands" in b: log("Selbsttest 10 Tokens int8 (gate_proj): " + ", ".join(f"{k} {b['small8_' + k] * 1000:.1f} ms" for k in b["small8_cands"])
                            + f"; 1 Token {b['mv8_1'] * 1000:.1f} ms -> {e.small8}")
if "attn2_diff" in b: log(f"Selbsttest Attention (8192 Pos.): 1 Token attn256 {b['dec1_attn256'] * 1000:.2f} ms, attn2 {b['dec1_attn2'] * 1000:.2f} ms; "
                          f"10 Tokens attn256 {b['sattn10_attn256'] * 1000:.1f} ms, attn2 {b['sattn10_attn2'] * 1000:.1f} ms, "
                          f"Abweichung {b['attn2_diff']:.1e} -> {e.attn_kernel}")
log("Spalten: Zeit je Aufruf, Tokens/s, Anteile je Teil (bei Qwen3.5 inkl. DeltaNet, falls gemessen)")

Q35 = hasattr(e, "_seek")
def vorbereiten(pos):                                                # Qwen3.5: rekurrenter Zustand braucht echte Tokens bis pos
    if not Q35: return
    if pos == 0: e.kv_ids = []; e._reset_state(); return
    if e.snap and e.snap[0] == pos and e.kv_ids[:pos] == e.snap[1]: return
    print(f"  (lese {pos} Tokens Kontext ein ...)", flush=True); e.prefill(list(range(2000, 2000 + pos)))

def mess(name, T, pos, reps):
    ids = list(range(1000, 1000 + T)); vorbereiten(pos)
    if T < 64: e.forward(ids, pos); e.g.sync()                       # kurz: einmal aufwaermen
    t = time.perf_counter()
    for _ in range(reps): e.forward(ids, pos)
    e.g.sync(); dt = (time.perf_counter() - t) / reps
    e.g.sync(); e.prof = {"_t": time.perf_counter()}                 # Aufteilung (wartet nach jedem Schritt)
    e.forward(ids, pos); e.g.sync()
    p = {k: v for k, v in e.prof.items() if k != "_t"}; e.prof = None; s = sum(p.values()) or 1
    log(f"{name:<28} T={T:<4} Pos={pos:<5} {dt * 1000:8.0f} ms {T / dt:7.1f} Tok/s   "
        + "  ".join(f"{k} {v / s * 100:3.0f}%" for k, v in sorted(p.items(), key=lambda x: -x[1])))

mess("Einlesen, Anfang", 512, 0, 1)                                 # aufsteigende Positionen: Kontext wird weiterverwendet
mess("Schreiben, kurzer Kontext", 1, 300, 5)
mess("Einlesen, Mitte", 512, 4096, 1)
mess("Einlesen, spaet", 512, 8192, 1)
mess("Geruest (10 Tokens)", 10, 9000, 3)
mess("Geruest (20 Tokens)", 20, 9000, 3)
mess("Schreiben, langer Kontext", 1, 9000, 5)
e.close()
OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"\nFertig: {OUT}")
