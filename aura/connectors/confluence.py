# aura/connectors/confluence.py — v78: Confluence (Data Center) per REST-API, nur lesen, nur Standardbibliothek.
# settings["confluence_links"] = Liste von Links. /pages/<id>/... = Seite + alle Unterseiten, /spaces/<KEY>/... = ganzer Bereich.
# Standard: anonym (alles, was im Bundesnetz ohnehin sichtbar ist). Optional Token in data\confluence_token.txt.
# ext_id = "<seitenId>|v<Version>" -> neue Version = neues Objekt; ctx.seen -> Worker loescht alte Versionen/verschwundene Seiten.
import json, re, urllib.parse, urllib.request
from html import unescape
from html.parser import HTMLParser
from .base import Connector
from ..config import DATA
from ..text import clean

PAGE = 50
BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "pre", "blockquote"}

def parse_link(url):
    """-> (basis, cql, beschreibung) oder ValueError."""
    u = urllib.parse.urlparse(url.strip())
    if u.scheme not in ("http", "https") or not u.netloc: raise ValueError("Kein gültiger Link")
    base = f"{u.scheme}://{u.netloc}"
    q = urllib.parse.parse_qs(u.query)
    m = re.search(r"/pages/(\d+)", u.path) or (re.search(r"(\d+)", q["pageId"][0]) if "pageId" in q else None)
    if m: return base, f"(id={m.group(1)} or ancestor={m.group(1)}) and type=page", f"Seite {m.group(1)} + Unterseiten"
    m = re.search(r"/(?:spaces|display)/([^/?#]+)", u.path) or (re.match(r"(.+)", q["key"][0]) if "key" in q else None)
    if m: return base, f'space="{m.group(1)}" and type=page', f"Bereich {m.group(1)}"
    raise ValueError("Link enthält weder /pages/<Nummer> noch /spaces/<KÜRZEL>")

class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.out = []
    def handle_starttag(self, tag, a):
        if tag in BLOCK: self.out.append("\n")
        elif tag in ("td", "th"): self.out.append(" | ")
    def handle_endtag(self, tag):
        if tag in BLOCK: self.out.append("\n")
    def handle_data(self, d): self.out.append(d)

def html_text(h):
    p = _Text(); p.feed(h or ""); t = unescape("".join(p.out))
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", t)).strip()

def _token():
    try: return (DATA / "confluence_token.txt").read_text(encoding="utf-8").strip()
    except Exception: return ""

def _get(url, tok):
    h = {"Accept": "application/json"}
    if tok: h["Authorization"] = "Bearer " + tok
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
        return json.load(r)

class Confluence(Connector):
    id, label = "confluence", "Confluence"
    hint = "Seiten (inkl. Unterseiten) oder ganze Bereiche aus eingefügten Links."

    def sync(self, ctx):
        links = [l for l in (ctx.settings.get("confluence_links") or []) if l.strip()]
        if not links: ctx.progress("Confluence: kein Link eingetragen"); return
        tok, seen, errors = _token(), set(), False
        for link in links:
            try: base, cql, desc = parse_link(link)
            except ValueError as e: errors = True; ctx.progress(f"Confluence: {link[:60]} – {e}"); continue
            start, total = 0, None
            while True:
                if ctx.cancelled(): return                            # unvollstaendig -> kein Aufraeumen
                url = (f"{base}/rest/api/content/search?cql={urllib.parse.quote(cql)}&limit={PAGE}&start={start}"
                       "&expand=version,space,ancestors")
                try: d = _get(url, tok)
                except Exception as e: errors = True; ctx.progress(f"Confluence {desc}: {e}"); break
                res = d.get("results") or []
                total = d.get("totalSize", total)
                ctx.progress(f"Confluence {desc}: {start}/{total or '?'}", start, total or None)
                for r in res:
                    ext = f"{r['id']}|v{r['version']['number']}"; seen.add(ext)
                    if ext in ctx.known: continue
                    try:
                        body = _get(f"{base}/rest/api/content/{r['id']}?expand=body.storage", tok)["body"]["storage"]["value"]
                    except Exception as e: errors = True; ctx.progress(f"Seite {r['title']} übersprungen: {e}"); continue
                    pfad = " › ".join([a.get("title", "") for a in r.get("ancestors") or []] + [r["title"]])
                    text = clean(html_text(body))
                    link_ = base + (r.get("_links", {}).get("webui") or f"/pages/viewpage.action?pageId={r['id']}")
                    yield {"ext_id": ext, "title": r["title"], "author": r["version"].get("by", {}).get("displayName", ""),
                           "ts": (r["version"].get("when") or "")[:16].replace("T", " "), "body": text, "text": text,
                           "prefix": f"{pfad}: ", "location": (r.get("space") or {}).get("name", ""),
                           "meta": {"url": link_, "page_id": r["id"], "space": (r.get("space") or {}).get("key", ""), "pfad": pfad}}
                if len(res) < PAGE: break
                start += PAGE
        ctx.seen = seen; ctx.complete = not errors and bool(seen)
