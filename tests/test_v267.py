# tests/test_v267.py — Agent: Termin aus dem Auftrag bestimmen, Rückfrage bei Mehrdeutigkeit (F7)
import sqlite3, sys, types, unittest
from datetime import datetime, timedelta
sys.modules.setdefault("winreg", types.ModuleType("winreg"))

class W:
    def __init__(self, termine):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, source TEXT, title TEXT, ts TEXT, location TEXT, recipients TEXT, body TEXT)")
        for i, (tage, std, titel, wer) in enumerate(termine, 1):
            ts = (datetime.now() + timedelta(days=tage)).replace(hour=std, minute=0).strftime("%Y-%m-%d %H:%M")
            self.conn.execute("INSERT INTO items VALUES (?,?,?,?,?,?,?)", (i, "outlook_calendar", titel, ts, "Bern", wer, ""))

class FallGF(unittest.TestCase):
    """17.11.2026: «Bereite mich für den nächsten Termin vor» nahm den 19.11., weil «mich» in «Michael» steckte."""
    def test_mich_und_abwesend(self):
        from aura import agent
        w = W([(0, 23, "Abwesend", ""), (1, 23, "MA-Anlass GB Ressourcen & Support", "Moser Daniel"),
               (2, 13, "Informationsmanagement Board VBS", "Müller Michael")])
        t, k, _ = agent.termin_wahl(w, "Bereite mich für den nächsten Termin vor.")
        self.assertEqual(t["title"], "MA-Anlass GB Ressourcen & Support")
        t, _, _ = agent.termin_wahl(w, "Bereite das Board vor"); self.assertEqual(t["title"], "Informationsmanagement Board VBS")


class TerminWahl(unittest.TestCase):
    def setUp(self):
        from aura import agent; self.A = agent
        self.w = W([(1, 9, "Jour fixe Daten", "Müller Hans; Keller Anna"), (1, 14, "KIAR Review", "Meier Paul"),
                    (2, 10, "Workshop Datenkatalog", "Müller Hans"), (3, 11, "Sitzung RSIT", "Keller Anna")])

    def wahl(self, a): return self.A.termin_wahl(self.w, a)

    def test_allgemein_naechster(self):
        t, k, _ = self.wahl("Bereite meinen nächsten Termin vor"); self.assertEqual(t["title"], "Jour fixe Daten"); self.assertEqual(k, [])

    def test_naechster_mit_fuellwoertern(self):
        t, k, _ = self.wahl("Erstelle mir Unterlagen für den nächsten Termin, möglichst kompakt"); self.assertEqual(t["title"], "Jour fixe Daten")

    def test_eindeutig(self):
        t, k, _ = self.wahl("Bereite das KIAR Review vor"); self.assertEqual(t["title"], "KIAR Review")
        t, _, _ = self.wahl("Sitzung RSIT vorbereiten"); self.assertEqual(t["title"], "Sitzung RSIT")

    def test_mehrdeutig_rueckfrage(self):
        t, k, g = self.wahl("Bereite die Sitzung mit Müller vor")
        self.assertIsNone(t); self.assertEqual([x["title"] for x in k], ["Jour fixe Daten", "Workshop Datenkatalog"]); self.assertIn("2 Termine", g)

    def test_mehrdeutig_mit_naechste(self):
        t, _, _ = self.wahl("Bereite die nächste Sitzung mit Müller vor"); self.assertEqual(t["title"], "Jour fixe Daten")

    def test_name_ohne_treffer(self):
        t, k, g = self.wahl("Bereite das Treffen mit Brunner vor")
        self.assertIsNone(t); self.assertEqual(len(k), 4); self.assertIn("keinen anstehenden Termin", g)

    def test_datum(self):
        t, k, g = self.wahl("Bereite meinen Termin morgen vor")
        self.assertIsNone(t); self.assertEqual(len(k), 2); self.assertIn("2 Termine", g)
        t, _, _ = self.wahl("Bereite den Termin übermorgen vor"); self.assertEqual(t["title"], "Workshop Datenkatalog")
        t, _, _ = self.wahl("Bereite den Termin morgen mit Meier vor"); self.assertEqual(t["title"], "KIAR Review")

    def test_datum_ohne_termin(self):
        t, k, g = self.wahl("Was steht am 01.01.2099 an?"); self.assertIsNone(t); self.assertIn("keinen anstehenden Termin", g)

if __name__ == "__main__": unittest.main()
