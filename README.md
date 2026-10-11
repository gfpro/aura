# AURA – lokales «zweites Gehirn»

Lokale RAG-Anwendung für Windows: Outlook-Mails, Outlook-Kalender, Edge-Verlauf und Dokumente durchsuchen
und befragen. Alles läuft lokal in Python (Standardbibliothek + mitgelieferte reine Python-Pakete in `vendor\`),
Rechenarbeit nativ auf der GPU über DirectX 11 (ctypes). Keine Installation, keine Admin-Rechte, keine Cloud.

## Start
Doppelklick auf **`AURA.pyw`**. Bei Problemen `AURA_debug.bat` (zeigt die Konsole); Fehler stehen in `logs\crash.log`.

## Voraussetzungen
- Windows, Python 3.10+ (64-Bit) mit tkinter, klassisches Outlook (für Mail/Kalender), Edge (für Verlauf)
- Modelle gemäss `models/README.md`

## Aufbau
| Ordner | Inhalt |
|---|---|
| `aura/connectors/` | Datenquellen (Steckplätze). Neue Quelle = neue Klasse + Eintrag in `__init__.py` |
| `aura/engine/` | Native GPU-Engine (Tokenizer, Gewichte, DirectX-Kernels, Embedder) |
| `aura/llm/` | Sprachmodelle: `extractive` (ohne LLM), `native` + `qwen.py` (Qwen3 auf der GPU), `bpe_tokenizer.py` |
| `aura/rag.py` | Hybride Suche (FTS5-BM25 + Vektoren, Reciprocal Rank Fusion) |
| `aura/worker.py` | Einziger Hintergrund-Thread für Outlook/GPU/Suche |
| `aura/gui.py` | Oberfläche (tkinter) |
| `tools/` | Migration aus dem Prototyp, Eval |
| `data/` `models/` `logs/` | lokal, **nie** im Repository (siehe `.gitignore`) |

## Hinweise
- Repository **privat** halten.
- Datenbank `data\aura.db` nur auf lokalem Laufwerk (nicht OneDrive/Netzlaufwerk).
- Drittkomponenten in `vendor/`: comtypes (MIT), customtkinter (MIT), darkdetect (BSD), packaging (Apache-2.0/BSD) – alles reines Python.
