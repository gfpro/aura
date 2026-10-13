# aura/dashboard.py — Startseite-Widgets (angeheftete Workflow-Ergebnisse) und Ablaufband im Workflow. Version 20261013v81
# v81: Widgets in eigener Ansicht («▶»), je Widget volle Breite untereinander.
# v80: Startseite zeigt nur Widgets = Anzeige-Ergebnis (Baustein «meldung») des letzten Laufs angehefteter Workflows.
#      Das Ablaufband (Schritte + Status) steht im Workflow, Reiter «Ablauf».
# Nur Anzeige: liest workflow.json und protokoll.json. Legt nie Jobs in den Worker.
import json, tkinter as tk
from pathlib import Path
import customtkinter as ctk
from . import log, hilfe

ANZEIGE = ("meldung",)                    # Bausteine, deren Ergebnis ein Widget zeigen kann


# ------------------------------------------------------------------ Anheften (Einstellung dash_widgets)
def pins(app):
    return list(app.s.get("dash_widgets") or [])

def ist_angeheftet(app, path): return path in pins(app)

def anheften(app, path, an=True):
    """Liste in den Einstellungen und in app.s gleich halten (andere Stellen speichern app.s)."""
    from .config import load_settings, save_settings
    s = load_settings(); p = [x for x in (s.get("dash_widgets") or []) if x != path]
    if an: p.append(path)
    s["dash_widgets"] = p; save_settings(s); app.s["dash_widgets"] = p

def hat_anzeige(wf):
    return any(st.get("type") in ANZEIGE for st in (wf or {}).get("steps", []))


def _farbe(col):
    if isinstance(col, (tuple, list)): return col[1] if ctk.get_appearance_mode() == "Dark" else col[0]
    return col


# ------------------------------------------------------------------ Startseite
class Widgets:
    def __init__(self, app, parent):
        from . import gui as G
        self.G, self.app = G, app
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.grid_columnconfigure(0, weight=1)
        self.draw()

    def alive(self):
        try: return self.frame.winfo_exists()
        except Exception: return False

    def draw(self):
        if not self.alive(): return
        G = self.G
        for c in self.frame.winfo_children(): c.destroy()
        ctk.CTkLabel(self.frame, text="MEINE WORKFLOW-ERGEBNISSE", font=G.font(10, "bold"), text_color=G.MUTED).grid(
            row=0, column=0, sticky="w", padx=8, pady=(0, 4))
        ps = [p for p in pins(self.app) if Path(p).is_file()]
        if not ps:
            ctk.CTkLabel(self.frame, text="Noch keine Widgets. Links «Workflows öffnen», Workflow wählen und «☆ Als Widget» klicken – "
                                          "geeignet sind Workflows mit der Ausgabe «Anzeige in AURA».",
                         font=G.font(11), text_color=G.MUTED, wraplength=700, justify="left", anchor="w").grid(
                row=1, column=0, sticky="w", padx=8)
            return
        for i, p in enumerate(ps):
            try: card = self._karte(p)
            except Exception: log.get().exception("Widget"); continue
            card.grid(row=1 + i, column=0, sticky="ew", padx=6, pady=6)
        hilfe.auto(self.frame, "haupt")

    def _karte(self, path):
        from .workflow import load_workflow
        from .ergebnisse import letzter_lauf, gesehen
        G = self.G
        try: wf = load_workflow(path); name = wf.get("name") or Path(path).parent.name
        except Exception: wf, name = None, Path(path).parent.name
        proto, stamp = letzter_lauf(path)
        neu = bool(stamp and stamp > gesehen())
        c = ctk.CTkFrame(self.frame, fg_color=G.BUBBLE, corner_radius=14, border_width=1, border_color=G.ACCENT if neu else G.BORDER,
                         )
        c.grid_columnconfigure(0, weight=1)
        hd = ctk.CTkFrame(c, fg_color="transparent"); hd.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))
        hd.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hd, text=name[:80], font=G.font(15, "bold"), text_color=G.INK, anchor="w").grid(row=0, column=0, sticky="w")
        x = ctk.CTkButton(hd, text="✕", width=24, height=22, corner_radius=6, font=G.font(11), fg_color="transparent",
                          hover_color=G.BORDER, text_color=G.MUTED, command=lambda: self._weg(path))
        x.grid(row=0, column=1); hilfe.tip(x, "Widget entfernen (der Workflow bleibt).")
        if proto is None: zeile, txt = "noch kein Lauf", "Noch kein Ergebnis. Workflow starten oder Zeitplan abwarten."
        else:
            z = f"{stamp[6:8]}.{stamp[4:6]}. {stamp[9:11]}:{stamp[11:13]}" if len(stamp or "") >= 13 else stamp
            ok = proto.get("status") == "ok"
            zeile = ("● neu · " if neu else "") + z + ("" if ok else f" · ✕ {proto.get('status')}")
            txt = "\n\n".join((m.get("text") or "").replace("**", "").strip() for m in proto.get("meldungen") or []).strip()
            if not ok and proto.get("error"): txt = f"Fehler: {proto['error']}"
            elif not txt:
                txt = ("Dieser Workflow hat kein Anzeige-Ergebnis. Im Workflow, Reiter «Schritte», die Ausgabe «Anzeige in AURA» ergänzen."
                       if not hat_anzeige(wf) else "Der letzte Lauf hat nichts zum Anzeigen geliefert.")
        ctk.CTkLabel(c, text=zeile, font=G.font(10), text_color=G.ACCENT if neu else G.MUTED, anchor="w").grid(
            row=1, column=0, sticky="w", padx=12)
        tb = ctk.CTkTextbox(c, height=280, font=G.font(12), wrap="word", fg_color=G.CARD, text_color=G.INK, border_width=0)
        tb.insert("1.0", txt[:6000]); tb.configure(state="disabled"); tb.grid(row=2, column=0, sticky="nsew", padx=12, pady=(4, 6))
        bb = ctk.CTkFrame(c, fg_color="transparent"); bb.grid(row=3, column=0, sticky="w", padx=10, pady=(0, 10))
        for t, cmd in (("Kopieren", lambda: self.app._copy(txt)), ("Alle Ergebnisse", self.app.open_ergebnisse),
                       ("Workflow", lambda: self.app._erg_workflow(path))):
            ctk.CTkButton(bb, text=t, height=24, width=0, corner_radius=8, font=G.font(11), fg_color=G.CARD, hover_color=G.BORDER,
                          text_color=G.INK, command=cmd).pack(side="left", padx=2)
        return c

    def _weg(self, path):
        anheften(self.app, path, False); self.draw()


# ------------------------------------------------------------------ Ablaufband (im Workflow, Reiter «Ablauf»)
W, H, GAP, PAD = 172, 92, 34, 12

class FlowBand:
    def __init__(self, app, parent, path):
        from . import gui as G
        self.G, self.app, self.path = G, app, path
        f = self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(f, text="Schritte des Workflows mit dem Ergebnis des letzten Laufs. Klick auf einen Schritt zeigt sein Ergebnis.",
                     font=G.font(11), text_color=G.MUTED, anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.cv = tk.Canvas(f, height=self._s(H + 2 * PAD), highlightthickness=0, bd=0)
        self.cv.grid(row=1, column=0, sticky="ew")
        self.sb = ctk.CTkScrollbar(f, orientation="horizontal", height=12, command=self.cv.xview)
        self.sb.grid(row=2, column=0, sticky="ew"); self.cv.configure(xscrollcommand=self.sb.set)
        self.info = ctk.CTkLabel(f, text="", font=G.font(11), text_color=G.MUTED, anchor="w", justify="left", wraplength=800)
        self.info.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.draw()

    def alive(self):
        try: return self.frame.winfo_exists()
        except Exception: return False

    def _s(self, v): return int(v * (ctk.ScalingTracker.get_widget_scaling(self.frame) or 1.0))

    def draw(self):
        if not self.alive(): return
        cv, G, c, s = self.cv, self.G, _farbe, self._s
        cv.delete("all"); cv.configure(bg=c(G.CARD)); self.steps = []; self.out = {}
        try:
            from .workflow import load_workflow
            from .ergebnisse import letzter_lauf
            wf = load_workflow(self.path); proto, stamp = letzter_lauf(self.path)
        except Exception as e:
            self.info.configure(text=f"Workflow nicht lesbar: {e}", text_color=G.ERR); return
        logm = {x.get("id"): x for x in (proto or {}).get("log") or []}
        fehler = proto is not None and proto.get("status") != "ok"; erster = True
        for i, st in enumerate(wf["steps"]):
            e = logm.get(st["id"])
            if proto is None: zust, sym, col = "noch kein Lauf", "○", G.MUTED
            elif e is not None:
                o = e.get("out"); w = o.get("_warnungen") if isinstance(o, dict) else None
                zust = f"{e.get('seconds', 0):.0f} s" + (f" · ⚠ {len(w)}" if w else "")
                sym, col = ("⚠", "#F59E0B") if w else ("✓", G.TEAL)
            elif fehler and erster: zust, sym, col, erster = "Fehler", "✕", G.ERR, False
            else: zust, sym, col = "übersprungen", "–", G.MUTED
            self.steps.append(st); self.out[st["id"]] = e
            x0, y0 = s(PAD + i * (W + GAP)), s(PAD); x1, y1 = x0 + s(W), y0 + s(H); tag = f"s{i}"
            cv.create_rectangle(x0, y0, x1, y1, fill=c(G.BUBBLE), outline=c(col), width=2, tags=(tag,))
            cv.create_rectangle(x0, y0, x0 + s(5), y1, fill=c(col), outline="", tags=(tag,))
            cv.create_text(x0 + s(14), y0 + s(10), anchor="nw", text=f"{i + 1}  {sym}", fill=c(col), font=(G.F, 10, "bold"), tags=(tag,))
            nm = st.get("label") or st["id"]
            cv.create_text(x0 + s(14), y0 + s(30), anchor="nw", text=nm if len(nm) <= 22 else nm[:21] + "…", fill=c(G.INK),
                           font=(G.F, 10, "bold"), tags=(tag,))
            cv.create_text(x0 + s(14), y0 + s(50), anchor="nw", text=st["type"], fill=c(G.MUTED), font=(G.F, 9), tags=(tag,))
            cv.create_text(x0 + s(14), y0 + s(68), anchor="nw", text=zust, fill=c(col), font=(G.F, 9), tags=(tag,))
            if i: cv.create_line(x0 - s(GAP - 4), (y0 + y1) // 2, x0 - s(4), (y0 + y1) // 2, fill=c(G.MUTED), width=2, arrow="last")
            cv.tag_bind(tag, "<Button-1>", lambda e, i=i: self._detail(i))
            cv.tag_bind(tag, "<Enter>", lambda e: cv.configure(cursor="hand2"))
            cv.tag_bind(tag, "<Leave>", lambda e: cv.configure(cursor=""))
        cv.configure(scrollregion=(0, 0, s(2 * PAD + len(wf["steps"]) * (W + GAP) - GAP), s(H + 2 * PAD)))
        if proto is None: t = f"{len(wf['steps'])} Schritte · noch kein Lauf"
        else:
            z = f"{stamp[6:8]}.{stamp[4:6]}. {stamp[9:11]}:{stamp[11:13]}" if len(stamp or "") >= 13 else stamp
            t = (f"{len(wf['steps'])} Schritte · letzter Lauf {z} · {'✓ fertig' if not fehler else '✕ ' + str(proto.get('status'))}"
                 f" · {proto.get('seconds', 0):.0f} s" + (f" · ⚠ {len(proto['pruefungen'])} Prüfhinweise" if proto.get("pruefungen") else ""))
            if proto.get("error"): t += f"\n{str(proto['error'])[:200]}"
        self.info.configure(text=t, text_color=G.ERR if fehler else G.MUTED)

    def _detail(self, i):
        st = self.steps[i]; e = self.out.get(st["id"])
        body = self.app.panel(f"{i + 1}. {st.get('label') or st['id']}", "ablauf_schritt", 620); body.grid_rowconfigure(1, weight=1)
        from .workflow.schema import BAUSTEINE
        besch = st.get("hilfe") or hilfe.SCHRITTE.get(st["type"]) or BAUSTEINE.get(st["type"], {}).get("beschreibung", "")
        ctk.CTkLabel(body, text=f"Baustein «{st['type']}»" + (f" – {besch}" if besch else "")
                     + ("" if e is None else f"\nDauer im letzten Lauf: {e.get('seconds', 0):.1f} s"),
                     font=self.G.font(11), text_color=self.G.MUTED, anchor="w", justify="left", wraplength=560).grid(
            row=0, column=0, sticky="w", padx=16, pady=(0, 6))
        tb = ctk.CTkTextbox(body, font=ctk.CTkFont(family="Consolas", size=11), wrap="word", fg_color=self.G.BUBBLE, text_color=self.G.INK)
        tb.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        if e is None: txt = "Dieser Schritt lief im letzten Lauf nicht (oder es gibt noch keinen Lauf)."
        else:
            out = e.get("out")
            txt = out["text"] if isinstance(out, dict) and isinstance(out.get("text"), str) and len(out) <= 3 else json.dumps(out, ensure_ascii=False, indent=1)
            if len(txt) > 30000: txt = txt[:30000] + "\n… (gekürzt – vollständig im Laufordner, protokoll.json)"
        tb.insert("1.0", txt); tb.configure(state="disabled")
