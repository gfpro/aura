# aura/geheim.py — Geheimnisse (Confluence-Token) mit Windows DPAPI (CurrentUser) schützen. Version 20261108v208
# Nur ctypes/Standardbibliothek. Ohne DPAPI (kein Windows, Fehler) gibt es KEINEN Klartext-Rückfall: Token = nicht verfügbar.
# Datei: data\confluence_token.dpapi. Alte Klartextdatei data\confluence_token.txt wird beim ersten Lesen verschlüsselt
# und erst NACH erfolgreicher Kontrolle (Entschlüsseln == Original) gelöscht. Token erscheint nie in Meldungen/Logs.
import ctypes, os, sys
from pathlib import Path

ENTROPIE = b"AURA-Confluence-Token-v1"

class GeheimFehler(RuntimeError): pass

class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]

def _blob(b):
    buf = ctypes.create_string_buffer(b, len(b))
    return _BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

def _dpapi(daten, schuetzen):
    if sys.platform != "win32": raise GeheimFehler("Windows-DPAPI nicht verfügbar (kein Windows)")
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    ein, _b1 = _blob(daten); ent, _b2 = _blob(ENTROPIE); aus = _BLOB()
    fn = crypt32.CryptProtectData if schuetzen else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(ein), None, ctypes.byref(ent), None, None, 0x1, ctypes.byref(aus))   # CRYPTPROTECT_UI_FORBIDDEN
    if not ok: raise GeheimFehler(f"DPAPI-Fehler {ctypes.GetLastError()}")
    try: return ctypes.string_at(aus.pbData, aus.cbData)
    finally: kernel32.LocalFree(aus.pbData)

def schuetzen(b): return _dpapi(b, True)
def entschuetzen(b): return _dpapi(b, False)

def speichern(pfad, text):
    """Geheimnis verschlüsselt speichern (atomar)."""
    pfad = Path(pfad); pfad.parent.mkdir(parents=True, exist_ok=True)
    enc = schuetzen(text.encode("utf-8"))
    if entschuetzen(enc).decode("utf-8") != text: raise GeheimFehler("Kontrolle nach dem Verschlüsseln fehlgeschlagen")
    tmp = pfad.with_suffix(".tmp"); tmp.write_bytes(enc); os.replace(tmp, pfad)

def laden(pfad, klartext_alt=None, melden=lambda m: None):
    """-> Text oder ''. Migriert eine alte Klartextdatei (nur nach erfolgreicher Verschlüsselung gelöscht)."""
    pfad = Path(pfad)
    if pfad.exists():
        try: return entschuetzen(pfad.read_bytes()).decode("utf-8").strip()
        except Exception as e: melden(f"Token nicht entschlüsselbar ({type(e).__name__}) – anderer Windows-Benutzer? Token neu setzen."); return ""
    if klartext_alt and Path(klartext_alt).exists():
        try:
            t = Path(klartext_alt).read_text(encoding="utf-8").strip()
            if not t: return ""
            speichern(pfad, t)
            Path(klartext_alt).unlink()
            melden("Confluence-Token: Klartextdatei verschlüsselt (DPAPI) und entfernt")
            return t
        except Exception as e:
            melden(f"Confluence-Token: Klartext gefunden, aber Verschlüsselung nicht möglich ({type(e).__name__}) – "
                   "Token wird NICHT verwendet. Datei data\\confluence_token.txt bitte manuell prüfen.")
            return ""
    return ""
