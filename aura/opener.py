# aura/opener.py — Original oeffnen (Mail/Termin in Outlook, Webseite im Browser, Dokument mit Standardprogramm).
# Laeuft in einem eigenen kurzen Thread mit eigener COM-Initialisierung: so muss ein Klick nicht warten,
# bis eine laufende Vektorberechnung im Worker fertig ist. Outlook serialisiert die Aufrufe selbst.
import json, os, sqlite3, threading, webbrowser
from datetime import datetime
from .config import DB_PATH
from . import log

def _lookup(item_id):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    try:
        r = conn.execute("SELECT source, ext_id, meta FROM items WHERE id = ?", (int(item_id),)).fetchone()
    finally:
        conn.close()
    if not r: raise RuntimeError(f"Objekt {item_id} nicht in der Datenbank")
    try: meta = json.loads(r[2] or "{}")
    except Exception: meta = {}
    return r[0], r[1], meta

def _outlook():
    import comtypes; comtypes.CoInitialize()
    from .connectors.base import outlook_namespace
    return outlook_namespace()

def _open_mail(ext_id, meta):
    _outlook().GetItemFromID(ext_id).Display(False)

def _open_event(ext_id, meta):
    eid, _, start = ext_id.partition("|")
    it = _outlook().GetItemFromID(eid)
    if start and getattr(it, "IsRecurring", False):          # Serie: das konkrete Vorkommen oeffnen
        try:
            occ = it.GetRecurrencePattern().GetOccurrence(datetime.fromisoformat(start.strip().replace("T", " ")))
            occ.Display(False); return
        except Exception:
            pass                                             # Fallback: ganze Serie
    it.Display(False)

def _open_web(ext_id, meta):
    url = meta.get("url") or ext_id
    if not str(url).lower().startswith(("http://", "https://")): raise RuntimeError(f"Keine Web-Adresse: {url[:80]}")
    webbrowser.open(url)

def _open_doc(ext_id, meta):
    p = meta.get("path") or ext_id
    if not os.path.exists(p): raise RuntimeError(f"Datei nicht gefunden: {p}")
    os.startfile(p)

HANDLERS = {"outlook_mail": _open_mail, "outlook_calendar": _open_event,
            "edge_history": _open_web, "folder_docs": _open_doc, "confluence": _open_web}

def open_item(item_id, report):
    """report(text) meldet Erfolg/Fehler an die Oberflaeche (thread-sicher ueber die Event-Queue)."""
    def run():
        try:
            src, ext, meta = _lookup(item_id)
            h = HANDLERS.get(src)
            if not h: raise RuntimeError(f"Oeffnen fuer Quelle {src} nicht unterstuetzt")
            h(ext, meta); report("Original geoeffnet")
        except Exception as e:
            log.get().exception(f"Original oeffnen fehlgeschlagen (item {item_id})")
            report(f"Oeffnen fehlgeschlagen: {type(e).__name__}: {e}")
    threading.Thread(target=run, daemon=True).start()
