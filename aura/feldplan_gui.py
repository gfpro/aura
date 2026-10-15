# aura/feldplan_gui.py — Fenster «Feldplan»: woher kommt jeder Wert der Vorlage? Version 20261015v94 (v94: «In welchem Dokument?» ohne doppelte/fest eingebaute Namen; v64e: «dann» mit Mehrfachauswahl bei Gruppen; v64d: Regel-Editor «Wenn … dann …»; v64c: «Workflow aus Feldplan bauen»; v64a2: Doppelklick = woher genau / Regel / fester Wert)
# Öffnet aus dem Reiter «Vorlage». Zeigt Gruppen (aufklappbar mit ihren Optionen) und Einzelfelder mit Herkunft.
# Herkunft per Knopf ändern (mehrere Zeilen markierbar); jede Änderung wird sofort in <vorlage>.feldplan.json gespeichert.
# Noch ohne Bauen und ohne Sprachmodell (kommt in v64b/c).
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
import customtkinter as ctk
from .workflow import feldplan as FP

FARBE = {"fakt": "#16A34A", "abgeleitet": "#7C3AED", "fest": "#0369A1", "manuell": "#B45309", "leer": "#9AA3AF", "offen": "#DC2626"}
ERKL = ("Fakt = steht in den Ausgangsdokumenten · Abgeleitet = braucht eine Regel (Wissen) · Fest = immer gleich · "
        "Manuell = weiss nur die Bedarfsstelle · Leer = nicht nötig · Offen = noch unklar (prüft später das Sprachmodell).\n"
        "Kästchen-Gruppen sind EINE Frage mit mehreren Antworten; «Mehrfach» erlaubt mehrere Kreuze. "
        "Mehrere Zeilen mit Ctrl/Shift markieren und dann einen Knopf drücken. DOPPELKLICK = genau angeben, woher der Wert kommt.")


def woher(e):
    """Kurzfassung der Detailangaben für die Tabelle."""
    h = e["herkunft"]
    if h == "fakt":
        t = " · ".join(x for x in (e.get("quelle"), e.get("hinweis")) if x)
        return t or "⚠ woher? (Doppelklick)"
    if h == "abgeleitet":
        if e.get("regeln"):
            n = len(e["regeln"]); d = e["regeln"][0].get("dann", ""); d = " + ".join(d) if isinstance(d, list) else d
            return f"{n} Regel{'n' if n > 1 else ''} → {d}" + (" …" if n > 1 else "")
        t = e.get("regel", "") + (f"  [{e['wissen']}]" if e.get("wissen") else "")
        return ("⚠ noch nicht umgesetzt: " + t) if t else "⚠ welche Regel? (Doppelklick)"
    if h == "fest": return f"= {e['wert']}" if e.get("wert") else "⚠ welcher Wert? (Doppelklick)"
    if h == "manuell": return f"Platzhalter «{e.get('platzhalter') or '[ergänzen]'}»"
    return ""


class FeldplanFenster:
    def __init__(self, ww, vorlage, rel=""):
        self.ww, self.G, self.vorlage, self.rel = ww, ww.G, Path(vorlage), rel
        G = self.G
        alt = FP.laden(self.vorlage)
        try: self.plan = FP.mischen(FP.analysieren(self.vorlage, rel), alt)
        except Exception as e: messagebox.showerror("Feldplan", f"Vorlage nicht lesbar: {e}", parent=ww.win); return
        FP.speichern(self.vorlage, self.plan)
        d = self.win = ctk.CTkToplevel(ww.win); d.title(f"Feldplan – {self.vorlage.name}"); d.transient(ww.win); d.geometry("1300x780")
        d.grid_columnconfigure(0, weight=1); d.grid_rowconfigure(3, weight=1)
        self.lbl = ctk.CTkLabel(d, text="", font=G.font(13, "bold"), anchor="w"); self.lbl.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(d, text=ERKL, font=G.font(11), text_color=G.MUTED, anchor="w", justify="left",
                     wraplength=1250).grid(row=1, column=0, sticky="w", padx=16)
        bar = ctk.CTkFrame(d, fg_color="transparent"); bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 6))
        ctk.CTkLabel(bar, text="Herkunft:", font=G.font(11)).pack(side="left", padx=(0, 6))
        for k in ("fakt", "abgeleitet", "fest", "manuell", "leer", "offen"):
            ctk.CTkButton(bar, text=FP.HERKUNFT[k].split(" (")[0], height=28, width=0, corner_radius=8, font=G.font(11),
                          fg_color=FARBE[k], hover_color=G.INK, text_color="white",
                          command=lambda k=k: self.setzen(k)).pack(side="left", padx=(0, 4))
        ctk.CTkButton(bar, text="Mehrfach ein/aus", height=28, width=0, corner_radius=8, font=G.font(11), fg_color=G.BORDER,
                      hover_color=G.MUTED, text_color=G.INK, command=self.mehrfach).pack(side="left", padx=(12, 4))
        self.o_f = ctk.CTkOptionMenu(bar, values=["alle zeigen"] + [FP.HERKUNFT[k] for k in FP.HERKUNFT], width=170, height=28,
                                     font=G.font(11), fg_color=G.BUBBLE, button_color=G.BORDER, text_color=G.INK,
                                     command=lambda v: self.fuellen())
        self.o_f.set("alle zeigen"); self.o_f.pack(side="left", padx=(12, 4))
        ctk.CTkButton(bar, text="▶ Workflow aus Feldplan bauen", height=28, width=0, corner_radius=8, font=G.font(11, "bold"),
                      fg_color=G.ACCENT, hover_color=G.ACCENT_HI, command=self.bauen).pack(side="right")
        ctk.CTkButton(bar, text="Neu analysieren", height=28, width=0, corner_radius=8, font=G.font(11), fg_color=G.BORDER,
                      hover_color=G.MUTED, text_color=G.INK, command=self.neu).pack(side="left", padx=(12, 0))
        fr = tk.Frame(d); fr.grid(row=3, column=0, sticky="nsew", padx=16); fr.grid_columnconfigure(0, weight=1); fr.grid_rowconfigure(0, weight=1)
        cols = ("nr", "abschnitt", "typ", "herkunft", "woher", "grund")
        tv = self.tv = ttk.Treeview(fr, columns=cols, show="tree headings", selectmode="extended")
        tv.heading("#0", text="Feld / Gruppe", anchor="w"); tv.column("#0", width=380, stretch=True)
        for c, w, h in zip(cols, (70, 220, 110, 130, 300, 260), ("Nr", "Abschnitt", "Typ", "Herkunft", "Woher genau / Regel / Wert", "Warum (AURA)")):
            tv.heading(c, text=h, anchor="w"); tv.column(c, width=w, anchor="w", stretch=c in ("abschnitt", "woher", "grund"))
        for k, col in FARBE.items(): tv.tag_configure(k, foreground=col)
        tv.tag_configure("option", foreground="#6B7280")
        sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=sb.set)
        tv.grid(row=0, column=0, sticky="nsew"); sb.grid(row=0, column=1, sticky="ns")
        tv.bind("<<TreeviewSelect>>", lambda e: self.detail())
        tv.bind("<Double-1>", lambda e: self.bearbeiten())
        self.det = ctk.CTkLabel(d, text="", font=G.font(11), text_color=G.MUTED, anchor="w", justify="left", wraplength=1250)
        self.det.grid(row=4, column=0, sticky="w", padx=16, pady=(6, 12))
        self.fuellen()

    # ------------------------------------------------------------------ Anzeige
    def fuellen(self):
        tv = self.tv; offen = {i for i in tv.get_children() if tv.item(i, "open")}
        tv.delete(*tv.get_children())
        f = self.o_f.get(); filt = next((k for k, v in FP.HERKUNFT.items() if v == f), None)
        for e in self.plan["eintraege"]:
            if filt and e["herkunft"] != filt: continue
            nr = f"{e['nrs'][0]}–{e['nrs'][-1]}" if len(e["nrs"]) > 1 else str(e["nrs"][0])
            typ = ("Auswahl" + (" (mehrfach)" if e.get("mehrfach") else "") + f", {len(e['nrs'])}") if e["art"] == "gruppe" else \
                  e["typ"] + (f" ({len(e['optionen'])})" if e.get("optionen") else "")
            text = ("▣ " if e["art"] == "gruppe" else "") + e["titel"] + ("  ✎" if e.get("von_hand") else "")
            tv.insert("", "end", iid=e["id"], text=text, open=e["id"] in offen, tags=(e["herkunft"],),
                      values=(nr, e["abschnitt"], typ, FP.HERKUNFT[e["herkunft"]], woher(e), e.get("grund", "")))
            if e["art"] == "gruppe":
                for j, (n, o) in enumerate(zip(e["nrs"], e["optionen"])):
                    tv.insert(e["id"], "end", iid=f"{e['id']}/{j}", text="   ☐ " + o, values=(n, "", "Option", "", "", ""), tags=("option",))
        self.lbl.configure(text=FP.zusammenfassung(self.plan))

    def detail(self):
        sel = self.tv.selection()
        if len(sel) != 1: self.det.configure(text=f"{len(sel)} Zeilen markiert." if sel else ""); return
        e = self._eintrag(sel[0])
        if not e: return
        t = f"Felder in der Vorlage: {', '.join(e['keys'][:6])}{' …' if len(e['keys']) > 6 else ''}"
        if e.get("kontext"): t += f"\nUmgebung in der Vorlage: {e['kontext']}"
        if e.get("optionen") and e["art"] != "gruppe": t += f"\nErlaubte Werte: {' | '.join(e['optionen'])}"
        if e.get("begleitfelder"): t += f"\nBegleitfelder (nur wenn angekreuzt): Nr. {', '.join(map(str, e['begleitfelder']))}"
        self.det.configure(text=t)

    def _eintrag(self, iid):
        iid = iid.split("/")[0]
        return next((e for e in self.plan["eintraege"] if e["id"] == iid), None)

    # ------------------------------------------------------------------ Ändern
    def _gewaehlt(self):
        es, seen = [], set()
        for i in self.tv.selection():
            e = self._eintrag(i)
            if e and e["id"] not in seen: seen.add(e["id"]); es.append(e)
        if not es: messagebox.showinfo("Feldplan", "Bitte zuerst eine oder mehrere Zeilen markieren.", parent=self.win)
        return es

    def _speichern(self, sel):
        try: FP.speichern(self.vorlage, self.plan)
        except Exception as e: messagebox.showerror("Feldplan", f"Nicht gespeichert: {e}", parent=self.win); return
        self.fuellen()
        sel = [i for i in sel if self.tv.exists(i)]
        if sel: self.tv.selection_set(sel); self.tv.see(sel[0])

    def setzen(self, k):
        es = self._gewaehlt()
        for e in es: e["herkunft"] = k; e["von_hand"] = True
        if es: self._speichern([e["id"] for e in es])

    def mehrfach(self):
        es = [e for e in self._gewaehlt() if e["art"] == "gruppe"]
        for e in es: e["mehrfach"] = not e.get("mehrfach"); e["von_hand"] = True
        if es: self._speichern([e["id"] for e in es])

    def neu(self):
        """Vorlage neu lesen (z.B. nach Änderung der .docx); von Hand Gesetztes bleibt."""
        try: self.plan = FP.mischen(FP.analysieren(self.vorlage, self.rel), self.plan)
        except Exception as e: messagebox.showerror("Feldplan", f"Vorlage nicht lesbar: {e}", parent=self.win); return
        self._speichern([])

    # ------------------------------------------------------------------ Detail (v64a2)
    def bearbeiten(self):
        """Doppelklick: genau angeben, woher der Wert kommt – je nach Herkunft andere Felder."""
        sel = self.tv.selection()
        if len(sel) != 1: return
        e = self._eintrag(sel[0])
        if not e: return
        G = self.G; gruppe = e["art"] == "gruppe"
        d = ctk.CTkToplevel(self.win); d.title(e["titel"][:60]); d.transient(self.win); d.grab_set(); d.geometry("780x720")
        d.grid_columnconfigure(1, weight=1); w = {}; r = [0]
        def zeile(lab, tip=""):
            ctk.CTkLabel(d, text=lab, font=G.font(12), anchor="w").grid(row=r[0], column=0, sticky="nw", padx=(16, 8), pady=(10, 0))
            if tip: ctk.CTkLabel(d, text=tip, font=G.font(10), text_color=G.MUTED, anchor="w", justify="left",
                                 wraplength=520).grid(row=r[0] + 1, column=1, sticky="w", padx=(0, 16))
        info = f"Nr. {', '.join(map(str, e['nrs'][:8]))}{' …' if len(e['nrs']) > 8 else ''} · {e['abschnitt']}"
        if gruppe: info += f"\nOptionen: {' | '.join(e['optionen'][:12])}{' …' if len(e['optionen']) > 12 else ''}"
        elif e.get("optionen"): info += f"\nErlaubte Werte: {' | '.join(e['optionen'])}"
        ctk.CTkLabel(d, text=info, font=G.font(11), text_color=G.MUTED, anchor="w", justify="left",
                     wraplength=680).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 0)); r[0] = 1
        zeile("Herkunft")
        o_h = ctk.CTkOptionMenu(d, values=[FP.HERKUNFT[k] for k in FP.HERKUNFT], width=220); o_h.set(FP.HERKUNFT[e["herkunft"]])
        o_h.grid(row=r[0], column=1, sticky="w", pady=(10, 0)); r[0] += 1
        teil = ctk.CTkFrame(d, fg_color="transparent"); teil.grid(row=r[0], column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        teil.grid_columnconfigure(1, weight=1); d.grid_rowconfigure(r[0], weight=1); r[0] += 1
        rl = [dict(x) for x in e.get("regeln") or []]                  # v64d: Regeln dieses Eintrags (Kopie bis «Speichern»)
        quellen = [i.get("label", i["id"]) for i in (getattr(self.ww, "wf", None) or {}).get("inputs", []) if i.get("type") == "files"]
        def feld(row, lab, key, tip="", vorschlaege=None, hoch=False):
            ctk.CTkLabel(teil, text=lab, font=G.font(12), anchor="w", width=120).grid(row=row, column=0, sticky="nw", padx=(16, 8), pady=(10, 0))
            if hoch:
                x = ctk.CTkTextbox(teil, height=80, wrap="word", border_width=1, border_color=G.BORDER); x.insert("1.0", e.get(key, ""))
            elif vorschlaege:
                x = ctk.CTkComboBox(teil, values=vorschlaege, width=420); x.set(e.get(key, ""))
            else:
                x = ctk.CTkEntry(teil, width=420); x.insert(0, e.get(key, ""))
            x.grid(row=row, column=1, sticky="ew", padx=(0, 16), pady=(10, 0)); w[key] = x
            if tip: ctk.CTkLabel(teil, text=tip, font=G.font(10), text_color=G.MUTED, anchor="w", justify="left",
                                 wraplength=520).grid(row=row + 1, column=1, sticky="w", padx=(0, 16))
        def zeigen(v):
            for c in teil.winfo_children(): c.destroy()
            w.clear(); k = next(k for k, t in FP.HERKUNFT.items() if t == v)
            if k == "fakt":
                feld(0, "In welchem Dokument?", "quelle", "z.B. «Leistungsbeschrieb», «Checkliste» oder «alle Unterlagen».",
                     list(dict.fromkeys(["alle Unterlagen"] + quellen)))          # v94: nur die Eingaben des Workflows, ohne Doppel
                feld(2, "Wo / wie erkennbar?", "hinweis", "Überschrift, Stichwort oder Formulierung, z.B. «unter ‹Auftraggeber›» "
                     "oder «Betrag in CHF bei ‹Kostendach›». Wird zum Hinweis ans Sprachmodell.", hoch=True)
                if gruppe: ctk.CTkLabel(teil, text="Bei einer Gruppe wählt das Sprachmodell EINE der Optionen (bzw. mehrere bei «Mehrfach»).",
                                        font=G.font(10), text_color=G.MUTED).grid(row=4, column=1, sticky="w")
            elif k == "abgeleitet":
                self._regel_liste(teil, e, rl, w)
                feld(6, "Grundlage (Wissen)", "wissen", "z.B. «BöB Art. 21» – wird Pflichtstelle im Wissen.")
                feld(8, "Regel in Worten", "regel", "Optional: Notiz, falls du die Regel noch nicht oben eintragen kannst.")
            elif k == "fest":
                opts = e.get("optionen") or []
                feld(0, "Fester Wert", "wert", "Steht bei jedem Fall gleich im Dokument." + (" Bei Kästchen/Auswahl: eine Option wählen." if opts else ""),
                     opts or None)
            elif k == "manuell":
                feld(0, "Platzhalter", "platzhalter", "Text, der im Dokument stehen bleibt, bis die Bedarfsstelle ergänzt. Leer = «[ergänzen]».")
            feld(10, "Notiz", "notiz", "Optional, nur für dich.")
        o_h.configure(command=zeigen); zeigen(o_h.get())
        def ok():
            k = next(k for k, t in FP.HERKUNFT.items() if t == o_h.get()); e["herkunft"] = k; e["von_hand"] = True
            if k == "abgeleitet":
                if rl: e["regeln"] = rl
                else: e.pop("regeln", None)
            for key in ("quelle", "hinweis", "regel", "wissen", "wert", "platzhalter", "notiz", "sonst"):
                if key in w:
                    x = w[key]; v = (x.get("1.0", "end") if isinstance(x, ctk.CTkTextbox) else x.get()).strip()
                    if v: e[key] = v
                    else: e.pop(key, None)
            d.destroy(); self._speichern([e["id"]])
        bb = ctk.CTkFrame(d, fg_color="transparent"); bb.grid(row=r[0], column=0, columnspan=2, sticky="e", padx=16, pady=14)
        ctk.CTkButton(bb, text="Abbrechen", width=100, fg_color=G.BORDER, text_color=G.INK, hover_color=G.MUTED,
                      command=d.destroy).pack(side="left", padx=6)
        ctk.CTkButton(bb, text="Speichern", width=100, fg_color=G.ACCENT, hover_color=G.ACCENT_HI, command=ok).pack(side="left")

    # ------------------------------------------------------------------ Bauen (v64c)
    def bauen(self):
        """Ersetzt im Workflow die Vorlage-Schritte durch den Bau aus dem Feldplan (Rest bleibt)."""
        import json
        from .workflow import feldplan_bau as FB
        ww = self.ww; cur = getattr(ww, "cur", None)
        if not cur or not str(cur).endswith("workflow.json"):
            messagebox.showinfo("Feldplan", "Nur bei Workflow-Paketen möglich.", parent=self.win); return
        if getattr(ww, "running", False): messagebox.showinfo("Feldplan", "Während eines Laufs nicht möglich.", parent=self.win); return
        offen = [e for e in self.plan["eintraege"] if e["herkunft"] == "fakt" and not (e.get("quelle") or e.get("hinweis"))]
        try:
            raw = json.loads(Path(cur).read_text(encoding="utf-8"))
            wf, info = FB.anwenden(raw, self.plan, self.rel)
        except Exception as e: messagebox.showerror("Feldplan", f"Nicht gebaut: {e}", parent=self.win); return
        if not messagebox.askyesno("Feldplan", FB.bericht(info) + "\n\nDie bisherigen Vorlage-Schritte im Workflow werden ersetzt "
                                   "(eine Sicherung «workflow.json.bak» bleibt). Fortfahren?", parent=self.win): return
        p = Path(cur)
        try:
            p.with_suffix(".json.bak").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
            tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps(wf, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(p)
        except Exception as e: messagebox.showerror("Feldplan", f"Nicht gespeichert: {e}", parent=self.win); return
        self.win.destroy(); ww.show(str(p))
        try: ww.tabs.set("Ausführen")
        except Exception: pass
        messagebox.showinfo("Feldplan", "Workflow neu gebaut. Testen im Reiter «Ausführen»." +
                            (f"\n\nTipp: Bei {len(offen)} Fakten fehlt noch «woher» (Doppelklick) – das Modell sucht dann selbst."
                             if offen else ""), parent=ww.win)

    # ------------------------------------------------------------------ Regeln (v64d)
    def _regel_liste(self, teil, e, rl, w):
        """Liste der Regeln «Wenn … → …» mit Knöpfen; erste zutreffende Regel gilt, sonst «Sonst»."""
        from .workflow import feldplan_bau as FB
        G = self.G
        ctk.CTkLabel(teil, text="Regeln", font=G.font(12), anchor="w", width=120).grid(row=0, column=0, sticky="nw", padx=(16, 8), pady=(10, 0))
        box = ctk.CTkFrame(teil, fg_color="transparent"); box.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=(10, 0))
        lb = tk.Listbox(box, height=6, activestyle="none", exportselection=False); lb.pack(fill="x")
        def fuellen(sel=None):
            lb.delete(0, "end")
            for r in rl: lb.insert("end", FB.regel_text(r, self.plan))
            if sel is not None and 0 <= sel < len(rl): lb.selection_set(sel)
        def gewaehlt():
            s = lb.curselection(); return s[0] if s else None
        bb = ctk.CTkFrame(box, fg_color="transparent"); bb.pack(anchor="w", pady=(4, 0))
        def b(t, c, main=False):
            ctk.CTkButton(bb, text=t, height=26, width=0, corner_radius=7, font=G.font(11), fg_color=G.ACCENT if main else G.BORDER,
                          hover_color=G.ACCENT_HI if main else G.MUTED, text_color="white" if main else G.INK, command=c).pack(side="left", padx=(0, 4))
        def neu():
            r = self._regel_dialog(e, None); self._grab(teil)
            if r: rl.append(r); fuellen(len(rl) - 1)
        def bearb():
            i = gewaehlt()
            if i is None: return
            r = self._regel_dialog(e, rl[i]); self._grab(teil)
            if r: rl[i] = r; fuellen(i)
        def loesch():
            i = gewaehlt()
            if i is not None: del rl[i]; fuellen()
        def schieb(dv):
            i = gewaehlt()
            if i is None or not 0 <= i + dv < len(rl): return
            rl[i], rl[i + dv] = rl[i + dv], rl[i]; fuellen(i + dv)
        b("+ Regel …", neu, True); b("Bearbeiten", bearb); b("Löschen", loesch); b("▲", lambda: schieb(-1)); b("▼", lambda: schieb(1))
        lb.bind("<Double-1>", lambda ev: bearb())
        ctk.CTkLabel(teil, text="Die erste zutreffende Regel gilt (Reihenfolge mit ▲▼). Bedingungen beziehen sich auf Fakten oder auf "
                                "andere Regeln. Läuft ohne Sprachmodell.", font=G.font(10), text_color=G.MUTED, anchor="w",
                     justify="left", wraplength=560).grid(row=1, column=1, sticky="w", padx=(0, 16))
        ctk.CTkLabel(teil, text="Sonst", font=G.font(12), anchor="w", width=120).grid(row=2, column=0, sticky="nw", padx=(16, 8), pady=(10, 0))
        zw = FB.ziel_werte(e)
        cb = ctk.CTkComboBox(teil, values=[""] + zw, width=420); cb.set(e.get("sonst", "")); w["sonst"] = cb
        cb.grid(row=2, column=1, sticky="w", padx=(0, 16), pady=(10, 0))
        ctk.CTkLabel(teil, text="Wenn keine Regel zutrifft. Leer = Feld bleibt leer (bei Text: «[ergänzen]»).", font=G.font(10),
                     text_color=G.MUTED, anchor="w").grid(row=3, column=1, sticky="w", padx=(0, 16))
        fuellen()

    def _grab(self, w):
        try: w.winfo_toplevel().grab_set()
        except Exception: pass

    def _regel_dialog(self, e, r):
        """Eine Regel: bis zu 3 Bedingungen (alle müssen zutreffen) und das Ergebnis. Rückgabe dict oder None."""
        from .workflow import feldplan_bau as FB
        G = self.G; r = r or {"wenn": [], "dann": ""}
        qs = [q for q in FB.quellen(self.plan) if q[0] != e["id"]]
        anz = {q[1]: q for q in qs}; by_id = {q[0]: q for q in qs}; KEINE = "– keine Bedingung –"
        d = ctk.CTkToplevel(self.win); d.title("Regel"); d.transient(self.win); d.grab_set(); d.geometry("900x380")
        ctk.CTkLabel(d, text=f"Regel für «{e['titel'][:60]}» – alle Bedingungen müssen zutreffen (für «oder»: zweite Regel anlegen).",
                     font=G.font(12, "bold"), anchor="w").grid(row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(14, 8))
        zeilen = []
        for i in range(3):
            c = (r.get("wenn") or [])[i] if i < len(r.get("wenn") or []) else {}
            ctk.CTkLabel(d, text="Wenn" if i == 0 else "und", font=G.font(12), width=50).grid(row=i + 1, column=0, padx=(16, 4), pady=4)
            o_f = ctk.CTkOptionMenu(d, values=[KEINE] + list(anz), width=330, dynamic_resizing=False)
            o_f.set(by_id[c["feld"]][1] if c.get("feld") in by_id else KEINE); o_f.grid(row=i + 1, column=1, padx=4, pady=4)
            o_o = ctk.CTkOptionMenu(d, values=list(FB.OPS), width=90); o_o.set(c.get("op", "=")); o_o.grid(row=i + 1, column=2, padx=4, pady=4)
            c_w = ctk.CTkComboBox(d, values=[""], width=340); c_w.grid(row=i + 1, column=3, padx=(4, 16), pady=4)
            def werte(v, c_w=c_w, keep=None):
                vals = anz[v][2] if v in anz else []
                c_w.configure(values=vals or [""]); c_w.set(keep if keep is not None else (vals[0] if vals else ""))
            o_f.configure(command=werte); werte(o_f.get(), keep=c.get("wert", ""))
            zeilen.append((o_f, o_o, c_w))
        ctk.CTkLabel(d, text="dann", font=G.font(12, "bold"), width=50).grid(row=5, column=0, padx=(16, 4), pady=(14, 4))
        zw = FB.ziel_werte(e); gruppe = e["art"] == "gruppe"
        if gruppe:                                                   # v64e: mehrere Kästchen ankreuzbar
            d.geometry("900x560")
            fr = tk.Frame(d); fr.grid(row=5, column=1, columnspan=3, sticky="ew", padx=4, pady=(14, 4))
            c_d = tk.Listbox(fr, selectmode="multiple", height=10, width=95, activestyle="none", exportselection=False)
            sb = tk.Scrollbar(fr, command=c_d.yview); c_d.configure(yscrollcommand=sb.set)
            c_d.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
            vorher = set(FB.dann_liste(r.get("dann")))
            for i, o in enumerate(zw):
                c_d.insert("end", o)
                if o in vorher: c_d.selection_set(i)
        else:
            c_d = ctk.CTkComboBox(d, values=zw or [""], width=560); c_d.set(r.get("dann", "") or (zw[0] if zw else ""))
            c_d.grid(row=5, column=1, columnspan=3, sticky="w", padx=4, pady=(14, 4))
        ctk.CTkLabel(d, text=("Mehrere Kästchen anklicken = alle werden angekreuzt. " if gruppe else "")
                             + "Zahlen werden erkannt (80'000.00, CHF 1.2 Mio). «enthält» prüft ein Stichwort im Text."
                             + ("" if zw else " Ergebnis ist freier Text."), font=G.font(10), text_color=G.MUTED,
                     anchor="w").grid(row=6, column=1, columnspan=3, sticky="w", padx=4)
        out = {}
        def ok():
            wenn = [{"feld": anz[f.get()][0], "op": o.get(), "wert": c.get().strip()} for f, o, c in zeilen if f.get() in anz]
            dann = [zw[i] for i in c_d.curselection()] if gruppe else c_d.get().strip()
            if not dann: messagebox.showwarning("Regel", "Bitte angeben, was herauskommen soll («dann»).", parent=d); return
            if zw and not gruppe and dann not in zw: messagebox.showwarning("Regel", "«dann» muss eine der Optionen der Vorlage sein.", parent=d); return
            out.update(wenn=wenn, dann=dann); d.destroy()
        bb = ctk.CTkFrame(d, fg_color="transparent"); bb.grid(row=7, column=0, columnspan=4, sticky="e", padx=16, pady=16)
        ctk.CTkButton(bb, text="Abbrechen", width=100, fg_color=G.BORDER, text_color=G.INK, hover_color=G.MUTED,
                      command=d.destroy).pack(side="left", padx=6)
        ctk.CTkButton(bb, text="Übernehmen", width=110, fg_color=G.ACCENT, hover_color=G.ACCENT_HI, command=ok).pack(side="left")
        d.wait_window()
        return out or None
