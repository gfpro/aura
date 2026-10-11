# aura/connectors/folder_docs.py — Dokumente aus einem Ordner (wie tiseR): txt, md, docx, pdf (pdf nur mit pypdf).
import re, zipfile
from datetime import datetime
from pathlib import Path
from .base import Connector
from ..text import clean

EXT = {".txt", ".md", ".docx", ".pdf"}

def read_text(p):
    s = p.suffix.lower()
    if s in (".txt", ".md"): return p.read_text(encoding="utf-8", errors="replace")
    if s == ".docx":
        xml = zipfile.ZipFile(p).read("word/document.xml").decode("utf-8", "replace")
        xml = re.sub(r"</w:p>", "\n\n", xml)
        return re.sub(r"<[^>]+>", "", xml)
    if s == ".pdf":
        from pypdf import PdfReader                    # optional: pypdf-Ordner in vendor\ ablegen
        return "\f".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages)
    return ""

class FolderDocs(Connector):
    id, label = "folder_docs", "Dokumentordner"
    hint = "Dateien aus einem Ordner (Einstellung: docs_folder)."

    def available(self):
        return True, ""                                # Ordner wird in der Oberflaeche gewaehlt

    def sync(self, ctx):
        root = Path(ctx.settings.get("docs_folder") or "")
        if not root.is_dir(): ctx.progress("Kein Dokumentordner gewaehlt"); return
        files = [p for p in root.rglob("*") if p.suffix.lower() in EXT]
        for k, p in enumerate(files):
            if ctx.cancelled(): return
            ext = f"{p}|{int(p.stat().st_mtime)}"        # geaenderte Datei = neue Version
            if ext in ctx.known: continue
            ctx.progress(f"Dokumente: {k}/{len(files)}", k, len(files))
            try: text = clean(read_text(p))
            except Exception as e: ctx.progress(f"{p.name} uebersprungen: {e}"); continue
            ts = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            yield {"ext_id": ext, "title": p.name, "ts": ts, "body": text, "text": text.replace("\f", "\n\n"),
                   "prefix": f"{p.stem}: ", "meta": {"path": str(p)}}
