# Wissenssammlungen (ab v28)

Jeder Unterordner ist eine Sammlung, z.B. `wissen\beschaffungsrecht\`. Dateien einfach hineinlegen
(pdf mit Textschicht, docx, txt, md). AURA gleicht beim Workflow-Start automatisch ab: neue und
geänderte Dateien werden gelesen und eingebettet, gelöschte entfernt. Datenbank: `data\wissen.db`
(getrennt von Mails/Kalender).

## sammlung.json (optional, empfohlen)
- `name`, `beschreibung`: was die Sammlung enthält (für Sachbearbeitende)
- `im_chat`: darf im Chat beigezogen werden (Schalter «Wissen im Chat» links)
- `max_alter_monate`: Warnung, wenn ein Dokument älter ist
- `dokumente`: je Datei `datei`, `kurz` (Kürzel für Zitate/Pflichtstellen, z.B. «BöB»), `titel`,
  `art` («recht» = nach Artikeln zerlegen, «text», Standard «auto»), `pflicht` (true = Workflow bricht ab, wenn
  die Datei fehlt), `stand` (JJJJ-MM-TT, z.B. Stand der Fedlex-Fassung; leer = Dateidatum)

Rechtstexte werden nach Artikeln zerlegt; jedes Stück beginnt mit `[BöB Art. 21 · Stand 2026-01-01]`.

## Im Workflow
```json
"knowledge": [{"sammlung": "beschaffungsrecht", "pflicht": ["BöB", "VöB"]}],
"steps": [ {"id": "recht", "type": "rag", "collection": "beschaffungsrecht",
            "pin": ["BöB Art. 15", "BöB Art. 21"], "query": "{{txt.text}}", "k": 4} ]
```
`pin` = Stellen, die immer mitgegeben werden. `query` + `k` = zusätzlich die passendsten Stellen.

## Prüfen
`py tools\wf_run.py --wissen` zeigt alle Sammlungen, Stücke, Vektoren, fehlende und veraltete Dokumente.
`py tools\wf_run.py --wissen-suche beschaffungsrecht "Freihändiges Verfahren" --pin "BöB Art. 21"`
