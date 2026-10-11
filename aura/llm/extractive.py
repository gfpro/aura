# aura/llm/extractive.py — Platzhalter ohne Sprachmodell: zeigt die besten Fundstellen.
from .base import LLMBackend

class Extractive(LLMBackend):
    name = "extractive"
    def generate(self, question, hits, on_token, cancelled):
        if not hits: on_token("Keine passenden Stellen gefunden."); return
        on_token("Kein Sprachmodell aktiv - die relevantesten Stellen:\n")
        for i, h in enumerate(hits):
            if cancelled(): return
            body = h["text"].split("): ", 1)[1] if "): " in h["text"][:200] else h["text"]
            on_token(f"\n[{i + 1}] {body[:400]}{'...' if len(body) > 400 else ''}\n")
