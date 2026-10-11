# aura/connectors/edge_history.py — Edge-Verlauf (Titel, Adresse, Suchbegriffe). Seiteninhalte werden NICHT geladen.
# Version 20261007v21: ein Eintrag pro Adresse; bekannte Adressen -> letzter Besuch/Anzahl aktualisieren;
# Rauschen (Anmeldung, Weiterleitungen, versteckte Seiten) ausfiltern; Domain als «author» (fuer «Seiten von admin.ch»).
import os, re, shutil, sqlite3, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from .base import Connector

EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)      # Chromium zaehlt Mikrosekunden ab 1601
SKIP_HOSTS = re.compile(r"(^|\.)(login\.microsoftonline\.com|login\.live\.com|login\.windows\.net|aadcdn\.\w+|"
                        r"msauth\.net|adfs\.|sso\.|okta\.com|account\.microsoft\.com|accounts\.google\.com)$", re.I)
SKIP_PATH = re.compile(r"/(oauth2?|saml2?|signin|sign-in|login|logout|auth|callback|redirect)(/|$|\?)", re.I)
SKIP_TITLE = re.compile(r"^(anmelden|sign in|sign-in|login|redirecting|weiterleitung|loading|wird geladen)\b", re.I)

def edge_profiles():
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data"
    return [p for p in base.glob("*/History") if p.is_file()] if base.exists() else []

def _open(hist):
    """Edge sperrt die Datei, solange es laeuft -> Kopie lesen; klappt das nicht, direkt unveraenderlich oeffnen."""
    tmp = Path(tempfile.gettempdir()) / f"aura_edge_{hist.parent.name}.db"
    try:
        shutil.copy2(hist, tmp)
        return sqlite3.connect(f"file:{tmp}?mode=ro", uri=True), tmp
    except OSError:
        return sqlite3.connect(f"file:{hist.as_posix()}?mode=ro&immutable=1", uri=True), None

def _clean(url):
    """Anker (#...) entfernen; gleiche Seite = gleicher Eintrag."""
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path, p.query, "")), p.netloc.lower().removeprefix("www.")

class EdgeHistory(Connector):
    id, label = "edge_history", "Edge-Verlauf"
    hint = "Besuchte Seiten und Suchbegriffe (Einstellung: edge_days, Standard 90). Nur Titel/Adresse, kein Seiteninhalt."

    def available(self):
        return (True, "") if edge_profiles() else (False, "Kein Edge-Profil gefunden")

    def sync(self, ctx):
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(ctx.settings.get("edge_days", 90)))
        cut_us = int((cutoff - EPOCH).total_seconds() * 1e6)
        for hist in edge_profiles():
            conn, tmp = _open(hist)
            try:
                rows = conn.execute(
                    "SELECT u.url, u.title, MAX(v.visit_time), COUNT(v.id), "
                    "(SELECT group_concat(DISTINCT k.term) FROM keyword_search_terms k WHERE k.url_id = u.id) "
                    "FROM urls u JOIN visits v ON v.url = u.id WHERE v.visit_time > ? AND u.hidden = 0 "
                    "GROUP BY u.id ORDER BY 3 DESC", (cut_us,)).fetchall()
            finally:
                conn.close()
                if tmp:
                    try: tmp.unlink()
                    except OSError: pass
            seen, new, upd, skip = set(), 0, 0, 0
            for k, (url, title, t, visits, terms) in enumerate(rows):
                if ctx.cancelled(): return
                if k % 200 == 0: ctx.progress(f"Edge ({hist.parent.name}): {k}/{len(rows)}", k, len(rows))
                if not url.startswith(("http://", "https://")): continue
                url, host = _clean(url)
                path = urlsplit(url).path
                if SKIP_HOSTS.search(host) or SKIP_PATH.search(path) or SKIP_TITLE.search(title or ""):
                    skip += 1; continue
                if url in seen: continue                    # gleiche Seite mit anderem Anker: neuester Besuch zaehlt
                seen.add(url)
                ts = (EPOCH + timedelta(microseconds=t)).astimezone().strftime("%Y-%m-%d %H:%M")
                meta = {"visits": visits, "profile": hist.parent.name, "url": url, "domain": host}
                if url in ctx.known:                        # schon gespeichert -> nur letzten Besuch/Anzahl nachfuehren
                    upd += 1
                    yield {"update": True, "ext_id": url, "ts": ts, "meta": meta}; continue
                title = (title or "").strip() or url
                text = f"{title}\n{host}\n{url}" + (f"\nSuchbegriff: {terms}" if terms else "")
                new += 1; ctx.known.add(url)
                yield {"ext_id": url, "title": title, "author": host, "ts": ts, "body": text,
                       "text": text, "prefix": "", "meta": meta}
            ctx.progress(f"Edge ({hist.parent.name}): {new} neu, {upd} aktualisiert, {skip} ausgefiltert")
