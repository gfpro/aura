# tools/check_kalender.py — Prueft, was vom Outlook-Kalender in der AURA-Datenbank liegt.
# Aufruf:  py tools\check_kalender.py TRILA      (Suchbegriff optional; AURA darf offen sein, nur lesen)
import sqlite3, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "vendor")]
from aura.config import DB_PATH

c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
now = datetime.now().strftime("%Y-%m-%d %H:%M")
n, lo, hi = c.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM items WHERE source='outlook_calendar'").fetchone()
fut = c.execute("SELECT COUNT(*) FROM items WHERE source='outlook_calendar' AND ts >= ?", (now,)).fetchone()[0]
ls = c.execute("SELECT last_sync, info FROM sync_state WHERE source='outlook_calendar'").fetchone()
print(f"Termine gesamt: {n}   davon ab jetzt: {fut}")
print(f"Zeitraum:       {lo}  bis  {hi}")
print(f"Letzter Sync:   {ls[0] if ls else '-'}   ({ls[1] if ls else ''})")
print("\nTermine pro Monat:")
for m, k in c.execute("SELECT substr(ts,1,7), COUNT(*) FROM items WHERE source='outlook_calendar' GROUP BY 1 ORDER BY 1"):
    print(f"  {m}  {k:>4}  {'#' * min(k // 2, 60)}")
if len(sys.argv) > 1:
    q = sys.argv[1]
    rows = c.execute("SELECT ts, title FROM items WHERE source='outlook_calendar' AND title LIKE ? ORDER BY ts",
                     (f"%{q}%",)).fetchall()
    print(f"\nTermine mit «{q}» im Titel: {len(rows)}")
    for ts, t in rows: print(f"  {'>' if ts >= now else ' '} {ts[:16]}  {t[:60]}")
    print("  (> = noch nicht vorbei)")
input("\nEnter zum Schliessen...")
