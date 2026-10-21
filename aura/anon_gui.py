# aura/anon_gui.py — Werkzeug «Text anonymisieren» (Vollansicht) und Assistent «Begriffsliste». Version 20261021v114
# v114: Hinweiskarte umbricht sauber; Prüfen: Maus über Markierung zeigt Herkunft, Rechtsklick = alle gleichen ab-/anwählen,
#       ruhigere Darstellung (Absätze, Seitenmarken); Assistent: Schalter «Nachnamen auch allein ersetzen».
# Ablauf wie tiseR: 1 Text wählen -> 2 Markierungen prüfen (blau Muster/Liste, orange Sprachmodell, grün von Hand, grau abgewählt)
# -> 3 Freigeben & ersetzen -> Kopieren/Speichern. Nichts wird gespeichert ausser der Begriffsliste (data\anon\begriffe.csv).
import re, tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
import customtkinter as ctk
from . import anon, hilfe
from .config import load_settings

F = "Segoe UI"
def font(size=13, weight="normal"): return ctk.CTkFont(family=F, size=size, weight=weight)
SIDE, CARD, BORDER = ("#FFFFFF", "#10172E"), ("#EEF0F7", "#18213D"), ("#E1E4EE", "#263156")
INK, MUTED = ("#111827", "#E6E9F2"), ("#6B7280", "#8E98B5")
ACCENT, ACCENT_HI = "#6E56F8", "#5A43E0"
WARN_BG, WARN_INK = ("#FFF4E5", "#3A2A10"), ("#7A4B00", "#FFD089")
# Markierungsfarben (Hintergrund hell, Schrift dunkel – lesbar in Hell und Dunkel)
FARBE = {"muster": "#BFDBFE", "begriff": "#BFDBFE", "llm": "#FED7AA", "manuell": "#BBF7D0"}
GRAU = "#D1D5DB"
EINSTUFUNG = ("Wichtig: Ein anonymisierter Text behält seine Einstufung (z.B. INTERN oder VERTRAULICH). Er darf nur dorthin, "
              "wo auch das Original hin darf. AURA erkennt keine heiklen Inhalte wie Beträge, Systemschwächen oder Pläne – "
              "das prüfst du selbst.")


class AnonWindow:
    def __init__(self, app):
        self.app = app
        self.body = app.view("anon", "Werkzeuge › Text anonymisieren")
        self.body.grid_columnconfigure(0, weight=1); self.body.grid_rowconfigure(0, weight=1)
        self.text, self.hits, self.name, self.res = "", [], "", ""
        self.scanning = False
        self.frame = None
        if not anon.BEGRIFFE.exists(): self.screen_start(erstmals=True)
        else: self.screen_start()

    def alive(self):
        try: return bool(self.body.winfo_exists())
        except Exception: return False

    def show(self): self.app.show_view("anon")

    # ------------------------------------------------------------------ Rahmen
    def _new(self, schritt, titel):
        if self.frame is not None:
            try: self.frame.destroy()
            except Exception: pass
        f = self.frame = ctk.CTkFrame(self.body, fg_color="transparent")
        f.grid(row=0, column=0, sticky="nsew", padx=28, pady=(6, 14)); f.grid_columnconfigure(0, weight=1)
        hd = ctk.CTkFrame(f, fg_color="transparent"); hd.grid(row=0, column=0, sticky="ew"); hd.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hd, text=titel, font=font(22, "bold"), text_color=INK, anchor="w").grid(row=0, column=0, sticky="w")
        if schritt: ctk.CTkLabel(hd, text=schritt, font=font(12), text_color=MUTED, anchor="w").grid(row=1, column=0, sticky="w")
        return f

    def _banner(self, f, r, text=EINSTUFUNG):
        b = ctk.CTkFrame(f, fg_color=WARN_BG, corner_radius=10); b.grid(row=r, column=0, sticky="ew", pady=(10, 8))
        lb = ctk.CTkLabel(b, text="⚠  " + text, font=font(12), text_color=WARN_INK, justify="left", anchor="w", wraplength=820)
        lb.pack(fill="x", padx=14, pady=10)
        b.bind("<Configure>", lambda e, l=lb: l.configure(wraplength=max(300, e.width - 40)), add="+")
        return b

    def _btn(self, parent, text, cmd, main=False, **kw):
        return ctk.CTkButton(parent, text=text, command=cmd, height=34, corner_radius=8, font=font(13, "bold" if main else "normal"),
                             fg_color=ACCENT if main else CARD, hover_color=ACCENT_HI if main else BORDER,
                             text_color="white" if main else INK, **kw)

    def _box(self, parent, height):
        tb = ctk.CTkTextbox(parent, height=height, font=ctk.CTkFont(family=F, size=13), wrap="word", fg_color=SIDE,
                            text_color=INK, border_width=1, border_color=BORDER, corner_radius=8)
        return tb

    # ------------------------------------------------------------------ 1 Text wählen
    def screen_start(self, erstmals=False):
        f = self._new("Schritt 1 von 3 · Text wählen", "Text anonymisieren")
        self._banner(f, 1)
        r = 2
        n_begr = len(anon.lade_begriffe()) if anon.BEGRIFFE.exists() else 0
        info = ctk.CTkFrame(f, fg_color=CARD, corner_radius=10); info.grid(row=r, column=0, sticky="ew", pady=(0, 10)); r += 1
        info.grid_columnconfigure(0, weight=1)
        if n_begr:
            txt = f"Begriffsliste: {n_begr} Einträge (Personen, Projekte, Standorte …) – nur auf diesem Rechner gespeichert."
            bt = "Begriffsliste bearbeiten …"
        else:
            txt = ("Noch keine Begriffsliste. Ohne Liste findet AURA nur Muster (AHV, IBAN, Mail, Telefon, Koordinaten) und – mit "
                   "Sprachmodell – Namen. Mit Liste werden auch deine heiklen Projekte, Standorte und Partner sicher erkannt.")
            bt = "Begriffsliste einrichten (5 Minuten) …"
        il = ctk.CTkLabel(info, text=txt, font=font(12), text_color=INK, justify="left", anchor="w", wraplength=760)
        il.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))
        info.bind("<Configure>", lambda e, l=il: l.configure(wraplength=max(300, e.width - 40)), add="+")   # v114
        self._btn(info, bt, self.wizard, main=not n_begr).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))
        row = ctk.CTkFrame(f, fg_color="transparent"); row.grid(row=r, column=0, sticky="ew"); r += 1
        self.b_datei = self._btn(row, "📄  Datei wählen und prüfen …", self.pick_file, main=True); self.b_datei.pack(side="left")
        ctk.CTkLabel(row, text="PDF, Word, Text, Markdown, E-Mail (.eml)", font=font(11), text_color=MUTED).pack(side="left", padx=12)
        ctk.CTkLabel(f, text="… oder Text hier einfügen (Strg+V):", font=font(12), text_color=MUTED, anchor="w").grid(
            row=r, column=0, sticky="w", pady=(14, 4)); r += 1
        self.inp = self._box(f, 220); self.inp.grid(row=r, column=0, sticky="nsew"); f.grid_rowconfigure(r, weight=1); r += 1
        opt = ctk.CTkFrame(f, fg_color="transparent"); opt.grid(row=r, column=0, sticky="ew", pady=(10, 0)); r += 1
        opt.grid_columnconfigure(0, weight=1)
        has_llm = self._backend() != "extractive"
        self.llm_var = tk.BooleanVar(value=has_llm and bool(load_settings().get("anon_llm", True)))
        sw = ctk.CTkSwitch(opt, text="Namen zusätzlich mit dem Sprachmodell suchen (gründlicher, etwa 20 Sekunden je Seite)",
                           variable=self.llm_var, font=font(12), text_color=INK, progress_color=ACCENT)
        sw.grid(row=0, column=0, sticky="w")
        if not has_llm: sw.configure(state="disabled", text="Namen mit Sprachmodell suchen – zuerst links unter «Chat» ein Modell wählen")
        self.b_text = self._btn(opt, "Eingefügten Text prüfen ▶", self.scan_text, main=True); self.b_text.grid(row=0, column=1)
        self.status = ctk.CTkLabel(f, text="", font=font(11), text_color=MUTED, anchor="w"); self.status.grid(row=r, column=0, sticky="w", pady=(6, 0))
        hilfe.auto(f, "anon")

    def _backend(self):
        s = self.app.s; ids = [m[0] for m in self.app.models]
        return s.get("llm") if s.get("llm") in ids else "extractive"

    def pick_file(self):
        p = filedialog.askopenfilename(parent=self.app.root, title="Datei zum Anonymisieren wählen",
                                       filetypes=[("Dokumente", "*.pdf *.docx *.txt *.md *.eml"), ("Alle Dateien", "*.*")])
        if p: self._scan(p, True)

    def scan_text(self):
        t = self.inp.get("1.0", "end").strip()
        if not t: self.status.configure(text="Bitte zuerst Text einfügen oder eine Datei wählen."); return
        self._scan(t, False)

    def _scan(self, src, is_file):
        if self.scanning: return
        self.scanning = True
        for b in (self.b_datei, self.b_text):
            try: b.configure(state="disabled")
            except Exception: pass
        s = load_settings(); s["anon_llm"] = bool(self.llm_var.get())
        from .config import save_settings; save_settings(s)
        self.status.configure(text="Prüfe … (Fortschritt links unter «Aufgaben»; «Pause» bricht ab)")
        self.app.w.submit("anon_scan", src, is_file, bool(self.llm_var.get()), self._backend())

    def on_progress(self, text):
        if self.scanning and getattr(self, "status", None) is not None:
            try: self.status.configure(text=text)
            except Exception: pass

    def on_busy(self, busy, name=None):
        if not busy and name == "anon_scan" and self.scanning:        # Job zu Ende ohne Ergebnis (Fehler)
            self.scanning = False
            for b in (getattr(self, "b_datei", None), getattr(self, "b_text", None)):
                try: b.configure(state="normal")
                except Exception: pass

    def on_scan(self, res):
        self.scanning = False
        if res.get("fehler"):
            self.screen_start(); self.status.configure(text="Fehler: " + res["fehler"]); return
        self.text, self.name = res["text"], res.get("name", "")
        self.hits = [dict(h, an=True) for h in res["hits"]]
        self.warn = res.get("warnungen") or []
        self.screen_check()

    # ------------------------------------------------------------------ 2 Prüfen
    def screen_check(self):
        f = self._new("Schritt 2 von 3 · Markierungen prüfen", f"Prüfen: {self.name}")
        r = 1
        leg = ctk.CTkFrame(f, fg_color="transparent"); leg.grid(row=r, column=0, sticky="ew", pady=(10, 4)); r += 1
        self.leg = {}
        for key, lab, col in (("liste", "Muster/Liste", FARBE["muster"]), ("llm", "Sprachmodell", FARBE["llm"]),
                              ("manuell", "von dir", FARBE["manuell"]), ("aus", "abgewählt", GRAU)):
            c = ctk.CTkLabel(leg, text=f"  {lab}  ", font=font(12), fg_color=col, text_color="#111827", corner_radius=6)
            c.pack(side="left", padx=(0, 8)); self.leg[key] = (c, lab)
        ctk.CTkLabel(f, text="Klick auf eine Markierung = nur diese Stelle ab-/anwählen (z.B. «Schweizer» in «Schweizer Bevölkerung»). "
                             "Rechtsklick = alle gleichen ab-/anwählen. Maus darüber zeigt, woher die Markierung stammt. "
                             "Text markieren und «＋ Markierung hinzufügen» = zusätzlich ersetzen.",
                     font=font(12), text_color=MUTED, anchor="w", justify="left", wraplength=900).grid(row=r, column=0, sticky="w"); r += 1
        if self.warn:
            self._banner(f, r, "Hinweise: " + " · ".join(self.warn)); r += 1
        tb = self.tb = self._box(f, 360); tb.grid(row=r, column=0, sticky="nsew", pady=(6, 0)); f.grid_rowconfigure(r, weight=1); r += 1
        t = self.tk = tb._textbox
        t.configure(spacing1=2, spacing3=8, padx=14, pady=10, font=(F, 13), wrap="word")     # v114: ruhigere Darstellung
        t.insert("1.0", self.text)
        t.tag_config("seite", foreground="#8E98B5", font=(F, 11, "bold"), spacing1=14)
        for m in re.finditer(r"^\[Seite \d+\]$", self.text, re.M): t.tag_add("seite", self._idx(m.start()), self._idx(m.end()))
        t.bind("<Key>", self._readonly)
        t.bind("<ButtonRelease-1>", self._click, add="+")
        t.bind("<Button-3>", self._click_all, add="+")
        t.bind("<Motion>", self._hover, add="+")
        for k, col in FARBE.items(): t.tag_config("q_" + k, background=col, foreground="#111827")
        t.tag_config("q_aus", background=GRAU, foreground="#6B7280", overstrike=True)
        t.tag_raise("sel")
        self._paint()
        ctk.CTkLabel(f, text="Tipp: Lies suchend, nicht bestätigend. Oft übersehen: Signaturen, Doppelnamen, Namen mit Umlauten, "
                             "Nachnamen wie «Koch» oder «Berger».", font=font(11), text_color=MUTED, anchor="w").grid(
            row=r, column=0, sticky="w", pady=(6, 0)); r += 1
        bar = ctk.CTkFrame(f, fg_color="transparent"); bar.grid(row=r, column=0, sticky="ew", pady=(8, 0)); r += 1
        self._btn(bar, "← Neuer Text", self.screen_start).pack(side="left")
        self._btn(bar, "＋ Markierung hinzufügen", self.add_sel).pack(side="left", padx=8)
        self._btn(bar, "Freigeben & ersetzen ▶", self.release, main=True).pack(side="right")
        self.status = ctk.CTkLabel(f, text="", font=font(11), text_color=MUTED, anchor="w"); self.status.grid(row=r, column=0, sticky="w")
        hilfe.auto(f, "anon")

    def _readonly(self, e):
        if (e.state & 0x4) and e.keysym.lower() in ("c", "a"): return None      # Strg+C / Strg+A erlaubt
        if e.keysym in ("Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next"): return None
        return "break"

    def _idx(self, off): return f"1.0 + {off} chars"

    def _paint(self):
        t = self.tk
        for tag in t.tag_names():
            if tag.startswith("q_") or tag.startswith("h"): t.tag_remove(tag, "1.0", "end")
        n = {"liste": 0, "llm": 0, "manuell": 0, "aus": 0}
        for i, h in enumerate(self.hits):
            a, b = self._idx(h["start"]), self._idx(h["end"])
            q = h["quelle"] if h["quelle"] in FARBE else "muster"
            t.tag_add(f"h{i}", a, b); t.tag_add("q_" + q if h["an"] else "q_aus", a, b)
            if not h["an"]: n["aus"] += 1
            else: n["liste" if q in ("muster", "begriff") else q] += 1
        for k, (c, lab) in self.leg.items(): c.configure(text=f"  {lab}: {n[k]}  ")
        t.tag_raise("sel")

    def _hit_at(self, e):
        for tag in self.tk.tag_names(f"@{e.x},{e.y}"):
            if re.fullmatch(r"h\d+", tag): return int(tag[1:])
        return None

    def _hover(self, e):
        i = self._hit_at(e)
        self.tk.configure(cursor="hand2" if i is not None else "xterm")
        if i == getattr(self, "_hov", None): return
        self._hov = i
        if i is None: return
        h = self.hits[i]; q = {"muster": "Muster", "begriff": "Begriffsliste", "llm": "Sprachmodell", "manuell": "von dir"}.get(h["quelle"], "")
        n = sum(1 for x in self.hits if x["text"].lower() == h["text"].lower())
        self.status.configure(text=f"«{h['text'][:50]}» · {q}: {h['muster']} → {h['ersatz']} · {'ausgewählt' if h['an'] else 'abgewählt'}"
                                   f" · {n}× im Text (Rechtsklick = alle)")

    def _click_all(self, e):
        i = self._hit_at(e)
        if i is None: return "break"
        w = self.hits[i]["text"].lower(); neu = not self.hits[i]["an"]; n = 0
        for h in self.hits:
            if h["text"].lower() == w: h["an"] = neu; n += 1
        self._paint(); self._hov = None
        self.status.configure(text=f"«{self.hits[i]['text'][:40]}»: {n} Stelle(n) {'angewählt' if neu else 'abgewählt'}.")
        return "break"

    def _click(self, e):
        t = self.tk
        if t.tag_ranges("sel"): return                                   # Maus-Markierung -> nicht umschalten
        for tag in t.tag_names(f"@{e.x},{e.y}"):
            if re.fullmatch(r"h\d+", tag):
                h = self.hits[int(tag[1:])]; h["an"] = not h["an"]; self._paint(); return

    def add_sel(self):
        t = self.tk
        try: a, b = t.index("sel.first"), t.index("sel.last")
        except tk.TclError: self.status.configure(text="Zuerst Text mit der Maus markieren."); return
        sel = t.get(a, b)
        s = len(t.get("1.0", a)); e = s + len(sel)
        if self.text[s:e] != sel:                                        # tiseR 6.3: Positionen absichern
            k = self.text.find(sel, max(0, s - 200))
            if k < 0 or not sel.strip(): self.status.configure(text="Markierung nicht eindeutig – nichts hinzugefügt."); return
            s, e = k, k + len(sel)
        sel = sel.strip()
        if not sel: return
        s = self.text.find(sel, s)
        e = s + len(sel)
        self.hits = [h for h in self.hits if h["an"] or not (h["start"] < e and s < h["end"])]   # abgewählte, die überlappen: weg
        on = [h for h in self.hits if h["an"]]
        neu = anon.alle_vorkommen(self.text, sel, on, "manuell", "[GESCHWAERZT]")
        if not neu and anon.frei(on, s, e):                              # Wortteil (keine Wortgrenze): genau diese Stelle
            neu = [{"start": s, "end": e, "text": sel, "muster": "manuell", "ersatz": "[GESCHWAERZT]", "quelle": "manuell",
                    "gruppe": "manuell|" + sel.lower()}]
        for h in neu: h["an"] = True
        self.hits = sorted(self.hits + neu, key=lambda h: h["start"])
        t.tag_remove("sel", "1.0", "end"); self._paint()
        self.status.configure(text=f"«{sel[:40]}»: {len(neu)} Stelle(n) hinzugefügt." if neu else "Bereits markiert.")

    # ------------------------------------------------------------------ 3 Ergebnis
    def release(self):
        n = sum(1 for h in self.hits if h["an"])
        if not n and not messagebox.askyesno("Nichts markiert", "Es ist keine Stelle markiert. Text trotzdem unverändert übernehmen?",
                                              parent=self.app.root): return
        self.res, n = anon.ersetzen(self.text, self.hits)
        f = self._new("Schritt 3 von 3 · Ergebnis", f"Anonymisiert: {self.name}")
        self._banner(f, 1)
        ctk.CTkLabel(f, text=f"{n} Stellen ersetzt. Gleiche Personen tragen im ganzen Text denselben Platzhalter "
                             "(z.B. [PERSON_1]). Eine Rückübersetzung gibt es nicht.",
                     font=font(12), text_color=MUTED, anchor="w", justify="left", wraplength=900).grid(row=2, column=0, sticky="w")
        tb = self._box(f, 380); tb.grid(row=3, column=0, sticky="nsew", pady=(6, 0)); f.grid_rowconfigure(3, weight=1)
        tb.insert("1.0", self.res); tb.configure(state="disabled")
        bar = ctk.CTkFrame(f, fg_color="transparent"); bar.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self._btn(bar, "← Zurück zum Prüfen", self.screen_check).pack(side="left")
        self._btn(bar, "Neuer Text", self.screen_start).pack(side="left", padx=8)
        self._btn(bar, "Speichern als .txt …", self.save).pack(side="right")
        self._btn(bar, "Kopieren", self.copy, main=True).pack(side="right", padx=8)
        self.status = ctk.CTkLabel(f, text="", font=font(11), text_color=MUTED, anchor="w"); self.status.grid(row=5, column=0, sticky="w")
        hilfe.auto(f, "anon")

    def copy(self):
        self.app.root.clipboard_clear(); self.app.root.clipboard_append(self.res)
        self.status.configure(text="In die Zwischenablage kopiert. Einstufung des Originals beachten.")

    def save(self):
        stem = Path(self.name).stem if self.name and self.name != "eingefügter Text" else "text"
        p = filedialog.asksaveasfilename(parent=self.app.root, initialfile=f"{stem}_anonymisiert.txt", defaultextension=".txt",
                                         filetypes=[("Text", "*.txt")])
        if p:
            Path(p).write_text(self.res, encoding="utf-8"); self.status.configure(text=f"Gespeichert: {p}")

    # ------------------------------------------------------------------ Assistent «Begriffsliste»
    def wizard(self):
        rows = anon.lade_begriffe()
        self.wz = {k[0]: anon.gruppen(rows, k[0]) for k in anon.KATEGORIEN}
        self.wz_eigene = [r for r in rows if r["Kategorie"] not in anon.KAT]
        self.wz_page = 0; self._wz_show()

    def _wz_take(self):
        if getattr(self, "wz_box", None) is not None and self.wz_page < len(anon.KATEGORIEN):
            try:
                kat = anon.KATEGORIEN[self.wz_page][0]
                self.wz[kat] = [l.strip() for l in self.wz_box.get("1.0", "end").split("\n") if l.strip()]
            except Exception: pass

    def _wz_go(self, d):
        self._wz_take(); self.wz_page = max(0, min(len(anon.KATEGORIEN), self.wz_page + d)); self._wz_show()

    def _wz_show(self):
        n = len(anon.KATEGORIEN) + 1; p = self.wz_page
        f = self._new(f"Begriffsliste · Schritt {p + 1} von {n}", "Begriffsliste einrichten")
        self.wz_box = None
        ctk.CTkLabel(f, text="Die Liste bleibt nur auf diesem Rechner. Sie wird nie durchsucht, nie ans Sprachmodell gegeben, "
                             "nie exportiert und nie auf GitHub gestellt.", font=font(11), text_color=MUTED, anchor="w",
                     justify="left", wraplength=900).grid(row=1, column=0, sticky="w", pady=(4, 10))
        bar = ctk.CTkFrame(f, fg_color="transparent")
        if p < len(anon.KATEGORIEN):
            kat, titel, ersatz, frage, erkl, bsp = anon.KATEGORIEN[p]
            ctk.CTkLabel(f, text=f"{titel}: {frage}", font=font(16, "bold"), text_color=INK, anchor="w").grid(row=2, column=0, sticky="w")
            ctk.CTkLabel(f, text=f"{erkl}  Im Text erscheint dafür {ersatz[:-1]}_1], {ersatz[:-1]}_2] …  Leer lassen, wenn nichts zutrifft.",
                         font=font(12), text_color=MUTED, anchor="w", justify="left", wraplength=900).grid(row=3, column=0, sticky="w", pady=(2, 6))
            tb = self.wz_box = self._box(f, 260); tb.grid(row=4, column=0, sticky="nsew"); f.grid_rowconfigure(4, weight=1)
            if self.wz[kat]: tb.insert("1.0", "\n".join(self.wz[kat]))
            ctk.CTkLabel(f, text="Beispiel:  " + bsp.replace("\n", "  ·  "), font=font(11), text_color=MUTED, anchor="w").grid(
                row=5, column=0, sticky="w", pady=(4, 0))
            tools = ctk.CTkFrame(f, fg_color="transparent"); tools.grid(row=6, column=0, sticky="w", pady=(8, 0))
            self._btn(tools, "Aus Datei übernehmen …", self._wz_import).pack(side="left")
            if kat == "person":
                self._btn(tools, "Vorschläge aus meinen Mails …", lambda: self.app.w.submit("anon_absender")).pack(side="left", padx=8)
                self.nach_var = tk.BooleanVar(value=bool(load_settings().get("anon_nachname_allein", True)))   # v114
                ctk.CTkSwitch(tools, text="Nachnamen auch allein ersetzen (findet mehr, aber z.B. auch «Schweizer» in «Schweizer Bevölkerung»)",
                              variable=self.nach_var, font=font(12), text_color=INK, progress_color=ACCENT,
                              command=self._nach_save).pack(side="left", padx=12)
            tb.focus_set()
        else:
            self._wz_summary(f)
        bar.grid(row=8, column=0, sticky="ew", pady=(12, 0))
        self._btn(bar, "Abbrechen", self.screen_start).pack(side="left")
        if p > 0: self._btn(bar, "← Zurück", lambda: self._wz_go(-1)).pack(side="left", padx=8)
        if p < len(anon.KATEGORIEN): self._btn(bar, "Weiter →", lambda: self._wz_go(+1), main=True).pack(side="right")
        else: self._btn(bar, "Speichern ✓", self._wz_save, main=True).pack(side="right")
        self.status = ctk.CTkLabel(f, text="", font=font(11), text_color=MUTED, anchor="w"); self.status.grid(row=9, column=0, sticky="w")
        hilfe.auto(f, "anon")

    def _nach_save(self):
        from .config import save_settings
        s = load_settings(); s["anon_nachname_allein"] = bool(self.nach_var.get()); save_settings(s)

    def _wz_rows(self):
        rows, hinweise = list(self.wz_eigene), []
        allein = bool(load_settings().get("anon_nachname_allein", True))
        for k in anon.KATEGORIEN:
            r, h = anon.zeilen_zu_begriffen(k[0], self.wz[k[0]], allein) if k[0] == "person" else anon.zeilen_zu_begriffen(k[0], self.wz[k[0]])
            rows += r; hinweise += h
        return rows, hinweise

    def _wz_summary(self, f):
        rows, hinweise = self._wz_rows()
        ctk.CTkLabel(f, text="Zusammenfassung", font=font(16, "bold"), text_color=INK, anchor="w").grid(row=2, column=0, sticky="w")
        box = ctk.CTkScrollableFrame(f, fg_color=CARD, corner_radius=10, height=300); box.grid(row=4, column=0, sticky="nsew")
        f.grid_rowconfigure(4, weight=1)
        for k in anon.KATEGORIEN:
            ctk.CTkLabel(box, text=f"{k[1]}: {len(self.wz[k[0]])}", font=font(13), text_color=INK, anchor="w").pack(anchor="w", padx=10, pady=1)
        if self.wz_eigene:
            ctk.CTkLabel(box, text=f"Übernommene Einträge mit eigenen Regeln: {len(self.wz_eigene)}", font=font(13),
                         text_color=INK, anchor="w").pack(anchor="w", padx=10, pady=1)
        ctk.CTkLabel(box, text=f"→ {len(rows)} Suchbegriffe (inkl. Schreibweise «Nachname Vorname»)", font=font(12),
                     text_color=MUTED, anchor="w").pack(anchor="w", padx=10, pady=(6, 4))
        for h in hinweise:
            ctk.CTkLabel(box, text="⚠ " + h, font=font(12), text_color=WARN_INK, anchor="w", justify="left",
                         wraplength=820).pack(anchor="w", padx=10, pady=1)

    def _wz_save(self):
        rows, _ = self._wz_rows()
        try: anon.speichere_begriffe(rows)
        except Exception as e: messagebox.showerror("Speichern", f"Begriffsliste nicht gespeichert: {e}", parent=self.app.root); return
        self.screen_start(); self.status.configure(text=f"Begriffsliste gespeichert ({len(rows)} Suchbegriffe).")

    def _wz_import(self):
        p = filedialog.askopenfilename(parent=self.app.root, title="Liste übernehmen (eine Zeile pro Begriff, oder Tabelle wie in tiseR)",
                                       filetypes=[("Listen", "*.txt *.csv *.xlsx *.docx *.md"), ("Alle Dateien", "*.*")])
        if not p: return
        try: rows, lines = anon.importiere(p)
        except Exception as e: self.status.configure(text=f"Datei nicht lesbar: {e}"); return
        self._wz_take()
        kat = anon.KATEGORIEN[self.wz_page][0]
        if lines:
            self.wz[kat] += [l for l in lines if l not in self.wz[kat]]
            msg = f"{len(lines)} Zeilen übernommen – bitte prüfen."
        else:
            n = 0
            for r in rows:
                if r["Kategorie"] in anon.KAT and r["Typ"] == "wort":
                    if r["Gruppe"] not in self.wz[r["Kategorie"]]: self.wz[r["Kategorie"]].append(r["Gruppe"]); n += 1
                elif not any(e["Begriff"] == r["Begriff"] for e in self.wz_eigene): self.wz_eigene.append(r); n += 1
            msg = f"{n} Einträge aus der Tabelle übernommen (auf die passenden Schritte verteilt)."
        self._wz_show(); self.status.configure(text=msg)

    def on_absender(self, lst):
        if not getattr(self, "wz_box", None) or self.wz_page != 0: return
        body = self.app.panel("Vorschläge aus meinen Mails", "anon_vorschlag", 440)
        body.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(body, text="Häufigste Absender. Nur anhaken, wer wirklich geschützt werden muss – nicht alle.",
                     font=font(12), text_color=MUTED, justify="left", wraplength=380, anchor="w").grid(row=0, column=0, sticky="w", padx=16)
        sc = ctk.CTkScrollableFrame(body, fg_color="transparent"); sc.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)
        have = {l.lower() for l in self.wz_box.get("1.0", "end").split("\n")}
        vars_ = []
        for name, c in lst:
            v = tk.BooleanVar(value=False)
            cb = ctk.CTkCheckBox(sc, text=f"{name}   ({c} Mails)", variable=v, font=font(12), text_color=INK, fg_color=ACCENT)
            if name.lower() in have: cb.configure(state="disabled", text=f"{name}   (schon erfasst)")
            cb.pack(anchor="w", pady=2); vars_.append((name, v))
        if not lst: ctk.CTkLabel(sc, text="Keine Absender gefunden (Mails noch nicht eingelesen?).", font=font(12), text_color=MUTED).pack()
        def take():
            sel = [n for n, v in vars_ if v.get()]
            if sel and self.wz_box is not None:
                cur = self.wz_box.get("1.0", "end").rstrip("\n")
                self.wz_box.insert("end", ("\n" if cur.strip() else "") + "\n".join(sel))
            self.app.close_panel()
        self._btn(body, "Übernehmen", take, main=True).grid(row=2, column=0, sticky="e", padx=16, pady=(0, 14))
