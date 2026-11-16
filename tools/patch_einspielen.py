# tools/patch_einspielen.py — Patch einspielen. Version 20261116v249 (vorher v208)
# Aufruf (AURA vorher schliessen):  cd /d C:\aura   und   py tools\patch_einspielen.py  [Datei.zip] [Schalter]
# Schalter:  --ohne-signatur   nur ohne hinterlegten Schlüssel wirksam: Herkunft wird NICHT geprüft (Entwicklung)
#            --aelter          bewusst eine ältere Version einspielen (sonst abgelehnt)
#            --vorlagen        vorhandene Dateien in workflows\ und wissen\ überschreiben (sonst bleiben deine erhalten)
# v249 (H4): Versionsprüfung – ein Paket mit älterer Version als die installierte wird abgelehnt (auch wenn gültig
#   signiert); bei signierten Paketen muss die Version im Manifest zur Version im Paket passen. models\ ist gesperrt.
#   Vorhandene Dateien in workflows\ und wissen\ werden nur mit --vorlagen ersetzt.
# Ohne Angabe: neuestes AURA_patch_*.zip in C:\aura. Ablauf (v208: alles wird geprüft, BEVOR eine Datei verändert wird):
#   1. ZIP prüfen: Pfade (kein «..», kein Laufwerk/UNC, kein «\\», kein «:»/ADS, keine Gerätenamen), Doppelte (auch nur
#      Gross-/Kleinschreibung), Grössen, ZIP-Bomben, Links. Geschützt: data\, logs\, _sicherung\, .git\.
#   2. Signatur: _manifest.json (SHA-256 je Datei) + _manifest.sig (Ed25519). Öffentlicher Schlüssel NUR aus der
#      Windows-Richtlinie HKLM\SOFTWARE\Policies\AURA, Wert «UpdateSchluessel» (hex, mehrere durch Komma/Zeilen).
#      Ohne Schlüssel: Abbruch. --ohne-signatur überspringt NUR die Herkunftsprüfung (Restrisiko, Warnung).
#   3. _entfernen.txt (eine Datei pro Zeile, ab C:\aura) wird genauso streng geprüft.
#   4. Sicherung nach _sicherung\vor_<patch>\, dann schreiben (über temporäre Datei). Fehler -> alles zurückgerollt.
#   5. Zu entfernende Dateien nach _sicherung\vor_<patch>\_entfernt\ verschieben – nichts wird gelöscht.
#   6. Kontrolle: jede geschriebene Datei wird per SHA-256 mit dem ZIP verglichen.
import json, os, shutil, stat, sys, zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from aura import ed25519                                              # noqa: E402
from aura.sicherheit import (SicherheitsFehler, zip_pruefen, zip_lesen, zip_sha256, datei_sha256, ziel_in,   # noqa: E402
                             pruefe_relpfad, pruefe_eindeutig, schluessel)

MANIFEST, SIGNATUR, ENTFERNEN = "_manifest.json", "_manifest.sig", "_entfernen.txt"
GESCHUETZT = ("data/", "logs/", "_sicherung/", ".git/", "models/")       # v249: models\ kommt nie über einen Patch
EIGENE = ("workflows/", "wissen/")                                    # v249: vorhandene Dateien nur mit --vorlagen ersetzen
INIT = "aura/__init__.py"

def version_aus(text):
    """'VERSION = "20261116v248"' -> ('20261116v248', (248, 20261116)); unlesbar -> (None, None)."""
    import re
    m = re.search(r'VERSION\s*=\s*["\'](\d{8})v(\d+)["\']', text or "")
    return (f"{m.group(1)}v{m.group(2)}", (int(m.group(2)), int(m.group(1)))) if m else (None, None)

def version_pruefen(z, payload, root, manifest, aelter, out):
    """v249: Zielversion (aus dem Paket) gegen die installierte Version. Wirft SicherheitsFehler."""
    ist_txt, ist = version_aus((root / INIT).read_text(encoding="utf-8", errors="replace") if (root / INIT).is_file() else "")
    init = next((i for i in payload if schluessel(i.filename) == INIT), None)
    ziel_txt, ziel = version_aus(zip_lesen(z, init, 2**20).decode("utf-8", "replace")) if init else (None, None)
    if manifest is not None:                                           # signiert: Manifest ist verbindlich
        m_txt, m = version_aus(f'VERSION = "{manifest.get("aura_version", "")}"')
        if m is None: raise SicherheitsFehler("Manifest ohne gültige Versionsangabe (aura_version)")
        if ziel is not None and ziel != m: raise SicherheitsFehler(f"Version im Manifest ({m_txt}) passt nicht zur Version im Paket ({ziel_txt})")
        ziel_txt, ziel = m_txt, m
    if ziel is None: out("Hinweis: Paket enthält keine Versionsangabe (aura\\__init__.py) – Versionsprüfung nicht möglich."); return
    out(f"Version: installiert {ist_txt or 'unbekannt'} -> Paket {ziel_txt}")
    if ist is not None and ziel < ist:
        if not aelter: raise SicherheitsFehler(f"Paket ist älter ({ziel_txt}) als die installierte Version ({ist_txt}). "
                                               "Bewusst zurückgehen nur mit --aelter.")
        out("WARNUNG: ältere Version wird eingespielt (--aelter).")

def vertrauensanker():
    """Öffentliche Update-Schlüssel aus der Windows-Richtlinie (nur Administratoren können HKLM\\...\\Policies schreiben)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\AURA") as k:
            v, _ = winreg.QueryValueEx(k, "UpdateSchluessel")
    except Exception: return []
    v = "\n".join(v) if isinstance(v, (list, tuple)) else str(v)
    out = []
    for t in v.replace(",", "\n").split():
        try:
            b = bytes.fromhex(t.strip())
            if len(b) == 32: out.append(b)
        except ValueError: pass
    return out

def signatur_pruefen(z, payload, keys):
    """Manifest-Signatur und Prüfsummen. Wirft SicherheitsFehler."""
    namen = set(z.namelist())
    if MANIFEST not in namen or SIGNATUR not in namen: raise SicherheitsFehler("Update ist nicht signiert (_manifest.json/_manifest.sig fehlt)")
    mb = zip_lesen(z, z.getinfo(MANIFEST), 16 * 2**20)
    try: sig = bytes.fromhex(zip_lesen(z, z.getinfo(SIGNATUR), 1024).decode("ascii").strip())
    except Exception: raise SicherheitsFehler("Signaturdatei unlesbar")
    if not any(ed25519.verify(k, mb, sig) for k in keys): raise SicherheitsFehler("Signatur ungültig – Update stammt nicht vom freigegebenen Herausgeber oder wurde verändert")
    try: m = json.loads(mb.decode("utf-8")); soll = m["dateien"]; assert isinstance(soll, dict)
    except Exception: raise SicherheitsFehler("Manifest unlesbar")
    ist = {i.filename for i in payload}
    if set(soll) != ist: raise SicherheitsFehler("Manifest passt nicht zum Paketinhalt (fehlende oder zusätzliche Dateien)")
    for i in payload:
        if zip_sha256(z, i) != soll[i.filename]: raise SicherheitsFehler(f"Prüfsumme falsch: {i.filename}")
    return m

def _bak_dir(root, stem):
    b = root / "_sicherung" / f"vor_{stem}"
    return b if not b.exists() else root / "_sicherung" / f"vor_{stem}_{datetime.now():%Y%m%d_%H%M%S}"

def einspielen(zp, root=ROOT, keys=None, ohne_signatur=False, out=print, aelter=False, vorlagen=False):
    """-> 0 ok, 1 Fehler. Verändert bei jedem Prüffehler KEINE Datei."""
    root = Path(root).resolve(); zp = Path(zp)
    keys = vertrauensanker() if keys is None else keys
    try:
        with zipfile.ZipFile(zp) as z:
            # ---------- Phase 1: vollständige Prüfung, noch keine Änderung
            infos = zip_pruefen(z, was="Patch-Eintrag")
            payload = [i for i in infos if i.filename not in (MANIFEST, SIGNATUR)]
            manifest = None
            if keys: manifest = signatur_pruefen(z, payload, keys); out("Signatur: gültig")
            elif ohne_signatur: out("WARNUNG: Herkunft NICHT geprüft (--ohne-signatur). Nur Pakete aus sicherer Quelle einspielen!")
            else: raise SicherheitsFehler("Kein Update-Schlüssel hinterlegt (Richtlinie HKLM\\SOFTWARE\\Policies\\AURA\\UpdateSchluessel) – "
                                          "Abbruch. Nur mit ausdrücklichem --ohne-signatur ohne Herkunftsprüfung.")
            version_pruefen(z, payload, root, manifest, aelter, out)
            schreiben = [i for i in payload if i.filename != ENTFERNEN]
            ziele, behalten = [], []
            for i in schreiben:
                if schluessel(i.filename).startswith(GESCHUETZT): raise SicherheitsFehler(f"Patch darf diesen Bereich nicht ändern: {i.filename}")
                t = ziel_in(root, i.filename, "Patch-Eintrag")
                if t.is_dir(): raise SicherheitsFehler(f"Ziel ist ein Ordner: {i.filename}")
                if schluessel(i.filename).startswith(EIGENE) and t.exists() and not vorlagen \
                        and datei_sha256(t) != zip_sha256(z, i):
                    behalten.append(i.filename); continue                 # v249: eigene Workflows/Wissensdateien bleiben
                ziele.append((i, t))
            weg = []
            if ENTFERNEN in {i.filename for i in payload}:
                roh = zip_lesen(z, z.getinfo(ENTFERNEN), 2**20).decode("utf-8-sig")
                zeilen = [n.strip() for n in roh.splitlines() if n.strip() and not n.strip().startswith("#")]
                pruefe_eindeutig(zeilen, "Zeile in _entfernen.txt")
                for n in zeilen:
                    pruefe_relpfad(n, "Zeile in _entfernen.txt")
                    if schluessel(n).startswith(GESCHUETZT + EIGENE): raise SicherheitsFehler(f"_entfernen.txt darf diesen Bereich nicht ändern: {n}")
                    weg.append((n, ziel_in(root, n, "Zeile in _entfernen.txt")))
            # ---------- Phase 2: Sicherung, Schreiben, Entfernen – bei Fehler vollständig zurückrollen
            bak = _bak_dir(root, zp.stem); out(f"Patch: {zp.name}\nSicherung: {bak}")
            for n in behalten: out(f"  behalten  {n}  (deine Fassung weicht ab; ersetzen mit --vorlagen)")
            gesichert, neu, verschoben = [], [], []
            try:
                for i, t in ziele:
                    if t.exists():
                        b = bak / i.filename; b.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(t, b); gesichert.append((t, b))
                for i, t in ziele:
                    existed = t.exists()
                    t.parent.mkdir(parents=True, exist_ok=True)
                    if existed: os.chmod(t, stat.S_IWRITE | stat.S_IREAD)
                    tmp = t.with_name(t.name + ".aura_tmp")
                    tmp.write_bytes(zip_lesen(z, i)); os.replace(tmp, t)
                    if not existed: neu.append(t)
                    if datei_sha256(t) != zip_sha256(z, i): raise OSError(f"Kontrolle fehlgeschlagen: {i.filename}")
                    out(f"  ok        {i.filename}")
                for n, q in weg:
                    if q.exists():
                        dz = bak / "_entfernt" / n; dz.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(q), str(dz)); verschoben.append((q, dz)); out(f"  entfernt  {n}  -> {dz.relative_to(root)}")
            except Exception as e:
                out(f"FEHLER beim Einspielen ({type(e).__name__}: {e}) – alles wird zurückgerollt. "
                    "AURA oder Editor geöffnet? Schliessen und nochmals ausführen.")
                for q, dz in reversed(verschoben):
                    try: shutil.move(str(dz), str(q))
                    except Exception as e2: out(f"  Zurückrollen fehlgeschlagen: {q} ({e2})")
                for t in neu:
                    try: t.unlink()
                    except Exception: pass
                for t, b in gesichert:
                    try: os.chmod(t, stat.S_IWRITE | stat.S_IREAD) if t.exists() else None; shutil.copy2(b, t)
                    except Exception as e2: out(f"  Zurückrollen fehlgeschlagen: {t} ({e2}) – Sicherung liegt in {b}")
                for i, t in ziele:
                    tmp = t.with_name(t.name + ".aura_tmp")
                    if tmp.exists():
                        try: tmp.unlink()
                        except Exception: pass
                out("Patch NICHT eingespielt."); return 1
    except SicherheitsFehler as e:
        out(f"ABGELEHNT: {e}\nEs wurde keine Datei verändert."); return 1
    except zipfile.BadZipFile:
        out("ABGELEHNT: keine gültige ZIP-Datei. Es wurde keine Datei verändert."); return 1
    out("Fertig."); return 0

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    schalter = {"--ohne-signatur", "--aelter", "--vorlagen"}
    unbekannt = [a for a in argv if a.startswith("--") and a not in schalter]
    if unbekannt: print("Unbekannter Schalter:", ", ".join(unbekannt)); return 1
    ohne, aelter, vorlagen = (x in argv for x in ("--ohne-signatur", "--aelter", "--vorlagen"))
    argv = [a for a in argv if a not in schalter]
    zips = [Path(argv[0])] if argv else sorted(ROOT.glob("AURA_patch_*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips or not zips[-1].is_file(): print("Kein AURA_patch_*.zip in", ROOT); return 1
    return einspielen(zips[-1], ROOT, ohne_signatur=ohne, aelter=aelter, vorlagen=vorlagen)

if __name__ == "__main__": sys.exit(main())
