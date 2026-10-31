# Änderungen

Neueste Version zuerst. Versionsnummern entsprechen `VERSION` in `aura/__init__.py` (Format `JJJJMMTTvNN`); einzelne Dateien tragen ihre Version im Dateikopf. Frühere Zwischenstände ohne eigenen Eintrag sind in der jeweils nächsten Version zusammengefasst.

---

## v145 – 31.10.2026 · Code prüfen: Bericht in AURA

- «Bericht öffnen» zeigt den Bericht in einem eigenen Fenster in AURA statt über die Windows-Dateizuordnung für `.md` (scheiterte bei App-V-Programmen); Knopf «Im Ordner zeigen».

## v144 – 31.10.2026 · Code prüfen: Sprachmodell nur als Zweite Meinung

- Tests mit Qwen3.5-4B und -9B: Modell-Befunde zu Code sind überwiegend falsch (9B: höchstens 1 von 8 geprüften «hoch»-Befunden zutreffend). Die Prüfung ohne Sprachmodell war in allen Läufen korrekt und bleibt die Hauptprüfung.
- Modellprüfung standardmässig aus; Schalter «Zweite Meinung (experimentell)» mit Warnhinweis (Einstellung `code_llm`).
- Modell-Befunde heissen «Modell (ungeprüft)», sind grau dargestellt, nie Stufe «hoch» und stehen im Bericht in einem eigenen Abschnitt am Ende.
- Weitere Widerlegungen: «wird nicht verwendet» (AURA zählt Vorkommen), «self.x nicht definiert/AttributeError» (Zuweisung gesucht); höchstens ein Befund je Zeile.

## v143 – 31.10.2026 · Code prüfen: weniger Rauschen

- Modell-Befunde werden deterministisch gefiltert: kein Lob («ist korrekt»), keine Kommentar-/Versions-/Rechtschreib-Kosmetik, keine Format-Echos, keine Dubletten, Zeile und Stufe sind Pflicht; höchstens 3 Befunde je Abschnitt.
- Behauptungen «undefiniert/NameError» werden gegen die Datei geprüft (Definitionen, Zuweisungen, Importe) und verworfen, wenn ein genannter Name existiert.
- Abschnitte aus überwiegend String-Daten (Shader, SQL, Prompts) oder nur Kommentaren gehen nicht ans Modell (schneller, kein Unsinn).
- Prompt mit Beispiel und klaren Ausschlüssen; Dateiliste mit höheren Zeilen (Unterstriche sichtbar).

## v142 – 31.10.2026 · Werkzeug «Code prüfen»

- Neu unter **Werkzeuge › Code prüfen**: Projektordner wählen (gespeichert als `code_folder`) und einlesen; Ausschlüsse wie `.git`, `venv`, `node_modules`, `vendor`, `models` sowie einfache `.gitignore`-Einträge; Dateien über 300 KB werden übersprungen.
- **Prüfung ohne Sprachmodell** (Sekunden): Syntaxfehler, mögliche Passwörter/Schlüssel im Klartext, `eval/exec`, `shell=True`, `except:` ohne Typ, verschluckte Fehler, veränderbare Standardwerte, lange Funktionen, viele Parameter, ungenutzte Importe, doppelte Codeblöcke, TODO/FIXME.
- **Prüfung mit Sprachmodell**: Abschnitt für Abschnitt (Python je Funktion/Klasse, sonst ~140-Zeilen-Fenster); Befunde mit Zeile, Stufe und Vorschlag; Bericht als Markdown unter `data\code\berichte`.
- **Vorschläge**: Doppelklick auf einen Befund → Auftrag anpassen → Diff. Übernehmen nur nach Klick, vorher Sicherung unter `data\code\sicherung\<zeit>\`. Python/JSON werden vor dem Schreiben auf Syntax geprüft; wurde die Datei inzwischen geändert, wird nicht geschrieben. «Sicherungen …» setzt einzelne Dateien zurück.
- Git wird nur lesend angezeigt (Zweig, offene Änderungen). Kein Push, kein Netzwerk.
- Neue Dateien `aura/code.py`, `aura/code_gui.py`; Jobs `code_scan`, `code_pruefen`, `code_vorschlag` in `worker.py`.

## v130–v141 – 29.–31.10.2026 · 4 Bit, Ausführlichkeit, sicherere Workflows

**Sprachmodell**
- **4-Bit-Gewichte** als Test-Funktion: Einstellung `"llm_bits"` (4, 8 oder 16) in `data\settings.json`; ohne Eintrag gilt wie bisher `llm_int8`. Umrechnung beim Laden auf der Grafikkarte, eigener Selbsttest, bei Fehlern Rückfall auf 8 Bit.
- Gemessen auf Intel-Grafik: 4 Bit spart Speicher, ist aber **nicht schneller** (kurze Textblöcke sogar langsamer). Standard bleibt **8 Bit**.
- Fehler beim Laden des 4-Bit-Modus stehen im Log (`DIAG int4_fehler`).

**Workflows**
- Regler **«Ausführlichkeit»** (knapp / normal / ausführlich) im Reiter «Ausführen», gespeichert je Workflow. Wirkt auf freie Antworten und auf Felder mit dem Häkchen «Länge folgt der Ausführlichkeit» – nie auf Auswahl- oder Zahlfelder.
- Neue **Schutz-Optionen für Felder**, damit das Sprachmodell nicht rät:
  - `min_sicherheit` / `unsicher_wert`: Ist das Modell bei einer Auswahl unsicher, setzt AURA einen Ersatzwert (z.B. «unklar») und schreibt einen Prüfhinweis.
  - `verneinung_pruefen`: Das Zitat und die folgenden Sätze werden ohne Modell auf Verneinungen geprüft («liegt nicht vor», «bietet … nicht an», «kommt nicht in Frage» …). Verneinte Werte werden verworfen.
  - Empfehlung: Zitat **nach** dem Wert (`beleg_nach`) – mit Zitat zuerst legt sich ein kleines Modell unzuverlässig fest.
- Grundsatz: **Das Sprachmodell erfasst nur Fakten, Entscheidungen trifft eine Regel.** Lieber «unklar» mit Hinweis als ein falscher Wert.

**Oberfläche**
- Neues, schärferes Programm-Icon (je Grösse eigens gezeichnet, 16–256 px).

## v119–v129 – 24.–29.10.2026 · Suche, Confluence, Chat-Verlauf

- Schieberegler **«Quellen»** (2–12): wie viele Quellen das Sprachmodell liest.
- Befehls- und Zeitwörter («nenne», «zeig», «letzte») verfälschen die Suche nicht mehr; Begriffe mit Bindestrich werden auch mit Leerzeichen gefunden.
- **Confluence:** mehrere Benachrichtigungsmails zur selben Seite zählen als eine Quelle; Hinweis unter der Antwort, wenn eine passende Seite kürzlich geändert wurde; Änderungen zwischen zwei Fassungen werden als eigenes Textstück gespeichert («Was wurde geändert?»).
- Quellenangabe in Klartext («Confluence-Seite, zuletzt geändert am …», «Termin am …»).
- 8 Bit ist Standard, der Schalter entfällt (bf16 nur noch zur Gegenprobe).
- **Chat-Verlauf** (v129): «＋ Neuer Chat», «🕘 Verlauf»; Chats werden 30 Tage gespeichert (`data\chats.db`). Senden-Knopf zeigt «⏳», solange Vektoren berechnet werden.

## v106–v118 – 16.–24.10.2026 · Tempo, Werkzeuge, Menü

- **Tempo** (v115–v118): Einlesen rund 2,5× schneller, kurze Blöcke zwischen JSON-Feldern rund 4× schneller, Aufmerksamkeit beim Schreiben knapp 2× schneller; AURA belegt rund 7 GB weniger Arbeitsspeicher.
- **Nur noch Qwen3.5** (v118): Qwen3 entfernt; Qwen3.5-9B lässt sich laden (bessere Antworten, langsamer).
- **Werkzeuge › Text anonymisieren** (v113): ersetzt Namen, AHV-Nummern, IBAN, Mailadressen, Telefonnummern, Koordinaten und eigene heikle Begriffe durch Platzhalter; geführte Begriffsliste (bleibt lokal).
- Seitenleiste mit Menügruppen (Chat, Wissen, Workflows, Werkzeuge, Einstellungen), «Log öffnen» (v109).
- Speicherverbrauch im Log (v106).

## v86–v105 – 14.–16.10.2026 · Qwen3.5, OneNote, bessere Antworten

- **Qwen3.5-4B** mit eigener Engine (v88/v89), 8 Bit und Denkblock aus.
- **OneNote** als Quelle (v87): Auswahl je Abschnitt, nur geänderte Seiten werden neu gelesen, Klick öffnet die Seite in OneNote.
- KV-Cache in 16 Bit (v85/v86): halber Speicher für langen Kontext.
- **Workflows:** Auswahlfelder werden «bewertet» statt geschrieben – das Modell darf nur erlaubte Werte wählen; Sicherheit je Feld im Log, unsichere Felder im Prüfbericht (v96).
- **Datei im Chat** (📎, v97–v99): gilt nur für den aktuellen Chat, wird nie in die Datenbank übernommen.
- **Vektorsuche auf der Grafikkarte** (v98): Suche 2,3 s → 0,1 s.
- Bessere Antworten (v101–v105): Personen und Quellen nur noch als Bonus statt harter Filter, kein Zusatzwissen, bester Treffer mit Nachbarstücken. Testwerkzeuge `tools\suche_test.py` und `tools\antwort_test.py` mit eigenen Testfragen.
- **Übersicht mit drei Bereichen** (v90): Eingabe – Wissen/Verarbeitung – Ergebnis; Schalter «Expertenansicht» für Schritte, Prüfliste, Vorlage.

## v65–v85 – 12.–14.10.2026 · 8 Bit, Widgets, Austausch

- **8-Bit-Gewichte** (v70): halber Grafikspeicher, schnelleres Schreiben; Umrechnung beim Laden, Selbsttest gegen bf16.
- Schweizer Rechtschreibung (ß → ss) in allen Antworten (v72).
- **Workflows exportieren/importieren** als `.aurawf.zip` inkl. Wissen und Vorlagen (v78).
- **Widgets** (v80–v82): Workflow-Ergebnisse auf der Startseite anheften; Ablaufband mit dem Ergebnis jedes Schritts.
- Info-Leiste rechts (Sprachmodell, Wissen, letzte Läufe, v68).

## v64 – 11.10.2026 · Feldplan und Regel-Editor

**Feldplan (v64a)**
- Neues Fenster «Feldplan …» im Reiter «Vorlage»: Für jedes Feld einer Word-Vorlage wird festgelegt, woher sein Wert kommt – *Fakt* (aus den Unterlagen), *Abgeleitet* (Regel), *Fest*, *Manuell*, *Leer* oder *Offen*.
- Erkennung ohne Sprachmodell: Abschnitte aus Überschriften (inkl. Anhänge ohne Überschriftenstil), Kästchen-Gruppen aus Abschnitten und Tabellen-Kopfzeilen, Begleitfelder (Textfeld neben einem Kästchen), Code-Muster, Personen-/Datums-/Begründungsfelder.
- Herkunft per Knopf ändern (mehrere Zeilen gleichzeitig); von Hand Geändertes bleibt beim «Neu analysieren» erhalten. Gespeichert als `vorlagen\<name>.feldplan.json`.
- Doppelklick (v64a2): Fundstelle und Hinweis für Fakten, fester Wert, Platzhaltertext.

**Bauen aus dem Feldplan (v64c)**
- «▶ Workflow aus Feldplan bauen»: Nur Fakten gehen ans Sprachmodell; eine Kästchen-Gruppe ist *eine* Auswahlfrage, die Kästchen setzt AURA danach selbst. Feste Werte und Platzhalter ohne Modell.
- Unterlagen stehen im gecachten Vorspann; das Wissen geht nicht mehr in den Faktenschritt.
- Budget-Prüfung beim Bauen: Passt ein Schritt nicht ins Kontextfenster, werden die Felder auf mehrere Schritte verteilt (statt Abbruch im Lauf).
- Messung an einer Vorlage mit 161 Feldern: 27 statt 161 Modellfelder, Laufzeit rund 3½ statt 10–25 Minuten.
- «Workflow beschreiben» erstellt bei Word-Vorlagen den Feldplan automatisch.
- Begleitfelder werden nur abgefragt, wenn ihr Kästchen gewählt ist (v64c2).

**Regeln (v64d, v64e)**
- Regel-Editor im Doppelklick-Fenster: «Wenn … dann …» mit bis zu drei Bedingungen (=, ≠, <, ≤, >, ≥, enthält), Reihenfolge, «Sonst».
- Bedingungen auf Fakten, feste Werte und andere Regeln (Verkettung); Zahlen wie «CHF 1.2 Mio» werden erkannt.
- Regeln laufen als Entscheidungstabelle ohne Sprachmodell; der Prüfbericht nennt die Regel, die gegriffen hat. «Grundlage (Wissen)» wird Pflichtstelle im Wissensschritt.
- Bei Gruppen darf eine Regel mehrere Kästchen ankreuzen (v64e).

**Korrekturen**
- Angekreuzte Kästchen setzen auch den inneren Zustand in Word, nicht nur das Zeichen ☒ (v64e).
- «keiner» gilt als leer; Platzhalter «[ergänzen]» in Begleitfeldern nur bei gewähltem Kästchen (v64f).

## v60 – 11.10.2026 · Ergebnisse, Zurücksetzen, Aufräumen

- Startseite «Letzte Ergebnisse» wird nach jedem Lauf und beim Zurück zum Chat aufgefrischt.
- Läufe lassen sich unter «Ergebnisse» löschen (Papierkorb `workflows\_geloescht\_laeufe`).
- «Quellen» → «Alles zurücksetzen …»: Datenbank, Synchronisationsstand und Quellenauswahl zurücksetzen, Auto-Abgleich aus; ausgeführt beim Neustart, bevor die Datenbank geöffnet wird.
- Hilfetexte verschwinden beim Minimieren oder beim Wechsel in ein anderes Programm und liegen nicht mehr über anderen Fenstern.
- Datenbank: WAL-Datei auf 64 MB begrenzt.
- `tools\ordner_pruefen.py`: Ordnerbericht (Grösse, Zweck, löschbar, GitHub ja/nein, bereits in Git erfasste Dateien) und Vorschlag für `.gitignore`.

## v55–v63 – 11.10.2026 · Workflow beschreiben, Ausgabe

- **Assistent «Workflow beschreiben»** ausgebaut: Namensfeld oben, Bausteine (Wann, Zeitraum, Woraus, Verarbeiten, Ergebnis, Form) per Klick oder Ziehen, «Lieber selbst zusammenstellen →»; «+ Neuer Workflow» öffnet direkt den Assistenten. Fehlt nichts, wird direkt gebaut, sonst erscheinen rote Rückfragen.
- Nur ein Ausgabeziel gewählt (Anzeige, Mail, Datei) = Zusammenfassung dorthin.
- Feld **Form** (v62): Stichpunkte, Text oder Tabelle; Tabellen werden nur bei «Tabelle» angehängt.
- Wörter innerhalb von Bausteinen werden nicht doppelt gelesen (v62).
- Zusammenfassungen (v63): höchstens 5 Stichpunkte; Zeitplan, Ausgabeziel und Form gehen nicht mehr in den Auftrag ans Modell; keine allgemeinen Ratschläge oder erfundenen Aufgaben.
- Termine und Mails: Kurzfassungen für das Modell (rund halb so viele Tokens), vollständige Listen hängt AURA selbst an; Mails ohne Abwesenheitsnotizen und Newsletter.
- Anzeige und Mail als gestaltetes HTML; Tabellen in den Ergebnis-Karten, Warnzeilen orange (v59).
- Ergebnis-Karte erklärt, wenn ein Lauf keinen Ausgabe-Schritt hat (v57); Startseite mit eingerahmtem Kasten «Letzte Ergebnisse» (v55).
- Mitgelieferte Beispiel-Workflows: «Termine 7 Tage», «Test Mails».

## v54 – 11.10.2026 · Ergebnisse und Zeitplan

- Ansicht **«Ergebnisse»**: «Als Nächstes» (Zeitplan-Läufe) und Karten der letzten Läufe aller Workflows mit Text, Prüfhinweisen, Öffnen, Kopieren, «Speichern unter …», Laufordner; Zähler «n neu» in der Seitenleiste.
- Ausgabeziele je Workflow: Anzeige in AURA (Standard), **Mail an mich** (Outlook, nur eigene Adresse, standardmässig Entwurf), Datei.
- Zeitplan-Läufe melden sich im Chat nur noch mit einem kurzen Hinweis.
- Termin-Zusammenfassung schneller: Modell schreibt nur Stichpunkte, Überschneidungen berechnet AURA.
- `Pruefbericht.txt` nur noch, wenn es etwas zu berichten gibt.

## v49–v53 – 11.10.2026 · Editor, Prüfliste, Zeitplan

- **Reiter «Schritte»** (v52): Workflow ohne JSON bearbeiten – Karten, Formular je Baustein, «Wert einfügen», «Speichern & diesen Schritt testen».
- **Reiter «Prüfliste»** (v50–v53): Prüfpunkte als allgemeine Regeln (enthält, enthält nicht, Muster in Abschnitt, Reihenfolge, Länge, Gliederung wie Vorlage) oder als Fragen ans Modell (ja/nein/unklar mit Beleg); Feld «Herkunft»; fertige Prüfpakete als JSON in `pruefpakete\`.
- Grundsatz: **kein Fachinhalt im Code** – der Code enthält nur allgemeine Bausteine; was geprüft oder erstellt wird, steht in Beschreibung, Prüfliste und Paketen.
- **Zeitplan** (v53): werktags, täglich oder an bestimmten Tagen zu einer Uhrzeit; läuft, solange AURA offen ist; Verpasstes vom selben Tag wird nachgeholt.
- Neue Bausteine: Termine holen, Mails holen, Für jedes …, Meldung in AURA.
- Erste Fassung von «Workflow beschreiben» (v53).
- Auto-Abgleich pausiert, solange ein Workflow läuft oder wartet (v49).
- Feldoption `beleg_nach`: Zitat nach dem Wert, bei neutralem Wert ohne Modell (v49).
- `tools\patch_einspielen.py` neu: Sicherung nach `_sicherung\vor_<patch>\`, Kontrolle je Datei, Entfernen von Dateien über `_entfernen.txt`.

## v45 – 11.10.2026

- Baustein `word_vorlage`: Option `platzhalter` – meldet nach dem Ausfüllen verbliebene Platzhaltertexte im Prüfbericht.

## v44 – 10.10.2026 · Diagnose und schnellere Engine

- **Diagnose:** `logs\aura.log` mit DIAG-Zeilen zu Kernel-Wahl, Vorspann-Cache, Einlesen/Schreiben, Zeit je Feld und je Schritt; `tools\prof_test.py` misst Selbsttests und Zeitanteile.
- **Attention beim Einlesen als Matrixmultiplikation** (v44c): Einlesen langer Texte rund 3× schneller (12 Minuten → rund 8 Minuten für einen grossen Workflow).
- Matrix-Kernel für kleine Blöcke (v44d) – schnelleres Weiterschalten zwischen JSON-Feldern.
- Feldoption **`vorschlag`**: Text nur in den Prüfbericht («Formulierungsvorschläge, nicht geprüft»), nie ins Dokument.
- Auswahlfelder mit «wann» enden, sobald ein erlaubter Wert steht (v44a2).
- Alle GPU-Neuerungen mit Selbsttest «gleich und schneller», sonst Rückfall auf die bisherige Variante.

## v38–v43 – 09./10.10.2026 · Belege, Prüfbericht, Cache

- **Infotexte** (Tooltips) für alle Knöpfe und Felder, zentral in `aura/hilfe.py` (v38).
- Ausdruck `belegt()` für Zitatprüfung (v39).
- Feldoptionen (v40): `auswahl` mit Abgrenzung («wann»), `verlaengern` (bis Satzende), `beleg`/`neutral`/`ohne_beleg`, `wenn_leer`, `label`; Plausibilitätsprüfungen `pruefungen` im Workflow; Auswahlwerte der Vorlage per Wortvergleich.
- **Prüfbericht** (v41): Hinweise des Werkzeugs gehen nie ins Dokument, sondern in `Pruefbericht.txt`; `leer_werte`.
- Standby-Schutz während eines Laufs; Split-K-Attention beim Schreiben (v42).
- **Prompt-Cache** (v43): bereits gelesener Text wird nicht erneut eingelesen; fester Vorspann wird auf der Festplatte gespeichert (`data\kvcache`) – gleicher Lauf ein zweites Mal rund 3× schneller. `rag` liefert Pflichtstellen und Suchtreffer getrennt.
- `AURA.pyw` fängt Abstürze ab (`logs\crash.log`); Logs nach `logs\`.

## v28–v37 – 08./09.10.2026 · Workflow-Engine und Wissen

- **Workflow-Engine** mit Bausteinen `extract`, `rag`, `llm` (erzwungenes JSON: AURA schreibt das Gerüst, das Modell nur die Werte), `set`, `regel` (Entscheidungstabelle), `word_vorlage`, `template`, `file_out`; Ausdrücke `{{ … }}` ohne `eval`.
- **Word-Vorlagen ausfüllen:** Inhaltssteuerelemente (Text, Datum, Auswahlliste, Kombinationsfeld, Kontrollkästchen) und alte Formularfelder; Formatierung bleibt erhalten.
- Zwischenstand nach jedem Schritt, «Ab Schritt neu», Prüfung vor dem Start.
- **Wissenssammlungen** (v28): eigene Datenbank `data\wissen.db`; Erlasse werden nach Artikeln zerlegt und zitierbar; Pflichtstellen (`pin`); Warnung bei veraltetem Stand; Verwaltung in der Oberfläche; Schalter «Wissen im Chat».
- **Workflow-Pakete** (v36): Ordner mit `workflow.json`, eigenem Wissen, Vorlagen und Läufen; Fenster «Workflows» mit Reitern Ausführen, Wissen, Vorlage.
- Dokumentordner mit «✕» abwählbar, inkl. Entfernen aus AURA (v37).
- Kommandozeile `tools\wf_run.py` (Workflows, Wissen, Vorlagenfelder).

## v23–v24 – 08.10.2026 · Ordnerauswahl, Auto-Abgleich, DirectML

- **Outlook-Ordnerauswahl** als Baum mit Häkchen; verschwundene Mails werden aus AURA entfernt, mit Rückfrage bei grösseren Mengen (v23).
- **Auto-Abgleich** alle 15 Minuten; bettet nur Neues ein und weicht Fragen sofort aus (v23).
- Embedding über **DirectML** (v24): rund 8× schneller (0,13 statt 1,1 s je Textstück), bestehende Vektoren bleiben gültig.

## v13 – 06.10.2026 · Grundlage

- Lokales «zweites Gehirn»: Outlook-Mails, Outlook-Kalender, Edge-Verlauf, Dokumentordner in einer SQLite-Datenbank mit Volltextsuche.
- Hybride Suche (Wörter + Bedeutung) mit Filtern für Person, Zeitraum, Termine und Fristen.
- Embedding (multilingual-e5-large) und Sprachmodell (Qwen3) **nativ auf der Grafikkarte** über eigene Kernels – ohne PyTorch, ohne Installation; Kernel-Selbsttest beim Laden.
- Oberfläche mit Chat, Quellenangaben und Zeitaufteilung je Antwort; ein Hintergrund-Thread für GPU und Outlook.
