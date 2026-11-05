# tools/empfaenger_test.py — Version 20261105v201 (AURA). Prüft, ob Outlook To, CC und Empfängeradressen liefert und wie lange das dauert.
# Liest nur und gibt nur Anzahlen aus, keine Namen oder Adressen.
# Aufruf:  cd /d C:\\aura  und  py tools\\empfaenger_test.py [Anzahl Mails, Standard 50]
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for v in (ROOT / "vendor").glob("*"):                                 # mitgelieferte Pakete wie comtypes
    if v.is_dir(): sys.path.append(str(v))
sys.path.append(str(ROOT / "vendor"))
import comtypes; comtypes.CoInitialize()
from aura.connectors.base import outlook_namespace

def ordner(ns):
    inbox = ns.GetDefaultFolder(6)
    try: return inbox.Parent.Folders("Ablage")
    except Exception: pass
    try: return inbox.Folders("Ablage")
    except Exception: return inbox

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    f = ordner(outlook_namespace()); it = f.Items; it.Sort("[ReceivedTime]", True)
    mails = emp = to = cc = adr = 0; t0 = time.perf_counter(); m = it.GetFirst()
    while m is not None and mails < n:
        try:
            for i in range(1, m.Recipients.Count + 1):
                r = m.Recipients.Item(i); emp += 1
                to += r.Type == 1; cc += r.Type == 2
                try:
                    u = r.AddressEntry.GetExchangeUser(); a = u.PrimarySmtpAddress if u else r.Address
                except Exception: a = ""
                adr += "@" in (a or "")
            mails += 1
        except Exception: pass
        m = it.GetNext()
    d = time.perf_counter() - t0
    print(f"Mails {mails} | Empfänger {emp} | To {to} | CC {cc} | mit Adresse {adr} ({adr / max(1, emp):.0%})")
    print(f"Dauer {d:.1f} s | {d / max(1, mails):.2f} s je Mail | hochgerechnet auf 7600 Mails: {d / max(1, mails) * 7600 / 60:.0f} min")

if __name__ == "__main__": main()
