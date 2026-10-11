# aura/workflow/quellen.py — Bausteine für AURA-Daten und Abläufe. Version 20261011v62
#   kalender   Termine aus dem abgeglichenen Outlook-Kalender in einem Zeitraum
#   mails      Mails aus dem abgeglichenen Postfach (Zeitraum, optional Suchbegriff)
#   fuer_jedes einen Baustein für jedes Element einer Liste ausführen (z.B. Mails zu jedem Termin); «item» = Element
#   meldung    Ergebnis in AURA anzeigen (Ansicht «Ergebnisse» auf der Startseite)
#   mail_an_mich  Ergebnis als Outlook-Mail an die eigene Adresse (Standard: nur Entwurf, nicht senden)
# v62: Form der Ausgabe wählbar: form = text | stichpunkte | tabelle (Tabellen nur bei «tabelle» oder ausdrücklich angegeben).
# v61: Anzeige/Mail hängen die Tabellen früherer Schritte automatisch an (tabellen_auto); Mail als gestaltetes HTML (Titel, Aufzählung, fett).
# v59: kalender/mails liefern «tabelle» (Zeilen zum Anzeigen); meldung/mail_an_mich zeigen Tabellen (AURA: Tabelle, Mail: HTML).
# v58: «kurz» = knappe Fassung fürs Sprachmodell (spart Tokens: 8B hat nur 4096); mails ohne automatische Antworten/Newsletter.
# v54: kalender liefert ueberschneidungen (Termine, die sich zeitlich überlappen) – berechnet, nicht vom Modell.
# Gelesen wird nur aus aura.db (lokal); Outlook selbst wird hier nicht angesprochen.
import re
from datetime import datetime, timedelta
from .nodes import node, NODES
from .expr import as_text, resolve

ZEITRAEUME = {"heute": "heute", "morgen": "morgen", "naechste_7": "nächste 7 Tage", "naechste_30": "nächste 30 Tage",
              "letzte_7": "letzte 7 Tage", "letzte_30": "letzte 30 Tage", "diese_woche": "diese Woche"}

def bereich(z, now=None):
    """Zeitraum-Schlüssel -> (von, bis) als 'YYYY-MM-DD HH:MM'."""
    now = now or datetime.now(); t0 = now.replace(hour=0, minute=0, second=0, microsecond=0); d = timedelta(days=1)
    z = (z or "heute").strip().lower().replace("ä", "ae").replace(" ", "_")
    z = {"naechste_7_tage": "naechste_7", "naechste_30_tage": "naechste_30", "letzte_7_tage": "letzte_7",
         "letzte_30_tage": "letzte_30"}.get(z, z)
    a, b = {"heute": (t0, t0 + d), "morgen": (t0 + d, t0 + 2 * d), "naechste_7": (now, t0 + 8 * d),
            "naechste_30": (now, t0 + 31 * d), "letzte_7": (t0 - 7 * d, now), "letzte_30": (t0 - 30 * d, now),
            "diese_woche": (t0 - t0.weekday() * d, t0 + (7 - t0.weekday()) * d)}.get(z, (t0, t0 + d))
    f = lambda x: x.strftime("%Y-%m-%d %H:%M")
    return f(a), f(b)

def _dt(ts):
    """'2026-10-11 08:30' -> '11.10. 08:30'"""
    return f"{ts[8:10]}.{ts[5:7]}. {ts[11:16]}" if len(ts) >= 16 else ts

def _ort(o):
    """Ort kurz: «Microsoft Teams-Besprechung» -> «Teams», «_ARMASUISSE-G1B SiZi C 00 077 24 Personen» -> «G1B SiZi C 00 077»."""
    if re.search(r"teams", o, re.I): return "Teams"
    o = re.sub(r"^_?[A-Z]+-", "", o); o = re.sub(r"\s+\d+\s+Personen$", "", o)
    return o[:28]

def _stand(ctx, source, warn):
    try:
        r = ctx.conn.execute("SELECT last_sync FROM sync_state WHERE source=?", (source,)).fetchone()
        if not r or not r[0]: warn.append(f"{source} wurde noch nie abgeglichen"); return
        if datetime.now() - datetime.fromisoformat(r[0]) > timedelta(hours=24):
            warn.append(f"{source} zuletzt abgeglichen am {r[0]} – Ergebnis evtl. nicht aktuell")
    except Exception: pass

def _erster_text(ctx, iid, n=500):
    r = ctx.conn.execute("SELECT text FROM chunks WHERE item_id=? ORDER BY ord LIMIT 1", (iid,)).fetchone()
    return re.sub(r"\s+", " ", r[0]).strip()[:n] if r else ""

@node("kalender", "Termine aus dem Outlook-Kalender (abgeglichen in AURA). Parameter: zeitraum (heute, morgen, naechste_7, "
                  "naechste_30, letzte_7, letzte_30, diese_woche), max (50)")
def n_kalender(p, state, ctx):
    von, bis = bereich(p.get("zeitraum")); warn = []; _stand(ctx, "outlook_calendar", warn)
    rows = ctx.conn.execute("SELECT id, title, ts, location, author, recipients, meta FROM items WHERE source='outlook_calendar' "
                            "AND ts >= ? AND ts < ? ORDER BY ts LIMIT ?", (von, bis, int(p.get("max", 50)))).fetchall()
    import json
    termine = []
    for iid, ti, ts, loc, org, who, meta in rows:
        try: ende = json.loads(meta or "{}").get("end", "")
        except Exception: ende = ""
        termine.append({"titel": ti or "", "beginn": ts, "ende": ende, "ort": loc or "", "organisator": org or "",
                        "teilnehmende": who or "", "notiz": _erster_text(ctx, iid, 300)})
    zeile = lambda t: (f"• {_dt(t['beginn'])}" + (f"–{t['ende'][11:16]}" if t["ende"] else "")
                       + f"  {t['titel']}" + (f"  ({t['ort']})" if t["ort"] else "")
                       + (f"\n  Teilnehmende: {t['teilnehmende'][:200]}" if t["teilnehmende"] else ""))
    text = "\n".join(zeile(t) for t in termine) or "Keine Termine im Zeitraum."
    kurz = "\n".join(f"{_dt(t['beginn'])}" + (f"–{t['ende'][11:16]}" if t["ende"] else "") + f" {t['titel'][:70]}"
                     + (f" ({len([x for x in t['teilnehmende'].split(';') if x.strip()])} Pers.)" if t["teilnehmende"] else "")
                     for t in termine) or "Keine Termine im Zeitraum."
    ueb = []                                                         # v54: Überschneidungen (Rechnen, nicht Modell)
    for i, a in enumerate(termine):
        for b in termine[i + 1:]:
            if a["ende"] and b["beginn"] < a["ende"] and b["beginn"][:10] == a["beginn"][:10]:
                ueb.append(f"• {_dt(b['beginn'])[:6]} {a['titel']} ({a['beginn'][11:16]}–{a['ende'][11:16]}) überschneidet sich mit "
                           f"{b['titel']} ({b['beginn'][11:16]}–{b['ende'][11:16] or '?'})")
    ctx.progress(f"Kalender {von[:10]}–{bis[:10]}: {len(termine)} Termine, {len(ueb)} Überschneidungen")
    konf = set()
    for i, a in enumerate(termine):
        for b in termine[i + 1:]:
            if a["ende"] and b["beginn"] < a["ende"] and b["beginn"][:10] == a["beginn"][:10]:
                konf |= {a["titel"] + a["beginn"], b["titel"] + b["beginn"]}
    tage = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    def _tag(ts):
        try: return tage[datetime.strptime(ts[:10], "%Y-%m-%d").weekday()] + " " + _dt(ts)[:6]
        except ValueError: return ts[:10]
    tabelle = [{"Tag": _tag(t["beginn"]), "Zeit": t["beginn"][11:16] + (f"–{t['ende'][11:16]}" if t["ende"] else ""),
                "Termin": t["titel"], "Ort": _ort(t["ort"]),
                "Pers.": str(len([x for x in t["teilnehmende"].split(";") if x.strip()])) if t["teilnehmende"] else "",
                "⚠": "überschneidet" if t["titel"] + t["beginn"] in konf else ""} for t in termine]
    return {"termine": termine, "text": text, "kurz": kurz, "tabelle": tabelle, "count": len(termine), "von": von, "bis": bis,
            "ueberschneidungen": "\n".join(ueb) or "keine", "anzahl_ueberschneidungen": len(ueb), "_warnungen": warn}

@node("mails", "Mails aus dem Postfach (abgeglichen in AURA). Parameter: zeitraum, suche (optional), max (10)")
def n_mails(p, state, ctx):
    von, bis = bereich(p.get("zeitraum", "letzte_7")); n = int(p.get("max", 10)); q = as_text(p.get("suche", "")).strip()
    warn = []; _stand(ctx, "outlook_mail", warn); mails = []
    filtern = str(p.get("filter", True)).lower() not in ("false", "nein", "0")      # v58
    roh = n * 3 if filtern else n
    if q and ctx.search:
        for h in ctx.search(q, roh * 4, ["outlook_mail"]) or []:
            ts = str(h.get("ts", ""))
            if von <= ts < bis: mails.append({"betreff": h.get("title", ""), "von": h.get("author", ""), "datum": ts,
                                               "text": re.sub(r"\s+", " ", h.get("text", ""))[:500]})
            if len(mails) >= roh: break
    else:
        for iid, ti, au, ts in ctx.conn.execute("SELECT id, title, author, ts FROM items WHERE source='outlook_mail' AND ts >= ? "
                                                "AND ts < ? ORDER BY ts DESC LIMIT ?", (von, bis, roh)):
            mails.append({"betreff": ti or "", "von": au or "", "datum": ts, "text": _erster_text(ctx, iid)})
    weg = 0
    if filtern:                                                      # v58: Rauschen weg (Abwesenheiten, Newsletter, Digests)
        rx = re.compile(r"^(automatische antwort|abwesenheit|out of office|automatic reply|autoreply|réponse automatique)|"
                        r"newsletter|digest|no-?reply|noreply|unsubscribe|abmelden", re.I)
        alt = mails; mails = [m for m in alt if not (rx.search(m["betreff"]) or rx.search(m["von"]) or "abwesend" in m["text"][:300].lower()
                                                    and m["betreff"].lower().startswith(("automatische", "abwesen")))][:n]
        weg = len(alt) - len(mails)
    text = "\n".join(f"• {_dt(m['datum'])} · {m['von']} · {m['betreff']}\n  {m['text'][:400]}" for m in mails) or "Keine passenden Mails."
    kurz = "\n".join(f"{_dt(m['datum'])} {m['von'][:30]}: {m['betreff'][:80]} – "
                      + re.sub(r"^.*?\(\S[^)]*\d{4}-\d\d-\d\d\):\s*", "", m["text"])[:180] for m in mails) or "Keine passenden Mails."
    tabelle = [{"Datum": _dt(m["datum"]), "Von": m["von"][:40], "Betreff": m["betreff"][:90]} for m in mails]
    return {"mails": mails, "text": text, "kurz": kurz, "tabelle": tabelle, "count": len(mails), "ausgefiltert": weg, "_warnungen": warn}

@node("fuer_jedes", "Einen Baustein für jedes Element einer Liste ausführen. Parameter: liste ({{schritt.liste}}), "
                    "schritt {type, …} mit {{item.feld}}, max (20)")
def n_fuer_jedes(p, state, ctx):
    liste = p.get("liste") or []
    if isinstance(liste, str): liste = [x for x in liste.splitlines() if x.strip()]
    sub = dict(p.get("schritt") or {}); typ = sub.pop("type", None)
    if typ not in NODES or typ == "fuer_jedes": raise RuntimeError(f"fuer_jedes: unbekannter Baustein «{typ}»")
    out, teile, kurz, warn = [], [], [], []
    for i, item in enumerate(liste[:int(p.get("max", 20))]):
        if ctx.cancelled(): break
        st2 = dict(state, item=item)
        r = NODES[typ](resolve(sub, st2), st2, ctx); out.append(r)
        name = item.get("titel") or item.get("betreff") or item.get("name") if isinstance(item, dict) else str(item)
        teile.append(f"## {name or f'Element {i + 1}'}\n{r.get('text', '') if isinstance(r, dict) else r}")
        kurz.append(f"## {name or f'Element {i + 1}'}\n{(r.get('kurz') or r.get('text', ''))[:600] if isinstance(r, dict) else str(r)[:600]}")
        for w in (r.get("_warnungen") or []) if isinstance(r, dict) else []:
            if w not in warn: warn.append(w)
    ctx.progress(f"Für jedes: {len(out)} Elemente bearbeitet")
    return {"ergebnisse": out, "text": "\n\n".join(teile) or "Keine Elemente.", "kurz": "\n".join(kurz) or "Keine Elemente.",
            "count": len(out), "_warnungen": warn}

def _tabellen(p, state=None):
    """v59: tabellen = {"Termine": [ {spalte: wert}, … ], …}. v61: ohne Angabe (tabellen_auto, Standard ein) werden alle
    «tabelle»-Ergebnisse früherer Schritte genommen (z.B. Termine holen, Mails holen)."""
    t = p.get("tabellen") or {}
    t = {k: v for k, v in t.items() if isinstance(v, list) and v and isinstance(v[0], dict)} if isinstance(t, dict) else {}
    if not t and state and str(p.get("form", "")).lower() == "tabelle":
        for sid, v in state.items():
            if isinstance(v, dict) and isinstance(v.get("tabelle"), list) and v["tabelle"] and isinstance(v["tabelle"][0], dict):
                t[sid.replace("_", " ").capitalize()] = v["tabelle"]
    return t

@node("meldung", "Ergebnis in AURA anzeigen (Ansicht «Ergebnisse»). Parameter: text, titel, tabellen {Name: Liste}")
def n_meldung(p, state, ctx):
    return {"_meldung": {"titel": as_text(p.get("titel") or state.get("workflow", {}).get("name", "")),
                         "text": _form_text(as_text(p.get("text", "")), p), "tabellen": _tabellen(p, state),
                         "form": str(p.get("form", "stichpunkte")).lower()}}

def _form_text(text, p):
    """form «text»: Aufzählungszeichen weg, Zeilen zu Absätzen zusammenziehen."""
    if str(p.get("form", "")).lower() != "text": return text
    return "\n\n".join(re.sub(r"^[-•*]\s+", "", l).strip() for l in text.splitlines() if l.strip())

def _md_html(text):
    """Kurzfazit (Markdown des Modells) -> HTML: «- » Aufzählung, **fett**, Leerzeilen = Absatz."""
    import html as H
    out, liste = [], False
    for line in text.splitlines():
        l = line.strip()
        if not l:
            if liste: out.append("</ul>"); liste = False
            continue
        x = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", H.escape(re.sub(r"^[-•*]\s+", "", l)))
        if re.match(r"^[-•*]\s+", l):
            if not liste: out.append("<ul style='margin:4px 0 8px 18px;padding:0'>"); liste = True
            out.append(f"<li style='margin:2px 0'>{x}</li>")
        else:
            if liste: out.append("</ul>"); liste = False
            out.append(f"<p style='margin:4px 0'>{x}</p>")
    if liste: out.append("</ul>")
    return "".join(out)

def _html(text, tabellen, titel=""):
    import html as H
    from datetime import datetime as _d
    out = ["<div style='font-family:Segoe UI,Arial,sans-serif;font-size:10.5pt;color:#111827'>"]
    if titel: out.append(f"<h2 style='margin:0 0 2px;color:#4F6BED;font-size:15pt'>{H.escape(titel)}</h2>"
                         f"<div style='color:#6B7280;font-size:9pt;margin-bottom:10px'>{_d.now():%d.%m.%Y %H:%M} · AURA</div>")
    if text.strip(): out.append(_md_html(text))
    for name, rows in tabellen.items():
        cols = list(rows[0])
        out.append(f"<h3 style='margin:16px 0 4px;font-size:11.5pt'>{H.escape(name)} ({len(rows)})</h3>"
                   "<table style='border-collapse:collapse;font-size:9.5pt'>")
        out.append("<tr>" + "".join(f"<th style='text-align:left;border-bottom:2px solid #4F6BED;padding:3px 8px'>{H.escape(c)}</th>" for c in cols) + "</tr>")
        for i, r in enumerate(rows):
            bg = "#F3F4F6" if i % 2 else "#FFFFFF"
            fg = "#B45309" if r.get("⚠") else "#111827"
            nw = lambda c: "white-space:nowrap;" if c in ("Tag", "Zeit", "Datum", "Pers.") else ""
            out.append(f"<tr style='background:{bg};color:{fg}'>" + "".join(f"<td style='padding:3px 8px;vertical-align:top;{nw(c)}'>{H.escape(str(r.get(c, '')))}</td>" for c in cols) + "</tr>")
        out.append("</table>")
    return "".join(out) + "<p style='color:#6B7280;font-size:9pt'>— erstellt von AURA (lokal)</p></div>"

@node("mail_an_mich", "Ergebnis als Outlook-Mail an die eigene Adresse. Parameter: betreff, text, senden (false = nur Entwurf)")
def n_mail_an_mich(p, state, ctx):
    """Nur an die eigene Adresse; Standard: Entwurf im Ordner «Entwürfe» (nichts verlässt den Rechner ohne eigenen Klick)."""
    from ..connectors.base import outlook_namespace
    ns = outlook_namespace(); app = ns.Application; m = app.CreateItem(0)
    try: adr = ns.CurrentUser.AddressEntry.GetExchangeUser().PrimarySmtpAddress
    except Exception: adr = ns.CurrentUser.Name
    m.To = adr; m.Subject = as_text(p.get("betreff") or state.get("workflow", {}).get("name", "AURA"))
    m.HTMLBody = _html(_form_text(as_text(p.get("text", "")), p), _tabellen(p, state), m.Subject)   # v61/v62: gestaltetes HTML
    senden = bool(p.get("senden", False)) and str(p.get("senden")).lower() not in ("false", "nein", "0")
    if senden: m.Send(); ctx.progress(f"Mail an {adr} gesendet")
    else: m.Save(); ctx.progress(f"Mail-Entwurf an {adr} in «Entwürfe» gespeichert")
    return {"an": adr, "gesendet": senden}
