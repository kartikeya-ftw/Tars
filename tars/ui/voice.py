"""
TARS - Voice I/O

Speech output goes through edge-tts neural voices when available and falls back
to Windows SAPI otherwise. Speech input has two modes: a one-shot capture, and a
persistent recogniser that keeps a single process alive for wake-word listening.

Why it changed:

  - Microsoft David Desktop is a 2010-era SAPI voice, and it was the loudest
    signal that this was a hobby script. edge-tts gives neural voices for the
    cost of one pip install.
  - speak() was a fire-and-forget daemon thread with no handle, so speech could
    not be interrupted. Playback now runs as a tracked subprocess and stop()
    kills it, which is what makes barge-in possible.
  - listen() spawned a fresh PowerShell process per call, paying ~1s of startup
    for every 6s listening window. WakeListener starts the recogniser once and
    streams recognised phrases over stdout for as long as it runs.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from tars.config import config
from tars.ui import theme as T
from tars.ui.audio import audio

console = Console()

CACHE_DIR = Path(tempfile.gettempdir()) / "tars_voice_cache"
# Bounded so a long session cannot fill the temp directory.
CACHE_MAX_FILES = 120

# Short phrases TARS uses to acknowledge that it has started real work, so the
# ReAct loop does not run in silence. Cached after first synthesis, so they come
# back instantly.
ACK_PHRASES = [
    "On it.",
    "Working.",
    "Give me a moment.",
    "Looking into it.",
]


def _ps_script(body: str, params: Optional[dict] = None) -> str:
    """
    Builds a PowerShell script with operands passed as base64 literals.

    Same reasoning as tars.core.host._ps: the base64 alphabet cannot terminate a
    single-quoted PowerShell string, so text can never be read as code.
    """
    prelude = ["[Console]::OutputEncoding = [System.Text.Encoding]::UTF8"]
    for name, value in (params or {}).items():
        blob = base64.b64encode(str(value).encode("utf-8")).decode("ascii")
        prelude.append(
            f"${name} = [System.Text.Encoding]::UTF8.GetString("
            f"[System.Convert]::FromBase64String('{blob}'))"
        )
    return "\n".join(prelude + [body])


class VoiceEngine:
    """Speech synthesis with an interruptible playback channel."""

    def __init__(self) -> None:
        self._speaking = threading.Event()
        self._playback: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        # Monotonic utterance id. Killing the playback process is not enough on
        # its own: synthesis takes a second or two, and an interruption arriving
        # in that window has no process to kill yet. Every utterance captures the
        # generation it was issued under and abandons itself if that has moved on.
        self._generation = 0
        self._ack_index = 0
        # Flipped to False the first time edge-tts or mp3 playback fails, so a
        # broken install degrades to SAPI once instead of on every utterance.
        self._edge_healthy: Optional[bool] = None
        self._last_spoken: str = ""

    # ─── State ──────────────────────────────────────────────────────────────

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    @property
    def last_spoken(self) -> str:
        """The most recent utterance, used to recognise microphone echo."""
        return self._last_spoken

    def engine_name(self) -> str:
        if config.tts_engine == "sapi":
            return "windows sapi"
        if self._edge_healthy is False:
            return "windows sapi (edge-tts unavailable)"
        if self._edge_healthy is None:
            return f"edge-tts {config.tts_voice} (untested)"
        return f"edge-tts {config.tts_voice}"

    # ─── Text preparation ───────────────────────────────────────────────────

    def clean_text_for_speech(self, text: str, max_chars: int = 450) -> str:
        """Strips markdown, box art, URLs, headers, and code symbols for natural TTS."""
        cleaned = re.sub(r"\[● CUE LIGHT ON\]", "", text)
        cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
        cleaned = re.sub(r"`[^`]*`", "", cleaned)
        cleaned = re.sub(r"\[.*?\]", "", cleaned)
        cleaned = re.sub(r"https?://\S+", "", cleaned)
        cleaned = re.sub(r"[─│╭╰╔╗═╚╝├┤┬┴┼║█▀▄▌▐░▒▓►◄▲▼◆◇●○•★☆]", " ", cleaned)
        cleaned = re.sub(r"#{1,6}\s*", "", cleaned)
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
        cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
        cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
        cleaned = re.sub(r"\|+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if len(cleaned) > max_chars:
            cut = cleaned[:max_chars]
            last_punct = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
            cleaned = cut[: last_punct + 1] if last_punct > 120 else cut + "..."

        return cleaned

    # ─── Synthesis ──────────────────────────────────────────────────────────

    def _cache_path(self, text: str, rate: Optional[str] = None,
                    pitch: Optional[str] = None) -> Path:
        # Prosody is part of the key: the same sentence spoken gently and spoken
        # briskly are different audio, and must not collide in the cache.
        key = (
            f"{text}|{config.tts_voice}"
            f"|{rate or config.tts_rate}|{pitch or config.tts_pitch}"
        )
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return CACHE_DIR / f"{digest}.mp3"

    def _prune_cache(self) -> None:
        try:
            files = sorted(CACHE_DIR.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
            for stale in files[:-CACHE_MAX_FILES]:
                stale.unlink(missing_ok=True)
        except OSError:
            pass

    def _synthesize_edge(self, text: str, rate: Optional[str] = None,
                         pitch: Optional[str] = None) -> Optional[Path]:
        """
        Renders `text` to an mp3 with edge-tts. Returns None if unavailable.

        `rate` and `pitch` override the configured baseline for this utterance
        only, which is how the affective layer makes bad news sound slower and
        lower without permanently retuning the operator's voice settings.
        """
        if config.tts_engine == "sapi":
            return None
        try:
            import edge_tts
        except ImportError:
            if self._edge_healthy is None:
                console.print(T.hint("edge-tts not installed, using Windows SAPI voice"))
                console.print(T.hint("pip install edge-tts   for a neural voice"))
            self._edge_healthy = False
            return None

        out = self._cache_path(text, rate, pitch)
        if out.exists() and out.stat().st_size > 0:
            # A cached file is proof the neural path worked at least once, so the
            # engine should not still describe itself as untested.
            self._edge_healthy = True
            return out

        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".part")

            async def _render() -> None:
                comm = edge_tts.Communicate(
                    text,
                    voice=config.tts_voice,
                    rate=rate or config.tts_rate,
                    pitch=pitch or config.tts_pitch,
                )
                await comm.save(str(tmp))

            # A dedicated loop per utterance: this runs on a worker thread that
            # has no loop of its own, and the cost is negligible next to network
            # synthesis.
            asyncio.run(_render())

            if not tmp.exists() or tmp.stat().st_size == 0:
                tmp.unlink(missing_ok=True)
                raise RuntimeError("edge-tts produced no audio")

            tmp.replace(out)
            self._edge_healthy = True
            self._prune_cache()
            return out
        except Exception as ex:
            if self._edge_healthy is not False:
                console.print(T.hint(f"neural voice unavailable ({type(ex).__name__}), falling back to SAPI"))
            self._edge_healthy = False
            return None

    # ─── Playback ───────────────────────────────────────────────────────────

    _PLAY_MP3 = """
Add-Type -AssemblyName PresentationCore
$player = New-Object System.Windows.Media.MediaPlayer
$player.Open([uri]$AudioPath)
$waited = 0
while (-not $player.NaturalDuration.HasTimeSpan -and $waited -lt 3000) {
    Start-Sleep -Milliseconds 50
    $waited += 50
}
if ($player.NaturalDuration.HasTimeSpan) {
    $ms = $player.NaturalDuration.TimeSpan.TotalMilliseconds
} else {
    throw 'could not determine audio duration'
}
$player.Volume = 1.0
$player.Play()
Start-Sleep -Milliseconds ([int]$ms + 180)
$player.Stop()
$player.Close()
"""

    _SPEAK_SAPI = """
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try { $synth.SelectVoice("Microsoft David Desktop") } catch {
    try { $synth.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Male) } catch {}
}
$synth.Rate = 0
$synth.Volume = 100
$synth.Speak($Utterance)
"""

    def _spawn(self, script: str, params: dict, timeout: int) -> bool:
        """Runs a playback script as a tracked subprocess. Returns success."""
        try:
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _ps_script(script, params)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except Exception:
            return False

        with self._lock:
            self._playback = proc

        try:
            _out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            return False
        finally:
            with self._lock:
                if self._playback is proc:
                    self._playback = None

        # A kill from stop() surfaces as a non-zero return; that is a successful
        # interruption, not a playback failure.
        return proc.returncode == 0 or proc.returncode is None

    def _kill_playback(self) -> bool:
        """Terminates the playback process, if one is running."""
        with self._lock:
            proc = self._playback
            self._playback = None
        if proc is None:
            return False
        try:
            proc.kill()
            return True
        except Exception:
            return False

    def _superseded(self, generation: int) -> bool:
        with self._lock:
            return self._generation != generation

    def stop(self) -> bool:
        """
        Interrupts speech in progress. This is what makes barge-in work: the
        operator can talk over TARS instead of waiting for it to finish.

        Bumping the generation cancels an utterance that has not started playing
        yet, so interrupting during synthesis works as well as interrupting
        mid-sentence.
        """
        was_active = self._speaking.is_set()
        with self._lock:
            self._generation += 1
        killed = self._kill_playback()
        self._speaking.clear()
        return killed or was_active

    def speak(self, text: str, non_blocking: bool = True, force: bool = False,
              rate: Optional[str] = None, pitch: Optional[str] = None,
              affect: bool = True) -> None:
        """
        Speaks `text`, cancelling anything currently playing or pending.

        `force` bypasses the mute so diagnostics can still be heard. A test
        command that silently does nothing when output is off is worse than no
        test command at all.

        `rate` and `pitch` shape this utterance only. When they are omitted and
        `affect` is on, the current emotional read supplies them, so TARS slows
        and drops for bad news and lifts for good. Pass affect=False for
        mechanical output such as a diagnostic, where mood is noise.
        """
        if not config.voice_output_enabled and not force:
            return

        cleaned = self.clean_text_for_speech(text)
        if not cleaned:
            return

        if affect and rate is None and pitch is None:
            try:
                from tars.core.emotion import emotion

                rate, pitch = emotion.prosody()
            except Exception:
                rate = pitch = None

        # A new utterance supersedes the old one rather than queueing behind it.
        with self._lock:
            self._generation += 1
            my_generation = self._generation
        self._kill_playback()
        self._last_spoken = cleaned

        def _task() -> None:
            self._speaking.set()
            try:
                mp3 = self._synthesize_edge(cleaned, rate, pitch)
                if self._superseded(my_generation):
                    return
                played = False
                if mp3 is not None:
                    played = self._spawn(self._PLAY_MP3, {"AudioPath": str(mp3)}, timeout=120)
                    if not played and not self._superseded(my_generation):
                        # mp3 playback is the other half of the edge path; if it
                        # cannot run, stop trying it this session.
                        self._edge_healthy = False
                if not played and not self._superseded(my_generation):
                    self._spawn(self._SPEAK_SAPI, {"Utterance": cleaned}, timeout=90)
            finally:
                # Only the current utterance owns the speaking flag; a superseded
                # one must not clear it out from under its replacement.
                with self._lock:
                    still_current = self._generation == my_generation
                if still_current:
                    self._speaking.clear()

        if non_blocking:
            threading.Thread(target=_task, daemon=True).start()
        else:
            _task()

    def speak_ack(self) -> None:
        """Speaks a short 'working on it' so the tool loop does not run silent."""
        if not (config.voice_output_enabled and config.spoken_ack):
            return
        phrase = ACK_PHRASES[self._ack_index % len(ACK_PHRASES)]
        self._ack_index += 1
        self.speak(phrase, non_blocking=True)

    def wait_until_quiet(self, timeout: float = 30.0) -> None:
        """Blocks until speech finishes, so the microphone does not hear TARS."""
        deadline = time.time() + timeout
        while self.is_speaking and time.time() < deadline:
            time.sleep(0.08)

    # ─── One-shot speech input ──────────────────────────────────────────────

    _RECOGNISE_ONCE = """
Add-Type -AssemblyName System.Speech
try {
    $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
    $engine.SetInputToDefaultAudioDevice()
    $engine.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
    $res = $engine.Recognize([System.TimeSpan]::FromSeconds($Seconds))
    if ($res -and $res.Text) { Write-Output ("HEARD:" + $res.Text) } else { Write-Output "NO_SPEECH" }
} catch {
    Write-Output ("ERROR:" + $_.Exception.Message)
}
"""

    def listen(self, timeout_seconds: int = 6) -> str:
        """
        Captures one spoken phrase.

        Prefers the persistent recogniser when it is already running, since that
        avoids paying process startup for a single phrase.
        """
        if wake_listener.is_running:
            console.print(T.info(f"listening ({timeout_seconds}s)"))
            audio.key_tick()
            phrase = wake_listener.poll(timeout=timeout_seconds)
            if phrase:
                self._echo_heard(phrase)
                return phrase
            console.print(T.hint("nothing recognised"))
            return ""

        console.print(T.info(f"listening ({timeout_seconds}s)"))
        audio.key_tick()

        try:
            proc = subprocess.run(
                [
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    _ps_script(self._RECOGNISE_ONCE, {"Seconds": int(timeout_seconds)}),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds + 8,
            )
        except subprocess.TimeoutExpired:
            console.print(T.hint("microphone timed out"))
            return ""
        except Exception as ex:
            console.print(T.error(f"audio capture failed: {ex}"))
            return ""

        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("HEARD:"):
                heard = line[6:].strip()
                if heard:
                    self._echo_heard(heard)
                    return heard
            elif line.startswith("ERROR:"):
                console.print(T.error(f"microphone: {line[6:].strip()}"))
                return ""

        console.print(T.hint("nothing recognised"))
        return ""

    def _echo_heard(self, text: str) -> None:
        console.print(
            f"  [{T.MUTED}]{config.operator_callsign.lower()} (voice)[/{T.MUTED}]  "
            f"[{T.TEXT_BRIGHT}]{text}[/{T.TEXT_BRIGHT}]"
        )
        audio.key_tick()


class WakeListener:
    """
    A single long-lived PowerShell speech recogniser.

    The one-shot approach paid process startup for every listening window, which
    is why talking to TARS felt like operating a machine rather than speaking to
    one. Here the engine is created once and recognised phrases stream back over
    stdout until the listener is stopped.
    """

    _SCRIPT = """
Add-Type -AssemblyName System.Speech
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
    $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
    $engine.SetInputToDefaultAudioDevice()
    $engine.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
} catch {
    Write-Output ("FATAL:" + $_.Exception.Message)
    exit 1
}
Write-Output "READY"
[Console]::Out.Flush()
while ($true) {
    try {
        $res = $engine.Recognize([System.TimeSpan]::FromSeconds(8))
    } catch {
        Write-Output ("FATAL:" + $_.Exception.Message)
        [Console]::Out.Flush()
        break
    }
    if ($res -and $res.Text) {
        Write-Output ("HEARD:" + $res.Text)
        [Console]::Out.Flush()
    }
}
"""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._phrases: "queue.Queue[str]" = queue.Queue()
        self._ready = threading.Event()
        self._fatal: str = ""

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def fatal_error(self) -> str:
        return self._fatal

    def start(self, wait_ready: float = 12.0) -> bool:
        """Boots the recogniser. Returns True once it reports READY."""
        if self.is_running:
            return True

        self._fatal = ""
        self._ready.clear()
        while not self._phrases.empty():
            try:
                self._phrases.get_nowait()
            except queue.Empty:
                break

        try:
            self._proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", self._SCRIPT],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception as ex:
            self._fatal = f"{type(ex).__name__}: {ex}"
            self._proc = None
            return False

        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()
        return self._ready.wait(timeout=wait_ready)

    def _pump(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                if line == "READY":
                    self._ready.set()
                elif line.startswith("HEARD:"):
                    phrase = line[6:].strip()
                    if phrase:
                        self._phrases.put(phrase)
                elif line.startswith("FATAL:"):
                    self._fatal = line[6:].strip()
                    self._ready.set()
                    break
        except Exception:
            pass

    def poll(self, timeout: float = 1.0) -> Optional[str]:
        """Returns the next recognised phrase, or None if none arrived in time."""
        try:
            return self._phrases.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self) -> None:
        """Discards buffered phrases. Used after TARS speaks, to drop echo."""
        while True:
            try:
                self._phrases.get_nowait()
            except queue.Empty:
                return

    def stop(self) -> None:
        proc = self._proc
        self._proc = None
        self._ready.clear()
        if proc is None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass


def strip_wake_word(phrase: str, wake_word: str) -> Optional[str]:
    """
    Detects the wake word and returns whatever followed it.

    Returns None when the wake word is absent, "" when the phrase was only the
    wake word (so the caller should listen for a follow-up), or the command text.
    Matching is loose because dictation recognisers routinely mangle short
    hotwords -- "hey tars" comes back as "hey cars", "hey stars", "a tarsi".
    """
    text = (phrase or "").strip().lower()
    if not text:
        return None

    wake = (wake_word or "hey tars").strip().lower()
    tokens = wake.split()
    tail = tokens[-1] if tokens else "tars"

    # Accept common mis-recognitions of the trailing token.
    variants = {tail, "tars", "cars", "stars", "tarts", "czars", "tsars", "dars", "tarsi"}
    pattern = r"^\W*(?:hey|hi|hello|ok|okay|yo)?\s*(" + "|".join(re.escape(v) for v in variants) + r")\b"

    match = re.match(pattern, text)
    if not match:
        # Also accept the exact configured phrase appearing anywhere early on.
        idx = text.find(wake)
        if idx == -1 or idx > 12:
            return None
        return text[idx + len(wake):].strip(" ,.:;!?")

    return text[match.end():].strip(" ,.:;!?")


INTERRUPT_WORDS = ("stop talking", "be quiet", "shut up", "quiet", "stop", "enough", "cancel")


def is_interrupt(phrase: str) -> bool:
    """True when a phrase is the operator talking over TARS to cut it off."""
    text = (phrase or "").strip().lower().strip(" .,!?")
    return text in INTERRUPT_WORDS or text.startswith(("stop talking", "be quiet", "shut up"))


voice = VoiceEngine()
wake_listener = WakeListener()
