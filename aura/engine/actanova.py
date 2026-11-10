"""Acta Nova: Suche in der offenen, angemeldeten Edge-Sitzung (nur lesen, nur Trefferlisten).
Modi: datei (Dokumentname), inhalt (Volltext), dossier (Dossiertitel), thema (dossier + inhalt).
Leitplanken: keine Dokumente oeffnen/laden, max. 1 Suche je 3 s, jede Suche in logs\\actanova.log.
"""
import json, threading, time
from pathlib import Path
from datetime import datetime
from . import edge

STANDARD_URL = "https://www.vbs.gever.admin.ch/web/Main.wxe?UserInteractionNumberToUse=0"


def start_url():
    """v212: eingetragene URL nur, wenn ihr Origin freigegeben ist (herkunft.py) – sonst Fehler (fail closed)."""
    from .herkunft import pruefe
    try:
        from ..config import load_settings
        u = (load_settings().get("actanova_url") or STANDARD_URL).strip()
    except Exception:
        u = STANDARD_URL
    return pruefe(u, "actanova")


def url_teil():
    from urllib.parse import urlparse
    return urlparse(start_url()).netloc or "gever.admin.ch"


START_URL = STANDARD_URL        # alt, fuer bestehende Aufrufe
LOGDATEI = edge.ROOT / "logs" / "actanova.log"
MIN_ABSTAND = 2.0
_letzte = [0.0]

# Formulare: Menuepunkt, Reiter-IDs (Endungen), Felder (Endungen)
FORM = {
    "dokument": {"menue": ["Geschäftsobjekt", "Dokument"], "krume": "Dokument suchen",
                 "tab_basis": "DocumentSearchFormPage_view_Tab_Command",
                 "tab_inhalt": "FileContentObjectContentSearchFormPage_view_Tab_Command",
                 "status": "DocumentSearchFormPage_view_LazyContainer_ctl01_ObjectFormPageDataSource_FileHandlingState_Value",
                 "name": "DocumentSearchFormPage_view_LazyContainer_ctl01_MSVC_ObjectFormPageDataSource_Name_SearchText_Value",
                 "inhalt": "FileContentObjectContentSearchFormPage_view_LazyContainer_ctl01_ObjectFormPageDataSource_DocumentContent_Value"},
    "dossier": {"menue": ["Geschäftsobjekt", "Dossier"], "krume": "Dossier suchen",
                "tab_basis": "FileSearchFormPage_view_Tab_Command",
                "status": "FileSearchFormPage_view_LazyContainer_ctl01_ObjectFormPageDataSource_FileHandlingState_Value",
                "titel": "FileSearchFormPage_view_LazyContainer_ctl01_MSVC_ObjectFormPageDataSource_Title_SearchText_Value"},
}

# JS-Helfer: Dokument (Top oder Frame) finden, das ein Element mit ID-Endung enthaelt
JS_LIB = r"""
const AN = {
 docs() { const d = [document]; document.querySelectorAll('iframe,frame').forEach(f => { try { if (f.contentDocument) d.push(f.contentDocument); } catch (e) {} }); return d; },
 el(suffix) { for (const d of AN.docs()) { const e = d.querySelector('[id$="' + suffix + '"]'); if (e) return e; } return null; },
 sichtbar(e) { if (!e) return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; },
 text(t, nurTop) { const ds = nurTop ? [document] : AN.docs();
   for (const d of ds) for (const e of d.querySelectorAll('a,span,li,button,div'))
     if (e.children.length <= 2 && (e.innerText || '').trim() === t && AN.sichtbar(e)) return e; return null; },
 busy() { for (const d of AN.docs()) { if (d.readyState !== 'complete') return true; if (d.body && d.body.style.cursor === 'wait' && d.body.innerText.length > 100) return true; } return false; }
};
"""


def _js(tab, code):
    return tab.js("(() => {" + JS_LIB + code + "})()")


def _warten(tab, bedingung_js, timeout=60.0, ruhe=0.3):
    """Wartet, bis bedingung_js (Ausdruck mit AN.*) true ist; toleriert Seitenwechsel."""
    ende = time.time() + timeout
    while time.time() < ende:
        time.sleep(ruhe)
        try:
            if _js(tab, f"return !AN.busy() && !!({bedingung_js});"):
                return True
        except Exception:
            pass
    return False


def _klick_id(tab, suffix):
    return _js(tab, f"const e = AN.el({json.dumps(suffix)}); if (!e) return false; e.click(); return true;")


def _klick_text(tab, text, nur_top=False):
    return _js(tab, f"const e = AN.text({json.dumps(text)}, {str(nur_top).lower()}); if (!e) return false; e.click(); return true;")


def _setzen(tab, suffix, wert):
    return _js(tab, f"""const e = AN.el({json.dumps(suffix)}); if (!e) return false;
      e.focus(); e.value = {json.dumps(wert)};
      e.dispatchEvent(new Event('input', {{bubbles: true}})); e.dispatchEvent(new Event('change', {{bubbles: true}}));
      return true;""")


def _status_leeren(tab, suffix):
    return _js(tab, f"""const e = AN.el({json.dumps(suffix)}); if (!e) return 'fehlt';
      let i = [...e.options].findIndex(o => o.value === '' || o.text.trim() === '');
      if (i < 0) return 'keine leere Option';
      if (e.selectedIndex === i) return 'ok';
      e.selectedIndex = i; e.dispatchEvent(new Event('change', {{bubbles: true}})); return 'geleert';""")


def _log(zeile):
    LOGDATEI.parent.mkdir(parents=True, exist_ok=True)
    with open(LOGDATEI, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {zeile}\n")


UNWICHTIG = {"Kontextmenü", "Verfügbare Inhalte", "Objektänderungen", "Mandant", "Inhalt"}


class ActaNovaFehler(RuntimeError):
    pass


def ein_tab(warten=15.0):
    """v213b: Genau EIN Acta-Nova-Tab. Nach dem Edge-Start bis `warten` s auf den Start-Tab warten (er laedt noch
    ueber die Anmeldung), Doppel schliessen, erst dann notfalls einen neuen Tab oeffnen."""
    from .herkunft import ist_erlaubt
    ende = time.time() + warten
    while True:
        offen = [t for t in edge.tabs() if ist_erlaubt(t.get("url", ""), "actanova")]
        if offen or time.time() > ende:
            break
        time.sleep(0.5)
    for x in offen[1:]:                                          # Doppel weg: zwei Initialisierungen blockieren sich
        edge.tab_zu(edge.Tab(x))
    return edge.Tab(offen[0]) if offen else edge.tab_neu(start_url())


def _zeigen(tab):
    edge.fenster(tab, "normal")
    try: tab.ws.cdp("Page.bringToFront")
    except Exception: pass


def init_haenger_loesen(tab, warten=20.0, versuche=2):
    """v213b: Haengt «DmsInitializationForm» («Client wird gestartet …»), zuerst Fenster sichtbar machen
    (der Client initialisiert offenbar nur sichtbar – so wirkt auch das manuelle Aus/Ein), danach neu laden."""
    for i in range(versuche + 1):
        _zeigen(tab)
        ende = time.time() + warten
        while time.time() < ende:
            try: href = tab.js("location.href") or ""
            except Exception: href = ""
            if href and "DmsInitializationForm" not in href:
                _log(f"init ok nach Versuch {i}")
                return True
            time.sleep(0.5)
        _log(f"init haengt ({href[:60]}) - Versuch {i + 1}")
        if i < versuche:
            try: tab.ws.cdp("Page.reload", ignoreCache=True)
            except Exception as x: _log(f"reload fehlgeschlagen: {x}")
    return False


def verbinden():
    """Haengt sich an die offene Acta-Nova-Sitzung. Startet Edge, falls noetig (Anmeldung macht der Mensch)."""
    edge.starten(start_url())
    tab = ein_tab(5.0)                                             # v213b: Doppel-Tabs vermeiden
    if tab: tab.dialog_schliessen()
    if not tab:
        raise ActaNovaFehler("Kein Acta-Nova-Tab offen - bitte im Edge-Fenster anmelden.")
    # Frisch starten: Startseite neu laden. Setzt die Brotkruemel zurueck und zeigt sofort (statt nach 90 s),
    # ob die Sitzung abgelaufen ist.
    # v214c: Nicht jedes Mal neu laden – jedes Neuladen startet den Acta-Nova-Client neu, und genau dieser Neustart
    # bleibt jedes zweite Mal haengen (Log 10.11.). Nur laden, wenn die Seite nicht schon bereit ist.
    bereit = False
    try: bereit = "DmsInitializationForm" not in (tab.js("location.href") or "") and _warten(tab, "AN.text('Suchen', true)", 2, 0.3)
    except Exception: pass
    if not bereit:
        try: tab.navigieren(start_url(), "actanova")
        except Exception: pass
    if not init_haenger_loesen(tab, 30.0, 1):                      # v213b
        raise ActaNovaFehler("Acta Nova bleibt bei «Client wird gestartet» stehen – Fenster ist offen, bitte prüfen.")
    if not _warten(tab, "AN.text('Suchen', true)", 15, 0.4):
        edge.fenster(tab, "normal")                                # Anmeldung braucht das sichtbare Fenster
        try: tab.ws.cdp("Page.bringToFront")
        except Exception: pass
        raise ActaNovaFehler("Acta-Nova-Sitzung abgelaufen – bitte im Edge-Fenster mit Karte/PIN anmelden, dann nochmals fragen.")
    tab.origin_pruefen("actanova")                                 # v212: nur auf freigegebener Seite weiterarbeiten
    edge.fenster(tab, "minimized")                                 # Suche laeuft unsichtbar weiter
    return tab


JS_DIALOG_OK = r"""for (const d of AN.docs()) for (const b of d.querySelectorAll('button, a, input[type=button], span'))
    if (/^(OK|Ok)$/.test((b.innerText || b.value || '').trim()) && AN.sichtbar(b)
        && /Brotkr|maximale Anzahl|Information/.test((b.closest('[role=dialog], [class*=Dialog], [class*=dialog], [class*=Modal], [class*=modal]') || d.body).innerText || '')) {
      b.click(); return true; } return false;"""

JS_KRUEMEL = r"""const nav = document.querySelector('[aria-label*="Brotkr"], [id*=BreadCrumb], [class*=readCrumb], [class*=readcrumb]');
  const a = nav ? [...nav.querySelectorAll('a')].filter(x => AN.sichtbar(x)) : [];
  return {n: a.length};"""


def _aufraeumen(tab, protokoll):
    """Verhindert «maximale Anzahl der Einträge in der Brotkrümelnavigation»: Hinweis wegklicken und bei langer
    Spur zur Startseite (erster Brotkruemel bzw. «Aktuelle Informationen») zurueck – das setzt die Spur zurueck."""
    if _js(tab, JS_DIALOG_OK):
        protokoll.append("Hinweis Brotkrümel geschlossen"); time.sleep(0.5)
    k = _js(tab, JS_KRUEMEL) or {}
    if (k.get("n") or 0) >= 6 or _js(tab, "return /maximale Anzahl der Eintr/.test(AN.docs().map(d => d.body ? d.body.innerText : '').join(' '));"):
        ok = _js(tab, """const nav = document.querySelector('[aria-label*="Brotkr"], [id*=BreadCrumb], [class*=readCrumb], [class*=readcrumb]');
            const a = nav && [...nav.querySelectorAll('a')].find(x => AN.sichtbar(x)); if (a) { a.click(); return true; } return false;""") \
            or _klick_text(tab, "Aktuelle Informationen")
        if ok:
            _warten(tab, "AN.text('Suchen', true)", 20)
            protokoll.append(f"Brotkrümel zurückgesetzt ({k.get('n')})")


def _formular_oeffnen(tab, art, protokoll):
    f = FORM[art]
    if _js(tab, f"return AN.sichtbar(AN.el({json.dumps(f['tab_basis'])}));"):
        return
    sel = f"AN.sichtbar(AN.el({json.dumps(f['tab_basis'])}))"
    # direkt ueber das Menue (Brotkruemel/Zurueck kosteten je 20 s Wartezeit ohne Wirkung)
    _aufraeumen(tab, protokoll)
    # Menuepfad: Suchen > Geschaeftsobjekt > Dokument|Dossier (Untermenue per Hover/Klick)
    if not _klick_text(tab, "Suchen", nur_top=True):
        raise ActaNovaFehler("Menue 'Suchen' nicht gefunden")
    time.sleep(0.4)
    pfad = f["menue"]
    for i, name in enumerate(pfad[:-1]):
        naechster = pfad[i + 1]
        _js(tab, f"""const e = AN.text({json.dumps(name)}, true); if (!e) return false;
          for (const t of ['mouseover', 'mouseenter', 'mousemove']) e.dispatchEvent(new MouseEvent(t, {{bubbles: true}}));
          return true;""")
        time.sleep(0.3)
        if not _js(tab, f"return !!AN.text({json.dumps(naechster)}, true);"):
            _klick_text(tab, name, nur_top=True)
            time.sleep(0.4)
    ziel = pfad[-1]
    ok = _klick_text(tab, ziel, nur_top=True)
    if not ok:  # Rueckfall: NUR innerhalb des Menues 'Suchen' entlang des Pfads (nie 'Neu > Dossier'!)
        ok = _js(tab, f"""const pfad = {json.dumps(pfad)};
          const eigen = li => {{ const a = li.querySelector(':scope > a, :scope > span > a, :scope > span');
                                 return a ? (a.innerText || a.textContent || '').trim() : ''; }};
          let knoten = [...document.querySelectorAll('li')].find(li => eigen(li) === 'Suchen');
          if (!knoten) return 'kein Menue Suchen';
          for (const name of pfad) {{
            const li = [...knoten.querySelectorAll('li')].find(x => eigen(x) === name);
            if (!li) return 'fehlt im Menue Suchen: ' + name;
            knoten = li;
          }}
          const a = knoten.querySelector(':scope > a') || knoten.querySelector('a');
          if (!a) return 'kein Link';
          a.click(); return true;""")
        protokoll.append(f"Menue Suchen (versteckt): {ok}")
        ok = ok is True
    if ok and _warten(tab, sel, 30):
        protokoll.append("Menue: Suchen > " + " > ".join(pfad))
        return
    diag = _js(tab, "return [...document.querySelectorAll('a,li,span')].filter(e => /Geschäftsobjekt|^Dossier$|^Dokument$/.test((e.innerText||'').trim())).map(e => e.tagName + ':' + (e.innerText||'').trim().slice(0,30) + ':' + (AN.sichtbar(e) ? 'sichtbar' : 'versteckt') + ':' + e.children.length);")
    protokoll.append(f"Menue-Diagnose: {diag}")
    menue = _js(tab, "return [...document.querySelectorAll('a,li,span')].filter(e => AN.sichtbar(e) && /such/i.test(e.innerText||'') && e.innerText.length < 40).map(e => e.innerText.trim());")
    raise ActaNovaFehler(f"Suchmaske '{art}' nicht erreichbar. Sichtbare Menuepunkte: {sorted(set(menue or []))} | {protokoll}")


def _reiter(tab, suffix_tab, suffix_feld):
    if _js(tab, f"return AN.sichtbar(AN.el({json.dumps(suffix_feld)}));"):
        return
    if not _klick_id(tab, suffix_tab):
        raise ActaNovaFehler(f"Reiter fehlt: {suffix_tab}")
    if not _warten(tab, f"AN.sichtbar(AN.el({json.dumps(suffix_feld)}))", 30):
        raise ActaNovaFehler(f"Feld nach Reiterwechsel nicht sichtbar: {suffix_feld}")


JS_TREFFER = r"""
 const kopf = [], zeilen = [], ids = new Set(); let info = '', weitere = false, anzahl = null;
 for (const d of AN.docs()) {
   const t = d.body ? d.body.innerText : '';
   const m = t.match(/Suchergebnisse \(Anzahl: (\d+)\)/); if (m) anzahl = +m[1];
   if (/weitere Suchergebnisse/.test(t)) weitere = true;
   if (/keine (Such)?ergebnisse|keine Objekte gefunden/i.test(t)) info = 'keine';
   const ths = d.querySelectorAll('table.bocListTable thead th');
   if (ths.length && !kopf.length) ths.forEach(th => kopf.push((th.innerText || '').trim()));
   d.querySelectorAll('tr.bocListDataRow').forEach(tr => {
     const id = tr.getAttribute('data-item-id'); if (!id || ids.has(id)) return; ids.add(id);
     const tds = [...tr.querySelectorAll('td')]; const zellen = tds.map(td => (td.innerText || '').replace(/\s+/g, ' ').trim());
     zeilen.push({id, zellen, namePos: tds.findIndex(td => td.getAttribute('role') === 'rowheader')});
   });
 }
 return {kopf, zeilen, anzahl, weitere, info};
"""


def _treffer_lesen(tab):
    r = _js(tab, JS_TREFFER) or {}
    kopf = r.get("kopf") or []
    liste = []
    for z in r.get("zeilen", []):
        zellen = z["zellen"]
        # Kopf und Zellen gleich lang -> per Spaltenname; sonst nur nicht-leere Zellen
        if "Name" in kopf and z.get("namePos", -1) >= 0:  # Versatz: Namenszelle <-> Spalte 'Name'
            off = z["namePos"] - kopf.index("Name")
            d = {}
            for i, k in enumerate(kopf):
                j = i + off
                if k and k not in UNWICHTIG and 0 <= j < len(zellen) and zellen[j] and zellen[j] != "Inhalt öffnen":
                    d[k] = zellen[j]
        else:
            d = {f"Spalte{i}": v for i, v in enumerate(zellen) if v}
        d["_id"] = z["id"]
        d["_typ"] = z["id"].split("|")[0]
        liste.append(d)
    return {"treffer": liste, "anzahl": r.get("anzahl"), "weitere": r.get("weitere", False),
            "kopf": kopf, "info": r.get("info", "")}


def _diag(text):
    try:
        from .. import log
        log.get().info("DIAG actanova " + text)
    except Exception:
        pass


def _suchen(tab, art, feld_tab, feld, begriff, protokoll, export=False):
    f = FORM[art]
    t0 = time.perf_counter(); zeiten = {}
    _formular_oeffnen(tab, art, protokoll); zeiten["maske"] = time.perf_counter() - t0
    _klick_id(tab, "ResetSearchButton")
    _warten(tab, f"AN.el({json.dumps(f['tab_basis'])})", 20)
    _reiter(tab, f["tab_basis"], f["status"])
    protokoll.append("Status: " + str(_status_leeren(tab, f["status"])))
    _warten(tab, "true", 10)
    for versuch in range(4):                       # das Leeren des Status loest evtl. ein Neuladen aus -> erneut versuchen
        try: _reiter(tab, f[feld_tab] if feld_tab else f["tab_basis"], f[feld])
        except ActaNovaFehler:
            if versuch == 3: raise
        if _setzen(tab, f[feld], begriff): break
        time.sleep(1.0); _warten(tab, "true", 10)
    else:
        raise ActaNovaFehler(f"Suchfeld fehlt: {feld}")
    # vorher evtl. vorhandene Trefferzeilen markieren, damit wir neue erkennen
    _js(tab, "AN.docs().forEach(d => d.querySelectorAll('tr.bocListDataRow').forEach(tr => tr.setAttribute('data-aura-alt', '1'))); return true;")
    zeiten["ausfuellen"] = time.perf_counter() - t0 - zeiten["maske"]
    if not _klick_id(tab, "SearchButton"):
        raise ActaNovaFehler("Knopf 'Suchen' fehlt")
    t1 = time.perf_counter()
    ok = _warten(tab, "AN.el('BackButton') || /Suchergebnisse|keine (Such)?ergebnisse/i.test(AN.docs().map(d => d.body ? d.body.innerText : '').join(' '))", 90, 1.0)
    if not ok:
        raise ActaNovaFehler(f"Keine Trefferseite nach 90 s – Seite: {tab.zustand()[:120]}")
    zeiten["suche"] = time.perf_counter() - t1
    erg = _treffer_lesen(tab)
    t2 = time.perf_counter()
    if export and erg["treffer"] and (erg["weitere"] or (erg["anzahl"] or 0) > len(erg["treffer"])):
        alle = exportieren(tab)
        if alle:
            erg["alle"] = alle
            protokoll.append(f"Export: {len(alle)} Zeilen")
        else:
            protokoll.append("Export fehlgeschlagen -> nur Seite 1")
    zeiten["export"] = time.perf_counter() - t2
    _diag(f"{art} '{begriff}' " + " ".join(f"{k}={v:.1f}s" for k, v in zeiten.items()) + f" treffer={erg.get('anzahl')}")
    return erg


def suche(modus, begriff, tab=None):
    """modus: datei | inhalt | dossier | thema. Gibt dict mit Trefferlisten zurueck."""
    begriff = (begriff or "").strip()
    if not begriff:
        raise ValueError("Leerer Suchbegriff")
    warte = MIN_ABSTAND - (time.time() - _letzte[0])
    if warte > 0:
        time.sleep(warte)
    tab = tab or verbinden()
    protokoll, t0 = [], time.time()
    erg = {"modus": modus, "begriff": begriff}
    try:
        if modus == "datei":
            erg["dokumente"] = _suchen(tab, "dokument", None, "name", begriff, protokoll)
        elif modus == "inhalt":
            erg["dokumente"] = _suchen(tab, "dokument", "tab_inhalt", "inhalt", begriff, protokoll)
        elif modus == "dossier":
            erg["dossiers"] = _suchen(tab, "dossier", None, "titel", begriff, protokoll)
        elif modus == "thema":
            erg["dossiers"] = _suchen(tab, "dossier", None, "titel", begriff, protokoll)
            time.sleep(MIN_ABSTAND)
            erg["dokumente"] = _suchen(tab, "dokument", "tab_inhalt", "inhalt", begriff, protokoll)
        else:
            raise ValueError("modus: datei | inhalt | dossier | thema")
        n = {k: len(v["treffer"]) for k, v in erg.items() if isinstance(v, dict)}
        _log(f"{modus} '{begriff}' -> {n} in {time.time() - t0:.1f}s")
    except Exception as e:
        _log(f"{modus} '{begriff}' FEHLER {type(e).__name__}: {e}")
        raise
    finally:
        _letzte[0] = time.time()
        erg["protokoll"] = protokoll
    return erg


def nach_dossier(treffer):
    """Gruppiert Dokumenttreffer nach Spalte 'Enthalten in'."""
    gruppen = {}
    for t in treffer:
        gruppen.setdefault(t.get("Enthalten in", "(ohne Dossier)"), []).append(t)
    return dict(sorted(gruppen.items(), key=lambda kv: -len(kv[1])))


# ---------------------------------------------------------------- Excel-Export (alle Treffer, nur Metadaten)
import shutil, tempfile, zipfile, re as _re
import xml.etree.ElementTree as _ET

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


XLSX_MAX_DATEI = 50 * 2**20       # v212: Grenzen fuer den Acta-Nova-Export
XLSX_MAX_XML = 64 * 2**20
XLSX_MAX_ZEILEN = 20_000
XLSX_MAX_SPALTEN = 200
XLSX_MAX_STRINGS = 500_000


def _xml(z, name):
    from .. import sicherheit as SI
    b = SI.zip_lesen(z, z.getinfo(name), XLSX_MAX_XML)
    if b"<!DOCTYPE" in b[:4096] or b"<!ENTITY" in b: raise ActaNovaFehler("Export enthält unzulässige XML-Deklarationen")
    return _ET.fromstring(b)


def _xlsx_zeilen(pfad):
    """Minimaler xlsx-Leser (ohne openpyxl): erste Tabelle als Liste von Zeilen (Strings). v212: harte Grenzen."""
    from .. import sicherheit as SI
    SI.pruefe_dokument(pfad, XLSX_MAX_DATEI)
    with zipfile.ZipFile(pfad) as z:
        SI.zip_pruefen(z, max_eintraege=2000, max_datei=XLSX_MAX_XML, max_gesamt=4 * XLSX_MAX_XML)
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in _xml(z, "xl/sharedStrings.xml").iter(_NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(_NS + "t"))[:5000])
                if len(shared) > XLSX_MAX_STRINGS: raise ActaNovaFehler("Export zu gross (zu viele Texte)")
        blatt = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]
        zeilen = []
        for row in _xml(z, blatt).iter(_NS + "row"):
            if len(zeilen) >= XLSX_MAX_ZEILEN: raise ActaNovaFehler(f"Export zu gross (> {XLSX_MAX_ZEILEN} Zeilen)")
            werte = {}
            for c in row.iter(_NS + "c"):
                ref = c.get("r", "")
                col = 0
                for ch in _re.match(r"[A-Z]+", ref).group(0) if ref else "A":
                    col = col * 26 + ord(ch) - 64
                v = c.find(_NS + "v")
                if c.get("t") == "s" and v is not None:
                    i = int(v.text) if (v.text or "").isdigit() else -1
                    w = shared[i] if 0 <= i < len(shared) else ""
                elif c.get("t") == "inlineStr":
                    w = "".join(t.text or "" for t in c.iter(_NS + "t"))
                else:
                    w = v.text if v is not None else ""
                if col > XLSX_MAX_SPALTEN: continue                    # v212
                werte[col - 1] = (w or "").strip()[:5000]
            if werte:
                zeilen.append([werte.get(i, "") for i in range(max(werte) + 1)])
        return zeilen


def exportieren(tab, timeout=60.0):
    """Klickt 'Excel-Export' der aktuellen Trefferliste, liest die Datei, loescht sie sofort.
    Rueckgabe: Liste von dicts (Spaltenname -> Wert) oder None."""
    ordner = Path(tempfile.mkdtemp(prefix="aura_acta_"))
    try:
        tab.ws.cdp("Page.setDownloadBehavior", behavior="allow", downloadPath=str(ordner))
        if not _klick_id(tab, "ExcelExportButton"):
            return None
        ende = time.time() + timeout
        datei = None
        while time.time() < ende:
            time.sleep(0.5)
            fertig = [p for p in ordner.glob("*.xlsx")]
            if fertig and not list(ordner.glob("*.crdownload")):
                datei = fertig[0]
                break
        if not datei:
            return None
        zeilen = _xlsx_zeilen(datei)
        kopf_i = next((i for i, z in enumerate(zeilen[:10]) if "Name" in z or "Titel" in z), None)
        if kopf_i is None:
            return None
        kopf = zeilen[kopf_i]
        return [{k: v for k, v in zip(kopf, z) if k and v} for z in zeilen[kopf_i + 1:] if any(z)]
    finally:
        shutil.rmtree(ordner, ignore_errors=True)
        try:
            tab.ws.cdp("Page.setDownloadBehavior", behavior="default")
        except Exception:
            pass


# ---------------------------------------------------------------- Ablageort in Acta Nova oeffnen
JS_FELD_NACH_LABEL = r"""(label) => {
  for (const d of AN.docs()) for (const c of d.querySelectorAll('td, th, label, span, div')) {
    if (c.children.length > 2 || (c.innerText || '').trim() !== label) continue;
    const row = c.closest('tr, [class*=Row], [class*=row]'); if (!row) continue;
    const inp = row.querySelector('input[type=text], input:not([type])'); if (inp && AN.sichtbar(inp)) return inp;
  } return null; }"""


def oeffnen(aktenzeichen):
    """Sucht das Dossier/Subdossier mit diesem Aktenzeichen und oeffnet es im (sichtbar gemachten) Edge-Fenster."""
    tab = verbinden()
    try:
        prot = []
        f = FORM["dossier"]
        _formular_oeffnen(tab, "dossier", prot)
        _klick_id(tab, "ResetSearchButton"); _warten(tab, f"AN.el({json.dumps(f['tab_basis'])})", 20)
        _reiter(tab, f["tab_basis"], f["status"])
        _status_leeren(tab, f["status"]); _warten(tab, "true", 10)
        ok = _js(tab, f"""const e = ({JS_FELD_NACH_LABEL})('Aktenzeichen'); if (!e) return false;
            e.focus(); e.value = {json.dumps(aktenzeichen)};
            e.dispatchEvent(new Event('input', {{bubbles: true}})); e.dispatchEvent(new Event('change', {{bubbles: true}}));
            return true;""")
        if not ok:
            raise ActaNovaFehler("Feld «Aktenzeichen» in der Dossier-Suche nicht gefunden")
        _klick_id(tab, "SearchButton")
        if not _warten(tab, "AN.docs().some(d => d.querySelector('tr.bocListDataRow'))", 60, 0.5):
            raise ActaNovaFehler(f"Kein Dossier mit Aktenzeichen {aktenzeichen}")
        _js(tab, """for (const d of AN.docs()) { const c = d.querySelector('tr.bocListDataRow td[role=rowheader] a, tr.bocListDataRow a');
                    if (c) { c.click(); return true; } } return false;""")
        _log(f"oeffnen {aktenzeichen}")
    finally:
        edge.fenster(tab, "normal")
        try: tab.ws.cdp("Page.bringToFront")
        except Exception: pass


# ---------------------------------------------------------------- Sitzung offen halten (nur wenn eingeschaltet)
SPERRE = threading.Lock()
_wach = {"t": None}


def wach_halten_starten(minuten=10):
    """Laedt alle n Minuten die Startseite neu, solange «actanova_wach» an ist – nur wenn gerade keine Suche laeuft."""
    if _wach["t"] and _wach["t"].is_alive():
        return
    def lauf():
        from ..config import load_settings
        while True:
            time.sleep(minuten * 60)
            s = load_settings()
            if not (s.get("actanova") and s.get("actanova_wach")):
                continue
            if not SPERRE.acquire(blocking=False):
                continue
            try:
                if edge.laeuft():
                    t = edge.tab_finden("actanova")
                    if t:
                        t.dialog_schliessen(); t.navigieren(start_url(), "actanova"); t.schliessen()
                        _log("wach halten: Startseite neu geladen")
            except Exception:
                pass
            finally:
                SPERRE.release()
    _wach["t"] = threading.Thread(target=lauf, daemon=True); _wach["t"].start()
