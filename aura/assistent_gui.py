# aura/assistent_gui.py — Fenster «Workflow beschreiben». Version 20261011v64c (v64c: Feldplan beim Bauen)
# Links: Beschreibung in eigenen Worten; Bausteine von rechts per Klick oder Ziehen einfügen («[…]», farbig).
# «Verstehen»: AURA liest die Bausteine selbst, das Sprachmodell ergänzt Lücken (falls geladen/gewählt).
# Danach ein Formular «Ich habe verstanden», in dem alles korrigierbar ist; fehlende Angaben sind rot markiert.
# «Workflow erstellen» baut das Paket (workflow/assistent.py) – Korrekturen danach im Reiter «Schritte».
import json, re, tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
import customtkinter as ctk
from .workflow import assistent as A

BEISPIEL = ("Beispiele:\n• Ich möchte [werktags um 08:00] eine [Zusammenfassung] von [meine Termine] [heute], dazu zu jedem Termin "
            "die wichtigsten [meine Mails] der [letzte 7 Tage].\n• Prüfe die [hochgeladene Dateien] gemäss [Wissen]. Regeln:\n"
            "  - Jede Quelle im Text steht im Literaturverzeichnis\n  - Das Fazit beantwortet die Forschungsfrage")


class Assistent:
    def __init__(self, ww, neu=True):
        self.ww, self.G, self.app, self.neu = ww, ww.G, ww.app, neu
        G = self.G; self.plan = None; self.vorlage = None; self.drag = None
        d = self.win = ctk.CTkToplevel(ww.win); d.title("Workflow beschreiben"); d.transient(ww.win); d.geometry("1250x800")
        d.grid_columnconfigure(0, weight=3); d.grid_columnconfigure(1, weight=1); d.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(d, fg_color="transparent"); left.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=12)
        left.grid_columnconfigure(0, weight=1); left.grid_rowconfigure(6, weight=1)
        nf = ctk.CTkFrame(left, fg_color="transparent"); nf.grid(row=0, column=0, sticky="ew", pady=(0, 10))     # v56: Name zuoberst
        ctk.CTkLabel(nf, text="Name des Workflows", font=G.font(12, "bold")).pack(side="left")
        self.e_name = ctk.CTkEntry(nf, width=420, placeholder_text="z.B. Termine der Woche (leer = Vorschlag von AURA)")
        self.e_name.pack(side="left", padx=10)
        ctk.CTkLabel(left, text="Was soll der Workflow tun?", font=G.font(16, "bold"), anchor="w").grid(row=1, column=0, sticky="w")
        ctk.CTkLabel(left, text="In eigenen Worten. Bausteine von rechts anklicken oder ins Feld ziehen – die liest AURA sicher. "
                                "Regeln je Zeile mit «- ».", font=G.font(11), text_color=G.MUTED, anchor="w",
                     wraplength=780, justify="left").grid(row=2, column=0, sticky="w")
        self.tb = ctk.CTkTextbox(left, height=170, font=G.font(13), wrap="word", border_width=1, border_color=G.BORDER)
        self.tb.grid(row=3, column=0, sticky="ew", pady=(6, 0)); self.tx = self.tb._textbox
        self.tx.tag_configure("chip", background="#DCE3FF", foreground="#1E3A8A")
        self.tx.bind("<KeyRelease>", lambda e: self._tag())
        ctk.CTkLabel(left, text=BEISPIEL, font=G.font(10), text_color=G.MUTED, anchor="w", justify="left",
                     wraplength=780).grid(row=4, column=0, sticky="w", pady=(4, 0))
        bb = ctk.CTkFrame(left, fg_color="transparent"); bb.grid(row=5, column=0, sticky="ew", pady=(8, 4))
        self.b_go = ctk.CTkButton(bb, text="✨  Mit Sprachmodell verstehen und Workflow bauen", height=36, font=G.font(13, "bold"),
                                  fg_color=G.ACCENT, hover_color=G.ACCENT_HI, command=self.verstehen); self.b_go.pack(side="left")
        self.lbl = ctk.CTkLabel(bb, text="", font=G.font(11), text_color=G.MUTED, wraplength=380, justify="left"); self.lbl.pack(side="left", padx=12)
        self.form = ctk.CTkScrollableFrame(left, fg_color=G.BUBBLE, corner_radius=8); self.form.grid(row=6, column=0, sticky="nsew", pady=(6, 0))
        self.form.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.form, text="Fehlt etwas oder ist etwas unklar, fragt AURA hier nach. Sonst wird der Workflow direkt gebaut.",
                     font=G.font(11), text_color=G.MUTED).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=10)
        ft = ctk.CTkFrame(left, fg_color="transparent"); ft.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        ctk.CTkButton(ft, text="Lieber selbst zusammenstellen (ohne Beschreibung) →", height=28, fg_color="transparent",
                      hover_color=G.BORDER, text_color=G.MUTED, font=G.font(11), command=self._manuell).pack(side="left")
        self.b_mk = ctk.CTkButton(ft, text="Workflow bauen", width=170, height=32, font=G.font(12, "bold"), fg_color=G.ACCENT,
                                  hover_color=G.ACCENT_HI, command=self.erstellen, state="disabled"); self.b_mk.pack(side="right")
        # ---- Bausteine
        right = ctk.CTkScrollableFrame(d, fg_color=G.CARD, corner_radius=8); right.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=12)
        ctk.CTkLabel(right, text="BAUSTEINE", font=G.font(10, "bold"), text_color=G.MUTED).pack(anchor="w", padx=8, pady=(6, 0))
        grp = None
        for g, label, hilfe in A.BAUSTEINE + [("Wissen", f"Wissen: {n}", "") for n in self._wissen_docs()]:
            if g != grp:
                grp = g; ctk.CTkLabel(right, text=g, font=G.font(11, "bold"), anchor="w").pack(anchor="w", padx=8, pady=(10, 2))
            c = ctk.CTkLabel(right, text=label, font=G.font(11), fg_color="#DCE3FF", text_color="#1E3A8A", corner_radius=10,
                             height=24, cursor="hand2"); c.pack(anchor="w", padx=12, pady=2)
            for w in (c, getattr(c, "_label", c)):
                w.bind("<ButtonPress-1>", lambda e, t=label: self._press(e, t))
                w.bind("<B1-Motion>", self._motion); w.bind("<ButtonRelease-1>", self._release)
            if hilfe:
                try:
                    from . import hilfe as H
                    H.tip(c, hilfe)
                except Exception: pass
        self.tb.focus_set()

    def _wissen_docs(self):
        if self.neu: return []
        try:
            sj = Path(self.ww.cur).parent / "wissen" / "sammlung.json" if self.ww.cur else None
            if sj and sj.exists(): return [d.get("kurz") or d.get("titel") or d.get("datei", "") for d in json.loads(sj.read_text(encoding="utf-8")).get("dokumente", [])][:12]
        except Exception: pass
        return []

    # ------------------------------------------------------------------ Bausteine einfügen (Klick oder Ziehen)
    def _tag(self):
        self.tx.tag_remove("chip", "1.0", "end"); txt = self.tx.get("1.0", "end")
        for m in re.finditer(r"\[[^\]\n]+\]", txt):
            self.tx.tag_add("chip", f"1.0+{m.start()}c", f"1.0+{m.end()}c")

    def _ins(self, t, index="insert"):
        before = self.tx.get(f"{index} -1c", index)
        self.tx.insert(index, ("" if before in ("", " ", "\n") else " ") + f"[{t}] "); self._tag(); self.tx.focus_set()

    def _press(self, e, t): self.drag = {"t": t, "x": e.x_root, "y": e.y_root, "moved": False, "lbl": None}

    def _motion(self, e):
        d = self.drag
        if not d: return
        if not d["moved"] and abs(e.x_root - d["x"]) + abs(e.y_root - d["y"]) > 6:
            d["moved"] = True; w = d["lbl"] = tk.Toplevel(self.win); w.overrideredirect(True)
            tk.Label(w, text=f"[{d['t']}]", bg="#DCE3FF", fg="#1E3A8A", padx=6, pady=2).pack()
        if d["lbl"]: d["lbl"].geometry(f"+{e.x_root + 8}+{e.y_root + 8}")

    def _release(self, e):
        d, self.drag = self.drag, None
        if not d: return
        if d["lbl"]: d["lbl"].destroy()
        if not d["moved"]: self._ins(d["t"]); return
        w = self.win.winfo_containing(e.x_root, e.y_root)
        if w is self.tx:
            idx = self.tx.index(f"@{e.x_root - self.tx.winfo_rootx()},{e.y_root - self.tx.winfo_rooty()}")
            self._ins(d["t"], idx)

    # ------------------------------------------------------------------ Verstehen
    def verstehen(self):
        text = self.tx.get("1.0", "end").strip()
        if not text: messagebox.showinfo("Workflow beschreiben", "Bitte zuerst beschreiben, was der Workflow tun soll.", parent=self.win); return
        p = A.lesen(text); p["_text"] = text
        self.lbl.configure(text_color=self.G.MUTED)
        if self.vorlage: p["vorlage"] = self.vorlage
        llm = self.app.s.get("llm") not in (None, "", "extractive")          # v56: immer mit Modell, wenn eines gewählt ist
        if llm and not self.ww.running:
            self.plan = p; self.b_go.configure(state="disabled")
            self.lbl.configure(text="Sprachmodell liest die Beschreibung … (ca. 30–60 s, beim ersten Mal plus Laden des Modells)")
            self.ww.assistent = self; self.app.w.submit("wf_plan", A.llm_prompt(text), A.llm_felder())
        else:
            self.lbl.configure(text="Kein Sprachmodell gewählt (links oben) – nur die Bausteine gelesen." if not llm
                               else "Sprachmodell gerade beschäftigt – nur die Bausteine gelesen.")
            self.zeigen(p); self._auto_bauen()

    def on_plan(self, r):
        """Antwort aus dem Worker: {"ok", "werte" | "fehler"}."""
        self.b_go.configure(state="normal")
        if not self.win.winfo_exists(): return
        p = self.plan or A.lesen(self.tx.get("1.0", "end"))
        if r.get("ok"): p = A.llm_mischen(p, r["werte"]); self.lbl.configure(text="")
        else: self.lbl.configure(text=f"Sprachmodell nicht verfügbar ({r.get('fehler', '')[:80]}) – nur Bausteine gelesen")
        self.zeigen(p); self._auto_bauen()

    def _auto_bauen(self):
        """v56: Fehlt nichts, wird direkt gebaut; sonst bleibt das Formular mit den roten Rückfragen offen."""
        if A.rueckfragen(self.plan) or self.plan.get("fragen"):
            self.lbl.configure(text="Bitte die rot markierten Punkte ergänzen, dann «Workflow bauen».", text_color=self.G.ERR)
        else: self.erstellen()

    def _manuell(self):
        self.win.destroy(); self.ww.new_leer()

    # ------------------------------------------------------------------ Formular «Ich habe verstanden»
    def zeigen(self, p):
        G = self.G; self.plan = p; f = self.form
        for c in f.winfo_children(): c.destroy()
        fehlt = dict(A.rueckfragen(p)); self.w = w = {}; r = 0
        def zeile(titel, key=None):
            nonlocal r
            ctk.CTkLabel(f, text=titel, font=G.font(12, "bold"), anchor="w", width=120).grid(row=r, column=0, sticky="nw", padx=10, pady=(10, 0))
            fr = ctk.CTkFrame(f, fg_color="transparent"); fr.grid(row=r, column=1, sticky="ew", pady=(10, 0)); r += 1
            if key and key in fehlt:
                ctk.CTkLabel(f, text="⚠ " + fehlt[key], font=G.font(11), text_color=G.ERR, anchor="w", wraplength=600,
                             justify="left").grid(row=r, column=1, sticky="w"); r += 1
            return fr
        ctk.CTkLabel(f, text="Ich habe verstanden:", font=G.font(13, "bold")).grid(row=r, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 0)); r += 1
        for q in p.get("fragen") or []:
            ctk.CTkLabel(f, text="Rückfrage des Sprachmodells: " + q, font=G.font(11), text_color=G.ERR, wraplength=700,
                         justify="left").grid(row=r, column=0, columnspan=2, sticky="w", padx=10); r += 1
        fr = zeile("Wann", "zeit")
        w["aus"] = ctk.CTkOptionMenu(fr, values=["beim Start", "Zeitplan"], width=130); w["aus"].set("Zeitplan" if p["ausloeser"] == "zeitplan" else "beim Start")
        w["aus"].pack(side="left")
        zp = p.get("zeitplan") or {"tage": "werktags", "zeit": "08:00"}
        w["tage"] = ctk.CTkOptionMenu(fr, values=["werktags", "taeglich", "mo", "di", "mi", "do", "fr"], width=110)
        w["tage"].set(zp["tage"] if isinstance(zp["tage"], str) else zp["tage"][0]); w["tage"].pack(side="left", padx=6)
        ctk.CTkLabel(fr, text="um").pack(side="left")
        w["zeit"] = ctk.CTkEntry(fr, width=70); w["zeit"].insert(0, zp.get("zeit", "08:00")); w["zeit"].pack(side="left", padx=6)
        ctk.CTkLabel(fr, text="(nur bei Zeitplan; läuft, solange AURA offen ist)", font=G.font(10), text_color=G.MUTED).pack(side="left")
        fr = zeile("Woraus", "woraus" if "woraus" in fehlt else ("dateien" if "dateien" in fehlt else None))
        zr = list(A.ZEITRAUM_LABEL.values())
        def quelle(key, text, an, zeitraum=None):
            row = ctk.CTkFrame(fr, fg_color="transparent"); row.pack(anchor="w", pady=1)
            cb = ctk.CTkCheckBox(row, text=text, width=160); (cb.select() if an else cb.deselect()); cb.pack(side="left"); w[key] = cb
            if zeitraum is not None or key in ("kalender", "mails"):
                om = ctk.CTkOptionMenu(row, values=["– Zeitraum wählen –"] + zr, width=170)
                om.set(A.ZEITRAUM_LABEL.get(zeitraum, "– Zeitraum wählen –")); om.pack(side="left", padx=6); w[key + "_zr"] = om
                if an and not zeitraum: ctk.CTkLabel(row, text="⚠ Zeitraum?", text_color=G.ERR, font=G.font(11)).pack(side="left")
            return row
        quelle("dateien", "Dateien beim Start", p["dateien"])
        quelle("kalender", "meine Termine", p["kalender"] is not None, (p["kalender"] or {}).get("zeitraum"))
        row = quelle("mails", "meine Mails", p["mails"] is not None, (p["mails"] or {}).get("zeitraum"))
        w["je"] = ctk.CTkCheckBox(row, text="zu jedem Termin"); (w["je"].select() if p["je_termin"] else w["je"].deselect()); w["je"].pack(side="left", padx=6)
        quelle("wissen", "Wissen dieses Workflows", p["wissen"])
        fr = zeile("Ergebnis", "ergebnis" if "ergebnis" in fehlt else ("vorlage" if "vorlage" in fehlt else None))
        for k, lab in A.ERGEBNISSE.items():
            row = ctk.CTkFrame(fr, fg_color="transparent"); row.pack(anchor="w", pady=1)
            cb = ctk.CTkCheckBox(row, text=lab, width=200); (cb.select() if k in p["ergebnis"] else cb.deselect()); cb.pack(side="left"); w["e_" + k] = cb
            if k == "word":
                self.l_v = ctk.CTkLabel(row, text=Path(self.vorlage).name if self.vorlage else "keine Vorlage gewählt", font=G.font(11),
                                        text_color=G.MUTED); self.l_v.pack(side="left", padx=6)
                ctk.CTkButton(row, text="Vorlage wählen …", width=120, height=24, fg_color=G.BORDER, text_color=G.INK,
                              hover_color=G.MUTED, command=self._vorlage).pack(side="left")
        fr = zeile("Form")                                                   # v62
        w["form"] = ctk.CTkOptionMenu(fr, values=list(A.FORMEN.values()), width=160)
        w["form"].set(A.FORMEN.get(p.get("form"), "Stichpunkte")); w["form"].pack(side="left")
        ctk.CTkLabel(fr, text="  Stichpunkte = Aufzählung · Text = Fliesstext · Tabelle = Aufzählung plus Tabellen der Daten",
                     font=G.font(10), text_color=G.MUTED).pack(side="left")
        fr = zeile("Regeln", "regeln")
        w["regeln"] = ctk.CTkTextbox(fr, height=90, wrap="word", border_width=1, border_color=G.BORDER); w["regeln"].pack(fill="x")
        w["regeln"].insert("1.0", "\n".join("- " + x for x in p["regeln"]))
        ctk.CTkLabel(fr, text="Eine Regel pro Zeile. Beim Prüfbericht wird jede zu einer Frage ans Sprachmodell (im Reiter «Prüfliste» "
                              "später auch als feste Regel einstellbar).", font=G.font(10), text_color=G.MUTED, wraplength=640,
                     justify="left").pack(anchor="w")
        fr = zeile("Auftrag")
        w["anw"] = ctk.CTkTextbox(fr, height=70, wrap="word", border_width=1, border_color=G.BORDER); w["anw"].pack(fill="x")
        w["anw"].insert("1.0", p["anweisung"])
        ctk.CTkLabel(fr, text="So bekommt es das Sprachmodell beim Zusammenfassen bzw. Ausfüllen.", font=G.font(10),
                     text_color=G.MUTED).pack(anchor="w")
        if not self.e_name.get().strip():
            q = [x for x, an in (("Termine", p["kalender"] is not None), ("Mails", p["mails"] is not None), ("Dokumente", p["dateien"])) if an]
            e = A.ERGEBNISSE.get((p["ergebnis"] or ["zusammenfassung"])[0], "Workflow")
            self.e_name.insert(0, f"{e} {' und '.join(q)}".strip())
        self.b_mk.configure(state="normal")

    def _vorlage(self):
        f = filedialog.askopenfilename(parent=self.win, title="Word-Vorlage wählen", filetypes=[("Word", "*.docx")])
        if f: self.vorlage = f; self.l_v.configure(text=Path(f).name); self.w["e_word"].select()

    def _lesen_formular(self):
        w, p = self.w, dict(self.plan); g = lambda k: w[k].get()
        p["ausloeser"] = "zeitplan" if g("aus") == "Zeitplan" else "manuell"
        t = g("tage"); p["zeitplan"] = {"tage": t if t in ("werktags", "taeglich") else [t], "zeit": g("zeit").strip().replace(".", ":")}
        if p["ausloeser"] != "zeitplan": p["zeitplan"] = None
        inv = {v: k for k, v in A.ZEITRAUM_LABEL.items()}
        p["dateien"] = bool(g("dateien")); p["wissen"] = bool(g("wissen")); p["je_termin"] = bool(g("je"))
        p["kalender"] = {"zeitraum": inv.get(g("kalender_zr"))} if g("kalender") else None
        p["mails"] = {"zeitraum": inv.get(g("mails_zr"))} if g("mails") else None
        p["ergebnis"] = [k for k in A.ERGEBNISSE if g("e_" + k)]
        p["regeln"] = [re.sub(r"^\s*[-•*]\s*", "", l).strip() for l in w["regeln"].get("1.0", "end").splitlines() if l.strip()]
        p["anweisung"] = w["anw"].get("1.0", "end").strip(); p["vorlage"] = self.vorlage
        p["form"] = {v: k for k, v in A.FORMEN.items()}.get(w["form"].get(), "stichpunkte")
        return p

    # ------------------------------------------------------------------ Erstellen
    def erstellen(self):
        from .workflow import paket, load_workflow
        p = self._lesen_formular(); fehlt = A.rueckfragen(p)
        if fehlt:
            self.zeigen(p)
            messagebox.showwarning("Workflow beschreiben", "Es fehlt noch:\n- " + "\n- ".join(f for _, f in fehlt), parent=self.win); return
        name = self.e_name.get().strip() or "Neuer Workflow"
        try: d = paket.create(name)
        except Exception as e: messagebox.showerror("Workflow beschreiben", str(e), parent=self.win); return
        rel, felder, fp = None, None, None
        if "word" in p["ergebnis"] and self.vorlage:
            from .workflow.docx_fill import analyze
            from .workflow import feldplan as FP
            t = paket.add_template(d, self.vorlage); rel = f"vorlagen/{t.name}"; felder = analyze(t)
            try: fp = FP.mischen(FP.analysieren(t, rel), FP.laden(t)); FP.speichern(t, fp)     # v64c
            except Exception as e: fp = None; messagebox.showwarning("Workflow beschreiben", f"Feldplan nicht erstellt ({e}) – baue ohne.", parent=self.win)
        wf = A.bauen(p, name, rel, felder, fp)
        (d / "workflow.json").write_text(json.dumps(wf, ensure_ascii=False, indent=1), encoding="utf-8")
        try: load_workflow(d / "workflow.json")
        except Exception as e: messagebox.showwarning("Workflow beschreiben", f"Erstellt, aber noch fehlerhaft:\n{e}\n\nBitte im Reiter «Schritte» korrigieren.", parent=self.win)
        self.win.destroy(); self.ww.refresh_list(); self.ww.show(str(d / "workflow.json")); self.ww.tabs.set("Schritte")
        fpt = ("\n\nVorlage: Feldplan im Reiter «Vorlage» → «Feldplan …» prüfen (woher kommt jeder Wert?), "
               "dann dort «Workflow aus Feldplan bauen»." if fp else "")
        messagebox.showinfo("Workflow gebaut", "So hat AURA die Beschreibung verstanden:\n\n" + "\n".join(A.zusammenfassung(p))
                            + fpt + "\n\nKorrekturen im Reiter «Schritte». Testen im Reiter «Ausführen».", parent=self.ww.win)
        if p["wissen"]:
            messagebox.showinfo("Workflow beschreiben", "Erstellt. Lege jetzt im Reiter «Wissen» die Dokumente ab (Richtlinien, Vorlagen …) "
                                "und klicke «Speichern & abgleichen».", parent=self.ww.win)
