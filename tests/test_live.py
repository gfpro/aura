# tests/test_live.py — Sicherheitstests v212 für Edge/CDP und Live-Quellen (V21-01 … V21-05). Kein Edge, kein Netz:
# alle Browser-/HTTP-Zugriffe sind Fakes. Ausführen:  py -m unittest discover -s tests -v
import io, shutil, sys, tempfile, threading, time, unittest, zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if sys.platform != "win32" and "winreg" not in sys.modules:
    import types; sys.modules["winreg"] = types.ModuleType("winreg")
from aura.engine import herkunft as HK, edge as E, intranet as IN, sharepoint as SP, actanova as AN   # noqa: E402

GUID = "/devtools/browser/0123abcd-4567-89ef-0123-456789abcdef"

class Herkunft(unittest.TestCase):
    def test_boese(self):
        for u in ("http://intranet.ar.admin.ch/de", "https://intranet.ar.admin.ch.attacker.invalid/",
                  "https://intranet.ar.admin.ch@attacker.invalid/", "https://user:pw@intranet.ar.admin.ch/",
                  "https://intranet.ar.admin.ch:8443/", "https://10.1.2.3/", "https://[::1]/", "https://evil.example/",
                  "https://sub.intranet.ar.admin.ch/", "https://intranet.ar.admin.ch./", "javascript:alert(1)",
                  "https://intranet.ar.admin.ch\\@evil/", "file:///C:/x", "", None, "https://intranet ar.admin.ch/"):
            with self.subTest(u=u): self.assertFalse(HK.ist_erlaubt(u, "intranet"))

    def test_gut(self):
        self.assertTrue(HK.ist_erlaubt("https://intranet.ar.admin.ch/de/search?x=1", "intranet"))
        self.assertTrue(HK.ist_erlaubt("https://INTRANET.ar.admin.ch:443/de", "intranet"))
        self.assertTrue(HK.ist_erlaubt("https://www.vbs.gever.admin.ch/web/Main.wxe", "actanova"))
        self.assertFalse(HK.ist_erlaubt("https://www.vbs.gever.admin.ch/web/Main.wxe", "intranet"))   # quellengetrennt
        self.assertTrue(HK.ist_erlaubt("https://portal.collab.admin.ch/sites/x"))                      # irgendeine Quelle

    def test_richtlinie(self):
        with mock.patch.object(HK, "_policy", lambda q: ("https://neu.admin.ch",) if q == "intranet" else ()):
            self.assertTrue(HK.ist_erlaubt("https://neu.admin.ch/x", "intranet"))
            self.assertFalse(HK.ist_erlaubt("https://intranet.ar.admin.ch/x", "intranet"))

# ---------------------------------------------------------------- V21-01 Edge-Bindung
class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aura_live_")); self.addCleanup(shutil.rmtree, self.tmp, True)
        prof = self.tmp / "edge_profil"; prof.mkdir()
        for k, v in (("PROFIL", prof), ("AKTIV", prof / "DevToolsActivePort"), ("PORTDATEI", self.tmp / "edge_port.txt"), ("PORT", 0)):
            p = mock.patch.object(E, k, v); p.start(); self.addCleanup(p.stop)
        E._proc["p"] = None

class EdgeBindung(Tmp):
    def fake_http(self, antworten):
        def h(path, method="GET", port=None):
            port = port or E.PORT
            if port not in antworten: raise ConnectionRefusedError
            return antworten[port]
        return mock.patch.object(E, "http", h)

    def test_kein_9222_fallback(self):
        with self.fake_http({9222: {"webSocketDebuggerUrl": "ws://127.0.0.1:9222" + GUID}}):
            self.assertFalse(E.laeuft()); self.assertEqual(E.PORT, 0)
        with self.assertRaises(E.EdgeFehler): E.http.__wrapped__ if hasattr(E.http, "__wrapped__") else E.http("/json")

    def test_fremde_instanz_mit_falscher_id(self):
        E.AKTIV.write_text(f"40123\n{GUID}\n")
        with self.fake_http({40123: {"webSocketDebuggerUrl": "ws://127.0.0.1:40123/devtools/browser/ffff0000-1111-2222-3333-444455556666"}}):
            self.assertFalse(E.laeuft())

    def test_manipulierte_portdatei(self):
        for inhalt in ("9222\n", "abc\n" + GUID, f"80\n{GUID}", f"40123\n/devtools/page/x"):
            with self.subTest(inhalt=inhalt):
                E.AKTIV.write_text(inhalt)
                with self.fake_http({40123: {"webSocketDebuggerUrl": "ws://127.0.0.1:40123" + GUID}, 9222: {}, 80: {}}):
                    self.assertFalse(E.laeuft())

    def test_eigene_instanz_ok(self):
        E.AKTIV.write_text(f"40123\n{GUID}\n")
        with self.fake_http({40123: {"webSocketDebuggerUrl": "ws://127.0.0.1:40123" + GUID}}):
            self.assertTrue(E.laeuft()); self.assertEqual(E.PORT, 40123)

    def test_ws_ziel(self):
        with mock.patch.object(E, "PORT", 40123):
            E.ws_pruefen("ws://127.0.0.1:40123/devtools/page/AB")
            for u in ("ws://127.0.0.1:9222/devtools/page/AB", "ws://evil:40123/devtools/page/AB", "wss://127.0.0.1:40123/devtools/x",
                      "ws://localhost:40123/devtools/x", "ws://127.0.0.1:40123/x", "ws://u@127.0.0.1:40123/devtools/x"):
                with self.subTest(u=u), self.assertRaises(E.EdgeFehler): E.ws_pruefen(u)

    def test_start_url_fremd_abgelehnt_vor_start(self):
        with mock.patch.object(E.subprocess, "Popen") as po, self.assertRaises(HK.HerkunftFehler):
            E.starten("https://evil.example/")
        po.assert_not_called()

    def test_tab_neu_fremd_abgelehnt(self):
        with mock.patch.object(E, "tabs") as t, self.assertRaises(HK.HerkunftFehler): E.tab_neu("https://evil.example/")
        t.assert_not_called()

    def test_tab_finden_exakter_origin(self):
        liste = [{"type": "page", "url": "https://www.vbs.gever.admin.ch.evil.invalid/x", "id": "1"},
                 {"type": "page", "url": "https://evil.invalid/?q=www.vbs.gever.admin.ch", "id": "2"}]
        with mock.patch.object(E, "tabs", lambda: liste), mock.patch.object(E, "Tab") as T:
            self.assertIsNone(E.tab_finden("actanova")); T.assert_not_called()

    def test_beenden_haengender_prozess(self):
        E.AKTIV.write_text(f"40123\n{GUID}\n")
        p = mock.Mock(); p.poll.return_value = None; E._proc["p"] = p
        with mock.patch.object(E, "laeuft", lambda: True), mock.patch.object(E, "WS"), mock.patch.object(E, "http", lambda *a, **k: {"webSocketDebuggerUrl": ""}), \
             mock.patch.object(E, "cache_leeren") as cl:
            self.assertFalse(E.beenden(warten=0.1))
        p.terminate.assert_called(); cl.assert_not_called(); self.assertTrue(E.AKTIV.exists())

    def test_beenden_ok_raeumt_auf(self):
        E.AKTIV.write_text(f"40123\n{GUID}\n"); E.PORTDATEI.write_text("1")
        with mock.patch.object(E, "laeuft", lambda: False), mock.patch.object(E, "cache_leeren") as cl:
            self.assertTrue(E.beenden(warten=0.1))
        cl.assert_called(); self.assertFalse(E.AKTIV.exists()); self.assertFalse(E.PORTDATEI.exists())

    def test_cache_leeren_entfernt_verlauf_behaelt_cookies(self):
        d = E.PROFIL / "Default"; (d / "Cache").mkdir(parents=True)
        for n in ("History", "Cookies", "Visited Links"): (d / n).write_text("x")
        (d / "Local Storage").mkdir()
        with mock.patch.object(E, "laeuft", lambda: False): E.cache_leeren(0.1)
        self.assertFalse((d / "History").exists()); self.assertFalse((d / "Cache").exists())
        self.assertTrue((d / "Cookies").exists()); self.assertTrue((d / "Local Storage").exists())

# ---------------------------------------------------------------- V21-03 Dialoge
class FakeWS:
    def __init__(self, typ=None):
        self.lock = threading.Condition(); self.calls = []
        self.events = [{"method": "Page.javascriptDialogOpening", "params": {"type": typ}}] if typ else []
    def cdp(self, method, timeout=30, **kw):
        self.calls.append((method, kw))
        if method == "Runtime.evaluate" and kw.get("expression") == "HAENGT": raise TimeoutError(method)
        return {"result": {"value": "ok"}}
    def schliessen(self): pass

def fake_tab(typ):
    t = E.Tab.__new__(E.Tab); t.info = {"url": "https://www.vbs.gever.admin.ch/"}; t.ws = FakeWS(typ); return t

class Dialoge(unittest.TestCase):
    def acc(self, t): return [kw["accept"] for m, kw in t.ws.calls if m == "Page.handleJavaScriptDialog"]

    def test_nur_alert_wird_bestaetigt(self):
        for typ, soll in (("alert", True), ("confirm", False), ("prompt", False), ("beforeunload", False), (None, False), ("neu", False)):
            with self.subTest(typ=typ):
                t = fake_tab(typ); t.dialog_schliessen(); self.assertEqual(self.acc(t), [soll])

    def test_timeout_bestaetigt_nie_confirm(self):
        t = fake_tab("confirm")
        with self.assertRaises(TimeoutError): t.js("HAENGT", timeout=1)
        self.assertEqual(self.acc(t), [False])

# ---------------------------------------------------------------- V21-02 / V21-05 Live-Quellen
class Live(unittest.TestCase):
    def test_intranet_fremde_treffer_verworfen(self):
        nav = []
        tab = mock.Mock(); tab.navigieren.side_effect = lambda u, q=None: (HK.pruefe(u, q), nav.append(u))
        treffer = [{"url": "https://intranet.ar.admin.ch/de/a", "titel": "a"}, {"url": "https://intranet.ar.admin.ch.attacker.invalid/b", "titel": "b"},
                   {"url": "https://intranet.ar.admin.ch@attacker.invalid/c", "titel": "c"}, {"url": "http://intranet.ar.admin.ch/d", "titel": "d"}]
        with mock.patch.object(IN, "basis", lambda: ("https://intranet.ar.admin.ch", "/de")), \
             mock.patch.object(IN, "_warten", lambda *a, **k: {"fertig": True, "anzahl": 4, "treffer": treffer}):
            out, _ = IN.suchen(tab, "x")
        self.assertEqual([t["url"] for t in out], ["https://intranet.ar.admin.ch/de/a"])
        self.assertTrue(all(HK.ist_erlaubt(u, "intranet") for u in nav))

    def test_intranet_basis_nur_freigegeben(self):
        for u in ("https://intranet.ar.admin.ch.evil.invalid/de", "http://intranet.ar.admin.ch/de", "https://evil.example/de"):
            with self.subTest(u=u), mock.patch("aura.config.load_settings", lambda: {"intranet_url": u}):
                self.assertEqual(IN.basis(), ("", ""))
        with mock.patch("aura.config.load_settings", lambda: {"intranet_url": "https://intranet.ar.admin.ch/fr"}):
            self.assertEqual(IN.basis(), ("https://intranet.ar.admin.ch", "/fr"))

    def test_intranet_stuecke_begrenzt(self):
        st = IN._stuecke("A" * 50_000 + "\n\n" + "kurz")
        self.assertTrue(all(len(x) <= IN.STUECK + 10 for x in st))
        self.assertLessEqual(len(IN._stuecke(("x" * 800 + "\n\n") * 100_000)), IN.MAX_STUECKE)

    def test_sharepoint_sites_gefiltert(self):
        with mock.patch("aura.config.load_settings", lambda: {"sharepoint_sites": ["https://portal.collab.admin.ch/sites/a", "https://portal.collab.admin.ch.evil.invalid/sites/b", "http://portal.collab.admin.ch/sites/c"]}):
            _, sites = SP._einstellungen()
        self.assertEqual(sites, ["https://portal.collab.admin.ch/sites/a"])

    def test_acta_start_url(self):
        with mock.patch("aura.config.load_settings", lambda: {"actanova_url": "https://www.vbs.gever.admin.ch.evil.invalid/web"}), self.assertRaises(HK.HerkunftFehler):
            AN.start_url()
        with mock.patch("aura.config.load_settings", lambda: {}):
            self.assertEqual(AN.start_url(), AN.STANDARD_URL)

class Xlsx(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp, True)

    def xlsx(self, rows, doctype=False):
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        body = "".join(f'<row><c r="A{i+1}" t="inlineStr"><is><t>{v}</t></is></c></row>' for i, v in enumerate(rows))
        x = ('<!DOCTYPE x [<!ENTITY a "b">]>' if doctype else "") + f'<worksheet xmlns="{ns}"><sheetData>{body}</sheetData></worksheet>'
        p = self.tmp / "e.xlsx"
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z: z.writestr("xl/worksheets/sheet1.xml", x)
        return p

    def test_normal(self):
        self.assertEqual(AN._xlsx_zeilen(self.xlsx(["Name", "Dok"])), [["Name"], ["Dok"]])

    def test_zu_viele_zeilen(self):
        with mock.patch.object(AN, "XLSX_MAX_ZEILEN", 5), self.assertRaises(AN.ActaNovaFehler): AN._xlsx_zeilen(self.xlsx(["x"] * 10))

    def test_doctype_abgelehnt(self):
        with self.assertRaises(AN.ActaNovaFehler): AN._xlsx_zeilen(self.xlsx(["x"], doctype=True))

    def test_datei_zu_gross(self):
        with mock.patch.object(AN, "XLSX_MAX_DATEI", 10), self.assertRaises(Exception): AN._xlsx_zeilen(self.xlsx(["x"]))

if __name__ == "__main__": unittest.main()
