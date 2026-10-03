"""
TARS - Host Control (allowlisted laptop actions)

A single tool, `host_control`, exposing a fixed verb enum. This is deliberately
not "run a shell command for me": every verb has typed, validated parameters and
a bounded blast radius, and each one is reversible.

Three rules the implementation holds to:

  1. Allowlist, not denylist. A verb that is not in VERBS does not exist, and
     open_app can only launch names present in the app allowlist.
  2. No string interpolation into a shell. Most verbs are pure ctypes calls into
     user32/kernel32 and touch no shell at all. The few that genuinely need
     PowerShell (brightness, clipboard, toast, wifi) go through _ps(), which
     passes every operand as a base64 blob decoded inside the script -- the
     base64 alphabet cannot terminate a PowerShell string literal.
  3. Everything is audited. Each invocation appends to mission_logs/audit.jsonl.

Deliberately absent: registry writes, service control, firewall and Defender
configuration, uninstalls, scheduled task creation, elevation, credential
access, and file deletion. Those are the "too deep" half and they stay out.
"""
from __future__ import annotations

import base64
import ctypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from tars.config import config
from tars.core.security import audit_action

IS_WINDOWS = sys.platform == "win32"
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# ─── Win32 virtual key codes ─────────────────────────────────────────────────

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

# Windows adjusts volume in 2-point steps per keypress.
VOLUME_STEP_PERCENT = 2


# ─── Default application allowlist ──────────────────────────────────────────
# Friendly name -> candidate executables, URIs, or absolute paths, tried in
# order. Entries that resolve to nothing on this machine are simply not offered.
# The operator can extend this at runtime via `apps add <name> <target>`.

DEFAULT_APPS: Dict[str, List[str]] = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "files": ["explorer.exe"],
    "terminal": ["wt.exe", "powershell.exe"],
    "powershell": ["powershell.exe"],
    "cmd": ["cmd.exe"],
    "task manager": ["taskmgr.exe"],
    "paint": ["mspaint.exe"],
    "snipping tool": ["snippingtool.exe", "ms-screenclip:"],
    "settings": ["ms-settings:"],
    "wordpad": ["write.exe"],
    "character map": ["charmap.exe"],
    "vscode": ["code.cmd", "code.exe", "code"],
    "code": ["code.cmd", "code.exe", "code"],
    "chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "firefox": ["firefox.exe"],
    "brave": ["brave.exe"],
    "spotify": ["spotify.exe"],
    "discord": ["discord.exe"],
    "slack": ["slack.exe"],
    "notion": ["notion.exe"],
    "obsidian": ["obsidian.exe"],
    "steam": ["steam.exe"],
    "whatsapp": ["whatsapp.exe"],
    "telegram": ["telegram.exe"],
    "postman": ["postman.exe"],
    "figma": ["figma.exe"],
    "zoom": ["zoom.exe"],
    "mail": ["outlookmail:", "ms-mail:"],
    "calendar": ["outlookcal:", "ms-calendar:"],
}

# Directories worth globbing when an executable is not on PATH and has no
# App Paths registry entry. Per-user install locations, mostly.
_COMMON_DIRS = [
    r"%LOCALAPPDATA%\Programs",
    r"%LOCALAPPDATA%",
    r"%APPDATA%",
    r"%PROGRAMFILES%",
    r"%PROGRAMFILES(X86)%",
]


def _is_uri(target: str) -> bool:
    return bool(re.match(r"^[a-z][a-z0-9+.\-]*:(?!\\)", target, re.IGNORECASE)) and not re.match(
        r"^[a-z]:\\", target, re.IGNORECASE
    )


def _resolve_from_registry(exe: str) -> Optional[str]:
    """
    Looks up an executable in the App Paths registry key, which is how Windows
    itself finds chrome.exe and friends. Read-only access to HKLM/HKCU.
    """
    if not IS_WINDOWS:
        return None
    try:
        import winreg
    except ImportError:
        return None

    subkey = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, subkey) as key:
                raw, _ = winreg.QueryValueEx(key, "")
                candidate = Path(os.path.expandvars(str(raw).strip('"')))
                if candidate.exists():
                    return str(candidate)
        except (OSError, ValueError):
            continue
    return None


def _resolve_from_common_dirs(exe: str) -> Optional[str]:
    stem = Path(exe).stem
    for raw_dir in _COMMON_DIRS:
        base = Path(os.path.expandvars(raw_dir))
        if "%" in str(base) or not base.exists():
            continue
        try:
            # One level deep, then the app's own folder. Deep recursion over
            # Program Files is far too slow to do on every lookup.
            for child in base.iterdir():
                if not child.is_dir():
                    continue
                direct = child / exe
                if direct.exists():
                    return str(direct)
                nested = child / stem.capitalize() / exe
                if nested.exists():
                    return str(nested)
                app_dir = child / "Application" / exe
                if app_dir.exists():
                    return str(app_dir)
        except (OSError, PermissionError):
            continue
    return None


def resolve_app(name: str) -> Tuple[Optional[str], bool]:
    """
    Resolves an allowlisted friendly name to something launchable.

    Returns (target, is_uri). target is None when the app is allowlisted but not
    installed on this machine.
    """
    key = (name or "").strip().lower()
    candidates: List[str] = []

    # Operator overrides win over the built-in table.
    override = (config.app_allowlist or {}).get(key)
    if override:
        candidates.append(str(override))
    candidates.extend(DEFAULT_APPS.get(key, []))

    if not candidates:
        return None, False

    for candidate in candidates:
        if _is_uri(candidate):
            return candidate, True

        expanded = os.path.expandvars(candidate)
        as_path = Path(expanded)
        if as_path.is_absolute() and as_path.exists():
            return str(as_path), False

        found = shutil.which(expanded)
        if found:
            return found, False

        found = _resolve_from_registry(Path(expanded).name)
        if found:
            return found, False

        found = _resolve_from_common_dirs(Path(expanded).name)
        if found:
            return found, False

    return None, False


def available_apps() -> List[Tuple[str, str]]:
    """Every allowlisted app that actually resolves here, as (name, target)."""
    names = sorted(set(list(DEFAULT_APPS.keys()) + list((config.app_allowlist or {}).keys())))
    out: List[Tuple[str, str]] = []
    for name in names:
        target, _ = resolve_app(name)
        if target:
            out.append((name, target))
    return out


# ─── PowerShell channel (injection-safe) ────────────────────────────────────

def _ps(script: str, params: Optional[Dict[str, object]] = None, timeout: int = 20) -> Tuple[int, str, str]:
    """
    Runs a fixed PowerShell script with operands passed as base64.

    Callers never interpolate user text into `script`. Each entry in `params`
    becomes a PowerShell variable assigned from a base64 literal, and the base64
    alphabet (A-Za-z0-9+/=) contains no quote or escape character that could
    terminate the literal. That makes the parameter channel non-executable by
    construction rather than by sanitisation.
    """
    if not IS_WINDOWS:
        return 1, "", "Host control requires Windows."

    prelude = [
        "$ErrorActionPreference = 'Stop'",
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8",
    ]
    for name, value in (params or {}).items():
        if not _IDENT_RE.match(str(name)):
            return 1, "", f"Invalid parameter name '{name}'."
        blob = base64.b64encode(str(value).encode("utf-8")).decode("ascii")
        prelude.append(
            f"${name} = [System.Text.Encoding]::UTF8.GetString("
            f"[System.Convert]::FromBase64String('{blob}'))"
        )

    full = "\n".join(prelude + [script])
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", full],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 1, "", f"PowerShell call timed out after {timeout}s."
    except Exception as ex:
        return 1, "", f"{type(ex).__name__}: {ex}"


def _tap_key(vk: int, repeat: int = 1, gap: float = 0.02) -> None:
    """Sends a virtual key press via user32.keybd_event. No shell involved."""
    if not IS_WINDOWS:
        return
    user32 = ctypes.windll.user32
    for _ in range(max(1, repeat)):
        user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
        time.sleep(gap)


# ─── Verb handlers ──────────────────────────────────────────────────────────
# Each returns a plain string, which becomes the tool result the model reads.

def _verb_list_apps(**_) -> str:
    apps = available_apps()
    if not apps:
        return "No allowlisted applications resolved on this machine."
    lines = [f"{len(apps)} applications available to open:"]
    lines += [f"  {name:<16} {target}" for name, target in apps]
    lines.append("Operator can extend the allowlist with: apps add <name> <path>")
    return "\n".join(lines)


def _verb_open_app(target: str = "", **_) -> str:
    name = (target or "").strip()
    if not name:
        return "Error: 'target' is required. Use verb 'list_apps' to see what is available."

    resolved, is_uri = resolve_app(name)
    if resolved is None:
        known = ", ".join(n for n, _ in available_apps()[:18])
        return (
            f"Refused: '{name}' is not in the application allowlist, or is not installed.\n"
            f"Available: {known}\n"
            f"The operator can allow it with: apps add {name.lower()} <path-to-exe>"
        )

    try:
        if is_uri:
            if not IS_WINDOWS:
                return "Error: URI handlers are Windows-only."
            # The URI comes from the allowlist table, not from the model.
            os.startfile(resolved)  # noqa: S606
        else:
            # argv list, shell=False: the path never passes through a command
            # interpreter, so a filename cannot smuggle an operator.
            subprocess.Popen(
                [resolved],
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
            )
    except Exception as ex:
        return f"Failed to launch '{name}': {type(ex).__name__}: {ex}"
    return f"Launched {name} ({resolved})."


def _verb_open_url(url: str = "", **_) -> str:
    raw = (url or "").strip()
    if not raw:
        return "Error: 'url' is required."

    # Resolve the scheme before normalising. Testing for "://" is not enough:
    # `javascript:alert(1)` contains no "://", so blindly prepending https would
    # produce "https://javascript:alert(1)", which then passes a scheme check.
    declared = re.match(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):(.*)$", raw, re.DOTALL)
    if declared:
        scheme, remainder = declared.group(1).lower(), declared.group(2)
        if scheme in ("http", "https"):
            pass
        elif re.match(r"^\d+(/|$)", remainder):
            # "example.com:8080/path" -- a host and port, not a scheme.
            raw = "https://" + raw
        else:
            return (
                f"Refused: scheme '{scheme}:' is not permitted. Only http and https are allowed; "
                f"file:, javascript:, data:, and shell protocol handlers are blocked."
            )
    else:
        raw = "https://" + raw

    parsed = urlparse(raw)
    if parsed.scheme.lower() not in ("http", "https"):
        return (
            f"Refused: scheme '{parsed.scheme}' is not permitted. Only http and https. "
            f"file:, javascript:, and shell handlers are blocked."
        )
    if not parsed.netloc:
        return f"Refused: '{url}' has no host component."

    allow = [d.strip().lower() for d in (config.url_allowlist or []) if d.strip()]
    if allow:
        host = parsed.netloc.lower().split(":")[0]
        if not any(host == d or host.endswith("." + d) for d in allow):
            return (
                f"Refused: '{host}' is not in the URL allowlist ({', '.join(allow)}). "
                f"Clear the list to permit any https host."
            )

    try:
        webbrowser.open(raw, new=2)
    except Exception as ex:
        return f"Failed to open URL: {type(ex).__name__}: {ex}"
    return f"Opened {raw} in the default browser."


_MEDIA_KEYS = {
    "play_pause": (VK_MEDIA_PLAY_PAUSE, "toggled play/pause"),
    "play": (VK_MEDIA_PLAY_PAUSE, "toggled play/pause"),
    "pause": (VK_MEDIA_PLAY_PAUSE, "toggled play/pause"),
    "next": (VK_MEDIA_NEXT_TRACK, "skipped to next track"),
    "previous": (VK_MEDIA_PREV_TRACK, "went to previous track"),
    "stop": (VK_MEDIA_STOP, "stopped playback"),
}


def _verb_media(action: str = "play_pause", **_) -> str:
    key = (action or "play_pause").strip().lower().replace("-", "_").replace(" ", "_")
    if key not in _MEDIA_KEYS:
        return f"Error: unknown media action '{action}'. Choose: {', '.join(sorted(_MEDIA_KEYS))}."
    vk, described = _MEDIA_KEYS[key]
    _tap_key(vk)
    return f"Media: {described}. Whichever player holds the media session responds."


def _verb_volume(action: str = "", level: Optional[int] = None, **_) -> str:
    act = (action or "").strip().lower()

    if act in ("mute", "unmute", "toggle_mute", "togglemute"):
        _tap_key(VK_VOLUME_MUTE)
        return "Volume: toggled mute."

    if act in ("up", "raise", "increase"):
        steps = 3 if level is None else max(1, min(int(level), 50)) // VOLUME_STEP_PERCENT or 1
        _tap_key(VK_VOLUME_UP, repeat=steps)
        return f"Volume: raised roughly {steps * VOLUME_STEP_PERCENT}%."

    if act in ("down", "lower", "decrease"):
        steps = 3 if level is None else max(1, min(int(level), 50)) // VOLUME_STEP_PERCENT or 1
        _tap_key(VK_VOLUME_DOWN, repeat=steps)
        return f"Volume: lowered roughly {steps * VOLUME_STEP_PERCENT}%."

    if act == "set":
        if level is None:
            return "Error: 'level' (0-100) is required when action is 'set'."
        try:
            target = max(0, min(int(level), 100))
        except (TypeError, ValueError):
            return f"Error: 'level' must be an integer 0-100, got '{level}'."
        # Floor first, then step up. Windows exposes no absolute-set hotkey, so
        # this is normalisation by keypress; granularity is 2%.
        _tap_key(VK_VOLUME_DOWN, repeat=52, gap=0.008)
        steps = target // VOLUME_STEP_PERCENT
        if steps:
            _tap_key(VK_VOLUME_UP, repeat=steps, gap=0.008)
        return f"Volume: set to approximately {steps * VOLUME_STEP_PERCENT}%."

    return "Error: volume action must be one of: up, down, set, mute."


def _verb_brightness(level: Optional[int] = None, **_) -> str:
    if level is None:
        code, out, err = _ps(
            "$b = Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness "
            "-ErrorAction Stop; Write-Output $b.CurrentBrightness"
        )
        if code != 0 or not out:
            return (
                "Could not read brightness. The WMI brightness interface is only exposed "
                "by built-in laptop panels, not external monitors."
            )
        return f"Display brightness is at {out.splitlines()[0].strip()}%."

    try:
        target = max(0, min(int(level), 100))
    except (TypeError, ValueError):
        return f"Error: 'level' must be an integer 0-100, got '{level}'."

    # `target` is an int by this point, so this interpolation carries no text.
    code, _out, err = _ps(
        "$m = Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods "
        "-ErrorAction Stop; "
        f"$m | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1; Brightness={target}}} "
        "| Out-Null"
    )
    if code != 0:
        return (
            f"Brightness change failed. External monitors do not expose the WMI brightness "
            f"interface; this works on built-in laptop panels only. ({err[:160]})"
        )
    return f"Display brightness set to {target}%."


def _verb_clipboard_get(**_) -> str:
    code, out, err = _ps("Get-Clipboard -Raw")
    if code != 0:
        return f"Could not read clipboard: {err[:200]}"
    if not out:
        return "Clipboard is empty, or holds non-text content."
    if len(out) > 4000:
        return f"Clipboard ({len(out)} chars, truncated):\n{out[:4000]}…"
    return f"Clipboard ({len(out)} chars):\n{out}"


def _verb_clipboard_set(text: str = "", **_) -> str:
    if text is None:
        return "Error: 'text' is required."
    payload = str(text)
    if len(payload) > 100_000:
        return "Error: refusing to place more than 100k characters on the clipboard."
    code, _out, err = _ps("Set-Clipboard -Value $Payload", {"Payload": payload})
    if code != 0:
        return f"Could not set clipboard: {err[:200]}"
    return f"Copied {len(payload)} characters to the clipboard."


def _verb_notify(title: str = "TARS", message: str = "", **_) -> str:
    body = (message or "").strip()
    if not body:
        return "Error: 'message' is required."
    heading = (title or "TARS").strip()[:64]

    script = """
Add-Type -AssemblyName System.Windows.Forms
$icon = New-Object System.Windows.Forms.NotifyIcon
$icon.Icon = [System.Drawing.SystemIcons]::Information
$icon.BalloonTipTitle = $Heading
$icon.BalloonTipText = $Body
$icon.Visible = $true
$icon.ShowBalloonTip(6000)
Start-Sleep -Milliseconds 6200
$icon.Dispose()
"""
    code, _out, err = _ps(script, {"Heading": heading, "Body": body[:240]}, timeout=15)
    if code != 0:
        return f"Notification failed: {err[:200]}"
    return f"Notification shown: {heading} - {body[:80]}"


def _verb_lock(**_) -> str:
    if not IS_WINDOWS:
        return "Error: lock is Windows-only."
    try:
        ok = ctypes.windll.user32.LockWorkStation()
    except Exception as ex:
        return f"Lock failed: {type(ex).__name__}: {ex}"
    if not ok:
        return "Lock call returned failure. The session may already be locked."
    return "Workstation locked."


def _verb_sleep_display(**_) -> str:
    if not IS_WINDOWS:
        return "Error: sleep_display is Windows-only."
    HWND_BROADCAST = 0xFFFF
    WM_SYSCOMMAND = 0x0112
    SC_MONITORPOWER = 0xF170
    MONITOR_OFF = 2
    try:
        ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, MONITOR_OFF)
    except Exception as ex:
        return f"Could not turn off the display: {type(ex).__name__}: {ex}"
    return "Display powered down. Move the mouse or press a key to wake it."


def _enumerate_windows() -> List[Tuple[int, str]]:
    """Visible, titled top-level windows as (hwnd, title)."""
    if not IS_WINDOWS:
        return []
    user32 = ctypes.windll.user32
    results: List[Tuple[int, str]] = []

    CBType = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))

    def _callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if title and title not in ("Program Manager", "Windows Input Experience"):
            results.append((hwnd, title))
        return True

    try:
        user32.EnumWindows(CBType(_callback), None)
    except Exception:
        return []
    return results


def _verb_list_windows(**_) -> str:
    windows = _enumerate_windows()
    if not windows:
        return "No visible top-level windows found."
    lines = [f"{len(windows)} open windows:"]
    lines += [f"  {title[:100]}" for _hwnd, title in windows[:40]]
    return "\n".join(lines)


def _verb_focus_window(target: str = "", **_) -> str:
    needle = (target or "").strip().lower()
    if not needle:
        return "Error: 'target' is required (a substring of the window title)."

    windows = _enumerate_windows()
    matches = [(h, t) for h, t in windows if needle in t.lower()]
    if not matches:
        titles = ", ".join(t[:40] for _h, t in windows[:10])
        return f"No open window title contains '{target}'. Currently open: {titles}"

    hwnd, title = matches[0]
    try:
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
    except Exception as ex:
        return f"Could not focus '{title}': {type(ex).__name__}: {ex}"
    return f"Focused window: {title}"


def _verb_battery(**_) -> str:
    try:
        import psutil
    except ImportError:
        return "psutil is not installed, so battery state is unavailable."
    bat = psutil.sensors_battery()
    if bat is None:
        return "No battery detected. This looks like a desktop, or the driver is not reporting."
    state = "charging" if bat.power_plugged else "on battery"
    parts = [f"Battery at {bat.percent:.0f}%, {state}"]
    if not bat.power_plugged and bat.secsleft and bat.secsleft > 0:
        hours, rem = divmod(int(bat.secsleft), 3600)
        parts.append(f"about {hours}h {rem // 60}m remaining")
    return ". ".join(parts) + "."


def _verb_network(**_) -> str:
    code, out, _err = _ps("netsh wlan show interfaces")
    summary: Dict[str, str] = {}
    if code == 0 and out:
        for line in out.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip().lower()
                if key in ("state", "ssid", "signal", "radio type", "receive rate (mbps)"):
                    summary[key] = val.strip()

    lines = []
    if summary:
        lines.append("Wi-Fi: " + ", ".join(f"{k} {v}" for k, v in summary.items() if v))
    else:
        lines.append("Wi-Fi: no wireless interface reporting (wired, disabled, or no adapter).")

    try:
        import psutil

        io = psutil.net_io_counters()
        lines.append(f"Traffic since boot: {io.bytes_recv / 1e9:.2f} GB down, {io.bytes_sent / 1e9:.2f} GB up.")
    except Exception:
        pass
    return "\n".join(lines)


# ─── Timers ─────────────────────────────────────────────────────────────────

@dataclass
class _Timer:
    label: str
    fires_at: float
    handle: threading.Timer = field(repr=False)


_timers: Dict[int, _Timer] = {}
_timer_lock = threading.Lock()
_timer_seq = 0


def _fire_timer(timer_id: int, label: str) -> None:
    with _timer_lock:
        _timers.pop(timer_id, None)
    _verb_notify(title="TARS timer", message=label)
    try:
        from tars.ui.voice import voice

        voice.speak(f"Timer finished: {label}", non_blocking=True)
    except Exception:
        pass
    audit_action("host", "timer_fired", {"label": label}, "ok")


def _verb_timer(minutes: Optional[float] = None, label: str = "", **_) -> str:
    if minutes is None:
        return "Error: 'minutes' is required."
    try:
        mins = float(minutes)
    except (TypeError, ValueError):
        return f"Error: 'minutes' must be a number, got '{minutes}'."
    if not 0 < mins <= 24 * 60:
        return "Error: timer must be between 0 and 1440 minutes."

    global _timer_seq
    text = (label or "reminder").strip()[:120]
    seconds = mins * 60.0

    with _timer_lock:
        _timer_seq += 1
        timer_id = _timer_seq
        handle = threading.Timer(seconds, _fire_timer, args=(timer_id, text))
        handle.daemon = True
        _timers[timer_id] = _Timer(label=text, fires_at=time.time() + seconds, handle=handle)
        handle.start()

    return f"Timer {timer_id} set for {mins:g} minute(s): {text}. I'll speak up and show a notification."


def _verb_list_timers(**_) -> str:
    with _timer_lock:
        snapshot = list(_timers.items())
    if not snapshot:
        return "No timers pending."
    now = time.time()
    lines = [f"{len(snapshot)} timer(s) pending:"]
    for tid, t in sorted(snapshot, key=lambda kv: kv[1].fires_at):
        remaining = max(0, int(t.fires_at - now))
        # "#1" rather than "[1]": the CLI renders tool output through Rich, which
        # would read a bracketed token as a style tag.
        lines.append(f"  #{tid}  {t.label} - {remaining // 60}m {remaining % 60}s left")
    return "\n".join(lines)


def _verb_cancel_timer(timer_id: Optional[int] = None, **_) -> str:
    if timer_id is None:
        with _timer_lock:
            for t in _timers.values():
                t.handle.cancel()
            count = len(_timers)
            _timers.clear()
        return f"Cancelled {count} timer(s)."
    try:
        tid = int(timer_id)
    except (TypeError, ValueError):
        return f"Error: 'timer_id' must be an integer, got '{timer_id}'."
    with _timer_lock:
        entry = _timers.pop(tid, None)
    if entry is None:
        return f"No pending timer with id {tid}."
    entry.handle.cancel()
    return f"Cancelled timer {tid} ({entry.label})."


# ─── Verb table ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class VerbSpec:
    handler: Callable[..., str]
    summary: str
    params: Tuple[str, ...] = ()


VERBS: Dict[str, VerbSpec] = {
    "list_apps": VerbSpec(_verb_list_apps, "list applications TARS is allowed to launch"),
    "open_app": VerbSpec(_verb_open_app, "launch an allowlisted application", ("target",)),
    "open_url": VerbSpec(_verb_open_url, "open an http/https URL in the default browser", ("url",)),
    "media": VerbSpec(_verb_media, "play/pause, next, previous, or stop media", ("action",)),
    "volume": VerbSpec(_verb_volume, "raise, lower, set, or mute system volume", ("action", "level")),
    "brightness": VerbSpec(_verb_brightness, "read or set built-in display brightness", ("level",)),
    "clipboard_get": VerbSpec(_verb_clipboard_get, "read the current clipboard text"),
    "clipboard_set": VerbSpec(_verb_clipboard_set, "place text on the clipboard", ("text",)),
    "notify": VerbSpec(_verb_notify, "show a desktop notification", ("title", "message")),
    "lock": VerbSpec(_verb_lock, "lock the workstation"),
    "sleep_display": VerbSpec(_verb_sleep_display, "turn the display off"),
    "list_windows": VerbSpec(_verb_list_windows, "list visible window titles"),
    "focus_window": VerbSpec(_verb_focus_window, "bring a window to the foreground", ("target",)),
    "battery": VerbSpec(_verb_battery, "battery percentage and charge state"),
    "network": VerbSpec(_verb_network, "Wi-Fi association and traffic counters"),
    "timer": VerbSpec(_verb_timer, "set a spoken reminder N minutes out", ("minutes", "label")),
    "list_timers": VerbSpec(_verb_list_timers, "list pending timers"),
    "cancel_timer": VerbSpec(_verb_cancel_timer, "cancel one timer, or all of them", ("timer_id",)),
}


def host_control(verb: str = "", **kwargs) -> str:
    """
    Single entry point for host actions. Dispatches on an exact verb match
    against VERBS; anything else is refused with the valid list.
    """
    name = (verb or "").strip().lower().replace("-", "_").replace(" ", "_")

    if not config.host_control_enabled:
        audit_action("host", name or "(none)", kwargs, "disabled")
        return (
            "Refused: host control is switched off. The operator can enable it with "
            "'host on'."
        )

    if not name:
        return "Error: 'verb' is required. " + describe_verbs()

    spec = VERBS.get(name)
    if spec is None:
        audit_action("host", name, kwargs, "unknown_verb")
        return f"Refused: '{verb}' is not a host_control verb. " + describe_verbs()

    # Drop anything the verb does not declare, so a stray argument from the model
    # cannot reach a handler's **kwargs and change behaviour.
    accepted = {k: v for k, v in kwargs.items() if k in spec.params}
    rejected = sorted(set(kwargs) - set(accepted))

    try:
        result = spec.handler(**accepted)
        status = "refused" if result.lower().startswith(("refused", "error")) else "ok"
    except Exception as ex:
        result = f"host_control '{name}' failed: {type(ex).__name__}: {ex}"
        status = "error"

    audit_action("host", name, {**accepted, "ignored_args": rejected or ""}, status)

    if rejected:
        result += f"\n(Ignored unrecognised parameter(s): {', '.join(rejected)}.)"
    return result


def describe_verbs() -> str:
    """One-line catalogue of verbs, used in refusal messages."""
    return "Valid verbs: " + ", ".join(sorted(VERBS))


def verb_table() -> List[Tuple[str, str, str]]:
    """(verb, params, summary) rows for the CLI readout."""
    return [
        (name, ", ".join(spec.params) or "-", spec.summary)
        for name, spec in sorted(VERBS.items())
    ]
