"""Acta Nova als Live-Quelle im Chat: suchen -> per Regel ranken -> Top 5 Ablageorte -> kurze LLM-Einordnung.
Ranking nur per Regel (Name, Dossier, Ordnungssystem, beide Suchen, Aktualitaet, Team, Mail-Kontakte).
Das LLM sieht nur die fertige Rangliste (Metadaten), nie Dokumentinhalte.
"""
import math, re, time
from datetime import datetime
from . import actanova, ordnungssystem as osys

AUSLOESER = re.compile(r"\b(acta\s?nova|gever|dossiers?|aktenzeichen|abgelegt|ablage|ordnungsposition|"
                       r"wo finde ich|wo liegt|wo liegen|wo ist .{0,30}(abgelegt|dokument|datei|dossier))\b", re.I)
ANDERE_QUELLE = re.compile(r"\b((?:e-?)?mails?\w*|termin\w*|kalender\w*|onenote|confluence|intranet)\b", re.I)
STOP = set("""wo was wer wie wann warum welche welcher welches finde finden ich du mir mich zu zum zur der die das den dem des
ein eine einen einer und oder in im ist sind liegt liegen gibt es informationen info infos infos thema themen zu über ueber
von vom bei mit auf für fuer acta nova gever dossier dossiers dokument dokumente datei dateien abgelegt ablage aktenzeichen
alles etwas mehr bitte muss musst müssen soll sollte sollen kann können darf dürfen habe hast hat haben
werde wird werden beim bei man beachten gilt gelten geht gehen läuft laeuft brauche braucht machen mache viele viel
wieviel wieviele tage regel regeln dazu dafür hier dort welchen welchem jetzt noch schon auch nur denn
befindet befinden sich findet findest steht stehen war waren wurde wurden wird werden heisst heißt bedeutet meint
zeige zeigen erkläre erklären gib nenne nenn liste über ueber betreffend bezüglich bzgl zum zur des dessen deren projekt projekte vorhaben geschäft geschaeft stand aktuell aktuelle kannst könntest sag zeig suche such weisst weißt wissen""".split())
AKTUELL = re.compile(r"\b(neu(e|s)?ste[nrms]?|aktuell(st)?e[nrms]?|letzte[nrms]?|jüngste[nrms]?|juengste[nrms]?|zuletzt|neu(e|en)?)\b", re.I)
DATUM = re.compile(r"\b(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?([0-3]\d)\b|\b(\d{2})(0[1-9]|1[0-2])([0-3]\d)\b")
OE = re.compile(r"\(([A-Za-z0-9]+)@")


EINGRENZUNG = re.compile(r"^\s*(?:nur|eher|in)?\s*(\d{1,4}(?:\.\d+)?)\b", re.I)


def ist_eingrenzung(frage, w):
    """Folgeantwort auf die Rueckfrage, z. B. «nur 044» -> letzte Rangliste filtern (ohne neue Suche)."""
    return bool(getattr(w, "acta_cache", None)) and bool(EINGRENZUNG.match(frage)) and len(frage.split()) <= 4


def soll_suchen(frage, settings):
    return bool(settings.get("actanova", False)) and bool(AUSLOESER.search(frage)) and not ANDERE_QUELLE.search(frage)


def suchbegriff(frage):
    """Inhaltswoerter der Frage (max. 2, Original-Schreibweise), laengste/Abkuerzungen zuerst."""
    w = [t.strip(".-") for t in re.findall(r"[\wÄÖÜäöüß\-\.]+", frage)]
    w = [t for t in w if t.lower() not in STOP and len(t) > 1 and not AKTUELL.fullmatch(t)]
    return " ".join(w[:3])                                   # Reihenfolge der Frage (z. B. «Home Office»)


def _datum(name):
    m = DATUM.search(name or "")
    if not m:
        return None
    try:
        if m.group(1):
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return datetime(2000 + int(m.group(4)), int(m.group(5)), int(m.group(6)))
    except ValueError:
        return None


def _zeilen(block):
    """Normalisiert Seite-1-Treffer bzw. Export-Zeilen."""
    roh = (block or {}).get("alle") or (block or {}).get("treffer") or []
    out = []
    for r in roh:
        name = r.get("Name") or r.get("Titel") or ""
        if r.get("Aktenzeichen") and r["Aktenzeichen"] not in name:
            name = f"{name} ({r['Aktenzeichen']})"
        dat = None
        for k in ("Geändert am/um", "Geändert am", "Erstellt am/um", "Erstellt am", "Registrierdatum", "Dokumentdatum", "Datum"):
            v = r.get(k)
            if v:
                m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", v) or re.search(r"(\d{4})-(\d{2})-(\d{2})", v)
                if m:
                    try:
                        a, b, c = (int(x) for x in m.groups())
                        dat = datetime(c, b, a) if a <= 31 and c > 1900 else datetime(a, b, c)
                        break
                    except ValueError:
                        pass
        out.append({"name": name, "container": r.get("Enthalten in", ""), "ff": r.get("Federführung", ""),
                    "status": r.get("Status") or r.get("Geschäftsobjektstatus", ""), "bem": r.get("Bemerkung", ""),
                    "datum": dat or _datum(name)})
    return out


def _ast(az):
    """'ar-044-16/3/3/2/6' -> 'ar-044-16/3/3' (Ast fuer die Gruppierung)."""
    if not az:
        return None
    kopf, _, rest = az.partition("/")
    teile = rest.split("/") if rest else []
    return "/".join([kopf] + teile[:2])


def _kontakte(conn):
    try:
        rows = conn.execute("SELECT author, COUNT(*) FROM items WHERE source='outlook_mail' AND author <> '' "
                            "GROUP BY author ORDER BY 2 DESC LIMIT 400").fetchall()
        return [(set(re.findall(r"\w{2,}", a.lower())), n) for a, n in rows]
    except Exception:
        return []


def _kontakt_bonus(ff, kontakte):
    namen = set(re.findall(r"\w{2,}", ff.split("(")[0].lower()))
    if len(namen) < 2:
        return 0.0
    for toks, n in kontakte:
        if len(namen & toks) >= 2:
            return min(1.5, 0.4 * math.log1p(n))
    return 0.0


def ranken(dossiers, dokumente, begriff, sims, eigene_oe="", kontakte=(), chrono=False):
    worte = [w.lower() for w in begriff.split()]
    sim_werte = sorted(sims.values()) if sims else []
    s_med = sim_werte[len(sim_werte) // 2] if sim_werte else 0
    s_max = sim_werte[-1] if sim_werte else 1
    jetzt = datetime.now()
    dossier_aeste = {_ast(osys.aus_aktenzeichen(d["name"])[1]) for d in dossiers}
    gruppen = {}

    def bewerten(e, art):
        pos, az = osys.aus_aktenzeichen(e["name"] if art == "dossier" else e["container"])
        if art == "dokument" and not az:
            pos, az = osys.aus_aktenzeichen(e["name"])
        n, c = e["name"].lower(), e["container"].lower()
        p = 0.0
        if worte and all(w in n for w in worte): p += 3
        elif any(w in n for w in worte): p += 1.5
        if worte and any(w in c for w in worte): p += 2
        if pos and sims and s_max > s_med:
            p += 3 * max(0.0, (max(sims.get(x, 0) for x in osys.eltern(pos)) - s_med) / (s_max - s_med))
        if art == "dokument" and _ast(az) in dossier_aeste: p += 2
        d = e.get("datum") or _datum(e["name"])
        if d:
            tage = max(0, (jetzt - d).days)
            if chrono:   # «neuste/aktuellste»: Datum ist das Hauptkriterium (bis +6, halbiert alle 90 Tage)
                p += 6 * 0.5 ** (tage / 90)
            else:
                p += 1.0 if tage < 365 else 0.5 if tage < 3 * 365 else 0
        m = OE.search(e["ff"])
        if eigene_oe and m and m.group(1)[:4].upper() == eigene_oe[:4].upper(): p += 1
        p += _kontakt_bonus(e["ff"], kontakte)
        if "storn" in e["status"].lower(): p -= 1
        return p, pos, az

    for art, liste in (("dossier", dossiers), ("dokument", dokumente)):
        for e in liste:
            p, pos, az = bewerten(e, art)
            key = _ast(az) or e["container"] or e["name"]
            g = gruppen.setdefault(key, {"ast": key, "pos": pos, "punkte": [], "dossiers": [], "dokumente": []})
            g["punkte"].append(p)
            g["dossiers" if art == "dossier" else "dokumente"].append((p, e))
            g["pos"] = g["pos"] or pos
    for g in gruppen.values():
        pk = sorted(g["punkte"], reverse=True)
        g["score"] = pk[0] + 0.3 * sum(pk[1:6])
        g["dossiers"].sort(key=lambda x: -x[0]); g["dokumente"].sort(key=lambda x: -x[0])
        daten = [e.get("datum") for _, e in g["dokumente"] + g["dossiers"] if e.get("datum")]
        g["neustes"] = max(daten) if daten else None
        if g["dossiers"]:
            g["label"] = g["dossiers"][0][1]["name"]
        else:
            g["label"] = g["dokumente"][0][1]["container"] or g["ast"]
    return sorted(gruppen.values(), key=lambda g: -g["score"])


def _titel_az(text):
    """'Titel (ar-044-16/3/3)' -> ('Titel', 'ar-044-16/3/3')"""
    m = re.search(r"\s*\(([a-z]{1,8}-[\d.]+-[\d/]+)\)\s*$", text or "")
    return (text[:m.start()].strip(), m.group(1)) if m else ((text or "").strip(), "")


def _os_kurz(pos):
    """Nur die tiefste Position: '213.11 Titel' statt des ganzen Pfads."""
    return f"{pos} {osys.positionen().get(pos, '')}".strip() if pos else ""


def _liste(top):
    bloecke = []
    for i, g in enumerate(top, 1):
        titel, az = _titel_az(g["label"])
        z = [f"{i}  {titel}"]
        info = "  ·  ".join(x for x in (az, _os_kurz(g["pos"])) if x)
        if info: z.append(f"   {info}")
        for _, d in g["dokumente"][:2]:
            dn, _ = _titel_az(d["name"])
            z.append(f"   → {dn}" + (f"  ({d['datum']:%d.%m.%Y})" if d.get("datum") else ""))
        n_dok = len(g["dokumente"])
        if n_dok > 2: z.append(f"   + {n_dok - 2} weitere Dokumente")
        bloecke.append("\n".join(z))
    return "\n\n".join(bloecke)


def _rueckfrage(gruppen, total_voll):
    """Rueckfrage, wenn die besten Aeste in verschiedenen Hauptbereichen liegen und knapp beieinander sind."""
    if len(gruppen) < 2:
        return ""
    a, b = gruppen[0], gruppen[1]
    knapp = b["score"] >= 0.85 * a["score"]
    if not (knapp or total_voll):
        return ""
    opts, seen = [], set()
    for g in gruppen[:6]:
        if g["pos"] and g["pos"][:3] not in seen:
            seen.add(g["pos"][:3]); opts.append(f"{osys.eltern(g['pos'])[-1]} {osys.positionen()[osys.eltern(g['pos'])[-1]]}")
    if len(opts) < 2:
        return ""
    return ("\n\nZum Eingrenzen: Geht es eher um " + ", ".join(f"«{o}»" for o in opts[:3]) +
            "? Antworte z. B. «nur 044» oder nenne Team/Zeitraum.")


def antworten(w, asked, backend_id, prev, ref, t0):
    """Wird von Worker.job_ask aufgerufen. w = Worker."""
    from ..config import load_settings
    s = load_settings()
    w.emit("answer_start", asked, "actanova", ref)
    if ist_eingrenzung(asked, w):
        pos = EINGRENZUNG.match(asked).group(1)
        c = w.acta_cache
        gef = [g for g in c["gruppen"] if g["pos"] and g["pos"].startswith(pos)]
        txt = (f"Eingegrenzt auf {pos} {osys.positionen().get(pos, '')} ({len(gef)} von {len(c['gruppen'])} Ablageorten, "
               f"Suche «{c['begriff']}»):\n\n" + (_liste(gef[:5]) if gef else "Keine Ablageorte in dieser Position."))
        w.emit("token", txt)
        w.emit("sources", [], {"total": time.perf_counter() - t0, "list": True})
        w.progress("Fertig (Acta Nova, eingegrenzt)"); return
    begriff = suchbegriff(asked)
    if not begriff:
        w.emit("token", "Für die Acta-Nova-Suche fehlt ein Suchbegriff (z. B. «Wo finde ich Infos zur GPK?»).")
        w.emit("sources", [], {"total": time.perf_counter() - t0, "list": True}); return
    c = getattr(w, "acta_cache", None)
    if c and c.get("begriff") == begriff and time.time() - c.get("t", 0) < 600:     # 10 min Zwischenspeicher
        dos, dok, eigene_oe = c["dos"], c["dok"], c["oe"]
        w.progress(f"Acta Nova: «{begriff}» aus Zwischenspeicher")
    else:
        dos = None
    try:
        if dos is not None: raise StopIteration
        actanova._log(f"chat '{begriff}' start")                                   # v222: Wegmarken fuer Haenger
        if not actanova.SPERRE.acquire(timeout=30):
            actanova._log("Sperre seit 30 s belegt (alter Lauf/Wachhalten haengt) – wird freigegeben")
            try: actanova.SPERRE.release()
            except RuntimeError: pass
            actanova.SPERRE.acquire(timeout=5)
        actanova._log("Sperre ok")
        w.progress(f"Acta Nova: suche «{begriff}» (Dossiers + Volltext) …")
        for versuch in (1, 2):                                   # v221: ganzer Ablauf einmal wiederholen, Fehler protokollieren
            try:
                tab = actanova.verbinden(); actanova._log("verbunden")
                eigene_oe = (actanova._js(tab, "const m = (document.body.innerText||'').match(/\\(([A-Za-z0-9]+)@[A-Za-z0-9.]+\\)/); return m ? m[1] : '';") or "")
                prot = []
                dos = actanova._suchen(tab, "dossier", None, "titel", begriff, prot, export=True); actanova._log("dossiers ok")
                time.sleep(actanova.MIN_ABSTAND)
                dok = actanova._suchen(tab, "dokument", "tab_inhalt", "inhalt", begriff, prot, export=True)
                break
            except Exception as x:
                actanova._log(f"chat '{begriff}' FEHLER Versuch {versuch}: {type(x).__name__}: {str(x)[:200]}")
                if versuch == 2 or w.cancel.is_set(): raise
                w.progress("Acta Nova: zweiter Versuch …")
                try: tab.navigieren(actanova.start_url(), "actanova")
                except Exception: pass
                time.sleep(3)
        actanova._log(f"chat '{begriff}' -> dossiers {dos.get('anzahl')}, dokumente {dok.get('anzahl')}; {'; '.join(prot)}")
        actanova.SPERRE.release()
    except StopIteration:
        pass
    except Exception as e:
        if actanova.SPERRE.locked():
            try: actanova.SPERRE.release()
            except RuntimeError: pass
        w.emit("token", f"Acta Nova nicht erreichbar: {e}\nBitte das Edge-Fenster öffnen und mit Karte/PIN anmelden, dann nochmals fragen.")
        w.emit("sources", [], {"total": time.perf_counter() - t0, "list": True}); return
    t_rang = time.perf_counter()
    w.progress("Acta Nova: Treffer gewichten …")
    try: emb = w._embedder()
    except Exception: emb = None
    sims = osys.aehnlichkeit(emb, asked)
    chrono = bool(AKTUELL.search(asked))
    gruppen = ranken(_zeilen(dos), _zeilen(dok), begriff, sims, eigene_oe, _kontakte(w.conn), chrono)
    top = gruppen[:5]
    w.acta_cache = {"begriff": begriff, "gruppen": gruppen, "dos": dos, "dok": dok, "oe": eigene_oe,
                    "t": (c or {}).get("t", time.time()) if c and c.get("begriff") == begriff else time.time()}
    actanova._diag(f"rang {time.perf_counter() - t_rang:.1f}s gruppen={len(gruppen)}")
    voll = (dos.get("anzahl") or 0) >= 200 or (dok.get("anzahl") or 0) >= 200
    liste = _liste(top) if top else "Keine Treffer in Acta Nova."
    if chrono:
        docs = sorted([e for e in _zeilen(dok) if e.get("datum")], key=lambda e: e["datum"], reverse=True)[:5]
        if docs:
            liste = ("NEUESTE DOKUMENTE\n" + "\n".join(
                f"{e['datum']:%d.%m.%Y}  {_titel_az(e['name'])[0]}\n            in {_titel_az(e['container'])[0] or '?'}"
                for e in docs) + "\n\nABLAGEORTE (nach Aktualität gewichtet)\n\n" + liste)
    kopf = (f"{dos.get('anzahl') or 0} Dossiers und {dok.get('anzahl') or 0} Dokumente zu «{begriff}» – "
            f"die {len(top)} passendsten von {len(gruppen)} Ablageorten:")
    t_search = time.perf_counter() - t0
    if top and backend_id != "extractive" and s.get("actanova_llm", False):   # Einordnung nur, wenn eingeschaltet
        hits = [{"title": g["label"], "source": "actanova", "ts": "", "author": "", "item_id": None, "chunk_id": None,
                 "location": osys.pfad(g["pos"]) if g["pos"] else "",
                 "text": f"Rang {i}. Ablageort: {g['label']}. Ordnungssystem: {osys.pfad(g['pos']) if g['pos'] else '-'}. "
                         f"Dokumente: " + "; ".join(d["name"] for _, d in g["dokumente"][:4])}
                for i, g in enumerate(top, 1)]
        q = (f"{asked}\n(Die Quellen sind eine nach Regeln gewichtete Rangliste von Ablageorten in Acta Nova, nur Titel, "
             f"keine Inhalte. Sage in höchstens 3 Sätzen, wo das Thema hauptsächlich liegt und welchen Ablageort man zuerst "
             f"öffnen sollte. Nenne nur Ablageorte aus den Quellen, mit Aktenzeichen. Behaupte nichts über Inhalte.)")
        try:
            be = w._llm(backend_id); be.settings = dict(s, llm_top_k=len(hits), leer_satz="Dazu finde ich in Acta Nova nichts."); be.used = None
            be.generate(q, hits, lambda t: w.emit("token", t), w.cancel.is_set)
            w.emit("token", "\n\n")
        except Exception as e:
            w.progress(f"Sprachmodell übersprungen: {e}")
        actanova._diag(f"llm {time.perf_counter() - t0 - t_search:.1f}s")
    ablage = ""
    if sims:                                   # Ablageberatung: passendste Positionen (tiefste Ebene) laut Ordnungssystem
        blatt = {az: v for az, v in sims.items() if not any(x != az and x.startswith(az) for x in sims)}
        best = sorted(blatt.items(), key=lambda x: -x[1])[:3]
        if best:
            ablage = "\n\nABLAGE GEMÄSS ORDNUNGSSYSTEM (für Neues zum Thema)\n" + "\n".join(
                f"   {az}  {osys.positionen().get(az, '')}" for az, _ in best)
    w.emit("token", kopf + "\n\n" + liste + ablage + _rueckfrage(gruppen, voll))
    # v228: Text (nur Metadaten) mitgeben, damit die Zusammenfassung über alle Quellen die Ablageorte kennt
    quellen = [{"title": g["label"], "source": "actanova", "ts": "",
                "item_id": "acta:" + (osys.aus_aktenzeichen(g["label"])[1] or g["ast"] or g["label"]), "chunk_id": None,
                "location": osys.pfad(g["pos"]) if g["pos"] else "",
                "text": (f"Ablageort in Acta Nova, Rang {i} von {len(gruppen)} (nach Regeln gewichtet): {g['label']}. "
                         f"Ordnungssystem: {osys.pfad(g['pos']) if g['pos'] else '-'}. Enthaltene Dokumente: "
                         + ("; ".join(_titel_az(d["name"])[0] for _, d in g["dokumente"][:4]) or "keine")
                         + ". (Nur Titel, keine Inhalte.)")} for i, g in enumerate(top, 1)]
    if ablage:
        quellen.insert(0, {"title": "Ablagevorschlag gemäss Ordnungssystem", "source": "actanova", "ts": "", "item_id": "acta:" + best[0][0],
                           "chunk_id": None, "location": "",
                           "text": "Passendste Ordnungspositionen für neue Unterlagen zum Thema: " + "; ".join(
                               f"{az} {osys.positionen().get(az, '')}" for az, _ in best)})
    w.emit("sources", quellen, {"search": t_search, "total": time.perf_counter() - t0, "list": backend_id == "extractive"})
    w.chat = {"qs": (prev + [asked])[-3:], "hits": [], "t": time.time()}
    w.progress(f"Fertig (Acta Nova, {len(gruppen)} Ablageorte)")
