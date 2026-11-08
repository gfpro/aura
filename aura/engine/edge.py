"""Edge-Bruecke: sichtbares Edge mit Debug-Port fernsteuern (DevTools-Protokoll, CDP).
Nur Python-Standardbibliothek. Anmeldung (Smartcard/PIN, SSO) macht der Mensch im Fenster;
AURA haengt sich an die laufende Sitzung an. Keine Credentials in AURA.
v212 Sicherheit: Edge waehlt den Port selbst (--remote-debugging-port=0) und schreibt ihn mit der geheimen Browser-ID in
data\\edge_profil\\DevToolsActivePort. AURA verbindet NUR, wenn /json/version exakt diese ID liefert (= Edge mit
AURA-Profil); kein Rueckfall auf 9222, keine fremde Instanz. WebSockets nur zu ws://127.0.0.1:<dieser Port>.
Navigation nur zu freigegebenen Origins (herkunft.py). Dialoge: nur «alert» bestaetigen, confirm/prompt/beforeunload
ablehnen. Restrisiko: der Loopback-Port ist fuer jeden lokalen Prozess erreichbar (CDP hat keine Anmeldung) –
darum schliesst AURA Edge nach Leerlauf (Einstellung «edge_leerlauf_min», Standard 60) und beim Beenden.
"""
import base64, json, os, re, socket, struct, subprocess, threading, time, urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
PROFIL = ROOT / "data" / "edge_profil"
PORTDATEI = ROOT / "data" / "edge_port.txt"          # bis v211; wird nicht mehr gelesen, nur noch entfernt
AKTIV = PROFIL / "DevToolsActivePort"                 # schreibt Edge selbst: Zeile 1 Port, Zeile 2 /devtools/browser/<id>
PORT = 0                                              # 0 = keine verifizierte Sitzung
_proc = {"p": None}
_zuletzt = [time.time()]
MAX_JSON = 8 * 2**20

_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # localhost nie ueber Proxy


class EdgeFehler(RuntimeError):
    pass


def _aktiv():
    """(port, browser_pfad) aus DevToolsActivePort oder None."""
    try:
        z = AKTIV.read_text(encoding="ascii").split()
        port, pfad = int(z[0]), z[1]
        if 1024 <= port <= 65535 and re.fullmatch(r"/devtools/browser/[0-9a-fA-F-]{8,64}", pfad): return port, pfad
    except Exception: pass
    return None


def http(path, method="GET", port=None):
    port = port or PORT
    if not port: raise EdgeFehler("Keine verifizierte AURA-Edge-Sitzung")
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
    with _http.open(req, timeout=5) as r:
        data = r.read(MAX_JSON + 1)
    if len(data) > MAX_JSON: raise EdgeFehler("Antwort von Edge zu gross")
    return json.loads(data.decode("utf-8"))


def _verifizieren():
    """Port nur uebernehmen, wenn die Browser-ID aus dem AURA-Profil exakt stimmt. -> True/False."""
    global PORT
    p = _proc["p"]
    if p is not None and p.poll() is not None and not _aktiv():
        PORT = 0; return False
    a = _aktiv()
    if not a: PORT = 0; return False
    port, pfad = a
    try:
        v = http("/json/version", port=port)
        if v.get("webSocketDebuggerUrl") == f"ws://127.0.0.1:{port}{pfad}":
            PORT = port; return True
    except Exception: pass
    PORT = 0; return False


def ws_pruefen(url):
    """CDP-WebSocket nur zu ws://127.0.0.1:<verifizierter Port>/devtools/..."""
    from urllib.parse import urlsplit
    u = urlsplit(url or "")
    if u.scheme != "ws" or u.hostname != "127.0.0.1" or u.port != PORT or not PORT or not u.path.startswith("/devtools/") \
            or u.username or u.password or u.netloc != f"127.0.0.1:{PORT}":
        raise EdgeFehler("CDP-Verbindung zu unerwartetem Ziel abgelehnt")
    return url


def benutzt():
    _zuletzt[0] = time.time()


def edge_pfad():
    for p in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""),
              os.environ.get("LOCALAPPDATA", "")):
        f = Path(p) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if f.exists():
            return str(f)
    raise RuntimeError("msedge.exe nicht gefunden")


def laeuft():
    """True nur fuer die verifizierte AURA-Edge (eigenes Profil, Browser-ID passt)."""
    return _verifizieren()


def starten(start_url="about:blank", warten=20.0):
    """Startet Edge mit Debug-Port und eigenem Profil, falls noch nicht offen. Gibt Browser-Version zurueck.
    Sicherheit: zufaelliger Port je Start, nur 127.0.0.1; Edge wird beim Beenden von AURA geschlossen."""
    if start_url != "about:blank":
        from .herkunft import pruefe
        pruefe(start_url)                                         # v212: nur freigegebene Live-Quellen
    benutzt()
    if not laeuft():
        PROFIL.mkdir(parents=True, exist_ok=True)
        for f in (AKTIV, PORTDATEI):                              # alte Angaben nie weiterverwenden
            try: f.unlink()
            except OSError: pass
        _proc["p"] = subprocess.Popen([edge_pfad(), "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
                          f"--user-data-dir={PROFIL}",
                          "--no-first-run", "--no-default-browser-check",
                          # minimiert weiterarbeiten: keine Drosselung von Timern/Rendering im Hintergrund
                          "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
                          "--disable-backgrounding-occluded-windows",
                          "--disk-cache-size=52428800",          # Seiten-Cache klein halten (50 MB), wird beim Beenden geloescht
                          # Windows: verdeckte/minimierte Fenster nicht drosseln; Edge-Schlafmodus für Tabs aus
                          "--disable-features=CalculateNativeWinOcclusion,msSleepingTabs,msEdgeSleepingTabs,TabFreeze,IntensiveWakeUpThrottling",
                          start_url])
        ende = time.time() + warten
        while not laeuft():
            if time.time() > ende:
                raise EdgeFehler("AURA-Edge antwortet nicht (DevToolsActivePort fehlt oder passt nicht) – abgebrochen")
            time.sleep(0.5)
        _waechter_starten()
    return http("/json/version").get("Browser", "?")


def _waechter_starten():
    """Schliesst die AURA-Edge nach Leerlauf (Einstellung «edge_leerlauf_min», 0 = nie)."""
    if getattr(_waechter_starten, "t", None) and _waechter_starten.t.is_alive(): return
    def lauf():
        while True:
            time.sleep(60)
            try:
                from ..config import load_settings
                m = float(load_settings().get("edge_leerlauf_min", 60) or 0)
            except Exception: m = 60
            if m > 0 and time.time() - _zuletzt[0] > m * 60 and laeuft():
                beenden(); return
            if not laeuft(): return
    _waechter_starten.t = threading.Thread(target=lauf, daemon=True); _waechter_starten.t.start()


class WS:
    """Minimaler WebSocket-Client fuer CDP."""

    def __init__(self, url):
        ws_pruefen(url)                                           # v212
        hostport, path = url.split("://", 1)[1].split("/", 1)
        host, port = hostport.split(":")
        self.s = socket.create_connection((host, int(port)), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n"
                        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                        f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            c = self.s.recv(4096)
            if not c:
                raise IOError("Handshake abgebrochen")
            buf += c
        head, self.rest = buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise IOError(head.decode(errors="replace"))
        self.s.settimeout(None)
        self.id = 0
        self.antworten, self.events = {}, []
        self.offen = True
        self.lock = threading.Condition()
        threading.Thread(target=self._lesen, daemon=True).start()

    def _recv(self, n):
        while len(self.rest) < n:
            c = self.s.recv(65536)
            if not c:
                raise IOError("Verbindung geschlossen")
            self.rest += c
        d, self.rest = self.rest[:n], self.rest[n:]
        return d

    def _frame(self):
        b1, b2 = self._recv(2)
        n = b2 & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._recv(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self._recv(8))[0]
        if b2 & 0x80:
            m = self._recv(4)
            data = bytes(x ^ m[i % 4] for i, x in enumerate(self._recv(n)))
        else:
            data = self._recv(n)
        return b1 & 0x80, b1 & 0x0F, data

    def _lesen(self):
        teile = b""
        try:
            while True:
                fin, op, data = self._frame()
                if op == 9:
                    self._send(data, 0xA)
                    continue
                if op == 8:
                    break
                teile += data
                if not fin:
                    continue
                msg = json.loads(teile.decode("utf-8"))
                teile = b""
                with self.lock:
                    if "id" in msg:
                        self.antworten[msg["id"]] = msg
                    else:
                        self.events.append(msg)
                        del self.events[:-2000]
                    self.lock.notify_all()
        except Exception:
            pass
        finally:
            with self.lock:
                self.offen = False
                self.lock.notify_all()

    def _send(self, data, op=1):
        m, n = os.urandom(4), len(data)
        head = bytes([0x80 | op])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.s.sendall(head + m + bytes(x ^ m[i % 4] for i, x in enumerate(data)))

    def cdp(self, method, timeout=30, **params):
        with self.lock:
            self.id += 1
            i = self.id
        self._send(json.dumps({"id": i, "method": method, "params": params}).encode())
        with self.lock:
            ende = time.time() + timeout
            while i not in self.antworten:
                if not self.offen:
                    raise IOError("Edge-Verbindung getrennt")
                rest = ende - time.time()
                if rest <= 0:
                    raise TimeoutError(method)
                self.lock.wait(rest)
            m = self.antworten.pop(i)
        if "error" in m:
            raise RuntimeError(f"{method}: {m['error']}")
        return m.get("result", {})

    def schliessen(self):
        try:
            self.s.close()
        except Exception:
            pass


class Tab:
    def __init__(self, info):
        self.info = info
        self.ws = WS(info["webSocketDebuggerUrl"])
        benutzt()
        try: self.ws.cdp("Page.enable", timeout=3)                # Dialog-Ereignisse (Typ) mitlesen
        except Exception: pass
        self.wecken()

    def wecken(self):
        """Hintergrund-Tab aufwecken: Edge friert inaktive Tabs ein (Schlafmodus) – dann laeuft dort kein Skript."""
        for m, kw in (("Page.setWebLifecycleState", {"state": "active"}),
                      ("Emulation.setFocusEmulationEnabled", {"enabled": True})):
            try: self.ws.cdp(m, timeout=3, **kw)
            except Exception: pass

    def dialog_typ(self):
        with self.ws.lock:
            for e in reversed(self.ws.events):
                if e.get("method") == "Page.javascriptDialogClosed": return None
                if e.get("method") == "Page.javascriptDialogOpening": return (e.get("params") or {}).get("type", "")
        return None

    def dialog_schliessen(self):
        """Offener Browser-Dialog blockiert jedes Skript im Tab. v212: nur «alert» (reiner Hinweis) bestaetigen;
        confirm/prompt/beforeunload/unbekannt werden ABGELEHNT – AURA bestaetigt nie eine Aktion."""
        typ = self.dialog_typ()
        try:
            self.ws.cdp("Page.handleJavaScriptDialog", timeout=3, accept=(typ == "alert"))
            return True
        except Exception:
            return False

    def origin_pruefen(self, quelle=None):
        """Vor dem Auslesen: aktuelle Seite muss zu einem freigegebenen Origin gehoeren (auch nach Redirects)."""
        from .herkunft import pruefe
        r = self.ws.cdp("Runtime.evaluate", timeout=5, expression="location.href", returnByValue=True)
        return pruefe(r.get("result", {}).get("value", ""), quelle)

    def navigieren(self, url, quelle=None):
        from .herkunft import pruefe
        pruefe(url, quelle); benutzt()
        return self.ws.cdp("Page.navigate", url=url)

    def zustand(self):
        try:
            r = self.ws.cdp("Runtime.evaluate", timeout=5, expression="location.href + ' | ' + document.title", returnByValue=True)
            return r.get("result", {}).get("value", "")
        except Exception as e:
            return f"keine Antwort ({type(e).__name__})"

    def js(self, ausdruck, timeout=30):
        benutzt()
        try:
            r = self.ws.cdp("Runtime.evaluate", timeout=timeout, expression=ausdruck,
                            returnByValue=True, awaitPromise=True)
        except TimeoutError:
            dialog = self.dialog_schliessen()
            self.wecken()                                       # eingefroren? aufwecken und einmal wiederholen
            if not dialog:
                try:
                    r = self.ws.cdp("Runtime.evaluate", timeout=min(timeout, 15), expression=ausdruck,
                                    returnByValue=True, awaitPromise=True)
                except TimeoutError:
                    raise TimeoutError(f"Seite antwortet nicht ({self.info.get('url', '')[:60]})")
                if "exceptionDetails" in r:
                    raise RuntimeError("JS-Fehler: " + json.dumps(r["exceptionDetails"])[:300])
                return r.get("result", {}).get("value")
            r = self.ws.cdp("Runtime.evaluate", timeout=timeout, expression=ausdruck,
                            returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            raise RuntimeError("JS-Fehler: " + json.dumps(r["exceptionDetails"])[:300])
        return r.get("result", {}).get("value")

    def schliessen(self):
        self.ws.schliessen()


def tabs():
    return [t for t in http("/json") if t.get("type") == "page"]


def tab_finden(quelle):
    """Tab einer Live-Quelle (exakter Origin-Vergleich, v212); bei mehreren der sichtbare/fokussierte."""
    from .herkunft import ist_erlaubt
    kandidaten = [t for t in tabs() if ist_erlaubt(t.get("url", ""), quelle)]
    if not kandidaten:
        return None
    if len(kandidaten) == 1:
        return Tab(kandidaten[0])
    for t in kandidaten:
        tab = Tab(t)
        try:
            if tab.js("document.visibilityState === 'visible' && document.hasFocus()", timeout=5):
                return tab
        except Exception:
            pass
        tab.schliessen()
    return Tab(kandidaten[0])


def tab_neu(url):
    """Neuer Tab im Hintergrund (holt das Fenster nicht nach vorne). v212: nur about:blank oder freigegebene Origins."""
    if url != "about:blank":
        from .herkunft import pruefe
        pruefe(url)
    benutzt()
    offen = tabs()
    if offen:
        t = Tab(offen[0])
        try:
            tid = t.ws.cdp("Target.createTarget", url=url, background=True)["targetId"]
        finally:
            t.schliessen()
        for _ in range(20):
            for info in tabs():
                if info.get("id") == tid:
                    return Tab(info)
            time.sleep(0.2)
    return Tab(http("/json/new?" + quote(url, safe=":/?&=%#"), method="PUT"))


def fenster(tab, zustand="minimized"):
    """Edge-Fenster minimieren ('minimized') oder zeigen ('normal'). Fehler werden ignoriert."""
    try:
        wid = tab.ws.cdp("Browser.getWindowForTarget", targetId=tab.info["id"])["windowId"]
        tab.ws.cdp("Browser.setWindowBounds", windowId=wid, bounds={"windowState": zustand})
        return True
    except Exception:
        return False


def verstecken():
    """Fenster mit beliebigem Tab minimieren (z. B. nach der Anmeldung)."""
    offen = tabs()
    if offen:
        t = Tab(offen[0])
        try:
            fenster(t, "minimized")
        finally:
            t.schliessen()


def tab_zu(tab):
    try:
        http("/json/close/" + tab.info["id"])
    except Exception:
        pass
    tab.schliessen()


def _melden(text):
    try:
        from .. import log
        log.get().warning("Edge: " + text)
    except Exception: pass


def beenden(warten=10.0):
    """AURA-Edge schliessen (beim Beenden von AURA / nach Leerlauf). v212: Ende wird geprueft; bleibt der eigene Prozess
    haengen, wird er beendet; gelingt auch das nicht, wird es gemeldet (Rueckgabe False). Ein Logout am Server ist das
    NICHT – die SSO-Sitzung kann im Profil erhalten bleiben."""
    try:
        if laeuft():
            ws = WS(http("/json/version")["webSocketDebuggerUrl"])
            try: ws.cdp("Browser.close", timeout=5)
            except Exception: pass
            ws.schliessen()
    except Exception as e:
        _melden(f"Schliessen fehlgeschlagen ({type(e).__name__})")
    ende = time.time() + warten
    while laeuft() and time.time() < ende: time.sleep(0.5)
    p = _proc["p"]
    if laeuft() and p is not None and p.poll() is None:
        try: p.terminate(); p.wait(5)
        except Exception: pass
    if laeuft():
        _melden("AURA-Edge läuft nach dem Beenden noch – bitte Edge-Fenster von AURA manuell schliessen")
        return False
    for f in (PORTDATEI, AKTIV):
        try: f.unlink()
        except OSError: pass
    cache_leeren()
    return True


CACHE_ORDNER = ("Cache", "Code Cache", "GPUCache", "DawnGraphiteCache", "DawnWebGPUCache",
                os.path.join("Service Worker", "CacheStorage"), os.path.join("Service Worker", "ScriptCache"),
                "Session Storage", "Sessions")                     # v212: auch Sitzungs-/Tab-Wiederherstellung
VERLAUF_DATEIEN = ("History", "History-journal", "Visited Links", "Top Sites", "Top Sites-journal",
                   "Shortcuts", "Shortcuts-journal")               # v212: Verlauf der AURA-Edge (nicht dein normales Edge)
# BLEIBT bewusst (fuer SSO/Anmeldung noetig): Cookies, Local Storage, IndexedDB, Einstellungen. Siehe README «Sicherheit».


def cache_leeren(warten=8.0):
    """Zwischengespeicherte Seiten (Acta Nova, SharePoint, Intranet) nach dem Beenden loeschen.
    Anmeldedaten/Einstellungen des Profils bleiben. Laeuft Edge noch, wird nichts geloescht."""
    import shutil
    ende = time.time() + warten
    while laeuft() and time.time() < ende:
        time.sleep(0.5)
    if laeuft():
        return 0
    frei = 0
    for prof in [PROFIL] + [p for p in PROFIL.glob("*") if p.is_dir() and (p.name == "Default" or p.name.startswith("Profile"))]:
        for name in CACHE_ORDNER:
            d = prof / name
            if d.is_dir():
                frei += sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                shutil.rmtree(d, ignore_errors=True)
        for name in VERLAUF_DATEIEN:
            f = prof / name
            if f.is_file():
                try: frei += f.stat().st_size; f.unlink()
                except OSError: pass
    return frei
