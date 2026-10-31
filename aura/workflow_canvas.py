# aura/workflow_canvas.py — Leinwand im Reiter «Bauen»: Workflow als Bild bauen. Version 20261031v152
# (v152: Klick auf einen Pfeil → «Verbindung löschen»)
# (v150: Verbinden – vom Anschluss ● rechts am Knoten auf einen anderen Knoten ziehen, Wert und Feld wählen; Schrift in Pixeln)
# (v149: Klick auf «▶ Start» = Eingaben und Zeitplan rechts; Knöpfe Wissen / Vorlage & Feldplan / Prüfpunkte am passenden Knoten)
# Links die Palette (Bausteine aus workflow/schema.py), in der Mitte die Leinwand, rechts die Details des gewählten Schritts.
# Spalte = Tiefe im Datenfluss (was ein Schritt verwendet, steht links davon), Farbe = Gruppe (Holen / Verarbeiten / Ausgeben).
# Die Pfeile zeigt AURA aus den Verweisen {{schritt.wert}} – man verdrahtet nichts von Hand, es gibt keine zweite Wahrheit neben
# der workflow.json. Die Nummer im Knoten ist die Reihenfolge des Laufs. Bedienung: Klick = Details, Doppelklick = Formular,
# Palette-Klick = neuer Schritt hinter dem gewählten, «◀ früher / später ▶» = Reihenfolge.
# v148: Mausrad = Zoom um den Zeiger, rechte (oder mittlere) Maustaste halten = Leinwand verschieben. Bearbeiten, Testen, Löschen und Speichern macht der bestehende SchrittEditor (workflow_editor.py).
import tkinter as tk
import customtkinter as ctk
from .workflow import graph as GR
from .workflow import schema as S

KW, KH = 190, 74            # Knotengrösse
SW, ZH = 250, 96            # Spaltenbreite, Zeilenhöhe
X0, Y0 = 20, 30             # Rand links und oben
START_X = X0 + SW - KH - 60 # v149: Start-Knoten nahe an der ersten Spalte
BAHNFARBE = {"Holen": "#0F9D7A", "Verarbeiten": "#6E56F8", "Ausgeben": "#D97706"}
STATUS = {"ok": ("#10B981", "Letzter Lauf: ok"), "fehler": ("#E5484D", "Letzter Lauf: Fehler"),
          "nicht gelaufen": ("#9CA3AF", "Im letzten Lauf übersprungen"), "offen": ("#9CA3AF", "Noch nicht gelaufen")}


def _kuerzen(t, n): return t if len(t) <= n else t[:n - 1] + "…"


class Leinwand:
    gewaehlt = None                                    # bleibt über das Neuzeichnen nach dem Speichern erhalten
    z = 1.0                                            # v148: Zoom, bleibt ebenfalls erhalten

    def __init__(self, editor, parent):
        self.ed, self.G = editor, editor.G
        G = self.G
        parent.grid_columnconfigure(1, weight=1); parent.grid_rowconfigure(0, weight=1)
        self._palette(parent)
        mitte = ctk.CTkFrame(parent, fg_color=G.BUBBLE, corner_radius=8, border_width=1, border_color=G.BORDER)
        mitte.grid(row=0, column=1, sticky="nsew", padx=6)
        mitte.grid_columnconfigure(0, weight=1); mitte.grid_rowconfigure(0, weight=1)
        self.c = tk.Canvas(mitte, highlightthickness=0, bd=0, bg=self._f(G.BUBBLE))
        self.c.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        sy = ctk.CTkScrollbar(mitte, command=self.c.yview); sy.grid(row=0, column=1, sticky="ns")
        sx = ctk.CTkScrollbar(mitte, orientation="horizontal", command=self.c.xview); sx.grid(row=1, column=0, sticky="ew")
        self.c.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.detail = ctk.CTkFrame(parent, fg_color=G.BUBBLE, corner_radius=8, width=270, border_width=1, border_color=G.BORDER)
        self.detail.grid(row=0, column=2, sticky="nsew"); self.detail.grid_propagate(False)
        self.c.bind("<ButtonPress-1>", self._press); self.c.bind("<Double-Button-1>", self._doppel)
        self.c.bind("<B1-Motion>", self._ziehen); self.c.bind("<ButtonRelease-1>", self._los)        # v150: Verbinden
        self.c.tag_bind("port", "<Enter>", lambda e: self.c.configure(cursor="hand2"))
        self.c.tag_bind("port", "<Leave>", lambda e: self.c.configure(cursor=""))
        self._link = None
        self.c.bind("<MouseWheel>", self._zoom)                                        # v148: Mausrad = Zoom
        for b in ("<ButtonPress-3>", "<ButtonPress-2>"): self.c.bind(b, lambda e: self.c.scan_mark(e.x, e.y))
        for b in ("<B3-Motion>", "<B2-Motion>"): self.c.bind(b, lambda e: self.c.scan_dragto(e.x, e.y, gain=1))   # Rechts halten = schieben
        self.zeichnen()

    # ------------------------------------------------------------------ Hilfen
    @staticmethod
    def _f(farbe):
        """Farbpaar (hell, dunkel) → eine Farbe für tk.Canvas."""
        if isinstance(farbe, (tuple, list)): return farbe[1] if ctk.get_appearance_mode() == "Dark" else farbe[0]
        return farbe

    def _fo(self, groesse, fett=False):
        f = (self.G.F, -max(6, round(groesse * 1.34 * Leinwand.z)))     # v150: Pixel statt Punkte – passt bei jeder Windows-Skalierung
        return f + ("bold",) if fett else f

    def _zoom(self, e):
        """Mausrad: hinein/hinaus um den Mauszeiger; der Punkt unter dem Zeiger bleibt stehen."""
        alt = Leinwand.z; neu = max(0.4, min(2.5, alt * (1.15 if e.delta > 0 else 1 / 1.15)))
        if abs(neu - alt) < 1e-3: return
        lx, ly = self.c.canvasx(e.x) / alt, self.c.canvasy(e.y) / alt
        Leinwand.z = neu; self.zeichnen()
        b, h = self._groesse
        if b > 0: self.c.xview_moveto(max(0, (lx * neu - e.x) / b))
        if h > 0: self.c.yview_moveto(max(0, (ly * neu - e.y) / h))

    @staticmethod
    def _xy(spalte, zeile):
        return X0 + spalte * SW, Y0 + zeile * ZH

    def _steps(self): return self.ed.raw.get("steps", [])

    def _index(self, sid):
        return next((i for i, s in enumerate(self._steps()) if s.get("id") == sid), None)

    # ------------------------------------------------------------------ Palette
    def _palette(self, parent):
        G = self.G
        p = ctk.CTkScrollableFrame(parent, fg_color="transparent", width=170); p.grid(row=0, column=0, sticky="ns")
        ctk.CTkLabel(p, text="BAUSTEINE", font=G.font(10, "bold"), text_color=G.MUTED).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(p, text="Klick = neuer Schritt hinter dem gewählten", font=G.font(10), text_color=G.MUTED,
                     wraplength=160, justify="left").pack(anchor="w", pady=(0, 6))
        for g in S.GRUPPEN:
            ctk.CTkLabel(p, text=g.upper(), font=G.font(10, "bold"), text_color=BAHNFARBE.get(g, G.MUTED)).pack(anchor="w", pady=(6, 2))
            for typ, m in S.BAUSTEINE.items():
                if m.get("gruppe") != g: continue
                b = ctk.CTkButton(p, text=m["titel"], anchor="w", height=26, corner_radius=6, font=G.font(11), fg_color=G.CARD,
                                  hover_color=G.BORDER, text_color=G.INK, border_width=0,
                                  command=lambda t=typ: self._neu(t))
                b.pack(fill="x", pady=1)
                try:
                    from . import hilfe
                    hilfe.tip(b, m.get("beschreibung", ""))
                except Exception: pass

    def _neu(self, typ):
        i = self._index(Leinwand.gewaehlt)
        self.ed._new(typ, len(self._steps()) if i is None else i + 1)

    # ------------------------------------------------------------------ Zeichnen
    def zeichnen(self):
        G, c = self.G, self.c
        c.delete("all")
        self.g = GR.bauen(self.ed.raw, self.ed.state)
        nodes = self.g["nodes"]
        spalten = max((x["spalte"] for x in nodes), default=0); zeilen = max((x["zeile"] for x in nodes), default=0)
        breite = X0 + (spalten + 1) * SW + 20; hoehe = Y0 + (zeilen + 1) * ZH + 40
        muted = self._f(G.MUTED)
        lx = X0                                                              # Legende der Gruppen
        for g in S.GRUPPEN:
            c.create_rectangle(lx, 8, lx + 10, 18, fill=BAHNFARBE.get(g), outline="")
            c.create_text(lx + 16, 13, text=g, anchor="w", fill=muted, font=self._fo(9)); lx += 110
        for e in self.g["edges"]: self._pfeil(e)                            # Pfeile unter den Knoten
        self._start_knoten()
        for nd in nodes: self._knoten(nd)
        if not nodes:
            c.create_text(X0 + SW, Y0 + KH / 2, anchor="w", fill=muted, font=self._fo(12),
                          text="Noch keine Schritte – links einen Baustein anklicken, zuerst meist «Dateien lesen».")
        z = Leinwand.z; c.scale("all", 0, 0, z, z)                            # Fonts sind schon skaliert (_fo)
        breite, hoehe = max(breite * z, c.winfo_width()), max(hoehe * z, c.winfo_height())
        self._groesse = (breite, hoehe); c.configure(scrollregion=(0, 0, breite, hoehe))
        self._details()

    def _pos(self, sid):
        if sid == "_start": s = self.g["start"]
        else: s = next(x for x in self.g["nodes"] if x["id"] == sid)
        return self._xy(s["spalte"], s["zeile"])

    def _pfeil(self, e):
        try: (x1, y1), (x2, y2) = self._pos(e["von"]), self._pos(e["nach"])
        except StopIteration: return
        farbe = "#9CA3AF" if e["ok"] else "#E5484D"
        if e["von"] == Leinwand.gewaehlt or e["nach"] == Leinwand.gewaehlt: farbe = "#6E56F8" if e["ok"] else farbe
        a, b = (x1 + KW, y1 + KH / 2), (x2, y2 + KH / 2)
        if e["von"] == "_start": a = (START_X + KH, y1 + KH / 2)
        if x2 <= x1:                                                        # Rückverweis: Bogen oben herum
            pts = (x1 + KW / 2, y1, x1 + KW / 2, y1 - 30, x2 + KW / 2, y2 - 30, x2 + KW / 2, y2)
        else:
            dx = max(40, (b[0] - a[0]) / 2)
            pts = (a[0], a[1], a[0] + dx, a[1], b[0] - dx, b[1], b[0], b[1])
        self.c.create_line(*pts, smooth=True, width=2 if farbe != "#9CA3AF" else 1.4, fill=farbe, arrow="last",
                           arrowshape=(9, 10, 4), dash=() if e["ok"] else (5, 3), tags=("kante", f"e:{e['von']}:{e['nach']}"))

    def _start_knoten(self):
        G, s = self.G, self.g["start"]; x, y = self._xy(0, 0)
        x = START_X - 30; tag = ("n:_start",); sel = Leinwand.gewaehlt == "_start"
        self.c.create_oval(x + 30, y, x + 30 + KH, y + KH, fill=self._f(G.BUBBLE), outline="#6E56F8" if sel else "#0F9D7A",
                           width=3 if sel else 2, tags=tag)
        self.c.create_text(x + 30 + KH / 2, y + KH / 2 - 10, text="▶ Start", fill=self._f(G.INK), font=self._fo(11, True), tags=tag)
        info = "Zeitplan" if s["zeitplan"] else "manuell"
        n = len(s["eingaben"])
        self.c.create_text(x + 30 + KH / 2, y + KH / 2 + 6, text=info, fill=self._f(G.MUTED), font=self._fo(9), tags=tag)
        self.c.create_text(x + 30 + KH / 2, y + KH / 2 + 20, text=f"{n} Eingabe{'n' if n != 1 else ''}", fill=self._f(G.MUTED),
                           font=self._fo(8), tags=tag)
        if n: self._port(START_X + KH, y + KH / 2, "_start")

    def _knoten(self, nd):
        G, c = self.G, self.c; x, y = self._xy(nd["spalte"], nd["zeile"]); tag = f"n:{nd['id']}"
        sel = nd["id"] == Leinwand.gewaehlt; rot = bool(nd["probleme"]) or nd["unbekannt"]
        rand = "#E5484D" if rot else ("#6E56F8" if sel else self._f(G.BORDER))
        c.create_rectangle(x + 3, y + 3, x + KW + 3, y + KH + 3, fill=self._f(G.BORDER), outline="", tags=(tag,))   # Schatten
        c.create_rectangle(x, y, x + KW, y + KH, fill=self._f(G.BUBBLE), outline=rand, width=2 if (sel or rot) else 1, tags=(tag,))
        c.create_rectangle(x, y, x + 6, y + KH, fill=BAHNFARBE.get(nd["gruppe"], "#6E56F8"), outline="", tags=(tag,))
        c.create_text(x + 14, y + 10, text=_kuerzen(f"{nd['index'] + 1}  {nd['titel']}", 23), anchor="nw", fill=self._f(G.INK),
                      font=self._fo(10, True), tags=(tag,))
        c.create_text(x + 14, y + 29, text=_kuerzen(f"{nd['baustein']} · {nd['id']}", 30), anchor="nw", fill=self._f(G.MUTED),
                      font=self._fo(9), tags=(tag,))
        unten = ("⚠ " + nd["probleme"][0]) if nd["probleme"] else (nd["kurz"] or "")
        c.create_text(x + 14, y + 48, text=_kuerzen(unten, 34), anchor="nw", fill="#E5484D" if nd["probleme"] else self._f(G.MUTED),
                      font=self._fo(9), tags=(tag,))
        farbe, _ = STATUS.get(nd["status"], STATUS["offen"])
        c.create_oval(x + KW - 16, y + 8, x + KW - 7, y + 17, fill=farbe, outline="", tags=(tag,))
        if nd["wenn"]:                                                      # Bedingung «Nur wenn» als Raute
            cx, cy = x + KW / 2, y
            c.create_polygon(cx, cy - 9, cx + 9, cy, cx, cy + 9, cx - 9, cy, fill="#F59E0B", outline="", tags=(tag,))
        if nd["typ"] == "fuer_jedes":
            c.create_text(x + KW - 12, y + KH - 12, text="↻", fill=self._f(G.MUTED), font=self._fo(12, True), tags=(tag,))
        self._port(x + KW, y + KH / 2, nd["id"])

    def _port(self, x, y, sid):
        """v150: Anschluss rechts am Knoten – von hier eine Verbindung auf einen anderen Knoten ziehen."""
        r = 7
        self.c.create_oval(x - r, y - r, x + r, y + r, fill=self._f(self.G.BUBBLE), outline="#6E56F8", width=2,
                           tags=("port", f"p:{sid}"))

    # ------------------------------------------------------------------ Details rechts
    def _details(self):
        G, d = self.G, self.detail
        for w in d.winfo_children(): w.destroy()
        if Leinwand.gewaehlt == "_start": self._details_start(); return
        nd = next((x for x in self.g["nodes"] if x["id"] == Leinwand.gewaehlt), None)
        if not nd:
            ctk.CTkLabel(d, text="Schritt anklicken für Details – «▶ Start» zeigt Eingaben und Zeitplan.\n\nDoppelklick öffnet das Formular.\n\nVerbinden: vom Kreis ● rechts am Knoten auf einen anderen Knoten ziehen, dann Wert und Feld wählen.\n\nDie Nummer im Knoten ist "
                         "die Reihenfolge des Laufs.\n\nMausrad = Zoom, rechte Maustaste halten = verschieben.\n\nPfeile zeigen, welcher Schritt das Ergebnis eines anderen "
                         "verwendet (rot = Problem).", font=G.font(11), text_color=G.MUTED, justify="left", wraplength=240
                         ).pack(anchor="nw", padx=12, pady=12)
            return
        def zeile(t, f=G.font(11), farbe=G.INK):
            ctk.CTkLabel(d, text=t, font=f, text_color=farbe, justify="left", anchor="w", wraplength=240).pack(anchor="w", padx=12, pady=1)
        zeile(nd["titel"], G.font(13, "bold"))
        zeile(f"{nd['baustein']} · Ergebnis unter «{nd['id']}»", G.font(10), G.MUTED)
        farbe, txt = STATUS.get(nd["status"], STATUS["offen"]); zeile("● " + txt, G.font(10), farbe)
        if nd["wenn"]: zeile(f"Nur wenn: {nd['wenn']}", G.font(10), "#D97706")
        for p in nd["probleme"]: zeile("⚠ " + p, G.font(10), G.ERR)
        if nd["unbekannt"]: zeile("⚠ Kein Formular für diesen Baustein – in der workflow.json bearbeiten.", G.font(10), G.ERR)
        if nd["kurz"]: zeile(nd["kurz"], G.font(10), G.MUTED)
        titel = {x["id"]: x["titel"] for x in self.g["nodes"]}; titel["_start"] = "Eingaben beim Start"
        rein, raus = GR.verwendet(self.g, nd["id"]), GR.verwendet_von(self.g, nd["id"])
        zeile("Verwendet: " + (", ".join(titel.get(x, x) for x in rein) or "–"), G.font(10))
        zeile("Wird verwendet von: " + (", ".join(titel.get(x, x) for x in raus) or "–"), G.font(10))
        bb = ctk.CTkFrame(d, fg_color="transparent"); bb.pack(anchor="w", padx=10, pady=(10, 4))
        i = nd["index"]
        ctk.CTkButton(bb, text="Bearbeiten …", height=28, width=0, fg_color=G.ACCENT, hover_color=G.ACCENT_HI, font=G.font(11, "bold"),
                      command=lambda: self.ed._edit(i)).pack(side="left", padx=2)
        self.ed._mini(bb, "Testen", lambda: self.ed._test(nd["id"])).pack(side="left", padx=2)
        self.ed._mini(bb, "✕", lambda: self.ed._del(i)).pack(side="left", padx=2)
        bb2 = ctk.CTkFrame(d, fg_color="transparent"); bb2.pack(anchor="w", padx=10)
        self.ed._mini(bb2, "◀ früher", lambda: self.ed._move(i, -1)).pack(side="left", padx=2)
        self.ed._mini(bb2, "später ▶", lambda: self.ed._move(i, 1)).pack(side="left", padx=2)
        ress = {"rag": ("Wissen", "📚 Wissen dieses Workflows …"), "word_vorlage": ("Vorlage", "📄 Vorlage & Feldplan …"),
                "pruefliste": ("Prüfliste", "✓ Prüfpunkte …")}.get(nd["typ"])          # v149: Hilfsmittel am passenden Knoten
        if ress and hasattr(self.ed.ww, "ressource"):
            ctk.CTkButton(d, text=ress[1], height=28, fg_color=G.CARD, hover_color=G.BORDER, text_color=G.INK, font=G.font(11),
                          command=lambda: self.ed.ww.ressource(ress[0])).pack(anchor="w", padx=12, pady=(10, 0))

    def _details_start(self):
        """v149: Eingaben beim Start und Zeitplan (früher Kasten «Auslöser» über den Schritten)."""
        G, d, ed = self.G, self.detail, self.ed
        def zeile(t, f=G.font(11), farbe=G.INK):
            ctk.CTkLabel(d, text=t, font=f, text_color=farbe, justify="left", anchor="w", wraplength=240).pack(anchor="w", padx=12, pady=1)
        zeile("▶ Start", G.font(13, "bold"))
        zp = ed.raw.get("zeitplan")
        try:
            from .zeitplan import beschreibung
            zeile(f"Zeitplan: {beschreibung(zp)}\n(läuft, solange AURA offen ist)" if zp else "Manuell – beim Start fragt AURA nach:",
                  G.font(10), G.MUTED)
        except Exception: pass
        ed._mini(d, "Zeitplan …", ed._zeitplan).pack(anchor="w", padx=12, pady=(4, 8))
        zeile("EINGABEN", G.font(10, "bold"), G.MUTED)
        inputs = ed.raw.get("inputs", [])
        if not inputs: zeile("keine", G.font(10), G.MUTED)
        for i, inp in enumerate(inputs):
            row = ctk.CTkFrame(d, fg_color="transparent"); row.pack(fill="x", padx=10, pady=1)
            art = "Dateien" if inp.get("type") == "files" else "Text"
            ctk.CTkLabel(row, text=f"{inp.get('label', inp['id'])}\n{art}{', freiwillig' if inp.get('optional') else ''} · input.{inp['id']}",
                         font=G.font(10), text_color=G.INK, justify="left", anchor="w", wraplength=150).pack(side="left")
            ed._mini(row, "✕", lambda i=i: ed._inp_del(i)).pack(side="right")
            ed._mini(row, "✎", lambda i=i: ed._inp_edit(i)).pack(side="right", padx=2)
        ed._mini(d, "+ Eingabe", lambda: ed._inp_edit(None)).pack(anchor="w", padx=12, pady=(6, 0))

    # ------------------------------------------------------------------ Maus
    def _treffer(self, e):
        x, y = self.c.canvasx(e.x), self.c.canvasy(e.y)                # schon im gezoomten Raum
        for it in reversed(self.c.find_overlapping(x - 1, y - 1, x + 1, y + 1)):
            for t in self.c.gettags(it):
                if t.startswith("n:"): return t[2:]
        return None

    def _port_treffer(self, e):
        x, y = self.c.canvasx(e.x), self.c.canvasy(e.y)
        for it in self.c.find_overlapping(x - 3, y - 3, x + 3, y + 3):
            for t in self.c.gettags(it):
                if t.startswith("p:"): return t[2:]
        return None

    def _press(self, e):
        quelle = self._port_treffer(e)
        if quelle:                                                          # v150: Verbindung beginnt
            x, y = self.c.canvasx(e.x), self.c.canvasy(e.y)
            self._link = {"von": quelle, "x": x, "y": y, "linie": None}; return
        sid = self._treffer(e)
        if sid is None:                                                     # v152: Klick auf einen Pfeil
            k = self._kante_treffer(e)
            if k: self._kante_menu(*k, e.x_root, e.y_root); return
        if sid != Leinwand.gewaehlt: Leinwand.gewaehlt = sid; self.zeichnen()

    def _kante_treffer(self, e):
        x, y = self.c.canvasx(e.x), self.c.canvasy(e.y)
        for it in self.c.find_overlapping(x - 4, y - 4, x + 4, y + 4):
            for t in self.c.gettags(it):
                if t.startswith("e:"): return tuple(t[2:].split(":", 1))
        return None

    def _kante_menu(self, von, nach, mx, my):
        titel = {x["id"]: x["titel"] for x in self.g["nodes"]}; titel["_start"] = "Start"
        m = tk.Menu(self.c, tearoff=0)
        m.add_command(label=f"Verbindung «{titel.get(von, von)}» → «{titel.get(nach, nach)}» löschen",
                      command=lambda: self._kante_loeschen(von, nach))
        m.add_command(label=f"«{titel.get(nach, nach)}» bearbeiten …", command=lambda: self.ed._edit(self._index(nach)))
        m.tk_popup(mx, my)

    def _kante_loeschen(self, von, nach):
        """v152: Entfernt im Ziel alle {{von.…}} (bei «Start»: alle {{input.…}}). «Nur wenn» wird nicht angefasst."""
        import re
        from tkinter import messagebox
        st = self._steps()[self._index(nach)]
        muster = re.compile(r"\{\{\s*" + (r"input" if von == "_start" else re.escape(von)) + r"\.[^}]*\}\}")
        n = [0]
        def weg(v):
            if isinstance(v, str):
                neu, k = muster.subn("", v)
                if k: n[0] += k; neu = re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", neu)).strip()
                return neu
            if isinstance(v, list): return [weg(x) for x in v]
            if isinstance(v, dict): return {k: weg(x) for k, x in v.items()}
            return v
        for k in [k for k in st if k not in ("id", "type", "label", "when")]:
            st[k] = weg(st[k])
            if st[k] in ("", [], {}): st.pop(k)
        if not n[0]:
            messagebox.showinfo("Verbindung", "Der Verweis steht nicht als {{…}} in einem Feld (z.B. in «Nur wenn») – bitte im "
                                "Formular entfernen.", parent=self.ed.ww.win)
            self.zeichnen(); return
        Leinwand.gewaehlt = nach
        self.ed._save()

    def _ziehen(self, e):
        l = self._link
        if not l: return
        x, y = self.c.canvasx(e.x), self.c.canvasy(e.y)
        if l["linie"]: self.c.coords(l["linie"], l["x"], l["y"], x, y)
        else: l["linie"] = self.c.create_line(l["x"], l["y"], x, y, fill="#6E56F8", width=2, dash=(6, 3), arrow="last")
        self.c.delete("ziel"); ziel = self._treffer(e)
        if ziel and ziel not in (l["von"], "_start"):
            bb = self.c.bbox(f"n:{ziel}")
            if bb: self.c.create_rectangle(*bb, outline="#6E56F8", width=3, tags=("ziel",))

    def _los(self, e):
        l, self._link = self._link, None
        if not l: return
        self.c.delete("ziel")
        if l["linie"]: self.c.delete(l["linie"])
        ziel = self._treffer(e)
        if ziel and ziel not in (l["von"], "_start"): self._verbinden(l["von"], ziel, e.x_root, e.y_root)

    # ------------------------------------------------------------------ v150: Verbinden = Ausdruck ins Feld schreiben
    def _ausgaben(self, quelle):
        if quelle == "_start":
            return [(f"input.{i['id']}", i.get("label", i["id"])) for i in self.ed.raw.get("inputs", [])]
        st = self._steps()[self._index(quelle)]
        herkunft = ""                                                      # v151: woher der Wert stammt, z.B. «Leistungsbeschrieb»
        m = __import__("re").search(r"input\.(\w+)", str(st.get("files", "")))
        if m:
            inp = next((i for i in self.ed.raw.get("inputs", []) if i.get("id") == m.group(1)), None)
            herkunft = f"  –  {inp.get('label', m.group(1)) if inp else m.group(1)}"
        aus = [(f"{quelle}.{k}", d + (herkunft if k == "text" else "")) for k, d in S.ergebnis(st)]
        return sorted(aus, key=lambda x: not x[0].endswith(".text"))       # der Text zuerst – fast immer die richtige Wahl

    def _verbinden(self, quelle, ziel, mx, my):
        """Menü: welcher Wert der Quelle in welches Feld des Ziels? Schreibt {{quelle.wert}} – die Verbindung IST der Verweis."""
        zi = self._index(ziel); st = self._steps()[zi]; meta = S.BAUSTEINE.get(st.get("type"), {})
        felder = [f for f in meta.get("felder", []) if f.get("wert_einfuegen") and f["typ"] in ("text", "textarea")]
        aus = self._ausgaben(quelle)
        if not felder or not aus:
            from tkinter import messagebox
            messagebox.showinfo("Verbinden", "Dieser Baustein hat kein Feld, das einen Wert übernimmt – im Formular "
                                "(Doppelklick) einstellen." if not felder else "Die Quelle liefert keinen Wert.", parent=self.ed.ww.win)
            return
        m = tk.Menu(self.c, tearoff=0)
        qt = "Eingaben beim Start" if quelle == "_start" else (self._steps()[self._index(quelle)].get("label") or quelle)
        m.add_command(label=f"Von «{qt}» nach «{st.get('label') or meta.get('titel')}» – zuerst das Feld wählen:", state="disabled")
        for f in felder:
            sub = tk.Menu(m, tearoff=0)
            for expr, desc in aus:
                sub.add_command(label=f"{expr}    {desc}"[:90], command=lambda f=f, x=expr: self._schreiben(quelle, zi, f, x))
            m.add_cascade(label=f"→ {f['label']}", menu=sub)
        m.tk_popup(mx, my)

    def _schreiben(self, quelle, zi, f, expr):
        from tkinter import messagebox
        st = self._steps(); step = st[zi]; key = f["key"]; neu = "{{" + expr + "}}"
        alt = step.get(key)
        if isinstance(alt, str) and alt.strip() and alt.strip() != str(f.get("standard", "")).strip():
            if neu in alt: return
            a = messagebox.askyesnocancel("Verbinden", f"«{f['label']}» enthält schon:\n{alt[:200]}\n\nJa = ersetzen · Nein = anhängen",
                                          parent=self.ed.ww.win)
            if a is None: return
            step[key] = neu if a else (alt.rstrip() + ("\n" if f["typ"] == "textarea" else " ") + neu)
        else: step[key] = neu
        qi = self._index(quelle) if quelle != "_start" else None
        if qi is not None and qi > zi:                                      # Quelle läuft später → davor schieben
            st.insert(zi, st.pop(qi))
        Leinwand.gewaehlt = step["id"]
        self.ed._save()

    def _doppel(self, e):
        sid = self._treffer(e); i = self._index(sid) if sid else None
        if i is not None: self.ed._edit(i)
