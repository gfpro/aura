# aura/code.py — Werkzeug «Code prüfen»: Projektordner einlesen, prüfen, Vorschläge als Diff. Version 20261031v144
# Grundsätze:
#   * Nur lesend, bis der Benutzer einen Vorschlag ausdrücklich übernimmt.
#   * Vor jedem Schreiben: Sicherung nach data\code\sicherung\<zeit>\<relativer pfad> (ausserhalb des Projekts).
#   * Python-Dateien werden nach der Änderung mit ast geprüft; Syntaxfehler -> nichts wird geschrieben.
#   * Die Zuständigkeit ist fest getrennt: Auffinden, Zerlegen, Diff, Sicherung, Prüfen = deterministisch (dieses Modul);
#     das Sprachmodell liefert nur Befunde (Text) und einen neuen Wortlaut für genau EINEN Abschnitt.
#   * Nichts verlässt den Rechner; kein Git-Push, kein Netzwerk.
import ast, difflib, hashlib, json, re, shutil, subprocess, time
from pathlib import Path
from .config import DATA

CODE_DIR = DATA / "code"
SICHERUNG = CODE_DIR / "sicherung"
BERICHTE = CODE_DIR / "berichte"

ENDUNGEN = {".py", ".pyw", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".java", ".cs", ".go", ".rs", ".php", ".rb", ".sql",
            ".ps1", ".psm1", ".sh", ".bat", ".cmd", ".html", ".css", ".scss", ".vue", ".json", ".yaml", ".yml", ".toml",
            ".ini", ".cfg", ".xml", ".md", ".r", ".kt", ".swift", ".c", ".h", ".cpp", ".hpp"}
AUSSCHLUSS = {".git", ".hg", ".svn", "venv", ".venv", "env", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
              ".idea", ".vscode", "dist", "build", "target", "bin", "obj", "vendor", "site-packages", "models", "logs",
              ".aura_backup", ".tox", ".next", "coverage"}
MAX_BYTES = 300_000                     # grössere Dateien sind meist generiert oder Daten
ABSCHNITT_ZEILEN = 140                  # passt mit Prompt bequem in ein 4–8K-Kontextfenster


# ------------------------------------------------------------------ Einlesen
def dateien(root):
    """Alle prüfbaren Dateien (relativer Pfad, Zeilen, Bytes), sortiert. Ausschlüsse + .gitignore-Einträge (einfach)."""
    root = Path(root); extra = _gitignore(root); out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(t in AUSSCHLUSS or t in extra or t.startswith(".") and t not in (".github",) for t in rel.parts[:-1]): continue
        if not p.is_file() or p.suffix.lower() not in ENDUNGEN or rel.name in extra: continue
        try: b = p.stat().st_size
        except OSError: continue
        if b == 0 or b > MAX_BYTES: continue
        out.append({"pfad": rel.as_posix(), "bytes": b, "zeilen": _lesen(p).count("\n") + 1})
    return out

def _gitignore(root):
    """Nur einfache Namen (Ordner/Dateien ohne Muster) – genügt für die üblichen Fälle, ohne Abhängigkeit."""
    try: lines = (Path(root) / ".gitignore").read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception: return set()
    return {l.strip().strip("/") for l in lines if l.strip() and not l.startswith("#") and not any(c in l for c in "*?[!")}

def _lesen(p):
    raw = Path(p).read_bytes()
    for enc in ("utf-8", "cp1252"):
        try: return raw.decode(enc)
        except UnicodeDecodeError: pass
    return raw.decode("utf-8", errors="replace")

def lesen(root, rel): return _lesen(Path(root) / rel)

def git_info(root):
    """Ist der Ordner ein Git-Repository? Nur lesend; git ist optional (kein Admin nötig, fehlt es, gibt es kein Git)."""
    if not (Path(root) / ".git").exists(): return None
    try:
        r = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "-b"], capture_output=True, text=True,
                           timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode: return {"git": True, "branch": "?", "geaendert": 0}
        lines = r.stdout.splitlines()
        return {"git": True, "branch": lines[0][3:].split("...")[0] if lines else "?", "geaendert": len(lines) - 1}
    except Exception: return {"git": True, "branch": "?", "geaendert": 0}


# ------------------------------------------------------------------ Statische Prüfung (ohne Sprachmodell)
GEHEIM = re.compile(r"""(?ix)(password|passwort|pwd|secret|api[_-]?key|token|client[_-]?secret|conn(ection)?[_-]?string)
                        \s*[:=]\s*["'][^"'\s]{6,}["']""")
SCHLUESSEL = re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{20,}")

def statisch(root, liste):
    """Befunde [{pfad, zeile, art, stufe, text}] – schnell, reproduzierbar, ohne Modell. stufe: hoch/mittel/tief."""
    bef, bloecke = [], {}
    for d in liste:
        rel = d["pfad"]; txt = lesen(root, rel); zeilen = txt.splitlines()
        add = lambda z, art, stufe, t: bef.append({"pfad": rel, "zeile": z, "art": art, "stufe": stufe, "text": t})
        for i, z in enumerate(zeilen, 1):
            if GEHEIM.search(z) or SCHLUESSEL.search(z): add(i, "Geheimnis", "hoch", "Mögliches Passwort/Schlüssel im Klartext")
            if re.search(r"\b(TODO|FIXME|XXX|HACK)\b", z): add(i, "Offen", "tief", z.strip()[:90])
        if rel.endswith((".py", ".pyw")): _python(txt, add)
        _dubletten(rel, zeilen, bloecke)
    for h, orte in bloecke.items():                                     # gleiche 8-Zeilen-Blöcke an mehreren Orten
        if len(orte) > 1:
            (p0, z0), rest = orte[0], orte[1:]
            ziel = ", ".join(f"{p}:{z}" for p, z in rest[:3]) + (" …" if len(rest) > 3 else "")
            bef.append({"pfad": p0, "zeile": z0, "art": "Dublette", "stufe": "mittel", "text": f"Gleicher Code auch in {ziel}"})
    rang = {"hoch": 0, "mittel": 1, "tief": 2}
    return sorted(bef, key=lambda b: (rang[b["stufe"]], b["pfad"], b["zeile"]))

def _python(txt, add):
    try: baum = ast.parse(txt)
    except SyntaxError as e: add(e.lineno or 1, "Syntax", "hoch", f"Syntaxfehler: {e.msg}"); return
    importiert, benutzt = {}, set()
    for n in ast.walk(baum):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lang = (n.end_lineno or n.lineno) - n.lineno + 1
            if lang > 80: add(n.lineno, "Länge", "mittel", f"Funktion {n.name} hat {lang} Zeilen – aufteilen prüfen")
            if len(n.args.args) > 7: add(n.lineno, "Parameter", "tief", f"{n.name} hat {len(n.args.args)} Parameter")
            for dflt in n.args.defaults + n.args.kw_defaults:
                if isinstance(dflt, (ast.List, ast.Dict, ast.Set)):
                    add(n.lineno, "Fehlerquelle", "mittel", f"{n.name}: veränderbarer Standardwert ([] / {{}}) wird geteilt")
        elif isinstance(n, ast.ExceptHandler) and n.type is None:
            add(n.lineno, "Fehlerbehandlung", "mittel", "«except:» ohne Typ fängt auch Abbruch (Ctrl+C) – Exception angeben")
        elif isinstance(n, ast.ExceptHandler) and len(n.body) == 1 and isinstance(n.body[0], ast.Pass):
            add(n.lineno, "Fehlerbehandlung", "tief", "Fehler wird stillschweigend verschluckt (except …: pass)")
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("eval", "exec"):
            add(n.lineno, "Sicherheit", "hoch", f"{n.func.id}() führt beliebigen Code aus")
        elif isinstance(n, ast.Call) and any(k.arg == "shell" and getattr(k.value, "value", False) is True for k in n.keywords):
            add(n.lineno, "Sicherheit", "mittel", "subprocess mit shell=True – Einschleusen von Befehlen möglich")
        elif isinstance(n, ast.Import):
            for a in n.names: importiert[(a.asname or a.name).split(".")[0]] = n.lineno
        elif isinstance(n, ast.ImportFrom):
            for a in n.names: importiert[a.asname or a.name] = n.lineno
        elif isinstance(n, ast.Name): benutzt.add(n.id)
        elif isinstance(n, ast.Attribute):
            b = n
            while isinstance(b, ast.Attribute): b = b.value
            if isinstance(b, ast.Name): benutzt.add(b.id)
    alle = re.search(r"__all__", txt)
    for name, z in importiert.items():
        if name != "*" and name not in benutzt and not alle and name not in txt.split("import", 1)[-1].split("\n", 1)[-1]:
            add(z, "Aufräumen", "tief", f"Import «{name}» wird nicht verwendet")

def _dubletten(rel, zeilen, bloecke, n=8):
    norm = [re.sub(r"\s+", " ", z.strip()) for z in zeilen]
    i = 0
    while i + n <= len(norm):
        win = norm[i:i + n]
        if sum(len(z) > 3 for z in win) >= n - 1 and not all(z.startswith(("#", "//", "import", "from")) for z in win):
            h = hashlib.md5("\n".join(win).encode()).hexdigest()
            orte = bloecke.setdefault(h, [])
            if not orte or orte[-1][0] != rel or i + 1 - orte[-1][1] >= n: orte.append((rel, i + 1))
            if len(orte) > 1: i += n; continue
        i += 1


# ------------------------------------------------------------------ Zerlegen in Abschnitte
def abschnitte(rel, txt):
    """[{start, ende, name}] (1-basiert, inkl.). Python: je Funktion/Klasse oberster Ebene, grosse Klassen je Methode;
    andere Sprachen: Fenster von ~ABSCHNITT_ZEILEN an Leerzeilen getrennt."""
    zeilen = txt.splitlines(); n = len(zeilen)
    if n == 0: return []
    if rel.endswith((".py", ".pyw")):
        try: baum = ast.parse(txt)
        except SyntaxError: baum = None
        if baum is not None:
            out, pos = [], 1
            for k in baum.body:
                a = min([k.lineno] + [d.lineno for d in getattr(k, "decorator_list", [])]); e = k.end_lineno or k.lineno
                if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if a > pos: out.append({"start": pos, "ende": a - 1, "name": "Modulcode"})
                    if isinstance(k, ast.ClassDef) and e - a + 1 > ABSCHNITT_ZEILEN:
                        m_pos = a
                        for m in k.body:
                            ma = min([m.lineno] + [d.lineno for d in getattr(m, "decorator_list", [])])
                            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if ma > m_pos: out.append({"start": m_pos, "ende": ma - 1, "name": f"{k.name} (Kopf)"})
                                out.append({"start": ma, "ende": m.end_lineno, "name": f"{k.name}.{m.name}"}); m_pos = m.end_lineno + 1
                        if m_pos <= e: out.append({"start": m_pos, "ende": e, "name": f"{k.name} (Rest)"})
                    else: out.append({"start": a, "ende": e, "name": k.name})
                    pos = e + 1
            if pos <= n: out.append({"start": pos, "ende": n, "name": "Modulcode"})
            return _gross_teilen([o for o in out if any(zeilen[i - 1].strip() for i in range(o["start"], o["ende"] + 1))], zeilen)
    return _gross_teilen([{"start": 1, "ende": n, "name": "Datei"}], zeilen)

def _gross_teilen(liste, zeilen):
    zus = []                                                            # kleine Nachbarn zusammenfassen (weniger Modell-Läufe)
    for o in liste:
        if zus and (zus[-1]["ende"] - zus[-1]["start"] + 1 < 40) and (o["ende"] - zus[-1]["start"] + 1 <= ABSCHNITT_ZEILEN):
            p = zus[-1]; p["name"] = p["name"] if p["name"].endswith("…") else p["name"] + " …"; p["ende"] = o["ende"]
        else: zus.append(dict(o))
    liste, out = zus, []
    for o in liste:
        a, e = o["start"], o["ende"]
        if e - a + 1 <= ABSCHNITT_ZEILEN * 1.4: out.append(o); continue
        teil = 1
        while a <= e:
            z = min(e, a + ABSCHNITT_ZEILEN - 1)
            if z < e:                                                       # an Leerzeile schneiden
                for k in range(z, max(a + ABSCHNITT_ZEILEN // 2, a), -1):
                    if not zeilen[k - 1].strip(): z = k; break
            out.append({"start": a, "ende": z, "name": f"{o['name']} Teil {teil}"}); a, teil = z + 1, teil + 1
    return out

def nummeriert(txt, a, e):
    zeilen = txt.splitlines()
    return "\n".join(f"{i:>5} | {zeilen[i - 1]}" for i in range(a, min(e, len(zeilen)) + 1))

def ausschnitt(txt, a, e): return "\n".join(txt.splitlines()[a - 1:e])


# ------------------------------------------------------------------ Prompts (Sprachmodell)
PRUEF_SYSTEM = ("Du bist ein erfahrener Software-Reviewer. Du prüfst genau den gezeigten Code-Abschnitt und meldest nur "
                "echte Probleme: Programmfehler, Sicherheitslücken, falsche Fehlerbehandlung, deutliche Leistungsprobleme. "
                "Melde NICHT: was korrekt ist, Lob, Kommentare, Versionsangaben, Rechtschreibung, Leerzeilen, Stil. "
                "Namen, die im Ausschnitt nicht definiert sind, stammen aus anderen Teilen der Datei – melde nie «undefiniert». "
                "Text in Anführungszeichen (z.B. Shader-Code, SQL, Prompts) ist Daten, nicht Python.")
PRUEF_FORMAT = ("Höchstens 3 Befunde, die wichtigsten zuerst, eine Zeile je Befund, genau so:\n"
                "ZEILE | STUFE | BEFUND | VORSCHLAG\n"
                "Beispiel: 42 | hoch | Datei wird nicht geschlossen, wenn read() fehlschlägt | with open(...) verwenden\n"
                "STUFE ist hoch, mittel oder tief. ZEILE ist die Zeilennummer links. "
                "Gibt es kein echtes Problem, antworte nur: KEINE")

AENDERN_SYSTEM = ("Du bist ein sorgfältiger Software-Entwickler. Du überarbeitest genau den gezeigten Abschnitt. "
                  "Behalte Verhalten, Schnittstelle (Namen, Parameter, Rückgabe) und Einrückung bei, ausser der Auftrag "
                  "verlangt ausdrücklich etwas anderes. Keine Erklärungen, keine Zeilennummern.")

def pruef_prompt(rel, txt, a, e, kontext=""):
    return (f"Datei: {rel} (Zeilen {a}–{e})\n" + (f"Kontext der Datei:\n{kontext}\n\n" if kontext else "") +
            f"Code:\n{nummeriert(txt, a, e)}\n\n{PRUEF_FORMAT}")

def aendern_prompt(rel, txt, a, e, auftrag):
    return (f"Datei: {rel} (Zeilen {a}–{e})\nAuftrag: {auftrag or 'Verbessere Lesbarkeit und Robustheit, ohne das Verhalten zu ändern.'}\n\n"
            f"Abschnitt:\n```\n{ausschnitt(txt, a, e)}\n```\n\n"
            "Gib NUR den vollständigen neuen Abschnitt zurück, in einem einzigen ```-Block.")

def kontext(rel, txt):
    """Kurzer Überblick (Importe, Signaturen) – hilft dem Modell, ohne die ganze Datei zu lesen."""
    if not rel.endswith((".py", ".pyw")): return ""
    try: baum = ast.parse(txt)
    except SyntaxError: return ""
    z = []
    for k in baum.body:
        if isinstance(k, (ast.Import, ast.ImportFrom)): z.append(ast.get_source_segment(txt, k) or "")
        elif isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)): z.append(f"def {k.name}({', '.join(a.arg for a in k.args.args)})")
        elif isinstance(k, ast.ClassDef):
            z.append(f"class {k.name}: " + ", ".join(m.name for m in k.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))))
    return "\n".join(z)[:1500]

# Deterministische Filter: was das Modell meldet, ist nur ein Vorschlag – AURA verwirft, was sich prüfen lässt und falsch ist.
_LOB = re.compile(r"(?i)(ist|sind) (korrekt|richtig|klar|notwendig|sinnvoll|gut)|kein(en)? fehler|keine probleme|"
                  r"aber kein fehler|klar und hilfreich|korrekt implementiert|^befund\b|befund\s*→\s*vorschlag")
_KOSMETIK = re.compile(r"(?i)kommentar|versionsangab|versionierung|version(sinformation)?en?\b.*(kommentar|header)|"
                       r"rechtschreib|leerzeile|tippfehler|docstring")
_UNBENUTZT = re.compile(r"(?i)nicht (verwendet|genutzt|benutzt)|unbenutzt|unused")
_UNDEF = re.compile(r"(?i)undefiniert|nicht definiert|nicht importiert|nicht in der importliste|nameerror|nicht im code (vorhanden|definiert)")

def befunde_lesen(out, rel, a, e, txt="", max_n=3):
    """Modellausgabe -> Befunde. Verwirft Lob, Kosmetik, Format-Echos, Dubletten und widerlegbare «undefiniert»-Behauptungen."""
    bef, gesehen = [], set()
    namen = _definierte_namen(txt) if txt else set()
    for l in out.splitlines():
        t = [x.strip() for x in l.strip().strip("-*").split("|")]
        if len(t) < 3: continue
        m = re.search(r"\d+", t[0])
        if not m: continue                                              # ohne Zeilennummer kein Befund
        stufe = t[1].lower()
        if stufe not in ("hoch", "mittel", "tief"): continue            # Format verfehlt -> verwerfen statt raten
        text = t[2]
        if len(text) < 12 or _LOB.search(text) or _KOSMETIK.search(text): continue
        if _UNBENUTZT.search(text):                                     # v144: «wird nicht verwendet» – zählt AURA selbst
            gen = [n for n in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text) if n in namen]
            if any(len(re.findall(rf"\b{re.escape(n)}\b", txt)) > 1 for n in gen): continue
        if re.search(r"\bself\.([A-Za-z_]\w*)", text) and _UNDEF.search(text) or re.search(r"(?i)attributeerror|nicht initialisiert", text):
            attr = set(re.findall(r"self\.([A-Za-z_]\w*)", text))      # v144: self.x «nicht definiert», aber irgendwo zugewiesen
            if attr & set(re.findall(r"self\.([A-Za-z_]\w*)\s*(?:,\s*self\.\w+\s*)*=(?!=)", txt)) or \
               any(re.search(rf"self\.{a}\b[^\n]*=", txt) for a in attr): continue
        if _UNDEF.search(text):                                         # «undefiniert»: jeder genannte Name, der in der Datei
            gen = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text))   # definiert/importiert ist, widerlegt die Behauptung
            if gen & namen or not txt: continue
        key = re.sub(r"\W+", "", text.lower())[:60]
        z = min(max(int(m.group()), a), e)
        if key in gesehen or ("z", z) in gesehen: continue              # v144: höchstens ein Befund je Zeile
        gesehen.update((key, ("z", z)))
        if stufe == "hoch": stufe = "mittel"                            # v144: Stufe «hoch» vergibt nur die Engine
        bef.append({"pfad": rel, "zeile": z, "art": "Modell (ungeprüft)", "stufe": stufe,
                    "text": text[:300], "vorschlag": t[3][:300] if len(t) > 3 else ""})
        if len(bef) >= max_n: break
    return bef

def _definierte_namen(txt):
    n = set(re.findall(r"^\s*(?:def|class)\s+([A-Za-z_]\w*)", txt, re.M))
    n |= set(re.findall(r"^\s*([A-Za-z_]\w*)\s*(?:,\s*[A-Za-z_]\w*\s*)*=", txt, re.M))
    for imp in re.findall(r"^\s*(?:from\s+\S+\s+)?import\s+(.+)$", txt, re.M):
        for teil in imp.strip("()").split(","):
            w = teil.split(" as ")[-1].strip(" ()\\")
            if w: n.add(w.split(".")[0])
    n |= set(re.findall(r"\bself\.([A-Za-z_]\w*)\s*=", txt))
    return n

def ueberspringen(rel, txt, a, e):
    """Abschnitte, die das Sprachmodell nicht prüfen soll: überwiegend String-Daten (Shader, SQL, Prompts) oder nur Kommentare."""
    zeilen = txt.splitlines()[a - 1:e]
    if not zeilen: return "leer"
    if all(not z.strip() or z.strip().startswith(("#", "//")) for z in zeilen): return "nur Kommentare"
    if rel.endswith((".py", ".pyw")):
        try: baum = ast.parse(txt)
        except SyntaxError: return ""
        inner = set()
        for n in ast.walk(baum):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and (n.end_lineno or n.lineno) - n.lineno >= 3:
                inner.update(range(n.lineno, (n.end_lineno or n.lineno) + 1))
        if sum(1 for i in range(a, e + 1) if i in inner) > 0.6 * (e - a + 1): return "überwiegend Text-/Shader-Daten"
    return ""

def code_block(out):
    """Erster ```-Block; ohne Block der ganze Text. Denk-Teil (<think>) wird entfernt."""
    if "</think>" in out: out = out.split("</think>", 1)[1]
    m = re.search(r"```[\w.+-]*\n(.*?)(?:```|\Z)", out, re.S)
    return (m.group(1) if m else out).rstrip("\n")


# ------------------------------------------------------------------ Vorschlag, Diff, Übernehmen
def vorschlag_bauen(root, rel, a, e, neu_abschnitt):
    """Neuer Dateitext + Diff + Prüfungsergebnis. Schreibt NICHTS."""
    alt = lesen(root, rel); zeilen = alt.splitlines(keepends=True)
    nl = "\r\n" if "\r\n" in alt else "\n"
    neu_z = [z + nl for z in neu_abschnitt.split("\n")]
    if a - 1 + (e - a + 1) == len(zeilen) and not alt.endswith(("\n", "\r")): neu_z[-1] = neu_z[-1].rstrip("\r\n")
    neu = "".join(zeilen[:a - 1] + neu_z + zeilen[e:])
    diff = "".join(difflib.unified_diff(alt.splitlines(keepends=True), neu.splitlines(keepends=True),
                                        fromfile=f"a/{rel}", tofile=f"b/{rel}", n=2))
    ok, warum = pruefen(rel, neu)
    return {"pfad": rel, "start": a, "ende": e, "neu": neu, "diff": diff, "ok": ok, "warum": warum,
            "hash_alt": hashlib.sha1(alt.encode("utf-8", "replace")).hexdigest()}

def pruefen(rel, txt):
    if rel.endswith((".py", ".pyw")):
        try: ast.parse(txt); return True, "Python-Syntax geprüft: in Ordnung"
        except SyntaxError as e: return False, f"Syntaxfehler in Zeile {e.lineno}: {e.msg} – wird nicht übernommen"
    if rel.endswith(".json"):
        try: json.loads(txt); return True, "JSON geprüft: in Ordnung"
        except ValueError as e: return False, f"Ungültiges JSON: {e}"
    return True, "Keine automatische Syntaxprüfung für diesen Dateityp – bitte Diff genau ansehen"

def uebernehmen(root, v):
    """Sicherung, dann Schreiben. Abbruch, wenn die Datei seit dem Vorschlag geändert wurde. Rückgabe Sicherungspfad."""
    if not v["ok"]: raise ValueError(v["warum"])
    p = Path(root) / v["pfad"]; alt = _lesen(p)
    if hashlib.sha1(alt.encode("utf-8", "replace")).hexdigest() != v["hash_alt"]:
        raise ValueError("Die Datei wurde seit dem Vorschlag verändert – bitte Abschnitt neu prüfen.")
    ziel = SICHERUNG / time.strftime("%Y%m%d_%H%M%S") / Path(root).name / v["pfad"]
    ziel.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, ziel)
    enc = "utf-8"
    try: p.read_bytes().decode("utf-8")
    except UnicodeDecodeError: enc = "cp1252"
    p.write_bytes(v["neu"].encode(enc, errors="strict"))
    return ziel

def sicherungen(root):
    """Neueste zuerst: [(zeit, datei_in_sicherung, rel)] für dieses Projekt."""
    out, name = [], Path(root).name
    if not SICHERUNG.exists(): return out
    for d in sorted(SICHERUNG.iterdir(), reverse=True):
        b = d / name
        if b.is_dir():
            for f in b.rglob("*"):
                if f.is_file(): out.append((d.name, f, f.relative_to(b).as_posix()))
    return out

def zuruecksetzen(root, sicherung_datei, rel):
    shutil.copy2(sicherung_datei, Path(root) / rel)


# ------------------------------------------------------------------ Bericht
def bericht(root, liste, bef, gi=None):
    BERICHTE.mkdir(parents=True, exist_ok=True)
    p = BERICHTE / f"{Path(root).name}_{time.strftime('%Y%m%d_%H%M')}.md"
    z = [f"# Code-Prüfung: {Path(root).name}", "", f"Ordner: `{root}`  ", f"Stand: {time.strftime('%d.%m.%Y %H:%M')}  ",
         f"Dateien: {len(liste)}, Zeilen: {sum(d['zeilen'] for d in liste)}  "]
    if gi: z.append(f"Git: Zweig `{gi['branch']}`, {gi['geaendert']} ungespeicherte Änderungen  ")
    eng = [b for b in bef if not b["art"].startswith("Modell")]; mod = [b for b in bef if b["art"].startswith("Modell")]
    z += ["", "| Stufe (ohne Sprachmodell) | Anzahl |", "|---|---|"] + \
         [f"| {s} | {sum(b['stufe'] == s for b in eng)} |" for s in ("hoch", "mittel", "tief")]
    if mod: z += ["", f"> {len(mod)} Befunde stammen aus der Zweiten Meinung des Sprachmodells (Abschnitt am Ende). "
                  "Sie sind ungeprüft und erfahrungsgemäss oft falsch – vor jeder Änderung selbst nachprüfen."]
    for s, t in [(s, [b for b in eng if b["stufe"] == s]) for s in ("hoch", "mittel", "tief")] + [("Zweite Meinung (Sprachmodell, ungeprüft)", mod)]:
        if not t: continue
        z += ["", f"## {s[0].upper() + s[1:]}", ""]
        z += [f"- `{b['pfad']}:{b['zeile']}` **{b['art']}** – {b['text']}" + (f" → {b['vorschlag']}" if b.get("vorschlag") else "")
              for b in t]
    p.write_text("\n".join(z) + "\n", encoding="utf-8")
    return p
