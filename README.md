# AURA – Artificial Understanding & Retrieval Assistant

Ein lokales «zweites Gehirn» für Windows: AURA durchsucht deine Outlook-Mails und -Termine, den Edge-Verlauf und Dokumentordner und beantwortet Fragen dazu – vollständig auf dem eigenen Rechner. Dazu kommen eine Workflow-Engine, die Word-Vorlagen aus Unterlagen ausfüllt und grafisch zusammengebaut wird, sowie Präsentationen aus angehängten Dokumenten.

Stand: v212 (November 2026) · Änderungen: [CHANGELOG.md](CHANGELOG.md)

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
   | [swiss-ai/Apertus-v1.5-8B](https://huggingface.co/swiss-ai/Apertus-v1.5-8B) | Gut für den Chat | `models\Apertus1.5-8B\` |

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

Zwei Varianten für die Updates. Die ZIP der neuen Version in «Downloads» speichern, AURA schliessen.

**Variante A:** Paket entzippen und das ursprüngliche AURA-Verzeichnis (C:\aura) überschreiben.

**Variante B:** Über die Kommandozeile im AURA-Verzeichnis (C:\aura) ausführen:

```
py tools\patch_einspielen.py
```

Bei beiden Varianten bleiben die Datenordner `data\`, `models\`, `workflows\` und `wissen\` erhalten.

**Ab v208 prüft `patch_einspielen.py` jedes Paket vollständig, bevor es eine Datei ändert:** Pfade (kein `..`, kein Laufwerk/UNC, kein `\`, kein `:`/ADS, keine Gerätenamen, keine Links aus `C:\aura` hinaus), Doppelte, Grössen und ZIP-Bomben. `data\`, `logs\`, `_sicherung\` und `.git\` sind gesperrt. Bei einem Fehler wird alles zurückgerollt. Zusätzlich verlangt das Skript eine **Signatur** (`_manifest.json` + `_manifest.sig`, Ed25519). Den öffentlichen Schlüssel verteilt die IT per Richtlinie: `HKLM\SOFTWARE\Policies\AURA`, Wert `UpdateSchluessel` (hex). Signiert wird nur auf dem Release-Rechner mit `py tools\patch_signieren.py`; der geheime Schlüssel liegt nie in `C:\aura` oder in Git. Solange kein Schlüssel verteilt ist: `py tools\patch_einspielen.py --ohne-signatur` – dann ist die Herkunft **nicht** geprüft (nur Pakete aus sicherer Quelle).

## Sicherheit (v208/v212)

- **Confluence:** nur `https://` und nur freigegebene Hosts (Standard `confluence.bit.admin.ch`; Liste per Richtlinie `HKLM\SOFTWARE\Policies\AURA`, Wert `ConfluenceHosts`). Links mit Port oder Zugangsdaten werden abgelehnt, Weiterleitungen auf andere Hosts ebenfalls. Der Token geht nur an den freigegebenen Host.
- **Confluence-Token:** verschlüsselt mit Windows DPAPI (nur dein Windows-Konto kann ihn lesen), Datei `data\confluence_token.dpapi`. Setzen: `py tools\confluence_token_setzen.py`. Eine alte `data\confluence_token.txt` wird beim ersten Sync verschlüsselt und danach gelöscht; klappt die Verschlüsselung nicht, wird der Token nicht verwendet (kein Klartext-Rückfall).
- **Workflows** lesen nur Dateien aus dem eigenen Workflow-Ordner und die Dateien, die du beim Start ausgewählt hast. Vorlagen müssen im Workflow-Ordner liegen. Recap-Ordner nur innerhalb von `C:\aura`.
- **Workflow-Pakete:** Manifest und Sammlungsnamen werden vollständig geprüft; Import gemeinsamer Sammlungen wird bei Fehlern zurückgerollt.
- **Grenzen:** ZIP max. 20 000 Einträge, 512 MB je Datei, 2 GB gesamt, Kompressionsverhältnis 200; Dokumente max. 200 MB, PDF max. 3 000 Seiten bzw. 300 s Textextraktion, Word-Inhalt max. 64 MB (`aura\sicherheit.py`).
- **Quellen im Sprachmodell** sind als Daten markiert; Anweisungen darin sollen ignoriert werden. Das senkt das Risiko von Prompt Injection, verhindert es aber nicht sicher – Ergebnisse zu Freigaben, Beträgen, Fristen und Zuständigkeiten immer an der Quelle prüfen.
- **Skills:** der Baustein «Mail an mich» läuft in einem Skill nur, wenn der Skill freigegeben ist und das Recht `extern` deklariert. Die Freigabe-Prüfsumme (SHA-256) zeigt Änderungen an, belegt aber **nicht** den Autor.
- **Betriebsvoraussetzungen (prüft AURA nicht selbst):** persönliches Windows-Konto; Festplattenverschlüsselung (BitLocker o.ä.); lokaler, nicht synchronisierter Installationsordner; Netzwerkzugriff nur auf den Confluence-Endpunkt. NTFS-Rechte der Datenordner auf «nur ich + SYSTEM + Administratoren» setzen: `py tools\datenordner_absichern.py --setzen` (sichert die alten Rechte; Rückgängig mit `--zurueck <Sicherungsdatei>`).
- **Live-Quellen (Acta Nova, Intranet, SharePoint):** nur freigegebene https-Origins, exakt verglichen (Schema, Host, Port) – Standard `www.vbs.gever.admin.ch`, `intranet.ar.admin.ch`, `portal.collab.admin.ch`; per Richtlinie `HKLM\SOFTWARE\Policies\AURA`, Werte `LiveOrigins_actanova`, `LiveOrigins_intranet`, `LiveOrigins_sharepoint`. Eingetragene URLs, Suchtreffer, neue Tabs und Navigationen ausserhalb davon werden abgelehnt; vor dem Auslesen wird die aktuelle Seite erneut geprüft (Redirects).
- **Datenfluss bei eingeschalteten Live-Quellen:** der Suchbegriff geht an die jeweilige Quelle (nur diese), die gelesenen Treffer/Seiten bleiben im Arbeitsspeicher und gehen nur ans lokale Sprachmodell; nichts an externe Dienste. AURA ist dann nicht mehr vollständig offline.
- **AURA-Edge:** eigenes Profil `data\edge_profil`; Edge wählt den Debug-Port selbst, AURA verbindet nur, wenn die Browser-ID im Profil passt (kein Port 9222, keine fremde Instanz). Dialoge: nur Hinweise («alert») werden bestätigt, Rückfragen («confirm», «prompt», «Seite verlassen?») immer abgelehnt. Edge schliesst nach 60 min ohne Nutzung (Einstellung `edge_leerlauf_min`, 0 = nie) und beim Beenden von AURA; bleibt Edge hängen, wird das im Log gemeldet. **Restrisiko:** die Debug-Schnittstelle hat keine Anmeldung – solange die AURA-Edge offen ist, kann jeder Prozess auf dem Gerät sie bedienen.
- **Was im Edge-Profil bleibt:** Cookies, Local Storage, IndexedDB und Einstellungen (für SSO nötig). Beim Beenden gelöscht: Caches, Sitzungsdaten, Verlauf der AURA-Edge. Schliessen ist **kein** Logout am Server. Das Profil liegt unter `data\` und wird von `tools\datenordner_absichern.py` mitgeschützt.
- **Diagnose** `tools\edge_test.py` nutzt ein eigenes Profil (`data\edge_profil_diagnose`) und Port 9333 und schreibt Seiteninhalte nach `tools\` – danach löschen.
- **Grenzen Live-Quellen:** Intranet 50 Treffer, 200 000 Zeichen je Seite, 200 Textstellen; SharePoint 40 Treffer, 2000 Zeichen je Feld; Acta-Nova-Export 50 MB, 20 000 Zeilen, 200 Spalten, keine DTD/Entities.
- Tests: `py -m unittest discover -s tests -v`.

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
