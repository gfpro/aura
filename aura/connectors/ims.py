# aura/connectors/ims.py — v246: + Prozessschritte/Rollen (processsteps.svc/processroles.svc); v245: Blättern robust, Host-Freigabe; v240: IMS ar (Prozessmodell armasuisse) per REST-API, nur lesen, nur Standardbibliothek.
# Anmeldung: Windows-Konto per NTLM über SSPI (secur32) – kein Passwort, kein Token, kein Edge.
# Ablauf: alle Dokumente unter dem Wurzelprozess (Header Item-Count/Page wie die IMS-Oberfläche), Acta-Nova-Vorlagen
#         und externe Links überspringen, je Dokument das PDF holen und mit folder_docs.read_text lesen (Grenzen aus sicherheit.py).
# ext_id = "<dokId>|v<Version>|<Ausgabedatum>|<FORMAT>" -> neue Fassung = neues Objekt; ctx.seen -> Worker entfernt alte Fassungen.
# Sicherheit: fester Host, nur https, keine Weiterleitungen (http.client folgt keinen), Antwortgrössen begrenzt.
# Einstellungen (optional): ims_prozess ("1"), ims_sprache ("de"), ims_auto (true = einmal pro Tag), ims_nur_pdf (true),
#   ims_typen (Liste Dokumenttyp-Kürzel, Standard STANDARD_TYPEN; ["*"] = alle). Filter auf den Metadaten -> nur passende PDFs werden geladen.
import base64, http.client, json, os, ssl, tempfile, time
from pathlib import Path
from .base import Connector
from ..text import clean
from .. import sicherheit as SI

HOST = "intranet.ims-ar.vbs.admin.ch"
CLIENT = "https://intranet.ims-ar-client.vbs.admin.ch"
API_DOK = "/imsar.pms.documents.svc/"
API_PROZ = "/imsar.pms.processes.svc/"
API_PDF = "/imsar.pms.filer.svc/documents/"
MAX_JSON = 64 * 2**20
SEITE = 500                       # Einträge je Abfrage (Header Item-Count)
TIMEOUT = 90
MAX_SEITEN = 100                  # v245: Schutz gegen Endlosschleife (max. 50'000 Einträge)
OHNE_SCHRITTE = "|ohne_schritte"   # v252 (F12): Kennung für Dokumente, deren Prozessschritte noch nicht abrufbar waren
STANDARD_TYPEN = ("RL", "RL-A", "PA", "PA-A", "AA", "AA-A", "CL", "CL-A", "VA", "VA-A", "EL", "EL-A",
                  "VS", "VS-A", "TV", "TV-A", "GP", "GP-A")   # v240d: ohne FO/FO-A/VO (Formulare/Vorlagen), LI wird ohnehin übersprungen


# ---------- NTLM über SSPI (nur Windows) ----------
def _sspi():
    import ctypes
    from ctypes import wintypes

    class SecHandle(ctypes.Structure):
        _fields_ = [("lower", ctypes.c_void_p), ("upper", ctypes.c_void_p)]

    class SecBuffer(ctypes.Structure):
        _fields_ = [("cbBuffer", wintypes.ULONG), ("BufferType", wintypes.ULONG), ("pvBuffer", ctypes.c_void_p)]

    class SecBufferDesc(ctypes.Structure):
        _fields_ = [("ulVersion", wintypes.ULONG), ("cBuffers", wintypes.ULONG), ("pBuffers", ctypes.POINTER(SecBuffer))]

    return ctypes, wintypes, SecHandle, SecBuffer, SecBufferDesc, ctypes.WinDLL("secur32")


class _NTLM:
    OK, WEITER = 0, 0x00090312

    def __init__(self):
        self.c, self.wt, self.H, self.B, self.D, self.s = _sspi()
        self.cred, self.ctx, self.hat_ctx = self.H(), self.H(), False
        r = self.s.AcquireCredentialsHandleW(None, "NTLM", 2, None, None, None, None,
                                             self.c.byref(self.cred), self.c.byref(self.c.c_longlong()))
        if r != self.OK: raise RuntimeError(f"Windows-Anmeldung nicht möglich (0x{r & 0xffffffff:08x})")

    def schritt(self, eingang=None):
        c = self.c
        puf = c.create_string_buffer(12288)
        aus = self.B(len(puf), 2, c.cast(puf, c.c_void_p))
        aus_d = self.D(0, 1, c.pointer(aus))
        ein_d = None
        if eingang:
            roh = c.create_string_buffer(eingang, len(eingang))
            ein_d = c.pointer(self.D(0, 1, c.pointer(self.B(len(eingang), 2, c.cast(roh, c.c_void_p)))))
        r = self.s.InitializeSecurityContextW(c.byref(self.cred), c.byref(self.ctx) if self.hat_ctx else None,
                                              "HTTP/" + HOST, 0, 0, 0x10, ein_d, 0, c.byref(self.ctx),
                                              c.byref(aus_d), c.byref(self.wt.ULONG()), c.byref(c.c_longlong()))
        if r not in (self.OK, self.WEITER): raise RuntimeError(f"Windows-Anmeldung abgelehnt (0x{r & 0xffffffff:08x})")
        self.hat_ctx = True
        return base64.b64encode(puf.raw[:aus.cbBuffer]).decode()

    def schliessen(self):
        if self.hat_ctx: self.s.DeleteSecurityContext(self.c.byref(self.ctx))
        self.s.FreeCredentialsHandle(self.c.byref(self.cred))


class _Client:
    """Eine https-Verbindung zum festen IMS-Host; NTLM-Handshake bei 401 auf derselben Verbindung."""

    def __init__(self, sprache="de"):
        self.sprache, self.conn = sprache, None

    def _neu(self):
        self.schliessen()
        from ..engine.herkunft import ist_erlaubt                         # v245: Host über zentrale Freigabe (GPO LiveOrigins_ims)
        if not ist_erlaubt(f"https://{HOST}/", "ims"): raise RuntimeError(f"IMS-Host {HOST} ist nicht freigegeben")
        self.conn = http.client.HTTPSConnection(HOST, context=ssl.create_default_context(), timeout=TIMEOUT)

    def schliessen(self):
        if self.conn:
            try: self.conn.close()
            except Exception: pass
        self.conn = None

    def _anfrage(self, pfad, kopf):
        self.conn.request("GET", pfad, headers=kopf)
        return self.conn.getresponse()

    def get(self, pfad, extra=None, max_bytes=MAX_JSON):
        kopf = {"Accept": "application/json, application/pdf", "Connection": "keep-alive",
                "Language-Code": self.sprache, **(extra or {})}
        for versuch in range(2):
            try:
                if self.conn is None: self._neu()
                r = self._anfrage(pfad, kopf)
                if r.status == 401:
                    r.read(); auth = _NTLM()
                    try:
                        r = self._anfrage(pfad, dict(kopf, Authorization="NTLM " + auth.schritt()))
                        ch = next((t.strip()[5:] for t in (r.getheader("WWW-Authenticate") or "").split(",")
                                   if t.strip().startswith("NTLM ")), None); r.read()
                        if r.status != 401 or not ch: raise RuntimeError(f"Anmeldung: HTTP {r.status}")
                        r = self._anfrage(pfad, dict(kopf, Authorization="NTLM " + auth.schritt(base64.b64decode(ch))))
                    finally: auth.schliessen()
                daten = r.read(max_bytes + 1)
                if r.status != 200: raise RuntimeError(f"HTTP {r.status}")     # auch 3xx: keine Weiterleitung
                if len(daten) > max_bytes: raise RuntimeError("Antwort zu gross")
                return r.getheader("Content-Type", ""), daten
            except (http.client.HTTPException, ConnectionError, OSError) as e:
                self.conn = None
                if versuch: raise RuntimeError(f"Verbindung fehlgeschlagen: {type(e).__name__}") from None

    def json(self, pfad, extra=None):
        typ, d = self.get(pfad, extra)
        if "json" not in typ: raise RuntimeError("keine JSON-Antwort")
        return json.loads(d)

    def liste(self, pfad, feld):
        """Alle Seiten über die Header Item-Count/Page (wie die IMS-Oberfläche).
        v245: Fehlt totalCount, wird weitergeblättert (früher: Abbruch nach Seite 1 -> unvollständig, aber als vollständig
        gemeldet -> Aufräumen hätte Dokumente gelöscht). Ignoriert der Server «Page» (gleiche Seite zweimal) oder wird
        MAX_SEITEN überschritten -> Fehler statt stiller Teilliste."""
        alle, seite, erste = [], 0, set()
        while True:
            j = self.json(pfad, {"Item-Count": str(SEITE), "Page": str(seite)})
            e = j.get(feld) or []
            kennung = json.dumps(e[:1], sort_keys=True, default=str)
            if e and kennung in erste: raise RuntimeError("IMS: Blättern wird nicht unterstützt (gleiche Seite erneut)")
            erste.add(kennung); alle += e
            try: total = int(j.get("totalCount"))
            except (TypeError, ValueError): total = None
            if not e or len(e) < SEITE or (total is not None and len(alle) >= total): return alle
            seite += 1
            if seite >= MAX_SEITEN: raise RuntimeError(f"IMS: mehr als {MAX_SEITEN * SEITE} Einträge – abgebrochen")


def _pfade(prozesse):
    """Prozess-ID -> «Oberprozess › … › Prozess»."""
    namen = {p["id"]: p.get("name", "") for p in prozesse}
    eltern = {p["id"]: p.get("parentId") for p in prozesse}
    out = {}
    for pid in namen:
        teile, k, n = [], pid, 0
        while k in namen and n < 20: teile.append(namen[k]); k = eltern.get(k); n += 1
        out[pid] = " › ".join(reversed([t for t in teile if t]))
    return out


API_SCHRITTE = "/imsar.pms.processsteps.svc/documents/"
API_ROLLEN = "/imsar.pms.processroles.svc/documents/"
FORMAT = "s1"                      # v246: Textformat; Änderung erzwingt einmaliges Neueinlesen


def _txt(v):
    """Feldwert aus IMS als kurzer Text (str, Liste von str/dicts oder dict)."""
    if v is None: return ""
    if isinstance(v, str): return " ".join(v.split())
    if isinstance(v, dict): return _txt(v.get("title") or v.get("name") or v.get("text") or "")
    if isinstance(v, (list, tuple)): return "; ".join(x for x in (_txt(e) for e in v) if x)
    return str(v)


def _schritte_text(cl, did):
    """v246: Prozessschritte und Rollen strukturiert (statt der Zeichnung im PDF).
    v252 (F12): -> (Text, ok). ok=False, wenn eine Abfrage scheiterte (Netz, Zeitüberschreitung, Serverfehler) – das Dokument
    wird dann beim nächsten Abgleich erneut versucht. «HTTP 404/204» heisst: dieses Dokument hat keine Schritte (ok)."""
    zeilen, ok = [], True
    def _fehler(e):
        return not any(c in str(e) for c in ("HTTP 404", "HTTP 204"))
    try:
        st = (cl.json(f"{API_SCHRITTE}{int(did)}", {"Item-Count": "9999", "Page": "0"}).get("processSteps") or [])
        def _nr(s):                                                   # v252: gemischte Typen (Zahl/Text) nicht mehr als Fehler
            try: return float(s.get("number") or 0)
            except (TypeError, ValueError): return 0.0
        for s in sorted(st, key=_nr):
            art = " (Entscheid)" if "decision" in str(s.get("shapeType") or "").lower() else ""
            teile = [f"Schritt {s.get('number', '?')}{art}: {_txt(s.get('processSequence'))}"]
            for lab, feld in (("Beschreibung", "description"), ("Vorgaben", "prerequisites"), ("Ergebnis", "result"),
                              ("Referenzen", "referenceText"), ("Referenzen", "references")):
                w = _txt(s.get(feld))
                if w and not any(w in x for x in teile): teile.append(f"{lab}: {w}")
            for k, lab in (("R", "Durchführung (R)"), ("A", "Verantwortung (A)"), ("C", "Mitwirkung (C)"), ("I", "Information (I)")):
                w = _txt(s.get("text" + k)) or _txt(s.get("roles" + k))
                if w: teile.append(f"{lab}: {w}")
            zeilen.append(" · ".join(teile))
    except Exception as e: ok = ok and not _fehler(e)
    try:
        ro = (cl.json(f"{API_ROLLEN}{int(did)}", {"Item-Count": "9999", "Page": "0"}).get("processRoles") or [])
        r = [f"{_txt(x.get('id'))} = {_txt(x.get('name'))}" + (f" ({_txt(x.get('processGroup'))})" if x.get("processGroup") else "")
             for x in ro if x.get("name")]
        if r: zeilen.append("Rollen: " + "; ".join(r))
    except Exception as e: ok = ok and not _fehler(e)
    return (("Prozessschritte:\n" + "\n".join(zeilen)) if zeilen else ""), ok


def _pdf_text(daten):
    from .folder_docs import read_text
    fd, name = tempfile.mkstemp(suffix=".pdf", prefix="aura_ims_")
    try:
        with os.fdopen(fd, "wb") as f: f.write(daten)
        return read_text(Path(name))
    finally:
        try: os.remove(name)
        except OSError: pass


class Ims(Connector):
    id, label = "ims", "IMS (Prozesse)"
    hint = "Prozessdokumente (PDF) aus dem IMS ar. Anmeldung mit dem Windows-Konto, Vorlagen aus Acta Nova werden übersprungen."

    def available(self):
        if os.name != "nt": return False, "nur unter Windows (Windows-Anmeldung)"
        return True, ""

    def sync(self, ctx):
        s = ctx.settings
        cl = _Client(str(s.get("ims_sprache") or "de")[:2])
        seen, errors, offen = set(), False, 0
        def behalten(did):                                            # v252 (F5): bisherige Fassungen dieses Dokuments nicht aufräumen
            seen.update(x for x in ctx.known if x.startswith(f"{did}|"))
        try:
            try:
                ctx.progress("IMS: Prozesse laden")
                pfade = _pfade(cl.liste(API_PROZ, "processes"))
                proz = str(s.get("ims_prozess") or "1").strip()
                if not proz.isdigit(): raise RuntimeError(f"Einstellung ims_prozess muss eine Zahl sein, nicht «{proz[:20]}»")
                docs = cl.liste(f"{API_DOK}processes/{proz}", "documents")
            except Exception as e:
                ctx.progress(f"IMS: {e}"); ctx.seen = seen; ctx.complete = False; return
            nur_pdf = s.get("ims_nur_pdf", True)
            typen = {str(x).strip().upper() for x in (s.get("ims_typen") or STANDARD_TYPEN) if str(x).strip()}
            if typen and "*" not in typen: docs = [d for d in docs if str((d.get("type") or {}).get("shortName") or "").upper() in typen]
            neueste = {}                                                      # je Dokument-ID nur die neueste Fassung
            for d in docs:
                a = neueste.get(d.get("id"))
                if a is None or str(d.get("publishDate") or "") > str(a.get("publishDate") or ""): neueste[d.get("id")] = d
            docs = list(neueste.values())
            ctx.progress(f"IMS: {len(docs)} Dokumente nach Filter")
            for k, d in enumerate(docs):
                if ctx.cancelled(): return                                    # unvollständig -> kein Aufräumen
                if d.get("isActaNova") or d.get("actaNovaLink") or d.get("externalLink"): continue
                if nur_pdf and not str(d.get("publishedFilename") or "").lower().endswith(".pdf"): continue
                did = d.get("id")
                if did is None: continue
                ext = f"{did}|v{d.get('version', '')}|{str(d.get('publishDate') or '')[:10]}|{FORMAT}"; seen.add(ext)
                if ext in ctx.known: continue
                ohne = ext + OHNE_SCHRITTE                                    # v252 (F12): gespeichert, aber Schritte fehlen noch
                ctx.progress(f"IMS: {k}/{len(docs)}", k, len(docs))
                try:
                    schritte, s_ok = _schritte_text(cl, did)                 # v246
                    if not s_ok and ohne in ctx.known:                       # weiterhin nicht abrufbar -> Bestand behalten, später erneut
                        seen.add(ohne); offen += 1; continue
                    typ, daten = cl.get(f"{API_PDF}{int(did)}", max_bytes=SI.DOC_MAX_BYTES)
                    if "pdf" not in typ or daten[:4] != b"%PDF": raise RuntimeError("kein PDF")
                    text = clean(_pdf_text(daten))
                    if schritte: text = (schritte + "\n\n" + text).strip()
                except Exception as e:
                    offen += 1; behalten(did); ctx.progress(f"IMS {did} übersprungen: {e}"); continue
                if not text.strip(): continue
                if not s_ok: seen.add(ohne); ext = ohne; offen += 1           # ohne Schritte speichern, beim nächsten Abgleich ergänzen
                pid = str(d.get("processId") or "")
                pfad = pfade.get(pid, "")
                titel = d.get("title") or str(did)
                o = d.get("owner") or {}
                t = d.get("type") or {}
                yield {"ext_id": ext, "title": titel, "author": f"{o.get('firstname', '')} {o.get('lastname', '')}".strip(),
                       "ts": str(d.get("publishDate") or "")[:16].replace("T", " "), "body": text, "text": text,
                       "prefix": f"IMS {did} {titel}" + (f" ({pfad})" if pfad else "") + ": ",
                       "location": pfad,
                       "meta": {"url": f"{CLIENT}/processes/{pid}/documents" if pid else CLIENT, "dok_id": did,
                                "version": d.get("version", ""), "typ": t.get("typeDefinition") or t.get("shortName", ""),
                                "prozess_id": pid, "pfad": pfad, "dateityp": "pdf"}}
        finally:
            cl.schliessen()
        if offen: ctx.progress(f"IMS: {offen} Dokument(e) unvollständig – wird beim nächsten Abgleich erneut versucht")
        ctx.seen = seen; ctx.complete = not errors and bool(seen)       # v252 (F5): Einzelfehler blockieren das Aufräumen nicht mehr
