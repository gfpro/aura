# AURA – Artificial Understanding & Retrieval Assistant

Ein lokales «zweites Gehirn» für Windows: AURA durchsucht deine Outlook-Mails und -Termine, den Edge-Verlauf und Dokumentordner und beantwortet Fragen dazu – vollständig auf dem eigenen Rechner. Dazu kommt eine Workflow-Engine, die Word-Vorlagen aus Unterlagen ausfüllt.

Stand: v64 (Oktober 2026) · Änderungen: [CHANGELOG.md](CHANGELOG.md)

---

## Warum AURA

- **Lokal:** Keine Cloud, keine Telemetrie, keine externen Modellaufrufe. Das Sprachmodell läuft auf der Intel Grafikkarte des Notebooks.
- **Ohne Installation:** Reines Python, kein `pip`, keine Administratorrechte. Start per Doppelklick auf `AURA.pyw`.
- **Nachvollziehbar:** Antworten nennen ihre Quellen; Workflow-Entscheide stammen aus Regeln, nicht aus dem Bauchgefühl des Modells.

## Funktionen

**Fragen stellen**
- Suche nach Wörtern und nach Bedeutung (Vektoren), kombiniert.
- Filter nach Person und Zeitraum aus der Frage heraus («Was schrieb X letzte Woche zum Budget?»).
- Antworten mit Quellenangaben; ohne Sprachmodell zeigt AURA die besten Fundstellen.

**Workflows**
- Füllen eine Word-Vorlage aus Unterlagen (z.B. PDF) aus – auf Knopfdruck oder nach Zeitplan.
- Neue Workflows entstehen mit «Workflow beschreiben» und einer Word-Vorlage. AURA erstellt daraus einen **Feldplan**: Für jedes Feld wird festgelegt, ob der Wert aus den Unterlagen stammt (*Fakt*), sich aus einer Regel ergibt (*Abgeleitet*), immer gleich ist (*Fest*) oder von Hand ergänzt wird (*Manuell*).
- Grundsatz: **Fakten liest das Sprachmodell, Entscheide trifft eine Regel.** Regeln werden ohne Programmierung im Feldplan erfasst («Wenn Betrag > 5000 → Zweite Unterschrift») und laufen ohne Sprachmodell.
- Jeder Lauf erzeugt das Ergebnisdokument und einen getrennten Prüfbericht (Hinweise, Platzhalter, welche Regel gegriffen hat).
- Anleitung für Gestalter: [docs/WORKFLOWS.md](docs/WORKFLOWS.md)

**Wissen**
- Wissenssammlungen (z.B. Gesetzestexte) für Workflows und optional für den Chat; Rechtstexte werden nach Artikeln zerlegt und zitierbar («BöB Art. 21»).

## Voraussetzungen

| | |
| --- | --- |
| Betriebssystem | Windows 10 oder 11 (64-bit) |
| Python | 3.11 oder neuer, mit tkinter (Standardinstallation von python.org) |
| Grafikkarte | DirectX 11 / DirectML; getestet nur mit integrierter GPU von Intel Core Ultra |
| Arbeitsspeicher | 16 GB, für Sprachmodelle ab 4B rund 32 GB |
| Speicherplatz | ca. 15 MB, 3 GB für das Embedding-Modell, plus 8–17 GB je Sprachmodell |
| Optional | klassisches Microsoft Outlook (Mails, Kalender), Microsoft Edge (Verlauf) |
| Umgebung | Die Nutzung ist für den BIT Client (HP Elitebook 8 G1i) optimiert. |

## Installation

1. Die Release-ZIP von der Seite *Releases* herunterladen (nicht «Code → Download ZIP»).
2. In einen lokalen Ordner entpacken, z.B. `C:\aura`. **Nicht** in OneDrive oder auf Netzlaufwerke – die Datenbank verträgt keine Synchronisation.
3. Modelle von Hugging Face herunterladen und in `models\` ablegen (Details: `models/README.md`):

   | Modell | Zweck | Ordner |
   | --- | --- | --- |
   | [intfloat/multilingual-e5-large](https://huggingface.co/intfloat/multilingual-e5-large) | Suche nach Bedeutung (Pflicht) | `models\multilingual-e5-large\` |
   | [Qwen/Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | Antworten und Workflows (empfohlen) | `models\Qwen3-4B\` |

   Jeder Modellordner braucht `config.json`, `tokenizer.json` und die `*.safetensors`-Dateien.
4. Doppelklick auf `AURA.pyw`. Beim ersten Start legt AURA Datenbank und Einstellungen an.

Ohne Sprachmodell funktioniert AURA ebenfalls und zeigt statt ausformulierter Antworten die besten Fundstellen.

## Erste Schritte

1. «Quellen» öffnen, Quellen verbinden und **Sync** drücken. Bei Outlook zuerst **Ordner** wählen.
2. **Vektoren berechnen** – einmalig, je nach Datenmenge Minuten bis Stunden; danach nur noch neue Einträge.
3. Sprachmodell wählen und **Laden** (ca. 1 Minute).
4. Frage stellen.

Workflow ausführen: «Workflows öffnen» → Workflow wählen → «Dateien wählen …» → «▶ Starten». Ergebnis und Prüfbericht erscheinen nach dem Lauf als Knöpfe und unter «Ergebnisse».

## Daten verwalten

| Was | Wo | Wirkung |
| --- | --- | --- |
| Einzelnen Lauf löschen | «Ergebnisse» → «Löschen» | Laufordner wandert nach `workflows\_geloescht\_laeufe` (zurückholbar) |
| Workflow löschen | Workflow → «Löschen» | Paket wandert nach `workflows\_geloescht` (zurückholbar) |
| Alles zurücksetzen | «Quellen» → «Alles zurücksetzen …» | Löscht alle eingelesenen Mails, Termine, Verlaufseinträge und Dokumente samt Vektoren, den Synchronisationsstand und die Quellenauswahl; schaltet den Auto-Abgleich aus. AURA startet neu. Outlook, Originaldateien, Wissen, Workflows und Modelle bleiben. |

Speicherplatz prüfen und aufräumen: `py tools\ordner_pruefen.py` zeigt je Ordner Grösse, Zweck und was gelöscht werden kann (ändert nichts).

## Updates

Die ZIP der neuen Version in «Downloads» speichern, AURA schliessen und im AURA-Ordner ausführen:

```
py tools\patch_einspielen.py
```

Die Datenordner `data\`, `models\`, `workflows\` und `wissen\` bleiben erhalten.

## Datenschutz

- Alle Daten bleiben auf dem Rechner: Datenbank in `data\`, Protokolle in `logs\`, Workflow-Läufe in `workflows\<name>\laeufe\`.
- AURA liest Outlook und Dateien nur; es verändert oder löscht dort nichts.
- **Für Mitwirkende:** `data\`, `logs\`, `models\`, `workflows\*\laeufe\` und die Dokumente in `wissen\` bzw. `workflows\*\wissen\` nie committen – die `.gitignore` schliesst sie aus. Word-Vorlagen nur einchecken, wenn sie nicht vertraulich sind. Vor einem Commit hilft `py tools\ordner_pruefen.py` (Abschnitt «schon in Git erfasst»).

## Grenzen

- Kleine lokale Modelle (4B/8B) machen Fehler. Workflow-Ergebnisse sind Entwürfe zur fachlichen Prüfung, keine Entscheide.
- Gescannte PDFs ohne Textschicht (OCR) werden nicht gelesen (keine Texterkennung).
- Ein Workflow-Lauf dauert mit einem 4B-Modell auf integrierter Grafik je nach Vorlage 2–5 Minuten. Notebook während eines Laufs nicht zuklappen; Zeitplan-Läufe starten nur, wenn AURA offen ist.
- Getestet auf Hardwareklasse der HP EliteBook mit AI-Features.

## Aufbau

| Ordner | Inhalt | Im Repository |
| --- | --- | --- |
| `AURA.pyw` | Startskript (Doppelklick) | ja |
| `aura\` | Programm: Oberfläche, Suche, Konnektoren, GPU-Engine, Workflow-Engine | ja |
| `tools\` | Kommandozeilenwerkzeuge (`wf_run.py`, `ordner_pruefen.py`, Updates, Messungen) | ja (nur `*.py`) |
| `vendor\` | mitgelieferte Pakete | ja |
| `docs\` | Anleitungen | ja |
| `pruefpakete\` | fertige Prüfpunkte für Prüflisten | ja |
| `workflows\` | Workflow-Pakete (`workflow.json`, Vorlagen, Wissen, Läufe) | nur `workflow.json` (Vorlagen nach Prüfung) |
| `wissen\` | gemeinsame Wissenssammlungen | nur `LIESMICH.md` |
| `models\` | Sprach- und Embedding-Modelle | nein |
| `data\`, `logs\` | Datenbank, Einstellungen, Protokolle – entstehen beim ersten Start | nein |

## Lizenz

Komponenten Dritter sind in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) aufgeführt (customtkinter, comtypes, pypdf). Die Modelle stehen unter eigenen Lizenzen: Qwen3 unter Apache 2.0, multilingual-e5-large unter MIT.
