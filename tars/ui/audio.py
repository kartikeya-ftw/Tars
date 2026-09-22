import sys
import time
import threading
from tars.config import config

try:
    if sys.platform == "win32":
        import winsound
    else:
        winsound = None
except ImportError:
    winsound = None

class AudioEngine:
    def __init__(self):
        self.available = (winsound is not None)

    def _play(self, freq: int, duration_ms: int):
        if not self.available or not config.sound_enabled:
            return
        try:
            winsound.Beep(freq, duration_ms)
        except Exception:
            pass

    def _run_async(self, target, *args):
        if not self.available or not config.sound_enabled:
            return
        threading.Thread(target=target, args=args, daemon=True).start()

    def cue_light(self):
        """Crisp robotic double-chirp for cue light."""
        def _task():
            self._play(1800, 45)
            time.sleep(0.03)
            self._play(2400, 60)
        self._run_async(_task)

    def morse_dot(self):
        """Short Morse code tone."""
        self._play(750, 65)

    def morse_dash(self):
        """Long Morse code tone."""
        self._play(750, 195)

    def thruster_pulse(self):
        """Low frequency RCS thruster burst."""
        def _task():
            self._play(180, 80)
        self._run_async(_task)

    def dock_lock(self):
        """Harmonic triad when docking lock is achieved."""
        def _task():
            for f in (523, 659, 784, 1046):
                self._play(f, 60)
                time.sleep(0.02)
        self._run_async(_task)

    def warning_beep(self):
        """Emergency alarm tone."""
        def _task():
            self._play(1200, 100)
            time.sleep(0.05)
            self._play(900, 100)
        self._run_async(_task)

    def key_tick(self):
        """Subtle mechanical terminal key feedback."""
        def _task():
            self._play(2800, 12)
        self._run_async(_task)

audio = AudioEngine()
