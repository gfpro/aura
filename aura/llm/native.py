# aura/llm/native.py — Hugging-Face-Sprachmodelle auf der nativen GPU-Engine. Version 20261014v86 (v86: gemm fp16; v85: KV-Cache fp16, Einstellung llm_kv16; v84: splitr im Log; v83: Split-K-Varianten im Log; v28: Kontextlaenge aus Einstellungen; v44: Kernel-Wahl ins Log; v70: 8-Bit-Gewichte, Einstellung llm_int8;
#   v72: Schweizer Rechtschreibung (ß -> ss) und ohne Vorspann «Antwort:»)
# Unterstuetzt: Qwen3ForCausalLM (z.B. Qwen3-0.6B ... Qwen3-4B-Instruct-2507), Gewichte bf16.
import json, time
from pathlib import Path
from .base import LLMBackend, build_prompt

SUPPORTED = {"Qwen3ForCausalLM"}
SYSTEM = ("Du bist AURA, ein lokaler Assistent. Antworte auf Deutsch, sachlich und knapp: hoechstens 4 Saetze, "
          "einfacher Text ohne Markdown (keine Sternchen, keine Rauten). Nenne zuerst die direkte Antwort. "
          "Stuetze dich ausschliesslich auf die Quellen und belege Aussagen mit der Quellennummer, z.B. [1]. "
          "Widersprechen sich Quellen, gilt die neueste (Datum beachten). "
          "Wenn die Quellen die Antwort nicht enthalten, sage das klar. "
          "Schreibe in Schweizer Rechtschreibung: immer ss statt ß. Beginne ohne Vorspann wie «Antwort:».")      # v72
STOP = {"<|im_end|>", "<|endoftext|>"}

class NativeCausalLM(LLMBackend):
    def __init__(self, model_dir):
        self.dir = Path(model_dir)
        self.cfg = json.loads((self.dir / "config.json").read_text(encoding="utf-8"))
        self.arch = (self.cfg.get("architectures") or ["?"])[0]
        self.name = self.dir.name; self.eng = self.tok = None
        self.progress = lambda *a: None; self.settings = {}

    def load(self):
        if self.arch not in SUPPORTED:
            raise RuntimeError(f"{self.arch} wird von der nativen Engine noch nicht unterstuetzt.")
        if self.eng: return
        from .bpe_tokenizer import BPETokenizer
        from .qwen import Qwen3Engine
        t0 = time.perf_counter()
        self.tok = BPETokenizer(self.dir / "tokenizer.json")
        self.eng = Qwen3Engine(self.dir, progress=self.progress, maxT=self.context_len(), int8=self.int8(), kv16_on=self.kv16())
        self.stop_ids = {self.tok.added[s] for s in STOP if s in self.tok.added}
        try: b = self.eng.self_check(self.progress)
        except Exception:
            self.unload(); raise                                       # v70: GPU-Speicher nicht belegt lassen
        e = self.eng
        self.kernels = (f"Gewichte {'int8' if e.q8 else 'bf16'}, Matrix {e.lin_kernel} ({b['gflops_' + e.lin_kernel]:.0f} GFLOPS), "
                        f"Attention {e.attn_kernel}, Einlesen {e.pre_kernel}, Schreiben {e.dec_kernel}, kleine Bloecke {e.small_kernel}")
        self.progress("Sprachmodell: Probelauf ..."); self.eng.forward(self.tok.encode("Hallo"), 0); self.eng.g.sync()
        self.load_s = time.perf_counter() - t0
        from ..log import diag                                       # v44: Kernel-Wahl und Selbsttest ins Log
        diag("kernel", modell=self.name, kontext=e.maxT, gewichte="int8" if e.q8 else "bf16", kv="fp16" if e.kv16 else "fp32",
             q8_diff=f"{b.get('q8_diff', 0):.1e}", q8_bf16_ms=b.get("q8_bf16", 0) * 1000, q8_int8_ms=b.get("q8_int8", 0) * 1000, laden_s=self.load_s, matrix=e.lin_kernel,
             gflops=b["gflops_" + e.lin_kernel], attention=e.attn_kernel, einlesen=e.pre_kernel, schreiben=e.dec_kernel,
             pre_v2_ms=b.get("pre_v2", 0) * 1000, pre_gemm_ms=b.get("pre_gemm", 0) * 1000, pre_diff=f"{b.get('pre_diff', 0):.1e}",
             dec_v2_ms=b.get("dec_v2", 0) * 1000, dec_split_ms=b.get("dec_split", 0) * 1000, dec_s128_ms=b.get("dec_split_128", 0) * 1000, dec_s64_ms=b.get("dec_split_64", 0) * 1000, dec_r128_ms=b.get("dec_splitr_128", 0) * 1000, dec_r64_ms=b.get("dec_splitr_64", 0) * 1000,
             klein=e.small_kernel, small_v2_ms=b.get("small_v2", 0) * 1000, small_mt_ms=b.get("small_mt", 0) * 1000,
             small_diff=f"{b.get('small_diff', 0):.1e}", klein_attn=e.small_attn,
             sattn_v2_ms=b.get("sattn_v2", 0) * 1000, sattn_split_ms=b.get("sattn_split", 0) * 1000, sattn_s128_ms=b.get("sattn_split_128", 0) * 1000, sattn_s64_ms=b.get("sattn_split_64", 0) * 1000, sattn_r128_ms=b.get("sattn_splitr_128", 0) * 1000, sattn_r64_ms=b.get("sattn_splitr_64", 0) * 1000,
             sattn_diff=f"{b.get('sattn_diff', 0):.1e}")
        self.progress(f"Sprachmodell bereit ({'8 Bit, ' if e.q8 else ''}geladen in {self.load_s:.0f} s)")

    def kv16(self):
        from ..config import load_settings
        return bool(load_settings().get("llm_kv16", True))           # v85: Standard an

    def int8(self):
        from ..config import load_settings
        return bool(load_settings().get("llm_int8", False))

    def context_len(self):
        """llm_context (Standard 16384), aber so begrenzt, dass Gewichte + KV-Cache in llm_mem_gb passen."""
        from ..config import load_settings
        s = load_settings(); want = int(s.get("llm_context", 16384)); mem = float(s.get("llm_mem_gb", 14)) * 1e9
        c = self.cfg; per_tok = c["num_hidden_layers"] * 2 * c["num_key_value_heads"] * c.get("head_dim", 128) * (2 if self.kv16() else 4)
        weights = sum(p.stat().st_size for p in self.dir.glob("*.safetensors"))
        if self.int8(): weights = int(weights * 0.52)                # v70: int8 = halbe Groesse + 1 Skala je 128 Werte
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
            text = f"<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"
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
