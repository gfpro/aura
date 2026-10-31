# tools\wf_test.py – vergleicht den letzten Lauf (zwischenstand.json) mit tests\<fall>\erwartet.json
# Aufruf: python tools\wf_test.py workflows\verfahrensentscheid workflows\verfahrensentscheid\tests\gatevision [laufordner]
import json, sys
from pathlib import Path
wf, fall = Path(sys.argv[1]), Path(sys.argv[2])
if len(sys.argv) > 3: zf = Path(sys.argv[3]) / "zwischenstand.json"
else:   # neuester Lauf, dessen Eingaben zu diesem Testfall gehören (gleiche Dateinamen)
    soll_dat = {x.name.lower() for x in fall.iterdir() if x.suffix.lower() in (".pdf", ".docx", ".md", ".txt")}
    soll_dat |= {d.lower() for d in json.loads((fall / "erwartet.json").read_text(encoding="utf-8")).get("_dateien", [])}
    gnr = str(json.loads((fall / "erwartet.json").read_text(encoding="utf-8")).get("_geschaeftsnr", "")).lower()
    def eing(z):
        e = {x.name.lower() for x in (z.parent / "eingaben").glob("*")}
        try: e |= {Path(f).name.lower() for v in json.loads(z.read_text(encoding="utf-8"))["input"].values() for f in (v or [])}
        except Exception: pass
        return e
    def passt(z):
        if eing(z) & soll_dat: return True
        if gnr:
            try: return str(json.loads(z.read_text(encoding="utf-8")).get("werte", {}).get("geschaeftsnr", "")).lower() == gnr
            except Exception: return False
        return False
    alle = list(wf.glob("laeufe/*/zwischenstand.json"))
    kand = [z for z in alle if passt(z)]
    if not kand:
        print(f"Kein Lauf passt zu {fall.name} (Dateien: {', '.join(sorted(soll_dat))}; Geschäfts-Nr.: {gnr or '-'})\nLetzte Läufe:")
        for z in sorted(alle, key=lambda p: p.stat().st_mtime)[-6:]: print(f"  {z.parent.name}: {', '.join(sorted(eing(z))) or '(keine Eingaben)'}")
        sys.exit(1)
    zf = max(kand, key=lambda p: p.stat().st_mtime)
print(f"Lauf: {zf.parent.name}\n")
st = json.loads(zf.read_text(encoding="utf-8"))
soll = json.loads((fall / "erwartet.json").read_text(encoding="utf-8"))
def get(p):
    v = st
    for t in p.split("."): v = v.get(t) if isinstance(v, dict) else None
    return v
def norm(x):
    if isinstance(x, str):
        s = x.strip().replace("'", "").replace("’", "")
        try: return float(s)
        except ValueError: return s.lower()
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else x
ok = 0
for k, w in soll.items():
    if k.startswith("_"): continue
    ist = get(k); hit = norm(ist) == norm(w); ok += hit
    print(f"{'✓' if hit else '✗'} {k:28} soll={w!r:.60}" + ("" if hit else f"\n{'':30}ist ={ist!r:.60}"))
n = sum(1 for k in soll if not k.startswith("_"))
print(f"\n{ok}/{n} Treffer")
sys.exit(0 if ok == n else 1)
