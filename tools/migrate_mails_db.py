# tools/migrate_mails_db.py — uebernimmt Mails UND bereits berechnete Vektoren aus der alten mails.db
# (Prototyp mail_import.py / embed_mails.py) in data\aura.db.   Aufruf:  py tools\migrate_mails_db.py [pfad\mails.db]
import json, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
from aura import db

src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "mails.db"
old = sqlite3.connect(f"file:{src}?mode=ro", uri=True); new = db.connect()
known = db.known_ids(new, "outlook_mail"); n = v = 0
for (eid, folder, subj, sname, saddr, to, cc, rec, conv, body) in old.execute(
        "SELECT entry_id, folder, subject, sender_name, sender_addr, to_line, cc_line, received, conversation_id, body FROM mails"):
    if eid in known: continue
    cur = new.execute("INSERT INTO items(source, ext_id, title, author, recipients, ts, body, meta, added) "
                      "VALUES('outlook_mail',?,?,?,?,?,?,?,datetime('now'))",
                      (eid, subj, sname, "; ".join(x for x in (to, cc) if x), (rec or "")[:16], body,
                       json.dumps({"folder": folder, "sender_addr": saddr, "conversation_id": conv}, ensure_ascii=False)))
    iid = cur.lastrowid; n += 1
    for ordn, text, vec in old.execute("SELECT ord, text, vec FROM chunks WHERE source = ? ORDER BY ord", ("mail:" + eid,)):
        if isinstance(vec, str): vec = None            # sehr alte JSON-Vektoren nicht uebernehmen
        new.execute("INSERT INTO chunks(item_id, ord, text, vec) VALUES(?,?,?,?)", (iid, ordn, text, vec)); v += vec is not None
    if n % 500 == 0: new.commit(); print(f"  {n} Mails ...")
new.commit(); db.rebuild_fts(new)
print(f"Fertig: {n} Mails uebernommen, {v} Vektoren uebernommen.")
