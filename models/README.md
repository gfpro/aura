# Modelle (nicht im Repository – zu gross für GitHub)

## Embedding (Pflicht für die Vektorsuche)
`models/multilingual-e5-large/` mit `config.json`, `model.safetensors`, `tokenizer.json`
Quelle: https://huggingface.co/intfloat/multilingual-e5-large

## Sprachmodell (optional, nächster Baustein)
Je ein Ordner pro Modell, z.B. `models/Qwen2.5-3B-Instruct/` mit `config.json`, `*.safetensors`, `tokenizer.json`.
AURA erkennt Modelle automatisch an `config.json` (Feld `architectures`).
