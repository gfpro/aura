# tools/modell_vergleich.py — Version 20261103v167 (AURA)
# Vergleicht zwei Sprachmodelle mit eval\fragen.txt, ganzer Chat-Weg wie tools\antwort_test.py.
# Aufruf: AURA schliessen, Netzbetrieb, cd /d C:\aura, dann
#   py tools\modell_vergleich.py [Anzahl Fragen]              z.B. 3 fuer einen Probelauf
# Ausgabe (nach jeder Frage gespeichert, ein Abbruch verliert nichts):
#   tools\vergleich_blind.csv     Antworten A/B in zufaelliger Reihenfolge, Spalte Urteil A/B zum Ausfuellen
#   tools\vergleich_schluessel.csv  welches Modell A/B ist, Zeiten, Mail beim Modell, Auto-Pruefung (erst nach dem Bewerten oeffnen)
import csv, ctypes, queue, random, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(1, str(ROOT / "vendor")); sys.path.insert(2, str(ROOT / "tools"))
from aura import db
from aura.worker import Worker
from antwort_test import auto, lesen, passt

MODELLE = ["hf:Qwen3.5-9B", "hf:Apertus1.5-8B"]

def wach(an):
    try: ctypes.windll.kernel32.SetThreadExecutionState(0x80000001 if an else 0x80000000)   # kein Standby waehrend des Laufs
    except Exception: pass

def fragen_lauf(w, bid, fragen, res):
    t0 = time.perf_counter(); w.job_load_llm(bid); print(f"{bid} geladen in {time.perf_counter() - t0:.0f} s")
    for n, (q, soll_betreff, soll) in enumerate(fragen, 1):
        while not w.events.empty(): w.events.get_nowait()
        w.chat = None; t1 = time.perf_counter(); fehler = ""
        try: w.job_ask(q, bid, False)
        except Exception as e: fehler = f"FEHLER: {e}"
        txt, quellen = "", []
        while True:
            try: kind, d = w.events.get_nowait()
            except queue.Empty: break
            if kind == "token": txt += d[0]
            elif kind == "sources": quellen = d[0]
        dt = time.perf_counter() - t1
        rang = next((r for r, h in enumerate(quellen, 1) if passt(soll_betreff, h.get("title", ""))), None)
        res[bid][n] = dict(txt=(txt.strip() or fehler), s=round(dt), mail=f"ja ({rang})" if rang else "nein", auto=auto(soll, txt))
        print(f"  [{n}/{len(fragen)}] {dt:4.0f} s · {q[:55]}")
        schreiben(fragen, res)
    w.job_unload_llm()

KARTE = {}
def schreiben(fragen, res):
    a, b = MODELLE
    with open(ROOT / "tools" / "vergleich_blind.csv", "w", encoding="utf-8-sig", newline="") as fb, \
         open(ROOT / "tools" / "vergleich_schluessel.csv", "w", encoding="utf-8-sig", newline="") as fk:
        wb = csv.writer(fb, delimiter=";"); wk = csv.writer(fk, delimiter=";")
        wb.writerow(["Nr", "Frage", "Erwartet", "Antwort A", "Antwort B", "Urteil A", "Urteil B", "Bemerkung"])
        wk.writerow(["Nr", "A ist", "B ist", f"Sek {a}", f"Sek {b}", f"Mail {a}", f"Mail {b}", f"Auto {a}", f"Auto {b}"])
        for n, (q, _, soll) in enumerate(fragen, 1):
            x, y = KARTE[n]; rx, ry = res[x].get(n), res[y].get(n); ra, rb = res[a].get(n, {}), res[b].get(n, {})
            wb.writerow([n, q, soll, (rx or {}).get("txt", ""), (ry or {}).get("txt", ""), "", "", ""])
            wk.writerow([n, x, y, ra.get("s", ""), rb.get("s", ""), ra.get("mail", ""), rb.get("mail", ""), ra.get("auto", ""), rb.get("auto", "")])

def main():
    fragen = lesen(ROOT / "eval" / "fragen.txt")
    if len(sys.argv) > 1 and sys.argv[1].isdigit(): fragen = fragen[:int(sys.argv[1])]
    rnd = random.SystemRandom()
    for n in range(1, len(fragen) + 1): KARTE[n] = rnd.sample(MODELLE, 2)
    res = {m: {} for m in MODELLE}
    w = Worker(); w.conn = db.connect(); wach(True)
    try:
        for m in MODELLE: fragen_lauf(w, m, fragen, res)
    finally: wach(False)
    print(f"Fertig. Bewerten: {ROOT / 'tools' / 'vergleich_blind.csv'}  ·  danach erst vergleich_schluessel.csv oeffnen")

if __name__ == "__main__": main()
