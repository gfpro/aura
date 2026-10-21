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
- Anschliessen von lokalen Quellen wie Outlook (lokale Mails & Kalender), Edge-Verlauf, Dokumentenordner, Confluence-Seiten mit Leserechten, OneNote (und bald noch mehr...).
- Suche nach Wörtern und nach Bedeutung (Vektoren), kombiniert.
- Filter nach Person und Zeitraum aus der Frage heraus («Was schrieb X letzte Woche zum Budget?»).
- Antworten mit Quellenangaben; ohne Sprachmodell zeigt AURA die besten Fundstellen.

**Workflows**
- Füllen eine Word-Vorlage aus Unterlagen (z.B. PDF) aus – auf Knopfdruck oder nach Zeitplan.
- Neue Workflows entstehen mit «Workflow beschreiben» und einer Word-Vorlage. AURA erstellt daraus einen **Feldplan**: Für jedes Feld wird festgelegt, ob der Wert aus den Unterlagen stammt (*Fakt*), sich aus einer Regel ergibt (*Abgeleitet*), immer gleich ist (*Fest*) oder von Hand ergänzt wird (*Manuell*).
- Grundsatz: **Fakten liest das Sprachmodell, Entscheide trifft eine Regel.** Regeln werden ohne Programmierung im Feldplan erfasst («Wenn Betrag > 5000 → Zweite Unterschrift») und laufen ohne Sprachmodell.
- Jeder Lauf erzeugt das Ergebnisdokument und einen getrennten Prüfbericht (Hinweise, Platzhalter, welche Regel gegriffen hat).

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

1. Zuerst sicherstellen, dass Python (min. 3.11) installiert ist. Für BV-MA im BIT-Store in Schale 3B bestellbar.
2. Die Release-ZIP von der Seite *Releases* herunterladen (Source code (zip)).
3. In einen lokalen Ordner entpacken, z.B. `C:\aura`. **Nicht** in OneDrive oder auf Netzlaufwerke – die Datenbank verträgt keine Synchronisation.
4. Modelle von Hugging Face herunterladen und in `C:\aura\models\` ablegen (Details: `C:\aura\models\README.md`):

   | Modell | Zweck | Ordner |
   | --- | --- | --- |
   | [intfloat/multilingual-e5-large](https://huggingface.co/intfloat/multilingual-e5-large) | Suche nach Bedeutung (Pflicht) | `models\multilingual-e5-large\` |
   | [Qwen/Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | Besser für kurze Antworten | `models\Qwen3-4B\` |
   | [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) | Besser für lange Antworten | `models\Qwen3.5-4B\` |

   Jeder Modellordner braucht `config.json`, `tokenizer.json` und die `*.safetensors`-Dateien.
6. Doppelklick auf `AURA.pyw`. Beim ersten Start legt AURA Datenbank und Einstellungen an.

Ohne Sprachmodell funktioniert AURA ebenfalls und zeigt statt ausformulierter Antworten die besten Fundstellen.

## Erste Schritte
**Chat**:
1. Im linken Seitenmenu «Quellen» öffnen, Quellen verbinden und **Sync** drücken. Bei Outlook zuerst **Ordner** wählen.
2. Danach im linken Seitenmenu **Vektoren berechnen** – einmalig, je nach Datenmenge Minuten bis Stunden; danach nur noch neue Einträge.
3. Im linken Seitenmenu Sprachmodell wählen und **Laden** (ca. 1 Minute).
4. Frage stellen.

**Workflow**:
1. Neuer Workflow im linken Seitenmenu unter **«Workflows öffnen»** → **«+Neuer Workflow»** starten.
2. Im neuen Fenster kann der Workflow entweder beschrieben oder zusammengebaut werden. Sobald die Beschreibung erstellt wurde, kann mit **«Mit Sprachmodell verstehen und Workflow bauen** der Workflow automatisiert erstellt werden. Sollte das Sprachmodell noch nicht geladen sein, braucht AURA zirka eine Minute für das Laden des Sprachmodells.
3. Im unteren Fenster kann der Workflow angepasst werden. Danach Klick auf **«Workflows bauen»**.
4. Im Hauptfenster erscheint danach der Workflow mit verschiedene Tabs. Unter dem Tab **«Ausführen»** kann der Workflow über «Starten» gestartet werden.
5. Der Output wird im gewählten Stil angezeigt (Mail an mich, oder im Dashboard AURA etc.).
 
Komplexere Workflows können mit Dokumenten (unter dem Tab «Ausführen»), mit immer wieder benötigten Hilfsdokumenten (unter dem Tab «Wissen») und mit vordefinierten Vorlagen (unter dem Tab «Vorlagen») konfiguriert werden. Anleitung für Gestalter: [anleitung/AURA_Workflows_Anleitung.pdf](anleitung/AURA_Workflows_Anleitung.pdf)

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
- Arbeitsspeicher-Auslastung während dem Betrieb sehr hoch (~90%).

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
