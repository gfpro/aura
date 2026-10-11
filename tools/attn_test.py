# tools/attn_test.py — v42: Schreibtempo mit v2- und Split-K-Attention bei kurzem und langem Kontext messen.
#   py tools\attn_test.py                 (Modell models\Qwen3-4B; AURA vorher schliessen)
#   py tools\attn_test.py Qwen3-8B-int8   (spaeter)          -> Ausgabe auch in tools\attn_test.txt
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path[:0] = [str(ROOT), str(ROOT / "vendor")]
OUT = Path(__file__).with_suffix(".txt"); lines = []
def say(*a):
    t = " ".join(str(x) for x in a); print(t); lines.append(t); OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
def main():
    from aura import VERSION
    from aura.llm.qwen import Qwen3Engine
    name = sys.argv[1] if len(sys.argv) > 1 else "Qwen3-4B"
    say(f"AURA {VERSION} · Modell {name}")
    t0 = time.perf_counter()
    e = Qwen3Engine(ROOT / "models" / name, progress=lambda m, *a: None, maxT=10240)
    say(f"geladen in {time.perf_counter() - t0:.0f} s")
    b = e.self_check(say)
    say(f"Selbsttest: Schreiben mit {e.dec_kernel} (Abweichung {b.get('dec_diff', -1):.1e})")
    for pos in (300, 2000, 5000, 9000):
        for k in ("v2", "split"):
            e.dec_kernel = k; e.forward([1000], pos); e.g.sync(); t = time.perf_counter()
            for i in range(5): e.forward([1000], pos + i)
            e.g.sync(); dt = (time.perf_counter() - t) / 5
            say(f"  Kontext {pos:5d}  {k:5s}  {dt * 1000:7.0f} ms/Token  = {1 / dt:4.2f} Tokens/s")
    e.close()
if __name__ == "__main__":
    try: main()
    except Exception:
        import traceback; say(traceback.format_exc())
    finally: input("\nEnter zum Schliessen...")
