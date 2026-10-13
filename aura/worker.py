# aura/worker.py — EIN Hintergrund-Thread fuer alles Schwere (Outlook, GPU, Suche).
# DirectX 11 und Outlook-COM vertragen keinen parallelen Zugriff aus mehreren Threads.
# Die Oberflaeche schickt Auftraege (jobs) und liest Ereignisse (events).
# v23: Ordnerauswahl Mails, Loeschen verschwundener Mails, automatischer Abgleich (job_autosync).
# v25: Workflows (job_workflows = Liste, job_workflow = ausfuehren).
# v28: Wissenssammlungen (data\\wissen.db): job_wissen_sync, im Chat zuschaltbar (Einstellung wissen_chat).
# v49: Auto-Abgleich wird verworfen, solange ein Workflow laeuft oder wartet (verfaelschte Laufzeiten).
# v65: Folgefragen (Gespraechsgedaechtnis ueber die letzten 3 Fragen).
# v67: Folgefrage nur per Knopf «Bezug zur letzten Frage» (follow=True); Worterkennung nur mit followup_auto.
# v36: Workflow-Pakete, Neustart ab Schritt (job_workflow start_at).
# v73: zitierter Mailverlauf wird durchsucht (nur Absaetze, die in keiner anderen Mail stehen); einmalige Nachbearbeitung
#      aller Mails (job_verlauf, startet automatisch); Mails geplanter Workflows (Betreff = Workflow-Name) ausgeschlossen.
import ctypes, json, queue, re, threading, time, traceback
from array import array
from . import db, listmode, log
from .config import MODELS, load_settings
from .connectors import BY_ID
from .connectors.base import SyncContext
from .engine.embedder import Embedder
from .llm import discover
from .rag import Retriever
from .text import clean, clean_mail, make_chunks, own_hashes, split_mail, verlauf_neu

# v65: Folgefrage = kurz (<= 6 Woerter) und mit Rueckbezug, oder beginnt mit «und/und was/mehr dazu ...»
FOLLOW_REF = re.compile(r"\b(dazu|davon|dafür|dafuer|dagegen|damit|darin|daran|darum|dahinter|hierzu|hierfür|dies|darüber|darueber|danach|davor|dabei|darauf|dort|deren|dessen|diese[nrms]?|jene[nrms]?|"
                        r"er|sie|ihm|ihn|ihr|ihre[nrms]?|ihnen|das|es)\b", re.I)
FOLLOW_START = re.compile(r"^\s*(und|aber|also|mehr|genauer|warum|wieso|weshalb|seit wann|bis wann|und was|was noch)\b", re.I)
CHRONO = re.compile(r"\b(ablauf|verlauf|chronolog\w*|der reihe nach|von anfang an|wie hat sich|entwicklung)\b", re.I)
DEADLINE = re.compile(r"\b(frist\w*|deadline|bis wann|sp[äa]testens|f[äa]llig\w*|eingabeschluss|termin f[üu]r)\b", re.I)

def keep_awake(on):
    """ES_CONTINUOUS|ES_SYSTEM_REQUIRED: kein Standby wegen Inaktivitaet. Zugeklappter Deckel,
    Startmenue->Energie oder eine IT-Richtlinie koennen das trotzdem uebersteuern."""
    try: return ctypes.windll.kernel32.SetThreadExecutionState(0x80000001 if on else 0x80000000)
    except Exception: return 0

class Worker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.jobs, self.events = queue.Queue(), queue.Queue()
        self.cancel = threading.Event()
        self.embedder = None; self.retriever = Retriever(); self.backends = {}
        self.pending = None; self.auto_runs = 0                      # v23
        self.chat = None                                              # v65: {'qs': [...], 'hits': [...], 't': Zeit}

    # ---- Schnittstelle fuer die Oberflaeche
    def submit(self, name, *args):
        if name == "autosync":                                          # v49: nie waehrend/vor einem Workflow, nie doppelt
            wartend = [n for n, _ in list(self.jobs.queue)]
            if getattr(self, "current", None) in ("workflow", "autosync") or "workflow" in wartend or "autosync" in wartend:
                log.get().info(f"Auto-Abgleich uebersprungen (laeuft: {getattr(self, 'current', None)}, wartend: {wartend})")
                return
        self.cancel.clear(); self.jobs.put((name, args))
    def emit(self, kind, *data): self.events.put((kind, data))

    def run(self):
        try:
            import comtypes; comtypes.CoInitialize()
        except Exception: pass
        self.conn = db.connect()
        self.emit("stats", db.stats(self.conn))
        if not db.flag(self.conn, "verlauf_v73") and self.conn.execute("SELECT 1 FROM items WHERE source='outlook_mail' LIMIT 1").fetchone():
            self.jobs.put(("verlauf", ()))                              # v73: einmalig, vor allen anderen Auftraegen
        while True:
            name, args = self.jobs.get(); self.current = name
            self.emit("busy", True, name)
            t0 = time.perf_counter(); log.get().info(f"Job {name} gestartet")
            try:
                getattr(self, "job_" + name)(*args)
                log.get().info(f"Job {name} fertig in {time.perf_counter() - t0:.1f} s")
            except Exception as e:
                log.get().exception(f"Job {name} fehlgeschlagen")
                self.emit("error", f"{type(e).__name__}: {e}", traceback.format_exc())
            finally:
                self.current = None; self.emit("busy", False, name); self.emit("stats", db.stats(self.conn))

    def progress(self, text, done=None, total=None): self.emit("progress", text, done, total)

    def _embedder(self):
        s = load_settings()
        if self.embedder is None: self.embedder = Embedder(MODELS / s["embed_model"])
        return self.embedder

    # ---- Auftraege
    def _stop(self, auto):
        """Abbruch: Pause-Knopf, oder (nur Auto-Abgleich) wenn ein Auftrag der Oberflaeche wartet."""
        return (lambda: self.cancel.is_set() or not self.jobs.empty()) if auto else self.cancel.is_set

    def job_sync(self, cid, confirm=False, auto=False):
        """confirm=True: jedes Loeschen erst bestaetigen (nach Ordner-Abwahl). Rueckgabe: Anzahl neue Objekte."""
        con = BY_ID[cid]; ok, why = con.available()
        if not ok: raise RuntimeError(why)
        stop = self._stop(auto)
        ctx = SyncContext(db.known_ids(self.conn, cid), load_settings(), self.progress, stop)
        try: ctx.seen = set()                                        # v18: vom Connector gesehene IDs (Kalender)
        except AttributeError: pass
        n = upd = 0; t0 = time.perf_counter()
        skip = self._mail_ausschluss() if cid == "outlook_mail" else set()   # v73
        for it in con.sync(ctx):
            if it.get("update"):                                     # v21: bekanntes Objekt, nur Zeit/Meta nachfuehren
                upd += self.conn.execute("UPDATE items SET ts = ?, meta = ? WHERE source = ? AND ext_id = ?",
                                         (it["ts"], json.dumps(it.get("meta") or {}, ensure_ascii=False), cid,
                                          it["ext_id"])).rowcount
                continue
            if skip and (it.get("title") or "").strip().lower() in skip: continue
            text = it.get("text") or clean(it.get("body", ""))
            prefix = it["prefix"] if "prefix" in it else f"{it.get('title', '')} ({it.get('author', '')}, {it.get('ts', '')[:10]}): "
            zit = []
            if cid == "outlook_mail":                                   # v73: Verlauf, nur Neues
                own = own_hashes(text); db.hashes_add(self.conn, own)
                if it.get("zitat"):
                    kept, new = verlauf_neu(it["zitat"], lambda hs: db.hashes_known(self.conn, hs))
                    db.hashes_add(self.conn, new); zit = make_chunks(kept, self._vprefix(it)) if kept else []
            if db.add_item(self.conn, cid, it, make_chunks(text, prefix), zit): n += 1
            if n and n % 200 == 0: self.conn.commit()
        removed = 0
        if cid == "outlook_calendar" and getattr(ctx, "seen", None) and not self.cancel.is_set() \
                and getattr(ctx, "complete", False) and getattr(ctx, "window_end", None):
            from datetime import datetime
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            gone = [i for i, e in self.conn.execute("SELECT id, ext_id FROM items WHERE source = 'outlook_calendar' "
                                                    "AND ts >= ? AND ts <= ?", (now, ctx.window_end)) if e not in ctx.seen]
            fut = self.conn.execute("SELECT COUNT(*) FROM items WHERE source = 'outlook_calendar' AND ts >= ?", (now,)).fetchone()[0]
            if len(gone) > max(10, fut * 0.3):                       # Sicherung: kein Massenloeschen bei Filterproblemen
                self.progress(f"Kalender: {len(gone)} kuenftige Termine nicht mehr gesehen - nicht geloescht (zu viele)")
            else:
                for i in gone: self.conn.execute("DELETE FROM items WHERE id = ?", (i,))
                removed = len(gone)
        ask = 0
        if cid == "outlook_mail" and getattr(ctx, "complete", False) and not stop():
            removed, ask = self._mail_cleanup(ctx.seen, confirm)
        self.conn.commit()
        if n or upd or removed:                                      # v23: nur bei Aenderungen neu aufbauen
            db.rebuild_fts(self.conn); self.retriever.invalidate()
        info = f"{n} neu" + (f", {upd} aktualisiert" if upd else "") + (f", {removed} entfernt" if removed else "") \
            + (f", {ask} zu entfernen (Bestaetigung offen)" if ask else "") + f" in {time.perf_counter() - t0:.0f} s" \
            + (" (abgebrochen)" if stop() else "")
        db.set_sync(self.conn, cid, info); self.progress(f"{con.label}: {info}")
        return n

    # ---- v73: zitierter Verlauf
    @staticmethod
    def _vprefix(it):
        return f"{it.get('title', '')} ({it.get('author', '')}, {(it.get('ts') or '')[:10]}) – zitierter Verlauf: "

    def _mail_ausschluss(self):
        """Betreffe, die AURA selbst erzeugt: Namen geplanter Workflows + Einstellung mail_ausschluss (Liste)."""
        out = {str(x).strip().lower() for x in (load_settings().get("mail_ausschluss") or []) if str(x).strip()}
        try:
            from .zeitplan import mit_zeitplan
            from .workflow.app import WF_DIR
            out |= {w["name"].strip().lower() for w in mit_zeitplan(WF_DIR) if w.get("name")}
        except Exception as e: log.get().warning(f"Ausschluss Workflow-Mails: {e}")
        return out

    def job_verlauf(self):
        """v73, einmalig: fuer alle eingelesenen Mails den zitierten Verlauf nachtragen (nur Absaetze, die in keiner
        anderen Mail stehen). Bestehende Stuecke und Vektoren bleiben. Abbrechbar; ein Neustart macht weiter."""
        c, t0 = self.conn, time.perf_counter()
        skip = self._mail_ausschluss()
        if skip:
            ids = [i for i, t in c.execute("SELECT id, title FROM items WHERE source='outlook_mail'") if (t or "").strip().lower() in skip]
            if ids: self._delete(ids); self.progress(f"Verlauf: {len(ids)} von AURA erzeugte Mails entfernt")
        rows = c.execute("SELECT id, title, author, ts, body FROM items WHERE source='outlook_mail' ORDER BY ts").fetchall()
        for k, (iid, ti, au, ts, body) in enumerate(rows):                # 1) eigene Texte aller Mails registrieren
            db.hashes_add(c, own_hashes(clean_mail(body, ti)))
            if k % 500 == 0: self.progress(f"Verlauf: eigene Texte {k}/{len(rows)}", k, len(rows)); c.commit()
        c.commit(); added = mails = 0
        for k, (iid, ti, au, ts, body) in enumerate(rows):                # 2) Verlauf, nur Neues
            if self.cancel.is_set(): break
            if k % 200 == 0: self.progress(f"Verlauf: Mails {k}/{len(rows)} · {added} neue Textstücke", k, len(rows)); c.commit()
            if c.execute("SELECT 1 FROM chunks WHERE item_id = ? AND zitat = 1 LIMIT 1", (iid,)).fetchone(): continue
            _, q = split_mail(body, ti)
            if not q: continue
            kept, new = verlauf_neu(q, lambda hs: db.hashes_known(c, hs))
            db.hashes_add(c, new)
            if not kept: continue
            ch = make_chunks(kept, self._vprefix({"title": ti, "author": au, "ts": ts}))
            o = c.execute("SELECT COALESCE(MAX(ord), -1) + 1 FROM chunks WHERE item_id = ?", (iid,)).fetchone()[0]
            c.executemany("INSERT INTO chunks(item_id, ord, text, zitat) VALUES(?,?,?,1)", [(iid, o + j, t) for j, t in enumerate(ch)])
            added += len(ch); mails += 1
        c.commit(); db.rebuild_fts(c); self.retriever.invalidate()
        done = not self.cancel.is_set()
        if done: db.flag(c, "verlauf_v73", time.strftime("%Y-%m-%d %H:%M"))
        log.get().info(f"Verlauf: {added} Stuecke aus {mails} Mails in {time.perf_counter() - t0:.0f} s, fertig={done}")
        self.progress(f"Verlauf: {added} neue Textstücke aus {mails} Mails" + (" – jetzt «Vektoren berechnen»" if added and done else "")
                      + ("" if done else " (unterbrochen, wird beim nächsten Start fortgesetzt)"))

    # ---- v23: Mails loeschen, die in keinem gewaehlten Ordner mehr liegen (abgewaehlt, verschoben, geloescht)
    def _mail_cleanup(self, seen, confirm):
        rows = self.conn.execute("SELECT id, ext_id FROM items WHERE source = 'outlook_mail'").fetchall()
        gone = [i for i, e in rows if e not in seen]
        if not gone: return 0, 0
        s = load_settings()
        limit = max(int(s.get("delete_confirm_n", 200)), int(len(rows) * float(s.get("delete_confirm_pct", 0.05))))
        if confirm or len(gone) > limit:                             # Sicherung gegen Massenloeschen
            ch = self._count_chunks(gone)
            self.pending = gone
            self.emit("confirm_delete", len(gone), ch, "nach Ordner-Abwahl" if confirm else "ungewoehnlich viele")
            return 0, len(gone)
        self._delete(gone); return len(gone), 0

    def _count_chunks(self, ids):
        n = 0
        for k in range(0, len(ids), 500):
            part = ids[k:k + 500]
            n += self.conn.execute(f"SELECT COUNT(*) FROM chunks WHERE item_id IN ({','.join('?' * len(part))})", part).fetchone()[0]
        return n

    def _delete(self, ids):
        for k in range(0, len(ids), 500):
            part = ids[k:k + 500]
            self.conn.execute(f"DELETE FROM items WHERE id IN ({','.join('?' * len(part))})", part)   # chunks per CASCADE
        self.conn.commit()

    def job_delete_source(self, cid):
        """v37: alle Objekte einer Quelle entfernen (z.B. Dokumentordner abgewaehlt). Dateien/Outlook bleiben unberuehrt."""
        ids = [r[0] for r in self.conn.execute("SELECT id FROM items WHERE source = ?", (cid,))]
        self.progress(f"Entferne {len(ids)} Objekte ({cid}) ...")
        if ids: self._delete(ids)
        self.conn.execute("DELETE FROM sync_state WHERE source = ?", (cid,)); self.conn.commit()
        db.rebuild_fts(self.conn); self.retriever.invalidate()
        self.progress("Datenbank wird verkleinert (VACUUM) ..."); self.conn.execute("VACUUM")
        self.progress(f"{len(ids)} Objekte entfernt ({cid})")

    def job_delete_pending(self):
        ids, self.pending = self.pending or [], None
        if not ids: return
        self.progress(f"Loesche {len(ids)} Mails ...")
        self._delete(ids); db.rebuild_fts(self.conn); self.retriever.invalidate()
        self.progress("Datenbank wird verkleinert (VACUUM) ...")
        self.conn.execute("VACUUM")
        db.set_sync(self.conn, "outlook_mail", f"{len(ids)} entfernt (bestaetigt)")
        self.progress(f"{len(ids)} Mails entfernt, Datenbank verkleinert")

    def job_folders(self):
        from .connectors.base import outlook_namespace
        from .connectors.outlook_mail import list_folders, resolve
        self.progress("Lese Outlook-Ordnerstruktur ...")
        t0 = time.perf_counter(); fl = list_folders(outlook_namespace(), self.progress)
        st = resolve(fl, load_settings().get("mail_folders") or {})
        for f in fl:
            if "eid" in f: f["on"] = st[f["eid"]]
        self.emit("folders", fl)
        self.progress(f"{sum('eid' in f for f in fl)} Ordner gelesen in {time.perf_counter() - t0:.1f} s")

    def job_autosync(self):
        """Alle autosync_min Minuten (von der Oberflaeche ausgeloest): neue Mails, ab und zu Kalender, dann nur die neuen
        Textstuecke einbetten. Weicht sofort, wenn die Oberflaeche einen Auftrag schickt. Fehler nur als Statuszeile."""
        s = load_settings(); self.auto_runs += 1
        first = self.conn.execute("SELECT COALESCE(MAX(id), 0) FROM chunks").fetchone()[0]
        cids = ["outlook_mail"]
        every = max(1, int(s.get("autosync_calendar_every", 4)))
        if self.conn.execute("SELECT 1 FROM items WHERE source='outlook_calendar' LIMIT 1").fetchone() \
                and (self.auto_runs - 1) % every == 0: cids.append("outlook_calendar")
        new = 0
        for cid in cids:
            try: new += self.job_sync(cid, auto=True) or 0
            except Exception as e:
                log.get().warning(f"Auto-Abgleich {cid}: {e}"); self.progress(f"Auto-Abgleich {cid} fehlgeschlagen: {e}")
            if not self.jobs.empty(): break
        if new and s.get("autosync_embed", True) and self.jobs.empty():
            try: self.job_embed(min_chunk=first, auto=True)
            except Exception as e: log.get().warning(f"Auto-Einbetten: {e}")
        self.emit("autosync_done", time.strftime("%H:%M"), new)

    def job_embed(self, min_chunk=None, auto=False):
        """min_chunk (v23): nur Textstuecke mit id > min_chunk (= im Auto-Abgleich neu dazugekommen)."""
        emb = self._embedder(); ok, why = emb.available()
        if not ok: raise RuntimeError(why)
        stop = self._stop(auto)
        todo = self.conn.execute("SELECT c.id, c.text FROM chunks c JOIN items i ON i.id = c.item_id "
                                 "WHERE c.vec IS NULL AND c.id > ? ORDER BY i.ts DESC", (min_chunk or 0,)).fetchall()
        if not todo: self.progress("Alle Textstuecke haben bereits einen Vektor."); return
        self.progress("Lade Embedding-Modell ..."); emb.load()
        total = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]; have = total - len(todo)
        if not keep_awake(True): self.progress("Hinweis: Standby-Schutz konnte nicht gesetzt werden")
        t0 = time.perf_counter(); n = 0; resets = emb.resets
        try:
            for cid, text in todo:
                if stop(): break
                self.conn.execute("UPDATE chunks SET vec = ? WHERE id = ?", (array("f", emb.passage(text)).tobytes(), cid))
                n += 1
                if emb.resets > resets:
                    resets = emb.resets; self.progress(f"GPU war weg (z.B. Standby) und wurde neu geladen: {emb.last_reset}")
                if n % 25 == 0:
                    keep_awake(True)                              # Leerlauf-Zaehler regelmaessig zuruecksetzen
                    self.conn.commit(); el = time.perf_counter() - t0; rest = el / n * (len(todo) - n)
                    done = have + n; fmt = lambda v: f"{v:,}".replace(",", "'")
                    self.progress(f"Vektoren: {fmt(done)} von {fmt(total)} ({done * 100 // total} %) | Rest ~{int(rest // 3600)}h{int(rest % 3600 // 60):02d}m",
                                  done, total)
        finally:
            self.conn.commit(); keep_awake(False); self.retriever.invalidate()
        self.progress(f"Vektoren: {n} berechnet" + (" (pausiert)" if stop() else ""))

    def _llm(self, backend_id):
        """Liefert das (geladene) Sprachmodell; nur eines ist gleichzeitig im GPU-Speicher."""
        cur = getattr(self, "llm", None)
        if cur and cur[0] != backend_id: cur[1].unload(); self.llm = cur = None
        if not cur:
            fac = dict((i, f) for i, _, f in discover(MODELS)).get(backend_id)
            if fac is None: raise RuntimeError(f"Sprachmodell {backend_id} nicht gefunden")
            self.llm = cur = (backend_id, fac())
        be = cur[1]; be.progress = self.progress
        if not be.loaded():
            self.emit("llm_state", "loading", "wird geladen ..."); be.load()
        return be

    def _llm_state(self):
        cur = getattr(self, "llm", None)
        if cur and cur[0] != "extractive" and cur[1].loaded():
            self.emit("llm_state", "ready", f"bereit · geladen in {getattr(cur[1], 'load_s', 0):.0f} s")
        elif cur and cur[0] == "extractive": self.emit("llm_state", "none", "kein Laden noetig")
        else: self.emit("llm_state", "off", "nicht geladen")

    def job_load_llm(self, backend_id):
        try:
            self._llm(backend_id)
            emb = self._embedder()
            if emb.available()[0]:
                self.progress("Bereite Suche vor (Embedding-Modell, Vektoren) ...")
                emb.query("Vorbereitung")                       # laedt e5 auf die GPU
                self.retriever.vector(self.conn, [0.0] * 1024, n=1)   # laedt alle Vektoren in den Speicher
                self.progress("Bereit")
        finally: self._llm_state()

    def job_unload_llm(self):
        cur = getattr(self, "llm", None)
        if cur: cur[1].unload(); self.llm = None
        self.progress("Sprachmodell entladen - GPU-Speicher freigegeben"); self._llm_state()

    @staticmethod
    def _drop_weak(hits, mode, s):
        """Schwache Treffer nicht ans Modell: nur im Hybrid-Modus, relativ zum besten RRF-Wert.
        Treffer in beiden Listen ~0,033, Platz 1 in nur einer Liste ~0,016 (= Haelfte, bleibt drin)."""
        rel = float(s.get("min_rel_score", 0.5))
        if mode != "hybrid" or rel <= 0 or len(hits) <= 2 or "score" not in hits[0]: return hits
        top = max(h["score"] for h in hits)
        keep = [h for i, h in enumerate(hits) if i < 2 or h["score"] >= rel * top]
        return keep

    def _add_neighbours(self, hits, n):
        """Frist-Fragen: Folgestueck (und Vorgaenger) derselben Mail anhaengen - die Frist steht oft im Nachbarstueck."""
        for h in hits[:n]:
            cid = h.get("chunk_id")
            if not cid: continue
            r = self.conn.execute("SELECT item_id, ord FROM chunks WHERE id = ?", (cid,)).fetchone()
            if not r: continue
            nb = dict(self.conn.execute("SELECT ord, text FROM chunks WHERE item_id = ? AND ord IN (?, ?)",
                                        (r[0], r[1] - 1, r[1] + 1)).fetchall())
            if nb: h["text"] = " … ".join(x for x in (nb.get(r[1] - 1), h["text"], nb.get(r[1] + 1)) if x)

    def _add_newer_in_thread(self, hits, max_add=2):
        """Frist-Fragen: neuere Mails desselben Verlaufs (conversation_id) dazuholen - dort wird oft verschoben."""
        have = {h["item_id"] for h in hits}; add = []
        for h in list(hits):
            if h.get("source") != "outlook_mail": continue
            r = self.conn.execute("SELECT json_extract(meta, '$.conversation_id') FROM items WHERE id = ?",
                                  (h["item_id"],)).fetchone()
            if not r or not r[0]: continue
            for iid, title, ts, author in self.conn.execute(
                    "SELECT id, title, ts, author FROM items WHERE source = 'outlook_mail' AND ts > ? "
                    "AND json_extract(meta, '$.conversation_id') = ? ORDER BY ts DESC LIMIT 3", (h["ts"], r[0])):
                if iid in have: continue
                c = self.conn.execute("SELECT id, text FROM chunks WHERE item_id = ? ORDER BY "
                                      "(text LIKE '%spätestens%' OR text LIKE '%bis zum%' OR text LIKE '%Frist%' "
                                      "OR text LIKE '%verschoben%' OR text LIKE '%bis am%') DESC, ord LIMIT 1", (iid,)).fetchone()
                if not c: continue
                have.add(iid)
                add.append({"chunk_id": c[0], "text": c[1], "item_id": iid, "source": "outlook_mail", "title": title or "",
                            "ts": ts or "", "author": author or "", "score": h.get("score", 0)})
        add.sort(key=lambda h: h["ts"], reverse=True)
        hits[:0] = add[:max_add]                                     # vorne: werden sicher ans Modell gegeben

    def _followup(self, question, s, follow=None):
        """Bisherige Fragen (max. 3) oder []. v67: follow=True (Knopf) = immer, False = nie,
        None = Worterkennung nur wenn followup_auto (Standard aus) und letzte Antwort frisch."""
        c = self.chat
        if not c or follow is False: return []
        if follow: return c["qs"]
        mins = float(s.get("followup_minutes", 15))
        if not s.get("followup_auto", False) or mins <= 0 or time.time() - c["t"] > mins * 60: return []
        w = re.findall(r"[\wÄÖÜäöü@-]+", question)
        own = [x for x in w[1:] if x[:1].isupper() and not FOLLOW_REF.fullmatch(x)]   # Nomen = eigenes Thema
        if FOLLOW_START.search(question) or (len(w) <= 6 and (FOLLOW_REF.search(question) or not own)): return c["qs"]
        return []

    def job_ask(self, question, backend_id, follow=None):
        t_start = time.perf_counter()
        prev = self._followup(question, load_settings(), follow)         # v65/v67
        ref = prev[-1] if prev else ""                                   # v67: Anzeige «Bezug: …» in der Oberflaeche
        asked = question                                                 # Originalfrage (Anzeige, Modell)
        if prev:                                                         # Suche mit dem bisherigen Thema
            question = " ".join(prev[-2:] + [asked]); self.progress(f"Folgefrage zu: {prev[-1][:60]}")
        # ---- Listenmodus ZUERST: ohne Embedding, ohne Filterlogik, ohne Sprachmodell (v18b)
        who = self.retriever.author_items(self.conn, question)
        lst = listmode.calendar_list(self.conn, question, who[0] if who else None) \
            or listmode.next_events(self.conn, question) or listmode.recent_mails(self.conn, question) \
            or listmode.web_list(self.conn, question)
        if lst:
            self.emit("answer_start", asked, "liste", ref); self.emit("token", lst[0])
            self.emit("sources", lst[1], {"search": time.perf_counter() - t_start, "total": time.perf_counter() - t_start,
                                          "list": True})
            log.get().info(f"Antwort: Listenmodus, {len(lst[1])} Eintraege")
            self.chat = {"qs": (prev + [asked])[-3:], "hits": [], "t": time.time()}
            self.progress(f"Fertig (Liste ohne Sprachmodell, {len(lst[1])} Einträge)"); return
        s = load_settings(); emb = self._embedder(); qvec = None
        if emb.available()[0] and self.conn.execute("SELECT 1 FROM chunks WHERE vec IS NOT NULL LIMIT 1").fetchone():
            self.progress("Suche (hybrid) ..."); qvec = emb.query(question); mode = "hybrid"
        else:
            self.progress("Suche (nur BM25 - noch keine Vektoren) ..."); mode = "bm25"
        R, k = self.retriever, int(s["top_k"])
        items = who[0] if who else None
        it = R.intent(self.conn, question)
        if it: items = R.filter_items(self.conn, it, items)
        info = [f"Person {' '.join(who[1])}"] if who else []
        if it and it.get("range"): info.append(it["range"][2])
        if it and it.get("source"): info.append("nur Termine")
        if it and it.get("recent"): info.append("neueste zuerst")
        if info: self.progress(f"Filter: {', '.join(info)} ({len(items) if items is not None else 'alle'} Objekte)")
        if it and it.get("source") == "outlook_calendar" and not self.conn.execute(
                "SELECT 1 FROM items WHERE source='outlook_calendar' LIMIT 1").fetchone():
            self.emit("answer_start", asked, mode, ref)
            self.emit("token", "Der Outlook-Kalender ist noch nicht synchronisiert. Bitte bei «Outlook-Kalender» auf Sync klicken.")
            self.emit("sources", []); return
        if items is not None and not items:   # (None = kein Filter)
            self.emit("answer_start", asked, mode, ref)
            self.emit("token", f"Keine Objekte für diesen Filter gefunden ({', '.join(info)}).")
            self.emit("sources", []); return
        # v77: «neueste» ohne Filter (items None) ist eine Themenfrage -> Suche mit staerkerem Aktualitaetsbonus
        if it and items is not None and (it.get("recent") or (it.get("range") and len(items) <= k)):
            hits = R.item_hits(self.conn, items, k)                 # Liste nach Datum statt nach Relevanz
        else:
            rw = float(s.get("recency_weight", 0.01)) * (3 if it and it.get("recent") else 1)
            hits = R.search(self.conn, question, qvec, k=k, mode=mode, items=items, prefer=R.facet(question),
                            recency=rw, half_days=int(s.get("recency_half_days", 180)),
                            quote_weight=float(s.get("zitat_gewicht", 0.8)))     # v73
            hits = self._drop_weak(hits, mode, s)
            if DEADLINE.search(question):
                self._add_newer_in_thread(hits)
                self._add_neighbours(hits, int(s.get("neighbour_hits", 2)))
                hits.sort(key=lambda h: h["ts"], reverse=True)          # neueste zuerst: die gilt
            if it and it.get("range"): hits.sort(key=lambda h: h["ts"])
            elif not DEADLINE.search(asked):                          # v64: die ans Modell gehenden nach Datum
                n = int(s.get("llm_top_k", 4))                           # Auswahl bleibt nach Relevanz
                hits[:n] = sorted(hits[:n], key=lambda h: h["ts"], reverse=not CHRONO.search(asked))
            wh = self._wissen_hits(question, s)                          # v28: Wissenssammlungen, falls eingeschaltet
            if wh: hits = hits[:2] + wh + hits[2:]; self.progress(f"Wissen: {len(wh)} Stellen aus {', '.join(sorted({h['source'][7:] for h in wh}))}")
        if prev and self.chat and self.chat["hits"]:                     # v65: Quellen der letzten Antwort mitnehmen
            have = {h["item_id"] for h in hits}
            old = [h for h in self.chat["hits"] if h["item_id"] not in have][:int(s.get("followup_keep", 2))]
            if old:
                hits = hits[:2] + old + hits[2:]
                if not DEADLINE.search(asked) and not (it and it.get("range")):
                    n = int(s.get("llm_top_k", 4))
                    hits[:n] = sorted(hits[:n], key=lambda h: h["ts"], reverse=not CHRONO.search(asked))
        self.emit("answer_start", asked, mode, ref)
        t_search = time.perf_counter() - t_start
        be = self._llm(backend_id); be.settings = s; be.used = None; be.timing = None
        t_gen = time.perf_counter()
        # Das Modell kennt weder Datum noch Uhrzeit -> mitgeben (sonst «heute» = Datum der Quelle)
        ctx_q = f"(Folgefrage. Vorherige Frage: {prev[-1]})\n" if prev else ""          # v65: nur die Frage, nie die Antwort
        q_llm = asked if backend_id == "extractive" else \
            f"(Aktuell: {listmode.now_text()}. Vergangenes als vergangen behandeln.)\n{ctx_q}{asked}"
        if backend_id != "extractive" and DEADLINE.search(asked):
            q_llm += ("\n(Die Quellen sind nach Datum sortiert, neueste zuerst. Werden mehrere Fristen genannt, gilt die "
                      "aus der neuesten Mail; ältere nur als verschoben erwähnen. Frist = Datum nach «spätestens», "
                      "«bis zum», «bis am». Ein Start- oder Einführungsdatum ist keine Frist.)")
        elif backend_id != "extractive" and len(hits) > 1 and not (it and it.get("range")):
            q_llm += ("\n(Die Quellen sind chronologisch sortiert, älteste zuerst. Erzähle den Ablauf in dieser Reihenfolge.)"
                      if CHRONO.search(asked) else
                      "\n(Die Quellen sind nach Datum sortiert, neueste zuerst. Beginne mit dem aktuellsten Stand, "
                      "danach kurz die Vorgeschichte.)")
        lab = (dict((i, l) for i, l, _ in discover(MODELS)).get(backend_id, "") + " " + backend_id).lower()
        if backend_id != "extractive" and "qwen3" in lab and "instruct" not in lab:
            q_llm += " /no_think"        # Qwen3-Hybridmodelle (z.B. 8B): Denkteil abschalten, sonst frisst er llm_max_new
        try:
            be.generate(q_llm, hits, lambda t: self.emit("token", t), self.cancel.is_set)
        finally:
            tm = dict(be.timing or {})
            tm.update(search=t_search, load=t_gen - t_start - t_search, total=time.perf_counter() - t_start)
            used = hits[:be.used] if be.used is not None else hits
            self.emit("sources", used, tm)
            self.chat = {"qs": (prev + [asked])[-3:], "hits": [dict(h) for h in used if h.get("item_id")][:4],
                         "t": time.time()}                               # v65
            self._llm_state()
        log.get().info(f"Antwort: {mode}, {len(hits)} Quellen, Modell {backend_id}, "
                       + ", ".join(f"{k} {v:.1f}" for k, v in tm.items() if isinstance(v, (int, float))))
        self.progress(f"Fertig ({mode}, {len(hits)} Quellen{', Folgefrage' if prev else ''})")

    # ---- v28: Wissenssammlungen
    def _wissen(self):
        if getattr(self, "wissen", None) is None:
            from .wissen import Wissen
            self.wissen = Wissen(self._embedder, self.progress)
        return self.wissen

    def job_wissen_sync(self, names=None):
        w = self._wissen(); names = names or w.names()
        if not names: self.progress("Keine Wissenssammlung vorhanden (Ordner C:\\aura\\wissen\\<name>)"); return
        st = w.prepare(names, self.cancel.is_set)
        self.emit("wissen_status", st)
        self.progress("Wissen: " + " · ".join(f"{n} {len(x['dokumente'])} Dok." + (f", fehlt: {', '.join(x['fehlend'])}" if x["fehlend"] else "")
                                             for n, x in st.items()))

    def _wissen_hits(self, question, s):
        """Chat: Treffer aus Wissenssammlungen, nur wenn der Schalter an ist."""
        try:
            w = self._wissen(); names = w.chat_names(s)
            return w.search(question, int(s.get("wissen_chat_k", 2)), names) if names else []
        except Exception as e:
            log.get().warning(f"Wissen im Chat: {e}"); return []

    # ---- v25: Workflows
    def job_workflows(self):
        from .workflow import list_workflows
        from .workflow.app import WF_DIR
        WF_DIR.mkdir(exist_ok=True); self.emit("workflows", list_workflows(WF_DIR))

    def job_wf_plan(self, prompt, fields):
        """v53: «Workflow beschreiben» – das Sprachmodell füllt Lücken des Bauplans (feste Felder, erzwungenes JSON)."""
        from .workflow.app import make_ctx
        from .workflow.nodes import _llm
        try:
            ctx = make_ctx(self.conn, load_settings(), self._llm, self._embedder, self.retriever, self.progress, self.cancel.is_set)
            r = _llm({"system": "Du hilfst, Arbeitsabläufe zu verstehen. Antworte knapp und nur mit dem, was in der Beschreibung steht.",
                      "prompt": prompt, "fields": fields}, {"workflow": {"llm": None}}, ctx)
            self.emit("wf_plan", {"ok": True, "werte": {k: v for k, v in r.items() if not k.startswith("_")}})
        except Exception as e:
            self.emit("wf_plan", {"ok": False, "fehler": f"{type(e).__name__}: {e}"})
        finally: self._llm_state()

    def job_workflow(self, path, inputs, backend_id=None, start_at=None, stop_after=None):
        """inputs: {eingabe_id: wert} (Dateien als Liste von Pfaden). Ereignisse: wf_step, wf_text, wf_done."""
        from .workflow import Runner, load_workflow
        from .workflow.app import make_ctx
        s = load_settings()
        if backend_id: s["llm"] = backend_id
        ctx = make_ctx(self.conn, s, self._llm, self._embedder, self.retriever, self.progress, self.cancel.is_set,
                       on_text=lambda t: self.emit("wf_text", t), wissen=self._wissen())
        keep_awake(True)
        try:
            try: run = Runner(load_workflow(path), inputs, ctx, on_step=lambda *a: self.emit("wf_step", *a), start_at=start_at,
                             stop_after=stop_after)
            except Exception as e:
                self.emit("wf_done", {"workflow": str(path), "status": "fehler", "error": str(e), "files": [], "log": [], "seconds": 0})
                return
            res = run.execute()
        finally:
            keep_awake(False); self._llm_state()
        log.get().info(f"Workflow {res['workflow']}: {res['status']} in {res['seconds']} s {res.get('error') or ''}")
        self.emit("wf_done", res)

