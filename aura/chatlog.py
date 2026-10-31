# aura/chatlog.py — gespeicherte Chats (v129). Version 20261029v129
# Eigene Datei data\chats.db (nicht aura.db): wird nur vom Oberflaechen-Thread benutzt, braucht den Worker nicht.
# Einstellungen: chats_behalten (Standard an), chats_tage (Standard 30). Aeltere Chats loescht purge() beim Start.
# Gespeichert werden nur Frage, Antworttext und Quellenangaben (Titel, Datum, Quelle, item_id) – keine Textstuecke.
import json, sqlite3, time
from .config import ROOT

PATH = ROOT / "data" / "chats.db"
_conn = None

def _db():
    global _conn
    if _conn is None:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(PATH))
        _conn.executescript("""
          CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY, t0 REAL, t1 REAL, titel TEXT);
          CREATE TABLE IF NOT EXISTS msgs(id INTEGER PRIMARY KEY, chat_id INTEGER, t REAL, frage TEXT, antwort TEXT, quellen TEXT);
          CREATE INDEX IF NOT EXISTS msgs_chat ON msgs(chat_id);""")
    return _conn

def purge(days):
    """Chats, deren letzte Nachricht aelter als days Tage ist, endgueltig loeschen. Liefert die Anzahl."""
    c = _db(); lim = time.time() - float(days) * 86400
    ids = [r[0] for r in c.execute("SELECT id FROM chats WHERE t1 < ?", (lim,))]
    for i in ids: c.execute("DELETE FROM msgs WHERE chat_id = ?", (i,))
    c.execute("DELETE FROM chats WHERE t1 < ?", (lim,)); c.commit()
    if ids: c.execute("VACUUM")                                       # geloeschter Inhalt nicht in der Datei liegen lassen
    return len(ids)

def _src(hits):
    out = []
    for h in hits or []:
        if not isinstance(h, dict): continue
        out.append({k: h.get(k) for k in ("item_id", "title", "ts", "source", "label", "path") if h.get(k) is not None})
    return out[:12]

def add(chat_id, frage, antwort, hits):
    """Frage + Antwort anhaengen; ohne chat_id wird ein neuer Chat angelegt. Liefert die chat_id."""
    c = _db(); now = time.time()
    if not chat_id or not c.execute("SELECT 1 FROM chats WHERE id = ?", (chat_id,)).fetchone():
        chat_id = c.execute("INSERT INTO chats(t0, t1, titel) VALUES(?, ?, ?)", (now, now, frage.strip()[:80])).lastrowid
    c.execute("INSERT INTO msgs(chat_id, t, frage, antwort, quellen) VALUES(?, ?, ?, ?, ?)",
              (chat_id, now, frage, antwort, json.dumps(_src(hits), ensure_ascii=False, default=str)))
    c.execute("UPDATE chats SET t1 = ? WHERE id = ?", (now, chat_id)); c.commit()
    return chat_id

def liste(n=200):
    return [{"id": i, "t0": a, "t1": b, "titel": t, "n": k} for i, a, b, t, k in _db().execute(
        "SELECT c.id, c.t0, c.t1, c.titel, (SELECT COUNT(*) FROM msgs m WHERE m.chat_id = c.id) "
        "FROM chats c ORDER BY c.t1 DESC LIMIT ?", (n,))]

def nachrichten(chat_id):
    return [{"t": t, "frage": f, "antwort": a, "quellen": json.loads(q or "[]")} for t, f, a, q in _db().execute(
        "SELECT t, frage, antwort, quellen FROM msgs WHERE chat_id = ? ORDER BY id", (chat_id,))]

def loeschen(chat_id=None):
    """Einen Chat (chat_id) oder alle (None) loeschen."""
    c = _db()
    if chat_id is None: c.execute("DELETE FROM msgs"); c.execute("DELETE FROM chats")
    else: c.execute("DELETE FROM msgs WHERE chat_id = ?", (chat_id,)); c.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    c.commit(); c.execute("VACUUM")
