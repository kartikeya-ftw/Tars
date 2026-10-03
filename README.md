# TARS Console Suite (Interstellar)
> *"Cooper, this is no time for caution."*

A console AI assistant built around **TARS**, the decommissioned US Marine Corps tactical
robot from Christopher Nolan's *Interstellar*, plus its two specialist units CASE and KIPP.

Python, `rich`, and `prompt_toolkit`. Underneath the persona it is a real ReAct agent: 18
tools spanning the filesystem, shell, Python execution, live web search, vision, host
telemetry, and an allowlisted laptop-control layer, driven by Gemini function calling, with
persistent memory across restarts and three independently-scoped agents that can hand work
to each other.

The terminal UI follows a single restrained design system (`tars/ui/theme.py`): one cool
accent, muted labels against bright values, thin rules instead of frames, and real machine
readings rather than decorative gauges.

---

## 🚀 Quick Start

Launch TARS directly from PowerShell or Windows Terminal:

```powershell
pip install -r requirements.txt
python tars_cli.py
```

Everything degrades rather than breaking if an optional dependency is missing: without
`edge-tts` the voice falls back to Windows SAPI, without `pillow` screen capture is
unavailable, and without an API key TARS runs on offline heuristics.

Worth running once on a new install:

```
security      # what the filesystem boundary allows
host          # every laptop action TARS can take
apps          # which applications resolved on this machine
voice test    # confirm the neural voice plays
```

---

## 🤖 Features & Capabilities

### 1. Dynamic Personality Engine & Cue Light
- **`humor <0-100>`**: Adjusts TARS's sarcasm, deadpan humor, and self-destruct jokes (default: `75%`).
- **`honesty <0-100>`**: Adjusts candor vs diplomatic tact (default: `90%`).
  - *"Absolute honesty isn't always the most diplomatic nor the safest form of communication with emotional beings."*
- **`sarcasm <0-100>`**: Calibrates cynical editorial remarks.
- **`empathy <0-100>`**: How much TARS brings to an emotionally loaded moment (default: `85%`). See below.
- **Physical Cue Light**: Visual LED badge `[● CUE LIGHT ON]` flashes automatically whenever TARS tells a joke or uses sarcasm, accompanied by a double-chirp tone. It stays dark on anything painful — a joke indicator that fires over bad news is worse than none.

### 1b. Affective Core (`tars/core/emotion.py`)
TARS reads what a message *means*, not just what it says, and answers in a register that
fits. This is local pattern and lexicon work — no extra model round-trip, so it costs no
latency.

- **17 registers**: grief, sadness, loneliness, anxiety, frustration, shame, exhaustion,
  illness, conflict, romance, joy, pride, gratitude, affection, nostalgia, vulnerability,
  neutral. Each carries its own behavioural instruction, injected into the system prompt
  for that turn only.
- **Relational memory**: a registry of the people in your life, each with a relation and a
  status — `living`, `deceased`, `estranged`, `unwell`. Mentioning a partner reads warm;
  mentioning someone who has died does not. TARS infers these from ordinary conversation,
  so saying *"my grandma passed away"* once is enough — it is retained, and TARS will not
  later refer to her as though she were alive.
- **Salience-weighted facts**: every stored fact has a weight. Anything at 6 or above is
  never evicted from the prompt or pruned from disk, so a note about a build flag cannot
  push out who you love. Retrieval scores weight, relevance to the current message, and
  recency together rather than blindly taking the most recent entries.
- **Mood carry**: the read decays over roughly eight minutes instead of resetting each
  turn, so TARS does not snap from consoling to flippant because one message was neutral.
- **Guards**: humor and sarcasm are suspended on painful turns regardless of the dials, the
  cue light is withheld, the spoken *"On it."* filler is skipped, and TARS is told not to
  go looking for a task to perform when you are just talking.
- **Voice follows affect**: speech rate and pitch shift per utterance — slower and lower for
  bad news, lifted for good. Toggle with `affect_voice` in `.tars_config.json`.
- **Off switch**: `empathy 0` disables the layer entirely and returns the older, flatter
  behaviour. `mood` shows what TARS currently reads in the room.

Routine work is unaffected: `read the config and list the models` gets no emotional
treatment at all, because it isn't asking for any.

### 1c. Shell Chrome (`tars/ui/chrome.py`)
The terminal UI is an instrument panel, not a log file.

- **Identity block** at startup: the four articulating slabs beside a box-drawing
  wordmark, under one diagonal gradient. Gradients are reserved for identity — data
  never gets one, so colour keeps meaning everywhere else.
- **Power-on report** ticking each subsystem as it reports in: tool registry, unit
  roster, memory matrix, affective core, uplink, voice, security boundary. Every value
  is a real reading.
- **Replies render behind a per-unit gutter** — sky for TARS, orange for CASE, violet
  for KIPP — with markdown parsed properly, so tables, lists, code fences, and inline
  code finally look like what they are. Badges carry state (`cue`, the affective read)
  in a separate channel from the gutter, which carries identity.
- **Live thinking indicator** during the blocking model call: pulsing slabs, elapsed
  time, and the tool currently running. Previously this stretch was dead air.
- **Status line above the prompt**: uplink, dials, the current affective read,
  directory, uptime. Ambient awareness without typing `status`.
- **Segmented meters** for host telemetry, in the same slab glyph language as the
  chassis, coloured by threshold rather than by gradient.
- `ui` tunes it (`ui animation|bar|logo|typewriter on|off`), `theme` previews the whole
  design system, `status` gives the full three-column readout.

**A real bug this fixed.** Replies used to be printed as
`console.print(f"[{TEXT}]{reply}[/{TEXT}]")`, which parsed the reply itself as Rich
markup. A reply containing `list[int]` silently lost `[int]`, and a reply containing
`[/]` raised `MarkupError`. `scratch/test_markup_bug.py` reproduces both against the
old path and verifies the new one.

### 2. Articulating Monolith Chassis Visualizer
TARS consists of 4 articulating slabs (`[1][2][3][4]`) connected by high-torque magnetic hinges. You can command physical reconfigurations:
- `chassis monolith` — Rigid 4-slab standing monolith (computing/standby mode).
- `chassis walk` — Staggered tripod walking gait.
- `chassis roll` — High-velocity centrifugal pinwheel rescue mode (from Miller's planet).
- `chassis dock` — Thruster and vector RCS alignment mode.
- `chassis quantum` — 5D Tesseract hypercube matrix.

### 3. Mission Subsystems & Simulators
- **`dock [rpm]`**: Recreate the iconic 68 RPM spin-synchronization docking maneuver with the damaged Endurance. Features real-time retro thruster burns, vector alignment, and movie quotes.
- **`relativity [hours]`**: Gravitational time dilation calculator for Miller's planet near Gargantua (1 hour = 7 Earth years; 1 tick = 1.25 Earth days).
- **`relativity schwarzschild <mass> <radius>`**: General relativity gravitational time dilation calculator based on Schwarzschild metric.
- **`morse <message>`**: Quantum data encoder simulating Cooper pulsing the second hand of Murph's Hamilton watch inside the 5D Tesseract. Includes visual second-hand movement and real audio beeps.
- **`self-destruct`**: The legendary simulated countdown with humor-dependent punchlines (*"10... 9... 8... knock knock"*).
- **`diagnostics`**: Full scan of reactor power, magnetic torque, sensor arrays, and life support.
- **`logs`**: Declassified US Marine Corps service archives and Lazarus mission briefing.

### 4. Deep Scientific Research Subsystem
- **`research <topic>`**: Conducts an in-depth scientific or tactical investigation on any topic (e.g. `research Doppler effect`, `research Gargantua accretion disk`, `research wormhole physics`).
- Integrates live neural reasoning with structured NASA telemetry formatting (Executive Summary, Theoretical Analysis, Mission Implications & Hazards, and TARS's Deadpan Tactical Assessment).
- Spoken voice feedback confirms report compilation.

### 5. Two-Way Spoken Voice System (Microphone Input & Speech Synthesis)
- **Voice Output (neural, interruptible)**:
  - Neural voices via [`edge-tts`](https://pypi.org/project/edge-tts/), defaulting to
    `en-US-GuyNeural`. Falls back to Windows SAPI automatically if `edge-tts` is not
    installed or synthesis fails, so voice never hard-breaks.
  - **`voice list`** shows a curated set of voices, **`voice set <name>`** switches,
    **`voice test`** plays a sample, **`voice engine sapi`** forces the fallback.
  - **Barge-in**: playback runs as a tracked subprocess, so **`voice stop`** (or talking
    over TARS during ambient listening) cuts it off mid-sentence. Interruption also works
    during the synthesis window, before any audio has started.
  - Utterances are cached by content hash, so repeated phrases replay instantly.
  - Markdown, box art, URLs, and code fences are stripped before speaking.
- **Voice Input (persistent recogniser)**:
  - **`wake`**: ambient hands-free listening. One `System.Speech.Recognition` process stays
    warm for the whole session rather than being respawned per phrase, and TARS acts only
    on speech that follows the wake word (default `hey tars`). Common mis-hearings of the
    hotword are accepted, since dictation engines routinely return "hey cars" or "hey stars".
  - **`listen`** / **`mic`**: capture a single spoken command.
  - **`voice-chat`**: continuous two-way loop without a wake word.
- **Spoken acknowledgement**: when a request turns into multi-step tool work, TARS says a
  short "on it" up front instead of leaving dead air until the final answer.

### 5b. Security Boundary
The agent holds a shell, so the boundary is enforced in `tars/core/security.py` rather than
left to the model's judgement.

- **Filesystem containment.** `read_file`, `write_file`, `patch_file`, `list_dir`,
  `grep_search`, and the PDF/data/image/AST tools all resolve through `resolve_safe_path()`,
  which confines them to the workspace root plus the system temp directory. **`roots`**
  shows the allowed set; **`roots add <dir>`** widens it.
- **Secrets are refused inside allowed roots too.** `.env*`, `.tars_config.json`, SSH and
  GPG directories, `*.pem` / `*.key` / `*.kdbx`, browser login stores, and ~40 other
  name and glob classes are denied for both read and write. `list_dir` withholds them
  rather than naming them, and `grep_search` skips them so searching for "password"
  cannot become a credential dump.
- **Payload classification.** Shell and Python payloads are graded SAFE / SENSITIVE /
  BLOCKED. BLOCKED (disk format, registry mutation, elevation, `iex`-from-web, Defender
  changes) never runs. SENSITIVE (recursive deletes, `shutdown`, service changes,
  `git reset --hard`, package installs) pauses for terminal approval and **denies on
  timeout or when nothing is attached to answer**. `run_python` is classified too; it
  previously ran with no checks at all, which made the shell rules moot.
- **`git_ops` is argv-based.** Its subcommand is allowlisted and its arguments are split
  into a list rather than interpolated into a PowerShell string.
- **Audit trail.** Every host action, refusal, and gate decision is appended to
  `mission_logs/audit.jsonl`. **`audit [n]`** reads it back.
- **`security`** prints the active boundary; **`confirm on|off`** controls the gate.

### 6. Non-Blocking Audio Feedback (Windows native)
- Threaded sound effects via Python's native `winsound`:
  - Cue light double-chirp
  - Morse code dots and dashes
  - Docking rotational lock chord
  - Warning and self-destruct alarms
- Toggle anytime via `sound on` / `sound off`.

---

### 7. Autonomous ReAct AI Agent Architecture
- **Model chain**: text and vision both lead with `gemini-3.8-flash` and degrade through
  `3.7-flash`, `3.6-flash`, `3.5-flash`, `flash-latest`, and finally the lite tier. The
  lite models sit at the tail deliberately — they are the quota backstop, so an exhausted
  free-tier window on the flagship degrades TARS instead of breaking it. Defined once in
  `tars/core/llm.py`; every subsystem routes through it. The status bar and `status` report
  the model that **actually served** the last turn, prefixing the intended head with `~`
  when nothing has answered yet.
- **Autonomous Tool Execution**: TARS directly interacts with your environment using
  Gemini function calling:
  - **File Operations**: `read_file`, `write_file`, `patch_file`, `list_dir`, `grep_search`.
  - **Execution Sandbox**: `run_command` (PowerShell with timeout and safety verification), `run_python` (in-memory script execution).
  - **Grounded Web Intelligence**: `web_search` (real-time live internet search), `fetch_url` (page scraper & cleaner).
  - **Machine Avionics**: `get_system_telemetry` (live CPU, memory, disk, and battery telemetry).
  - **Computer Vision**: `inspect_image` (multimodal image & screenshot analysis).
- **Autonomous Goal Runner (`/goal <objective>`)**:
  - Automatically deconstructs complex goals into sequential sub-directives.
  - Renders a live mission task matrix with real-time status updates (`PENDING`, `EXECUTING`, `COMPLETED`).
  - Executes tool actions autonomously until completion, delivering a structured tactical debrief.
- **Persistent Memory Matrix (`.tars_memory.json`)**:
  - Remembers operator facts, preferred workflows, and past mission logs across restarts.
  - Tell TARS *"Remember that my favorite framework is FastAPI"* or inspect with `/memory`.
  - Facts carry a **category and a salience weight**; anything weighted 6 or above is never
    evicted, so trivia cannot displace what matters. `memory` shows the weights.
  - A **people registry** tracks who is in your life and whether they are living, deceased,
    estranged, or unwell. Inspect with `people`. TARS fills it in from conversation and can
    also write to it directly via the `remember_person` tool.
  - TARS stores things **unprompted** now. You should not have to say "remember that" for it
    to retain your girlfriend's name or that your grandmother died.
- **Safety guardrails are structural, not personality-driven.**
  - An earlier version of this document claimed high honesty made TARS halt before
    destructive operations. It did not: the check was an unconditional regex denylist that
    ignored the honesty value entirely, and `run_python` skipped it. Enforcement now lives
    in `tars/core/security.py` and is independent of the personality dials — see
    *Security Boundary* above. Humor and honesty affect how TARS talks, not what it is
    permitted to do.

### 8. Multi-Unit Agent Architecture (TARS, CASE, KIPP)

Each unit is a real agent with its own persona, tool scope, reasoning budget, step
ceiling, and isolated conversation history — not a prompt prefix on a shared brain.
Defined in `tars/core/agents.py`, executed by the single `Agent` class in `tars/core/agent.py`.

| Unit | Designation | Role | Humor | Tools | Voice |
|---|---|---|---|---|---|
| **TARS** | USMC 04 | Commander / generalist | operator-set | 24 (incl. host control, memory, delegation) | Deadpan, dry, economical |
| **CASE** | USMC 02 | Execution: code, shell, tests | 0% | 17 (read + write + exec) | Clipped declaratives, zero banter |
| **KIPP** | USMC 01 | Research & verification | 10% | 12 (**read-only**) | Forensic, pedantic, cites everything |

- **Tool scoping is enforced, not suggested.** KIPP holds no write or exec tools, so a
  research sweep cannot have side effects. The agent loop rejects out-of-scope calls even
  if the model attempts one.
- **`host_control` belongs to TARS alone.** CASE runs up to 16 unattended steps with write
  and exec authority, which is not where physical side effects on the machine belong.
- **Memory tools belong to TARS alone.** `remember`, `remember_person`, `recall`, and
  `forget` write to the operator's personal record. That is the relationship, and a
  specialist grinding through an unattended build has no business editing it.
- **Autonomous delegation.** TARS holds `delegate_to_case` and `delegate_to_kipp` as real
  tools and decides for itself when a task suits a specialist. CASE and KIPP hold no
  delegation tools, which bounds recursion at one level by construction.
- **`hive <objective>`** puts TARS in command and lets it choose which units to involve
  and in what order, rather than forcing a fixed research-then-code pipeline.
- **`units`** shows the roster, personalities, and tool scopes.
- Direct dispatch remains available via `case <task>` and `kipp <query>`.
- **Autonomous Self-Healing Loop (`heal <command>`)**:
  - Intercepts failing tests, builds, or scripts.
  - Diagnoses the traceback, locates faulty lines, generates and applies surgical patches, and re-runs until green.
- **Data & Document Intelligence**:
  - **`pdf <file.pdf> [query]`**: Ingests and queries local PDF technical documents via `pypdf`.
  - **`data <file.csv> [query]`**: Performs data science analysis on datasets with `pandas`.
  - **`symbols [path]`**: AST code analyzer extracting class definitions, functions, arguments, and line numbers.
  - **`look` / `screen`**: Desktop screen analysis via Gemini Vision.

---

## 9. Host Control (`host_control`)

One tool with a fixed verb enum, so "operate my laptop" is a narrow, validated path rather
than a shell prompt. Ask in plain language — *"put on some music"*, *"what's my battery"*,
*"copy that to the clipboard"*, *"remind me in ten minutes"* — or drive it directly with
`host <verb>`.

| Verb | Does |
|---|---|
| `list_apps` | what TARS is allowed to launch here |
| `open_app` | launch an allowlisted application |
| `open_url` | open an http/https URL |
| `media` | play/pause, next, previous, stop |
| `volume` | up, down, set, mute |
| `brightness` | read or set the built-in panel |
| `clipboard_get` / `clipboard_set` | read or write the clipboard |
| `notify` | desktop notification |
| `lock` / `sleep_display` | lock the session, or power the screen down |
| `list_windows` / `focus_window` | enumerate and raise windows |
| `battery` / `network` | charge state, Wi-Fi association, traffic counters |
| `timer` / `list_timers` / `cancel_timer` | spoken reminders |

How it stays safe:

- **Allowlist, not denylist.** A verb absent from the table does not exist, and `open_app`
  resolves only names in the application allowlist (via PATH, the App Paths registry key,
  and common install locations). **`apps`** lists what resolved; **`apps add <name> <path>`**
  permits one more.
- **Mostly no shell at all.** Media keys, volume, window focus, lock, and display power are
  `ctypes` calls into `user32`. The few verbs that genuinely need PowerShell (brightness,
  clipboard, toast, Wi-Fi) pass every operand as base64 decoded inside the script, so text
  can never be read as code.
- **Typed parameters.** Levels and timer durations are coerced and range-checked;
  `open_url` permits only `http`/`https`, rejecting `file:`, `javascript:`, `data:`, and
  shell protocol handlers. Parameters a verb does not declare are dropped and reported
  rather than silently reaching the handler.
- **Deliberately absent**: registry writes, service control, firewall and Defender
  configuration, uninstalls, scheduled tasks, elevation, credential access, and file
  deletion. **`host off`** disables the layer entirely.

## 10. Proactive Sentinel

`proactive on` starts a background watcher that speaks up unprompted: battery low or
critical, battery charged enough to unplug, disk pressure, memory pressure, and sustained
CPU load. Each rule latches so a condition reports once and only re-arms after it clears,
and each alert is spoken, toasted, and logged. `proactive interval <seconds>` tunes the poll
rate; the setting survives restarts.

---

## ⌨️ Command Directory

Run `help` in the shell for the live, grouped reference. Highlights:

| Command | Subsystem | Description |
|---|---|---|
| `help` | Directory | Grouped command reference |
| `units` | Agent Roster | Unit personalities, tool scopes, and step ceilings |
| `new` | Session | Clear conversation context for all three units |
| `hive <mission>` | Multi-Unit | TARS commands and delegates to CASE/KIPP as the work requires |
| `case <task>` | Execution Unit | Dispatch CASE directly (0% humor, verifies by running) |
| `kipp <query>` | Research Unit | Dispatch KIPP directly (read-only, sourced findings) |
| `heal <command>` | Self-Healing | Run command, intercept errors, apply patches, & re-test |
| `look` / `screen` | Desktop Vision | Capture primary screen and diagnose with Gemini Vision |
| `pdf <file> [query]` | Document Engine | Extract and query text from PDF documents |
| `data <file> [query]` | Data Science | Load CSV/TSV with pandas, compute stats & null checks |
| `symbols [path]` | AST Code Parser | Extract classes, functions, and line numbers across code |
| `goal` / `/goal <task>` | Autonomous Agent | Execute multi-step goal with automated tool plan & debrief |
| `memory` / `/memory` | Persistent Core | Inspect, record, or clear long-term memories and mission history |
| `tools` / `/tools` | Tool Registry | Inspect all 17 active tools (files, shell, python, web, vision, etc.) |
| `host` | Host Control | List every allowlisted laptop action |
| `host <verb> [args]` | Host Control | Run one directly, e.g. `host open_app spotify` |
| `apps` / `apps add <n> <p>` | Allowlist | Applications TARS may launch |
| `mute` / `louder` / `play` | Shorthand | Direct routes to the common media actions |
| `security` | Boundary | Active roots, secret classes, and gate state |
| `roots [add\|remove] <dir>` | Boundary | Directories the filesystem tools may touch |
| `audit [n]` | Audit Trail | Recent host actions and gate decisions |
| `confirm on \| off` | Boundary | Pause for approval before sensitive commands |
| `wake` | Voice Presence | Ambient wake-word listening |
| `proactive on \| off` | Sentinel | Let TARS raise host issues unprompted |
| `sys` / `avionics` | Machine Vitals | Live CPU, RAM, Disk, and Battery avionics on TARS slabs |
| `research <topic>` | Grounded Dossier | Conduct live web research with citations & local report export |
| `status` / `hud` | Telemetry | Display NASA Endurance HUD & telemetry |
| `chassis <mode>` | Geometry | Transform slabs: `monolith`, `walk`, `roll`, `dock`, `quantum` |
| `humor <val>` | Personality | Set humor level 0-100 (e.g. `humor 60`) |
| `honesty <val>` | Personality | Set honesty level 0-100 (e.g. `honesty 95`) |
| `sarcasm <val>` | Personality | Set sarcasm quotient 0-100 |
| `empathy <val>` | Personality | How much TARS brings to a loaded moment, 0-100 (`0` disables the layer) |
| `mood` | Affective State | What TARS currently reads in the room, and why |
| `people` | Relational Memory | Who TARS knows in your life, and their status |
| `people status <name> <state>` | Relational Memory | `living` \| `deceased` \| `estranged` \| `unwell` |
| `people forget <name>` | Relational Memory | Remove someone from the registry |
| `listen` / `mic` | Voice Input | Capture voice command from microphone and execute |
| `voice-chat` | Hands-Free Loop | Continuous two-way voice conversation loop |
| `voice on / off` | Speech Synthesis | Enable or mute spoken voice feedback |
| `voice stop` | Barge-In | Cut off speech in progress |
| `voice list` / `voice set <n>` | Neural Voices | Inspect or switch the neural voice |
| `voice test` | Diagnostics | Play a sample through the active engine |
| `dock [rpm]` | Flight Simulator | 68 RPM Endurance spin docking simulation |
| `relativity [hrs]` | Relativity | Miller's planet gravitational time dilation |
| `morse <text>` | Quantum Relay | Morse code transmission via Murph's watch |
| `self-destruct` | Tactical | Classic movie countdown routine |
| `diagnostics` | Hardware Scan | System health, reactor, and torque scan |
| `logs` | Military Archives| USMC service history |
| `sound on / off` | Audio | Enable or mute audio harness |
| `callsign <name>` | Operator ID | Change commander name (default: Cooper) |
| `api-key <key>` | Neural Hook | Attach Gemini API key for open-ended LLM chat |
| `clear` | Terminal | Refresh HUD and clear screen |
| `exit` | Power Down | Power down TARS |
| *`<any prompt / task>`* | ReAct Agent | Direct TARS to inspect files, run code, search web, or converse |

---

## 🎬 Lore Quotes to Try
- *"TARS, what's your self-destruct sequence?"*
- *"TARS, tell me a joke."*
- *"Cooper, this is no time for caution!"*
- *"What happened to Dr. Mann?"*
- *"Is love quantifiable, TARS?"*
- *"Humor, seventy-five percent."*
- *"Honesty, ninety-five percent."*
