# aura/text.py — Text aufbereiten und in Stuecke teilen (aus mail_import v03 uebernommen).
import re

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
