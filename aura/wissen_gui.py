# aura/wissen_gui.py — Ansicht «Wissenssammlungen»: anlegen, Dokumente hinzufuegen/entfernen, Angaben pflegen.
# Version 20261011v46 (v38: Infotexte, v46: Vollansicht im Hauptfenster). Schreibt sammlung.json; Abgleich laeuft im Worker (job wissen_sync).
import os, tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from .wissen import Wissen, WISSEN_DIR, folder
from . import hilfe

ARTEN = {"auto": "automatisch", "recht": "Erlass (Artikel)", "text": "Fliesstext"}
ARTEN_R = {v: k for k, v in ARTEN.items()}

class WissenWindow:
    def __init__(self, app):
        from . import gui as G
        self.G, self.app = G, app
        self.w = Wissen(lambda: None, lambda *a: None)              # nur lesen/verwalten; Einbetten macht der Worker
        self.cur, self.rows, self.dirty = None, [], False
        win = self.win = app.view("wissen", "Wissenssammlungen")   # v46: Rahmen im Hauptfenster
        win.grid_columnconfigure(1, weight=1); win.grid_rowconfigure(0, weight=1)
        # links: Liste der Sammlungen
        left = ctk.CTkFrame(win, fg_color=G.CARD, corner_radius=0, width=230); left.grid(row=0, column=0, sticky="nsw")
        left.grid_propagate(False); left.grid_columnconfigure(0, weight=1); left.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(left, text="SAMMLUNGEN", font=G.font(10, "bold"), text_color=G.MUTED, anchor="w").grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 6))
        self.lst = ctk.CTkScrollableFrame(left, fg_color="transparent"); self.lst.grid(row=1, column=0, sticky="nsew", padx=6)
        self.lst.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(left, text="+ Neue Sammlung", height=32, corner_radius=8, font=G.font(12, "bold"), fg_color=G.ACCENT,
                      hover_color=G.ACCENT_HI, command=self.new).grid(row=2, column=0, sticky="ew", padx=12, pady=12)
        hilfe.auto(left, "wissen")
        # rechts: Details
        self.right = ctk.CTkFrame(win, fg_color="transparent"); self.right.grid(row=0, column=1, sticky="nsew", padx=18, pady=14)
        self.right.grid_columnconfigure(0, weight=1); self.right.grid_rowconfigure(3, weight=1)
        self.refresh_list()
        names = self.w.names()
        if names: self.show(names[0])
        else: ctk.CTkLabel(self.right, text="Noch keine Sammlung. Links «+ Neue Sammlung».", font=G.font(13),
                           text_color=G.MUTED).grid(row=0, column=0, pady=60)

    def alive(self): return self.win is not None and self.win.winfo_exists()
    def close(self): self.app.show_chat()          # v46: Ansicht bleibt offen; ungespeicherte Angaben gehen nicht verloren

    # ------------------------------------------------------------------ Liste
    def refresh_list(self):
        G = self.G
        for c in self.lst.winfo_children(): c.destroy()
        for i, n in enumerate(self.w.names()):
            m = self.w.manifest(n); sel = n == self.cur
            ctk.CTkButton(self.lst, text=m.get("name") or n, anchor="w", height=30, corner_radius=8, font=G.font(12, "bold" if sel else "normal"),
                          fg_color=G.ACCENT if sel else "transparent", hover_color=G.BORDER,
                          text_color="white" if sel else G.INK, command=lambda n=n: self.switch(n)).grid(row=i, column=0, sticky="ew", pady=1)

    def switch(self, n):
        if n == self.cur: return
        if self.dirty and not messagebox.askyesno("Wissen", "Änderungen nicht gespeichert. Verwerfen?", parent=self.win): return
        self.show(n)

    def new(self):
        d = ctk.CTkInputDialog(text="Name der neuen Sammlung (z.B. «Beschaffungsrecht», «HERMES»):", title="Neue Sammlung")
        t = d.get_input()
        if not t: return
        try: n = self.w.create(t)
        except Exception as e: messagebox.showerror("Wissen", str(e), parent=self.win); return
        self.show(n)

    # ------------------------------------------------------------------ Details
    def show(self, name):
        G = self.G; self.cur, self.dirty = name, False
        for c in self.right.winfo_children(): c.destroy()
        m = self.w.manifest(name); self.man = m
        # Kopf
        hd = ctk.CTkFrame(self.right, fg_color="transparent"); hd.grid(row=0, column=0, sticky="ew"); hd.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hd, text="Anzeigename", font=G.font(11), text_color=G.MUTED).grid(row=0, column=0, sticky="w")
        self.e_name = ctk.CTkEntry(hd, height=30, font=G.font(14, "bold")); self.e_name.insert(0, m.get("name", name))
        self.e_name.grid(row=0, column=1, sticky="ew", padx=(10, 0)); hilfe.tip(self.e_name, "#w_name")
        ctk.CTkLabel(hd, text=f"Ordner: {folder(name).relative_to(WISSEN_DIR.parent)}", font=G.font(10), text_color=G.MUTED).grid(row=0, column=2, padx=12)
        ctk.CTkLabel(hd, text="Beschreibung", font=G.font(11), text_color=G.MUTED).grid(row=1, column=0, sticky="nw", pady=(8, 0))
        self.t_desc = ctk.CTkTextbox(hd, height=52, font=G.font(12), wrap="word", border_width=1, border_color=G.BORDER)
        self.t_desc.insert("1.0", m.get("beschreibung", "")); self.t_desc.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=(8, 0))
        hilfe.tip(self.t_desc, "#w_beschreibung")
        opt = ctk.CTkFrame(self.right, fg_color="transparent"); opt.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.v_chat = tk.BooleanVar(value=bool(m.get("im_chat", True)))
        ctk.CTkCheckBox(opt, text="Im Chat verwendbar (wenn «Wissen im Chat» eingeschaltet ist)", variable=self.v_chat,
                        font=G.font(12), command=self.touch).pack(side="left")
        ctk.CTkLabel(opt, text="Warnung ab Alter (Monate, 0 = nie):", font=G.font(12), text_color=G.INK).pack(side="left", padx=(24, 6))
        self.e_age = ctk.CTkEntry(opt, width=50, height=28); self.e_age.insert(0, str(m.get("max_alter_monate", 12)))
        self.e_age.pack(side="left"); self.e_age.bind("<KeyRelease>", lambda e: self.touch()); hilfe.tip(self.e_age, "#w_alter")
        # Werkzeugleiste
        bar = ctk.CTkFrame(self.right, fg_color="transparent"); bar.grid(row=2, column=0, sticky="ew", pady=(12, 6))
        btn = lambda t, c, acc=False: ctk.CTkButton(bar, text=t, height=30, corner_radius=8, font=G.font(12, "bold" if acc else "normal"),
                                                    fg_color=G.ACCENT if acc else G.CARD, hover_color=G.ACCENT_HI if acc else G.BORDER,
                                                    text_color="white" if acc else G.INK, command=c)
        btn("+ Dokumente hinzufügen …", self.add).pack(side="left")
        btn("Ordner öffnen", lambda: os.startfile(str(folder(name))) if hasattr(os, "startfile") else None).pack(side="left", padx=6)
        self.b_save = btn("Speichern & abgleichen", self.save, acc=True); self.b_save.pack(side="right")
        self.lbl_state = ctk.CTkLabel(bar, text="", font=G.font(11), text_color=G.MUTED); self.lbl_state.pack(side="right", padx=12)
        # Dokumenttabelle
        tab = self.tab = ctk.CTkScrollableFrame(self.right, fg_color=G.CARD, corner_radius=10)
        tab.grid(row=3, column=0, sticky="nsew")
        for c, wgt in enumerate((3, 1, 4, 2, 1, 0, 3, 0)): tab.grid_columnconfigure(c, weight=wgt)
        for c, h in enumerate(("Datei", "Kürzel", "Titel", "Art", "Stand", "Pflicht", "Status", "")):
            hilfe.tip(ctk.CTkLabel(tab, text=h.upper(), font=G.font(10, "bold"), text_color=G.MUTED, anchor="w"),
                      hilfe.WISSEN_SPALTEN.get(h, "")).grid(row=0, column=c, sticky="w", padx=6, pady=(6, 4))
        self.rows = []
        for i, d in enumerate(self.w.doc_rows(name), start=1): self._row(i, d)
        if len(self.rows) == 0:
            ctk.CTkLabel(tab, text="Noch keine Dokumente. «+ Dokumente hinzufügen …» (PDF mit Text, Word, Text, Markdown).",
                         font=G.font(12), text_color=G.MUTED).grid(row=1, column=0, columnspan=8, pady=30)
        self.hint = ctk.CTkLabel(self.right, text="", font=G.font(11), text_color=G.ERR, anchor="w", justify="left")
        self.hint.grid(row=4, column=0, sticky="ew", pady=(8, 0)); self.show_hints()
        hilfe.auto(self.right, "wissen")
        self.refresh_list()

    def _row(self, i, d):
        G, tab = self.G, self.tab
        hilfe.tip(ctk.CTkLabel(tab, text=d["datei"] + ("" if d["vorhanden"] else "  (fehlt)"), font=G.font(11),
                               text_color=G.INK if d["vorhanden"] else G.ERR, anchor="w"),
                  hilfe.WISSEN_SPALTEN["Datei"]).grid(row=i, column=0, sticky="w", padx=6, pady=2)
        e_k = ctk.CTkEntry(tab, height=26, font=G.font(11)); e_k.insert(0, d.get("kurz", "")); e_k.grid(row=i, column=1, sticky="ew", padx=4)
        e_t = ctk.CTkEntry(tab, height=26, font=G.font(11)); e_t.insert(0, d.get("titel", "")); e_t.grid(row=i, column=2, sticky="ew", padx=4)
        o_a = ctk.CTkOptionMenu(tab, values=list(ARTEN.values()), height=26, font=G.font(11), dynamic_resizing=False, width=130,
                                fg_color=G.BUBBLE, button_color=G.BORDER, text_color=G.INK, command=lambda _v: self.touch())
        o_a.set(ARTEN.get(d.get("art", "auto"), ARTEN["auto"])); o_a.grid(row=i, column=3, sticky="ew", padx=4)
        e_s = ctk.CTkEntry(tab, height=26, width=90, font=G.font(11), placeholder_text="TT.MM.JJJJ")
        if d.get("stand"): e_s.insert(0, d["stand"])
        e_s.grid(row=i, column=4, sticky="ew", padx=4)
        v_p = tk.BooleanVar(value=bool(d.get("pflicht")))
        hilfe.tip(ctk.CTkCheckBox(tab, text="", variable=v_p, width=24, command=self.touch),
                  hilfe.WISSEN_SPALTEN["Pflicht"]).grid(row=i, column=5, padx=4)
        db = d.get("db")
        st = "neu – noch nicht abgeglichen" if not db else \
            f"{'Artikel' if db[0].get('art') == 'recht' else 'Text'} · {db[1]} Stücke · {db[2]} Vektoren"
        hilfe.tip(ctk.CTkLabel(tab, text=st, font=G.font(10), text_color=G.MUTED, anchor="w"),
                  hilfe.WISSEN_SPALTEN["Status"]).grid(row=i, column=6, sticky="w", padx=6)
        ctk.CTkButton(tab, text="✕", width=28, height=26, corner_radius=6, fg_color="transparent", hover_color=G.BORDER,
                      text_color=G.MUTED, command=lambda f=d["datei"]: self.remove(f)).grid(row=i, column=7, padx=4)
        for e in (e_k, e_t, e_s): e.bind("<KeyRelease>", lambda ev: self.touch())
        for wd, col in ((e_k, "Kürzel"), (e_t, "Titel"), (o_a, "Art"), (e_s, "Stand")): hilfe.tip(wd, hilfe.WISSEN_SPALTEN[col])
        self.rows.append({"datei": d["datei"], "kurz": e_k, "titel": e_t, "art": o_a, "stand": e_s, "pflicht": v_p})
        if d.get("neu"): self.touch()                                  # Datei im Ordner, aber noch nicht eingetragen

    def touch(self):
        self.dirty = True
        if self.lbl_state.winfo_exists(): self.lbl_state.configure(text="● nicht gespeichert", text_color="#F59E0B")

    def show_hints(self):
        st = self.w.status(self.cur); msgs = []
        if st["fehlend"]: msgs.append("Pflichtdokument fehlt: " + ", ".join(st["fehlend"]))
        if st["veraltet"]: msgs.append("Stand prüfen (älter als erlaubt): " + ", ".join(st["veraltet"]))
        if st.get("fehler"): msgs.append(st["fehler"])
        self.hint.configure(text="   ".join(msgs))

    # ------------------------------------------------------------------ Aktionen
    def collect(self):
        from .wissen import parse_date
        m = dict(self.man); errs = []
        m["name"] = self.e_name.get().strip() or self.cur
        m["beschreibung"] = self.t_desc.get("1.0", "end").strip()
        m["im_chat"] = bool(self.v_chat.get())
        try: m["max_alter_monate"] = max(0, int(self.e_age.get().strip() or 0))
        except ValueError: errs.append("Alter: bitte eine ganze Zahl")
        docs, kurz = [], set()
        for r in self.rows:
            k, stand = r["kurz"].get().strip(), r["stand"].get().strip()
            if not k: errs.append(f"{r['datei']}: Kürzel fehlt")
            elif k.lower() in kurz: errs.append(f"Kürzel «{k}» doppelt")
            kurz.add(k.lower())
            if stand and parse_date(stand) is None: errs.append(f"{r['datei']}: Stand «{stand}» – bitte TT.MM.JJJJ")
            docs.append({"datei": r["datei"], "kurz": k, "titel": r["titel"].get().strip(), "art": ARTEN_R[r["art"].get()],
                         "stand": stand, "pflicht": bool(r["pflicht"].get())})
        m["dokumente"] = docs
        return m, errs

    def save(self):
        m, errs = self.collect()
        if errs: messagebox.showerror("Wissen", "Bitte korrigieren:\n- " + "\n- ".join(errs), parent=self.win); return
        self.w.save_manifest(self.cur, m); self.dirty = False
        self.lbl_state.configure(text="gespeichert – Abgleich läuft …", text_color=self.G.MUTED)
        self.app.w.submit("wissen_sync", [self.cur])
        self.refresh_list()

    def add(self):
        if self.dirty:
            m, errs = self.collect()
            if not errs: self.w.save_manifest(self.cur, m)
        fs = filedialog.askopenfilenames(parent=self.win, title="Dokumente hinzufügen",
                                         filetypes=[("Dokumente", "*.pdf *.docx *.txt *.md"), ("Alle Dateien", "*.*")])
        if not fs: return
        try: self.w.add_files(self.cur, fs)
        except Exception as e: messagebox.showerror("Wissen", str(e), parent=self.win); return
        self.show(self.cur)
        self.lbl_state.configure(text="Kürzel, Art und Stand ergänzen, dann «Speichern & abgleichen»", text_color="#F59E0B")
        self.dirty = True

    def remove(self, datei):
        if not messagebox.askyesno("Wissen", f"«{datei}» aus der Sammlung entfernen?\n\nDie Datei wird nach "
                                   f"wissen\\{self.cur}\\_entfernt verschoben (nicht gelöscht).", parent=self.win): return
        self.w.remove_file(self.cur, datei); self.show(self.cur)
        self.app.w.submit("wissen_sync", [self.cur])

    def on_status(self, st):
        """Ereignis wissen_status aus dem Worker (nach dem Abgleich)."""
        if not self.alive() or self.cur not in st or self.dirty: return
        self.show(self.cur)
        x = st[self.cur]
        self.lbl_state.configure(text=f"abgeglichen · {len(x['dokumente'])} Dokumente", text_color=self.G.OK)


class WissenPanel(WissenWindow):
    """v36: dieselbe Dokumenttabelle, eingebettet in einen Reiter (Wissen eines Workflow-Pakets)."""
    def __init__(self, app, parent, name):
        from . import gui as G
        self.G, self.app = G, app
        self.w = Wissen(lambda: None, lambda *a: None)
        self.cur, self.rows, self.dirty = None, [], False
        self.win = parent.winfo_toplevel(); self.right = parent
        self.right.grid_columnconfigure(0, weight=1); self.right.grid_rowconfigure(3, weight=1)
        from .wissen import folder
        f = folder(name); f.mkdir(parents=True, exist_ok=True)
        if not (f / "sammlung.json").exists(): self.w.save_manifest(name, {"name": name, "im_chat": False, "max_alter_monate": 12, "dokumente": []})
        self.show(name)

    def refresh_list(self): pass
    def alive(self): return self.right is not None and self.right.winfo_exists()
