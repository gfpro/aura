# aura/config.py — Pfade und Einstellungen. Alles liegt im Programmordner (lokal, keine Cloud).
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, MODELS, LOGS, EVAL = ROOT / "data", ROOT / "models", ROOT / "logs", ROOT / "eval"
DB_PATH, SETTINGS_PATH = DATA / "aura.db", DATA / "settings.json"

DEFAULTS = {
    "embed_model": "multilingual-e5-large",  # Ordner unter models\
    "llm": "extractive",                     # Backend-ID (siehe aura/llm)
    "top_k": 6,                              # Textstuecke pro Antwort
    "edge_days": 90,                         # Edge-Verlauf: wie weit zurueck
    "calendar_past_days": 365, "calendar_future_days": 180,
    "docs_folder": "",                       # Dokumentordner fuer den Datei-Connector
    "llm_top_k": 4,                          # Quellen fuer das Sprachmodell (mehr = langsamer)
    "llm_max_new": 250,                      # maximale Antwortlaenge in Tokens
    "llm_temperature": 0.0,                  # 0 = immer das wahrscheinlichste Wort (schnell, sachlich)
    "llm_int8": True,                        # v125: 8-Bit-Gewichte (Standard); false nur als Gegenprobe
}

def ensure_dirs():
    for d in (DATA, MODELS, LOGS, EVAL): d.mkdir(exist_ok=True)

SETTINGS_VERSION = 2

def load_settings():
    s = dict(DEFAULTS)
    try: s.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
    except Exception: pass
    if s.get("settings_version", 1) < 2:                 # alte, automatisch gespeicherte Standardwerte nachziehen
        if s.get("llm_max_new") == 400: s["llm_max_new"] = 250
        if s.get("llm_temperature") == 0.3: s["llm_temperature"] = 0.0
    s["settings_version"] = SETTINGS_VERSION
    return s

def save_settings(s):
    ensure_dirs(); SETTINGS_PATH.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")

def location_warning():
    """Datenbank soll nie in synchronisierten oder Netzwerk-Ordnern liegen."""
    p = str(ROOT).lower()
    if "onedrive" in p or p.startswith("\\\\") or p.startswith("h:"):
        return f"Achtung: AURA liegt in {ROOT} (OneDrive/Netzlaufwerk). Bitte lokal ablegen, z.B. C:\\aura."
    return ""
