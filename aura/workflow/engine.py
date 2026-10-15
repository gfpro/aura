# aura/workflow/engine.py — Workflows laden, pruefen und Schritt fuer Schritt ausfuehren. Version 20261015v95 (v42: Standby waehrend des Laufs verhindern)
# v95: extract mit "alle_eingaben": true liest JEDE Datei-Eingabe einzeln und setzt die Texte mit Kopfzeile «##### EINGABE «<Bezeichnung>» #####»
#      zusammen (max_chars gerecht verteilt). Liefert «Dokumente lesen» keinen Text, bricht der Lauf ab (statt das Modell
#      auf leere Unterlagen anzusetzen); Ausnahme: "leer_erlaubt": true.
#
# v40: "pruefungen": [{"name", "wenn": Ausdruck (wahr = Problem), "meldung": Text mit {{...}}}] laufen nach jedem
#      Lauf. Zusammen mit den _warnungen der Schritte stehen sie in res["pruefungen"] (Protokoll und Fenster).
# v41: Grundsatz «Erklaerungen des Werkzeugs nie ins Ausgabedokument»: _hinweise/_warnungen aller Schritte,
#      Pruefungen und Belege landen im separaten Pruefbericht.txt im Laufordner (öffnet neben dem Ergebnis).
# v54: Pruefbericht.txt nur, wenn es etwas zu berichten gibt (Hinweise, Belege, Prüfliste, Vorschläge, Entscheide).
# v53: Bausteine kalender/mails/fuer_jedes/meldung (quellen.py); "zeitplan": {"tage", "zeit"} im Workflow;
#      Meldungen der Schritte in res["meldungen"].
# v52: Runner(stop_after=...) haelt nach einem Schritt an («Schritt testen» im Reiter «Schritte»).
# v50: Baustein «pruefliste» (pruefliste.py) wird geprueft und erscheint als eigener Abschnitt im Pruefbericht.
# v44: Feldoption «vorschlag» (Formulierungsvorschlaege nur im Pruefbericht). Die Engine verweigert den Workflow,
#      wenn ein anderer Schritt oder eine Pruefung ein Vorschlagsfeld verwendet. Laufzeiten je Schritt ins Log.
#
# Format (workflows\*.json):
# { "name": "...", "description": "...", "llm": "<Backend-ID, optional>",
#   "inputs": [ {"id": "files", "type": "files", "label": "Unterlagen", "ext": [".pdf", ".docx"]},
#               {"id": "text",  "type": "text",  "label": "Bemerkungen", "optional": true} ],
#   "steps":  [ {"id": "txt", "type": "extract", "files": "{{input.files}}"},
#               {"id": "ana", "type": "llm", "prompt": "... {{txt.text}} ...", "max_new": 800},
#               {"id": "x",   "type": "set", "when": "contains(ana.text, 'einladung')", "values": {...}} ] }
# Ergebnis jedes Schritts liegt unter seiner id; Eingaben unter input.<id>. "when" ueberspringt Schritte.
import json, re, time, traceback
from datetime import datetime
from pathlib import Path
from .expr import evaluate, resolve, render, as_text, truthy, ExprError
from .nodes import NODES
from .llmio import Cancelled
from ..log import diag

INPUT_TYPES = ("files", "text")

class WorkflowError(ValueError): pass

def load_workflow(path):
    path = Path(path)
    if path.is_dir(): path = path / "workflow.json"                  # Workflow-Paket (Ordner)
    try: wf = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e: raise WorkflowError(f"{path.name}: kein gueltiges JSON ({e})")
    errs, ids = [], set()
    if not isinstance(wf.get("steps"), list) or not wf["steps"]: errs.append("'steps' fehlt oder ist leer")
    for i, inp in enumerate(wf.get("inputs", [])):
        if inp.get("type") not in INPUT_TYPES: errs.append(f"Eingabe {i + 1}: type muss {INPUT_TYPES} sein")
        if not inp.get("id"): errs.append(f"Eingabe {i + 1}: id fehlt")
    for i, st in enumerate(wf.get("steps") or []):
        sid, typ = st.get("id"), st.get("type")
        if not sid: errs.append(f"Schritt {i + 1}: id fehlt")
        elif sid in ids or sid == "input": errs.append(f"Schritt {i + 1}: id «{sid}» doppelt/reserviert")
        ids.add(sid)
        if typ not in NODES: errs.append(f"Schritt {sid or i + 1}: unbekannter type «{typ}» (erlaubt: {', '.join(NODES)})")
        if typ == "llm":
            for f in st.get("fields") or []:
                if not isinstance(f, dict) or not f.get("name"): errs.append(f"Schritt {sid}: fields braucht name"); continue
                if f.get("vorschlag"):                               # v44: Vorschlag nie ins Dokument
                    bad = [k for k in ("auswahl", "zahl", "beleg", "wenn_leer") if f.get(k)]
                    if bad: errs.append(f"Schritt {sid}, Feld «{f['name']}»: vorschlag lässt sich nicht mit {', '.join(bad)} kombinieren")
                    ref = f"{sid}.{f['name']}"
                    andere = json.dumps([x for x in wf["steps"] if x is not st] + [wf.get("pruefungen") or []], ensure_ascii=False)
                    if re.search(re.escape(ref) + r"(?![\w])", andere):
                        errs.append(f"Feld «{ref}» ist ein Vorschlag (nur Prüfbericht) und darf nirgends verwendet werden")
        if typ == "pruefliste":                                         # v50
            from .pruefliste import validate
            errs += validate(st)
        if typ == "fuer_jedes" and (st.get("schritt") or {}).get("type") not in NODES:
            errs.append(f"Schritt {sid}: «schritt» braucht einen gültigen type")
    zp = wf.get("zeitplan")
    if zp is not None:
        from ..zeitplan import pruefen
        errs += pruefen(zp)
        if any(not i.get("optional") for i in wf.get("inputs", [])): errs.append("zeitplan: Workflows nach Zeitplan dürfen keine Pflicht-Eingaben haben")
    for i, pr in enumerate(wf.get("pruefungen") or []):
        if not isinstance(pr, dict) or not pr.get("wenn") or not pr.get("meldung"): errs.append(f"pruefungen {i + 1}: wenn und meldung nötig")
    if errs: raise WorkflowError(f"{path.name}:\n- " + "\n- ".join(errs))
    kn = []
    for k in wf.get("knowledge") or []:                              # "beschaffungsrecht" oder {"sammlung":..., "pflicht":[...]}
        k = {"sammlung": k} if isinstance(k, str) else dict(k)
        if not k.get("sammlung"): errs.append("knowledge: Eintrag ohne sammlung")
        kn.append(k)
    if errs: raise WorkflowError(f"{path.name}:\n- " + "\n- ".join(errs))
    pkg = path.name == "workflow.json"
    own = f"wf:{path.parent.name}" if pkg else None
    def eigen(c):                                                    # «eigen» = Wissen dieses Workflow-Pakets
        if own is None: return c
        if isinstance(c, list): return [own if x == "eigen" else x for x in c]
        return own if c == "eigen" else c
    for k in kn: k["sammlung"] = eigen(k["sammlung"])
    for st in wf.get("steps") or []:
        if st.get("collection"): st["collection"] = eigen(st["collection"])
    wf["knowledge"] = kn
    wf.setdefault("name", path.parent.name if pkg else path.stem); wf.setdefault("inputs", []); wf["_path"] = str(path)
    if pkg: wf["_dir"] = str(path.parent)
    return wf

def list_workflows(folder):
    out = []
    for p in sorted(Path(folder).glob("*/workflow.json")) + sorted(Path(folder).glob("*.json")):
        try: wf = load_workflow(p); out.append({"path": str(p), "name": wf["name"], "description": wf.get("description", ""),
                                                "inputs": wf["inputs"], "error": None})
        except Exception as e: out.append({"path": str(p), "name": p.stem, "description": "", "inputs": [], "error": str(e)})
    return out

class Ctx:
    """Verbindung zur App (Worker oder Kommandozeile). llm(backend_id|None) -> (backend, id, label)."""
    def __init__(self, conn, settings, llm, search, wf_dir, out_dir, runs_dir,
                 progress=print, cancelled=lambda: False, on_text=None, wissen=None):
        self.conn, self.settings, self.llm, self.search, self.wissen = conn, settings, llm, search, wissen
        self.wf_dir, self.out_dir, self.runs_dir = Path(wf_dir), Path(out_dir), Path(runs_dir)
        self.progress, self.cancelled, self.on_text = progress, cancelled, on_text

def _short(v, n=300):
    if isinstance(v, dict): return {k: _short(x, n) for k, x in v.items() if k != "hits"}
    if isinstance(v, str) and len(v) > n: return v[:n] + f"… ({len(v)} Zeichen)"
    return v

def latest_state(runs_dir, wf):
    """Neuester gespeicherter Zwischenstand dieses Workflows (oder None)."""
    if wf.get("_dir"): c = sorted(Path(wf["_dir"]).glob("laeufe/*/zwischenstand.json"))
    else: c = sorted(Path(runs_dir).glob(f"*_{Path(wf['_path']).stem}.state.json"))
    return c[-1] if c else None

def check_files(wf, wf_dir, inputs):
    """Vor dem Lauf: Eingabedateien und feste Vorlagen/Dateien der Schritte muessen existieren."""
    errs = []
    for i in wf["inputs"]:
        if i["type"] == "files":
            for f in inputs.get(i["id"]) or []:
                if not Path(f).is_file(): errs.append(f"Eingabedatei fehlt: {f}")
    for st in wf["steps"]:
        for key in ("vorlage", "file"):
            v = st.get(key)
            if isinstance(v, str) and "{{" not in v:
                p = Path(v) if Path(v).is_absolute() else Path(wf_dir) / v
                if not p.is_file(): errs.append(f"Schritt «{st['id']}»: Datei fehlt: {p}")
    return errs

def _wach(on):
    """v42: Windows waehrend eines Laufs nicht in den Ruhezustand schicken (gilt fuer diesen Thread).
    Bildschirm darf aus; Deckel zuklappen schickt das Notebook trotzdem schlafen."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | (0x00000001 if on else 0))   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    except Exception: pass

class Runner:
    def __init__(self, wf, inputs, ctx, on_step=None, start_at=None, state_file=None, stop_after=None):
        """start_at/state_file: Neustart ab einem Schritt mit den gespeicherten Ergebnissen der Schritte davor."""
        self.wf, self.ctx = wf, ctx; self.on_step = on_step or (lambda *a: None); self.start_at = start_at; self.stop_after = stop_after
        ctx.wf_dir = Path(wf["_path"]).parent                         # Vorlagen usw. relativ zum Workflow
        ids = [s["id"] for s in wf["steps"]]
        if start_at:
            if start_at not in ids: raise WorkflowError(f"Schritt «{start_at}» gibt es nicht ({', '.join(ids)})")
            sf = Path(state_file) if state_file else latest_state(ctx.runs_dir, wf)
            if not sf or not sf.exists(): raise WorkflowError("Kein gespeicherter Zwischenstand fuer diesen Workflow")
            self.state = json.loads(sf.read_text(encoding="utf-8"))
            need = [x for x in ids[:ids.index(start_at)] if x not in self.state
                    and not next(s for s in wf["steps"] if s["id"] == x).get("when")]
            if need: raise WorkflowError(f"Zwischenstand {sf.name} hat keine Ergebnisse fuer: {', '.join(need)}")
            if inputs: self.state["input"].update({k: v for k, v in inputs.items() if v})
            ctx.progress(f"Neustart ab «{start_at}» mit Zwischenstand {sf.name}")
        else:
            miss = [i["id"] for i in wf["inputs"] if not i.get("optional") and not inputs.get(i["id"])]
            if miss: raise WorkflowError(f"Eingabe fehlt: {', '.join(miss)}")
            self.state = {"input": dict(inputs)}
        errs = check_files(wf, ctx.wf_dir, self.state["input"] if not start_at else {})
        if errs: raise WorkflowError("Vor dem Start:\n- " + "\n- ".join(errs))
        self.state.update(workflow={"name": wf["name"], "llm": wf.get("llm")}, now=datetime.now().strftime("%d.%m.%Y %H:%M"))
        self.log = []
        if wf.get("_dir"):                                           # Paket: alles eines Laufs in laeufe\<Zeit>\
            run_dir = (Path(state_file) if state_file else latest_state(ctx.runs_dir, wf)).parent if start_at \
                else Path(wf["_dir"]) / "laeufe" / datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir.mkdir(parents=True, exist_ok=True)
            ctx.out_dir = ctx.runs_dir = run_dir
            self.state_path, self.log_path = run_dir / "zwischenstand.json", run_dir / "protokoll.json"
            if not start_at: self._copy_inputs(run_dir / "eingaben")
        else:
            self.state_path = Path(ctx.runs_dir) / f"{datetime.now():%Y%m%d_%H%M%S}_{Path(wf['_path']).stem}.state.json"
            self.log_path = None

    def _copy_inputs(self, dest):
        """Eingabedateien in den Laufordner kopieren: der Lauf bleibt nachvollziehbar, auch wenn das Original wandert."""
        import shutil
        for i in self.wf["inputs"]:
            if i["type"] != "files" or not self.state["input"].get(i["id"]): continue
            dest.mkdir(parents=True, exist_ok=True); new = []
            for f in self.state["input"][i["id"]]:
                t = dest / Path(f).name
                if Path(f).resolve() != t.resolve(): shutil.copy2(f, t)
                new.append(str(t))
            self.state["input"][i["id"]] = new

    def _save_state(self):
        """Nach jedem Schritt: vollstaendiger Zwischenstand (fuer «ab Schritt neu starten»)."""
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state, ensure_ascii=False, default=str), encoding="utf-8"); tmp.replace(self.state_path)
        except Exception as e: self.ctx.progress(f"Zwischenstand nicht gespeichert: {e}")

    def _prepare_knowledge(self):
        """Wissenssammlungen abgleichen und pruefen: fehlende Pflichtdokumente = Abbruch, Veraltetes = Warnung."""
        kn = self.wf.get("knowledge") or []
        if not kn: return
        if self.ctx.wissen is None: raise WorkflowError("Wissenssammlungen sind hier nicht verfuegbar")
        names = [k["sammlung"] for k in kn]
        self.ctx.progress(f"Wissen vorbereiten: {', '.join(names)} ...")
        st = self.ctx.wissen.prepare(names, self.ctx.cancelled)
        errs = []
        for k in kn:
            s = st[k["sammlung"]]; have = {d["kurz"].lower() for d in s["dokumente"]} | {d["titel"].lower() for d in s["dokumente"]}
            miss = list(s["fehlend"]) + [p for p in k.get("pflicht", []) if p.lower() not in have]
            if miss: errs.append(f"Sammlung «{k['sammlung']}»: es fehlen {', '.join(miss)} (Ordner wissen\\{k['sammlung']})")
            if not s["dokumente"]: errs.append(f"Sammlung «{k['sammlung']}» ist leer")
            for v in s["veraltet"]: self.ctx.progress(f"Achtung, Stand pruefen: {v}")
            if s.get("fehler"): self.ctx.progress(f"Achtung: {s['fehler']}")
        self.state["wissen"] = st
        if errs: raise WorkflowError("Wissen unvollstaendig:\n- " + "\n- ".join(errs))

    def _pruefen(self):
        """v40: Warnungen der Schritte + Plausibilitaetspruefungen des Workflows."""
        out = []
        for st in self.wf["steps"]:
            v = self.state.get(st["id"])
            if isinstance(v, dict):
                for k in ("_warnungen", "_hinweise"):
                    x = v.get(k) or []
                    x = [s.strip() for s in (x.split("|") if isinstance(x, str) else x) if s and s.strip()]
                    out += [f"{st.get('label', st['id'])}: {w}" for w in x]
        for p in self.wf.get("pruefungen") or []:
            try:
                if truthy(evaluate(p["wenn"], self.state)): out.append(as_text(render(p["meldung"], self.state)))
            except Exception as e: out.append(f"Prüfung «{p.get('name', p['wenn'][:40])}» nicht auswertbar: {e}")
        for m in out: self.ctx.progress(f"Prüfung: {m}")
        return out

    def _bericht(self, pr, files):
        """v41: Pruefbericht.txt – alles, was das Werkzeug zur Erklaerung sagt, getrennt vom amtlichen Dokument."""
        L = [f"PRÜFBERICHT – {self.wf['name']}", f"Lauf: {self.state.get('now', '')}   ·   erstellt von AURA, nicht Teil des Dokuments", ""]
        L += ["Ergebnis: " + ", ".join(Path(f).name for f in files) if files else "Ergebnis: –", ""]
        for st in self.wf["steps"]:                                    # v50: Ergebnis der Prüfliste
            v = self.state.get(st["id"])
            if st["type"] == "pruefliste" and isinstance(v, dict):
                from .pruefliste import bericht
                L += [f"PRÜFLISTE «{st.get('label', st['id'])}»: {v.get('fehler', 0)} Fehler, {v.get('hinweise', 0)} Hinweise, "
                      f"{v.get('ok', 0)} erfüllt, {v.get('nicht_pruefbar', 0)} nicht prüfbar"] + bericht(v.get("_pruefliste") or []) + [""]
        L += ["PRÜFHINWEISE (bitte vor der Abgabe prüfen)"] + ([f"  • {m}" for m in pr] or ["  keine"]) + [""]
        bel = []
        for st in self.wf["steps"]:
            v = self.state.get(st["id"])
            if not isinstance(v, dict): continue
            for k, ok in v.items():
                if not k.endswith("_belegt") or ok is None: continue
                n = k[:-7]; z = str(v.get(n + "_beleg", ""))[:300]
                bel.append(f"  {'✓ belegt  ' if ok else '✗ verworfen'}  {n}: «{v.get(n + '_roh', v.get(n, ''))}»\n               Zitat: «{z}»")
        L += ["BELEGE AUS DEN UNTERLAGEN"] + (bel or ["  keine belegpflichtigen Angaben"]) + [""]
        vor = []                                                     # v44: Formulierungsvorschlaege
        for st in self.wf["steps"]:
            v = self.state.get(st["id"])
            if isinstance(v, dict):
                for k, t in (v.get("_vorschlaege") or {}).items(): vor.append(f"  {k}:\n    " + str(t).replace("\n", "\n    "))
        if vor: L += ["FORMULIERUNGSVORSCHLÄGE (vom Sprachmodell, nicht geprüft, nicht im Dokument)"] + vor + [""]
        for st in self.wf["steps"]:
            v = self.state.get(st["id"])
            if st["type"] == "regel" and isinstance(v, dict):
                L += [f"ENTSCHEID «{st.get('label', st['id'])}»: Regel «{v.get('_regel', '')}»", ""]
        L += ["Eingaben:"] + [f"  {Path(f).name}" for i in self.wf["inputs"] if i["type"] == "files"
                              for f in (self.state["input"].get(i["id"]) or [])]
        p = Path(self.ctx.out_dir) / "Pruefbericht.txt"
        p.write_text("\n".join(L) + "\n", encoding="utf-8-sig")
        return str(p)

    def _bericht_noetig(self, pr):
        if pr: return True
        for st in self.wf["steps"]:
            v = self.state.get(st["id"])
            if st["type"] in ("pruefliste", "regel") and isinstance(v, dict): return True
            if isinstance(v, dict) and (v.get("_vorschlaege") or any(k.endswith("_belegt") and x is not None for k, x in v.items())):
                return True
        return False

    def _extract_alle(self, params):
        """v95: Jede Datei-Eingabe einzeln lesen; Texte mit Kopfzeile, Zeichenbudget gerecht verteilt (kurze geben ab)."""
        mx = int(params.get("max_chars") or 16000)
        base = {k: v for k, v in params.items() if k not in ("files", "alle_eingaben", "leer_erlaubt")}
        teile = []
        for i in self.wf["inputs"]:
            fs = self.state["input"].get(i["id"]) if i.get("type") == "files" else None
            if not fs: continue
            o = NODES["extract"](dict(base, files=fs, max_chars=mx), self.state, self.ctx) or {}
            teile.append((i.get("label") or i["id"], o, str(o.get("text") or "")))
        if not teile: return {"text": "", "files": [], "chars": 0, "truncated": False, "teile": {}}
        # Kopf je Eingabe; darunter steht wie bisher «=== Dokument: <Datei> ===» (n_extract) – so kennt das Modell beides
        kopf = [f"##### EINGABE «{lab}» #####\n" for lab, _, _ in teile]
        MARKE = "\n[... gekürzt]"
        rest = max(0, mx - sum(len(k) + 2 + len(MARKE) for k in kopf)); quote = [0] * len(teile)
        for n, j in enumerate(sorted(range(len(teile)), key=lambda j: len(teile[j][2]))):
            quote[j] = min(len(teile[j][2]), rest // (len(teile) - n)); rest -= quote[j]
        text = "\n\n".join(k + t[:q].rstrip() + (MARKE if len(t) > q else "") for k, (_, _, t), q in zip(kopf, teile, quote))
        return {"text": text, "chars": len(text), "files": [f for _, o, _ in teile for f in (o.get("files") or [])],
                "truncated": any(o.get("truncated") or len(t) > q for (_, o, t), q in zip(teile, quote)),
                "teile": {lab: min(len(t), q) for (lab, _, t), q in zip(teile, quote)}}

    def execute(self):
        _wach(True)
        try: return self._execute()
        finally: _wach(False)

    def _execute(self):
        ctx, t_all = self.ctx, time.perf_counter(); status = "ok"; err = None
        steps = self.wf["steps"]
        try:
            self._prepare_knowledge()
            first = [x["id"] for x in steps].index(self.start_at) if self.start_at else 0
            for i, st in enumerate(steps):
                sid, typ = st["id"], st["type"]
                if i < first:
                    self.log.append({"id": sid, "type": typ, "aus_zwischenstand": True}); continue
                if ctx.cancelled(): raise Cancelled()
                if st.get("when") and not truthy(evaluate(st["when"], self.state)):
                    self.log.append({"id": sid, "type": typ, "skipped": True}); self.on_step(i, len(steps), sid, "übersprungen")
                    continue
                self.on_step(i, len(steps), sid, "läuft")
                ctx.progress(f"Schritt {i + 1}/{len(steps)}: {st.get('label', sid)} ({typ})")
                params = {k: v for k, v in st.items() if k not in ("id", "type", "when", "label")}
                skip = {"template": ("text",), "regel": ("regeln", "sonst"), "fuer_jedes": ("schritt",)}.get(typ, ())
                params = resolve(params, self.state, skip=skip)
                t0 = time.perf_counter()
                try:
                    if typ == "extract" and st.get("alle_eingaben"): out = self._extract_alle(params)     # v95
                    else: out = NODES[typ](params, self.state, ctx)
                except (Cancelled, KeyboardInterrupt): raise
                except ExprError as e: raise WorkflowError(f"Schritt «{sid}»: {e}")
                except Exception as e: raise WorkflowError(f"Schritt «{sid}» ({typ}): {type(e).__name__}: {e}") from e
                if typ == "extract" and not st.get("leer_erlaubt") and not (isinstance(out, dict) and str(out.get("text") or "").strip()):
                    n = len(out.get("files") or []) if isinstance(out, dict) else 0                     # v95
                    raise WorkflowError(f"Schritt «{st.get('label', sid)}»: " + (
                        "keine Dateien erhalten – liest der Schritt die richtige Eingabe? (Workflow → Übersicht)" if not n else
                        f"aus {n} Datei(en) kein Text lesbar – gescanntes PDF ohne Textschicht?"))
                self.state[sid] = out
                dt = time.perf_counter() - t0
                self.log.append({"id": sid, "type": typ, "seconds": round(dt, 1), "out": _short(out)})
                self.on_step(i, len(steps), sid, f"fertig {dt:.0f} s")
                self._save_state()
                if self.stop_after == sid:                                  # v52: Schritt testen
                    ctx.progress(f"Test: angehalten nach «{st.get('label', sid)}»"); break
        except Cancelled: status = "abgebrochen"
        except Exception as e:
            status, err = "fehler", str(e); self.log.append({"error": str(e), "trace": traceback.format_exc()[-2000:]})
        pr = self._pruefen() if status == "ok" else []
        total = time.perf_counter() - t_all
        files = [v["path"] for v in self.state.values() if isinstance(v, dict) and isinstance(v.get("path"), str)]
        if status == "ok" and self._bericht_noetig(pr):
            try: files.append(self._bericht(pr, files))
            except Exception as e: ctx.progress(f"Prüfbericht nicht geschrieben: {e}")
        meld = [v["_meldung"] for v in self.state.values() if isinstance(v, dict) and isinstance(v.get("_meldung"), dict)]
        res = {"workflow": self.wf["name"], "path": self.wf.get("_path"), "meldungen": meld, "status": status, "error": err, "seconds": round(total, 1),
               "files": files, "log": self.log, "zwischenstand": str(self.state_path), "pruefungen": pr}
        try:
            self.ctx.runs_dir.mkdir(parents=True, exist_ok=True)
            p = self.log_path or self.ctx.runs_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{Path(self.wf['_path']).stem}.json"
            p.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8"); res["run_log"] = str(p)
        except Exception as e: ctx.progress(f"Lauf-Protokoll nicht gespeichert: {e}")
        diag("workflow", name=self.wf["name"], status=status, s=total, hinweise=len(pr),
             schritte=[f"{l['id']}:{l['seconds']}" for l in self.log if "seconds" in l])
        ctx.progress(f"Workflow {self.wf['name']}: {status} nach {total:.0f} s" + (f" – {err}" if err else "")
                     + (f" · {len(pr)} Prüfhinweise" if pr else ""))
        return res
