# tests/test_v266.py — Memo: Ablage, Quelle, lange Aufnahme in Abschnitten (ohne GPU)
import math, struct, sys, tempfile, types, unittest, wave
from pathlib import Path
sys.modules.setdefault("winreg", types.ModuleType("winreg"))   # nur Windows; unter Linux reicht ein Platzhalter

class MemoTest(unittest.TestCase):
    def test_tagesdatei_und_einlesen(self):
        from datetime import datetime
        from aura.connectors import memos
        from aura.connectors.base import SyncContext
        with tempfile.TemporaryDirectory() as d:
            s = {"memo_folder": d}
            p1 = memos.speichern(s, "Eingangspost", "Einladungen versendet.", datetime(2026, 11, 17, 9, 5))
            p2 = memos.speichern(s, "Budget", "Zweiter Text.", datetime(2026, 11, 17, 14, 30))
            p3 = memos.speichern(s, "Neu", "Morgen.", datetime(2026, 11, 18, 8, 0))
            self.assertEqual(p1, p2); self.assertNotEqual(p1, p3); self.assertEqual(p1.name, "2026-11-17_Memos.md")
            t = memos.lesen(p1)
            self.assertTrue(t.startswith("# Memos vom 17.11.2026"))
            self.assertIn("## 09:05 · Eingangspost", t); self.assertIn("## 14:30 · Budget", t); self.assertEqual(memos.anzahl(t), 2)
            self.assertEqual(memos.liste(s), [p3, p1])
            ctx = SyncContext(set(), s, lambda *a: None, lambda: False)
            self.assertEqual(len(list(memos.Memos().sync(ctx))), 2); self.assertTrue(ctx.complete)

    def test_bearbeiten_und_loeschen(self):
        from aura.connectors import memos
        from aura.connectors.base import SyncContext
        with tempfile.TemporaryDirectory() as d:
            s = {"memo_folder": d}
            p = memos.speichern(s, "A", "eins")
            memos.aendern(p, "# Memos\n\n## 09:00 · A\n\nkorrigiert")
            self.assertIn("korrigiert", memos.lesen(p))
            memos.loeschen(p); self.assertEqual(memos.liste(s), [])
            ctx = SyncContext(set(), s, lambda *a: None, lambda: False)
            self.assertEqual(list(memos.Memos().sync(ctx)), []); self.assertTrue(ctx.complete)

    def test_abschnitte(self):
        from aura.engine import whisper_dml, mel
        SR = mel.SR; s = []
        for k in range(SR * 70):                                     # 70 s Ton mit Pause bei 27-28 s und 55-56 s
            t = k / SR; ruhe = 27 <= t < 28 or 55 <= t < 56
            s.append(0.0 if ruhe else 0.3 * math.sin(2 * math.pi * 220 * t))
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "a.wav"
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
                w.writeframes(b"".join(struct.pack("<h", int(v * 32767)) for v in s))
            laengen = []
            class Fake:
                NM = 80
                def encode(self, rows): pass
                def generate(self): return [len(laengen)]
                def decode(self, ids): return f"T{ids[0]}"
            f = Fake()
            orig = mel.log_mel
            def fake(st, n): laengen.append(len(st) / SR); return [], 0
            mel.log_mel = fake
            try: text = whisper_dml.Whisper.transcribe_lang(f, wav)
            finally: mel.log_mel = orig
        self.assertEqual(len(laengen), 3); self.assertTrue(all(x <= 30 for x in laengen))
        self.assertAlmostEqual(laengen[0], 27.5, delta=0.6)          # Schnitt in der Pause
        self.assertEqual(text, "T1 T2 T3")

class SchleifeTest(unittest.TestCase):
    def test_text(self):
        from aura.engine.whisper_dml import entschleifen
        self.assertEqual(entschleifen("Ich bin zuhause, " + "ich bin zuhause, " * 40 + "ich bin zuha"), "Ich bin zuhause")
        ok = "Die Einladungen zur Bearbeitung der Eingangspost sind versendet."
        self.assertEqual(entschleifen(ok), ok)
        self.assertEqual(entschleifen("Das ist sehr sehr sehr gut."), "Das ist sehr sehr sehr gut.")

    def test_schleife(self):
        from aura.engine.whisper_dml import _schleife
        x = [1, 2]; S = [5, 6, 7, 8]
        self.assertEqual(_schleife(x + S), 0)
        self.assertEqual(_schleife(x + S + S), 0)
        out = x + S * 4; self.assertEqual(out[:_schleife(out)], x + S)
        self.assertEqual(_schleife([3, 9, 9, 9]), 0)                  # dreimal dasselbe Wort bleibt
        out = [3] + [9] * 5; self.assertEqual(out[:_schleife(out)], [3, 9])

class F16Test(unittest.TestCase):
    def test_f16(self):
        import json
        from aura.engine.weights import SafeTensors
        daten = struct.pack("<4e", 1.5, -2.25, 0.125, 3.0)
        kopf = json.dumps({"w": {"dtype": "F16", "shape": [4], "data_offsets": [0, len(daten)]}}).encode()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.safetensors"; p.write_bytes(struct.pack("<Q", len(kopf)) + kopf + daten)
            st = SafeTensors(p)
            self.assertEqual(list(st.floats("w")), [1.5, -2.25, 0.125, 3.0]); self.assertEqual(list(st.floats("w", 1, 2)), [-2.25, 0.125])
            st.mm.close(); st.f.close()

if __name__ == "__main__": unittest.main()
