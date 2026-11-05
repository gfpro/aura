# aura/graph_gui.py — Ansicht «Zusammenhänge» (Wissen). Version 20261105v204
# Zeigt immer nur die Umgebung eines Treffers oder einer Person, nie den ganzen Graphen.
# Klick = Details, Doppelklick = neu zentrieren, Knopf = Original öffnen. Mausrad = Zoom, rechte Maustaste halten = verschieben.
import math, threading, tkinter as tk
from tkinter import font as tkfont
import customtkinter as ctk
from . import graph as G

F = "Segoe UI"
def font(size=13, weight="normal"): return ctk.CTkFont(family=F, size=size, weight=weight)
CARD, BORDER, INK, MUTED = ("#EDEFEA", "#232B24"), ("#C9CEC3", "#303A31"), ("#1C211C", "#E8ECE4"), ("#525A50", "#A3AD9F")
ACCENT, ACCENT_HI = "#B3121D", "#8E0E17"
QUELLEN = {"outlook_mail": ("Mail", "#2563EB"), "outlook_calendar": ("Termin", "#D97706"), "onenote": ("OneNote", "#7C3AED"),
           "edge_history": ("Edge", "#0F9D7A"), "folder_docs": ("Dokument", "#64748B"), "confluence": ("Confluence", "#0891B2")}
PERSON = "#B3121D"
ZEIT = {"Alle Daten": None, "Letzte 30 Tage": 30, "Letzte 90 Tage": 90, "Letztes Jahr": 365}
KW, KH = 150, 42

def kurz(t, n=24): return t if len(t) <= n else t[:n - 1] + "…"
def passend(t, f, breite):
    """v204: Kürzt nach gemessener Breite statt nach Zeichenzahl."""
    if f.measure(t) <= breite: return t
    while t and f.measure(t + "…") > breite: t = t[:-1]
    return t + "…"
def farbe(typ): return PERSON if typ == "person" else QUELLEN.get(typ, ("", "#64748B"))[1]
def typname(typ): return "Person" if typ == "person" else QUELLEN.get(typ, (typ, ""))[0]

def anordnen(knoten, start):
    """Start in der Mitte, Stufe 1 im inneren, Stufe 2 im äusseren Ring. Liefert {id: (x, y)}."""
    pos = {start: (0.0, 0.0)}
    rand = 0
    for stufe, rx0, ry0 in ((1, 280, 150), (2, 560, 300)):       # v195: Ellipse, die Beschriftungen überlappen nicht
        ids = [i for i, n in knoten.items() if n["stufe"] == stufe]
        rx, ry = max(rx0 + rand, len(ids) * 27), max(ry0 + rand * .4, len(ids) * 10)
        for j, i in enumerate(ids):
            w = 2 * math.pi * j / max(1, len(ids)) - math.pi / 2
            pos[i] = (rx * math.cos(w), ry * math.sin(w))
        if ids: rand = rx - rx0
    return pos

class GraphFenster:
    def __init__(self, app, start=None):
        self.app = app; self.start = start; self.knoten, self.kanten, self.pos = {}, [], {}
        self.gewaehlt = None; self.scale = 1.0
        b = app.view("graph", "Zusammenhänge"); self.body = b
        b.grid_columnconfigure(1, weight=1); b.grid_rowconfigure(0, weight=1)
        l = ctk.CTkFrame(b, fg_color=CARD, corner_radius=0, width=270); l.grid(row=0, column=0, sticky="nsw", padx=(14, 8), pady=10)
        l.grid_propagate(False); l.grid_columnconfigure(0, weight=1); l.grid_rowconfigure(6, weight=1)
        self.e = ctk.CTkEntry(l, placeholder_text="Person oder Titel suchen", corner_radius=0, font=font(12))
        self.e.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6)); self.e.bind("<Return>", lambda _: self.suchen())
        ctk.CTkButton(l, text="Suchen", height=28, corner_radius=0, fg_color=ACCENT, hover_color=ACCENT_HI, font=font(12),
                      command=self.suchen).grid(row=1, column=0, sticky="ew", padx=10)
        z = ctk.CTkFrame(l, fg_color="transparent"); z.grid(row=2, column=0, sticky="ew", padx=10, pady=(8, 2))
        self.m_zeit = ctk.CTkOptionMenu(z, values=list(ZEIT), width=150, corner_radius=0, font=font(11), command=lambda _: self.zeichnen_neu()); self.m_zeit.pack(side="left")
        self.m_tiefe = ctk.CTkSegmentedButton(z, values=["1", "2"], corner_radius=0, font=font(11), command=lambda _: self.zeichnen_neu()); self.m_tiefe.set("1"); self.m_tiefe.pack(side="right")
        q = ctk.CTkFrame(l, fg_color="transparent"); q.grid(row=3, column=0, sticky="ew", padx=10, pady=2)
        self.qv = {}
        for j, (s, (n, _)) in enumerate(QUELLEN.items()):
            v = tk.BooleanVar(value=True); self.qv[s] = v
            ctk.CTkCheckBox(q, text=n, variable=v, width=115, checkbox_width=15, checkbox_height=15, corner_radius=0, font=font(11),
                            fg_color=ACCENT, hover_color=ACCENT_HI, command=self.zeichnen_neu).grid(row=j // 2, column=j % 2, sticky="w", pady=2)
        self.lb_stand = ctk.CTkLabel(l, text="", font=font(11), text_color=MUTED, wraplength=245, justify="left")
        self.lb_stand.grid(row=4, column=0, sticky="w", padx=10)
        ctk.CTkButton(l, text="Neu aufbauen", height=24, corner_radius=0, fg_color=BORDER, hover_color=BORDER, text_color=INK, font=font(11),
                      command=lambda: self.aufbau(True)).grid(row=5, column=0, sticky="ew", padx=10, pady=(4, 6))
        self.liste = ctk.CTkScrollableFrame(l, fg_color="transparent", corner_radius=0); self.liste.grid(row=6, column=0, sticky="nsew", padx=4, pady=(0, 6))
        m = ctk.CTkFrame(b, fg_color=CARD, corner_radius=0); m.grid(row=0, column=1, sticky="nsew", pady=10)
        m.grid_columnconfigure(0, weight=1); m.grid_rowconfigure(0, weight=1)
        self.c = tk.Canvas(m, highlightthickness=0, bd=0); self.c.grid(row=0, column=0, sticky="nsew")
        self.c.bind("<MouseWheel>", self._zoom)
        for x in ("<ButtonPress-3>", "<ButtonPress-2>"): self.c.bind(x, lambda e: self.c.scan_mark(e.x, e.y))
        for x in ("<B3-Motion>", "<B2-Motion>"): self.c.bind(x, lambda e: self.c.scan_dragto(e.x, e.y, gain=1))
        self.c.bind("<Configure>", lambda e: self.zeichnen())
        r = ctk.CTkFrame(b, fg_color=CARD, corner_radius=0, width=260); r.grid(row=0, column=2, sticky="nse", padx=(8, 14), pady=10)
        r.grid_propagate(False); r.grid_columnconfigure(0, weight=1); r.grid_rowconfigure(2, weight=1)
        self.d_titel = ctk.CTkLabel(r, text="Kein Element gewählt", font=font(13, "bold"), text_color=INK, wraplength=235, justify="left", anchor="w")
        self.d_titel.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))
        self.d_sub = ctk.CTkLabel(r, text="", font=font(11), text_color=MUTED, anchor="w"); self.d_sub.grid(row=1, column=0, sticky="ew", padx=10)
        self.d_box = ctk.CTkScrollableFrame(r, fg_color="transparent", corner_radius=0); self.d_box.grid(row=2, column=0, sticky="nsew", padx=4, pady=6)
        self.b_orig = ctk.CTkButton(r, text="Original öffnen", height=30, corner_radius=0, fg_color=ACCENT, hover_color=ACCENT_HI, font=font(12),
                                    state="disabled", command=self.original); self.b_orig.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.aufbau(False)

    def alive(self):
        try: return bool(self.body.winfo_exists())
        except tk.TclError: return False

    def quellen(self): return {s for s, v in self.qv.items() if v.get()}

    def aufbau(self, zwingend):
        if not zwingend and G.aktuell(): self.lb_stand.configure(text="Graph ist aktuell."); self._bereit(); return
        self.lb_stand.configure(text="Graph wird aufgebaut ..."); self.erg = None
        def lauf():
            try: self.erg = G.aufbauen()
            except Exception as e: self.erg = e
        threading.Thread(target=lauf, daemon=True).start(); self._warten()

    def _warten(self):
        if not self.alive(): return
        if self.erg is None: self.body.after(200, self._warten); return
        if isinstance(self.erg, Exception): self.lb_stand.configure(text=f"Aufbau fehlgeschlagen: {self.erg}"); return
        self.lb_stand.configure(text=f"{self.erg[0]:,} Knoten, {self.erg[1]:,} Kanten".replace(",", "'")); self._bereit()

    def _bereit(self):
        if self.start: s, self.start = self.start, None; self.zentrieren(s)

    def suchen(self):
        for w in self.liste.winfo_children(): w.destroy()
        t = self.e.get().strip()
        if not t: return
        try: hits = G.suchen(t, self.quellen())
        except Exception as e: self.lb_stand.configure(text=f"Noch kein Graph: {e}"); return
        if not hits: ctk.CTkLabel(self.liste, text="Keine Treffer.", font=font(12), text_color=MUTED).pack(anchor="w", padx=6); return
        for h in hits:
            lb = ctk.CTkLabel(self.liste, text=f"{typname(h['typ'])} · {kurz(h['titel'], 30)}", font=font(11), text_color=INK, anchor="w", cursor="hand2")
            lb.pack(fill="x", padx=4); lb.bind("<Button-1>", lambda e, i=h["id"]: self.zentrieren(i))

    def zentrieren(self, nid):
        self.mitte = nid; self.gewaehlt = nid; self.zeichnen_neu()

    def zeichnen_neu(self):
        nid = getattr(self, "mitte", None)
        if not nid: return
        try: self.knoten, self.kanten = G.umgebung(nid, int(self.m_tiefe.get()), self.quellen(), ZEIT[self.m_zeit.get()])
        except Exception as e: self.lb_stand.configure(text=f"Fehler: {e}"); return
        self.pos = anordnen(self.knoten, nid) if self.knoten else {}
        self.c.update_idletasks(); bx = max((abs(p[0]) for p in self.pos.values()), default=1) * 2 + KW + 40   # v195: passt ins Fenster
        by = max((abs(p[1]) for p in self.pos.values()), default=1) * 2 + KH + 40
        self.scale = max(.4, min(1.0, self.c.winfo_width() / bx, self.c.winfo_height() / by)); self.zeichnen(); self.details()

    def zeichnen(self):
        c = self.c; c.delete("all")
        dunkel = ctk.get_appearance_mode() == "Dark"
        bg, tx, ln = ("#232B24", "#E8ECE4", "#54605A") if dunkel else ("#EDEFEA", "#1C211C", "#A7AEA3")
        c.configure(bg=bg)
        if not self.pos:
            c.create_text(max(c.winfo_width(), 300) / 2, max(c.winfo_height(), 200) / 2, fill=tx, font=(F, 12),
                          text="Person oder Titel suchen und Treffer anklicken."); return
        mx, my, s = c.winfo_width() / 2, c.winfo_height() / 2, self.scale
        p = {i: (mx + x * s, my + y * s) for i, (x, y) in self.pos.items()}
        for von, nach, art in self.kanten:
            if von in p and nach in p:
                c.create_line(*p[von], *p[nach], fill=ln, width=1, dash=(3, 3) if art == "zeitlich_nah" else None)
        for i, n in self.knoten.items():
            x, y = p[i]; w, h = KW * s / 2, KH * s / 2; dick = 3 if i == self.gewaehlt else 1
            t = c.create_rectangle(x - w, y - h, x + w, y + h, fill=bg, outline=farbe(n["typ"]), width=dick)
            st = c.create_rectangle(x - w, y - h, x - w + 6 * s, y + h, fill=farbe(n["typ"]), outline="")
            sub = typname(n["typ"]) + (f" · {n['ts'][:10]}" if n["ts"] else "")
            f1 = tkfont.Font(family=F, size=-max(8, int(12 * s)), weight="bold"); f2 = tkfont.Font(family=F, size=-max(7, int(10 * s)))
            platz = 2 * w - 16 * s
            a = c.create_text(x - w + 12 * s, y - 7 * s, anchor="w", fill=tx, font=f1, text=passend(n["titel"], f1, platz))
            b = c.create_text(x - w + 12 * s, y + 10 * s, anchor="w", fill=ln if dunkel else "#525A50", font=f2, text=passend(sub, f2, platz))
            for o in (t, st, a, b):
                c.tag_bind(o, "<Button-1>", lambda e, q=i: self.waehlen(q))
                c.tag_bind(o, "<Double-Button-1>", lambda e, q=i: self.zentrieren(q))

    def _zoom(self, e):
        self.scale = min(2.0, max(.4, self.scale * (1.1 if e.delta > 0 else .9))); self.zeichnen()

    def waehlen(self, nid): self.gewaehlt = nid; self.zeichnen(); self.details()

    def details(self):
        for w in self.d_box.winfo_children(): w.destroy()
        n = self.knoten.get(self.gewaehlt)
        if not n: self.b_orig.configure(state="disabled"); return
        self.d_titel.configure(text=n["titel"]); self.d_sub.configure(text=typname(n["typ"]) + (f" · {n['ts'][:16]}" if n["ts"] else ""))
        self.b_orig.configure(state="normal" if n.get("item_id") else "disabled")
        for von, nach, art in self.kanten:
            if self.gewaehlt not in (von, nach): continue
            o = self.knoten.get(nach if von == self.gewaehlt else von)
            if not o: continue
            lb = ctk.CTkLabel(self.d_box, text=f"{G.ART_TEXT.get(art, art)}: {kurz(o['titel'], 34)}", font=font(11), text_color=INK, anchor="w", cursor="hand2")
            lb.pack(fill="x", padx=4); lb.bind("<Button-1>", lambda e, q=o["id"]: self.waehlen(q))

    def original(self):
        n = self.knoten.get(self.gewaehlt)
        if n and n.get("item_id"): self.app.open_original(n["item_id"])
