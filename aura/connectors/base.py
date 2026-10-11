# aura/connectors/base.py — Steckplatz fuer Datenquellen.
# Neue Quelle = neue Klasse mit id/label + available() + sync(ctx), dann in __init__.py eintragen.

class SyncContext:
    def __init__(self, known, settings, progress, cancelled):
        self.known = known            # set der bereits gespeicherten ext_ids -> ueberspringen
        self.settings = settings      # dict aus data\settings.json
        self.progress = progress      # progress(text, done=None, total=None)
        self.cancelled = cancelled    # Funktion -> True, wenn der Nutzer abbricht

class Connector:
    id = "base"
    label = "Basis"
    hint = ""                         # kurzer Hilfetext fuer die Oberflaeche

    def available(self):
        """(True, "") oder (False, Grund) - wird vor dem Sync geprueft."""
        return True, ""

    def sync(self, ctx):
        """Liefert Dicts: ext_id, title, author, recipients, ts, location, body, meta,
        optional 'text' (bereits bereinigter Text fuer die Stuecke) und 'prefix'."""
        return iter(())

def outlook_namespace():
    """Verbindung zu Outlook. COM muss in JEDEM Thread initialisiert werden (Worker-Thread!)."""
    import comtypes, comtypes.client as cc
    try: comtypes.CoInitialize()
    except OSError: pass
    try: app = cc.GetActiveObject("Outlook.Application", dynamic=True)
    except Exception: app = cc.CreateObject("Outlook.Application", dynamic=True)
    return app.GetNamespace("MAPI")

def outlook_available():
    try:
        import comtypes  # noqa: F401
    except Exception as e:
        return False, f"comtypes fehlt ({e}) - Ordner vendor\\comtypes pruefen"
    return True, ""

def iso(v):
    try: return v.isoformat(sep=" ", timespec="minutes") if v and v.year > 1990 else ""
    except Exception: return ""
