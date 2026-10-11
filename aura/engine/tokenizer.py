# engine/tokenizer.py — Version 20261005v02  (AURA)
# Reiner-Python-Tokenizer fuer multilingual-e5-large (XLM-R, Unigram/SentencePiece).
# Liest models\multilingual-e5-large\tokenizer.json. Keine Abhaengigkeiten.

import json, re, base64, struct, unicodedata
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / "models" / "multilingual-e5-large" / "tokenizer.json"

class Precompiled:
    """Exakte Nachbildung des SentencePiece-'Precompiled'-Normalizers (nmt_nfkc):
    Double-Array-Trie (Darts) ueber UTF-8-Bytes + Pool mit Ersatzstrings."""
    def __init__(self, b64):
        blob = base64.b64decode(b64)
        n = struct.unpack_from("<I", blob, 0)[0]
        self.trie = struct.unpack_from("<%dI" % (n // 4), blob, 4)
        self.pool = blob[4 + n:]
    def _prefix(self, key, start):
        """Laengster Treffer ab key[start]: (laenge, ersatz_bytes) oder None."""
        t = self.trie; u = t[0]; pos = (u >> 10) << ((u & 512) >> 6); best = None
        for i in range(start, len(key)):
            c = key[i]; pos ^= c; u = t[pos]
            if (u & 0x800000FF) != c: break
            pos ^= (u >> 10) << ((u & 512) >> 6)
            if (u >> 8) & 1:
                v = t[pos] & 0x7FFFFFFF
                best = (i + 1 - start, self.pool[v:self.pool.index(0, v)])
        return best
    def _one(self, s):
        b = s.encode("utf-8"); m = self._prefix(b, 0)
        return m[1].decode("utf-8") if m and m[0] == len(b) else None
    def __call__(self, text):
        # Wie HF: Graphem (Grundzeichen + Kombinationszeichen) zuerst als Ganzes ersetzen,
        # z.B. "u"+U+0308 -> "ü" (zerlegte Umlaute aus Mac-/PDF-Texten), sonst zeichenweise.
        out, i, n = [], 0, len(text)
        while i < n:
            j = i + 1
            while j < n and unicodedata.combining(text[j]): j += 1
            g = text[i:j]
            r = self._one(g) if j - i > 1 and len(g.encode("utf-8")) < 6 else None
            if r is None:
                r = "".join(x if (y := self._one(x)) is None else y for x in g)
            out.append(r); i = j
        return "".join(out)

class XLMRTokenizer:
    def __init__(self, path=DEFAULT):
        j = json.loads(Path(path).read_text(encoding="utf-8"))
        m = j["model"]
        if m.get("type") != "Unigram": raise ValueError("Erwarte Unigram-Modell, gefunden: %s" % m.get("type"))
        vocab = m["vocab"]
        special = {t["content"] for t in j.get("added_tokens", [])}
        self.scores = [s for _, s in vocab]
        # Spezialtokens (<s>, </s>, <unk>, ...) duerfen nicht als Textstueck gematcht werden
        self.vocab = {p: i for i, (p, _) in enumerate(vocab) if p not in special}
        self.ids = {p: i for i, (p, _) in enumerate(vocab)}
        self.unk = m.get("unk_id", 3)
        self.unk_score = min(self.scores) - 10.0      # wie HF tokenizers (kUnkPenalty)
        self.maxlen = max(len(p) for p in self.vocab)
        self.bos, self.eos = self.ids["<s>"], self.ids["</s>"]
        self.pieces = [p for p, _ in vocab]
        norm = j.get("normalizer") or {}
        if norm.get("type") == "Sequence":
            norm = next((x for x in norm.get("normalizers", []) if x.get("type") == "Precompiled"), {})
        self._norm = Precompiled(norm["precompiled_charsmap"]) if norm.get("precompiled_charsmap") else None
        self._cache = {}

    def normalize(self, text):
        return self._norm(text) if self._norm else text

    def _word(self, w):
        hit = self._cache.get(w)
        if hit is not None: return hit
        n = len(w); NEG = -1e30
        best = [NEG] * (n + 1); back = [None] * (n + 1); best[0] = 0.0
        for i in range(n):
            bi = best[i]
            if bi == NEG: continue
            single = False
            for j in range(i + 1, min(n, i + self.maxlen) + 1):
                pid = self.vocab.get(w[i:j])
                if pid is None: continue
                if j == i + 1: single = True
                s = bi + self.scores[pid]
                if s > best[j]: best[j] = s; back[j] = (i, pid)
            if not single:                                  # unbekanntes Zeichen -> <unk>
                s = bi + self.unk_score
                if s > best[i + 1]: best[i + 1] = s; back[i + 1] = (i, self.unk)
        out, j = [], n
        while j > 0:
            i, pid = back[j]; out.append(pid); j = i
        out.reverse()
        fused = []                                          # aufeinanderfolgende <unk> verschmelzen
        for t in out:
            if not (t == self.unk and fused and fused[-1] == self.unk): fused.append(t)
        if len(self._cache) < 200000: self._cache[w] = fused
        return fused

    def encode(self, text, max_len=512):
        ids = []
        for w in self.normalize(text).split():
            ids.extend(self._word("\u2581" + w))
        return [self.bos] + ids[:max_len - 2] + [self.eos]

    def tokens(self, text):
        return [self.pieces[i] for i in self.encode(text)]
