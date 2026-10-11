# tools/speed_test.py — Version 20261006v02  (AURA)
# Misst das Sprachmodell auf diesem Rechner: alte vs. neue GPU-Kernels (Ergebnis + Tempo),
# dann Einlesen von 1'000 Tokens mit Aufteilung nach Rechenschritten.
# Aufruf:  py tools\speed_test.py [models\Qwen3-4B]      (AURA vorher schliessen)
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path[:0] = [str(ROOT), str(ROOT / "vendor")]
from aura.llm.bpe_tokenizer import BPETokenizer
from aura.llm import qwen as Q

MODEL = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "models" / "Qwen3-4B"

def run_prefill(eng, ids, lin, attn, profile):
    eng.lin_kernel, eng.attn_kernel = lin, attn
    eng.prof = {"_t": time.perf_counter()} if profile else None
    t0 = time.perf_counter(); eng.prefill(ids); dt = time.perf_counter() - t0
    prof = eng.prof; eng.prof = None
    if prof: prof.pop("_t")
    return dt, prof

def main():
    tok = BPETokenizer(MODEL / "tokenizer.json")
    print("=== Modell laden ===")
    t0 = time.perf_counter()
    eng = Q.Qwen3Engine(MODEL, progress=lambda m, *a: print("\r  " + m + " " * 10, end=""))
    print(f"\n  geladen in {time.perf_counter() - t0:.0f} s")

    print("\n=== 1: Kernel-Selbsttest (alt v1 / neu v2) ===")
    b = eng.self_check()
    for v in b["lin_names"]:
        ok = "OK" if b["diff_" + v] < 1e-3 else "FEHLER"
        print(f"  Matrix {v:4}: {b['lin_' + v] * 1000:6.0f} ms ({b['gflops_' + v]:4.0f} GFLOPS) | Abweichung {b['diff_' + v]:.1e} {ok}")
    print(f"  Attention: v1 {b['attn_v1'] * 1000:6.0f} ms | v2 {b['attn_v2'] * 1000:6.0f} ms "
          f"| Abweichung {b['attn_diff']:.1e} {'OK' if b['attn_diff'] < 1e-3 else 'FEHLER'}")
    best = (eng.lin_kernel, eng.attn_kernel)
    print(f"  -> gewaehlt: Matrix {best[0]}, Attention {best[1]}")

    print("\n=== 2: Quellen einlesen (1'024 Tokens) ===")
    ids = tok.encode("Der Zuschlag für die Weiterentwicklung GEVER wurde erteilt. " * 120)[:1024]
    run_prefill(eng, ids[:64], *best, False)                                 # Aufwaermen
    old, _ = run_prefill(eng, ids, "v1", "v1", False)
    new, _ = run_prefill(eng, ids, *best, False)
    print(f"  alt (v1/v1): {old:5.1f} s ({len(ids) / old:4.0f} Tokens/s)")
    print(f"  neu ({best[0]}/{best[1]}): {new:5.1f} s ({len(ids) / new:4.0f} Tokens/s)  -> {old / new:.1f}x")
    _, prof = run_prefill(eng, ids, *best, True)
    tot = sum(prof.values())
    print("  Aufteilung (mit Messpausen): " + "  ".join(f"{k} {v:.1f} s ({v * 100 / tot:.0f} %)" for k, v in sorted(prof.items(), key=lambda x: -x[1])))

    print("\n=== 3: Schreiben ===")
    logits = eng.prefill(ids[:200]); pos = 200; t0 = time.perf_counter(); n = 30
    for _ in range(n): logits = eng.forward([Q.sample(logits, 0)], pos); pos += 1
    dt = time.perf_counter() - t0
    print(f"  {n} Tokens in {dt:.1f} s = {n / dt:.2f} Tokens/s")

if __name__ == "__main__":
    try: main()
    except Exception:
        import traceback; traceback.print_exc()
    input("\nEnter zum Schliessen...")
