# AURA – Artificial Understanding & Retrieval Assistant

**Dein lokales «zweites Gehirn» für Windows.** AURA durchsucht deine Outlook-Mails, deinen Kalender, deinen Edge-Verlauf und deine Dokumente und beantwortet Fragen dazu – vollständig auf deinem Rechner. Dazu kommt eine schlanke Workflow-Engine, die Unterlagen nach festen Regeln prüft und Word-Vorlagen ausfüllt.

> *A local, privacy-first search & question-answering assistant for Outlook, calendar, browser history and documents, with a lightweight workflow engine. Runs entirely on a Windows laptop GPU in pure Python – no cloud, no installation.*

---

## Warum AURA

- **Alles bleibt lokal.** Keine Cloud, keine Telemetrie, keine Eingaben an fremde Modelle. Sprachmodell und Suche laufen auf der eigenen Grafikkarte.
- **Keine Installation.** Reines Python mit mitgelieferten Paketen. Kein `pip`, kein Admin-Recht, kein PyTorch – die GPU wird direkt über DirectX angesprochen.
- **Start per Doppelklick** auf `AURA.pyw`.

## Funktionen

**Fragen an die eigenen Daten**
- Quellen per Schalter: Outlook-Mails (Ordner wählbar), Outlook-Kalender, Edge-Verlauf, Dokumentordner (PDF mit Text, Word, Text, Markdown)
- Hybride Suche (Stichwort + Bedeutung) mit Filtern für Person und Zeitraum
- Antworten mit Quellenangabe; Klick öffnet das Original in Outlook bzw. die Datei
- Listen ohne Sprachmodell, z.B. «Welche Termine habe ich diese Woche?»
- Automatischer Abgleich alle 15 Minuten
- Infotexte zu jedem Knopf und Feld (Mouseover)

**Workflows**
- Unterlagen einlesen → Fakten durch das Sprachmodell erfassen → **Entscheide per Regeltabelle** (rechnen und vergleichen macht nie das Modell) → feste **Word-Vorlage** ausfüllen
- **Belegpflicht:** Angaben, die nur mit wörtlichem Zitat aus den Unterlagen gelten; erfundene Zitate werden erkannt und verworfen
- Sichtbare Platzhalter statt erfundenem Text, wenn Informationen fehlen
- **Prüfbericht** getrennt vom Ergebnisdokument: Hinweise, verworfene Angaben, Belege, Plausibilitätsprüfungen
- Eigene Wissenssammlungen je Workflow (z.B. Gesetzestexte, nach Artikeln zerlegt, mit Stand-Datum)
- Workflows als Pakete (`workflow.json` + Wissen + Vorlagen + Läufe), vollständig im Fenster verwaltbar
- Zwischenstand nach jedem Schritt, «ab Schritt neu starten», Prompt-Cache für wiederkehrende Teile

## Voraussetzungen

| | |
|---|---|
| Betriebssystem | Windows 10/11 (64 Bit) |
| Python | 3.11 oder neuer, mit tkinter (Standardinstallation von python.org) |
| Grafikkarte | DirectX 11 / DirectML; **getestet nur auf Intel Core Ultra (integrierte GPU)**. Andere GPUs sind ungetestet. |
| Arbeitsspeicher | 16 GB, für Sprachmodelle ab 4B-Grösse eher 32 GB |
| Speicherplatz | ~3 GB (Embedding) + 8–17 GB je Sprachmodell |
| Optional | Microsoft Outlook (klassisch) für Mail und Kalender; Microsoft Edge für den Verlauf |

## Installation

1. **Release-ZIP herunterladen** (Seite *Releases*, nicht «Code → Download ZIP»).
2. **Entpacken in einen lokalen Ordner**, z.B. `C:\aura`. Nicht in OneDrive oder auf ein Netzlaufwerk – die Datenbank verträgt keine Synchronisation.
3. **Modelle herunterladen** von Hugging Face und in `models\` ablegen (Details in [`models/README.md`](models/README.md)):
   - Embedding (Pflicht): [`intfloat/multilingual-e5-large`](https://huggingface.co/intfloat/multilingual-e5-large) → `models\multilingual-e5-large\`
   - Sprachmodell (optional, für ausformulierte Antworten und Workflows): z.B. [`Qwen/Qwen3-4B-Instruct-2507`](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) → `models\Qwen3-4B\`
   - Benötigt werden je Ordner `config.json`, `tokenizer.json` und die `*.safetensors`-Dateien.
4. **`AURA.pyw` doppelklicken.** Beim ersten Start legt AURA Datenbank und Einstellungen selbst an.

Ohne Sprachmodell funktioniert AURA auch: Es zeigt dann die besten Fundstellen statt einer ausformulierten Antwort.

## Erste Schritte

1. Zahnrad **⚙** → Quellen verbinden und **Sync** drücken (bei Outlook vorher **Ordner** wählen).
2. **Vektoren berechnen** – einmalig, je nach Datenmenge einige Minuten bis Stunden; danach nur noch für Neues.
3. Sprachmodell wählen und **Laden** (ca. 1 Minute).
4. Frage stellen.

Workflows: **Workflows öffnen** → Workflow wählen → Dateien wählen → **▶ Starten**. Ergebnis und Prüfbericht erscheinen nach dem Lauf als Knöpfe.

## Updates

Neue Version als ZIP in «Downloads» speichern, AURA schliessen und im AURA-Ordner ausführen:

```
py tools\patch_einspielen.py
```

Eigene Daten (`data\`, `models\`, `workflows\`, `wissen\`) bleiben erhalten.

## Datenschutz

- AURA liest Outlook, Kalender und Verlauf **nur lokal** und speichert die Texte in einer lokalen SQLite-Datenbank (`data\`).
- Es gibt keine Netzverbindung ausser dem Laden offizieller Quellen, wenn ein Workflow das ausdrücklich vorsieht.
- Eingabedateien eines Workflow-Laufs werden nie in die allgemeine Suche aufgenommen.
- Die Datenbank enthält Inhalte deiner Mails: Ordner entsprechend schützen und nie in ein Repository oder einen synchronisierten Ordner legen.

## Grenzen

- Kleine lokale Modelle (4B/8B) machen Fehler. Ergebnisse von Workflows sind **Entwürfe zur fachlichen Prüfung**, keine Entscheide.
- Gescannte PDFs ohne Textschicht werden nicht gelesen (kein OCR).
- Ein Workflow-Lauf mit einem 4B-Modell dauert auf einer integrierten GPU 5–15 Minuten. Das Notebook nicht zuklappen.
- Getestet auf einer einzigen Hardware-Klasse.

## Aufbau

```
AURA.pyw        Start
aura\           Programm (Oberfläche, Suche, Konnektoren, GPU-Engine, Workflow-Engine)
tools\          Kommandozeile (wf_run.py), Updates, Messwerkzeuge
vendor\         mitgelieferte Pakete
models\         Modelle (nicht im Repository)
workflows\      Workflow-Pakete
wissen\         gemeinsame Wissenssammlungen
data\ logs\     werden beim Start angelegt (nicht im Repository)
```

Workflow-Format und Bausteine: siehe [`docs/workflows.md`](docs/workflows.md).

## Lizenz

Drittkomponenten: siehe [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) (customtkinter, comtypes, pypdf). Die Modelle unterliegen ihren eigenen Lizenzen (Qwen3: Apache 2.0, multilingual-e5-large: MIT).
