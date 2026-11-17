# tests/test_v269.py — Live-Antwort: Zusammenfassung sichtbar, Einzelergebnisse je Quelle im Akkordeon
import sys, types, unittest
sys.modules.setdefault("winreg", types.ModuleType("winreg"))
try:
    from aura import gui
except Exception as e:                                    # ohne tkinter/customtkinter nicht prüfbar
    gui = None; GRUND = str(e)

T = """— Lokal —
Mail A
Mail B

— Acta Nova —
1  Dossier X

— Zusammenfassung über alle Quellen —
Das Projekt läuft [1]."""

@unittest.skipIf(gui is None, "GUI-Module fehlen")
class Abschnitte(unittest.TestCase):
    def teile(self, t):
        f = types.SimpleNamespace(KOPF=gui.App.KOPF)
        return gui.App._abschnitte(f, t)

    def test_live(self):
        zf, t = self.teile(T)
        self.assertEqual(zf, "— Zusammenfassung über alle Quellen —\\nDas Projekt läuft [1].")
        self.assertEqual([n for n, _ in t], ["Lokal", "Acta Nova"]); self.assertEqual(t[0][1], "Mail A\\nMail B")

    def test_ohne_zusammenfassung(self):
        x = "— Lokal —\\nMail A\\n\\n— Acta Nova —\\n1  Dossier X"
        self.assertEqual(self.teile(x), (x, []))
        self.assertEqual(self.teile("Normale Antwort."), ("Normale Antwort.", []))

if __name__ == "__main__": unittest.main()
