# aura/mikrofon.py — Spracheingabe im Chat. Version 20261117v266 (v266: Klasse Memo)
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

def schweiz(text):
    """v266: Schweizer Rechtschreibung – ß wird ss (abschaltbar mit "stt_eszett": true in settings.json)."""
    from .config import load_settings
    if load_settings().get("stt_eszett"): return text
    return text.replace("ß", "ss").replace("ẞ", "SS")

STT_MODELLE = ("whisper-large-v3-turbo", "whisper-small", "whisper-base")   # v266: bestes vorhandenes zuerst

def modell():
    """Einstellung «stt_modell» (Ordnername unter «models»), sonst das erste vorhandene aus STT_MODELLE.
    Weitere Ordner whisper-* (z.B. ein Schweizerdeutsch-Modell) gehen über die Einstellung."""
    from .config import load_settings
    wahl = (load_settings().get("stt_modell") or "").strip()
    for n in ((wahl,) if wahl else ()) + STT_MODELLE:
        d = MODELS / n
        if n and (d / "model.safetensors").exists(): return d
    return None


class Mikrofon:
    def __init__(self, app):
        self.app = app; self.b = app.b_mic; self.engine = None
        self.rec = False; self.busy = False; self.res = None; self.t0 = 0
        self.farbe = self.b.cget("fg_color")

    def say(self, s): self.app.status.configure(text=s)

    def toggle(self):
        if self.busy: return
        m = getattr(self.app, "memo", None)                             # v266: nicht gleichzeitig mit einem Memo
        if m and (m.rec or m.busy): return
        if self.rec: self.stop(); return
        if modell() is None:
            self.say(f"Spracheingabe: kein Modell gefunden (z.B. Ordner {MODELS / 'whisper-small'})."); return
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
            t = time.perf_counter(); text = schweiz(self.engine.transcribe(wav))
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


# ---------------------------------------------------------------- v266: Memo
MEMO_MAX_S = 600                                                      # 10 Minuten je Memo

def _vorschlag(text):
    """Titel ohne Sprachmodell: die ersten Wörter des ersten Satzes."""
    import re
    satz = re.split(r"(?<=[.!?])\s", text.strip(), 1)[0]
    w = satz.split()[:6]
    return " ".join(w).rstrip(".,;:!?") or "Memo"


class Memo:
    """Knopf «📝 Memo» oben in der Leiste: aufnehmen (bis 10 min), erkennen, Text und Titel prüfen, als Markdown speichern.
    Teilt die Whisper-Engine mit der Spracheingabe (nur einmal im GPU-Speicher)."""
    def __init__(self, app, mic):
        self.app, self.mic = app, mic; self.b = app.b_memo
        self.rec = False; self.busy = False; self.res = None; self.t0 = 0; self.dlg = None
        self.farbe = self.b.cget("fg_color"); self.ink = self.b.cget("text_color"); self.status = ""

    def say(self, s): self.app.status.configure(text=s)

    def toggle(self):
        if self.busy or self.mic.rec or self.mic.busy: return
        if self.rec: self.stop(); return
        if modell() is None:
            self.say(f"Memo: kein Spracherkennungsmodell gefunden (Ordner {MODELS / 'whisper-small'})."); return
        try:
            try: mci("close aura_memo")
            except OSError: pass
            mci("open new Type waveaudio Alias aura_memo")
            mci("set aura_memo bitspersample 16 channels 1 samplespersec 16000 alignment 2 bytespersec 32000")
            mci("record aura_memo")
        except OSError as e: self.say(f"Memo: {e}"); return
        self.rec = True; self.t0 = time.time(); self.b.configure(text="⏹ 0:00", fg_color=FARBE_AUF, text_color="#FFFFFF"); self._tick()

    def _tick(self):
        if not self.rec: return
        s = time.time() - self.t0
        if s >= MEMO_MAX_S: self.stop(); return
        self.b.configure(text=f"⏹ {int(s) // 60}:{int(s) % 60:02d}")
        self.say(f"📝 Memo-Aufnahme … {int(s) // 60}:{int(s) % 60:02d} von {MEMO_MAX_S // 60}:00. Nochmals klicken zum Beenden.")
        self.b.after(500, self._tick)

    def stop(self):
        self.rec = False; self.b.configure(text="📝 Memo", fg_color=self.farbe, text_color=self.ink)
        d = DATA / "stt"; d.mkdir(exist_ok=True); wav = d / "memo.wav"
        try: mci("stop aura_memo"); mci(f'save aura_memo "{wav}"'); mci("close aura_memo")
        except OSError as e: self.say(f"Memo: {e}"); return
        self.busy = True; self.res = None; self.b.configure(text="⏳ Memo"); self.status = "Memo wird erkannt …"
        threading.Thread(target=self._job, args=(wav,), daemon=True).start(); self.b.after(200, self._poll)

    def _job(self, wav):
        try:
            if self.mic.engine is None:
                self.status = "Spracherkennung wird geladen …"
                from .engine.whisper_dml import Whisper
                w = Whisper(modell(), progress=lambda *_: None); w.load(); self.mic.engine = w
            t = time.perf_counter()
            def prog(txt, *_): self.status = f"Memo wird erkannt … {txt}"
            text = schweiz(self.mic.engine.transcribe_lang(wav, progress=prog))
            try:
                from . import log
                tm = self.mic.engine.timing
                log.get().info(f"Memo: {modell().name}, {tm.get('audio', 0):.1f} s Audio, {time.perf_counter() - t:.1f} s, "
                               f"Abschnitte {tm.get('abschnitte')}")
            except Exception: pass
            self.res = (text, time.perf_counter() - t, None)
        except Exception as e:
            w, self.mic.engine = self.mic.engine, None
            try:
                if w: w.close()
            except Exception: pass
            self.res = ("", 0, e)
        finally:
            try: wav.unlink()
            except OSError: pass

    def _poll(self):
        if self.res is None: self.say(self.status); self.b.after(300, self._poll); return
        text, s, err = self.res; self.busy = False; self.b.configure(text="📝 Memo")
        if err: self.say(f"Memo fehlgeschlagen: {err}"); return
        if not text: self.say("Memo: es wurde nichts erkannt."); return
        self.say(f"Memo erkannt mit {modell().name} ({s:.0f} s). Bitte prüfen und speichern.")
        self._dialog(text)
        self.app.w.submit("memo_titel", text, self.app.s.get("llm", "extractive"))

    # ---- Prüfen und speichern
    def _dialog(self, text):
        import customtkinter as ctk
        from datetime import datetime
        from .connectors.memos import ordner
        self.wann = datetime.now(); self.titel_geaendert = False
        w = self.dlg = ctk.CTkToplevel(self.app.root); w.title("Memo prüfen"); w.geometry("760x560"); w.transient(self.app.root)
        w.grid_columnconfigure(0, weight=1); w.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(w, text=f"Titel  ·  {self.wann:%d.%m.%Y}", anchor="w").grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
        self.e_titel = ctk.CTkEntry(w, corner_radius=0); self.e_titel.grid(row=1, column=0, sticky="ew", padx=16)
        self.e_titel.insert(0, _vorschlag(text)); self.e_titel.bind("<Key>", lambda e: setattr(self, "titel_geaendert", True))
        ctk.CTkLabel(w, text="Text (Erkennung kann Fehler enthalten – bitte prüfen)", anchor="w").grid(
            row=2, column=0, sticky="ew", padx=16, pady=(12, 2))
        self.t_text = ctk.CTkTextbox(w, wrap="word", corner_radius=0); self.t_text.grid(row=3, column=0, sticky="nsew", padx=16)
        self.t_text.insert("1.0", text)
        ctk.CTkLabel(w, text=f"Ablage: {ordner(self.app.s)}", anchor="w", justify="left", wraplength=720).grid(
            row=4, column=0, sticky="ew", padx=16, pady=(8, 0))
        unten = ctk.CTkFrame(w, fg_color="transparent"); unten.grid(row=5, column=0, sticky="ew", padx=16, pady=12)
        ctk.CTkButton(unten, text="Verwerfen", width=100, corner_radius=0, fg_color="transparent", border_width=1,
                      command=self._verwerfen).pack(side="right")
        ctk.CTkButton(unten, text="Speichern", width=100, corner_radius=0, command=self._speichern).pack(side="right", padx=8)
        w.protocol("WM_DELETE_WINDOW", self._verwerfen); w.after(100, w.lift)

    def titel_vom_modell(self, t):
        """Ereignis «memo_titel» vom Worker: ersetzt den Vorschlag, solange der Benutzer nichts geändert hat."""
        if self.dlg is None or not self.dlg.winfo_exists() or self.titel_geaendert: return
        self.e_titel.delete(0, "end"); self.e_titel.insert(0, t)

    def _verwerfen(self):
        from tkinter import messagebox
        if self.dlg is None: return
        if not messagebox.askyesno("Memo", "Memo verwerfen? Der Text geht verloren.", parent=self.dlg): return
        self.dlg.destroy(); self.dlg = None; self.say("Memo verworfen.")

    def _speichern(self):
        from tkinter import messagebox
        from .connectors.memos import speichern
        titel = self.e_titel.get().strip() or "Memo"; text = self.t_text.get("1.0", "end").strip()
        if not text: messagebox.showwarning("Memo", "Der Text ist leer.", parent=self.dlg); return
        try: p = speichern(self.app.s, titel, text, self.wann)
        except Exception as e: messagebox.showerror("Memo", f"Nicht gespeichert: {e}", parent=self.dlg); return
        self.dlg.destroy(); self.dlg = None
        self.say(f"Memo an {p.name} angehängt – wird eingelesen."); self.app.w.submit("memo_einlesen")
        mw = getattr(self.app, "memowin", None)                         # Werkzeuge › Memos offen -> Liste nachführen
        if mw is not None and mw.alive(): mw.refresh()
