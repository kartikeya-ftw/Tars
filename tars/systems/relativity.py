import math
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from tars.core.personality import personality
from tars.ui import theme as T
from tars.ui.audio import audio
from tars.config import config

console = Console()

def calculate_time_dilation(hours_on_miller: float = 1.0):
    """
    Calculates time dilation between Miller's Planet (in Gargantua's gravitational well)
    and Earth / Endurance orbital frame.
    """
    # Exact film ratio: 1 hour on Miller's planet = 7 Earth years
    EARTH_YEARS_PER_MILLER_HOUR = 7.0
    DAYS_PER_YEAR = 365.25
    HOURS_PER_DAY = 24.0

    earth_years_elapsed = hours_on_miller * EARTH_YEARS_PER_MILLER_HOUR
    earth_days_elapsed = earth_years_elapsed * DAYS_PER_YEAR
    earth_hours_elapsed = earth_days_elapsed * HOURS_PER_DAY

    # Each tick in the Zimmer score = 1.25 Earth days (every 0.85 seconds)
    ticks_elapsed = int(earth_days_elapsed / 1.25)

    table = Table(box=T.BARE, expand=True, pad_edge=False, padding=(0, 1),
                  title=f"[{T.MUTED}]gargantua ergosphere  {T.G_DOT}  time dilation[/{T.MUTED}]")
    table.add_column("Location / Frame", style="bold yellow", width=26)
    table.add_column("Time Elapsed", style="bold white", width=24)
    table.add_column("Comparative Factor", style="cyan")

    table.add_row("MILLER'S PLANET SURFACE", f"{hours_on_miller:.2f} HOURS ({hours_on_miller*60:.1f} mins)", "1.00x [PROPER TIME]")
    table.add_row("ENDURANCE ORBIT (Romilly)", f"{earth_years_elapsed:.2f} YEARS", f"61,320.00x SLOWER")
    table.add_row("EARTH SURFACE (Murph/NASA)", f"{earth_years_elapsed:.2f} YEARS ({earth_days_elapsed:,.1f} days)", "DILATION RATIO: 1h = 7y")
    table.add_row("METRONOME PULSES (Ticks)", f"{ticks_elapsed:,} TICKS", "1 TICK ≈ 1.25 EARTH DAYS")

    comment = ""
    if hours_on_miller >= 3.0:
        comment = (
            f"[bold cyan]TARS:[/bold cyan] \"Coop, Brand was gone for just over three hours. "
            f"By the time we got back up, Romilly had aged twenty-three years, four months, and eight days. "
            f"Every second down there is cost in human generations.\""
        )
    else:
        comment = (
            f"[bold cyan]TARS:[/bold cyan] \"At this proximity to Gargantua, time is a non-renewable resource, {config.operator_callsign}. "
            f"Try not to linger for a swim.\""
        )

    panel = Panel(
        table,
        subtitle=comment,
        border_style="cyan"
    )
    console.print(panel)
    audio.key_tick()

def calculate_schwarzschild_dilation(mass_solar: float, radius_km: float, proper_minutes: float = 60.0):
    """
    General Relativity gravitational time dilation calculator based on Schwarzschild metric:
    t_coord = t_proper / sqrt(1 - 2GM / (r * c^2))
    """
    G = 6.67430e-11
    M_sun = 1.989e30
    c = 299792458.0

    M = mass_solar * M_sun
    r = radius_km * 1000.0

    # Schwarzschild radius r_s = 2GM / c^2
    r_s = (2.0 * G * M) / (c ** 2)

    if r <= r_s:
        console.print(f"[bold red]FATAL TELEMETRY: Radius {radius_km:.1f} km is within or at the event horizon (r_s = {r_s/1000.0:.1f} km). Infinite time dilation / Singularity reached.[/bold red]")
        return

    factor = 1.0 / math.sqrt(1.0 - (r_s / r))
    coord_minutes = proper_minutes * factor

    table = Table(box=box.SIMPLE_HEAD, title="[bold magenta]GENERAL RELATIVITY // GRAVITATIONAL WELL ANALYSIS[/bold magenta]")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold white")

    table.add_row("BLACK HOLE MASS", f"{mass_solar:,.1f} Solar Masses")
    table.add_row("EVENT HORIZON RADIUS (r_s)", f"{r_s/1000.0:,.1f} km")
    table.add_row("ORBITAL RADIUS (r)", f"{radius_km:,.1f} km ({radius_km / (r_s/1000.0):.2f} r_s)")
    table.add_row("PROPER TIME AT ORBIT", f"{proper_minutes:.2f} minutes")
    table.add_row("ASYMPTOTIC OBSERVER TIME", f"{coord_minutes:.2f} minutes ({coord_minutes / 60:.2f} hours)")
    table.add_row("GRAVITATIONAL TIME FACTOR", f"{factor:.4f}x")

    console.print(Panel(table, border_style="magenta"))
    audio.key_tick()
