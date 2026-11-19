# aura/memos_gui.py — Werkzeuge › Memos. Version 20261117v266
# Liste der Tage (neueste zuerst; je Tag eine Datei mit allen Memos), Inhalt bearbeiten, löschen (nach _geloescht), Datei/Ordner öffnen.
# Aufgenommen wird oben in der Leiste (Knopf «Memo», mikrofon.Memo). Änderungen werden sofort neu eingelesen.
import os
from tkinter import messagebox
import customtkinter as ctk
from .connectors import memos as M

F = "Segoe UI"
def font(size=13, weight="normal"): return ctk.CTkFont(family=F, size=size, weight=weight)
SIDE, CARD, BORDER = ("#E7EAE3", "#0C0F0D"), ("#EDEFEA", "#232B24"), ("#C9CEC3", "#303A31")
INK, MUTED = ("#1C211C", "#E8ECE4"), ("#525A50", "#A3AD9F")
ACCENT, ACCENT_HI = "#B3121D", "#8E0E17"
WAHL = ("#D8DDD2", "#303A31")


class MemoWindow:
    def __init__(self, app):
        self.app = app; self.cur = None; self.dirty = False; self.knoepfe = {}
        self.body = app.view("memos", "Werkzeuge › Memos")
        self.body.grid_columnconfigure(1, weight=1); self.body.grid_rowconfigure(1, weight=1)
        kopf = ctk.CTkFrame(self.body, fg_color="transparent"); kopf.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(8, 6))
        self.l_ordner = ctk.CTkLabel(kopf, text="", font=font(11), text_color=MUTED, anchor="w"); self.l_ordner.pack(side="left")
        ctk.CTkButton(kopf, text="Ordner öffnen", height=28, corner_radius=0, font=font(11), fg_color=CARD, hover_color=BORDER,
                      text_color=INK, command=self._ordner).pack(side="right")
        ctk.CTkButton(kopf, text="Ordner wählen …", height=28, corner_radius=0, font=font(11), fg_color=CARD, hover_color=BORDER,
                      text_color=INK, command=self._ordner_waehlen).pack(side="right", padx=6)
        self.lst = ctk.CTkScrollableFrame(self.body, width=300, fg_color=CARD, corner_radius=0)
        self.lst.grid(row=1, column=0, sticky="nsw", padx=(24, 8), pady=(0, 16)); self.lst.grid_columnconfigure(0, weight=1)
        ed = ctk.CTkFrame(self.body, fg_color="transparent"); ed.grid(row=1, column=1, sticky="nsew", padx=(8, 24), pady=(0, 16))
        ed.grid_columnconfigure(0, weight=1); ed.grid_rowconfigure(3, weight=1)
        self.l_info = ctk.CTkLabel(ed, text="Tag links wählen.", font=font(11), text_color=MUTED, anchor="w")
        self.l_info.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(ed, text="Je Memo ein Abschnitt «## Zeit · Thema». Alles ist frei bearbeitbar.", font=font(10),
                     text_color=MUTED, anchor="w").grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.t_text = ctk.CTkTextbox(ed, wrap="word", corner_radius=0, font=font(13), state="disabled")
        self.t_text.grid(row=3, column=0, sticky="nsew")
        self.t_text.bind("<Key>", lambda e: self._geaendert(), add="+")
        unten = ctk.CTkFrame(ed, fg_color="transparent"); unten.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.b_save = ctk.CTkButton(unten, text="Speichern", width=110, height=30, corner_radius=0, font=font(12, "bold"),
                                    fg_color=ACCENT, hover_color=ACCENT_HI, command=self._speichern, state="disabled")
        self.b_save.pack(side="left")
        self.b_open = ctk.CTkButton(unten, text="Datei öffnen", width=110, height=30, corner_radius=0, font=font(12), fg_color=CARD,
                                    hover_color=BORDER, text_color=INK, command=self._oeffnen, state="disabled")
        self.b_open.pack(side="left", padx=6)
        self.b_del = ctk.CTkButton(unten, text="Löschen", width=90, height=30, corner_radius=0, font=font(12), fg_color="transparent",
                                   border_width=1, border_color=ACCENT, hover_color=BORDER, text_color=ACCENT, command=self._loeschen,
                                   state="disabled")
        self.b_del.pack(side="right")
        self.refresh()

    def alive(self):
        try: return bool(self.body.winfo_exists())
        except Exception: return False

    # ---- Liste
    def refresh(self, waehle=None):
        self.l_ordner.configure(text=f"Ablage: {M.ordner(self.app.s)}")
        for c in self.lst.winfo_children(): c.destroy()
        self.knoepfe = {}; dateien = M.liste(self.app.s)
        if not dateien:
            ctk.CTkLabel(self.lst, text="Noch keine Memos.\nAufnehmen oben mit «Memo».", font=font(11), text_color=MUTED,
                         justify="left").grid(row=0, column=0, sticky="w", padx=10, pady=10)
        for i, p in enumerate(dateien):
            try: n = M.anzahl(M.lesen(p))
            except OSError: continue
            datum = p.name[:10] if p.name[4:5] == "-" else ""
            name = f"{datum[8:10]}.{datum[5:7]}.{datum[:4]}" if datum else p.stem
            if not p.name.endswith("_Memos.md") and datum: name += "  " + p.stem[11:]          # ältere Einzeldatei
            b = ctk.CTkButton(self.lst, text=f"{name}  ·  {n} Memo{'s' if n != 1 else ''}", anchor="w",
                              height=30, corner_radius=0, font=font(12), fg_color="transparent", hover_color=BORDER,
                              text_color=INK, command=lambda p=p: self._waehlen(p))
            b.grid(row=i, column=0, sticky="ew", pady=1); self.knoepfe[str(p)] = b
        ziel = waehle or (self.cur if self.cur and self.cur.exists() else None)
        if ziel and ziel.exists(): self._waehlen(ziel, frage=False)
        else: self._leer()

    def _leer(self):
        self.cur = None; self.dirty = False
        self.t_text.configure(state="normal"); self.t_text.delete("1.0", "end")
        for w in (self.t_text, self.b_save, self.b_open, self.b_del): w.configure(state="disabled")
        self.l_info.configure(text="Tag links wählen.")

    def _waehlen(self, p, frage=True):
        if frage and self.dirty and self.cur and p != self.cur:
            if not messagebox.askyesno("Memo", "Änderungen am offenen Tag verwerfen?", parent=self.app.root): return
        try: inhalt = M.lesen(p)
        except OSError as e: messagebox.showerror("Memo", f"Nicht lesbar: {e}", parent=self.app.root); return
        self.cur = p
        for w in (self.t_text, self.b_open, self.b_del): w.configure(state="normal")
        self.t_text.delete("1.0", "end"); self.t_text.insert("1.0", inhalt)
        self.dirty = False; self.b_save.configure(state="disabled"); self.l_info.configure(text=p.name)
        for k, b in self.knoepfe.items(): b.configure(fg_color=WAHL if k == str(p) else "transparent")

    def _geaendert(self):
        if self.cur is None: return
        self.dirty = True; self.b_save.configure(state="normal"); self.l_info.configure(text=f"{self.cur.name} · geändert")

    # ---- Aktionen
    def _speichern(self):
        if self.cur is None: return
        inhalt = self.t_text.get("1.0", "end").strip()
        if not inhalt: messagebox.showwarning("Memo", "Der Inhalt ist leer. Zum Entfernen «Löschen» wählen.", parent=self.app.root); return
        try: M.aendern(self.cur, inhalt)
        except Exception as e: messagebox.showerror("Memo", f"Nicht gespeichert: {e}", parent=self.app.root); return
        self.dirty = False; self.refresh(waehle=self.cur)
        self.app.status.configure(text=f"Gespeichert: {self.cur.name} – wird neu eingelesen."); self.app.w.submit("memo_einlesen")

    def _loeschen(self):
        if self.cur is None: return
        if not messagebox.askyesno("Memo", f"Alle Memos dieses Tages löschen?\n{self.cur.name}\n\nEinzelne Memos entfernst du "
                                   "stattdessen im Text und speicherst.\n\nDie Datei kommt in den Unterordner «_geloescht» "
                                   "und wird aus AURA entfernt.", parent=self.app.root): return
        try: M.loeschen(self.cur)
        except Exception as e: messagebox.showerror("Memo", f"Nicht gelöscht: {e}", parent=self.app.root); return
        self.cur = None; self.refresh()
        self.app.status.configure(text="Memos des Tages gelöscht."); self.app.w.submit("memo_einlesen")

    def _oeffnen(self):
        if self.cur and self.cur.exists(): os.startfile(str(self.cur))

    def _ordner(self):
        d = M.ordner(self.app.s); d.mkdir(parents=True, exist_ok=True); os.startfile(str(d))

    def _ordner_waehlen(self):
        self.app.pick_memo_folder(); self.cur = None; self.refresh()
