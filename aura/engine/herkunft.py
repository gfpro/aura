"""Zentrale Origin-Allowlist fuer alle Live-Quellen (Acta Nova, Intranet, SharePoint, Confluence). Version 20261108v212
Vergleich als Tupel (scheme, host, port) – nie per startswith()/Teilstring. Nur https, keine Zugangsdaten in der URL,
keine IP-Literale (ausser ausdruecklich freigegeben), keine ungewoehnlichen Host-Schreibweisen.
Freigabe administrativ per Gruppenrichtlinie: HKLM\\SOFTWARE\\Policies\\AURA, Wert «LiveOrigins_<quelle>»
(z.B. LiveOrigins_intranet = "https://intranet.ar.admin.ch"; mehrere durch Komma/Leerzeichen/Zeilen). Fehlt der Wert,
gelten die Standards unten. Benutzer-Einstellungen (URLs unter «Wissen») muessen INNERHALB dieser Liste liegen.
"""
import re
from urllib.parse import urlsplit

STANDARD = {
    "actanova": ("https://www.vbs.gever.admin.ch",),
    "intranet": ("https://intranet.ar.admin.ch",),
    "sharepoint": ("https://portal.collab.admin.ch",),
    "confluence": ("https://confluence.bit.admin.ch",),
}
_HOST = re.compile(r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")
_IP = re.compile(r"^[0-9.]+$|^\[.*\]$|:")


class HerkunftFehler(ValueError):
    pass


def origin(url, ip_erlaubt=False):
    """-> (scheme, host, port). HerkunftFehler bei allem Unueblichen."""
    if not isinstance(url, str) or not url.strip() or any(c.isspace() or ord(c) < 32 or c == "\\" for c in url.strip()):
        raise HerkunftFehler("Keine gültige Adresse")
    try:
        u = urlsplit(url.strip()); port = u.port
    except ValueError:
        raise HerkunftFehler("Keine gültige Adresse")
    if u.scheme.lower() != "https":
        raise HerkunftFehler("Nur https-Adressen sind erlaubt")
    if "@" in u.netloc:
        raise HerkunftFehler("Adresse mit Zugangsdaten wird nicht akzeptiert")
    host = (u.hostname or "").lower()
    netloc_host = u.netloc.lower().rsplit(":", 1)[0] if port is not None else u.netloc.lower()
    if host != netloc_host or (not _HOST.match(host) and not (ip_erlaubt and host)) or (not ip_erlaubt and (_IP.search(host) or host.replace(".", "").isdigit())):
        raise HerkunftFehler("Ungewöhnliche Host-Schreibweise wird nicht akzeptiert")
    return ("https", host, port or 443)


def _policy(quelle):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\AURA") as k:
            v, _ = winreg.QueryValueEx(k, f"LiveOrigins_{quelle}")
        v = " ".join(v) if isinstance(v, (list, tuple)) else str(v)
        return tuple(x for x in v.replace(",", " ").split() if x)
    except Exception:
        return ()


def erlaubt(quelle):
    """Freigegebene Origins einer Quelle als Menge von Tupeln (Richtlinie, sonst Standard)."""
    out = set()
    for u in (_policy(quelle) or STANDARD.get(quelle, ())):
        try: out.add(origin(u, ip_erlaubt=True))
        except HerkunftFehler: pass
    return out


def alle_erlaubt():
    out = set()
    for q in STANDARD: out |= erlaubt(q)
    return out


# v216: Intranets der Bundesverwaltung frei waehlbar (Feld unter «Wissen»), aber nur unter dieser Domain.
# Gilt nur ohne Gruppenrichtlinie LiveOrigins_intranet – ist sie gesetzt, gilt allein sie.
DOMAIN = {"intranet": "admin.ch"}


def _domain_ok(o, quelle):
    d = DOMAIN.get(quelle)
    return bool(d) and not _policy(quelle) and o[2] == 443 and o[1].endswith("." + d) and not _IP.search(o[1])


def ist_erlaubt(url, quelle=None):
    """True nur, wenn die URL exakt zu einem freigegebenen Origin gehoert (quelle=None: irgendeine Live-Quelle).
    Intranet: zusaetzlich jeder https-Host unter *.admin.ch (Port 443)."""
    menge = alle_erlaubt() if quelle is None else erlaubt(quelle)
    try: o = origin(url)
    except HerkunftFehler:
        try: return origin(url, ip_erlaubt=True) in menge
        except HerkunftFehler: return False
    return o in menge or any(_domain_ok(o, q) for q in ([quelle] if quelle else DOMAIN))


def pruefe(url, quelle=None):
    """URL zurueckgeben oder HerkunftFehler mit verstaendlicher Meldung."""
    if not ist_erlaubt(url, quelle):
        o = sorted(f"https://{h}" + ("" if p == 443 else f":{p}") for _, h, p in (alle_erlaubt() if quelle is None else erlaubt(quelle)))
        raise HerkunftFehler(f"Adresse ist nicht freigegeben ({str(url)[:80]}). Erlaubt: {', '.join(o) or 'keine'}")
    return url
