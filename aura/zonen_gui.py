# aura/zonen_gui.py — Reiter «Übersicht»: der Workflow in drei Bereichen. Version 20261015v91
# (v95: «Mitlesen» / «Reparieren» stellen «Dokumente lesen» auf alle Datei-Eingaben um)
# (v93: «Reparieren» für Schritte, die eine fehlende Eingabe lesen)
# (v91: geladener Workflow statt Rohdatei; Eingaben bearbeiten/entfernen; «+ Vorlage hochladen …» mit Analyse im Feldplan)
# ① Was kommt rein? · ② Was soll AURA wissen und tun? · ③ Was kommt raus? – ohne Schritt-IDs und Ausdrücke, Fehlendes rot.
# Inhalt aus workflow/zonen.py. Geändert wird über die bestehenden Dialoge (Eingabe, Zeitplan, Wissen, Feldplan);
# was nur Spezialisten brauchen, öffnet die Expertenansicht.
import json
from pathlib import Path
from tkinter import messagebox
import customtkinter as ctk
from .workflow import zonen as Z

ROT_BG, ROT_FG = ("#FDECEA", "#3A1A17"), ("#8A1C12", "#F5B4AC")
FARBEN = ("#1F4E99", "#2F7D5B", "#B45309")


class ZonenAnsicht:
    def __init__(self, ww, tab):
        self.ww, self.G = ww, ww.G
        G = self.G
        for c in range(3): tab.grid_columnconfigure(c, weight=1, uniform="zone")
        tab.grid_rowconfigure(1, weight=1)
        try: raw = json.loads(Path(ww.cur).read_text(encoding="utf-8"))
        except Exception as e:
            ctk.CTkLabel(tab, text=f"Workflow nicht lesbar: {e}", text_color=G.ERR).grid(row=0, column=0, sticky="w"); return
        geladen = getattr(ww, "wf", None) or {}                           # v91: so, wie die Engine ihn ausführt
        for k in ("steps", "inputs", "knowledge", "zeitplan"):
            if geladen.get(k): raw[k] = geladen[k]
        self.pkg = Path(ww.cur).parent if str(ww.cur).endswith("workflow.json") else None
        a = Z.analyse(raw, self.pkg)
        hd = ctk.CTkFrame(tab, fg_color="transparent"); hd.grid(row=0, column=0, columnspan=3, sticky="ew", padx=4, pady=(4, 8))
        n = a["fehlt"]
        ctk.CTkLabel(hd, text="Alles beisammen – bereit zum Ausführen." if not n else
                     f"{n} Punkt{'e' if n > 1 else ''} rot markiert – bitte ergänzen.", font=G.font(13, "bold"),
                     text_color=G.OK if not n else ROT_FG, anchor="w").pack(anchor="w")
        if raw.get("beschreibung_original"):
            ctk.CTkLabel(hd, text="Beschreibung: " + Z._kurz(raw["beschreibung_original"], 260), font=G.font(11),
                         text_color=G.MUTED, anchor="w", justify="left", wraplength=1000).pack(anchor="w", pady=(2, 0))
        p = self.pkg is not None
        self._zone(tab, 0, "① Was kommt rein?", a["start"], a["rein"],
                   [("+ Eingabe …", self._eingabe), ("Zeitplan …", self._zeitplan)] if p else [])
        self._zone(tab, 1, "② Was soll AURA wissen und tun?", None, a["wissen"],
                   ([("Hilfsdokumente …", lambda: ww.tabs.set("Wissen"))] if p else []) +
                   [("Schritte im Detail …", lambda: ww.tabs.set("Schritte"))])
        self._zone(tab, 2, "③ Was kommt raus?", None, a["raus"],
                   ([("+ Vorlage hochladen …", self._vorlage_neu)] if p else []))
        ctk.CTkButton(tab, text="Weiter: Ausführen ▶", height=32, corner_radius=8, font=G.font(12, "bold"), fg_color=G.ACCENT,
                      hover_color=G.ACCENT_HI, command=lambda: ww.tabs.set("Ausführen")).grid(row=2, column=2, sticky="e", padx=4, pady=(10, 4))

    def _zone(self, tab, col, titel, start, items, aktionen):
        G = self.G
        z = ctk.CTkFrame(tab, fg_color=G.BUBBLE, corner_radius=10); z.grid(row=1, column=col, sticky="nsew", padx=4)
        z.grid_columnconfigure(0, weight=1); z.grid_rowconfigure(2, weight=1)
        ctk.CTkFrame(z, height=4, fg_color=FARBEN[col], corner_radius=2).grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        ctk.CTkLabel(z, text=titel, font=G.font(13, "bold"), text_color=G.INK, anchor="w").grid(row=1, column=0, sticky="w", padx=12, pady=(6, 4))
        lst = ctk.CTkScrollableFrame(z, fg_color="transparent"); lst.grid(row=2, column=0, sticky="nsew", padx=4)
        lst.grid_columnconfigure(0, weight=1)
        gezeigt = set()
        for i, (t, u, rot, akt) in enumerate(items):
            f = ctk.CTkFrame(lst, fg_color=ROT_BG if rot else G.CARD, corner_radius=8); f.grid(row=i, column=0, sticky="ew", pady=3)
            ctk.CTkLabel(f, text=("⚠ " if rot else "") + t, font=G.font(12, "bold"), text_color=ROT_FG if rot else G.INK,
                         anchor="w", justify="left", wraplength=280).pack(anchor="w", padx=10, pady=(6, 0 if u else 6))
            if u: ctk.CTkLabel(f, text=u, font=G.font(11), text_color=ROT_FG if rot else G.MUTED, anchor="w", justify="left",
                               wraplength=280).pack(anchor="w", padx=10, pady=(0, 6))
            knoepfe = []
            if akt and akt[0] == "eingabe" and self.pkg is not None:          # v91
                knoepfe = [("Bearbeiten", lambda n=akt[1]: self._inp(n, "edit")), ("✕ Entfernen", lambda n=akt[1]: self._inp(n, "del"))]
                if rot and "keinem Schritt" in (u or ""): knoepfe.insert(0, ("Mitlesen", self._alle_lesen))     # v95
            elif akt and akt[0] == "repar" and self.pkg is not None:          # v93
                knoepfe = [("Reparieren …", lambda m=akt[1]: self._reparieren(m))]
            elif akt and akt[0] == "vorlage" and self.pkg is not None and akt[1] and akt[1] not in gezeigt:
                gezeigt.add(akt[1]); knoepfe = [("Felder zuordnen …", lambda r=akt[1]: self._feldplan(r))]
            if knoepfe:
                kb = ctk.CTkFrame(f, fg_color="transparent"); kb.pack(anchor="w", padx=8, pady=(0, 6))
                for kt, kc in knoepfe:
                    ctk.CTkButton(kb, text=kt, height=24, width=0, corner_radius=6, font=G.font(11), fg_color=G.BORDER,
                                  hover_color=G.MUTED, text_color=G.INK, command=kc).pack(side="left", padx=(0, 4))
        bb = ctk.CTkFrame(z, fg_color="transparent"); bb.grid(row=3, column=0, sticky="ew", padx=10, pady=(6, 4))
        for t, cmd in aktionen:
            ctk.CTkButton(bb, text=t, height=28, width=0, corner_radius=8, font=G.font(11), fg_color=G.CARD, hover_color=G.BORDER,
                          text_color=G.INK, command=cmd).pack(side="left", padx=(0, 6), pady=2)
        if start: ctk.CTkLabel(z, text=start, font=G.font(11), text_color=G.MUTED, anchor="w").grid(row=4, column=0, sticky="w", padx=12, pady=(0, 10))

    # ------------------------------------------------------------------ Aktionen (bestehende Dialoge)
    def _ed(self):
        """Dialoge des Schritt-Editors ohne dessen Oberfläche; nach dem Speichern zurück in die Übersicht."""
        from .workflow_editor import SchrittEditor as SE
        ed = SE.__new__(SE); ed.ww, ed.G, ed.state = self.ww, self.G, None
        ed.raw = json.loads(Path(self.ww.cur).read_text(encoding="utf-8"))
        ed._save = lambda tab="Übersicht": SE._save(ed, "Übersicht")
        return ed

    def _eingabe(self): self._ed()._inp_edit(None)

    def _inp(self, iid, was):
        """v91: Eingabe über ihre id in der gespeicherten workflow.json finden (nicht über die Position)."""
        if self.ww.running: messagebox.showinfo("Eingaben", "Während eines Laufs nicht ändern.", parent=self.ww.win); return
        ed = self._ed(); ids = [x.get("id") for x in ed.raw.get("inputs", [])]
        if iid not in ids:
            messagebox.showinfo("Eingaben", "Diese Eingabe steht nicht direkt in der workflow.json (sie entsteht beim Laden) – "
                                "bitte in der Expertenansicht ändern.", parent=self.ww.win); return
        (ed._inp_edit if was == "edit" else ed._inp_del)(ids.index(iid))
    def _zeitplan(self): self._ed()._zeitplan()

    def _alle_lesen(self, still=False):
        """v95: «Dokumente lesen» liest jede Datei-Eingabe einzeln, mit Dokumentname als Kopfzeile."""
        if self.ww.running: messagebox.showinfo("Dokumente", "Während eines Laufs nicht möglich.", parent=self.ww.win); return False
        ed = self._ed(); ex = [s for s in ed.raw.get("steps", []) if s.get("type") == "extract"]
        if not ex:
            messagebox.showinfo("Dokumente", "Der Workflow hat keinen Schritt «Dokumente lesen» – in der Expertenansicht "
                                "(Reiter «Schritte») «Dateien lesen» hinzufügen.", parent=self.ww.win); return False
        ex[0]["alle_eingaben"] = True; ed._save()
        if not still: messagebox.showinfo("Dokumente", f"«{ex[0].get('label', ex[0]['id'])}» liest jetzt alle Datei-Eingaben. "
                                          "Das Sprachmodell sieht jedes Dokument mit seinem Namen, z.B. «=== Checkliste ===».", parent=self.ww.win)
        return True

    def _reparieren(self, alt):
        """v93: Verweise «input.<alt>» in allen Schritten auf eine vorhandene Datei-Eingabe umhängen."""
        import re
        if self.ww.running: messagebox.showinfo("Reparieren", "Während eines Laufs nicht möglich.", parent=self.ww.win); return
        ed = self._ed(); fi = [i for i in ed.raw.get("inputs", []) if i.get("type") == "files"]
        nutzer = [s for s in ed.raw.get("steps", []) if re.search(rf"(?<![\w.])input\.{re.escape(alt)}\b", json.dumps(s, ensure_ascii=False))]
        if fi and nutzer and all(s.get("type") == "extract" for s in nutzer):     # v95: nur «Dokumente lesen» betroffen
            self._alle_lesen(); return
        if not fi:
            messagebox.showinfo("Reparieren", "Es gibt keine Datei-Eingabe. Zuerst «+ Eingabe …» (Art: Dateien) anlegen.", parent=self.ww.win); return
        G = self.G; d = ctk.CTkToplevel(self.ww.win); d.title("Reparieren"); d.transient(self.ww.win); d.grab_set(); d.geometry("520x220")
        ctk.CTkLabel(d, text=f"Welche Eingabe sollen die Schritte statt «{alt}» lesen?\nTipp: Eine Datei-Eingabe nimmt beliebig viele Dateien "
                     "auf (z.B. Leistungsbeschrieb und Checkliste zusammen).", font=G.font(12), wraplength=480, justify="left").pack(anchor="w", padx=16, pady=(16, 8))
        namen = {f"{i.get('label', i['id'])}  ({i['id']})": i["id"] for i in fi}
        o = ctk.CTkOptionMenu(d, values=list(namen), width=440); o.set(list(namen)[0]); o.pack(anchor="w", padx=16)
        def ok():
            neu = namen[o.get()]; txt = json.dumps(ed.raw.get("steps", []), ensure_ascii=False)
            ed.raw["steps"] = json.loads(re.sub(rf"(?<![\w.])input\.{re.escape(alt)}\b", "input." + neu, txt))
            d.destroy(); ed._save()
        ctk.CTkButton(d, text="Umhängen", fg_color=G.ACCENT, hover_color=G.ACCENT_HI, command=ok).pack(anchor="e", padx=16, pady=16)

    def _vorlage_neu(self):
        """v91: Word-Vorlage ins Paket kopieren und gleich analysieren (Feldplan öffnet sich)."""
        from tkinter import filedialog
        from .workflow import paket
        if self.ww.running: messagebox.showinfo("Vorlage", "Während eines Laufs nicht möglich.", parent=self.ww.win); return
        f = filedialog.askopenfilename(parent=self.ww.win, title="Word-Vorlage wählen", filetypes=[("Word", "*.docx")])
        if not f: return
        try: t = paket.add_template(self.pkg, f)
        except Exception as e: messagebox.showerror("Vorlage", f"Nicht übernommen: {e}", parent=self.ww.win); return
        rel = f"vorlagen/{t.name}"
        self.ww.show(self.ww.cur); self.ww.tabs.set("Übersicht")
        self._feldplan(rel)

    def _feldplan(self, rel):
        p = self.pkg / rel
        if not p.is_file(): messagebox.showinfo("Felder zuordnen", f"Vorlage nicht gefunden: {rel}", parent=self.ww.win); return
        from .feldplan_gui import FeldplanFenster
        self.ww.fp = FeldplanFenster(self.ww, p, rel)
