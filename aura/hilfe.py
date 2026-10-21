# aura/hilfe.py — Infotexte (Tooltips) fuer alle Fenster. Version 20261021v114 (v114: Schalter Nachnamen; v113: Werkzeuge › Text anonymisieren; v109: Menügruppen, Widgets, Log öffnen; v90: Übersicht, Expertenansicht; v82: «Beim Start Widgets zeigen»; v81: Widgets-Ansicht; v80: «▶», Widgets; v79: «⌂», Ablaufband; v75: Position korrigiert (Reihenfolge withdraw/topmost/geometry/deiconify); v74: Tooltip vor dem Hauptfenster; v70: Text «8 Bit»; v68: Info-Leiste rechts; v60: Tooltip verschwindet beim Minimieren/Fensterwechsel, nicht mehr über anderen Programmen; v46: Slide-In, Vollansicht, Startfragen)
# Alle Texte stehen hier an einem Ort. Zuordnung:
#   auto(fenster, ctx)  - findet Knoepfe/Schalter/Haekchen anhand ihrer Beschriftung (TEXTE[ctx], dann TEXTE["*"])
#   tip(widget, key)    - fester Text fuer Felder ohne Beschriftung (key beginnt mit "#") oder freier Text
# Workflows koennen eigene Texte liefern: "hilfe" bei inputs und steps in der workflow.json.
import tkinter as tk
import customtkinter as ctk

DELAY_MS = 600
WATCH_MS = 300                                                      # v60: Prüfintervall, solange ein Tooltip sichtbar ist

TEXTE = {
    "haupt": {
        "Quellen": "Quellen verwalten: Outlook-Mails, Kalender, Edge-Verlauf und Dokumentordner verbinden und abgleichen.",
        "Laden": "Lädt das gewählte Sprachmodell auf die Grafikkarte (ca. 1 Minute). Nötig für ausformulierte Antworten und für Workflows.",
        "Entladen": "Gibt den Grafikspeicher frei. Bis zum nächsten «Laden» zeigt AURA nur Fundstellen statt ausformulierter Antworten.",
        "Auto-Abgleich": "Holt alle 15 Minuten neue Mails, Termine und Verlaufseinträge und berechnet deren Vektoren. Fragen bleiben währenddessen möglich.",
        "Wissen im Chat": "Ein: Antworten im Chat ziehen zusätzlich die Wissenssammlungen bei (z.B. Gesetzestexte).\nAus: nur Mails, Termine, Verlauf und Dokumente.",
        "Wissen": "Öffnet die Wissenssammlungen: Fachdokumente, die Workflows und – falls eingeschaltet – der Chat verwenden.",
        "Vektoren berechnen": "Berechnet für neu eingelesene Texte die Vektoren (Suche nach Bedeutung). Ohne Vektoren findet AURA nur exakt gleiche Wörter. «Pause» unterbricht.",
        "Pause": "Unterbricht die laufende Arbeit (Vektoren, Abgleich). Bereits Erledigtes bleibt erhalten; später einfach neu starten.",
        "Workflows öffnen": "Öffnet die Workflows: Unterlagen nach festem Ablauf prüfen und eine Vorlage ausfüllen lassen (z.B. Verfahrensentscheid).",
        "➤": "Frage senden (Enter). Shift+Enter fügt eine neue Zeile ein.",
        "Kopieren": "Kopiert den Text in die Zwischenablage.",
        "Alle Ergebnisse": "Öffnet die Ansicht «Ergebnisse» mit allen Läufen.",
        "Workflow": "Öffnet diesen Workflow.",
        "8 Bit (schneller)": "Ein: Das Sprachmodell wird beim Laden auf 8 Bit umgerechnet. Braucht halb so viel Grafikspeicher und "
                             "schreibt schneller; die Antworten können minimal abweichen. Gilt beim nächsten «Laden».",
        "Info-Leiste rechts": "Zeigt rechts Sprachmodell, Wissensdatenbank und die letzten Workflow-Läufe. Blendet sich bei "
                              "schmalem Fenster automatisch aus – Fenster breiter ziehen, dann erscheint sie wieder.",
        "alle anzeigen →": "Öffnet die Ansicht «Ergebnisse» mit allen Läufen, Dokumenten und Prüfhinweisen.",
        "Beim Start Widgets zeigen": "Ein: AURA öffnet beim Start die Widgets (▶). Aus: AURA öffnet mit den Fragen (⌂). Wirkt beim nächsten Start.",
        "⌂": "Zu den Fragen (Startseite mit Kacheln). Der Chatverlauf wird dabei geleert.",
        "▶": "Workflow-Ergebnisse: die angehefteten Widgets in voller Breite. «⌂» führt zurück zu den Fragen.",
        "Ergebnisse": "Ergebnisse aller Workflows: neueste zuerst, mit Öffnen, Speichern und Laufordner.",
        "Log öffnen": "Öffnet das Protokoll (Log) – nützlich bei Fehlermeldungen.",
        "Text anonymisieren": "Ersetzt Namen, AHV-Nummern, IBAN, Mailadressen, Telefonnummern, Koordinaten und deine heiklen Begriffe "
                              "durch Platzhalter. Du prüfst die Markierungen, bevor etwas ersetzt wird. Die Einstufung des Textes bleibt.",
        "Kontext": "Zeigt die Textstücke, die das Sprachmodell für diese Antwort gelesen hat. Hilfreich, wenn eine Antwort falsch wirkt: Stand die Information überhaupt drin?",
    },
    "anon": {                                                        # v113
        "📄  Datei wählen und prüfen …": "Datei wählen (PDF mit Text, Word, Text, Markdown, E-Mail .eml). AURA liest sie nur – die Datei bleibt unverändert.",
        "Eingefügten Text prüfen ▶": "Prüft den Text im Feld darüber. Nichts wird gespeichert.",
        "Begriffsliste einrichten (5 Minuten) …": "Geführt: Personen, Projekte, Standorte, Partner und Systeme erfassen. Die Liste bleibt nur auf diesem Rechner.",
        "Begriffsliste bearbeiten …": "Begriffsliste ergänzen oder ändern (geführt, Schritt für Schritt).",
        "＋ Markierung hinzufügen": "Zuerst Text mit der Maus markieren. AURA ersetzt dann diese Stelle und alle gleich geschriebenen.",
        "Freigeben & ersetzen ▶": "Ersetzt alle farbig markierten Stellen. Grau (abgewählt) bleibt stehen.",
        "← Neuer Text": "Verwirft diese Prüfung und beginnt mit einem neuen Text.",
        "Kopieren": "Kopiert den anonymisierten Text in die Zwischenablage.",
        "Speichern als .txt …": "Speichert den anonymisierten Text als Textdatei an einem Ort deiner Wahl.",
        "Aus Datei übernehmen …": "Liste aus einer Datei übernehmen: eine Zeile pro Begriff (txt, docx) oder eine Tabelle mit Spalte «Begriff» "
                                  "(csv, xlsx – z.B. die tiseR-Liste, Blatt «_anon»).",
        "Vorschläge aus meinen Mails …": "Zeigt die häufigsten Absender aus deinen Mails zum Anhaken. Nur übernehmen, wer wirklich geschützt werden muss.",
        "Weiter →": "Eingaben dieser Seite merken und weiter. Gespeichert wird erst am Schluss.",
        "Speichern ✓": "Speichert die Begriffsliste (nur auf diesem Rechner, data\\anon\\begriffe.csv).",
        "Abbrechen": "Ohne Speichern zurück.",
        "Nachnamen auch allein ersetzen *": "Ein: «Muster» wird auch ohne Vornamen ersetzt (findet mehr). Gross-/Kleinschreibung zählt, "
                                           "gewöhnliche Wörter wie «Koch» oder «Schweizer» bleiben aussen vor. Aus: nur Vor- und Nachname zusammen.",
    },
    "quellen": {
        "Ordner": "Outlook-Ordner wählen, die AURA einlesen soll. Mails aus abgewählten Ordnern werden nach Rückfrage aus AURA entfernt – in Outlook bleibt alles.",
        "…": "Dokumentordner auf diesem Rechner wählen (PDF mit Text, Word, Text, Markdown). Danach «Sync».",
        "✕": "Dokumentordner abwählen: Die eingelesenen Dokumente werden aus AURA entfernt, die Dateien im Ordner bleiben unberührt. Erneutes Einlesen ist jederzeit möglich.",
        "Links": "Confluence-Links verwalten: Seite (mit allen Unterseiten) oder ganzen Bereich einfügen. Ohne Anmeldung, nur öffentlich sichtbare Seiten.",
        "+ Link einfügen": "Fügt den Link hinzu. Danach in «Quellen» bei Confluence «Sync».",
        "Sync": "Liest neue Einträge dieser Quelle ein (Bekanntes wird übersprungen). Danach links «Vektoren berechnen».",
        "Schliessen": "Bereich schliessen. Ein laufender Abgleich geht im Hintergrund weiter.",
        "Alles zurücksetzen …": "Löscht alles Eingelesene (Mails, Termine, Verlauf, Dokumente, Vektoren), wählt alle Quellen ab und "
                                "schaltet den Auto-Abgleich aus. Outlook, Originaldateien, Wissen und Workflows bleiben. AURA startet neu.",
    },
    "ordner": {
        "Speichern & synchronisieren": "Speichert die Auswahl und gleicht sofort ab. Mails aus abgewählten Ordnern werden nach Rückfrage aus AURA gelöscht (in Outlook bleiben sie).",
        "Abbrechen": "Zurück zu den Quellen, ohne die Auswahl zu speichern.",
    },
    "wissen": {
        "+ Neue Sammlung": "Legt eine neue Wissenssammlung an. Danach Dokumente hinzufügen.",
        "+ Dokumente hinzufügen …": "Kopiert Dateien in die Sammlung (PDF mit Textschicht, Word, Text, Markdown). Danach Kürzel, Art und Stand ergänzen und «Speichern & abgleichen».",
        "Ordner öffnen": "Öffnet den Sammlungsordner im Explorer. Normalerweise nicht nötig – alles lässt sich hier pflegen.",
        "Speichern & abgleichen": "Speichert die Angaben und bereitet die Dokumente für die Suche auf (zerlegen, Vektoren berechnen). Dauert je nach Umfang einige Minuten.",
        "✕": "Dokument aus der Sammlung entfernen. Die Datei wird in den Unterordner «_entfernt» verschoben, nicht gelöscht.",
        "Im Chat verwendbar (wenn «Wissen im Chat» eingeschaltet ist)":
            "Ein: Diese Sammlung wird im Chat beigezogen, sofern links «Wissen im Chat» eingeschaltet ist. Aus: nur für Workflows.",
    },
    "workflow": {
        "+ Neuer Workflow": "Legt ein neues Workflow-Paket an (Ordner mit workflow.json, eigenem Wissen, Vorlagen und Läufen).",
        "Gemeinsame Sammlungen …": "Wissenssammlungen, die mehrere Workflows (und der Chat) gemeinsam nutzen. «← Zurück» führt wieder hierher.",
        "workflow.json bearbeiten": "Öffnet die Workflow-Definition im Texteditor (für KI-Spezialisten). Nach dem Speichern «Neu laden».",
        "Neu laden": "Liest die workflow.json neu ein, z.B. nach einer Änderung im Editor.",
        "Ordner öffnen": "Öffnet den Paketordner im Explorer (workflow.json, wissen, vorlagen, laeufe).",
        "Löschen": "Löscht den Workflow mit Wissen, Vorlagen und allen Läufen. Der Ordner wird nach «workflows\\_geloescht» verschoben und lässt sich von dort zurückholen.",
        "In Paket umwandeln": "Wandelt die alte Einzeldatei in ein Paket mit eigenem Wissen, Vorlagen und Läufen um. Einmalig nötig für Workflows aus Versionen vor v36.",
        "☆ Als Widget": "Zeigt das Ergebnis des letzten Laufs als Widget unter «Workflows › Widgets» (nur bei Ausgabe «Anzeige in AURA» sinnvoll).",
        "★ Als Widget": "Ist als Widget unter «Workflows › Widgets» angeheftet. Klick entfernt das Widget wieder (der Workflow bleibt).",
        "Ablauf": "Schritte des Workflows als Band mit dem Ergebnis des letzten Laufs. Klick auf einen Schritt zeigt sein Ergebnis.",
        "Ausführen": "Workflow mit eigenen Unterlagen starten und den Fortschritt verfolgen.",
        "Wissen": "Fachdokumente, die nur dieser Workflow verwendet.",
        "Vorlage": "Felder der Word-Vorlage, ihre Zuordnung und der Wert aus dem letzten Lauf – zum Prüfen der Abfüllung.",
        "Dateien wählen …": "Eingabedateien für diesen Lauf wählen. Sie werden nur gelesen und nie in AURAs Wissen aufgenommen.",
        "▶  Starten": "Startet den Workflow mit den Eingaben links. Dauer je nach Modell ca. 10–25 Minuten – Notebook währenddessen nicht zuklappen.",
        "Abbrechen": "Bricht den Lauf nach dem aktuellen Schritt ab. Erledigte Schritte bleiben im Zwischenstand gespeichert.",
        "Ab Schritt neu (letzter Lauf)": "Wiederholt den letzten Lauf ab dem gewählten Schritt und übernimmt die Ergebnisse der Schritte davor. "
                                         "So lassen sich Regeln oder die Vorlagenzuordnung in Sekunden testen, ohne das Sprachmodell erneut laufen zu lassen.",
        "+ Vorlage hinzufügen …": "Word-Vorlage (.docx) ins Paket kopieren. Danach in der workflow.json einen Schritt «word_vorlage» darauf verweisen lassen.",
        "Laufordner öffnen": "Öffnet den Ordner dieses Laufs: Eingaben, Ergebnis, Zwischenstand und Protokoll.",
        "Öffnen: *": "Öffnet das erzeugte Dokument. Es ist ein Entwurf – bitte fachlich prüfen.",
        "Expertenansicht": "Aus: Übersicht, Ausführen und Wissen – für die tägliche Arbeit.\nEin: zusätzlich Ablauf, Schritte, Prüfliste, "
                           "Vorlage und «workflow.json bearbeiten» (für KI-Spezialisten).",
        "+ Eingabe …": "Neue Eingabe beim Start: Dateien (z.B. Unterlagen) oder ein Textfeld.",
        "Zeitplan …": "Workflow automatisch ausführen lassen, z.B. werktags um 08:00 (läuft, solange AURA offen ist).",
        "Hilfsdokumente …": "Richtlinien, Erlasse und Vorlagen, die AURA bei diesem Workflow beizieht (Reiter «Wissen»).",
        "Schritte im Detail …": "Öffnet die Expertenansicht mit allen Schritten und ihren Einstellungen.",
        "Felder zuordnen …": "Für jedes Feld der Vorlage festlegen, woher der Wert kommt: aus den Unterlagen, aus einer Regel, fester Wert "
                             "oder Bedarfsstelle trägt nach. Danach «Workflow aus Feldplan bauen».",
        "+ Vorlage hochladen …": "Word-Vorlage (.docx) wählen. AURA kopiert sie in den Workflow, liest alle Felder aus und öffnet "
                                 "«Felder zuordnen»: pro Feld festlegen, woher der Wert kommt, dann «Workflow aus Feldplan bauen».",
        "Bearbeiten": "Bezeichnung, Art (Dateien/Text), Dateitypen und «freiwillig» ändern.",
        "✕ Entfernen": "Eingabe entfernen. Wird sie von einem Schritt verwendet, warnt AURA vorher; ein Workflow, der danach nicht mehr "
                       "läuft, wird nicht gespeichert.",
        "Mitlesen": "«Dokumente lesen» liest danach alle Datei-Eingaben – jedes Dokument mit seinem Namen, damit das Sprachmodell "
                    "z.B. Leistungsbeschrieb und Checkliste auseinanderhält.",
        "Weiter: Ausführen ▶": "Zum Reiter «Ausführen»: Unterlagen wählen und starten.",
    },
    "*": {
        "#modell": "Sprachmodell wählen. Ohne Sprachmodell zeigt AURA nur die besten Fundstellen. Qwen-Modelle formulieren Antworten, müssen aber zuerst geladen werden («Laden»).",
        "#modell_status": "Zustand des Sprachmodells: grau = nicht geladen, orange = wird geladen, grün = bereit.",
        "#uebersicht": "Anzahl eingelesener Objekte und wie viele davon Vektoren haben. Unter 100 %: «Vektoren berechnen».",
        "#auto_status": "Zeitpunkt und Ergebnis des letzten automatischen Abgleichs.",
        "#frage": "Frage in normaler Sprache stellen, z.B. «Welche Termine habe ich nächste Woche?» oder «Was schrieb X zum Budget?».\nEnter = senden, Shift+Enter = neue Zeile.",
        "#beispiel": "Klick stellt die Frage sofort.\nBei «XY» wird sie nur ins Eingabefeld übernommen: «XY» ist markiert und wird beim Tippen durch dein Thema ersetzt.",
        "#version": "Installierte Version von AURA. Klick öffnet das Protokoll (Log) – nützlich bei Fehlermeldungen.",
        "#fortschritt": "Was AURA gerade im Hintergrund tut. Balken: blau = läuft, grün = fertig, rot = Fehler (Details: Einstellungen › Log öffnen).",
        "#zurueck": "Zurück zur vorherigen Ansicht bzw. zum Chat. Diese Ansicht bleibt im Hintergrund offen – ein laufender Workflow läuft weiter.",
        "#panel_zu": "Bereich schliessen (Esc). Ein laufender Abgleich geht im Hintergrund weiter.",
        "#w_name": "Name, wie er in Listen erscheint. Der Ordnername bleibt unverändert.",
        "#w_beschreibung": "Wofür die Sammlung gedacht ist – hilft anderen bei der Auswahl.",
        "#w_alter": "Ab diesem Alter (gemessen am «Stand») warnt AURA, dass ein Dokument veraltet sein könnte. 0 = nie warnen.",
        "#wf_ab": "Schritt, ab dem «Ab Schritt neu» rechnet. Alle Schritte davor kommen aus dem letzten Lauf.",
        "#wf_vorlage_tabelle": "Grün = Feld wurde im letzten Lauf gefüllt, grau = leer, rot = Fehler in der Zuordnung. Spaltenbreite durch Ziehen am Spaltenrand anpassen.",
        "#wf_input_files": "Dateien für diesen Lauf. Mit * markierte Eingaben sind Pflicht.",
        "#wf_input_text": "Freie Angabe für diesen Lauf. Ohne * ist das Feld optional.",
    },
}

# Spalten der Dokumenttabelle (Wissenssammlungen): Kopf und Zellen zeigen denselben Text
WISSEN_SPALTEN = {
    "Datei": "Dateiname im Sammlungsordner. Rot = Datei fehlt.",
    "Kürzel": "Kurzname, mit dem Workflows das Dokument ansprechen, z.B. «BöB». Muss eindeutig sein.",
    "Titel": "Voller Titel; erscheint in den Quellenangaben.",
    "Art": "Wie das Dokument zerlegt wird: «Erlass (Artikel)» = nach Artikeln (Gesetze, Verordnungen), «Fliesstext» = nach Absätzen, «automatisch» = AURA entscheidet.",
    "Stand": "Stand des Dokuments (TT.MM.JJJJ). Erscheint in jeder Fundstelle und löst bei Überalterung eine Warnung aus.",
    "Pflicht": "Angehakt: Workflows brechen ab, wenn dieses Dokument fehlt.",
    "Status": "Ergebnis des letzten Abgleichs: Anzahl Textstücke und Vektoren.",
}

# Schritt-Typen der Workflow-Engine (Standardtext, wenn der Schritt keine eigene "hilfe" hat)
SCHRITTE = {
    "extract": "Liest den Text aus den Eingabedateien.",
    "rag": "Sucht passende Stellen in der Wissenssammlung; Pflichtstellen werden immer mitgegeben.",
    "llm": "Das Sprachmodell erfasst Fakten oder Text. Längster Schritt des Laufs.",
    "set": "Legt feste Werte fest oder formt Werte um (ohne Sprachmodell).",
    "regel": "Entscheidungstabelle: Die erste zutreffende Regel gilt. Rechnet ohne Sprachmodell.",
    "word_vorlage": "Füllt die Word-Vorlage mit den Ergebnissen.",
    "template": "Füllt eine Text-/HTML-Vorlage.",
    "file_out": "Schreibt eine Ergebnisdatei.",
}

TIP_CLASSES = (ctk.CTkButton, ctk.CTkSwitch, ctk.CTkCheckBox)


def lookup(ctx, text):
    """Infotext zu einer Beschriftung: zuerst im Fenster-Kontext, dann allgemein; «xyz *» passt als Anfang."""
    if not text: return ""
    text = str(text)
    for c in (ctx, "*"):
        d = TEXTE.get(c, {})
        if text in d: return d[text]
        for k, v in d.items():
            if k.endswith(" *") and text.startswith(k[:-1]): return v
    return ""


class Tooltip:
    """Kleines Infofenster nach kurzer Verweildauer der Maus. text = str oder Funktion (wird beim Anzeigen gelesen)."""
    def __init__(self, widget, text):
        self.w, self.text, self.job, self.top = widget, text, None, None
        widget._aura_tip = self
        for seq, fn in (("<Enter>", self._enter), ("<Leave>", self._leave), ("<ButtonPress>", self._hide)):
            try: widget.bind(seq, fn, add="+")
            except Exception: pass

    def _enter(self, _e=None):
        self._cancel()
        try: self.job = self.w.after(DELAY_MS, self._show)
        except Exception: pass

    def _leave(self, _e=None):
        # CTk-Knoepfe bestehen aus mehreren Teilen: Wechsel zwischen den Teilen ist kein Verlassen
        try: self.w.after(40, self._check_left)
        except Exception: self._hide()

    def _check_left(self):
        try:
            x, y = self.w.winfo_pointerxy(); under = self.w.winfo_containing(x, y)
            p, s = str(self.w), str(under) if under is not None else ""
            if s == p or s.startswith(p + "."): return                 # noch ueber einem Teil dieses Widgets
        except Exception: pass
        self._hide()

    def _cancel(self):
        if self.job:
            try: self.w.after_cancel(self.job)
            except Exception: pass
            self.job = None

    def _show(self):
        self.job = None
        try:
            txt = self.text() if callable(self.text) else self.text
            if not txt or self.top or not self.w.winfo_viewable(): return
            dark = ctk.get_appearance_mode() == "Dark"
            sc = ctk.ScalingTracker.get_widget_scaling(self.w) or 1.0
            top = self.top = tk.Toplevel(self.w); top.withdraw()           # v75: erst unsichtbar aufbauen und platzieren
            top.wm_overrideredirect(True)
            try: top.attributes("-topmost", True)                         # vor dem Platzieren setzen, sonst springt es nach 0,0
            except Exception: pass
            tk.Label(top, text=txt, justify="left", wraplength=int(380 * sc), padx=int(9 * sc), pady=int(6 * sc),
                     bg="#2A303B" if dark else "#FFFBE6", fg="#E8EAED" if dark else "#111827",
                     relief="solid", bd=1, font=("Segoe UI", 10)).pack()
            top.update_idletasks()
            px = self.w.winfo_pointerx() + 14
            py = self.w.winfo_rooty() + self.w.winfo_height() + 6
            sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
            tw, th = top.winfo_reqwidth(), top.winfo_reqheight()
            if px + tw > sw - 8: px = max(8, sw - tw - 8)
            if py + th > sh - 40: py = max(8, self.w.winfo_rooty() - th - 6)     # unten kein Platz -> oberhalb
            top.wm_geometry(f"+{px}+{py}"); top.deiconify(); top.lift()
            top.wm_geometry(f"+{px}+{py}")                                 # Windows: nach dem Anzeigen nochmals setzen
            # v74/v75: zuoberst statt transient (lag sonst hinter dem Hauptfenster). Unkritisch, weil _watch den Tooltip
            # schliesst, sobald AURA nicht mehr im Vordergrund ist.
            self.w.after(WATCH_MS, self._watch)
        except Exception:
            self._hide()

    def _watch(self):
        """v60: Solange sichtbar regelmässig prüfen – weg, wenn AURA minimiert/inaktiv ist oder die Maus woanders steht."""
        if not self.top: return
        try:
            tl = self.w.winfo_toplevel()
            weg = (not self.w.winfo_exists() or not self.w.winfo_viewable() or tl.state() in ("iconic", "withdrawn")
                   or self.w.focus_displayof() is None)                 # anderes Programm im Vordergrund
            if not weg:
                x, y = self.w.winfo_pointerxy(); under = self.w.winfo_containing(x, y)
                p, s = str(self.w), str(under) if under is not None else ""
                weg = not (s == p or s.startswith(p + "."))
        except Exception: weg = True
        if weg: self._hide()
        else: self.w.after(WATCH_MS, self._watch)

    def _hide(self, _e=None):
        self._cancel()
        if self.top:
            try: self.top.destroy()
            except Exception: pass
            self.top = None


def tip(widget, key_or_text):
    """Fester Infotext: "#schluessel" aus TEXTE["*"] oder direkt ein Text bzw. eine Funktion."""
    if widget is None or getattr(widget, "_aura_tip", None): return widget
    t = key_or_text
    if isinstance(t, str) and t.startswith("#"): t = TEXTE["*"].get(t, "")
    if t: Tooltip(widget, t)
    return widget


def auto(container, ctx):
    """Haengt Infotexte an alle beschrifteten Knoepfe, Schalter und Haekchen unterhalb von container.
    Der Text wird beim Anzeigen nachgeschlagen (z.B. «Laden»/«Entladen» wechselt). Mehrfach aufrufbar."""
    try: kids = container.winfo_children()
    except Exception: return
    for w in kids:
        if isinstance(w, TIP_CLASSES):
            if getattr(w, "_aura_tip", None): continue
            try: label = w.cget("text")
            except Exception: continue
            if lookup(ctx, label): Tooltip(w, lambda w=w: lookup(ctx, w.cget("text")))
            continue                                   # Innenleben von CTk-Knoepfen nicht durchsuchen
        auto(w, ctx)
