# quellen_test.py – Diagnose: OneNote (COM) und Webseite mit Windows-Anmeldung (WinHttp)
# Aufruf:  py tools\quellen_test.py [URL]
# Ausgabe: tools\quellen_test.txt  (Titel/Namen vor dem Teilen schwärzen)
# Liest nur, schreibt nichts in AURA.
import os, sys, re, time, html, traceback
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor"))
OUT = os.path.join(ROOT, "tools", "quellen_test.txt")
NS = "{http://schemas.microsoft.com/office/onenote/2013/onenote}"
zeilen = []

def log(s=""):
    print(s); zeilen.append(str(s))

def host(u):
    m = re.match(r"^https?://([^/]+)", u or "")
    return m.group(1) if m else "?"

def klartext(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

# ---------- 1. OneNote ----------
TLB = "{0EA692EE-BB50-4E3C-AEF0-356D91732725}"
TLB_PFADE = []
def onenote_registry():
    import winreg
    for hive, hn in ((winreg.HKEY_CLASSES_ROOT, "HKCR"), (winreg.HKEY_CURRENT_USER, "HKCU\\Software\\Classes")):
        base = ("TypeLib\\" if hn == "HKCR" else "Software\\Classes\\TypeLib\\") + TLB
        try:
            k = winreg.OpenKey(hive, base)
        except OSError:
            log(f"{hn}: Typbibliothek nicht eingetragen"); continue
        i = 0
        while True:
            try:
                ver = winreg.EnumKey(k, i); i += 1
            except OSError:
                break
            for arch in ("win64", "win32"):
                try:
                    p = winreg.QueryValue(hive, base + "\\" + ver + "\\0\\" + arch)
                    datei = re.sub(r"\\\d+$", "", p or "")
                    TLB_PFADE.append(p)
                    log(f"  Ressourcen-Nummer: {p[len(datei):] or 'keine'}")
                    log(f"{hn} Version {ver} {arch}: Datei vorhanden={os.path.exists(datei)} · {os.path.basename(datei)}")
                except OSError:
                    pass

def test_onenote():
    log("== 1. OneNote (COM) ==")
    try:
        import comtypes.client as cc
    except Exception as e:
        log(f"FEHLER comtypes: {e}"); return
    on = None
    # Typbibliothek direkt aus ONENOTE.EXE laden (Registrierung ist oft fehlerhaft)
    exe = None
    for pf in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
        for sub in (r"Microsoft Office\root\Office16", r"Microsoft Office\Office16"):
            p = os.path.join(pf, sub, "ONENOTE.EXE")
            if os.path.exists(p):
                exe = p; break
        if exe: break
    log(f"ONENOTE.EXE gefunden: {bool(exe)}")
    onenote_registry()
    for p in TLB_PFADE:
        try:
            from comtypes.typeinfo import LoadTypeLibEx
            tlib = LoadTypeLibEx(p)          # versteht «ONENOTE.EXE\3»
            log("Typbibliothek geladen")
            mod = cc.GetModule(tlib)
            on = cc.CreateObject("OneNote.Application", interface=mod.IApplication)
            log("verbunden (Typbibliothek mit Ressourcen-Nummer)"); break
        except Exception as e:
            log(f"Typbibliothek {os.path.basename(p)}: {type(e).__name__} {e!r}")
            log("".join(traceback.format_exc().splitlines(True)[-6:]))
    if on is None:
        log("=> Keine COM-Schnittstelle (Store-App oder OneNote nicht installiert)."); return
    xml = None
    for args in (("", 4), ("", 4, None, 0)):
        try:
            r = on.GetHierarchy(*args)
            xml = r if isinstance(r, str) else (r[0] if isinstance(r, (list, tuple)) else None)
            if xml: break
        except Exception as e:
            log(f"GetHierarchy{args[:2]}: {e}")
    if not xml:
        log("=> GetHierarchy lieferte nichts."); return
    t = time.time()
    root = ET.fromstring(xml)
    nbs = root.findall(f".//{NS}Notebook")
    secs = root.findall(f".//{NS}Section")
    pages = root.findall(f".//{NS}Page")
    log(f"Notizbücher {len(nbs)} · Abschnitte {len(secs)} · Seiten {len(pages)} ({time.time()-t:.1f} s)")
    for nb in nbs[:10]:
        log(f"  Notizbuch: path={nb.get('path','?')[:3]}… isUnread={nb.get('isUnread')}")
    if not pages:
        return
    gesamt, t, n = 0, time.time(), min(5, len(pages))
    for p in pages[:n]:
        try:
            r = on.GetPageContent(p.get("ID"))
            pxml = r if isinstance(r, str) else r[0]
            pr = ET.fromstring(pxml)
            txt = klartext(" ".join((e.text or "") for e in pr.iter(f"{NS}T")))
            gesamt += len(txt)
            log(f"  Seite geändert {p.get('lastModifiedTime')}: {len(txt)} Zeichen Text")
        except Exception as e:
            log(f"  GetPageContent: {e}")
    log(f"=> {n} Seiten gelesen in {time.time()-t:.1f} s, {gesamt} Zeichen")
    try:
        on.GetHyperlinkToObject(pages[0].get("ID"), "")
        log("Link zur Seite: ok (Öffnen aus AURA möglich)")
    except Exception as e:
        log(f"Link zur Seite: {e}")

# ---------- 2. Webseite ----------
PROXY = None
URL = ""
def proxy_aus_pac(pac, url):
    import ctypes
    from ctypes import wintypes as W
    class OPT(ctypes.Structure):
        _fields_ = [("dwFlags", W.DWORD), ("dwAutoDetectFlags", W.DWORD), ("lpszAutoConfigUrl", W.LPCWSTR),
                    ("lpvReserved", W.LPVOID), ("dwReserved", W.DWORD), ("fAutoLogonIfChallenged", W.BOOL)]
    class INFO(ctypes.Structure):
        _fields_ = [("dwAccessType", W.DWORD), ("lpszProxy", W.LPWSTR), ("lpszProxyBypass", W.LPWSTR)]
    w = ctypes.WinDLL("winhttp.dll", use_last_error=True)
    w.WinHttpOpen.restype = W.LPVOID
    w.WinHttpOpen.argtypes = [W.LPCWSTR, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD]
    w.WinHttpGetProxyForUrl.argtypes = [W.LPVOID, W.LPCWSTR, ctypes.POINTER(OPT), ctypes.POINTER(INFO)]
    h = w.WinHttpOpen("AURA", 1, None, None, 0)
    o = OPT(2, 0, pac, None, 0, True)
    i = INFO()
    if not w.WinHttpGetProxyForUrl(h, url, ctypes.byref(o), ctypes.byref(i)):
        log(f"PAC-Auswertung fehlgeschlagen: Fehler {ctypes.get_last_error()}")
        return None
    p = i.lpszProxy
    log(f"PAC: Zugriffsart {i.dwAccessType}, Proxy {'ja' if p else 'nein'}")
    return p.split(";")[0].strip() if p else None

def proxy_info():
    global PROXY
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        def val(n):
            try: return winreg.QueryValueEx(k, n)[0]
            except OSError: return None
        en, srv, pac = val("ProxyEnable"), val("ProxyServer"), val("AutoConfigURL")
        log(f"Proxy aktiv={en} · ProxyServer={'ja' if srv else 'nein'} · PAC-Datei={'ja' if pac else 'nein'}")
        if en and srv:
            PROXY = srv
            log("Test über Proxy aus den Windows-Einstellungen")
        elif pac:
            PROXY = proxy_aus_pac(pac, URL)
            log(f"PAC liefert für diese URL: {PROXY or 'DIRECT (kein Proxy)'}")
    except Exception as e:
        log(f"Proxy-Einstellungen nicht lesbar: {e}")

def test_web(url):
    log(""); log(f"== 2. Webseite mit Windows-Anmeldung ==")
    global URL
    URL = url
    log("URL-Host: " + host(url))
    proxy_info()
    try:
        import comtypes.client as cc
        req = cc.CreateObject("WinHttp.WinHttpRequest.5.1", dynamic=True)
        req.Open("GET", url, False)
        if PROXY:
            req.SetProxy(2, PROXY, "<local>")
        req.SetAutoLogonPolicy(0)          # 0 = Windows-Anmeldung immer mitsenden
        req.SetTimeouts(5000, 10000, 10000, 30000)
        t = time.time(); req.Send()
        log(f"Status {req.Status} {req.StatusText} ({time.time()-t:.1f} s)")
        try:
            log("End-URL-Host: " + host(str(req.Option(1))))
        except Exception:
            pass
        ct = req.GetResponseHeader("Content-Type") if req.Status == 200 else ""
        body = req.ResponseText or ""
        txt = klartext(re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", body))
        log(f"Content-Type {ct} · HTML {len(body)} Zeichen · Text {len(txt)} Zeichen")
        if "login.microsoftonline.com" in body or "login.microsoftonline" in str(getattr(req, 'Option', lambda i: '')(1)):
            log("=> Weiterleitung zur Microsoft-Anmeldung: Cloud (Entra ID), Windows-Anmeldung reicht nicht.")
        elif req.Status == 200 and len(txt) < 500:
            log("=> Kaum Text: Seite wird per JavaScript aufgebaut (z.B. SharePoint).")
        elif req.Status == 200:
            log("=> Text lesbar.")
    except Exception as e:
        log(f"FEHLER: {e}")

def test_edge(url):
    import subprocess, tempfile
    log(""); log("== 3. Edge im Hintergrund (eigenes Profil, Windows-Anmeldung) ==")
    edge = None
    for pf in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
        p = os.path.join(pf, r"Microsoft\Edge\Application\msedge.exe")
        if os.path.exists(p):
            edge = p; break
    if not edge:
        log("msedge.exe nicht gefunden"); return
    prof = os.path.join(tempfile.gettempdir(), "aura_edge_test")
    t = time.time()
    try:
        r = subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-first-run",
                            "--user-data-dir=" + prof, "--virtual-time-budget=15000",
                            "--dump-dom", url], capture_output=True, timeout=90)
        dom = r.stdout.decode("utf-8", "replace")
    except Exception as e:
        log(f"FEHLER: {e}"); return
    txt = klartext(re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", dom))
    log(f"Rückgabe {r.returncode} · {time.time()-t:.1f} s · HTML {len(dom)} · Text {len(txt)} Zeichen")
    if "eiam" in dom.lower() and len(txt) < 1500:
        log("=> Bleibt bei der eIAM-Anmeldung hängen.")
    elif len(txt) >= 1500:
        log("=> Inhalt lesbar (Anmeldung automatisch).")
    else:
        log("=> Wenig Text – unklar, Ausgabe prüfen.")

if __name__ == "__main__":
    try:
        test_onenote()
    except Exception:
        log(traceback.format_exc())
    if len(sys.argv) > 1:
        test_web(sys.argv[1])
        test_edge(sys.argv[1])
    else:
        log(""); log("(keine URL angegeben – Webtest übersprungen)")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(zeilen))
    print(f"\nGespeichert: {OUT}")
