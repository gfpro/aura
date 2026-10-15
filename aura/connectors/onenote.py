# aura/connectors/onenote.py — v87: OneNote (Desktop-Version) per COM, nur lesen.
# Auswahl je Abschnitt: settings["onenote_sections"] = {ID: true/false}. Notizbuecher/Abschnittsgruppen sind
# Knoten im Baum; neue Abschnitte erben die Wahl des Elternknotens. Standard: AUS (nichts ohne bewusste Wahl).
# Typbibliothek: in ONENOTE.EXE als Ressource 3, Registrierung nur 32 Bit -> direkt per LoadTypeLibEx laden.
# ext_id = "<SeitenID>|<lastModifiedTime>" -> geaenderte Seite = neues Objekt; ctx.seen -> Worker entfernt alte Versionen.
import html, re, winreg
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from .base import Connector
from ..text import clean

NS = "{http://schemas.microsoft.com/office/onenote/2013/onenote}"
TLB = "{0EA692EE-BB50-4E3C-AEF0-356D91732725}"
_MOD = None

def _tlb_path():
    k = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "TypeLib\\" + TLB)
    vers = []
    i = 0
    while True:
        try: vers.append(winreg.EnumKey(k, i)); i += 1
        except OSError: break
    for v in sorted(vers, reverse=True):
        for arch in ("win64", "win32"):
            try: return winreg.QueryValue(winreg.HKEY_CLASSES_ROOT, f"TypeLib\\{TLB}\\{v}\\0\\{arch}")
            except OSError: pass
    raise RuntimeError("OneNote-Typbibliothek nicht eingetragen (Desktop-OneNote installiert?)")

def app():
    """Verbindung zu OneNote. COM muss im aufrufenden Thread initialisiert sein."""
    global _MOD
    import comtypes, comtypes.client as cc
    from comtypes.typeinfo import LoadTypeLibEx
    try: comtypes.CoInitialize()
    except OSError: pass
    if _MOD is None: _MOD = cc.GetModule(LoadTypeLibEx(_tlb_path()))
    return cc.CreateObject("OneNote.Application", interface=_MOD.IApplication)

def _xml(r):
    return r if isinstance(r, str) else r[0]

def _ts(v):
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception: return ""

def _text(s):
    s = re.sub(r"(?i)<br\s*/?>", "\n", s or "")
    return html.unescape(re.sub(r"<[^>]+>", "", s))

def tree(on):
    """Baum fuer die Auswahl (Reihenfolge = Anzeige): {eid, name, path, depth, parent, count, default_on, kind}.
    kind = notebook | group | section. count = Seitenzahl (Abschnitt) bzw. Summe."""
    root = ET.fromstring(_xml(on.GetHierarchy("", 4)))
    out = []
    def walk(el, path, depth, parent):
        for c in el:
            tag = c.tag.replace(NS, "")
            if tag not in ("Notebook", "SectionGroup", "Section"): continue
            if c.get("isRecycleBin") == "true" or c.get("isInRecycleBin") == "true": continue
            name = c.get("nickname") or c.get("name") or ""
            p = f"{path} › {name}" if path else name
            node = {"eid": c.get("ID"), "name": name, "path": p, "depth": depth, "parent": parent, "default_on": False,
                    "kind": {"Notebook": "notebook", "SectionGroup": "group", "Section": "section"}[tag]}
            out.append(node)
            if tag == "Section":
                node["count"] = sum(1 for pg in c.findall(f"{NS}Page") if pg.get("isInRecycleBin") != "true")
                node["locked"] = c.get("locked") == "true" or c.get("encrypted") == "true"
            else:
                k = len(out); walk(c, p, depth + 1, node["eid"])
                node["count"] = sum(x["count"] for x in out[k:] if x["kind"] == "section")
    walk(root, "", 0, None)
    return out, root

def resolve(nodes, choice):
    """{eid: bool}: explizite Wahl > erbt vom Elternknoten > aus."""
    state = {}
    for n in nodes:
        e = n["eid"]
        state[e] = bool(choice[e]) if e in choice else state.get(n["parent"], False)
    return state

class OneNote(Connector):
    id, label = "onenote", "OneNote"
    hint = "Gewählte Abschnitte der geöffneten Notizbücher (Desktop-OneNote), nur geänderte Seiten werden nachgeladen."

    def available(self):
        try: _tlb_path(); return True, ""
        except Exception as e: return False, str(e)

    def sync(self, ctx):
        on = app()
        nodes, root = tree(on)
        state = resolve(nodes, ctx.settings.get("onenote_sections") or {})
        secs = {n["eid"]: n for n in nodes if n["kind"] == "section" and state.get(n["eid"])}
        if not secs: ctx.progress("OneNote: kein Abschnitt gewählt («Abschnitte»)"); return
        todo, seen, errors = [], set(), False
        for s in root.iter(f"{NS}Section"):
            n = secs.get(s.get("ID"))
            if not n: continue
            if n.get("locked"): ctx.progress(f"OneNote: {n['path']} gesperrt – übersprungen"); errors = True; continue
            for pg in s.findall(f"{NS}Page"):
                if pg.get("isInRecycleBin") == "true": continue
                ext = f"{pg.get('ID')}|{pg.get('lastModifiedTime')}"; seen.add(ext)
                if ext not in ctx.known: todo.append((pg, n, ext))
        for k, (pg, n, ext) in enumerate(todo):
            if ctx.cancelled(): return                                    # unvollstaendig -> kein Aufraeumen
            if k % 10 == 0: ctx.progress(f"OneNote: {k}/{len(todo)} Seiten", k, len(todo))
            try: pr = ET.fromstring(_xml(on.GetPageContent(pg.get("ID"))))
            except Exception as e: errors = True; ctx.progress(f"Seite übersprungen: {e}"); continue
            titel = pg.get("name") or "(ohne Titel)"
            zeilen, autor = [], ""
            for oe in pr.iter(f"{NS}OE"):
                autor = autor or oe.get("lastModifiedBy") or oe.get("author") or ""
                t = " ".join(_text(x.text) for x in oe.findall(f"{NS}T")).strip()
                if t: zeilen.append(t)
            text = clean("\n".join(zeilen))
            if titel and not text.startswith(titel): text = f"{titel}\n{text}"
            yield {"ext_id": ext, "title": titel, "author": autor, "ts": _ts(pg.get("lastModifiedTime")),
                   "location": n["path"], "body": text, "text": text, "prefix": f"{n['path']} › {titel}: ",
                   "meta": {"page_id": pg.get("ID"), "section_id": n["eid"], "pfad": n["path"]}}
        ctx.seen = seen; ctx.complete = not errors
