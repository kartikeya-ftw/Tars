from tars.systems.docking import run_docking_simulation
from tars.systems.relativity import calculate_time_dilation, calculate_schwarzschild_dilation
from tars.systems.quantum import transmit_quantum_morse
from tars.systems.tactical import run_diagnostics, show_military_logs, execute_self_destruct
from tars.systems.chat import process_chat
from tars.systems.research import run_deep_research
from tars.systems.goals import run_autonomous_goal
from tars.systems.hive import run_case_task, run_kipp_research, run_hive_mission

__all__ = [
    "run_docking_simulation",
    "calculate_time_dilation",
    "calculate_schwarzschild_dilation",
    "transmit_quantum_morse",
    "run_diagnostics",
    "show_military_logs",
    "execute_self_destruct",
    "process_chat",
    "run_deep_research",
    "run_autonomous_goal",
    "run_case_task",
    "run_kipp_research",
    "run_hive_mission"
]


