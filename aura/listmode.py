# aura/listmode.py — Listen-Antworten ohne Sprachmodell (Version 20261011v47; v46: Mails im Zeitraum «heute erhalten»)
# «Welche Termine habe ich diese Woche?» / «Alle Mails von X» brauchen kein LLM: vollstaendig, korrekt, < 1 s.
import json, re
from datetime import datetime, timedelta

WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
WD_LONG = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MAX = 40

def now_text(now=None):
    n = now or datetime.now()
    return f"{WD_LONG[n.weekday()]}, {n:%d.%m.%Y}, {n:%H:%M} Uhr"

def _dt(s):
    if not s: return None
    try: return datetime.fromisoformat(str(s).strip().replace("T", " ")[:19])
    except ValueError:
        try: return datetime.strptime(str(s)[:10], "%Y-%m-%d")
        except ValueError: return None

def date_range(q, now=None):
    """Erkennt einen Zeitraum in der Frage -> (start, ende_exklusiv, Bezeichnung) oder None."""
    n = now or datetime.now(); d0 = n.replace(hour=0, minute=0, second=0, microsecond=0)
    q = q.lower(); mon = d0 - timedelta(days=d0.weekday())
    if "übermorgen" in q or "uebermorgen" in q: return d0 + timedelta(2), d0 + timedelta(3), "übermorgen"
    if "morgen" in q and "heute morgen" not in q: return d0 + timedelta(1), d0 + timedelta(2), "morgen"
    if "heute" in q: return d0, d0 + timedelta(1), "heute"
    if re.search(r"n[äa]e?chste[nr]?\s+woche", q): return mon + timedelta(7), mon + timedelta(14), "nächste Woche"
    if re.search(r"(letzte[nr]?|vergangene[nr]?|vorige[nr]?)\s+woche", q): return mon - timedelta(7), mon, "letzte Woche"
    if re.search(r"(diese[nr]?|kommende[nr]?)\s+woche|\bwoche\b", q): return mon, mon + timedelta(7), "diese Woche"
    first = d0.replace(day=1); nxt = (first + timedelta(32)).replace(day=1)
    if re.search(r"n[äa]e?chste[nr]?\s+monat", q): return nxt, (nxt + timedelta(32)).replace(day=1), "nächster Monat"
    if re.search(r"(diese[nr]?|im)\s+monat", q): return first, nxt, "dieser Monat"
    if re.search(r"\b(demn[äa]chst|anstehend|bevorstehend|n[äa]chsten tage)\b", q): return n, d0 + timedelta(8), "nächste 7 Tage"
    return None

CAL_WORDS = re.compile(r"\b(termin\w*|meeting\w*|sitzung\w*|kalender|agenda|besprechung\w*)\b", re.I)
CONTENT = re.compile(r"\b(worum|warum|wieso|inhalt|agenda von|traktand\w*|vorbereiten|zusammenfass\w*|was steht)\b", re.I)
MAIL_LIST = re.compile(r"\b(alle|liste|auflisten|zeig\w*)\b.*\b(mails?|nachrichten)\b", re.I)

def calendar_list(conn, q, items=None, now=None):
    """Liefert (text, hits) oder None, wenn die Frage keine Terminliste ist."""
    if not CAL_WORDS.search(q) or CONTENT.search(q): return None
    rg = date_range(q, now)
    if not rg: return None
    n = now or datetime.now(); start, end, label = rg
    sql = ("SELECT id, title, ts, location, meta FROM items WHERE source = 'outlook_calendar' "
           "AND ts >= ? AND ts < ?")
    args = [start.strftime("%Y-%m-%d"), (end + timedelta(days=1)).strftime("%Y-%m-%d")]   # grob, danach exakt
    if items is not None:
        if not items: return f"Keine Termine {label} für diese Person.", []
        sql += f" AND id IN ({','.join(str(int(i)) for i in items)})"
    rows = []
    for iid, title, ts, loc, meta in conn.execute(sql + " ORDER BY ts", args):
        st = _dt(ts)
        if not st or not (start <= st < end): continue
        try: m = json.loads(meta or "{}")
        except Exception: m = {}
        en = _dt(m.get("end")) or st
        rows.append((iid, title or "(ohne Titel)", ts, st, en, loc or ""))
    if not rows:
        return f"Keine Termine {label} ({start:%d.%m.}–{(end - timedelta(1)):%d.%m.}). Jetzt: {now_text(n)}.", []
    hits = []
    for iid, title, ts, st, en, loc in rows[:MAX]:
        allday = st.hour == st.minute == 0 and (en - st) >= timedelta(hours=23)
        when = "ganztägig" if allday else f"{st:%H:%M}–{en:%H:%M}"
        state = "läuft" if st <= n < en else ("vorbei" if en <= n else "")
        lab = f"{WD[st.weekday()]} {st:%d.%m.}  {when}  ·  {title[:70]}" + (f"  ·  {loc[:30]}" if loc else "")
        hits.append({"item_id": iid, "ts": ts, "source": "outlook_calendar", "title": title, "text": "",
                     "label": lab, "state": state})
    past = sum(1 for h in hits if h["state"] == "vorbei"); cur = [h for h in hits if h["state"] == "läuft"]
    up = [h for h in hits if not h["state"]]
    span = f"{start:%d.%m.}" if end - start <= timedelta(days=1) else f"{start:%d.%m.}–{(end - timedelta(1)):%d.%m.}"
    txt = (f"{label[0].upper() + label[1:]} ({span}): {len(rows)} Termin{'' if len(rows) == 1 else 'e'}"
           + (f", {past} davon bereits vorbei" if past else "") + ".")
    if cur: txt += f"\nGerade läuft: {cur[0]['title']}."
    if up: txt += f"\nAls Nächstes: {up[0]['label']}."
    elif not cur: txt += "\nKeine weiteren Termine in diesem Zeitraum."
    if len(rows) > MAX: txt += f"\n(Nur die ersten {MAX} angezeigt.)"
    txt += f"\nJetzt: {now_text(n)}."
    return txt, hits

def mail_list(conn, q, who):
    """«Alle Mails von X» -> neueste 25 Mails dieser Person. who = (item_ids, names) aus Retriever.author_items."""
    if not who or not MAIL_LIST.search(q): return None
    ids = ",".join(str(int(i)) for i in who[0])
    rows = conn.execute(f"SELECT id, title, ts FROM items WHERE source = 'outlook_mail' AND id IN ({ids}) "
                        "ORDER BY ts DESC LIMIT 25").fetchall()
    total = conn.execute(f"SELECT COUNT(*) FROM items WHERE source = 'outlook_mail' AND id IN ({ids})").fetchone()[0]
    hits = [{"item_id": i, "ts": ts or "", "source": "outlook_mail", "title": t or "", "text": "",
             "label": f"{(ts or '')[:10]}  ·  {(t or '(ohne Betreff)')[:90]}"} for i, t, ts in rows]
    txt = f"{total} Mails von {' '.join(who[1])}" + (f", die neuesten {len(hits)}:" if total > len(hits) else ":")
    return txt, hits

# ---------------------------------------------------------------- v18: Person/Thema statt nur Absender
STOP = {"welche", "welcher", "welches", "wann", "was", "wer", "wie", "ist", "sind", "das", "der", "die", "den", "dem",
        "des", "ein", "eine", "einen", "mit", "von", "an", "und", "oder", "mir", "mich", "ich", "du", "habe", "hast",
        "haben", "hat", "nenne", "zeige", "zeig", "liste", "alle", "letzte", "letzten", "letzter", "neueste", "neuesten",
        "jüngste", "jüngsten", "zuletzt", "nächste", "nächsten", "nächster", "nächstes", "naechste", "kommende",
        "kommenden", "mails", "mail", "nachrichten", "nachricht", "termin", "termine", "meeting", "meetings",
        "sitzung", "sitzungen", "besprechung", "treffen", "findet", "statt", "gibt", "es", "bitte", "zum", "zur", "im",
        "am", "bei", "für", "fuer", "geschrieben", "geschickt", "bekommen", "erhalten", "gesendet", "wieder",
        # v46: Zeitwoerter sind keine Personen/Themen (sonst filtert «heute» nach Betreff «heute»)
        "heute", "gestern", "vorgestern", "morgen", "übermorgen", "woche", "diese", "dieser", "diesem", "diesen",
        "monat", "neue", "neuen", "eingegangen", "gekommen", "welchen", "e-mails", "e-mail"}
NEXT_EV = re.compile(r"\b(n[äa]e?chste[nrs]?|kommende[nrs]?|bevorstehende[nrs]?)\b.*"
                     r"\b(termin\w*|meeting\w*|sitzung\w*|besprechung\w*|treffen|call)\b"
                     r"|\bwann\b.*\b(n[äa]e?chste[nrs]?|wieder)\b", re.I)          # «Wann ist das nächste TRILA?»
LAST_MAIL = re.compile(r"\b(letzte[nr]?|neueste[nr]?|j[üu]ngste[nr]?|alle|zuletzt|liste|zeig\w*)\b.*\b(mails?|nachrichten)\b"
                       r"|\b(mails?|nachrichten)\b.*\b(zuletzt|neueste|letzte)\b", re.I)
# v46: «Welche Mails habe ich heute erhalten?» / «Mails diese Woche bekommen»
MAIL_RANGE = re.compile(r"\b(welche|alle|liste|auflisten|zeig\w*|nenne|neue)\b.*\b(e-?mails?|mails?|nachrichten)\b"
                        r"|\b(e-?mails?|mails?|nachrichten)\b.*\b(erhalten|bekommen|eingegangen|gekommen)\b", re.I)

def _terms(q):
    return [w for w in re.findall(r"[^\W\d_][\w\-]{2,}", q) if w.lower() not in STOP]

def _person_or_topic(conn, q, source):
    """Begriffe der Frage -> SQL-Bedingung. Kommt ein Begriff in Absender/Empfaengern vor, gilt er als Person,
    sonst als Thema (Titel). Liefert (where, args, beschreibung) oder None."""
    conds, args, desc = [], [], []
    for w in _terms(q):
        like = f"%{w}%"
        if conn.execute(f"SELECT 1 FROM items WHERE source = ? AND (author LIKE ? OR recipients LIKE ?) LIMIT 1",
                        (source, like, like)).fetchone():
            conds.append("(author LIKE ? OR recipients LIKE ?)"); args += [like, like]; desc.append(w)
        elif conn.execute("SELECT 1 FROM items WHERE source = ? AND title LIKE ? LIMIT 1", (source, like)).fetchone():
            conds.append("title LIKE ?"); args.append(like); desc.append(f"«{w}»")
    return (" AND ".join(conds), args, " ".join(desc)) if conds else None

def next_events(conn, q, now=None, n=5):
    """«Wann ist das nächste Meeting mit X / das nächste TRILA?» -> die naechsten n Termine ab jetzt."""
    if not NEXT_EV.search(q) or date_range(q, now) or CONTENT.search(q): return None
    f = _person_or_topic(conn, q, "outlook_calendar")
    if not f: return None
    now = now or datetime.now()
    rows = conn.execute(f"SELECT id, title, ts, location, meta FROM items WHERE source = 'outlook_calendar' AND {f[0]} "
                        "AND ts >= ? ORDER BY ts LIMIT ?", f[1] + [(now - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M"), n + 5]).fetchall()
    hits = []
    for iid, title, ts, loc, meta in rows:
        st = _dt(ts)
        try: en = _dt(json.loads(meta or "{}").get("end")) or st
        except Exception: en = st
        if not st or en <= now: continue                       # schon vorbei
        state = "läuft" if st <= now else ""
        hits.append({"item_id": iid, "ts": ts, "source": "outlook_calendar", "title": title or "", "text": "", "state": state,
                     "label": f"{WD[st.weekday()]} {st:%d.%m.%Y}  {st:%H:%M}–{en:%H:%M}  ·  {(title or '')[:70]}"
                              + (f"  ·  {loc[:30]}" if loc else "")})
        if len(hits) >= n: break
    if not hits:
        last = conn.execute(f"SELECT ts, title FROM items WHERE source = 'outlook_calendar' AND {f[0]} AND ts < ? "
                            "ORDER BY ts DESC LIMIT 1", f[1] + [now.strftime("%Y-%m-%d %H:%M")]).fetchone()
        txt = f"Kein kommender Termin mit {f[2]} im Kalender."
        if last: txt += f" Der letzte war am {_dt(last[0]):%d.%m.%Y} ({last[1]})."
        return txt + f"\nJetzt: {now_text(now)}.", []
    h = hits[0]; st = _dt(h["ts"])
    days = (st.date() - now.date()).days
    when = "heute" if days == 0 else "morgen" if days == 1 else f"in {days} Tagen"
    return (f"Nächster Termin mit {f[2]}: {WD_LONG[st.weekday()]}, {st:%d.%m.%Y}, {st:%H:%M} Uhr ({when}) – {h['title']}."
            + f"\nJetzt: {now_text(now)}."), hits

def recent_mails(conn, q, n=15, now=None):
    """«Nenne die letzten Mails mit/von X» -> neueste Mails, X als Absender ODER Empfaenger (oder Betreff).
    v46: «Welche Mails habe ich heute erhalten?» -> alle Mails im Zeitraum, mit oder ohne Person/Thema."""
    if CONTENT.search(q): return None
    rg = date_range(q, now) if MAIL_RANGE.search(q) else None
    if not rg and not LAST_MAIL.search(q): return None
    f = _person_or_topic(conn, q, "outlook_mail")
    if not f and not rg: return None
    where, args, desc = f if f else ("1 = 1", [], "")
    args = list(args)
    if rg:
        where += " AND ts >= ? AND ts < ?"
        args += [rg[0].strftime("%Y-%m-%d %H:%M"), rg[1].strftime("%Y-%m-%d %H:%M")]
        n = MAX
    rows = conn.execute(f"SELECT id, title, ts, author FROM items WHERE source = 'outlook_mail' AND {where} "
                        "ORDER BY ts DESC LIMIT ?", args + [n]).fetchall()
    total = conn.execute(f"SELECT COUNT(*) FROM items WHERE source = 'outlook_mail' AND {where}", args).fetchone()[0]
    oneday = bool(rg) and rg[1] - rg[0] <= timedelta(days=1)

    def when(ts):
        st = _dt(ts)
        if not rg or not st: return (ts or "")[:10]
        return f"{st:%H:%M}" if oneday else f"{WD[st.weekday()]} {st:%d.%m. %H:%M}"
    hits = [{"item_id": i, "ts": ts or "", "source": "outlook_mail", "title": t or "", "text": "",
             "label": f"{when(ts)}  ·  {(a or '')[:25]}  ·  {(t or '(ohne Betreff)')[:80]}"} for i, t, ts, a in rows]
    if rg:
        span = f"{rg[0]:%d.%m.}" if oneday else f"{rg[0]:%d.%m.}–{(rg[1] - timedelta(1)):%d.%m.}"
        head = f"{total} Mail{'' if total == 1 else 's'} {rg[2]} ({span})" + (f" mit {desc}" if desc else "")
        if not total: return head + f". Jetzt: {now_text(now)}.", []
    else:
        head = f"{total} Mails mit {desc}"
    return head + (f", die neuesten {len(hits)}:" if total > len(hits) else ":"), hits

# ---------------------------------------------------------------- v21: Edge-Verlauf als Liste
WEB = re.compile(r"\b(webseiten?|websites?|links?|urls?|verlauf|edge|browser|besucht\w*|gesurft|aufgerufen|angeschaut)\b"
                 r"|\bwelche\s+seiten\b|\bseiten\s+(zu|über|ueber|von|mit|auf)\b", re.I)
WEB_STOP = STOP | {"seite", "seiten", "webseite", "webseiten", "website", "websites", "link", "links", "url", "urls",
                   "verlauf", "besucht", "besuchte", "besuchten", "gesurft", "aufgerufen", "geöffnet", "geoeffnet",
                   "gestern", "heute", "vorgestern", "woche", "diese", "dieser", "letzte", "vergangene", "monat",
                   "über", "ueber", "thema", "internet", "edge", "browser", "wurde", "wurden", "worden", "wird",
                   "werden", "nach", "welchen", "welchem", "habe", "hatte", "hast", "zuletzt", "mal", "schon",
                   "gesucht", "suche", "gegoogelt", "letzten", "letztes", "jemals", "genau", "uhr"}
SEARCHQ = re.compile(r"\b(gesucht|gegoogelt|suchbegriffe?|wonach|recherchiert)\b", re.I)

def web_list(conn, q, now=None, n=25):
    """«Welche Seiten habe ich gestern besucht?» / «Seiten zu GEVER» -> Liste aus dem Edge-Verlauf.
    Achtung: Zeit = LETZTER Besuch einer Seite (frueher besuchte, spaeter erneut geoeffnete Seiten zaehlen spaet)."""
    if not (WEB.search(q) or SEARCHQ.search(q)) or CONTENT.search(q): return None
    if not conn.execute("SELECT 1 FROM items WHERE source = 'edge_history' LIMIT 1").fetchone():
        return "Der Edge-Verlauf ist noch nicht synchronisiert (Quellen → Edge-Verlauf → Sync).", []
    rg = date_range(q, now)
    if rg is None and re.search(r"\bvorgestern\b", q, re.I):
        d0 = (now or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
        rg = (d0 - timedelta(2), d0 - timedelta(1), "vorgestern")
    if rg is None and re.search(r"\bgestern\b", q, re.I):
        d0 = (now or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
        rg = (d0 - timedelta(1), d0, "gestern")
    words = [w for w in re.findall(r"[^\W_][\w\-\.]{1,}", q) if w.lower() not in WEB_STOP and len(w) > 2]
    # Woerter ohne einzigen Treffer weglassen (z.B. Fuellwoerter, die in keiner Stoppliste stehen)
    words = [w for w in words if conn.execute(
        "SELECT 1 FROM items WHERE source = 'edge_history' AND (title LIKE ? OR ext_id LIKE ? OR body LIKE ?) LIMIT 1",
        [f"%{w}%"] * 3).fetchone()]
    if SEARCHQ.search(q): return search_terms(conn, rg, words, now)
    sql, args = "SELECT id, title, ts, author, meta FROM items WHERE source = 'edge_history'", []
    for w in words:
        sql += " AND (title LIKE ? OR ext_id LIKE ? OR body LIKE ?)"; args += [f"%{w}%"] * 3
    if rg:
        sql += " AND ts >= ? AND ts < ?"; args += [rg[0].strftime("%Y-%m-%d %H:%M"), rg[1].strftime("%Y-%m-%d %H:%M")]
    if not words and not rg: return None                       # zu unbestimmt -> normale Suche
    total = conn.execute(sql.replace("id, title, ts, author, meta", "COUNT(*)"), args).fetchone()[0]
    rows = conn.execute(sql + " ORDER BY ts DESC LIMIT ?", args + [n]).fetchall()
    hits = []
    for iid, title, ts, host, meta in rows:
        try: v = json.loads(meta or "{}").get("visits", 1)
        except Exception: v = 1
        st = _dt(ts)
        hits.append({"item_id": iid, "ts": ts or "", "source": "edge_history", "title": title or "", "text": "",
                     "label": f"{st:%d.%m. %H:%M}  ·  {(host or '')[:30]}  ·  {(title or '')[:80]}" + (f"  ({v}×)" if v > 1 else "")
                     if st else (title or "")[:90]})
    what = " ".join(f"«{w}»" for w in words)
    head = f"{total} Seite{'' if total == 1 else 'n'}" + (f" zu {what}" if words else "") + (f", zuletzt besucht {rg[2]}" if rg else "")
    if not hits: return head + ". (Zeitangabe = letzter Besuch einer Seite.)", []
    return head + (f", die neuesten {len(hits)}" if total > len(hits) else "") + ":", hits

def search_terms(conn, rg, words, now=None, n=40):
    """«Wonach habe ich gesucht?» -> Suchbegriffe aus dem Edge-Verlauf (Google, Bing, …), neueste zuerst."""
    sql = ("SELECT id, title, ts, body FROM items WHERE source = 'edge_history' AND (body LIKE '%Suchbegriff:%' "
           "OR title LIKE '% - Google Suche' OR title LIKE '% - Google Search' OR title LIKE '% - Suche' OR title LIKE '% - Bing')")
    args = []
    for w in words: sql += " AND (title LIKE ? OR body LIKE ?)"; args += [f"%{w}%"] * 2
    if rg: sql += " AND ts >= ? AND ts < ?"; args += [rg[0].strftime("%Y-%m-%d %H:%M"), rg[1].strftime("%Y-%m-%d %H:%M")]
    hits, seen = [], set()
    for iid, title, ts, body in conn.execute(sql + " ORDER BY ts DESC LIMIT 300", args):
        m = re.search(r"Suchbegriff:\s*(.+)", body or "")
        term = (m.group(1) if m else re.sub(r"\s+-\s+(Google Suche|Google Search|Suche|Bing)$", "", title or "")).strip()
        key = term.lower().strip('"')
        if not term or key in seen: continue
        seen.add(key); st = _dt(ts)
        hits.append({"item_id": iid, "ts": ts or "", "source": "edge_history", "title": term, "text": "",
                     "label": f"{st:%d.%m. %H:%M}  ·  {term[:90]}" if st else term[:90]})
        if len(hits) >= n: break
    head = f"{len(hits)} Suchbegriffe" + (f" {rg[2]}" if rg else "") + (" (neueste zuerst)" if hits else "") + ":"
    if not hits: head = "Keine Suchbegriffe gefunden" + (f" ({rg[2]})" if rg else "") + "."
    return head + "\n(Ob ein Begriff eine Person ist, erkennt AURA nicht – die Liste zeigt alle Suchen.)", hits
