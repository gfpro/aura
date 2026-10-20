# aura/workflow/recap.py — Bausteine für Rückblicke. Version 20261019v108
#   edge             besuchte Seiten/Suchbegriffe aus dem abgeglichenen Edge-Verlauf in einem Zeitraum
#   onenote          in einem Zeitraum geänderte OneNote-Seiten (abgeglichen)
#   gruppieren       Elemente (Mails, Termine, Seiten, Notizen) zu Themen verknüpfen – Python, kein Sprachmodell.
#                    Jede Verknüpfung trägt ihre Begründung (gleicher Betreff, gleiche Person + Wort, seltene Wörter, Zeitnähe).
#   themen_bericht   Themen + Zusammenfassungen + Termine von heute als Markdown-Datei in einen festen Ordner
#                    (Standard <AURA>\recap\JJJJ-MM-TT.md) und recap\neuester.json für die Karte «Recap» in AURA.
# Zeitraum «seit_letztem» (alle Bausteine mit Zeitraum): vom letzten erfolgreichen Lauf DIESES Workflows bis jetzt,
# höchstens «max_tage» (14) zurück; ohne früheren Lauf ab gestern 00:00. Montag -> automatisch Fr–So, nach Ferien die Ferien.
import json, math, re
from datetime import datetime, timedelta
from pathlib import Path
from .nodes import node
from .expr import as_text

def seit_letztem(ctx, max_tage=14, now=None):
    now = now or datetime.now(); t0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    von = t0 - timedelta(days=1)
    try:
        for p in sorted(Path(ctx.wf_dir).glob("laeufe/*/protokoll.json"), key=lambda p: p.parent.name, reverse=True):
            try: d = json.loads(p.read_text(encoding="utf-8"))
            except Exception: continue
            if d.get("status") == "ok":
                von = datetime.strptime(p.parent.name, "%Y%m%d_%H%M%S"); break
    except Exception: pass
    von = max(von, t0 - timedelta(days=int(max_tage)))
    return von.strftime("%Y-%m-%d %H:%M"), now.strftime("%Y-%m-%d %H:%M")

def zeitraum(p, ctx, standard="heute"):
    from .quellen import bereich
    z = str(p.get("zeitraum") or standard).strip().lower()
    if z in ("seit_letztem", "seit letztem", "seit_letztem_lauf"): return seit_letztem(ctx, p.get("max_tage", 14))
    return bereich(z)

def _erster(ctx, iid, n=400):
    r = ctx.conn.execute("SELECT text FROM chunks WHERE item_id=? ORDER BY ord LIMIT 1", (iid,)).fetchone()
    return re.sub(r"\s+", " ", r[0]).strip()[:n] if r else ""

@node("edge", "Besuchte Seiten und Suchbegriffe aus dem Edge-Verlauf (abgeglichen). Parameter: zeitraum, max (150)")
def n_edge(p, state, ctx):
    von, bis = zeitraum(p, ctx, "gestern")
    rows = ctx.conn.execute("SELECT id, title, author, ts FROM items WHERE source='edge_history' AND ts >= ? AND ts < ? "
                            "ORDER BY ts LIMIT ?", (von, bis, int(p.get("max", 150)))).fetchall()
    seiten = []
    for iid, ti, dom, ts in rows:
        m = re.search(r"Suchbegriff: (.+)", _erster(ctx, iid, 600))
        seiten.append({"titel": ti or "", "domain": dom or "", "zeit": ts, "suche": m.group(1).strip() if m else ""})
    ctx.progress(f"Edge {von}–{bis}: {len(seiten)} Seiten")
    text = "\n".join(f"• {s['zeit'][11:16]} {s['titel'][:90]} ({s['domain']})" + (f" – Suche: {s['suche']}" if s["suche"] else "")
                     for s in seiten) or "Keine Seiten im Zeitraum."
    return {"seiten": seiten, "text": text, "count": len(seiten), "von": von, "bis": bis,
            "tabelle": [{"Zeit": s["zeit"][5:16], "Seite": s["titel"][:80], "Domain": s["domain"]} for s in seiten]}

@node("onenote", "Im Zeitraum geänderte OneNote-Seiten (abgeglichen). Parameter: zeitraum, max (50)")
def n_onenote(p, state, ctx):
    von, bis = zeitraum(p, ctx, "gestern")
    rows = ctx.conn.execute("SELECT id, title, location, ts FROM items WHERE source='onenote' AND ts >= ? AND ts < ? "
                            "ORDER BY ts LIMIT ?", (von, bis, int(p.get("max", 50)))).fetchall()
    seiten = [{"titel": ti or "", "pfad": loc or "", "zeit": ts, "text": _erster(ctx, iid, 600)} for iid, ti, loc, ts in rows]
    ctx.progress(f"OneNote {von}–{bis}: {len(seiten)} Seiten")
    text = "\n".join(f"• {s['zeit'][5:16]} {s['titel']} ({s['pfad']})\n  {s['text'][:300]}" for s in seiten) or "Keine Seiten geändert."
    return {"seiten": seiten, "text": text, "count": len(seiten), "von": von, "bis": bis}

# ---------------------------------------------------------------- gruppieren
STOP = set("""aber alle allem allen aller auch beim bitte damit dann dass dein deine denn diese diesem diesen dieser dies doch
durch eine einem einen einer eines etwa euch flow habe haben hallo hast hatte heute hier ihre ihren immer jetzt kann kein
keine können machen mehr mein meine mich mit morgen muss noch nach nicht nichts oder ohne schon sehr sein seine sich sind
soll sollte über unter viel vielen vom von vor wann warum was weil wenn werden wie wieder wir wird wurde zum zur zwischen
danke dank gruss grüsse freundliche freundlichen liebe lieber besten herzliche bern mail mails termin termine meeting
teams microsoft besprechung datum uhr woche montag dienstag mittwoch donnerstag freitag samstag sonntag this that with from
have your will about https http www html""".split())
WORT = re.compile(r"[A-Za-zÄÖÜäöüàéèç0-9][\wÄÖÜäöüàéèç\-]{3,}")
KERN = re.compile(r"^((aw|wg|re|fw|fwd|antw|tr|wtr)\s*:\s*)+", re.I)

def _kern(t): return re.sub(r"\s+", " ", KERN.sub("", (t or "").strip())).lower()
def _woerter(t): return {w.lower().strip("-") for w in WORT.findall(t or "") if w.lower() not in STOP and not w.isdigit()}
def _personen(s): return {x.strip().lower() for x in re.split(r"[;,]", s or "") if len(x.strip()) > 2}
def _dt(ts):
    try: return datetime.strptime(ts[:16], "%Y-%m-%d %H:%M")
    except Exception: return None

def _zt(ts): return f"{ts[8:10]}.{ts[5:7]}. {ts[11:16]}" if len(ts) >= 16 else ts

def _liste(x, key):
    if isinstance(x, dict): x = x.get(key) or []
    return x if isinstance(x, list) else []

@node("gruppieren", "Elemente zu Themen verknüpfen (ohne Sprachmodell). Parameter: mails, termine, seiten, notizen "
                    "(Listen aus früheren Schritten), min_woerter (2), fenster_h (2), max_anteil (0.1), max_gruppen (15)")
def n_gruppieren(p, state, ctx):
    el = []
    for m in _liste(p.get("mails"), "mails"):
        el.append({"art": "Mail", "zeit": m.get("datum", ""), "titel": m.get("betreff", ""), "von": m.get("von", ""),
                   "personen": _personen(m.get("von")), "text": m.get("text", "")})
    for t in _liste(p.get("termine"), "termine"):
        el.append({"art": "Termin", "zeit": t.get("beginn", ""), "titel": t.get("titel", ""), "von": t.get("organisator", ""),
                   "personen": _personen(t.get("teilnehmende")) | _personen(t.get("organisator")), "text": t.get("notiz", "")})
    for s in _liste(p.get("seiten"), "seiten"):
        el.append({"art": "Edge", "zeit": s.get("zeit", ""), "titel": s.get("titel", ""), "von": s.get("domain", ""),
                   "personen": set(), "text": s.get("suche", "")})
    for s in _liste(p.get("notizen"), "seiten"):
        el.append({"art": "OneNote", "zeit": s.get("zeit", ""), "titel": s.get("titel", ""), "von": s.get("pfad", ""),
                   "personen": set(), "text": s.get("text", "")})
    n = len(el)
    for e in el:
        e["w"] = _woerter(e["titel"] + " " + e["text"][:300]); e["k"] = _kern(e["titel"]); e["t"] = _dt(e["zeit"])
    grenze = max(4, math.ceil(n * float(p.get("max_anteil", 0.1))))      # häufige Wörter/Personen verknüpfen nichts
    df, pf = {}, {}
    for e in el:
        for w in e["w"]: df[w] = df.get(w, 0) + 1
        for x in e["personen"]: pf[x] = pf.get(x, 0) + 1
    for e in el:
        e["w"] = {w for w in e["w"] if 2 <= df[w] <= grenze}
        e["personen"] = {x for x in e["personen"] if pf[x] <= max(3, n * 0.3)}
    mw, fh = int(p.get("min_woerter", 2)), float(p.get("fenster_h", 2))
    eltern = list(range(n)); gruende = {}
    def wurzel(i):
        while eltern[i] != i: eltern[i] = eltern[eltern[i]]; i = eltern[i]
        return i
    for i in range(n):
        for j in range(i + 1, n):
            a, b = el[i], el[j]; g = None; gem = sorted(a["w"] & b["w"])
            if a["k"] and len(a["k"]) >= 6 and a["k"] == b["k"]: g = "gleicher Betreff"
            elif len(gem) >= mw: g = "Wörter: " + ", ".join(gem[:4])
            elif gem and (a["personen"] & b["personen"]):
                g = f"Person {sorted(a['personen'] & b['personen'])[0]} + Wort «{gem[0]}»"
            elif gem and "Edge" in (a["art"], b["art"]) and a["t"] and b["t"] and abs((a["t"] - b["t"]).total_seconds()) <= fh * 3600:
                g = f"Edge kurz davor/danach + Wort «{gem[0]}»"
            if g:
                ri, rj = wurzel(i), wurzel(j)
                if ri != rj: eltern[rj] = ri
                gruende.setdefault((i, j), g)
    cl = {}
    for i in range(n): cl.setdefault(wurzel(i), []).append(i)
    gruppen, einzeln = [], []
    for ids in sorted(cl.values(), key=len, reverse=True):
        if len(ids) < 2: einzeln.append(ids[0]); continue
        if len(gruppen) >= int(p.get("max_gruppen", 15)): einzeln += ids; continue
        ids.sort(key=lambda i: el[i]["zeit"])
        haupt = next((el[i] for i in ids if el[i]["art"] in ("Mail", "Termin")), el[ids[0]])
        bg = []
        for (i, j), g in gruende.items():
            if i in ids and g not in bg: bg.append(g)
        zeilen = [f"[{el[i]['art']} {_zt(el[i]['zeit'])}] {el[i]['von'][:40]}: {el[i]['titel'][:100]} – "
                  + re.sub(r"\s+", " ", el[i]["text"])[:300] for i in ids]
        gruppen.append({"titel": KERN.sub("", haupt["titel"]).strip() or "Thema", "begruendung": bg[:5],
                        "elemente": [{k: el[i][k] for k in ("art", "zeit", "titel", "von")} for i in ids],
                        "text": "\n".join(zeilen)[:int(p.get("max_chars", 2500))]})
    einzel = [{k: el[i][k] for k in ("art", "zeit", "titel", "von")} for i in sorted(einzeln, key=lambda i: el[i]["zeit"])]
    ctx.progress(f"Gruppieren: {n} Elemente → {len(gruppen)} Themen, {len(einzel)} einzeln")
    text = "\n".join(f"• {g['titel']} ({len(g['elemente'])}) – {'; '.join(g['begruendung'])}" for g in gruppen) or "Keine Themen."
    return {"gruppen": gruppen, "einzeln": einzel, "count": len(gruppen), "elemente": n, "text": text}

# ---------------------------------------------------------------- themen_bericht

@node("themen_bericht", "Themen + Zusammenfassungen als Markdown in einen festen Ordner. Parameter: gruppen, zusammenfassungen, "
                        "heute (Termine), von, bis, ordner (recap), name")
def n_themen_bericht(p, state, ctx):
    gr = p.get("gruppen") or {}
    gruppen = _liste(gr, "gruppen"); einzeln = gr.get("einzeln", []) if isinstance(gr, dict) else []
    zs = _liste(p.get("zusammenfassungen"), "ergebnisse")
    zs = [as_text(z.get("text", "") if isinstance(z, dict) else z).strip() for z in zs]
    heute = _liste(p.get("heute"), "termine")
    von, bis = as_text(p.get("von", "")), as_text(p.get("bis", ""))
    jetzt = datetime.now()
    L = [f"# Recap {_zt(von)} – {_zt(bis)}", f"_erstellt {jetzt:%d.%m.%Y %H:%M} von AURA · Zusammenfassungen vom Sprachmodell, "
         "Verknüpfungen von Regeln – Originale unten je Thema_", "", f"## Heute ({len(heute)} Termine)"]
    L += [f"- {t.get('beginn', '')[11:16]}" + (f"–{t['ende'][11:16]}" if t.get("ende") else "") + f" {t.get('titel', '')}"
          + (f" ({t['ort'][:30]})" if t.get("ort") else "") for t in heute] or ["- keine"]
    L += ["", f"## Themen ({len(gruppen)})"]
    themen = []
    for i, g in enumerate(gruppen):
        z = zs[i] if i < len(zs) else ""
        themen.append({"titel": g["titel"], "zusammenfassung": z, "anzahl": len(g["elemente"])})
        L += ["", f"### {g['titel']}", f"> {z or '(keine Zusammenfassung)'}", ""]
        L += [f"- {e['art']} {_zt(e['zeit'])} · {e['von'][:40]} · {e['titel']}" for e in g["elemente"]]
        L += [f"_verknüpft über: {'; '.join(g['begruendung'])}_"]
    L += ["", f"## Einzeln ({len(einzeln)})"] + [f"- {e['art']} {_zt(e['zeit'])} · {e['titel']}" for e in einzeln]
    o = Path(as_text(p.get("ordner") or "recap"))
    if not o.is_absolute(): o = Path(ctx.wf_dir).parent.parent / o
    o.mkdir(parents=True, exist_ok=True)
    f = o / f"{as_text(p.get('name') or jetzt.strftime('%Y-%m-%d'))}.md"
    md = "\n".join(L) + "\n"; f.write_text(md, encoding="utf-8")
    (o / "neuester.json").write_text(json.dumps({"datei": str(f), "erstellt": jetzt.strftime("%Y-%m-%d %H:%M"), "von": von, "bis": bis,
        "themen": themen, "einzeln": len(einzeln), "heute": [{"zeit": t.get("beginn", "")[11:16], "ende": (t.get("ende") or "")[11:16],
        "titel": t.get("titel", ""), "ort": t.get("ort", "")} for t in heute]}, ensure_ascii=False, indent=1), encoding="utf-8")
    ctx.progress(f"Recap gespeichert: {f}")
    K = [f"Seit {_zt(von)} · {len(gruppen)} Themen, {len(einzeln)} einzeln", ""]          # kurz: fürs Widget (Baustein meldung)
    for t in themen[:8]: K += [f"- **{t['titel'][:70]}** ({t['anzahl']}): {t['zusammenfassung'][:220]}"]
    K += ["", f"Heute: {len(heute)} Termine"] + [f"- {t.get('beginn', '')[11:16]} {t.get('titel', '')[:60]}" for t in heute[:10]]
    return {"path": str(f), "text": md, "kurz": "\n".join(K), "themen": len(gruppen)}
