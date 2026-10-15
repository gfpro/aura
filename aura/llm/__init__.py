# aura/llm/__init__.py — Version 20261015v89 (v89: Qwen3.5 in der Modellliste)
# Sprachmodell-Steckplaetze. discover() findet Modelle in models\ anhand ihrer config.json.
import json
from pathlib import Path
from .base import LLMBackend
from .extractive import Extractive
from .native import NativeCausalLM, SUPPORTED

def discover(models_dir):
    """Liste von (id, Anzeigename, Fabrik). 'extractive' ist immer verfuegbar."""
    out = [("extractive", "Kein LLM - relevanteste Stellen zeigen", Extractive)]
    for cfg in sorted(Path(models_dir).glob("*/config.json")):
        try: arch = (json.loads(cfg.read_text(encoding="utf-8")).get("architectures") or [""])[0]
        except Exception: continue
        if arch.endswith("ForCausalLM") or arch in SUPPORTED:            # v89: Qwen3_5ForConditionalGeneration
            c = json.loads(cfg.read_text(encoding="utf-8"))
            if arch == "Qwen3ForCausalLM" and c.get("max_position_embeddings", 0) >= 262144:
                arch += ", Instruct-2507"                       # die 2507-Instruct-Variante hat 256K Kontext
            if arch.startswith("Qwen3_5"): arch = "Qwen3.5"                 # v89: kurzer Anzeigename
            mark = "" if arch.split(",")[0] in SUPPORTED or arch == "Qwen3.5" else " (noch nicht unterstuetzt)"
            out.append((f"hf:{cfg.parent.name}", f"{cfg.parent.name} [{arch}]{mark}",
                        lambda d=cfg.parent: NativeCausalLM(d)))
    return out
