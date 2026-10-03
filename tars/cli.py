import sys
import time
import os
import shlex
from pathlib import Path

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        os.system("chcp 65001 >nul 2>&1")
    except Exception:
        pass

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
from tars.ui.voice import voice, wake_listener, strip_wake_word, is_interrupt
from tars.core.memory import memory
from tars.core.agent import tars_agent
from tars.core.host import (
    VERBS,
    DEFAULT_APPS,
    available_apps,
    host_control,
    resolve_app,
    verb_table,
)
from tars.core.security import (
    allowed_roots,
    describe_boundary,
    read_audit_tail,
)
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
    sentinel,
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

from tars.ui import chrome
from tars.ui.console import console

COMMANDS_LIST = [
    "help", "status", "monolith", "chassis", "dock", "relativity",
    "morse", "research", "listen", "voice", "voice-chat", "self-destruct",
    "diagnostics", "logs", "settings", "humor", "honesty", "sarcasm",
    "empathy", "mood", "people", "/people", "ui", "theme",
    "sound", "callsign", "api-key", "clear", "exit", "quit",
    "goal", "/goal", "memory", "/memory", "tools", "/tools",
    "sys", "telemetry", "avionics",
    "case", "/case", "kipp", "/kipp", "hive", "/hive",
    "heal", "look", "screen", "pdf", "data", "symbols", "git",
    "units", "new",
    # host control, security boundary, and presence
    "host", "apps", "roots", "security", "boundary", "audit",
    "wake", "ambient", "proactive", "sentinel",
]

# Shorthands so spoken and typed input reach host_control without the operator
# having to name the verb. "mute" -> host volume mute, and so on.
HOST_SHORTCUTS = {
    "mute": ("volume", {"action": "mute"}),
    "unmute": ("volume", {"action": "mute"}),
    "louder": ("volume", {"action": "up"}),
    "quieter": ("volume", {"action": "down"}),
    "play": ("media", {"action": "play_pause"}),
    "pause": ("media", {"action": "play_pause"}),
    "next-track": ("media", {"action": "next"}),
    "prev-track": ("media", {"action": "previous"}),
    "lock": ("lock", {}),
    "battery": ("battery", {}),
    "wifi": ("network", {}),
    "clipboard": ("clipboard_get", {}),
    "windows": ("list_windows", {}),
}

prompt_style = Style.from_dict({
    'unit': f'{T.ACCENT} bold',
    'bracket': f'{T.FAINT}',
    'callsign': f'{T.TEXT_BRIGHT} bold',
    'symbol': f'{T.ACCENT} bold',
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
    ("host", [
        ("host", "list every laptop action TARS is allowed to take"),
        ("host <verb> [args]", "run one directly, e.g. host open_app spotify"),
        ("apps", "applications TARS may launch"),
        ("apps add <name> <path>", "allow one more application"),
        ("mute / louder / play", "shorthands for the common media actions"),
    ]),
    ("security", [
        ("security", "the active boundary: roots, secret classes, gate state"),
        ("roots", "directories the filesystem tools may touch"),
        ("roots add <dir>", "widen the filesystem boundary"),
        ("audit [n]", "recent host actions and gate decisions"),
        ("confirm on | off", "pause for approval before sensitive commands"),
    ]),
    ("voice", [
        ("wake", "ambient wake-word listening, hands free"),
        ("listen", "capture one spoken command"),
        ("voice-chat", "continuous hands-free conversation"),
        ("voice on | off", "toggle speech synthesis"),
        ("voice stop", "cut off speech in progress"),
        ("voice set <name>", "change the neural voice"),
        ("voice list", "available neural voices"),
        ("proactive on | off", "let TARS speak up unprompted"),
        ("sound on | off", "toggle audio feedback"),
    ]),
    ("personality", [
        ("humor <0-100>", "TARS humor level"),
        ("honesty <0-100>", "TARS candour level"),
        ("sarcasm <0-100>", "TARS sarcasm level"),
        ("empathy <0-100>", "how much TARS brings to a loaded moment"),
        ("mood", "what TARS currently reads in the room"),
        ("chassis <mode>", "monolith | walk | roll | dock | quantum"),
    ]),
    ("interface", [
        ("ui", "interface settings"),
        ("ui animation on|off", "boot stagger and the live thinking indicator"),
        ("ui bar on|off", "the status line above the prompt"),
        ("ui logo on|off", "full identity block or one compact line"),
        ("theme", "preview the palette, meters, and reply styling"),
    ]),
    ("memory", [
        ("memory", "everything retained about you"),
        ("memory remember <fact>", "store something durable"),
        ("people", "who TARS knows in your life"),
        ("people status <name> <state>", "living | deceased | estranged | unwell"),
        ("people forget <name>", "remove someone from the registry"),
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
        ("empathy", f"{config.empathy}%" if config.empathy else "off"),
        ("affective voice", "on" if config.affect_voice else "off"),
        ("callsign", config.operator_callsign),
        ("speech output", "on" if config.voice_output_enabled else "off"),
        ("voice", voice.engine_name()),
        ("wake word", f"'{config.wake_word}'"),
        ("spoken ack", "on" if config.spoken_ack else "off"),
        ("microphone", "ready" if config.voice_input_enabled else "off"),
        ("audio feedback", "on" if config.sound_enabled else "off"),
        ("typewriter", "on" if config.typewriter_effect else "off"),
        ("host control", "on" if config.host_control_enabled else "off"),
        ("apps allowed", str(len(available_apps()))),
        ("fs roots", str(len(allowed_roots()))),
        ("confirm gate", "on" if config.confirm_sensitive else "off"),
        ("proactive", "watching" if sentinel.is_running else ("armed" if config.proactive_enabled else "off")),
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
        voice.stop()
        wake_listener.stop()
        sentinel.stop()
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

    elif cmd in ("ui", "theme"):
        sub = args[0].lower() if args else ""
        if cmd == "theme" or sub in ("preview", "show", "palette"):
            chrome.show_theme()
            return True

        toggles = {
            "animation": "ui_animation",
            "anim": "ui_animation",
            "statusbar": "ui_status_bar",
            "bar": "ui_status_bar",
            "status": "ui_status_bar",
            "logo": "ui_logo",
            "typewriter": "typewriter_effect",
        }
        if sub in toggles and len(args) > 1:
            field = toggles[sub]
            want = args[1].lower()
            if want not in ("on", "off"):
                console.print(T.error(f"usage: ui {sub} on | off"))
                return True
            setattr(config, field, want == "on")
            config.save()
            console.print(T.ok(f"{sub} {want}"))
            return True

        rows = [
            ("animation", "on" if config.ui_animation else "off"),
            ("status bar", "on" if config.ui_status_bar else "off"),
            ("logo", "full" if config.ui_logo else "compact"),
            ("typewriter", "on" if config.typewriter_effect else "off"),
            ("width", str(chrome.width())),
            ("colour", console.color_system or "none"),
        ]
        console.print()
        console.print(T.rule("interface"))
        console.print(T.kv_table(rows, columns=2, label_width=14))
        console.print()
        console.print(T.hint("ui animation|bar|logo|typewriter on|off   ·   theme  for the palette"))
        console.print()
        return True

    elif cmd in ("empathy", "mood"):
        if cmd == "mood" or not args:
            from tars.core.emotion import PROFILES, Affect, emotion

            reading = emotion.last
            current = reading.effective_affect
            rows = [
                ("empathy dial", f"{config.empathy}%"),
                ("affective voice", "on" if config.affect_voice else "off"),
                ("current read", PROFILES[current].label if current is not Affect.NEUTRAL else "nothing notable"),
                ("confidence", f"{reading.intensity:.0%}" if reading.is_charged else "-"),
                ("carried mood", emotion.mood.value),
                ("signals", ", ".join(reading.evidence[:3]) or "-"),
                ("about", state.mood_subject or "-"),
            ]
            console.print()
            console.print(T.rule("affective state"))
            console.print(T.kv_table(rows, columns=2, label_width=16))
            console.print()
            if cmd == "empathy":
                console.print(T.hint("empathy <0-100> to retune"))
                console.print()
            return True
        try:
            val = int(args[0].replace("%", ""))
            ack, trigger_cue = personality.set_empathy(val)
            state.cue_light_active = trigger_cue
            if trigger_cue:
                audio.cue_light()
            _say(ack, trigger_cue, speak=False)
        except ValueError:
            console.print(T.error("usage: empathy <0-100>"))
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
        elif arg in ["stop", "hush", "quiet"]:
            console.print(T.ok("speech cut") if voice.stop() else T.info("nothing was playing"))
        elif arg in ["set", "voice", "use"]:
            if len(args) < 2:
                console.print(T.warn("usage: voice set <voice-name>   e.g. voice set en-GB-RyanNeural"))
                return True
            config.tts_voice = args[1].strip()
            config.tts_engine = "auto"
            config.save()
            console.print(T.ok(f"voice set to {config.tts_voice}"))
            voice.speak("This is how I sound now.", non_blocking=True)
        elif arg in ["list", "voices"]:
            show_voices()
        elif arg in ["engine"]:
            if len(args) > 1 and args[1].lower() in ("sapi", "auto", "edge"):
                config.tts_engine = "sapi" if args[1].lower() == "sapi" else "auto"
                config.save()
                console.print(T.ok(f"tts engine: {config.tts_engine}"))
            else:
                console.print(T.info(f"tts engine is '{config.tts_engine}' ({voice.engine_name()})"))
        elif arg in ["test", "check"]:
            console.print(T.info(f"engine: {voice.engine_name()}"))
            if not config.voice_output_enabled:
                console.print(T.warn("speech output is off, so this test plays once and then stays silent"))
                console.print(T.hint("run 'voice on' to hear TARS reply normally"))
            console.print(T.info("synthesising, first run needs a second or two"))
            voice.speak(
                f"Voice check. Humor at {config.humor} percent, {config.operator_callsign}.",
                non_blocking=False,
                force=True,
            )
            console.print(T.ok(f"playback finished via {voice.engine_name()}"))
        else:
            console.print("Usage: voice on | off | listen | chat | stop | set <name> | list | engine | test")
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
            record = memory.remember_fact(" ".join(args[1:]))
            console.print(T.ok(
                f"fact archived  [{record.get('category')}, salience {record.get('salience')}/10]"
                if record else "nothing to archive"
            ))
        else:
            console.print()
            console.print(T.rule("memory"))
            console.print(memory.get_memory_summary())
            console.print()
        return True

    elif cmd in ["people", "/people"]:
        sub = args[0].lower() if args else ""
        if sub == "add" and len(args) >= 3:
            # people add <relation> <name> [status]
            relation, name = args[1], args[2]
            status = args[3].lower() if len(args) > 3 else "living"
            record = memory.remember_person(name=name, relation=relation, status=status)
            console.print(T.ok(
                f"{record.get('name')} registered as {record.get('relation')} ({record.get('status')})"
            ))
        elif sub in ("status", "set") and len(args) >= 3:
            # people status <name> <living|deceased|estranged|unwell>
            name, status = args[1], args[2].lower()
            existing = memory.resolve_people(name)
            if not existing:
                console.print(T.error(f"nobody on file matching '{name}'"))
                return True
            record = memory.remember_person(
                name=existing[0].get("name", ""),
                relation=existing[0].get("relation", ""),
                status=status,
            )
            console.print(T.ok(f"{record.get('name')}: status now {record.get('status')}"))
        elif sub in ("forget", "remove") and len(args) >= 2:
            target = " ".join(args[1:])
            console.print(T.ok(f"removed {target}") if memory.forget_person(target)
                          else T.error(f"nobody on file matching '{target}'"))
        elif not memory.people:
            console.print()
            console.print(T.info("nobody registered yet"))
            console.print(T.hint("TARS records people as you mention them, or: people add <relation> <name> [status]"))
            console.print()
        else:
            console.print()
            console.print(T.rule(f"people  {T.G_DOT}  {len(memory.people)} on file"))
            p_table = Table(box=T.BARE, show_header=True, expand=True, pad_edge=False, padding=(0, 1))
            p_table.add_column("", style=f"bold {T.TEXT_BRIGHT}", width=20, no_wrap=True)
            p_table.add_column("relation", width=16, no_wrap=True)
            p_table.add_column("status", width=12, no_wrap=True)
            p_table.add_column("", style=T.MUTED, overflow="fold")
            for record in memory.people.values():
                status = (record.get("status") or "living").lower()
                tone = {"deceased": "magenta", "estranged": T.WARN,
                        "unwell": T.WARN}.get(status, T.OK)
                p_table.add_row(
                    str(record.get("name", "")),
                    str(record.get("relation", "")),
                    f"[{tone}]{status}[/{tone}]",
                    str(record.get("note", "") or ""),
                )
            console.print(p_table)
            console.print()
            console.print(T.hint("people status <name> <living|deceased|estranged|unwell>"))
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

    elif cmd in HOST_SHORTCUTS:
        verb, kwargs = HOST_SHORTCUTS[cmd]
        # `louder 10` / `quieter 6` pass a magnitude through.
        if args and verb == "volume" and kwargs.get("action") in ("up", "down"):
            try:
                kwargs = {**kwargs, "level": int(args[0])}
            except ValueError:
                pass
        console.print(T.info(host_control(verb=verb, **kwargs)))
        return True

    elif cmd in ["host", "hostctl"]:
        if not args:
            show_host_verbs()
            return True
        sub = args[0].lower()
        if sub in ("on", "enable"):
            config.host_control_enabled = True
            config.save()
            console.print(T.ok("host control enabled"))
            return True
        if sub in ("off", "disable"):
            config.host_control_enabled = False
            config.save()
            console.print(T.info("host control disabled; TARS can no longer operate the machine"))
            return True
        verb, kwargs, err = _parse_host_invocation(args)
        if err:
            console.print(T.warn(err))
            return True
        _report(f"host {T.G_DOT} {verb}", host_control(verb=verb, **kwargs))
        return True

    elif cmd in ["apps", "applications"]:
        if args and args[0].lower() == "add":
            if len(args) < 3:
                console.print(T.warn("usage: apps add <name> <path-or-exe>"))
                return True
            name = args[1].strip().lower()
            target = " ".join(args[2:]).strip().strip('"')
            config.app_allowlist = {**(config.app_allowlist or {}), name: target}
            config.save()
            resolved, _is_uri = resolve_app(name)
            if resolved:
                console.print(T.ok(f"'{name}' allowlisted, resolves to {resolved}"))
            else:
                console.print(T.warn(f"'{name}' added, but nothing resolves at '{target}' yet"))
            return True
        if args and args[0].lower() in ("remove", "rm", "del"):
            if len(args) < 2:
                console.print(T.warn("usage: apps remove <name>"))
                return True
            name = args[1].strip().lower()
            current = dict(config.app_allowlist or {})
            if current.pop(name, None) is None:
                console.print(T.info(f"'{name}' was not an operator-added entry"))
                return True
            config.app_allowlist = current
            config.save()
            console.print(T.ok(f"removed '{name}' from the operator allowlist"))
            return True
        show_apps()
        return True

    elif cmd in ["roots", "boundary-roots"]:
        if args and args[0].lower() == "add":
            if len(args) < 2:
                console.print(T.warn("usage: roots add <directory>"))
                return True
            target = " ".join(args[1:]).strip().strip('"')
            resolved = Path(os.path.expandvars(os.path.expanduser(target)))
            if not resolved.is_dir():
                console.print(T.error(f"'{target}' is not an existing directory"))
                return True
            entries = list(config.allowed_fs_roots or [])
            if str(resolved) in entries:
                console.print(T.info("already an allowed root"))
                return True
            entries.append(str(resolved))
            config.allowed_fs_roots = entries
            config.save()
            console.print(T.ok(f"filesystem boundary widened to include {resolved}"))
            console.print(T.hint("secret files stay refused inside allowed roots"))
            return True
        if args and args[0].lower() in ("remove", "rm", "del"):
            if len(args) < 2:
                console.print(T.warn("usage: roots remove <directory>"))
                return True
            target = " ".join(args[1:]).strip().strip('"')
            entries = [e for e in (config.allowed_fs_roots or []) if e.lower() != target.lower()]
            if len(entries) == len(config.allowed_fs_roots or []):
                console.print(T.info("that path was not in the extra roots list"))
                return True
            config.allowed_fs_roots = entries
            config.save()
            console.print(T.ok("root removed"))
            return True
        console.print()
        console.print(T.rule("filesystem roots"))
        for root in allowed_roots():
            console.print(f"  [{T.TEXT_BRIGHT}]{root}[/{T.TEXT_BRIGHT}]")
        console.print()
        console.print(T.hint("roots add <dir> to widen, roots remove <dir> to narrow"))
        console.print()
        return True

    elif cmd in ["security", "boundary", "sec"]:
        console.print()
        console.print(T.rule("security boundary"))
        console.print(T.kv_table(describe_boundary(), columns=2, label_width=20))
        console.print()
        console.print(T.hint("filesystem tools are contained; run_command remains the wide path"))
        console.print()
        return True

    elif cmd in ["confirm", "gate"]:
        if not args:
            state_str = "on" if config.confirm_sensitive else "off"
            console.print(T.info(f"confirmation gate is {state_str}"))
            return True
        if args[0].lower() in ("on", "enable", "1"):
            config.confirm_sensitive = True
            config.save()
            console.print(T.ok("sensitive commands will pause for approval"))
        elif args[0].lower() in ("off", "disable", "0"):
            config.confirm_sensitive = False
            config.save()
            console.print(T.warn("gate off: sensitive commands will run unattended"))
        else:
            console.print(T.warn("usage: confirm on | off"))
        return True

    elif cmd in ["audit", "trail"]:
        limit = 20
        if args:
            try:
                limit = max(1, min(int(args[0]), 200))
            except ValueError:
                pass
        show_audit(limit)
        return True

    elif cmd in ["wake", "ambient", "hey"]:
        run_ambient_loop()
        return True

    elif cmd in ["proactive", "sentinel", "watch"]:
        if not args:
            console.print()
            console.print(T.rule("proactive sentinel"))
            console.print(T.kv_table(sentinel.status_rows(), columns=2, label_width=18))
            console.print()
            console.print(T.hint("proactive on   to let TARS raise things unprompted"))
            console.print()
            return True
        sub = args[0].lower()
        if sub in ("on", "enable", "1", "start"):
            config.proactive_enabled = True
            config.save()
            started = sentinel.start()
            console.print(T.ok("sentinel watching" if started else "sentinel already running"))
            console.print(T.hint("battery, disk, memory, and sustained CPU; spoken and toasted"))
        elif sub in ("off", "disable", "0", "stop"):
            config.proactive_enabled = False
            config.save()
            sentinel.stop()
            console.print(T.info("sentinel stood down"))
        elif sub in ("interval", "every"):
            if len(args) < 2:
                console.print(T.warn("usage: proactive interval <seconds>"))
                return True
            try:
                config.proactive_interval = max(15, min(int(args[1]), 3600))
                config.save()
                console.print(T.ok(f"poll interval {config.proactive_interval}s"))
            except ValueError:
                console.print(T.warn("usage: proactive interval <seconds>"))
        else:
            console.print(T.warn("usage: proactive on | off | interval <seconds>"))
        return True

    # Fallback: hand the raw input to TARS as a conversational/agentic request.
    # The model call blocks for seconds at a time, so the turn runs under a live
    # indicator rather than leaving the shell looking hung.
    with chrome.begin_thinking(unit="TARS"):
        try:
            reply, cue_triggered = process_chat(raw)
        finally:
            chrome.end_thinking()

    state.cue_light_active = cue_triggered
    if cue_triggered:
        audio.cue_light()
    _say(reply, cue_triggered, mood=_current_mood())
    return True


def _report(title: str, body: str):
    """Renders tool output under a titled rule instead of inside a heavy panel."""
    console.print()
    console.print(T.rule(title))
    console.print(f"[{T.TEXT}]{body}[/{T.TEXT}]")
    console.print()


def _say(text: str, cue: bool = False, unit: str = "TARS", speak: bool = True,
         mood: str = ""):
    """
    Renders a unit's reply and optionally speaks it.

    Delegates the drawing to `chrome.reply`, which renders markdown and does not
    interpret Rich markup. The previous implementation interpolated the reply
    straight into a markup string, so a reply containing `list[int]` or a
    footnote `[1]` was parsed as a style tag and either raised or silently lost
    characters.

    `mood` is passed explicitly rather than read from the affective core here. A
    dial acknowledgement should not inherit the badge from whatever the operator
    happened to be feeling two turns ago.
    """
    chrome.reply(text, unit=unit, cue=cue, mood=mood)
    if speak:
        voice.speak(text, non_blocking=True)


def _current_mood() -> str:
    """The affective read to badge a conversational reply with, or ''."""
    try:
        from tars.core.emotion import emotion

        affect = emotion.last.effective_affect
        return affect.value if affect.value != "neutral" else ""
    except Exception:
        return ""


# ─── Host control helpers ───────────────────────────────────────────────────

_INT_PARAMS = {"level", "timer_id"}
_FLOAT_PARAMS = {"minutes"}


def _parse_host_invocation(tokens):
    """
    Parses `host <verb> [key=value ...] [bare words]` into (verb, kwargs, error).

    Bare words collapse onto the verb's first declared parameter, so
    `host open_app visual studio code` and `host open_app target="vscode"` both
    work. Anything the verb does not declare is reported rather than silently
    dropped, because a typo'd parameter should not look like a successful call.
    """
    verb = tokens[0].strip().lower().replace("-", "_")
    spec = VERBS.get(verb)
    if spec is None:
        return "", {}, f"'{tokens[0]}' is not a host verb. Run 'host' for the list."

    kwargs = {}
    bare = []
    for token in tokens[1:]:
        if "=" in token and not token.startswith("="):
            key, _, value = token.partition("=")
            key = key.strip().lower()
            if key not in spec.params:
                return "", {}, f"verb '{verb}' takes: {', '.join(spec.params) or '(no parameters)'}"
            kwargs[key] = value.strip().strip('"').strip("'")
        else:
            bare.append(token)

    if bare:
        if not spec.params:
            return "", {}, f"verb '{verb}' takes no parameters"
        # Prefer the first declared parameter that is not already set.
        slot = next((p for p in spec.params if p not in kwargs), spec.params[0])
        kwargs[slot] = " ".join(bare).strip().strip('"')

    for key in list(kwargs):
        try:
            if key in _INT_PARAMS:
                kwargs[key] = int(kwargs[key])
            elif key in _FLOAT_PARAMS:
                kwargs[key] = float(kwargs[key])
        except (TypeError, ValueError):
            return "", {}, f"'{key}' must be a number, got '{kwargs[key]}'"

    return verb, kwargs, ""


def show_host_verbs():
    """Renders the host_control verb catalogue."""
    rows = verb_table()
    state = "enabled" if config.host_control_enabled else "disabled"
    console.print()
    console.print(T.rule(f"host control  {T.G_DOT}  {len(rows)} verbs  {T.G_DOT}  {state}"))
    table = Table(box=T.BARE, show_header=False, expand=True, pad_edge=False, padding=(0, 1))
    table.add_column(width=18, no_wrap=True)
    table.add_column(width=22, no_wrap=True)
    table.add_column(ratio=1, overflow="fold")
    for verb, params, summary in rows:
        table.add_row(
            Text(f"  {verb}", style=T.TEXT_BRIGHT),
            Text(params, style=T.FAINT),
            Text(summary, style=T.MUTED),
        )
    console.print(table)
    console.print()
    console.print(T.hint("host open_app spotify   ·   host volume set level=35   ·   host timer 10 label=tea"))
    console.print(T.hint("registry, services, firewall, uninstalls, and deletes are deliberately absent"))
    console.print()
    audio.key_tick()


def show_apps():
    """Lists allowlisted apps that actually resolve on this machine."""
    apps = available_apps()
    custom = set((config.app_allowlist or {}).keys())
    console.print()
    console.print(T.rule(f"application allowlist  {T.G_DOT}  {len(apps)} available"))
    if not apps:
        console.print(T.warn("nothing resolved; add one with: apps add <name> <path>"))
    else:
        table = Table(box=T.BARE, show_header=False, expand=True, pad_edge=False, padding=(0, 1))
        table.add_column(width=20, no_wrap=True)
        table.add_column(ratio=1, overflow="fold")
        for name, target in apps:
            tag = "  ·" if name in custom else "   "
            table.add_row(
                Text(f"{tag} {name}", style=T.TEXT_BRIGHT),
                Text(target, style=T.MUTED),
            )
        console.print(table)
    missing = sorted(set(DEFAULT_APPS) - {n for n, _ in apps})
    if missing:
        console.print()
        console.print(T.hint(f"known but not installed here: {', '.join(missing[:14])}"))
    console.print()
    console.print(T.hint("· marks an operator-added entry   ·   apps add <name> <path>"))
    console.print()


def show_audit(limit: int):
    """Shows the tail of the audit trail."""
    records = read_audit_tail(limit)
    console.print()
    console.print(T.rule(f"audit trail  {T.G_DOT}  last {len(records)}"))
    if not records:
        console.print(T.info("nothing recorded yet"))
        console.print()
        return
    table = Table(box=T.BARE, show_header=False, expand=True, pad_edge=False, padding=(0, 1))
    table.add_column(width=18, no_wrap=True)
    table.add_column(width=12, no_wrap=True)
    table.add_column(width=20, no_wrap=True)
    table.add_column(ratio=1, overflow="fold")
    for rec in records:
        result = str(rec.get("result", ""))
        colour = {
            "ok": T.MUTED,
            "approved": T.OK,
            "announced": T.ACCENT,
        }.get(result, T.WARN if result else T.MUTED)
        detail = rec.get("detail") or {}
        summary = "  ".join(f"{k}={v}" for k, v in detail.items() if v)[:160]
        table.add_row(
            Text("  " + str(rec.get("ts", ""))[5:19], style=T.FAINT),
            Text(str(rec.get("category", "")), style=T.MUTED),
            Text(str(rec.get("action", "")), style=T.TEXT_BRIGHT),
            Text(f"{result}  {summary}", style=colour),
        )
    console.print(table)
    console.print()


SUGGESTED_VOICES = [
    ("en-US-GuyNeural", "male, US, level and dry - the default"),
    ("en-US-ChristopherNeural", "male, US, deeper and slower"),
    ("en-US-EricNeural", "male, US, clipped and matter-of-fact"),
    ("en-US-AndrewNeural", "male, US, warmer and conversational"),
    ("en-GB-RyanNeural", "male, UK, measured"),
    ("en-GB-ThomasNeural", "male, UK, formal"),
    ("en-AU-WilliamNeural", "male, AU"),
    ("en-US-AriaNeural", "female, US"),
    ("en-US-JennyNeural", "female, US, softer"),
    ("en-GB-SoniaNeural", "female, UK"),
]


def show_voices():
    """Lists a curated set of neural voices, and the full catalogue command."""
    console.print()
    console.print(T.rule("neural voices"))
    table = Table(box=T.BARE, show_header=False, expand=True, pad_edge=False, padding=(0, 1))
    table.add_column(width=28, no_wrap=True)
    table.add_column(ratio=1, overflow="fold")
    for name, desc in SUGGESTED_VOICES:
        marker = f"{T.G_OK} " if name == config.tts_voice else "  "
        table.add_row(
            Text(f"  {marker}{name}", style=T.TEXT_BRIGHT if name == config.tts_voice else T.TEXT),
            Text(desc, style=T.MUTED),
        )
    console.print(table)
    console.print()
    console.print(T.info(f"active engine: {voice.engine_name()}"))
    console.print(T.hint("voice set <name> to switch   ·   edge-tts --list-voices for all 400+"))
    console.print()


# ─── Ambient wake-word listening ────────────────────────────────────────────

# How long after the wake word TARS keeps waiting for the actual command.
WAKE_ARM_SECONDS = 12.0
# Phrases arriving within this window of TARS speaking are treated as the
# microphone hearing TARS itself, not the operator.
ECHO_GRACE_SECONDS = 1.0

AMBIENT_EXITS = (
    "exit", "quit", "stand down", "stop listening", "close channel",
    "that's all", "thats all", "go to sleep", "dismissed",
)


def _looks_like_echo(phrase: str) -> bool:
    """True when a recognised phrase is most likely TARS's own voice fed back."""
    spoken = (voice.last_spoken or "").lower()
    if not spoken:
        return False
    text = phrase.lower().strip(" .,!?")
    if len(text) < 4:
        return False
    return text in spoken


def run_ambient_loop():
    """
    Hands-free ambient listening gated on a wake word.

    One recogniser process stays warm for the whole session, which is what makes
    this feel like presence rather than a series of 6-second capture windows. The
    operator can also talk over TARS: an interrupt phrase, or the wake word
    itself, kills speech in progress.
    """
    console.print()
    console.print(T.section(
        "ambient listening",
        f"say '{config.wake_word}' then your request  ·  'stand down' or ctrl+c to stop",
    ))

    if not config.voice_output_enabled:
        console.print(T.warn("speech output is off, so TARS will listen but reply only in text"))
        console.print(T.hint("run 'voice on' first for a real two-way conversation"))

    if not wake_listener.start():
        reason = wake_listener.fatal_error or "the recogniser did not report ready in time"
        console.print(T.error(f"could not start ambient listening: {reason}"))
        console.print(T.hint("check that a microphone is connected and Windows speech is available"))
        return

    config.wake_word_enabled = True
    config.save()
    console.print(T.ok("recogniser online and staying warm"))
    console.print(T.hint(f"wake word: '{config.wake_word}'   ·   interrupt with 'stop' while TARS is talking"))
    console.print()
    voice.speak(f"Standing by. Say {config.wake_word} when you need me.", non_blocking=True)

    armed_until = 0.0
    last_speech_seen = time.time()

    try:
        while True:
            if voice.is_speaking:
                last_speech_seen = time.time()

            phrase = wake_listener.poll(timeout=0.4)
            if phrase is None:
                if not wake_listener.is_running:
                    console.print(T.error("the recogniser exited; ambient listening stopped"))
                    break
                continue

            now = time.time()
            remainder = strip_wake_word(phrase, config.wake_word)
            recently_spoke = (now - last_speech_seen) < ECHO_GRACE_SECONDS

            # Barge-in. An interrupt phrase or the wake word cuts speech short.
            if voice.is_speaking or recently_spoke:
                if is_interrupt(phrase) or remainder is not None:
                    if voice.stop():
                        console.print(T.info("interrupted"))
                    wake_listener.drain()
                    if remainder is None or not remainder:
                        armed_until = now + WAKE_ARM_SECONDS if remainder == "" else 0.0
                        continue
                elif _looks_like_echo(phrase):
                    continue
                else:
                    continue

            command = None
            if remainder is not None:
                if remainder:
                    command = remainder
                else:
                    armed_until = now + WAKE_ARM_SECONDS
                    console.print(T.info("listening"))
                    audio.key_tick()
                    continue
            elif now < armed_until:
                command = phrase
                armed_until = 0.0
            else:
                # No wake word and not armed: ambient conversation, ignored.
                continue

            if command.strip().lower().strip(" .,!?") in AMBIENT_EXITS:
                console.print(T.info("standing down"))
                voice.speak("Standing down.", non_blocking=False)
                break

            chrome.echo_operator(command, source="voice")
            audio.key_tick()

            if not execute_command(command):
                break

            last_speech_seen = time.time()
            wake_listener.drain()

    except (KeyboardInterrupt, EOFError):
        console.print()
        console.print(T.info("ambient listening stopped"))
    finally:
        wake_listener.stop()
        config.wake_word_enabled = False
        config.save()


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
    chrome.boot()
    audio.dock_lock()

    # Resume the sentinel if the operator left it on. Proactivity that has to be
    # re-enabled on every launch is not proactivity.
    if config.proactive_enabled:
        if sentinel.start():
            console.print(T.info("proactive sentinel watching host state"))

    # Say so when TARS is muted. Otherwise a config left at voice_output_enabled
    # false looks indistinguishable from speech being broken.
    if not config.voice_output_enabled:
        console.print(T.info("speech output is off  ·  'voice on' to enable, 'voice test' to sample it"))
    if not config.sound_enabled:
        console.print(T.info("audio feedback is off  ·  'sound on' to enable"))

    session = None
    if sys.stdin.isatty():
        try:
            session = PromptSession(completer=WordCompleter(COMMANDS_LIST, ignore_case=True))
        except Exception:
            session = None

    while True:
        try:
            # Ambient state above the prompt, so the shell always shows which
            # model is answering, where the dials sit, and what it is reading.
            chrome.prompt_line()
            prompt_fragments = [
                ('class:bracket', '  ['),
                ('class:callsign', config.operator_callsign.lower()),
                ('class:bracket', '] '),
                ('class:symbol', f'{T.G_CARET} '),
            ]
            if session is not None:
                user_input = session.prompt(prompt_fragments, style=prompt_style)
            else:
                user_input = input(f"  [{config.operator_callsign.lower()}] {T.G_CARET} ")
            continue_loop = execute_command(user_input)
            if not continue_loop:
                break
        except (KeyboardInterrupt, EOFError):
            console.print()
            console.print(T.info(f"powering down. see you on the other side, {config.operator_callsign}."))
            break
        except Exception as e:
            console.print(T.error(f"{type(e).__name__}: {e}"))
