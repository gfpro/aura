# aura/code_gui.py — Werkzeug «Code prüfen» (Vollansicht). Version 20261031v145
# Ablauf: 1 Projektordner wählen -> Einlesen (statische Prüfung ohne Modell, Sekunden) -> 2 Dateien wählen und mit dem
# Sprachmodell prüfen (Abschnitt für Abschnitt) -> 3 Doppelklick auf einen Befund: Auftrag anpassen, Vorschlag erzeugen,
# Diff prüfen, Übernehmen (mit Sicherung) oder Verwerfen. «Sicherungen …» stellt frühere Stände wieder her.
import os, subprocess, tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk
from . import code
from .config import load_settings, save_settings

F = "Segoe UI"
def font(size=13, weight="normal"): return ctk.CTkFont(family=F, size=size, weight=weight)
SIDE, CARD, BORDER = ("#FFFFFF", "#10172E"), ("#EEF0F7", "#18213D"), ("#E1E4EE", "#263156")
INK, MUTED = ("#111827", "#E6E9F2"), ("#6B7280", "#8E98B5")
ACCENT, ACCENT_HI = "#6E56F8", "#5A43E0"
WARN_BG, WARN_INK = ("#FFF4E5", "#3A2A10"), ("#7A4B00", "#FFD089")
STUFE_FARBE = {"hoch": "#FECACA", "mittel": "#FDE68A", "tief": "#E5E7EB"}
HINWEIS = ("Arbeite auf einer Kopie oder einem eigenen Git-Zweig. AURA ändert nur, was du einzeln übernimmst, und legt vorher "
           "eine Sicherung unter data\\code\\sicherung an. Nichts verlässt den Rechner; Push/Pull machst du selbst.")


class CodeWindow:
    def __init__(self, app):
        self.app = app
        self.body = app.view("code", "Werkzeuge › Code prüfen")
        self.body.grid_columnconfigure(0, weight=1); self.body.grid_rowconfigure(0, weight=1)
        self.root_dir = load_settings().get("code_folder", "")
        self.dateien, self.befunde, self.statik, self.vorschlag = [], [], [], None
        self.bericht_pfad = ""
        self._bau()
        if self.root_dir and Path(self.root_dir).is_dir(): self.einlesen()

    def alive(self):
        try: return bool(self.body.winfo_exists())
        except Exception: return False

    # ------------------------------------------------------------------ Aufbau
    def _btn(self, parent, text, cmd, main=False, **kw):
        return ctk.CTkButton(parent, text=text, command=cmd, height=32, corner_radius=8, font=font(12, "bold" if main else "normal"),
                             fg_color=ACCENT if main else CARD, hover_color=ACCENT_HI if main else BORDER,
                             text_color="white" if main else INK, **kw)

    def _bau(self):
        f = ctk.CTkFrame(self.body, fg_color="transparent"); f.grid(row=0, column=0, sticky="nsew", padx=24, pady=(6, 12))
        f.grid_columnconfigure(0, weight=1); f.grid_rowconfigure(4, weight=1)
        ctk.CTkLabel(f, text="Code prüfen", font=font(22, "bold"), text_color=INK, anchor="w").grid(row=0, column=0, sticky="w")
        b = ctk.CTkFrame(f, fg_color=WARN_BG, corner_radius=10); b.grid(row=1, column=0, sticky="ew", pady=(6, 8))
        lb = ctk.CTkLabel(b, text="⚠  " + HINWEIS, font=font(12), text_color=WARN_INK, justify="left", anchor="w", wraplength=820)
        lb.pack(fill="x", padx=14, pady=8)
        b.bind("<Configure>", lambda e: lb.configure(wraplength=max(300, e.width - 40)), add="+")

        top = ctk.CTkFrame(f, fg_color=CARD, corner_radius=10); top.grid(row=2, column=0, sticky="ew"); top.grid_columnconfigure(1, weight=1)
        self._btn(top, "Projektordner …", self.ordner_waehlen, main=not self.root_dir).grid(row=0, column=0, padx=10, pady=8)
        self.l_ordner = ctk.CTkLabel(top, text=self.root_dir or "Noch kein Ordner gewählt", font=font(12), text_color=INK, anchor="w")
        self.l_ordner.grid(row=0, column=1, sticky="ew")
        self.l_git = ctk.CTkLabel(top, text="", font=font(11), text_color=MUTED); self.l_git.grid(row=0, column=2, padx=8)
        self._btn(top, "Neu einlesen", self.einlesen).grid(row=0, column=3, padx=(0, 10))

        act = ctk.CTkFrame(f, fg_color="transparent"); act.grid(row=3, column=0, sticky="ew", pady=(8, 6))
        self.llm_var = tk.BooleanVar(value=bool(load_settings().get("code_llm", False)))          # v144: standardmässig aus
        ctk.CTkSwitch(act, text="Zweite Meinung (experimentell)", variable=self.llm_var, command=self._llm_schalter, font=font(12),
                      text_color=INK, progress_color=ACCENT).pack(side="left", padx=(0, 10))
        self.b_pruef = self._btn(act, "▶ Zweite Meinung einholen", self.pruefen, main=True); self.b_pruef.pack(side="left")
        self._btn(act, "Abbrechen", lambda: self.app.w.cancel.set(), width=90).pack(side="left", padx=6)
        self._btn(act, "Bericht öffnen", self.bericht_oeffnen, width=110).pack(side="left", padx=(0, 6))
        self._btn(act, "Sicherungen …", self.sicherungen, width=110).pack(side="left")
        self.l_status = ctk.CTkLabel(act, text="", font=font(11), text_color=MUTED, anchor="e"); self.l_status.pack(side="right")

        pw = tk.PanedWindow(f, orient="horizontal", sashwidth=6, bd=0, bg="#E1E4EE"); pw.grid(row=4, column=0, sticky="nsew")
        st = ttk.Style(); st.configure("Code.Treeview", rowheight=28, font=(F, 10))  # v143: Unterstriche sichtbar; st.configure("Code.Treeview.Heading", font=(F, 10, "bold"))
        lf = tk.Frame(pw); self.t_dat = ttk.Treeview(lf, columns=("z", "h"), style="Code.Treeview", selectmode="extended")
        self.t_dat.heading("#0", text="Datei"); self.t_dat.heading("z", text="Zeilen"); self.t_dat.heading("h", text="Hinweise")
        self.t_dat.column("#0", width=260); self.t_dat.column("z", width=60, anchor="e"); self.t_dat.column("h", width=70, anchor="e")
        self._scroll(lf, self.t_dat); pw.add(lf, minsize=220)
        rf = tk.Frame(pw); self.t_bef = ttk.Treeview(rf, columns=("s", "o", "a", "t"), show="headings", style="Code.Treeview")
        for c, t, w in (("s", "Stufe", 60), ("o", "Ort", 190), ("a", "Art", 110), ("t", "Befund", 520)):
            self.t_bef.heading(c, text=t); self.t_bef.column(c, width=w, stretch=(c == "t"))
        for s_, col in STUFE_FARBE.items(): self.t_bef.tag_configure(s_, background=col, foreground="#111827")
        self._scroll(rf, self.t_bef); pw.add(rf, minsize=320)
        self.t_dat.bind("<<TreeviewSelect>>", lambda e: self._zeige_befunde())
        self.t_bef.bind("<Double-1>", lambda e: self.vorschlag_dialog())
        self.b_pruef.configure(state="normal" if self.llm_var.get() else "disabled")
        self.t_bef.tag_configure("modell", foreground="#6B7280")
        ctk.CTkLabel(f, text="Doppelklick auf einen Befund: Vorschlag erzeugen und als Diff prüfen. Ohne Auswahl links: alle Dateien.",
                     font=font(11), text_color=MUTED, anchor="w").grid(row=5, column=0, sticky="w", pady=(6, 0))

    def _scroll(self, parent, tree):
        sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview); tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")

    # ------------------------------------------------------------------ Aktionen
    def ordner_waehlen(self):
        d = filedialog.askdirectory(title="Projektordner wählen (am besten eine Kopie oder ein Git-Zweig)", parent=self.app.root)
        if not d: return
        if os.path.normcase(os.path.abspath(d)) == os.path.normcase(str(code.DATA.parent)):
            if not messagebox.askyesno("AURA", "Das ist der AURA-Programmordner selbst. Trotzdem prüfen?", parent=self.app.root): return
        self.root_dir = d; s = load_settings(); s["code_folder"] = d; save_settings(s)
        self.l_ordner.configure(text=d); self.einlesen()

    def einlesen(self):
        if not self.root_dir: self.ordner_waehlen(); return
        self.l_status.configure(text="lese ein …"); self.app.w.submit("code_scan", self.root_dir)

    def _backend(self):
        from .llm import discover
        from .config import MODELS
        s = load_settings(); ids = [i for i, _, _ in discover(MODELS)]
        return s.get("llm") if s.get("llm") in ids else "extractive"

    def _llm_schalter(self):
        s = load_settings(); s["code_llm"] = bool(self.llm_var.get()); save_settings(s)
        self.b_pruef.configure(state="normal" if self.llm_var.get() else "disabled")
        if self.llm_var.get():
            messagebox.showinfo("AURA – Zweite Meinung", "Das lokale Sprachmodell prüft den Code zusätzlich. Seine Befunde sind "
                                "erfahrungsgemäss oft falsch (z.B. «undefiniert», obwohl definiert). AURA verwirft, was sich "
                                "widerlegen lässt, und stuft Modell-Befunde nie als «hoch» ein.\n\nVerlässlich ist die Prüfung "
                                "ohne Sprachmodell. Modell-Befunde immer selbst nachprüfen.", parent=self.app.root)

    def pruefen(self):
        if not self.llm_var.get(): return
        if not self.dateien: messagebox.showinfo("AURA", "Zuerst einen Projektordner einlesen.", parent=self.app.root); return
        be = self._backend()
        if be == "extractive":
            messagebox.showinfo("AURA", "Dafür braucht es ein Sprachmodell – links unter «Chat» eines wählen und laden.", parent=self.app.root); return
        rels = list(self.t_dat.selection()) or [d["pfad"] for d in self.dateien]
        n_zeilen = sum(d["zeilen"] for d in self.dateien if d["pfad"] in rels)
        if n_zeilen > 3000 and not messagebox.askyesno(
                "AURA", f"{len(rels)} Dateien mit {n_zeilen:,} Zeilen – das kann lange dauern (grob 20–60 s je 100 Zeilen).\n\n"
                        "Tipp: links nur die wichtigen Dateien markieren.\n\nTrotzdem starten?".replace(",", "'"), parent=self.app.root): return
        self.befunde = [b for b in self.befunde if not b["art"].startswith("Modell") or b["pfad"] not in rels]
        self.l_status.configure(text="Sprachmodell prüft …")
        self.app.w.submit("code_pruefen", self.root_dir, rels, be, self.statik)

    def bericht_oeffnen(self):
        p = self.bericht_pfad or (str(code.bericht(self.root_dir, self.dateien, self.befunde, code.git_info(self.root_dir)))
                                  if self.dateien else "")
        if not p: return
        self.bericht_pfad = p                                           # v145: im eigenen Fenster statt Dateizuordnung (App-V)
        w = ctk.CTkToplevel(self.app.root); w.title(f"Bericht – {Path(p).name}"); w.geometry("980x700"); w.transient(self.app.root)
        w.grid_columnconfigure(0, weight=1); w.grid_rowconfigure(0, weight=1)
        t = tk.Text(w, font=(F, 10), wrap="word", bd=0, padx=12, pady=10); t.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))
        sb = ttk.Scrollbar(w, command=t.yview); sb.grid(row=0, column=1, sticky="ns", pady=(12, 6)); t.configure(yscrollcommand=sb.set)
        t.tag_configure("h1", font=(F, 15, "bold")); t.tag_configure("h2", font=(F, 12, "bold"), spacing1=10)
        t.tag_configure("hinweis", foreground="#7A4B00", background="#FFF4E5")
        for z in Path(p).read_text(encoding="utf-8").splitlines():
            tag = "h1" if z.startswith("# ") else "h2" if z.startswith("## ") else "hinweis" if z.startswith(">") else ""
            t.insert("end", z.lstrip("#> ").replace("**", "").replace("`", "") + "\n", tag)
        t.configure(state="disabled")
        bt = ctk.CTkFrame(w, fg_color="transparent"); bt.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        self._btn(bt, "Im Ordner zeigen", lambda: subprocess.Popen(["explorer", "/select,", str(Path(p))]), width=130).pack(side="left")
        self._btn(bt, "Schliessen", w.destroy, width=90).pack(side="right")

    # ------------------------------------------------------------------ Ereignisse aus dem Worker
    def on_code(self, d):
        art = d.get("art")
        if art == "scan":
            self.dateien, self.statik = d["dateien"], d["befunde"]; self.befunde = list(self.statik); self.bericht_pfad = ""
            g = d.get("git")
            self.l_git.configure(text=(f"Git · Zweig {g['branch']} · {g['geaendert']} offene Änderungen" if g else "kein Git – Sicherung über AURA"))
            self._zeige_dateien(); self._zeige_befunde()
            self.l_status.configure(text=f"{len(self.dateien)} Dateien · {len(self.statik)} Hinweise ohne Modell")
        elif art == "befunde":
            self.befunde += d["befunde"]; self._zeige_dateien(keep=True); self._zeige_befunde()
        elif art == "fertig":
            self.bericht_pfad = d.get("bericht", "")
            self.l_status.configure(text="Prüfung abgebrochen" if d.get("abgebrochen") else "Prüfung fertig – Bericht gespeichert")
        elif art == "vorschlag": self._zeige_vorschlag(d)
        elif art == "fehler":
            self.l_status.configure(text=""); messagebox.showerror("AURA – Code prüfen", d["text"], parent=self.app.root)

    def on_progress(self, text):
        if text.startswith("Code:"): self.l_status.configure(text=text[5:].strip()[:90])

    def _zeige_dateien(self, keep=False):
        sel = self.t_dat.selection() if keep else ()
        n = {}
        for b in self.befunde: n[b["pfad"]] = n.get(b["pfad"], 0) + 1
        self.t_dat.delete(*self.t_dat.get_children())
        for d in self.dateien:
            self.t_dat.insert("", "end", iid=d["pfad"], text=d["pfad"], values=(d["zeilen"], n.get(d["pfad"], "")))
        try:
            if sel: self.t_dat.selection_set(sel)
        except tk.TclError: pass

    def _zeige_befunde(self):
        sel = set(self.t_dat.selection())
        self.t_bef.delete(*self.t_bef.get_children())
        for i, b in enumerate(self.befunde):
            if sel and b["pfad"] not in sel: continue
            txt = b["text"] + (f"  → {b['vorschlag']}" if b.get("vorschlag") else "")
            self.t_bef.insert("", "end", iid=str(i), values=(b["stufe"], f"{b['pfad']}:{b['zeile']}", b["art"], txt), tags=(b["stufe"],) + (("modell",) if b["art"].startswith("Modell") else ()))

    # ------------------------------------------------------------------ Vorschlag
    def vorschlag_dialog(self):
        s = self.t_bef.selection()
        if not s: return
        b = self.befunde[int(s[0])]
        try: txt = code.lesen(self.root_dir, b["pfad"])
        except OSError as e: messagebox.showerror("AURA", str(e), parent=self.app.root); return
        ab = next((a for a in code.abschnitte(b["pfad"], txt) if a["start"] <= b["zeile"] <= a["ende"]), None)
        if ab is None: return
        w = self.dlg = ctk.CTkToplevel(self.app.root); w.title(f"Vorschlag – {b['pfad']}"); w.geometry("1000x720")
        w.transient(self.app.root); w.grid_columnconfigure(0, weight=1); w.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(w, text=f"{b['pfad']} › {ab['name']}", font=font(15, "bold"), text_color=INK, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        r = ctk.CTkFrame(w, fg_color="transparent"); r.grid(row=1, column=0, sticky="ew", padx=16, pady=4)
        ctk.CTkLabel(r, text="Zeilen", font=font(12), text_color=MUTED).pack(side="left")
        self.e_a, self.e_e = (ctk.CTkEntry(r, width=60) for _ in range(2))
        self.e_a.insert(0, str(ab["start"])); self.e_e.insert(0, str(ab["ende"]))
        self.e_a.pack(side="left", padx=4); ctk.CTkLabel(r, text="bis", font=font(12), text_color=MUTED).pack(side="left"); self.e_e.pack(side="left", padx=4)
        ctk.CTkLabel(r, text="Auftrag an das Sprachmodell:", font=font(12), text_color=MUTED).pack(side="left", padx=(16, 4))
        self.e_auf = ctk.CTkTextbox(w, height=60, font=font(12)); self.e_auf.grid(row=2, column=0, sticky="ew", padx=16)
        self.e_auf.insert("1.0", f"Behebe: {b['text']}" + (f" ({b['vorschlag']})" if b.get("vorschlag") else "") +
                          ". Ändere sonst nichts am Verhalten.")
        self.t_diff = tk.Text(w, font=("Consolas", 10), wrap="none", bd=0, padx=8, pady=6)
        self.t_diff.grid(row=3, column=0, sticky="nsew", padx=16, pady=8)
        for tag, col in (("plus", "#DCFCE7"), ("minus", "#FEE2E2"), ("kopf", "#E0E7FF")): self.t_diff.tag_configure(tag, background=col)
        self.t_diff.insert("1.0", code.nummeriert(txt, ab["start"], ab["ende"])); self.t_diff.configure(state="disabled")
        bt = ctk.CTkFrame(w, fg_color="transparent"); bt.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._btn(bt, "▶ Vorschlag erzeugen", lambda: self._vorschlag_start(b["pfad"]), main=True).pack(side="left")
        self.b_ueber = self._btn(bt, "✓ Übernehmen (mit Sicherung)", self._uebernehmen, state="disabled"); self.b_ueber.pack(side="left", padx=8)
        self._btn(bt, "Schliessen", w.destroy, width=90).pack(side="right")
        self.l_pruef = ctk.CTkLabel(bt, text="", font=font(11), text_color=MUTED); self.l_pruef.pack(side="left", padx=8)
        self.vorschlag = None

    def _vorschlag_start(self, rel):
        be = self._backend()
        if be == "extractive":
            messagebox.showinfo("AURA", "Dafür braucht es ein Sprachmodell – links unter «Chat» eines wählen.", parent=self.dlg); return
        try: a, e = int(self.e_a.get()), int(self.e_e.get())
        except ValueError: return
        if e < a or e - a > 400: messagebox.showinfo("AURA", "Bitte höchstens 400 Zeilen auf einmal.", parent=self.dlg); return
        self.l_pruef.configure(text="Sprachmodell schreibt …"); self.b_ueber.configure(state="disabled")
        self.app.w.submit("code_vorschlag", self.root_dir, rel, a, e, self.e_auf.get("1.0", "end").strip(), be)

    def _zeige_vorschlag(self, v):
        if not getattr(self, "dlg", None) or not self.dlg.winfo_exists(): return
        self.vorschlag = v; t = self.t_diff; t.configure(state="normal"); t.delete("1.0", "end")
        if not v["diff"]: t.insert("1.0", "Das Sprachmodell hat nichts geändert.")
        for l in v["diff"].splitlines(keepends=True):
            tag = "kopf" if l.startswith(("@@", "---", "+++")) else "plus" if l.startswith("+") else "minus" if l.startswith("-") else ""
            t.insert("end", l, tag)
        t.configure(state="disabled")
        self.l_pruef.configure(text=("✓ " if v["ok"] else "✗ ") + v["warum"], text_color=("#15803D" if v["ok"] else "#B91C1C"))
        self.b_ueber.configure(state="normal" if v["ok"] and v["diff"] else "disabled")

    def _uebernehmen(self):
        v = self.vorschlag
        if not v: return
        try: ziel = code.uebernehmen(self.root_dir, v)
        except Exception as e: messagebox.showerror("AURA", str(e), parent=self.dlg); return
        messagebox.showinfo("AURA", f"Übernommen.\n\nSicherung des alten Stands:\n{ziel}", parent=self.dlg)
        self.dlg.destroy(); self.einlesen()

    def sicherungen(self):
        if not self.root_dir: return
        liste = code.sicherungen(self.root_dir)
        if not liste: messagebox.showinfo("AURA", "Für diesen Ordner gibt es noch keine Sicherungen.", parent=self.app.root); return
        w = ctk.CTkToplevel(self.app.root); w.title("Sicherungen"); w.geometry("720x420"); w.transient(self.app.root)
        tr = ttk.Treeview(w, columns=("z", "p"), show="headings", style="Code.Treeview")
        tr.heading("z", text="Zeitpunkt"); tr.heading("p", text="Datei"); tr.column("z", width=160); tr.column("p", width=520)
        for i, (z, _, rel) in enumerate(liste): tr.insert("", "end", iid=str(i), values=(f"{z[6:8]}.{z[4:6]}.{z[:4]} {z[9:11]}:{z[11:13]}", rel))
        tr.pack(fill="both", expand=True, padx=12, pady=12)
        def zurueck():
            s = tr.selection()
            if not s: return
            z, f, rel = liste[int(s[0])]
            if messagebox.askyesno("AURA", f"{rel} auf den Stand vor der Änderung vom {tr.item(s[0])['values'][0]} zurücksetzen?\n\n"
                                   "Spätere Änderungen an dieser Datei gehen verloren.", parent=w):
                code.zuruecksetzen(self.root_dir, f, rel); w.destroy(); self.einlesen()
        self._btn(w, "Ausgewählte Datei zurücksetzen", zurueck).pack(pady=(0, 12))
