# aura/workflow/expr.py — Ausdruecke in Workflows: {{ pfad.zum.wert }} und kleine Funktionen. Version 20261009v40 (v39: belegt(), v40: Formularfragen kein Beleg)
# Bewusst KEIN eval(): nur Pfade, Text-/Zahl-Literale und Funktionen aus FUNCS.
#   {{ txt.text }}                      -> Wert aus einem frueheren Schritt
#   {{ contains(js.empfehlung, 'einladungsverfahren', 'art. 20') }}
#   {{ box(not(empty(input.files))) }}
import html, json, re
from datetime import datetime

class ExprError(ValueError): pass

def _text(v):
    if v is None: return ""
    if isinstance(v, (dict, list)): return json.dumps(v, ensure_ascii=False, indent=1)
    if isinstance(v, bool): return "ja" if v else "nein"
    return str(v)

def _truthy(v):
    if isinstance(v, str): return v.strip().lower() not in ("", "0", "false", "nein", "none")
    return bool(v)

def num(v):
    """'CHF 180'000.-' / '1.2 Mio' / '180 000' / 180000 -> 180000.0; nichts erkennbar -> None."""
    if isinstance(v, (int, float)) and not isinstance(v, bool): return float(v)
    t = _text(v).lower().replace("\u2019", "'").replace("\u00a0", " ")
    m = re.search(r"\d{1,3}(?:['’ ]\d{3})+(?:[.,]\d+)?|\d{1,3}(?:\.\d{3})+(?!\d)|\d+(?:[.,]\d+)?", t)
    if not m: return None
    s = m.group(0)
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s): s = s.replace(".", "")
    s = re.sub(r"['’ ]", "", s).replace(",", ".")
    x = float(s); rest = t[m.end():m.end() + 8]
    if re.match(r"\s*(mio|million)", rest): x *= 1e6
    elif re.match(r"\s*(mrd|milliard)", rest): x *= 1e9
    elif re.match(r"\s*(tsd|k\b|tausend)", rest): x *= 1e3
    return x

def _cmp(a, b, op):
    a, b = num(a), num(b)
    return False if a is None or b is None else op(a, b)

def chf(v):
    x = num(v)
    return "" if x is None else f"{x:,.0f}".replace(",", "'")

_ZQ = str.maketrans({"\u00ad": "", "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u00ab": '"', "\u00bb": '"',
                     "\u2013": "-", "\u2014": "-", "\u00a0": " ", "\u00df": "ss"})

def _norm(t):
    """Fuer Belegvergleich: klein, Silbentrennung am Zeilenende aufheben, Anfuehrungszeichen/Leerraum vereinheitlichen."""
    t = _text(t).translate(_ZQ).lower()
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)          # «Beschaf-\nfung» -> «beschaffung»
    t = re.sub(r"[\"'`]", "", t)
    return re.sub(r"\s+", " ", t).strip()

def belegt(zitat, *texte, mindest=20):
    """True, wenn das Zitat (sinngemaess woertlich) in einem der Texte steht. Auslassungen «…»/«...» erlaubt:
    jeder Teil (>= 8 Zeichen) muss vorkommen, zusammen mindestens `mindest` Zeichen. Keine Angabe -> False."""
    z = _norm(zitat).rstrip(" .;,-")
    if z.endswith((":", "?")): return False                      # Formularfrage/Ueberschrift, kein Beleg
    z = z.strip(" .:;,-")
    if not z or z.startswith(("keine angabe", "keiner", "keine", "unklar")): return False
    teile = [x.strip(" .:;,-") for x in re.split(r"\.\.\.|\u2026|\[\.\.\.\]", z)]
    teile = [x for x in teile if len(x) >= 8]
    if sum(len(x) for x in teile) < int(mindest): return False
    hay = " ".join(_norm(t) for t in texte if t)
    return all(x in hay for x in teile)

FUNCS = {
    "belegt":   belegt,
    "contains": lambda text, *terms: any(str(t).lower() in _text(text).lower() for t in terms),
    "not":      lambda v: not _truthy(v),
    "and":      lambda *v: all(_truthy(x) for x in v),
    "or":       lambda *v: any(_truthy(x) for x in v),
    "eq":       lambda a, b: _text(a).strip().lower() == _text(b).strip().lower(),
    "empty":    lambda v: not _truthy(v),
    "default":  lambda v, d: v if _truthy(v) else d,
    "box":      lambda v: "☒" if _truthy(v) else "☐",
    "num":      num,
    "chf":      chf,
    "ge":       lambda a, b: _cmp(a, b, lambda x, y: x >= y),
    "gt":       lambda a, b: _cmp(a, b, lambda x, y: x > y),
    "le":       lambda a, b: _cmp(a, b, lambda x, y: x <= y),
    "lt":       lambda a, b: _cmp(a, b, lambda x, y: x < y),
    "isin":     lambda v, *opts: _text(v).strip().lower() in [str(o).lower() for o in opts],
    "iif":      lambda c, a, b="": a if _truthy(c) else b,
    "yesno":    lambda v: "☒ Ja ☐ Nein" if _truthy(v) else "☐ Ja ☒ Nein",
    "lower":    lambda v: _text(v).lower(),
    "upper":    lambda v: _text(v).upper(),
    "len":      lambda v: len(v) if v is not None else 0,
    "join":     lambda v, sep=", ": sep.join(_text(x) for x in (v or [])),
    "pluck":    lambda v, key: [x.get(key) if isinstance(x, dict) else None for x in (v or [])],
    "truncate": lambda v, n: _text(v)[:int(n)],
    "today":    lambda fmt="%d.%m.%Y": datetime.now().strftime(fmt),
    "json":     lambda v: json.dumps(v, ensure_ascii=False, indent=1),
}

_TOK = re.compile(r"\s*(?:(?P<s>'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")|(?P<n>-?\d+(?:\.\d+)?)"
                  r"|(?P<id>[A-Za-z_À-ſ][\w.\-]*)|(?P<op>[(),]))")

def _tokens(src):
    out, pos = [], 0
    src = src.strip()
    while pos < len(src):
        m = _TOK.match(src, pos)
        if not m or m.end() == pos: raise ExprError(f"Unverstaendlicher Ausdruck bei «{src[pos:pos + 20]}» in «{src}»")
        kind = m.lastgroup; val = m.group(kind); pos = m.end()
        out.append((kind, val))
        while pos < len(src) and src[pos].isspace(): pos += 1
    return out

def lookup(path, state):
    """a.b.0.c -> state['a']['b'][0]['c']; fehlende Teile -> None (kein Fehler)."""
    cur = state
    for p in path.split("."):
        if isinstance(cur, dict): cur = cur.get(p)
        elif isinstance(cur, (list, tuple)) and p.lstrip("-").isdigit():
            i = int(p); cur = cur[i] if -len(cur) <= i < len(cur) else None
        else: return None
        if cur is None: return None
    return cur

def evaluate(src, state):
    toks = _tokens(src); pos = 0
    def parse():
        nonlocal pos
        if pos >= len(toks): raise ExprError(f"Ausdruck unvollstaendig: «{src}»")
        kind, val = toks[pos]; pos += 1
        if kind == "s":
            return re.sub(r"\\(.)", lambda e: {"n": "\n", "t": "\t"}.get(e.group(1), e.group(1)), val[1:-1])
        if kind == "n": return float(val) if "." in val else int(val)
        if kind == "id":
            if pos < len(toks) and toks[pos] == ("op", "("):
                fn = FUNCS.get(val)
                if fn is None: raise ExprError(f"Unbekannte Funktion {val}() - erlaubt: {', '.join(sorted(FUNCS))}")
                pos += 1; args = []
                if toks[pos:pos + 1] == [("op", ")")]: pos += 1; return fn()
                while True:
                    args.append(parse())
                    if pos >= len(toks): raise ExprError(f"Klammer fehlt: «{src}»")
                    sep = toks[pos][1]; pos += 1
                    if sep == ")": break
                    if sep != ",": raise ExprError(f"Erwartet , oder ) in «{src}»")
                return fn(*args)
            low = val.lower()
            if low in ("true", "ja"): return True
            if low in ("false", "nein"): return False
            if low in ("none", "null"): return None
            return lookup(val, state)
        raise ExprError(f"Unerwartet «{val}» in «{src}»")
    v = parse()
    if pos != len(toks): raise ExprError(f"Zu viel im Ausdruck: «{src}»")
    return v

_TPL = re.compile(r"\{\{((?:(?!\}\}).)*)\}\}", re.S)       # Inhalt ohne «}}» (sonst fasst fullmatch mehrere Ausdruecke zusammen)

def render(text, state, escape=None):
    """Ersetzt {{...}}. Besteht der Text NUR aus einem Ausdruck, kommt der Rohwert zurueck (Liste, Dict, ...).
    Eingesetzte Werte werden nicht nochmals ausgewertet (Dokumenttext mit {{ ist harmlos)."""
    if not isinstance(text, str) or "{{" not in text: return text
    m = _TPL.fullmatch(text.strip())
    if m and escape is None: return evaluate(m.group(1), state)
    return _TPL.sub(lambda m: (escape or (lambda x: x))(_text(evaluate(m.group(1), state))), text)

def resolve(obj, state, skip=()):
    if isinstance(obj, str): return render(obj, state)
    if isinstance(obj, list): return [resolve(x, state) for x in obj]
    if isinstance(obj, dict): return {k: (v if k in skip else resolve(v, state)) for k, v in obj.items()}
    return obj

def html_escape(s): return html.escape(s, quote=False).replace("\r\n", "\n").replace("\n", "<br>")
truthy = _truthy
as_text = _text
