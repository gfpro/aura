# aura/llm/native.py — Hugging-Face-Sprachmodelle auf der nativen GPU-Engine. Version 20261031v146 (v146: freigegebene Chat-Rolle aus skills.py im Systemtext; v130: 4-Bit-Gewichte, Einstellung llm_bits 4/8/16; v118: nur noch Qwen3.5, Qwen3-Engine entfernt; v110: Quellen nur mit Link werden genannt; v106: Speicher nach Engine-Aufbau ins Log; v104: System-Prompt ohne Satzgrenze – nur die Frage beantworten, keine Fuellsaetze; v88: Qwen3.5 ueber qwen35.py, Denkmodus aus; v86: gemm fp16; v85: KV-Cache fp16, Einstellung llm_kv16; v84: splitr im Log; v83: Split-K-Varianten im Log; v28: Kontextlaenge aus Einstellungen; v44: Kernel-Wahl ins Log; v70: 8-Bit-Gewichte, Einstellung llm_int8;
#   v72: Schweizer Rechtschreibung (ß -> ss) und ohne Vorspann «Antwort:»)
# Unterstuetzt: Qwen3.5 (Qwen3_5ForConditionalGeneration / Qwen3_5ForCausalLM, z.B. Qwen3.5-4B), Gewichte bf16 oder int8.
import json, time
from pathlib import Path
from .base import LLMBackend, build_prompt

SUPPORTED = {"Qwen3_5ForConditionalGeneration", "Qwen3_5ForCausalLM"}   # v118: Qwen3 entfernt
Q35 = {"Qwen3_5ForConditionalGeneration", "Qwen3_5ForCausalLM"}
def _rolle():                                                          # v146: freigegebene Chat-Rolle (skills.py)
    try:
        from ..skills import chat_zusatz
        return chat_zusatz()
    except Exception: return ""


NO_THINK = "<think>\n\n</think>\n\n"                                # v88: Qwen3.5 ohne Denkmodus
SYSTEM = ("Du bist AURA, ein lokaler Assistent. Antworte auf Deutsch, sachlich und knapp: nur was gefragt ist, ohne "
          "Fuellsaetze, einfacher Text ohne Markdown (keine Sternchen, keine Rauten). Nenne zuerst die direkte Antwort. "
          "Stuetze dich ausschliesslich auf die Quellen und belege Aussagen mit der Quellennummer, z.B. [1]. "
          "Widersprechen sich Quellen, gilt die neueste (Datum beachten). "
          "Enthaelt eine Quelle nur Betreff, Absender und einen Link, nenne genau das (Absender, Datum, Betreff, Inhalt verlinkt). "
          "Wenn die Quellen die Antwort nicht enthalten, sage das klar. "
          "Schreibe in Schweizer Rechtschreibung: immer ss statt ß. Beginne ohne Vorspann wie «Antwort:».")      # v72
STOP = {"<|im_end|>", "<|endoftext|>"}

class NativeCausalLM(LLMBackend):
    def __init__(self, model_dir):
        self.dir = Path(model_dir)
        self.cfg = json.loads((self.dir / "config.json").read_text(encoding="utf-8"))
        self.arch = (self.cfg.get("architectures") or ["?"])[0]
        self.q35 = self.arch in Q35                                     # v88
        self.name = self.dir.name; self.eng = self.tok = None
        self.progress = lambda *a: None; self.settings = {}

    def load(self):
        if self.arch not in SUPPORTED:
            raise RuntimeError(f"{self.arch} wird nicht unterstuetzt - AURA laeuft nur noch mit Qwen3.5 (Einstellung llm, z.B. hf:Qwen3.5-4B).")
        if self.eng: return
        from .bpe_tokenizer import BPETokenizer
        from .qwen35 import Qwen35Engine as Engine                    # v118: einzige Engine
        t0 = time.perf_counter()
        self.tok = BPETokenizer(self.dir / "tokenizer.json")
        self.eng = Engine(self.dir, progress=self.progress, maxT=self.context_len(), int8=self.bits() <= 8, kv16_on=self.kv16(), int4=self.bits() == 4)
        self.stop_ids = {self.tok.added[s] for s in STOP if s in self.tok.added}
        from ..log import mem; mem("llm:engine_aufgebaut")            # v106: zeigt, ob CPU-Kopie der Gewichte bleibt
        try: b = self.eng.self_check(self.progress)
        except Exception:
            self.unload(); raise                                       # v70: GPU-Speicher nicht belegt lassen
        e = self.eng
        return self._ready_q35(b, t0)

    def _ready_q35(self, b, t0):
        e = self.eng
        self.kernels = (f"Qwen3.5, Gewichte {self._wlabel()}, Matrix {e.lin_kernel}, kleine Bloecke {e.small_kernel}, "
                        f"Attention {e.attn_kernel}, Einlesen {e.pre_kernel}, Schreiben {e.dec_kernel}")
        self.progress("Sprachmodell: Probelauf ..."); self.eng.forward(self.tok.encode("Hallo"), 0); self.eng.g.sync()
        self.eng.kv_ids = []; self.eng._reset_state()
        self.load_s = time.perf_counter() - t0
        from ..log import diag
        diag("kernel", modell=self.name, engine="qwen35", kontext=e.maxT, gewichte=self._wlabel(),
             kv="fp16" if e.kv16 else "fp32", laden_s=self.load_s, matrix=e.lin_kernel, klein=e.small_kernel, attention=e.attn_kernel, einlesen=e.pre_kernel, schreiben=e.dec_kernel,
             **{k: (f"{v:.1e}" if k.endswith("diff") or k.startswith("attn") else v * 1000) for k, v in b.items()
                if isinstance(v, float) and not k.startswith("gflops")})
        self.progress(f"Sprachmodell bereit (Qwen3.5, {('4 Bit, ' if e.q4 else '8 Bit, ') if e.q8 else ''}geladen in {self.load_s:.0f} s)")

    def chat_suffix(self):
        """v88: Text direkt nach '<|im_start|>assistant\\n' (Qwen3.5: leerer Denkblock)."""
        return NO_THINK if self.q35 else ""

    def kv16(self):
        from ..config import load_settings
        return bool(load_settings().get("llm_kv16", True))           # v85: Standard an

    def int8(self): return self.bits() <= 8                            # v130: alter Name, bleibt fuer Aufrufer

    def bits(self):
        """v130: llm_bits (4, 8 oder 16). Fehlt es, gilt das alte llm_int8 (true = 8, false = 16)."""
        from ..config import load_settings
        s = load_settings(); b = s.get("llm_bits")
        if b is None: return 8 if s.get("llm_int8", True) else 16
        b = int(b); return b if b in (4, 8, 16) else 8

    def _wlabel(self):
        e = self.eng
        return "int4 (lm_head int8)" if getattr(e, "q4", False) else "int8" if e.q8 else "bf16"

    def context_len(self):
        """llm_context (Standard 16384), aber so begrenzt, dass Gewichte + KV-Cache in llm_mem_gb passen."""
        from ..config import load_settings
        s = load_settings(); want = int(s.get("llm_context", 16384)); mem = float(s.get("llm_mem_gb", 14)) * 1e9
        c = self.cfg.get("text_config", self.cfg)                       # v88: Qwen3.5 verschachtelt
        nkv = sum(1 for t in c.get("layer_types", []) if t == "full_attention") if self.q35 else c["num_hidden_layers"]
        per_tok = nkv * 2 * c["num_key_value_heads"] * c.get("head_dim", 128) * (2 if self.kv16() else 4)
        weights = sum(p.stat().st_size for p in self.dir.glob("*.safetensors"))
        b = self.bits()
        if b <= 8: weights = int(weights * (0.52 if b == 8 else 0.33))   # v70 int8; v130 int4 (Schichten ~0,28, lm_head int8)
        fit = int((mem - weights) / per_tok) // 512 * 512
        n = max(4096, min(want, fit))
        self.progress(f"Kontext {n} Tokens (KV-Cache {n * per_tok / 1e9:.1f} GB, Gewichte {weights / 1e9:.1f} GB)")
        return n

    def loaded(self): return self.eng is not None

    def unload(self):
        if self.eng:
            try: self.eng.close()
            except Exception: pass
        self.eng = None

    def prompt_ids(self, question, hits, budget):
        """Chat-Vorlage (ChatML). Quellen werden gekuerzt, bis der Prompt ins Budget passt."""
        hits = list(hits)
        while True:
            user = build_prompt(question, hits)
            text = f"<|im_start|>system\n{SYSTEM}{_rolle()}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n{self.chat_suffix()}"
            ids = self.tok.encode(text)
            if len(ids) <= budget or not hits: return ids, len(hits)
            hits = hits[:-1]

    def generate(self, question, hits, on_token, cancelled):
        from ..engine.gpu import DeviceLost
        try: return self._generate(question, hits, on_token, cancelled)
        except DeviceLost as e:                        # einmal automatisch neu laden und wiederholen
            self.unload(); self.progress(f"GPU-Zuruecksetzung ({e}) - lade neu und versuche nochmals ...")
            return self._generate(question, hits, on_token, cancelled)

    def _generate(self, question, hits, on_token, cancelled):
        from .bpe_tokenizer import StreamDecoder
        from .qwen import sample
        from ..engine.gpu import DeviceLost
        s = self.settings
        max_new = int(s.get("llm_max_new", 250)); temp = float(s.get("llm_temperature", 0.0))
        hits = hits[:int(s.get("llm_top_k", 4))]
        self.load()
        ids, used = self.prompt_ids(question, hits, self.eng.maxT - max_new - 8); self.used = used
        try:
            t0 = time.perf_counter()
            logits = self.eng.prefill(ids, self.progress, cancelled)
            if logits is None: return
            t1 = time.perf_counter(); pos = len(ids); dec = StreamDecoder(self.tok); n = 0
            out = swiss_stream(on_token)                                # v72
            self.progress(f"Kontext gelesen ({len(ids)} Tokens, {t1 - t0:.0f} s) - schreibe Antwort ...")
            while n < max_new and pos < self.eng.maxT and not cancelled():
                tid = sample(logits, temp)
                if tid in self.stop_ids: break
                txt = dec.push(tid)
                if txt: out.push(txt)
                n += 1
                logits = self.eng.forward([tid], pos); pos += 1
            out.flush(); dt = time.perf_counter() - t1
            self.timing = {"ctx": len(ids), "prefill": t1 - t0, "out": n, "gen": dt}
            self.progress(f"{used} Quellen · Kontext {len(ids)} Tokens in {t1 - t0:.0f} s · Antwort {n} Tokens "
                          f"({n / dt if dt > 0 else 0:.1f}/s)")
        except DeviceLost:
            self.unload(); raise


class swiss_stream:
    """v72: Ausgabe an die Oberfläche in Schweizer Schreibweise (ß -> ss) und ohne einleitendes «Antwort:».
    Hält nur die ersten Zeichen zurück, bis klar ist, ob ein Vorspann folgt."""
    PRE = ("antwort:", "antwort :")
    def __init__(self, emit): self.emit, self.head, self.open = emit, "", True
    def push(self, txt):
        txt = txt.replace("ß", "ss").replace("ẞ", "SS")
        if not self.open: self.emit(txt); return
        self.head += txt; h = self.head.lstrip().lower()
        if any(p.startswith(h) for p in self.PRE) and len(h) < 10: return      # könnte noch «Antwort:» werden
        self.open = False; t = self.head.lstrip()
        for p in self.PRE:
            if t.lower().startswith(p): t = t[len(p):].lstrip(); break
        if t: self.emit(t)
    def flush(self):
        if self.open and self.head.strip(): self.open = False; self.emit(self.head.lstrip())
