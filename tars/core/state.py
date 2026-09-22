from enum import Enum
import time

class ChassisMode(str, Enum):
    MONOLITH = "MONOLITH"     # Default 4-column solid slab
    WALK = "WALK"             # Staggered tripod / crutch walking gait
    ROLL = "ROLL"             # High-speed pinwheel rescue mode
    DOCK = "DOCK"             # Thruster and vector RCS alignment
    QUANTUM = "QUANTUM"       # Tesseract data transmission grid

class TarsState:
    def __init__(self):
        self.chassis_mode: ChassisMode = ChassisMode.MONOLITH
        self.reactor_power: float = 98.4
        self.battery_cells: str = "4/4 OK"
        self.hinge_torque: str = "NOMINAL (14,200 Nm)"
        self.thruster_rcs: str = "ACTIVE (Delta-V Ready)"
        self.mission_status: str = "ENDURANCE // LAZARUS MISSION"
        self.location: str = "DEEP SPACE // GARGANTUA PROXIMITY"
        self.cue_light_active: bool = False
        self.last_cue_reason: str = ""
        self.boot_time: float = time.time()
        self.commands_processed: int = 0

    @property
    def uptime_str(self) -> str:
        seconds = int(time.time() - self.boot_time)
        hrs = seconds // 3600
        mins = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"

state = TarsState()
