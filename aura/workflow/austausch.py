# aura/workflow/austausch.py — Workflow-Pakete exportieren/importieren (Übergabe an Mitarbeitende). Version 20261013v78
# Datei: <name>.aurawf.zip
#   paket.json                 Manifest: Format, AURA-Version, Name, gemeinsame Sammlungen, Prüfsummen
#   workflow/...               Inhalt von workflows\<name>\ (workflow.json, wissen\, vorlagen\, optional laeufe\)
#   gemeinsam/<sammlung>/...   eingebundene gemeinsame Sammlungen aus wissen\<sammlung>\
# Eingebettete Vektoren werden NICHT mitgegeben: Der Empfänger bettet beim ersten Lauf bzw. im Reiter «Wissen» neu ein.
import getpass, hashlib, json, re, shutil, zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from .. import VERSION
from ..wissen import WF_DIR, WISSEN_DIR, slugify

FORMAT = 1
SKIP = re.compile(r"(^|/)(~\$|\.~lock|Thumbs\.db$|desktop\.ini$|_entfernt/|__pycache__/)", re.I)

def _vnum(v):                                   # "20261013v77" -> (20261013, 77)
    m = re.match(r"(\d{8})v(\d+)", str(v or "")); return (int(m[1]), int(m[2])) if m else (0, 0)

def _sha(data): return hashlib.sha256(data).hexdigest()

def _sammlungen(wf):
    """Namen aller eingebundenen Sammlungen ausser «eigen» (roh aus workflow.json)."""
    out = []
    def add(c):
        for x in (c if isinstance(c, list) else [c]):
            if isinstance(x, str) and x and x != "eigen" and x not in out: out.append(x)
    for k in wf.get("knowledge") or []: add(k.get("sammlung") if isinstance(k, dict) else k)
    def walk(st):
        if isinstance(st, dict):
            if st.get("collection"): add(st["collection"])
            walk(st.get("schritt"))                     # fuer_jedes
    for st in wf.get("steps") or []: walk(st)
    return out

# ------------------------------------------------------------------ Export
def export(pkg, ziel, mit_laeufen=False, progress=print):
    """Workflow-Paket als ZIP schreiben. Liefert (pfad, hinweise)."""
    pkg = Path(pkg); wf = json.loads((pkg / "workflow.json").read_text(encoding="utf-8"))
    hinweise, dateien = [], {}

    def walk(st):                                       # absolute Vorlagen/Dateien ins Paket holen
        if not isinstance(st, dict): return
        for key in ("vorlage", "file"):
            v = st.get(key)
            if isinstance(v, str) and "{{" not in v and Path(v).is_absolute():
                p = Path(v)
                if p.is_file():
                    dateien[f"workflow/vorlagen/{p.name}"] = p.read_bytes(); st[key] = f"vorlagen/{p.name}"
                    hinweise.append(f"Absoluter Pfad ins Paket übernommen: {p.name}")
                else: hinweise.append(f"Schritt «{st.get('id')}»: Datei fehlt und wird nicht mitgegeben: {v}")
        walk(st.get("schritt"))
    for st in wf.get("steps") or []: walk(st)

    for f in sorted(pkg.rglob("*")):
        rel = f.relative_to(pkg).as_posix()
        if not f.is_file() or rel == "workflow.json" or SKIP.search(rel): continue
        if rel.startswith("laeufe/") and not mit_laeufen: continue
        dateien.setdefault(f"workflow/{rel}", f.read_bytes())
    dateien["workflow/workflow.json"] = json.dumps(wf, ensure_ascii=False, indent=1).encode("utf-8")

    gemeinsam = []
    for s in _sammlungen(wf):
        if s.startswith("wf:"): hinweise.append(f"Wissen eines anderen Workflows («{s}») wird nicht mitgegeben"); continue
        d = WISSEN_DIR / s
        if not d.is_dir(): hinweise.append(f"Gemeinsame Sammlung «{s}» nicht gefunden – nicht im Paket"); continue
        for f in sorted(d.rglob("*")):
            rel = f.relative_to(d).as_posix()
            if f.is_file() and not SKIP.search(rel): dateien[f"gemeinsam/{s}/{rel}"] = f.read_bytes()
        gemeinsam.append(s)

    manifest = {"format": FORMAT, "aura_version": VERSION, "name": pkg.name, "titel": wf.get("name", pkg.name),
                "exportiert": datetime.now().isoformat(timespec="seconds"), "von": getpass.getuser(),
                "mit_laeufen": bool(mit_laeufen), "gemeinsam": gemeinsam,
                "dateien": {k: _sha(v) for k, v in sorted(dateien.items())}}
    ziel = Path(ziel); tmp = ziel.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("paket.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for k, v in sorted(dateien.items()): z.writestr(k, v)
    tmp.replace(ziel)
    progress(f"Exportiert: {ziel} ({len(dateien)} Dateien)")
    return ziel, hinweise

# ------------------------------------------------------------------ Import
class NameBesetzt(ValueError): pass

def lesen(zpath):
    """Manifest lesen und das ZIP prüfen (Pfade, Prüfsummen, Version). Liefert (manifest, warnungen)."""
    with zipfile.ZipFile(zpath) as z:
        if "paket.json" not in z.namelist(): raise ValueError("Kein AURA-Workflow-Paket (paket.json fehlt)")
        m = json.loads(z.read("paket.json").decode("utf-8"))
        if m.get("format") != FORMAT: raise ValueError(f"Paketformat {m.get('format')} wird nicht unterstützt")
        for n in z.namelist():
            p = PurePosixPath(n)
            if n.endswith("/"): continue
            if p.is_absolute() or ".." in p.parts or ":" in n or "\\" in n or p.parts[0] not in ("paket.json", "workflow", "gemeinsam"):
                raise ValueError(f"Unzulässiger Pfad im Paket: {n}")
            if n != "paket.json" and m["dateien"].get(n) != _sha(z.read(n)):
                raise ValueError(f"Datei beschädigt oder verändert: {n}")
        if set(m["dateien"]) - set(z.namelist()): raise ValueError("Paket unvollständig: " + ", ".join(sorted(set(m["dateien"]) - set(z.namelist()))))
    warn = []
    if _vnum(m.get("aura_version")) > _vnum(VERSION):
        warn.append(f"Paket stammt aus neuerer AURA-Version ({m['aura_version']}, hier {VERSION}) – evtl. nicht alle Bausteine bekannt")
    return m, warn

def importieren(zpath, name=None, gemeinsam_ersetzen=False, progress=print):
    """Paket nach workflows\\<name>\\ entpacken. Liefert (workflow_ordner, bericht_zeilen).
    NameBesetzt, wenn der Workflow schon existiert und kein anderer Name angegeben ist."""
    from .engine import load_workflow
    m, bericht = lesen(zpath)
    titel_neu = name.strip() if name else None
    name = slugify(name or m["name"])
    if not name: raise ValueError("Ungültiger Name")
    d = WF_DIR / name
    if d.exists(): raise NameBesetzt(f"Workflow «{name}» gibt es schon")
    tmp = WF_DIR / f"_import_{datetime.now():%Y%m%d_%H%M%S}"
    try:
        with zipfile.ZipFile(zpath) as z:
            for n in m["dateien"]:
                if n.startswith("workflow/"):
                    t = tmp / PurePosixPath(n).relative_to("workflow"); t.parent.mkdir(parents=True, exist_ok=True); t.write_bytes(z.read(n))
            for sub in ("wissen", "vorlagen", "laeufe"): (tmp / sub).mkdir(exist_ok=True)
            wfp = tmp / "workflow.json"; wf = json.loads(wfp.read_text(encoding="utf-8"))
            if wf.get("zeitplan") is not None:            # nie unbemerkt beim Empfänger laufen lassen
                bericht.append(f"Zeitplan entfernt (war: {json.dumps(wf.pop('zeitplan'), ensure_ascii=False)}) – bei Bedarf neu setzen")
            if titel_neu: wf["name"] = titel_neu           # sonst zwei Einträge mit gleichem Titel in der Liste
            wfp.write_text(json.dumps(wf, ensure_ascii=False, indent=1), encoding="utf-8")
            # gemeinsame Sammlungen
            for s in m.get("gemeinsam", []):
                ziel = WISSEN_DIR / s; files = [n for n in m["dateien"] if n.startswith(f"gemeinsam/{s}/")]
                if ziel.is_dir() and not gemeinsam_ersetzen:
                    neu, anders = 0, []
                    for n in files:
                        t = ziel / PurePosixPath(n).relative_to(f"gemeinsam/{s}")
                        if not t.exists(): t.parent.mkdir(parents=True, exist_ok=True); t.write_bytes(z.read(n)); neu += 1
                        elif _sha(t.read_bytes()) != m["dateien"][n]: anders.append(t.name)
                    bericht.append(f"Sammlung «{s}» vorhanden: {neu} Dateien ergänzt" +
                                   (f", abweichend (deine Fassung behalten): {', '.join(anders)}" if anders else ""))
                else:
                    if ziel.is_dir():
                        alt = WISSEN_DIR / f"_ersetzt_{datetime.now():%Y%m%d_%H%M%S}_{s}"; shutil.move(str(ziel), str(alt))
                        bericht.append(f"Sammlung «{s}» ersetzt (alte Fassung: {alt.name})")
                    else: bericht.append(f"Sammlung «{s}» neu angelegt")
                    for n in files:
                        t = ziel / PurePosixPath(n).relative_to(f"gemeinsam/{s}"); t.parent.mkdir(parents=True, exist_ok=True); t.write_bytes(z.read(n))
        if name != m["name"]: bericht.append(f"Unter neuem Namen angelegt: {name}")
        shutil.move(str(tmp), str(d))
        try: load_workflow(d / "workflow.json")
        except Exception as e: bericht.append(f"ACHTUNG – Workflow hier fehlerhaft: {e}")
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True); raise
    if any(n.startswith("workflow/laeufe/") for n in m["dateien"]):
        bericht.append("Läufe mitgeliefert: nur zum Nachsehen, «Ab Schritt neu» funktioniert damit nicht zuverlässig")
    bericht.append(f"Exportiert von {m.get('von', '?')} am {m.get('exportiert', '?')} (AURA {m.get('aura_version', '?')})")
    bericht.append("Wissen wird beim ersten Lauf bzw. im Reiter «Wissen» neu eingebettet")
    progress(f"Importiert: {d}")
    return d, bericht
