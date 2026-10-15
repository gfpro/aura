# tools/q35_test.py — Version 20261015v88 (AURA)
# Test der Qwen3.5-Engine ohne Oberflaeche (AURA vorher schliessen).
#   py tools\q35_test.py C:\aura\models\Qwen3.5-4B          (bf16)
#   py tools\q35_test.py C:\aura\models\Qwen3.5-4B --int8   (8 Bit)
# Ausgabe zusaetzlich in tools\q35_test.txt
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
OUT = ROOT / "tools" / "q35_test.txt"; lines = []
def log(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); lines.append(s)
    OUT.write_text("\n".join(lines), encoding="utf-8")

from aura.llm.bpe_tokenizer import BPETokenizer, StreamDecoder
from aura.llm.qwen35 import Qwen35Engine

args = [a for a in sys.argv[1:] if not a.startswith("--")]
d = Path(args[0]) if args else ROOT / "models" / "Qwen3.5-4B"
int8 = "--int8" in sys.argv
log(f"Modell {d}, {'int8' if int8 else 'bf16'}")
t0 = time.perf_counter()
tok = BPETokenizer(d / "tokenizer.json"); log(f"Tokenizer {time.perf_counter() - t0:.1f} s")
t0 = time.perf_counter()
eng = Qwen35Engine(d, progress=lambda *a: None, maxT=8192, int8=int8)
log(f"Geladen {time.perf_counter() - t0:.0f} s")
b = eng.self_check(log)
stop = {tok.added[s] for s in ("<|im_end|>", "<|endoftext|>") if s in tok.added}

def ask(q, n=60):
    ids = tok.encode(f"<|im_start|>user\n{q}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n")
    t1 = time.perf_counter(); lg = eng.prefill(ids); t2 = time.perf_counter()
    dec, out, pos, k = StreamDecoder(tok), "", len(ids), 0
    while k < n:
        tid = lg.index(max(lg))
        if tid in stop: break
        out += dec.push(tid); lg = eng.forward([tid], pos); pos += 1; k += 1
    t3 = time.perf_counter()
    log(f"\nFRAGE: {q}\nANTWORT: {out.strip()}\n  Einlesen {len(ids)} Tok in {t2 - t1:.1f} s, Schreiben {k} Tok in {t3 - t2:.1f} s "
        f"({k / max(t3 - t2, 1e-9):.1f} Tok/s), Cache {eng.reused}")
    return ids, out

ask("Was ist die Hauptstadt der Schweiz? Antworte in einem Satz.")
ask("Nenne drei Farben, nur durch Komma getrennt.", 30)
ids, a1 = ask("Erklaere in zwei Saetzen, was ein Verfahrensentscheid im oeffentlichen Beschaffungswesen ist.")
# gleiche Frage nochmals: Cache + Ruecksprung (Zustand aus Schnappschuss) muessen dieselbe Antwort geben
_, a2 = ask("Erklaere in zwei Saetzen, was ein Verfahrensentscheid im oeffentlichen Beschaffungswesen ist.")
log("\nRuecksprung-Test:", "OK (gleiche Antwort)" if a1 == a2 else "ABWEICHUNG")
# Lange Eingabe: Tempo bei Kontext ~4000
long = "Dies ist ein Fuelltext ueber Beschaffung, Vertraege und Fristen. " * 300
ask(long + "\nWorum ging es im Text? Ein Satz.", 30)
eng.close(); log("\nFertig.")
