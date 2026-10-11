# aura/workflow/llmio.py — Sprachmodell fuer Workflows: eigener Chat-Prompt, freie Antwort und erzwungenes JSON.
# Version 20261010v44 (v40: Feldgrenzen bis Satzende; v43: Vorspann mit Festplatten-Cache des KV-Caches;
#                     v44: Kennzahlen ins Log logs\aura.log – Cache-Treffer, Einlesen, Schreiben je Feld, Geruest;
#                     v44a2: Auswahlfelder mit «wann» enden, sobald ein erlaubter Wert steht – der Abgrenzungstext
#                     wird nicht mehr mitgeschrieben (spart Zeit, keine falsche Kuerzungswarnung))
#
# Erzwungenes JSON ("fields"): Das Geruest {"feld": " ... ", "feld2": " ... "} schreibt NICHT das Modell,
# sondern AURA. Das Modell fuellt nur die Werte. Ergebnis: immer gueltiges JSON mit genau diesen Feldern,
# egal wie klein das Modell ist. Ein Wert endet am ersten nicht maskierten " oder nach max_tokens.
#
# Backend aura/llm/native.py: be.eng (Qwen3Engine), be.tok (BPETokenizer, Spezialtokens in tok.added),
# be.stop_ids. Pruefen:  py tools\wf_run.py --check
import heapq, json, math, random, re, sys, time
from ..log import diag

ENGINE_ATTRS = ("engine", "eng", "model", "m", "qwen", "net")
TOK_ATTRS = ("tok", "tokenizer", "bpe", "tk")

class Cancelled(Exception): pass

class Parts:
    def __init__(self, be):
        self.be = be
        self.eng = next((getattr(be, a) for a in ENGINE_ATTRS
                         if hasattr(getattr(be, a, None), "forward") and hasattr(getattr(be, a, None), "prefill")), None)
        self.tok = next((getattr(be, a) for a in TOK_ATTRS if hasattr(getattr(be, a, None), "encode")), None)
        if self.eng is None or self.tok is None:
            raise RuntimeError("Sprachmodell-Backend: Engine/Tokenizer nicht gefunden. Vorhandene Attribute: "
                               + ", ".join(sorted(k for k in vars(be) if not k.startswith("__"))))
        self.maxT = int(getattr(self.eng, "maxT", 4096))
        self.chunk = int(getattr(sys.modules.get(type(self.eng).__module__), "CHUNK", 512))
        self.im_start, self.im_end = self.special("<|im_start|>"), self.special("<|im_end|>")
        stop = {self.im_end} | set(getattr(be, "stop_ids", None) or ())
        eos = (getattr(self.eng, "cfg", {}) or {}).get("eos_token_id")
        stop.update(eos if isinstance(eos, list) else [eos] if isinstance(eos, int) else [])
        try: stop.add(self.special("<|endoftext|>"))
        except Exception: pass
        self.stop = stop

    def encode(self, s): return list(self.tok.encode(s))
    def decode(self, ids):
        if hasattr(self.tok, "decode"): return self.tok.decode(list(ids))
        from ..llm.bpe_tokenizer import StreamDecoder               # native.py: Tokenizer ohne decode()
        d = StreamDecoder(self.tok); return "".join(d.push(t) or "" for t in ids)
    def special(self, s):
        added = getattr(self.tok, "added", None)
        if isinstance(added, dict) and s in added: return added[s]
        ids = self.encode(s)
        if len(ids) != 1: raise RuntimeError(f"Tokenizer kennt {s} nicht als Spezialtoken (ergibt {ids[:6]})")
        return ids[0]

def parts(be): return Parts(be)

def chat_ids(P, system, user, think_off, vorspann=""):
    """Qwen3-Chatvorlage. think_off: leerer Denkteil (wie enable_thinking=False) fuer Hybrid-Modelle.
    v43: vorspann = fester Anfang der Benutzernachricht; wird getrennt kodiert, damit der Anfang immer gleich bleibt.
    Rueckgabe: ids (und P.head = Anzahl Tokens von System + Vorspann)."""
    head = f"<|im_start|>system\n{system.strip()}<|im_end|>\n" if system else ""
    head += "<|im_start|>user\n" + (vorspann.strip() + "\n\n" if vorspann and vorspann.strip() else "")
    tail = f"{user.strip()}<|im_end|>\n<|im_start|>assistant\n" + ("<think>\n\n</think>\n\n" if think_off else "")
    h = P.encode(head); P.head = len(h)
    return h + P.encode(tail)

KV_KEEP = 2                                                         # so viele Vorspann-Caches behalten (VE: ~1 GB je Datei)

def kv_disk(P, ids, progress, save=False):
    """v43: KV-Cache von System + Vorspann auf der Festplatte (data\\kvcache). Laden vor dem Einlesen, Speichern danach."""
    e = P.eng; n = getattr(P, "head", 0)
    if not hasattr(e, "load_kv") or n < 256: return                  # kurzer Anfang: lohnt nicht
    import hashlib
    from ..config import DATA
    key = hashlib.sha1((e.dir.name + "|" + ",".join(map(str, ids[:n]))).encode()).hexdigest()[:16]
    f = DATA / "kvcache" / f"{key}.kv"
    try:
        t = time.perf_counter()
        if save:
            if f.exists() or getattr(e, "reused", 0) >= n: return
            e.save_kv(f, n); progress(f"Vorspann-Cache gespeichert ({n} Tokens)")
            diag("kvcache", aktion="gespeichert", tokens=n, mb=f.stat().st_size / 1e6, s=time.perf_counter() - t)
            old = sorted(f.parent.glob("*.kv"), key=lambda p: p.stat().st_mtime)[:-KV_KEEP]
            for o in old: o.unlink()
        elif getattr(e, "kv_ids", [])[:n] == ids[:n]:
            diag("kvcache", aktion="im_speicher", tokens=n)            # schon im Grafikspeicher, nichts zu laden
        elif not f.exists():
            diag("kvcache", aktion="kein_cache", tokens=n)
        else:
            got = e.load_kv(f)
            if got == n:
                progress(f"Vorspann aus Cache geladen ({n} Tokens)"); f.touch()
                diag("kvcache", aktion="geladen", tokens=n, s=time.perf_counter() - t)
            else: diag("kvcache", aktion="abweichend", erwartet=n, geladen=got)
    except Exception as x:
        progress(f"Vorspann-Cache übersprungen: {type(x).__name__}: {x}")
        diag("kvcache", aktion="fehler", fehler=f"{type(x).__name__}:{x}")

def sample(logits, temperature, recent=(), penalty=1.0, rng=random):
    if penalty and penalty != 1.0:
        for t in set(recent):
            v = logits[t]; logits[t] = v / penalty if v > 0 else v * penalty
    if temperature <= 0: return logits.index(max(logits))
    top = heapq.nlargest(20, range(len(logits)), key=logits.__getitem__)
    m = logits[top[0]]; ps = [math.exp((logits[i] - m) / temperature) for i in top]; z = sum(ps)
    acc, keep = 0.0, []
    for i, p in zip(top, ps):
        keep.append((i, p)); acc += p / z
        if acc >= 0.8: break
    r = rng.random() * sum(p for _, p in keep)
    for i, p in keep:
        r -= p
        if r <= 0: return i
    return keep[-1][0]

class Gen:
    """Haelt Position und Logits im KV-Cache des Modells."""
    def __init__(self, P, ids, progress, cancelled, reserve):
        self.P, self.e = P, P.eng
        if len(ids) + reserve > P.maxT:
            raise RuntimeError(f"Zu viel Text fuers Sprachmodell: Eingabe {len(ids)} + Antwort {reserve} Tokens > "
                               f"{P.maxT}. Dokumenttext kuerzen (extract: max_chars) oder max_tokens senken.")
        t0 = time.perf_counter()
        kv_disk(P, ids, progress)                                    # v43: Vorspann von der Festplatte
        self.logits = self.e.prefill(ids, progress, cancelled)
        if self.logits is None: raise Cancelled()
        self.cached = int(getattr(self.e, "reused", 0))
        kv_disk(P, ids, progress, save=True)
        self.pos = len(ids); self.t_prefill = time.perf_counter() - t0; self.n_in = len(ids)
        self.n_out = 0; self.recent = []

    def accept(self, t):
        self.logits = self.e.forward([t], self.pos); self.pos += 1; self.n_out += 1
        self.recent.append(t); self.recent = self.recent[-64:]

    def feed(self, ids):
        for s in range(0, len(ids), self.P.chunk):
            part = ids[s:s + self.P.chunk]
            if self.pos + len(part) >= self.P.maxT: raise RuntimeError("Kontextgrenze erreicht")
            self.logits = self.e.forward(part, self.pos); self.pos += len(part)

def _quote_at(s):
    """Position des ersten nicht maskierten " oder -1."""
    esc = False
    for i, c in enumerate(s):
        if esc: esc = False
        elif c == "\\": esc = True
        elif c == '"': return i
    return -1

def _unescape(v):
    v = v.rstrip("\ufffd")
    if v.endswith("\\") and not v.endswith("\\\\"): v = v[:-1]
    try: return json.loads('"' + v.replace("\n", "\\n").replace("\t", "\\t") + '"')
    except Exception: return v.replace("\\n", "\n").replace('\\"', '"')

def generate(be, system, user, max_new=400, temperature=0.0, penalty=1.05, on_text=None,
             progress=lambda *a: None, cancelled=lambda: False, think_off=False, vorspann=""):
    """Freie Antwort. Rueckgabe (text, statistik)."""
    P = parts(be); g = Gen(P, chat_ids(P, system, user, think_off, vorspann), progress, cancelled, max_new)
    out, shown, t0 = [], "", time.perf_counter()
    for _ in range(max_new):
        if cancelled(): raise Cancelled()
        t = sample(g.logits, temperature, g.recent, penalty)
        if t in P.stop: break
        out.append(t); txt = P.decode(out)
        if on_text and not txt.endswith("\ufffd"): on_text(txt[len(shown):]); shown = txt
        if g.pos + 1 >= P.maxT: break
        g.accept(t)
        if len(out) % 20 == 0: progress(f"Schreibe: {len(out)} Tokens")
    gen = time.perf_counter() - t0
    st = {"in": g.n_in, "cache": g.cached, "out": len(out), "prefill_s": g.t_prefill, "gen_s": gen}
    _diag_llm("llm_text", P, st)
    return P.decode(out).strip(), st

def _diag_llm(was, P, st):
    """v44: eine Zeile mit allen Zeiten. tok_s = geschriebene Tokens je Sekunde (ohne Einlesen)."""
    neu = st["in"] - st.get("cache", 0)
    diag(was, modell=getattr(getattr(P.eng, "dir", None), "name", "?"), eingabe=st["in"], cache=st.get("cache", 0),
         prefill_s=st["prefill_s"], prefill_tok_s=neu / st["prefill_s"] if st["prefill_s"] > 0 and neu else 0,
         out=st["out"], gen_s=st["gen_s"], tok_s=st["out"] / st["gen_s"] if st["gen_s"] > 0 else 0,
         geruest_s=st.get("geruest_s", 0), maxT=P.maxT)

def structured(be, system, user, fields, temperature=0.0, penalty=1.05, on_field=None,
               progress=lambda *a: None, cancelled=lambda: False, think_off=False, vorspann=""):
    """fields: [{"name": ..., "max_tokens": ..., "verlaengern": true}]. Rueckgabe (dict, statistik). Gueltiges JSON garantiert.
    v40: Erreicht ein Feld max_tokens, schreibt das Modell weiter bis zum Satzende (hoechstens nochmals max_tokens).
    Reicht auch das nicht, wird am letzten Satzende gekuerzt. statistik: verlaengert / gekuerzt (Feldnamen)."""
    P = parts(be)
    names = [f["name"] for f in fields]; lim = [int(f.get("max_tokens", 250)) for f in fields]
    ids = chat_ids(P, system, user, think_off, vorspann) + P.encode('{\n  "%s": "' % names[0])
    reserve = sum(lim) + 12 * len(fields)
    g = Gen(P, ids, progress, cancelled, reserve)
    res, t0, ext, cut = {}, time.perf_counter(), [], []
    felder, feed_s = [], 0.0                                            # v44: Zeit je Feld und fuer das Geruest
    END = re.compile(r"[.!?…)»]\s*$")
    for i, name in enumerate(names):
        progress(f"Feld {i + 1}/{len(names)}: {name}", i, len(names))
        out, closed, val, at_end = [], False, "", False; tf = time.perf_counter()
        hard = lim[i] * 2 if fields[i].get("verlaengern", True) else lim[i]
        opts = sorted(fields[i]["auswahl"], key=len, reverse=True) if fields[i].get("_wann") else None
        skip = fields[i].get("_skip_wenn")                              # v49: Beleg zu neutralem Wert -> «keiner»
        if skip and res.get(skip[0], "").strip().lower().rstrip(".") in skip[1]:
            val, closed, hard = "keiner", True, 0
        for k in range(hard):
            if cancelled(): raise Cancelled()
            if k >= lim[i]:                                         # ueber der Grenze: nur bis zum Satzende
                if k == lim[i]: ext.append(name)
                if END.search(P.decode(out)): at_end = True; break
            if g.pos + 2 >= P.maxT: break
            t = sample(g.logits, temperature, g.recent, penalty)
            if t in P.stop: break                                   # Modell will aufhoeren -> Feld schliessen
            out.append(t); s = P.decode(out); k = _quote_at(s)
            if k >= 0: val, closed = s[:k], True; break
            if opts:                                                # v44a2: «Wert – Abgrenzung» -> beim Wert aufhoeren
                o = next((o for o in opts if s.startswith(o) and s[len(o):len(o) + 2] in (" –", " -")), None)
                if o: val, closed = o, True; break
            g.accept(t)
        if closed:
            in_cache = P.decode(out[:-1]) if out else ""                           # letztes Token (mit ") ist NICHT im Cache
            rest = val[len(in_cache):] if val.startswith(in_cache) else ""
        else:
            val = P.decode(out); rest = ""
            n_bs = len(val) - len(val.rstrip("\\"))                 # abgeschnitten mitten in \-Folge
            if n_bs % 2: rest = "\\"
            if len(out) >= lim[i] and not at_end and not END.search(val):   # auch verlaengert kein Satzende
                cut.append(name)
                m = max(val.rfind(". "), val.rfind("! "), val.rfind("? "), val.rfind(".\n"))
                if m > len(val) * 0.4: val = val[:m + 1]
                else: val = val.rstrip(" ,;:-") + " …"
        nxt = (',\n  "%s": "' % names[i + 1]) if i + 1 < len(names) else "\n}"
        dt = time.perf_counter() - tf; tg = time.perf_counter()
        if i + 1 < len(names): g.feed(P.encode(rest + '"' + nxt))
        feed_s += time.perf_counter() - tg
        felder.append([name, len(out), round(dt, 1)])
        res[name] = _unescape(val).strip()
        if on_field: on_field(name, res[name], closed or at_end)
    gen = time.perf_counter() - t0
    st = {"in": g.n_in, "cache": g.cached, "out": g.n_out, "prefill_s": g.t_prefill, "gen_s": gen,
          "geruest_s": round(feed_s, 1), "felder": felder,
          "verlaengert": [n for n in ext if n not in cut], "gekuerzt": cut}
    _diag_llm("llm_json", P, st)
    diag("llm_felder", felder=[f"{n}:{k}/{s}s" for n, k, s in felder])
    return res, st

def fallback_generate(be, settings, system, user, on_text, cancelled):
    """Nur falls parts() scheitert: ueber die normale Frage-Schnittstelle (Prompt als eine 'Quelle')."""
    be.settings = dict(settings, llm_top_k=1); be.used = None; be.timing = None
    buf = []
    be.generate(user, [{"text": (system + "\n\n" if system else "") + user, "title": "Auftrag", "ts": "",
                        "source": "workflow", "item_id": 0, "author": "", "chunk_id": 0, "score": 1}],
                lambda t: (buf.append(t), on_text and on_text(t)), cancelled)
    txt = "".join(buf)
    return (txt.split("</think>", 1)[1] if "</think>" in txt else txt).strip()

def extract_json(txt, names):
    """Fallback ohne Zwang: erstes {...} suchen, fehlende Felder leer."""
    a, b = txt.find("{"), txt.rfind("}")
    try: d = json.loads(txt[a:b + 1]) if a >= 0 and b > a else {}
    except Exception: d = {}
    return {n: str(d.get(n, "")) for n in names}
