# tools\wf_test.py – vergleicht den letzten Lauf (zwischenstand.json) mit tests\<fall>\erwartet.json
# Aufruf: python tools\wf_test.py workflows\verfahrensentscheid tests\gatevision
import json, sys
from pathlib import Path
wf, fall = Path(sys.argv[1]), Path(sys.argv[2])
st = json.loads(sorted(wf.glob("laeufe/*/zwischenstand.json"))[-1].read_text(encoding="utf-8"))
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
