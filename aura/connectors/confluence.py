# aura/connectors/confluence.py — v78: Confluence (Data Center) per REST-API, nur lesen, nur Standardbibliothek.
# settings["confluence_links"] = Liste von Links. /pages/<id>/... = Seite + alle Unterseiten, /spaces/<KEY>/... = ganzer Bereich.
# Standard: anonym (alles, was im Bundesnetz ohnehin sichtbar ist). Optional Token (v208: DPAPI-verschlüsselt, data\confluence_token.dpapi).
# ext_id = "<seitenId>|v<Version>" -> neue Version = neues Objekt; ctx.seen -> Worker loescht alte Versionen/verschwundene Seiten.
# v208 Sicherheit: nur https, nur freigegebene Hosts (Richtlinie HKLM\SOFTWARE\Policies\AURA «ConfluenceHosts», sonst
#      confluence.bit.admin.ch), keine Ports/Zugangsdaten im Link, Redirects nur auf denselben Host, Antwortgrösse begrenzt.
import json, re, ssl, urllib.error, urllib.parse, urllib.request
from html import unescape
from html.parser import HTMLParser
from .base import Connector
from ..config import DATA
from ..text import clean

PAGE = 50
BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "pre", "blockquote"}
STANDARD_HOSTS = ("confluence.bit.admin.ch",)
MAX_ANTWORT = 32 * 2**20                                    # 32 MB je Antwort
TIMEOUT = 60
_HOST = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")

def erlaubte_hosts():
    """Administrativ festgelegte Positivliste (Gruppenrichtlinie), sonst der freigegebene Bundes-Host."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\AURA") as k:
            v, _ = winreg.QueryValueEx(k, "ConfluenceHosts")
        v = " ".join(v) if isinstance(v, (list, tuple)) else str(v)
        hs = tuple(h.strip().lower() for h in v.replace(",", " ").split() if h.strip())
        if hs: return hs
    except Exception: pass
    return STANDARD_HOSTS

def pruefe_url(url, hosts=None):
    """-> (scheme, host). ValueError bei allem, was nicht exakt https://<freigegebener Host>/... ist."""
    hosts = erlaubte_hosts() if hosts is None else hosts
    if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 for c in url.strip()): raise ValueError("Kein gültiger Link")
    try: u = urllib.parse.urlsplit(url.strip())
    except ValueError: raise ValueError("Kein gültiger Link")
    if u.scheme.lower() != "https": raise ValueError("Nur https-Links sind erlaubt")
    if "@" in u.netloc: raise ValueError("Link mit Zugangsdaten wird nicht akzeptiert")
    try: port = u.port
    except ValueError: raise ValueError("Ungültiger Port")
    if port is not None or ":" in u.netloc: raise ValueError("Link mit Portangabe wird nicht akzeptiert")
    host = (u.hostname or "")
    if host != u.netloc.lower() or not _HOST.match(host) or host.replace(".", "").isdigit():
        raise ValueError("Ungewöhnliche Host-Schreibweise wird nicht akzeptiert")
    if host not in hosts: raise ValueError(f"Host «{host}» ist nicht freigegeben (erlaubt: {', '.join(hosts)})")
    return "https", host

def parse_link(url, hosts=None):
    """-> (basis, cql, beschreibung) oder ValueError."""
    _, host = pruefe_url(url, hosts)
    u = urllib.parse.urlsplit(url.strip())
    base = f"https://{host}"
    q = urllib.parse.parse_qs(u.query)
    m = re.search(r"/pages/(\d+)", u.path) or (re.search(r"(\d+)", q["pageId"][0]) if "pageId" in q else None)
    if m: return base, f"(id={m.group(1)} or ancestor={m.group(1)}) and type=page", f"Seite {m.group(1)} + Unterseiten"
    m = re.search(r"/(?:spaces|display)/([A-Za-z0-9_~-]+)", u.path) or (re.fullmatch(r"[A-Za-z0-9_~-]+", q["key"][0]) if "key" in q else None)
    if m: return base, f'space="{m.group(1) if m.re.groups else m.group(0)}" and type=page', f"Bereich {m.group(1) if m.re.groups else m.group(0)}"
    raise ValueError("Link enthält weder /pages/<Nummer> noch /spaces/<KÜRZEL>")

def ersteller(r):
    """v206: Erstellt von/am aus dem Feld history einer Seite."""
    h = r.get("history") or {}
    return {"erstellt_von": (h.get("createdBy") or {}).get("displayName", ""), "erstellt_am": (h.get("createdDate") or "")[:16].replace("T", " ")}

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

def _token(melden=lambda m: None):
    from ..geheim import laden
    return laden(DATA / "confluence_token.dpapi", DATA / "confluence_token.txt", melden)

class _NurGleicherHost(urllib.request.HTTPRedirectHandler):
    """Redirects nur innerhalb desselben https-Hosts; alles andere wird abgelehnt (Token verlässt den Host nie)."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        alt = urllib.parse.urlsplit(req.full_url); neu = urllib.parse.urlsplit(urllib.parse.urljoin(req.full_url, newurl))
        if neu.scheme != "https" or neu.netloc.lower() != alt.netloc.lower():
            raise urllib.error.HTTPError(req.full_url, code, "Weiterleitung auf anderen Host/Schema abgelehnt", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def _opener():
    return urllib.request.build_opener(_NurGleicherHost(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))

def _get(url, tok, hosts=None, opener=None):
    pruefe_url(url, hosts)                                   # Token nur an freigegebene Hosts
    h = {"Accept": "application/json"}
    if tok: h["Authorization"] = "Bearer " + tok
    try:
        with (opener or _opener()).open(urllib.request.Request(url, headers=h), timeout=TIMEOUT) as r:
            data = r.read(MAX_ANTWORT + 1)
    except urllib.error.HTTPError as e: raise RuntimeError(f"HTTP {e.code}: {e.reason}") from None
    except urllib.error.URLError as e: raise RuntimeError(f"Verbindung fehlgeschlagen: {type(e.reason).__name__}") from None
    if len(data) > MAX_ANTWORT: raise RuntimeError("Antwort zu gross")
    return json.loads(data)

class Confluence(Connector):
    id, label = "confluence", "Confluence"
    hint = "Seiten (inkl. Unterseiten) oder ganze Bereiche aus eingefügten Links."

    def sync(self, ctx):
        links = [l for l in (ctx.settings.get("confluence_links") or []) if l.strip()]
        if not links: ctx.progress("Confluence: kein Link eingetragen"); return
        tok, seen, errors = _token(ctx.progress), set(), False
        for link in links:
            try: base, cql, desc = parse_link(link)
            except ValueError as e: errors = True; ctx.progress(f"Confluence: {urllib.parse.urlsplit(link.strip())._replace(query='', fragment='').geturl()[:60]} – {e}"); continue
            start, total = 0, None
            while True:
                if ctx.cancelled(): return                            # unvollstaendig -> kein Aufraeumen
                url = (f"{base}/rest/api/content/search?cql={urllib.parse.quote(cql)}&limit={PAGE}&start={start}"
                       "&expand=version,space,ancestors,history")
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
                    webui = str(r.get("_links", {}).get("webui") or "")
                    link_ = base + (webui if webui.startswith("/") and not webui.startswith("//") else f"/pages/viewpage.action?pageId={r['id']}")
                    yield {"ext_id": ext, "title": r["title"], "author": r["version"].get("by", {}).get("displayName", ""),
                           "ts": (r["version"].get("when") or "")[:16].replace("T", " "), "body": text, "text": text,
                           "prefix": f"{pfad}: ", "location": (r.get("space") or {}).get("name", ""),
                           "meta": {"url": link_, "page_id": r["id"], "space": (r.get("space") or {}).get("key", ""), "pfad": pfad,
                                    **ersteller(r)}}
                if len(res) < PAGE: break
                start += PAGE
        ctx.seen = seen; ctx.complete = not errors and bool(seen)
