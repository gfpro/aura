# aura/mikrofon.py — Spracheingabe im Chat. Version 20261104v182
# Aufnahme ueber Windows-MCI (winmm), Whisper auf der GPU (engine/whisper_dml.py), Text ins Eingabefeld (nie automatisch senden).
# Whisper wird beim ersten Diktat geladen und bleibt geladen. Die Aufnahme wird nach der Auswertung geloescht.
import ctypes, threading, time
from .config import DATA, MODELS

MAX_S = 30
FARBE_AUF = "#C0392B"

def mci(cmd):
    r = ctypes.windll.winmm.mciSendStringW(cmd, None, 0, 0)
    if r:
        e = ctypes.create_unicode_buffer(256); ctypes.windll.winmm.mciGetErrorStringW(r, e, 255)
        raise OSError(e.value or f"MCI-Fehler {r}")

def modell():
    for n in ("whisper-small", "whisper-base"):
        d = MODELS / n
        if (d / "model.safetensors").exists(): return d
    return None


class Mikrofon:
    def __init__(self, app):
        self.app = app; self.b = app.b_mic; self.engine = None
        self.rec = False; self.busy = False; self.res = None; self.t0 = 0
        self.farbe = self.b.cget("fg_color")

    def say(self, s): self.app.status.configure(text=s)

    def toggle(self):
        if self.busy: return
        if self.rec: self.stop(); return
        if modell() is None:
            self.say(f"Spracheingabe: kein Modell gefunden (Ordner {MODELS / 'whisper-small'})."); return
        try:
            try: mci("close aura_rec")
            except OSError: pass
            mci("open new Type waveaudio Alias aura_rec")
            mci("set aura_rec bitspersample 16 channels 1 samplespersec 16000 alignment 2 bytespersec 32000")
            mci("record aura_rec")
        except OSError as e: self.say(f"Mikrofon: {e}"); return
        self.rec = True; self.t0 = time.time(); self.b.configure(text="\uE71A", fg_color=FARBE_AUF); self._tick()

    def _tick(self):
        if not self.rec: return
        s = time.time() - self.t0
        if s >= MAX_S: self.stop(); return
        self.say(f"🎙 Aufnahme läuft … {int(s)} s von {MAX_S} s. Nochmals klicken zum Beenden.")
        self.b.after(300, self._tick)

    def stop(self):
        self.rec = False; self.b.configure(text="\uE720", fg_color=self.farbe)
        d = DATA / "stt"; d.mkdir(exist_ok=True); wav = d / "aufnahme.wav"
        try: mci("stop aura_rec"); mci(f'save aura_rec "{wav}"'); mci("close aura_rec")
        except OSError as e: self.say(f"Mikrofon: {e}"); return
        self.busy = True; self.res = None; self.b.configure(text="\uE895")
        self.say("Sprache wird erkannt …" if self.engine else "Spracherkennung wird geladen …")
        threading.Thread(target=self._job, args=(wav,), daemon=True).start(); self.b.after(100, self._poll)

    def _job(self, wav):
        try:
            if self.engine is None:
                from .engine.whisper_dml import Whisper
                w = Whisper(modell(), progress=lambda *_: None); w.load(); self.engine = w
            t = time.perf_counter(); text = self.engine.transcribe(wav)
            self.res = (text, time.perf_counter() - t, None)
        except Exception as e:
            w, self.engine = self.engine, None
            try:
                if w: w.close()
            except Exception: pass
            self.res = ("", 0, e)
        finally:
            try: wav.unlink()
            except OSError: pass

    def _poll(self):
        if self.res is None: self.b.after(100, self._poll); return
        text, s, err = self.res; self.busy = False; self.b.configure(text="\uE720")
        if err: self.say(f"Spracheingabe fehlgeschlagen: {err}"); return
        if not text: self.say("Es wurde nichts erkannt."); return
        e = self.app.entry; alt = e.get("1.0", "end").strip()
        e.insert("end", (" " if alt else "") + text); e.focus_set()
        self.say(f"Text eingefügt ({s:.1f} s). Prüfen, dann Enter zum Senden.")
