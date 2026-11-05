# aura/connectors/outlook_mail.py — Mail-Ordner des Hauptpostfachs (klassisches Outlook, nur lesen).
# v23: Ordnerauswahl (settings["mail_folders"] = {EntryID: true/false}); neue Unterordner erben vom Elternordner.
#      Beim Sync werden alle EntryIDs der gewaehlten Ordner gesammelt (ctx.seen) -> Worker loescht Verschwundenes.
# v112: Anhaenge (pdf/docx/txt/md, bis anhang_max_mb) als Text: it["anhaenge"] = [(name, text)]; anhang_texte() auch fuer Nachtrag.
# v73: zusaetzlich «zitat» = zitierter Verlauf (der Worker behaelt daraus nur Neues).
from .base import Connector, outlook_namespace, outlook_available, iso, empfaenger
from ..text import split_mail

SKIP_DEFAULT = (3, 4, 16, 20, 23)   # Geloescht, Postausgang, Entwuerfe, Sync-Probleme, Junk
SKIP_NAMES = {"aufgezeichnete unterhaltungen", "conversation history", "suchordner", "search folders",
              "rss-feeds", "rss feeds", "synchronisierungsprobleme", "sync issues"}
ENCRYPTED = -2146893792             # 0x80090020
ANH_EXT = (".pdf", ".docx", ".txt", ".md")

def anhang_texte(it, settings, progress=lambda *a: None):
    """v112: Text der Datei-Anhaenge einer Mail. Nur olByValue (1), erlaubte Endungen, bis anhang_max_mb.
    Speichert kurz in %TEMP%\\aura_anh und loescht danach."""
    if not settings.get("mail_anhaenge", True): return []
    import os, re, tempfile
    from pathlib import Path
    from ..workflow.nodes import read_file
    try: att = it.Attachments; n = att.Count
    except Exception: return []
    if not n: return []
    maxb = float(settings.get("anhang_max_mb", 5)) * 1e6; maxc = int(settings.get("anhang_max_zeichen", 60000))
    d = Path(tempfile.gettempdir()) / "aura_anh"; d.mkdir(exist_ok=True); out = []
    for i in range(1, n + 1):
        try:
            a = att.Item(i); name = a.FileName or ""
            if a.Type != 1 or not name.lower().endswith(ANH_EXT) or (a.Size or 0) > maxb: continue
            f = d / re.sub(r'[\\/:*?"<>|]', "_", name)
            a.SaveAsFile(str(f))
            try: txt = re.sub(r"\n{3,}", "\n\n", read_file(str(f))).strip()[:maxc]
            finally:
                try: os.remove(f)
                except OSError: pass
            if len(txt) >= 50: out.append((name, txt))
        except Exception as e: progress(f"Anhang uebersprungen: {e}")
    return out

def list_folders(ns, progress=lambda *a: None, counts=True):
    """Alle Mail-Ordner des Hauptpostfachs als Liste (Baumreihenfolge):
    {eid, name, path, depth, parent, count, default_on}. Liest keine einzelne Mail."""
    skip = set()
    for n in SKIP_DEFAULT:
        try: skip.add(ns.GetDefaultFolder(n).EntryID)
        except Exception: pass
    out = []
    def walk(f, path, depth, parent):
        try:
            name = f.Name or ""; eid = f.EntryID
            p = f"{path}/{name}" if path else name
            off = eid in skip or name.strip().lower() in SKIP_NAMES
            me = parent
            if f.DefaultItemType == 0:
                cnt = -1
                if counts:
                    try: cnt = f.Items.Count
                    except Exception: pass
                out.append({"eid": eid, "name": name, "path": p, "depth": depth, "parent": parent,
                            "count": cnt, "default_on": not off})
                me = eid
            subs = f.Folders
            for i in range(1, subs.Count + 1): walk(subs.Item(i), p, depth + 1, me)
        except Exception as e:
            progress(f"Ordner nicht lesbar ({path}): {e}"); out.append({"error": str(e), "path": path})
    walk(ns.GetDefaultFolder(6).Parent, "", 0, None)
    return out

def resolve(folders, choice):
    """{eid: bool}. Reihenfolge: explizite Wahl > Standard-aus (Geloescht, Junk ...) > erbt vom Elternordner > ein."""
    state = {}
    for f in folders:
        if "eid" not in f: continue
        e = f["eid"]
        if e in choice: state[e] = bool(choice[e])
        elif not f["default_on"]: state[e] = False
        elif f["parent"] in state: state[e] = state[f["parent"]]
        else: state[e] = True
    return state

class OutlookMail(Connector):
    id, label = "outlook_mail", "Outlook-Mails"
    hint = "Gewählte Ordner des Hauptpostfachs, nur neue Mails werden nachgeladen."

    def available(self): return outlook_available()

    def sync(self, ctx):
        ns = outlook_namespace()
        folders = list_folders(ns, ctx.progress, counts=False)
        state = resolve(folders, ctx.settings.get("mail_folders") or {})
        seen = set(); errors = any("error" in f for f in folders)
        for f in folders:
            if "eid" not in f or not state.get(f["eid"]): continue
            fname, short = f["path"], f["name"]
            try:
                folder = ns.GetFolderFromID(f["eid"])
                table, todo = folder.GetTable(), []
                while not table.EndOfTable:
                    row = table.GetNextRow(); eid = row.Item("EntryID"); seen.add(eid)
                    if eid not in ctx.known and str(row.Item("MessageClass") or "").startswith("IPM.Note"): todo.append(eid)
            except Exception as e:
                errors = True; ctx.progress(f"Ordner uebersprungen ({fname}): {e}"); continue
            for k, eid in enumerate(todo):
                if ctx.cancelled(): return                           # unvollstaendig -> kein Aufraeumen
                if k % 25 == 0: ctx.progress(f"{short}: {k}/{len(todo)}", k, len(todo))
                try:
                    it = ns.GetItemFromID(eid)
                    subj, body = it.Subject or "", it.Body or ""
                    try:
                        addr = it.Sender.GetExchangeUser().PrimarySmtpAddress if it.SenderEmailType == "EX" else it.SenderEmailAddress
                    except Exception: addr = ""
                    ts = iso(it.ReceivedTime) or iso(it.SentOn) or iso(it.CreationTime)
                    own, zit = split_mail(body, subj)
                    anh = anhang_texte(it, ctx.settings, ctx.progress)                     # v112
                    emp = empfaenger(it)                                                   # v203
                    yield {"anhaenge": anh, "ext_id": eid, "title": subj, "author": it.SenderName or "",
                           "recipients": "; ".join(x for x in (it.To or "", it.CC or "") if x), "ts": ts,
                           "body": body, "text": own, "zitat": zit,
                           "meta": {"folder": fname, "folder_id": f["eid"], "sender_addr": addr or "",
                                    "conversation_id": getattr(it, "ConversationID", "") or "",
                                    "to": emp[1], "cc": emp[2]}}
                except Exception as e:
                    if getattr(e, "args", None) and e.args[0] == ENCRYPTED: continue   # verschluesselt
                    ctx.progress(f"Mail uebersprungen: {e}")
            if ctx.cancelled(): return
        try: ctx.seen = seen; ctx.complete = not errors and bool(seen)
        except AttributeError: pass                                  # aeltere SyncContext: kein Aufraeumen
