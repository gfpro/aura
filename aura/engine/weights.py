# engine/weights.py — Version 20261005v01  (AURA)
# Schritt 2: Gewichte von multilingual-e5-large laden (reines Python, mmap, keine Kopie in den RAM)
# und die Embedding-Schicht auf der CPU rechnen. Test:  py engine\weights.py

import json, math, mmap, struct, sys, time
from array import array
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "multilingual-e5-large"
_DT = {"F32": ("f", 4), "F16": ("e", 2)}

class SafeTensors:
    """Liest das safetensors-Format: 8 Byte Header-Laenge, JSON-Header, dann Rohdaten."""
    def __init__(self, path):
        self.f = open(path, "rb")
        self.mm = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        n = struct.unpack("<Q", self.mm[:8])[0]
        hdr = json.loads(self.mm[8:8 + n]); hdr.pop("__metadata__", None)
        self.base = 8 + n
        # Praefix "roberta." o.ae. entfernen, damit Namen einheitlich sind
        self.t = {k.split("roberta.", 1)[-1]: v for k, v in hdr.items()}
    def names(self): return list(self.t)
    def shape(self, k): return self.t[k]["shape"]
    def dtype(self, k): return self.t[k]["dtype"]
    def raw(self, k):
        a, b = self.t[k]["data_offsets"]
        return memoryview(self.mm)[self.base + a: self.base + b]
    def floats(self, k, start=0, count=None):
        """Ausschnitt als array('f') (Elemente start..start+count)."""
        code, size = _DT[self.dtype(k)]
        mv = self.raw(k)
        end = len(mv) // size if count is None else start + count
        arr = array(code); arr.frombytes(mv[start * size: end * size])
        return arr if code == "f" else array("f", arr)

def expected(cfg):
    L, H, I = cfg["num_hidden_layers"], cfg["hidden_size"], cfg["intermediate_size"]
    e = {"embeddings.word_embeddings.weight": [cfg["vocab_size"], H],
         "embeddings.position_embeddings.weight": [cfg["max_position_embeddings"], H],
         "embeddings.token_type_embeddings.weight": [cfg["type_vocab_size"], H],
         "embeddings.LayerNorm.weight": [H], "embeddings.LayerNorm.bias": [H]}
    for l in range(L):
        p = f"encoder.layer.{l}."
        for m in ("query", "key", "value"):
            e[p + f"attention.self.{m}.weight"] = [H, H]; e[p + f"attention.self.{m}.bias"] = [H]
        e[p + "attention.output.dense.weight"] = [H, H]; e[p + "attention.output.dense.bias"] = [H]
        e[p + "attention.output.LayerNorm.weight"] = [H]; e[p + "attention.output.LayerNorm.bias"] = [H]
        e[p + "intermediate.dense.weight"] = [I, H]; e[p + "intermediate.dense.bias"] = [I]
        e[p + "output.dense.weight"] = [H, I]; e[p + "output.dense.bias"] = [H]
        e[p + "output.LayerNorm.weight"] = [H]; e[p + "output.LayerNorm.bias"] = [H]
    return e

class Model:
    def __init__(self, model_dir=MODEL_DIR):
        self.cfg = json.loads((Path(model_dir) / "config.json").read_text(encoding="utf-8"))
        self.st = SafeTensors(Path(model_dir) / "model.safetensors")
        self.H = self.cfg["hidden_size"]; self.eps = self.cfg.get("layer_norm_eps", 1e-5)
        self.pad = self.cfg.get("pad_token_id", 1)
        self._ln_w = self.st.floats("embeddings.LayerNorm.weight")
        self._ln_b = self.st.floats("embeddings.LayerNorm.bias")
        self._type0 = self.st.floats("embeddings.token_type_embeddings.weight", 0, self.H)

    def embed(self, ids):
        """Embedding-Schicht fuer eine Token-Folge: Wort + Position + Typ, dann LayerNorm.
        XLM-R zaehlt Positionen ab pad_token_id+1 (=2). Rueckgabe: array('f') len(ids)*H."""
        H = self.H; out = array("f")
        for i, tid in enumerate(ids):
            w = self.st.floats("embeddings.word_embeddings.weight", tid * H, H)
            p = self.st.floats("embeddings.position_embeddings.weight", (self.pad + 1 + i) * H, H)
            x = [w[k] + p[k] + self._type0[k] for k in range(H)]
            mu = sum(x) / H; var = sum((v - mu) ** 2 for v in x) / H; r = 1.0 / math.sqrt(var + self.eps)
            out.extend((x[k] - mu) * r * self._ln_w[k] + self._ln_b[k] for k in range(H))
        return out

def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    t0 = time.perf_counter(); m = Model(); t1 = time.perf_counter()
    c = m.cfg
    print(f"Modell: {c.get('model_type')} | {c['num_hidden_layers']} Schichten | {c['hidden_size']} dim | "
          f"{c['num_attention_heads']} Koepfe | FFN {c['intermediate_size']} | Vokabular {c['vocab_size']}")
    print(f"Geoeffnet in {t1 - t0:.2f} s")
    exp = expected(c); have = set(m.st.names())
    missing = [k for k in exp if k not in have]
    wrong = [k for k in exp if k in have and m.st.shape(k) != exp[k]]
    extra = sorted(have - set(exp))
    params = sum(math.prod(m.st.shape(k)) for k in have)
    print(f"Tensoren: {len(have)} | Parameter: {params / 1e6:.0f} Mio | Datentypen: {sorted({m.st.dtype(k) for k in have})}")
    print(f"  [{'OK' if not missing else 'FEHLER'}] fehlend: {len(missing)} {missing[:3]}")
    print(f"  [{'OK' if not wrong else 'FEHLER'}] falsche Form: {len(wrong)} {wrong[:3]}")
    print(f"  [INFO] zusaetzlich (werden nicht gebraucht): {extra[:4]}")
    bad = 0                                           # Stichprobe auf NaN/Inf
    for k in list(exp)[::25]:
        a = m.st.floats(k, 0, min(4096, math.prod(m.st.shape(k))))
        bad += sum(1 for v in a if v != v or abs(v) == float("inf"))
    print(f"  [{'OK' if not bad else 'FEHLER'}] NaN/Inf in Stichprobe: {bad}")
    try:
        from tokenizer import XLMRTokenizer
        ids = XLMRTokenizer().encode("passage: Der Zuschlag für den Vertrag wurde erteilt.")
        t2 = time.perf_counter(); e = m.embed(ids); t3 = time.perf_counter()
        H = m.H; row = e[H:2 * H]
        mu = sum(row) / H; sd = math.sqrt(sum((v - mu) ** 2 for v in row) / H)
        print(f"Embedding-Schicht: {len(ids)} Tokens in {t3 - t2:.2f} s | Token 1: Mittel {mu:+.4f}, Streuung {sd:.4f}")
        print(f"  erste Werte: {[round(v, 4) for v in row[:6]]}")
    except Exception as ex:
        print(f"  [FEHLER] Embedding-Test: {ex}")
    input("\nEnter zum Schliessen...")

if __name__ == "__main__":
    main()
