# aura/llm/bpe_tokenizer.py — Version 20261015v88  (AURA)
#   v88: \p{X} allgemein uebersetzt (auch \p{M} fuer Qwen3.5), innerhalb und ausserhalb von [...]
# Reiner-Python-Tokenizer fuer Byte-Level-BPE-Modelle (Qwen2/Qwen3, Llama-3-Stil).
# Liest tokenizer.json. Keine Abhaengigkeiten.

import json, re, unicodedata
from pathlib import Path

def _bytes_to_unicode():
    """GPT-2-Abbildung: jedes Byte -> ein druckbares Unicode-Zeichen."""
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]; n = 0
    for b in range(256):
        if b not in bs: bs.append(b); cs.append(256 + n); n += 1
    return dict(zip(bs, map(chr, cs)))

_CLASS_CACHE = {}
def _unicode_class(prefix):
    """Zeichenklasse fuer alle Codepunkte, deren Kategorie mit prefix beginnt ('L' oder 'N'),
    als Regex-Bereichsliste - ersetzt \\p{L} / \\p{N}, die Pythons re nicht kennt."""
    if prefix in _CLASS_CACHE: return _CLASS_CACHE[prefix]
    parts, start, prev = [], None, None
    for cp in range(0x110000):
        hit = unicodedata.category(chr(cp)).startswith(prefix)
        if hit and start is None: start = cp
        if not hit and start is not None:
            parts.append((start, cp - 1)); start = None
    if start is not None: parts.append((start, 0x10FFFF))
    esc = lambda c: ("\\" + chr(c)) if chr(c) in "\\]^-[" else chr(c)
    s = "".join(esc(a) if a == b else esc(a) + "-" + esc(b) for a, b in parts)
    _CLASS_CACHE[prefix] = s
    return s

def _translate_regex(pat):
    """Ersetzt \\p{L}, \\p{N}, \\p{M} ... durch Bereichslisten (Pythons re kennt \\p nicht)."""
    out, i, inside = [], 0, False
    while i < len(pat):
        ch = pat[i]
        if ch == "\\":
            if pat[i + 1:i + 3] == "p{":
                j = pat.index("}", i); r = _unicode_class(pat[i + 3:j])
                out.append(r if inside else f"[{r}]"); i = j + 1; continue
            out.append(pat[i:i + 2]); i += 2; continue
        if ch == "[" and not inside: inside = True
        elif ch == "]" and inside: inside = False
        out.append(ch); i += 1
    return re.compile("".join(out))

class BPETokenizer:
    def __init__(self, path):
        j = json.loads(Path(path).read_text(encoding="utf-8"))
        m = j["model"]
        if m.get("type") != "BPE": raise ValueError("Erwarte BPE-Modell")
        self.vocab = m["vocab"]
        merges = m["merges"]
        self.ranks = {(tuple(x) if isinstance(x, list) else tuple(x.split(" ", 1))): i for i, x in enumerate(merges)}
        self.added = {t["content"]: t["id"] for t in j.get("added_tokens", [])}
        self.special_ids = {t["id"] for t in j.get("added_tokens", []) if t.get("special")}
        self.id2tok = {i: t for t, i in self.vocab.items()}
        self.id2tok.update({i: t for t, i in self.added.items()})
        pre = j.get("pre_tokenizer") or {}
        pats = [p for p in (pre.get("pretokenizers") or [pre]) if p.get("type") == "Split"]
        self.split = _translate_regex(pats[0]["pattern"]["Regex"]) if pats else re.compile(r"\S+|\s+")
        norm = (j.get("normalizer") or {}).get("type")
        self.nfc = norm == "NFC"
        self.b2u = _bytes_to_unicode(); self.u2b = {v: k for k, v in self.b2u.items()}
        alt = "|".join(re.escape(t) for t in sorted(self.added, key=len, reverse=True))
        self.added_rx = re.compile(f"({alt})") if alt else None
        self._cache = {}

    def _bpe(self, word):
        hit = self._cache.get(word)
        if hit is not None: return hit
        parts = list(word)
        while len(parts) > 1:
            best, idx = None, -1
            for i in range(len(parts) - 1):
                r = self.ranks.get((parts[i], parts[i + 1]))
                if r is not None and (best is None or r < best): best, idx = r, i
            if best is None: break
            a, b = parts[idx], parts[idx + 1]; out, i = [], 0
            while i < len(parts):                          # alle Vorkommen dieses Paares verschmelzen
                if i < len(parts) - 1 and parts[i] == a and parts[i + 1] == b: out.append(a + b); i += 2
                else: out.append(parts[i]); i += 1
            parts = out
        ids = [self.vocab[p] for p in parts]
        if len(self._cache) < 100000: self._cache[word] = ids
        return ids

    def _encode_plain(self, text, out):
        if self.nfc: text = unicodedata.normalize("NFC", text)
        for piece in self.split.findall(text):
            out.extend(self._bpe("".join(self.b2u[b] for b in piece.encode("utf-8"))))

    def encode(self, text, allow_special=True):
        """Text -> IDs. Spezialtokens wie <|im_start|> im Text werden als solche erkannt."""
        out = []
        if allow_special and self.added_rx:
            for i, seg in enumerate(self.added_rx.split(text)):
                if i % 2: out.append(self.added[seg])
                elif seg: self._encode_plain(seg, out)
        else:
            self._encode_plain(text, out)
        return out

    def token_bytes(self, tid):
        t = self.id2tok.get(tid, "")
        if tid in self.added.values(): return t.encode("utf-8")
        return bytes(self.u2b.get(c, 0) for c in t)

    def decode(self, ids, skip_special=True):
        b = b"".join(self.token_bytes(i) for i in ids if not (skip_special and i in self.special_ids))
        return b.decode("utf-8", errors="replace")

class StreamDecoder:
    """Gibt Text Stueck fuer Stueck aus, ohne halbe UTF-8-Zeichen (Umlaute!) zu zerreissen."""
    def __init__(self, tok, skip_special=True):
        self.tok, self.skip, self.buf = tok, skip_special, b""
    def push(self, tid):
        if self.skip and tid in self.tok.special_ids: return ""
        self.buf += self.tok.token_bytes(tid)
        for cut in range(len(self.buf), max(len(self.buf) - 4, -1), -1):
            try:
                s = self.buf[:cut].decode("utf-8"); self.buf = self.buf[cut:]; return s
            except UnicodeDecodeError:
                continue
        return ""
