import json,sys; sys.path.insert(0,"aura"); from expr import evaluate, resolve, truthy
wf=json.load(open("out/verfahrensentscheid/workflow.json")); S={s["id"]:s for s in wf["steps"]}
GRe="340 Art. 21 Abs. 2 lit. e – Folgeauftrag (Ersetzung, Ergänzung, Erweiterung), Wechsel unzumutbar"
GRc="320 Art. 21 Abs. 2 lit. c – technische Besonderheit / geistiges Eigentum / nur eine Anbieterin"
base=dict(leistungsart="Dienstleistungen",auftragswert="1752000",oeff_auftrag="ja",kriegsmaterial="nein",art10="keine",antrag="Freihändiges Verfahren",
 grund=GRe,grund2=GRc,anhang3="ja",positivliste="unklar",vertragstyp="1070 Informatikdienstleistungen",inkl_instandhaltung="ja",inkl_ausbildung="ja",
 inkl_ersatzteile="nein",inkl_doku="nein",schwaerzung="keine",begruendung="Begr.",vertragskonstrukt="x",titel="T",gegenstand="G",kompetenzbereich="Beschaffung",auftraggeber="A",bedarfsstelle="B")
faelle={"GateVision":{}, "DL 120k":dict(auftragswert="120000",antrag="Unterschwelliges Verfahren bis CHF 150'000",grund="keine",grund2="keine"),
 "DL 190k Einladung":dict(auftragswert="190000",antrag="Einladungsverfahren",grund="keine",grund2="keine"),
 "Art.10 Inhouse":dict(art10="630 Art. 10 Abs. 3 lit. c – Inhouse (innerhalb Bundesverwaltung)",antrag="keine",grund="keine"),
 "Kriegsmaterial 900k":dict(leistungsart="Lieferungen",kriegsmaterial="ja",auftragswert="900000",antrag="Einladungsverfahren",grund="keine",grund2="keine")}
for nm,d in faelle.items():
    st={"werte":dict(base,**d),"txt_cl":{"text":""},"now":"27.10.2026"}
    st["b"]=resolve(S["b"]["values"],st)
    for r in S["v"]["regeln"]:
        if truthy(evaluate(r["wenn"],st)): st["v"]=resolve(r["dann"],st); break
    f=resolve(S["word"]["felder"],st)
    an=[k for k,x in f.items() if x is True]
    pr=[p["name"] for p in wf["pruefungen"] if truthy(evaluate(p["wenn"],st))]
    print(f"\n## {nm}: {st['v']['wert']} | 2.1={st['v']['bv']!r} | 2.4={st['v']['av']!r}\n  ☒ "+" · ".join(a[:38] for a in an)+f"\n  Prüfungen: {pr}")
