import re
import sys
import time
import base64
import threading
import subprocess
from rich.console import Console
from tars.config import config
from tars.ui.audio import audio

console = Console()

class VoiceEngine:
    def __init__(self):
        self.is_speaking = False

    def clean_text_for_speech(self, text: str, max_chars: int = 450) -> str:
        """Strips markdown, box art, URLs, headers, and code symbols for natural robotic TTS."""
        cleaned = re.sub(r"\[● CUE LIGHT ON\]", "", text)
        cleaned = re.sub(r"\[.*?\]", "", cleaned)
        cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
        cleaned = re.sub(r"`[^`]*`", "", cleaned)
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
            last_punct = max(cut.rfind('.'), cut.rfind('!'), cut.rfind('?'))
            if last_punct > 120:
                cleaned = cut[:last_punct + 1]
            else:
                cleaned = cut + "..."

        return cleaned

    def speak(self, text: str, non_blocking: bool = True):
        """Speaks the text using Windows System.Speech.Synthesis with Microsoft David."""
        if not config.voice_output_enabled:
            return

        cleaned = self.clean_text_for_speech(text)
        if not cleaned:
            return

        def _task():
            self.is_speaking = True
            b64_text = base64.b64encode(cleaned.encode('utf-8')).decode('ascii')
            ps_script = f"""
            Add-Type -AssemblyName System.Speech
            $bytes = [System.Convert]::FromBase64String('{b64_text}')
            $text = [System.Text.Encoding]::UTF8.GetString($bytes)
            $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
            try {{
                $synth.SelectVoice("Microsoft David Desktop")
            }} catch {{
                try {{
                    $synth.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Male)
                }} catch {{}}
            }}
            $synth.Rate = 0
            $synth.Volume = 100
            $synth.Speak($text)
            """
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    capture_output=True,
                    timeout=45
                )
            except Exception:
                pass
            finally:
                self.is_speaking = False

        if non_blocking:
            threading.Thread(target=_task, daemon=True).start()
        else:
            _task()

    def listen(self, timeout_seconds: int = 6) -> str:
        """
        Listens to the default microphone using Windows System.Speech.Recognition.
        Returns recognized text or empty string.
        """
        console.print(f"[bold green]🎙 LISTENING... Speak to TARS now ({timeout_seconds}s timeout)[/bold green]")
        audio.key_tick()

        ps_script = f"""
        Add-Type -AssemblyName System.Speech
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        try {{
            $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
            $engine.SetInputToDefaultAudioDevice()
            $grammar = New-Object System.Speech.Recognition.DictationGrammar
            $engine.LoadGrammar($grammar)
            $res = $engine.Recognize([System.TimeSpan]::FromSeconds({timeout_seconds}))
            if ($res -and $res.Text) {{
                Write-Output ("HEARD:" + $res.Text)
            }} else {{
                Write-Output "NO_SPEECH"
            }}
        }} catch {{
            Write-Output ("ERROR:" + $_.Exception.Message)
        }}
        """

        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds + 5
            )
            out = proc.stdout.strip()
            
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("HEARD:"):
                    heard = line[6:].strip()
                    if heard:
                        console.print(f"[bold cyan]{config.operator_callsign} (Voice):[/bold cyan] [bold white]\"{heard}\"[/bold white]")
                        audio.key_tick()
                        return heard
                elif line.startswith("ERROR:"):
                    console.print(f"[dim red]Microphone notice: {line[6:].strip()}[/dim red]")
                    return ""

            console.print("[dim yellow]No speech recognized. Say again or type in the prompt.[/dim yellow]")
            return ""
        except Exception as e:
            console.print(f"[dim red]Audio capture exception: {e}[/dim red]")
            return ""

voice = VoiceEngine()
