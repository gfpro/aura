# aura/connectors/outlook_calendar.py — Termine (inkl. Serien) in einem Zeitfenster.
from datetime import datetime, timedelta
from .base import Connector, outlook_namespace, outlook_available, iso
from ..text import clean

class OutlookCalendar(Connector):
    id, label = "outlook_calendar", "Outlook-Kalender"
    hint = "Termine im Zeitfenster (Einstellungen: calendar_past_days / calendar_future_days)."

    def available(self): return outlook_available()

    def _items(self, cal, start, end, ctx):
        items = cal.Items; items.Sort("[Start]"); items.IncludeRecurrences = True
        # Restrict erwartet Datumsformate gemaess Windows-Regionaleinstellung -> mehrere Formate probieren.
        for fmt in ("%d.%m.%Y %H:%M", "%m/%d/%Y %I:%M %p"):
            try:
                r = items.Restrict(f"[Start] >= '{start.strftime(fmt)}' AND [Start] <= '{end.strftime(fmt)}'")
                first = r.GetFirst()
                if first is not None: return r, first
            except Exception: pass
        ctx.progress("Kalenderfilter nicht moeglich - durchlaufe alle Termine (langsamer)")
        return items, items.GetFirst()

    def sync(self, ctx):
        ns = outlook_namespace(); now = datetime.now()
        start = now - timedelta(days=int(ctx.settings.get("calendar_past_days", 365)))
        end = now + timedelta(days=int(ctx.settings.get("calendar_future_days", 180)))
        coll, it = self._items(ns.GetDefaultFolder(9), start, end, ctx); n = 0
        seen = getattr(ctx, "seen", None)                          # v18: fuer das Entfernen abgesagter Termine
        try: ctx.window_end = end.strftime("%Y-%m-%d %H:%M"); ctx.had_errors = False
        except AttributeError: seen = None
        while it is not None:
            if ctx.cancelled(): return
            try:
                st = it.Start
                if st.replace(tzinfo=None) > end: break
                if st.replace(tzinfo=None) >= start:
                    ext = f"{it.EntryID}|{iso(st)}"               # Serien teilen die EntryID -> Startzeit dazu
                    if seen is not None: seen.add(ext)
                    if ext not in ctx.known:
                        subj = it.Subject or ""; loc = it.Location or ""
                        who = "; ".join(x for x in (it.RequiredAttendees or "", it.OptionalAttendees or "") if x)
                        text = (f"Termin: {subj}\nWann: {iso(st)} bis {iso(it.End)}\nOrt: {loc}\n"
                                f"Organisator: {it.Organizer or ''}\nTeilnehmende: {who}\n\n{clean(it.Body or '')}")
                        yield {"ext_id": ext, "title": subj, "author": it.Organizer or "", "recipients": who,
                               "ts": iso(st), "location": loc, "body": it.Body or "", "text": text,
                               "meta": {"end": iso(it.End), "recurring": bool(it.IsRecurring)}}
                n += 1
                if n % 50 == 0: ctx.progress(f"Kalender: {n} Termine geprueft")
            except Exception as e:
                ctx.progress(f"Termin uebersprungen: {e}")
                if seen is not None: ctx.had_errors = True
            it = coll.GetNext()
        if seen is not None: ctx.complete = not ctx.had_errors    # nur bei fehlerfreiem Durchlauf aufraeumen
