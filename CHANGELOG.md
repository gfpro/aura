# Änderungen

Neueste Version zuerst. Versionsnummern entsprechen `VERSION` in `aura/__init__.py` (Format `JJJJMMTTvNN`); einzelne Dateien tragen ihre Version im Dateikopf. Frühere Zwischenstände ohne eigenen Eintrag sind in der jeweils nächsten Version zusammengefasst.

---

## v226–v228 – 12.11.2026 · Ganzes Dokument statt Ausschnitte, Acta Nova in der Zusammenfassung

**Aufträge zu angehängten Dokumenten (neu)**
- Aufträge wie «Fasse zusammen», «Überblick», «Optimierungen», «Empfehlungen», «Risiken», «nächste Schritte» oder «bewerten» lesen bei einem Anhang das **ganze Dokument** statt nur der passendsten Textstücke (vorher sah das Modell 4 Ausschnitte).
- **Durchgang 1:** Das Dokument wird an Kapitelüberschriften geteilt (höchstens 12 Abschnitte à ~3500 Zeichen), jeder Abschnitt wird zu Kernaussagen verdichtet. Läuft **im Hintergrund direkt nach dem Anhängen**, sofern ein Sprachmodell geladen ist; eine Frage unterbricht und liest ab dem erreichten Abschnitt weiter. Ergebnis bleibt je Anhang im Chat gespeichert (Folgeaufträge ohne erneutes Lesen).
- **Zusammenfassung ohne Sprachmodell:** je Abschnitt Titel mit [n] und bis zu 7 Kernaussagen – kein Abschnitt fällt mehr weg.
- **Optimierungen in festen Feldern** (`llmio.structured`): je Massnahme Bereich, Problem mit [n], Massnahme, Herkunft. Herkunft ist eine Auswahl «Dokument» / «Vorschlag» (keine leere Spalte mehr). Leere und doppelte Massnahmen werden verworfen. Nächste Schritte und Fazit im selben Modelllauf.
- Quellen [n] = Kapitel des Dokuments (Kapiteltitel zuerst); «Kontext» zeigt die Kernaussagen.
- Gemessen am «Abschlussbericht Zentralisierung Postein- und Postausgang» (Qwen3.5-9B): 126 s statt 363 s (v226), alle Kapitel abgedeckt.
- Einstellungen: `dok_ganz`, `dok_vorlesen`, `dok_block` (3500), `dok_max_abschnitte` (12), `dok_map_tokens` (260), `dok_optimierungen` (5).

**Live-Quellen**
- Zusammenfassung über alle Quellen sieht jetzt auch **Acta Nova**: Ablageorte gehen als Metadaten-Text (Rang, Aktenzeichen, Ordnungssystem, Dokumenttitel) und der «Ablagevorschlag gemäss Ordnungssystem» mit. Vorher fielen sie mangels Text weg; die Zusammenfassung meldete «nicht angegeben», obwohl die Liste darüber die Ablageorte zeigte. Hinweis ans Modell: Acta-Nova-Quellen sind Ablageorte, keine Inhalte.

**Oberfläche**
- Anhang-Zeile («📎 … nur in diesem Chat») in eigener Zeile, «▶ Als Präsentation» zuerst – bei schmalem Fenster nicht mehr abgeschnitten.
- Kein Flackern mehr beim Schreiben: Antwortblöcke wachsen während des Streamens nur noch und werden am Ende einmal eingepasst (vorher Wachsen/Schrumpfen Zeile für Zeile, zweimal pro Sekunde).

**Geänderte Dateien**
- `aura\gui.py` (v227), `aura\worker.py` (v228), `aura\engine\actanova_rang.py`, `aura\__init__.py` (Version `20261112v228`).

**Bekannte Grenzen**
- Optimierungen geben oft die Lösung des Dokuments wieder («Dokument») statt Lücken zu benennen; geplant: mindestens zwei «Vorschläge» mit Bezug zu Einwänden im Dokument.
- Schreiben mit 2,6 Tokens/s (Qwen3.5-9B) bzw. 1,8–2,1 (Apertus) – lange Aufträge brauchen 1–3 Minuten.
- Agent (Pilot) bleibt unverändert; Überarbeitung folgt.

## 20261111v225
- Teams-Testbaustein zurückgebaut (engine/teams.py entfernt, Freigabe teams.cloud.microsoft/teams.microsoft.com gestrichen): Edge trennt die Fernsteuerung, sobald Teams lädt (Richtlinie) – Thema beendet.

## 20261111v224
- Test: Teams Web als Live-Quelle (engine/teams.py), nur lesend, noch nicht im Chat; Freigabe teams.microsoft.com (Quelle «teams»); Protokoll und Diagnose in logs/teams.log.

## 20261111v223
- Acta Nova: hängt «Client wird gestartet», lädt AURA die Startseite frisch (neues Sitzungs-Token) statt die Init-Seite mit dem alten Token neu zu laden; Diagnose der Init-Seite (Text, angefragte Hosts, Sichtbarkeit) in logs/actanova.log.

## 20261111v222
- Acta Nova: Sperre wartet höchstens 30 s (bisher unbegrenzt – mögliche Ursache für Hänger ohne Fehlermeldung); Wegmarken jedes Schritts in logs/actanova.log, um Hänger zu lokalisieren.

## 20261111v221
- Agent: Kalender und Mail-Suche zum Termintitel macht der Code fest (Engine); das Modell ergänzt nur noch (max. 3 Schritte), allgemeine Suchwörter wie «nächster Termin» werden vermieden. Notiz bis 700 Tokens (bisher bei 250 abgeschnitten).
- Zusammenfassung über alle Quellen bis 700 Tokens; Antwortblöcke prüfen ihre Höhe nach dem Layout ein zweites Mal.
- Acta Nova: Fehler im Chat-Ablauf werden in logs/actanova.log protokolliert; der ganze Ablauf (Verbinden + Suchen) wird einmal wiederholt.

## 20261111v220
- Chat: Höhe der Antwortblöcke wird nachgeführt, wenn während der Anpassung Text dazukommt (abgeschnittene letzte Zeilen der Zusammenfassung).
- Zusammenfassung über alle Quellen und Agent-Notiz laufen mindestens auf «Normal», auch wenn «Kurz» gewählt ist (bisher max. zwei Sätze).
- Acta Nova: bleibt die Trefferseite aus, wird die Startseite neu geladen und die Suche einmal wiederholt (Protokoll in logs/actanova.log).

## 20261111v219
- Agent: Schlussnotiz mit konkretem Ziel (erster gefundener Termin + Mails als Hintergrund) statt «bereite vor» – behebt «Dazu habe ich nichts gefunden» trotz Treffern; Zieltermin wird angezeigt.
- Agent-Schalter: Symbol «Schritte» (Stufen) mit Beschriftung, grün = ein.

## 20261111v218
- Agent: Kalender ignoriert generische Begriffe («nächster Termin») und liefert dann die nächsten Termine; dem Modell werden nur verfügbare Werkzeuge angeboten (Acta Nova nur, wenn eingeschaltet); Termintitel und Teilnehmende fliessen in den nächsten Schritt; Anzeigefehler KeyError 'search' behoben.
- Oberfläche: Agent-Schalter als Symbol 🤖 (grüner Rahmen = ein); Tag/Nacht als Symbol ☀/☾ oben neben «Neuer Chat».

## 20261111v217
- Pilot Agent: neuer Schalter «Agent» im Chat. Das Sprachmodell wählt pro Schritt Werkzeug + Suchbegriff (Kalender, Mail, Acta Nova falls ein), der Code führt nur lesend aus; max. 5 Schritte, Wiederholungen werden abgelehnt, jeder Schritt sichtbar. Danach Vorbereitungsnotiz mit Quellen. Protokoll je Lauf in logs/agent_protokoll.jsonl (Modellvergleich).

## v213–v216 – 09.–10.11.2026 · Quellen öffnen, Anzeige, Acta-Nova-Start, mehrere Intranets

**Live-Quellen**
- SharePoint: Klick auf eine Quelle öffnet das Dokument im angemeldeten AURA-Edge. Pfade mit Leerzeichen/Umlauten werden vor der Herkunftsprüfung kodiert (vorher still abgelehnt); Standardbrowser nur als Rückfall.
- Abgelehnte Adressen nennen den Host und werden kopiert; Acta-Nova-Aktenzeichen wird beim Klick sofort kopiert, Meldung statt stillem Abbruch, solange AURA arbeitet.
- Acta Nova: genau ein Tab (Start-Tab abwarten, Doppel schliessen). Startseite wird vor der Suche nur noch neu geladen, wenn sie nicht bereit ist – der Neustart des Clients blieb jedes zweite Mal bei «Client wird gestartet» hängen. Hänger: Fenster sichtbar machen, nach 30 s neu laden, sonst klare Meldung (`init …` in `acta_nova.log`).
- Acta Nova ist bei jedem Start aus; Einschalten öffnet Edge zur Anmeldung mit Karte/PIN.
- Intranet: mehrere Adressen (eine pro Zeile), alle werden durchsucht und gemeinsam gewichtet; Herkunft je Treffer in Klammern. Freigabe für das Intranet: jeder https-Host unter `*.admin.ch` (Port 443); mit Richtlinie `LiveOrigins_intranet` gilt nur diese. Acta Nova und SharePoint bleiben auf feste Adressen beschränkt.

**Antworten**
- Text markier- und kopierbar (Ctrl+C, Ctrl+A).
- Je Quelle ein farbiger Block (Lokal, Intranet, Acta Nova, SharePoint, Confluence) und eigener Block «Zusammenfassung über alle Quellen»; folgt Hell/Dunkel.
- Aufzählungen («- ») und einfache Tabellen («A | B») erlaubt und ausgerichtet dargestellt; Schrift in Pixeln wie die übrige Oberfläche.
- Höhe der Antwort passt sich der tatsächlichen Breite an (kein Abschneiden, keine Lücke, kein Flackern).
- Begriffe in Anführungszeichen ("…", «…», „…“) müssen wörtlich vorkommen; sonst «Den genauen Begriff … finde ich nicht.» ohne Modelllauf. Gilt für die lokale Suche, noch nicht für Live-Quellen und den Listenmodus.

**Geänderte Dateien**
- `aura\gui.py`, `aura\worker.py`, `aura\llm\native.py`, `aura\engine\actanova.py`, `aura\engine\intranet.py`, `aura\engine\herkunft.py`, `aura\__init__.py` (Version `20261110v216`).

**Bekannte Grenzen**
- Acta Nova: «Ablageort öffnen» findet Subdossiers über das Feld «Aktenzeichen» teils nicht.
- Tippfehler in Anführungszeichen werden nicht korrigiert (Vorschlag «Meintest du …?» offen).

## v212 – 08.11.2026 · Sicherheits-Review v21 (V20-01 bis V21-05)

- Übernommen aus v208 (dort für v20 erstellt): Update-Prüfung mit Signatur und Rollback, Confluence-Host-Allowlist + DPAPI-Token, Workflow-Lese-Freigaben, Manifest-Prüfung mit transaktionalem Import, ZIP-/Dokumentgrenzen, Prompt-Abgrenzung, Skill-Rechte (SHA-256).
- Edge/CDP: Port durch Edge gewählt, Bindung an die Browser-ID im AURA-Profil, kein Fallback 9222, WebSocket nur zu 127.0.0.1:<Port>, Leerlauf-Abschaltung, Beenden mit Kontrolle und Meldung.
- Dialoge: nur «alert» bestätigen, «confirm»/«prompt»/«beforeunload» ablehnen (auch bei Timeout).
- Live-Quellen: zentrale Origin-Allowlist `aura\engine\herkunft.py` (Richtlinie `LiveOrigins_*`) für eingetragene URLs, Suchtreffer, Tabs, Navigation und vor dem Auslesen; GUI nutzt dieselbe Prüfung.
- Grenzen: Intranet-Seiten/Treffer/Textstellen, SharePoint-Treffer, Acta-Nova-XLSX (Grösse, Zeilen, Spalten, Strings, keine DTD).
- Edge-Profil: Verlauf/Sitzungsdaten werden beim Beenden gelöscht; Cookies/Local Storage bleiben bewusst (SSO).
- Diagnose `tools\edge_test.py` mit eigenem Profil/Port. Versionen in `aura\__init__.py`, README und CHANGELOG angeglichen.
- Neu: `aura\engine\herkunft.py`, `tests\test_live.py`.

## v211 – 06.–08.11.2026 · Live-Quellen: Acta Nova, Intranet, SharePoint

**Live-Quellen (neu)**
- Drei Quellen, die **bei der Frage** durchsucht werden – nichts wird gespeichert. Ein/aus über die Schalter **Acta Nova**, **Intranet**, **SharePoint** im Chat (grüner Punkt = ein). Einrichten unter **Wissen → Quellen → Live-Quellen**.
- Eigenes Edge-Fenster von AURA (Profil `data\edge_profil`): Anmeldung mit Karte/PIN bzw. Windows-Konto durch den Menschen, AURA arbeitet danach minimiert im Hintergrund. Nur lesen – AURA speichert, ändert oder erstellt nichts in den Systemen.
- **Antwortaufbau:** zuerst «Lokal», dann je Live-Quelle eine Trefferliste (sofort lesbar), am Schluss **eine** Zusammenfassung über alle Quellen. Belege der Zusammenfassung stehen vorne in der Quellenliste, die übrigen Treffer neueste zuerst. Dauer mit allen Quellen rund 150 statt 380 s; das Sprachmodell bleibt geladen.

**Acta Nova**
- Suche in Dossiertiteln und im Volltext, alle Treffer über den Excel-Export (Datei wird sofort gelöscht); «Geschäftsobjektstatus» wird geleert, damit auch Abgeschlossenes gefunden wird.
- Ranking per Regel: Begriff im Namen/Dossier, Nähe zum **Ordnungssystem**, Ablageort in beiden Suchen, Aktualität, eigenes Team, Mail-Kontakte. Ergebnis: Top 5 Ablageorte mit Aktenzeichen und Ordnungsposition; bei «neuste …» zuerst die neuesten Dokumente.
- Vorschlag «Ablage gemäss Ordnungssystem»; Eingrenzen mit «nur 044» ohne neue Suche; Klick auf eine Quelle öffnet das Dossier.
- Ordnungssystem als Excel-Export aus Acta Nova einlesen, ansehen, entfernen (`wissen\ordnungssystem.csv`); funktioniert für jedes Amt.
- Stabilität: jede Suche startet auf der Startseite (keine volle Brotkrümelleiste mehr), abgelaufene Sitzung wird in höchstens 15 s erkannt; optional «Sitzung offen halten».

**Intranet**
- Adresse unter Wissen (alle VBS-Intranets mit gleicher Suche). Treffer werden nach Bedeutung neu gewichtet, die vier besten Seiten parallel gelesen.

**SharePoint**
- Suche über alle Sites mit Berechtigung (Antwort in unter einer Sekunde); eingetragene Sites werden bevorzugt. Jeder Treffer mit **Amt und Site**, Liste nach Amt gruppiert.

**Oberfläche**
- Wissen › Quellen: neuer Abschnitt «Live-Quellen» mit «Einrichten» je Quelle.
- Sendetaste aus dem Logo (Dreieck, gedreht); während der Antwort Stopp-Taste.
- Grüne Punkte für aktive Quellen (Schalter und rechte Leiste).
- «Entwickelt von armasuisse» mit Menü (Entwickler, Amt, R+S IT).
- Die Ansicht springt beim Schreiben nicht mehr nach unten, wenn man hochgescrollt hat.
- «Max. Quellen» gilt auch für Listen ohne Sprachmodell.
- Satz bei fehlenden Treffern je Quelle («Dazu finde ich in den lokalen Quellen nichts.» usw.).

**Sicherheit**
- Debug-Port des AURA-Edge: zufälliger Port je Start, nur lokal, Edge wird beim Beenden von AURA geschlossen. Restrisiko: Während AURA läuft, kann ein anderes Programm desselben Kontos die angemeldeten Sitzungen über den Port nutzen.
- Seiten-Cache des AURA-Edge auf 50 MB begrenzt und beim Beenden gelöscht (keine Kopien von Acta-Nova- oder SharePoint-Seiten auf der Festplatte).

**Neue Dateien und Einstellungen**
- `aura/engine/edge.py`, `actanova.py`, `actanova_rang.py`, `ordnungssystem.py`, `intranet.py`, `sharepoint.py`; Testskripte `tools\edge_test.py`, `edge_test2.py`, `actanova_suche.py`, `intranet_test.py`, `sharepoint_test.py`.
- `data\settings.json`: `actanova`, `actanova_url`, `actanova_llm`, `actanova_wach`, `intranet`, `intranet_url`, `sharepoint`, `sharepoint_sites`, `live_mit_lokal`, `edge_beim_beenden_schliessen`.
- Ordner `data\edge_profil` (Edge-Profil von AURA) und `wissen\ordnungssystem.csv` gehören nicht ins GitHub-Repository.

**Bekannte Grenzen**
- Acta Nova: Nach einer Pause läuft die Sitzung ab, dann ist die PIN nötig. Rund 40–80 s je Suche (Acta Nova selbst braucht 2–9 s je Seitenwechsel).
- Die Zusammenfassung stützt sich bei Acta Nova nur auf Titel, nicht auf Inhalte.

## v207 – 05.11.2026 · Edge und Confluence verbinden

- Edge-Besuche werden über Seiten-ID oder Titel mit der Confluence-Seite verbunden.
- Trefferliste in «Zusammenhänge»: Edge zuletzt, gleiche Titel nur einmal.

## v206 – 05.11.2026 · Confluence und Dokumente

- Confluence speichert Erstellt von/am, Dokumente Autor, Dateityp und Erstellt am.
- Graph: Verbindung «erstellte» für Confluence und Dokumente.
- `tools\\metadaten_nachtrag.py` ergänzt auch bestehende Confluence-Seiten und Dokumente, ohne Texte oder Vektoren zu ändern.

## v205 – 05.11.2026 · Abfolgefragen ohne Sprachmodell

- Abfolgefragen werden direkt aus dem Graphen beantwortet: Mail, Termine, Zeit, Titel und Teilnehmende. Das verhindert verfälschte Daten.
- Inhaltsfragen laufen weiter über das Sprachmodell.

## v204 – 05.11.2026 · Feinschliff Zusammenhänge und Glossar

- Beschriftungen werden nach gemessener Breite gekürzt.
- «Mail von BRF» findet die Person über das Glossar.
- Einträge vom Typ Abkürzung erweitern die Suche nicht mehr, sie gehen nur als Hinweis ans Sprachmodell.
- Der Graph erkennt nun auch reine Metadaten-Änderungen als veraltet.

## v203 – 05.11.2026 · To, CC und Adressen

- Mail- und Kalender-Konnektor speichern To/CC bzw. Pflicht/optional mit Adresse in `meta`.
- Neu `tools\\metadaten_nachtrag.py` ergänzt bestehende Objekte ohne neue Texte oder Vektoren.
- Graph: neue Verbindungen «empfing in CC» und «optional eingeladen»; gleiche Adresse führt Namensvarianten zusammen.

## v202 – 05.11.2026 · Graph: nur ein Aufbau gleichzeitig

- Behebt «table knoten already exists», wenn zwei Aufbauten gleichzeitig liefen oder eine alte Zwischendatei lag.

## v201 – 05.11.2026 · Graph: Confluence und Absenderadresse

- Confluence-Seiten sind über «Geändert von» mit Personen verbunden.
- Gleiche Absenderadresse führt Namensvarianten zusammen.
- Neu `tools\\empfaenger_test.py`: misst To, CC und Empfängeradressen ohne Namen auszugeben.

## v200 – 05.11.2026 · Glossar im Titel, Graph immer aktuell

- Inhaltsfragen mit Monat: Objekte mit dem Glossarbegriff im Titel stehen zuerst, höchstens vier.
- Der Graph wird nach dem Auto-Abgleich und vor Abfolgefragen neu aufgebaut, wenn er nicht mehr zur Datenbank passt.

## v199 – 05.11.2026 · Inhaltsfragen ohne Termine

- Inhaltsfragen mit Monat durchsuchen keine Termine mehr: Lange Teams-Einladungen zählten bisher als Text und verdrängten Notizen.

## v198 – 05.11.2026 · Glossar

- Neu unter **Wissen › Glossar**: Excel oder CSV mit Begriff, Bedeutung, Typ hochladen. Ein Upload ersetzt alles; Speicherort `data\\glossar.json`.
- Begriffe erweitern die Suche, das Sprachmodell erhält nur passende Einträge, mehrdeutige werden so bezeichnet.
- Einträge vom Typ Person führen Namensvarianten im Graphen zusammen.

## v197 – 05.11.2026 · Inhaltsfragen: Monat und Text

- Inhaltsfragen mit Monat («Juni 2026», «im Juni») suchen nur in diesem Monat und nur in Quellen mit Text.
- Bei Inhaltsfragen geben reine Termine und Edge-Einträge keinen Personen-Bonus mehr.

## v196 – 04.11.2026 · OneNote: Datum aus dem Titel

- Beginnt ein Seitentitel mit einem Datum, gilt dieses statt des Änderungsdatums. Bestehende Seiten werden einmalig angepasst.
- Zusammenhänge: Beschriftungen passen in ihre Kästen.

## v195 – 04.11.2026 · Zusammenhänge: Personen zusammenführen

- Namensvarianten derselben Person werden zu einem Knoten, wenn die Zuordnung eindeutig ist.
- Vergangene Objekte kommen vor Terminen in der Zukunft.
- Anordnung als Ellipse, passt sich dem Fenster an.

## v194 – 04.11.2026 · Zusammenhänge im Chat als Standard

- Der Schalter ist neu standardmässig ein und heisst «Zusammenhänge im Chat».
- Antworten nennen die Zeitfolge und behaupten keinen inhaltlichen Bezug ohne Beleg.

## v193 – 04.11.2026 · Zusammenhänge: Namen, mehrere Termine, kein Folgetermin

- Namen mit Teilen wie `da`, `de`, `van` werden erkannt; Personen passen nur noch als ganze Wörter.
- Mehrere Folgetermine am selben Tag: Das Sprachmodell soll alle nennen.
- Ohne Folgetermin antwortet AURA ohne Sprachmodell. Ohne Datum gilt nur die neueste Mail.
- Schalter «Zusammenhänge im Chat» steht oberhalb von «Skills & Rollen».

## v192 – 04.11.2026 · Zusammenhänge: mehrere Folgetermine

- Abfolgefragen liefern alle Termine des nächsten Tages, höchstens drei, statt nur den ersten.

## v191 – 04.11.2026 · Zusammenhänge: Datum und leere Datei

- Nennt eine Abfolgefrage ein Datum (TT.MM.JJJJ), gilt nur die Mail von diesem Tag.
- Lesen legt keine leere `graph.db` mehr an.

## v190 – 04.11.2026 · Zusammenhänge im Chat (Versuch)

- Neuer Schalter unter Einstellungen, standardmässig aus: Abfolgefragen mit Person ergänzen Mail und folgenden Termin aus dem Graphen. Alle anderen Fragen bleiben unverändert.
- `tools\zusammenhang_test.py` misst neu den Weg `chat+graph` und meldet, welche Fragen aus `eval\fragen.txt` die Regel auslösen würden.

## v189 – 04.11.2026 · Zusammenhänge (Metadaten-Graph)

- Neu unter **Wissen › Zusammenhänge**: zeigt rund um eine Person, Mail, einen Termin oder eine Seite die Verbindungen; Filter nach Zeitraum, Quelle und Tiefe.
- Knopf **Zusammenhänge** unter Chat-Antworten startet beim ersten Treffer.
- `data\graph.db` entsteht ohne Sprachmodell aus Metadaten und wird bei geänderter Datenbank neu aufgebaut. Suche und Antworten bleiben unverändert.
- Klick = Details, Doppelklick = neu zentrieren, Mausrad = Zoom, rechte Maustaste halten = verschieben.
- Bekannte Grenze: «ähnlicher Titel, zeitlich nah» (gestrichelt) ist nur ein Hinweis, kein Beleg.
- `tools\zusammenhang_test.py` versteht auch Quellen wie `OneNote: [Seite]`.

## v185–v188 – 04.11.2026 · Chat: offene Fragen, Seitenleiste

**Antworten**
- «Fasse … zusammen» (getrennt geschrieben) gilt als Inhaltsfrage und geht nicht mehr in den Listenmodus (vorher «0 Mails mit «Fasse» «zusammen»»).
- Ursache für «Dazu steht in den Quellen nichts», obwohl die Quellen das Thema enthalten: Die Belegpflicht aus v171 kennt nur eine einzelne «gefragte Angabe».
- Offene Fragen («Welche Informationen …», «Was weisst du …», «Fasse … zusammen», «Überblick») erhalten eine eigene Belegregel: wiedergeben, was die Quellen zum Thema sagen, auch Teilinformationen, mit Quellennummer; direkt mit dem Inhalt beginnen und nicht aufzählen, was fehlt. Absage nur, wenn keine Quelle das Thema erwähnt.
- Konkrete Fragen behalten die strenge Regel von v171.
- Bekannte Grenze: Je Mail geht nur ein Textstück ans Modell, auch nicht alle angezeigten Quellen. Zusammenfassungen «aller Mails» sehen daher nur einen Ausschnitt.

**Oberfläche**
- Skills & Rollen liegt neu unter **Einstellungen**, direkt nach «Beim Start Widgets zeigen».
- Die geöffnete Menügruppe steht in einem eigenen farbigen Rechteck, wie der Kasten «Aufgaben».

## v183–v184 – 04.11.2026 · Eingabefeld und Knöpfe

- Senden und Mikrofon als kleinere Knöpfe (34 statt 46 Pixel) mit Symbolen aus der Windows-Schrift Segoe MDL2; Mikrofon dezent links vom Senden-Knopf.
- Eingabefeld niedriger (52 statt 84 Pixel).

## v182 – 04.11.2026 · Spracheingabe im Chat

- Mikrofonknopf im Chat: klicken, sprechen, nochmals klicken (höchstens 30 s). Der Text erscheint im Eingabefeld und wird nie automatisch gesendet.
- Während einer Antwort ist der Knopf gesperrt. Whisper wird beim ersten Diktat geladen und bleibt geladen; die Aufnahme wird nach der Auswertung gelöscht.
- Modell: `models\whisper-small`, sonst `models\whisper-base`.
- Testeintrag unter Werkzeuge entfernt, `aura/stt_gui.py` entfällt. Diagnose-Pausen beim Laden nur noch mit Umgebungsvariable `AURA_DIAG`.
- Neue Datei `aura/mikrofon.py`.

## v175–v181 – 04.11.2026 · Whisper auf der Grafikkarte

- Neue Engine `aura/engine/whisper_dml.py`: Whisper über DirectML in FP16, ohne Zusatzpakete. Faltungen als versetzte Matrixmultiplikationen, Decoder mit K/V-Cache (höchstens 224 Tokens je 30 s).
- Neu `aura/engine/mel.py`: WAV lesen und Log-Mel-Spektrogramm in reinem Python. Aufnahme über Windows-MCI (winmm).
- Rechenweg gegen Hugging Face geprüft (Encoder, Decoder, Mel) an einem kleinen Zufallsmodell.
- Treiber-Absturz `0x887A0005` beim Vorbereiten behoben: `gemm` mit krummer Zeilenzahl der Wort-Matrix stürzte ab. Die Matrix wird in Stücken von 4096 Zeilen gerechnet und mit Nullzeilen aufgefüllt; Decoder ohne Metacommands; Encoder in Teil-Listen.
- Neu `tools\whisper_test.py`: Messung ohne Oberfläche, mit Mikrofon oder WAV-Datei.
- Gemessen mit Whisper base: 10 s Audio in 1,4 s (Mel 1,0 s, Encoder 0,14 s). Hochdeutsch brauchbar, Berndeutsch mit base nicht.

## v174 – 03.11.2026 · Apertus: längerer Kontext

- Kontext für Apertus von 8'192 auf 13'312 Tokens erhöht, damit lange Workflows laufen. Anpassbar mit `llm_context_apertus` in `data\settings.json`.

## v173 – 03.11.2026 · Workflows: Rückgängig und Versionen

- Im Reiter «Bauen»: Knopf «↶ Rückgängig» und Ctrl+Z (mehrfach), Knopf «Versionen …» mit früheren Ständen zum Wiederherstellen.
- Vor jedem erfolgreichen Speichern legt AURA eine Version unter `_versionen` im Workflow-Ordner ab (höchstens 50). Gilt für die `workflow.json`, nicht für Wissen, Vorlagen und Feldplan.

## v172 – 03.11.2026 · Skills & Rollen direkt bearbeiten

- Knopf «Inhalt bearbeiten» mit Speichern und Abbrechen statt reiner Ansicht; die alte Fassung kommt nach `_versionen`.
- Eine Änderung hebt die Freigabe auf; AURA fragt nach dem Speichern, ob die neue Fassung gleich freigegeben werden soll.

## v169–v171 – 03.11.2026 · Chat: Belegpflicht

- Nach jeder Chat-Frage steht eine Belegpflicht: nur nennen, was ausdrücklich in den Quellen steht; das Datum einer Quelle zählt als Beleg; sonst «Dazu steht in den Quellen nichts.».
- Drei Fassungen an 30 Testfragen verglichen (v170 verworfen). Gemessen mit v171 (Apertus): 18 richtig, 6 teilweise, 6 falsch, 3 statt 5 falsche Behauptungen gegenüber v168.
- Bekannte Grenze: Das Modell antwortet teils «nichts», obwohl die Quellen das Thema enthalten.

## v168 – 03.11.2026 · Chat: Quellen statt Rückfrage

- Passen seltene Wörter nur teilweise, liest das Modell die zwei besten Teiltreffer mit (Plätze 3 und 4), statt «Meintest du …?» zu fragen. Alte Rückfrage mit `"rueckfrage_fragen": true`.

## v166–v167 – 03.11.2026 · Antwortlänge als Schieberegler, Modellvergleich

- Kurz / Normal / Ausführlich als Schieberegler; dazu eine Längenanweisung direkt nach der Frage. Tokengrenzen bleiben 250 / 500 / 900 (v166 hatte sie irrtümlich geändert, v167 korrigiert).
- Neu: `tools\modell_vergleich.py` vergleicht zwei Modelle mit `eval\fragen.txt`, mit blinder Bewertungsdatei und Schlüsseldatei.

## v165 – 03.11.2026 · Apertus 1.5 als Sprachmodell

- Neue Engine `aura/llm/apertus.py` für Apertus 1.5 (nur Text): 8-Bit-Gewichte, KV-Cache fp16, xIELU, RoPE `llama3`, Selbsttest gegen Python beim Laden. Apertus 1.5-8B erscheint in der Modellliste.
- Tokenizer und Chat-Vorlage (v164-Vorbereitung): Normalizer-Regeln, `ignore_merges`, keine Bild-/Audio-Tokens im Suchmuster, Chat-Vorlage je Modell, Denkmarker werden ausgefiltert. Prüfung: `tools\apertus_tok_test.py`.
- Vergleich mit Qwen3.5-9B: Chat mit 30 Testfragen praktisch gleichauf und schneller. Im Workflow Verfahrensentscheid nicht brauchbar (falscher Staatsvertragsbereich), deshalb für Workflows Qwen3.5-9B verwenden.

## v164 – 03.11.2026 · Nur eine AURA-Instanz, Messung Relevanzprüfung

- Zweiter Start öffnet keine neue Instanz, sondern holt das offene Fenster nach vorn.
- Neu: `tools\relevanz_test.py` misst eine Ja/Nein-Prüfung pro Quelle (ohne Eingriff in AURA).

## v163 – 03.11.2026 · Chat: Antwortlänge wählbar, weniger falsche Rückfragen

- Schalter Kurz / Normal / Ausführlich unter «Max. Quellen» (Anweisung ans Modell und 250 / 500 / 900 Tokens).
- Rückfrage nur noch, wenn ein seltenes Wort in keiner gewählten Quelle vorkommt; Füllwörter wie «bis» und «muss» zählen nicht mehr.

## v162 – 03.11.2026 · Chat: Regler «Max. Quellen», Vorselektion vollständig

- Der Regler heisst «Max. Quellen»: Er ist eine Obergrenze, schwache Treffer filtert `min_rel_score` weiterhin aus.
- Die Vorselektion zeigt alle ausgewählten Quellen statt höchstens 4.

## v161 – 03.11.2026 · Chat: Anzeige heisst «Vorselektion wird geprüft»

## v160 – 03.11.2026 · Chat: Quellen sofort sichtbar

- Sobald die Suche fertig ist, zeigt die Antwort die Vorselektion mit bis zu 4 anklickbaren Quellen – noch vor dem Laden des Modells. Am Ende ersetzt die Quellenliste diese Anzeige.
- Keine Treffer: kurze Meldung ohne Modelllauf.
- Einstellung `sofort_treffer` (Standard: an).

## v156 – 31.10.2026 · Präsentation: Einschränkungen nicht unterschlagen

- Leitplanke ohne Sprachmodell: Behauptet ein Stichpunkt unbedingt «zulässig / erlaubt / verboten / muss …», steht im passenden Quellsatz aber «grundsätzlich», «unter Voraussetzungen», «sofern/soweit», «in der Regel» oder «nur wenn», ergänzt AURA die Einschränkung in Klammern und nennt die Folie in der Antwort unter «Bitte prüfen».
- Am Bericht «Rechtlicher Rahmen Public Cloud» geprüft: «Datenübermittlung an Cloud-Anbieter bleibt rechtlich zulässig» → «… (grundsätzlich)»; bereits eingeschränkte oder nicht absolute Stichpunkte bleiben unverändert.

## v155 – 31.10.2026 · Präsentation: kürzere Stichpunkte

- Ein Gedanke pro Stichpunkt: «A; B» wird in zwei Stichpunkte geteilt (höchstens 5 je Folie); kürzere Längengrenze.
- Zweispaltige Folie nur noch mit kurzen Spaltentiteln (höchstens 5 Wörter), sonst Aufzählung – keine abgeschnittenen Titel mehr.

## v154 – 31.10.2026 · Präsentation: Kernaussagen statt Inhaltsangabe

- Lange Kapitel: statt der ersten Sätze je Unterkapitel gehen die aussagekräftigsten Sätze ans Modell (Pflichten, Verbote, Voraussetzungen, Risiken, Folgen – «muss», «nicht zulässig», «strafbar», «daher» …); Unterkapitel «Schlussfolgerung/Fazit» ganz.
- Auftrag ans Modell: Kernaussagen und Folgen nennen statt beschreiben, wovon der Text handelt; möglichst jedes Unterkapitel abdecken.
- Umbrochene Überschriften werden ergänzt («Bestimmungen zur Informationssicherheit des» → «… des Bundes»).
- Stichpunkte in Schweizer Schreibung (ß → ss).

## v153 – 31.10.2026 · Präsentation: Gliederung nach Kapiteln

- Nummerierte Überschriften zählen nur, wenn die Nummer in die Folge passt (1 → 1.1 → 1.2 → 2 …, Neubeginn bei 1 für einen neuen Teil). Fussnoten («12 Siehe …») und Seitenköpfe («Bundeskanzlei BK») werden so nicht mehr zu Folientiteln; ein Inhaltsverzeichnis wird übersprungen.
- Fussnoten werden aus dem Folientext entfernt; wiederkehrende Kopf-/Fusszeilen ebenso.
- Lange Kapitel: je Unterkapitel Titel und erste Sätze statt nur der Kapitelanfang – das Modell sieht den ganzen Inhalt.
- Titel und Fazit stützen sich auf die «Zusammenfassung» des Dokuments (oder Management Summary, Fazit), nicht mehr auf den Textanfang.
- Test am Bericht «Rechtlicher Rahmen Public Cloud» (38 Seiten): 8 Folien = die 8 Kapitel (vorher Fussnoten als Titel).

## v152 – 31.10.2026 · Präsentation aus dem Chat, Verbindung löschen, lxml-Test

**Präsentation im Chat**
- Datei anhängen (📎) und «▶ Als Präsentation» klicken – oder schreiben, z.B. «Mach daraus eine Präsentation für die Geschäftsleitung». Ergebnis: PowerPoint in der Vorlage der Bundesverwaltung (16:9), Knöpfe «Öffnen» und «Im Ordner zeigen» unter der Antwort; gespeichert in `data\praesentationen`.
- Ablauf: Gliederung ohne Sprachmodell (Überschriften, sonst Blöcke à ~1800 Zeichen, höchstens 10 Inhaltsfolien) → je Abschnitt verdichtet das Modell zu Titel, Folienart (Aufzählung / Gegenüberstellung / Kernaussage) und 2–4 Stichpunkten → Titelfolie, Inhalt und Fazit setzt AURA zusammen.
- Leitplanken ohne Modell: Stichpunkte mit Zahlen, die im Text nicht vorkommen, werden verworfen; zu lange gekürzt; Doppelte entfernt; Überschriften aus dem Text haben Vorrang.
- Einstellungen: `praes_9b` (true = grösseres Modell verwenden, falls vorhanden), `praes_vorlage` (eigene .pptx), `praes_max_folien`.
- Neuer PowerPoint-Baustein **ohne Zusatzpakete** (`aura/pptx_bau.py`, nur zipfile + XML wie bei Word): Folien verweisen auf die Layouts der Vorlage (Titelseite, Inhaltsseite, Zwei Inhalte), Design und Logo bleiben erhalten.
- Neue Dateien `aura/praesentation.py`, `aura/pptx_bau.py`, `aura/assets/Praesentation_16-9.pptx`.

**Leinwand**
- Klick auf einen Pfeil → «Verbindung löschen» entfernt im Ziel alle `{{quelle.…}}` (bei «Start»: `{{input.…}}`); «Nur wenn» wird nicht angefasst.

**lxml-Test**
- `py tools\lxml_test.py` prüft, ob lxml, Pillow und python-pptx auf diesem Rechner laden (drei Ordner: `vendor\bin_test`, `%LOCALAPPDATA%`, `%TEMP%`). Pakete für Python 3.11–3.13 in `tools\lxml_test\`. Ändert nichts an AURA.

## v151 – 31.10.2026 · Verbinden: klarere Auswahl

- Menü nennt Quelle und Ziel («Von … nach …»); der gelesene Text steht zuerst und zeigt, aus welcher Eingabe er stammt (z.B. «dateien.text – der gelesene Text – Leistungsbeschrieb»).

## v150 – 31.10.2026 · Leinwand: Verbinden per Ziehen

- Jeder Knoten hat rechts einen Anschluss ●. Von dort auf einen anderen Knoten ziehen → Menü «In … übernehmen»: Feld des Ziels und Wert der Quelle wählen (z.B. → Dateien: input.checkliste). AURA schreibt den Ausdruck `{{quelle.wert}}` ins Feld – die Verbindung *ist* der Verweis, es entsteht keine zweite Wahrheit.
- Steht im Feld schon etwas: ersetzen oder anhängen. Läuft die Quelle später als das Ziel, wird sie automatisch davor geschoben.
- Vom «▶ Start» lassen sich Eingaben (`input.…`) auf Schritte ziehen.
- Schrift auf der Leinwand in Pixeln statt Punkten: passt bei jeder Windows-Skalierung in die Knoten.

## v149 – 31.10.2026 · Workflows: zwei Reiter statt sieben

- Nur noch **«Bauen»** (Leinwand) und **«Ausführen»**. «Übersicht» und «Ablauf» entfallen – Struktur, fehlende Verweise und Status des letzten Laufs zeigt die Leinwand. Der Schalter «Expertenansicht» entfällt.
- **Wissen**, **Vorlagen & Feldplan** und **Prüfliste** öffnen sich als Fenster: über die Knöpfe über der Leinwand oder am passenden Knoten («Wissen durchsuchen», «Word-Vorlage ausfüllen», «Prüfliste»). Offene Fenster werden nach dem Speichern aufgefrischt; alte Sprünge auf diese Reiter führen dorthin.
- Kasten «Auslöser» entfällt auf der Leinwand: Klick auf **«▶ Start»** zeigt Eingaben und Zeitplan rechts (bearbeiten, hinzufügen, entfernen). Start-Knoten näher an der ersten Spalte, mit Anzahl Eingaben.
- Kopfzeile: nur «☆ Als Widget» und **«⋯»** (Neu laden, Ordner öffnen, Exportieren, workflow.json bearbeiten, Löschen).
- «+ Schritt hinzufügen» nur noch in der Ansicht «Liste» – auf der Leinwand übernimmt das die Palette.

## v148 – 31.10.2026 · Leinwand: Zoom und Verschieben

- Mausrad = Zoom um den Mauszeiger (40–250 %, bleibt beim Neuzeichnen erhalten); rechte oder mittlere Maustaste halten = Leinwand verschieben.
- Text in Anführungszeichen innerhalb von `{{ … }}` und «Nur wenn» (z.B. «Art. 21 Abs. 2») gilt nicht mehr als Verweis – keine falschen «unbekannter Wert».

## v147 – 31.10.2026 · Scharfes Taskleisten-Symbol

- Das Fenstersymbol wird in der Grösse geladen, die Windows für die aktuelle Skalierung verlangt (z.B. 40 px bei 125 %, 48 px bei 150 %), statt das 32-px-Symbol von Tk hochzuskalieren. Grösse und DPI im Log (`DIAG icon`).

## v146 – 31.10.2026 · Leinwand für Workflows, Skills & Rollen

**Leinwand (Reiter «Schritte»)**
- Neue Standardansicht **«Leinwand»**, Umschalter «Leinwand | Liste» (gespeichert als `schritte_ansicht`).
- Links die Palette mit allen Bausteinen (Holen, Verarbeiten, Ausgeben): Klick = neuer Schritt hinter dem gewählten.
- In der Mitte der Workflow als Bild: Spalte = Tiefe im Datenfluss (was ein Schritt verwendet, steht links davon), Farbe = Gruppe, Nummer = Reihenfolge des Laufs. Raute = «Nur wenn», ↻ = «Für jedes …», Punkt = Ergebnis des letzten Laufs.
- **Pfeile werden aus den Verweisen `{{schritt.wert}}` abgeleitet**, nicht gespeichert – keine zweite Wahrheit neben der `workflow.json`. Rot gestrichelt = verwendet einen Schritt, der erst später läuft; roter Rand = unbekannter Wert oder fehlende Eingabe.
- Rechts die Details des gewählten Schritts: verwendet / wird verwendet von, Probleme, Bearbeiten, Testen, Löschen, «◀ früher / später ▶». Doppelklick öffnet das Formular.
- Neue Dateien `aura/workflow/graph.py` (ohne Oberfläche, testbar) und `aura/workflow_canvas.py`.

**Skills & Rollen**
- Neu unter **Workflows › Skills & Rollen**: verfügbare Skills und Rollen mit Beschreibung, Rechten, Version und Autor; Schalter «Freigegeben».
- **Rolle** = Markdown in `C:\aura\rollen\`. Verwendung im Chat (Auswahl «Rolle» über dem Chat; die AURA-Regeln – nur Quellen, mit Belegen – gehen vor) und im Baustein «Anweisung ans Sprachmodell» (Feld «Rolle», der bisherige Text heisst jetzt «Systemtext»).
- **Skill** = Workflow-Paket mit `skill.json` (Titel, Beschreibung, Rolle, Rechte, Version, Autor, Stand). «Als neuen Workflow …» kopiert ihn ohne Läufe.
- **Freigabe mit Prüfsumme** (`skills_freigabe`): Neu importierte und seit der Freigabe geänderte Einträge sind aus (orange markiert), bis man sie prüft. Kein Sprachmodell wählt Skills aus.
- **Markdown importieren …**: Rollen-Dateien werden Rollen, Aufgaben-/Skill-Dateien ein Workflow-Paket im Rohbau mit `anleitung.md`; «Arbeite nach `ROLLE_….md`» verknüpft die Rolle. Feldplan, Regeln und Wissen richtet man danach ein.
- Neue Dateien `aura/skills.py`, `aura/skills_gui.py`.

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
