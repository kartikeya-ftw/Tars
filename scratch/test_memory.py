"""
Unit test suite for TARS Persistent Memory
"""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tars.core.memory import memory

def test_memory():
    # Save a fact
    memory.remember_fact("Commander is testing the new memory subsystem.")
    summary = memory.get_memory_summary()
    assert "Commander is testing the new memory subsystem." in summary, "Fact not in summary"

    # Context prompt
    prompt = memory.get_memory_context_prompt()
    assert "Commander is testing the new memory subsystem." in prompt, "Fact not in context prompt"

    # Mission record
    memory.record_mission("Test Objective 1", "Executed memory validation successfully.", success=True)
    assert len(memory.mission_history) > 0, "Mission history not recorded"
    
    print("✔ Memory save, load, and context prompt tests passed.")

if __name__ == "__main__":
    test_memory()
    print("ALL MEMORY TESTS PASSED SUCCESSFULLY! ✔")
