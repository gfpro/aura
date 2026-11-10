"""Intranet armasuisse als Live-Quelle: Suche per URL -> Treffer per e5 gewichten -> beste Seiten lesen ->
beste Textstellen ans Sprachmodell. Inhalte werden nur fuer die Antwort gelesen, nicht gespeichert.
"""
import math, re, time
from urllib.parse import quote
from . import edge

def basen():
    """v216: Eine oder mehrere Intranet-Adressen unter «Wissen» (getrennt durch Leerzeichen, Komma oder Semikolon)
    -> [('https://intranet.ar.admin.ch', '/de'), ...]. Nur freigegebene Origins (herkunft.py)."""
    from urllib.parse import urlparse
    from ..config import load_settings
    from .herkunft import ist_erlaubt
    out = []
    for roh in re.split(r"[\s,;]+", (load_settings().get("intranet_url") or "").strip()):
        u = urlparse(roh)
        if not roh or not u.scheme or not u.netloc or not ist_erlaubt(roh, "intranet"):
            continue
        m = re.match(r"^/(de|fr|it|en|rm)\b", u.path or "")
        b = (f"{u.scheme}://{u.netloc}", "/" + (m.group(1) if m else "de"))
        if b not in out: out.append(b)
    return out


def basis():
    """Erste Adresse (Kompatibilitaet). ('', '') wenn keine."""
    b = basen()
    return b[0] if b else ("", "")


def _name(b):
    """'https://intranet.ar.admin.ch' -> 'AR'  (Kurzname fuer die Anzeige)."""
    teile = b[0].split("//", 1)[-1].split(".")
    return (teile[1] if len(teile) > 2 and teile[0] == "intranet" else teile[0]).upper()


SUCH_PFAD = "/search?search={q}&searchType=pages&sort=relevance&page={p}&display=list"
MAX_SEITEN_SUCHE = 2       # 2 x 12 Treffer
MAX_SEITEN_LESEN = 4
STUECK = 900               # Zeichen je Textstelle
MAX_TREFFER = 50           # v212: Treffer je Suche
MAX_SEITE = 200_000        # v212: Zeichen je Seite (wird schon im Browser gekuerzt)
MAX_STUECKE = 200          # v212: Textstellen je Seite

JS_TREFFER = r"""(() => {
 const out = [];
 document.querySelectorAll('ul.search-results-list > li').forEach(li => {
   const a = li.querySelector('a[href]'); if (!a) return;
   const meta = [...li.querySelectorAll('.meta-info__item')].map(x => x.innerText.trim());
   out.push({titel: (li.querySelector('.card__title')||{}).innerText || '', url: a.href,
             typ: meta[0] || '', datum: meta[1] || '',
             text: ((li.querySelector('.card__description')||{}).innerText || '').trim()});
 });
 const n = (document.querySelector('.search-results__occurences strong')||{}).innerText || '0';
 return {anzahl: parseInt(n) || 0, treffer: out, fertig: !!document.querySelector('.search-results__occurences')};
})()"""

JS_SEITE = r"""(() => {
 const m = document.querySelector('main') || document.body;
 const k = m.cloneNode(true);
 k.querySelectorAll('nav, header, footer, aside, script, style, .back-to-top-wrapper, [class*=breadcrumb]').forEach(x => x.remove());
 return {titel: String(document.title).slice(0, 500), text: (k.innerText || '').slice(0, 200000).replace(/\n{3,}/g, '\n\n').trim()};
})()"""


def _warten(tab, ausdruck, timeout=20.0):
    ende = time.time() + timeout
    while time.time() < ende:
        time.sleep(0.5)
        try:
            r = tab.js(ausdruck)
            if r:
                return r
        except Exception:
            pass
    return None


def _norm(v):
    v = [float(x) for x in v]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def soll_suchen(frage, settings):
    return bool(settings.get("intranet", False))


def suchen(tab, begriff, b=None):
    from .herkunft import ist_erlaubt
    BASIS, sprache = b or basis()
    if not BASIS: raise RuntimeError("Intranet-Adresse fehlt oder ist nicht freigegeben")
    treffer, anzahl = [], 0
    for p in range(1, MAX_SEITEN_SUCHE + 1):
        tab.navigieren(BASIS + sprache + SUCH_PFAD.format(q=quote(begriff, safe=""), p=p), "intranet")
        time.sleep(0.8)
        r = _warten(tab, f"(() => {{ const r = {JS_TREFFER}; return r.fertig ? r : null; }})()", 20) or {}
        anzahl = r.get("anzahl", anzahl)
        treffer += r.get("treffer", [])
        if len(treffer) >= anzahl or not r.get("treffer"):
            break
    seen, out = set(), []
    for t in treffer:
        if t["url"] not in seen and ist_erlaubt(t["url"], "intranet") and len(out) < MAX_TREFFER:     # v212: exakter Origin
            seen.add(t["url"]); out.append(t)
    return out, anzahl


def lesen(tab, url):
    tab.navigieren(url, "intranet")
    time.sleep(0.8)
    alt, ende = -1, time.time() + 20
    r = {}
    while time.time() < ende:                    # warten, bis der Text nicht mehr waechst (Seite wird per JS gebaut)
        time.sleep(0.6)
        try:
            r = tab.js(JS_SEITE) or {}
        except Exception:
            continue
        n = len(r.get("text", ""))
        if n > 200 and n == alt:
            break
        alt = n
    try: tab.origin_pruefen("intranet")                        # v212
    except Exception: return ""
    return str(r.get("text", ""))[:MAX_SEITE]


def _diag(text):
    try:
        from .. import log
        log.get().info("DIAG intranet " + text)
    except Exception:
        pass


def _fertig_lesen(tab, timeout=20.0):
    """Wartet, bis der Seitentext nicht mehr waechst; liefert den Text (Seite wurde schon geladen)."""
    alt, ende, r = -1, time.time() + timeout, {}
    while time.time() < ende:
        time.sleep(0.4)
        try:
            r = tab.js(JS_SEITE) or {}
        except Exception:
            continue
        n = len(r.get("text", ""))
        if n > 200 and n == alt:
            break
        alt = n
    try: tab.origin_pruefen("intranet")                        # v212: nach Redirect nicht fremde Seite auslesen
    except Exception: tab.schliessen(); return ""
    tab.schliessen()
    return str(r.get("text", ""))[:MAX_SEITE]


def _stuecke(text):
    abs_ = []
    for a in re.split(r"\n\s*\n", text[:MAX_SEITE]):                # v212: lange Absaetze teilen
        a = a.strip()
        abs_ += [a[i:i + STUECK] for i in range(0, len(a), STUECK)] if a else []
    out, cur = [], ""
    for a in abs_:
        if len(cur) + len(a) > STUECK and cur:
            out.append(cur); cur = ""
        cur = (cur + "\n" + a).strip()
    if cur:
        out.append(cur)
    return out[:MAX_STUECKE]


def antworten(w, asked, backend_id, prev, ref, t0):
    from ..config import load_settings
    from .actanova_rang import suchbegriff
    s = load_settings()
    w.emit("answer_start", asked, "intranet", ref)
    begriff = suchbegriff(asked)
    if not basis()[0]:
        w.emit("token", "Keine Intranet-URL eingetragen – bitte unter «Wissen → Intranet» die Adresse des Intranets eintragen.")
        w.emit("sources", [], {"total": time.perf_counter() - t0, "list": True}); return
    if not begriff:
        w.emit("token", "Für die Intranet-Suche fehlt ein Suchbegriff.")
        w.emit("sources", [], {"total": time.perf_counter() - t0, "list": True}); return
    tab = None
    try:
        neu_gestartet = not edge.laeuft()
        edge.starten()
        if neu_gestartet: time.sleep(1.5)
        edge.verstecken()                                          # Intranet braucht keine Anmeldung (SSO)
        w.progress(f"Intranet: suche «{begriff}» …")
        tab = edge.tab_neu("about:blank")
        treffer, anzahl, mehrere = [], 0, len(basen()) > 1            # v216: alle eingetragenen Intranets
        for b in basen():
            try:
                tr, n = suchen(tab, begriff, b)
            except Exception as x:
                _diag(f"{b[0]}: {x}"); continue
            for t in tr: t["netz"] = _name(b)
            treffer += tr; anzahl += n
        if not treffer:
            w.emit("token", f"Im Intranet gibt es zu «{begriff}» keine Treffer.")
            w.emit("sources", [], {"total": time.perf_counter() - t0, "list": True}); return
        # 1) Treffer neu gewichten: e5(Frage, Titel+Beschreibung) + Begriff im Titel + Rang der Intranetsuche
        emb = w._embedder()
        qv = _norm(emb.query(asked))
        worte = [x.lower() for x in begriff.split()]
        for i, t in enumerate(treffer):
            t["score"] = _cos(qv, _norm(emb.query(f"{t['titel']}. {t['text']}"))) \
                + (0.08 if any(x in t["titel"].lower() for x in worte) else 0) + 0.02 * (1 - i / len(treffer))
        treffer.sort(key=lambda t: -t["score"])
        t_such = time.perf_counter() - t0
        # 2) beste Seiten parallel laden (je ein Tab), dann lesen; 3) beste Textstellen waehlen
        w.progress(f"Intranet: lese {min(MAX_SEITEN_LESEN, len(treffer))} Seiten …")
        t1 = time.perf_counter()
        extra = []
        try:
            for t in treffer[:MAX_SEITEN_LESEN]:
                x = edge.tab_neu(t["url"]); extra.append((x, t))
            texte = [(t, _fertig_lesen(x)) for x, t in extra]
        finally:
            for x, _ in extra: edge.tab_zu(x)
        t_lesen = time.perf_counter() - t1
        stellen = []
        for t, txt in texte:
            for st in _stuecke(txt)[:15]:
                stellen.append((_cos(qv, _norm(emb.query(st))), t, st))
        t_emb = time.perf_counter() - t1 - t_lesen
        _diag(f"suche={t_such:.1f}s lesen={t_lesen:.1f}s embed={t_emb:.1f}s seiten={len(texte)} stellen={len(stellen)}")
    except Exception as e:
        w.emit("token", f"Intranet nicht erreichbar: {e}")
        w.emit("sources", [], {"total": time.perf_counter() - t0, "list": True}); return
    finally:
        if tab: edge.tab_zu(tab)
    stellen.sort(key=lambda x: -x[0])
    n = min(4, int(s.get("llm_top_k", 4)))                     # kurz halten: Sprachmodell ist der langsamste Teil
    hits = [{"title": t["titel"] + (f" ({t['netz']})" if len(basen()) > 1 else ""), "source": "intranet", "ts": "", "author": t["datum"], "item_id": t["url"], "chunk_id": None,
             "location": t["url"], "url": t["url"], "text": st} for _, t, st in stellen[:n]]
    t_search = time.perf_counter() - t0
    if backend_id != "extractive" and hits:
        q = (f"{asked}\n(Die Quellen sind Textstellen aus dem Intranet armasuisse. Antworte nur daraus und nenne die Seite. "
             f"Steht die Antwort nicht darin, sage das.)")
        try:
            be = w._llm(backend_id); be.settings = dict(s, llm_top_k=len(hits), leer_satz="Dazu finde ich im Intranet nichts."); be.used = None
            t2 = time.perf_counter()
            be.generate(q, hits, lambda x: w.emit("token", x), w.cancel.is_set)
            _diag(f"llm={time.perf_counter() - t2:.1f}s stellen={len(hits)}")
        except Exception as e:
            w.emit("token", f"(Sprachmodell übersprungen: {e})")
    seiten = []
    for t in treffer[:5]:
        seiten.append(f"– {t['titel']} ({t['datum']}{', ' + t['netz'] if len(basen()) > 1 else ''}): {t['url']}")
    w.emit("token", f"\n\nIntranet: {anzahl} Treffer zu «{begriff}», gewichtet; die passendsten Seiten:\n" + "\n".join(seiten))
    w.emit("sources", hits, {"search": t_search, "total": time.perf_counter() - t0, "list": backend_id == "extractive"})
    w.chat = {"qs": (prev + [asked])[-3:], "hits": [], "t": time.time()}
    w.progress(f"Fertig (Intranet, {len(treffer)} Treffer, {min(MAX_SEITEN_LESEN, len(treffer))} Seiten gelesen)")
