# v224 Testbaustein: Teams Web (teams.microsoft.com/v2) live ueber Edge durchsuchen – nur lesend, eigenes Konto.
# Noch nicht im Chat eingebunden. Test:  from aura.engine import teams; teams.test("Suchbegriff")
import json, time
from datetime import datetime
from . import edge

URL = "https://teams.cloud.microsoft/"
LOGDATEI = edge.ROOT / "logs" / "teams.log"
SUCHFELD = ["#ms-searchux-input", "input[data-tid='searchInputField']", "input[type='search']",
            "input[placeholder*='Such']", "input[placeholder*='Search']", "[role='search'] input"]
TREFFER = ["[data-tid*='search-result']", "[data-tid*='searchResult']", "[id^='search-result']",
           "[role='listitem']", "[role='option']"]


def _log(z):
    LOGDATEI.parent.mkdir(parents=True, exist_ok=True)
    with open(LOGDATEI, "a", encoding="utf-8") as f: f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {z}\n")


def _warten(tab, js, timeout, ruhe=0.5):
    ende = time.time() + timeout
    while time.time() < ende:
        try:
            if tab.js(js): return True
        except Exception: pass
        time.sleep(ruhe)
    return False


def verbinden():
    edge.starten(URL)
    tab = edge.tab_finden("teams")
    if not tab: tab = edge.tab_neu(URL)
    sel = json.dumps(", ".join(SUCHFELD))
    if not _warten(tab, f"!!document.querySelector({sel})", 45):        # Teams braucht ~20 s
        raise RuntimeError("Teams-Suchfeld nach 45 s nicht gefunden (angemeldet?)")
    return tab


def suche(begriff, max_treffer=10):
    t0 = time.perf_counter(); tab = verbinden(); _log(f"suche '{begriff}': verbunden {time.perf_counter() - t0:.1f}s")
    sel = json.dumps(", ".join(SUCHFELD))
    tab.js(f"(() => {{ const e = document.querySelector({sel}); e.focus(); e.click(); "
           f"if ('value' in e) e.value = ''; return true; }})()")
    time.sleep(0.5)
    tab.ws.cdp("Input.insertText", text=begriff); time.sleep(0.3)
    for typ in ("keyDown", "keyUp"):
        tab.ws.cdp("Input.dispatchKeyEvent", type=typ, key="Enter", code="Enter", windowsVirtualKeyCode=13)
    time.sleep(6)                                                     # Ergebnisse laden
    diag = tab.js("""(() => { const sels = %s; const z = {};
        sels.forEach(s => z[s] = document.querySelectorAll(s).length);
        return JSON.stringify({url: location.href.slice(0, 120), zaehler: z}); })()""" % json.dumps(TREFFER))
    _log(f"  diagnose: {diag}")
    roh = tab.js("""(() => { const sels = %s; let el = [];
        for (const s of sels) { el = [...document.querySelectorAll(s)].filter(x => (x.innerText||'').trim().length > 20); if (el.length) break; }
        return JSON.stringify(el.slice(0, %d).map(x => x.innerText.replace(/\\s+/g, ' ').trim().slice(0, 400))); })()"""
                 % (json.dumps(TREFFER), max_treffer))
    treffer = json.loads(roh or "[]")
    _log(f"  {len(treffer)} Treffer in {time.perf_counter() - t0:.1f}s")
    for i, t in enumerate(treffer, 1): _log(f"  [{i}] {t[:300]}")
    tab.schliessen()
    return treffer


def test(begriff="AURA"):
    try:
        r = suche(begriff)
        print(f"{len(r)} Treffer – Details in {LOGDATEI}")
        for t in r[:5]: print("-", t[:150])
    except Exception as e:
        _log(f"FEHLER {type(e).__name__}: {e}"); print("Fehler:", e)
