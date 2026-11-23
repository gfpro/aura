"""Acta Nova: Suche in der offenen, angemeldeten Edge-Sitzung (nur lesen, nur Trefferlisten).
Modi: datei (Dokumentname), inhalt (Volltext), dossier (Dossiertitel), thema (dossier + inhalt).
Leitplanken: keine Dokumente oeffnen/laden, max. 1 Suche je 3 s, jede Suche in logs\\actanova.log.
"""
import json, os, threading, time
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


JS_MAX = r"""(n) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  for (const d of AN.docs()) for (const c of d.querySelectorAll('td, th, label, span, div')) {
    if (c.children.length > 3 || !norm(c.innerText).startsWith('Maximale Anzahl')) continue;
    const row = c.closest('tr, [class*=Row], [class*=row]'); if (!row) continue;
    const e = row.querySelector('input[type=text], input[type=number], input:not([type])'); if (!e || !AN.sichtbar(e)) continue;
    e.focus(); e.value = String(n);
    e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true}));
    return e.value || '?'; } return ''; }"""


JS_REITER_SA = r"""const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  for (const d of AN.docs()) for (const e of d.querySelectorAll('[id$="_Tab_Command"]'))
    if (norm(e.innerText) === 'Suchabfrage' && AN.sichtbar(e)) { e.click(); return 'id ' + e.id.split('_').slice(-4).join('_'); }
  const t = AN.text('Suchabfrage'); if (!t) return '';
  const a = t.closest('a,[id$="_Tab_Command"],[role=tab]') || t; a.click(); return 'Text ' + a.tagName + ' ' + (a.id || '').slice(-40);"""


def _max_treffer(tab, n):
    """v259: Reiter «Suchabfrage» öffnen und «Maximale Anzahl der Suchergebnisse» setzen (Standard von Acta Nova: 200).
    Muss VOR dem Klick auf «Suchen» geschehen. Gelingt es nicht, sucht AURA mit dem Standard weiter."""
    try:
        wie = _js(tab, JS_REITER_SA)                                  # v261: Reiter über seinen Befehls-Link, nicht über den Text
        if not wie: _log("max_treffer: Reiter «Suchabfrage» nicht gefunden"); return False
        _log(f"max_treffer: Reiter geklickt ({wie})")
        if not _warten(tab, "[...AN.docs()].some(d => /Maximale Anzahl/.test(d.body ? d.body.innerText : ''))", 5):   # v289: 5 statt 15 s
            _log("max_treffer: Feld nicht sichtbar"); return False
        wert = _js(tab, f"return ({JS_MAX})({int(n)});"); ok = bool(wert)
        _log(f"max_treffer {n}: {'ok, Feld=' + str(wert) if ok else 'Feld fehlt'}")   # v260: gelesener Wert
        return ok
    except Exception as e:
        _log(f"max_treffer: {type(e).__name__}"); return False


def _max_einstellung():
    try:
        from ..config import load_settings
        return max(200, min(5000, int(load_settings().get("actanova_max_treffer", 1000))))
    except Exception: return 1000


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


LOG_MAX = 512 * 1024                     # v263: Rotation (eine ältere Datei .1)


def _k(text):
    """v263 (M6): Suchbegriffe und Aktenzeichen nicht im Log – nur Länge. Mit Einstellung
    «actanova_log_begriffe» = true (zur Fehlersuche) im Klartext."""
    try:
        from ..config import load_settings
        if load_settings().get("actanova_log_begriffe"): return f"'{text}'"
    except Exception: pass
    return f"[{len(text or '')} Z.]"


def _log(zeile):
    LOGDATEI.parent.mkdir(parents=True, exist_ok=True)
    try:
        if LOGDATEI.exists() and LOGDATEI.stat().st_size > LOG_MAX:
            os.replace(LOGDATEI, LOGDATEI.with_name(LOGDATEI.name + ".1"))
    except OSError: pass
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
        alle = edge.tabs()
        offen = [t for t in alle if ist_erlaubt(t.get("url", ""), "actanova")]
        if not offen:                                            # v286: Start-Tab steht evtl. noch auf der eIAM-Anmeldung
            offen = [t for t in alle if _start_tab["id"] and t.get("id") == _start_tab["id"]]
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


def _init_diagnose(tab):
    """v223: Was wartet die Init-Seite? Text, angefragte Hosts (z.B. localhost des Acta-Nova-Clients), Fehler."""
    try:
        info = tab.js("""(() => { const r = performance.getEntriesByType('resource').map(e => e.name.split('?')[0]);
            const hosts = [...new Set(r.map(u => { try { return new URL(u).host } catch(e) { return u } }))];
            return JSON.stringify({text: (document.body ? document.body.innerText : '').slice(0, 200),
                hosts: hosts, letzte: r.slice(-6), sichtbar: document.visibilityState, fokus: document.hasFocus()}); })()""")
        _log(f"init diagnose: {str(info)[:900]}")
    except Exception as x:
        _log(f"init diagnose fehlgeschlagen: {x}")


def init_haenger_loesen(tab, warten=20.0, versuche=2, erst=6.0):
    """v213b: Haengt «DmsInitializationForm» («Client wird gestartet …»), zuerst Fenster sichtbar machen
    (der Client initialisiert offenbar nur sichtbar – so wirkt auch das manuelle Aus/Ein), danach neu laden.
    v282: Erster Versuch nur `erst` s. Konsole beim Hänger: «Failed to initialize content script … Receiving end does
    not exist» (WebExtensionTrayApplicationProxyDetection) – die Acta-Nova-Erweiterung ist im zuerst geladenen Tab
    noch nicht verbunden; erst ein erneutes Laden klappt. Langes Warten bringt also nichts."""
    for i in range(versuche + 1):
        _zeigen(tab)
        ende = time.time() + (min(erst, warten) if i == 0 else warten)
        while time.time() < ende:
            try: href = tab.js("location.href") or ""
            except Exception: href = ""
            if href and "DmsInitializationForm" not in href:
                _log(f"init ok nach Versuch {i}")
                return True
            time.sleep(0.5)
        _log(f"init haengt ({href[:60]}) - Versuch {i + 1}")
        if i == 0: _init_diagnose(tab)
        if i < versuche:                                       # v223: frisch zur Startseite (neues Token) statt Reload der
            try: tab.navigieren(start_url(), "actanova")       # Init-Seite mit altem ReturnUrl-Token
            except Exception as x: _log(f"neu laden fehlgeschlagen: {x}")
    return False


ERWEITERUNG = "llpihbcbbpaijhmmfgddchmkgabhefol"      # v283: Acta-Nova-Erweiterung (ID aus der Edge-Konsole)


def _erweiterung_da(tab):
    """v283: Läuft der Hintergrund der Acta-Nova-Erweiterung? (True/False, oder None = nicht feststellbar)"""
    try:
        r = tab.ws.cdp("Target.getTargets") or {}
        infos = r.get("targetInfos") or (r.get("result") or {}).get("targetInfos")
        if infos is None: return None
        return any(ERWEITERUNG in (t.get("url") or "") and t.get("type") != "page" for t in infos)
    except Exception:
        return None


_start_tab = {"id": None}                              # v286: Tab, den edge_starten_leer mit Acta Nova geladen hat


def _erweiterung_gestartet():
    """v299: Hintergrund der Erweiterung über die Browser-Verbindung (Target.getTargets, sieht auch Service Worker);
    /json allein listet ihn nicht zuverlässig -> bisher oft volle Wartezeit. Rückgabe True/False."""
    try:
        if any(ERWEITERUNG in (t.get("url") or "") for t in edge.http("/json")): return True
    except Exception: pass
    ws = None
    try:
        ws = edge.WS(edge.http("/json/version")["webSocketDebuggerUrl"])
        infos = (ws.cdp("Target.getTargets", timeout=3) or {}).get("targetInfos") or []
        return any(ERWEITERUNG in (t.get("url") or "") for t in infos)
    except Exception: return False
    finally:
        if ws: ws.schliessen()


def edge_starten_leer(max_s=None, nachlauf=None):
    """v285: Edge NICHT mehr direkt mit der Acta-Nova-Adresse starten. Bisher lud Edge die Seite (Zertifikat, PIN) schon
    beim Start, bevor die per Richtlinie verwaltete Erweiterung «Acta Nova Client» bereit war -> «Receiving end does
    not exist», erst der zweite Start klappte. Manuell (Edge erst offen, dann Acta Nova) klappt es immer – genau das
    ahmt AURA jetzt nach: leer starten, auf die Erweiterung warten, kurze Nachlaufzeit, dann Acta Nova laden."""
    if edge.laeuft(): return False
    t0 = time.time(); edge.starten("about:blank")
    try:
        from ..config import load_settings
        st = load_settings()
    except Exception: st = {}
    if nachlauf is None: nachlauf = float(st.get("acta_nachlauf_s", 1.5))   # v299: bisher fest 5 s
    # v300: Log 23.11. 18:29: auf dem leeren Tab wird die Erweiterung nie sichtbar («nicht gesehen nach 32.4 s») – sie
    # startet erst mit der Acta-Nova-Seite. Langes Warten bringt nichts; bereit_machen() wartet danach auf die Erweiterung
    # und laedt neu («bereit: Erweiterung da», «neu geladen», «init ok»). Darum nur noch kurz warten (Standard 3 s).
    if max_s is None: max_s = float(st.get("acta_erweiterung_warten_s", 3.0))
    ende, gesehen = time.time() + max_s, False
    while time.time() < ende:
        gesehen = _erweiterung_gestartet()                        # v299: auch Service Worker erkennen
        if gesehen: break
        time.sleep(0.3)
    t_erw = time.time() - t0
    time.sleep(nachlauf)
    _log(f"edge: leer gestartet, Erweiterung {'da' if gesehen else 'nicht gesehen'} nach {t_erw:.1f} s, "
         f"Nachlauf {nachlauf:.1f} s, jetzt Acta Nova laden")
    try:
        alle = edge.tabs()
        _log("edge: Tabs " + ", ".join((x.get("url") or "?")[:40] for x in alle))          # v287: Diagnose
        leer = [x for x in alle if (x.get("url") or "") in ("about:blank", "") or (x.get("url") or "").startswith("edge://newtab")]
        if leer:                                                  # v287: nur den leeren Start-Tab nehmen, nie einen
            t = edge.Tab(leer[0])                                 # versteckten (z. B. Seite der Erweiterung)
            try: t.navigieren(start_url(), "actanova")
            except Exception: t.schliessen(); raise
        else:
            t = edge.tab_neu(start_url())
        _start_tab["id"] = t.info.get("id")                       # v286: diesen Tab merken (kein zweiter)
        try: edge.fenster(t, "normal"); t.ws.cdp("Page.bringToFront")
        except Exception: pass
        finally: t.schliessen()
        _log("edge: Acta Nova geladen")
    except Exception as x:
        _log(f"edge: Acta Nova laden fehlgeschlagen: {type(x).__name__}: {str(x)[:120]}")
    return True


def bereit_machen(tab, anmeldung_max=300.0):
    """v282: Nach dem Einschalten von Acta Nova: warten, bis der Mensch angemeldet ist (Adresse auf dem Acta-Nova-Host),
    dann den bekannten Erst-Hänger sofort per Neuladen lösen. So scheitert nicht mehr die erste Frage im Chat."""
    host = url_teil(); ende = time.time() + anmeldung_max
    while time.time() < ende:
        try: href = tab.js("location.href") or ""
        except Exception: href = ""
        if host in href: break
        time.sleep(1.0)
    else:
        _log("bereit: Anmeldung nicht abgeschlossen"); return False
    _log("bereit: angemeldet")
    # v283: Die Seite fragt die Erweiterung, bevor deren Hintergrund läuft («Receiving end does not exist», Konsole
    # 19.11.). Darum zuerst bis 30 s auf die Erweiterung warten und dann neu laden – erst dann klappt die Initialisierung.
    erw = None; ende = time.time() + 30
    while time.time() < ende:
        erw = _erweiterung_da(tab)
        if erw is not False: break
        time.sleep(1.0)
    _log(f"bereit: Erweiterung {'da' if erw else 'fehlt' if erw is False else 'nicht prüfbar'}")
    try: href = tab.js("location.href") or ""
    except Exception: href = ""
    if "DmsInitializationForm" in href:                     # hängt am Start -> nach Erweiterung einmal frisch laden
        time.sleep(1.0)
        try: tab.navigieren(start_url(), "actanova"); _log("bereit: neu geladen")
        except Exception as x: _log(f"bereit: neu laden fehlgeschlagen: {type(x).__name__}")
    ok = init_haenger_loesen(tab, 30.0, 2, 6.0)
    if ok: ok = _warten(tab, "AN.text('Suchen', true)", 20, 0.5)
    # v284: Log 19.11. 07:15–07:19: Erweiterung «da», drei Neuladungen im selben Tab hängen; Minuten später klappt es
    # sofort. Darum nicht mehr denselben Tab neu laden, sondern einen frischen Tab öffnen (Inhaltsskript wird neu
    # angebunden) und den alten schliessen – bis zu 4 Runden über ca. 2 Minuten, still im Hintergrund.
    runde = 0
    while not ok and runde < 4:
        runde += 1; time.sleep(10)
        try:
            neu = edge.tab_neu(start_url()); _log(f"bereit: frischer Tab (Runde {runde})")
            alt, tab = tab, neu
            edge.tab_zu(alt)
            ok = init_haenger_loesen(tab, 20.0, 0, 20.0) and _warten(tab, "AN.text('Suchen', true)", 20, 0.5)
        except Exception as x:
            _log(f"bereit: frischer Tab fehlgeschlagen: {type(x).__name__}")
    if runde:
        try: tab.schliessen()                                  # Verbindung zum neuen Tab; der Tab selbst bleibt offen
        except Exception: pass
    _log(f"bereit: {'ok' if ok else 'nicht bereit'}")
    return ok


def verbinden():
    """Haengt sich an die offene Acta-Nova-Sitzung. Startet Edge, falls noetig (Anmeldung macht der Mensch)."""
    edge_starten_leer()                                            # v285: erst leer starten, dann Acta Nova
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


JS_DIALOG_OK = r"""// v263 (H5): nur in einem gefundenen Dialog, der den Brotkrümel- bzw. Trefferzahl-Hinweis enthält
  for (const d of AN.docs()) for (const b of d.querySelectorAll('button, a, input[type=button], span')) {
    if (!/^(OK|Ok)$/.test((b.innerText || b.value || '').trim()) || !AN.sichtbar(b)) continue;
    const dlg = b.closest('[role=dialog], [role=alertdialog], [class*=Dialog], [class*=dialog], [class*=Modal], [class*=modal]');
    if (!dlg || dlg === d.body) continue;
    const t = dlg.innerText || ''; if (t.length > 600) continue;
    if (/Brotkr|maximale Anzahl der Eintr/.test(t)) { b.click(); return true; } }
  return false;"""

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
    """v220: Bleibt die Trefferseite aus (jede 2. Suche), Startseite neu laden und genau einmal wiederholen."""
    try:
        return _suchen_einmal(tab, art, feld_tab, feld, begriff, protokoll, export, streng=True)
    except ActaNovaFehler as e:
        if "Trefferseite" not in str(e) and "Suchfeld" not in str(e) and "Suchen" not in str(e): raise
        _log(f"wiederhole {_k(begriff)} ({art}) nach: {str(e)[:80]}"); protokoll.append("Neuladen + Wiederholung")
        tab.navigieren(start_url(), "actanova"); _warten(tab, "document.readyState === 'complete'", 30); time.sleep(1.5)
        return _suchen_einmal(tab, art, feld_tab, feld, begriff, protokoll, export, streng=False)


def _suchen_einmal(tab, art, feld_tab, feld, begriff, protokoll, export=False, streng=False):
    f = FORM[art]
    t0 = time.perf_counter(); zeiten = {}
    _log(f"  {art}: Maske oeffnen"); _formular_oeffnen(tab, art, protokoll); zeiten["maske"] = time.perf_counter() - t0
    _log(f"  {art}: Maske offen")
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
    if not _max_treffer(tab, _max_einstellung()) and streng:   # v259: mehr als 200 Treffer (Reiter «Suchabfrage»)
        # v289: Erscheint das Feld nicht, ist die Maske halb neu geladen – dann blieb der Klick auf «Suchen» wirkungslos
        # und AURA wartete 90 s (Log 17.–19.11.). Sofort neu aufbauen; im zweiten Durchgang notfalls ohne Trefferzahl.
        raise ActaNovaFehler("Suchfeld Trefferzahl nicht bereit – Maske neu")
    elif not streng and not _js(tab, "return /Maximale Anzahl/.test(AN.docs().map(d => d.body ? d.body.innerText : '').join(' '));"):
        _klick_id(tab, f["tab_basis"]); _warten(tab, "AN.el('SearchButton')", 5)   # v289: zurück auf die Grundmaske
    _log(f"  {art}: suche"); 
    if not _klick_id(tab, "SearchButton"):
        raise ActaNovaFehler("Knopf 'Suchen' fehlt")
    t1 = time.perf_counter()
    ok = _warten(tab, "AN.el('BackButton') || /Suchergebnisse \\(Anzahl|keine (Such)?ergebnisse/i.test(AN.docs().map(d => d.body ? d.body.innerText : '').join(' '))", 90, 1.0)
    if not ok:
        raise ActaNovaFehler(f"Keine Trefferseite nach 90 s – Seite: {tab.zustand()[:120]}")
    zeiten["suche"] = time.perf_counter() - t1
    _log(f"  {art}: Treffer lesen"); erg = _treffer_lesen(tab)
    t2 = time.perf_counter()
    if export and erg["treffer"] and (erg["weitere"] or (erg["anzahl"] or 0) > len(erg["treffer"])):
        alle = exportieren(tab)
        if alle:
            erg["alle"] = alle
            protokoll.append(f"Export: {len(alle)} Zeilen")
        else:
            protokoll.append("Export fehlgeschlagen -> nur Seite 1")
    zeiten["export"] = time.perf_counter() - t2
    _diag(f"{art} {_k(begriff)} " + " ".join(f"{k}={v:.1f}s" for k, v in zeiten.items()) + f" treffer={erg.get('anzahl')}")
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
        _log(f"{modus} {_k(begriff)} -> {n} in {time.time() - t0:.1f}s")
    except Exception as e:
        _log(f"{modus} {_k(begriff)} FEHLER {type(e).__name__}")
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


_NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_NS_PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _datenblatt(z):
    """v281: Pfad des ersten Blatts ohne «#» im Namen. Rückfall: kleinste Blattnummer (numerisch, nicht alphabetisch)."""
    try:
        ziele = {r.get("Id"): r.get("Target", "") for r in _xml(z, "xl/_rels/workbook.xml.rels").iter(_NS_PR + "Relationship")}
        for s in _xml(z, "xl/workbook.xml").iter(_NS + "sheet"):
            if (s.get("name") or "").startswith("#"): continue
            t = ziele.get(s.get(_NS_R + "id"), "").lstrip("/")
            pfad = t if t.startswith("xl/") else "xl/" + t
            if pfad in z.namelist(): return pfad
    except (KeyError, ActaNovaFehler, _ET.ParseError):
        pass
    nr = lambda n: int(_re.search(r"(\d+)\.xml$", n).group(1)) if _re.search(r"(\d+)\.xml$", n) else 0
    return sorted((n for n in z.namelist() if _re.match(r"xl/worksheets/sheet\d+\.xml$", n)), key=nr)[0]


def _xlsx_zeilen(pfad):
    """Minimaler xlsx-Leser (ohne openpyxl): Datenblatt als Liste von Zeilen (Strings). v212: harte Grenzen.
    v281: Acta Nova legt vorne Hilfsblätter an («#Aliases», Auswahllisten). Gelesen wird das erste Blatt, dessen
    Name nicht mit «#» beginnt (Reihenfolge laut workbook.xml); bisher wurde stets sheet1 = «#Aliases» gelesen."""
    from .. import sicherheit as SI
    SI.pruefe_dokument(pfad, XLSX_MAX_DATEI)
    with zipfile.ZipFile(pfad) as z:
        SI.zip_pruefen(z, max_eintraege=2000, max_datei=XLSX_MAX_XML, max_gesamt=4 * XLSX_MAX_XML)
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in _xml(z, "xl/sharedStrings.xml").iter(_NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(_NS + "t"))[:5000])
                if len(shared) > XLSX_MAX_STRINGS: raise ActaNovaFehler("Export zu gross (zu viele Texte)")
        blatt = _datenblatt(z)
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
    Rueckgabe: Liste von dicts (Spaltenname -> Wert) oder None.
    v264: Downloadziel über «Browser.setDownloadBehavior» (browserweit). «Page.setDownloadBehavior» wirkte in Edge
    nicht: Die Datei landete im normalen Download-Ordner, AURA fand sie nicht («Export fehlgeschlagen»)."""
    ordner = Path(tempfile.mkdtemp(prefix="aura_acta_"))
    browser = False
    try:
        try:
            tab.ws.cdp("Browser.setDownloadBehavior", behavior="allow", downloadPath=str(ordner)); browser = True
        except Exception:
            tab.ws.cdp("Page.setDownloadBehavior", behavior="allow", downloadPath=str(ordner))
        if not _klick_id(tab, "ExcelExportButton"):
            _log("export: Knopf fehlt"); return None
        ende = time.time() + timeout
        datei = None
        while time.time() < ende:
            time.sleep(0.5)
            fertig = [p for p in ordner.glob("*.xlsx")]
            if fertig and not list(ordner.glob("*.crdownload")):
                datei = fertig[0]
                break
        if not datei:
            _log(f"export: keine Datei nach {timeout:.0f} s ({'Browser' if browser else 'Page'})"); return None
        zeilen = _xlsx_zeilen(datei)
        # v281: Zeile 1 = technische Namen (FormattedNumber, FileHandlingContainer …), Zeile 2 = deutsche Spalten.
        # Das Ranking braucht die deutschen («Enthalten in», «Referenznummer») – diese Zeile zuerst suchen.
        deutsch = ("Enthalten in", "Referenznummer", "Aktenzeichen", "Titel")
        kopf_i = next((i for i, z in enumerate(zeilen[:10]) if any(k in z for k in deutsch)), None)
        if kopf_i is None:
            kopf_i = next((i for i, z in enumerate(zeilen[:10]) if "Name" in z), None)
        if kopf_i is None:
            _log("export: Kopfzeile nicht erkannt"); return None
        kopf = zeilen[kopf_i]
        # v281: Export hängt Objektverweise an («… (ar-032.1-131/14) <File|guid|System.Guid>») – wie in der Bildschirmliste kürzen
        ref = lambda v: _re.sub(r"\s*<[A-Za-z.]+\|[0-9a-fA-F-]+\|System\.Guid>\s*$", "", v)
        erg = [{k: ref(v) for k, v in zip(kopf, z) if k and ref(v)} for z in zeilen[kopf_i + 1:] if any(z)]
        _log(f"export: {len(erg)} Zeilen"); return erg
    finally:
        shutil.rmtree(ordner, ignore_errors=True)
        try:
            tab.ws.cdp("Browser.setDownloadBehavior" if browser else "Page.setDownloadBehavior", behavior="default")
        except Exception:
            pass


# ---------------------------------------------------------------- Ablageort in Acta Nova oeffnen
JS_FELD_NACH_LABEL = r"""(label) => {
  for (const d of AN.docs()) for (const c of d.querySelectorAll('td, th, label, span, div')) {
    if (c.children.length > 2 || (c.innerText || '').trim() !== label) continue;
    const row = c.closest('tr, [class*=Row], [class*=row]'); if (!row) continue;
    const inp = row.querySelector('input[type=text], input:not([type])'); if (inp && AN.sichtbar(inp)) return inp;
  } return null; }"""


JS_AZ_OBEN = r"""(titelSuffix, wert) => {
  // v262: Es gibt zwei Felder «Aktenzeichen»: oben (das Dossier selbst) und unter «Enthalten in» (sucht IN diesem
  // Dossier). Kandidaten: sichtbare Textfelder, deren Beschriftung mit «Aktenzeichen» beginnt (label[for], Zeile, Vorgänger).
  // Genommen wird das erste, das nicht im Block «Enthalten in» steht. Rückgabe: {ok, id, liste} für das Log.
  const norm = s => (s || '').replace(/\s+/g, ' ').trim(); const liste = []; let wahl = null;
  const beschr = e => {
    const l = e.id && e.ownerDocument.querySelector('label[for="' + e.id + '"]'); if (l) return norm(l.innerText);
    let p = e; for (let i = 0; i < 4 && p; i++) { p = p.parentElement; if (!p) break;
      let v = p.previousElementSibling; if (v && norm(v.innerText)) return norm(v.innerText).slice(0, 40); }
    return ''; };
  const imBlockEnthalten = e => { let p = e; for (let i = 0; i < 12 && p; i++) { p = p.parentElement;
      if (p && /ParentFile|Parent|Contained|Enthalten/i.test(p.id || '')) return true; } return /Parent|Contained/i.test(e.id || ''); };
  for (const d of AN.docs()) for (const e of d.querySelectorAll('input[type=text], input:not([type])')) {
    if (!AN.sichtbar(e)) continue; const b = beschr(e); const kurz = (e.id || '').split('_').slice(-4).join('_');
    liste.push(kurz + '=' + b);
    if (!wahl && /^Aktenzeichen/.test(b) && !imBlockEnthalten(e)) wahl = e;
  }
  if (!wahl) return {ok: false, liste: liste.slice(0, 30)};
  wahl.focus(); wahl.value = wert; wahl.dispatchEvent(new Event('input', {bubbles: true})); wahl.dispatchEvent(new Event('change', {bubbles: true}));
  return {ok: true, id: (wahl.id || '').split('_').slice(-4).join('_')}; }"""


def oeffnen(aktenzeichen, titel=None):
    """Sucht das Dossier/Subdossier mit diesem Aktenzeichen und oeffnet es im (sichtbar gemachten) Edge-Fenster.
    v258: zusätzlich mit Titel (sonst kamen alle Unterdossiers mit gleichem Anfang, und das erste wurde geöffnet).
    Findet die Suche mit Titel nichts, wird nur mit Aktenzeichen gesucht. Geöffnet wird die Zeile mit genau diesem
    Aktenzeichen, sonst die erste."""
    tab = verbinden()
    try:
        prot = []
        f = FORM["dossier"]
        _formular_oeffnen(tab, "dossier", prot)
        _klick_id(tab, "ResetSearchButton"); _warten(tab, f"AN.el({json.dumps(f['tab_basis'])})", 20)
        _reiter(tab, f["tab_basis"], f["status"])
        _status_leeren(tab, f["status"]); _warten(tab, "true", 10)
        r = _js(tab, f"return ({JS_AZ_OBEN})({json.dumps(f['titel'])}, {json.dumps(aktenzeichen)});") or {}
        if not r.get("ok"):
            _log(f"oeffnen: Feld Aktenzeichen fehlt; Felder: {r.get('liste')}")      # v262: Diagnose
            raise ActaNovaFehler("Oberes Feld «Aktenzeichen» in der Dossier-Suche nicht gefunden")
        _log(f"oeffnen: Aktenzeichen in {r.get('id')}")
        mit_titel = bool(titel) and _setzen(tab, f["titel"], titel)       # v259: Titelfeld über seine ID
        treffer = "AN.docs().some(d => d.querySelector('tr.bocListDataRow'))"
        # v290: «fertig» erst auf der Trefferseite (wie bei der Suche), nicht schon, wenn die Maske irgendeinen Text zeigt
        fertig = treffer + " || AN.el('BackButton') || /Suchergebnisse \\(Anzahl|keine (Such)?ergebnisse/i.test(AN.docs().map(d => d.body ? d.body.innerText : '').join(' '))"
        def suchen():                                                        # v259: bei «keine Suchergebnisse» nicht 60 s warten
            _js(tab, "AN.docs().forEach(d => d.querySelectorAll('tr.bocListDataRow').forEach(tr => tr.remove())); return true;")
            geklickt = _klick_id(tab, "SearchButton")
            ok = _warten(tab, fertig, 8, 0.5)
            if not ok and geklickt and _js(tab, "return AN.sichtbar(AN.el('SearchButton'));"):   # v290: Klick verpufft
                _log("oeffnen: Klick ohne Wirkung – nochmals"); _klick_id(tab, "SearchButton"); ok = _warten(tab, fertig, 50, 0.5)
            n = _js(tab, "return AN.docs().reduce((s, d) => s + d.querySelectorAll('tr.bocListDataRow').length, 0);") or 0
            _log(f"oeffnen: Suche {'Trefferseite' if ok else 'ohne Trefferseite'}, {n} Zeilen (Knopf {'ja' if geklickt else 'fehlt'})")
            return n > 0
        if not suchen():
            if not mit_titel: raise ActaNovaFehler(f"Kein Dossier mit Aktenzeichen {aktenzeichen}")
            _setzen(tab, f["titel"], "")                                       # v258: Titel weg, nur Aktenzeichen
            if not suchen(): raise ActaNovaFehler(f"Kein Dossier mit Aktenzeichen {aktenzeichen}")
        genau = json.dumps(_re.escape(aktenzeichen) + r"(?![/\d])")              # v258: genau dieses, kein Unterdossier
        gew = _js(tab, f"""const genau = new RegExp({genau});
            const zeilen = []; for (const d of AN.docs()) zeilen.push(...d.querySelectorAll('tr.bocListDataRow'));
            const z = zeilen.find(r => genau.test(r.innerText || '')) || zeilen[0]; if (!z) return false;
            const c = z.querySelector('td[role=rowheader] a') || z.querySelector('a'); if (!c) return false;
            c.click(); return true;""")
        _log(f"oeffnen {_k(aktenzeichen)}" + (" mit Titel" if mit_titel else "") + ("" if gew else " – Zeile nicht klickbar"))
    finally:
        edge.fenster(tab, "normal")
        try: tab.ws.cdp("Page.bringToFront")
        except Exception: pass


# ---------------------------------------------------------------- Sitzung offen halten (nur wenn eingeschaltet)
SPERRE = threading.Lock()
_wach = {"t": None, "echt": None, "selbst": None}


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
                jetzt, zul = time.time(), edge._zuletzt[0]
                if zul != _wach["selbst"]: _wach["echt"] = zul        # echte Nutzung seit dem letzten Wachhalten
                max_h = max(1, min(12, int(s.get("actanova_wach_max_h", 4))))
                if jetzt - (_wach["echt"] or jetzt) > max_h * 3600:   # v263 (M3): Höchstdauer ohne echte Nutzung
                    continue
                _log("wach halten: start")
                if edge.laeuft():
                    t = edge.tab_finden("actanova")
                    if t:
                        t.dialog_schliessen(); t.navigieren(start_url(), "actanova"); t.schliessen()
                        _log("wach halten: Startseite neu geladen")
                _wach["selbst"] = edge._zuletzt[0]                    # v263 (M3): eigene Nutzung erkennen
            except Exception:
                pass
            finally:
                SPERRE.release()
    _wach["t"] = threading.Thread(target=lauf, daemon=True); _wach["t"].start()
