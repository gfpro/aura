# Registrierte Datenquellen (Reihenfolge = Anzeige in der Oberflaeche)
from .outlook_mail import OutlookMail
from .outlook_calendar import OutlookCalendar
from .edge_history import EdgeHistory
from .folder_docs import FolderDocs

CONNECTORS = [OutlookMail(), OutlookCalendar(), EdgeHistory(), FolderDocs()]
BY_ID = {c.id: c for c in CONNECTORS}
