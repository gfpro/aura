import urllib.request, json, os
F = r"C:\aura\data\confluence_token.txt"
url = "https://confluence.bit.admin.ch/rest/api/content/search?cql=ancestor=1116048521&limit=5&expand=version"
for name, tok in [("anonym", None), ("token", open(F).read().strip() if os.path.exists(F) else None)]:
    if name == "token" and not tok: continue
    h = {"Accept": "application/json"}
    if tok: h["Authorization"] = "Bearer " + tok
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30))
        print(name, "OK, gesamt:", d.get("totalSize", d.get("size")))
        for r in d["results"]: print("  ", r["id"], r["version"]["number"], r["title"])
    except Exception as e:
        print(name, "FEHLER:", e, getattr(e, "read", lambda: b"")()[:200])