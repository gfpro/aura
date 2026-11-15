# aura/connectors/jira.py — v231: Jira (Data Center) ueber die angemeldete Edge-Sitzung von AURA, nur lesen.
# Kein Token: Anmeldung (Smartcard/eIAM) macht Edge; AURA ruft /rest/api/2/search per fetch() im Jira-Tab auf.
# Auswahl (Einstellungen): jira_beteiligt (Standard True) = Bearbeiter/Melder/Beobachter = ich;
#                          jira_projekte = Liste von Projektschluesseln (z.B. ["UNTARLMMO"]). Beides wird mit OR verbunden.
# ext_id = "<KEY>|<updated>" -> geaendertes Ticket = neues Objekt; ctx.seen -> Worker loescht alte Staende.
# Personen (mit Adresse) in meta["personen"] -> graph.py: erstellte / zugewiesen / kommentierte.
import json, re, time
from urllib.parse import quote
from .base import Connector
from ..text import clean

BASIS = "https://jira.bit.admin.ch"
PAGE = 50
FELDER = "summary,description,status,reporter,assignee,comment,updated,created,project,issuetype"
_KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,30}$")

def jql(settings, filter_ids=()):
    """v232: + Favoriten-Filter aus Jira, + zuletzt angesehene Tickets; alles auf jira_tage (365) begrenzt."""
    teile = []
    if settings.get("jira_beteiligt", True):
        teile.append("assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser()")
    pr = [p.strip().upper() for p in (settings.get("jira_projekte") or []) if _KEY.match(p.strip().upper())]
    if pr: teile.append(f"project in ({', '.join(pr)})")
    ids = [str(int(i)) for i in filter_ids if str(i).isdigit()]
    if ids: teile.append(" OR ".join(f"filter = {i}" for i in ids))
    if settings.get("jira_angesehen", True): teile.append("issuekey in issueHistory()")
    if not teile: return ""
    tage = int(settings.get("jira_tage", 365) or 0)
    q = " OR ".join(f"({t})" for t in teile)
    return (f"({q}) AND updated >= -{tage}d" if tage > 0 else q) + " ORDER BY updated DESC"

def favoriten(tab):
    """IDs der in Jira als Favorit markierten Filter (nur wenn jira_favoriten, Standard True)."""
    return [f.get("id") for f in _get(tab, "/rest/api/2/filter/favourite") if isinstance(f, dict)]

def wiki_text(t):
    """Jira-Wiki-Markup -> lesbarer Text (fuer Embeddings ohne Steuerzeichen)."""
    t = (t or "").replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"\{(code|noformat)(?::[^}]*)?\}(.*?)\{\1\}", lambda m: m.group(2), t, flags=re.S)
    t = re.sub(r"\{(?:color|panel|quote|anchor)(?::[^}]*)?\}", "", t)
    t = re.sub(r"\[([^|\]]+)\|[^\]]+\]", r"\1", t)              # [Text|Link] -> Text
    t = re.sub(r"\[~([^\]]+)\]", r"@\1", t)                     # [~user] -> @user
    t = re.sub(r"\[(https?://[^\]]+)\]", r"\1", t)
    t = re.sub(r"^\s*h[1-6]\.\s*", "", t, flags=re.M)           # Ueberschriften
    t = re.sub(r"^\s*[*#-]+\s+", "- ", t, flags=re.M)           # Aufzaehlungen
    t = re.sub(r"^\s*\|\|?|\|\|?\s*$", "", t, flags=re.M).replace("||", " | ")
    t = re.sub(r"!\S+?!", "", t)                                # eingebettete Bilder
    t = re.sub(r"(?<!\w)[*_+](\S[^*_+\n]*?\S|\S)[*_+](?!\w)", r"\1", t)   # *fett* _kursiv_ +unterstr+
    return clean(t)

def _person(u):
    u = u or {}
    return {"n": u.get("displayName") or "", "a": (u.get("emailAddress") or "").lower()}

def _ts(v): return (v or "")[:16].replace("T", " ")

def ticket(i):
    """Ein Suchtreffer -> Dict fuer db.add_item."""
    f = i.get("fields") or {}
    key, titel = i["key"], f.get("summary") or ""
    status = (f.get("status") or {}).get("name", "")
    melder, bearb = _person(f.get("reporter")), _person(f.get("assignee"))
    teile = [wiki_text(f.get("description"))]
    personen = [dict(melder, art="erstellte")] if melder["n"] else []
    if bearb["n"]: personen.append(dict(bearb, art="zugewiesen"))
    for c in (f.get("comment") or {}).get("comments") or []:
        p = _person(c.get("author")); txt = wiki_text(c.get("body"))
        if txt: teile.append(f"Kommentar {p['n']} ({_ts(c.get('created'))[:10]}):\n{txt}")
        if p["n"]: personen.append(dict(p, art="kommentierte"))
    text = "\n\n".join(t for t in teile if t)
    return {"ext_id": f"{key}|{f.get('updated', '')}", "title": f"{key} {titel}", "author": melder["n"],
            "recipients": bearb["n"], "ts": _ts(f.get("updated")), "location": (f.get("project") or {}).get("name", ""),
            "body": text, "text": text, "prefix": f"{key} {titel} [{status}]: ",
            "meta": {"url": f"{BASIS}/browse/{key}", "key": key, "status": status,
                     "typ": (f.get("issuetype") or {}).get("name", ""), "erstellt_am": _ts(f.get("created")),
                     "personen": personen}}

# v231: Das Dashboard zeigt nur die lokale Passwortmaske. Eine Seite, die Anmeldung verlangt, leitet dagegen auf
#       eIAM (Login-Auswahl) weiter; dort klickt AURA einmal «FED-LOGIN" (nur Klick, nichts wird gelesen),
#       danach meldet die Smartcard automatisch an. Erfolg = /rest/api/2/myself liefert 200, nicht «Seite geladen".
START = BASIS + "/secure/ViewProfile.jspa"
_FED = ("(()=>{const e=[...document.querySelectorAll('a,button,[role=button],li,div')]"
        ".filter(x=>x.children.length<4&&/^\\s*FED-LOGIN\\s*$/i.test(x.innerText||''));"
        "if(!e.length)return false;(e[0].closest('a,button,[role=button]')||e[0]).click();return true})()")

def _angemeldet(t):
    from ..engine.herkunft import ist_erlaubt
    if not ist_erlaubt(t.js("location.href") or "", "jira"): return False
    return t.js("fetch('/rest/api/2/myself',{credentials:'same-origin'}).then(r=>r.status)", timeout=20) == 200

def _tab(settings=None):
    from ..engine import edge
    if not edge.laeuft(): edge.starten(); time.sleep(1.5)
    edge.verstecken()
    t = edge.tab_finden("jira")
    try:
        if t and _angemeldet(t): return t
    except Exception: pass
    if t: t.navigieren(START, "jira")
    else: t = edge.tab_neu(START)
    ende, geklickt = time.time() + 60, False
    while time.time() < ende:
        time.sleep(1)
        try:
            if t.js("document.readyState") != "complete": continue
            if _angemeldet(t): return t
            if not geklickt and "FED-LOGIN" in (t.js("document.body ? document.body.innerText : ''") or "").upper():
                geklickt = bool(t.js(_FED))
        except Exception: pass
    edge.fenster(t, "normal")
    raise RuntimeError("Jira: Anmeldung nicht abgeschlossen – bitte im Edge-Fenster von AURA «FED-LOGIN» wählen und erneut abgleichen")

def _get(tab, pfad):
    tab.origin_pruefen("jira")                                  # nur im Jira-Origin lesen
    js = ("fetch(%s,{credentials:'same-origin',headers:{Accept:'application/json'}})"
          ".then(r=>r.text().then(t=>[r.status,t]))") % json.dumps(pfad)
    st, body = tab.js(js, timeout=60)
    if st == 401: raise RuntimeError("Jira: nicht angemeldet (401)")
    if st != 200: raise RuntimeError(f"Jira: HTTP {st}")
    return json.loads(body)

class Jira(Connector):
    id, label = "jira", "Jira"
    hint = "Tickets, an denen du beteiligt bist, und eingetragene Projekte (über die Edge-Anmeldung)."

    def available(self):
        try:
            from ..engine import edge; edge.edge_pfad()
        except Exception as e: return False, f"Edge nicht verfügbar ({e})"
        return True, ""

    def sync(self, ctx):
        tab = _tab(); ids = []
        if ctx.settings.get("jira_favoriten", True):
            try: ids = favoriten(tab)
            except Exception as e: ctx.progress(f"Jira: Favoriten-Filter nicht lesbar ({e})")
        q = jql(ctx.settings, ids)
        if not q: ctx.progress("Jira: nichts ausgewählt"); return
        ctx.progress(f"Jira: {len(ids)} Favoriten-Filter")
        seen, start, total, fehler = set(), 0, None, False
        while True:
            if ctx.cancelled(): return                          # unvollstaendig -> kein Aufraeumen
            try: d = _get(tab, f"/rest/api/2/search?jql={quote(q)}&startAt={start}&maxResults={PAGE}&fields={FELDER}")
            except Exception as e: ctx.progress(str(e)); fehler = True; break
            res = d.get("issues") or []; total = d.get("total", total)
            ctx.progress(f"Jira: {start}/{total or '?'}", start, total or None)
            for i in res:
                try: it = ticket(i)
                except Exception as e: fehler = True; ctx.progress(f"Jira {i.get('key')}: übersprungen ({e})"); continue
                seen.add(it["ext_id"])
                if it["ext_id"] not in ctx.known: yield it
            start += len(res)
            if not res or start >= (total or 0): break
        ctx.seen = seen; ctx.complete = not fehler and bool(seen)
