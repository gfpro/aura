# tests/test_v268.py — Aktualität der Live-Quellen (geändert/erstellt)
import sys, types, unittest
from datetime import datetime, timedelta
sys.modules.setdefault("winreg", types.ModuleType("winreg"))

class Aktualitaet(unittest.TestCase):
    def test_datum(self):
        from aura.engine.aktualitaet import datum
        self.assertEqual(datum("Aktualisiert am 3.2.2025"), datetime(2025, 2, 3))
        self.assertEqual(datum("2026-11-17T14:05:00Z"), datetime(2026, 11, 17))
        self.assertIsNone(datum("")); self.assertIsNone(datum("31.02.2025"))

    def test_bonus(self):
        from aura.engine.aktualitaet import bonus
        j = datetime(2026, 11, 17)
        self.assertAlmostEqual(bonus(j, False, 6, 1.5, j), 1.5)
        self.assertAlmostEqual(bonus(j - timedelta(days=365), False, 6, 1.5, j), 0.75)
        self.assertAlmostEqual(bonus(j - timedelta(days=90), True, 6, 1.5, j), 3.0)
        self.assertEqual(bonus(None, True, 6, 1.5, j), 0)

    def test_acta_zeilen(self):
        from aura.engine import actanova_rang as R
        z = R._zeilen({"alle": [{"Name": "Bericht", "Geändert am/um": "12.11.2026 10:00", "Erstellt am/um": "03.02.2025"},
                                 {"Name": "Alt", "Erstellt am": "01.01.2020"}]})
        self.assertEqual(z[0]["geaendert"], datetime(2026, 11, 12)); self.assertEqual(z[0]["erstellt"], datetime(2025, 2, 3))
        self.assertEqual(z[0]["datum"], datetime(2026, 11, 12)); self.assertEqual(z[1]["datum"], datetime(2020, 1, 1))
        self.assertEqual(R._stand(z[0]), "geändert 12.11.2026, erstellt 03.02.2025")

if __name__ == "__main__": unittest.main()
