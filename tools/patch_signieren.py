# tools/patch_signieren.py — Update-ZIP signieren (NUR auf dem Release-Rechner, NICHT auf Arbeitsplätzen). Version 20261108v208
# Schlüssel erzeugen (einmalig; geheime Datei sicher und AUSSERHALB von C:\aura und Git aufbewahren):
#     py tools\patch_signieren.py --neuer-schluessel D:\sicher\aura_update.key
#   -> gibt den öffentlichen Schlüssel (hex) aus. Diesen per Gruppenrichtlinie verteilen:
#      HKLM\SOFTWARE\Policies\AURA  REG_SZ  UpdateSchluessel = <hex>
# Signieren:  py tools\patch_signieren.py AURA_patch_xyz.zip D:\sicher\aura_update.key
#   -> schreibt _manifest.json (SHA-256 aller Dateien) und _manifest.sig in eine Kopie <name>_signiert.zip.
import json, os, secrets, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aura import ed25519, VERSION                                     # noqa: E402
from aura.sicherheit import zip_pruefen, zip_sha256, zip_lesen         # noqa: E402

def signieren(zp, sk, ziel=None):
    zp = Path(zp); ziel = Path(ziel) if ziel else zp.with_name(zp.stem + "_signiert.zip")
    with zipfile.ZipFile(zp) as z, zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as o:
        infos = [i for i in zip_pruefen(z) if i.filename not in ("_manifest.json", "_manifest.sig")]
        m = {"format": 1, "aura_version": VERSION, "dateien": {i.filename: zip_sha256(z, i) for i in infos}}
        mb = json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
        for i in infos: o.writestr(i.filename, zip_lesen(z, i))
        o.writestr("_manifest.json", mb); o.writestr("_manifest.sig", ed25519.sign(sk, mb).hex())
    return ziel

def main(a):
    if len(a) == 2 and a[0] == "--neuer-schluessel":
        k = Path(a[1])
        if k.exists(): print("Datei existiert schon – nicht überschrieben."); return 1
        sk = secrets.token_bytes(32)
        fd = os.open(k, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f: f.write(sk.hex())
        print("Öffentlicher Schlüssel (für die Richtlinie UpdateSchluessel):\n" + ed25519.public_key(sk).hex()); return 0
    if len(a) == 2:
        sk = bytes.fromhex(Path(a[1]).read_text().strip())
        print("Signiert:", signieren(a[0], sk)); return 0
    print(__doc__ or "Aufruf siehe Kopf der Datei"); return 1

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
