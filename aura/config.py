# aura/config.py — Pfade und Einstellungen. Alles liegt im Programmordner (lokal, keine Cloud).
import os
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
    "live_akkordeon": True,                  # v269: Live-Antwort -> Einzelergebnisse je Quelle eingeklappt
    "stt_modell": "",                        # v266: Whisper-Ordner unter models\ (leer = bestes vorhandenes)
    "memo_folder": "",                       # v266: Ordner fuer Memos (leer = Dokumente\AURA-Memos)
    "llm_top_k": 4,                          # Quellen fuer das Sprachmodell (mehr = langsamer)
    "antwort_stufe": "Kurz",                 # v163: Kurz | Normal | Ausführlich
    "llm_max_new": 250,                      # maximale Antwortlaenge in Tokens
    "llm_temperature": 0.0,                  # 0 = immer das wahrscheinlichste Wort (schnell, sachlich)
    "graph_suche": True,                     # v190: Abfolgefragen über den Graphen ergänzen (v194: Standard ein)
    "llm_int8": True,                        # v125: 8-Bit-Gewichte (Standard); false nur als Gegenprobe
}

def ensure_dirs():
    for d in (DATA, MODELS, LOGS, EVAL): d.mkdir(exist_ok=True)

SETTINGS_VERSION = 2

def load_settings():
    s = dict(DEFAULTS)
    try:
        roh = SETTINGS_PATH.read_text(encoding="utf-8"); s.update(json.loads(roh)); _sichern(roh)
    except FileNotFoundError: pass
    except Exception as e: _settings_defekt(e)                       # v249 (M9): nicht still mit Standardwerten weiter
    if s.get("settings_version", 1) < 2:                 # alte, automatisch gespeicherte Standardwerte nachziehen
        if s.get("llm_max_new") == 400: s["llm_max_new"] = 250
        if s.get("llm_temperature") == 0.3: s["llm_temperature"] = 0.0
    s["settings_version"] = SETTINGS_VERSION
    return s

_DEFEKT = {"gemeldet": False}
_SICHERUNG = {"erledigt": False}
SICHERUNGEN = 3

def _sichern(roh):
    """v252: einmal je Programmstart die lesbare settings.json als Sicherung ablegen – settings.sicherung.1.json (neueste)
    bis .3.json. Nur wenn sich der Inhalt gegenüber der neuesten Sicherung geändert hat. Fehler hier stören AURA nie."""
    if _SICHERUNG["erledigt"]: return
    _SICHERUNG["erledigt"] = True
    try:
        pfad = lambda n: SETTINGS_PATH.with_name(f"settings.sicherung.{n}.json")
        if pfad(1).exists() and pfad(1).read_text(encoding="utf-8") == roh: return
        for n in range(SICHERUNGEN - 1, 0, -1):
            if pfad(n).exists(): os.replace(pfad(n), pfad(n + 1))
        tmp = pfad(1).with_name(pfad(1).name + ".tmp"); tmp.write_text(roh, encoding="utf-8"); os.replace(tmp, pfad(1))
    except Exception: pass

def _settings_defekt(e):
    """v249 (M9): defekte settings.json einmal sichern (settings.defekt.json) und im Log melden. AURA läuft mit
    Standardwerten weiter; die Sicherung wird nie überschrieben, damit sich die Einstellungen von Hand retten lassen."""
    if _DEFEKT["gemeldet"]: return
    _DEFEKT["gemeldet"] = True
    try:
        ziel = SETTINGS_PATH.with_name("settings.defekt.json")
        if not ziel.exists(): ziel.write_bytes(SETTINGS_PATH.read_bytes())
    except Exception: pass
    try:
        from . import log
        log.get().error(f"settings.json ist nicht lesbar ({type(e).__name__}) – Standardwerte aktiv, Kopie in data\\settings.defekt.json")
    except Exception: pass

def settings_defekt():
    """True, wenn settings.json in dieser Sitzung nicht lesbar war (für einen Hinweis in der Oberfläche)."""
    return _DEFEKT["gemeldet"]

def save_settings(s):
    """v249 (M9): atomar – erst in eine temporäre Datei, dann ersetzen. Ein Abbruch mitten im Schreiben hinterlässt
    nie eine halbe settings.json. v251: War settings.json in dieser Sitzung nicht lesbar, wird NICHT gespeichert –
    sonst würden die Standardwerte die echten Einstellungen ersetzen (am 16.11.2026 nach entzogenen Ordnerrechten passiert)."""
    ensure_dirs()
    if _DEFEKT["gemeldet"]:                                           # v251: nie Standardwerte über eine nicht lesbare Datei schreiben
        if not _DEFEKT.get("save_gemeldet"):
            _DEFEKT["save_gemeldet"] = True
            try:
                from . import log
                log.get().error("Einstellungen NICHT gespeichert: settings.json war beim Lesen nicht lesbar (Rechte oder defekt). "
                                "Datei prüfen und AURA neu starten.")
            except Exception: pass
        return
    tmp = SETTINGS_PATH.with_name(SETTINGS_PATH.name + ".tmp")
    tmp.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, SETTINGS_PATH)

def location_warning():
    """Datenbank soll nie in synchronisierten oder Netzwerk-Ordnern liegen."""
    if _DEFEKT["gemeldet"]:                                           # v251: sichtbarer Hinweis über die bestehende Warnzeile
        return ("Achtung: data\\settings.json ist nicht lesbar (Zugriffsrechte oder defekte Datei). AURA läuft mit "
                "Standardwerten und speichert keine Einstellungen, damit nichts überschrieben wird. Datei prüfen, dann neu starten.")
    p = str(ROOT).lower()
    if "onedrive" in p or p.startswith("\\\\") or p.startswith("h:"):
        return f"Achtung: AURA liegt in {ROOT} (OneDrive/Netzlaufwerk). Bitte lokal ablegen, z.B. C:\\aura."
    return ""
