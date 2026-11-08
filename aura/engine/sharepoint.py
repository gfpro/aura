"""SharePoint als Live-Quelle: REST-Suche (/_api/search/query) in der angemeldeten Edge-Sitzung.
Sucht ueberall (berechtigungsgefiltert), bevorzugt die unter «Wissen → SharePoint» eingetragenen Sites und weist
jeden Treffer mit Amt und Site aus. Gelesen werden nur Suchtreffer (Titel, Pfad, Auszug), nichts wird gespeichert.
"""
import json, math, re, time
from collections import Counter
from datetime import datetime
from urllib.parse import urlparse
from . import edge

STANDARD = "https://portal.collab.admin.ch"
MAX_TREFFER = 40
SEL = "Title,Path,Author,LastModifiedTime,FileType,HitHighlightedSummary,SiteTitle,SPSiteURL,SiteName"

JS_SUCHE = r"""(async (basis, q, n, sel) => {
  const u = basis + "/_api/search/query?querytext='" + encodeURIComponent(q.replace(/'/g, "''")) + "'&rowlimit=" + n
          + "&selectproperties='" + sel + "'&trimduplicates=true";
  const r = await fetch(u, {headers: {Accept: "application/json;odata=nometadata"}, credentials: "include"});
  if (!r.ok) return {status: r.status, rows: []};
  const j = await r.json(); const rel = j.PrimaryQueryResult.RelevantResults;
  return {status: r.status, total: rel.TotalRows,
          rows: rel.Table.Rows.map(row => Object.fromEntries(row.Cells.map(c => [c.Key, c.Value])))};
})"""


def _einstellungen():
    from ..config import load_settings
    s = load_settings()
    from .herkunft import ist_erlaubt                                 # v212: nur freigegebene Origins
    sites = [x.strip().rstrip("/") for x in (s.get("sharepoint_sites") or []) if x and x.strip() and ist_erlaubt(x.strip(), "sharepoint")]
    return s, sites


def soll_suchen(frage, settings):
    return bool(settings.get("sharepoint", False))


def site_url(u):
    p = urlparse(u)
    t = [x for x in p.path.split("/") if x]
    if len(t) >= 2 and t[0].lower() in ("sites", "teams"):
        return f"{p.scheme}://{p.netloc}/{t[0]}/{t[1]}"
    return f"{p.scheme}://{p.netloc}"


def _basis(sites):
    return site_url(sites[0]) if sites else STANDARD


def _tab(basis):
    from .herkunft import ist_erlaubt
    t = edge.tab_finden("sharepoint")
    if t:
        return t, False
    t = edge.tab_neu(basis)
    ende = time.time() + 30
    while time.time() < ende:
        time.sleep(0.5)
        try:
            if t.js("document.readyState") == "complete" and ist_erlaubt(t.js("location.href") or "", "sharepoint"):
                return t, True
        except Exception:
            pass
    return t, True


def _auszug(s):
    s = re.sub(r"</?c\d>", "", s or "")
    return re.sub(r"\s+", " ", s.replace("<ddd/>", " … ")).strip()


AMT = re.compile(r"\b([A-ZÄÖÜ][A-ZÄÖÜ0-9&\-]{1,11})\s*$")


def amt(row):
    """Amt aus den Autoren ('Nachname Vorname BAZL' -> BAZL); sonst aus dem Site-Namen."""
    kand = []
    for a in (row.get("Author") or "").split(";"):
        m = AMT.search(a.strip())
        if m and not m.group(1).isdigit():
            kand.append(m.group(1))
    if kand:
        return Counter(kand).most_common(1)[0][0]
    return (row.get("SiteTitle") or "").strip() or urlparse(row.get("Path") or "").netloc


def _datum(v):
    try:
        return datetime.fromisoformat((v or "")[:19])
    except Exception:
        return None


def _norm(v):
    v = [float(x) for x in v]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _diag(text):
    try:
        from .. import log
        log.get().info("DIAG sharepoint " + text)
    except Exception:
        pass


def antworten(w, asked, backend_id, prev, ref, t0):
    from .actanova_rang import suchbegriff, AKTUELL
    s, sites = _einstellungen()
    w.emit("answer_start", asked, "sharepoint", ref)
    begriff = suchbegriff(asked)
    if not begriff:
        w.emit("token", "Für die SharePoint-Suche fehlt ein Suchbegriff.")
        w.emit("sources", [], {"total": time.perf_counter() - t0, "list": True}); return
    basis = _basis(sites)
    try:
        neu = not edge.laeuft(); edge.starten()
        if neu: time.sleep(1.5)
        edge.verstecken()
        w.progress(f"SharePoint: suche «{begriff}» …")
        t1 = time.perf_counter()
        tab, eigen = _tab(basis)
        tab.dialog_schliessen()
        if "login" in (tab.js("location.href") or "").lower():
            edge.fenster(tab, "normal")
            w.emit("token", "SharePoint: bitte im Edge-Fenster von AURA einmal anmelden, dann nochmals fragen.")
            w.emit("sources", [], {"total": time.perf_counter() - t0, "list": True}); return
        tab.origin_pruefen("sharepoint")                            # v212: nur auf freigegebener Seite suchen
        r = {}
        for b in ([site_url(x) for x in sites] or [basis]):      # Suche ueber eine Site, auf die man Zugriff hat
            r = tab.js(f"({JS_SUCHE})({json.dumps(b)}, {json.dumps(begriff)}, {MAX_TREFFER}, {json.dumps(SEL)})", timeout=40) or {}
            if r.get("status") == 200: break
        tab.schliessen()
        if r.get("status") == 403 and not sites:
            w.emit("token", "SharePoint: Die Suche braucht eine Site, auf die du Zugriff hast – bitte unter «Wissen → SharePoint "
                            "→ Einrichten» mindestens eine eintragen (gesucht wird trotzdem überall).")
            w.emit("sources", [], {"total": time.perf_counter() - t0, "list": True}); return
    except Exception as e:
        w.emit("token", f"SharePoint nicht erreichbar: {type(e).__name__}: {e}")
        w.emit("sources", [], {"total": time.perf_counter() - t0, "list": True}); return
    rows, total = (r.get("rows") or [])[:MAX_TREFFER], r.get("total") or 0     # v212: Grenzen
    rows = [{k: (str(v)[:2000] if v is not None else v) for k, v in list(x.items())[:40]} for x in rows if isinstance(x, dict)]
    t_such = time.perf_counter() - t1
    if not rows:
        w.emit("token", f"In SharePoint gibt es zu «{begriff}» keine Treffer." + (f" (Status {r.get('status')})" if r.get("status") != 200 else ""))
        w.emit("sources", [], {"total": time.perf_counter() - t0, "list": True}); return
    # Gewichten: Rang der SharePoint-Suche + e5(Frage, Titel+Auszug) + eigene Sites + (bei «neuste») Datum
    chrono = bool(AKTUELL.search(asked))
    try:
        emb = w._embedder(); qv = _norm(emb.query(asked))
    except Exception:
        emb = qv = None
    jetzt = datetime.now()
    eigene = [site_url(x).lower() for x in sites]
    for i, row in enumerate(rows):
        row["_auszug"] = _auszug(row.get("HitHighlightedSummary"))
        row["_amt"] = amt(row)
        row["_datum"] = _datum(row.get("LastModifiedTime"))
        p = 1.0 - i / len(rows)                                      # Relevanz laut SharePoint
        if qv:
            p += 2 * sum(a * b for a, b in zip(qv, _norm(emb.query(f"{row.get('Title')}. {row['_auszug']}"))))
        if any((row.get("Path") or "").lower().startswith(e) for e in eigene): p += 0.8
        if chrono and row["_datum"]: p += 2 * 0.5 ** (max(0, (jetzt - row["_datum"]).days) / 90)
        row["_score"] = p
    rows.sort(key=lambda x: -x["_score"])
    _diag(f"suche={t_such:.1f}s treffer={total} gelesen={len(rows)} gewichtet={time.perf_counter() - t1 - t_such:.1f}s")
    top = rows[:8]
    hits = [{"title": f"{x.get('Title')} ({x['_amt']})", "source": "sharepoint", "ts": (x.get("LastModifiedTime") or "")[:10],
             "author": x["_amt"], "item_id": x.get("Path"), "chunk_id": None, "location": x.get("Path"),
             "text": f"{x.get('Title')} – {x.get('SiteTitle') or ''} – Amt {x['_amt']}: {x['_auszug']}"} for x in top]
    t_search = time.perf_counter() - t0
    if backend_id != "extractive":
        q = (f"{asked}\n(Die Quellen sind Suchtreffer aus SharePoint mit Auszügen; nenne bei jeder Aussage das Amt. "
             f"Antworte nur aus den Auszügen.)")
        try:
            be = w._llm(backend_id); be.settings = dict(s, llm_top_k=4, leer_satz="Dazu finde ich in SharePoint nichts."); be.used = None
            t2 = time.perf_counter()
            be.generate(q, hits[:4], lambda x: w.emit("token", x), w.cancel.is_set)
            _diag(f"llm={time.perf_counter() - t2:.1f}s")
            w.emit("token", "\n\n")
        except Exception as e:
            w.emit("token", f"(Sprachmodell übersprungen: {e})\n\n")
    # Liste nach Amt gruppiert, damit die Herkunft sichtbar bleibt
    gruppen = {}
    for x in top:
        gruppen.setdefault(x["_amt"], []).append(x)
    bl = []
    for a, xs in gruppen.items():
        site = xs[0].get("SiteTitle") or ""
        z = [f"{a}" + (f"  ·  {site}" if site and site != a else "")]
        for x in xs:
            d = f"{x['_datum']:%d.%m.%Y}" if x["_datum"] else ""
            z.append(f"   → {x.get('Title')}  ({', '.join(v for v in ((x.get('FileType') or '').lower(), d) if v)})")
        bl.append("\n".join(z))
    w.emit("token", f"{total} Treffer in SharePoint zu «{begriff}» – die {len(top)} passendsten, nach Amt:\n\n" + "\n\n".join(bl))
    w.emit("sources", hits, {"search": t_search, "total": time.perf_counter() - t0, "list": backend_id == "extractive"})
    w.chat = {"qs": (prev + [asked])[-3:], "hits": [], "t": time.time()}
    w.progress(f"Fertig (SharePoint, {total} Treffer)")
