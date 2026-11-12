# aura/skills_gui.py — Fenster «Skills & Rollen» (Werkzeuge › Skills & Rollen). Version 20261112v229 (v229: «＋ Neu …» erstellt Rolle/Skill als Markdown; v172: Inhalt direkt bearbeiten)
# Zeigt, was verfügbar ist, mit Rechten, Version und Autor; Schalter «Freigegeben». Neu importierte oder geänderte Einträge sind
# aus, bis sie hier geprüft und freigegeben werden. Logik in skills.py – hier nur die Oberfläche.
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
import customtkinter as ctk
from . import skills as SK


class SkillsFenster:
    def __init__(self, app):
        import aura.gui as G
        self.app, self.G = app, G
        w = self.win = ctk.CTkToplevel(app.root); w.title("Skills & Rollen"); w.geometry("860x680"); w.transient(app.root)
        w.protocol("WM_DELETE_WINDOW", self.schliessen)
        hd = ctk.CTkFrame(w, fg_color="transparent"); hd.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(hd, text="Skills & Rollen", font=G.font(20, "bold"), text_color=G.INK).pack(side="left")
        ctk.CTkButton(hd, text="＋ Neu …", height=30, fg_color=G.ACCENT, hover_color=G.ACCENT_HI,
                      font=G.font(12, "bold"), command=self.neu).pack(side="right")                     # v229
        ctk.CTkButton(hd, text="Markdown importieren …", height=30, fg_color=G.BORDER, hover_color=G.MUTED, text_color=G.INK,
                      font=G.font(12), command=self.importieren).pack(side="right", padx=6)
        ctk.CTkButton(hd, text="Ordner «rollen»", height=30, fg_color=G.BORDER, hover_color=G.MUTED, text_color=G.INK,
                      font=G.font(12), command=self._ordner).pack(side="right", padx=6)
        ctk.CTkLabel(w, text="Rolle = Haltung und Arbeitsgrundsätze, im Chat (Auswahl über dem Chat) oder im Baustein «Anweisung ans "
                     "Sprachmodell». Skill = fertiger Workflow mit Beschreibung, als Vorlage für eigene Workflows.\n"
                     "Neu importierte oder geänderte Einträge sind aus, bis du sie geprüft und freigegeben hast.",
                     font=G.font(11), text_color=G.MUTED, justify="left", anchor="w", wraplength=820).pack(fill="x", padx=16)
        self.lst = ctk.CTkScrollableFrame(w, fg_color="transparent"); self.lst.pack(fill="both", expand=True, padx=10, pady=8)
        self.lst.grid_columnconfigure(0, weight=1)
        self.fuellen()

    def alive(self):
        try: return bool(self.win.winfo_exists())
        except Exception: return False

    def schliessen(self):
        try: self.app.refresh_rolle()
        except Exception: pass
        self.win.destroy()

    def _ordner(self):
        SK.ROLLEN_DIR.mkdir(exist_ok=True)
        try:
            import os; os.startfile(str(SK.ROLLEN_DIR))
        except Exception as e: messagebox.showinfo("Skills & Rollen", f"{SK.ROLLEN_DIR}\n\n{e}", parent=self.win)

    # ------------------------------------------------------------------ Liste
    def fuellen(self):
        G = self.G
        for c in self.lst.winfo_children(): c.destroy()
        eintraege = SK.alle(); r = 0
        for art, titel in (("skill", "SKILLS"), ("rolle", "ROLLEN")):
            ctk.CTkLabel(self.lst, text=titel, font=G.font(10, "bold"), text_color=G.MUTED, anchor="w").grid(row=r, column=0, sticky="w", pady=(8, 2)); r += 1
            teil = [e for e in eintraege if e["art"] == art]
            if not teil:
                ctk.CTkLabel(self.lst, text="Noch keine. «＋ Neu …» erstellt eine, «Markdown importieren …» übernimmt eine Datei wie "
                             + ("AUFGABE_….md." if art == "skill" else "ROLLE_….md."), font=G.font(11), text_color=G.MUTED,
                             anchor="w").grid(row=r, column=0, sticky="w"); r += 1
            for e in teil: self._karte(e, r); r += 1

    def _karte(self, e, r):
        G = self.G
        k = ctk.CTkFrame(self.lst, fg_color=G.BUBBLE, corner_radius=0, border_width=1,
                         border_color=G.AMBER if e["geaendert"] else (G.ACCENT if e["aktiv"] else G.BORDER))
        k.grid(row=r, column=0, sticky="ew", pady=3); k.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(k, text=e["titel"], font=G.font(13, "bold"), text_color=G.INK, anchor="w").grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))
        info = [x for x in (f"Version {e['version']}" if e["version"] else "", e["autor"], e["name"]) if x]
        ctk.CTkLabel(k, text="  ·  ".join(info), font=G.font(10), text_color=G.MUTED, anchor="w").grid(row=1, column=0, sticky="w", padx=12)
        zeilen = []
        if e["beschreibung"]: zeilen.append(e["beschreibung"])
        rechte = [SK.RECHTE[x] for x in e.get("rechte", [])]
        zeilen.append("Rechte: " + (", ".join(rechte) if rechte else "nur lokal lesen"))
        if e.get("rolle"):
            t = next((x["titel"] for x in SK.rollen() if x["name"] == e["rolle"]), e["rolle"] + " (fehlt)")
            zeilen.append(f"Rolle: {t}")
        if e.get("status"): zeilen.append(f"Stand: {e['status']}")
        ctk.CTkLabel(k, text="\n".join(zeilen), font=G.font(11), text_color=G.INK, anchor="w", justify="left",
                     wraplength=560).grid(row=2, column=0, sticky="w", padx=12, pady=(2, 4))
        if e["geaendert"]:
            ctk.CTkLabel(k, text="⚠ Inhalt seit der Freigabe geändert – bitte prüfen und neu freigeben.", font=G.font(11),
                         text_color=G.AMBER_HI, anchor="w").grid(row=3, column=0, sticky="w", padx=12)
        rechts = ctk.CTkFrame(k, fg_color="transparent"); rechts.grid(row=0, column=1, rowspan=4, sticky="ne", padx=10, pady=8)
        var = tk.BooleanVar(value=e["aktiv"])
        ctk.CTkSwitch(rechts, text="Freigegeben", variable=var, font=G.font(11), text_color=G.INK, progress_color=G.ACCENT,
                      command=lambda: self._freigabe(e, var.get())).pack(anchor="e")
        bb = ctk.CTkFrame(rechts, fg_color="transparent"); bb.pack(anchor="e", pady=(6, 0))
        self._knopf(bb, "Inhalt bearbeiten", lambda: self._ansehen(e))
        if e["art"] == "skill":
            self._knopf(bb, "Workflow öffnen", lambda: self._oeffnen(e["pfad"]))
            if e["aktiv"]: self._knopf(bb, "Als neuen Workflow …", lambda: self._vorlage(e))
        self._knopf(bb, "Entfernen", lambda: self._entfernen(e))

    def _knopf(self, parent, text, cmd):
        G = self.G
        ctk.CTkButton(parent, text=text, height=24, width=0, corner_radius=0, font=G.font(11), fg_color=G.BORDER,
                      hover_color=G.MUTED, text_color=G.INK, command=cmd).pack(anchor="e", pady=1, fill="x")

    # ------------------------------------------------------------------ Aktionen
    def _freigabe(self, e, an):
        if an and e.get("rechte"):
            if not messagebox.askyesno("Skills & Rollen", f"«{e['titel']}» verlangt diese Rechte:\n- "
                                       + "\n- ".join(SK.RECHTE[x] for x in e["rechte"]) + "\n\nFreigeben?", parent=self.win):
                self.fuellen(); return
        SK.freigeben(e["key"], an); self.fuellen()

    def _ansehen(self, e):
        G = self.G
        p = e["pfad"] if e["art"] == "rolle" else Path(e["pfad"]) / "anleitung.md"
        if not Path(p).is_file(): p = Path(e["pfad"]) / "skill.json"
        d = ctk.CTkToplevel(self.win); d.title(e["titel"]); d.geometry("760x640"); d.transient(self.win)
        alt = Path(p).read_text(encoding="utf-8", errors="replace")
        fuss = ctk.CTkFrame(d, fg_color="transparent"); fuss.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        tb = ctk.CTkTextbox(d, font=ctk.CTkFont(family="Consolas", size=12), wrap="word"); tb.pack(fill="both", expand=True, padx=10, pady=10)
        tb.insert("1.0", alt)
        def speichern():                                               # v172
            neu = tb.get("1.0", "end-1c")
            if neu == alt: d.destroy(); return
            war_aktiv = e["aktiv"]
            try: SK.speichern(p, neu)
            except Exception as ex: messagebox.showerror("Skills & Rollen", str(ex), parent=d); return
            if war_aktiv and messagebox.askyesno("Skills & Rollen", "Gespeichert. Die alte Fassung liegt im Ordner _versionen.\n\n"
                                                 "Du hast den Inhalt geändert, die Freigabe ist deshalb aufgehoben. Geänderte Fassung jetzt "
                                                 "freigeben? Sonst stoppen Workflows mit dieser Rolle.", parent=d):
                SK.freigeben(e["key"], True)
            d.destroy(); self.fuellen()
        ctk.CTkButton(fuss, text="Speichern", height=30, fg_color=G.ACCENT, hover_color=G.ACCENT_HI, font=G.font(12, "bold"),
                      command=speichern).pack(side="right")
        ctk.CTkButton(fuss, text="Abbrechen", height=30, fg_color=G.BORDER, hover_color=G.MUTED, text_color=G.INK, font=G.font(12),
                      command=d.destroy).pack(side="right", padx=6)

    def _oeffnen(self, pfad):
        self.schliessen(); self.app.open_workflows()
        w = getattr(self.app, "wfwin", None)
        try: w.show(str(Path(pfad) / "workflow.json"))
        except Exception: pass

    def _vorlage(self, e):
        d = ctk.CTkInputDialog(text=f"Name des neuen Workflows (Kopie von «{e['titel']}»):", title="Als neuen Workflow")
        titel = (d.get_input() or "").strip()
        if not titel: return
        try: ziel = SK.als_vorlage(e, titel)
        except Exception as ex: messagebox.showerror("Skills & Rollen", str(ex), parent=self.win); return
        self._oeffnen(ziel)

    def _entfernen(self, e):
        was = "Die Rolle kommt in den Ordner rollen\\_geloescht." if e["art"] == "rolle" else \
              "Der Workflow bleibt erhalten, er ist danach nur kein Skill mehr."
        if messagebox.askyesno("Skills & Rollen", f"«{e['titel']}» entfernen?\n\n{was}", parent=self.win):
            SK.entfernen(e); self.fuellen()

    def importieren(self):
        pfade = filedialog.askopenfilenames(parent=self.win, title="Markdown-Datei(en) wählen", filetypes=[("Markdown", "*.md")])
        if not pfade: return
        # Rollen zuerst, damit ein Skill seine Rolle («Arbeite nach ROLLE_….md») gleich findet
        pfade = sorted(pfade, key=lambda p: SK.art_raten(Path(p).read_text(encoding="utf-8", errors="replace"), p) != "rolle")
        meld = []
        for p in pfade:
            art = SK.art_raten(Path(p).read_text(encoding="utf-8", errors="replace"), p)
            frage = (f"«{Path(p).name}» als {'Rolle' if art == 'rolle' else 'Skill'} übernehmen?\n\n"
                     "Ja = so übernehmen · Nein = als " + ("Skill" if art == "rolle" else "Rolle") + " · Abbrechen = überspringen")
            a = messagebox.askyesnocancel("Importieren", frage, parent=self.win)
            if a is None: continue
            if a is False: art = "skill" if art == "rolle" else "rolle"
            try: _, ziel = SK.importieren(p, art); meld.append(f"✓ {Path(p).name} → {'Rolle' if art == 'rolle' else 'Skill'} ({Path(ziel).name})")
            except Exception as ex: meld.append(f"✕ {Path(p).name}: {ex}")
        self.fuellen()
        if meld:
            messagebox.showinfo("Importieren", "\n".join(meld) + "\n\nNeue Einträge sind aus, bis du sie freigibst. Ein importierter Skill "
                                "ist ein Rohbau: Schritte, Feldplan und Regeln richtest du im Workflow ein (Anleitung unter «Inhalt "
                                "bearbeiten»).", parent=self.win)

    # ------------------------------------------------------------------ v229: Neu erstellen (Formular, ohne Sprachmodell)
    FELDER = {"rolle": [("haltung", "Haltung", "Wie tritt die Rolle auf? Z.B. «Sachlicher Berater der Geschäftsleitung, kritisch, knapp.»", 3),
                        ("grundsaetze", "Arbeitsgrundsätze (eine pro Zeile)", "Zuerst die Kernaussage\nRisiken immer nennen", 5),
                        ("nicht", "Nicht tun (eine pro Zeile)", "Keine Vermutungen als Fakten\nKeine Füllsätze", 3)],
              "skill": [("aufgabe", "Aufgabe", "Was soll der Skill erreichen, für wen?", 3),
                        ("eingaben", "Eingaben (eine pro Zeile)", "Angebot als PDF\nCheckliste", 3),
                        ("schritte", "Schritte (einer pro Zeile)", "Dokument lesen\nKriterien prüfen\nBericht erstellen", 5),
                        ("ausgabe", "Ergebnis", "Z.B. Word-Bericht nach Vorlage, Tabelle mit Befunden", 2),
                        ("pruefen", "Prüfpunkte (einer pro Zeile)", "Jede Aussage mit Fundstelle", 3)]}

    def neu(self):
        G = self.G
        d = ctk.CTkToplevel(self.win); d.title("Neu: Rolle oder Skill"); d.geometry("720x760"); d.transient(self.win); d.grab_set()
        fuss = ctk.CTkFrame(d, fg_color="transparent"); fuss.pack(side="bottom", fill="x", padx=14, pady=(0, 12))
        art = tk.StringVar(value="Rolle")
        ctk.CTkSegmentedButton(d, values=["Rolle", "Skill"], variable=art, selected_color=G.ACCENT, selected_hover_color=G.ACCENT_HI,
                               command=lambda _: zeigen()).pack(anchor="w", padx=14, pady=(14, 6))
        sf = ctk.CTkScrollableFrame(d, fg_color="transparent"); sf.pack(fill="both", expand=True, padx=8)
        sf.grid_columnconfigure(0, weight=1)
        w = {}
        def feld(parent, key, label, hinweis, zeilen, r):
            ctk.CTkLabel(parent, text=label, font=G.font(11, "bold"), text_color=G.INK, anchor="w").grid(row=r, column=0, sticky="w", padx=6, pady=(8, 0))
            if zeilen == 1:
                e = ctk.CTkEntry(parent, placeholder_text=hinweis, height=28)
            else:
                e = ctk.CTkTextbox(parent, height=22 * zeilen + 8, font=G.font(12), border_width=1, wrap="word")
                e.insert("1.0", hinweis); e._hinweis = hinweis; e.configure(text_color=G.MUTED)
                def rein(_ev, e=e):
                    if e.get("1.0", "end-1c") == e._hinweis: e.delete("1.0", "end"); e.configure(text_color=G.INK)
                e.bind("<FocusIn>", rein)
            e.grid(row=r + 1, column=0, sticky="ew", padx=6); w[key] = e
        allg = ctk.CTkFrame(sf, fg_color="transparent"); allg.grid(row=0, column=0, sticky="ew"); allg.grid_columnconfigure(0, weight=1)
        for i, (k, l, h) in enumerate((("titel", "Titel *", "Z.B. Beschaffungsprüfer"), ("beschreibung", "Kurzbeschreibung", "Ein Satz: wofür?"),
                                       ("autor", "Autor", ""))):
            feld(allg, k, l, h, 1, 2 * i)
        boxen = {}
        for a, fl in self.FELDER.items():
            b = ctk.CTkFrame(sf, fg_color="transparent"); b.grid_columnconfigure(0, weight=1); boxen[a] = b
            for i, (k, l, h, z) in enumerate(fl): feld(b, k, l, h, z, 2 * i)
        sk = boxen["skill"]; r = 2 * len(self.FELDER["skill"])
        rollen = {x["titel"]: x["name"] for x in SK.rollen()}
        ctk.CTkLabel(sk, text="Rolle", font=G.font(11, "bold"), text_color=G.INK, anchor="w").grid(row=r, column=0, sticky="w", padx=6, pady=(8, 0))
        rolle = ctk.CTkOptionMenu(sk, values=["Keine"] + list(rollen), fg_color=G.CARD, button_color=G.CARD, text_color=G.INK)
        rolle.grid(row=r + 1, column=0, sticky="w", padx=6)
        ctk.CTkLabel(sk, text="Rechte (nur ankreuzen, was der Skill wirklich braucht)", font=G.font(11, "bold"), text_color=G.INK,
                     anchor="w").grid(row=r + 2, column=0, sticky="w", padx=6, pady=(8, 0))
        rv = {}
        for j, (k, t) in enumerate(SK.RECHTE.items()):
            rv[k] = tk.BooleanVar(value=False)
            ctk.CTkCheckBox(sk, text=t, variable=rv[k], font=G.font(11)).grid(row=r + 3 + j, column=0, sticky="w", padx=6, pady=1)
        vorschau = ctk.CTkTextbox(sf, height=180, font=ctk.CTkFont(family="Consolas", size=11), wrap="word", state="disabled")
        def wert(k):
            e = w[k]
            if isinstance(e, ctk.CTkTextbox):
                t = e.get("1.0", "end-1c"); return "" if t == getattr(e, "_hinweis", None) else t
            return e.get()
        def daten():
            a = "rolle" if art.get() == "Rolle" else "skill"
            f = {k: wert(k) for k in ("titel", "beschreibung", "autor")}
            f.update({k: wert(k) for k, *_ in self.FELDER[a]})
            if a == "skill":
                f["rolle"] = rollen.get(rolle.get(), ""); f["rechte"] = [k for k, v in rv.items() if v.get()]
            return a, f
        def zeigen():
            for a, b in boxen.items():
                if (a == "rolle") == (art.get() == "Rolle"): b.grid(row=1, column=0, sticky="ew")
                else: b.grid_remove()
            vorschau.grid_remove()
        def vorschau_zeigen():
            a, f = daten()
            vorschau.configure(state="normal"); vorschau.delete("1.0", "end")
            vorschau.insert("1.0", SK.md_bauen(a, dict(f, titel=f["titel"] or "(Titel)"))); vorschau.configure(state="disabled")
            vorschau.grid(row=2, column=0, sticky="ew", padx=6, pady=(10, 0))
        def anlegen():
            a, f = daten()
            try: ziel = SK.neu_erstellen(a, f)
            except Exception as ex: messagebox.showerror("Skills & Rollen", str(ex), parent=d); return
            d.destroy(); self.fuellen()
            messagebox.showinfo("Skills & Rollen", f"{'Rolle' if a == 'rolle' else 'Skill'} «{f['titel']}» erstellt ({Path(ziel).name}).\n\n"
                                "Sie ist aus, bis du sie freigibst." + ("" if a == "rolle" else " Der Skill ist ein Rohbau: Schritte "
                                "richtest du im Workflow ein («Workflow öffnen»)."), parent=self.win)
        ctk.CTkButton(fuss, text="Erstellen", height=30, fg_color=G.ACCENT, hover_color=G.ACCENT_HI, font=G.font(12, "bold"),
                      command=anlegen).pack(side="right")
        ctk.CTkButton(fuss, text="Vorschau", height=30, fg_color=G.BORDER, hover_color=G.MUTED, text_color=G.INK, font=G.font(12),
                      command=vorschau_zeigen).pack(side="right", padx=6)
        ctk.CTkButton(fuss, text="Abbrechen", height=30, fg_color=G.BORDER, hover_color=G.MUTED, text_color=G.INK, font=G.font(12),
                      command=d.destroy).pack(side="left")
        zeigen(); w["titel"].focus_set()
