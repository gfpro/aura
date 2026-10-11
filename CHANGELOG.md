# Änderungen

Neueste Version zuerst. Versionsnummern entsprechen `VERSION` in `aura/__init__.py` (Format `JJJJMMTTvNN`); einzelne Dateien tragen ihre Version im Dateikopf. Frühere Zwischenstände ohne eigenen Eintrag sind in der jeweils nächsten Version zusammengefasst.

---

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
