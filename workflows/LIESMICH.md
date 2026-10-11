# AURA-Workflows (ab v25, Stand v34)

Ein Workflow ist eine JSON-Datei in diesem Ordner. Schritte laufen der Reihe nach; das Ergebnis jedes
Schritts liegt unter seiner `id`, Eingaben unter `input.<id>`.

## Ausdrücke
`{{ txt.text }}` setzt einen Wert ein. Erlaubte Funktionen (kein Python, kein eval):
contains, not, and, or, eq, isin, empty, default, iif, num, chf, ge, gt, le, lt, box, yesno, lower, upper, len, join, pluck, truncate, today, json.
`"when": "contains(kp.empfehlung, 'einladung')"` überspringt einen Schritt, wenn falsch.

## Bausteine
| type | Zweck | wichtige Parameter |
|---|---|---|
| extract | Text aus pdf/docx/txt/md | files, max_chars (Standard 12000) |
| llm | Sprachmodell | system, prompt, max_new **oder** fields [{name, hint, max_tokens}], temperature (0), backend |
| rag | Suche in Wissenssammlung oder AURA-Daten | collection + pin (Pflichtstellen) oder sources; query, k, max_chars |
| set | Werte festlegen | values |
| template | Text/HTML aus Vorlage | file (relativ zu workflows\) oder text, html (true) |
| file_out | Datei nach data\outputs | content, name, format (doc/html/md/txt/json), open |
| regel | Entscheidungstabelle (erste zutreffende Regel) | regeln [{name, wenn, dann}], sonst |
| word_vorlage | Word-Vorlage ausfüllen (Steuerelemente, Kontrollkästchen, Auswahllisten, «[Text]»-Felder) | vorlage, felder {Feldname: Wert}, name, open |

Grundsatz: **Rechnen und Vergleichen macht die `regel`, nicht das Sprachmodell.** Das Modell liefert Fakten
(`"zahl": true` → zusätzlich `<feld>_zahl`; `"auswahl": [...]` → nur erlaubte Werte, sonst «unklar»).

Feldnamen einer Word-Vorlage: `py tools\wf_run.py --vorlage-felder workflows\vorlagen\X.docx`
(schreibt zusätzlich `X.felder.json` als Gerüst für `felder`).

`fields` erzwingt gültiges JSON: AURA schreibt das Gerüst, das Modell nur die Werte. Leere Werte werden zu
«Keine Angabe in den Unterlagen.».

`"knowledge": [{"sammlung": "beschaffungsrecht", "pflicht": ["BöB", "VöB"]}]` gleicht die Sammlung vor dem Start
ab und bricht ab, wenn Pflichtdokumente fehlen (siehe wissen\LIESMICH.md).

## Grenzen (Stand v25)
- Kontext: Einstellung `llm_context` (Standard 16'384 Tokens), automatisch begrenzt durch `llm_mem_gb` (Standard 14).
  Faustregel: 1 Token ≈ 3–4 Zeichen Deutsch. Langer Kontext = langes Einlesen.
- Kein Netzzugriff (Fedlex-Abruf folgt in v29 über eine Freigabeliste).
- Gescannte PDFs ohne Textschicht werden nicht gelesen.
- Protokoll jedes Laufs: data\wf_runs\
