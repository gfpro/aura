# tools/relevanz_test.py — Version 20261103v164 (AURA)
# Misst: Lohnt sich eine Ja/Nein-Prüfung pro Quelle vor der Antwort? Ändert nichts an AURA oder der Datenbank.
# Eingabe:  eval\fragen.txt   «Frage | Betreff der richtigen Mail | erwartete Antwort»
# Ausgabe:  tools\relevanz_test.txt
# Aufruf:   AURA schliessen, Netzbetrieb, dann  cd /d C:\aura  und  py tools\relevanz_test.py  [erste N Fragen] [Zeichen je Quelle]
import faulthandler, queue, sys, time
faulthandler.enable()                                                   # harte Abstuerze sichtbar machen
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(1, str(ROOT / "vendor")); sys.path.insert(2, str(ROOT / "tools"))
from antwort_test import lesen, passt
from aura import db
from aura.config import load_settings
from aura.worker import Worker
from aura.workflow import llmio

SYS = "Du prüfst, ob ein Textauszug zur Frage passt. Antworte nur mit ja oder nein."

def main():
    fragen = lesen(ROOT / "eval" / "fragen.txt")
    if len(sys.argv) > 1 and sys.argv[1].isdigit(): fragen = fragen[:int(sys.argv[1])]
    zeichen = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    s = load_settings(); bid = s.get("llm"); n_q = int(s.get("llm_top_k", 4))
    w = Worker(); w.conn = db.connect()                                 # nur Suche (extractive, eigener Worker)
    m = Worker(); m.conn = db.connect()                                 # nur Sprachmodell: _llm entlaedt sonst das Modell
    print(f"{len(fragen)} Fragen · Modell {bid} · {n_q} Quellen · {zeichen} Zeichen je Quelle · lade Modell ...")
    be = m._llm(bid); be.settings = s; print("Modell geladen", flush=True)
    zeilen = []; alle = behalten = richtig = verloren = 0; zeit = 0.0
    for n, (q, betreff, _) in enumerate(fragen, 1):
        while not w.events.empty(): w.events.get_nowait()
        w.chat = None; hits = []
        w.job_ask(q, "extractive", False)                               # nur Suche, kein Sprachmodell
        while True:
            try: kind, d = w.events.get_nowait()
            except queue.Empty: break
            if kind == "sources": hits = d[0]
        hits = hits[:n_q]; t0 = time.perf_counter(); ja = []
        for h in hits:
            user = f"Frage: {q}\nAuszug aus «{h.get('title', '')}»:\n{h.get('text', '')[:zeichen]}\nPasst der Auszug zur Frage?"
            out, _st = llmio.generate(be, SYS, user, max_new=3, temperature=0.0, penalty=1.0, think_off=True)
            ok = not out.strip().lower().startswith("nein"); ja.append(ok)
        dt = time.perf_counter() - t0; zeit += dt
        ist = [passt(betreff, h.get("title", "")) for h in hits]
        drin, weg = any(ist), any(i and j for i, j in zip(ist, ja))
        alle += len(hits); behalten += sum(ja); richtig += drin; verloren += drin and not weg
        z = f"[{n}] {dt:4.0f} s · {sum(ja)}/{len(hits)} behalten · richtige Quelle {'fehlt schon' if not drin else 'behalten' if weg else 'VERLOREN'} · {q[:60]}"
        print(z, flush=True); zeilen.append(z)
    fazit = (f"\nFazit: {behalten}/{alle} Quellen behalten · richtige Quelle in {richtig} Fragen vorhanden, davon {verloren} verloren · "
             f"Prüfung {zeit / max(1, len(fragen)):.0f} s je Frage")
    print(fazit); (ROOT / "tools" / "relevanz_test.txt").write_text("\n".join(zeilen) + "\n" + fazit, encoding="utf-8")

if __name__ == "__main__": main()
