# aura/workflow/docx_fill.py — Word-Vorlagen (.docx) ausfuellen, ohne Zusatzpakete. Version 20261011v64e (v64e: Kästchen-Zustand auch bei «w14:val="0" />» mit Leerzeichen; v40: Optionen per Wortvergleich, leere Felder gemeldet)
# Unterstuetzt: Inhaltssteuerelemente (Text, Rich-Text, Auswahlliste, Kombinationsfeld, Datum, Kontrollkaestchen)
# und alte Formular-Textfelder (FORMTEXT, z.B. «[Text]»). Formatierung, Kopf-/Fusszeilen, Logos bleiben unveraendert.
# Felder werden ueber ihre Beschriftung angesprochen (Text daneben), bei Mehrfachvorkommen mit «@2», «@3» ...
import html, re, zipfile
from datetime import date, datetime
from pathlib import Path

PARTS = ("word/document.xml",)
_T = re.compile(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>")
_SDT = re.compile(r"<w:sdt>(?:(?!<w:sdt>).)*?</w:sdt>", re.S)

def _plain(xml):
    """Text mit Zeilenumbruch je Absatz."""
    xml = re.sub(r"<w:tab/>|<w:br/>", "<w:t> </w:t>", xml)
    return "\n".join(html.unescape("".join(_T.findall(p))) for p in xml.split("</w:p>"))

def _formtext_spans(x):
    """Alte Formularfelder FORMTEXT: (start, ende, start_text, ende_text)."""
    out, pos = [], 0
    while True:
        b = x.find('w:fldCharType="begin"', pos)
        if b < 0: return out
        e = x.find('w:fldCharType="end"', b)
        if e < 0: return out
        seg = x[b:e]
        if "FORMTEXT" in seg and "<w:textInput" in seg:
            rs = max(x.rfind("<w:r>", 0, b), x.rfind("<w:r ", 0, b))
            re_ = x.find("</w:r>", e) + 6
            sep = x.find('w:fldCharType="separate"', b, e)
            ts = x.find("</w:r>", sep) + 6 if sep > 0 else e
            te = max(x.rfind("<w:r>", 0, e), x.rfind("<w:r ", 0, e))
            out.append((rs, re_, ts, te))
        pos = e + 10

def _kind(s):
    if "w14:checkbox" in s: return "kontrollkaestchen"
    if "<w:dropDownList" in s: return "auswahl"
    if "<w:comboBox" in s: return "kombination"
    if "<w:date" in s: return "datum"
    return "text"

def analyze_xml(x):
    """Alle Felder in Dokumentreihenfolge: dict(nr, typ, key, label, optionen, start, ende, ...)."""
    fields = []
    for m in _SDT.finditer(x):
        s = m.group(0)
        fields.append({"typ": _kind(s), "start": m.start(), "ende": m.end(), "sdt": True,
                       "alias": (re.search(r'<w:alias w:val="([^"]*)"', s) or [None, ""])[1],
                       "optionen": [html.unescape(o) for o in re.findall(r'<w:listItem w:displayText="([^"]*)"', s)]})
    for rs, re_, ts, te in _formtext_spans(x):
        if any(f["start"] <= rs < f["ende"] for f in fields): continue
        fields.append({"typ": "text", "start": rs, "ende": re_, "sdt": False, "ts": ts, "te": te, "alias": "", "optionen": []})
    fields.sort(key=lambda f: f["start"])
    for i, f in enumerate(fields):
        prev_end = fields[i - 1]["ende"] if i else 0
        nxt = fields[i + 1]["start"] if i + 1 < len(fields) else len(x)
        before = _plain(x[max(prev_end, f["start"] - 6000):f["start"]])
        after = _plain(x[f["ende"]:min(nxt, f["ende"] + 4000)])
        lines = [l.strip() for l in before.split("\n")]
        b = lines[-1] if lines else ""                              # Text im selben Absatz vor dem Feld
        if len(re.sub(r"[^A-Za-zÄÖÜäöü]", "", b)) < 3:               # zu kurz (z.B. «/»): vorige Zeile dazunehmen
            prev = next((l for l in reversed(lines[:-1]) if l), "")
            b = (prev + " " + b).strip()
        if len(b) > 70: b = b[-70:].split(" ", 1)[-1]
        a = after.split("\n")[0].strip()[:80] or " ".join(after.split())[:80]
        if f["alias"]: lab = f["alias"]
        elif f["typ"] == "kontrollkaestchen": lab = a or b
        else: lab = b
        if not lab.strip(" /:"):                                     # Feld direkt hinter einem anderen Feld
            lab = f"{fields[i - 1]['label']} (2)" if i else (a or f"Feld {i + 1}")
        lab = re.sub(r"\s+", " ", lab).strip(" :").strip()
        if len(re.sub(r"[^A-Za-zÄÖÜäöü]", "", lab)) < 3:              # z.B. «/» zwischen zwei Feldern
            lab = f"{fields[i - 1]['label']} (2)" if i else f"Feld {i + 1}"
        f["label"] = lab or f"Feld {i + 1}"
        f["nr"] = i + 1
    seen = {}
    for f in fields:
        k = f["label"][:70]; seen[k] = seen.get(k, 0) + 1
        f["key"] = k if seen[k] == 1 else f"{k}@{seen[k]}"
    return fields

def analyze(path):
    with zipfile.ZipFile(path) as z: x = z.read(PARTS[0]).decode("utf-8")
    return [{k: f[k] for k in ("nr", "typ", "key", "optionen")} for f in analyze_xml(x)]

# ----------------------------------------------------------------------------- Werte einsetzen
def _esc(s): return html.escape(str(s), quote=False)

def _runs(rpr, text):
    lines = str(text).replace("\r\n", "\n").split("\n")
    out = []
    for i, l in enumerate(lines):
        if i: out.append(f"<w:r>{rpr}<w:br/></w:r>")
        out.append(f'<w:r>{rpr}<w:t xml:space="preserve">{_esc(l)}</w:t></w:r>')
    return "".join(out)

def _clean_rpr(content):
    m = re.search(r"<w:rPr>.*?</w:rPr>", content, re.S)
    rpr = m.group(0) if m else ""
    return re.sub(r'<w:rStyle w:val="[^"]*(?:Platzhalter|laceholder)[^"]*"/>', "", rpr)

def _fill_sdt(s, typ, val):
    if typ == "kontrollkaestchen":
        on = bool(val) and str(val).strip().lower() not in ("0", "false", "nein", "none")
        s = re.sub(r'<w14:checked w14:val="[01]"\s*/>', f'<w14:checked w14:val="{1 if on else 0}"/>', s)
        st = re.search(r'<w14:(checkedState|uncheckedState)[^>]*w14:val="([0-9A-Fa-f]+)"', s)
        chk = re.search(r'<w14:checkedState[^>]*w14:val="([0-9A-Fa-f]+)"', s)
        unc = re.search(r'<w14:uncheckedState[^>]*w14:val="([0-9A-Fa-f]+)"', s)
        sym = chr(int((chk if on else unc).group(1), 16)) if (chk and unc) else ("☒" if on else "☐")
        a, b = s.find("<w:sdtContent>"), s.rfind("</w:sdtContent>")
        body = re.sub(r"(<w:t(?:\s[^>]*)?>)[^<]*(</w:t>)", lambda m: m.group(1) + sym + m.group(2), s[a:b], count=1)
        return s[:a] + body + s[b:]
    text = str(val)
    if typ == "datum":
        d = None
        for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
            try: d = datetime.strptime(text.strip()[:10], fmt).date(); break
            except ValueError: pass
        if d:
            text = d.strftime("%d.%m.%Y")
            s = re.sub(r'(<w:date)(?: w:fullDate="[^"]*")?', rf'\1 w:fullDate="{d.isoformat()}T00:00:00Z"', s, count=1)
    s = s.replace("<w:showingPlcHdr/>", "")
    a = s.find("<w:sdtContent>") + len("<w:sdtContent>"); b = s.rfind("</w:sdtContent>")
    content = s[a:b]
    rpr = _clean_rpr(content)
    if re.search(r"<w:p[ >]", content):                              # Block-Steuerelement: Absatz behalten
        p = re.search(r"<w:p[ >].*?</w:p>", content, re.S).group(0)
        ppr = (re.search(r"<w:pPr>.*?</w:pPr>", p, re.S) or [""])[0] if re.search(r"<w:pPr>", p) else ""
        head = re.match(r"<w:p[^>]*>", p).group(0)
        new = f"{head}{ppr}{_runs(rpr, text)}</w:p>"
    else:
        new = _runs(rpr, text)
    return s[:a] + new + s[b:]

def _fill_formtext(x, f, val):
    seg = x[f["ts"]:f["te"]]
    rpr = _clean_rpr(seg) or _clean_rpr(x[f["start"]:f["ts"]])
    return x[:f["ts"]] + _runs(rpr, val) + x[f["te"]:]

def match_option(val, options):
    v = str(val).strip().lower()
    if not v: return None
    for o in options:
        if o.lower() == v: return o
    for o in options:
        if v in o.lower() or o.lower() in v: return o
    w = lambda s: set(re.findall(r"[a-zäöüé0-9]+", s.lower())) - {"und", "oder", "gemäss", "artikel", "art"}
    vw = w(v)                                                        # v40: gleiche Woerter, andere Reihenfolge
    best = [o for o in options if vw and vw <= w(o)]
    if best: return min(best, key=lambda o: len(w(o)))
    return None

def fill(template, out_path, values, leer=None):
    """values: {key oder 'nr:N': wert}. Leere Werte (None, '') lassen das Feld unveraendert.
    Rueckgabe: (gefuellt, unbekannte_keys, warnungen)."""
    with zipfile.ZipFile(template) as z: x = z.read(PARTS[0]).decode("utf-8")
    fields = analyze_xml(x); by = {f["key"]: f for f in fields}; by.update({f"nr:{f['nr']}": f for f in fields})
    todo, unknown, warn = [], [], []
    for k, v in values.items():
        f = by.get(k)
        if f is None: unknown.append(k); continue
        if f["typ"] != "kontrollkaestchen" and (v is None or str(v).strip() == ""):
            if leer is not None: leer.append(k)                      # v40: zugeordnet, aber leer
            continue
        if f["typ"] in ("auswahl", "kombination") and f["optionen"]:
            o = match_option(v, f["optionen"])
            if o is None:
                if f["typ"] == "auswahl": warn.append(f"{k}: «{v}» ist keine erlaubte Auswahl"); continue
            else: v = o
        todo.append((f, v))
    for f, v in sorted(todo, key=lambda t: -t[0]["start"]):          # von hinten, damit Positionen stimmen
        if f["sdt"]: x = x[:f["start"]] + _fill_sdt(x[f["start"]:f["ende"]], f["typ"], v) + x[f["ende"]:]
        else: x = _fill_formtext(x, f, v)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(template) as zi, zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zo:
        for item in zi.infolist():
            data = x.encode("utf-8") if item.filename == PARTS[0] else zi.read(item.filename)
            zo.writestr(item, data)
    return len(todo), unknown, warn
