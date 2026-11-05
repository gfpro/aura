# aura/glossar.py — Glossar (Begriff | Bedeutung | Typ). Version 20261105v204
# Bleibt lokal in data\\glossar.json. Ein Upload ersetzt das ganze Glossar. Typ: Person, Abkürzung, Projekt (frei).
import json, re
from pathlib import Path
from .config import DATA

PFAD = DATA / "glossar.json"
_cache = (None, [])

def laden():
    global _cache
    try: m = PFAD.stat().st_mtime
    except OSError: return []
    if _cache[0] != m:
        try: _cache = (m, json.loads(PFAD.read_text(encoding="utf-8")))
        except ValueError: return []
    return _cache[1]

def aus_zeilen(rows):
    """Sucht die Kopfzeile mit «Begriff» und «Bedeutung». Liefert (Einträge, Anzahl übersprungen)."""
    rows = [[str(c or "").strip() for c in r] for r in rows]
    kopf = next((i for i, r in enumerate(rows) if {"begriff", "bedeutung"} <= {c.lower() for c in r}), None)
    if kopf is None: raise ValueError("Es fehlen die Spalten «Begriff» und «Bedeutung».")
    k = [c.lower() for c in rows[kopf]]; b, d = k.index("begriff"), k.index("bedeutung"); t = k.index("typ") if "typ" in k else None
    out, weg = [], 0
    for r in rows[kopf + 1:]:
        if not any(r): continue
        be = r[b] if b < len(r) else ""; de = r[d] if d < len(r) else ""
        if not be or not de: weg += 1; continue
        out.append({"begriff": be, "bedeutung": de, "typ": r[t] if t is not None and t < len(r) else ""})
    return out, weg

def einlesen(pfad):
    p = Path(pfad)
    if p.suffix.lower() == ".xlsx":
        from .anon import _xlsx
        rows = _xlsx(p)
    else:
        rows = [re.split(r"[;\t]", z) for z in p.read_text(encoding="utf-8-sig").splitlines()]
    return aus_zeilen(rows)

def speichern(eintraege):
    PFAD.write_text(json.dumps(eintraege, ensure_ascii=False, indent=1), encoding="utf-8")

def _trifft(begriff, text):
    fl = 0 if begriff.isupper() else re.I                     # BRF nur gross, Projektnamen auch klein
    return re.search(r"(?<![\w])%s(?![\w])" % re.escape(begriff), text, fl) is not None

def treffer(text, eintraege=None):
    return [e for e in (laden() if eintraege is None else eintraege) if _trifft(e["begriff"], text)]

def erweitern(frage, eintraege=None):
    """Hängt die Bedeutungen an die Suchfrage an. Die Anzeige und das Sprachmodell behalten die Originalfrage."""
    neu = [e["bedeutung"] for e in treffer(frage, eintraege) if e["bedeutung"].lower() not in frage.lower()
           and not e.get("typ", "").lower().startswith("abk")]   # v204: Abkürzungen nur als Hinweis ans Sprachmodell
    return f"{frage} {' '.join(dict.fromkeys(neu))}" if neu else frage

def hinweis(text, eintraege=None):
    """Kurzer Hinweis fürs Sprachmodell; mehrdeutige Begriffe werden als solche genannt."""
    g = {}
    for e in treffer(text, eintraege): g.setdefault(e["begriff"], []).append(e["bedeutung"])
    if not g: return ""
    t = "; ".join(f"{k} = {v[0]}" if len(v) == 1 else f"{k} ist mehrdeutig: {' / '.join(v)}" for k, v in g.items())
    return f"\n(Glossar: {t}. Rate bei Mehrdeutigkeit nicht.)"
