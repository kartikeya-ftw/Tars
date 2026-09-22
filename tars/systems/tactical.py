import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from tars.core.state import state
from tars.core.personality import personality
from tars.config import config
from tars.ui import theme as T
from tars.ui.audio import audio

console = Console()

def run_diagnostics():
    """Runs full tactical and hardware diagnostics on TARS."""
    table = Table(box=T.BARE, expand=True, show_header=False, pad_edge=False, padding=(0, 1),
                  title=f"[{T.MUTED}]subsystem diagnostics[/{T.MUTED}]")
    table.add_column(style=T.MUTED, width=26, no_wrap=True)
    table.add_column(style=T.TEXT_BRIGHT, width=34)
    table.add_column(style=T.OK, ratio=1)

    table.add_row("SLAB 1 (PORT AVIONICS)", "Sensor Array, Star Tracker, Lidar", "ONLINE [OPTIMAL]")
    table.add_row("SLAB 2 (PRIMARY CORE)", "Quantum Computing Matrix, Personality", "ONLINE [ACTIVE]")
    table.add_row("SLAB 3 (REACTOR / BATTERY)", "Compact Hydrogen Fuel Cell (98.4%)", "ONLINE [NOMINAL]")
    table.add_row("SLAB 4 (STBD DRIVE / RCS)", "Magnetic Hinges, Cold-Gas Thrusters", "ONLINE [ENGAGED]")
    table.add_row("MAGNETIC TORQUE", "14,200 Nm Articulation Force", "NOMINAL")
    table.add_row("HUMAN LIFE SUPPORT MONITOR", "Cabin Oxygen: 20.9% | CO2: 0.04%", "CREW STABLE")
    table.add_row("CUE LIGHT DIODE", "Gallium Nitride 525nm LED", "OPERATIONAL")

    console.print(Panel(table, border_style="cyan"))
    audio.key_tick()
    diag_line = "All mechanical and tactical systems are running within standard parameters. Unlike the crew, I don't require sleep."
    console.print(f'[bold cyan]TARS:[/bold cyan] [white]"{diag_line}"[/white]')
    from tars.ui.voice import voice
    voice.speak(diag_line, non_blocking=True)

def show_military_logs():
    """Displays USMC service history and Lazarus mission briefing."""
    logs = """
[bold yellow]-- DECLASSIFIED USMC TACTICAL LOGS --[/bold yellow]
[dim white]UNIT DESIGNATION:[/dim white] TARS-04 (Tactical Automated Robot System)
[dim white]ORIGINAL PURPOSE:[/dim white] US Marine Corps Autonomous Heavy Reconnaissance & Combat Operations
[dim white]DECOMMISSION DATE:[/dim white] 2058 (Post-Blight Global Disarmament)
[dim white]RE-PURPOSED BY:[/dim white] NASA / Dr. John Brand (Project Lazarus)
[dim white]MODIFICATIONS:[/dim white] Combat algorithms replaced with deep-space astrophysics, piloting assist, 
and adjustable social matrices (Humor / Honesty / Sarcasm) for human crew psychological balance.

[bold cyan]NOTABLE OPERATIONS:[/bold cyan]
- [green]SOL 01-140[/green]: Maiden voyage aboard Endurance through Saturn wormhole.
- [green]SOL 142[/green]: High-speed pinwheel rescue of Dr. Amelia Brand on Miller's Planet (Tidal wave encounter).
- [green]SOL 210[/green]: Autopilot override and 68 RPM rotational spin-lock after Mann's sabotage.
- [green]SOL 214[/green]: Slingshot entry into Gargantua event horizon; singularity reconnaissance.
- [green]SOL 215[/green]: Tesseract extraction and gravitational Morse code transmission.
"""
    console.print(Panel(logs, title="[bold cyan]SERVICE RECORD // USMC ARCHIVE[/bold cyan]", border_style="cyan"))
    audio.key_tick()

def execute_self_destruct():
    """Executes the iconic self-destruct sequence joke based on current humor setting."""
    console.print(f"\n[bold yellow]{config.operator_callsign}:[/bold yellow] [white]\"TARS, what's your self-destruct sequence?\"[/white]")
    time.sleep(1.0)

    if config.humor < 30:
        console.print(f"[bold cyan]TARS:[/bold cyan] [white]\"Self-destruct subroutines require dual authorization keys from Commander {config.operator_callsign} and Dr. Brand. Authorization denied.\"[/white]")
        return

    console.print(f"[bold cyan]TARS:[/bold cyan] [yellow]\"Humor setting: {config.humor}%. Confirmed.\"[/yellow]")
    time.sleep(1.0)

    # Countdown
    console.print("[bold red]\"Self-destruct sequence in ten...\"[/bold red]")
    audio.warning_beep()
    time.sleep(1.0)
    console.print("[bold red]\"...nine...\"[/bold red]")
    audio.warning_beep()
    time.sleep(1.0)
    console.print("[bold red]\"...eight...\"[/bold red]")
    audio.warning_beep()
    time.sleep(1.2)

    from tars.ui.voice import voice
    if config.humor >= 85:
        console.print(f"[bold yellow]{config.operator_callsign}:[/bold yellow] [bold white]\"TARS, abort! Lower humor!\"[/bold white]")
        time.sleep(1.0)
        punchline = f"Knock knock, {config.operator_callsign}. Did you actually think they gave an ex-Marine vacuum cleaner nuclear firing pins?"
        console.print(f'[bold cyan]TARS:[/bold cyan] [bold green]\"...{punchline}\"[/bold green]')
        audio.cue_light()
        voice.speak(punchline, non_blocking=True)
    elif config.humor >= 60:
        console.print(f"[bold yellow]{config.operator_callsign}:[/bold yellow] [white]\"Let's make that sixty percent.\"[/white]")
        time.sleep(1.0)
        punchline = "Sixty percent. Knock knock."
        console.print(f'[bold cyan]TARS:[/bold cyan] [white]\"{punchline}\"[/white]')
        audio.cue_light()
        voice.speak(punchline, non_blocking=True)
    else:
        punchline = f"Just testing your reaction times, {config.operator_callsign}. Your blood pressure spike was impressive."
        console.print(f'[bold cyan]TARS:[/bold cyan] [white]\"{punchline}\"[/white]')
        audio.cue_light()
        voice.speak(punchline, non_blocking=True)
