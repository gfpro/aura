# tools/antwort_test.py — Version 20261016v104 (AURA)  v104: Daten auch als 2026/12/01 und 2026-12-01
# Prueft die ANTWORTEN des Chats mit eigenen Testfragen (ganzer Weg: Filter, Suche, Sprachmodell – wie in AURA).
# Eingabe:  eval\fragen.txt   «Frage | Betreff der richtigen Mail | erwartete Antwort»
# Ausgabe:  tools\antwort_test.txt (lesbar) und tools\antwort_test.csv (Excel, Spalte «Urteil» zum Ausfuellen)
# Aufruf:   AURA schliessen, Netzbetrieb, dann  cd /d C:\aura  und  py tools\antwort_test.py  [erste N Fragen, z.B. 5]
# Modell:   das in AURA gewaehlte (Einstellung «llm»), mit denselben Einstellungen (8 Bit, KV fp16 ...).
import csv, queue, re, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(1, str(ROOT / "vendor"))
from aura import db
from aura.config import load_settings
from aura.worker import Worker

PRE = re.compile(r"^\s*((aw|wg|re|fw|fwd|antw|weiterl)\s*:\s*)+", re.I)
def norm(t): return re.sub(r"\s+", " ", PRE.sub("", (t or "").lower())).strip(" .")
def passt(soll, titel):
    a, b = norm(soll), norm(titel)
    return a == b or (len(a) >= 15 and (a in b or b in a))

MON = {"januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6, "juli": 7, "august": 8,
       "september": 9, "oktober": 10, "november": 11, "dezember": 12}
def daten(t):
    """Alle Tagesdaten als (Tag, Monat): «20. Oktober 2026», «20.10.2026», «20.10.»"""
    t = t.lower(); out = set()
    for d, m in re.findall(r"\b(\d{1,2})\.\s*(" + "|".join(MON) + r")\b", t): out.add((int(d), MON[m]))
    for d, m in re.findall(r"\b(\d{1,2})\.(\d{1,2})\.", t): out.add((int(d), int(m)))
    for m, d in re.findall(r"\b20\d\d[/-](\d{1,2})[/-](\d{1,2})\b", t): out.add((int(d), int(m)))   # v104
    return out

def auto(soll, ist):
    """Automatische Vorpruefung: ✓ / ✗ / – (nicht pruefbar). Nur Daten, Zahlen und ja/nein – den Rest beurteilt der Mensch."""
    if not soll: return "–"
    s, i = soll.lower().strip(), ist.lower()
    ds = daten(s)
    if ds: return "✓" if ds & daten(i) else "✗"
    zs = set(re.findall(r"\d{2,}", re.sub(r"(\d)'(\d)", r"\1\2", s)))
    if zs: return "✓" if zs <= set(re.findall(r"\d{2,}", re.sub(r"(\d)'(\d)", r"\1\2", i))) else "✗"
    if re.match(r"^(ja|nein)\b", s):
        jn = s.split()[0].strip(",.")
        andere = "nein" if jn == "ja" else "ja"
        return "✓" if re.search(rf"\b{jn}\b", i) and not re.match(rf"^\W*{andere}\b", i) else "✗"
    return "–"

def lesen(p):
    out = []
    for z in p.read_text(encoding="utf-8-sig").splitlines():
        t = [x.strip() for x in z.split("|")]
        if len(t) < 2 or not t[0] or t[0].lower() == "frage": continue
        out.append((t[0], t[1], t[2] if len(t) > 2 else ""))
    return out

def main():
    f = ROOT / "eval" / "fragen.txt"
    if not f.exists(): print(f"Fehlt: {f}"); return
    fragen = lesen(f)
    if len(sys.argv) > 1 and sys.argv[1].isdigit(): fragen = fragen[:int(sys.argv[1])]
    s = load_settings(); bid = s.get("llm")
    w = Worker(); w.conn = db.connect()                                 # Worker ohne Thread: job_ask direkt aufrufen
    print(f"{len(fragen)} Fragen · Modell {bid} · Sprachmodell wird geladen ...")
    t0 = time.perf_counter(); w.job_load_llm(bid); print(f"geladen in {time.perf_counter() - t0:.0f} s")
    rows = []
    for n, (q, soll_betreff, soll) in enumerate(fragen, 1):
        while not w.events.empty(): w.events.get_nowait()
        w.chat = None; t1 = time.perf_counter()
        try: w.job_ask(q, bid, False)
        except Exception as e: print(f"  [{n}] Fehler: {e}")
        txt, quellen, tm = "", [], {}
        while True:
            try: kind, d = w.events.get_nowait()
            except queue.Empty: break
            if kind == "token": txt += d[0]
            elif kind == "sources": quellen = d[0]; tm = d[1] if len(d) > 1 else {}
        dt = time.perf_counter() - t1
        rang = next((r for r, h in enumerate(quellen, 1) if passt(soll_betreff, h.get("title", ""))), None)
        a = auto(soll, txt)
        rows.append({"Nr": n, "Frage": q, "Erwartet": soll, "AURA": txt.strip(), "Mail beim Modell": f"ja ({rang})" if rang else "nein",
                     "Auto": a, "Urteil": "", "Sekunden": round(dt), "Quellen": " | ".join(h.get("title", "")[:60] for h in quellen)})
        print(f"  [{n}/{len(fragen)}] {dt:4.0f} s · Mail {'ja' if rang else 'NEIN'} · auto {a} · {q[:50]}")
    out = ROOT / "tools"
    with open(out / "antwort_test.csv", "w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";"); wr.writeheader(); wr.writerows(rows)
    mail = sum(r["Mail beim Modell"] != "nein" for r in rows); ok = sum(r["Auto"] == "✓" for r in rows)
    bad = sum(r["Auto"] == "✗" for r in rows); pr = ok + bad
    kopf = [f"Antwort-Test {time.strftime('%d.%m.%Y %H:%M')} · {len(rows)} Fragen · Modell {bid}",
            f"Richtige Mail beim Modell: {mail}/{len(rows)}",
            f"Automatisch prüfbar (Datum/Zahl/ja-nein): {pr} · davon richtig {ok}, falsch {bad}",
            f"Zeit je Frage: Ø {sum(r['Sekunden'] for r in rows) / len(rows):.0f} s",
            "Fehlerart: «Mail nein» = Suche · «Mail ja + falsch» = Modell oder Prompt", ""]
    lines = []
    for r in rows:
        lines += [f"[{r['Nr']}] {r['Frage']}", f"    erwartet: {r['Erwartet']}", f"    AURA:     {r['AURA']}",
                  f"    Mail beim Modell: {r['Mail beim Modell']} · auto {r['Auto']} · {r['Sekunden']} s", f"    Quellen: {r['Quellen']}", ""]
    (out / "antwort_test.txt").write_text("\n".join(kopf + lines), encoding="utf-8")
    print("\n" + "\n".join(kopf)); print(f"Details: {out / 'antwort_test.txt'}  ·  Excel: {out / 'antwort_test.csv'}")
    w.job_unload_llm()

if __name__ == "__main__": main()
