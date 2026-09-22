import sys
import time
import os
import shlex

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        os.system("chcp 65001 >nul 2>&1")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style

from tars.config import config
from tars.core.state import state, ChassisMode
from tars.core.personality import personality
from tars.ui import theme as T
from tars.ui.audio import audio
from tars.ui.monolith import get_monolith_render
from tars.ui.banner import get_hud_banner, get_masthead
from tars.ui.voice import voice
from tars.core.memory import memory
from tars.core.agent import tars_agent
from tars.core.tools import (
    TOOL_REGISTRY,
    GEMINI_TOOLS_DECLARATION,
    get_system_telemetry,
    inspect_screen,
    analyze_pdf,
    analyze_data,
    generate_chart,
    find_symbols,
    git_ops
)
from tars.systems import (
    run_docking_simulation,
    calculate_time_dilation,
    calculate_schwarzschild_dilation,
    transmit_quantum_morse,
    run_diagnostics,
    show_military_logs,
    execute_self_destruct,
    process_chat,
    run_deep_research,
    run_autonomous_goal,
    run_case_task,
    run_kipp_research,
    run_hive_mission
)

console = Console()

COMMANDS_LIST = [
    "help", "status", "monolith", "chassis", "dock", "relativity",
    "morse", "research", "listen", "voice", "voice-chat", "self-destruct",
    "diagnostics", "logs", "settings", "humor", "honesty", "sarcasm",
    "sound", "callsign", "api-key", "clear", "exit", "quit",
    "goal", "/goal", "memory", "/memory", "tools", "/tools",
    "sys", "telemetry", "avionics",
    "case", "/case", "kipp", "/kipp", "hive", "/hive",
    "heal", "look", "screen", "pdf", "data", "symbols", "git",
    "units", "new"
]

prompt_style = Style.from_dict({
    'unit': f'{T.ACCENT} bold',
    'callsign': f'{T.MUTED}',
    'symbol': f'{T.FAINT}',
})

def print_typewriter(text: str, speed: float = 0.01):
    """Outputs text with subtle typewriter cadence."""
    if not config.typewriter_effect:
        console.print(text)
        return
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(speed)
    sys.stdout.write("\n")
    sys.stdout.flush()

HELP_GROUPS = [
    ("units", [
        ("case <task>", "dispatch CASE (Unit 02) for code, shell, and test work"),
        ("kipp <query>", "dispatch KIPP (Unit 01) for sourced research and verification"),
        ("hive <objective>", "TARS commands, delegating to CASE and KIPP as needed"),
        ("units", "show the unit roster, personalities, and tool scopes"),
    ]),
    ("work", [
        ("goal <objective>", "plan a multi-step objective and execute it with a live checklist"),
        ("heal <command>", "run a command, diagnose failures, patch, and re-run"),
        ("research <topic>", "grounded web research, archived to mission_logs/"),
        ("<anything else>", "speak to TARS directly; it will use tools as required"),
    ]),
    ("inspect", [
        ("look / screen", "capture the desktop and analyse it with vision"),
        ("pdf <file> [query]", "extract and query a PDF"),
        ("data <file> [query]", "load a CSV/TSV/Excel file and summarise it"),
        ("symbols [path]", "index classes and functions via AST"),
        ("git <subcommand>", "run a git operation in the workspace"),
        ("sys", "live CPU, memory, disk, and battery readings"),
        ("tools", "list every tool and which units may use it"),
    ]),
    ("session", [
        ("status", "session and host status readout"),
        ("memory [clear]", "inspect or wipe persistent memory and mission log"),
        ("new", "clear conversation context for all units"),
        ("settings", "current configuration"),
        ("callsign <name>", "set how TARS addresses you"),
        ("api-key <key>", "attach a Gemini API key"),
        ("clear", "clear the screen"),
        ("exit", "shut down"),
    ]),
    ("voice", [
        ("listen", "capture one spoken command"),
        ("voice-chat", "continuous hands-free conversation"),
        ("voice on | off", "toggle speech synthesis"),
        ("sound on | off", "toggle audio feedback"),
    ]),
    ("personality", [
        ("humor <0-100>", "TARS humor level"),
        ("honesty <0-100>", "TARS candour level"),
        ("sarcasm <0-100>", "TARS sarcasm level"),
        ("chassis <mode>", "monolith | walk | roll | dock | quantum"),
    ]),
    ("simulation", [
        ("dock [rpm]", "Endurance spin-docking sequence"),
        ("relativity [hrs]", "Miller's planet time dilation"),
        ("morse <text>", "gravitational Morse transmission"),
        ("diagnostics", "subsystem self-check"),
        ("logs", "service record"),
        ("self-destruct", "the countdown"),
    ]),
]


def show_help():
    """
    Renders the command reference, grouped by intent.

    Built as a single table so the command column stays aligned across every
    group. Cells are Text objects rather than markup strings, because several
    commands contain square brackets (`pdf <file> [query]`) which Rich would
    otherwise parse as style tags and silently drop.
    """
    table = Table(box=T.BARE, show_header=False, expand=True, pad_edge=False, padding=(0, 1))
    table.add_column(width=26, no_wrap=True)
    table.add_column(ratio=1, overflow="fold")

    for gi, (group, entries) in enumerate(HELP_GROUPS):
        if gi:
            table.add_row("", "")
        table.add_row(Text(f"  {group.upper()}", style=f"bold {T.MUTED}"), "")
        for cmd, desc in entries:
            table.add_row(
                Text(f"    {cmd}", style=T.TEXT_BRIGHT),
                Text(desc, style=T.MUTED),
            )

    console.print()
    console.print(table)
    console.print()
    audio.key_tick()


def show_units():
    """Shows the unit roster: personality, tool scope, and how to reach each one."""
    from tars.core.agents import ROSTER

    console.print()
    console.print(T.rule("unit roster"))
    for key in ("TARS", "CASE", "KIPP"):
        p = ROSTER[key]
        color = T.AGENT_COLORS[key]
        console.print()
        console.print(
            f"  [bold {color}]{p.name}[/bold {color}]  [{T.MUTED}]{p.designation}[/{T.MUTED}]"
            f"   [{T.FAINT}]{T.G_DOT}[/{T.FAINT}]   [{T.TEXT}]{p.role}[/{T.TEXT}]"
        )
        humor = "operator-set" if p.humor is None else f"{p.humor}%"
        honesty = "operator-set" if p.honesty is None else f"{p.honesty}%"
        rows = [
            ("humor", humor),
            ("honesty", honesty),
            ("tool scope", f"{len(p.tools)} tools"),
            ("step ceiling", str(p.max_steps)),
            ("reasoning", "extended" if p.thinking_budget else "fast"),
            ("reach via", "default prompt" if key == "TARS" else f"{key.lower()} <task>"),
        ]
        console.print(T.kv_table(rows, columns=2, label_width=14))
    console.print()
    console.print(T.hint("TARS delegates to CASE and KIPP on its own when a task suits them"))
    console.print()

def show_settings():
    from tars.core.llm import TEXT_MODELS, resolve_api_key

    if resolve_api_key():
        key_state = "set in .tars_config.json" if config.key_is_persisted_to_disk else "set from environment"
    else:
        key_state = f"[{T.WARN}]not configured[/{T.WARN}]"

    rows = [
        ("humor", f"{config.humor}%"),
        ("honesty", f"{config.honesty}%"),
        ("sarcasm", f"{config.sarcasm}%"),
        ("callsign", config.operator_callsign),
        ("speech output", "on" if config.voice_output_enabled else "off"),
        ("microphone", "ready" if config.voice_input_enabled else "off"),
        ("audio feedback", "on" if config.sound_enabled else "off"),
        ("typewriter", "on" if config.typewriter_effect else "off"),
        ("api key", key_state),
        ("model order", ", ".join(TEXT_MODELS[:3]) + " ..."),
    ]
    console.print()
    console.print(T.rule("settings"))
    console.print(T.kv_table(rows, columns=2, label_width=16))
    if config.key_is_persisted_to_disk:
        console.print()
        console.print(T.warn(
            "API key is stored in plaintext in .tars_config.json. If this folder syncs to "
            "OneDrive, move it to .env instead (see .env.example)."
        ))
    console.print()

def execute_command(user_input: str) -> bool:
    """
    Parses and executes a user command or routes to conversational AI.
    Returns False to exit the loop, True to continue.
    """
    raw = user_input.strip()
    if not raw:
        return True

    state.commands_processed += 1
    parts = raw.split()
    cmd = parts[0].lower()
    args = parts[1:]

    # Reset cue light at start of each new command
    state.cue_light_active = False

    if cmd in ["exit", "quit", "powerdown", "shutdown"]:
        console.print()
        console.print(T.info(f"see you on the other side, {config.operator_callsign}."))
        audio.key_tick()
        time.sleep(0.8)
        return False

    elif cmd in ["clear", "cls"]:
        os.system("cls" if os.name == "nt" else "clear")
        console.print(get_hud_banner())
        return True

    elif cmd in ["help", "?"]:
        show_help()
        return True

    elif cmd in ["sys", "telemetry", "avionics"]:
        _report("host telemetry", get_system_telemetry())
        return True

    elif cmd in ["status", "hud"]:
        console.print(get_hud_banner())
        return True

    elif cmd == "monolith":
        console.print(get_monolith_render())
        return True

    elif cmd == "chassis":
        if not args:
            console.print(get_monolith_render())
            console.print("[dim]Modes available: monolith, walk, roll, dock, quantum[/dim]")
            return True
        mode_str = args[0].upper()
        try:
            new_mode = ChassisMode[mode_str]
            state.chassis_mode = new_mode
            console.print(T.info(f"chassis reconfigured: {new_mode.value.lower()}"))
            audio.thruster_pulse()
            console.print(get_monolith_render(new_mode))
        except KeyError:
            console.print(T.error(f"unknown mode '{args[0]}'. choose: monolith, walk, roll, dock, quantum"))
        return True

    elif cmd == "settings":
        show_settings()
        return True

    elif cmd == "humor":
        if not args:
            console.print(T.info(f"humor is {config.humor}%"))
            return True
        try:
            val = int(args[0].replace("%", ""))
            ack, trigger_cue = personality.set_humor(val)
            state.cue_light_active = trigger_cue
            if trigger_cue:
                audio.cue_light()
            _say(ack, trigger_cue, speak=False)
        except ValueError:
            console.print(T.error("usage: humor <0-100>"))
        return True

    elif cmd == "honesty":
        if not args:
            console.print(T.info(f"honesty is {config.honesty}%"))
            return True
        try:
            val = int(args[0].replace("%", ""))
            ack, trigger_cue = personality.set_honesty(val)
            state.cue_light_active = trigger_cue
            if trigger_cue:
                audio.cue_light()
            _say(ack, trigger_cue, speak=False)
        except ValueError:
            console.print(T.error("usage: honesty <0-100>"))
        return True

    elif cmd == "sarcasm":
        if not args:
            console.print(T.info(f"sarcasm is {config.sarcasm}%"))
            return True
        try:
            val = int(args[0].replace("%", ""))
            ack, trigger_cue = personality.set_sarcasm(val)
            state.cue_light_active = trigger_cue
            if trigger_cue:
                audio.cue_light()
            _say(ack, trigger_cue, speak=False)
        except ValueError:
            console.print(T.error("usage: sarcasm <0-100>"))
        return True

    elif cmd == "sound":
        if not args:
            status = "ENABLED" if config.sound_enabled else "MUTED"
            console.print(f"Audio harness status: {status}. Usage: sound on | sound off")
            return True
        arg = args[0].lower()
        if arg in ["on", "enable", "1"]:
            config.sound_enabled = True
            config.save()
            audio.key_tick()
            console.print(T.ok("audio feedback on"))
        elif arg in ["off", "disable", "mute", "0"]:
            config.sound_enabled = False
            config.save()
            console.print(T.info("audio feedback off"))
        else:
            console.print(T.warn("usage: sound on | off"))
        return True

    elif cmd == "voice":
        if not args:
            status = "ENABLED (Speaking)" if config.voice_output_enabled else "MUTED"
            console.print(f"TARS voice synthesis is {status}. Usage: voice on | voice off | voice listen | voice-chat")
            return True
        arg = args[0].lower()
        if arg in ["on", "enable", "1"]:
            config.voice_output_enabled = True
            config.save()
            console.print(T.ok("speech output on"))
            voice.speak(f"Voice output operational, {config.operator_callsign}.", non_blocking=True)
        elif arg in ["off", "disable", "mute", "0"]:
            config.voice_output_enabled = False
            config.save()
            console.print(T.info("speech output off"))
        elif arg in ["listen", "mic", "in"]:
            speech = voice.listen(timeout_seconds=6)
            if speech:
                execute_command(speech)
        elif arg in ["chat", "loop"]:
            run_voice_loop()
        else:
            console.print("Usage: voice on | off | listen | chat")
        return True

    elif cmd in ["listen", "mic", "hear"]:
        speech = voice.listen(timeout_seconds=6)
        if speech:
            execute_command(speech)
        return True

    elif cmd in ["voice-chat", "voice-loop", "handsfree"]:
        run_voice_loop()
        return True

    elif cmd == "callsign":
        if not args:
            console.print(f"Current operator callsign: '{config.operator_callsign}'. Usage: callsign <name>")
            return True
        config.operator_callsign = " ".join(args)
        config.save()
        console.print(T.ok(f"callsign set to '{config.operator_callsign}'"))
        return True

    elif cmd in ["api-key", "geminikey", "key", "gemini"]:
        if not args:
            from tars.core.llm import resolve_api_key
            if resolve_api_key():
                console.print(T.ok("api key active"))
            else:
                console.print(T.warn("no api key configured, running offline heuristics"))
                console.print(T.hint("get one at https://aistudio.google.com/app/apikey"))
                console.print(T.hint("then run: api-key <your_key>   (or put it in .env)"))
            return True
        config.gemini_api_key = args[0].strip()
        config.save()
        console.print(T.ok("api key saved, live reasoning enabled"))
        audio.cue_light()
        return True

    elif cmd == "dock":
        rpm = 68
        if args:
            try:
                rpm = int(args[0])
            except ValueError:
                pass
        run_docking_simulation(target_rpm=rpm)
        return True

    elif cmd in ["relativity", "time", "dilation"]:
        if args and args[0].lower() == "schwarzschild":
            # Usage: relativity schwarzschild <mass> <radius>
            mass = float(args[1]) if len(args) > 1 else 100000000.0 # Gargantua 100M suns
            radius = float(args[2]) if len(args) > 2 else 500000000.0
            calculate_schwarzschild_dilation(mass, radius)
        else:
            hours = 1.0
            if args:
                try:
                    hours = float(args[0])
                except ValueError:
                    pass
            calculate_time_dilation(hours)
        return True

    elif cmd in ["morse", "quantum", "watch"]:
        msg = "EUREKA"
        if args:
            msg = " ".join(args)
        transmit_quantum_morse(msg)
        return True

    elif cmd in ["research", "study", "analyze"]:
        if not args:
            console.print(T.warn("usage: research <topic>"))
            return True
        run_deep_research(" ".join(args))
        return True

    elif cmd in ["self-destruct", "selfdestruct"]:
        execute_self_destruct()
        return True

    elif cmd in ["diagnostics", "diag"]:
        run_diagnostics()
        return True

    elif cmd in ["logs", "log", "archives"]:
        show_military_logs()
        return True

    elif cmd in ["goal", "/goal"]:
        if not args:
            console.print(T.warn("usage: goal <objective>"))
            return True
        run_autonomous_goal(" ".join(args))
        return True

    elif cmd in ["memory", "/memory"]:
        if args and args[0].lower() in ["clear", "reset"]:
            memory.clear()
            console.print(T.ok("persistent memory cleared"))
        elif args and args[0].lower() in ["remember", "add"]:
            memory.remember_fact(" ".join(args[1:]))
            console.print(T.ok("fact archived"))
        else:
            console.print()
            console.print(T.rule("memory"))
            console.print(memory.get_memory_summary())
            console.print()
        return True

    elif cmd in ["tools", "/tools"]:
        from tars.core.agent import DELEGATION_DECLARATIONS
        from tars.core.agents import CASE_TOOLS, KIPP_TOOLS

        all_decls = list(GEMINI_TOOLS_DECLARATION) + list(DELEGATION_DECLARATIONS)
        console.print()
        console.print(T.rule(f"tool registry  {T.G_DOT}  {len(all_decls)} tools"))
        t_table = Table(box=T.BARE, show_header=True, expand=True, pad_edge=False, padding=(0, 1))
        t_table.add_column("", style=f"bold {T.TEXT_BRIGHT}", width=22, no_wrap=True)
        t_table.add_column("units", width=16, no_wrap=True)
        t_table.add_column("", style=T.MUTED, overflow="fold")

        for decl in all_decls:
            name = decl["name"]
            holders = []
            if name in CASE_TOOLS:
                holders.append(f"[{T.AGENT_COLORS['CASE']}]CASE[/{T.AGENT_COLORS['CASE']}]")
            if name in KIPP_TOOLS:
                holders.append(f"[{T.AGENT_COLORS['KIPP']}]KIPP[/{T.AGENT_COLORS['KIPP']}]")
            scope = f"[{T.ACCENT}]TARS[/{T.ACCENT}]" + ("  " + " ".join(holders) if holders else "")
            desc = decl.get("description", "").split(".")[0].strip()
            t_table.add_row(f"  {name}", scope, desc)
        console.print(t_table)
        console.print()
        audio.key_tick()
        return True

    elif cmd in ["units", "roster", "agents"]:
        show_units()
        return True

    elif cmd in ["new", "reset"]:
        from tars.core.agent import reset_all_conversations

        reset_all_conversations()
        console.print(T.ok("conversation context cleared for all units"))
        return True

    elif cmd in ["case", "/case"]:
        if not args:
            console.print(T.warn("usage: case <technical task>"))
            return True
        run_case_task(" ".join(args))
        return True

    elif cmd in ["kipp", "/kipp"]:
        if not args:
            console.print(T.warn("usage: kipp <research question>"))
            return True
        run_kipp_research(" ".join(args))
        return True

    elif cmd in ["hive", "/hive"]:
        if not args:
            console.print(T.warn("usage: hive <objective>"))
            return True
        run_hive_mission(" ".join(args))
        return True

    elif cmd in ["heal", "selfheal", "fix"]:
        if not args:
            console.print(T.warn("usage: heal <command>"))
            return True
        tars_agent.heal_and_execute(" ".join(args), max_retries=3, verbose=True)
        return True

    elif cmd in ["look", "screen", "inspect-screen"]:
        query = " ".join(args) if args else "Analyze what is visible on this desktop screen."
        console.print(T.info("capturing screen and analysing"))
        audio.key_tick()
        _report("screen", inspect_screen(query))
        return True

    elif cmd in ["pdf", "analyze-pdf"]:
        if not args:
            console.print(T.warn("usage: pdf <file.pdf> [query]"))
            return True
        q = " ".join(args[1:]) if len(args) > 1 else "Summarize the key contents of this document."
        _report(f"pdf {T.G_DOT} {args[0]}", analyze_pdf(args[0], q))
        return True

    elif cmd in ["data", "analyze-data"]:
        if not args:
            console.print(T.warn("usage: data <file.csv> [query]"))
            return True
        q = " ".join(args[1:]) if len(args) > 1 else "Analyze this dataset"
        _report(f"dataset {T.G_DOT} {args[0]}", analyze_data(args[0], q))
        return True

    elif cmd in ["symbols", "find-symbols"]:
        target = args[0] if args else "."
        _report(f"symbols {T.G_DOT} {target}", find_symbols(target))
        return True

    elif cmd == "git":
        sub = args[0] if args else "status"
        extra = " ".join(args[1:]) if len(args) > 1 else ""
        _report(f"git {sub}", git_ops(sub, extra))
        return True

    # Fallback: hand the raw input to TARS as a conversational/agentic request.
    reply, cue_triggered = process_chat(raw)
    state.cue_light_active = cue_triggered
    if cue_triggered:
        audio.cue_light()
    _say(reply, cue_triggered)
    return True


def _report(title: str, body: str):
    """Renders tool output under a titled rule instead of inside a heavy panel."""
    console.print()
    console.print(T.rule(title))
    console.print(f"[{T.TEXT}]{body}[/{T.TEXT}]")
    console.print()


def _say(text: str, cue: bool = False, unit: str = "TARS", speak: bool = True):
    """
    Renders a unit's reply. Attribution is a coloured unit name on its own line;
    the cue light is a small trailing marker rather than a shouted badge.
    """
    color = T.AGENT_COLORS.get(unit.upper(), T.ACCENT)
    header = f"[bold {color}]{unit.upper()}[/bold {color}]"
    if cue:
        header += f"  [{T.OK}]{T.G_DOT} cue[/{T.OK}]"
    console.print()
    console.print(header)
    console.print(f"[{T.TEXT}]{text}[/{T.TEXT}]")
    console.print()
    if speak:
        voice.speak(text, non_blocking=True)

def run_voice_loop():
    """Hands-free continuous two-way voice conversation loop."""
    console.print(T.section("hands-free voice", "speak normally; say 'exit' or press Ctrl+C to return"))
    voice.speak(f"Voice channel open, {config.operator_callsign}. I'm listening.", non_blocking=False)

    while True:
        try:
            # Wait for any prior speech synthesis to finish before opening microphone
            while voice.is_speaking:
                time.sleep(0.1)
            time.sleep(0.4)

            user_speech = voice.listen(timeout_seconds=7)
            if not user_speech:
                continue
            lower = user_speech.lower().strip()
            if any(w in lower for w in ["exit", "stop", "quit", "disconnect", "cancel", "close channel"]):
                console.print(T.info("voice channel closed"))
                voice.speak("Voice channel closed.", non_blocking=False)
                break

            # Execute command or conversational dialogue
            cont = execute_command(user_speech)
            if not cont:
                break

            # Ensure TARS finishes speaking before next turn starts
            while voice.is_speaking:
                time.sleep(0.1)
            time.sleep(0.4)
        except (KeyboardInterrupt, EOFError):
            console.print(T.info("voice channel closed"))
            voice.speak("Voice channel closed.", non_blocking=False)
            break


def run_tars_shell():
    """Main CLI entrypoint running interactive REPL."""
    os.system("cls" if os.name == "nt" else "clear")
    console.print(get_masthead())
    audio.dock_lock()

    session = None
    if sys.stdin.isatty():
        try:
            session = PromptSession(completer=WordCompleter(COMMANDS_LIST, ignore_case=True))
        except Exception:
            session = None

    while True:
        try:
            prompt_fragments = [
                ('class:callsign', f'{config.operator_callsign.lower()} '),
                ('class:symbol', f'{T.G_PROMPT} '),
            ]
            if session is not None:
                user_input = session.prompt(prompt_fragments, style=prompt_style)
            else:
                user_input = input(f"{config.operator_callsign.lower()} {T.G_PROMPT} ")
            continue_loop = execute_command(user_input)
            if not continue_loop:
                break
        except (KeyboardInterrupt, EOFError):
            console.print()
            console.print(T.info(f"powering down. see you on the other side, {config.operator_callsign}."))
            break
        except Exception as e:
            console.print(T.error(f"{type(e).__name__}: {e}"))
