import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / ".tars_config.json"
ENV_FILE = PROJECT_ROOT / ".env"

# Load a local .env early so GEMINI_API_KEY can be supplied without writing the
# key into .tars_config.json. Falls back silently if python-dotenv is absent.
if ENV_FILE.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_FILE)
    except ImportError:
        # Minimal parser so .env still works without python-dotenv installed.
        try:
            for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                os.environ.setdefault(name.strip(), value.strip().strip("\"'"))
        except OSError:
            pass

class TarsConfig:
    def __init__(self):
        self.humor: int = 75
        self.honesty: int = 90
        self.sarcasm: int = 65
        self.sound_enabled: bool = True
        self.voice_output_enabled: bool = True
        self.voice_input_enabled: bool = True
        self.typewriter_effect: bool = True
        self.typewriter_speed: float = 0.012
        self.operator_callsign: str = "Rohit"
        # File-backed key only. The environment fallback lives in
        # tars.core.llm.resolve_api_key() so an env-supplied key is never
        # written back to disk by save().
        self.gemini_api_key: str = ""
        self.load()

    @property
    def key_is_persisted_to_disk(self) -> bool:
        """True when the API key is stored in plaintext in .tars_config.json."""
        return bool(self.gemini_api_key)

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.humor = data.get("humor", self.humor)
                    self.honesty = data.get("honesty", self.honesty)
                    self.sarcasm = data.get("sarcasm", self.sarcasm)
                    self.sound_enabled = data.get("sound_enabled", self.sound_enabled)
                    self.voice_output_enabled = data.get("voice_output_enabled", self.voice_output_enabled)
                    self.voice_input_enabled = data.get("voice_input_enabled", self.voice_input_enabled)
                    self.typewriter_effect = data.get("typewriter_effect", self.typewriter_effect)
                    self.operator_callsign = data.get("operator_callsign", self.operator_callsign)
                    self.gemini_api_key = data.get("gemini_api_key", self.gemini_api_key)
            except Exception:
                pass

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "humor": self.humor,
                    "honesty": self.honesty,
                    "sarcasm": self.sarcasm,
                    "sound_enabled": self.sound_enabled,
                    "voice_output_enabled": self.voice_output_enabled,
                    "voice_input_enabled": self.voice_input_enabled,
                    "typewriter_effect": self.typewriter_effect,
                    "operator_callsign": self.operator_callsign,
                    "gemini_api_key": self.gemini_api_key
                }, f, indent=2)
        except Exception:
            pass

config = TarsConfig()
