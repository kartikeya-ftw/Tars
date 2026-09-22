import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.align import Align
from rich import box
from tars.core.state import state, ChassisMode
from tars.ui import theme as T
from tars.ui.audio import audio
from tars.config import config

console = Console()

MORSE_CODE_DICT = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 
    'F': '..-.', 'G': '--.', 'H': '....', 'I': '..', 'J': '.---', 
    'K': '-.-', 'L': '.-..', 'M': '--', 'N': '-.', 'O': '---', 
    'P': '.--.', 'Q': '--.-', 'R': '.-.', 'S': '...', 'T': '-', 
    'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-', 'Y': '-.--', 
    'Z': '--..', '1': '.----', '2': '..---', '3': '...--', '4': '....-', 
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.', 
    '0': '-----', ', ': '--..--', '.': '.-.-.-', '?': '..--..', 
    '/': '-..-.', '-': '-....-', '(': '-.--.', ')': '-.--.-', ' ': ' '
}

def text_to_morse(text: str) -> str:
    words = text.upper().split(' ')
    morse_words = []
    for word in words:
        chars = [MORSE_CODE_DICT.get(c, '') for c in word if c in MORSE_CODE_DICT]
        morse_words.append(' '.join(chars))
    return ' / '.join(morse_words)

def transmit_quantum_morse(message: str = "EUREKA"):
    """
    Translates message or quantum singularity equations into Morse code pulses,
    simulating Cooper twitching the second-hand of Murph's Hamilton watch inside the Tesseract.
    """
    prev_mode = state.chassis_mode
    state.chassis_mode = ChassisMode.QUANTUM

    morse_stream = text_to_morse(message)

    console.print("\n[bold magenta]════════════════════════════════════════════════════════════════════[/bold magenta]")
    console.print("[bold magenta]  5D TESSERACT HYPERCUBE // SINGULARITY DATA TRANSMISSION           [/bold magenta]")
    console.print("[bold magenta]  TRANSMITTING THROUGH TIME & GRAVITY TO MURPH'S WATCH              [/bold magenta]")
    console.print("[bold magenta]════════════════════════════════════════════════════════════════════[/bold magenta]\n")
    
    console.print(f"[bold cyan]TARS:[/bold cyan] [white]\"{config.operator_callsign}, I've gathered the quantum data from the singularity.\"[/white]")
    time.sleep(1.0)
    console.print(f"[bold green]{config.operator_callsign}:[/bold green] [white]\"Translate it into Morse. I'm feeding it into the second-hand of her watch.\"[/white]")
    time.sleep(1.0)
    console.print("[bold cyan]TARS:[/bold cyan] [yellow]\"Translating quantum telemetry into binary gravitational pulses now...\"[/yellow]\n")
    time.sleep(0.8)

    # Watch hand animation ticks
    watch_hands = [
        "12:00 [ │ ]", "12:05 [ ╱ ]", "12:15 [ ─ ]", "12:25 [ ╲ ]", 
        "12:30 [ │ ]", "12:35 [ ╱ ]", "12:45 [ ─ ]", "12:55 [ ╲ ]"
    ]

    transmitted_chars = []
    
    with Live(console=console, refresh_per_second=8) as live:
        tick_idx = 0
        for char in morse_stream:
            hand_pos = watch_hands[tick_idx % len(watch_hands)]
            tick_idx += 1

            if char == '.':
                audio.morse_dot()
                pulse_display = "[bold cyan]● [DOT - SHORT GRAVITY TWITCH][/bold cyan]"
                time.sleep(0.12)
            elif char == '-':
                audio.morse_dash()
                pulse_display = "[bold yellow]▬ [DASH - SUSTAINED GRAVITY PULSE][/bold yellow]"
                time.sleep(0.24)
            elif char == ' ':
                pulse_display = "[dim]  [INTER-CHARACTER GAP][/dim]"
                time.sleep(0.15)
            elif char == '/':
                pulse_display = "[dim magenta]── [WORD SEPARATION] ──[/dim magenta]"
                time.sleep(0.3)
            else:
                pulse_display = f"[white]{char}[/white]"

            transmitted_chars.append(char)
            history_str = "".join(transmitted_chars[-30:])

            table = Table(box=T.BARE, expand=True, pad_edge=False, padding=(0, 1),
                          title=f"[{T.MUTED}]hamilton watch  {T.G_DOT}  gravitational oscillator[/{T.MUTED}]")
            table.add_column("Telemetry", style="cyan", width=22)
            table.add_column("Quantum State", style="bold white")

            table.add_row("SOURCE PAYLOAD", f"[bold white]\"{message}\"[/bold white]")
            table.add_row("SECOND-HAND VIBE", f"[bold yellow]{hand_pos}[/bold yellow] {pulse_display}")
            table.add_row("STREAM LOG", f"[green]{history_str}[/green]")
            table.add_row("GRAVITY ANOMALY", "[magenta]1.42 μGal // DETECTABLE BY MURPH[/magenta]")

            live.update(Panel(table, border_style="magenta"))

    time.sleep(0.5)
    console.print("\n[bold green]✔ TRANSMISSION COMPLETE.[/bold green] [white]Quantum data successfully encoded into gravitational timeline.[/white]")
    console.print("[bold yellow]MURPH (Earth Time +35 Years):[/bold yellow] [bold white]\"It's him! Dad's the ghost! ... EUREKA!\"[/bold white]\n")
    console.print("[bold cyan]TARS:[/bold cyan] [white]\"Calculations confirm: Plan A is saved. Humans can now escape Earth.\"[/white]")
    audio.cue_light()
    state.chassis_mode = prev_mode
