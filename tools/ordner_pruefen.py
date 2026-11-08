# tools/ordner_pruefen.py — Ordnerstruktur von AURA prüfen: was ist Code, was Daten, was löschbar, was nicht auf GitHub.
# Nur lesen: löscht und ändert nichts. Aufruf:  py tools\ordner_pruefen.py   (oder mit Pfad: py tools\ordner_pruefen.py C:\aura)
# Ergebnis: Bericht im Fenster + tools\ordner_bericht.txt + tools\gitignore_vorschlag.txt (die echte .gitignore bleibt unberührt).
import fnmatch, os, subprocess, sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
GROSS_MB = 50                                   # GitHub lehnt Dateien > 100 MB ab; ab 50 MB warnt es

# (Muster relativ zu ROOT, Kategorie, Benutzer braucht es?, auf GitHub?, Hinweis) – erste passende Regel gilt
REGELN = [
    ("**/__pycache__",          "Cache",     "nein", "nein", "wird von Python neu erzeugt – löschbar"),
    ("data/kvcache",            "Cache",     "nein", "nein", "Vorspann-Cache des Sprachmodells – löschbar, wird neu erzeugt"),
    ("logs",                    "Protokoll", "nein", "nein", "Logdateien – löschbar (Inhalt kann vertraulich sein)"),
    ("workflows/_geloescht/_laeufe", "Papierkorb","nein", "nein", "gelöschte Läufe (v60) – löschbar"),
    ("workflows/_geloescht/*",  "Papierkorb","nein", "nein", "gelöschter Workflow – vor dem Löschen prüfen, ob er noch gebraucht wird"),
    ("workflows/_geloescht",    "Papierkorb","nein", "nein", "gelöschte Workflows – löschbar, wenn nichts mehr gebraucht wird"),
    ("**/_entfernt",            "Papierkorb","nein", "nein", "entfernte Vorlagen – löschbar"),
    ("workflows/*/laeufe",      "Ergebnisse","nein", "nein", "Läufe mit echten Dokumenten – nach Prüfung löschbar, NIE auf GitHub"),
    ("workflows/*/wissen",      "Daten",     "ja",   "nein", "Wissen des Workflows (Dokumente, Index) – vertraulich"),
    ("workflows/*/vorlagen",    "Vorlage",   "ja",   "prüfen", "Word-Vorlagen – nur auf GitHub, wenn sie nicht vertraulich sind"),
    ("workflows",               "Workflows", "ja",   "teilweise", "workflow.json ja, Läufe/Wissen nein"),
    ("wissen",                  "Daten",     "ja",   "nein", "gemeinsame Wissenssammlungen (Dokumente) – vertraulich; LIESMICH.md darf auf GitHub"),
    ("data",                    "Daten",     "ja",   "nein", "Index, Vektoren, Einstellungen – persönlich, nicht löschen"),
    ("models",                  "Modell",    "ja",   "nein", "Sprachmodelle – zu gross für GitHub, separat verteilen"),
    ("vendor",                  "Pakete",    "ja",   "prüfen", "mitgelieferte Pakete – gross? dann Release/Git LFS statt Repository"),
    ("tools",                   "Entwickler","nein", "teilweise", "nur für dich: *.py ja, Ausgaben (*.txt, *.json) nein"),
    ("aura",                    "Code",      "ja",   "ja",   "Programmcode"),
    ("pruefpakete",             "Inhalte",   "ja",   "ja",   "Prüfpakete (JSON) – ja, wenn nicht vertraulich"),
    (".git",                    "Git",       "nein", "–",    "Git-Verwaltung"),
]
# Dateien, die nie auf GitHub gehören (unabhängig vom Ordner)
NIE_GITHUB = ["*.log", "*.kv", "*.db", "*.sqlite", "*.sqlite3", "*.pyc", "*.tmp", "*.bak", "*.json.bak", "*.safetensors",
              "*.gguf", "*.bin", "*.pt", "*.npy", "*.faiss", "*.db-wal", "*.db-shm", "_*.txt", "tools/*.txt", "tools/*.json", "*settings*.json", "*.pdf", "*.msg", "*.eml"]

def regel(rel):
    r = rel.replace("\\", "/")
    for muster, *rest in REGELN:
        if fnmatch.fnmatch(r, muster) or fnmatch.fnmatch(r, muster.replace("**/", "")) or \
           (muster.startswith("**/") and r.split("/")[-1] == muster[3:]):
            return (muster, *rest)
    return None

def groesse(p):
    n, b = 0, 0
    for dp, dn, fn in os.walk(p):
        for f in fn:
            try: b += (Path(dp) / f).stat().st_size; n += 1
            except OSError: pass
    return n, b

def mb(b): return f"{b / 1e6:,.1f} MB".replace(",", "'")

def main():
    out = [f"AURA – Ordnerprüfung von {ROOT}", "Nur gelesen, nichts geändert.", ""]
    zeilen, gesehen = [], set()
    for p in sorted(ROOT.rglob("*")):
        if not p.is_dir(): continue
        rel = p.relative_to(ROOT).as_posix()
        if any(rel == s or rel.startswith(s + "/") for s in gesehen): continue      # unter einer erkannten Regel: nicht tiefer
        r = regel(rel)
        tief = rel.count("/")
        if r is None and tief > 0: continue                                         # nur oberste Ebene ohne Regel zeigen
        n, b = groesse(p); zeilen.append((rel, n, b, r))
        unter = r and (r[0] in ("aura", "tools") or any(m.startswith(r[0] + "/") for m, *_ in REGELN))
        if not unter: gesehen.add(rel)                                              # Unterordner mit eigenen Regeln weiter prüfen
    out.append(f"{'Ordner':<46} {'Dateien':>8} {'Grösse':>12}  {'Art':<11} {'Benutzer':<8} {'GitHub':<9} Hinweis")
    out.append("-" * 150)
    loeschbar = 0
    for rel, n, b, r in zeilen:
        if r: _, art, ben, gh, hin = r
        else: art, ben, gh, hin = "unbekannt", "?", "?", "nicht zugeordnet – bitte selbst entscheiden"
        if art in ("Cache", "Protokoll", "Papierkorb", "Ergebnisse"): loeschbar += b
        out.append(f"{rel:<46} {n:>8} {mb(b):>12}  {art:<11} {ben:<8} {gh:<9} {hin}")
    out += ["", f"Löschbar (Cache, Protokolle, Papierkorb, Läufe): {mb(loeschbar)}", ""]
    # Dateien auf oberster Ebene
    out.append("Dateien im Hauptordner:")
    for f in sorted(x for x in ROOT.iterdir() if x.is_file()):
        nie = any(fnmatch.fnmatch(f.name, m) for m in NIE_GITHUB)
        out.append(f"  {f.name:<40} {mb(f.stat().st_size):>12}  GitHub: {'nein' if nie else 'ja'}")
    # grosse Dateien
    gross = [(p, p.stat().st_size) for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts
             and p.stat().st_size > GROSS_MB * 1e6]
    out += ["", f"Dateien über {GROSS_MB} MB (nicht ins Repository; GitHub-Grenze 100 MB):"]
    out += [f"  {p.relative_to(ROOT).as_posix():<70} {mb(s):>12}" for p, s in sorted(gross, key=lambda x: -x[1])] or ["  keine"]
    # tools: was davon nicht auf GitHub
    t = ROOT / "tools"
    if t.exists():
        aus = [x.name for x in sorted(t.iterdir()) if x.is_file() and x.suffix.lower() in (".txt", ".json", ".log", ".csv")]
        out += ["", "tools – Ausgaben, die nicht auf GitHub gehören:"] + [f"  {a}" for a in aus] if aus else []
    # bereits in Git erfasste Dateien, die nicht hineingehören
    if (ROOT / ".git").exists():
        try:
            fs = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, timeout=30).stdout.splitlines()
            schlecht = [f for f in fs if any(fnmatch.fnmatch(f, m) or fnmatch.fnmatch(Path(f).name, m) for m in NIE_GITHUB)
                        or (regel(str(Path(f).parent.as_posix())) or ("", "", "", "ja"))[3] == "nein"
                        or any(fnmatch.fnmatch(f, m + "/*") for m in ("workflows/*/laeufe/*", "workflows/*/wissen/*", "data/*", "logs/*"))]
            out += ["", f"ACHTUNG – schon in Git erfasst, gehört aber nicht hinein ({len(schlecht)}):"]
            out += [f"  {f}" for f in schlecht[:60]] + (["  …"] if len(schlecht) > 60 else []) if schlecht else ["  keine"]
            if schlecht: out.append("  Entfernen aus Git (Dateien bleiben auf der Festplatte):  git rm -r --cached <pfad>")
        except Exception as e: out += ["", f"Git nicht prüfbar: {e}"]
    else: out += ["", "Kein Git-Repository in diesem Ordner gefunden."]
    gi = ["# Vorschlag von tools/ordner_pruefen.py – prüfen, dann als .gitignore übernehmen", "__pycache__/", "*.pyc",
          "data/", "logs/", "models/", "workflows/*/laeufe/", "workflows/*/wissen/", "workflows/_geloescht/", "**/_entfernt/",
          "*.log", "*.kv", "*.db", "*.sqlite*", "*.tmp", "*.bak", "*settings*.json", "tools/*.txt", "tools/*.json",
          "# Vertrauliche Vorlagen? dann auch:", "# workflows/*/vorlagen/", "# Grosse Pakete? dann auch:", "# vendor/wheels/"]
    (ROOT / "tools").mkdir(exist_ok=True)
    (ROOT / "tools" / "gitignore_vorschlag.txt").write_text("\n".join(gi) + "\n", encoding="utf-8")
    (ROOT / "tools" / "ordner_bericht.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    print("\nGespeichert: tools\\ordner_bericht.txt und tools\\gitignore_vorschlag.txt")

if __name__ == "__main__":
    main()
    if sys.stdin and sys.stdin.isatty():
        try: input("\nEnter zum Schliessen...")
        except EOFError: pass
