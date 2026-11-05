# tools/graph_diagnose.py — Version 20261104v191 (AURA). Zeigt, wo die Abfolge-Regel abbricht. Liest nur; gibt nur Anzahlen und Daten aus.
# Aufruf:  cd /d C:\aura  und  py tools\graph_diagnose.py Benito "Fritz Ofer"
import sqlite3, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
from aura import graph as G
print("graph.db vorhanden:", G.GRAPH_PATH.exists(), "| aktuell:", G.aktuell())
c = sqlite3.connect(G.GRAPH_PATH)
print("Knoten:", dict(c.execute("SELECT typ, count(*) FROM knoten GROUP BY typ").fetchall()))
print("Kanten:", dict(c.execute("SELECT art, count(*) FROM kanten GROUP BY art").fetchall()))
jetzt = time.strftime("%Y-%m-%d %H:%M")
for name in sys.argv[1:]:
    w = name.lower().split()
    pers = [r[0] for r in c.execute("SELECT id FROM knoten WHERE typ='person' AND " + " AND ".join("id LIKE ?" for _ in w), [f"%{x}%" for x in w])]
    print(f"\n{name}: {len(pers)} Personenknoten")
    for i, p in enumerate(pers[:8], 1):
        r = c.execute("""SELECT k.typ, k.ts FROM kanten e JOIN knoten k ON k.id = e.nach WHERE e.von=?
                         UNION SELECT k.typ, k.ts FROM kanten e JOIN knoten k ON k.id = e.von WHERE e.nach=?""", (p, p)).fetchall()
        m = sorted(x[1] for x in r if x[0] == G.MAIL and x[1] and x[1] <= jetzt)
        t = sorted(x[1] for x in r if x[0] == G.TERMIN and x[1])
        if m: print("  Nächste Termine nach der neuesten Mail:", [x for x in t if x > m[-1]][:4])
        print(f"  Person {i}: {len(m)} Mails (neueste {m[-3:]}), {len(t)} Termine (letzte {t[-3:]})")
