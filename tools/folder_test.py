# tools/folder_test.py — v23: liest die Outlook-Ordnerstruktur und misst GetTable (nur lesen, schreibt nichts).
# Aufruf in C:\aura:  python tools\folder_test.py      (AURA vorher schliessen)
import os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "vendor")]
import comtypes; comtypes.CoInitialize()
from aura.config import load_settings
from aura.connectors.base import outlook_namespace
from aura.connectors.outlook_mail import list_folders, resolve

ns = outlook_namespace()
t = time.perf_counter(); fl = list_folders(ns, print); t_tree = time.perf_counter() - t
st = resolve(fl, load_settings().get("mail_folders") or {})
for f in fl:
    if "error" in f: print(f"  FEHLER  {f['path']}: {f['error']}"); continue
    print(f"{'[x]' if st[f['eid']] else '[ ]'} {'  ' * f['depth']}{f['name']}  ({f['count']})")
print(f"\nStruktur: {sum('eid' in f for f in fl)} Ordner in {t_tree:.1f} s")
n = 0; t = time.perf_counter()
for f in fl:
    if "eid" in f and st[f["eid"]]:
        tb = ns.GetFolderFromID(f["eid"]).GetTable()
        while not tb.EndOfTable: tb.GetNextRow().Item("EntryID"); n += 1
dt = time.perf_counter() - t
print(f"GetTable: {n} EntryIDs in {dt:.1f} s ({n / dt if dt else 0:.0f}/s)")
