# tools/metadaten_nachtrag.py — Version 20261105v206 (AURA). Ergänzt bestehende Mails und Termine um To/CC und Adressen.
# Ändert nur items.meta, keine Texte und Vektoren. Abbrechen (Strg+C) und erneut starten ist jederzeit möglich.
# Aufruf: AURA schliessen, Outlook offen lassen, dann  cd /d C:\\aura  und  py tools\\metadaten_nachtrag.py
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "vendor")]
from aura import db
from urllib.parse import urlsplit
from aura.connectors.base import empfaenger, outlook_namespace
from aura.connectors import confluence as CF
from aura.connectors.folder_docs import doc_meta

def weitere(conn):
    """v206: Confluence (Erstellt von/am) und Dokumente (Autor, Dateityp, Erstellt am)."""
    tok = CF._token(); ok = weg = 0
    for iid, meta in conn.execute("SELECT id, meta FROM items WHERE source='confluence'").fetchall():
        m = json.loads(meta or "{}")
        if "erstellt_von" in m: continue
        try:
            u = urlsplit(m["url"]); r = CF._get(f"{u.scheme}://{u.netloc}/rest/api/content/{m['page_id']}?expand=history", tok)
            m.update(CF.ersteller(r)); ok += 1
            conn.execute("UPDATE items SET meta=? WHERE id=?", (json.dumps(m, ensure_ascii=False), iid))
        except Exception: weg += 1
    conn.commit(); print(f"Confluence: ergänzt {ok}, übersprungen {weg}")
    ok = weg = 0
    for iid, meta in conn.execute("SELECT id, meta FROM items WHERE source='folder_docs'").fetchall():
        m = json.loads(meta or "{}")
        if "dateityp" in m: continue
        try:
            d = doc_meta(Path(m["path"])); m.update(d); ok += 1
            conn.execute("UPDATE items SET meta=?, author=? WHERE id=?", (json.dumps(m, ensure_ascii=False), d["autor"], iid))
        except Exception: weg += 1
    conn.commit(); print(f"Dokumente: ergänzt {ok}, übersprungen {weg}")

def main():
    conn = db.connect(); ns = outlook_namespace()
    rows = [r for r in conn.execute("SELECT id, ext_id, meta FROM items WHERE source IN ('outlook_mail', 'outlook_calendar')")
            if '"to"' not in (r[2] or "")]
    print(f"{len(rows)} Objekte offen"); t0 = time.perf_counter(); ok = weg = 0
    try:
        for n, (iid, ext, meta) in enumerate(rows, 1):
            try:
                emp = empfaenger(ns.GetItemFromID(ext.partition("|")[0]))
                m = json.loads(meta or "{}"); m["to"], m["cc"] = emp[1], emp[2]
                conn.execute("UPDATE items SET meta=? WHERE id=?", (json.dumps(m, ensure_ascii=False), iid)); ok += 1
            except Exception: weg += 1                              # z.B. nur noch auf dem Server
            if n % 100 == 0:
                conn.commit(); d = time.perf_counter() - t0
                print(f"  {n}/{len(rows)} · ergänzt {ok} · übersprungen {weg} · noch {d / n * (len(rows) - n) / 60:.0f} min", end="\r")
    finally:
        conn.commit()
    print(f"\nOutlook fertig: ergänzt {ok}, übersprungen {weg}, {(time.perf_counter() - t0) / 60:.1f} min")
    weitere(conn)

if __name__ == "__main__": main()
