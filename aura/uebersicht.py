# aura/uebersicht.py — Startseite «Übersicht» (nächste Termine, letzte Mails) und Tacho «Datenbestand» der Info-Leiste. Version 20261123v299
# v299: Tacho-Segmente proportional zur Objektzahl (bisher logarithmisch); kleine Quellen erhalten ein Mindeststück von 6°.
# v271: Tacho als geglättetes Bild in physischen Pixeln (scharf); Termine und Mails nebeneinander, zweizeilig.
# v276: Ganztägige Termine «morgen» / «Fr 20.11.» statt 00:00; Zeitfelder gleich breit.
# v274: Breite folgt dem verfügbaren Platz; unter 620 px Termine und Mails untereinander.
# v273: Systemmails gebündelt («6× …», aufklappbar), Zeilenzahl nach Fensterhöhe, «–» bei fehlendem Ort, Datum als Seitentitel.
# v270: Neu. Nur Anzeige: liest die Datenbank direkt (eigene kurze Verbindung, nur SELECT), kein Sprachmodell, keine Jobs im Worker.
#       Tacho: Bogen 270°, Segment je Quelle (v299: proportional mit Mindeststück), Mitte = Objekte gesamt.
#       Statuspunkt je Quelle: grün / orange / rot nach Alter des letzten Abgleichs und Anteil Textstücke mit Vektor.
import math, sqlite3, tkinter as tk
from datetime import datetime, timedelta
import customtkinter as ctk
from .config import DB_PATH
from . import log

# Feste Farbe je Quelle (Rot bleibt dem Akzent und Fehlern vorbehalten)
QUELL_FARBE = {"outlook_mail": "#2DD4A4", "outlook_calendar": "#3B82F6", "edge_history": "#F59E0B",
               "folder_docs": "#A3AD9F", "confluence": "#22D3EE", "ims": "#F472B6", "jira": "#818CF8",
               "onenote": "#A78BFA", "memos": "#F0997B"}
GRUEN, ORANGE, ROT, GRAU = "#10B981", "#F59E0B", "#E5484D", ("#C4C8CF", "#4B5260")
TAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember")
NICHT_TERMIN = ("abwesend", "mittag", "ferien", "urlaub", "blocker")   # wie Agent v267: keine echten Termine


def _farbe(col):
    if isinstance(col, (tuple, list)): return col[1] if ctk.get_appearance_mode() == "Dark" else col[0]
    return col


def _zeit(s):
    try: return datetime.fromisoformat((s or "").strip()[:16])
    except Exception: return None


def _gross(s): return s[:1].upper() + s[1:]


# ------------------------------------------------------------------ Statuspunkt
def status(x, jetzt=None):
    """(Farbe, Erklärung) für eine Quelle aus db.stats(): Abgleich-Alter und Vektor-Anteil, das Schlechtere zählt."""
    jetzt = jetzt or datetime.now()
    ch, ve = x.get("chunks", 0) or 0, x.get("vectors", 0) or 0
    anteil = ve / ch if ch else 1.0
    t = _zeit(x.get("last_sync"))
    if t is None: return GRAU, "Noch kein Abgleich bekannt."
    alter = jetzt - t
    stufe, gruende = 0, []
    if alter > timedelta(days=3): stufe = 2; gruende.append(f"letzter Abgleich vor {alter.days} Tagen")
    elif alter > timedelta(hours=24): stufe = 1; gruende.append("letzter Abgleich älter als 24 Stunden")
    if anteil < 0.5: stufe = 2; gruende.append(f"nur {int(anteil * 100)} % der Textstücke mit Vektor")
    elif anteil < 0.95: stufe = max(stufe, 1); gruende.append(f"{int(anteil * 100)} % der Textstücke mit Vektor")
    txt = f"Zuletzt abgeglichen: {t:%d.%m.%Y %H:%M}. " + (_gross("; ".join(gruende)) + "." if gruende else "Aktuell, alle Vektoren berechnet.")
    return (GRUEN, ORANGE, ROT)[stufe], txt


# ------------------------------------------------------------------ Tacho (Info-Leiste rechts)
def anteile(werte, frei, minimum=6.0):
    """v299: Bogenlänge je Quelle proportional zur Objektzahl. Quellen unter dem Mindeststück erhalten «minimum» Grad,
    der Rest wird unter den übrigen proportional verteilt (wiederholt, bis alles passt)."""
    n = len(werte)
    if not n: return []
    if minimum * n >= frei: return [frei / n] * n
    fix, ext = set(), [0.0] * n
    while True:
        rest = frei - minimum * len(fix)
        summe = sum(w for i, w in enumerate(werte) if i not in fix) or 1.0
        neu = {i for i, w in enumerate(werte) if i not in fix and rest * w / summe < minimum}
        if not neu:
            for i, w in enumerate(werte): ext[i] = minimum if i in fix else rest * w / summe
            return ext
        fix |= neu
class Tacho:
    """Bogen 270° als selbst gerechnetes Bild (Kantenglättung, physische Pixel je Windows-Skalierung) auf einem tk.Canvas.
    v271: tk.Canvas zeichnet Bögen ohne Glättung und in logischen Pixeln → unscharf/treppig. Ohne Pillow (DLLs gesperrt)."""
    def __init__(self, parent, bg, ink, muted, leer, size=180):
        self.bg, self.ink, self.muted, self.leer, self.size = bg, ink, muted, leer, size
        self.cv = tk.Canvas(parent, width=size, height=int(size * 0.82), highlightthickness=0, bd=0)
        self._img, self._key = None, None

    @staticmethod
    def _hex(c): c = c.lstrip("#"); return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))

    def _bild(self, W, H, sc, segmente, bg):
        """segmente: [(u0, u1, '#rrggbb')] in Grad entlang des Bogens (0 = links unten, 270 = rechts unten)."""
        b = self._hex(bg); seg = [(u0, u1, self._hex(f)) for u0, u1, f in segmente]
        cx = cy = W / 2.0; ro = W / 2.0 - 14 * sc; ri = ro - 13 * sc
        hb = "#%02x%02x%02x" % b; zeilen = []
        rad = math.pi / 180.0
        for y in range(H):
            dy = cy - (y + 0.5); row = []
            for x in range(W):
                dx = (x + 0.5) - cx; d = math.hypot(dx, dy)
                cr = min(d - ri, ro - d) + 0.5
                if cr <= 0: row.append(hb); continue
                cr = 1.0 if cr > 1 else cr
                u = (225.0 - math.degrees(math.atan2(dy, dx))) % 360.0
                best, col = 0.0, None
                for u0, u1, f in seg:
                    ca = min(u - u0, u1 - u) * rad * d + 0.5
                    if ca > best: best, col = (1.0 if ca > 1 else ca), f
                    if best >= 1.0: break
                a = cr * best
                if col is None or a <= 0: row.append(hb); continue
                row.append("#%02x%02x%02x" % tuple(int(bb + (ff - bb) * a + 0.5) for bb, ff in zip(b, col)))
            zeilen.append("{" + " ".join(row) + "}")
        img = tk.PhotoImage(master=self.cv, width=W, height=H)
        img.put(" ".join(zeilen))
        return img

    def draw(self, st, connectors, total_text, sub_text):
        cv = self.cv
        try:
            try: sc = ctk.ScalingTracker.get_window_scaling(cv.winfo_toplevel()) or 1.0
            except Exception: sc = 1.0
            W, H = round(self.size * sc), round(self.size * 0.82 * sc)
            on = [(c, st[c.id]) for c in connectors if c.id in st and st[c.id].get("items", 0) > 0]
            luecke = 2.5 if len(on) > 1 else 0.0
            frei = 270.0 - luecke * max(0, len(on) - 1)
            exts = anteile([x.get("items", 0) for _, x in on], frei)   # v299: proportional, Mindeststück
            segmente, pos = [], 0.0
            for (c, _), ext in zip(on, exts):
                segmente.append((pos, pos + ext, QUELL_FARBE.get(c.id, "#A3AD9F"))); pos += ext + luecke
            if not segmente: segmente = [(0.0, 270.0, _farbe(self.leer))]
            bg = _farbe(self.bg)
            key = (W, H, bg, tuple((round(a, 1), round(b, 1), f) for a, b, f in segmente))
            if key != self._key:
                self._img, self._key = self._bild(W, H, sc, segmente, bg), key
            cv.delete("all"); cv.configure(bg=bg, width=W, height=H)
            cv.create_image(0, 0, image=self._img, anchor="nw")
            cv.create_text(W / 2, W / 2 - 8 * sc, text=total_text, fill=_farbe(self.ink), font=("Consolas", 17, "bold"))
            cv.create_text(W / 2, W / 2 + 18 * sc, text=sub_text, fill=_farbe(self.muted), font=("Segoe UI", 9), justify="center")
        except Exception: log.get().exception("Tacho")


# ------------------------------------------------------------------ Übersicht (Startseite)
def _abfragen(n_termine=5, n_mails=40):
    """Nächste Termine (ab jetzt) und letzte Mails. Liefert ([(id, ts, titel, ort)], [(id, ts, titel, absender)])."""
    termine, mails = [], []
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=3)
    except Exception: return termine, mails
    try:
        jetzt = datetime.now().isoformat(sep=" ", timespec="minutes")
        heute0 = datetime.now().strftime("%Y-%m-%d 00:00")
        for iid, ts, ti, ort, meta in conn.execute(
                "SELECT id, ts, title, location, meta FROM items WHERE source = 'outlook_calendar' AND ts >= ? ORDER BY ts LIMIT ?",
                (heute0, n_termine * 3)):
            if any(w in (ti or "").lower() for w in NICHT_TERMIN): continue
            gt = _ganztags(ts, meta)
            if not gt and ts < jetzt: continue                           # vorbei; Ganztägiges von heute bleibt
            termine.append((iid, ("G" if gt else "") + ts, ti or "(ohne Titel)", ort or ""))
            if len(termine) >= n_termine: break
        mails = [(iid, ts, ti or "(ohne Betreff)", au or "") for iid, ts, ti, au in conn.execute(
            "SELECT id, ts, title, author FROM items WHERE source = 'outlook_mail' AND ts <> '' ORDER BY ts DESC LIMIT ?",
            (n_mails,))]
    except Exception: log.get().exception("Übersicht lesen")
    finally: conn.close()
    return termine, mails


def _ganztags(ts, meta):
    """v276: Beginn 00:00 und Dauer in ganzen Tagen (Outlook speichert Ganztägiges so)."""
    try:
        import json
        a, e = _zeit(ts), _zeit((json.loads(meta or "{}") or {}).get("end"))
        if not a or not e or (a.hour, a.minute) != (0, 0): return False
        d = (e - a).total_seconds(); return d >= 86400 and d % 86400 == 0
    except Exception: return False


def _kurzzeit(ts, termin):
    gt = ts.startswith("G") if ts else False
    if gt:
        t = _zeit(ts[1:]); heute = datetime.now().date()
        if t is None: return "ganztags"
        if t.date() == heute: return "heute"
        if t.date() == heute + timedelta(days=1): return "morgen"
        return f"{TAGE[t.weekday()][:2]} {t:%d.%m.}"
    t = _zeit(ts)
    if t is None: return "–"
    heute = datetime.now().date()
    if t.date() == heute: return f"{t:%H:%M}"
    if termin:
        if t.date() == heute + timedelta(days=1): return f"morgen {t:%H:%M}"
        if t.date() < heute + timedelta(days=7): return f"{TAGE[t.weekday()][:2]} {t:%H:%M}"
        return f"{t:%d.%m.}"
    if t.date() == heute - timedelta(days=1): return "gestern"
    return f"{t:%d.%m.}"


def _kurz(t, n): t = " ".join((t or "").split()); return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def _betreff(t):
    """Präfixe wie «AW:», «WG:», «RE:», «FW:» weglassen – sie fressen in schmalen Spalten den Platz."""
    import re
    return re.sub(r"^((AW|WG|RE|FW|FWD|Antw|Fwd)\s*:\s*)+", "", (t or "").strip(), flags=re.I) or t


def _absender(a):
    a = (a or "").strip()
    return a[:-len(" ARMASUISSE")] if a.upper().endswith(" ARMASUISSE") else a


def _ort(o):
    o = (o or "").strip()
    return "Teams" if "teams" in o.lower() else o


def datum_lang(d=None):
    d = d or datetime.now(); return f"{TAGE[d.weekday()]}, {d.day}. {MONATE[d.month - 1]} {d.year}"


def datum_kurz(d=None):
    d = d or datetime.now(); return f"{TAGE[d.weekday()][:2]}, {d.day}. {MONATE[d.month - 1]}"


def _buendeln(mails, n, offen):
    """Gleicher Absender + gleicher Betreffanfang (Systemmeldungen, z.B. Acta Nova) → eine Zeile «5× …», per Klick aufklappbar.
    Reihenfolge nach der neusten Mail je Bündel; höchstens n sichtbare Zeilen."""
    gruppen, folge = {}, []
    for iid, ts, ti, au in mails:
        b = _betreff(ti)
        k = ((au or "").strip().lower(), " ".join(b.lower().split())[:24])
        if k not in gruppen: gruppen[k] = []; folge.append(k)
        gruppen[k].append((iid, ts, b, _absender(au)))
    zeilen = []
    for k in folge:
        g = gruppen[k]; iid, ts, b, au = g[0]
        if len(g) == 1: zeilen.append((iid, _kurzzeit(ts, False), b, au or "–", None))
        else:
            schl = "|".join(k); auf = schl in offen
            import os
            gem = os.path.commonprefix([x[2] for x in g]); gem = gem[:gem.rfind(" ") + 1] if " " in gem else gem
            zeilen.append((iid, _kurzzeit(ts, False), f"{'▾' if auf else '▸'} {len(g)}× {(gem.strip() or b)}", au or "–", ("kopf", schl)))
            if auf: zeilen += [(i, _kurzzeit(t, False), "… " + (bb[len(gem):] or bb), a or "–", ("kind", schl)) for i, t, bb, a in g[:8]]
        if sum(1 for z in zeilen if not (z[4] and z[4][0] == "kind")) >= n: break   # Aufgeklapptes verdrängt nichts
    return zeilen


class Uebersicht:
    """Zwei Karten (Termine, Mails) mit runden Ecken; Klick öffnet das Original in Outlook."""
    def __init__(self, app, parent, breite=640):
        from . import gui as G
        self.G, self.app, self.breite = G, app, breite
        self.offen = set()                                                # aufgeklappte Bündel (Schlüssel)
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.grid_columnconfigure((0, 1), weight=1, uniform="ueb")
        self._warte = None
        self.frame.bind("<Configure>", self._groesse, add="+")             # v274: Breite folgt dem Platz (Info-Leiste ein/aus)
        self.draw()

    def _groesse(self, e):
        try:
            sc = ctk.ScalingTracker.get_widget_scaling(self.frame) or 1.0
            b = int(min(1200, e.width / sc))
        except Exception: return
        if b < 200 or abs(b - self.breite) < 40: return
        self.breite = b
        if self._warte: self.frame.after_cancel(self._warte)
        self._warte = self.frame.after(120, self.draw)

    @property
    def einspaltig(self): return self.breite < 620

    def alive(self):
        try: return self.frame.winfo_exists()
        except Exception: return False

    def _anzahl(self):
        """Zeilen je Karte nach verfügbarer Höhe (Fenster minus Kopf und Eingabe), 5 bis 12."""
        try:
            sc = ctk.ScalingTracker.get_window_scaling(self.frame.winfo_toplevel()) or 1.0
            h = self.app.root.winfo_height() / sc - 380
            return max(5, min(12, int(h // 42)))
        except Exception: return 5

    def draw(self):
        if not self.alive(): return
        for c in self.frame.winfo_children(): c.destroy()
        n = self._anzahl()
        termine, mails = _abfragen(n_termine=n)
        self._karte(0, "Nächste Termine", [(i, _kurzzeit(ts, True), ti, _ort(ort) or "–", None) for i, ts, ti, ort in termine],
                    "Keine anstehenden Termine – oder der Outlook-Kalender ist nicht verbunden (Wissen › Quellen).")
        self._karte(1, "Letzte Mails", _buendeln(mails, n, self.offen),
                    "Keine Mails – oder die Outlook-Mails sind nicht verbunden (Wissen › Quellen).")

    def _karte(self, spalte, titel, zeilen, leer):
        G = self.G; eins = self.einspaltig; bk = self.breite if eins else (self.breite - 12) // 2
        self.frame.grid_columnconfigure(1, weight=0 if eins else 1, uniform="" if eins else "ueb")
        k = ctk.CTkFrame(self.frame, fg_color=G.BUBBLE, corner_radius=12, border_width=1, border_color=G.BORDER)
        if eins: k.grid(row=1 + spalte, column=0, columnspan=2, sticky="nsew", pady=(0, 12))
        else: k.grid(row=1, column=spalte, sticky="nsew", padx=(0, 12) if spalte == 0 else (0, 0))
        k.grid_columnconfigure(0, weight=1)
        kopf = ctk.CTkFrame(k, fg_color="transparent"); kopf.grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))
        ctk.CTkLabel(kopf, text="●", font=G.font(11), text_color=G.ACCENT, width=12).pack(side="left")
        ctk.CTkLabel(kopf, text=" " + titel, font=G.font(12, "bold"), text_color=G.INK).pack(side="left")
        if not zeilen:
            ctk.CTkLabel(k, text=leer, font=G.font(11), text_color=G.MUTED, anchor="w", justify="left",
                         wraplength=bk - 30).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 12))
            return
        zeichen = max(18, min(110, (bk - 135) // 8))                                # Titel kürzen statt umbrechen
        for r, (iid, zeit, ti, neben, bund) in enumerate(zeilen, start=1):
            z = ctk.CTkFrame(k, fg_color="transparent", corner_radius=8, cursor="hand2")
            z.grid(row=r, column=0, sticky="ew", padx=8, pady=(1, 10 if r == len(zeilen) else 1)); z.grid_columnconfigure(1, weight=1)
            pill = ctk.CTkLabel(z, text=zeit, font=("Consolas", 11), text_color=G.INK, fg_color=G.CARD, corner_radius=8,
                                width=100, height=22)
            pill.grid(row=0, column=0, rowspan=2, padx=(6, 10), pady=4, sticky="n")
            t = ctk.CTkLabel(z, text=_kurz(ti, zeichen), font=G.font(12), text_color=G.INK, anchor="w", height=18)
            t.grid(row=0, column=1, sticky="w", pady=(3, 0))
            n = ctk.CTkLabel(z, text=_kurz(neben, zeichen + 6), font=G.font(10), text_color=G.MUTED, anchor="w", height=14)
            n.grid(row=1, column=1, sticky="w", pady=(0, 3))
            if bund and bund[0] == "kind": pill.configure(fg_color="transparent", text_color=G.MUTED)
            for w in (z, pill, t, n):
                if bund and bund[0] == "kopf": w.bind("<Button-1>", lambda e, k=bund[1]: self._umschalten(k))
                else: w.bind("<Button-1>", lambda e, i=iid: self._oeffnen(i))
                w.bind("<Enter>", lambda e, f=z: f.configure(fg_color=G.CARD))
                w.bind("<Leave>", lambda e, f=z: f.configure(fg_color="transparent"))

    def _umschalten(self, k):
        self.offen.symmetric_difference_update({k}); self.draw()

    def _oeffnen(self, iid):
        from .opener import open_item
        open_item(iid, lambda msg: self.app.w.events.put(("progress", (msg, None, None))))
