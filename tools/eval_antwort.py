# tools/eval_antwort.py — Version 20261123v298 (AURA) · v298: --set schluessel=wert (nur für die Messung, z.B. llm_top_k=3); v297: Kopfzeile der Zusammenfassung sauber abgeschnitten; v296: Live-Quellen (Acta Nova, Intranet, SharePoint) für die Messung aus, Warnung bei Live-Antwort; v295: Datum auch als JJJJ-MM-TT/JJJJ/MM/TT; v294: Agent für die Messung aus (Schalter --agent zum Gegentest)
# Misst den ganzen Chat-Weg MIT Sprachmodell: stehen die Pflichtbegriffe in der Antwort, und wie lange dauert es?
# Grundlage: eval\fragen_v2.txt (wie tools\eval_suche.py), Ablauf wie tools\modell_vergleich.py.
# Aufruf: AURA schliessen, Netzbetrieb, cd /d C:\aura, dann
#   python -u tools\eval_antwort.py                         beide Standardmodelle, alle Fragen
#   python -u tools\eval_antwort.py --n 3                   Probelauf mit 3 Fragen
#   python -u tools\eval_antwort.py --modelle hf:Qwen3.5-9B nur ein Modell
# Ergebnis (nach jeder Frage gespeichert): eval\antwort_JJJJMMTT_HHMM.txt (Übersicht) und .csv (je Frage, mit Antworttext)
import argparse, csv, ctypes, queue, re, sys, time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(1, str(ROOT / "vendor")); sys.path.insert(2, str(ROOT / "tools"))
from aura import db                                            # noqa: E402
from aura.config import EVAL, load_settings                    # noqa: E402
from aura import worker as worker_mod                          # noqa: E402
from aura.worker import Worker                                 # noqa: E402
from eval_suche import lies_fragen, pflicht_ok, passt, norm    # noqa: E402

sys.excepthook = sys.__excepthook__                            # AURA-Log leitet Fehler sonst in die Logdatei um
STANDARD = ["hf:Qwen3.5-4B", "hf:Qwen3.5-9B"]
MON = ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "dezember"]
NICHT = re.compile(r"nicht (enthalten|erwähnt|ersichtlich|angegeben|genannt|beschrieben|vermerkt|zu finden|aufgeführt|bekannt)"
                   r"|keine (angabe|information|begründung|hinweise?)|geht (daraus )?nicht hervor|steht nicht|lässt sich nicht", re.I)


def wach(an):
    try: ctypes.windll.kernel32.SetThreadExecutionState(0x80000001 if an else 0x80000000)
    except Exception: pass


def antwort_pflicht(pflicht, text):
    """Pflichtbegriffe in der Antwort. datum=JJJJ-MM-TT wird zu «7.10.2026 / 07.10. / 7. Oktober»."""
    if not pflicht or pflicht == "-": return None
    teile = []
    for t in [p.strip() for p in pflicht.split(";") if p.strip()]:
        if t.startswith("datum="):
            y, m, d = (int(x) for x in t[6:].split("-"))
            t = f"{y}-{m:02d}-{d:02d}/{y}/{m:02d}/{d:02d}/{d}.{m}.{y}/{d:02d}.{m:02d}.{y}/{d}.{m:02d}./{d:02d}.{m:02d}./{d}. {MON[m - 1]}/{d}.{m}."
        teile.append(t)
    return pflicht_ok(";".join(teile), [text], "")


def lauf(w, bid, fragen, res, schreiben):
    t0 = time.perf_counter(); w.job_load_llm(bid); print(f"{bid} geladen in {time.perf_counter() - t0:.0f} s")
    for n, f in enumerate(fragen, 1):
        while not w.events.empty(): w.events.get_nowait()
        erst = [None]; orig = w.events.put
        def put(ev, _o=orig):
            if ev[0] == "token" and erst[0] is None: erst[0] = time.perf_counter()
            _o(ev)
        w.events.put = put
        w.chat = None; t1 = time.perf_counter(); fehler = ""
        try: w.job_ask(f["frage"], bid, False)
        except Exception as e: fehler = f"FEHLER: {e}"
        finally: w.events.put = orig
        txt, quellen, modus = "", [], ""
        while True:
            try: kind, d = w.events.get_nowait()
            except queue.Empty: break
            if kind == "token": txt += d[0]
            elif kind == "sources": quellen = d[0]
            elif kind == "answer_start" and len(d) > 1: modus = str(d[1])
        dt = time.perf_counter() - t1; t_erst = (erst[0] - t1) if erst[0] else dt
        if "— Zusammenfassung" in txt:                            # v296: Live-Antwort – nur die Zusammenfassung des Modells bewerten
            print("  WARNUNG: Live-Quellen waren aktiv – bewertet wird nur die Zusammenfassung")
            txt = txt.split("— Zusammenfassung über alle Quellen —", 1)[-1].lstrip()   # v297: ganze Kopfzeile weg
        beleg = f["belege"][0][1]
        rang = next((r for r, h in enumerate(quellen, 1) if passt(beleg, h.get("title", ""))), None)
        if f["kat"] == "abstinenz": ok = bool(NICHT.search(txt))
        else: ok = antwort_pflicht(f["pflicht"], txt)
        res[bid][n] = {"s": round(dt, 1), "s_erstes": round(t_erst, 1), "zeichen": len(txt), "modus": modus,
                       "beleg": rang or "", "ok": "" if ok is None else ("ja" if ok else "nein"), "txt": (txt.strip() or fehler)}
        print(f"  [{n}/{len(fragen)}] {dt:5.0f} s (erstes Wort {t_erst:4.0f} s) {res[bid][n]['ok'] or '-':4} {f['frage'][:50]}")
        schreiben()
    w.job_unload_llm()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datei", default=str(EVAL / "fragen_v2.txt"))
    ap.add_argument("--modelle", nargs="+", default=STANDARD)
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--set", nargs="*", default=[], metavar="SCHLUESSEL=WERT",
                    help="Einstellungen nur für diese Messung überschreiben, z.B. --set llm_top_k=3")
    ap.add_argument("--live", action="store_true", help="Live-Quellen eingeschaltet lassen (Standard: aus)")
    ap.add_argument("--agent", action="store_true", help="Agent eingeschaltet lassen (Standard: aus, normaler Chat)")
    a = ap.parse_args()
    fragen = [f for f in lies_fragen(a.datei) if f["kat"] != "live"]
    if a.n: fragen = fragen[:a.n]
    if not a.agent:                                            # v294: gespeicherter Agent-Schalter gilt nicht für die Messung
        _orig = worker_mod.load_settings
        worker_mod.load_settings = lambda: {**_orig(), "agent": False}
    if not a.live:                                             # v296: gespeicherte Live-Schalter gelten nicht für die Messung
        _orig2 = worker_mod.load_settings
        worker_mod.load_settings = lambda: {**_orig2(), "actanova": False, "intranet": False, "sharepoint": False}
    extra = {}
    for kv in a.set:                                           # v298
        k, _, v = kv.partition("=")
        try: v = int(v)
        except ValueError:
            try: v = float(v)
            except ValueError: v = {"true": True, "false": False}.get(v.lower(), v)
        extra[k.strip()] = v
    if extra:
        _orig3 = worker_mod.load_settings
        worker_mod.load_settings = lambda: {**_orig3(), **extra}
    s = worker_mod.load_settings(); stempel = datetime.now().strftime("%Y%m%d_%H%M"); EVAL.mkdir(exist_ok=True)
    kopf = (f"Agent {'ein' if s.get('agent') else 'aus'}, Live-Quellen {'ein' if s.get('actanova') or s.get('intranet') or s.get('sharepoint') else 'aus'}, Antwortstufe {s.get('antwort_stufe')}, llm_top_k {s.get('llm_top_k')}, stueck_wahl {s.get('stueck_wahl')}, "
            f"je_thread {s.get('je_thread')}, graph_suche {s.get('graph_suche')}" + (f", gesetzt {extra}" if extra else ""))
    res = {m: {} for m in a.modelle}

    def schreiben():
        with open(EVAL / f"antwort_{stempel}.csv", "w", newline="", encoding="utf-8-sig") as fh:
            wr = csv.writer(fh, delimiter=";")
            wr.writerow(["nr", "kat", "frage", "erwartet", "pflicht"] + [f"{m} {x}" for m in a.modelle
                                                                         for x in ("ok", "s", "s_erstes", "beleg", "antwort")])
            for n, f in enumerate(fragen, 1):
                wr.writerow([n, f["kat"], f["frage"], f["antwort"], f["pflicht"]] +
                            [res[m].get(n, {}).get(x, "") for m in a.modelle for x in ("ok", "s", "s_erstes", "beleg", "txt")])
        out = [f"AURA Antwort-Messung {stempel} – {len(fragen)} Fragen · {kopf}", ""]
        for m in a.modelle:
            r = res[m]
            if not r: continue
            out.append(f"== {m} ==   Kategorie | geprüft | richtig | Ø s | Ø s bis erstes Wort | Ø Zeichen")
            for k in sorted({f["kat"] for f in fragen}) + ["GESAMT"]:
                ns = [n for n, f in enumerate(fragen, 1) if n in r and (k == "GESAMT" or f["kat"] == k)]
                if not ns: continue
                gp = [n for n in ns if r[n]["ok"]]
                out.append(f"   {k:12} | {len(gp):2} | {sum(1 for n in gp if r[n]['ok'] == 'ja'):2} | "
                           f"{sum(r[n]['s'] for n in ns) / len(ns):5.0f} | {sum(r[n]['s_erstes'] for n in ns) / len(ns):5.0f} | "
                           f"{sum(r[n]['zeichen'] for n in ns) // len(ns)}")
            out.append("")
        out.append("richtig = alle Pflichtbegriffe stehen in der Antwort (Abstinenz: Antwort sagt, dass es nicht drinsteht).")
        out.append("Grob: falsche Schreibweise in der Antwort zählt als falsch – Zweifelsfälle in der .csv nachlesen.")
        (EVAL / f"antwort_{stempel}.txt").write_text("\n".join(out), encoding="utf-8")

    w = Worker(); w.conn = db.connect(); wach(True)
    print(f"{len(fragen)} Fragen, Modelle {a.modelle} · {kopf}")
    try:
        for m in a.modelle: lauf(w, m, fragen, res, schreiben)
    finally: wach(False)
    print((EVAL / f"antwort_{stempel}.txt").read_text(encoding="utf-8"))
    print(f"\nGespeichert: eval\\antwort_{stempel}.txt / .csv")


if __name__ == "__main__": main()
