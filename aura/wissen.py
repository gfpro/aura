# aura/wissen.py — Wissenssammlungen: Fachdokumente fuer Workflows (und auf Wunsch fuer den Chat). Version 20261008v36
# Ordner wissen\<sammlung>\ mit beliebigen Dateien (pdf, docx, txt, md) + optional sammlung.json (Beschreibung,
# Pflichtdokumente, Stand). Eigene Datenbank data\wissen.db - getrennt von Mails/Kalender/Verlauf.
# Rechtstexte werden nach Artikeln zerlegt; jedes Stueck beginnt mit «[BöB Art. 21 · Stand 2026-01-01]».
import hashlib, json, re, shutil, time
from datetime import date, datetime
from pathlib import Path
from array import array
from . import db
from .config import DATA, ROOT
from .rag import Retriever
from .text import clean, make_chunks

WISSEN_DIR, WISSEN_DB = ROOT / "wissen", DATA / "wissen.db"
WF_DIR = ROOT / "workflows"

def folder(name):
    """Sammlung -> Ordner. «wf:<workflow>» = Wissen eines Workflow-Pakets (workflows\\<workflow>\\wissen),
    sonst gemeinsame Sammlung (wissen\\<name>)."""
    return WF_DIR / name[3:] / "wissen" if name.startswith("wf:") else WISSEN_DIR / name
CHUNKER = 5                                            # erhoehen = alle Dokumente neu zerlegen
EXT = {".pdf", ".docx", ".txt", ".md", ".html", ".htm"}
# Artikel/Anhang am Zeilenanfang - auch hinter einem Gliederungstitel auf derselben Zeile
# («4. Kapitel: Vergabeverfahren Art. 16 Schwellenwerte», so liefert pypdf Fedlex-PDFs) und mit geschuetztem Leerzeichen.
SEC = re.compile(r"^[ \t\u00a0]*(?:[^\n]{0,80}?\b(?:Kapitel|Abschnitt|Titel|Teil)\b[^\n]{0,120}?[ \t\u00a0])?"
                 r"((?:Art\.|Artikel)[ \t\u00a0]*(\d+)[a-z]{0,6}\b|Anhang[ \t\u00a0]+\d+[a-z]?\b)", re.M | re.I)

def _norm_label(s):
    s = re.sub(r"[\s\u00a0]+", " ", s.strip())
    s = re.sub(r"^(Artikel|Art\.?)\s*", "Art. ", s, flags=re.I)
    m = re.match(r"^anhang\s*(\d+)([a-z]?)$", s, re.I)
    if m:                                                  # «Anhang 425» = Anhang 4 + Fussnote 25
        n = m.group(1); n = n[0] if int(n) > 12 else n
        return f"Anhang {n}{m.group(2)}"
    return s

def parse_date(s):
    """'2026-01-01' oder '01.01.2026' -> date, sonst None."""
    s = (s or "").strip()
    try:
        if re.match(r"\d{4}-\d{2}-\d{2}", s): return date.fromisoformat(s[:10])
        m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None
    except ValueError: return None

def legal_chunks(text, kurz, stand, strict=False):
    """Zerlegung nach Art./Anhang. None, wenn der Text nicht wie ein Erlass aussieht.
    strict (art=auto): erst ab Art. 1/2 und mind. 5 Artikel - sonst sind es nur Verweise in einem Fachtext."""
    allm = list(SEC.finditer(text))
    # Beginn = erste Zeile «Art. 1»; davor (Ingress «gestuetzt auf Art. 173 BV ...») ist Einleitung, keine Gliederung
    start = next((i for i, m in enumerate(allm) if m.group(2) and int(m.group(2)) == 1),
                 next((i for i, m in enumerate(allm) if m.group(2) and int(m.group(2)) <= 2), 0))
    marks, last = [], -1
    for m in allm[start:]:
        if m.group(2):                                   # Artikelnummern steigen; Verweise am Zeilenanfang ignorieren
            n = int(m.group(2))
            if n < last or n > last + 30 and last >= 0: continue
            last = n
        marks.append(m)
    if not marks: return None
    arts = [int(m.group(2)) for m in marks if m.group(2)]
    if len(arts) < 3 or strict and (len(arts) < 5 or arts[0] > 2): return None
    tag = f" · Stand {stand}" if stand else ""
    out = []
    head = clean(text[:marks[0].start()])
    if head: out += make_chunks(head, f"[{kurz} Einleitung{tag}] ")
    for i, m in enumerate(marks):
        body = clean(text[m.start():marks[i + 1].start() if i + 1 < len(marks) else len(text)])
        out += make_chunks(body, f"[{kurz} {_norm_label(m.group(1))}{tag}] ")
    return out

def slugify(s):
    s = (s or "").strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("é", "e"), ("è", "e"), ("à", "a")): s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:40]

def norm_pin(p):
    """'BöB Art 21' / 'BöB Art. 21 Abs. 2' -> 'BöB Art. 21'"""
    m = re.match(r"^(.*?)\s*((?:Art(?:ikel|\.)?|Anhang)\s*\d+[a-z]?)", p.strip(), re.I)
    return f"{m.group(1).strip()} {_norm_label(m.group(2))}" if m else p.strip()

class Wissen:
    def __init__(self, get_embedder=lambda: None, progress=print):
        self.conn = db.connect(WISSEN_DB); self.R = Retriever()
        self.get_embedder, self.progress = get_embedder, progress
        WISSEN_DIR.mkdir(exist_ok=True)

    # ---- Sammlungen
    def names(self): return sorted(p.name for p in WISSEN_DIR.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))

    def all_names(self):
        """Gemeinsame Sammlungen + Wissen aller Workflow-Pakete."""
        wf = sorted(f"wf:{p.parent.name}" for p in WF_DIR.glob("*/wissen") if p.is_dir()) if WF_DIR.exists() else []
        return self.names() + wf

    def manifest(self, name):
        f = folder(name) / "sammlung.json"
        try: m = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except Exception as e: m = {"_error": f"sammlung.json: {e}"}
        m.setdefault("name", name); m.setdefault("dokumente", [])
        return m

    def _files(self, name):
        d = folder(name)
        return sorted(f for f in d.rglob("*") if f.is_file() and f.suffix.lower() in EXT
                      and not any(x.startswith(("_", "~$", ".")) for x in f.relative_to(d).parts))

    # ---- Verwaltung (Oberflaeche): sammlung.json wird nur hier geschrieben
    def save_manifest(self, name, man):
        man = {k: v for k, v in man.items() if not k.startswith("_")}
        f = folder(name) / "sammlung.json"; tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8"); tmp.replace(f)

    def create(self, title, beschreibung=""):
        name = slugify(title)
        if not name: raise ValueError("Bitte einen Namen mit Buchstaben oder Ziffern eingeben")
        if folder(name).exists(): raise ValueError(f"Sammlung «{name}» gibt es schon")
        folder(name).mkdir(parents=True)
        self.save_manifest(name, {"name": title.strip(), "beschreibung": beschreibung, "im_chat": True,
                                  "max_alter_monate": 12, "dokumente": []})
        return name

    def add_files(self, name, paths):
        """Kopiert Dateien in die Sammlung und legt Eintraege an. Rueckgabe: Liste der Dateinamen."""
        fold = folder(name); man = self.manifest(name)
        have = {d.get("datei", "").lower() for d in man["dokumente"]}; out = []
        for p in paths:
            p = Path(p)
            if p.suffix.lower() not in EXT: raise ValueError(f"{p.name}: Dateityp nicht unterstuetzt ({', '.join(sorted(EXT))})")
            shutil.copy2(p, fold / p.name); out.append(p.name)
            if p.name.lower() not in have:
                man["dokumente"].append({"datei": p.name, "kurz": p.stem, "titel": p.stem, "art": "auto",
                                         "stand": "", "pflicht": False})
        self.save_manifest(name, man)
        return out

    def remove_file(self, name, datei):
        """Datei nach <sammlung>\\_entfernt verschieben (nicht loeschen) und Eintrag entfernen."""
        fold = folder(name); f = fold / datei
        if f.exists():
            (fold / "_entfernt").mkdir(exist_ok=True)
            shutil.move(str(f), str(fold / "_entfernt" / f"{datetime.now():%Y%m%d_%H%M}_{f.name}"))
        man = self.manifest(name)
        man["dokumente"] = [d for d in man["dokumente"] if d.get("datei", "").lower() != datei.lower()]
        self.save_manifest(name, man)

    def doc_rows(self, name):
        """Dateien im Ordner + Eintraege aus sammlung.json + Stand in der Datenbank, fuer die Oberflaeche."""
        fold = folder(name); man = self.manifest(name)
        files = {f.name.lower(): f for f in self._files(name)} if fold.is_dir() else {}
        db_ = {}
        for ext, meta, n, v in self.conn.execute(
                "SELECT i.ext_id, i.meta, COUNT(c.id), COUNT(c.vec) FROM items i LEFT JOIN chunks c ON c.item_id = i.id "
                "WHERE i.source = ? GROUP BY i.id", (name,)):
            db_[Path(ext).name.lower()] = (json.loads(meta or "{}"), n, v)
        rows, seen = [], set()
        for d in man["dokumente"]:
            k = d.get("datei", "").lower(); seen.add(k)
            rows.append(dict(d, vorhanden=k in files, db=db_.get(k)))
        for k, f in files.items():
            if k not in seen:
                rows.append({"datei": f.name, "kurz": f.stem, "titel": f.stem, "art": "auto", "stand": "", "pflicht": False,
                             "vorhanden": True, "db": db_.get(k), "neu": True})
        return rows

    # ---- Abgleich
    def sync(self, names=None, stop=lambda: False):
        from .workflow.nodes import read_file
        total = {"neu": 0, "geaendert": 0, "entfernt": 0, "fehler": []}
        for name in names or self.names():
            fold = folder(name)
            if not fold.is_dir():
                if name.startswith("wf:"): continue                  # Workflow ohne eigenes Wissen
                raise RuntimeError(f"Wissenssammlung «{name}» fehlt (Ordner {fold})")
            man = self.manifest(name); docs = {d.get("datei", "").lower(): d for d in man["dokumente"]}
            known = {e: (i, json.loads(m or "{}")) for i, e, m in
                     self.conn.execute("SELECT id, ext_id, meta FROM items WHERE source = ?", (name,))}
            seen, changed = set(), False
            for f in self._files(name):
                if stop(): break
                rel = f.relative_to(fold).as_posix(); seen.add(rel); st = f.stat()
                d = docs.get(f.name.lower(), {})                      # Angaben aus sammlung.json gehoeren zur Signatur:
                dh = hashlib.md5(json.dumps(d, sort_keys=True).encode()).hexdigest()[:8]   # geaenderter Stand/Art -> neu
                sig = f"{st.st_size}:{int(st.st_mtime)}:{CHUNKER}:{dh}"
                if rel in known and known[rel][1].get("sig") == sig: continue
                self.progress(f"Wissen {name}: lese {f.name} ...")
                try: text = read_file(f)
                except Exception as e: total["fehler"].append(f"{name}/{rel}: {e}"); continue
                d = docs.get(f.name.lower(), {})
                kurz = d.get("kurz") or f.stem
                stand = d.get("stand") or date.fromtimestamp(st.st_mtime).isoformat()
                art = d.get("art", "auto")
                chunks = legal_chunks(text, kurz, stand, strict=art == "auto") if art in ("recht", "auto") else None
                if chunks is None:
                    if art == "recht":
                        nums = [m.group(2) for m in SEC.finditer(text) if m.group(2)][:8]
                        self.progress(f"Achtung {kurz}: Artikel nicht erkannt (Zeilenanfaenge Art.: {', '.join(nums) or 'keine'}) - als Fliesstext zerlegt")
                    chunks = make_chunks(clean(text), f"[{kurz} · Stand {stand}] ")
                if rel in known:
                    self.conn.execute("DELETE FROM items WHERE id = ?", (known[rel][0],)); total["geaendert"] += 1
                else: total["neu"] += 1
                db.add_item(self.conn, name, {"ext_id": rel, "title": d.get("titel") or f.stem, "author": kurz, "ts": stand,
                                              "location": str(f), "body": "",
                                              "meta": {"sig": sig, "kurz": kurz, "stand": stand,
                                                       "art": "recht" if any(re.match(r"\[[^\]]* (?:Art\.|Anhang) ", c) for c in chunks[:80]) else "text"}},
                            chunks)
                changed = True
            if not stop():
                for rel, (iid, _) in known.items():
                    if rel not in seen:
                        self.conn.execute("DELETE FROM items WHERE id = ?", (iid,)); total["entfernt"] += 1; changed = True
            self.conn.commit()
            if changed: db.rebuild_fts(self.conn); self.R.invalidate()
            db.set_sync(self.conn, name, f"{total['neu']} neu, {total['geaendert']} geaendert, {total['entfernt']} entfernt")
        return total

    def embed(self, names=None, stop=lambda: False):
        emb = self.get_embedder()
        if emb is None or not emb.available()[0]: return 0
        q = "SELECT c.id, c.text FROM chunks c JOIN items i ON i.id = c.item_id WHERE c.vec IS NULL"
        args = []
        if names: q += f" AND i.source IN ({','.join('?' * len(names))})"; args = list(names)
        todo = self.conn.execute(q, args).fetchall()
        if not todo: return 0
        emb.load(); t0 = time.perf_counter()
        for n, (cid, text) in enumerate(todo, 1):
            if stop(): break
            self.conn.execute("UPDATE chunks SET vec = ? WHERE id = ?", (array("f", emb.passage(text)).tobytes(), cid))
            if n % 25 == 0:
                self.conn.commit(); self.progress(f"Wissen: Vektoren {n}/{len(todo)} ({time.perf_counter() - t0:.0f} s)", n, len(todo))
        self.conn.commit(); self.R.invalidate()
        return len(todo)

    def prepare(self, names, stop=lambda: False):
        """Vor einem Workflow: Ordner abgleichen und neue Stuecke einbetten. Liefert Status je Sammlung."""
        r = self.sync(names, stop); n = self.embed(names, stop)
        if r["neu"] or r["geaendert"] or r["entfernt"] or n:
            self.progress(f"Wissen: {r['neu']} neu, {r['geaendert']} geaendert, {r['entfernt']} entfernt, {n} Stuecke eingebettet")
        for e in r["fehler"]: self.progress(f"Wissen – nicht lesbar: {e}")
        return {nm: self.status(nm) for nm in names}

    # ---- Abfrage
    def status(self, name):
        man = self.manifest(name); fold = folder(name)
        files = {f.name.lower() for f in self._files(name)} if fold.is_dir() else set()
        rows = self.conn.execute("SELECT i.title, i.author, i.ts, i.meta, COUNT(c.id), COUNT(c.vec) FROM items i "
                                 "LEFT JOIN chunks c ON c.item_id = i.id WHERE i.source = ? GROUP BY i.id ORDER BY i.author",
                                 (name,)).fetchall()
        max_m = int(man.get("max_alter_monate", 0) or 0); today = date.today(); old = []
        for title, kurz, stand, *_ in rows:
            d = parse_date(stand)
            if d is None: continue
            if max_m and (today.year - d.year) * 12 + today.month - d.month > max_m: old.append(f"{kurz} (Stand {stand[:10]})")
        missing = [d.get("kurz") or d.get("datei") for d in man["dokumente"]
                   if d.get("pflicht") and d.get("datei", "").lower() not in files]
        return {"name": man["name"], "beschreibung": man.get("beschreibung", ""), "im_chat": bool(man.get("im_chat", True)),
                "dokumente": [{"titel": t, "kurz": k, "stand": s, "stuecke": c, "vektoren": v,
                               "art": json.loads(m or "{}").get("art", "")} for t, k, s, m, c, v in rows],
                "fehlend": missing, "veraltet": old, "fehler": man.get("_error")}

    def search(self, query, k=6, names=None, pin=None):
        """Pflichtstellen (pin) zuerst, dann Suche (hybrid, wenn Vektoren da sind). Treffer wie rag.search + path."""
        names = names or self.names()
        if isinstance(names, str): names = [names]
        items = [r[0] for r in self.conn.execute(f"SELECT id FROM items WHERE source IN ({','.join('?' * len(names))})", names)]
        if not items: return []
        hits, seen = [], set()
        for p in pin or []:
            lab = norm_pin(p); n0 = len(hits)
            for cid, text, iid, src, title, ts, kurz, loc in self.conn.execute(
                    f"SELECT c.id, c.text, i.id, i.source, i.title, i.ts, i.author, i.location FROM chunks c JOIN items i "
                    f"ON i.id = c.item_id WHERE i.source IN ({','.join('?' * len(names))}) AND (c.text LIKE ? OR c.text LIKE ?) "
                    f"ORDER BY i.id, c.ord", names + [f"[{lab}]%", f"[{lab} ·%"]):
                if cid in seen: continue
                seen.add(cid); hits.append(self._hit(cid, text, iid, src, title, ts, kurz, loc, 1.0, pinned=True))
            if len(hits) == n0: self.progress(f"Hinweis: Pflichtstelle «{p}» nicht gefunden (als «{lab}» gesucht)")
        if query and k > 0:
            emb, qvec, mode = self.get_embedder(), None, "bm25"
            if emb is not None and emb.available()[0] and self.conn.execute("SELECT 1 FROM chunks WHERE vec IS NOT NULL LIMIT 1").fetchone():
                qvec, mode = emb.query(query), "hybrid"
            try: found = self.R.search(self.conn, query, qvec, k=k + len(seen), mode=mode, items=items, per_item=3)
            except TypeError: found = self.R.search(self.conn, query, qvec, k=k + len(seen), mode=mode, items=items)
            for h in found:
                if h["chunk_id"] in seen: continue
                seen.add(h["chunk_id"])
                loc = self.conn.execute("SELECT location FROM items WHERE id = ?", (h["item_id"],)).fetchone()
                h.update(path=loc[0] if loc else "", source=f"wissen:{h['source']}", pinned=False); hits.append(h)
                if len(hits) >= len(pin or []) and sum(not x.get("pinned") for x in hits) >= k: break
        return hits

    @staticmethod
    def _hit(cid, text, iid, src, title, ts, kurz, loc, score, pinned):
        return {"chunk_id": cid, "text": text, "item_id": iid, "source": f"wissen:{src}", "title": title or "", "ts": ts or "",
                "author": kurz or "", "score": score, "path": loc or "", "pinned": pinned}

    def chat_names(self, settings):
        """Sammlungen fuer den Chat: Schalter wissen_chat, Auswahl wissen_chat_sammlungen (leer = alle mit im_chat)."""
        if not settings.get("wissen_chat", False): return []
        sel = settings.get("wissen_chat_sammlungen") or []
        return [n for n in self.all_names() if (n in sel if sel else self.manifest(n).get("im_chat", True))]
