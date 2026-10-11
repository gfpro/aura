# aura/llm/base.py — Schnittstelle fuer Sprachmodelle.
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
    src = {"outlook_mail": "Mail", "outlook_calendar": "Termin", "edge_history": "Webseite", "folder_docs": "Dokument"}
    import datetime; d = datetime.date.today()
    ctx = "\n\n".join(f"[{i + 1}] {src.get(h['source'], h['source'])} vom {h['ts'][:16]}, von {h.get('author') or 'unbekannt'}, "
                       f"Betreff: {h['title']}\n{h['text']}" for i, h in enumerate(hits))
    return (f"Heute ist {WOCHENTAG[d.weekday()]}, {d.strftime('%d.%m.%Y')}.\n"
            "Beantworte die Frage ausschliesslich anhand der Quellen. Belege jede Aussage mit der Quellennummer, "
            "z.B. [1] oder [2]. Wenn die Quellen die Antwort nicht enthalten, sage das.\n\n"
            f"Quellen:\n{ctx}\n\nFrage: {question}\nAntworte kurz, in hoechstens 3 Saetzen.\nAntwort:")
