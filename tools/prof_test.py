# tools/prof_test.py - misst, wohin die Rechenzeit beim Einlesen, beim Geruest und beim Schreiben geht. Version 20261014v86 (v86: 8 Bit und KV fp16 aus den Einstellungen, neue Split-Varianten)
# Aendert nichts. AURA vorher schliessen (sonst teilen sich zwei Programme die GPU).
# Aufruf:  py tools\prof_test.py            (Qwen3-4B)
#          py tools\prof_test.py Qwen3-8B   (spaeter, sobald 8B laeuft)
# Ergebnis: C:\aura\tools\prof_test.txt  (dauert etwa 5-8 Minuten)
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from aura.llm.qwen import Qwen3Engine
from aura.config import load_settings

MODELL = sys.argv[1] if len(sys.argv) > 1 else "Qwen3-4B"
OUT = ROOT / "tools" / "prof_test.txt"
L = []
def log(s): print(s, flush=True); L.append(s)

t0 = time.perf_counter()
S = load_settings(); INT8, KV16 = bool(S.get("llm_int8", False)), bool(S.get("llm_kv16", True))
e = Qwen3Engine(ROOT / "models" / MODELL, progress=lambda *a: None, maxT=12288, int8=INT8, kv16_on=KV16)
b = e.self_check(lambda m: None)
log(f"Modell {MODELL}, Gewichte {'int8' if e.q8 else 'bf16'}, KV {'fp16' if e.kv16 else 'fp32'}, geladen in {time.perf_counter() - t0:.0f} s")
log(f"Kernel: Matrix {e.lin_kernel} ({b['gflops_' + e.lin_kernel]:.0f} GFLOPS), Attention Einlesen "
    f"{getattr(e, 'pre_kernel', e.attn_kernel)}, Attention Schreiben {e.dec_kernel}")
if "pre_gemm" in b: log(f"Selbsttest Einlesen ab Position {b['pre_pos']}: v2 {b['pre_v2'] * 1000:.0f} ms, gemm {b['pre_gemm'] * 1000:.0f} ms, "
                      f"Abweichung {b['pre_diff']:.1e}")
if "small_mt" in b: log(f"Selbsttest 10 Tokens: {e.lin_kernel} {b['small_v2'] * 1000:.1f} ms, mt {b['small_mt'] * 1000:.1f} ms, "
                        f"Abweichung {b['small_diff']:.1e} -> {e.small_kernel}")
for was, key, wahl in (("Schreiben", "dec_", e.dec_kernel), ("Attention 10 Tokens", "sattn_", e.small_attn)):
    vs = [k[len(key):] for k in b if k.startswith(key) and not k.startswith(key + "diff") and k != key + "pos"]
    if vs: log(f"Selbsttest {was}: " + ", ".join(f"{v} {b[key + v] * 1000:.1f} ms" for v in vs) + f" -> {wahl}")
log("Spalten: Zeit je Aufruf, Tokens/s, Anteil linear (Gewichte) / attention / andere")

def mess(name, T, pos, reps):
    ids = list(range(1000, 1000 + T))
    if T < 64: e.forward(ids, pos); e.g.sync()                       # kurz: einmal aufwaermen
    t = time.perf_counter()
    for _ in range(reps): e.forward(ids, pos)
    e.g.sync(); dt = (time.perf_counter() - t) / reps
    e.g.sync(); e.prof = {"_t": time.perf_counter()}                 # Aufteilung (wartet nach jedem Schritt)
    e.forward(ids, pos); e.g.sync()
    p = {k: v for k, v in e.prof.items() if k != "_t"}; e.prof = None; s = sum(p.values()) or 1
    log(f"{name:<28} T={T:<4} Pos={pos:<5} {dt * 1000:8.0f} ms {T / dt:7.1f} Tok/s   "
        + "  ".join(f"{k} {p.get(k, 0) / s * 100:3.0f}%" for k in ("linear", "attention", "andere")))

mess("Einlesen, Anfang", 512, 0, 1)
mess("Einlesen, Mitte", 512, 4096, 1)
mess("Einlesen, spaet", 512, 8192, 1)
mess("Geruest (10 Tokens)", 10, 9000, 3)
mess("Geruest (20 Tokens)", 20, 9000, 3)
mess("Schreiben, kurzer Kontext", 1, 300, 5)
mess("Schreiben, langer Kontext", 1, 9000, 5)
e.close()
OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"\nFertig: {OUT}")
