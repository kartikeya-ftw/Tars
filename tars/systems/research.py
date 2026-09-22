import time
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.table import Table
from rich import box
from tars.config import config
from tars.core.state import state, ChassisMode
from tars.core.personality import personality
from tars.ui.audio import audio

console = Console()

def run_deep_research(topic: str) -> str:
    """
    Executes an in-depth research investigation on any scientific, tactical, or general topic.
    Combines live LLM synthesis with NASA Endurance telemetry formatting.
    """
    cleaned = topic.strip()
    if not cleaned:
        console.print("[bold red]Please specify a research topic. Usage: research <topic>[/bold red]")
        return ""

    prev_mode = state.chassis_mode
    state.chassis_mode = ChassisMode.QUANTUM

    console.print(f"\n[bold cyan]╔════════════════════════════════════════════════════════════════════╗[/bold cyan]")
    console.print(f"[bold cyan]║  TARS DEEP-SPACE RESEARCH SUBSYSTEM // ARCHIVE QUERY               ║[/bold cyan]")
    console.print(f"[bold cyan]║  TARGET SUBJECT: {cleaned.upper():<48}  ║[/bold cyan]")
    console.print(f"[bold cyan]╚════════════════════════════════════════════════════════════════════╝[/bold cyan]\n")

    audio.key_tick()

    # Step 1: Live Web Grounding Search
    from tars.core.tools import web_search, fetch_url
    from tars.core.memory import memory
    from pathlib import Path

    console.print(f"[dim cyan]>[/dim cyan] [dim white]Conducting live web sweep for '{cleaned}'...[/dim white]")
    audio.key_tick()
    web_data = web_search(cleaned, num_results=4)

    # Step 2: Animated scan sequence
    scan_steps = [
        "Indexing NASA Lazarus & JPL astrophysics repositories...",
        "Querying US Marine Corps tactical sensor databases...",
        "Correlating live web telemetry and citations...",
        "Synthesizing findings through quantum computing matrix..."
    ]

    for step in scan_steps:
        console.print(f"[dim cyan]>[/dim cyan] [dim white]{step}[/dim white]")
        audio.key_tick()
        time.sleep(0.2)

    from tars.core.llm import extract_text, generate, resolve_api_key

    if not resolve_api_key():
        console.print("[bold yellow]Warning: Gemini API Key not configured. Using cached tactical knowledge base.[/bold yellow]")
        time.sleep(0.5)

    current_date = datetime.now().strftime("%A, %B %d, %Y, %H:%M:%S")

    system_instruction = (
        f"You are TARS, the tactical automated robot system (USMC Unit 04) from Interstellar. "
        f"You are conducting a thorough, rigorous research investigation on the requested topic for Commander {config.operator_callsign}. "
        f"Current Earth date/time: {current_date}. "
        f"Settings: Humor: {config.humor}%, Honesty: {config.honesty}%, Sarcasm: {config.sarcasm}%. "
        f"Format your response as a professional, deeply informative scientific/tactical report in GitHub markdown: "
        f"1. **EXECUTIVE SUMMARY** (Concise, accurate high-level synthesis) "
        f"2. **TECHNICAL & THEORETICAL ANALYSIS** (Deep dive into mechanics, verified facts, or principles) "
        f"3. **GROUNDED SOURCES & CITATIONS** (Reference real URLs and findings gathered from telemetry) "
        f"4. **MISSION IMPLICATIONS & RISKS** (Hazards, practical challenges, or critical insights) "
        f"5. **TARS TACTICAL ASSESSMENT** (1-2 sentences of dry, deadpan military conclusion tailored to your current humor and honesty settings). "
        f"Do NOT use emojis. Maintain TARS's intellectual competence and understated wit."
    )

    prompt = (
        f"Perform a comprehensive, factual research dossier on: '{cleaned}'.\n\n"
        f"VERIFIED TELEMETRY & LIVE WEB EVIDENCE:\n{web_data}\n\n"
        f"Incorporate the findings and cite the sources gathered above."
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
    }

    resp_data, _model, last_error = generate(payload, timeout=40)
    report_content = extract_text(resp_data) if resp_data else ""

    if not report_content:
        report_content = f"""
### 1. MISSION ALERT: LIVE DOSSIER SYNTHESIS INCOMPLETE
Could not retrieve full neural report ({last_error}).

### 2. LIVE WEB TELEMETRY GATHERED:
{web_data}

### 3. TARS TACTICAL ASSESSMENT
Honesty setting: {config.honesty}%. I've compiled the raw web telemetry above, but neural synthesis dropped. Check your comms link or query me again, {config.operator_callsign}.
"""

    state.chassis_mode = prev_mode
    audio.dock_lock()

    # Automatically archive to mission_logs/
    logs_dir = Path("mission_logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    clean_filename = "".join(c for c in cleaned if c.isalnum() or c in (" ", "_", "-")).rstrip()
    filename = logs_dir / f"research_{clean_filename.replace(' ', '_')}_{int(time.time())}.md"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# TARS Research Dossier: {cleaned.upper()}\n\n{report_content}\n")
        export_notice = f"[dim green]✔ Dossier archived to: {filename}[/dim green]"
    except Exception:
        export_notice = ""

    # Archive in persistent memory
    memory.record_mission(f"Research: {cleaned}", f"Compiled dossier with live web telemetry.", success=True)

    console.print("\n")
    panel = Panel(
        Markdown(report_content),
        title=f"[bold cyan]RESEARCH REPORT // SUBJECT: {cleaned.upper()}[/bold cyan]",
        subtitle=f"[dim]GENERATED BY TARS-04 | H: {config.humor}% | HON: {config.honesty}%[/dim]",
        border_style="cyan",
        padding=(1, 2)
    )
    console.print(panel)
    if export_notice:
        console.print(export_notice)
    audio.cue_light()
    from tars.ui.voice import voice
    voice.speak(f"Research dossier on {cleaned} compiled and displayed on HUD, {config.operator_callsign}.", non_blocking=True)
    return report_content

