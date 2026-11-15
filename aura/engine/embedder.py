# aura/engine/embedder.py — e5-Embeddings. Nur im Worker-Thread verwenden!
# v24: Standard ist DirectML (D3D12, engine/e5_dml.py, ~6x schneller, gleiche Vektoren: Kosinus 0,99999).
#      settings["embed_engine"] = "dml" | "native". Scheitert DirectML beim Laden, faellt AURA auf die native Engine zurueck.
from pathlib import Path

NEEDED = ("config.json", "model.safetensors", "tokenizer.json")

def _lost(e):
    """Geraet weg (Standby, Treiber-Reset)?"""
    s = str(e)
    return "entfernt" in s or "HRESULT" in s or "0x887A" in s.upper()

class EmbeddingAbgebrochen(RuntimeError):
    """v244: Abbrechen-Knopf während der GPU-Wiederherstellung."""


class Embedder:
    def __init__(self, model_dir):
        self.dir = Path(model_dir); self.tok = self.enc = self.dml = None
        self.resets, self.last_reset = 0, ""
        self.kind = None                                   # "dml" | "native" nach load()

    def available(self):
        missing = [f for f in NEEDED if not (self.dir / f).exists()]
        return (False, f"Modell unvollstaendig in {self.dir}: fehlt {', '.join(missing)}") if missing else (True, "")

    def _want(self):
        try:
            from ..config import load_settings
            return load_settings().get("embed_engine", "dml")
        except Exception: return "dml"

    def load(self):
        if self.enc or self.dml: return
        from .tokenizer import XLMRTokenizer
        from .. import log
        self.tok = XLMRTokenizer(self.dir / "tokenizer.json")
        if self._want() == "dml":
            try:
                from .e5_dml import E5DML
                e = E5DML(self.dir, progress=lambda s: None); e.load()
                self.dml, self.kind = e, "dml"
                log.get().info(f"Embedding: DirectML auf {e.dev.name}, Gewichte in {e.load_s:.1f} s")
                return
            except Exception:
                log.get().exception("Embedding: DirectML nicht moeglich - native Engine")
                self.dml = None
        from .weights import Model
        from .gpu import Encoder
        self.enc, self.kind = Encoder(Model(self.dir)), "native"

    WAITS = (0, 5, 15, 30, 60)        # v244 (FUN-05): max. ~110 s statt ~17 min, und abbrechbar
    abbruch = None                    # threading.Event des Workers (Abbrechen-Knopf); None = nicht abbrechbar

    def _embed(self, text):
        import threading
        try: from .gpu import DeviceLost
        except Exception: DeviceLost = RuntimeError
        last = None
        warte = self.abbruch if self.abbruch is not None else threading.Event()
        for wait in self.WAITS:
            if wait and warte.wait(wait):             # True = Abbrechen gedrückt -> sofort zurück
                raise EmbeddingAbgebrochen(f"Embedding abgebrochen während GPU-Wiederherstellung ({last})")
            try:
                self.load(); ids = self.tok.encode(text)
                return self.dml.vector(ids) if self.dml else self.enc.embed(ids)
            except (DeviceLost, RuntimeError, OSError) as e:   # Geraet weg oder (noch) nicht neu erstellbar
                if not isinstance(e, DeviceLost) and not _lost(e): raise
                last = e; self.resets += 1; self.last_reset = str(e)
                self.close()                          # altes Geraet freigeben, neu laden, nochmals versuchen
        try:
            from .. import log
            log.get().error(f"Embedding: GPU nach {sum(self.WAITS)} s nicht wieder verfügbar ({last}) – "
                            "AURA neu starten oder «embed_engine» = native wählen.")
        except Exception: pass
        raise last                                    # Typ bleibt DeviceLost: Aufrufer (Prüfliste, Workflow) erkennen ihn

    def close(self):
        if self.enc:
            try: self.enc.g.close()
            except Exception: pass
        if self.dml:
            try: self.dml.dev.close()                 # D3D12/DirectML-Objekte freigeben (~1,1 GB)
            except Exception: pass
        self.enc = None; self.dml = None

    def passage(self, text): return self._embed("passage: " + text)
    def query(self, text):   return self._embed("query: " + text)
