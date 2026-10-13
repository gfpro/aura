# aura/db.py — eine SQLite-Datenbank fuer alle Quellen. Version 20261012v73
# v73: chunks.zitat (1 = Stueck aus dem zitierten Mailverlauf), Tabellen para_hash und aura_flags.
# v60: WAL-Datei auf 64 MB begrenzt (journal_size_limit); «Alles zurücksetzen» löscht die Datenbank beim nächsten Start.
# items  = ein Objekt pro Mail/Termin/Webseite/Dokument;  chunks = Textstuecke mit Vektor (float32-BLOB)
import json, sqlite3, time
from datetime import datetime
from .config import DB_PATH, DATA, ensure_dirs

RESET_FLAG = DATA / "reset.flag"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
    id INTEGER PRIMARY KEY, source TEXT NOT NULL, ext_id TEXT NOT NULL,
    title TEXT, author TEXT, recipients TEXT, ts TEXT, location TEXT, body TEXT, meta TEXT, added TEXT,
    UNIQUE(source, ext_id));
CREATE TABLE IF NOT EXISTS chunks(
    id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    ord INTEGER NOT NULL, text TEXT NOT NULL, vec BLOB);
CREATE INDEX IF NOT EXISTS ix_chunks_item ON chunks(item_id);
CREATE INDEX IF NOT EXISTS ix_items_source ON items(source);
CREATE TABLE IF NOT EXISTS sync_state(source TEXT PRIMARY KEY, last_sync TEXT, info TEXT);
CREATE TABLE IF NOT EXISTS para_hash(h TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS aura_flags(k TEXT PRIMARY KEY, v TEXT);
"""

def connect(path=None):
    ensure_dirs()
    conn = sqlite3.connect(path or DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL"); conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_size_limit=67108864")              # v60: WAL nach dem Zurückschreiben auf 64 MB kürzen
    conn.executescript(SCHEMA)
    if "zitat" not in {r[1] for r in conn.execute("PRAGMA table_info(chunks)")}:          # v73
        conn.execute("ALTER TABLE chunks ADD COLUMN zitat INTEGER NOT NULL DEFAULT 0"); conn.commit()
    fresh = not conn.execute("SELECT 1 FROM sqlite_master WHERE name='chunks_fts'").fetchone()
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, content='chunks', content_rowid='id')")
    if fresh: rebuild_fts(conn)
    return conn

def rebuild_fts(conn):
    conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')"); conn.commit()

def known_ids(conn, source):
    return {r[0] for r in conn.execute("SELECT ext_id FROM items WHERE source=?", (source,))}

def add_item(conn, source, it, chunks, zitat=()):
    """Fuegt ein Objekt samt Textstuecken ein. Bereits vorhandene (source, ext_id) werden uebersprungen.
    v73: zitat = Stuecke aus dem zitierten Verlauf (hinter den eigenen, Markierung zitat = 1)."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO items(source, ext_id, title, author, recipients, ts, location, body, meta, added) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (source, it["ext_id"], it.get("title", ""), it.get("author", ""), it.get("recipients", ""),
         it.get("ts", ""), it.get("location", ""), it.get("body", ""), json.dumps(it.get("meta") or {}, ensure_ascii=False),
         datetime.now().isoformat(sep=" ", timespec="seconds")))
    if not cur.rowcount: return None
    iid = cur.lastrowid
    conn.executemany("INSERT INTO chunks(item_id, ord, text) VALUES(?,?,?)", [(iid, k, c) for k, c in enumerate(chunks)])
    if zitat: conn.executemany("INSERT INTO chunks(item_id, ord, text, zitat) VALUES(?,?,?,1)",
                               [(iid, len(chunks) + k, c) for k, c in enumerate(zitat)])
    return iid

def set_sync(conn, source, info):
    conn.execute("INSERT OR REPLACE INTO sync_state VALUES(?,?,?)",
                 (source, datetime.now().isoformat(sep=" ", timespec="minutes"), info)); conn.commit()

def stats(conn):
    """{source: {items, chunks, vectors, last_sync}}"""
    out = {}
    for src, n in conn.execute("SELECT source, COUNT(*) FROM items GROUP BY source"):
        out[src] = {"items": n, "chunks": 0, "vectors": 0, "last_sync": ""}
    for src, c, v in conn.execute("SELECT i.source, COUNT(c.id), COUNT(c.vec) FROM chunks c "
                                  "JOIN items i ON i.id = c.item_id GROUP BY i.source"):
        out.setdefault(src, {"items": 0, "last_sync": ""}).update(chunks=c, vectors=v)
    for src, ls in conn.execute("SELECT source, last_sync FROM sync_state"):
        out.setdefault(src, {"items": 0, "chunks": 0, "vectors": 0})["last_sync"] = ls
    return out

# ----------------------------------------------------------------------------- v60: Wartung
def checkpoint(conn):
    """Änderungen aus der WAL-Datei in die Datenbank schreiben und die WAL-Datei kürzen."""
    try: conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception: pass

def zuruecksetzen_vormerken():
    """Merkt «Alles zurücksetzen» vor; ausgeführt wird es beim nächsten Start, bevor jemand die Datenbank öffnet."""
    ensure_dirs(); RESET_FLAG.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")

def vor_start_zuruecksetzen():
    """Beim Start aufrufen, BEVOR der Worker die Datenbank öffnet. Rückgabe: None (nichts zu tun), True (erledigt)
    oder eine Fehlermeldung. Löscht aura.db (+ -wal, -shm) und den Vorspann-Cache. Wissen, Workflows, Modelle bleiben."""
    if not RESET_FLAG.exists(): return None
    ziele = [DB_PATH, DB_PATH.with_name(DB_PATH.name + "-wal"), DB_PATH.with_name(DB_PATH.name + "-shm")]
    ziele += list((DATA / "kvcache").glob("*.kv")) if (DATA / "kvcache").exists() else []
    rest = []
    for f in ziele:
        for _ in range(40):                                        # alte AURA-Instanz kann die Datei noch kurz halten
            try:
                if f.exists(): f.unlink()
                break
            except PermissionError: time.sleep(0.25)
        else: rest.append(f.name)
    if rest: return "Zurücksetzen unvollständig – noch gesperrt: " + ", ".join(rest) + ". AURA schliessen und erneut starten."
    try: RESET_FLAG.unlink()
    except Exception: pass
    return True

# ----------------------------------------------------------------------------- v73: Absatz-Pruefsummen, Merker
def hashes_known(conn, hs):
    hs = list(hs); out = set()
    for i in range(0, len(hs), 500):
        part = hs[i:i + 500]
        out |= {r[0] for r in conn.execute(f"SELECT h FROM para_hash WHERE h IN ({','.join('?' * len(part))})", part)}
    return out

def hashes_add(conn, hs):
    if hs: conn.executemany("INSERT OR IGNORE INTO para_hash(h) VALUES(?)", [(h,) for h in hs])

def flag(conn, k, v=None):
    if v is None:
        r = conn.execute("SELECT v FROM aura_flags WHERE k = ?", (k,)).fetchone(); return r[0] if r else None
    conn.execute("INSERT OR REPLACE INTO aura_flags VALUES(?, ?)", (k, str(v))); conn.commit()
