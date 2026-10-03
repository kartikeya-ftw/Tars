"""
TARS - Proactive Sentinel

A background watcher that speaks without being asked. This is the difference
between an assistant that is summoned and one that is resident: nothing else in
the suite initiates contact.

Each rule is a condition plus a latch. The latch arms when the condition becomes
true, fires once, and only re-arms after the condition has cleared, so a battery
sitting at 14% produces one warning rather than one per poll. A cooldown floor
gives a second layer of protection against chatter.

Readings come from psutil, the same source as get_system_telemetry, so the
sentinel and the telemetry readout can never disagree.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from rich.console import Console
from rich.text import Text

from tars.config import config
from tars.core.security import audit_action
from tars.ui import theme as T

console = Console()

# A rule returns (triggered, message) on each poll.
RuleFn = Callable[[], Tuple[bool, str]]


@dataclass
class Rule:
    """One watched condition with its own latch and cooldown."""

    name: str
    check: RuleFn
    cooldown: float = 900.0
    speak: bool = True
    _armed: bool = field(default=True, repr=False)
    _last_fired: float = field(default=0.0, repr=False)

    def evaluate(self, now: float) -> Optional[str]:
        try:
            triggered, message = self.check()
        except Exception:
            return None

        if not triggered:
            # Condition cleared: re-arm so the next occurrence is reported.
            self._armed = True
            return None

        if not self._armed or (now - self._last_fired) < self.cooldown:
            return None

        self._armed = False
        self._last_fired = now
        return message


def _battery_low() -> Tuple[bool, str]:
    import psutil

    bat = psutil.sensors_battery()
    if bat is None or bat.power_plugged:
        return False, ""
    if bat.percent > 15:
        return False, ""
    tail = ""
    if bat.secsleft and bat.secsleft > 0:
        tail = f" About {int(bat.secsleft) // 60} minutes left."
    return True, f"Battery at {bat.percent:.0f}% and unplugged.{tail}"


def _battery_critical() -> Tuple[bool, str]:
    import psutil

    bat = psutil.sensors_battery()
    if bat is None or bat.power_plugged or bat.percent > 7:
        return False, ""
    return True, f"Battery critical, {bat.percent:.0f}%. Plug in now."


def _battery_charged() -> Tuple[bool, str]:
    import psutil

    bat = psutil.sensors_battery()
    if bat is None or not bat.power_plugged or bat.percent < 97:
        return False, ""
    return True, f"Battery at {bat.percent:.0f}%. You can unplug."


def _disk_pressure() -> Tuple[bool, str]:
    import psutil

    from tars.core.security import PROJECT_ROOT

    usage = psutil.disk_usage(str(PROJECT_ROOT))
    free_gb = usage.free / (1024 ** 3)
    if usage.percent < 92:
        return False, ""
    return True, f"Disk is {usage.percent:.0f}% full, {free_gb:.1f} gigabytes free."


def _memory_pressure() -> Tuple[bool, str]:
    import psutil

    mem = psutil.virtual_memory()
    if mem.percent < 93:
        return False, ""
    return True, f"Memory at {mem.percent:.0f}%. Something is holding a lot of RAM."


class _SustainedCpu:
    """
    Fires when CPU stays high across consecutive polls rather than on one spike.
    A single 95% sample is just a build starting; four in a row is a problem.
    """

    def __init__(self, threshold: float = 88.0, samples: int = 4) -> None:
        self.threshold = threshold
        self.samples = samples
        self._hits = 0

    def __call__(self) -> Tuple[bool, str]:
        import psutil

        pct = psutil.cpu_percent(interval=0.4)
        if pct < self.threshold:
            self._hits = 0
            return False, ""
        self._hits += 1
        if self._hits < self.samples:
            return False, ""
        self._hits = 0
        try:
            procs = sorted(
                psutil.process_iter(["name", "cpu_percent"]),
                key=lambda p: p.info.get("cpu_percent") or 0,
                reverse=True,
            )
            worst = next((p.info.get("name") for p in procs if p.info.get("name")), None)
        except Exception:
            worst = None
        tail = f" {worst} is the biggest consumer." if worst else ""
        return True, f"CPU has been above {self.threshold:.0f}% for a while.{tail}"


class Sentinel:
    """Owns the watcher thread and the rule set."""

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.rules: List[Rule] = [
            Rule("battery_critical", _battery_critical, cooldown=300.0),
            Rule("battery_low", _battery_low, cooldown=900.0),
            Rule("battery_charged", _battery_charged, cooldown=1800.0),
            Rule("disk_pressure", _disk_pressure, cooldown=3600.0),
            Rule("memory_pressure", _memory_pressure, cooldown=1800.0),
            Rule("cpu_sustained", _SustainedCpu(), cooldown=1800.0),
        ]

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.is_running:
            return False
        try:
            import psutil  # noqa: F401
        except ImportError:
            console.print(T.error("psutil is not installed, so the sentinel cannot read host state"))
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="tars-sentinel")
        self._thread.start()
        audit_action("sentinel", "started", {"interval": config.proactive_interval}, "ok")
        return True

    def stop(self) -> bool:
        if not self.is_running:
            return False
        self._stop.set()
        audit_action("sentinel", "stopped", {}, "ok")
        return True

    def _announce(self, rule_name: str, message: str) -> None:
        line = Text.assemble(
            ("  ", ""),
            ("!", T.WARN),
            ("  ", ""),
            ("TARS", f"bold {T.ACCENT}"),
            ("  ", ""),
            (message, T.TEXT),
        )
        console.print()
        console.print(line)
        console.print()
        audit_action("sentinel", rule_name, {"message": message}, "announced")

        try:
            from tars.ui.voice import voice

            voice.speak(message, non_blocking=True)
        except Exception:
            pass

        try:
            from tars.core.host import host_control

            host_control(verb="notify", title="TARS", message=message)
        except Exception:
            pass

    def _loop(self) -> None:
        # Let the shell finish drawing before the first poll, and avoid greeting
        # the operator with an alert the instant they enable this.
        self._stop.wait(5.0)
        while not self._stop.is_set():
            if not config.proactive_enabled:
                self._stop.wait(5.0)
                continue

            now = time.time()
            for rule in self.rules:
                if self._stop.is_set():
                    break
                message = rule.evaluate(now)
                if message:
                    self._announce(rule.name, message)

            interval = max(15, int(config.proactive_interval or 60))
            self._stop.wait(interval)

    def status_rows(self) -> List[Tuple[str, str]]:
        """Label/value pairs for the CLI readout."""
        rows = [
            ("state", "watching" if self.is_running else "idle"),
            ("enabled", "yes" if config.proactive_enabled else "no"),
            ("poll interval", f"{max(15, int(config.proactive_interval or 60))}s"),
            ("rules", str(len(self.rules))),
        ]
        for rule in self.rules:
            state = "armed" if rule._armed else "latched"
            rows.append((rule.name.replace("_", " "), state))
        return rows


sentinel = Sentinel()
