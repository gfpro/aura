# aura/glossar_gui.py — Ansicht «Glossar» (Wissen). Version 20261105v198
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk
from . import glossar as GL

F = "Segoe UI"
def font(size=13, weight="normal"): return ctk.CTkFont(family=F, size=size, weight=weight)
INK, MUTED, CARD = ("#1C211C", "#E8ECE4"), ("#525A50", "#A3AD9F"), ("#EDEFEA", "#232B24")
ACCENT, ACCENT_HI = "#B3121D", "#8E0E17"

class GlossarFenster:
    def __init__(self, app):
        b = app.view("glossar", "Glossar"); self.body = b
        b.grid_columnconfigure(0, weight=1); b.grid_rowconfigure(1, weight=1)
        k = ctk.CTkFrame(b, fg_color="transparent"); k.grid(row=0, column=0, sticky="ew", padx=14, pady=10)
        ctk.CTkButton(k, text="Excel hochladen", height=30, corner_radius=0, fg_color=ACCENT, hover_color=ACCENT_HI, font=font(12),
                      command=self.hochladen).pack(side="left")
        self.info = ctk.CTkLabel(k, text="", font=font(12), text_color=MUTED); self.info.pack(side="left", padx=12)
        self.t = ttk.Treeview(b, columns=("b", "d", "t"), show="headings")
        for c, n, w in (("b", "Begriff", 200), ("d", "Bedeutung", 520), ("t", "Typ", 140)):
            self.t.heading(c, text=n); self.t.column(c, width=w, anchor="w")
        self.t.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.zeigen()

    def alive(self):
        try: return bool(self.body.winfo_exists())
        except Exception: return False

    def zeigen(self):
        self.t.delete(*self.t.get_children()); e = GL.laden()
        for x in e: self.t.insert("", "end", values=(x["begriff"], x["bedeutung"], x.get("typ", "")))
        self.info.configure(text=f"{len(e)} Einträge. Ein Upload ersetzt alles. Spalten: Begriff, Bedeutung, Typ. Bleibt auf diesem Rechner.")

    def hochladen(self):
        p = filedialog.askopenfilename(filetypes=[("Excel oder CSV", "*.xlsx *.csv")])
        if not p: return
        try: e, weg = GL.einlesen(p)
        except Exception as x: messagebox.showerror("Glossar", str(x)); return
        if not e: messagebox.showerror("Glossar", "Keine Einträge gefunden."); return
        GL.speichern(e); self.zeigen()
        if weg: self.info.configure(text=f"{len(e)} Einträge, {weg} unvollständige Zeilen übersprungen.")
