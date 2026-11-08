# aura/connectors/folder_docs.py — Dokumente aus einem Ordner (wie tiseR): txt, md, docx, pdf (pdf nur mit pypdf).
import re, zipfile
from datetime import datetime
from pathlib import Path
from .base import Connector
from ..text import clean
from .. import sicherheit as SI

EXT = {".txt", ".md", ".docx", ".pdf"}

def read_text(p):
    """v208: Grössen-, Seiten- und Zeitgrenzen (aura/sicherheit.py)."""
    import time
    s = p.suffix.lower()
    if s in (".txt", ".md"): SI.pruefe_dokument(p); return p.read_text(encoding="utf-8", errors="replace")
    if s == ".docx":
        xml = SI.docx_xml(p)
        xml = re.sub(r"</w:p>", "\n\n", xml)
        return re.sub(r"<[^>]+>", "", xml)
    if s == ".pdf":
        from pypdf import PdfReader                    # optional: pypdf-Ordner in vendor\ ablegen
        SI.pruefe_dokument(p); r = PdfReader(str(p))
        if len(r.pages) > SI.DOC_MAX_SEITEN: raise SI.SicherheitsFehler(f"{p.name}: {len(r.pages)} Seiten – Grenze {SI.DOC_MAX_SEITEN}")
        out, t0 = [], time.monotonic()
        for pg in r.pages:
            if time.monotonic() - t0 > SI.DOC_MAX_SEKUNDEN: raise SI.SicherheitsFehler(f"{p.name}: Textextraktion dauert zu lange")
            out.append(pg.extract_text() or "")
        return "\f".join(out)
    return ""

def doc_meta(p):
    """v206: Dateityp, Erstellt am und Autor. Der Autor kommt aus docx bzw. pdf, sonst leer."""
    autor = ""
    try:
        if p.suffix.lower() == ".docx":
            m = re.search(r"<dc:creator[^>]*>([^<]*)<", SI.docx_xml(p, "docProps/core.xml", 2**20))
            autor = m.group(1).strip() if m else ""
        elif p.suffix.lower() == ".pdf":
            from pypdf import PdfReader
            autor = str((PdfReader(str(p)).metadata or {}).get("/Author") or "").strip()
    except Exception: pass
    return {"autor": autor, "dateityp": p.suffix.lower().lstrip("."),
            "erstellt_am": datetime.fromtimestamp(p.stat().st_ctime).strftime("%Y-%m-%d %H:%M")}

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
            dm = doc_meta(p)                                  # v206
            yield {"ext_id": ext, "title": p.name, "author": dm["autor"], "ts": ts, "body": text, "text": text.replace("\f", "\n\n"),
                   "prefix": f"{p.stem}: ", "meta": {"path": str(p), **dm}}
