# aura/skills.py — Skills und Rollen: finden, freigeben, importieren. Version 20261031v146
# Rolle  = Markdown-Datei in C:\aura\rollen\<name>.md (Haltung, Arbeitsgrundsätze). Wird als Zusatz zum Systemtext verwendet:
#          im Chat (Auswahl «Rolle» über dem Chat) oder im Baustein «Anweisung ans Sprachmodell» (Feld «Rolle»).
# Skill  = Workflow-Paket mit skill.json (Anzeigename, Beschreibung, Rolle, Rechte, Version, Autor). Erscheint in der Palette
#          der Leinwand und kann als Vorlage für einen neuen Workflow kopiert werden.
# Freigabe: Jeder Skill und jede Rolle ist aus, bis sie freigegeben wird. Gespeichert wird eine Prüfsumme des Inhalts
# (Einstellung «skills_freigabe»): Ändert sich die Datei – z.B. durch eine neue Fassung eines Kollegen –, ist sie wieder aus.
# Kein Sprachmodell entscheidet, welcher Skill gilt (zu unzuverlässig, siehe v144) – nur die Freigabe durch den Menschen.
import hashlib, json, re, shutil
from pathlib import Path
from .config import ROOT, load_settings, save_settings
from .wissen import WF_DIR, slugify

ROLLEN_DIR = ROOT / "rollen"
RECHTE = {"web": "🌐 liest im Internet", "extern": "✉️ schreibt nach aussen", "datei": "💾 schreibt Dateien"}


def _frontmatter(txt):
    """(meta, body) aus «---\\nname: …\\ndescription: …\\n---»."""
    m = re.match(r"\ufeff?---\s*\n(.*?)\n---\s*\n?", txt, flags=re.S)
    if not m: return {}, txt
    meta = {}
    for z in m.group(1).splitlines():
        if ":" in z: k, v = z.split(":", 1); meta[k.strip().lower()] = v.strip().strip('"\'')
    return meta, txt[m.end():]


def _slug(t, n=60):
    """Dateiname ohne Kürzung auf 24 Zeichen (Rollennamen sind oft lang)."""
    t = t.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("é", "e"), ("è", "e"), ("à", "a"), ("ß", "ss")): t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:n]


def _hash(*pfade):
    h = hashlib.sha1()
    for p in pfade:
        p = Path(p)
        if p.is_file(): h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _titel_aus(body, fallback):
    m = re.search(r"^#\s+(.+)$", body, flags=re.M)
    return re.sub(r"^(Rolle|Skill|Aufgabe)\s*:\s*", "", m.group(1)).strip() if m else fallback


# ------------------------------------------------------------------ Finden
def _quellen():
    try: return json.loads((ROLLEN_DIR / ".quellen.json").read_text(encoding="utf-8"))
    except Exception: return {}


def rollen():
    out = []; qu = _quellen()
    for p in sorted(ROLLEN_DIR.glob("*.md")) if ROLLEN_DIR.exists() else []:
        txt = p.read_text(encoding="utf-8", errors="replace"); meta, body = _frontmatter(txt)
        out.append({"art": "rolle", "key": f"rolle:{p.stem}", "name": p.stem, "pfad": p, "hash": _hash(p), "quelle": qu.get(p.name, ""),
                    "titel": _titel_aus(body, p.stem), "beschreibung": meta.get("description", ""), "rechte": [],
                    "version": meta.get("version", ""), "autor": meta.get("author", meta.get("autor", ""))})
    return out


def skills():
    out = []
    for sj in sorted(WF_DIR.glob("*/skill.json")):
        d = sj.parent
        try: m = json.loads(sj.read_text(encoding="utf-8"))
        except Exception as e: m = {"titel": d.name, "beschreibung": f"skill.json nicht lesbar: {e}"}
        out.append({"art": "skill", "key": f"skill:{d.name}", "name": d.name, "pfad": d,
                    "hash": _hash(sj, d / "workflow.json", d / "anleitung.md"),
                    "titel": m.get("titel") or d.name, "beschreibung": m.get("beschreibung", ""),
                    "rolle": m.get("rolle", ""), "rechte": [r for r in m.get("rechte", []) if r in RECHTE],
                    "version": str(m.get("version", "")), "autor": m.get("autor", ""), "status": m.get("status", "")})
    return out


def alle():
    """Skills und Rollen mit Freigabestatus: aktiv (freigegeben, unverändert), geaendert (freigegeben, Inhalt seither neu)."""
    fg = load_settings().get("skills_freigabe") or {}
    out = skills() + rollen()
    for e in out:
        alt = fg.get(e["key"])
        e["aktiv"] = alt == e["hash"]; e["geaendert"] = bool(alt) and alt != e["hash"]
    return out


def freigeben(key, an=True):
    s = load_settings(); fg = dict(s.get("skills_freigabe") or {})
    e = next((x for x in skills() + rollen() if x["key"] == key), None)
    if an and e: fg[key] = e["hash"]
    else: fg.pop(key, None)
    s["skills_freigabe"] = fg
    if not an and key == f"rolle:{s.get('chat_rolle')}": s["chat_rolle"] = ""
    save_settings(s)


# ------------------------------------------------------------------ Rollen verwenden
def aktive_rollen():
    return [e for e in alle() if e["art"] == "rolle" and e["aktiv"]]


def rolle_text(name):
    """Text einer freigegebenen Rolle (ohne Kopfzeilen); leer, wenn unbekannt oder nicht freigegeben."""
    if not name: return ""
    e = next((x for x in aktive_rollen() if x["name"] == name), None)
    if not e: return ""
    _, body = _frontmatter(e["pfad"].read_text(encoding="utf-8", errors="replace"))
    return body.strip()


def chat_rolle():
    return load_settings().get("chat_rolle") or ""


def setze_chat_rolle(name):
    s = load_settings(); s["chat_rolle"] = name or ""; save_settings(s)


def chat_zusatz():
    """Zusatz zum Systemtext des Chats – nur bei freigegebener, gewählter Rolle."""
    t = rolle_text(chat_rolle())
    return ("\n\nArbeite zusätzlich nach dieser Rolle. Die Regeln oben (nur Quellen, Belege) gehen vor:\n" + t) if t else ""


# ------------------------------------------------------------------ Importieren
def art_raten(txt, dateiname=""):
    meta, body = _frontmatter(txt); n = (meta.get("name", "") + " " + Path(dateiname).stem).lower()
    if n.startswith("rolle") or " rolle" in n or re.search(r"^#\s*Rolle\b", body, flags=re.M): return "rolle"
    return "skill"


def importieren(pfad, art=None):
    """Markdown-Datei als Rolle oder Skill übernehmen. Liefert (art, ziel). Der Skill wird freigabepflichtig angelegt:
    ein Workflow-Paket im Rohbau (Dateien lesen) mit anleitung.md; Feldplan, Regeln und Wissen richtet man danach ein."""
    p = Path(pfad); txt = p.read_text(encoding="utf-8", errors="replace"); meta, body = _frontmatter(txt)
    art = art or art_raten(txt, p.name)
    name = _slug(meta.get("name") or p.stem) or "import"
    if art == "rolle":
        ROLLEN_DIR.mkdir(exist_ok=True); ziel = ROLLEN_DIR / f"{name}.md"
        if ziel.exists(): raise ValueError(f"Rolle «{name}» gibt es schon – zuerst entfernen oder umbenennen.")
        shutil.copy2(p, ziel)
        (ROLLEN_DIR / ".quellen.json").write_text(json.dumps({**_quellen(), ziel.name: p.name}, ensure_ascii=False, indent=1), encoding="utf-8")
        return art, ziel
    from .workflow import paket
    titel = _titel_aus(body, name)
    d = paket.create(titel)                                    # wirft, wenn es den Workflow schon gibt
    shutil.copy2(p, d / "anleitung.md")
    rolle = ""
    m = re.search(r"`(ROLLE_[^`]+?)\.md`", body)              # «Arbeite nach `ROLLE_….md`» → bekannte Rolle verknüpfen
    if m:
        quelle = m.group(1) + ".md"                           # Datei, aus der die Rolle importiert wurde (Feld «quelle»)
        rolle = next((r["name"] for r in rollen() if r.get("quelle") == quelle or r["name"] == _slug(m.group(1))), "")
    (d / "skill.json").write_text(json.dumps({
        "titel": titel, "beschreibung": meta.get("description", ""), "rolle": rolle, "rechte": [],
        "version": meta.get("version", "1"), "autor": meta.get("author", ""), "quelle": p.name,
        "status": "Rohbau – Schritte, Feldplan und Regeln noch einrichten (siehe anleitung.md)"},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return art, d


def entfernen(e):
    """Rolle in den Papierkorb (rollen\\_geloescht) bzw. Skill-Kennzeichnung (skill.json) entfernen – der Workflow bleibt."""
    if e["art"] == "rolle":
        t = ROLLEN_DIR / "_geloescht"; t.mkdir(exist_ok=True); shutil.move(str(e["pfad"]), str(t / e["pfad"].name))
    else:
        sj = e["pfad"] / "skill.json"
        if sj.exists(): sj.rename(sj.with_name("skill.json.entfernt"))
    freigeben(e["key"], False)


def als_vorlage(e, titel):
    """Neuen Workflow aus einem Skill kopieren (ohne Läufe). Liefert den neuen Paketordner."""
    name = slugify(titel); ziel = WF_DIR / name
    if not name: raise ValueError("Bitte einen Namen mit Buchstaben oder Ziffern eingeben")
    if ziel.exists(): raise ValueError(f"Workflow «{name}» gibt es schon")
    shutil.copytree(e["pfad"], ziel, ignore=shutil.ignore_patterns("laeufe", "skill.json", "skill.json.entfernt"))
    (ziel / "laeufe").mkdir(exist_ok=True)
    wj = ziel / "workflow.json"; wf = json.loads(wj.read_text(encoding="utf-8")); wf["name"] = titel.strip()
    wj.write_text(json.dumps(wf, ensure_ascii=False, indent=1), encoding="utf-8")
    return ziel
