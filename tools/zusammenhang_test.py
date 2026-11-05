# tools/zusammenhang_test.py — Version 20261105v200 (v190: Vorsatz legt die Quelle fest, jeder Treffer zählt nur für einen Beleg) (AURA)
# Vergleichswert fuer einen Graphen: Findet die heutige Suche ALLE Belege einer Zusammenhangsfrage?
# Eingabe:  eval\fragen_zusammenhang.txt   Zeilen «Frage | Antwort | Quelle 1; Quelle 2; Quelle 3»
#           Vorsatz wie «Mail:» oder «Termin:» vor einer Quelle ist erlaubt und wird ignoriert.
# Ausgabe:  tools\zusammenhang_test.txt (und Kurzfassung in der Konsole)
# Aufruf:   AURA schliessen, dann  cd /d C:\aura  und  py tools\zusammenhang_test.py [Pfad\zu\fragen.txt]
# Liest nur, die Datenbank wird nicht veraendert.
import re, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))

VORSATZ = re.compile(r"^\s*(mail|e-mail|termin|kalender|edge|web|webseite|onenote|notiz|dokument|datei)\s*:\s*", re.I)
QUELLE = {"mail": "outlook_mail", "e-mail": "outlook_mail", "termin": "outlook_calendar", "kalender": "outlook_calendar",
          "edge": "edge_history", "web": "edge_history", "webseite": "edge_history", "onenote": "onenote", "notiz": "onenote",
          "dokument": "folder_docs", "datei": "folder_docs"}
K = (8, 20)                                                     # 8 = wie im Chat; 20 = zeigt, ob nur die Trefferzahl fehlt

def beleg(x):
    """Liefert (Quelle oder None, Titel)."""
    m = VORSATZ.match(x)
    return (QUELLE[m.group(1).lower()] if m else None, VORSATZ.sub("", x).strip().strip("[]").strip())

def zuordnen(soll, hits, passt):
    """Ordnet jedem Beleg einen eigenen Treffer zu; ein Treffer zählt nur einmal."""
    frei, raenge = set(range(len(hits))), []
    for src, t in soll:
        r = next((i for i in sorted(frei) if (not src or hits[i].get("source") == src) and passt(t, hits[i]["title"])), None)
        if r is None: raenge.append(None)
        else: frei.discard(r); raenge.append(r + 1)
    return raenge

def lesen(p):
    out, fehler = [], []
    for nr, z in enumerate(p.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not z.strip() or z.lstrip().startswith("#"): continue
        t = [x.strip() for x in z.split("|")]
        if t[0].lower() == "frage": continue
        if len(t) != 3 or not t[0]: fehler.append(f"Zeile {nr}: nicht genau 3 Spalten"); continue
        q = [beleg(x) for x in t[2].split(";")]; q = [x for x in q if x[1]]
        if not q: fehler.append(f"Zeile {nr}: keine Quelle"); continue
        out.append((t[0], t[1], q))
    return out, fehler

def chat_treffer(R, conn, q, qv, s, k):                         # gleicher Weg wie tools\suche_test.py, Weg «chat»
    pl = R.plan(conn, q); it, items, boost = pl["intent"], pl["items"], pl["boost"]
    vorne = pl.get("vorne") or []
    if vorne:
        pl2 = R.search(conn, q, qv, k=k, mode="hybrid", items=items)
        return R.item_hits(conn, vorne, len(vorne)) + [h for h in pl2 if h.get("item_id") not in vorne]
    rw = float(s.get("recency_weight", 0.01)) * (3 if it and it.get("recent") else 1)
    if it and items is not None and (it.get("recent") or (it.get("range") and len(items) <= 8)):
        return R.item_hits(conn, items, k)
    return R.search(conn, q, qv, k=k, mode="hybrid", items=items, prefer=R.facet(q), recency=rw, boost=boost,
                    half_days=int(s.get("recency_half_days", 180)), quote_weight=float(s.get("zitat_gewicht", 0.8)))

def main():
    from suche_test import norm, passt
    from aura import graph
    from aura import db
    from aura.config import MODELS, load_settings
    from aura.engine.embedder import Embedder
    from aura.rag import Retriever
    f = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "eval" / "fragen_zusammenhang.txt"
    if not f.exists(): print(f"Fehlt: {f}"); return
    fragen, fehler = lesen(f)
    for x in fehler: print("  !!", x)
    if not fragen: print("Keine gueltigen Fragen."); return
    s = load_settings(); conn = db.connect(); R = Retriever()
    emb = Embedder(MODELS / s["embed_model"]); ok = emb.available()[0]
    print(f"{len(fragen)} Fragen · Vektoren: {'ja' if ok else 'NEIN (nur BM25)'} · Modell {s['embed_model']}")
    titel = {(q, norm(t)) for (q, t) in conn.execute("SELECT source, title FROM items")}
    wege = ["bm25", "vektor", "hybrid", "chat", "chat+graph"] if ok else ["bm25"]
    erg = {w: {k: {"alle": 0, "belege": 0} for k in K} for w in wege}
    pruefbar, belege, zeilen = 0, 0, []
    for i, (q, antwort, soll) in enumerate(fragen, 1):
        fehlt = [x for x in soll if not any((not x[0] or q == x[0]) and passt(x[1], t) for q, t in titel)]
        zeilen.append(f"\n[{i}] {q}\n    Antwort: {antwort}")
        for x in fehlt: zeilen.append(f"    !! nicht in der Datenbank: {x[0] or 'alle Quellen'}: {x[1]}")
        if fehlt: zeilen.append("    -> nicht gewertet"); continue
        pruefbar += 1; belege += len(soll); qv = emb.query(q) if ok else None
        for w in wege:
            if w == "chat+graph":
                from aura import glossar
                ids = graph.abfolge_items(q); q = glossar.erweitern(q); h0 = R.item_hits(conn, ids, len(ids)) if ids else []
                hits = (h0 + [h for h in chat_treffer(R, conn, q, qv, s, K[-1]) if h.get("item_id") not in ids])[:K[-1]]
            else: hits = chat_treffer(R, conn, q, qv, s, K[-1]) if w == "chat" else R.search(conn, q, qv, k=K[-1], mode={"vektor": "vector"}.get(w, w))
            raenge = zuordnen(soll, hits, passt)
            for k in K:
                n = sum(1 for r in raenge if r and r <= k)
                erg[w][k]["belege"] += n; erg[w][k]["alle"] += n == len(soll)
            zeilen.append(f"    {w:<11} Raenge {' / '.join(str(r or '-') for r in raenge)}")
        print(f"  {i}/{len(fragen)}", end="\r")
    kopf = [f"Zusammenhang-Test {time.strftime('%d.%m.%Y %H:%M')} · {pruefbar} von {len(fragen)} Fragen gewertet · {belege} Belege", ""]
    kopf.append(f"{'Weg':<11}{'alle Top 8':>12}{'alle Top 20':>13}{'Belege Top 8':>14}{'Belege Top 20':>15}")
    for w in wege:
        e = erg[w]
        kopf.append(f"{w:<11}{e[8]['alle']:>9}/{pruefbar:<2}{e[20]['alle']:>10}/{pruefbar:<2}{e[8]['belege']:>11}/{belege:<2}{e[20]['belege']:>12}/{belege:<2}")
    alt = ROOT / "eval" / "fragen.txt"
    if alt.exists():
        an = [z.split("|")[0].strip() for z in alt.read_text(encoding="utf-8-sig").splitlines() if graph.ist_abfolge(z.split("|")[0])]
        kopf.append(f"\nRegel löst in fragen.txt aus: {len(an)} Fragen" + "".join(f"\n  - {x[:80]}" for x in an))
    kopf.append("\nMassgebend: Zeilen chat und chat+graph, «alle Top 8». Top 20 deutlich besser = eher mehr Treffer statt Graph.")
    kopf.append("Kleine Unterschiede sind bei 10-15 Fragen Zufall.")
    out = "\n".join(kopf + fehler + zeilen)
    (ROOT / "tools" / "zusammenhang_test.txt").write_text(out, encoding="utf-8")
    print("\n" + "\n".join(kopf)); print(f"\nDetails: {ROOT / 'tools' / 'zusammenhang_test.txt'}")

if __name__ == "__main__": main()
