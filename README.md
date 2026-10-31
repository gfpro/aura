# AURA – Artificial Understanding & Retrieval Assistant

Ein lokales «zweites Gehirn» für Windows: AURA durchsucht deine Outlook-Mails und -Termine, den Edge-Verlauf und Dokumentordner und beantwortet Fragen dazu – vollständig auf dem eigenen Rechner. Dazu kommen eine Workflow-Engine, die Word-Vorlagen aus Unterlagen ausfüllt und grafisch zusammengebaut wird, sowie Präsentationen aus angehängten Dokumenten.

Stand: v156 (Oktober 2026) · Änderungen: [CHANGELOG.md](CHANGELOG.md)

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
- Datei anhängen (📎): Fragen zu einem Dokument, das nur für diesen Chat gilt; Chats bleiben 30 Tage im Verlauf.
- Optional eine **Rolle** wählen (z.B. «Beschaffungsspezialist»), die die Arbeitsweise des Sprachmodells festlegt.

**Präsentationen**
- Datei anhängen und «▶ Als Präsentation» klicken (oder «Mach daraus eine Präsentation» schreiben): AURA erstellt eine PowerPoint in der Vorlage der Bundesverwaltung, gegliedert nach den Kapiteln des Dokuments.
- Leitplanken ohne Sprachmodell: erfundene Zahlen werden entfernt, fehlende Einschränkungen («grundsätzlich») ergänzt und zur Prüfung gemeldet. Ergebnis ist ein Entwurf.

**Workflows**
- Füllen eine Word-Vorlage aus Unterlagen (z.B. PDF) aus – auf Knopfdruck oder nach Zeitplan.
- Grafisch bauen auf der **Leinwand**: Bausteine aus der Palette hinzufügen, per Ziehen verbinden, Pfeil anklicken zum Lösen; Mausrad = Zoom, rechte Maustaste = verschieben. Rot markiert fehlende Werte oder eine falsche Reihenfolge.
- Neue Workflows entstehen mit «Workflow beschreiben» und einer Word-Vorlage. AURA erstellt daraus einen **Feldplan**: Für jedes Feld wird festgelegt, ob der Wert aus den Unterlagen stammt (*Fakt*), sich aus einer Regel ergibt (*Abgeleitet*), immer gleich ist (*Fest*) oder von Hand ergänzt wird (*Manuell*).
- Grundsatz: **Fakten liest das Sprachmodell, Entscheide trifft eine Regel.** Regeln werden ohne Programmierung im Feldplan erfasst («Wenn Betrag > 5000 → Zweite Unterschrift») und laufen ohne Sprachmodell.
- Jeder Lauf erzeugt das Ergebnisdokument und einen getrennten Prüfbericht (Hinweise, Platzhalter, welche Regel gegriffen hat).

**Skills & Rollen**
- Skills und Rollen (Markdown, z.B. von Kollegen) importieren und freigeben unter «Workflows › Skills & Rollen». Neues oder Geändertes bleibt aus, bis es geprüft und freigegeben ist.

**Wissen**
- Wissenssammlungen (z.B. Gesetzestexte) für Workflows und optional für den Chat; Rechtstexte werden nach Artikeln zerlegt und zitierbar («BöB Art. 21»).

## Voraussetzungen

| | |
| --- | --- |
| Betriebssystem | Windows 10 oder 11 (64-bit) |
| Python | 3.10 oder neuer, mit tkinter (Standardinstallation von python.org) |
| Grafikkarte | DirectX 11 / DirectML; getestet nur mit integrierter GPU von Intel Core Ultra |
| Arbeitsspeicher | 16 GB, für Sprachmodelle ab 4B rund 32 GB |
| Speicherplatz | ca. 15 MB, 3 GB für das Embedding-Modell, plus 8–17 GB je Sprachmodell |
| Optional | klassisches Microsoft Outlook (Mails, Kalender), Microsoft Edge (Verlauf) |
| Umgebung | Die Nutzung ist für den BIT Client (HP Elitebook 8 G1i) optimiert. |

## Installation

1. Zuerst sicherstellen, dass Python (min. 3.10) installiert ist. Für BV-MA im BIT-Store in Schale 3B bestellbar.
2. Die Release-ZIP von der Seite *Releases* herunterladen (Source code (zip)).
3. In einen lokalen Ordner entpacken, z.B. `C:\aura`. **Nicht** in OneDrive oder auf Netzlaufwerke – die Datenbank verträgt keine Synchronisation.
4. Modelle von Hugging Face herunterladen und in `C:\aura\models\` ablegen (Details: `C:\aura\models\README.md`):

   | Modell | Zweck | Ordner |
   | --- | --- | --- |
   | [intfloat/multilingual-e5-large](https://huggingface.co/intfloat/multilingual-e5-large) | Suche nach Bedeutung (Pflicht) | `models\multilingual-e5-large\` |
   | [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) | Schneller für Chat | `models\Qwen3.5-4B\` |
   | [Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) | Besser für Workflow | `models\Qwen3.5-9B\` |

   Jeder Modellordner braucht `config.json`, `tokenizer.json` und die `*.safetensors`-Dateien.
5. Doppelklick auf `AURA.pyw`. Beim ersten Start legt AURA Datenbank und Einstellungen an.

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
4. Der Workflow erscheint im Reiter **«Bauen»** als Leinwand. Klick auf einen Baustein zeigt Details, Doppelklick öffnet das Formular, «▶ Start» zeigt Eingaben und Zeitplan.
5. Im Reiter **«Ausführen»** Dateien wählen und «Starten» drücken. Der Output erscheint im gewählten Stil (Mail an mich, Anzeige in AURA etc.).

Hilfsdokumente (**«📚 Wissen»**), Word-Vorlagen samt Feldplan (**«📄 Vorlagen & Feldplan»**) und Prüfpunkte (**«✓ Prüfliste»**) öffnen sich über die Knöpfe über der Leinwand oder am passenden Baustein. Anleitung für Gestalter: [anleitung/AURA_Workflows_Anleitung.pdf](anleitung/AURA_Workflows_Anleitung.pdf)

## Daten verwalten

| Was | Wo | Wirkung |
| --- | --- | --- |
| Einzelnen Lauf löschen | «Ergebnisse» → «Löschen» | Laufordner wandert nach `workflows\_geloescht\_laeufe` (zurückholbar) |
| Workflow löschen | Workflow → «⋯» → «Löschen …» | Paket wandert nach `workflows\_geloescht` (zurückholbar) |
| Alles zurücksetzen | «Quellen» → «Alles zurücksetzen …» | Löscht alle eingelesenen Mails, Termine, Verlaufseinträge und Dokumente samt Vektoren, den Synchronisationsstand und die Quellenauswahl; schaltet den Auto-Abgleich aus. AURA startet neu. Outlook, Originaldateien, Wissen, Workflows und Modelle bleiben. |

Speicherplatz prüfen und aufräumen: `py tools\ordner_pruefen.py` zeigt je Ordner Grösse, Zweck und was gelöscht werden kann (ändert nichts).

## Updates

Die ZIP der neuen Version in «Downloads» speichern, AURA schliessen und im AURA-Ordner ausführen:

```
py tools\patch_einspielen.py
```

Die Datenordner `data\`, `models\`, `workflows\` und `wissen\` bleiben erhalten.

## Datenschutz

- Alle Daten bleiben auf dem Rechner: Datenbank in `data\`, Protokolle in `logs\`, Workflow-Läufe in `workflows\<name>\laeufe\`, Präsentationen in `data\praesentationen\`.
- AURA liest Outlook und Dateien nur; es verändert oder löscht dort nichts.
- **Für Mitwirkende:** `data\`, `logs\`, `models\`, `workflows\*\laeufe\` und die Dokumente in `wissen\` bzw. `workflows\*\wissen\` nie committen – die `.gitignore` schliesst sie aus. Word-Vorlagen nur einchecken, wenn sie nicht vertraulich sind. Vor einem Commit hilft `py tools\ordner_pruefen.py` (Abschnitt «schon in Git erfasst»).

## Grenzen

- Kleine lokale Modelle (4B/9B) machen Fehler. Workflow-Ergebnisse und Präsentationen sind Entwürfe zur fachlichen Prüfung, keine Entscheide.
- Eine Präsentation aus einem 40-seitigen Bericht dauert rund 8 Minuten (9B).
- Pakete mit eigenen DLLs (z.B. lxml, Pillow) blockiert die Gruppenrichtlinie des BIT Clients; AURA kommt ohne sie aus (Word und PowerPoint direkt als XML).
- Gescannte PDFs ohne Textschicht (OCR) werden nicht gelesen (keine Texterkennung).
- Ein Workflow-Lauf dauert mit einem 4B-Modell auf integrierter Grafik je nach Vorlage 2–5 Minuten. Notebook während eines Laufs nicht zuklappen; Zeitplan-Läufe starten nur, wenn AURA offen ist.
- Getestet auf Hardwareklasse der HP EliteBook mit AI-Features.
- Arbeitsspeicher-Auslastung während dem Betrieb sehr hoch (~90%).

## Aufbau

| Ordner | Inhalt | Im Repository |
| --- | --- | --- |
| `AURA.pyw` | Startskript (Doppelklick) | ja |
| `aura\` | Programm: Oberfläche, Suche, Konnektoren, GPU-Engine, Workflow-Engine, Präsentationsvorlage (`assets\`) | ja |
| `tools\` | Kommandozeilenwerkzeuge (`wf_run.py`, `ordner_pruefen.py`, Updates, Messungen) | ja (nur `*.py`, ohne `tools\lxml_test\`) |
| `vendor\` | mitgelieferte Pakete | ja |
| `anleitung\` | Anleitungen | ja |
| `rollen\` | Rollen für Chat und Sprachmodell-Schritte (Markdown) | nur nicht vertrauliche |
| `pruefpakete\` | fertige Prüfpunkte für Prüflisten | ja |
| `workflows\` | Workflow-Pakete (`workflow.json`, Vorlagen, Wissen, Läufe) | nur `workflow.json` (Vorlagen nach Prüfung) |
| `wissen\` | gemeinsame Wissenssammlungen | nur `LIESMICH.md` |
| `models\` | Sprach- und Embedding-Modelle | nein |
| `data\`, `logs\` | Datenbank, Einstellungen, Protokolle – entstehen beim ersten Start | nein |

## Lizenz

Die Komponenten Dritter sowie die Modelle stehen unter eigenen Lizenzen: Qwen3.5 unter Apache 2.0, multilingual-e5-large unter MIT. AURA ist primär ein Prototyp, der für den Test im BV-Netz gedacht ist.
