# aura/engine/aktualitaet.py — Version 20261117v268
# Gemeinsame Aktualitäts-Gewichtung der Live-Quellen (Acta Nova, Intranet, SharePoint).
# Immer: kleiner Bonus für Neueres (halbiert pro Jahr). Fragt jemand nach «neuste/aktuell/zuletzt …»: starker Bonus
# (halbiert alle 90 Tage). Datum = «geändert am», sonst «erstellt am».
import re
from datetime import datetime

def datum(v):
    """'17.11.2026', '17.11.2026 14:05', '2026-11-17T…', 'Aktualisiert am 3.2.2025' -> datetime, sonst None."""
    if not v: return None
    if isinstance(v, datetime): return v.replace(tzinfo=None)
    v = str(v)
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", v)
    if m:
        try: return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError: return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", v)
    if m:
        try: return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError: return None
    return None

def bonus(d, chrono, stark, mild, jetzt=None):
    """Punkte für die Aktualität. stark = Höchstwert bei chrono (Halbwertszeit 90 Tage), mild = sonst (365 Tage)."""
    if not d: return 0.0
    tage = max(0, ((jetzt or datetime.now()) - d).days)
    return stark * 0.5 ** (tage / 90) if chrono else mild * 0.5 ** (tage / 365)

def stand(geaendert=None, erstellt=None):
    """Text für Quelle und Anzeige: 'geändert 12.11.2026, erstellt 03.02.2025' (nur vorhandene Angaben)."""
    t = [f"geändert {geaendert:%d.%m.%Y}" if geaendert else "", f"erstellt {erstellt:%d.%m.%Y}" if erstellt else ""]
    return ", ".join(x for x in t if x)
