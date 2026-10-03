import json
import os
from pathlib import Path
from typing import Dict, List

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
        # How much of itself the unit brings to an emotionally loaded turn.
        # 0 disables the affective layer entirely and returns the old, flatter
        # behaviour. Low values acknowledge in a line and move on; high values
        # let presence outrank brevity.
        self.empathy: int = 85
        # Whether a turn's emotional read shapes speech rate and pitch.
        self.affect_voice: bool = True
        self.sound_enabled: bool = True
        self.voice_output_enabled: bool = True
        self.voice_input_enabled: bool = True
        self.typewriter_effect: bool = True
        self.typewriter_speed: float = 0.012
        self.operator_callsign: str = "Rohit"

        # ─── Shell chrome ───────────────────────────────────────────────────
        # Boot stagger and the live thinking indicator. Turning this off makes
        # the shell fully static, which is what you want over a slow SSH link
        # or when piping output somewhere.
        self.ui_animation: bool = True
        # One-line HUD above the prompt: uplink, dials, affective read, uptime.
        self.ui_status_bar: bool = True
        # Full identity block at startup. Off gives a single compact line.
        self.ui_logo: bool = True

        # ─── Security boundary ──────────────────────────────────────────────
        # Filesystem tools are confined to the workspace root plus the system
        # temp directory. Anything else the operator wants reachable has to be
        # named here explicitly (see `roots add` in the shell).
        self.allowed_fs_roots: List[str] = []
        # When on, SENSITIVE shell/Python payloads pause for terminal approval
        # instead of running unattended. Turning this off is a real reduction in
        # safety, not a convenience toggle.
        self.confirm_sensitive: bool = True

        # ─── Host control ───────────────────────────────────────────────────
        # The allowlisted laptop-control action layer (tars/core/host.py).
        self.host_control_enabled: bool = True
        # name -> executable, URI, or absolute path. Only these apps can launch.
        self.app_allowlist: Dict[str, str] = {}
        # Domains open_url may reach. Empty list means any https/http URL.
        self.url_allowlist: List[str] = []

        # ─── Voice presence ─────────────────────────────────────────────────
        # "auto" prefers edge-tts neural voices and falls back to Windows SAPI.
        self.tts_engine: str = "auto"
        self.tts_voice: str = "en-US-GuyNeural"
        self.tts_rate: str = "+8%"
        self.tts_pitch: str = "-6Hz"
        self.wake_word: str = "hey tars"
        self.wake_word_enabled: bool = False
        # Short spoken acknowledgement when TARS starts multi-step tool work,
        # so there is no dead air while the ReAct loop runs.
        self.spoken_ack: bool = True

        # ─── Proactive sentinel ─────────────────────────────────────────────
        self.proactive_enabled: bool = False
        self.proactive_interval: int = 60

        # File-backed key only. The environment fallback lives in
        # tars.core.llm.resolve_api_key() so an env-supplied key is never
        # written back to disk by save().
        self.gemini_api_key: str = ""
        self.load()

    @property
    def key_is_persisted_to_disk(self) -> bool:
        """True when the API key is stored in plaintext in .tars_config.json."""
        return bool(self.gemini_api_key)

    # Single source of truth for what round-trips to disk. Listed once so adding
    # a setting cannot silently fail to persist.
    PERSISTED = (
        "humor",
        "honesty",
        "sarcasm",
        "empathy",
        "affect_voice",
        "sound_enabled",
        "voice_output_enabled",
        "voice_input_enabled",
        "typewriter_effect",
        "ui_animation",
        "ui_status_bar",
        "ui_logo",
        "operator_callsign",
        "allowed_fs_roots",
        "confirm_sensitive",
        "host_control_enabled",
        "app_allowlist",
        "url_allowlist",
        "tts_engine",
        "tts_voice",
        "tts_rate",
        "tts_pitch",
        "wake_word",
        "wake_word_enabled",
        "spoken_ack",
        "proactive_enabled",
        "proactive_interval",
        "gemini_api_key",
    )

    def load(self):
        if not CONFIG_FILE.exists():
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        if not isinstance(data, dict):
            return
        for key in self.PERSISTED:
            if key not in data:
                continue
            current = getattr(self, key)
            incoming = data[key]
            # Reject a stored value whose type no longer matches the default, so
            # a hand-edited config cannot inject e.g. a string where a list of
            # allowed roots is expected.
            if isinstance(current, bool) and not isinstance(incoming, bool):
                continue
            if isinstance(current, (list, dict)) and not isinstance(incoming, type(current)):
                continue
            if isinstance(current, int) and not isinstance(current, bool) and not isinstance(incoming, int):
                continue
            setattr(self, key, incoming)

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({key: getattr(self, key) for key in self.PERSISTED}, f, indent=2)
        except Exception:
            pass

config = TarsConfig()
