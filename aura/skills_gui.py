# aura/skills_gui.py — Fenster «Skills & Rollen» (Workflows › Skills & Rollen). Version 20261031v146
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
        ctk.CTkButton(hd, text="Markdown importieren …", height=30, fg_color=G.ACCENT, hover_color=G.ACCENT_HI,
                      font=G.font(12, "bold"), command=self.importieren).pack(side="right")
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
                ctk.CTkLabel(self.lst, text="Noch keine. «Markdown importieren …» übernimmt eine Datei wie "
                             + ("AUFGABE_….md." if art == "skill" else "ROLLE_….md."), font=G.font(11), text_color=G.MUTED,
                             anchor="w").grid(row=r, column=0, sticky="w"); r += 1
            for e in teil: self._karte(e, r); r += 1

    def _karte(self, e, r):
        G = self.G
        k = ctk.CTkFrame(self.lst, fg_color=G.BUBBLE, corner_radius=8, border_width=1,
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
        self._knopf(bb, "Inhalt ansehen", lambda: self._ansehen(e))
        if e["art"] == "skill":
            self._knopf(bb, "Workflow öffnen", lambda: self._oeffnen(e["pfad"]))
            if e["aktiv"]: self._knopf(bb, "Als neuen Workflow …", lambda: self._vorlage(e))
        self._knopf(bb, "Entfernen", lambda: self._entfernen(e))

    def _knopf(self, parent, text, cmd):
        G = self.G
        ctk.CTkButton(parent, text=text, height=24, width=0, corner_radius=6, font=G.font(11), fg_color=G.BORDER,
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
        tb = ctk.CTkTextbox(d, font=ctk.CTkFont(family="Consolas", size=12), wrap="word"); tb.pack(fill="both", expand=True, padx=10, pady=10)
        tb.insert("1.0", Path(p).read_text(encoding="utf-8", errors="replace")); tb.configure(state="disabled")

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
                                "ansehen»).", parent=self.win)
