# aura/workflow_gui.py — Ansicht «Workflows»: Pakete anlegen, ausfuehren, Wissen und Vorlagen pflegen. Version 20261030v133
# (v133: Regler auch bei Sprachmodell-Schritten innerhalb anderer Schritte, z.B. «Je Thema zusammenfassen»)
# (v132: Regler «Ausführlichkeit» im Reiter «Ausführen» – knapp / normal / ausführlich, gespeichert in der workflow.json)
# (v93: Start gesperrt, wenn ein Schritt eine fehlende Eingabe liest; Rückfrage bei Datei-Eingaben, die kein Schritt liest)
# (v92: Schalter «Expertenansicht» fest rechts ausserhalb der Knopfleiste, «Löschen» zuletzt, Neuaufbau verzögert –
#  vorher lag nach dem Umschalten «Löschen» unter dem Mauszeiger und wurde beim Loslassen ausgelöst)
# (v90: Reiter «Übersicht» mit drei Bereichen (zonen_gui.py) als Standard; Schalter «Expertenansicht» blendet Ablauf, Schritte,
#  Prüfliste, Vorlage und «workflow.json bearbeiten» ein; ein Sprung auf einen ausgeblendeten Reiter schaltet sie selbst ein)
# (v81: Knopf heisst «☆ Als Widget»)
# (v80: «☆ Auf Startseite» (Widget), Reiter «Ablauf» mit Ablaufband aus dashboard.py)
# (v78: «Exportieren …» / «Importieren …» – Übergabe als .aurawf.zip, austausch.py)
# (v64a: Knopf «Feldplan …» im Reiter «Vorlage»)
# (v53: «Workflow beschreiben», Meldungen, allgemeine Prüfregeln; v52: Reiter «Schritte» (workflow_editor.py); v51: Vorlage entfernen, Herkunft der Prüfpunkte; v50: Reiter «Prüfliste» – Prüfpunkte ohne JSON anlegen; v38: Infotexte, v40: Prüfhinweise nach dem Lauf, v46: Vollansicht im Hauptfenster statt eigenem Fenster)
# Ausfuehren laeuft im Worker (job workflow); Ereignisse wf_step / wf_done / progress kommen ueber App._poll hierher.
import json, os, tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk
from .wissen import WF_DIR
from .workflow import list_workflows, load_workflow, latest_state
from .workflow import paket
from . import hilfe

def _open(p):
    if hasattr(os, "startfile"):
        try: os.startfile(str(p))
        except Exception as e: messagebox.showerror("AURA", f"Öffnen fehlgeschlagen: {e}")

class WorkflowWindow:
    def __init__(self, app):
        from . import gui as G
        self.G, self.app = G, app
        self.cur, self.wf, self.inputs, self.step_lbl, self.running = None, None, {}, {}, False
        win = self.win = app.view("workflows", "Workflows")          # v46: Rahmen im Hauptfenster
        win.grid_columnconfigure(1, weight=1); win.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(win, fg_color=G.CARD, corner_radius=0, width=250); left.grid(row=0, column=0, sticky="nsw")
        left.grid_propagate(False); left.grid_columnconfigure(0, weight=1); left.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(left, text="WORKFLOWS", font=G.font(10, "bold"), text_color=G.MUTED, anchor="w").grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 6))
        self.lst = ctk.CTkScrollableFrame(left, fg_color="transparent"); self.lst.grid(row=1, column=0, sticky="nsew", padx=6)
        self.lst.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(left, text="+ Neuer Workflow", height=32, corner_radius=8, font=G.font(12, "bold"), fg_color=G.ACCENT,
                      hover_color=G.ACCENT_HI, command=self.new).grid(row=2, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkButton(left, text="Gemeinsame Sammlungen …", height=28, corner_radius=8, font=G.font(11), fg_color=G.BORDER,
                      hover_color=G.MUTED, text_color=G.INK, command=self.app.open_wissen).grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 4))
        ctk.CTkButton(left, text="Importieren …", height=28, corner_radius=8, font=G.font(11), fg_color=G.BORDER,
                      hover_color=G.MUTED, text_color=G.INK, command=self.importieren).grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))
        hilfe.auto(left, "workflow")
        self.right = ctk.CTkFrame(win, fg_color="transparent"); self.right.grid(row=0, column=1, sticky="nsew", padx=18, pady=12)
        self.right.grid_columnconfigure(0, weight=1); self.right.grid_rowconfigure(1, weight=1)
        self.refresh_list()
        first = next(iter(self.items), None)
        if first: self.show(first["path"])

    def alive(self): return self.win is not None and self.win.winfo_exists()
    def close(self): self.app.show_chat()          # v46: Ansicht bleibt im Hintergrund offen, ein Lauf läuft weiter

    # ------------------------------------------------------------------ Liste
    def refresh_list(self):
        G = self.G
        for c in self.lst.winfo_children(): c.destroy()
        WF_DIR.mkdir(exist_ok=True)
        self.items = list_workflows(WF_DIR)
        for i, it in enumerate(self.items):
            pkg = it["path"].endswith("workflow.json"); sel = it["path"] == self.cur
            ctk.CTkButton(self.lst, text=it["name"] + ("" if pkg else "  (Einzeldatei)"), anchor="w", height=30, corner_radius=8,
                          font=G.font(12, "bold" if sel else "normal"), fg_color=G.ACCENT if sel else "transparent",
                          hover_color=G.BORDER, text_color="white" if sel else (G.INK if not it["error"] else G.ERR),
                          command=lambda p=it["path"]: self.show(p)).grid(row=i, column=0, sticky="ew", pady=1)

    def new(self):
        """v56: direkt «Workflow beschreiben»; «selbst zusammenstellen» unten im Fenster."""
        from .assistent_gui import Assistent
        self.assistent = Assistent(self, neu=True)

    def new_leer(self):
        t = ctk.CTkInputDialog(text="Name des neuen Workflows:", title="Neuer Workflow").get_input()
        if not t: return
        try: d = paket.create(t)
        except Exception as e: messagebox.showerror("Workflows", str(e), parent=self.win); return
        self.refresh_list(); self.show(str(d / "workflow.json"))

    # ------------------------------------------------------------------ Details
    def show(self, path):
        G = self.G
        if self.running: messagebox.showinfo("Workflows", "Während eines Laufs bitte nicht wechseln.", parent=self.win); return
        for c in self.right.winfo_children(): c.destroy()
        self.cur = path; self.refresh_list()
        try: self.wf = load_workflow(path); err = None
        except Exception as e: self.wf, err = None, str(e)
        hd = ctk.CTkFrame(self.right, fg_color="transparent"); hd.grid(row=0, column=0, sticky="ew"); hd.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hd, text=(self.wf or {}).get("name", Path(path).stem), font=G.font(18, "bold"), text_color=G.INK, anchor="w",
                     justify="left", wraplength=700).grid(row=0, column=0, sticky="w")
        bar = ctk.CTkFrame(hd, fg_color="transparent"); bar.grid(row=1, column=0, sticky="w", pady=(4, 0))   # v48: Knoepfe unter dem Titel
        b = lambda t, c: ctk.CTkButton(bar, text=t, height=28, width=0, corner_radius=8, font=G.font(11), fg_color=G.CARD,
                                       hover_color=G.BORDER, text_color=G.INK, command=c).pack(side="left", padx=(0, 6))
        pkg = path.endswith("workflow.json")
        self.experte = bool(self.app.s.get("wf_experte"))                   # v90
        b("Neu laden", lambda: self.show(path))
        if pkg:
            b("Ordner öffnen", lambda: _open(Path(path).parent)); b("Exportieren …", self.exportieren)
            from .dashboard import ist_angeheftet                        # v80
            pin = ist_angeheftet(self.app, path)
            ctk.CTkButton(bar, text="★ Als Widget" if pin else "☆ Als Widget", height=28, width=0, corner_radius=8,
                          font=G.font(11, "bold"), fg_color=G.ACCENT if pin else G.CARD, hover_color=G.ACCENT_HI if pin else G.BORDER,
                          text_color="white" if pin else G.INK, command=self.pin_toggle).pack(side="left", padx=(0, 6))
        else: b("In Paket umwandeln", self.migrate)
        if self.experte: b("workflow.json bearbeiten", lambda: _open(path))      # v92: hinten, verschiebt nichts davor
        if pkg: b("Löschen", self.delete)                                      # v92: zuletzt
        self.sw_exp = ctk.CTkSwitch(hd, text="Expertenansicht", font=G.font(11), command=self._experte_umschalten)   # v92: fester Platz
        (self.sw_exp.select() if self.experte else self.sw_exp.deselect()); self.sw_exp.grid(row=0, column=1, sticky="ne", padx=(8, 0))
        if self.wf and self.wf.get("description"):
            ctk.CTkLabel(hd, text=self.wf["description"], font=G.font(11), text_color=G.MUTED, anchor="w", justify="left",
                         wraplength=700).grid(row=2, column=0, sticky="w", pady=(4, 0))
        if err:
            ctk.CTkLabel(self.right, text=f"Workflow fehlerhaft:\n{err}", font=G.font(12), text_color=G.ERR, justify="left",
                         anchor="nw").grid(row=1, column=0, sticky="nw", pady=20); hilfe.auto(self.right, "workflow"); return
        tabs = self.tabs = ctk.CTkTabview(self.right, fg_color=G.CARD, segmented_button_selected_color=G.ACCENT)
        tabs.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self._tabnamen = []; _set = tabs.set                                 # v90: nur angezeigte Reiter; Rest = Expertenansicht
        def add(n): self._tabnamen.append(n); return tabs.add(n)
        def sicher(n):
            if n in self._tabnamen: _set(n)
            else: self._experte_an(n)
        tabs.set = sicher
        try:                                                             # v90: drei Bereiche
            from .zonen_gui import ZonenAnsicht
            self.zonen = ZonenAnsicht(self, add("Übersicht"))
        except Exception as e:
            ctk.CTkLabel(tabs.tab("Übersicht"), text=f"Übersicht nicht verfügbar: {e}", text_color=G.ERR).pack(anchor="w")
        self._tab_run(add("Ausführen"))
        self.band = None
        if self.experte:
            try:                                                         # v80: Ablaufband
                from .dashboard import FlowBand
                t = add("Ablauf"); t.grid_columnconfigure(0, weight=1)
                self.band = FlowBand(self.app, t, path); self.band.frame.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
            except Exception as e:
                self.band = None; ctk.CTkLabel(tabs.tab("Ablauf"), text=f"Ablauf nicht verfügbar: {e}", text_color=G.ERR).pack(anchor="w")
            try:                                                         # v52: Schritte ohne JSON
                from .workflow_editor import SchrittEditor
                self.editor = SchrittEditor(self, add("Schritte"))
            except Exception as e:
                ctk.CTkLabel(tabs.tab("Schritte"), text=f"Schritt-Editor nicht verfügbar: {e}", text_color=G.ERR).pack(anchor="w")
            if pkg: self._tab_pruefliste(add("Prüfliste"))               # v50
        if pkg: self._tab_wissen(add("Wissen"))
        if self.experte: self._tab_vorlage(add("Vorlage"))
        _set("Übersicht")
        hilfe.SCHRITTE.setdefault("pruefliste", "Prüft die Eingabedateien gegen die Punkte im Reiter «Prüfliste».")
        hilfe.auto(self.right, "workflow")              # Wissen-Reiter hat seine Texte schon (Kontext «wissen»)

    # ------------------------------------------------------------------ Reiter Ausfuehren
    def _tab_run(self, t):
        G = self.G; t.grid_columnconfigure(0, weight=1); t.grid_columnconfigure(1, weight=1); t.grid_rowconfigure(0, weight=1)
        lf = ctk.CTkFrame(t, fg_color="transparent"); lf.grid(row=0, column=0, sticky="nsew", padx=(4, 12))
        lf.grid_columnconfigure(0, weight=1); r = 0; self.inputs = {}
        ctk.CTkLabel(lf, text="EINGABEN", font=G.font(10, "bold"), text_color=G.MUTED, anchor="w").grid(row=r, column=0, sticky="w"); r += 1
        for inp in self.wf["inputs"]:
            itip = inp.get("hilfe") or hilfe.TEXTE["*"]["#wf_input_" + ("files" if inp["type"] == "files" else "text")]
            hilfe.tip(ctk.CTkLabel(lf, text=inp.get("label", inp["id"]) + ("" if inp.get("optional") else " *"), font=G.font(12),
                                   text_color=G.INK, anchor="w"), itip).grid(row=r, column=0, sticky="w", pady=(8, 2)); r += 1
            if inp["type"] == "files":
                box = ctk.CTkTextbox(lf, height=70, font=G.font(11), border_width=1, border_color=G.BORDER, wrap="none")
                box.grid(row=r, column=0, sticky="ew"); box.configure(state="disabled"); r += 1; hilfe.tip(box, itip)
                self.inputs[inp["id"]] = {"type": "files", "files": [], "box": box}
                ctk.CTkButton(lf, text="Dateien wählen …", height=26, width=140, corner_radius=7, font=G.font(11), fg_color=G.BORDER,
                              hover_color=G.MUTED, text_color=G.INK, command=lambda i=inp: self.pick(i)).grid(row=r, column=0, sticky="w", pady=(4, 0)); r += 1
            else:
                e = ctk.CTkTextbox(lf, height=48, font=G.font(12), border_width=1, border_color=G.BORDER, wrap="word")
                e.grid(row=r, column=0, sticky="ew"); r += 1; hilfe.tip(e, itip)
                self.inputs[inp["id"]] = {"type": "text", "entry": e}
        if self._ausf_wirkt():                                         # v132
            af = ctk.CTkFrame(lf, fg_color="transparent"); af.grid(row=r, column=0, sticky="ew", pady=(14, 0)); r += 1
            ctk.CTkLabel(af, text="Ausführlichkeit", font=G.font(12), text_color=G.INK).pack(side="left", padx=(0, 10))
            werte = {"knapp": "knapp", "normal": "normal", "ausfuehrlich": "ausführlich"}
            self.seg_ausf = ctk.CTkSegmentedButton(af, values=list(werte.values()), font=G.font(11),
                                                   selected_color=G.ACCENT, command=self._ausf_setzen)
            self.seg_ausf.set(werte.get(str(self.wf.get("ausfuehrlichkeit") or self._raw().get("ausfuehrlichkeit") or "normal"), "normal"))
            self.seg_ausf.pack(side="left"); hilfe.tip(self.seg_ausf, "#wf_ausf")
        bb = ctk.CTkFrame(lf, fg_color="transparent"); bb.grid(row=r, column=0, sticky="ew", pady=(14, 0)); r += 1
        self.b_start = ctk.CTkButton(bb, text="▶  Starten", height=34, corner_radius=8, font=G.font(13, "bold"), fg_color=G.ACCENT,
                                     hover_color=G.ACCENT_HI, command=self.start); self.b_start.pack(side="left")
        ctk.CTkButton(bb, text="Abbrechen", height=34, width=90, corner_radius=8, font=G.font(12), fg_color=G.CARD,
                      hover_color=G.BORDER, text_color=G.INK, command=self.app.w.cancel.set).pack(side="left", padx=8)
        rs = ctk.CTkFrame(lf, fg_color="transparent"); rs.grid(row=r, column=0, sticky="ew", pady=(10, 0)); r += 1
        ids = [s["id"] for s in self.wf["steps"]]
        self.o_ab = ctk.CTkOptionMenu(rs, values=ids, width=130, height=28, font=G.font(11), fg_color=G.BUBBLE, button_color=G.BORDER,
                                      text_color=G.INK); self.o_ab.set(ids[-1]); self.o_ab.pack(side="left"); hilfe.tip(self.o_ab, "#wf_ab")
        ctk.CTkButton(rs, text="Ab Schritt neu (letzter Lauf)", height=28, corner_radius=8, font=G.font(11), fg_color=G.BORDER,
                      hover_color=G.MUTED, text_color=G.INK, command=self.restart).pack(side="left", padx=6)
        ctk.CTkLabel(lf, text="* = Pflichteingabe. Ein Lauf dauert je nach Modell 10–25 Minuten. Notebook nicht zuklappen – "
                              "Standby unterbricht den Lauf. «← Zurück» lässt den Lauf im Hintergrund weiterlaufen.",
                     font=G.font(11), text_color=G.MUTED, anchor="w", justify="left",
                     wraplength=380).grid(row=r, column=0, sticky="w", pady=(12, 0)); r += 1
        # rechts: Schritte, Status, Ergebnis
        rf = ctk.CTkFrame(t, fg_color="transparent"); rf.grid(row=0, column=1, sticky="nsew"); rf.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(rf, text="SCHRITTE", font=G.font(10, "bold"), text_color=G.MUTED, anchor="w").grid(row=0, column=0, sticky="w")
        sf = ctk.CTkFrame(rf, fg_color=G.BUBBLE, corner_radius=8); sf.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        self.step_lbl = {}
        for i, s in enumerate(self.wf["steps"]):
            l = ctk.CTkLabel(sf, text=f"○  {i + 1}. {s.get('label', s['id'])}  ({s['type']})", font=G.font(12), text_color=G.MUTED, anchor="w",
                             justify="left", wraplength=240)                    # v48: lange Schrittnamen umbrechen
            from .workflow.schema import BAUSTEINE as _B
            hilfe.tip(l, s.get("hilfe") or hilfe.SCHRITTE.get(s["type"]) or _B.get(s["type"], {}).get("beschreibung", ""))
            l.pack(anchor="w", padx=10, pady=1); self.step_lbl[s["id"]] = (l, f"{i + 1}. {s.get('label', s['id'])}  ({s['type']})")
        self.lbl_prog = ctk.CTkLabel(rf, text="", font=G.font(11), text_color=G.MUTED, anchor="w", justify="left", wraplength=260)
        self.lbl_prog.grid(row=2, column=0, sticky="ew")
        self.res = ctk.CTkFrame(rf, fg_color="transparent"); self.res.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        last = latest_state(self.app_runs_dir(), self.wf)
        if last: ctk.CTkLabel(self.res, text=f"Letzter Lauf: {last.parent.name if self.wf.get('_dir') else last.name}",
                              font=G.font(11), text_color=G.MUTED).pack(anchor="w")

    def _ausf_wirkt(self):
        """v132: Regler nur zeigen, wenn ein Sprachmodell-Schritt frei schreibt oder ein Feld «ausfuehrlich_ok» hat."""
        def llm_schritte(o):                                           # v133: auch verschachtelt (z.B. in «fuer_jedes»)
            if isinstance(o, dict):
                if o.get("type") == "llm": yield o
                for v in o.values(): yield from llm_schritte(v)
            elif isinstance(o, list):
                for v in o: yield from llm_schritte(v)
        for s in llm_schritte((self.wf or {}).get("steps", [])):
            fs = s.get("fields")
            if not fs and s.get("ausfuehrlich_ok", True): return True
            if any(isinstance(f, dict) and f.get("ausfuehrlich_ok") for f in fs or []): return True
        return False

    def _ausf_setzen(self, v):
        if self.running:
            messagebox.showinfo("Workflows", "Während eines Laufs nicht ändern – gilt ab dem nächsten Lauf.", parent=self.win)
        wert = {"knapp": "knapp", "normal": "normal", "ausführlich": "ausfuehrlich"}.get(v, "normal")
        try:
            raw = self._raw()
            if wert == "normal": raw.pop("ausfuehrlichkeit", None)
            else: raw["ausfuehrlichkeit"] = wert
            tmp = Path(self.cur).with_suffix(".tmp")
            tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(self.cur)
            if isinstance(self.wf, dict):
                if wert == "normal": self.wf.pop("ausfuehrlichkeit", None)
                else: self.wf["ausfuehrlichkeit"] = wert
        except Exception as e: messagebox.showerror("Workflows", f"Nicht gespeichert: {e}", parent=self.win)

    def app_runs_dir(self):
        from .workflow.app import RUNS_DIR
        return RUNS_DIR

    def pick(self, inp):
        exts = " ".join("*" + e for e in inp.get("ext", [".pdf", ".docx", ".txt", ".md"]))
        fs = filedialog.askopenfilenames(parent=self.win, title=inp.get("label", "Dateien wählen"),
                                         filetypes=[("Dokumente", exts), ("Alle Dateien", "*.*")])
        if not fs: return
        d = self.inputs[inp["id"]]; d["files"] = list(fs); box = d["box"]
        box.configure(state="normal"); box.delete("1.0", "end"); box.insert("1.0", "\n".join(Path(f).name for f in fs))
        box.configure(state="disabled")

    def collect(self):
        out = {}
        for k, d in self.inputs.items():
            out[k] = d["files"] if d["type"] == "files" else d["entry"].get("1.0", "end").strip()
        return out

    def _reset_steps(self):
        for sid, (l, txt) in self.step_lbl.items(): l.configure(text=f"○  {txt}", text_color=self.G.MUTED)
        for c in self.res.winfo_children(): c.destroy()

    def start(self, start_at=None, stop_after=None):
        if self.running: return
        if stop_after is None: stop_after = getattr(self, "pending_stop", None)
        inputs = {} if start_at else self.collect()
        if not start_at:
            miss = [i.get("label", i["id"]) for i in self.wf["inputs"] if not i.get("optional") and not inputs.get(i["id"])]
            if miss: messagebox.showwarning("Workflows", "Bitte ausfüllen:\n- " + "\n- ".join(miss), parent=self.win); return
            from .workflow.zonen import verweise                               # v93
            fehlend, ungelesen = verweise(self.wf)
            if fehlend:
                messagebox.showerror("Workflows", "Nicht gestartet: Ein Schritt liest eine Eingabe, die es nicht mehr gibt ("
                                     + ", ".join(fehlend) + "). Das Sprachmodell bekäme keine Unterlagen.\n\nIm Reiter «Übersicht» "
                                     "bei «① Was kommt rein?» → «Reparieren …».", parent=self.win); self.tabs.set("Übersicht"); return
            leer = [i.get("label", i["id"]) for i in self.wf["inputs"] if i["id"] in ungelesen and inputs.get(i["id"])]
            if leer and not messagebox.askyesno("Workflows", "Diese Dateien liest kein Schritt – sie werden nicht verwendet:\n- "
                                                + "\n- ".join(leer) + "\n\nTrotzdem starten?", default="no", parent=self.win): return
        self._reset_steps(); self.running = True; self.b_start.configure(state="disabled")
        self.lbl_prog.configure(text="Gestartet …" + (" (wartet, bis der laufende Auftrag fertig ist)" if self.app.busy else ""))
        self.pending_stop = None
        self.app.w.submit("workflow", self.cur, inputs, None, start_at, stop_after)

    def restart(self):
        if not latest_state(self.app_runs_dir(), self.wf):
            messagebox.showinfo("Workflows", "Noch kein gespeicherter Lauf.", parent=self.win); return
        self.start(self.o_ab.get())

    # ---- Ereignisse aus dem Worker
    def on_step(self, i, n, sid, status):
        if not self.alive() or sid not in self.step_lbl: return
        l, txt = self.step_lbl[sid]
        sym, col = ("▶", self.G.ACCENT) if status == "läuft" else ("–", self.G.MUTED) if status == "übersprungen" else ("✓", self.G.OK)
        l.configure(text=f"{sym}  {txt}   {'' if status == 'läuft' else status}", text_color=col)

    # ---- v90: Expertenansicht
    def _set_experte(self, an):
        from .config import load_settings, save_settings
        st = load_settings(); st["wf_experte"] = bool(an); save_settings(st); self.app.s["wf_experte"] = bool(an); self.experte = bool(an)

    def _experte_umschalten(self):
        if self.running:
            messagebox.showinfo("Workflows", "Während eines Laufs bitte nicht umschalten.", parent=self.win)
            (self.sw_exp.select() if self.experte else self.sw_exp.deselect()); return
        self._set_experte(not self.experte)
        self.win.after(150, lambda: self.show(self.cur))                       # v92: erst nach dem Loslassen der Maus neu aufbauen

    def _experte_an(self, ziel=None):
        """Sprung auf einen Reiter der Expertenansicht (z.B. aus dem Feldplan oder «Schritte im Detail …»)."""
        if self.running: messagebox.showinfo("Workflows", "Während eines Laufs bitte nicht wechseln.", parent=self.win); return
        self._set_experte(True); self.show(self.cur)
        if ziel in self._tabnamen: self.tabs.set(ziel)

    def pin_toggle(self):
        """v80: Workflow als Widget auf der Startseite anheften / entfernen."""
        from .dashboard import ist_angeheftet, anheften, hat_anzeige
        an = not ist_angeheftet(self.app, self.cur)
        if an and not hat_anzeige(self.wf):
            if not messagebox.askyesno("Widget", "Dieser Workflow hat keine Ausgabe «Anzeige in AURA» – das Widget bliebe leer.\n\n"
                                       "Trotzdem anheften? (Ausgabe im Reiter «Schritte» ergänzen)", parent=self.win): return
        anheften(self.app, self.cur, an); self.show(self.cur)
        try: self.app._welcome_erg()
        except Exception: pass

    def on_progress(self, text):
        if self.alive() and self.running: self.lbl_prog.configure(text=text)

    def on_plan(self, r):
        a = getattr(self, "assistent", None)
        if a is not None:
            try: a.on_plan(r)
            except Exception: pass

    def on_done(self, res):
        if not self.alive(): return
        G = self.G; self.running = False; self.b_start.configure(state="normal")
        b = getattr(self, "band", None)                                  # v80
        if b is not None and b.alive(): b.draw()
        ok = res.get("status") == "ok"
        self.lbl_prog.configure(text=f"{'Fertig' if ok else res.get('status', '').capitalize()} nach {res.get('seconds', 0):.0f} s"
                                + (f"\n{res['error']}" if res.get("error") else ""), text_color=G.OK if ok else G.ERR)
        if res.get("error"):
            for sid, (l, txt) in self.step_lbl.items():
                if l.cget("text").startswith("▶"): l.configure(text=f"✕  {txt}", text_color=G.ERR)
        for m in res.get("meldungen") or []:                            # v53: Meldungen der Schritte
            box = ctk.CTkFrame(self.res, fg_color=G.BUBBLE, corner_radius=8); box.pack(fill="x", anchor="w", pady=(0, 6))
            ctk.CTkLabel(box, text=m.get("titel") or "Meldung", font=G.font(11, "bold"), anchor="w").pack(anchor="w", padx=10, pady=(6, 0))
            ctk.CTkLabel(box, text=(m.get("text") or "")[:3000], font=G.font(11), anchor="w", justify="left",
                         wraplength=520).pack(anchor="w", padx=10, pady=(0, 6))
        pr = res.get("pruefungen") or []
        if pr:                                                          # v40: Pruefhinweise (Warnungen + Plausibilitaet)
            box = ctk.CTkFrame(self.res, fg_color=("#FEF3C7", "#3A2F12"), corner_radius=8); box.pack(fill="x", anchor="w", pady=(0, 6))
            ctk.CTkLabel(box, text=f"⚠ {len(pr)} Prüfhinweis{'e' if len(pr) > 1 else ''} – Ergebnis gezielt prüfen", font=G.font(11, "bold"),
                         text_color=("#92400E", "#FCD34D"), anchor="w").pack(anchor="w", padx=10, pady=(6, 2))
            for m in pr[:12]:
                ctk.CTkLabel(box, text="• " + m, font=G.font(11), text_color=G.INK, anchor="w", justify="left",
                             wraplength=500).pack(anchor="w", padx=10)
            if len(pr) > 12: ctk.CTkLabel(box, text=f"… und {len(pr) - 12} weitere (protokoll.json)", font=G.font(10),
                                          text_color=G.MUTED).pack(anchor="w", padx=10)
            ctk.CTkFrame(box, height=6, fg_color="transparent").pack()
        for f in res.get("files") or []:
            ctk.CTkButton(self.res, text=f"Öffnen: {Path(f).name}", height=28, corner_radius=8, font=G.font(11, "bold"), fg_color=G.ACCENT,
                          hover_color=G.ACCENT_HI, command=lambda f=f: _open(f)).pack(anchor="w", pady=2)
        if res.get("zwischenstand"):
            ctk.CTkButton(self.res, text="Laufordner öffnen", height=26, corner_radius=8, font=G.font(11), fg_color=G.BORDER,
                          hover_color=G.MUTED, text_color=G.INK, command=lambda: _open(Path(res["zwischenstand"]).parent)).pack(anchor="w", pady=2)
        hilfe.auto(self.res, "workflow")

    # ------------------------------------------------------------------ Reiter Wissen
    def _tab_wissen(self, t):
        from .wissen_gui import WissenPanel
        t.grid_columnconfigure(0, weight=1); t.grid_rowconfigure(0, weight=1)
        f = ctk.CTkFrame(t, fg_color="transparent"); f.grid(row=0, column=0, sticky="nsew")
        self.wpanel = WissenPanel(self.app, f, f"wf:{Path(self.cur).parent.name}")
        shared = [k["sammlung"] for k in self.wf.get("knowledge", []) if not k["sammlung"].startswith("wf:")]
        if shared:
            ctk.CTkLabel(t, text="Zusätzlich eingebunden (gemeinsam): " + ", ".join(shared), font=self.G.font(11),
                         text_color=self.G.MUTED, anchor="w").grid(row=1, column=0, sticky="w", pady=(6, 0))

    # ------------------------------------------------------------------ Reiter Vorlage
    def _tab_vorlage(self, t):
        G = self.G; t.grid_columnconfigure(0, weight=1); t.grid_rowconfigure(2, weight=1)
        top = ctk.CTkFrame(t, fg_color="transparent"); top.grid(row=0, column=0, sticky="ew")
        steps = [s for s in self.wf["steps"] if s["type"] == "word_vorlage"]
        self.vsteps = {s["vorlage"]: s for s in steps if isinstance(s.get("vorlage"), str)}
        vdir = Path(self.cur).parent / "vorlagen"
        files = sorted({*(self.vsteps.keys()), *(f"vorlagen/{p.name}" for p in vdir.glob("*.docx"))}) if vdir.exists() else list(self.vsteps)
        self.o_v = ctk.CTkOptionMenu(top, values=files or ["(keine Vorlage)"], width=380, height=28, font=G.font(11), fg_color=G.BUBBLE,
                                     button_color=G.BORDER, text_color=G.INK, command=lambda v: self.fill_table())
        self.o_v.set(files[0] if files else "(keine Vorlage)"); self.o_v.pack(side="left")
        if self.cur.endswith("workflow.json"):
            ctk.CTkButton(top, text="+ Vorlage hinzufügen …", height=28, corner_radius=8, font=G.font(11), fg_color=G.BORDER,
                          hover_color=G.MUTED, text_color=G.INK, command=self.add_template).pack(side="left", padx=8)
            ctk.CTkButton(top, text="Vorlage entfernen", height=28, corner_radius=8, font=G.font(11), fg_color=G.BORDER,
                          hover_color=G.MUTED, text_color=G.INK, command=self.del_template).pack(side="left")
            ctk.CTkButton(top, text="Feldplan …", height=28, corner_radius=8, font=G.font(11, "bold"), fg_color=G.ACCENT,
                          hover_color=G.ACCENT_HI, command=self.feldplan).pack(side="left", padx=8)      # v64a
        self.lbl_v = ctk.CTkLabel(t, text="", font=G.font(11), text_color=G.MUTED, anchor="w", justify="left")
        self.lbl_v.grid(row=1, column=0, sticky="ew", pady=(6, 4))
        fr = tk.Frame(t); fr.grid(row=2, column=0, sticky="nsew"); fr.grid_columnconfigure(0, weight=1); fr.grid_rowconfigure(0, weight=1)
        cols = ("nr", "typ", "feld", "zuordnung", "wert")
        tv = self.tv = ttk.Treeview(fr, columns=cols, show="headings")
        for c, w, h in zip(cols, (45, 110, 330, 330, 330), ("Nr", "Typ", "Feld in der Vorlage", "Zuordnung (Ausdruck)", "Wert im letzten Lauf")):
            tv.heading(c, text=h, anchor="w"); tv.column(c, width=w, anchor="w", stretch=c in ("feld", "zuordnung", "wert"))
        tv.tag_configure("leer", foreground="#9AA3AF"); tv.tag_configure("fehler", foreground="#E5484D"); tv.tag_configure("an", foreground="#22C55E")
        sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=sb.set)
        tv.grid(row=0, column=0, sticky="nsew"); sb.grid(row=0, column=1, sticky="ns"); hilfe.tip(tv, "#wf_vorlage_tabelle")
        ctk.CTkLabel(t, text="Nur nötig, wenn AURA ein Word-Dokument AUSFÜLLEN soll (wie beim Verfahrensentscheid). "
                             "Soll AURA ein Dokument PRÜFEN, gehört das zu prüfende Dokument in «Ausführen» und der Massstab "
                             "(Richtlinien, leere Vorlage) in «Wissen»; die Prüfpunkte stehen im Reiter «Prüfliste».",
                     font=G.font(11), text_color=G.MUTED, anchor="w", justify="left", wraplength=900).grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.fill_table()

    def add_template(self):
        f = filedialog.askopenfilename(parent=self.win, title="Word-Vorlage wählen", filetypes=[("Word", "*.docx")])
        if not f: return
        t = paket.add_template(Path(self.cur).parent, f)
        messagebox.showinfo("Workflows", f"Vorlage abgelegt: vorlagen\\{t.name}\n\nIm Workflow einen Schritt «word_vorlage» mit "
                            f"\"vorlage\": \"vorlagen/{t.name}\" anlegen; die Feldliste steht im Reiter «Vorlage».", parent=self.win)
        self.show(self.cur); self.tabs.set("Vorlage")

    def feldplan(self):
        """v64a: Woher kommt jeder Wert der Vorlage? (feldplan_gui.py)"""
        rel = self.o_v.get(); p = Path(self.cur).parent / rel
        if not p.is_file(): messagebox.showinfo("Feldplan", "Keine Vorlage ausgewählt.", parent=self.win); return
        from .feldplan_gui import FeldplanFenster
        self.fp = FeldplanFenster(self, p, rel)

    def del_template(self):
        """v51: Vorlage aus vorlagen\\ nach vorlagen\\_entfernt\\ verschieben (nicht löschen)."""
        rel = self.o_v.get(); p = Path(self.cur).parent / rel
        if not p.is_file(): messagebox.showinfo("Workflows", "Keine Vorlage ausgewählt.", parent=self.win); return
        if rel in self.vsteps:
            messagebox.showwarning("Workflows", f"Die Vorlage wird im Schritt «{self.vsteps[rel]['id']}» verwendet.\n"
                                   "Zuerst den Schritt in der workflow.json anpassen.", parent=self.win); return
        if not messagebox.askyesno("Workflows", f"Vorlage «{p.name}» entfernen?\n\nSie wird nach vorlagen\\_entfernt "
                                   "verschoben und kann von dort zurückgeholt werden.", parent=self.win): return
        d = p.parent / "_entfernt"; d.mkdir(exist_ok=True)
        try: p.replace(d / p.name)
        except Exception as e: messagebox.showerror("Workflows", f"Nicht verschoben: {e}", parent=self.win); return
        self.show(self.cur); self.tabs.set("Vorlage")

    def fill_table(self):
        from .workflow.docx_fill import analyze
        from .workflow.expr import render, as_text
        tv = self.tv; tv.delete(*tv.get_children())
        rel = self.o_v.get(); p = Path(self.cur).parent / rel
        if not p.is_file(): self.lbl_v.configure(text="Keine Vorlage. «+ Vorlage hinzufügen …»"); return
        try: fields = analyze(p)
        except Exception as e: self.lbl_v.configure(text=f"Vorlage nicht lesbar: {e}", text_color=self.G.ERR); return
        mapping = (self.vsteps.get(rel) or {}).get("felder") or {}
        sf = latest_state(self.app_runs_dir(), self.wf); state = None
        if sf:
            try: state = json.loads(sf.read_text(encoding="utf-8"))
            except Exception: state = None
        n_map = n_leer = 0
        for f in fields:
            expr = mapping.get(f["key"], mapping.get(f"nr:{f['nr']}"))
            val, tag = "", "leer"
            if expr is not None:
                n_map += 1
                if state is not None:
                    try:
                        v = render(expr, state)
                        val = ("☒" if v and str(v).lower() not in ("false", "0", "nein") else "☐") if f["typ"] == "kontrollkaestchen" else as_text(v)
                        tag = "an" if val and val != "☐" else ""
                        if not val: n_leer += 1
                    except Exception as e: val, tag = f"Fehler: {e}", "fehler"
            typ = f["typ"] + (f" ({len(f['optionen'])})" if f["optionen"] else "")
            tv.insert("", "end", values=(f["nr"], typ, f["key"], "" if expr is None else str(expr).replace("\n", " ⏎ "),
                                         val.replace("\n", " ⏎ ")[:300]), tags=(tag,) if tag else ())
        unknown = [k for k in mapping if k not in {f["key"] for f in fields} and not k.startswith("nr:")]
        msg = f"{len(fields)} Felder · {n_map} zugeordnet · {len(fields) - n_map} ohne Zuordnung"
        msg += f" · {n_leer} im letzten Lauf leer" if state is not None else " · noch kein Lauf"
        if unknown: msg += f"\nZuordnungen ohne passendes Feld: {', '.join(unknown[:6])}{' …' if len(unknown) > 6 else ''}"
        self.lbl_v.configure(text=msg, text_color=self.G.ERR if unknown else self.G.MUTED)

    # ------------------------------------------------------------------ Reiter Pruefliste (v50)
    def _raw(self):
        return json.loads(Path(self.cur).read_text(encoding="utf-8"))

    def _pl_step(self, raw):
        return next((s for s in raw.get("steps", []) if s.get("type") == "pruefliste"), None)

    def _tab_pruefliste(self, t):
        from .workflow import pruefliste as PL
        G = self.G; self.PL = PL; t.grid_columnconfigure(0, weight=1); t.grid_rowconfigure(2, weight=1)
        try: st = self._pl_step(self._raw())
        except Exception: st = None
        self.pl = [dict(x) for x in (st or {}).get("punkte", [])]
        ctk.CTkLabel(t, text="Was soll AURA an der Datei unter «Ausführen» prüfen? Jede Zeile ist ein Prüfpunkt.\n"
                             "Regel = feste Prüfung ohne Sprachmodell (Sekunden).  Frage = das Sprachmodell antwortet ja/nein mit "
                             "Zitat (je Frage ca. 1–3 Minuten; mit «Abschnitt» schneller und genauer).",
                     font=G.font(11), text_color=G.MUTED, anchor="w", justify="left", wraplength=900).grid(row=0, column=0, sticky="w")
        bar = ctk.CTkFrame(t, fg_color="transparent"); bar.grid(row=1, column=0, sticky="w", pady=(8, 6))
        def b(txt, cmd, main=False):
            ctk.CTkButton(bar, text=txt, height=28, width=0, corner_radius=8, font=G.font(11, "bold" if main else "normal"),
                          fg_color=G.ACCENT if main else G.BORDER, hover_color=G.ACCENT_HI if main else G.MUTED,
                          text_color="white" if main else G.INK, command=cmd).pack(side="left", padx=(0, 6))
        b("+ Regel …", lambda: self._pl_edit(None, "regel"), True)
        b("+ Frage ans Sprachmodell …", lambda: self._pl_edit(None, "frage"), True)
        b("Paket einfügen …", self._pl_paket); b("Bearbeiten", lambda: self._pl_edit(self._pl_sel()))
        b("Löschen", self._pl_del); b("▲", lambda: self._pl_move(-1)); b("▼", lambda: self._pl_move(1))
        fr = tk.Frame(t); fr.grid(row=2, column=0, sticky="nsew"); fr.grid_columnconfigure(0, weight=1); fr.grid_rowconfigure(0, weight=1)
        cols = ("nr", "name", "art", "was", "abschnitt", "schwere", "ergebnis")
        tv = self.pltv = ttk.Treeview(fr, columns=cols, show="headings", selectmode="browse")
        for c, w, h in zip(cols, (40, 260, 80, 300, 100, 70, 330),
                           ("Nr", "Prüfpunkt", "Wie", "Was genau / Frage", "Abschnitt", "Schwere", "Ergebnis im letzten Lauf")):
            tv.heading(c, text=h, anchor="w"); tv.column(c, width=w, anchor="w", stretch=c in ("name", "was", "ergebnis"))
        tv.tag_configure("ok", foreground="#22C55E"); tv.tag_configure("fehler", foreground="#E5484D"); tv.tag_configure("offen", foreground="#9AA3AF")
        sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=sb.set)
        tv.grid(row=0, column=0, sticky="nsew"); sb.grid(row=0, column=1, sticky="ns")
        tv.bind("<Double-1>", lambda e: self._pl_edit(self._pl_sel()))
        self.pl_info = ctk.CTkLabel(t, text="", font=G.font(11), text_color=G.MUTED, anchor="w", justify="left", wraplength=900)
        self.pl_info.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self._pl_fill()

    def _pl_last(self):
        sf = latest_state(self.app_runs_dir(), self.wf) if self.wf else None
        if not sf: return None
        try: state = json.loads(sf.read_text(encoding="utf-8"))
        except Exception: return None
        v = next((state.get(s["id"]) for s in self.wf["steps"] if s["type"] == "pruefliste"), None)
        return {r["name"]: r for r in (v or {}).get("_pruefliste", [])} if isinstance(v, dict) else None

    def _pl_fill(self):
        tv = self.pltv; tv.delete(*tv.get_children()); last = self._pl_last()
        titel = {rid: ti for rid, ti, _, _ in self.PL.katalog()}
        for i, pk in enumerate(self.pl):
            pk = self.PL.normalize(pk); frage = pk.get("art") == "frage"
            was = pk.get("frage", "") if frage else (titel.get(pk.get("regel"), pk.get("regel", "?"))
                                                     + (f": {pk['wert']}" if pk.get("wert") else ""))
            erg, tag = "noch kein Lauf", "offen"
            if last is not None:
                r = last.get(pk["name"])
                if r is None: erg = "im letzten Lauf noch nicht dabei"
                else:
                    erg = {True: "✓ ", False: "✗ ", None: "? "}[r["ok"]] + (r["details"][0] if r["details"] else "")
                    tag = {True: "ok", False: "fehler", None: "offen"}[r["ok"]]
            tv.insert("", "end", iid=str(i), values=(i + 1, pk["name"], "Frage" if frage else "Regel", was.replace("\n", " "),
                                                     pk.get("abschnitt", ""), pk["schwere"], erg[:200]), tags=(tag,))
        n_f = sum(1 for p in self.pl if p.get("art") == "frage")
        self.pl_info.configure(text=f"{len(self.pl)} Prüfpunkte ({len(self.pl) - n_f} Regeln, {n_f} Fragen). Änderungen werden sofort "
                                    "gespeichert. Doppelklick = bearbeiten. Ausführliches Ergebnis: Pruefbericht.txt nach dem Lauf."
                               if self.pl else "Noch keine Prüfpunkte. Tipp: «Paket einfügen …» → «APA 7» legt eine fertige Liste an.")

    def _pl_sel(self):
        s = self.pltv.selection()
        if not s: messagebox.showinfo("Prüfliste", "Bitte zuerst eine Zeile anklicken.", parent=self.win); return None
        return int(s[0])

    def _pl_save(self, sel=None):
        """Prüfliste in workflow.json schreiben (Rest bleibt unverändert). Leere Liste = Schritt entfernen."""
        if self.running: messagebox.showinfo("Prüfliste", "Während eines Laufs nicht ändern.", parent=self.win); return
        try:
            raw = self._raw(); st = self._pl_step(raw)
            if self.pl and st is None:
                fin = next((i["id"] for i in raw.get("inputs", []) if i.get("type") == "files"), None)
                if not fin: raise ValueError("Der Workflow hat keine Eingabe vom Typ «files» – nichts zu prüfen")
                ids = {s.get("id") for s in raw.get("steps", [])}; sid = "pl" if "pl" not in ids else "pruefliste"
                st = {"id": sid, "type": "pruefliste", "label": "Prüfliste", "files": "{{input." + fin + "}}"}
                raw.setdefault("steps", []).append(st)
            if st is not None:
                if self.pl: st["punkte"] = self.pl
                else: raw["steps"].remove(st)
            if not raw.get("steps"): raise ValueError("Der Workflow braucht mindestens einen Schritt")
            tmp = Path(self.cur).with_suffix(".tmp")
            tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(self.cur)
        except Exception as e: messagebox.showerror("Prüfliste", f"Nicht gespeichert: {e}", parent=self.win); return
        self.show(self.cur); self.tabs.set("Prüfliste")
        if sel is not None and str(sel) in self.pltv.get_children(): self.pltv.selection_set(str(sel)); self.pltv.see(str(sel))

    def _pl_del(self):
        i = self._pl_sel()
        if i is None or not messagebox.askyesno("Prüfliste", f"Prüfpunkt «{self.PL.normalize(self.pl[i])['name']}» löschen?",
                                                parent=self.win): return
        del self.pl[i]; self._pl_save()

    def _pl_move(self, d):
        i = self._pl_sel()
        if i is None or not 0 <= i + d < len(self.pl): return
        self.pl[i], self.pl[i + d] = self.pl[i + d], self.pl[i]; self._pl_save(i + d)

    def _pl_paket(self):
        pk = self.PL.pakete(); names = list(pk); G = self.G
        dlg = ctk.CTkToplevel(self.win); dlg.title("Paket einfügen"); dlg.transient(self.win); dlg.grab_set(); dlg.geometry("560x360")
        ctk.CTkLabel(dlg, text="Fertige Prüfpunkte anhängen (danach einzeln anpassen oder löschen):", font=G.font(12),
                     wraplength=520, justify="left").pack(anchor="w", padx=16, pady=(16, 8))
        info = ctk.CTkLabel(dlg, text="", font=G.font(11), text_color=G.MUTED, wraplength=520, justify="left", anchor="w")
        def zeig(v):
            p = pk[v]; n = len(p.get("punkte", []))
            info.configure(text=f"{n} Prüfpunkte. {p.get('beschreibung', '')}\nHerkunft: {p.get('quelle') or '–'}\n\nEigene Pakete: JSON-Datei in C:\\aura\\pruefpakete\\ "
                                "ablegen (gleicher Aufbau wie «punkte» in der workflow.json, dazu «name» und «quelle»).")
        o = ctk.CTkOptionMenu(dlg, values=names, width=520, command=zeig); o.set(names[0]); o.pack(padx=16)
        info.pack(anchor="w", padx=16, pady=(10, 0)); zeig(names[0])
        def ok():
            have = {self.PL.normalize(p)["name"] for p in self.pl}
            neu = [self.PL.normalize(p) for p in pk[o.get()].get("punkte", [])]
            self.pl += [p for p in neu if p["name"] not in have]; dlg.destroy(); self._pl_save()
        ctk.CTkButton(dlg, text="Einfügen", fg_color=G.ACCENT, hover_color=G.ACCENT_HI, command=ok).pack(pady=16)

    def _pl_edit(self, idx, art=None):
        """Dialog für einen Prüfpunkt. idx=None: neu (art «regel» oder «frage»)."""
        if idx is None and art is None: return
        G, PL = self.G, self.PL
        pk = PL.normalize(self.pl[idx]) if idx is not None else {"art": art}
        art = pk.get("art", "regel"); frage = art == "frage"
        kat = PL.katalog(); by_t = {ti: (rid, be, sw) for rid, ti, be, sw in kat}; t_of = {rid: ti for rid, ti, _, _ in kat}
        dlg = ctk.CTkToplevel(self.win); dlg.title("Frage ans Sprachmodell" if frage else "Regel"); dlg.transient(self.win)
        dlg.grab_set(); dlg.geometry("640x620"); dlg.grid_columnconfigure(1, weight=1); r = 0
        def lab(txt, tip=None):
            nonlocal r
            ctk.CTkLabel(dlg, text=txt, font=G.font(12), anchor="w").grid(row=r, column=0, sticky="nw", padx=(16, 8), pady=(10, 0))
            if tip: ctk.CTkLabel(dlg, text=tip, font=G.font(10), text_color=G.MUTED, anchor="w", justify="left",
                                 wraplength=440).grid(row=r + 1, column=1, sticky="w", padx=(0, 16))
        w = {}
        if not frage:
            lab("Regel"); o = ctk.CTkOptionMenu(dlg, values=[ti for _, ti, _, _ in kat], width=440)
            o.set(t_of.get(pk.get("regel"), kat[0][1])); o.grid(row=r, column=1, sticky="w", padx=(0, 16), pady=(10, 0)); r += 1
            desc = ctk.CTkLabel(dlg, text="", font=G.font(11), text_color=G.MUTED, anchor="w", justify="left", wraplength=440)
            desc.grid(row=r, column=1, sticky="w", padx=(0, 16)); r += 1; w["regel"] = o
        lab("Name im Bericht"); e_n = ctk.CTkEntry(dlg, width=440); e_n.insert(0, pk.get("name", ""))
        e_n.grid(row=r, column=1, sticky="w", padx=(0, 16), pady=(10, 0)); r += 1
        if frage:
            lab("Frage", "So formulieren, dass «ja» = in Ordnung bedeutet. Beispiel: «Wird eine Forschungsfrage ausdrücklich formuliert?»")
            tb = ctk.CTkTextbox(dlg, width=440, height=90, wrap="word"); tb.insert("1.0", pk.get("frage", ""))
            tb.grid(row=r, column=1, sticky="w", padx=(0, 16), pady=(10, 0)); r += 2; w["frage"] = tb
            lab("Abschnitt", "Wort aus der Kapitelüberschrift, z.B. «Einleitung» oder «Fazit». Leer = ganze Arbeit (langsamer, "
                             "das Sprachmodell sieht nur die ersten ca. 10'000 Zeichen).")
            e_a = ctk.CTkEntry(dlg, width=220); e_a.insert(0, pk.get("abschnitt", ""))
            e_a.grid(row=r, column=1, sticky="w", padx=(0, 16), pady=(10, 0)); r += 2; w["abschnitt"] = e_a
        else:
            lab("Was genau"); e_w = ctk.CTkEntry(dlg, width=440); e_w.insert(0, pk.get("wert", ""))
            e_w.grid(row=r, column=1, sticky="w", padx=(0, 16), pady=(10, 0))
            h_w = ctk.CTkLabel(dlg, text="", font=G.font(10), text_color=G.MUTED, wraplength=440, justify="left")
            h_w.grid(row=r + 1, column=1, sticky="w"); r += 2; w["wert"] = e_w
            lab("Abschnitt"); e_ab = ctk.CTkEntry(dlg, width=220); e_ab.insert(0, pk.get("abschnitt", ""))
            e_ab.grid(row=r, column=1, sticky="w", padx=(0, 16), pady=(10, 0))
            h_a = ctk.CTkLabel(dlg, text="", font=G.font(10), text_color=G.MUTED, wraplength=440, justify="left")
            h_a.grid(row=r + 1, column=1, sticky="w"); r += 2; w["abschnitt"] = e_ab
        if True:
            lab("Herkunft", "Woher stammt die Anforderung? Z.B. «Wegleitung CAS, Kap. 3» – erscheint im Prüfbericht.")
            e_q = ctk.CTkEntry(dlg, width=440); e_q.insert(0, pk.get("quelle", ""))
            e_q.grid(row=r, column=1, sticky="w", padx=(0, 16), pady=(10, 0)); r += 2; w["quelle"] = e_q
        lab("Schwere", "Fehler = muss korrigiert werden. Hinweis = bitte anschauen.")
        o_s = ctk.CTkOptionMenu(dlg, values=list(PL.SCHWERE), width=140); o_s.set(pk.get("schwere", "Hinweis"))
        o_s.grid(row=r, column=1, sticky="w", padx=(0, 16), pady=(10, 0)); r += 2
        if not frage:
            def on_regel(v, first=False):
                rid, be, sw = by_t[v]; fn = PL.REGELN[rid]; desc.configure(text=be)
                h_w.configure(text=fn.wert or "bei dieser Regel nicht nötig")
                h_a.configure(text=fn.abschnitt or "bei dieser Regel nicht nötig")
                if not first:
                    if e_n.get().strip() in t_of.values() or not e_n.get().strip(): e_n.delete(0, "end"); e_n.insert(0, v)
                    o_s.set(sw)
            o.configure(command=on_regel); on_regel(o.get(), first=idx is not None)
        def ok():
            neu = {"art": art, "name": e_n.get().strip(), "schwere": o_s.get()}
            if w.get("quelle") and w["quelle"].get().strip(): neu["quelle"] = w["quelle"].get().strip()
            if frage:
                neu["frage"] = w["frage"].get("1.0", "end").strip(); a = w["abschnitt"].get().strip()
                if a: neu["abschnitt"] = a
                if not neu["frage"]: messagebox.showwarning("Prüfliste", "Bitte eine Frage eingeben.", parent=dlg); return
            else:
                neu["regel"] = by_t[w["regel"].get()][0]; v = w["wert"].get().strip()
                if v: neu["wert"] = v
                a = w["abschnitt"].get().strip()
                if a: neu["abschnitt"] = a
            if not neu["name"]: neu["name"] = (neu.get("frage", "")[:60] if frage else w["regel"].get())
            other = {PL.normalize(p)["name"] for j, p in enumerate(self.pl) if j != idx}
            if neu["name"] in other: messagebox.showwarning("Prüfliste", "Diesen Namen gibt es schon.", parent=dlg); return
            if idx is None: self.pl.append(neu); sel = len(self.pl) - 1
            else: self.pl[idx] = neu; sel = idx
            dlg.destroy(); self._pl_save(sel)
        bb = ctk.CTkFrame(dlg, fg_color="transparent"); bb.grid(row=r, column=0, columnspan=2, sticky="e", padx=16, pady=16)
        ctk.CTkButton(bb, text="Abbrechen", width=100, fg_color=G.BORDER, text_color=G.INK, hover_color=G.MUTED,
                      command=dlg.destroy).pack(side="left", padx=6)
        ctk.CTkButton(bb, text="Speichern", width=100, fg_color=G.ACCENT, hover_color=G.ACCENT_HI, command=ok).pack(side="left")

    # ------------------------------------------------------------------ Verwalten
    def delete(self):
        name = Path(self.cur).parent.name
        if not messagebox.askyesno("Workflows", f"Workflow «{name}» mit Wissen, Vorlagen und allen Läufen löschen?\n\n"
                                   f"Der Ordner wird nach workflows\\_geloescht verschoben.", parent=self.win): return
        try: paket.delete(Path(self.cur).parent)
        except Exception as e: messagebox.showerror("Workflows", str(e), parent=self.win); return
        self.cur = None; self.refresh_list()
        for c in self.right.winfo_children(): c.destroy()

    def exportieren(self):
        """v78: Paket mit Wissen, Vorlagen und gemeinsamen Sammlungen als .aurawf.zip."""
        from .workflow import austausch
        pkg = Path(self.cur).parent
        f = filedialog.asksaveasfilename(parent=self.win, title="Workflow exportieren", initialfile=f"{pkg.name}.aurawf.zip",
                                         defaultextension=".zip", filetypes=[("AURA-Workflow", "*.aurawf.zip"), ("ZIP", "*.zip")])
        if not f: return
        laeufe = any((pkg / "laeufe").glob("*")) and messagebox.askyesno(
            "Exportieren", "Auch die bisherigen Läufe (Eingaben, Ergebnisse) mitgeben?\n\nNur nötig zum Nachsehen beim Empfänger.",
            default="no", parent=self.win)
        try: z, hw = austausch.export(pkg, f, mit_laeufen=laeufe, progress=lambda m: None)
        except Exception as e: messagebox.showerror("Exportieren", str(e), parent=self.win); return
        messagebox.showinfo("Exportieren", f"Gespeichert: {z}\n\nEnthält Wissen und Vorlagen. Vor der Weitergabe Inhalt auf "
                            "schutzwürdige Daten prüfen." + ("\n\nHinweise:\n- " + "\n- ".join(hw) if hw else ""), parent=self.win)

    def importieren(self):
        """v78: .aurawf.zip einlesen; bei Namenskonflikt neuen Namen erfragen."""
        from .workflow import austausch
        f = filedialog.askopenfilename(parent=self.win, title="Workflow importieren",
                                       filetypes=[("AURA-Workflow", "*.aurawf.zip *.zip")])
        if not f: return
        try: m, _ = austausch.lesen(f)
        except Exception as e: messagebox.showerror("Importieren", str(e), parent=self.win); return
        from .wissen import WISSEN_DIR
        vorhanden = [s for s in m.get("gemeinsam", []) if (WISSEN_DIR / s).is_dir()]
        ersetzen = bool(vorhanden) and messagebox.askyesno(
            "Importieren", f"Gemeinsame Sammlungen gibt es hier schon: {', '.join(vorhanden)}\n\n"
            "Ja = durch die Fassung im Paket ersetzen (alte wird gesichert)\nNein = behalten, nur fehlende Dateien ergänzen",
            default="no", parent=self.win)
        name = None
        while True:
            try: d, ber = austausch.importieren(f, name=name, gemeinsam_ersetzen=ersetzen, progress=lambda x: None); break
            except austausch.NameBesetzt as e:
                name = ctk.CTkInputDialog(text=f"{e}.\nNeuer Name:", title="Importieren").get_input()
                if not name: return
            except Exception as e: messagebox.showerror("Importieren", str(e), parent=self.win); return
        messagebox.showinfo("Importieren", f"Workflow «{m.get('titel', d.name)}» importiert.\n\n- " + "\n- ".join(ber), parent=self.win)
        self.refresh_list(); self.show(str(d / "workflow.json"))

    def migrate(self):
        from .wissen import Wissen
        shared = set(Wissen(lambda: None, lambda *a: None).names())
        cand = [k["sammlung"] for k in (self.wf or {}).get("knowledge", []) if k["sammlung"] in shared]
        sam = None
        for c in cand:
            if messagebox.askyesno("Workflows", f"Sammlung «{c}» in den Workflow umziehen?\n(Nein = bleibt gemeinsame Sammlung)",
                                   parent=self.win): sam = c; break
        try: d = paket.migrate(self.cur, sammlung=sam, progress=lambda m: None)
        except Exception as e: messagebox.showerror("Workflows", str(e), parent=self.win); return
        self.refresh_list(); self.show(str(d / "workflow.json"))
