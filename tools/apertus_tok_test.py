# tools/apertus_tok_test.py — Version 20261103v164: Prueft AURAs Tokenizer gegen Referenzwerte (tokenizers-Bibliothek).
# Aufruf in C:\aura:  py tools\apertus_tok_test.py models\<Apertus-Ordner>
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aura.llm.bpe_tokenizer import BPETokenizer
t0 = time.perf_counter(); tok = BPETokenizer(Path(sys.argv[1]) / "tokenizer.json"); print(f"Tokenizer geladen in {time.perf_counter() - t0:.1f} s")
ref = json.loads((Path(__file__).parent / "apertus_tok_ref.json").read_text(encoding="utf-8"))
bad = 0
for r in ref:
    ids = tok.encode(r["text"])
    if ids != r["ids"]:
        bad += 1; print("ABWEICHUNG:", repr(r["text"][:70])); print("  AURA:", ids[:15]); print("  Soll:", r["ids"][:15])
print(f"{len(ref) - bad} von {len(ref)} gleich"); print("OK" if not bad else "FEHLER")
