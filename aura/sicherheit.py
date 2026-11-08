# aura/sicherheit.py — Zentrale Sicherheitsprüfungen (Pfade, ZIP-Grenzen, Dokumentgrenzen). Version 20261108v208
# Nur Standardbibliothek. Wird von tools/patch_einspielen.py, workflow/austausch.py, workflow/nodes.py und den
# Connectoren benutzt. Grundsatz: fail closed – im Zweifel ablehnen, bevor irgendeine Datei verändert wird.
#
# Pfadregeln (Windows-Semantik, gilt auch beim Testen unter Linux):
#   relative Pfade nur mit «/», keine «\\», kein «:» (Laufwerk, NTFS-ADS), kein führendes «/», keine leeren, «.»- oder
#   «..»-Segmente, kein Segment mit Punkt/Leerzeichen am Ende, keine Gerätenamen (CON, NUL, COM1 …), keine Steuerzeichen.
#   Danach wird der Zielpfad mit os.path.realpath aufgelöst (folgt Symlinks/Junctions) und muss in der Wurzel liegen.
import hashlib, ntpath, os, re, stat
from pathlib import Path, PurePosixPath

class SicherheitsFehler(ValueError):
    """Eingabe verletzt eine Sicherheitsregel. Meldung enthält nie Dateiinhalte."""

# ------------------------------------------------------------------ Grenzwerte (zentral, siehe README «Sicherheit»)
ZIP_MAX_EINTRAEGE = 20_000             # Anzahl Einträge eines ZIP (Update / Workflow-Paket)
ZIP_MAX_DATEI = 512 * 2**20            # 512 MB je entpackte Datei
ZIP_MAX_GESAMT = 2 * 2**30             # 2 GB entpackt insgesamt
ZIP_MAX_VERHAELTNIS = 200              # Kompressionsverhältnis (nur geprüft ab 1 MB entpackt)
PFAD_MAX_TIEFE = 24                    # Verzeichnisebenen
PFAD_MAX_LAENGE = 240                  # Zeichen (Windows MAX_PATH-Reserve)
DOC_MAX_BYTES = 200 * 2**20            # 200 MB je PDF/DOCX/Textdatei
DOC_MAX_SEITEN = 3_000                 # PDF-Seiten
DOC_MAX_SEKUNDEN = 300                 # Textextraktion je Dokument
DOCX_MAX_XML = 64 * 2**20              # 64 MB entpacktes word/document.xml
DOCX_MAX_EINTRAEGE = 5_000

_GERAETE = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {f"{p}{i}" for p in ("COM", "LPT") for i in
            list("123456789") + ["¹", "²", "³"]}
_VERBOTEN = re.compile(r'[\x00-\x1f<>"|?*:\\]')

def pruefe_relpfad(name, was="Pfad"):
    """Relativen Pfad (ZIP-Eintrag, Zeile aus _entfernen.txt, Manifestwert) prüfen -> Tupel der Segmente."""
    if not isinstance(name, str) or not name: raise SicherheitsFehler(f"{was}: leer oder kein Text")
    if len(name) > PFAD_MAX_LAENGE: raise SicherheitsFehler(f"{was} zu lang: {name[:60]}…")
    if _VERBOTEN.search(name): raise SicherheitsFehler(f"{was} enthält unzulässige Zeichen (\\ : * ? \" < > | oder Steuerzeichen): {name!r}")
    if name.startswith("/") or ntpath.isabs(name) or ntpath.splitdrive(name)[0]: raise SicherheitsFehler(f"{was} ist absolut: {name!r}")
    teile = name.split("/")
    if len(teile) > PFAD_MAX_TIEFE: raise SicherheitsFehler(f"{was} zu tief verschachtelt: {name[:60]}…")
    for t in teile:
        if t in ("", ".", ".."): raise SicherheitsFehler(f"{was} enthält leere, «.» oder «..»-Segmente: {name!r}")
        if t[-1] in ". ": raise SicherheitsFehler(f"{was}: Segment endet mit Punkt/Leerzeichen: {name!r}")
        if t.split(".")[0].rstrip(" ").upper() in _GERAETE: raise SicherheitsFehler(f"{was}: reservierter Gerätename: {name!r}")
    return tuple(teile)

def schluessel(name):
    """Vergleichsschlüssel wie unter Windows (Gross-/Kleinschreibung egal)."""
    return name.casefold()

def _real(p): return os.path.normcase(os.path.realpath(str(p)))

def liegt_in(pfad, wurzel):
    """True, wenn der aufgelöste Pfad (Links/Junctions verfolgt) in der aufgelösten Wurzel liegt (oder sie ist)."""
    w, p = _real(wurzel), _real(pfad)
    try: return os.path.commonpath([w, p]) == w
    except ValueError: return False                                  # anderes Laufwerk

def ziel_in(wurzel, relname, was="Pfad"):
    """Relativen Namen prüfen und als Pfad innerhalb der Wurzel liefern. Wirft SicherheitsFehler."""
    teile = pruefe_relpfad(relname, was)
    ziel = Path(wurzel).joinpath(*teile)
    if not liegt_in(ziel, wurzel): raise SicherheitsFehler(f"{was} führt aus dem erlaubten Ordner hinaus (Link/Junction?): {relname!r}")
    return ziel

def pruefe_eindeutig(namen, was="Eintrag"):
    """Doppelte oder nur in Gross-/Kleinschreibung verschiedene Namen ablehnen (auch Datei vs. Ordner gleichen Namens)."""
    gesehen, ordner = {}, set()
    for n in namen:
        k = schluessel(n)
        if k in gesehen: raise SicherheitsFehler(f"{was} doppelt bzw. kollidiert unter Windows: {gesehen[k]!r} / {n!r}")
        gesehen[k] = n
        teile = k.split("/")
        for i in range(1, len(teile)): ordner.add("/".join(teile[:i]))
    konflikt = ordner & set(gesehen)
    if konflikt: raise SicherheitsFehler(f"{was} ist zugleich Datei und Ordner: {sorted(konflikt)[0]!r}")

# ------------------------------------------------------------------ ZIP
def zip_pruefen(z, max_eintraege=ZIP_MAX_EINTRAEGE, max_datei=ZIP_MAX_DATEI, max_gesamt=ZIP_MAX_GESAMT,
                max_verh=ZIP_MAX_VERHAELTNIS, was="ZIP-Eintrag"):
    """Alle Einträge eines geöffneten ZipFile prüfen, BEVOR etwas entpackt wird. -> Liste der Datei-ZipInfos."""
    infos = z.infolist()
    if len(infos) > max_eintraege: raise SicherheitsFehler(f"Zu viele Einträge im ZIP ({len(infos)} > {max_eintraege})")
    dateien, gesamt = [], 0
    for i in infos:
        n = i.filename
        if i.flag_bits & 0x1: raise SicherheitsFehler(f"Verschlüsselter {was} wird nicht unterstützt: {n!r}")
        typ = stat.S_IFMT((i.external_attr >> 16) & 0xFFFF)                 # 0 = nicht angegeben (Windows-ZIPs)
        if typ == stat.S_IFLNK: raise SicherheitsFehler(f"Symbolischer Link im ZIP: {n!r}")
        if typ and typ not in (stat.S_IFREG, stat.S_IFDIR): raise SicherheitsFehler(f"Sondertyp im ZIP: {n!r}")
        if n.endswith("/"):
            pruefe_relpfad(n[:-1], was); continue
        pruefe_relpfad(n, was)
        if i.file_size > max_datei: raise SicherheitsFehler(f"{was} zu gross ({i.file_size // 2**20} MB): {n!r}")
        if i.file_size > 2**20 and i.file_size > max_verh * max(1, i.compress_size):
            raise SicherheitsFehler(f"Verdächtiges Kompressionsverhältnis (ZIP-Bombe?): {n!r}")
        gesamt += i.file_size
        if gesamt > max_gesamt: raise SicherheitsFehler(f"ZIP entpackt zu gross (> {max_gesamt // 2**20} MB)")
        dateien.append(i)
    pruefe_eindeutig([i.filename for i in dateien] + [i.filename[:-1] for i in infos if i.filename.endswith("/")
                      and i.filename[:-1] not in {d.filename for d in dateien}], was)
    return dateien

def zip_lesen(z, info, max_bytes=ZIP_MAX_DATEI):
    """Eintrag lesen; die tatsächlich gelesene Menge wird gezählt (Metadaten im ZIP nicht blind vertrauen)."""
    out, n = [], 0
    with z.open(info) as f:
        while True:
            b = f.read(1 << 20)
            if not b: break
            n += len(b)
            if n > max_bytes or n > info.file_size: raise SicherheitsFehler(f"Eintrag grösser als angegeben/erlaubt: {info.filename!r}")
            out.append(b)
    return b"".join(out)

def zip_sha256(z, info, max_bytes=ZIP_MAX_DATEI):
    """SHA-256 blockweise, ohne den Eintrag ganz in den Speicher zu laden."""
    h, n = hashlib.sha256(), 0
    with z.open(info) as f:
        while True:
            b = f.read(1 << 20)
            if not b: break
            n += len(b)
            if n > max_bytes or n > info.file_size: raise SicherheitsFehler(f"Eintrag grösser als angegeben/erlaubt: {info.filename!r}")
            h.update(b)
    return h.hexdigest()

def datei_sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

# ------------------------------------------------------------------ Dokumente
def pruefe_dokument(p, max_bytes=DOC_MAX_BYTES):
    """Grösse vor dem Lesen prüfen (PDF/DOCX/Text)."""
    try: g = os.path.getsize(p)
    except OSError as e: raise SicherheitsFehler(f"Datei nicht lesbar: {Path(p).name} ({type(e).__name__})")
    if g > max_bytes: raise SicherheitsFehler(f"{Path(p).name} ist zu gross ({g // 2**20} MB, Grenze {max_bytes // 2**20} MB)")

def docx_xml(p, teil="word/document.xml", max_bytes=DOCX_MAX_XML):
    """XML-Teil aus einer .docx (ZIP) mit Grenzen lesen."""
    import zipfile
    pruefe_dokument(p)
    with zipfile.ZipFile(p) as z:
        if len(z.infolist()) > DOCX_MAX_EINTRAEGE: raise SicherheitsFehler(f"{Path(p).name}: zu viele Teile im Word-Dokument")
        i = z.getinfo(teil)
        if i.file_size > max_bytes: raise SicherheitsFehler(f"{Path(p).name}: Dokumentinhalt zu gross ({i.file_size // 2**20} MB)")
        return zip_lesen(z, i, max_bytes).decode("utf-8", "replace")

# ------------------------------------------------------------------ Freigaben für Workflow-Dateizugriffe
class Freigaben:
    """Wo ein Workflow lesen darf: im eigenen Paket/Ordner und in vom Benutzer ausgewählten Eingabedateien."""
    def __init__(self, wf_dir, eingaben=()):
        self.wf_dir = Path(wf_dir)
        self.dateien = {_real(f) for f in eingaben if f}
    def erlaube(self, dateien):
        self.dateien |= {_real(f) for f in dateien if f}
    def ressource(self, v, was="Vorlage"):
        """Statische/dynamische Ressource des Workflows (Vorlage, Textvorlage): MUSS im Workflow-Ordner liegen."""
        s = str(v)
        if not s.strip(): raise SicherheitsFehler(f"{was}: leerer Pfad")
        p = Path(s) if (Path(s).is_absolute() or ntpath.isabs(s) or ntpath.splitdrive(s)[0]) else self.wf_dir / s.replace("\\", "/")
        if not liegt_in(p, self.wf_dir): raise SicherheitsFehler(f"{was} liegt ausserhalb des Workflow-Ordners: {Path(s).name}")
        return p
    def lesen(self, v, was="Datei"):
        """Datei zum Lesen (extract, pruefliste): ausgewählte Eingabe ODER im Workflow-Ordner."""
        s = str(v)
        if _real(s) in self.dateien: return Path(s)
        return self.ressource(s, was + " (weder ausgewählte Eingabe noch im Workflow-Ordner)")
