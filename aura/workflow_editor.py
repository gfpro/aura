# aura/workflow_editor.py — Reiter «Bauen»: Workflow ohne JSON zusammenstellen. Version 20261031v149
# (v149: Reiter heisst «Bauen»; auf der Leinwand stehen Eingaben und Zeitplan beim Start-Knoten statt im Kasten «Auslöser»;
#  Knöpfe Wissen, Vorlagen & Feldplan, Prüfliste über der Leinwand)
# (v146: Ansicht «Leinwand» (workflow_canvas.py) als Standard, Umschalter Leinwand | Liste; v132: Feldoption «Länge folgt der Ausführlichkeit»)
# Auslöser (Eingaben beim Start) + Liste der Schritte als Karten. Jeder Schritt wird in einem Formular bearbeitet, das aus
# workflow/schema.py entsteht. «Wert einfügen» zeigt die Ergebnisse früherer Schritte zum Anklicken. Unbekannte Parameter
# eines Schritts bleiben beim Speichern unverändert. Gespeichert wird nur, wenn die Engine den Workflow danach akzeptiert.
import json, re, tkinter as tk
from pathlib import Path
from tkinter import messagebox
import customtkinter as ctk
from .workflow import load_workflow, latest_state
from .workflow import schema as S

def _kurz(v, n=90):
    s = re.sub(r"\s+", " ", v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)).strip()
    return s if len(s) <= n else s[:n] + " …"

def _slug(t):
    t = t.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("é", "e"), ("è", "e"), ("à", "a")): t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:24] or "eingabe"

def _refs(obj, name):
    """Kommt «name.» (Schritt-id oder input.<id>) in obj vor?"""
    return bool(re.search(rf"(?<![\w.]){re.escape(name)}\.", json.dumps(obj, ensure_ascii=False)))


def _gespeicherte_ansicht():
    try:
        from .config import load_settings
        return "Liste" if load_settings().get("schritte_ansicht") == "Liste" else "Leinwand"
    except Exception: return "Leinwand"


class SchrittEditor:
    ansicht = _gespeicherte_ansicht()                     # v146: «Leinwand» (Standard) oder «Liste»

    def __init__(self, ww, tab):
        self.ww, self.G = ww, ww.G
        self.raw = json.loads(Path(ww.cur).read_text(encoding="utf-8"))
        self.state = self._last_state()
        G = self.G; t = tab; t.grid_columnconfigure(0, weight=1); t.grid_rowconfigure(3, weight=1)
        leinwand = SchrittEditor.ansicht == "Leinwand"
        if not leinwand: self._ausloeser(t)                    # v149: auf der Leinwand stehen Eingaben/Zeitplan beim Start-Knoten
        self._kopf(t, leinwand)

    def _ausloeser(self, t):
        G = self.G
        ctk.CTkLabel(t, text="AUSLÖSER", font=G.font(10, "bold"), text_color=G.MUTED, anchor="w").grid(row=0, column=0, sticky="w")
        af = ctk.CTkFrame(t, fg_color=G.BUBBLE, corner_radius=8); af.grid(row=1, column=0, sticky="ew", pady=(4, 10))
        af.grid_columnconfigure(0, weight=1)
        zp = self.raw.get("zeitplan")
        top = ctk.CTkFrame(af, fg_color="transparent"); top.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))
        from .zeitplan import beschreibung
        ctk.CTkLabel(top, text=(f"Zeitplan: {beschreibung(zp)} (läuft, solange AURA offen ist; Verpasstes von heute wird nachgeholt)"
                                if zp else "Manuell – beim Start fragt AURA nach:"), font=G.font(12), text_color=G.INK, anchor="w").pack(side="left")
        self._mini(top, "Zeitplan …", self._zeitplan).pack(side="right")
        r = 1
        for i, inp in enumerate(self.raw.get("inputs", [])):
            row = ctk.CTkFrame(af, fg_color="transparent"); row.grid(row=r, column=0, sticky="ew", padx=10); r += 1
            art = "Dateien" if inp.get("type") == "files" else "Text"
            ctk.CTkLabel(row, text=f"•  {inp.get('label', inp['id'])}   ({art}{', freiwillig' if inp.get('optional') else ''})   "
                                   f"→ Wert: input.{inp['id']}", font=G.font(11), text_color=G.INK, anchor="w").pack(side="left")
            self._mini(row, "✕", lambda i=i: self._inp_del(i)).pack(side="right")
            self._mini(row, "Bearbeiten", lambda i=i: self._inp_edit(i)).pack(side="right", padx=4)
        self._mini(af, "+ Eingabe", lambda: self._inp_edit(None)).grid(row=r, column=0, sticky="w", padx=10, pady=(4, 8))

    def _kopf(self, t, leinwand):
        G = self.G
        hd = ctk.CTkFrame(t, fg_color="transparent"); hd.grid(row=2, column=0, sticky="ew")
        if Path(self.ww.cur).name == "workflow.json":                  # v149: Hilfsmittel des Workflows als Fenster
            for name, txt in (("Wissen", "📚 Wissen"), ("Vorlage", "📄 Vorlagen & Feldplan"), ("Prüfliste", "✓ Prüfliste")):
                b = ctk.CTkButton(hd, text=txt, height=28, width=0, corner_radius=8, font=G.font(11), fg_color=G.BUBBLE,
                                  hover_color=G.BORDER, text_color=G.INK, command=lambda n=name: self.ww.ressource(n))
                b.pack(side="left", padx=(0, 6))
        else:
            ctk.CTkLabel(hd, text="SCHRITTE", font=G.font(10, "bold"), text_color=G.MUTED).pack(side="left")
        if not leinwand:                                               # v149: auf der Leinwand übernimmt das die Palette
            ctk.CTkButton(hd, text="+ Schritt hinzufügen", height=28, corner_radius=8, font=G.font(11, "bold"), fg_color=G.ACCENT,
                          hover_color=G.ACCENT_HI, command=lambda: self._add(len(self.raw.get("steps", [])))).pack(side="right")
        sw = ctk.CTkSegmentedButton(hd, values=["Leinwand", "Liste"], height=28, font=G.font(11), command=self._ansicht,
                                    selected_color=G.ACCENT, selected_hover_color=G.ACCENT_HI)          # v146
        sw.set(SchrittEditor.ansicht); sw.pack(side="right", padx=8)
        self.lst = None; self.canvas = None
        if leinwand:
            fr = ctk.CTkFrame(t, fg_color="transparent"); fr.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
            try:
                from .workflow_canvas import Leinwand
                self.canvas = Leinwand(self, fr)
            except Exception as e:
                ctk.CTkLabel(fr, text=f"Leinwand nicht verfügbar: {e}", text_color=G.ERR).grid(row=0, column=0, sticky="w")
        else:
            self.lst = ctk.CTkScrollableFrame(t, fg_color="transparent"); self.lst.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
            self.lst.grid_columnconfigure(0, weight=1)
            self._cards()

    def _ansicht(self, wert):
        """v146: Leinwand oder Liste; die Wahl bleibt gespeichert (Einstellung «schritte_ansicht»)."""
        if wert == SchrittEditor.ansicht: return
        SchrittEditor.ansicht = wert
        try:
            from .config import load_settings, save_settings
            st = load_settings(); st["schritte_ansicht"] = wert; save_settings(st)
        except Exception: pass
        self.ww.show(self.ww.cur); self.ww.tabs.set("Bauen")

    # ------------------------------------------------------------------ Hilfen
    def _mini(self, parent, text, cmd):
        G = self.G
        return ctk.CTkButton(parent, text=text, height=24, width=0, corner_radius=6, font=G.font(11), fg_color=G.BORDER,
                             hover_color=G.MUTED, text_color=G.INK, command=cmd)

    def _last_state(self):
        try:
            sf = latest_state(self.ww.app_runs_dir(), self.ww.wf) if self.ww.wf else None
            return json.loads(sf.read_text(encoding="utf-8")) if sf else None
        except Exception: return None

    def _save(self, tab="Bauen"):
        """workflow.json schreiben; lehnt die Engine den Workflow ab, wird die alte Fassung zurückgeschrieben."""
        if self.ww.running: messagebox.showinfo("Schritte", "Während eines Laufs nicht ändern.", parent=self.ww.win); return False
        p = Path(self.ww.cur); old = p.read_text(encoding="utf-8")
        try:
            p.write_text(json.dumps(self.raw, ensure_ascii=False, indent=1), encoding="utf-8"); load_workflow(p)
        except Exception as e:
            p.write_text(old, encoding="utf-8"); self.raw = json.loads(old)
            messagebox.showerror("Schritte", f"Nicht gespeichert – der Workflow wäre so fehlerhaft:\n\n{e}", parent=self.ww.win)
            return False
        self.ww.show(self.ww.cur); self.ww.tabs.set(tab)
        warn = self._order_warnings()
        if warn: messagebox.showwarning("Schritte", "Achtung, Reihenfolge:\n- " + "\n- ".join(warn), parent=self.ww.win)
        return True

    def _order_warnings(self):
        st = self.raw.get("steps", []); out = []
        for i, s in enumerate(st):
            for later in st[i:]:
                if later is not s and _refs({k: v for k, v in s.items() if k != "id"}, later["id"]):
                    out.append(f"«{s.get('label', s['id'])}» verwendet «{later.get('label', later['id'])}», das erst später läuft")
        return out

    def _vars(self, upto):
        """[(Gruppe, [(Ausdruck, Beschreibung)])] für «Wert einfügen» – Eingaben und alle Schritte vor upto."""
        out = [("Eingaben beim Start", [(f"input.{i['id']}", i.get("label", "")) for i in self.raw.get("inputs", [])])]
        for s in self.raw.get("steps", [])[:upto]:
            items = [(f"{s['id']}.{k}", d) for k, d in S.ergebnis(s)]
            v = (self.state or {}).get(s["id"])
            if isinstance(v, dict):                                       # was der letzte Lauf wirklich geliefert hat
                have = {e for e, _ in items}
                items += [(f"{s['id']}.{k}", "") for k in v if not k.startswith("_") and f"{s['id']}.{k}" not in have and k != "hits"]
                items = [(e, d + (f"  –  «{_kurz(v.get(e.split('.', 1)[1]), 40)}»" if e.split(".", 1)[1] in v else "")) for e, d in items]
            out.append((f"{s.get('label') or S.titel(s['type'])}  ({s['id']})", items))
        out.append(("Allgemein", [("now", "Datum und Zeit des Laufs"), ("workflow.name", "Name des Workflows")]))
        return out

    def _insert_menu(self, widget, upto, btn):
        m = tk.Menu(btn, tearoff=0)
        for grp, items in self._vars(upto):
            sub = tk.Menu(m, tearoff=0)
            for expr, desc in items:
                sub.add_command(label=f"{expr}    {desc}"[:110], command=lambda e=expr: self._insert(widget, "{{" + e + "}}"))
            if not items: sub.add_command(label="(nichts)", state="disabled")
            m.add_cascade(label=grp, menu=sub)
        m.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())

    @staticmethod
    def _insert(widget, txt):
        if isinstance(widget, ctk.CTkTextbox): widget.insert("insert", txt); widget.focus_set()
        else:
            e = getattr(widget, "_entry", widget); e.insert(e.index("insert"), txt); e.focus_set()

    # ------------------------------------------------------------------ Karten
    def _cards(self):
        G = self.G
        for c in self.lst.winfo_children(): c.destroy()
        steps = self.raw.get("steps", [])
        if not steps:
            ctk.CTkLabel(self.lst, text="Noch keine Schritte. «+ Schritt hinzufügen» – zuerst meist «Dateien lesen».",
                         font=G.font(12), text_color=G.MUTED).grid(row=0, column=0, sticky="w", pady=10)
        for i, s in enumerate(steps):
            meta = S.BAUSTEINE.get(s.get("type"), {})
            card = ctk.CTkFrame(self.lst, fg_color=G.BUBBLE, corner_radius=8, border_width=1, border_color=G.BORDER)
            card.grid(row=i * 2, column=0, sticky="ew", pady=(0, 2)); card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(card, text=str(i + 1), width=28, height=28, corner_radius=14, fg_color=G.ACCENT, text_color="white",
                         font=G.font(12, "bold")).grid(row=0, column=0, rowspan=3, padx=10, pady=8, sticky="n")
            ctk.CTkLabel(card, text=s.get("label") or meta.get("titel", s["type"]), font=G.font(13, "bold"), text_color=G.INK,
                         anchor="w").grid(row=0, column=1, sticky="w", pady=(8, 0))
            ctk.CTkLabel(card, text=f"{meta.get('titel', s['type'])}  ·  Ergebnis unter «{s['id']}»"
                                    + (f"  ·  nur wenn: {s['when']}" if s.get("when") else ""),
                         font=G.font(10), text_color=G.MUTED, anchor="w").grid(row=1, column=1, sticky="w")
            main = next((s.get(f["key"]) for f in meta.get("felder", []) if f["typ"] in ("text", "textarea") and s.get(f["key"])), "")
            v = (self.state or {}).get(s["id"])
            last = ("Letzter Lauf: " + _kurz(v.get("text") if isinstance(v, dict) and v.get("text") else
                                             {k: x for k, x in v.items() if not k.startswith("_") and k != "hits"}, 110)) \
                if isinstance(v, dict) else "Letzter Lauf: –"
            ctk.CTkLabel(card, text=(_kurz(main, 110) + "\n" if main else "") + last, font=G.font(11), text_color=G.MUTED,
                         anchor="w", justify="left", wraplength=640).grid(row=2, column=1, sticky="w", pady=(2, 8))
            bb = ctk.CTkFrame(card, fg_color="transparent"); bb.grid(row=0, column=2, rowspan=3, padx=8)
            self._mini(bb, "Bearbeiten", lambda i=i: self._edit(i)).pack(side="left", padx=2)
            self._mini(bb, "▲", lambda i=i: self._move(i, -1)).pack(side="left", padx=2)
            self._mini(bb, "▼", lambda i=i: self._move(i, 1)).pack(side="left", padx=2)
            self._mini(bb, "✕", lambda i=i: self._del(i)).pack(side="left", padx=2)
            plus = ctk.CTkButton(self.lst, text="＋", width=28, height=18, corner_radius=9, font=G.font(11), fg_color="transparent",
                                 hover_color=G.BORDER, text_color=G.MUTED, command=lambda i=i: self._add(i + 1))
            plus.grid(row=i * 2 + 1, column=0, pady=(0, 2))

    def _move(self, i, d):
        st = self.raw["steps"]
        if not 0 <= i + d < len(st): return
        st[i], st[i + d] = st[i + d], st[i]; self._save()

    def _del(self, i):
        st = self.raw["steps"]; s = st[i]
        users = [o.get("label", o["id"]) for o in st if o is not s and _refs(o, s["id"])]
        if _refs(self.raw.get("pruefungen") or [], s["id"]): users.append("Plausibilitätsprüfungen")
        msg = f"Schritt «{s.get('label', s['id'])}» löschen?"
        if users: msg += "\n\nAchtung, sein Ergebnis wird verwendet in:\n- " + "\n- ".join(users)
        if len(st) == 1: messagebox.showinfo("Schritte", "Der letzte Schritt kann nicht gelöscht werden.", parent=self.ww.win); return
        if messagebox.askyesno("Schritte", msg, parent=self.ww.win): del st[i]; self._save()

    # ------------------------------------------------------------------ Schritt hinzufügen
    def _add(self, pos):
        G = self.G
        dlg = ctk.CTkToplevel(self.ww.win); dlg.title("Schritt hinzufügen"); dlg.transient(self.ww.win); dlg.grab_set()
        dlg.geometry("620x620")
        fr = ctk.CTkScrollableFrame(dlg, fg_color="transparent"); fr.pack(fill="both", expand=True, padx=12, pady=12)
        fr.grid_columnconfigure(0, weight=1); r = 0
        for g in S.GRUPPEN:
            ctk.CTkLabel(fr, text=g.upper(), font=G.font(10, "bold"), text_color=G.MUTED, anchor="w").grid(row=r, column=0, sticky="w", pady=(8, 2)); r += 1
            for typ, m in S.BAUSTEINE.items():
                if m["gruppe"] != g: continue
                b = ctk.CTkButton(fr, text=f"{m['titel']}\n{m['beschreibung']}", anchor="w", height=52, corner_radius=8,
                                  font=G.font(11), fg_color=G.BUBBLE, hover_color=G.BORDER, text_color=G.INK,
                                  command=lambda t=typ: (dlg.destroy(), self._new(t, pos)))
                b.grid(row=r, column=0, sticky="ew", pady=2); r += 1
                try: b._text_label.configure(justify="left", wraplength=540)
                except Exception: pass

    def _new(self, typ, pos):
        if typ == "pruefliste":
            messagebox.showinfo("Schritte", "Die Prüfliste legst du im Fenster «Prüfliste» an – der Schritt entsteht mit dem ersten "
                                "Prüfpunkt.", parent=self.ww.win)
            self.ww.tabs.set("Prüfliste"); return
        meta = S.BAUSTEINE[typ]; ids = {s["id"] for s in self.raw.get("steps", [])}
        sid, n = meta["id"], 2
        while sid in ids or sid == "input": sid = f"{meta['id']}{n}"; n += 1
        step = {"id": sid, "type": typ, "label": meta["titel"]}
        for f in meta["felder"]:
            if "standard" in f: step[f["key"]] = f["standard"]
        self._edit(None, step, pos)

    # ------------------------------------------------------------------ Schritt bearbeiten
    def _edit(self, i, new=None, pos=None):
        G = self.G; step = dict(new if new is not None else self.raw["steps"][i])
        idx = pos if new is not None else i
        meta = S.BAUSTEINE.get(step["type"])
        if not meta:
            messagebox.showinfo("Schritte", f"Für den Baustein «{step['type']}» gibt es noch kein Formular – bitte in der "
                                "workflow.json bearbeiten.", parent=self.ww.win); return
        dlg = ctk.CTkToplevel(self.ww.win); dlg.title(f"{meta['titel']} – {step['id']}"); dlg.transient(self.ww.win)
        dlg.grab_set(); dlg.geometry("780x720")
        ctk.CTkLabel(dlg, text=meta["beschreibung"], font=G.font(11), text_color=G.MUTED, wraplength=740, justify="left",
                     anchor="w").pack(anchor="w", padx=16, pady=(12, 0))
        fr = ctk.CTkScrollableFrame(dlg, fg_color="transparent"); fr.pack(fill="both", expand=True, padx=8, pady=8)
        fr.grid_columnconfigure(1, weight=1)
        widgets, r = {}, 0
        for f in S.GEMEINSAM + meta["felder"]:
            ctk.CTkLabel(fr, text=f["label"] + (" *" if f.get("pflicht") else ""), font=G.font(12), anchor="nw", width=150,
                         justify="left", wraplength=150).grid(row=r, column=0, sticky="nw", padx=(8, 8), pady=(10, 0))
            w = self._widget(fr, f, step.get(f["key"]), dlg); w.grid(row=r, column=1, sticky="ew", pady=(10, 0))
            widgets[f["key"]] = (f, w)
            if f.get("wert_einfuegen"):
                b = ctk.CTkButton(fr, text="Wert einfügen ▾", width=110, height=26, corner_radius=6, font=G.font(11),
                                  fg_color=G.BORDER, hover_color=G.MUTED, text_color=G.INK)
                tgt = w if not isinstance(w, ctk.CTkFrame) else getattr(w, "_ziel", w)
                b.configure(command=lambda w=tgt, b=b: self._insert_menu(w, idx, b)); b.grid(row=r, column=2, sticky="nw", padx=8, pady=(10, 0))
            r += 1
            if f.get("hilfe"):
                ctk.CTkLabel(fr, text=f["hilfe"], font=G.font(10), text_color=G.MUTED, anchor="w", justify="left",
                             wraplength=520).grid(row=r, column=1, sticky="w"); r += 1
        v = (self.state or {}).get(step["id"]) if new is None else None
        if isinstance(v, dict):
            ctk.CTkLabel(fr, text="Ergebnis im letzten Lauf", font=G.font(12), anchor="nw").grid(row=r, column=0, sticky="nw", padx=8, pady=(14, 0))
            tb = ctk.CTkTextbox(fr, height=110, font=G.font(11), wrap="word")
            tb.insert("1.0", "\n".join(f"{k}: {_kurz(x, 300)}" for k, x in v.items() if not k.startswith("_") and k != "hits"))
            tb.configure(state="disabled"); tb.grid(row=r, column=1, columnspan=2, sticky="ew", pady=(14, 0)); r += 1

        def collect():
            out = dict(step)
            for key, (f, w) in widgets.items():
                try: val = self._value(f, w, step.get(key))
                except ValueError as e:
                    messagebox.showwarning("Schritte", f"«{f['label']}»: {e}", parent=dlg); return None
                if val in (None, "", [], {}) and f["typ"] not in ("ja_nein", "info"):
                    if f.get("pflicht"): messagebox.showwarning("Schritte", f"Bitte «{f['label']}» ausfüllen.", parent=dlg); return None
                    out.pop(key, None)
                elif f["typ"] != "info" and not (key not in step and val == f.get("standard")): out[key] = val
            return out

        def save(test=False):
            out = collect()
            if out is None: return
            st = self.raw.setdefault("steps", [])
            if new is not None: st.insert(idx, out)
            else: st[i] = out
            dlg.destroy()
            if self._save() and test: self._test(out["id"])
        bb = ctk.CTkFrame(dlg, fg_color="transparent"); bb.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(bb, text="Speichern & diesen Schritt testen", fg_color=G.BORDER, text_color=G.INK, hover_color=G.MUTED,
                      command=lambda: save(True)).pack(side="left")
        ctk.CTkButton(bb, text="Speichern", width=110, fg_color=G.ACCENT, hover_color=G.ACCENT_HI, command=save).pack(side="right")
        ctk.CTkButton(bb, text="Abbrechen", width=100, fg_color=G.BORDER, text_color=G.INK, hover_color=G.MUTED,
                      command=dlg.destroy).pack(side="right", padx=6)

    def _test(self, sid):
        ids = [s["id"] for s in self.raw["steps"]]
        if ids.index(sid) == 0 or not self._last_state():
            self.ww.pending_stop = sid; self.ww.tabs.set("Ausführen")
            self.ww.lbl_prog.configure(text=f"Test vorbereitet: Eingaben wählen und «Starten» – der Lauf hält nach «{sid}» an.")
            messagebox.showinfo("Schritte", "Für den Test braucht es die Eingaben: im Reiter «Ausführen» Dateien wählen und "
                                "«Starten» drücken. Der Lauf hält nach diesem Schritt an.", parent=self.ww.win)
        else:
            self.ww.tabs.set("Ausführen"); self.ww.start(start_at=sid, stop_after=sid)

    # ------------------------------------------------------------------ Formularfelder
    def _options(self, f, cur):
        o = f.get("optionen") or []
        if o == "vorlagen":
            d = Path(self.ww.cur).parent / "vorlagen"; o = [f"vorlagen/{p.name}" for p in sorted(d.glob("*.docx"))] if d.exists() else []
        elif o == "sammlungen":
            o = ["", "eigen"]
            try:
                from .wissen import Wissen
                o += sorted(Wissen(lambda: None, lambda *a: None).names())
            except Exception: pass
        elif o == "quellen": o = S.QUELLEN
        elif o == "rollen":                                                # v146: freigegebene Rollen
            o = [""]
            try:
                from .skills import aktive_rollen
                o += [r["name"] for r in aktive_rollen()]
            except Exception: pass
        o = list(o)
        if cur not in (None, "") and str(cur) not in o: o.append(str(cur))
        return o or [""]

    def _widget(self, parent, f, cur, dlg):
        G, typ = self.G, f["typ"]
        if cur is None: cur = f.get("standard")
        if typ == "textarea" or typ in ("json", "werte"):
            tb = ctk.CTkTextbox(parent, height=f.get("hoehe", 90 if typ != "json" else 120), font=G.font(12 if typ != "json" else 11),
                                wrap="word", border_width=1, border_color=G.BORDER)
            if typ == "json": txt = "" if cur in (None, [], {}) and not f.get("pflicht") else json.dumps(cur, ensure_ascii=False, indent=1)
            elif typ == "werte": txt = "\n".join(f"{k} = {x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)}"
                                                 for k, x in (cur or {}).items())
            else: txt = cur if isinstance(cur, str) else ("" if cur is None else json.dumps(cur, ensure_ascii=False))
            tb.insert("1.0", txt); return tb
        if typ == "ja_nein":
            cb = ctk.CTkCheckBox(parent, text=""); (cb.select() if cur else cb.deselect()); return cb
        if typ == "auswahl":
            o = self._options(f, cur); om = ctk.CTkOptionMenu(parent, values=o, width=380, fg_color=G.BUBBLE,
                                                               button_color=G.BORDER, text_color=G.INK)
            om.set("" if cur is None else str(cur)); return om
        if typ == "info":
            fr = ctk.CTkFrame(parent, fg_color="transparent")
            n = len(cur) if isinstance(cur, list) else 0
            ctk.CTkLabel(fr, text=f"{n} Einträge", font=G.font(11)).pack(side="left")
            self._mini(fr, "Prüfliste öffnen …", lambda: (dlg.destroy(), self.ww.tabs.set("Prüfliste"))).pack(side="left", padx=8)
            return fr
        if typ == "felder":
            fr = ctk.CTkFrame(parent, fg_color="transparent"); fr._felder = [dict(x) for x in (cur or [])]
            lbl = ctk.CTkLabel(fr, text="", font=G.font(11), anchor="w", justify="left", wraplength=420)
            def show():
                n = [x.get("name", "?") for x in fr._felder]
                lbl.configure(text=(f"{len(n)} Felder: " + ", ".join(n[:6]) + (" …" if len(n) > 6 else "")) if n else "keine – freie Antwort")
            def edit():
                res = self._felder_dialog(dlg, fr._felder)
                if res is not None: fr._felder = res; show()
            self._mini(fr, "Felder bearbeiten …", edit).pack(side="left"); lbl.pack(side="left", padx=8); show(); return fr
        e = ctk.CTkEntry(parent, font=G.font(12))
        if cur is not None: e.insert(0, ", ".join(map(str, cur)) if typ == "liste" and isinstance(cur, list) else str(cur))
        return e

    def _value(self, f, w, orig):
        typ = f["typ"]
        if typ == "info": return orig
        if typ == "felder": return w._felder
        if typ == "ja_nein": return bool(w.get())
        if typ == "auswahl": return w.get()
        txt = (w.get("1.0", "end") if isinstance(w, ctk.CTkTextbox) else w.get()).strip()
        if typ == "zahl":
            if not txt: return None
            try: x = float(txt.replace("'", "").replace(",", ".")); return int(x) if x == int(x) else x
            except ValueError: raise ValueError("bitte eine Zahl eingeben")
        if typ == "liste": return [x.strip() for x in txt.split(",") if x.strip()]
        if typ == "json":
            if not txt: return None
            try: return json.loads(txt)
            except ValueError as e: raise ValueError(f"kein gültiges JSON ({e})")
        if typ == "werte":
            out = {}
            for line in txt.splitlines():
                if not line.strip(): continue
                if "=" not in line: raise ValueError(f"Zeile «{line.strip()}» braucht «name = wert»")
                k, v = (x.strip() for x in line.split("=", 1))
                o = (orig or {}).get(k)
                if o is not None and not isinstance(o, str):
                    try: v = json.loads(v)
                    except ValueError: pass
                out[k] = v
            return out
        return txt

    # ------------------------------------------------------------------ Felder des Sprachmodells
    def _felder_dialog(self, parent, felder):
        G = self.G; felder = [dict(x) for x in felder]; res = {"v": None}
        dlg = ctk.CTkToplevel(parent); dlg.title("Antwort in Feldern"); dlg.transient(parent); dlg.grab_set(); dlg.geometry("720x560")
        ctk.CTkLabel(dlg, text="Jedes Feld ist ein Wert, den das Modell ausfüllt. Spätere Schritte verwenden ihn mit «Wert einfügen».",
                     font=G.font(11), text_color=G.MUTED, wraplength=680, justify="left").pack(anchor="w", padx=14, pady=(12, 6))
        lst = ctk.CTkScrollableFrame(dlg, fg_color="transparent"); lst.pack(fill="both", expand=True, padx=10)
        lst.grid_columnconfigure(0, weight=1)
        def fill():
            for c in lst.winfo_children(): c.destroy()
            for j, x in enumerate(felder):
                row = ctk.CTkFrame(lst, fg_color=G.BUBBLE, corner_radius=6); row.grid(row=j, column=0, sticky="ew", pady=2)
                row.grid_columnconfigure(0, weight=1)
                extra = [n for n, k in (("Auswahl", "auswahl"), ("Zahl", "zahl"), ("Beleg", "beleg"), ("nur Prüfbericht", "vorschlag"), ("ausführlich", "ausfuehrlich_ok")) if x.get(k)]
                ctk.CTkLabel(row, text=f"{x.get('name')}   " + (f"[{', '.join(extra)}]  " if extra else "") + _kurz(x.get("hint", ""), 70),
                             font=G.font(11), anchor="w").grid(row=0, column=0, sticky="w", padx=8, pady=4)
                bb = ctk.CTkFrame(row, fg_color="transparent"); bb.grid(row=0, column=1, padx=4)
                self._mini(bb, "Bearbeiten", lambda j=j: one(j)).pack(side="left", padx=2)
                self._mini(bb, "▲", lambda j=j: mv(j, -1)).pack(side="left", padx=2)
                self._mini(bb, "✕", lambda j=j: (felder.pop(j), fill())).pack(side="left", padx=2)
        def mv(j, d):
            if 0 <= j + d < len(felder): felder[j], felder[j + d] = felder[j + d], felder[j]; fill()
        def one(j):
            x = dict(felder[j]) if j is not None else {"max_tokens": 120}
            d2 = ctk.CTkToplevel(dlg); d2.title("Feld"); d2.transient(dlg); d2.grab_set(); d2.geometry("620x560"); d2.grid_columnconfigure(1, weight=1)
            def lab(r, t, tip=None):
                ctk.CTkLabel(d2, text=t, font=G.font(12)).grid(row=r, column=0, sticky="nw", padx=12, pady=(10, 0))
                if tip: ctk.CTkLabel(d2, text=tip, font=G.font(10), text_color=G.MUTED, wraplength=430, justify="left").grid(row=r + 1, column=1, sticky="w")
            lab(0, "Name", "Kurz, ohne Leerzeichen, z.B. «auftragswert». Unter diesem Namen steht der Wert später bereit.")
            en = ctk.CTkEntry(d2); en.insert(0, x.get("name", "")); en.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(10, 0))
            lab(2, "Was soll drinstehen?", "Kurze Anweisung für das Modell, z.B. «Gesamtbetrag in CHF ohne MWST; unbekannt: 0».")
            eh = ctk.CTkTextbox(d2, height=80, wrap="word"); eh.insert("1.0", x.get("hint", "")); eh.grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=(10, 0))
            lab(4, "Länge (Tokens)", "≈ Wortteile. 10 für ein Wort, 80 für einen Satz, 250 für einen Absatz.")
            el = ctk.CTkEntry(d2, width=100); el.insert(0, str(x.get("max_tokens", 120))); el.grid(row=4, column=1, sticky="w", pady=(10, 0))
            dicts = any(isinstance(o, dict) for o in x.get("auswahl") or [])
            lab(6, "Nur diese Werte", "Optional, durch | getrennt, z.B. «ja | nein | unklar»." +
                (" (Enthält Erklärungen – nur in der workflow.json änderbar.)" if dicts else ""))
            ea = ctk.CTkEntry(d2); ea.insert(0, " | ".join(o if isinstance(o, str) else o.get("wert", "") for o in x.get("auswahl") or []))
            if dicts: ea.configure(state="disabled")
            ea.grid(row=6, column=1, sticky="ew", padx=(0, 12), pady=(10, 0))
            cz = ctk.CTkCheckBox(d2, text="Zahl (zusätzlich <name>_zahl)"); cb = ctk.CTkCheckBox(d2, text="Mit wörtlichem Beleg aus den Unterlagen")
            cv = ctk.CTkCheckBox(d2, text="Nur als Vorschlag in den Prüfbericht (nie ins Ergebnis)")
            cx = ctk.CTkCheckBox(d2, text="Länge folgt der Ausführlichkeit (Regler im Reiter «Ausführen»)")   # v132
            for c, k, r in ((cz, "zahl", 8), (cb, "beleg", 9), (cv, "vorschlag", 10), (cx, "ausfuehrlich_ok", 11)):
                (c.select() if x.get(k) else c.deselect()); c.grid(row=r, column=1, sticky="w", pady=(8, 0))
            def ok():
                n = re.sub(r"[^\w]", "_", en.get().strip())
                if not n: messagebox.showwarning("Feld", "Bitte einen Namen eingeben.", parent=d2); return
                if any(o.get("name") == n for k, o in enumerate(felder) if k != j):
                    messagebox.showwarning("Feld", "Diesen Namen gibt es schon.", parent=d2); return
                x.update(name=n, hint=eh.get("1.0", "end").strip())
                try: x["max_tokens"] = max(1, int(el.get().strip()))
                except ValueError: messagebox.showwarning("Feld", "Länge: bitte eine Zahl.", parent=d2); return
                if not dicts:
                    a = [o.strip() for o in ea.get().split("|") if o.strip()]
                    if a: x["auswahl"] = a
                    else: x.pop("auswahl", None)
                for c, k in ((cz, "zahl"), (cb, "beleg"), (cv, "vorschlag"), (cx, "ausfuehrlich_ok")):
                    if c.get(): x[k] = True
                    else: x.pop(k, None)
                if j is None: felder.append(x)
                else: felder[j] = x
                d2.destroy(); fill()
            ctk.CTkButton(d2, text="Übernehmen", fg_color=G.ACCENT, hover_color=G.ACCENT_HI, command=ok).grid(row=12, column=1, sticky="e", padx=12, pady=16)
        bb = ctk.CTkFrame(dlg, fg_color="transparent"); bb.pack(fill="x", padx=14, pady=10)
        self._mini(bb, "+ Feld", lambda: one(None)).pack(side="left")
        ctk.CTkButton(bb, text="Übernehmen", width=110, fg_color=G.ACCENT, hover_color=G.ACCENT_HI,
                      command=lambda: (res.update(v=felder), dlg.destroy())).pack(side="right")
        ctk.CTkButton(bb, text="Abbrechen", width=100, fg_color=G.BORDER, text_color=G.INK, hover_color=G.MUTED,
                      command=dlg.destroy).pack(side="right", padx=6)
        fill(); dlg.wait_window(); return res["v"]

    def _zeitplan(self):
        G = self.G; zp = self.raw.get("zeitplan") or {"tage": "werktags", "zeit": "08:00"}
        dlg = ctk.CTkToplevel(self.ww.win); dlg.title("Zeitplan"); dlg.transient(self.ww.win); dlg.grab_set(); dlg.geometry("520x260")
        on = ctk.CTkCheckBox(dlg, text="Nach Zeitplan ausführen"); (on.select() if self.raw.get("zeitplan") else on.deselect())
        on.pack(anchor="w", padx=16, pady=(16, 8))
        row = ctk.CTkFrame(dlg, fg_color="transparent"); row.pack(anchor="w", padx=16)
        t = zp.get("tage"); ot = ctk.CTkOptionMenu(row, values=["werktags", "taeglich", "mo", "di", "mi", "do", "fr", "sa", "so"], width=120)
        ot.set(t if isinstance(t, str) else (t[0] if t else "werktags")); ot.pack(side="left")
        ctk.CTkLabel(row, text=" um ").pack(side="left"); ez = ctk.CTkEntry(row, width=70); ez.insert(0, zp.get("zeit", "08:00")); ez.pack(side="left")
        ctk.CTkLabel(dlg, text="Ein Lauf nach Zeitplan kann keine Dateien abfragen: Pflicht-Eingaben vorher entfernen oder freiwillig machen. "
                               "Das Ergebnis erscheint als Meldung im Chat.", font=G.font(10), text_color=G.MUTED, wraplength=480,
                     justify="left").pack(anchor="w", padx=16, pady=10)
        def ok():
            if on.get():
                v = ot.get(); self.raw["zeitplan"] = {"tage": v if v in ("werktags", "taeglich") else [v], "zeit": ez.get().strip().replace(".", ":")}
            else: self.raw.pop("zeitplan", None)
            dlg.destroy(); self._save()
        ctk.CTkButton(dlg, text="Speichern", fg_color=G.ACCENT, hover_color=G.ACCENT_HI, command=ok).pack(anchor="e", padx=16, pady=8)

    # ------------------------------------------------------------------ Eingaben (Auslöser «Manuell»)
    def _inp_del(self, i):
        inp = self.raw["inputs"][i]; pat = re.compile(rf"input\.{re.escape(inp['id'])}\b")
        users = [s.get("label", s["id"]) for s in self.raw.get("steps", []) if pat.search(json.dumps(s, ensure_ascii=False))]
        msg = f"Eingabe «{inp.get('label', inp['id'])}» entfernen?"
        if users: msg += "\n\nSie wird verwendet in:\n- " + "\n- ".join(users)
        if messagebox.askyesno("Eingaben", msg, parent=self.ww.win): del self.raw["inputs"][i]; self._save()

    def _inp_edit(self, i):
        G = self.G; inp = dict(self.raw["inputs"][i]) if i is not None else {"type": "files", "ext": [".pdf", ".docx", ".txt", ".md"]}
        dlg = ctk.CTkToplevel(self.ww.win); dlg.title("Eingabe beim Start"); dlg.transient(self.ww.win); dlg.grab_set()
        dlg.geometry("560x360"); dlg.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(dlg, text="Bezeichnung").grid(row=0, column=0, sticky="w", padx=12, pady=(14, 0))
        en = ctk.CTkEntry(dlg); en.insert(0, inp.get("label", "")); en.grid(row=0, column=1, sticky="ew", padx=12, pady=(14, 0))
        ctk.CTkLabel(dlg, text="Art").grid(row=1, column=0, sticky="w", padx=12, pady=(10, 0))
        ot = ctk.CTkOptionMenu(dlg, values=["Dateien", "Text"]); ot.set("Dateien" if inp.get("type") == "files" else "Text")
        ot.grid(row=1, column=1, sticky="w", padx=12, pady=(10, 0))
        ctk.CTkLabel(dlg, text="Dateitypen").grid(row=2, column=0, sticky="w", padx=12, pady=(10, 0))
        ee = ctk.CTkEntry(dlg); ee.insert(0, ", ".join(inp.get("ext", []))); ee.grid(row=2, column=1, sticky="ew", padx=12, pady=(10, 0))
        ctk.CTkLabel(dlg, text="nur bei Dateien, z.B. .pdf, .docx", font=G.font(10), text_color=G.MUTED).grid(row=3, column=1, sticky="w", padx=12)
        co = ctk.CTkCheckBox(dlg, text="freiwillig (darf leer bleiben)"); (co.select() if inp.get("optional") else co.deselect())
        co.grid(row=4, column=1, sticky="w", padx=12, pady=(10, 0))
        if i is not None:
            ctk.CTkLabel(dlg, text=f"In Schritten verwendbar als: input.{inp['id']}", font=G.font(10), text_color=G.MUTED).grid(
                row=5, column=1, sticky="w", padx=12, pady=(10, 0))
        def ok():
            lab = en.get().strip()
            if not lab: messagebox.showwarning("Eingaben", "Bitte eine Bezeichnung eingeben.", parent=dlg); return
            inp.update(label=lab, type="files" if ot.get() == "Dateien" else "text")
            if i is None:
                ids = {x["id"] for x in self.raw.get("inputs", [])}; b = _slug(lab); nid, n = b, 2
                while nid in ids: nid = f"{b}{n}"; n += 1
                inp["id"] = nid
            if inp["type"] == "files":
                inp["ext"] = [("." + x.strip().lstrip(".")).lower() for x in ee.get().split(",") if x.strip()] or [".pdf", ".docx", ".txt", ".md"]
            else: inp.pop("ext", None)
            if co.get(): inp["optional"] = True
            else: inp.pop("optional", None)
            if i is None: self.raw.setdefault("inputs", []).append(inp)
            else: self.raw["inputs"][i] = inp
            dlg.destroy(); self._save()
        ctk.CTkButton(dlg, text="Speichern", fg_color=G.ACCENT, hover_color=G.ACCENT_HI, command=ok).grid(row=6, column=1, sticky="e", padx=12, pady=18)
