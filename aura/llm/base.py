# aura/llm/base.py — Schnittstelle fuer Sprachmodelle. Version 20261024v126
# v126: Quellenzeile sagt, was das Datum bedeutet (Termin am, Seite zuletzt geaendert am, besucht am) und Quelle in Klartext.
# v104: Empfaenger in der Quellenzeile; nur die Frage beantworten (keine Fuellsaetze), «nicht gefunden» statt raten.
class LLMBackend:
    name = "basis"
    used = None                                    # wie viele Quellen das Modell tatsaechlich gesehen hat
    def load(self):
        """Modell laden (im Worker-Thread)."""
    def loaded(self): return True
    def unload(self): pass
    def generate(self, question, hits, on_token, cancelled):
        """Antwort erzeugen. hits = Liste von Treffern (dict mit text, title, ts, source).
        on_token(str) fuer jedes neue Textstueck aufrufen; cancelled() pruefen."""
        raise NotImplementedError

WOCHENTAG = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

def build_prompt(question, hits):
    """Prompt im RAG-Stil: nummerierte Quellen, Antwort nur aus den Quellen, mit [n]-Verweisen."""
    src = {"outlook_mail": "Mail vom", "outlook_calendar": "Termin am", "edge_history": "Webseite, besucht am",
           "folder_docs": "Dokument vom", "confluence": "Confluence-Seite, zuletzt geändert am",
           "onenote": "OneNote-Seite vom", "anhang": "Angehängtes Dokument"}           # v126
    import datetime; d = datetime.date.today()
    an = lambda h: f", an {h['recipients'][:200]}" if h.get("recipients") else ""          # v104: «Wer waren die Adressaten?»
    ctx = "\n\n".join(f"[{i + 1}] {src.get(h['source'], h['source'] + ' vom')} {h['ts'][:16]}, von {h.get('author') or 'unbekannt'}{an(h)}, "
                       f"Betreff: {h['title']}\n{h['text']}" for i, h in enumerate(hits))
    return (f"Heute ist {WOCHENTAG[d.weekday()]}, {d.strftime('%d.%m.%Y')}.\n"
            "Beantworte die Frage ausschliesslich anhand der Quellen. Belege jede Aussage mit der Quellennummer, "
            "z.B. [1] oder [2]. Steht die Antwort nicht in den Quellen, schreibe nur: «Dazu habe ich in den Quellen nichts "
            "gefunden.» Rate nicht und verneine nichts, was die Quellen nicht ausdruecklich verneinen.\n\n"
            f"Quellen:\n{ctx}\n\nFrage: {question}\n"
            "Beantworte genau diese Frage – vollstaendig, aber ohne Zusatzinformationen, die nicht gefragt sind.\nAntwort:")
