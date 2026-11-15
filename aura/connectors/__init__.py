# Registrierte Datenquellen (Reihenfolge = Anzeige in der Oberflaeche)
from .outlook_mail import OutlookMail
from .outlook_calendar import OutlookCalendar
from .edge_history import EdgeHistory
from .folder_docs import FolderDocs
from .confluence import Confluence
from .onenote import OneNote
from .jira import Jira
from .ims import Ims

CONNECTORS = [OutlookMail(), OutlookCalendar(), EdgeHistory(), FolderDocs(), Confluence(), Ims(), Jira(), OneNote()]
BY_ID = {c.id: c for c in CONNECTORS}
