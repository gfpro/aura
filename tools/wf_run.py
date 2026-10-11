# tools/wf_run.py — Workflows ohne Oberflaeche testen. Version 20261008v36  (AURA vorher schliessen: GPU!)
#   py tools\wf_run.py --check                      Schnittstelle zum Sprachmodell pruefen (zuerst!)
#   py tools\wf_run.py --list                       vorhandene Workflows
#   py tools\wf_run.py workflows\dokument_kurzpruefung.json --file C:\pfad\a.pdf --text "Hinweis"
#   py tools\wf_run.py --wissen                     Wissenssammlungen abgleichen, einbetten, Status zeigen
#   py tools\wf_run.py --wissen-suche beschaffungsrecht "freihaendiges Verfahren" [--pin "BöB Art. 21"]
#   py tools\wf_run.py --wissen-diag C:\aura\wissen\beschaffungsrecht\boeb.pdf   (Artikel-Erkennung pruefen)
#   py tools\wf_run.py --vorlage-felder workflows\vorlagen\X.docx    (Felder einer Word-Vorlage auflisten)
#   py tools\wf_run.py workflows\X.json             ohne --file: Dateiauswahl-Fenster
#   py tools\wf_run.py workflows\X.json --ab doc    Neustart ab Schritt «doc» mit dem letzten Zwischenstand
#                                                    (--zustand <datei.state.json> fuer einen bestimmten)
#   py tools\wf_run.py --umziehen workflows\verfahrensentscheid.json --sammlung beschaffungsrecht
#                                                    Einzeldatei-Workflow in ein Paket (Ordner) umziehen
#   py tools\wf_run.py workflows\verfahrensentscheid   Paket ausfuehren (Ordner statt .json)
#   Optionen: --llm <Backend-ID> (sonst Einstellung), --set id=wert (weitere Eingaben)
import argparse, json, sys, time, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "vendor")]

from aura import db
from aura.config import MODELS, load_settings
from aura.llm import discover
from aura.rag import Retriever
from aura.workflow import Runner, list_workflows, load_workflow, llmio
from aura.workflow.app import WF_DIR, make_ctx
from aura.wissen import Wissen, WISSEN_DIR

def progress(t, done=None, total=None):
    print(f"   {t}" + (f"  [{done}/{total}]" if total else ""), flush=True)

_be = {}
def get_llm(bid):
    if bid not in _be:
        fac = {i: f for i, _, f in discover(MODELS)}.get(bid)
        if fac is None: sys.exit(f"Sprachmodell {bid} nicht gefunden. Vorhanden: {[i for i, _, _ in discover(MODELS)]}")
        be = fac(); be.progress = progress; t0 = time.perf_counter(); be.load()
        print(f"   Modell {bid} geladen in {time.perf_counter() - t0:.0f} s"); _be[bid] = be
    return _be[bid]

_emb = []
def get_embedder():
    if not _emb:
        try:
            from aura.engine.embedder import Embedder
            _emb.append(Embedder(MODELS / load_settings()["embed_model"]))
        except Exception as e: print(f"   (Embedding nicht verfuegbar: {e} - Suche nur BM25)"); _emb.append(None)
    return _emb[0]

def check(bid):
    print(f"=== Pruefung Workflow-Schnittstelle, Modell {bid} ===")
    be = get_llm(bid)
    try: P = llmio.parts(be)
    except Exception as e:
        print(f"[FEHLER] {e}")
        for k, v in sorted(vars(be).items()): print(f"     {k}: {type(v).__name__}")
        print("-> Bitte diese Ausgabe und aura\\llm\\native.py zurueckmelden."); return
    print(f"[OK] Engine {type(P.eng).__name__}, Tokenizer {type(P.tok).__name__}, Kontext {P.maxT} Tokens, Block {P.chunk}")
    print(f"[OK] Spezialtokens im_start={P.im_start} im_end={P.im_end}, Stop={sorted(P.stop)}")
    t = "Grüezi «Frist» bis spätestens 08.10.2026 – Art. 21 Abs. 2 BöB"
    rt = P.decode(P.encode(t)); print(f"[{'OK' if rt == t else 'ABW.'}] Tokenizer hin/zurueck: {rt!r}")
    label = {i: l for i, l, _ in discover(MODELS)}.get(bid, "") + " " + bid
    off = "qwen3" in label.lower() and "instruct" not in label.lower()
    t0 = time.perf_counter()
    txt, st = llmio.generate(be, "Antworte kurz auf Deutsch.", "Was ist Bern? Ein Satz.", 40, think_off=off)
    print(f"[OK] Freitext ({time.perf_counter() - t0:.0f} s, {st['out']} Tokens): {txt!r}")
    t0 = time.perf_counter()
    res, st = llmio.structured(be, "Du extrahierst Angaben.",
                               "Text: Die Firma Muster AG liefert bis spätestens 12.11.2026 zwei Server für CHF 48'000.\n\n"
                               "Antworte als JSON mit den Feldern anbieter, frist, betrag.",
                               [{"name": "anbieter", "max_tokens": 20}, {"name": "frist", "max_tokens": 20},
                                {"name": "betrag", "max_tokens": 20}], think_off=off)
    print(f"[OK] JSON-Zwang ({time.perf_counter() - t0:.0f} s): {json.dumps(res, ensure_ascii=False)}")
    print(f"     Einlesen {st['in']} Tokens in {st['prefill_s']:.1f} s, {st['out']} Tokens geschrieben in {st['gen_s']:.1f} s")
    print("Ergebnis: Schnittstelle funktioniert." if all(res.values()) else "Ergebnis: PRUEFEN (leere Felder).")

def wissen_status(w):
    names = w.names()
    if not names: print(f"Keine Sammlung. Ordner anlegen: {WISSEN_DIR}\\<name>\\ und Dokumente hineinlegen."); return
    st = w.prepare(names)
    for n, x in st.items():
        print(f"\n== {n}: {x['name']} ==" + (f"  ({x['beschreibung']})" if x["beschreibung"] else ""))
        for d in x["dokumente"]: print(f"   {d['kurz']:<22} Stand {d['stand'][:10]}  {'Artikel' if d.get('art') == 'recht' else 'Text':<7} {d['stuecke']:>4} Stuecke, {d['vektoren']:>4} Vektoren  {d['titel']}")
        for m in x["fehlend"]: print(f"   [FEHLT] Pflichtdokument {m}")
        for v in x["veraltet"]: print(f"   [ALT]   {v}")
        if x.get("fehler"): print(f"   [FEHLER] {x['fehler']}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow", nargs="?"); ap.add_argument("--check", action="store_true")
    ap.add_argument("--list", action="store_true"); ap.add_argument("--llm")
    ap.add_argument("--file", action="append", default=[]); ap.add_argument("--text", default="")
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--wissen", action="store_true"); ap.add_argument("--wissen-suche", nargs=2)
    ap.add_argument("--pin", action="append", default=[]); ap.add_argument("--wissen-diag"); ap.add_argument("--vorlage-felder")
    ap.add_argument("--ab"); ap.add_argument("--zustand")
    ap.add_argument("--umziehen"); ap.add_argument("--sammlung")
    a = ap.parse_args(); s = load_settings(); bid = a.llm or s.get("llm")
    try:
        if a.check: return check(bid)
        if a.wissen: return wissen_status(Wissen(get_embedder, progress))
        if a.umziehen:
            from aura.workflow.paket import migrate
            migrate(a.umziehen, sammlung=a.sammlung, wissen=Wissen(get_embedder, progress), progress=progress); return
        if a.vorlage_felder:                                         # Felder einer Word-Vorlage + Geruest fuer die Zuordnung
            from aura.workflow.docx_fill import analyze
            fs = analyze(a.vorlage_felder); out = Path(a.vorlage_felder).with_suffix(".felder.json")
            for f in fs:
                print(f"{f['nr']:>4} {f['typ']:<17} {f['key']}" + (f"   [{' | '.join(f['optionen'])}]" if f["optionen"] else ""))
            out.write_text(json.dumps({f["key"]: "" for f in fs}, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"\n{len(fs)} Felder. Geruest fuer 'felder' im Workflow: {out}")
            return
        if a.wissen_diag:                                            # Gliederung eines Dokuments pruefen
            from aura.workflow.nodes import read_file
            from aura.wissen import SEC, legal_chunks
            t = read_file(a.wissen_diag); ms = list(SEC.finditer(t))
            print(f"{len(t)} Zeichen, {len(ms)} Zeilen mit Art./Anhang. Erste 12:")
            for m in ms[:12]: print("   ", repr(t[m.start():m.end() + 30]))
            ch = legal_chunks(t, "X", "", strict=True)
            print(f"Ergebnis: {'nach Artikeln, ' + str(len(ch)) + ' Stuecke' if ch else 'KEINE Artikelstruktur erkannt'}")
            if ch: print("   Abschnitte:", ", ".join(sorted({c[3:c.find(']')] for c in ch}, key=lambda x: (len(x), x))[:40]))
            return
        if a.wissen_suche:
            w = Wissen(get_embedder, progress); w.prepare([a.wissen_suche[0]])
            for h in w.search(a.wissen_suche[1], 4, [a.wissen_suche[0]], a.pin):
                print(f"\n{'[PFLICHT] ' if h.get('pinned') else ''}{h['text'][:400]}")
            return
        if a.list or not a.workflow:
            for w in list_workflows(WF_DIR):
                print(f"{Path(w['path']).name:40} {w['name']}" + (f"\n   FEHLER: {w['error']}" if w["error"] else ""))
            return
        wf = load_workflow(a.workflow); inputs = {}
        for i in wf["inputs"]:
            if i["type"] == "files":
                files = list(a.file)
                if not files and not a.ab:                            # keine Datei angegeben -> Auswahlfenster
                    import tkinter as tk
                    from tkinter import filedialog
                    r = tk.Tk(); r.withdraw()
                    files = list(filedialog.askopenfilenames(title=i.get("label", "Dateien waehlen"),
                                 filetypes=[("Dokumente", " ".join("*" + e for e in i.get("ext", [".pdf", ".docx"]))), ("Alle", "*.*")]))
                    r.destroy()
                    for f in files: print(f"   Datei: {f}")
                inputs[i["id"]] = [str(Path(f).resolve()) for f in files]
            elif i["type"] == "text": inputs[i["id"]] = a.text
        for kv in a.set: k, _, v = kv.partition("="); inputs[k] = v
        if a.llm: s["llm"] = a.llm
        conn = db.connect()
        ctx = make_ctx(conn, s, get_llm, get_embedder, Retriever(), progress, lambda: False,
                       on_text=lambda t: print(t, end="", flush=True), wissen=Wissen(get_embedder, progress))
        res = Runner(wf, inputs if not a.ab else {k: v for k, v in inputs.items() if v and k in [x.split("=")[0] for x in a.set]},
                     ctx, on_step=lambda i, n, sid, st: print(f"-- [{i + 1}/{n}] {sid}: {st}"),
                     start_at=a.ab, state_file=a.zustand).execute()
        print(f"\nStatus: {res['status']} ({res['seconds']} s)" + (f"\nFehler: {res['error']}" if res["error"] else ""))
        for f in res["files"]: print(f"Datei: {f}")
        print(f"Protokoll: {res.get('run_log')}")
        if res["status"] == "fehler":
            done = [l["id"] for l in res["log"] if "id" in l and ("seconds" in l or l.get("aus_zwischenstand"))]
            nxt = next((x["id"] for x in wf["steps"] if x["id"] not in done), None)
            if done and nxt: print(f"Nach der Korrektur ohne neuen Modell-Lauf weiter:  py tools\\wf_run.py {a.workflow} --ab {nxt}")
    except Exception:
        traceback.print_exc()
    finally:
        input("\nEnter zum Schliessen...")

if __name__ == "__main__":
    main()
