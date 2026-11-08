# aura/ed25519.py — Ed25519 (RFC 8032) in reinem Python, nur Standardbibliothek. Version 20261108v208
# Zweck: Signaturprüfung von Update-Paketen ohne Zusatzpaket. Nicht zeitkonstant – für das PRÜFEN öffentlicher Daten
# unkritisch; SIGNIEREN nur auf dem Release-Rechner (tools/patch_signieren.py), nie im Client mit geheimem Schlüssel.
import hashlib

p = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
d = -121665 * pow(121666, p - 2, p) % p
_I = pow(2, (p - 1) // 4, p)

def _h(m): return int.from_bytes(hashlib.sha512(m).digest(), "little")

def _add(P, Q):
    X1, Y1, Z1, T1 = P; X2, Y2, Z2, T2 = Q
    A = (Y1 - X1) * (Y2 - X2) % p; B = (Y1 + X1) * (Y2 + X2) % p
    C = 2 * T1 * T2 * d % p; D = 2 * Z1 * Z2 % p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % p, G * H % p, F * G % p, E * H % p)

def _mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1: Q = _add(Q, P)
        P = _add(P, P); s >>= 1
    return Q

def _eq(P, Q):
    return (P[0] * Q[2] - Q[0] * P[2]) % p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % p == 0

def _xrec(y, sign):
    if y >= p: return None
    x2 = (y * y - 1) * pow(d * y * y + 1, p - 2, p) % p
    if x2 == 0: return None if sign else 0
    x = pow(x2, (p + 3) // 8, p)
    if (x * x - x2) % p: x = x * _I % p
    if (x * x - x2) % p: return None
    if (x & 1) != sign: x = p - x
    return x

_gy = 4 * pow(5, p - 2, p) % p
_gx = _xrec(_gy, 0)
G = (_gx, _gy, 1, _gx * _gy % p)

def _enc(P):
    zi = pow(P[2], p - 2, p); x = P[0] * zi % p; y = P[1] * zi % p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")

def _dec(s):
    if len(s) != 32: return None
    y = int.from_bytes(s, "little"); sign = y >> 255; y &= (1 << 255) - 1
    x = _xrec(y, sign)
    return None if x is None else (x, y, 1, x * y % p)

def _expand(sk):
    if len(sk) != 32: raise ValueError("Geheimer Schlüssel muss 32 Byte haben")
    h = hashlib.sha512(sk).digest(); a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8; a |= 1 << 254
    return a, h[32:]

def public_key(sk):
    return _enc(_mul(_expand(sk)[0], G))

def sign(sk, msg):
    a, prefix = _expand(sk); A = _enc(_mul(a, G))
    r = _h(prefix + msg) % L; R = _enc(_mul(r, G))
    s = (r + _h(R + A + msg) * a) % L
    return R + int.to_bytes(s, 32, "little")

def verify(pk, msg, sig):
    """True nur bei gültiger Signatur. Wirft nie."""
    try:
        if len(pk) != 32 or len(sig) != 64: return False
        A = _dec(pk); R = _dec(sig[:32])
        if A is None or R is None: return False
        s = int.from_bytes(sig[32:], "little")
        if s >= L: return False
        k = _h(sig[:32] + pk + msg) % L
        return _eq(_mul(s, G), _add(R, _mul(k, A)))
    except Exception:
        return False
