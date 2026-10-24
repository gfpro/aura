# Modelle (nicht im Repository – zu gross für GitHub)

## Embedding (Pflicht für die Vektorsuche)
`models/multilingual-e5-large/` mit `config.json`, `model.safetensors`, `tokenizer.json`
Quelle: https://huggingface.co/intfloat/multilingual-e5-large

## Sprachmodell (optional, nächster Baustein)
Je ein Ordner pro Modell, z.B. `models/Qwen3.5-4B/` mit `chat_template.jinja`, `config.json`, `merges.txt`, `*.safetensors`, `preprocessor_config.json`, `tokenizer.json`, `tokenizer_config.json`, `vocab.json`.
AURA erkennt Modelle automatisch an `config.json` (Feld `architectures`).

## Sprachmodell (optional, nächster Baustein)
Je ein Ordner pro Modell, z.B. `models/Qwen3.5-9B/` mit `chat_template.jinja`, `config.json`, `merges.txt`, `*.safetensors`, `preprocessor_config.json`, `tokenizer.json`, `tokenizer_config.json`, `vocab.json`.
AURA erkennt Modelle automatisch an `config.json` (Feld `architectures`).
