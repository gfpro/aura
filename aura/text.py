# aura/text.py — Text aufbereiten und in Stuecke teilen (aus mail_import v03 uebernommen). Version 20261012v73
# v73: split_mail() liefert zusaetzlich den zitierten Verlauf; verlauf_neu() behaelt daraus nur Absaetze, die noch in
#      keiner anderen Mail stehen (Pruefsumme je Absatz, Tabelle para_hash).
import hashlib, re

CHUNK_TARGET, CHUNK_HARD, CHUNK_MIN = 500, 750, 15

_RX_QUOTE = re.compile(
    r'^\s*(?:-{2,}\s*(?:Original Message|Urspr\u00fcngliche Nachricht|Message d\'origine|Messaggio originale)\s*-{2,}'
    r'|(?:Von|From|De|Da)\s*:.*\n(?:.*\n){0,3}?\s*(?:Gesendet|Sent|Envoy\u00e9|Inviato|Date|Datum)\s*:)', re.M | re.I)
_RX_FWD = re.compile(r'^\s*(WG|FW|FWD|TR|I)\s*:', re.I)
_RX_HDRBLOCK = re.compile(
    r'^\s*(?:Von|From|De|Da)\s*:\s*(?P<who>[^\n<\[]*)[^\n]*\n'
    r'(?:[^\n]*\n){0,1}?\s*(?:Gesendet|Sent|Envoy\u00e9|Inviato|Date|Datum)\s*:\s*(?P<when>[^\n]*)\n'
    r'(?:\s*(?:An|To|\u00c0|A|Cc|Betreff|Subject|Objet|Oggetto|Wichtigkeit|Importance)\s*:[^\n]*\n)*', re.M | re.I)
_RX_NOISE = re.compile(r'<mailto:[^>]*>|<https?://[^>]*>|\[cid:[^\]]*\]', re.I)

def clean_mail(body, subject=""):
    """Zitate in Antworten abschneiden; bei Weiterleitungen Kopfbloecke zu einer Zeile verdichten."""
    body = _RX_NOISE.sub("", (body or "").replace("\r\n", "\n").replace("\r", "\n"))
    if not _RX_FWD.match(subject or ""):
        m = _RX_QUOTE.search(body)
        if m and m.start() > 40: body = body[:m.start()]
    body = _RX_HDRBLOCK.sub(lambda m: "\n\n-- weitergeleitet/zitiert: %s, %s --\n\n"
                            % (m.group("who").strip(" \"'"), m.group("when").strip()), body)
    return clean(body)

def clean(text):
    text = re.sub(r'[ \t\u00a0]+', ' ', (text or "").replace("\r\n", "\n").replace("\r", "\n"))
    return re.sub(r'\n{3,}', '\n\n', text).strip()

def make_chunks(text, prefix=""):
    """Absatzweise auf ~500 Zeichen buendeln (max. 750); jedes Stueck bekommt den Praefix."""
    parts = []
    for para in re.split(r'\n\s*\n', text or ""):
        para = " ".join(para.split())
        while len(para) > CHUNK_HARD:
            cut = para.rfind(" ", 0, CHUNK_HARD); cut = cut if cut > 0 else CHUNK_HARD
            parts.append(para[:cut]); para = para[cut:].strip()
        if para: parts.append(para)
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) + 1 > CHUNK_HARD: out.append(cur); cur = ""
        cur = (cur + " " + p).strip()
        if len(cur) >= CHUNK_TARGET: out.append(cur); cur = ""
    if cur: out.append(cur)
    return [prefix + c for c in out if len(c) >= CHUNK_MIN]


# ----------------------------------------------------------------------------- v73: zitierter Verlauf
PARA_MIN = 40                      # kuerzere Absaetze (Gruss, Anrede) werden nicht verglichen
_RX_SECTION = re.compile(r"(?=^-- (?:weitergeleitet/)?zitiert: )", re.M)

def split_mail(body, subject=""):
    """(eigener Text wie clean_mail, zitierter Verlauf). Weiterleitungen: alles ist eigener Text, Verlauf leer."""
    own = clean_mail(body, subject)
    if _RX_FWD.match(subject or ""): return own, ""
    b = _RX_NOISE.sub("", (body or "").replace("\r\n", "\n").replace("\r", "\n"))
    m = _RX_QUOTE.search(b)
    if not m or m.start() <= 40: return own, ""
    q = _RX_HDRBLOCK.sub(lambda m: "\n\n-- zitiert: %s, %s --\n\n" % (m.group("who").strip(" \"'"), m.group("when").strip()), b[m.start():])
    return own, clean(q)

def para_hash(p):
    """Pruefsumme eines Absatzes (Kleinschreibung, nur Wortzeichen) oder None, wenn zu kurz."""
    n = " ".join(re.sub(r"[\W_]+", " ", p.lower()).split())
    return hashlib.sha1(n.encode("utf-8")).hexdigest()[:16] if len(n) >= PARA_MIN else None

def paragraphs(text):
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", text or "") if p.strip()]

def own_hashes(text):
    return {h for h in map(para_hash, paragraphs(text)) if h}

def verlauf_neu(quoted, known):
    """Behaelt aus dem Verlauf nur Absaetze, deren Pruefsumme nicht in known (Funktion: set -> bekannte) liegt.
    Ein Abschnitt (eine zitierte Mail) bleibt nur, wenn mindestens ein laengerer Absatz neu ist; dann mit Kopfzeile
    und kurzen Absaetzen. Rueckgabe: (Text, neue Pruefsummen)."""
    out, new = [], set()
    for sec in _RX_SECTION.split(quoted or ""):
        ps = paragraphs(sec)
        if not ps: continue
        hs = [None if _RX_SECTION.match(p) else para_hash(p) for p in ps]     # Kopfzeile zaehlt nicht
        kn = known({h for h in hs if h}) | new
        keep = [p for p, h in zip(ps, hs) if h is None or h not in kn]
        if not any(h and h not in kn for h in hs): continue
        out.append("\n\n".join(keep)); new |= {h for h in hs if h and h not in kn}
    return "\n\n".join(out), new
