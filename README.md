# TARS Console Suite (Interstellar)
> *"Cooper, this is no time for caution."*

A console AI assistant built around **TARS**, the decommissioned US Marine Corps tactical
robot from Christopher Nolan's *Interstellar*, plus its two specialist units CASE and KIPP.

Python, `rich`, and `prompt_toolkit`. Underneath the persona it is a real ReAct agent: 17
tools spanning the filesystem, shell, Python execution, live web search, vision, and host
telemetry, driven by Gemini function calling, with persistent memory across restarts and
three independently-scoped agents that can hand work to each other.

The terminal UI follows a single restrained design system (`tars/ui/theme.py`): one cool
accent, muted labels against bright values, thin rules instead of frames, and real machine
readings rather than decorative gauges.

---

## 🚀 Quick Start

Launch TARS directly from PowerShell or Windows Terminal:

```powershell
python tars_cli.py
```

*(No external dependencies needed beyond `rich` and `prompt_toolkit`, which are already available in your environment).*

---

## 🤖 Features & Capabilities

### 1. Dynamic Personality Engine & Cue Light
- **`humor <0-100>`**: Adjusts TARS's sarcasm, deadpan humor, and self-destruct jokes (default: `75%`).
- **`honesty <0-100>`**: Adjusts candor vs diplomatic tact (default: `90%`).
  - *"Absolute honesty isn't always the most diplomatic nor the safest form of communication with emotional beings."*
- **`sarcasm <0-100>`**: Calibrates cynical editorial remarks.
- **Physical Cue Light**: Visual LED badge `[● CUE LIGHT ON]` flashes automatically whenever TARS tells a joke or uses sarcasm, accompanied by a double-chirp tone.

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
- **Voice Input (Speech-to-Text)**:
  - **`listen`** or **`mic`**: Listens to your microphone via Windows native `System.Speech.Recognition`, transcribes your words, prints them to the terminal (`Cooper (Voice): "..."`), executes the command or question, and speaks the answer back.
  - **`voice-chat`**: Hands-free continuous two-way voice loop. Speak directly to TARS, listen to his response, and converse without typing.
- **Voice Output (Text-to-Speech)**:
  - Powered by Windows native `System.Speech.Synthesis` using Microsoft David (stoic, male American cadence).
  - Automatically cleans markdown formatting, asterisks, URLs, and table artifacts so TARS speaks naturally.
  - **`voice on` / `voice off`**: Toggle speech synthesis anytime.

### 6. Non-Blocking Audio Feedback (Windows native)
- Threaded sound effects via Python's native `winsound`:
  - Cue light double-chirp
  - Morse code dots and dashes
  - Docking rotational lock chord
  - Warning and self-destruct alarms
- Toggle anytime via `sound on` / `sound off`.

---

### 7. Autonomous ReAct AI Agent Architecture
- **Autonomous Tool Execution**: TARS directly interacts with your environment using Gemini 3.6 Flash Function Calling:
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
- **Personality-Governed Safety Guardrails**:
  - High honesty (`honesty: 90%`) prompts and halts before potentially destructive operations.

### 8. Multi-Unit Agent Architecture (TARS, CASE, KIPP)

Each unit is a real agent with its own persona, tool scope, reasoning budget, step
ceiling, and isolated conversation history — not a prompt prefix on a shared brain.
Defined in `tars/core/agents.py`, executed by the single `Agent` class in `tars/core/agent.py`.

| Unit | Designation | Role | Humor | Tools | Voice |
|---|---|---|---|---|---|
| **TARS** | USMC 04 | Commander / generalist | operator-set | 19 (incl. delegation) | Deadpan, dry, economical |
| **CASE** | USMC 02 | Execution: code, shell, tests | 0% | 17 (read + write + exec) | Clipped declaratives, zero banter |
| **KIPP** | USMC 01 | Research & verification | 10% | 12 (**read-only**) | Forensic, pedantic, cites everything |

- **Tool scoping is enforced, not suggested.** KIPP holds no write or exec tools, so a
  research sweep cannot have side effects. The agent loop rejects out-of-scope calls even
  if the model attempts one.
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
| `sys` / `avionics` | Machine Vitals | Live CPU, RAM, Disk, and Battery avionics on TARS slabs |
| `research <topic>` | Grounded Dossier | Conduct live web research with citations & local report export |
| `status` / `hud` | Telemetry | Display NASA Endurance HUD & telemetry |
| `chassis <mode>` | Geometry | Transform slabs: `monolith`, `walk`, `roll`, `dock`, `quantum` |
| `humor <val>` | Personality | Set humor level 0-100 (e.g. `humor 60`) |
| `honesty <val>` | Personality | Set honesty level 0-100 (e.g. `honesty 95`) |
| `sarcasm <val>` | Personality | Set sarcasm quotient 0-100 |
| `listen` / `mic` | Voice Input | Capture voice command from microphone and execute |
| `voice-chat` | Hands-Free Loop | Continuous two-way voice conversation loop |
| `voice on / off` | Speech Synthesis | Enable or mute spoken voice feedback |
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
