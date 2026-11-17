# aura/connectors/memos.py — Version 20261117v266
# Gesprochene Memos (Knopf «📝 Memo» oben) liegen je Tag in einer Markdown-Datei in einem eigenen Ordner und werden wie
# Dokumente eingelesen. Ordner: Einstellung «memo_folder», sonst Dokumente\AURA-Memos des Benutzers.
# Verwaltung (Liste, Bearbeiten, Löschen): Werkzeuge › Memos (memos_gui.py).
import ctypes, re
from datetime import datetime
from pathlib import Path
from .folder_docs import FolderDocs

ORDNERNAME = "AURA-Memos"

def _dokumente():
    """Windows-Ordner «Dokumente» (auch wenn umgeleitet), sonst ~/Documents."""
    try:
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value: return Path(buf.value)
    except Exception: pass
    return Path.home() / "Documents"

def ordner(settings):
    p = (settings or {}).get("memo_folder") or ""
    return Path(p) if p else _dokumente() / ORDNERNAME

def tagesdatei(settings, wann):
    return ordner(settings) / f"{wann:%Y-%m-%d}_Memos.md"

def speichern(settings, titel, text, wann=None):
    """v266: Alle Memos eines Tages in einer Datei JJJJ-MM-TT_Memos.md, je Memo ein Abschnitt «## HH:MM · Thema».
    Neue Memos werden angehängt; nichts wird überschrieben. Rückgabe: Pfad der Tagesdatei."""
    wann = wann or datetime.now(); d = ordner(settings); d.mkdir(parents=True, exist_ok=True)
    p = tagesdatei(settings, wann)
    alt = p.read_text(encoding="utf-8", errors="replace").rstrip() + "\n\n" if p.exists() else f"# Memos vom {wann:%d.%m.%Y}\n\n"
    titel = " ".join((titel or "").split()) or "Memo"
    inhalt = alt + f"## {wann:%H:%M} · {titel}\n\n{text.strip()}\n"
    tmp = p.with_suffix(".tmp"); tmp.write_text(inhalt, encoding="utf-8"); tmp.replace(p)
    return p

def liste(settings):
    """Memo-Dateien im Ordner (ohne Unterordner wie _geloescht), neueste zuerst."""
    d = ordner(settings)
    if not d.is_dir(): return []
    return sorted((p for p in d.glob("*.md") if p.is_file()), key=lambda p: (p.name[:10], p.stat().st_mtime), reverse=True)

def lesen(p):
    return Path(p).read_text(encoding="utf-8", errors="replace")

def anzahl(text):
    """Anzahl Memos (Abschnitte «## ») in einer Tagesdatei; alte Einzeldateien zählen als 1."""
    return max(1, len(re.findall(r"^## ", text, re.M)))

def aendern(p, inhalt):
    """Speichert den bearbeiteten Inhalt der Tagesdatei."""
    p = Path(p); tmp = p.with_suffix(".tmp"); tmp.write_text(inhalt.rstrip() + "\n", encoding="utf-8"); tmp.replace(p)
    return p

def loeschen(p):
    """Verschiebt die Datei nach _geloescht (Endung .geloescht – wird nicht mehr eingelesen). Rückgängig: Datei zurückholen und umbenennen."""
    p = Path(p); d = p.parent / "_geloescht"; d.mkdir(exist_ok=True)
    ziel = d / f"{p.name}.geloescht"; k = 2
    while ziel.exists(): ziel = d / f"{p.name}.{k}.geloescht"; k += 1
    p.replace(ziel); return ziel

class Memos(FolderDocs):
    id, label = "memos", "Memos"
    hint = "Gesprochene Memos (Knopf «Memo» im Chat) als Markdown-Dateien."

    def sync(self, ctx):
        d = ordner(ctx.settings)
        if not d.is_dir(): ctx.progress("Noch keine Memos"); ctx.seen = set(); ctx.complete = False; return
        s = dict(ctx.settings); s["docs_folder"] = str(d)
        orig = ctx.settings; ctx.settings = s
        try:
            for it in super().sync(ctx):
                it["meta"]["memo"] = True; yield it
        finally: ctx.settings = orig
        if not ctx.cancelled(): ctx.complete = True                   # auch leerer Ordner -> gelöschte Memos aus AURA entfernen
