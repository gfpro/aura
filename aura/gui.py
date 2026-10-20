# aura/gui.py — moderne Oberflaeche mit CustomTkinter (mitgeliefert in vendor\, reines Python). Version 20261020v109
# v109: Seitenleiste neu: aufklappbare Gruppen Chat · Wissen · Workflows · Einstellungen (nur eine offen, gemerkt in menu_offen);
#       Wissens-Zusammenfassung entfaellt (steht in der Info-Leiste rechts); «▶» entfaellt (→ Workflows › Widgets);
#       unten Bereich «Aufgaben» mit Balken: blau = laeuft, gruen = fertig, rot = Fehler; «Vektoren berechnen»/«Pause» dort.
# v98: Eingabezeile wieder kompakt (leerer Anhang-Rahmen hatte 200 px Hoehe), «Bezug» wieder sichtbar.
# v97: Anhang im Chat (📎): Datei nur fuer diesen Chat, sichtbar ueber dem Eingabefeld; «⌂» = neuer Chat leert ihn.
# v87: OneNote – Abschnittsauswahl (gleiche Baumansicht wie Outlook-Ordner).
# v82: Startseiten-Wahl als Schalter «Beim Start Widgets zeigen» (statt Segmentknopf Fragen|Widgets).
# v81: «▶» öffnet die Ansicht «Workflow-Ergebnisse» (Widgets, volle Breite); Startseite nur Fragen; Wahl der ersten Seite (Einstellung startseite).
# v80: Knopf «▶» (Workflows) neben «⌂»; Startseite zeigt angeheftete Workflow-Ergebnisse (Widgets) statt Ablaufband.
# v79: Knopf «⌂» (Startseite) in der Seitenleiste; Ablaufband des gewählten Workflows auf der Startseite (dashboard.py).
# v71: Logo (aura\assets: logo_*.png in der Seitenleiste, aura.ico für Fenster und Taskleiste).
# v70: Schalter «8 Bit (schneller)» unter dem Sprachmodell (Einstellung llm_int8).
# v69: Darstellung Hell/Dunkel/System umschaltbar (unten links, gespeichert); Untertitel ausgeschrieben; Modellname kürzer.
# v68: Farbschema Navy (dunkel), Info-Leiste rechts (Sprachmodell, Vektordatenbank, Workflows; ein-/ausblendbar, blendet sich
#      bei schmalem Fenster aus), Startseite mit Kacheln statt Knöpfen; «Letzte Ergebnisse» wandert in die Info-Leiste.
# v67: Knopf «↳ Bezug zur letzten Frage» (gilt fuer eine Frage, schaltet sich nach dem Senden aus).
# v60: «Alles zurücksetzen» (Quellen); Startseite «Letzte Ergebnisse» wird aufgefrischt; Läufe lassen sich löschen (Papierkorb).
# v59: Tabellen in den Ergebnis-Karten (Termine, Mails …).
# v57: Ergebnis-Karte erklärt, wenn ein Lauf nichts anzeigt (kein Ausgabe-Schritt).
# v55: «Letzte Ergebnisse» auf der Startseite eingerahmt.
# v54: Ansicht «Ergebnisse» (Startseite, Seitenleiste mit «n neu»), Zeitplan-Läufe nur noch als kurzer Hinweis im Chat.
# v53: Zeitplan-Takt. v38: Infotexte. v46: Slide-In (Kontext), Vollansicht (Workflows/Wissen). v47: Quellen/Ordner als Vollansicht, kein Zahnrad, Fenster 20 % kleiner.
import ctypes, queue, re, time, tkinter as tk
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk
import os
from pathlib import Path                                            # v71
from . import VERSION, log, hilfe
from .config import MODELS, load_settings, save_settings, location_warning
from .connectors import CONNECTORS
from .llm import discover
from .opener import open_item
from .worker import Worker

APP_NAME = "AURA"
SUBTITLE = "Artificial Understanding & Retrieval Assistant"
F = "Segoe UI"
# Farbpaare (hell, dunkel) - folgen automatisch dem Windows-Farbschema
BG      = ("#F4F5FA", "#0B1020")          # v68: Navy-Schema
SIDE    = ("#FFFFFF", "#10172E")
CARD    = ("#EEF0F7", "#18213D")
BUBBLE  = ("#FFFFFF", "#151D36")
BORDER  = ("#E1E4EE", "#263156")
INK     = ("#111827", "#E6E9F2")
MUTED   = ("#6B7280", "#8E98B5")
ACCENT, ACCENT_HI = "#6E56F8", "#5A43E0"
TEAL    = ("#0F9D7A", "#2DD4A4")          # v68: Statusfarbe der Info-Leiste
OK, OFF, ERR = "#10B981", ("#C4C8CF", "#4B5260"), "#E5484D"
BLUE    = "#3B82F6"                        # v109: Balken «läuft»
FH = "Georgia"
MODI = {"Hell": "light", "Dunkel": "dark", "System": "system"}            # v69                            # v68: Serifen nur für wenige Überschriften
# v46: Startfragen. Mit «XY» wird nur ins Eingabefeld uebernommen (XY markiert), sonst sofort gefragt.
SUGGESTIONS = ["Welche Termine habe ich diese Woche?",
               "Welche Mails habe ich heute erhalten?",
               "Welche Informationen sind zum Thema XY vorhanden?"]
# v68: Kacheln der Startseite (Symbol, Titel, Untertitel, Frage; None = Workflows öffnen)
TILES = [("▦", "Termine diese Woche", "Kalender aus Outlook", SUGGESTIONS[0]),
         ("✉", "Mails von heute", "Posteingang, lokal durchsucht", SUGGESTIONS[1]),
         ("⌕", "Thema suchen", "Mails, Dokumente, Verlauf", SUGGESTIONS[2]),
         ("▶", "Workflow starten", "Abläufe und Ergebnisse", None)]

def visible(t):
    """Qwen3-Denkteil <think>…</think> nicht anzeigen (auch leer, wie bei /no_think)."""
    if "<think>" not in t: return t.strip()
    return t.split("</think>", 1)[1].strip() if "</think>" in t else ""

def font(size=13, weight="normal"): return ctk.CTkFont(family=F, size=size, weight=weight)
def hfont(size=18): return ctk.CTkFont(family=FH, size=size, weight="bold")
def fmt(v): return f"{v:,}".replace(",", "'")
def secs(v): return f"{v:.0f} s" if v >= 10 else f"{v:.1f} s"

class App:
    def __init__(self, root):
        from .db import vor_start_zuruecksetzen                        # v60: vor dem Öffnen der Datenbank
        try: reset = vor_start_zuruecksetzen()
        except Exception as e: reset = f"Zurücksetzen fehlgeschlagen: {e}"
        self.root, self.w = root, Worker(); self.w.start()
        self.s = load_settings(); self.buttons = []; self.cur = None; self.cur_text = ""; self.t_ask = 0.0
        self.win = None; self.rows = {}; self.src_btns = []; self.stats = {}; self.busy = False
        # v46: Slide-In (rechts) und Vollansichten (Hauptbereich)
        self.pnl = self.pnl_key = self.pnl_close = self._pnl_job = None; self.pnl_w = self.pnl_x = 0
        self.views = {}; self.view_cur = self.view_prev = None
        self._pb_job = None; self._pb_ind = False; self._pb_fail = False          # v109
        # CustomTkinter multipliziert geometry() mit der Windows-Skalierung (z.B. 150 %) -> vorher herausrechnen
        sc = ctk.ScalingTracker.get_window_scaling(root) or 1.0
        sw, sh = root.winfo_screenwidth() / sc, root.winfo_screenheight() / sc
        W, H = int(min(sw * 0.80, 1480)), int(min(sh * 0.72, 820))   # v68: breiter wegen Info-Leiste rechts
        root.geometry(f"{W}x{H}+{int((sw - W) / 2)}+{int(max(0, (sh - H) / 3))}")
        root.title(f"{APP_NAME} – {SUBTITLE}"); root.minsize(820, 560); root.configure(fg_color=BG)
        root.grid_columnconfigure(1, weight=1); root.grid_rowconfigure(0, weight=1)
        self.last_speed = None                                         # v68: Tempo der letzten Antwort (Info-Leiste)
        self._sidebar(); self._main(); self._rightbar()
        hilfe.auto(root, "haupt")                                      # v38: Infotexte
        root.bind("<Escape>", lambda e: self.close_panel(), add="+")   # v46: Slide-In schliessen
        warn = location_warning()
        if warn: self.bubble(warn, "err")
        if reset is True: self.bubble("AURA wurde zurückgesetzt: Mails, Termine, Verlauf und Dokumente sind entfernt, alle Quellen "
                                      "abgewählt, der Auto-Abgleich ist aus. Unter «Wissen › Quellen» neu verbinden.", "a")
        elif reset: self.bubble(reset, "err")
        root.after(100, self.poll)
        # v23: automatischer Abgleich - erster Lauf 2 min nach dem Start, danach alle autosync_min Minuten
        self.fvars = {}; self.flist = []; self.confirm_open = False; self.decline_until = 0.0
        self.next_auto = time.time() + 120; root.after(30000, self.autotick)
        root.after(1500, self._erg_badge)                              # v54
        if self.s.get("startseite") == "widgets": root.after(300, self.open_widgets)   # v81
        root.bind("<Configure>", self._on_resize, add="+"); root.after(400, self._rb_apply)   # v68

    # ------------------------------------------------------------------ Seitenleiste (v109: aufklappbare Gruppen)
    def _sidebar(self):
        side = ctk.CTkFrame(self.root, width=280, corner_radius=0, fg_color=SIDE, border_width=0)
        side.grid(row=0, column=0, sticky="nsw"); side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1); side.grid_rowconfigure(1, weight=1)
        # Kopf: Logo, Name, ⌂
        hd = ctk.CTkFrame(side, fg_color="transparent"); hd.grid(row=0, column=0, sticky="ew", padx=(20, 14), pady=(22, 0))
        hd.grid_columnconfigure(1, weight=1)
        logo = self._logo(40)                                            # v71
        if logo is not None: ctk.CTkLabel(hd, text="", image=logo, width=40, height=40).grid(row=0, column=0)
        else: ctk.CTkLabel(hd, text="◆", width=36, height=36, corner_radius=10, fg_color=ACCENT,
                           text_color="white", font=font(16, "bold")).grid(row=0, column=0)
        tt = ctk.CTkFrame(hd, fg_color="transparent"); tt.grid(row=0, column=1, sticky="w", padx=10)
        ctk.CTkLabel(tt, text=APP_NAME, font=font(20, "bold"), text_color=INK, height=22).pack(anchor="w")
        ctk.CTkLabel(tt, text="Artificial Understanding &\nRetrieval Assistant", font=font(11), text_color=MUTED,
                     justify="left", anchor="w").pack(anchor="w")                     # v69
        ctk.CTkButton(hd, text="⌂", width=34, height=34, corner_radius=10, font=font(18, "bold"), fg_color=CARD,
                      hover_color=BORDER, text_color=ACCENT, command=self.go_home).grid(row=0, column=2, sticky="e")   # v79

        menu = ctk.CTkFrame(side, fg_color="transparent"); menu.grid(row=1, column=0, sticky="new", padx=12, pady=(20, 0))
        self.grp = {}; self.grp_cur = None

        # ---- Chat: Sprachmodell, 8 Bit
        b = self._grp(menu, "Chat", "Sprachmodell wählen, laden und 8 Bit.")
        self.models = discover(MODELS); ids = [m[0] for m in self.models]
        self.om = ctk.CTkOptionMenu(b, values=[m[1] for m in self.models], height=32, corner_radius=8,
                                    font=font(12), dropdown_font=font(12), fg_color=CARD, button_color=CARD,
                                    button_hover_color=BORDER, text_color=INK, command=self.pick_model, dynamic_resizing=False)
        self.om.set(self.models[ids.index(self.s["llm"])][1] if self.s["llm"] in ids else self.models[0][1])
        self.om.grid(row=0, column=0, sticky="ew"); hilfe.tip(self.om, "#modell")
        lrow = ctk.CTkFrame(b, fg_color="transparent"); lrow.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        lrow.grid_columnconfigure(1, weight=1)
        self.llm_dot = ctk.CTkLabel(lrow, text="●", text_color=OFF, font=font(12), width=14); self.llm_dot.grid(row=0, column=0)
        self.llm_info = ctk.CTkLabel(lrow, text="nicht geladen", font=font(11), text_color=MUTED, anchor="w")
        self.llm_info.grid(row=0, column=1, sticky="w", padx=(6, 0)); hilfe.tip(self.llm_info, "#modell_status")
        self.b_llm = ctk.CTkButton(lrow, text="Laden", width=76, height=28, corner_radius=8, font=font(12, "bold"),
                                   fg_color=ACCENT, hover_color=ACCENT_HI, command=self.toggle_llm)
        self.b_llm.grid(row=0, column=2); self.llm_ready = False
        self.q8_var = tk.BooleanVar(value=bool(self.s.get("llm_int8", False)))                # v70
        self._switch(b, "8 Bit (schneller)", self.q8_var, self.toggle_q8, 2)
        self._llm_view("none" if self.s["llm"] == "extractive" else "off",
                       "kein Laden noetig" if self.s["llm"] == "extractive" else "nicht geladen")

        # ---- Wissen: Quellen, Wissenssammlungen
        b = self._grp(menu, "Wissen", "Quellen verbinden und Wissenssammlungen pflegen.")
        self._item(b, "Quellen", self.open_sources, 0)
        hilfe.tip(self._item(b, "Wissenssammlungen", self.open_wissen, 1), hilfe.TEXTE["haupt"]["Wissen"])

        # ---- Workflows
        b = self._grp(menu, "Workflows", "Workflows öffnen, Ergebnisse und Widgets.")
        self._item(b, "Workflows öffnen", self.open_workflows, 0)
        self.b_erg = self._item(b, "Ergebnisse", self.open_ergebnisse, 1)                  # v54
        hilfe.tip(self.b_erg, "Ergebnisse aller Workflows: neueste zuerst, mit Öffnen, Speichern und Laufordner.")
        hilfe.tip(self._item(b, "Widgets", self.open_widgets, 2), hilfe.TEXTE["haupt"]["▶"])

        # ---- Einstellungen
        b = self._grp(menu, "Einstellungen", "Abgleich, Anzeige und Protokoll.")
        self.auto_var = tk.BooleanVar(value=bool(self.s.get("autosync", True)))           # v23
        self._switch(b, "Auto-Abgleich", self.auto_var, self.toggle_auto, 0, pady=(0, 0))
        self.auto_lbl = ctk.CTkLabel(b, text=self._auto_text(), font=font(10), text_color=MUTED, anchor="w", height=16)
        self.auto_lbl.grid(row=1, column=0, sticky="w", padx=(42, 0)); hilfe.tip(self.auto_lbl, "#auto_status")
        self.wissen_var = tk.BooleanVar(value=bool(self.s.get("wissen_chat", False)))       # v28
        self._switch(b, "Wissen im Chat", self.wissen_var, self.toggle_wissen, 2)
        self.rb_var = tk.BooleanVar(value=bool(self.s.get("rechte_leiste", True)))          # v68
        self._switch(b, "Info-Leiste rechts", self.rb_var, self.toggle_rb, 3)
        self.start_var = tk.BooleanVar(value=self.s.get("startseite") == "widgets")          # v82
        self._switch(b, "Beim Start Widgets zeigen", self.start_var, self.set_start, 4)
        self.sb_mode = ctk.CTkSegmentedButton(b, values=list(MODI), height=26, font=font(11), command=self.set_mode,  # v69
                                              selected_color=ACCENT, selected_hover_color=ACCENT_HI, unselected_color=CARD,
                                              unselected_hover_color=BORDER, fg_color=CARD, text_color=INK)
        self.sb_mode.set(next((k for k, v in MODI.items() if v == self.s.get("darstellung", "system")), "System"))
        self.sb_mode.grid(row=5, column=0, sticky="ew", pady=(10, 4))
        hilfe.tip(self.sb_mode, "Darstellung: Hell, Dunkel oder wie Windows (System). Wird gespeichert.")
        hilfe.tip(self._item(b, "Log öffnen", self.open_log, 6), hilfe.TEXTE["*"]["#version"])

        self._grp_open(self.s.get("menu_offen", "Chat") or None, save=False)

        # ---- Aufgaben (unten)
        tb = ctk.CTkFrame(side, fg_color=CARD, corner_radius=10); tb.grid(row=2, column=0, sticky="sew", padx=12, pady=(8, 4))
        tb.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(tb, text="AUFGABEN", font=font(10, "bold"), text_color=MUTED, anchor="w").grid(
            row=0, column=0, sticky="w", padx=12, pady=(8, 0))
        self.prog = ctk.CTkLabel(tb, text="Bereit", font=font(11), text_color=INK, wraplength=230, justify="left", anchor="w")
        self.prog.grid(row=1, column=0, sticky="ew", padx=12); hilfe.tip(self.prog, "#fortschritt")
        self.pb = ctk.CTkProgressBar(tb, height=6, corner_radius=3, progress_color=BLUE, fg_color=BORDER)
        self.pb.grid(row=2, column=0, sticky="ew", padx=12, pady=(6, 8)); self.pb.set(0)
        box = ctk.CTkFrame(tb, fg_color="transparent"); box.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 10))
        box.grid_columnconfigure(0, weight=1)
        self.b_embed = ctk.CTkButton(box, text="Vektoren berechnen", height=28, corner_radius=8, font=font(12, "bold"),
                                     fg_color=ACCENT, hover_color=ACCENT_HI, command=lambda: self.w.submit("embed"))
        self.b_embed.grid(row=0, column=0, sticky="ew"); self.buttons.append(self.b_embed)
        ctk.CTkButton(box, text="Pause", width=64, height=28, corner_radius=8, font=font(12), fg_color=SIDE,
                      hover_color=BORDER, text_color=INK, command=self.w.cancel.set).grid(row=0, column=1, padx=(6, 0))
        vl = ctk.CTkLabel(side, text=f"Version {VERSION}  ·  lokal, ohne Cloud", font=font(10), text_color=MUTED, cursor="hand2")
        vl.bind("<Button-1>", lambda e: self.open_log()); hilfe.tip(vl, "#version")
        vl.grid(row=3, column=0, sticky="sw", padx=20, pady=(2, 10))

    def _grp(self, menu, name, tiptext):
        """v109: Gruppenkopf (Wort ohne Pfeil) + Inhalt; Klick klappt auf/zu."""
        h = ctk.CTkButton(menu, text=name, anchor="w", height=34, corner_radius=8, font=font(14, "bold"), fg_color="transparent",
                          hover_color=CARD, text_color=INK, command=lambda: self._grp_open(name))
        h.pack(fill="x", pady=(2, 0)); hilfe.tip(h, tiptext)
        b = ctk.CTkFrame(menu, fg_color="transparent"); b.grid_columnconfigure(0, weight=1)
        self.grp[name] = (h, b); return b

    def _grp_open(self, name, save=True):
        if name == self.grp_cur: name = None                           # zweiter Klick schliesst
        if name not in self.grp: name = None
        for n, (h, b) in self.grp.items():
            if n == name: b.pack(fill="x", after=h, padx=(10, 2), pady=(2, 10)); h.configure(text_color=ACCENT)
            else: b.pack_forget(); h.configure(text_color=INK)
        self.grp_cur = name
        if save:
            self.s = load_settings(); self.s["menu_offen"] = name or ""; save_settings(self.s)

    def _item(self, parent, text, cmd, r):
        b = ctk.CTkButton(parent, text=text, anchor="w", height=30, corner_radius=8, font=font(12), fg_color="transparent",
                          hover_color=CARD, text_color=INK, command=cmd)
        b.grid(row=r, column=0, sticky="ew", pady=1); return b

    def _switch(self, parent, text, var, cmd, r, pady=(8, 0)):
        s = ctk.CTkSwitch(parent, text=text, variable=var, font=font(11), text_color=INK, progress_color=ACCENT,
                          switch_width=32, switch_height=16, command=cmd)
        s.grid(row=r, column=0, sticky="w", padx=(2, 0), pady=pady); return s

    # ---- v109: Balken im Bereich «Aufgaben»
    def _pb_cancel(self):
        if self._pb_job:
            try: self.root.after_cancel(self._pb_job)
            except Exception: pass
            self._pb_job = None

    def _pb_det(self):
        if self._pb_ind:
            self.pb.stop(); self.pb.configure(mode="determinate"); self._pb_ind = False

    def _pb_start(self):
        self._pb_cancel(); self._pb_fail = False
        self.pb.configure(progress_color=BLUE)
        if not self._pb_ind: self.pb.configure(mode="indeterminate"); self.pb.start(); self._pb_ind = True

    def _pb_value(self, v):
        self._pb_det(); self.pb.configure(progress_color=ERR if self._pb_fail else BLUE); self.pb.set(v)

    def _pb_done(self):
        self._pb_cancel(); self._pb_det()
        self.pb.configure(progress_color=ERR if self._pb_fail else OK); self.pb.set(1)
        self._pb_job = self.root.after(15000 if self._pb_fail else 5000, self._pb_reset)

    def _pb_error(self):
        self._pb_fail = True; self._pb_det(); self.pb.configure(progress_color=ERR); self.pb.set(1)

    def _pb_reset(self):
        self._pb_job = None; self._pb_fail = False
        self.pb.configure(progress_color=BLUE); self.pb.set(0); self.prog.configure(text="Bereit")

    def _title(self, parent, text, r):
        ctk.CTkLabel(parent, text=text.upper(), font=font(10, "bold"), text_color=MUTED, anchor="w").grid(
            row=r, column=0, sticky="w", padx=22, pady=(20, 6))
        return r + 1

    # ------------------------------------------------------------------ v68: Info-Leiste rechts
    RB_MIN = 1180                     # Fensterbreite (ohne Windows-Skalierung), unter der sich die Leiste ausblendet

    def _rightbar(self):
        """Nur Anzeige: liest Werte, die schon vorliegen (Statistik, Modellzustand, protokoll.json). Legt nie Jobs in den Worker."""
        rb = self.rb = ctk.CTkFrame(self.root, width=300, corner_radius=0, fg_color=SIDE)
        rb.grid_propagate(False); rb.pack_propagate(False)
        sf = ctk.CTkScrollableFrame(rb, fg_color="transparent", scrollbar_button_color=BORDER, scrollbar_button_hover_color=MUTED)
        sf.pack(fill="both", expand=True, padx=2, pady=10); sf.grid_columnconfigure(0, weight=1)
        # --- Sprachmodell
        c = self._rb_card(sf, "SPRACHMODELL", 0)
        self.rb_mname = ctk.CTkLabel(c, text="", font=hfont(15), text_color=INK, anchor="w", justify="left", wraplength=240)
        self.rb_mname.grid(row=1, column=0, sticky="w", padx=14)
        self.rb_mtyp = ctk.CTkLabel(c, text="", font=font(10), text_color=MUTED, anchor="w", height=14)
        self.rb_mtyp.grid(row=4, column=0, sticky="w", padx=14, pady=(0, 10))      # v69: Architektur klein
        self.rb_mstate = ctk.CTkLabel(c, text="", font=font(11), text_color=MUTED, anchor="w")
        self.rb_mstate.grid(row=2, column=0, sticky="w", padx=14, pady=(2, 0))
        self.rb_mspeed = ctk.CTkLabel(c, text="", font=font(11), text_color=MUTED, anchor="w", justify="left", wraplength=230)
        self.rb_mspeed.grid(row=3, column=0, sticky="w", padx=14, pady=(2, 2))
        hilfe.tip(c, "Gewähltes Sprachmodell und sein Zustand. Tempo = Schreibgeschwindigkeit der letzten Antwort im Chat.")
        # --- Vektordatenbank
        c = self._rb_card(sf, "WISSEN · DATENBANK", 1)
        self.rb_vbig = ctk.CTkLabel(c, text="–", font=hfont(18), text_color=INK, anchor="w")
        self.rb_vbig.grid(row=1, column=0, sticky="w", padx=14)
        self.rb_vsub = ctk.CTkLabel(c, text="", font=font(11), text_color=MUTED, anchor="w")
        self.rb_vsub.grid(row=2, column=0, sticky="w", padx=14)
        self.rb_vbar = ctk.CTkProgressBar(c, height=6, corner_radius=3, progress_color=TEAL, fg_color=BORDER)
        self.rb_vbar.grid(row=3, column=0, sticky="ew", padx=14, pady=(8, 6)); self.rb_vbar.set(0)
        self.rb_vsrc = ctk.CTkFrame(c, fg_color="transparent"); self.rb_vsrc.grid(row=4, column=0, sticky="ew", padx=10)
        self.rb_vsrc.grid_columnconfigure(0, weight=1)
        self.rb_vauto = ctk.CTkLabel(c, text="", font=font(10), text_color=MUTED, anchor="w", justify="left", wraplength=230)
        self.rb_vauto.grid(row=5, column=0, sticky="w", padx=14, pady=(4, 12))
        hilfe.tip(c, "Eingelesene Objekte und Textstücke je Quelle. Der Balken zeigt, wie viele Textstücke schon einen Vektor haben "
                     "(Suche nach Bedeutung). Unter 100 %: links «Vektoren berechnen».")
        # --- Workflows
        c = self._rb_card(sf, "WORKFLOWS", 2)
        ctk.CTkButton(c, text="alle anzeigen →", width=0, height=20, corner_radius=8, font=font(11), fg_color="transparent",
                      hover_color=BORDER, text_color=ACCENT, command=self.open_ergebnisse).grid(row=0, column=0, sticky="e", padx=10, pady=(8, 0))
        self.rb_plan = ctk.CTkLabel(c, text="", font=font(11), text_color=INK, anchor="w", justify="left", wraplength=230)
        self.rb_plan.grid(row=1, column=0, sticky="w", padx=14)
        self.rb_wbox = ctk.CTkFrame(c, fg_color="transparent"); self.rb_wbox.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 10))
        self.rb_wbox.grid_columnconfigure(0, weight=1)
        hilfe.auto(rb, "haupt")
        self._rb_model(); self._rb_stats(); self._rb_runs()

    def _rb_card(self, parent, title, row):
        c = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
        c.grid(row=row, column=0, sticky="ew", padx=8, pady=6); c.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(c, text=title, font=font(10, "bold"), text_color=MUTED, anchor="w").grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))
        return c

    def _rb_ok(self): return getattr(self, "rb", None) is not None

    def _rb_model(self, col=None, text=None):
        if not self._rb_ok(): return
        try:
            nm = self.om.get(); kurz, _, rest = nm.partition(" [")
            self.rb_mname.configure(text=kurz)
            typ = rest.rstrip("]").replace(", ", " · ") if rest else ""
            if self.s.get("llm_int8") and self.s.get("llm") != "extractive": typ = (typ + " · " if typ else "") + "8 Bit"
            self.rb_mtyp.configure(text=typ)
            if text is not None:
                self.rb_mstate.configure(text=f"● {text}", text_color=TEAL if col == OK else ("#F59E0B" if col == "#F59E0B" else MUTED))
            sp = self.last_speed
            self.rb_mspeed.configure(text=(f"Letzte Antwort: {sp[0]:.1f} Tokens/s · {secs(sp[1])} gesamt".replace(".", ",")
                                           if sp else "Noch keine Antwort mit Sprachmodell in dieser Sitzung."))
        except Exception: log.get().exception("Info-Leiste Modell")

    def _rb_stats(self):
        if not self._rb_ok(): return
        try:
            st = self.stats or {}
            on = [c for c in CONNECTORS if c.id in st]
            it = sum(st[c.id].get("items", 0) for c in on); ch = sum(st[c.id].get("chunks", 0) for c in on)
            ve = sum(st[c.id].get("vectors", 0) for c in on)
            self.rb_vbig.configure(text=f"{fmt(it)} Objekte" if on else "Keine Quelle")
            self.rb_vsub.configure(text=f"{fmt(ch)} Textstücke · {ve * 100 // ch if ch else 0} % mit Vektor" if on else "Links «Wissen › Quellen» öffnen")
            self.rb_vbar.set(ve / ch if ch else 0)
            for w in self.rb_vsrc.winfo_children(): w.destroy()
            ctk.CTkLabel(self.rb_vsrc, text=f"{len(on)} VON {len(CONNECTORS)} QUELLEN VERBUNDEN", font=font(9, "bold"),
                         text_color=MUTED, anchor="w").grid(row=0, column=0, columnspan=2, sticky="w", padx=4, pady=(2, 2))
            for i, c in enumerate(CONNECTORS, start=1):
                x = st.get(c.id)
                ctk.CTkLabel(self.rb_vsrc, text=("● " if x else "○ ") + c.label, font=font(11), anchor="w",
                             text_color=INK if x else MUTED).grid(row=i, column=0, sticky="w", padx=4)
                ctk.CTkLabel(self.rb_vsrc, text=fmt(x.get("items", 0)) if x else "–", font=font(11), text_color=MUTED,
                             anchor="e").grid(row=i, column=1, sticky="e", padx=4)
            auto = "ein" if self.s.get("autosync", True) else "aus"
            self.rb_vauto.configure(text=f"Auto-Abgleich {auto}  ·  {self._auto_text()}")
        except Exception: log.get().exception("Info-Leiste Statistik")

    def _rb_runs(self):
        if not self._rb_ok(): return
        try:
            from .ergebnisse import laeufe
            from .workflow.app import WF_DIR
            for w in self.rb_wbox.winfo_children(): w.destroy()
            try:
                from .zeitplan import mit_zeitplan, naechster
                plan = sorted([(naechster(w["zeitplan"]), w["name"]) for w in mit_zeitplan(WF_DIR)], key=lambda x: (x[0] is None, x[0] or 0))
                plan = [p for p in plan if p[0]]
                self.rb_plan.configure(text=f"⏰ Als Nächstes: {plan[0][1]}, {plan[0][0].strftime('%d.%m. %H:%M')}" if plan else "")
            except Exception: self.rb_plan.configure(text="")
            ls = laeufe(WF_DIR, 5)
            if not ls:
                ctk.CTkLabel(self.rb_wbox, text="Noch keine Läufe.", font=font(11), text_color=MUTED, anchor="w").grid(row=0, column=0, sticky="w", padx=6)
            for i, x in enumerate(ls):
                ok = x["status"] == "ok"
                row = ctk.CTkFrame(self.rb_wbox, fg_color="transparent", corner_radius=8); row.grid(row=i, column=0, sticky="ew", pady=1)
                row.grid_columnconfigure(1, weight=1)
                ic = ctk.CTkLabel(row, text="✓" if ok else "✕", width=22, font=font(12, "bold"), text_color=TEAL if ok else ERR)
                ic.grid(row=0, column=0, rowspan=2, padx=(4, 4))
                t1 = ctk.CTkLabel(row, text=("● " if x["neu"] else "") + x["workflow"][:30], font=font(11, "bold" if x["neu"] else "normal"),
                                  text_color=INK, anchor="w", height=16, cursor="hand2")
                t1.grid(row=0, column=1, sticky="w", pady=(4, 0))
                t2 = ctk.CTkLabel(row, text=f"{x['zeit']}  ·  {x['seconds']:.0f} s" + ("" if ok else f"  ·  {x['status']}"), font=font(10),
                                  text_color=MUTED, anchor="w", height=14)
                t2.grid(row=1, column=1, sticky="w", pady=(0, 4))
                for w in (row, ic, t1, t2):
                    w.bind("<Button-1>", lambda e: self.open_ergebnisse())
                    w.bind("<Enter>", lambda e, r=row: r.configure(fg_color=BORDER)); w.bind("<Leave>", lambda e, r=row: r.configure(fg_color="transparent"))
        except Exception: log.get().exception("Info-Leiste Workflows")

    def set_mode(self, label):
        """v69: Hell/Dunkel/System sofort umschalten und speichern."""
        m = MODI.get(label, "system"); ctk.set_appearance_mode(m)
        self.s = load_settings(); self.s["darstellung"] = m; save_settings(self.s)

    def toggle_rb(self):
        self.s = load_settings(); self.s["rechte_leiste"] = bool(self.rb_var.get()); save_settings(self.s)
        self._rb_apply()
        if self.s["rechte_leiste"] and not self.rb.winfo_manager():
            self.status.configure(text="Info-Leiste: Fenster zu schmal – Fenster breiter ziehen, dann erscheint sie.")

    def _rb_apply(self):
        if not self._rb_ok(): return
        sc = ctk.ScalingTracker.get_window_scaling(self.root) or 1.0
        show = bool(self.s.get("rechte_leiste", True)) and self.root.winfo_width() / sc >= self.RB_MIN
        if show and not self.rb.winfo_manager(): self.rb.grid(row=0, column=2, sticky="nse")
        elif not show and self.rb.winfo_manager(): self.rb.grid_remove()
        self.root.after_idle(self._rewrap)

    def _on_resize(self, e):
        if e.widget is not self.root: return
        if getattr(self, "_rs_job", None):
            try: self.root.after_cancel(self._rs_job)
            except Exception: pass
        self._rs_job = self.root.after(250, self._rb_apply)

    # ------------------------------------------------------------------ v46: Slide-In von rechts
    def panel(self, title, key, width=440, on_close=None):
        """Oeffnet ein Slide-In ueber dem Chat (rechts). Liefert den Inhaltsrahmen. on_close wird beim Schliessen gerufen."""
        self.close_panel(anim=False)
        sc = ctk.ScalingTracker.get_widget_scaling(self.root) or 1.0
        width = int(min(width, max(360, self.root.winfo_width() / sc * 0.7)))
        p = ctk.CTkFrame(self.root, width=width, fg_color=SIDE, corner_radius=0, border_width=1, border_color=BORDER)
        p.grid_propagate(False); p.grid_columnconfigure(0, weight=1); p.grid_rowconfigure(1, weight=1)
        hd = ctk.CTkFrame(p, fg_color="transparent"); hd.grid(row=0, column=0, sticky="ew", padx=(20, 10), pady=(14, 6))
        hd.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hd, text=title, font=font(18, "bold"), text_color=INK, anchor="w").grid(row=0, column=0, sticky="w")
        hilfe.tip(ctk.CTkButton(hd, text="✕", width=32, height=32, corner_radius=8, font=font(14), fg_color="transparent",
                                hover_color=CARD, text_color=MUTED, command=self.close_panel), "#panel_zu").grid(row=0, column=1)
        body = ctk.CTkFrame(p, fg_color="transparent"); body.grid(row=1, column=0, sticky="nsew", padx=1, pady=(0, 1))
        body.grid_columnconfigure(0, weight=1)
        self.pnl, self.pnl_key, self.pnl_close, self.pnl_w, self.pnl_x = p, key, on_close, width, 0
        self._slide(+1)
        return body

    def _slide(self, d):
        """d = +1 hinein, -1 hinaus; 8 Schritte à 15 ms."""
        p = self.pnl
        if p is None: return
        try:
            step = max(1, self.pnl_w // 8)
            self.pnl_x = x = min(self.pnl_w, max(0, self.pnl_x + d * step))
            p.place(relx=1.0, x=-x, y=0, relheight=1.0); p.tkraise()          # v47: width nur im Konstruktor erlaubt
        except Exception:
            log.get().exception("Slide-In"); self._destroy_panel(); return
        if (d > 0 and x < self.pnl_w) or (d < 0 and x > 0):
            self._pnl_job = self.root.after(15, lambda: self._slide(d))
        else:
            self._pnl_job = None
            if d < 0: self._destroy_panel()

    def close_panel(self, anim=True):
        if self.pnl is None: return
        if self._pnl_job:
            try: self.root.after_cancel(self._pnl_job)
            except Exception: pass
            self._pnl_job = None
        cb, self.pnl_close, self.pnl_key = self.pnl_close, None, None
        if cb:
            try: cb()
            except Exception: log.get().exception("close_panel")
        if anim: self._slide(-1)
        else: self._destroy_panel()

    def _destroy_panel(self):
        if self.pnl is not None:
            try: self.pnl.destroy()
            except Exception: pass
        self.pnl, self.pnl_key, self.pnl_x = None, None, 0

    # ------------------------------------------------------------------ v46: Vollansichten (Workflows, Wissen)
    def view(self, key, title):
        """Legt eine Vollansicht im Hauptbereich an (ersetzt den Chat, Seitenleiste bleibt). Liefert den Inhaltsrahmen."""
        old = self.views.pop(key, None)
        if old is not None:
            try: old.destroy()
            except Exception: pass
        outer = ctk.CTkFrame(self.root, fg_color=SIDE, corner_radius=0)
        outer.grid_columnconfigure(0, weight=1); outer.grid_rowconfigure(1, weight=1)
        hd = ctk.CTkFrame(outer, fg_color="transparent"); hd.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        hilfe.tip(ctk.CTkButton(hd, text="← Zurück", width=90, height=28, corner_radius=8, font=font(12), fg_color=CARD,
                                hover_color=BORDER, text_color=INK, command=self.back), "#zurueck").pack(side="left")
        ctk.CTkLabel(hd, text=title.upper(), font=font(10, "bold"), text_color=MUTED).pack(side="left", padx=12)
        body = ctk.CTkFrame(outer, fg_color=SIDE, corner_radius=0); body.grid(row=1, column=0, sticky="nsew")
        self.views[key] = outer; self.show_view(key)
        return body

    def show_view(self, key):
        self.close_panel(anim=False)
        if self.view_cur is None: self.view_prev = None
        elif self.view_cur != key: self.view_prev = self.view_cur
        self.mainf.grid_remove()
        for k, v in self.views.items():
            if k != key: v.grid_remove()
        self.views[key].grid(row=0, column=1, sticky="nsew"); self.view_cur = key

    def show_chat(self):
        for v in self.views.values(): v.grid_remove()
        self.mainf.grid(); self.view_cur = self.view_prev = None
        self._welcome_erg()                                              # v60: Startseite aktuell halten
        self.entry.focus_set()

    def back(self):
        """Zurueck zur vorherigen Ansicht (z.B. Wissen -> Workflows), sonst zum Chat. Ansichten bleiben offen."""
        prev = self.view_prev
        if prev in self.views and prev != self.view_cur:
            self.view_cur = None; self.show_view(prev)
        else: self.show_chat()

    # ------------------------------------------------------------------ Quellen (Slide-In, Zahnrad)
    def open_sources(self):
        """v47: Vollansicht wie Wissen/Workflows (bleibt im Hintergrund offen)."""
        if "quellen" in self.views and self.views["quellen"].winfo_exists(): self.show_view("quellen"); return
        body = self.view("quellen", "Quellen")
        w = self.win = ctk.CTkFrame(body, fg_color="transparent"); w.grid(row=0, column=0, sticky="nw", padx=24, pady=12)
        w.grid_columnconfigure(0, weight=1, minsize=520)
        ctk.CTkLabel(w, text="Sync holt nur neue Objekte. Danach unten links «Vektoren berechnen».",
                     font=font(11), text_color=MUTED, anchor="w", justify="left", wraplength=500).grid(
            row=0, column=0, sticky="w", padx=4, pady=(0, 10))
        self.rows, self.src_btns = {}, []
        for i, c in enumerate(CONNECTORS):
            card = ctk.CTkFrame(w, fg_color=CARD, corner_radius=10)
            card.grid(row=1 + i, column=0, sticky="ew", pady=3)
            card.grid_columnconfigure(1, weight=1)
            dot = ctk.CTkLabel(card, text="●", text_color=OFF, font=font(11), width=12)
            dot.grid(row=0, column=0, rowspan=2, padx=(12, 6))
            ctk.CTkLabel(card, text=c.label, font=font(12, "bold"), text_color=INK, anchor="w", height=18).grid(
                row=0, column=1, sticky="w", pady=(7, 0))
            info = ctk.CTkLabel(card, text="noch nicht verbunden", font=font(10), text_color=MUTED,
                                anchor="w", justify="left", height=16)
            info.grid(row=1, column=1, sticky="w", pady=(0, 7))
            btns = ctk.CTkFrame(card, fg_color="transparent"); btns.grid(row=0, column=2, rowspan=2, padx=(12, 10))
            if c.id == "outlook_mail":                              # v23: Ordnerauswahl
                ctk.CTkButton(btns, text="Ordner", width=56, height=24, corner_radius=7, font=font(11), fg_color=BORDER,
                              hover_color=MUTED, text_color=INK, command=self.open_folders).pack(side="left", padx=(0, 4))
            if c.id == "folder_docs":
                ctk.CTkButton(btns, text="…", width=26, height=24, corner_radius=7, fg_color=BORDER,
                              hover_color=MUTED, text_color=INK, command=self.pick_folder).pack(side="left", padx=(0, 4))
                ctk.CTkButton(btns, text="✕", width=26, height=24, corner_radius=7, fg_color=BORDER,      # v37: Ordner entfernen
                              hover_color=MUTED, text_color=INK, command=self.remove_folder).pack(side="left", padx=(0, 4))
            if c.id == "onenote":                                   # v87: Abschnittsauswahl
                ctk.CTkButton(btns, text="Abschnitte", width=76, height=24, corner_radius=7, font=font(11), fg_color=BORDER,
                              hover_color=MUTED, text_color=INK, command=lambda: self.open_folders("onenote")).pack(side="left", padx=(0, 4))
            if c.id == "confluence":                                # v78: Links verwalten
                ctk.CTkButton(btns, text="Links", width=52, height=24, corner_radius=7, font=font(11), fg_color=BORDER,
                              hover_color=MUTED, text_color=INK, command=self.open_confluence).pack(side="left", padx=(0, 4))
            b = ctk.CTkButton(btns, text="Sync", width=48, height=24, corner_radius=7, font=font(11, "bold"),
                              fg_color=ACCENT, hover_color=ACCENT_HI, command=lambda c=c: self.sync(c)); b.pack(side="left")
            self.src_btns.append(b); self.rows[c.id] = (dot, info)
        rz = ctk.CTkFrame(w, fg_color="transparent"); rz.grid(row=2 + len(CONNECTORS), column=0, sticky="ew", pady=(24, 0))   # v60
        ctk.CTkButton(rz, text="Alles zurücksetzen …", height=28, corner_radius=8, font=font(11), fg_color="transparent",
                      border_width=1, border_color=ERR, hover_color=BORDER, text_color=ERR, command=self.reset_all).pack(side="left")
        ctk.CTkLabel(rz, text="  Löscht alle eingelesenen Daten und beendet alle Synchronisationen.", font=font(10),
                     text_color=MUTED).pack(side="left")
        self._show_stats(); hilfe.auto(w, "quellen")
        for b in self.src_btns: b.configure(state="disabled" if self.busy else "normal")

    def reset_all(self):
        """v60: Datenbank (Mails, Termine, Verlauf, Dokumente) löschen, Quellen abwählen, Auto-Abgleich aus – mit Neustart."""
        import subprocess, sys
        from .db import zuruecksetzen_vormerken
        n = sum(v.get("items", 0) for v in (self.stats or {}).values())
        if not messagebox.askyesno(APP_NAME, f"Alles zurücksetzen?\n\nGelöscht werden:\n• alle eingelesenen Mails, Termine, Verlaufseinträge "
                                   f"und Dokumente ({fmt(n)} Objekte) samt Vektoren\n• der Stand aller Synchronisationen\n"
                                   "• die Auswahl der Outlook-Ordner und des Dokumentordners\n• der Vorspann-Cache der Workflows\n\n"
                                   "Der Auto-Abgleich wird ausgeschaltet.\n\nBleiben erhalten: Outlook und alle Originaldateien, "
                                   "Wissenssammlungen, Workflows, Ergebnisse, Sprachmodelle.", icon="warning", parent=self.root): return
        if not messagebox.askyesno(APP_NAME, "Wirklich? Das lässt sich nicht rückgängig machen.\n\nAURA startet danach neu.",
                                   icon="warning", default="no", parent=self.root): return
        try:
            self.s = load_settings()
            self.s.update(mail_folders={}, onenote_sections={}, docs_folder="", confluence_links=[], autosync=False, autosync_last=""); save_settings(self.s)
            zuruecksetzen_vormerken()
        except Exception as e: messagebox.showerror(APP_NAME, f"Nicht zurückgesetzt: {e}", parent=self.root); return
        log.get().info("Alles zurücksetzen: vorgemerkt, Neustart")
        try: self.w.cancel.set()                                     # laufende Arbeit abbrechen
        except Exception: pass
        try: subprocess.Popen([sys.executable] + sys.argv, cwd=os.getcwd())
        except Exception as e:
            messagebox.showinfo(APP_NAME, f"Bitte AURA selbst neu starten – das Zurücksetzen erfolgt beim nächsten Start.\n({e})",
                                parent=self.root)
        try: self.root.destroy()
        finally: os._exit(0)                                          # Worker sofort beenden, damit die Datenbank frei wird

    def _close_sources(self):
        self.win, self.rows, self.src_btns = None, {}, []

    def _show_stats(self):
        st = self.stats
        for cid, (dot, info) in self.rows.items():
            x = st.get(cid)
            if x:
                dot.configure(text_color=OK)
                info.configure(text=f"{fmt(x.get('items', 0))} Objekte · {fmt(x.get('vectors', 0))}/{fmt(x.get('chunks', 0))} Vektoren"
                               + (f"\nzuletzt {x['last_sync']}" if x.get("last_sync") else ""), height=0)
        self._rb_stats()                                                 # v68

    # ------------------------------------------------------------------ Chatbereich
    def _main(self):
        main = self.mainf = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0); main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1); main.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(main, text="Fragen", font=font(22, "bold"), text_color=INK, anchor="w").grid(
            row=0, column=0, sticky="w", padx=36, pady=(26, 6))
        self.chat = ctk.CTkScrollableFrame(main, fg_color="transparent", corner_radius=0,
                                           scrollbar_button_color=BORDER, scrollbar_button_hover_color=MUTED)
        self.chat.grid(row=1, column=0, sticky="nsew", padx=24)
        self.chat.grid_columnconfigure(0, weight=1)
        self.chat.bind("<Configure>", lambda e: self._rewrap(), add="+")   # add="+": CTk-eigene Scroll-Bindung behalten
        self.msgs = []; self._welcome()
        # Eingabe: mehrzeilig, Enter = senden, Shift+Enter = neue Zeile
        bar = ctk.CTkFrame(main, fg_color=BUBBLE, corner_radius=16, border_width=1, border_color=BORDER)
        bar.grid(row=2, column=0, sticky="ew", padx=36, pady=(10, 6)); bar.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkTextbox(bar, height=84, font=font(14), fg_color="transparent", text_color=INK,
                                    wrap="word", border_width=0, activate_scrollbars=False)
        self.entry.grid(row=0, column=0, sticky="ew", padx=(14, 6), pady=10)
        self.entry.bind("<Return>", self._enter); self.entry.focus_set(); hilfe.tip(self.entry, "#frage")
        self.b_ask = ctk.CTkButton(bar, text="➤", width=46, height=46, corner_radius=23, font=font(18, "bold"),
                                   fg_color=ACCENT, hover_color=ACCENT_HI, command=self.ask)
        self.b_ask.grid(row=0, column=1, padx=(0, 12), pady=10, sticky="se"); self.buttons.append(self.b_ask)
        self.follow = False                                              # v67: Bezug zur letzten Frage (einmalig)
        tools = ctk.CTkFrame(bar, fg_color="transparent", height=24)     # v98: Werkzeugzeile (Bezug, Anhang) links unten
        tools.grid(row=1, column=0, columnspan=2, sticky="w", padx=(14, 12), pady=(0, 10))
        self.b_follow = ctk.CTkButton(tools, text="↳ Bezug zur letzten Frage", height=24, corner_radius=12, font=font(11),
                                      fg_color="transparent", hover_color=BORDER, text_color=MUTED, border_width=1,
                                      border_color=BORDER, command=self.toggle_follow)
        self.b_follow.pack(side="left")
        self.b_anhang = ctk.CTkButton(tools, text="📎 Datei anhängen", height=24, corner_radius=12, font=font(11),
                                      fg_color="transparent", hover_color=BORDER, text_color=MUTED, border_width=1,
                                      border_color=BORDER, command=self.add_anhang)
        self.b_anhang.pack(side="left", padx=(8, 0)); self.buttons.append(self.b_anhang)
        self.anh_box = ctk.CTkFrame(tools, fg_color="transparent", width=1, height=1)   # v98: leer = keine Hoehe
        self.status = ctk.CTkLabel(main, text="Enter = senden  ·  Shift+Enter = neue Zeile", font=font(11),
                                   text_color=MUTED, anchor="w")
        self.status.grid(row=3, column=0, sticky="ew", padx=40, pady=(0, 12))

    def _welcome(self):
        f = ctk.CTkFrame(self.chat, fg_color="transparent"); f.grid(row=0, column=0, pady=(24, 0))
        ctk.CTkLabel(f, text="Woran arbeitest du heute?", font=hfont(28), text_color=INK).pack()
        ctk.CTkLabel(f, text="AURA durchsucht deine Mails, Termine, deinen Verlauf und Dokumente – lokal auf diesem Rechner.",
                     font=font(13), text_color=MUTED).pack(pady=(6, 22))
        grid = ctk.CTkFrame(f, fg_color="transparent"); grid.pack()       # v68: Kacheln 2 × 2
        for i, t in enumerate(TILES): self._tile(grid, *t).grid(row=i // 2, column=i % 2, padx=6, pady=6, sticky="nsew")
        self.welcome = f

    def open_widgets(self):
        """v81: Ansicht «Workflow-Ergebnisse» – angeheftete Workflows als Widgets in voller Breite."""
        d = getattr(self, "dash", None)
        if "widgets" in self.views and self.views["widgets"].winfo_exists() and d is not None and d.alive():
            self.show_view("widgets"); d.draw(); return
        body = self.view("widgets", "Workflow-Ergebnisse"); body.grid_columnconfigure(0, weight=1); body.grid_rowconfigure(0, weight=1)
        sf = ctk.CTkScrollableFrame(body, fg_color="transparent"); sf.grid(row=0, column=0, sticky="nsew", padx=20, pady=8)
        sf.grid_columnconfigure(0, weight=1)
        try:
            from .dashboard import Widgets
            self.dash = Widgets(self, sf); self.dash.frame.grid(row=0, column=0, sticky="ew")
        except Exception as e:
            log.get().exception("Widgets"); self.dash = None
            ctk.CTkLabel(sf, text=f"Widgets nicht verfügbar: {e}", text_color=ERR).grid(row=0, column=0, sticky="w")

    def set_start(self, _=None):
        """v82: Welche Seite AURA beim Start zeigt (Schalter ein = Widgets, aus = Fragen). Wirkt beim nächsten Start."""
        self.s = load_settings(); self.s["startseite"] = "widgets" if self.start_var.get() else "chat"; save_settings(self.s)
        self.status.configure(text="Beim nächsten Start: " + ("Widgets" if self.start_var.get() else "Fragen (⌂)"))

    def go_home(self):
        """v79: zurück zur Startseite (Kacheln + Ablaufband); der Chatverlauf wird geleert."""
        if self.cur: self.status.configure(text="Bitte warten, bis die Antwort fertig ist."); return
        self.close_panel(anim=False); self.show_chat()
        for c in self.chat.winfo_children(): c.destroy()
        self.msgs = []; self.welcome = None; self._welcome()
        self.w.submit("anhang_leeren")                                   # v97: neuer Chat = ohne Anhang
        try: self.chat._parent_canvas.yview_moveto(0)
        except Exception: pass

    def _logo(self, size):
        """v71: Logo als PNG passend zur Windows-Skalierung (Tk kann PNG ohne Zusatzpaket). None = Datei fehlt."""
        import warnings
        try:
            sc = ctk.ScalingTracker.get_window_scaling(self.root) or 1.0
            want = size * sc; d = Path(__file__).resolve().parent / "assets"
            n = next((n for n in (40, 60, 80, 256) if n >= want - 2), 256)
            img = tk.PhotoImage(master=self.root, file=str(d / f"logo_{n}.png"))
            f = max(1, round(n / want))
            if f > 1: img = img.subsample(f, f)
            self._logo_img = img; warnings.filterwarnings("ignore", message=".*CTkImage.*")
            return img
        except Exception: return None

    def _tile(self, parent, sym, title, sub, q):
        """v68: Kachel der Startseite; Klick auf jeden Teil löst aus."""
        c = ctk.CTkFrame(parent, fg_color=BUBBLE, corner_radius=14, border_width=1, border_color=BORDER, width=300, height=74)
        c.grid_propagate(False); c.grid_columnconfigure(1, weight=1)
        ic = ctk.CTkLabel(c, text=sym, width=38, height=38, corner_radius=10, fg_color=CARD, text_color=ACCENT, font=font(16, "bold"))
        ic.grid(row=0, column=0, rowspan=2, padx=(14, 10), pady=16)
        t1 = ctk.CTkLabel(c, text=title, font=font(13, "bold"), text_color=INK, anchor="w", height=18, cursor="hand2")
        t1.grid(row=0, column=1, sticky="sw", pady=(16, 0))
        t2 = ctk.CTkLabel(c, text=sub, font=font(11), text_color=MUTED, anchor="w", height=16)
        t2.grid(row=1, column=1, sticky="nw", pady=(0, 16))
        go = (lambda e=None: self.open_workflows()) if q is None else (lambda e=None, q=q: self._fill(q))
        for w in (c, ic, t1, t2):
            w.bind("<Button-1>", go)
            w.bind("<Enter>", lambda e: c.configure(border_color=ACCENT)); w.bind("<Leave>", lambda e: c.configure(border_color=BORDER))
        hilfe.tip(c, "Öffnet die Workflows mit ihren Ergebnissen." if q is None else hilfe.TEXTE["*"]["#beispiel"])
        return c

    def _welcome_erg(self):
        """v68: «Letzte Ergebnisse» steht jetzt in der Info-Leiste rechts (Name bleibt, wird von mehreren Stellen gerufen)."""
        self._rb_runs()
        d = getattr(self, "dash", None)                                  # v79
        if d is not None and d.alive(): d.draw()

    def _fill(self, s):
        """v46: ohne «XY» sofort fragen; mit «XY» nur einsetzen und XY markieren (Tippen ersetzt es)."""
        self.entry.delete("1.0", "end"); self.entry.insert("1.0", s); self.entry.focus_set()
        i = s.find("XY")
        if i < 0: self.ask(); return
        t = getattr(self.entry, "_textbox", self.entry)
        try:
            t.tag_remove("sel", "1.0", "end"); t.tag_add("sel", f"1.{i}", f"1.{i + 2}"); t.mark_set("insert", f"1.{i + 2}")
        except Exception: pass

    def _enter(self, e):
        if e.state & 0x1: return None             # Shift gedrueckt -> normale neue Zeile
        self.ask(); return "break"

    def _wrap(self):
        # winfo_width liefert echte Pixel, wraplength wird von CustomTkinter nochmals skaliert -> herausrechnen
        sc = ctk.ScalingTracker.get_widget_scaling(self.chat) or 1.0
        return max(320, int(self.chat.winfo_width() / sc * 0.72))
    def _rewrap(self):
        for lbl in self.msgs: lbl.configure(wraplength=self._wrap())

    def bubble(self, text, kind="a"):
        """kind: q (Frage, rechts) | a (Antwort, links) | err"""
        if self.welcome: self.welcome.destroy(); self.welcome = None
        row = len(self.chat.winfo_children())
        right = kind == "q"
        holder = ctk.CTkFrame(self.chat, fg_color="transparent"); holder.grid(row=row, column=0, sticky="ew", pady=6)
        holder.grid_columnconfigure(0 if right else 1, weight=1)
        bg = {"q": ACCENT, "a": BUBBLE, "err": ("#FDECEC", "#3A1F22")}[kind]
        fg = {"q": "white", "a": INK, "err": ERR}[kind]
        b = ctk.CTkFrame(holder, fg_color=bg, corner_radius=16, border_width=0 if kind != "a" else 1, border_color=BORDER)
        b.grid(row=0, column=1 if right else 0, sticky="e" if right else "w", padx=8)
        lbl = ctk.CTkLabel(b, text=text, font=font(14), text_color=fg, justify="left", anchor="w", wraplength=self._wrap())
        lbl.pack(padx=16, pady=11, anchor="w"); self.msgs.append(lbl)
        self._scroll(); return b, lbl

    def sources(self, frame, hits, answer, tm=None):
        foot = ctk.CTkFrame(frame, fg_color="transparent"); foot.pack(fill="x", padx=16, pady=(0, 12))
        is_list = bool(tm and tm.get("list"))
        if hits:
            ctk.CTkLabel(foot, text="EINTRÄGE  (Klick öffnet in Outlook)" if is_list else "QUELLEN",
                         font=font(10, "bold"), text_color=MUTED).pack(anchor="w", pady=(2, 2))
            past = [h for h in hits if h.get("state") == "vorbei"]
            if is_list and len(past) > 3:                          # vergangene Termine eingeklappt
                box = ctk.CTkFrame(foot, fg_color="transparent")
                tog = ctk.CTkButton(foot, text=f"▸ {len(past)} vergangene anzeigen", height=22, corner_radius=7,
                                    font=font(11), fg_color="transparent", hover_color=CARD, text_color=MUTED, anchor="w")
                def flip(b=box, t=tog, n=len(past)):
                    if b.winfo_manager(): b.pack_forget(); t.configure(text=f"▸ {n} vergangene anzeigen")
                    else: b.pack(anchor="w", after=t); t.configure(text=f"▾ {n} vergangene ausblenden")
                    self.root.update_idletasks(); cv = self.chat._parent_canvas; cv.configure(scrollregion=cv.bbox("all"))
                tog.configure(command=flip); tog.pack(anchor="w")
            else: box = None
            for i, h in enumerate(hits):
                parent = box if box is not None and h.get("state") == "vorbei" else foot
                if "label" in h:                                   # Listenmodus: Zeile mit Uhrzeit, ohne [n]
                    st = h.get("state", "")
                    txt = h["label"] + ("   (vorbei)" if st == "vorbei" else "   (läuft)" if st == "läuft" else "")
                    col = OFF if st == "vorbei" else INK
                    fs = 12
                else:
                    txt = f"[{i + 1}]  {h['ts'][:10]}  ·  {h['source'].replace('_', ' ')}  ·  {h['title'][:80]}"
                    col, fs = MUTED, 11
                lb = ctk.CTkLabel(parent, text=txt, font=font(fs), text_color=col, anchor="w", height=20, cursor="hand2")
                lb.pack(anchor="w")
                if h.get("path"):                                  # v28: Wissenssammlung -> Datei oeffnen
                    lb.bind("<Button-1>", lambda e, p=h["path"]: self._open_file(p))
                else: lb.bind("<Button-1>", lambda e, iid=h["item_id"]: self.open_original(iid))
                lb.bind("<Enter>", lambda e, l=lb: l.configure(text_color=ACCENT))
                lb.bind("<Leave>", lambda e, l=lb, c=col: l.configure(text_color=c))
        row = ctk.CTkFrame(foot, fg_color="transparent"); row.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(row, text="Kopieren", width=78, height=24, corner_radius=8, font=font(11), fg_color=CARD,
                      hover_color=BORDER, text_color=INK, command=lambda: self._copy(answer)).pack(side="left")
        if hits and not is_list:
            ctk.CTkButton(row, text="Kontext", width=70, height=24, corner_radius=8, font=font(11), fg_color=CARD,
                          hover_color=BORDER, text_color=INK,
                          command=lambda: self.show_context(hits)).pack(side="left", padx=(6, 0))
        if is_list and tm:
            ctk.CTkLabel(row, text=f"⏱ {secs(tm['total'])}  ·  ohne Sprachmodell", font=font(11),
                         text_color=MUTED, anchor="w").pack(side="left", padx=(12, 0))
        elif tm and tm.get("total"):
            parts = [f"Suche {secs(tm['search'])}"]
            if tm.get("load", 0) >= 1: parts.append(f"Modell laden {secs(tm['load'])}")
            if "prefill" in tm: parts.append(f"Quellen lesen {secs(tm['prefill'])}")
            if tm.get("gen"): parts.append(f"Schreiben {secs(tm['gen'])} ({tm['out'] / tm['gen']:.1f} Tokens/s)")
            if tm.get("gen"): self.last_speed = (tm["out"] / tm["gen"], tm["total"]); self._rb_model()      # v68
            ctk.CTkLabel(row, text=f"⏱ {secs(tm['total'])}   ·   " + "  ·  ".join(parts), font=font(11),
                         text_color=MUTED, anchor="w").pack(side="left", padx=(12, 0))
        hilfe.auto(row, "haupt")

    def open_log(self):
        try: os.startfile(log.LOG_PATH)
        except Exception as e: self.status.configure(text=f"Log nicht gefunden: {log.LOG_PATH} ({e})")

    def show_context(self, hits):
        """Zeigt die Textstuecke, die an das Sprachmodell gingen (Fehlersuche: stand die Antwort ueberhaupt drin?). v46: Slide-In."""
        w = self.panel("Kontext fürs Sprachmodell", "kontext", 680); w.grid_rowconfigure(0, weight=1)
        tb = ctk.CTkTextbox(w, font=ctk.CTkFont(family="Consolas", size=12), wrap="word", fg_color=BUBBLE, text_color=INK)
        tb.grid(row=0, column=0, sticky="nsew", padx=12, pady=(0, 12))
        for i, h in enumerate(hits):
            tb.insert("end", f"[{i + 1}]  {h['ts'][:16]}  ·  {h['title']}\n", )
            tb.insert("end", f"{h.get('text', '')}\n\n" + "-" * 80 + "\n\n")
        tb.insert("end", f"{sum(len(h.get('text', '')) for h in hits):,} Zeichen gesamt".replace(",", "'"))
        tb.configure(state="disabled")

    def _open_file(self, p):
        try: os.startfile(p)
        except Exception as e: self.status.configure(text=f"Datei nicht geöffnet: {e}")

    def open_original(self, item_id):
        self.status.configure(text="Öffne Original ...")
        open_item(item_id, lambda msg: self.w.events.put(("progress", (msg, None, None))))

    def _copy(self, t): self.root.clipboard_clear(); self.root.clipboard_append(t)
    def _scroll(self):
        self.root.update_idletasks()
        try:
            cv = self.chat._parent_canvas
            cv.configure(scrollregion=cv.bbox("all")); cv.yview_moveto(1.0)
        except Exception: pass

    # ------------------------------------------------------------------ Aktionen
    def sync(self, c):
        if c.id == "folder_docs" and not self.s.get("docs_folder"): self.pick_folder()
        self.w.submit("sync", c.id)
    def remove_folder(self):
        """v37: Dokumentordner abwaehlen und seine Dokumente aus AURA entfernen (die Dateien selbst bleiben)."""
        n = (self.stats.get("folder_docs") or {}).get("items", 0)
        cur = self.s.get("docs_folder") or "(keiner gewählt)"
        if not messagebox.askyesno(f"{APP_NAME} – Dokumentordner", f"Ordner: {cur}\n\nAbwählen und {fmt(n)} eingelesene Dokumente aus AURA "
                                   "entfernen?\n\nDie Dateien im Ordner bleiben unberührt.", parent=self.root): return
        self.s["docs_folder"] = ""; save_settings(self.s)
        self.w.submit("delete_source", "folder_docs")

    # ---- v78: Confluence-Links (Seite = inkl. Unterseiten, Bereich = alles)
    def open_confluence(self):
        from .connectors.confluence import parse_link
        body = self.view("confluence", "Confluence-Links")
        w = ctk.CTkFrame(body, fg_color="transparent"); w.grid(row=0, column=0, sticky="nw", padx=24, pady=12)
        w.grid_columnconfigure(0, weight=1, minsize=520)
        ctk.CTkLabel(w, text="Link einer Seite (holt alle Unterseiten) oder eines Bereichs einfügen. Abgleich einmal täglich "
                             "im Auto-Abgleich oder per «Sync». Ohne Anmeldung – nur öffentlich sichtbare Seiten.",
                     font=font(11), text_color=MUTED, anchor="w", justify="left", wraplength=500).grid(row=0, column=0, sticky="w", pady=(0, 8))
        links = list(self.s.get("confluence_links") or [])
        for i, l in enumerate(links):
            r = ctk.CTkFrame(w, fg_color=CARD, corner_radius=8); r.grid(row=1 + i, column=0, sticky="ew", pady=2)
            try: d = parse_link(l)[2]
            except ValueError as e: d = f"⚠ {e}"
            ctk.CTkLabel(r, text=f"{d}\n{l[:80]}", font=font(10), text_color=INK, anchor="w", justify="left").pack(side="left", padx=10, pady=4)
            ctk.CTkButton(r, text="✕", width=26, height=24, corner_radius=7, fg_color=BORDER, hover_color=MUTED, text_color=INK,
                          command=lambda l=l: self._conf_remove(l)).pack(side="right", padx=8)
        e = ctk.CTkEntry(w, placeholder_text="https://confluence.bit.admin.ch/spaces/…", height=28)
        e.grid(row=2 + len(links), column=0, sticky="ew", pady=(10, 0))
        def add():
            l = e.get().strip()
            try: parse_link(l)
            except ValueError as x: messagebox.showerror(APP_NAME, str(x), parent=self.root); return
            if l not in links: self.s["confluence_links"] = links + [l]; save_settings(self.s)
            self.open_confluence()
        ctk.CTkButton(w, text="+ Link einfügen", height=28, corner_radius=8, font=font(11, "bold"), fg_color=ACCENT,
                      hover_color=ACCENT_HI, command=add).grid(row=3 + len(links), column=0, sticky="w", pady=6)

    def _conf_remove(self, l):
        if not messagebox.askyesno(APP_NAME, f"Link entfernen?\n{l}\n\nSeiten, die nur über diesen Link kamen, werden beim "
                                   "nächsten «Sync» aus AURA entfernt.", parent=self.root): return
        self.s["confluence_links"] = [x for x in (self.s.get("confluence_links") or []) if x != l]; save_settings(self.s)
        if not self.s["confluence_links"]: self.w.submit("delete_source", "confluence")
        self.open_confluence()

    def pick_folder(self):
        d = filedialog.askdirectory(title="Dokumentordner waehlen", parent=self.root)
        if d: self.s["docs_folder"] = d; save_settings(self.s)
    def pick_model(self, label):
        self.s["llm"] = next(m[0] for m in self.models if m[1] == label); save_settings(self.s)
        if self.llm_ready: self.w.submit("unload_llm")          # altes Modell aus dem GPU-Speicher
        self._llm_view("none" if self.s["llm"] == "extractive" else "off",
                       "kein Laden noetig" if self.s["llm"] == "extractive" else "nicht geladen")

    def toggle_q8(self):
        """v70: 8-Bit-Gewichte ein/aus. Gilt beim nächsten «Laden»; ein geladenes Modell wird entladen."""
        self.s = load_settings(); self.s["llm_int8"] = bool(self.q8_var.get()); save_settings(self.s)
        if self.llm_ready:
            self.w.submit("unload_llm"); self.status.configure(text="8 Bit geändert – Sprachmodell entladen. Bitte neu «Laden».")
        else: self.status.configure(text="8 Bit geändert – gilt beim nächsten «Laden».")
        self._rb_model()

    def toggle_llm(self):
        if self.llm_ready: self.w.submit("unload_llm"); return
        busy = self.b_embed.cget("state") == "disabled"
        self.w.submit("load_llm", self.s["llm"])
        if busy: self.w.cancel.set()                            # laufende Vektorberechnung pausieren
        self._llm_view("loading", "wird geladen ..." + (" (Vektoren werden pausiert)" if busy else ""))

    def _llm_view(self, state, text):
        col = {"ready": OK, "loading": "#F59E0B", "off": OFF, "none": OFF}.get(state, OFF)
        self.llm_dot.configure(text_color=col); self.llm_info.configure(text=text)
        self.llm_ready = state == "ready"
        self._rb_model(col, text)                                        # v68
        if state == "none": self.b_llm.grid_remove()
        else:
            self.b_llm.grid(); self.b_llm.configure(text="Entladen" if state == "ready" else "Laden",
                                                     state="disabled" if state == "loading" else "normal")
    # ------------------------------------------------------------------ v97: Anhang im Chat
    def add_anhang(self):
        ps = filedialog.askopenfilenames(parent=self.root, title="Datei für diesen Chat anhängen",
                                         filetypes=[("Dokumente", "*.pdf *.docx *.txt *.md"), ("Alle Dateien", "*.*")])
        if ps: self.w.submit("anhang", list(ps))

    def _show_anhang(self, lst):
        for c in self.anh_box.winfo_children(): c.destroy()
        if not lst: self.anh_box.pack_forget(); return
        self.anh_box.pack(side="left", padx=(8, 0))
        names = ", ".join(a["name"] for a in lst)
        ctk.CTkLabel(self.anh_box, text=f"📎 {names[:60]}{'…' if len(names) > 60 else ''}  ·  nur in diesem Chat",
                     font=font(11), text_color=ACCENT).pack(side="left")
        ctk.CTkButton(self.anh_box, text="✕", width=24, height=22, corner_radius=11, font=font(11), fg_color="transparent",
                      hover_color=BORDER, text_color=MUTED, command=lambda: self.w.submit("anhang_leeren")).pack(side="left", padx=(4, 0))

    def toggle_follow(self, on=None):
        """v67: Folgefrage-Knopf. Gilt nur fuer die naechste Frage."""
        self.follow = (not self.follow) if on is None else on
        self.b_follow.configure(fg_color=ACCENT if self.follow else "transparent",
                                text_color="white" if self.follow else MUTED,
                                border_color=ACCENT if self.follow else BORDER)

    def ask(self):
        q = self.entry.get("1.0", "end").strip()
        if not q or self.b_ask.cget("state") == "disabled": return
        if re.search(r"\bXY\b", q):                                    # v46: Platzhalter aus der Startfrage
            self.status.configure(text="Bitte «XY» durch ein Thema ersetzen."); return
        self.entry.delete("1.0", "end")
        self.w.submit("ask", q, self.s["llm"] if any(m[0] == self.s["llm"] for m in self.models) else "extractive",
                      self.follow)                                       # v67: True = Bezug, False = neues Thema
        self.toggle_follow(False)

    # ------------------------------------------------------------------ v23: Auto-Abgleich
    def _auto_text(self):
        last = self.s.get("autosync_last")
        return f"Letzter Abgleich: {last}" if last else f"alle {self.s.get('autosync_min', 15)} min, noch kein Lauf"

    def open_workflows(self):
        from .workflow_gui import WorkflowWindow
        if getattr(self, "wfwin", None) and self.wfwin.alive(): self.show_view("workflows"); return
        self.wfwin = WorkflowWindow(self)

    def _wf(self, meth, *a):
        w = getattr(self, "wfwin", None)
        if w is not None and w.alive(): getattr(w, meth)(*a)

    def open_wissen(self):
        from .wissen_gui import WissenWindow
        if getattr(self, "wwin", None) and self.wwin.alive(): self.show_view("wissen"); return
        self.wwin = WissenWindow(self)

    def toggle_wissen(self):
        self.s = load_settings(); self.s["wissen_chat"] = bool(self.wissen_var.get()); save_settings(self.s)
        self.status.configure(text="Wissenssammlungen im Chat: " + ("ein" if self.s["wissen_chat"] else "aus"))
        if self.s["wissen_chat"]: self.w.submit("wissen_sync")             # Ordner abgleichen und einbetten

    def toggle_auto(self):
        self.s["autosync"] = bool(self.auto_var.get()); save_settings(self.s)
        if self.s["autosync"]: self.next_auto = time.time() + 5

    def _zp_done(self, res):
        """v53: Ergebnis eines Zeitplan-Laufs als Meldung im Chat."""
        laeuft = getattr(self, "zp_laeuft", set())
        if res.get("path") not in laeuft: return
        laeuft.discard(res.get("path"))
        ok = res.get("status") == "ok"
        txt = f"⏰ {res.get('workflow')} (Zeitplan) – {'fertig' if ok else res.get('status')}" + (f": {res.get('error')}" if res.get("error") else "")
        txt += "\nDas Ergebnis steht links unter «Workflows › Ergebnisse»."
        try: self.bubble(txt, "a"); self._scroll()
        except Exception: log.get().exception("Zeitplan-Meldung")

    # ------------------------------------------------------------------ v54: Ergebnisse
    def _erg_badge(self):
        try:
            from .ergebnisse import anzahl_neu
            from .workflow.app import WF_DIR
            n = anzahl_neu(WF_DIR)
            self.b_erg.configure(text=f"Ergebnisse  ·  {n} neu" if n else "Ergebnisse", fg_color=ACCENT if n else "transparent",
                                 text_color="white" if n else INK)
            h = getattr(self, "grp", {}).get("Workflows")                # v109: Hinweis auch bei zugeklappter Gruppe
            if h: h[0].configure(text=f"Workflows  ·  {n} neu" if n else "Workflows")
        except Exception: log.get().exception("Ergebnisse zählen")

    def open_ergebnisse(self):
        from pathlib import Path
        from .ergebnisse import laeufe, als_gesehen
        from .workflow.app import WF_DIR
        from .zeitplan import mit_zeitplan, naechster, beschreibung
        body = self.view("ergebnisse", "Ergebnisse"); body.grid_columnconfigure(0, weight=1); body.grid_rowconfigure(0, weight=1)
        sf = ctk.CTkScrollableFrame(body, fg_color="transparent"); sf.grid(row=0, column=0, sticky="nsew", padx=20, pady=8)
        sf.grid_columnconfigure(0, weight=1); r = 0
        plan = [(naechster(w["zeitplan"]), w) for w in mit_zeitplan(WF_DIR)]
        plan = sorted([x for x in plan if x[0]], key=lambda x: x[0])
        if plan:
            ctk.CTkLabel(sf, text="ALS NÄCHSTES", font=font(10, "bold"), text_color=MUTED).grid(row=r, column=0, sticky="w", pady=(4, 2)); r += 1
            for d, w in plan:
                ctk.CTkLabel(sf, text=f"⏰  {d.strftime('%a %d.%m. %H:%M').replace('Mon', 'Mo').replace('Tue', 'Di').replace('Wed', 'Mi').replace('Thu', 'Do').replace('Fri', 'Fr').replace('Sat', 'Sa').replace('Sun', 'So')}"
                                      f"   {w['name']}   ({beschreibung(w['zeitplan'])}; nur wenn AURA offen ist)",
                             font=font(12), text_color=INK, anchor="w").grid(row=r, column=0, sticky="w"); r += 1
        ctk.CTkLabel(sf, text="LETZTE LÄUFE", font=font(10, "bold"), text_color=MUTED).grid(row=r, column=0, sticky="w", pady=(14, 2)); r += 1
        ls = laeufe(WF_DIR, 30)
        if not ls:
            ctk.CTkLabel(sf, text="Noch keine Läufe. Workflows starten unter «Workflows öffnen».", font=font(12),
                         text_color=MUTED).grid(row=r, column=0, sticky="w")
        for x in ls:
            self._erg_card(sf, x).grid(row=r, column=0, sticky="ew", pady=4); r += 1
        als_gesehen(); self._erg_badge()

    def _erg_card(self, parent, x):
        from pathlib import Path
        c = ctk.CTkFrame(parent, fg_color=BUBBLE, corner_radius=12, border_width=1, border_color=ACCENT if x["neu"] else BORDER)
        c.grid_columnconfigure(0, weight=1)
        ok = x["status"] == "ok"
        hd = ctk.CTkFrame(c, fg_color="transparent"); hd.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 2))
        if x["neu"]: ctk.CTkLabel(hd, text="NEU", font=font(9, "bold"), fg_color=ACCENT, text_color="white", corner_radius=6,
                                  width=34, height=18).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(hd, text=x["workflow"], font=font(14, "bold"), text_color=INK).pack(side="left")
        ctk.CTkLabel(hd, text=f"   {x['zeit']}  ·  {'✓ fertig' if ok else '✕ ' + str(x['status'])}  ·  {x['seconds']:.0f} s",
                     font=font(11), text_color=OK if ok else ERR).pack(side="left")
        r = 1
        if x.get("error"):
            ctk.CTkLabel(c, text=str(x["error"])[:400], font=font(11), text_color=ERR, wraplength=self._wrap(), justify="left",
                         anchor="w").grid(row=r, column=0, sticky="w", padx=14); r += 1
        for m in x["meldungen"]:
            t = (m.get("text") or "").replace("**", "").strip()                # v59: Markdown-Sterne nicht anzeigen
            if not t: continue
            tb = ctk.CTkTextbox(c, height=min(300, 30 + 20 * min(14, t.count("\n") + 1 + len(t) // 110)), font=font(12), wrap="word",
                                fg_color=CARD, text_color=INK, border_width=0)
            tb.insert("1.0", t); tb.configure(state="disabled"); tb.grid(row=r, column=0, sticky="ew", padx=14, pady=(4, 0)); r += 1
        for m in x["meldungen"]:                                         # v59: Tabellen
            for name, rows in (m.get("tabellen") or {}).items():
                if not rows: continue
                ctk.CTkLabel(c, text=f"{name}  ({len(rows)})", font=font(12, "bold"), text_color=INK, anchor="w").grid(
                    row=r, column=0, sticky="w", padx=14, pady=(8, 2)); r += 1
                fr = tk.Frame(c); fr.grid(row=r, column=0, sticky="ew", padx=14); fr.grid_columnconfigure(0, weight=1); r += 1
                cols = list(rows[0])
                st = ttk.Style(); st.configure("Aura.Treeview", font=(F, 9), rowheight=20)
                st.configure("Aura.Treeview.Heading", font=(F, 9, "bold"))
                tv = ttk.Treeview(fr, columns=cols, show="headings", height=min(len(rows), 12), style="Aura.Treeview")
                for col in cols:
                    w = min(260 if col in ("Termin", "Betreff") else 130, max(len(col), *(len(str(rw.get(col, ""))) for rw in rows)) * 7 + 14)
                    tv.heading(col, text=col, anchor="w"); tv.column(col, width=w, minwidth=40, anchor="w", stretch=False)
                tv.tag_configure("warn", foreground="#B45309"); tv.tag_configure("alt", background="#F3F4F6")
                for i, rw in enumerate(rows):
                    tags = ("warn",) if rw.get("⚠") else (("alt",) if i % 2 else ())
                    tv.insert("", "end", values=[rw.get(col, "") for col in cols], tags=tags)
                tv.grid(row=0, column=0, sticky="ew")
                hs = ttk.Scrollbar(fr, orient="horizontal", command=tv.xview); tv.configure(xscrollcommand=hs.set)
                hs.grid(row=1, column=0, sticky="ew")
                if len(rows) > 12:
                    sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=sb.set); sb.grid(row=0, column=1, sticky="ns")
        if ok and not x["meldungen"] and not x["files"]:                  # v57
            ctk.CTkLabel(c, text="Der Lauf war erfolgreich, aber der Workflow hat keinen Ausgabe-Schritt. Im Reiter «Schritte» "
                                 "«Anzeige in AURA» (oder «Datei speichern») hinzufügen – oder den Workflow neu beschreiben.",
                         font=font(11), text_color=MUTED, wraplength=self._wrap(), justify="left", anchor="w").grid(
                row=r, column=0, sticky="w", padx=14, pady=(4, 0)); r += 1
        if x["pruefungen"]:
            ctk.CTkLabel(c, text=f"⚠ {len(x['pruefungen'])} Prüfhinweis(e) – siehe Pruefbericht.txt", font=font(11),
                         text_color=("#92400E", "#FCD34D"), anchor="w").grid(row=r, column=0, sticky="w", padx=14, pady=(4, 0)); r += 1
        bb = ctk.CTkFrame(c, fg_color="transparent"); bb.grid(row=r, column=0, sticky="w", padx=12, pady=(6, 10))
        def btn(t, cmd, main=False):
            ctk.CTkButton(bb, text=t, height=26, width=0, corner_radius=8, font=font(11, "bold" if main else "normal"),
                          fg_color=ACCENT if main else CARD, hover_color=ACCENT_HI if main else BORDER,
                          text_color="white" if main else INK, command=cmd).pack(side="left", padx=2)
        for f in x["files"]: btn(f"Öffnen: {Path(f).name[:40]}", lambda f=f: self._open_file(f), not Path(f).name.startswith("Pruefbericht"))
        texte = "\n\n".join(m.get("text", "") for m in x["meldungen"]).strip()
        if texte: btn("Kopieren", lambda t=texte: (self._copy(t), self.status.configure(text="Ergebnis kopiert")))
        if texte or x["files"]: btn("Speichern unter …", lambda x=x, t=texte: self._erg_save(x, t))
        btn("Laufordner", lambda: self._open_file(x["ordner"]))
        btn("Workflow", lambda p=x["path"]: self._erg_workflow(p))
        btn("Löschen", lambda x=x: self._erg_delete(x))                  # v60
        return c

    def _erg_delete(self, x):
        """v60: Lauf aus «Ergebnisse» entfernen – der Laufordner wandert nach workflows\\_geloescht\\_laeufe (zurückholbar)."""
        import shutil
        from pathlib import Path
        from .workflow.app import WF_DIR
        src = Path(x["ordner"])
        if not src.is_dir(): messagebox.showinfo(APP_NAME, "Laufordner nicht gefunden.", parent=self.root); return
        if not messagebox.askyesno(APP_NAME, f"Lauf «{x['workflow']}» vom {x['zeit']} löschen?\n\nDer Laufordner (mit dem erzeugten "
                                   "Dokument) wird nach workflows\\_geloescht\\_laeufe verschoben und lässt sich von dort zurückholen.",
                                   parent=self.root): return
        ziel = WF_DIR / "_geloescht" / "_laeufe"; ziel.mkdir(parents=True, exist_ok=True)
        dst = ziel / f"{src.parent.parent.name}__{src.name}"
        n = 2
        while dst.exists(): dst = ziel / f"{src.parent.parent.name}__{src.name}_{n}"; n += 1
        try: shutil.move(str(src), str(dst))
        except Exception as e: messagebox.showerror(APP_NAME, f"Nicht gelöscht: {e}", parent=self.root); return
        self.status.configure(text="Lauf gelöscht (Papierkorb: workflows\\_geloescht\\_laeufe)")
        self.open_ergebnisse(); self._erg_badge(); self._welcome_erg()

    def _erg_save(self, x, text):
        """«Download»: Ergebnisdatei (oder den angezeigten Text) an einen frei gewählten Ort kopieren."""
        import shutil
        from pathlib import Path
        files = [f for f in x["files"] if not Path(f).name.startswith("Pruefbericht")]
        src = Path(files[0]) if files else None
        name = src.name if src else f"{x['workflow']} {x['stamp'][:8]}.md"
        ziel = filedialog.asksaveasfilename(parent=self.root, initialfile=name, defaultextension=Path(name).suffix or ".md")
        if not ziel: return
        try:
            if src: shutil.copy2(src, ziel)
            else: Path(ziel).write_text(text, encoding="utf-8")
            self.status.configure(text=f"Gespeichert: {ziel}")
        except Exception as e: messagebox.showerror(APP_NAME, f"Nicht gespeichert: {e}", parent=self.root)

    def _erg_workflow(self, path):
        self.open_workflows()
        try: self.wfwin.show(path)
        except Exception: pass

    def _zeitplan_tick(self):
        """v53: fällige Workflows mit Zeitplan starten (nur wenn nichts anderes läuft)."""
        from .zeitplan import faellig, mit_zeitplan
        from .workflow.app import WF_DIR
        if self.busy or not self.w.jobs.empty(): return
        for path in faellig(mit_zeitplan(WF_DIR)):
            if not hasattr(self, "zp_laeuft"): self.zp_laeuft = set()
            self.zp_laeuft.add(path); log.get().info(f"Zeitplan: starte {path}")
            self.w.submit("workflow", path, {}, None)

    def autotick(self):
        try: self._zeitplan_tick()
        except Exception: log.get().exception("Zeitplan")
        try:
            if self.s.get("autosync", True) and time.time() >= self.next_auto:
                if not self.busy and self.w.jobs.empty() and not self.cur:
                    self.w.submit("autosync")
                    self.next_auto = time.time() + 60 * max(1, int(self.s.get("autosync_min", 15)))
                else: self.next_auto = time.time() + 60             # beschaeftigt -> in 1 min nochmals
        except Exception: log.get().exception("autotick")
        self.root.after(30000, self.autotick)

    def _confirm_delete(self, n, chunks, why):
        if self.confirm_open: return
        if why != "nach Ordner-Abwahl" and time.time() < self.decline_until: return
        self.confirm_open = True
        try:
            yes = messagebox.askyesno(f"{APP_NAME} – Mails entfernen",
                                      f"{fmt(n)} Mails ({fmt(chunks)} Textstücke) liegen in keinem gewählten Ordner mehr "
                                      f"({why}).\n\nAus AURA löschen? Die Mails in Outlook bleiben unberührt.\n"
                                      "Wieder anwählen = neu einlesen und neu einbetten.", parent=self.root)
        finally: self.confirm_open = False
        if yes: self.w.submit("delete_pending")
        else:
            self.decline_until = time.time() + 24 * 3600
            self.status.configure(text="Nicht gelöscht. Nächste Rückfrage frühestens in 24 h.")

    # ------------------------------------------------------------------ v23: Outlook-Ordnerauswahl (v46: Slide-In)
    def open_folders(self, kind="outlook"):
        if self.busy or not self.w.jobs.empty():
            self.status.configure(text="Bitte warten, bis der laufende Auftrag fertig ist (oder Pause)."); return
        self.w.submit("onenote_tree" if kind == "onenote" else "folders")

    def _show_folders(self, fl, kind="outlook"):
        self.flist = [f for f in fl if "eid" in f]; self.fkind = kind
        body = self.view("ordner", "OneNote-Abschnitte" if kind == "onenote" else "Outlook-Ordner")   # v47/v87
        w = ctk.CTkFrame(body, fg_color="transparent", width=600); w.grid(row=0, column=0, sticky="nsw", padx=24, pady=12)
        body.grid_rowconfigure(0, weight=1); w.grid_propagate(False); w.grid_columnconfigure(0, weight=1); w.grid_rowconfigure(1, weight=1)
        errs = sum("error" in f for f in fl)
        ctk.CTkLabel(w, text=("Nur angehakte Abschnitte werden synchronisiert. Neue Abschnitte übernehmen die Wahl des "
                              "Notizbuchs bzw. der Gruppe. Abgewählte Abschnitte werden aus AURA entfernt (OneNote bleibt unberührt). "
                              "Achtung: geteilte Notizbücher enthalten auch Inhalte anderer Personen.") if kind == "onenote" else
                             ("Nur angehakte Ordner werden synchronisiert. Neue Unterordner übernehmen die Wahl des "
                              "Elternordners. Abgewählte Ordner werden nach Rückfrage aus AURA gelöscht.")
                             + (f"\n⚠ {errs} Ordner nicht lesbar – Löschen ist bis dahin gesperrt." if errs else ""),
                     font=font(11), text_color=MUTED, anchor="w", justify="left", wraplength=480).grid(
            row=0, column=0, sticky="w", padx=20, pady=(0, 8))
        box = ctk.CTkScrollableFrame(w, fg_color=CARD, corner_radius=10)
        box.grid(row=1, column=0, sticky="nsew", padx=16); box.grid_columnconfigure(0, weight=1)
        self.fvars = {}
        for i, f in enumerate(self.flist):
            v = tk.BooleanVar(value=f.get("on", True)); self.fvars[f["eid"]] = v
            cnt = f" ({fmt(f['count'])})" if f.get("count", -1) >= 0 else ""
            nm = f["name"] or "(Postfach)"
            if kind == "onenote": nm = {"notebook": "📓 ", "group": "📁 "}.get(f.get("kind"), "") + nm + (" 🔒" if f.get("locked") else "")
            ctk.CTkCheckBox(box, text=f"{nm}{cnt}", variable=v, font=font(12), text_color=INK,
                            checkbox_width=18, checkbox_height=18, fg_color=ACCENT, hover_color=ACCENT_HI,
                            command=lambda e=f["eid"]: self._cascade(e)).grid(
                row=i, column=0, sticky="w", padx=(10 + 18 * f["depth"], 10), pady=2)
        self.fsum = ctk.CTkLabel(w, text="", font=font(11), text_color=MUTED, anchor="w")
        self.fsum.grid(row=2, column=0, sticky="w", padx=20, pady=(8, 0)); self._fsum()
        bar = ctk.CTkFrame(w, fg_color="transparent"); bar.grid(row=3, column=0, sticky="e", padx=16, pady=(8, 16))
        ctk.CTkButton(bar, text="Abbrechen", width=90, height=30, corner_radius=8, font=font(12), fg_color=CARD,
                      hover_color=BORDER, text_color=INK, command=lambda: self.show_view("quellen")).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="Speichern & synchronisieren", height=30, corner_radius=8, font=font(12, "bold"),
                      fg_color=ACCENT, hover_color=ACCENT_HI, command=self._save_folders).pack(side="left")
        hilfe.auto(bar, "ordner")

    def _cascade(self, eid):
        # Haken setzen/entfernen gilt fuer alle Unterordner
        val = self.fvars[eid].get(); idx = next(i for i, f in enumerate(self.flist) if f["eid"] == eid)
        d0 = self.flist[idx]["depth"]
        for f in self.flist[idx + 1:]:
            if f["depth"] <= d0: break
            self.fvars[f["eid"]].set(val)
        self._fsum()

    def _fsum(self):
        if getattr(self, "fkind", "outlook") == "onenote":                 # v87: nur Abschnitte zaehlen
            al = [f for f in self.flist if f.get("kind") == "section"]
            on = [f for f in al if self.fvars[f["eid"]].get()]
            self.fsum.configure(text=f"{len(on)} von {len(al)} Abschnitten gewählt · {fmt(sum(f.get('count', 0) for f in on))} Seiten"); return
        on = [f for f in self.flist if self.fvars[f["eid"]].get()]
        n = sum(max(0, f.get("count", 0)) for f in on)
        self.fsum.configure(text=f"{len(on)} von {len(self.flist)} Ordnern gewählt · ~{fmt(n)} Einträge")

    def _save_folders(self):
        on = getattr(self, "fkind", "outlook") == "onenote"            # v87
        self.s["onenote_sections" if on else "mail_folders"] = {e: bool(v.get()) for e, v in self.fvars.items()}; save_settings(self.s)
        self.open_sources()                                          # zurueck zu den Quellen (Fortschritt sichtbar)
        self.views.pop("ordner").destroy()
        self.w.submit("sync", "onenote" if on else "outlook_mail", True)   # True: Abwahl = bewusstes Loeschen

    # ------------------------------------------------------------------ Ereignisse aus dem Worker
    def poll(self):
        """Nie abbrechen: ein Fehler bei einem Ereignis darf die Anzeige aller weiteren Antworten nicht stoppen."""
        try: self._poll()
        except Exception as e:
            log.get().exception("Anzeigefehler in poll")
            try: self.bubble(f"Anzeigefehler: {type(e).__name__}: {e}", "err"); self.cur = None
            except Exception: pass
            self.root.after(150, self.poll)

    def _poll(self):
        try:
            while True:
                kind, d = self.w.events.get_nowait()
                if kind == "progress":
                    self.prog.configure(text=d[0]); self.status.configure(text=d[0])
                    self._wf("on_progress", d[0])
                    if d[1] is not None and d[2]: self._pb_value(d[1] / d[2])     # v109
                elif kind == "busy":
                    self.busy = d[0]
                    auto = len(d) > 1 and d[1] == "autosync"             # v23: Fragen bleiben waehrend Auto-Abgleich moeglich
                    for b in self.buttons + self.src_btns:
                        if auto and b is self.b_ask: continue
                        try: b.configure(state="disabled" if d[0] else "normal")
                        except Exception: pass                           # v46: Slide-In evtl. schon geschlossen
                    if d[0]: self._pb_start()                            # v109: blau = läuft
                    else: self._pb_done()                                # grün = fertig (rot, falls Fehler)
                elif kind == "stats":
                    self.stats = d[0]; self._show_stats()
                elif kind == "answer_start":
                    if self.view_cur: self.show_chat()                   # v46: Antwort erscheint im Chat
                    qb, _ = self.bubble(d[0], "q")
                    if len(d) > 2 and d[2]:                              # v67: Folgefrage sichtbar machen
                        ctk.CTkLabel(qb, text=f"↳ Bezug: {d[2][:70]}{'…' if len(d[2]) > 70 else ''}", font=font(11),
                                     text_color="#DCE3FF", anchor="w").pack(padx=16, pady=(0, 9), anchor="w")
                    self.cur, lbl = self.bubble("…", "a"); self.cur_lbl = lbl; self.cur_text = ""
                    self.t_ask = time.perf_counter()
                elif kind == "token" and self.cur:
                    self.cur_text += d[0]
                elif kind == "sources" and self.cur:
                    vis = visible(self.cur_text) or "(Keine Antwort – Token-Grenze im Denkteil erreicht)"
                    self.cur_lbl.configure(text=vis)
                    self.sources(self.cur, d[0], vis, d[1] if len(d) > 1 else None)
                    self.cur = None; self._scroll()
                elif kind == "llm_state": self._llm_view(d[0], d[1])
                elif kind == "anhang": self._show_anhang(d[0])           # v97
                elif kind == "folders": self._show_folders(*d)
                elif kind == "confirm_delete": self._confirm_delete(*d)
                elif kind == "wf_step": self._wf("on_step", *d)
                elif kind == "wf_done":
                    self._wf("on_done", d[0]); self._zp_done(d[0]); self._erg_badge(); self._welcome_erg()
                    if self.view_cur == "ergebnisse": self.open_ergebnisse()
                elif kind == "wf_plan": self._wf("on_plan", d[0])
                elif kind == "wissen_status":
                    if getattr(self, "wwin", None): self.wwin.on_status(d[0])
                    w = getattr(self, "wfwin", None)
                    if w is not None and w.alive() and getattr(w, "wpanel", None): w.wpanel.on_status(d[0])
                elif kind == "autosync_done":
                    self.s["autosync_last"] = f"{d[0]} · +{d[1]} neu"; save_settings(self.s)
                    self.auto_lbl.configure(text=self._auto_text()); self._rb_stats()   # v68
                elif kind == "error" and getattr(self, "wfwin", None) and self.wfwin.alive() and self.wfwin.running:
                    self._pb_error(); self.prog.configure(text=f"Fehler: {d[0]}"[:200])
                    self.wfwin.on_done({"status": "fehler", "error": d[0]})
                    self.bubble(f"Fehler: {d[0]}", "err")
                elif kind == "error":
                    self._pb_error(); self.prog.configure(text=f"Fehler: {d[0]}"[:200])          # v109: rot
                    self.bubble(f"Fehler: {d[0]}\n(Details: Einstellungen › «Log öffnen»)", "err"); self.status.configure(text=f"Fehler: {d[0]}")
        except queue.Empty:
            pass
        now = time.perf_counter()
        vis = visible(self.cur_text) if self.cur else ""
        if self.cur and vis and now - getattr(self, "t_draw", 0) > 0.5:   # max. 2x pro Sekunde neu zeichnen
            self.cur_lbl.configure(text=vis); self._scroll(); self.t_draw = now
        if self.cur and not vis and "<think>" in self.cur_text:
            self.cur_lbl.configure(text=f"…  denkt  {time.perf_counter() - self.t_ask:.0f} s")
        elif self.cur and not vis:                       # Wartezeit live anzeigen, bis das erste Wort kommt
            self.cur_lbl.configure(text=f"…  {time.perf_counter() - self.t_ask:.0f} s")
        self.root.after(150, self.poll)

def main():
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    ctk.set_appearance_mode(load_settings().get("darstellung", "system"))   # v69: Hell/Dunkel/System aus den Einstellungen
    lg = log.get(); lg.info(f"===== AURA {VERSION} gestartet =====")
    try: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("armasuisse.AURA")   # v71: eigenes Taskleisten-Symbol
    except Exception: pass
    root = ctk.CTk()
    try: root.iconbitmap(str(Path(__file__).resolve().parent / "assets" / "aura.ico"))       # v71
    except Exception: pass
    root.report_callback_exception = lambda t, v, tb: lg.error("Fehler in der Oberflaeche", exc_info=(t, v, tb))
    App(root); root.mainloop(); lg.info("AURA beendet")
