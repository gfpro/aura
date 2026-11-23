# tools/eval_suche.py — misst nur die Suche (ohne Sprachmodell) mit eval\fragen_v2.txt. Version 20261122v294 (v294: Vergleich ohne / Nachbarn wie im Chat / mit Stückwahl; v293: Graph-Treffer ohne Empfänger, Fehler sichtbar; v292: Graph-Weg für Abfolgefragen, Thread-Bündelung im Vergleich)
# Aufruf in C:\aura:   python tools\eval_suche.py            (optional: --datei eval\andere.txt  --k 20)
# Ergebnis: eval\suche_JJJJMMTT_HHMM.txt (Übersicht) und .csv (je Frage). Liest die DB nur, ändert nichts.
import argparse, csv, re, sys, time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aura.config import load_settings, MODELS, EVAL      # noqa: E402
from aura import db                                       # noqa: E402
from aura.rag import Retriever                            # noqa: E402

TYP = {"mail": "outlook_mail", "termin": "outlook_calendar", "onenote": "onenote", "confluence": "confluence"}
PRAEFIX = re.compile(r"^\s*((aw|wg|re|fw|fwd|antw|tr|sv|r)\s*:\s*)+", re.I)


def norm(t):
    t = PRAEFIX.sub("", (t or "").replace("ß", "ss"))
    return re.sub(r"[^0-9a-zäöüàéèâêîôûç]+", " ", t.lower()).strip()


def passt(soll, ist):
    """Titelvergleich: gleich, oder (bei längeren Titeln) der eine im anderen enthalten."""
    s, i = norm(soll), norm(ist)
    return bool(s) and (s == i or (len(s) >= 12 and (s in i or (len(i) >= 12 and i in s))))


def lies_fragen(pfad):
    out = []
    for z in Path(pfad).read_text(encoding="utf-8").splitlines():
        if not z.strip() or z.lstrip().startswith("#"): continue
        f = [x.strip() for x in z.split("|")]
        if len(f) < 5: print("übersprungen (Format):", z[:60]); continue
        belege = []
        for b in f[2].split(" + "):
            typ, _, titel = b.partition(":")
            belege.append((typ.strip().lower(), titel.strip()))
        out.append({"frage": f[0], "kat": f[1].lower(), "belege": belege, "pflicht": f[3], "antwort": f[4]})
    return out


def pflicht_ok(pflicht, texte, ts):
    if not pflicht or pflicht == "-": return None
    hay = norm(" ".join(texte)) + " "
    for teil in [p.strip() for p in pflicht.split(";") if p.strip()]:
        if teil.startswith("datum="):
            if not (ts or "").startswith(teil[6:]): return False
        elif not any(norm(alt) and norm(alt) in hay for alt in teil.split("/")): return False
    return True


def rang(hits, belege, quellen):
    """Rang (1-basiert) des schlechtesten Belegs; None wenn ein Beleg fehlt. Leere Titel (z.B. «WG:») zählen als gefunden."""
    r = 0
    for typ, titel in belege:
        if not norm(titel): continue
        src = TYP.get(typ); src = src if src in quellen else None
        pos = next((n for n, h in enumerate(hits, 1) if (src is None or h["source"] == src) and passt(titel, h["title"])), None)
        if pos is None: return None
        r = max(r, pos)
    return r or 1


def im_index(conn, belege, quellen):
    for typ, titel in belege:
        s = norm(titel)
        if not s: continue
        src = TYP.get(typ); src = src if src in quellen else None
        wort = max(s.split(), key=len)
        sql = "SELECT title FROM items WHERE title LIKE ?" + (" AND source = ?" if src else "")
        if not any(passt(titel, t) for (t,) in conn.execute(sql, [f"%{wort}%"] + ([src] if src else []))): return False
    return True


def graph_ids(frage):
    if not s_graph[0]: return None
    try:
        from aura import graph
        r = graph.abfolge(frage)
        return r["ids"] if r else None
    except Exception as e:
        print("  Graph:", e); return None


def graph_vorne(conn, R, frage, hits):
    """wie worker._graph_vorne: Belege aus dem Graphen zuerst"""
    ids = graph_ids(frage)
    if not ids: return hits
    return R.item_hits(conn, ids, len(ids)) + [h for h in hits if h.get("item_id") not in ids]


def graph_rang(conn, R, frage, belege, quellen):
    """'-' = Regel greift nicht; sonst Rang aller Belege in der Graph-Antwort oder 'falsch'."""
    ids = graph_ids(frage)
    if ids is None: return "-"
    if not ids: return "kein Termin"
    return rang(R.item_hits(conn, ids, len(ids)), belege, quellen) or "falsch"


s_graph = [True]
# Kopie aus aura/worker.py (Import von worker laedt Outlook/Modelle)
DEADLINE = re.compile(r"\b(frist\w*|deadline|bis wann|sp[äa]testens|f[äa]llig\w*|eingabeschluss|termin f[üu]r)\b", re.I)


def nachbarn(conn, hits, n):
    """wie worker._add_neighbours: Vorgaenger- und Folgestueck an die ersten n Treffer haengen"""
    for h in hits[:n]:
        r = conn.execute("SELECT item_id, ord FROM chunks WHERE id = ?", (h.get("chunk_id"),)).fetchone() if h.get("chunk_id") else None
        if not r: continue
        nb_ = dict(conn.execute("SELECT ord, text FROM chunks WHERE item_id = ? AND ord IN (?, ?)", (r[0], r[1] - 1, r[1] + 1)).fetchall())
        if nb_: h["text"] = " … ".join(x for x in (nb_.get(r[1] - 1), h["text"], nb_.get(r[1] + 1)) if x)
    return hits


def main():
    sys.excepthook = sys.__excepthook__                       # AURA-Log leitet Fehler sonst in die Logdatei um
    ap = argparse.ArgumentParser()
    ap.add_argument("--datei", default=str(EVAL / "fragen_v2.txt"))
    ap.add_argument("--k", type=int, default=20)
    a = ap.parse_args()
    s = load_settings(); conn = db.connect(); R = Retriever()
    quellen = {r[0] for r in conn.execute("SELECT DISTINCT source FROM items")}
    fragen = [f for f in lies_fragen(a.datei) if f["kat"] != "live"]
    n_llm, rel = int(s.get("llm_top_k", 4)), float(s.get("min_rel_score", 0.5))
    je = int(s.get("je_thread", 0)); nb = int(s.get("nachbarn_top", 1)); sw = int(s.get("stueck_wahl", 2)) or 2; s_graph[0] = bool(s.get("graph_suche", True))
    emb = None
    if conn.execute("SELECT 1 FROM chunks WHERE vec IS NOT NULL LIMIT 1").fetchone():
        try:
            from aura.engine.embedder import Embedder
            emb = Embedder(MODELS / s["embed_model"])
            sys.excepthook = sys.__excepthook__
            if not emb.available()[0]: emb = None
            else: emb.query("Vorbereitung")
        except Exception as e:
            print("Embedder nicht verfügbar:", e); emb = None
    modi = ["bm25"] + (["vector", "hybrid"] if emb else [])
    print(f"{len(fragen)} Fragen, Modi {modi}, Quellen in DB: {sorted(quellen)}")
    zeilen = []
    for nr, f in enumerate(fragen, 1):
        z = {"nr": nr, "kat": f["kat"], "frage": f["frage"][:80], "im_index": im_index(conn, f["belege"], quellen)}
        t0 = time.perf_counter(); qvec = emb.query(f["frage"]) if emb else None; t_emb = time.perf_counter() - t0
        pl = R.plan(conn, f["frage"])
        for m in modi:
            t0 = time.perf_counter()
            try:
                hits = R.search(conn, f["frage"], qvec if m != "bm25" else None, k=a.k, mode=m, items=pl["items"],
                                prefer=R.facet(f["frage"]), boost=pl["boost"],
                                recency=float(s.get("recency_weight", 0.01)), half_days=int(s.get("recency_half_days", 180)),
                                quote_weight=float(s.get("zitat_gewicht", 0.8)))
            except Exception as e:
                print(f"  Frage {nr} {m}: Fehler {e}"); hits = []
            z[f"rang_{m}"] = rang(hits, f["belege"], quellen)
            z[f"ms_{m}"] = round((time.perf_counter() - t0 + (t_emb if m != "bm25" else 0)) * 1000)
            if m == modi[-1]:                                       # Annäherung an das, was das Modell sieht
                top = max((h["score"] for h in hits), default=0)
                stark = [h for i, h in enumerate(hits) if i < 2 or h["score"] >= rel * top] if m == "hybrid" else hits
                ts = next((h["ts"] for h in hits if passt(f["belege"][0][1], h["title"])), "")
                basis = graph_vorne(conn, R, f["frage"], R.threads(conn, stark, n_llm, je) if je else stark)
                frist = bool(DEADLINE.search(f["frage"])) if DEADLINE else False
                varianten = (("", [dict(h) for h in basis]),
                             ("_chat", nachbarn(conn, [dict(h) for h in basis], 0 if frist else nb)),
                             ("_stueck", nachbarn(conn, basis if frist else R.stueck_wahl(conn, [dict(h) for h in basis], f["frage"],
                                                  qvec if m == "hybrid" else None, sw), 0 if frist else nb)))
                for tag, liste in varianten:
                    vis = liste[:n_llm]
                    z["ans_modell" + tag] = rang(vis, f["belege"], quellen) is not None
                    z["zeichen" + tag] = sum(len(h.get("text") or "") for h in vis)
                    z["pflicht" + tag] = pflicht_ok(f["pflicht"], [" ".join(h.get(x) or "" for x in ("text", "title", "author", "recipients"))
                                                                 for h in vis], ts)
                z["graph"] = graph_rang(conn, R, f["frage"], f["belege"], quellen)
                z["top3"] = " || ".join(h["title"][:50] for h in hits[:3])
        zeilen.append(z)
        print(f"{nr:2} {f['kat']:12} " + " ".join(f"{m}={z[f'rang_{m}'] or '-'}" for m in modi) + ("" if z["im_index"] else "  (Beleg nicht im Index)"))

    stempel = datetime.now().strftime("%Y%m%d_%H%M"); EVAL.mkdir(exist_ok=True)
    with open(EVAL / f"suche_{stempel}.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]), delimiter=";"); w.writeheader(); w.writerows(zeilen)
    kats = sorted({z["kat"] for z in zeilen}) + ["GESAMT"]
    out = [f"AURA Suche-Messung {stempel} – {len(zeilen)} Fragen, k={a.k}, an Modell = erste {n_llm} nach min_rel_score {rel}", ""]
    for m in modi:
        out.append(f"== {m} ==   Kategorie | n | im Index | R@1 | R@5 | R@10 | MRR | ms/Frage")
        for k in kats:
            g = [z for z in zeilen if k == "GESAMT" or z["kat"] == k]; r = [z[f"rang_{m}"] for z in g]
            pz = lambda x: f"{sum(1 for v in r if v and v <= x)}/{len(g)}"
            mrr = sum(1 / v for v in r if v) / len(g)
            out.append(f"   {k:12} | {len(g):2} | {sum(z['im_index'] for z in g):2} | {pz(1)} | {pz(5)} | {pz(10)} | {mrr:.2f} | "
                       f"{sum(z[f'ms_{m}'] for z in g) // len(g)}")
        out.append("")
    g = [z for z in zeilen if z["pflicht"] is not None]
    out.append(f"Ans Modell ({modi[-1]}, inkl. Graph, je_thread={je}): Beleg | Pflichtbegriffe  ohne / Chat heute (Nachbarn {nb}) / + Stückwahl {sw}")
    for k in kats:
        h = [z for z in zeilen if k == "GESAMT" or z["kat"] == k]; hp = [z for z in h if z["pflicht"] is not None]
        p = lambda t: f"{sum(1 for z in hp if z['pflicht' + t])}/{len(hp)}"
        out.append(f"   {k:12} Beleg {sum(z['ans_modell'] for z in h)}/{len(h)}   Pflicht {p('')} / {p('_chat')} / {p('_stueck')}")
    out.append(f"   Zeichen im Kontext (Ø, ~Tokens = /4): {sum(z['zeichen'] for z in zeilen)//len(zeilen)} / "
               f"{sum(z['zeichen_chat'] for z in zeilen)//len(zeilen)} / {sum(z['zeichen_stueck'] for z in zeilen)//len(zeilen)}")
    gr = [z for z in zeilen if z["graph"] != "-"]
    out.append("")
    out.append(f"Graph-Weg (Abfolgefragen, ohne Sprachmodell): Regel greift bei {len(gr)} Fragen, "
               f"richtig {sum(1 for z in gr if isinstance(z['graph'], int))}, falsch {sum(1 for z in gr if z['graph'] == 'falsch')}, "
               f"kein Termin {sum(1 for z in gr if z['graph'] == 'kein Termin')}"
               + ("" if s_graph[0] else "  (Schalter graph_suche ist AUS)"))
    out.append("Hinweis: Streuung, Seltene-Wörter-Tausch und Confluence-Vorzug des Chats sind nicht nachgebildet.")
    (EVAL / f"suche_{stempel}.txt").write_text("\n".join(out), encoding="utf-8")
    print("\n" + "\n".join(out) + f"\n\nGespeichert: eval\\suche_{stempel}.txt / .csv")


if __name__ == "__main__":
    main()
