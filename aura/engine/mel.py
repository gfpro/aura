# aura/engine/mel.py — Version 20261104v175  (AURA)
# Whisper-Vorverarbeitung in reinem Python (ohne numpy): WAV lesen, 16 kHz mono, Log-Mel-Spektrogramm.
import cmath, math, wave
from array import array

SR, NFFT, HOP, FRAMES = 16000, 400, 160, 3000

def read_wav(path):
    """WAV (8/16 Bit) -> Liste von Floats -1..1, mono, 16 kHz."""
    with wave.open(str(path), "rb") as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw == 2: a = array("h"); a.frombytes(raw); s = [v / 32768.0 for v in a]
    elif sw == 1: s = [(v - 128) / 128.0 for v in raw]
    else: raise ValueError(f"WAV mit {sw * 8} Bit wird nicht unterstuetzt")
    if ch > 1: s = [sum(s[i:i + ch]) / ch for i in range(0, len(s) - ch + 1, ch)]
    if sr != SR:                                                      # lineare Umrechnung genuegt fuer Sprache
        k = sr / SR; m = int(len(s) / k); o = []
        for i in range(m):
            p = i * k; j = int(p); f = p - j
            o.append(s[j] * (1 - f) + s[min(j + 1, len(s) - 1)] * f)
        s = o
    return s

_TW = {}
def _fft(x):
    n = len(x)
    if n == 1: return x
    p = 2 if n % 2 == 0 else 5
    parts = [_fft(x[r::p]) for r in range(p)]
    tw = _TW.get(n)
    if tw is None: tw = _TW[n] = [cmath.exp(-2j * math.pi * k / n) for k in range(n)]
    m = n // p
    if p == 2:
        a, b = parts; o = [0j] * n
        for k in range(m):
            t = tw[k] * b[k]; o[k] = a[k] + t; o[k + m] = a[k] - t
        return o
    return [sum(parts[r][k % m] * tw[(r * k) % n] for r in range(p)) for k in range(n)]

def _hz2mel(f):
    if f < 1000: return 3 * f / 200
    return 15 + 27 * math.log(f / 1000) / math.log(6.4)
def _mel2hz(m):
    if m < 15: return 200 * m / 3
    return 1000 * 6.4 ** ((m - 15) / 27)

def filters(n_mels):
    """Slaney-Mel-Filter: je Mel-Band Liste (bin, gewicht), nur Werte != 0."""
    lo, hi = _hz2mel(0.0), _hz2mel(8000.0)
    pts = [_mel2hz(lo + (hi - lo) * i / (n_mels + 1)) for i in range(n_mels + 2)]
    fq = [i * SR / NFFT for i in range(NFFT // 2 + 1)]; out = []
    for m in range(n_mels):
        l, c, r = pts[m:m + 3]; e = 2 / (r - l); row = []
        for i, f in enumerate(fq):
            v = min((f - l) / (c - l), (r - f) / (r - c))
            if v > 0: row.append((i, v * e))
        out.append(row)
    return out

def log_mel(s, n_mels=80, progress=None):
    """-> (Liste von FRAMES Zeilen zu n_mels Floats, Anzahl echter Frames). Max. 30 s."""
    s = list(s[:SR * 30]); fb = filters(n_mels); h = NFFT // 2
    win = [0.5 - 0.5 * math.cos(2 * math.pi * i / NFFT) for i in range(NFFT)]
    n = min(len(s) // HOP, FRAMES)
    pad = s[h:0:-1] + s + (s[-2:-h - 2:-1] if len(s) >= FRAMES * HOP else [0.0] * (FRAMES * HOP - len(s)) + [0.0] * h)
    rows = []
    for t in range(n + (1 if n < FRAMES else 0)):                     # eine Zeile mehr: Stille fuer den Rest
        fr = pad[t * HOP:t * HOP + NFFT]
        sp = _fft([complex(a * b) for a, b in zip(fr, win)])
        pw = [c.real * c.real + c.imag * c.imag for c in sp[:h + 1]]
        rows.append([math.log10(max(sum(pw[i] * w for i, w in r), 1e-10)) for r in fb])
        if progress and t % 200 == 0: progress(t, n)
    # Stille-Zeile am Ende steht fuer alle restlichen Frames (Nullen -> Boden)
    tail = rows.pop() if n < FRAMES else None
    mx = max((max(r) for r in rows), default=-10.0); fl = mx - 8.0
    out = [[(max(v, fl) + 4) / 4 for v in r] for r in rows]
    if n < FRAMES:
        out.append([(max(v, fl) + 4) / 4 for v in tail])              # Uebergang zur Stille
        out += [[(fl + 4) / 4] * n_mels for _ in range(FRAMES - n - 1)]
    return out, n
