# tools/whisper_test.py — Whisper-Messung ohne GUI (v177).
# Aufruf:  py tools\whisper_test.py            -> 10 s Aufnahme vom Mikrofon, danach Datei geloescht
#          py tools\whisper_test.py datei.wav [modellordner]   ("-" statt Datei = Aufnahme)
import ctypes, os, sys, time
from pathlib import Path
R = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(R))
from aura.engine.whisper_dml import Whisper

def mci(c):
    r = ctypes.windll.winmm.mciSendStringW(c, None, 0, 0)
    if r: raise OSError(f"MCI-Fehler {r}: {c}")

wav = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "-" else None; temp = wav is None
m = sys.argv[2] if len(sys.argv) > 2 else R / "models" / "whisper-base"
w = Whisper(m); w.load()
if temp:
    wav = str(R / "data" / "whisper_test.wav")
    mci("open new Type waveaudio Alias t")
    mci("set t bitspersample 16 channels 1 samplespersec 16000 alignment 2 bytespersec 32000")
    input("Enter startet 10 s Aufnahme ..."); mci("record t"); print("Sprich jetzt ..."); time.sleep(10)
    mci("stop t"); mci(f'save t "{wav}"'); mci("close t")
try:
    t = time.perf_counter(); print("TEXT:", w.transcribe(wav, lambda s: print("\r" + s[-90:], end="", flush=True)))
    print(f"Gesamt {time.perf_counter() - t:.1f} s", w.timing)
except Exception as e:
    print("\nFEHLER in", w.stage, ":", e, w.timing); raise
finally:
    if temp and os.path.exists(wav): os.remove(wav)
    w.close()
