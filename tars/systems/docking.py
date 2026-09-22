import time
import sys
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn
from rich.table import Table
from rich.live import Live
from rich.align import Align
from rich.text import Text
from rich import box
from tars.ui import theme as T
from tars.ui.audio import audio
from tars.core.state import state, ChassisMode
from tars.config import config

console = Console()

def run_docking_simulation(target_rpm: int = 68):
    """
    Executes the dramatic spin-synchronization docking maneuver with the spinning Endurance.
    """
    prev_mode = state.chassis_mode
    state.chassis_mode = ChassisMode.DOCK

    console.print(T.section("docking", "endurance airlock compromised, uncontrolled rotation"))

    audio.warning_beep()
    time.sleep(1.2)

    console.print("[bold cyan]TARS:[/bold cyan] [white]\"Endurance rotation is sixty-seven... sixty-eight RPM.\"[/white]")
    time.sleep(1.0)
    console.print(f"[bold green]{config.operator_callsign}:[/bold green] [white]\"TARS, get ready to match our spin with the retro thrusters.\"[/white]")
    time.sleep(1.0)
    console.print(f"[bold cyan]TARS:[/bold cyan] [bold yellow]\"{config.operator_callsign}, this is no time for caution!\"[/bold yellow]")
    time.sleep(1.2)
    console.print(f"[bold green]{config.operator_callsign}:[/bold green] [bold white]\"Case, match spin. We're locking on.\"[/bold white]\n")
    time.sleep(1.0)

    current_rpm = 0.0
    distance_m = 120.0
    alignment_pct = 12.0
    stratosphere_alt_km = 45.0

    steps = 18
    rpm_step = target_rpm / steps
    dist_step = 120.0 / steps
    align_step = (100.0 - alignment_pct) / steps

    with Live(console=console, refresh_per_second=6) as live:
        for i in range(steps + 1):
            current_rpm = min(float(target_rpm), current_rpm + rpm_step + (0.4 if i % 2 == 0 else -0.3))
            distance_m = max(0.0, 120.0 - (i * dist_step))
            alignment_pct = min(100.0, 12.0 + (i * align_step))
            stratosphere_alt_km = max(18.2, 45.0 - (i * 1.4))

            # Trigger sound burst
            if i % 3 == 0:
                audio.thruster_pulse()

            status_color = "red" if alignment_pct < 60 else ("yellow" if alignment_pct < 90 else "green")
            
            table = Table(box=T.BARE, expand=True, show_header=False, pad_edge=False, padding=(0, 1))
            table.add_column(style=T.MUTED, width=22, no_wrap=True)
            table.add_column(style=T.TEXT_BRIGHT, width=28)
            table.add_column(style=status_color, ratio=1)

            table.add_row("ENDURANCE ROTATION", f"{target_rpm} RPM [COUNTER-CLOCKWISE]", "[red]UNCONTROLLED[/red]")
            table.add_row("RANGER ROTATION", f"{current_rpm:.1f} RPM", "[green]SYNCHRONIZING...[/green]" if current_rpm < target_rpm else "[bold green]ROTATION MATCHED[/bold green]")
            table.add_row("DISTANCE TO RING", f"{distance_m:.1f} METERS", "[yellow]APPROACHING AT 1.2 m/s[/yellow]" if distance_m > 5 else "[bold green]FINAL CONTACT ZONE[/bold green]")
            table.add_row("DOCKING ALIGNMENT", f"{alignment_pct:.1f}%", f"[{status_color}]AXIAL DRIFT: {max(0.0, (100 - alignment_pct)/10):.2f}°[/{status_color}]")
            table.add_row("ORBITAL DECAY ALT", f"{stratosphere_alt_km:.1f} KM", "[red]CRITICAL STRATOSPHERE ENTRY[/red]" if stratosphere_alt_km < 25 else "[yellow]DECENT RATE HIGH[/yellow]")

            # Movie voice line at 60%
            dialogue = ""
            if i == int(steps * 0.55):
                dialogue = f"\n[bold cyan]TARS:[/bold cyan] [bold red]\"{config.operator_callsign}, it's not possible!\"[/bold red]\n[bold green]{config.operator_callsign.upper()}:[/bold green] [bold white]\"No, it's necessary.\"[/bold white]"
            elif i >= steps:
                dialogue = "\n[bold green]AUTOPILOT:[/bold green] [bold cyan]MAIN DOCKING CLAMPS ENGAGED. HARD ROTATIONAL SEAL ESTABLISHED.[/bold cyan]"

            live.update(Group(table, Text.from_markup(dialogue) if dialogue else Text("")))
            time.sleep(0.35)

    audio.dock_lock()
    time.sleep(0.5)
    console.print()
    console.print(T.ok("docking complete, rotation restored to 0 rpm"))
    dock_line = f"Nice flying, {config.operator_callsign}. Next time, let's see if we can do it without shedding an airlock."
    console.print(f"[{T.TEXT}]{dock_line}[/{T.TEXT}]")
    audio.cue_light()
    from tars.ui.voice import voice
    voice.speak(dock_line, non_blocking=True)
    state.chassis_mode = prev_mode
