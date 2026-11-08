"""Ordnungssystem armasuisse (fix vorgegeben): Positionen, Titel, Pfad; Aehnlichkeit Frage <-> Position per e5.
Quelle: ordnungssystem_ar.csv (Export aus Acta Nova, 768 Positionen). Vektoren werden einmal berechnet und gecacht.
"""
import csv, hashlib, json, math, re
from pathlib import Path

HIER = Path(__file__).resolve().parent
ROOT = HIER.parents[1]
CSV = ROOT / "wissen" / "ordnungssystem.csv"          # amtsspezifisch, eingelesen unter «Wissen»
ALT = HIER / "ordnungssystem_ar.csv"                   # Uebergang: frueher mitgeliefert
CACHE = ROOT / "data" / "ordnungssystem_vec.json"

_POS = None      # {aktenzeichen: titel}
_VEC = None      # {aktenzeichen: [float]}


def datei():
    if not CSV.exists() and ALT.exists():               # einmalig uebernehmen, danach alte Kopie entfernen
        CSV.parent.mkdir(parents=True, exist_ok=True); CSV.write_bytes(ALT.read_bytes())
        try: ALT.unlink()
        except OSError: pass
    return CSV if CSV.exists() else None


def info():
    """{'datei', 'stand', 'n'} oder None."""
    if not datei():
        return None
    from datetime import datetime
    return {"datei": str(CSV), "stand": datetime.fromtimestamp(CSV.stat().st_mtime).strftime("%d.%m.%Y %H:%M"),
            "n": len(positionen())}


def entfernen():
    global _POS, _VEC
    for f in (CSV, CACHE, ALT):
        try: f.unlink()
        except OSError: pass
    _POS, _VEC = None, None


def positionen():
    """{aktenzeichen: titel}; leer, wenn kein Ordnungssystem eingelesen ist (Ranking laeuft dann ohne)."""
    global _POS
    if _POS is None:
        _POS = {}
        if datei():
            with open(CSV, encoding="utf-8") as f:
                _POS = {r["aktenzeichen"]: r["titel"] for r in csv.DictReader(f, delimiter=";")}
    return _POS


def _hash():
    return hashlib.sha1(CSV.read_bytes()).hexdigest() if datei() else ""


def importieren(pfad):
    """Excel-Export (oder CSV) des Ordnungssystems aus Acta Nova -> wissen\\ordnungssystem.csv. Gibt Anzahl zurueck."""
    global _POS, _VEC
    pfad = Path(pfad)
    if pfad.suffix.lower() == ".csv":
        txt = pfad.read_text(encoding="utf-8-sig")
        trenner = ";" if txt.split("\n", 1)[0].count(";") >= txt.split("\n", 1)[0].count(",") else ","
        zeilen = list(csv.reader(txt.splitlines(), delimiter=trenner))
    else:
        from .actanova import _xlsx_zeilen
        zeilen = _xlsx_zeilen(pfad)
    kopf_i = next((i for i, z in enumerate(zeilen[:10]) if "Aktenzeichen" in z or "aktenzeichen" in z), None)
    if kopf_i is None:
        raise ValueError("Spalte «Aktenzeichen» nicht gefunden – bitte den Excel-Export des Ordnungssystems aus Acta Nova wählen.")
    kopf = [k[:1].upper() + k[1:] for k in zeilen[kopf_i]]
    ia, it = kopf.index("Aktenzeichen"), kopf.index("Titel") if "Titel" in kopf else None
    ity = kopf.index("Typ") if "Typ" in kopf else None
    out = []
    for z in zeilen[kopf_i + 1:]:
        if len(z) > ia and z[ia].strip():
            out.append([z[ity] if ity is not None and len(z) > ity else "", z[ia].strip(),
                        z[it].strip() if it is not None and len(z) > it else ""])
    if not out:
        raise ValueError("Keine Positionen gefunden.")
    CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(["typ", "aktenzeichen", "titel"]); w.writerows(out)
    _POS, _VEC = None, None
    return len(out)


def eltern(pos):
    """'044' -> ['0', '04', '044']; '032.2' -> ['0', '03', '032', '032.2']"""
    out, basis = [], pos.split(".")[0]
    for i in range(1, len(basis) + 1):
        out.append(basis[:i])
    if "." in pos:
        out.append(pos)
    return [p for p in out if p in positionen()]


def pfad(pos):
    return " › ".join(f"{p} {positionen()[p]}" for p in eltern(pos))


AZ = re.compile(r"\b[a-z]{1,8}-(\d{1,4}(?:\.\d+)?)-[\d/]+")        # Amtskuerzel beliebig (ar-, gs- …)


def aus_aktenzeichen(text):
    """'... (ar-044-16/3/3/2/6)' -> ('044', 'ar-044-16/3/3/2/6'); bestes = laengste bekannte Position."""
    m = AZ.search(text or "")
    if not m or not positionen():
        return (None, m.group(0)) if m else (None, None)
    pos = m.group(1)
    while pos and pos not in positionen():
        pos = pos[:-1].rstrip(".")
    return (pos or None), m.group(0)


def _norm(v):
    v = [float(x) for x in v]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _vektoren(emb):
    global _VEC
    if _VEC is not None:
        return _VEC
    pos = positionen()
    h = _hash()
    try:
        c = json.loads(CACHE.read_text(encoding="utf-8"))
        if c.get("hash") == h:
            _VEC = c["vec"]
            return _VEC
    except Exception:
        pass
    _VEC = {}
    for az, titel in pos.items():               # Pfad gibt Kontext ("Allgemeines" allein ist leer)
        _VEC[az] = _norm(emb.query(pfad(az)))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"hash": h, "vec": _VEC}), encoding="utf-8")
    return _VEC


def aehnlichkeit(emb, frage):
    """{position: Kosinus} fuer alle Positionen; leeres dict, wenn kein Embedder."""
    try:
        if emb is None or not positionen() or not emb.available()[0]:
            return {}
        q = _norm(emb.query(frage))
        return {az: sum(a * b for a, b in zip(q, v)) for az, v in _vektoren(emb).items()}
    except Exception:
        return {}


def top(sims, n=5, ebene=None):
    """Beste Positionen; ebene=1 -> nur Hauptgruppen (0..5), 2 -> zweistellig usw."""
    items = [(az, s) for az, s in sims.items() if ebene is None or len(az.split(".")[0]) == ebene]
    return sorted(items, key=lambda x: -x[1])[:n]
