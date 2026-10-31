# aura/pptx_bau.py — PowerPoint aus einer Vorlage bauen, ohne Zusatzpakete (nur zipfile + Text-XML). Version 20261031v152
# Wie docx_fill: keine DLL, nichts zu installieren. Die Vorlage liefert Design, Masterfolien und Layouts; AURA legt neue Folien
# an, die auf diese Layouts verweisen, und setzt nur Texte in deren Platzhalter. Folien der Vorlage selbst werden entfernt.
# Folien: [{"art": "titel"|"inhalt"|"zwei"|"aussage", "titel": str, "untertitel": str, "punkte": [str | (ebene, str)],
#           "links": [...], "rechts": [...], "notizen": str}]
import re, zipfile
from pathlib import Path
from xml.sax.saxutils import escape

NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
R_LAYOUT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
R_SLIDE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
CT_SLIDE = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
NEBEN = {"sldNum", "ftr", "dt", "sldImg", "hdr"}                  # Platzhalter, die AURA nicht füllt


def layouts(z):
    """{datei: {"name", "ph": [(type, idx)]}} aller Folienlayouts der Vorlage."""
    out = {}
    for n in z.namelist():
        if not re.fullmatch(r"ppt/slideLayouts/slideLayout\d+\.xml", n): continue
        x = z.read(n).decode("utf-8")
        m = re.search(r'<p:cSld name="([^"]*)"', x)
        ph = [(re.search(r'type="(\w+)"', p).group(1) if 'type="' in p else "body",
               (re.search(r'idx="(\d+)"', p) or [None, None])[1]) for p in re.findall(r"<p:ph\b[^>]*>", x)]
        out[n.rsplit("/", 1)[1]] = {"name": (m.group(1) if m else "").replace("&quot;", '"'), "ph": ph}
    return out


def _waehle(lay, art):
    """Passendes Layout: zuerst nach Namen (deutsch/englisch), sonst nach Platzhaltern."""
    namen = {"titel": ("titelseite", "title slide", "titelfolie"), "inhalt": ("inhaltsseite", "title and content", "titel und inhalt"),
             "zwei": ("zwei inhalte", "two content"), "aussage": ("inhaltsseite", "title and content")}[art]
    for nm in namen:
        for f, l in sorted(lay.items(), key=lambda kv: int(re.sub(r"\D", "", kv[0]))):
            if l["name"].lower().startswith(nm): return f
    def body(l): return [p for p in l["ph"] if p[0] in ("body", "obj") or (p[0] not in NEBEN and p[0] not in ("title", "ctrTitle", "subTitle"))]
    for f, l in lay.items():
        t = {p[0] for p in l["ph"]}
        if art == "titel" and "ctrTitle" in t: return f
        if art == "zwei" and "title" in t and len(body(l)) >= 2: return f
        if art in ("inhalt", "aussage") and "title" in t and len(body(l)) == 1: return f
    raise ValueError(f"Die Vorlage hat kein Layout für «{art}»")


def _absatz(t, ebene=0, gross=False):
    pr = f'<a:pPr lvl="{ebene}"/>' if ebene else ""
    if gross: pr = '<a:pPr marL="0" indent="0"><a:buNone/></a:pPr>'
    rpr = f'<a:rPr lang="de-CH" sz="{2800 if gross else (2000 if not ebene else 1800)}" dirty="0"/>'   # gut lesbar
    return f"<a:p>{pr}<a:r>{rpr}<a:t>{escape(str(t))}</a:t></a:r></a:p>"


def _platz(nr, typ, idx, absaetze):
    attr = (f' type="{typ}"' if typ != "body" else "") + (f' idx="{idx}"' if idx is not None else "")
    inhalt = "".join(absaetze) or '<a:p><a:endParaRPr lang="de-CH"/></a:p>'
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{nr}" name="Platzhalter {nr}"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            f'<p:nvPr><p:ph{attr}/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>{inhalt}</p:txBody></p:sp>')


def _liste(punkte):
    out = []
    for p in punkte or []:
        e, t = p if isinstance(p, (tuple, list)) else (0, p)
        if str(t).strip(): out.append(_absatz(str(t).strip(), int(e)))
    return out


def _folie_xml(f, lay):
    art = f.get("art", "inhalt"); ph = lay["ph"]; sp = []; nr = 2
    bodies = [p for p in ph if p[0] not in NEBEN and p[0] not in ("title", "ctrTitle", "subTitle")]
    for typ, idx in ph:
        if typ in NEBEN: continue
        if typ in ("title", "ctrTitle"): abs_ = [_absatz(f.get("titel", ""))]
        elif typ == "subTitle": abs_ = [_absatz(z) for z in str(f.get("untertitel", "")).split("\n") if z.strip()]
        elif art == "zwei" and len(bodies) >= 2:
            abs_ = _liste(f.get("links") if (typ, idx) == bodies[0] else f.get("rechts") if (typ, idx) == bodies[1] else [])
        elif (typ, idx) == (bodies[0] if bodies else None):
            abs_ = [_absatz(f.get("aussage", ""), gross=True)] if art == "aussage" else _liste(f.get("punkte"))
        else: continue
        sp.append(_platz(nr, typ, idx, abs_)); nr += 1
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:sld {NS}><p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>'
            + "".join(sp) + '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')


def bauen(vorlage, ziel, folien):
    """Schreibt ziel (.pptx). Liefert die Anzahl Folien."""
    vorlage, ziel = Path(vorlage), Path(ziel)
    with zipfile.ZipFile(vorlage) as z:
        dateien = {n: z.read(n) for n in z.namelist()}
        lay = layouts(z)
    pres = dateien["ppt/presentation.xml"].decode("utf-8")
    prels = dateien["ppt/_rels/presentation.xml.rels"].decode("utf-8")
    ct = dateien["[Content_Types].xml"].decode("utf-8")
    # ---- Folien der Vorlage entfernen (samt Notizen)
    alte = [n for n in dateien if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
    for n in alte:
        rel = f"ppt/slides/_rels/{n.rsplit('/', 1)[1]}.rels"
        for t in re.findall(r'Target="\.\./notesSlides/([^"]+)"', dateien.get(rel, b"").decode("utf-8")):
            for k in (f"ppt/notesSlides/{t}", f"ppt/notesSlides/_rels/{t}.rels"): dateien.pop(k, None)
            ct = re.sub(rf'<Override PartName="/ppt/notesSlides/{re.escape(t)}"[^>]*/>', "", ct)
        dateien.pop(n, None); dateien.pop(rel, None)
        ct = re.sub(rf'<Override PartName="/{re.escape(n)}"[^>]*/>', "", ct)
    rids = re.findall(rf'<Relationship[^>]*Id="(\w+)"[^>]*Type="{re.escape(R_SLIDE)}"[^>]*/>', prels) + \
           re.findall(rf'<Relationship[^>]*Type="{re.escape(R_SLIDE)}"[^>]*Id="(\w+)"[^>]*/>', prels)
    prels = re.sub(rf'<Relationship[^>]*Type="{re.escape(R_SLIDE)}"[^>]*/>', "", prels)
    for rid in rids: pres = re.sub(rf'<p:sldId [^>]*r:id="{rid}"\s*/>', "", pres)
    if "<p:sldIdLst" not in pres:
        pres = re.sub(r"(</p:sldMasterIdLst>)", r"\1<p:sldIdLst></p:sldIdLst>", pres, count=1)
    pres = re.sub(r"<p:sldIdLst\s*/>", "<p:sldIdLst></p:sldIdLst>", pres)
    # ---- neue Folien
    n_rid = max([int(x) for x in re.findall(r'Id="rId(\d+)"', prels)] + [0]) + 1
    neue_ids = []
    for i, f in enumerate(folien, start=1):
        lf = _waehle(lay, f.get("art", "inhalt"))
        dateien[f"ppt/slides/slide{i}.xml"] = _folie_xml(f, lay[lf]).encode("utf-8")
        dateien[f"ppt/slides/_rels/slide{i}.xml.rels"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/'
            f'package/2006/relationships"><Relationship Id="rId1" Type="{R_LAYOUT}" Target="../slideLayouts/{lf}"/>'
            '</Relationships>').encode("utf-8")
        ct = ct.replace("</Types>", f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="{CT_SLIDE}"/></Types>')
        rid = f"rId{n_rid}"; n_rid += 1
        prels = prels.replace("</Relationships>", f'<Relationship Id="{rid}" Type="{R_SLIDE}" Target="slides/slide{i}.xml"/></Relationships>')
        neue_ids.append(f'<p:sldId id="{255 + i}" r:id="{rid}"/>')
    pres = re.sub(r"<p:sldIdLst>.*?</p:sldIdLst>", "<p:sldIdLst>" + "".join(neue_ids) + "</p:sldIdLst>", pres, count=1, flags=re.S)
    dateien["ppt/presentation.xml"] = pres.encode("utf-8")
    dateien["ppt/_rels/presentation.xml.rels"] = prels.encode("utf-8")
    dateien["[Content_Types].xml"] = ct.encode("utf-8")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp = ziel.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", dateien.pop("[Content_Types].xml"))      # muss zuerst stehen
        for n, b in dateien.items(): z.writestr(n, b)
    tmp.replace(ziel)
    return len(folien)
