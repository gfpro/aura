# aura/praesentation.py — Präsentation aus einem Text (Anhang im Chat). Version 20261031v156
# Grundsatz wie bei den Workflows: Der Code entscheidet, das Sprachmodell verdichtet nur.
#   1. Gliederung OHNE Modell: Überschriften im Text (nummeriert, «#», kurze Zeilen vor einem Absatz), sonst Blöcke à ~1800 Zeichen.
#   2. Je Abschnitt füllt das Modell feste Felder: Titel, Folienart (Aufzählung / Gegenüberstellung / Kernaussage), 2–4 Stichpunkte.
#      Leitplanken ohne Modell: Stichpunkte mit Zahlen, die im Abschnitt nicht vorkommen, werden verworfen; zu lange gekürzt;
#      Doppelte entfernt; unvollständige Gegenüberstellung oder Kernaussage → Aufzählung.
#   3. Titelfolie, Agenda und Fazit setzt AURA zusammen; Ausgabe über pptx_bau.py in die Vorlage (Standard: Bundesverwaltung 16:9).
# Einstellungen (data\settings.json): praes_vorlage (Pfad .pptx), praes_9b (true = grösseres Modell verwenden, falls vorhanden),
# praes_max_folien (Standard 10 Inhaltsfolien).
import re, time
from datetime import date
from pathlib import Path
from .config import ROOT, DATA, load_settings

VORLAGE = ROOT / "aura" / "assets" / "Praesentation_16-9.pptx"
ZIEL_DIR = DATA / "praesentationen"
WUNSCH = re.compile(r"\b(pr[äa]sentation\w*|folien\w*|powerpoint|pptx|slides?|foliens[äa]tz\w*)\b", re.I)

SYSTEM = ("Du machst aus einem Textabschnitt eine Folie für eine Präsentation. Verdichte – schreibe nicht ab: "
          "Stichpunkte mit höchstens 12 Wörtern, ein Gedanke pro Stichpunkt (kein Semikolon), keine ganzen Sätze, keine Einleitung. Nenne Kernaussagen und Folgen – "
          "was gilt, was ist zu tun, wo liegt das Risiko – statt zu beschreiben, wovon der Text handelt. "
          "Gibt es Unterkapitel (##), decke möglichst jedes mit einem Stichpunkt ab. Nur was im Abschnitt steht; "
          "keine Zahlen, Namen oder Daten erfinden. Schweizer Rechtschreibung (ss statt ß).")
ARTEN = ["Aufzählung", "Gegenüberstellung", "Kernaussage"]


# ------------------------------------------------------------------ 1. Gliederung (ohne Modell)
# v153: Nummerierte Überschriften werden nur akzeptiert, wenn die Nummer in die Folge passt (1 → 1.1 → 1.2 → 2 …, Neubeginn
# bei 1 für «Teil 2»). Fussnoten («12 Siehe …») und Seitenköpfe fallen so heraus; das Inhaltsverzeichnis wird übersprungen.
_KAND = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+([A-ZÄÖÜ«(][^\n]{1,85})$")
_FUSS = re.compile(r"^(vgl|siehe|so |z\.\s?b|art\.|sr |bbl|insbesondere|https?|www\.|ob |eine |die definition|bisweilen|"
                   r"allerdings|unter |es ist|zur |zum |a\.m\.|u\.e\.)", re.I)


def _kopfzeilen(zeilen):
    """Zeilen, die oft wörtlich wiederkehren (Seitenkopf/-fuss), z.B. «Bundeskanzlei BK»."""
    from collections import Counter
    c = Counter(z.strip() for z in zeilen if 2 < len(z.strip()) < 60)
    return {z for z, n in c.items() if n >= 4}


def _kandidaten(zeilen):
    out = []
    for i, z in enumerate(zeilen):
        m = _KAND.match(z)
        if not m: continue
        nr, titel = m.group(1), re.sub(r"\s*\.{2,}.*$|\s+\d{1,3}$", "", m.group(2)).strip()   # TOC-Punkte, Fussnotenziffer
        if not titel or titel.endswith((".", ",", ";")) or _FUSS.match(titel) or len(titel.split()) > 12: continue
        if re.search(r"\b(des|der|die|den|dem|und|für|von|zur|zum|im|in|mit|bei|über|auf)$", titel) and i + 1 < len(zeilen):
            nxt = zeilen[i + 1].strip().split()                          # v154: umbrochene Überschrift («… des» / «Bundes»)
            if nxt and nxt[0][:1].isupper(): titel += " " + nxt[0]
        out.append((i, tuple(int(x) for x in nr.split(".")), titel))
    return out


def _folge(kand):
    """Nur Überschriften, deren Nummer auf die vorige folgt. Liefert [(zeile, nummer, titel)]."""
    ok, cur = [], ()
    for i, n, t in kand:
        erlaubt = n == cur + (1,) or n == (1,) or any(n == cur[:k] + (cur[k] + 1,) for k in range(len(cur)))
        if erlaubt: ok.append((i, n, t)); cur = n
    return ok


def gliedern(text, max_abschnitte=10):
    """[(titel, inhalt)] – Kapitel aus nummerierten Überschriften, sonst kurze Titelzeilen, sonst gleich grosse Blöcke."""
    text = re.sub(r"\[Seite \d+\]\n?", "", text or "").strip()
    zeilen = text.splitlines(); kopf = _kopfzeilen(zeilen)
    zeilen = [z for z in zeilen if z.strip() not in kopf]
    kand = _kandidaten(zeilen)
    ueber = _folge(kand)
    spaet = {}                                                           # Inhaltsverzeichnis: gleicher Titel später = echter Text
    for i, n, t in ueber: spaet[(n, t.lower()[:40])] = i
    toc_ende = max([min(i for i, n, t in ueber if (n, t.lower()[:40]) == k) for k, j in spaet.items()
                    if sum(1 for _, n2, t2 in ueber if (n2, t2.lower()[:40]) == k) > 1] or [-1])
    if toc_ende >= 0:
        erste_doppelt = min(j for k, j in spaet.items() if sum(1 for _, n2, t2 in ueber if (n2, t2.lower()[:40]) == k) > 1)
        ueber = [x for x in ueber if x[0] >= erste_doppelt]
    if len(ueber) >= 3:
        ebene = 1
        while sum(1 for _, n, _ in ueber if len(n) == ebene) < 4 and ebene < 3: ebene += 1
        if sum(1 for _, n, _ in ueber if len(n) == ebene) > max_abschnitte * 2: ebene = max(1, ebene - 1)
        kopfz = {i for i, _, _ in ueber}
        teile = []
        for k, (i, n, t) in enumerate(ueber):
            if len(n) != ebene and not (len(n) < ebene): continue
            ende = next((j for j, m, _ in ueber[k + 1:] if len(m) <= len(n)), len(zeilen))
            body = [z for z in zeilen[i + 1:ende] if not re.match(r"^\d{1,3}\s+\S", z) or zeilen.index(z) in kopfz]
            # Unterkapitel als «## Titel» behalten, Fussnoten («17 Siehe …») weglassen
            sub = {j: f"## {tt}" for j, m, tt in ueber if i < j < ende}
            body = [sub.get(i + 1 + q, z) for q, z in enumerate(zeilen[i + 1:ende])
                    if (i + 1 + q) in sub or not re.match(r"^\d{1,3}\s+[A-ZÄÖÜ«(a-z]", z)]
            teile.append((t, "\n".join(body).strip()))
        teile = [(t, x) for t, x in teile if len(x) >= 80]
    else:
        teile = []
        for i, z in enumerate(zeilen):                                   # unnummeriert: kurze Titelzeile vor einem Absatz
            folgt = " ".join(zeilen[i + 1:i + 4]); w = z.strip().split()
            if (z.strip() and len(z.strip()) <= 70 and len(w) <= 8 and z.strip()[0].isupper() and not re.search(r"[.;,:]$", z.strip())
                    and len(folgt) >= 150 and (i == 0 or not zeilen[i - 1].strip())):
                teile.append((z.strip(), []))
            elif teile: teile[-1][1].append(z)
        teile = [(t, "\n".join(b).strip()) for t, b in teile if len("\n".join(b).strip()) >= 150]
        if len(teile) < 2:                                               # keine Gliederung → Blöcke
            absaetze = [a.strip() for a in re.split(r"\n\s*\n", text) if a.strip()]; teile, buf = [], ""
            for a in absaetze:
                if len(buf) + len(a) > 1800 and buf: teile.append((None, buf)); buf = ""
                buf += ("\n\n" if buf else "") + a
            if buf: teile.append((None, buf))
    while len(teile) > max_abschnitte:                                   # kleinste Nachbarn zusammenlegen
        j = min(range(len(teile) - 1), key=lambda k: len(teile[k][1]) + len(teile[k + 1][1]))
        (t1, x1), (t2, x2) = teile[j], teile[j + 1]
        teile[j:j + 2] = [(t1 or t2, x1 + "\n\n" + (f"## {t2}\n" if t2 else "") + x2)]
    return [(t, _verdichten(x)) for t, x in teile]


_SIGNAL = re.compile(r"\b(muss|müssen|ist zu|sind zu|darf|dürfen|nicht zulässig|zulässig|unzulässig|verboten|gilt|gelten|"
                     r"empfiehlt|empfohlen|erforderlich|notwendig|zwingend|voraus(?:setzung|gesetzt)|risiko|haft\w*|strafbar|"
                     r"verantwortlich|wichtig|insbesondere|daher|deshalb|somit|folglich|grundsätzlich)\b", re.I)


def _verdichten(x, maxz=3800):
    """Lange Kapitel: je Unterkapitel Titel + die aussagekräftigsten Sätze (Pflichten, Verbote, Folgen) statt nur der Anfang.
    «Schlussfolgerung/Fazit»-Unterkapitel gehen ganz mit. Reihenfolge der Sätze bleibt erhalten."""
    if len(x) <= maxz: return x
    bloecke = re.split(r"(?m)^(?=## )", x); n = max(1, len(bloecke)); out = []
    wichtig = [b for b in bloecke if re.match(r"## .*(schlussfolgerung|fazit|zusammenfassung|ergebnis)", b, re.I)]
    rest_platz = maxz - sum(min(len(b), 900) for b in wichtig); je = max(250, rest_platz // max(1, n - len(wichtig)))
    for b in bloecke:
        kopf, _, rest = b.partition("\n") if b.startswith("## ") else ("", "", b)
        saetze = [st for st in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", rest).strip()) if len(st) > 25]
        if b in wichtig: t = " ".join(saetze)[:900]
        else:
            rang = sorted(range(len(saetze)), key=lambda k: (-len(_SIGNAL.findall(saetze[k])), k))
            wahl, laenge = set(), 0
            for k in [0] + rang:                                           # erster Satz (Thema) + stärkste Aussagen
                if k >= len(saetze) or k in wahl: continue
                if laenge + len(saetze[k]) > je and wahl: break
                wahl.add(k); laenge += len(saetze[k])
            t = " ".join(saetze[k] for k in sorted(wahl))
        out.append((kopf + "\n" if kopf else "") + t.strip())
    return "\n".join(out)[:maxz + 400]


# ------------------------------------------------------------------ 2. Leitplanken (ohne Modell)
def _zahlen(t): return set(re.findall(r"\d[\d'’.,]*\d|\d", t))


def _sauber(p, quelle, max_w=14):
    p = re.sub(r"^[\s•\-–*\d.)]+", "", str(p or "")).strip().strip('"').rstrip(".").replace("ß", "ss")   # v154: Schweizer Schreibung
    if not p or p.lower() in ("leer", "-", "keine", "unklar", "n/a"): return ""
    norm = lambda z: z.replace("'", "").replace("’", "").replace(",", ".")
    q = {norm(z) for z in _zahlen(quelle)}
    if any(norm(z) not in q for z in _zahlen(p)): return ""              # erfundene Zahl → weg
    w = p.split()
    return " ".join(w[:max_w]) + (" …" if len(w) > max_w else "")


# v156: Leitplanke für Einschränkungen. Kleine Modelle lassen «grundsätzlich», «unter Voraussetzungen» u.ä. gern weg und machen
# aus einer bedingten Aussage eine unbedingte. Behauptet ein Stichpunkt «zulässig/erlaubt/verboten/muss …» ohne Einschränkung,
# steht im passenden Quellsatz aber eine, ergänzt AURA sie in Klammern und meldet die Folie zur Prüfung.
_ABSOLUT = re.compile(r"\b(zulässig|unzulässig|erlaubt|verboten|strafbar|darf|dürfen|muss|müssen|gilt|gelten|ist ausgeschlossen|"
                      r"nicht möglich|möglich|pflicht\w*|untersagt|verbiet\w*)\b", re.I)
_EINSCHR = [(re.compile(r"\bgrundsätzlich\b", re.I), "grundsätzlich"),
            (re.compile(r"\bunter (?:bestimmten |gewissen |engen )?(?:voraussetzungen|bedingungen)\b", re.I), "unter Voraussetzungen"),
            (re.compile(r"\b(?:sofern|soweit|vorbehältlich|wenn\b.{0,60}\b(?:erfüllt|vorliegt|gegeben))", re.I), "unter Voraussetzungen"),
            (re.compile(r"\bin der regel\b|\bregelmässig\b|\bmeist(?:ens)?\b", re.I), "in der Regel"),
            (re.compile(r"\bausnahmsweise\b|\bnur (?:dann|wenn|bei|mit|unter)\b", re.I), "nur unter Bedingungen")]
_SCHON = re.compile(r"\b(grundsätzlich|voraussetzung\w*|bedingung\w*|in der regel|meist\w*|sofern|soweit|wenn|falls|nur|"
                    r"ausnahmsweise|vorbehalt\w*|teilweise|unter umständen|i\.\s?d\.\s?r\.)\b", re.I)


def _woerter(t): return {w.lower() for w in re.findall(r"[A-Za-zÄÖÜäöüß-]{5,}", t)}


def einschraenkung(punkt, quelle):
    """Liefert (punkt_neu, hinweis|None)."""
    if not _ABSOLUT.search(punkt) or _SCHON.search(punkt): return punkt, None
    w = _woerter(punkt) - {"zulässig", "unzulässig", "erlaubt", "verboten", "müssen", "dürfen", "gelten", "strafbar"}
    if len(w) < 2: return punkt, None
    best = None
    for satz in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", quelle)):
        treffer = len(w & _woerter(satz))
        if treffer >= 2 and (best is None or treffer > best[0]): best = (treffer, satz)
    if not best: return punkt, None
    for rx, wort in _EINSCHR:
        if rx.search(best[1]):
            return f"{punkt} ({wort})", f"Einschränkung «{wort}» ergänzt: «{punkt[:60]}» – im Original prüfen"
    return punkt, None


def folie_aus(res, titel_text, quelle):
    punkte, gesehen = [], set()
    for k in ("punkt1", "punkt2", "punkt3", "punkt4"):                   # v155: «A; B» → zwei Stichpunkte (höchstens 5)
        for teil in re.split(r"\s*;\s*", str(res.get(k) or "")):
            p = _sauber(teil, quelle)
            if p and p.lower() not in gesehen and len(punkte) < 5: punkte.append(p); gesehen.add(p.lower())
    titel = _sauber(res.get("titel"), quelle + " " + (titel_text or ""), 8) or titel_text or "Abschnitt"
    if titel_text and len(titel_text) <= 60: titel = titel_text                   # Überschrift aus dem Text hat Vorrang
    art = res.get("art") if res.get("art") in ARTEN else "Aufzählung"
    aussage = _sauber(res.get("aussage"), quelle, 25)
    if art == "Kernaussage" and aussage:
        return {"art": "aussage", "titel": titel, "aussage": aussage, "punkte": punkte}
    kurz = lambda t: t and len(str(t).split()) <= 5                  # v155: Spaltentitel müssen kurz sein, sonst Aufzählung
    if art == "Gegenüberstellung" and len(punkte) >= 2 and kurz(res.get("links_titel")) and kurz(res.get("rechts_titel")):
        h = (len(punkte) + 1) // 2
        return {"art": "zwei", "titel": titel, "links": [_sauber(res["links_titel"], quelle, 5)] + [(1, p) for p in punkte[:h]],
                "rechts": [_sauber(res["rechts_titel"], quelle, 5)] + [(1, p) for p in punkte[h:]]}
    if not punkte and aussage: return {"art": "aussage", "titel": titel, "aussage": aussage}
    return {"art": "inhalt", "titel": titel, "punkte": punkte or ["(kein Inhalt erkannt – Abschnitt prüfen)"]}


def _zusammenfassung(text, n=3000):
    """v153: Abschnitt «Zusammenfassung/Management Summary/Fazit» des Dokuments – sonst der Textanfang (ohne Verzeichnisse)."""
    m = re.search(r"(?mi)^\s*(?:\d+(?:\.\d+)*\.?\s+)?(zusammenfassung|management summary|executive summary|das wichtigste in k[üu]rze|"
                  r"fazit|schlussfolgerungen?)\s*$", text)
    if m: return text[m.end():m.end() + n].strip()
    t = re.sub(r"(?s)^.*?(?:inhaltsverzeichnis|änderungsverzeichnis).*?\n\s*\n", "", text[:20000], count=1, flags=re.I)
    return t[:n]


# ------------------------------------------------------------------ 3. Ablauf
def erstellen(text, name, auftrag, llm_feld, progress=lambda *a: None, cancelled=lambda: False):
    """llm_feld(system, user, fields) -> dict. Liefert (pfad, folien, hinweise)."""
    s = load_settings(); hinweise = []
    vorlage = Path(s.get("praes_vorlage") or VORLAGE)
    if not vorlage.is_file(): raise RuntimeError(f"Vorlage fehlt: {vorlage}")
    teile = gliedern(text, int(s.get("praes_max_folien", 10)))
    if not teile: raise RuntimeError("Im Anhang ist kein Text, aus dem sich Folien machen lassen.")
    folien = []
    for i, (t, x) in enumerate(teile):
        if cancelled(): raise RuntimeError("abgebrochen")
        progress(f"Präsentation: Folie {i + 1} von {len(teile)} …", i, len(teile) + 1)
        user = (f"Auftrag: {auftrag}\n\n" if auftrag else "") + (f"Überschrift: {t}\n" if t else "") + f"Abschnitt:\n{x}"
        res = llm_feld(SYSTEM, user, [
            {"name": "titel", "max_tokens": 20}, {"name": "art", "max_tokens": 8, "auswahl": ARTEN},
            {"name": "punkt1", "max_tokens": 26}, {"name": "punkt2", "max_tokens": 26},
            {"name": "punkt3", "max_tokens": 26}, {"name": "punkt4", "max_tokens": 26},
            {"name": "aussage", "max_tokens": 50},
            {"name": "links_titel", "max_tokens": 10}, {"name": "rechts_titel", "max_tokens": 10}])
        f = folie_aus(res or {}, t, x); folien.append(f)
        for feld in ("punkte", "links", "rechts"):                       # v156: Einschränkungen nicht unterschlagen
            neu = []
            for p in f.get(feld) or []:
                ebene, txt = p if isinstance(p, tuple) else (None, p)
                txt2, h = einschraenkung(txt, x)
                if h: hinweise.append(f"Folie «{f['titel']}»: {h}")
                neu.append((ebene, txt2) if ebene is not None else txt2)
            if f.get(feld): f[feld] = neu
        if f.get("aussage"):
            f["aussage"], h = einschraenkung(f["aussage"], x)
            if h: hinweise.append(f"Folie «{f['titel']}»: {h}")
        if f["art"] == "inhalt" and f["punkte"][0].startswith("(kein Inhalt"): hinweise.append(f"Folie «{f['titel']}»: nichts erkannt")
    progress("Präsentation: Titel und Fazit …", len(teile), len(teile) + 1)
    kopf = "\n".join(f"- {f['titel']}" for f in folien)
    res = llm_feld(SYSTEM.replace("aus einem Textabschnitt eine Folie", "Titel und Fazit einer Präsentation"),
                   (f"Auftrag: {auftrag}\n\n" if auftrag else "") + f"Folien:\n{kopf}\n\nZusammenfassung des Textes:\n{_zusammenfassung(text)}",
                   [{"name": "titel", "max_tokens": 24}, {"name": "untertitel", "max_tokens": 30},
                    {"name": "fazit1", "max_tokens": 32}, {"name": "fazit2", "max_tokens": 32}, {"name": "fazit3", "max_tokens": 32}]) or {}
    titel = _sauber(res.get("titel"), text, 10) or Path(name).stem.replace("_", " ")
    fazit = [p for p in (_sauber(res.get(k), text) for k in ("fazit1", "fazit2", "fazit3")) if p]
    alle = [{"art": "titel", "titel": titel, "untertitel": "\n".join(x for x in (_sauber(res.get("untertitel"), text, 14),
                                                                              date.today().strftime("%d.%m.%Y")) if x)}]
    if len(folien) >= 3: alle.append({"art": "inhalt", "titel": "Inhalt", "punkte": [f["titel"] for f in folien]})
    alle += folien
    if fazit: alle.append({"art": "inhalt", "titel": "Fazit", "punkte": fazit})
    from .pptx_bau import bauen
    stamm = re.sub(r"[^\w\-]+", "_", Path(name).stem)[:40] or "Praesentation"
    ziel = ZIEL_DIR / f"{stamm}_{time.strftime('%Y%m%d_%H%M')}.pptx"
    bauen(vorlage, ziel, alle)
    return ziel, alle, hinweise
