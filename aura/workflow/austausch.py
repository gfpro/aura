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
from .. import sicherheit as SI

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
        if not sammlung_ok(s): hinweise.append(f"Sammlungsname «{s[:60]}» unzulässig – nicht im Paket"); continue    # v208
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

# v208: Manifest vollständig prüfen (Schema, Sammlungsnamen, Beziehung gemeinsam <-> dateien) und ZIP-Grenzen (sicherheit.py)
_SAMMLUNG = re.compile(r"^[A-Za-z0-9ÄÖÜäöüÉÈÀéèà][A-Za-z0-9ÄÖÜäöüÉÈÀéèà _.\-]{0,63}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

def sammlung_ok(s):
    """Sicherer Sammlungsname: ein einziges Segment, keine Separatoren/Laufwerke/Traversal, kein Gerätename."""
    if not isinstance(s, str) or not _SAMMLUNG.match(s): return False
    try: SI.pruefe_relpfad(s, "Sammlung")
    except SI.SicherheitsFehler: return False
    return True

def _manifest_pruefen(m, zip_namen):
    if not isinstance(m, dict): raise ValueError("Manifest ungültig (kein Objekt)")
    if m.get("format") != FORMAT: raise ValueError(f"Paketformat {m.get('format')!r} wird nicht unterstützt")
    for k, n in (("name", 80), ("titel", 200), ("aura_version", 40), ("exportiert", 40), ("von", 120)):
        v = m.get(k)
        if (k == "name" and not isinstance(v, str)) or (v is not None and (not isinstance(v, str) or len(v) > n)):
            raise ValueError(f"Manifest: Feld «{k}» ungültig")
    if not m["name"].strip() or not slugify(m["name"]): raise ValueError("Manifest: Name ungültig")
    if not isinstance(m.get("mit_laeufen", False), bool): raise ValueError("Manifest: Feld «mit_laeufen» ungültig")
    gm = m.get("gemeinsam", [])
    if not isinstance(gm, list) or len(gm) > 100: raise ValueError("Manifest: «gemeinsam» muss eine Liste sein")
    for g in gm:
        if not sammlung_ok(g) or g.startswith("_"): raise ValueError(f"Manifest: unzulässiger Sammlungsname {str(g)[:60]!r}")
    SI.pruefe_eindeutig(gm, "Sammlung")
    d = m.get("dateien")
    if not isinstance(d, dict) or len(d) > SI.ZIP_MAX_EINTRAEGE: raise ValueError("Manifest: «dateien» fehlt oder ungültig")
    gk = {SI.schluessel(g): g for g in gm}
    for n, h in d.items():
        if not isinstance(n, str) or not isinstance(h, str) or not _HEX64.match(h): raise ValueError(f"Manifest: Eintrag ungültig: {str(n)[:60]!r}")
        teile = SI.pruefe_relpfad(n, "Manifest-Eintrag")
        if teile[0] == "workflow" and len(teile) >= 2: continue
        if teile[0] == "gemeinsam" and len(teile) >= 3 and teile[1] in gm and gk[SI.schluessel(teile[1])] == teile[1]: continue
        raise ValueError(f"Manifest: Eintrag gehört zu keinem erlaubten Bereich/keiner Sammlung: {n[:60]!r}")
    ist = set(zip_namen) - {"paket.json"}
    if set(d) - ist: raise ValueError("Paket unvollständig: " + ", ".join(sorted(set(d) - ist))[:300])
    if ist - set(d): raise ValueError("Paket enthält nicht deklarierte Dateien: " + ", ".join(sorted(ist - set(d)))[:300])

def lesen(zpath):
    """Manifest lesen und das ZIP prüfen (Pfade, Grenzen, Schema, Prüfsummen, Version). Liefert (manifest, warnungen)."""
    try:
        with zipfile.ZipFile(zpath) as z:
            infos = {i.filename: i for i in SI.zip_pruefen(z, was="Paket-Eintrag")}
            if "paket.json" not in infos: raise ValueError("Kein AURA-Workflow-Paket (paket.json fehlt)")
            for n in infos:
                if n != "paket.json" and n.split("/")[0] not in ("workflow", "gemeinsam"): raise ValueError(f"Unzulässiger Pfad im Paket: {n}")
            try: m = json.loads(SI.zip_lesen(z, infos["paket.json"], 8 * 2**20).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError): raise ValueError("paket.json ist kein gültiges JSON")
            _manifest_pruefen(m, infos)
            for n, i in infos.items():
                if n != "paket.json" and m["dateien"][n] != SI.zip_sha256(z, i): raise ValueError(f"Datei beschädigt oder verändert: {n}")
    except SI.SicherheitsFehler as e: raise ValueError(f"Paket abgelehnt: {e}") from None
    except zipfile.BadZipFile: raise ValueError("Keine gültige ZIP-Datei") from None
    warn = []
    if _vnum(m.get("aura_version")) > _vnum(VERSION):
        warn.append(f"Paket stammt aus neuerer AURA-Version ({m['aura_version']}, hier {VERSION}) – evtl. nicht alle Bausteine bekannt")
    return m, warn

def importieren(zpath, name=None, gemeinsam_ersetzen=False, progress=print):
    """Paket nach workflows\\<name>\\ entpacken. Liefert (workflow_ordner, bericht_zeilen).
    NameBesetzt, wenn der Workflow schon existiert und kein anderer Name angegeben ist.
    v208: alles wird zuerst geprüft und in Arbeitsordner entpackt; erst dann werden Sammlungen/Workflow übernommen.
    Fehler -> vollständiges Zurückrollen (neue Dateien entfernt, ersetzte Sammlungen zurückverschoben)."""
    from .engine import load_workflow
    m, bericht = lesen(zpath)
    titel_neu = name.strip() if name else None
    name = slugify(name or m["name"])
    if not name: raise ValueError("Ungültiger Name")
    d = WF_DIR / name
    if d.exists(): raise NameBesetzt(f"Workflow «{name}» gibt es schon")
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    tmp = WF_DIR / f"_import_{stamp}"; stage = WISSEN_DIR / f"_import_{stamp}"
    neu_dateien, ersetzt, neu_ordner = [], [], []          # fürs Zurückrollen
    try:
        with zipfile.ZipFile(zpath) as z:
            infos = {i.filename: i for i in z.infolist()}
            for n in m["dateien"]:
                if n.startswith("workflow/"):
                    t = SI.ziel_in(tmp, n[len("workflow/"):]); t.parent.mkdir(parents=True, exist_ok=True); t.write_bytes(SI.zip_lesen(z, infos[n]))
            for sub in ("wissen", "vorlagen", "laeufe"): (tmp / sub).mkdir(parents=True, exist_ok=True)
            wfp = tmp / "workflow.json"
            try: wf = json.loads(wfp.read_text(encoding="utf-8")); assert isinstance(wf, dict)
            except Exception: raise ValueError("workflow.json fehlt oder ist ungültig")
            if wf.get("zeitplan") is not None:            # nie unbemerkt beim Empfänger laufen lassen
                bericht.append(f"Zeitplan entfernt (war: {json.dumps(wf.pop('zeitplan'), ensure_ascii=False)[:200]}) – bei Bedarf neu setzen")
            if titel_neu: wf["name"] = titel_neu           # sonst zwei Einträge mit gleichem Titel in der Liste
            wfp.write_text(json.dumps(wf, ensure_ascii=False, indent=1), encoding="utf-8")
            # gemeinsame Sammlungen: zuerst vollständig in den Arbeitsordner
            for s in m.get("gemeinsam", []):
                for n in m["dateien"]:
                    if n.startswith(f"gemeinsam/{s}/"):
                        t = SI.ziel_in(stage, n[len("gemeinsam/"):]); t.parent.mkdir(parents=True, exist_ok=True); t.write_bytes(SI.zip_lesen(z, infos[n]))
        # Übernehmen
        for s in m.get("gemeinsam", []):
            ziel = SI.ziel_in(WISSEN_DIR, s, "Sammlung"); quelle = stage / s
            files = sorted(f for f in quelle.rglob("*") if f.is_file()) if quelle.is_dir() else []
            if ziel.is_dir() and not gemeinsam_ersetzen:
                n_neu, anders = 0, []
                for f in files:
                    rel = f.relative_to(quelle).as_posix(); t = SI.ziel_in(ziel, rel, "Sammlungsdatei")
                    if not t.exists():
                        t.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, t); neu_dateien.append(t); n_neu += 1
                    elif SI.datei_sha256(t) != m["dateien"][f"gemeinsam/{s}/{rel}"]: anders.append(t.name)
                bericht.append(f"Sammlung «{s}» vorhanden: {n_neu} Dateien ergänzt" +
                               (f", abweichend (deine Fassung behalten): {', '.join(anders)}" if anders else ""))
            else:
                if ziel.exists() and not ziel.is_dir(): raise ValueError(f"Sammlung «{s}»: Zielname ist belegt")
                if ziel.is_dir():
                    alt = SI.ziel_in(WISSEN_DIR, f"_ersetzt_{stamp}_{s}", "Sammlung")
                    shutil.move(str(ziel), str(alt)); ersetzt.append((ziel, alt))
                    bericht.append(f"Sammlung «{s}» ersetzt (alte Fassung: {alt.name})")
                else: bericht.append(f"Sammlung «{s}» neu angelegt")
                if quelle.is_dir(): shutil.move(str(quelle), str(ziel))
                else: ziel.mkdir(parents=True)
                neu_ordner.append(ziel)
        if name != m["name"]: bericht.append(f"Unter neuem Namen angelegt: {name}")
        shutil.move(str(tmp), str(d))
        try: load_workflow(d / "workflow.json")
        except Exception as e: bericht.append(f"ACHTUNG – Workflow hier fehlerhaft: {e}")
    except Exception:
        for t in reversed(neu_dateien):
            try: t.unlink()
            except Exception: pass
        for z_ in neu_ordner: shutil.rmtree(z_, ignore_errors=True)
        for ziel, alt in reversed(ersetzt):
            try:
                if not ziel.exists(): shutil.move(str(alt), str(ziel))
            except Exception as e2: progress(f"Zurückrollen fehlgeschlagen: alte Sammlung liegt in {alt} ({e2})")
        shutil.rmtree(tmp, ignore_errors=True); shutil.rmtree(stage, ignore_errors=True); raise
    shutil.rmtree(stage, ignore_errors=True)
    if any(n.startswith("workflow/laeufe/") for n in m["dateien"]):
        bericht.append("Läufe mitgeliefert: nur zum Nachsehen, «Ab Schritt neu» funktioniert damit nicht zuverlässig")
    bericht.append(f"Exportiert von {m.get('von', '?')} am {m.get('exportiert', '?')} (AURA {m.get('aura_version', '?')})")
    bericht.append("Wissen wird beim ersten Lauf bzw. im Reiter «Wissen» neu eingebettet")
    progress(f"Importiert: {d}")
    return d, bericht
