# aura/stt_gui.py — Werkzeug «Spracheingabe (Test)». Version 20261104v175
# Misst Whisper auf der GPU (engine/whisper_dml.py). Aufnahme ueber Windows-MCI (winmm, keine Zusatz-DLL).
# Die Aufnahme bleibt lokal in data\stt und wird nach der Auswertung geloescht.
import ctypes, threading, time, tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
from .config import DATA, MODELS

F = "Segoe UI"
def font(s=13, w="normal"): return ctk.CTkFont(family=F, size=s, weight=w)
ACCENT, ACCENT_HI = "#B3121D", "#8E0E17"
MUTED = ("#525A50", "#A3AD9F")
PFLICHT = ("model.safetensors", "config.json", "vocab.json", "added_tokens.json")

def mci(cmd):
    buf = ctypes.create_unicode_buffer(256)
    r = ctypes.windll.winmm.mciSendStringW(cmd, buf, 255, 0)
    if r:
        e = ctypes.create_unicode_buffer(256); ctypes.windll.winmm.mciGetErrorStringW(r, e, 255)
        raise OSError(e.value or f"MCI-Fehler {r}")
    return buf.value


class SttWindow:
    def __init__(self, app):
        self.app = app; self.body = app.view("stt", "Werkzeuge › Spracheingabe (Test)")
        self.body.grid_columnconfigure(0, weight=1); self.body.grid_rowconfigure(2, weight=1)
        self.engine = None; self.rec = False; self.busy = False; self.t_rec = 0
        ctk.CTkLabel(self.body, text="Sprich bis 30 Sekunden, dann Stopp. Alles läuft lokal; die Aufnahme wird danach gelöscht.",
                     font=font(12), text_color=MUTED, anchor="w").grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        bar = ctk.CTkFrame(self.body, fg_color="transparent"); bar.grid(row=1, column=0, sticky="w", padx=16)
        self.b_rec = ctk.CTkButton(bar, text="🎙 Aufnahme", command=self.toggle, fg_color=ACCENT, hover_color=ACCENT_HI, font=font())
        self.b_rec.pack(side="left", padx=(0, 8))
        self.b_file = ctk.CTkButton(bar, text="WAV-Datei wählen", command=self.pick, fg_color="transparent", border_width=1,
                                    text_color=("#1C211C", "#E8ECE4"), font=font())
        self.b_file.pack(side="left", padx=(0, 8))
        self.b_free = ctk.CTkButton(bar, text="Modell entladen", command=self.free, fg_color="transparent", border_width=1,
                                    text_color=("#1C211C", "#E8ECE4"), font=font())
        self.b_free.pack(side="left")
        self.txt = ctk.CTkTextbox(self.body, font=font(14), wrap="word"); self.txt.grid(row=2, column=0, sticky="nsew", padx=16, pady=10)
        self.stat = ctk.CTkLabel(self.body, text="", font=font(11), text_color=MUTED, anchor="w", justify="left", wraplength=800)
        self.stat.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 12))
        self.model = MODELS / "whisper-base"
        fehlt = [f for f in PFLICHT if not (self.model / f).exists()]
        if fehlt: self.say(f"Im Ordner {self.model} fehlt: {', '.join(fehlt)}"); self.b_rec.configure(state="disabled"); self.b_file.configure(state="disabled")

    def alive(self):
        try: return bool(self.body.winfo_exists())
        except tk.TclError: return False
    def say(self, s): self.body.after(0, lambda: self.stat.configure(text=s))
    def show(self, s):
        def f(): self.txt.delete("1.0", "end"); self.txt.insert("1.0", s)
        self.body.after(0, f)

    def toggle(self):
        if self.busy: return
        try:
            if not self.rec:
                try: mci("close aura_rec")
                except OSError: pass
                mci("open new Type waveaudio Alias aura_rec")
                mci("set aura_rec bitspersample 16 channels 1 samplespersec 16000 alignment 2 bytespersec 32000")
                mci("record aura_rec"); self.rec = True; self.t_rec = time.time()
                self.b_rec.configure(text="⏹ Stopp", fg_color="#C0392B"); self.say("Aufnahme läuft …")
            else:
                d = DATA / "stt"; d.mkdir(exist_ok=True); w = d / "aufnahme.wav"
                mci("stop aura_rec"); mci(f'save aura_rec "{w}"'); mci("close aura_rec"); self.rec = False
                self.b_rec.configure(text="🎙 Aufnahme", fg_color=ACCENT); self.run(w, True)
        except OSError as e:
            self.rec = False; self.b_rec.configure(text="🎙 Aufnahme", fg_color=ACCENT); self.say(f"Mikrofon: {e}")

    def pick(self):
        p = filedialog.askopenfilename(filetypes=[("WAV", "*.wav")])
        if p and not self.busy: self.run(p, False)

    def run(self, wav, temp):
        self.busy = True
        def job():
            from pathlib import Path
            try:
                if self.engine is None:
                    from .engine.whisper_dml import Whisper
                    self.say("Modell wird geladen …"); w = Whisper(self.model, progress=self.say); w.load(); self.engine = w
                self.say("Wird ausgewertet …"); t0 = time.perf_counter()
                text = self.engine.transcribe(wav, self.show); ges = time.perf_counter() - t0
                self.show(text); t = self.engine.timing; a = max(t.get("audio", 1), .01)
                self.say(f"{a:.1f} s Audio in {ges:.1f} s (Faktor {ges / a:.2f}) · Laden {self.engine.load_s:.1f} s · Mel {t['mel']:.1f} · "
                         f"Encoder {t['encoder']:.1f} · Prompt {t['prompt']:.1f} · Decoder {t['decoder']:.1f} s für {t['tokens']} Tokens · Teile {t['teile']}")
            except Exception as e:
                w = self.engine; self.engine = None
                self.say(f"Fehler ({getattr(w, 'stage', 'Laden')}): {e} · bisherige Teile: {w.timing.get('teile', '-') if w else '-'}")
            finally:
                self.busy = False
                if temp:
                    try: Path(wav).unlink()
                    except OSError: pass
        threading.Thread(target=job, daemon=True).start()

    def free(self):
        if self.engine is None or self.busy: return
        self.engine.close(); self.engine = None; self.say("Modell entladen.")
