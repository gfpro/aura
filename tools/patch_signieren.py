# tools/patch_signieren.py — Update-ZIP signieren (NUR auf dem Release-Rechner, NICHT auf Arbeitsplätzen). Version 20261116v249
# v249 (H4): aura_version im Manifest = Version IM PAKET (aura\\__init__.py), nicht die des Signier-Rechners. Ein Paket ohne
#   aura\\__init__.py wird nicht signiert – ohne Versionsangabe gäbe es keinen Schutz gegen das Einspielen alter Pakete.
# Schlüssel erzeugen (einmalig; geheime Datei sicher und AUSSERHALB von C:\aura und Git aufbewahren):
#     py tools\patch_signieren.py --neuer-schluessel D:\sicher\aura_update.key
#   -> gibt den öffentlichen Schlüssel (hex) aus. Diesen per Gruppenrichtlinie verteilen:
#      HKLM\SOFTWARE\Policies\AURA  REG_SZ  UpdateSchluessel = <hex>
# Signieren:  py tools\patch_signieren.py AURA_patch_xyz.zip D:\sicher\aura_update.key
#   -> schreibt _manifest.json (SHA-256 aller Dateien) und _manifest.sig in eine Kopie <name>_signiert.zip.
import json, os, secrets, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aura import ed25519                                              # noqa: E402
from aura.sicherheit import zip_pruefen, zip_sha256, zip_lesen         # noqa: E402

def signieren(zp, sk, ziel=None):
    import re
    zp = Path(zp); ziel = Path(ziel) if ziel else zp.with_name(zp.stem + "_signiert.zip")
    with zipfile.ZipFile(zp) as z:
        infos = [i for i in zip_pruefen(z) if i.filename not in ("_manifest.json", "_manifest.sig")]
        init = next((i for i in infos if i.filename.casefold() == "aura/__init__.py"), None)
        v = re.search(r'VERSION\s*=\s*["\'](\d{8}v\d+)["\']', zip_lesen(z, init, 2**20).decode("utf-8", "replace")) if init else None
        if not v: raise ValueError('Nicht signiert: Das Paket enthält keine aura\\__init__.py mit VERSION = "JJJJMMTTvNN".')
        m = {"format": 1, "aura_version": v.group(1), "dateien": {i.filename: zip_sha256(z, i) for i in infos}}
        mb = json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
        with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as o:
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
        try: print("Signiert:", signieren(a[0], sk)); return 0
        except ValueError as e: print(e); return 1
    print(__doc__ or "Aufruf siehe Kopf der Datei"); return 1

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
