# Registrierte Datenquellen (Reihenfolge = Anzeige in der Oberflaeche)
from .outlook_mail import OutlookMail
from .outlook_calendar import OutlookCalendar
from .edge_history import EdgeHistory
from .folder_docs import FolderDocs
from .confluence import Confluence

CONNECTORS = [OutlookMail(), OutlookCalendar(), EdgeHistory(), FolderDocs(), Confluence()]
BY_ID = {c.id: c for c in CONNECTORS}
