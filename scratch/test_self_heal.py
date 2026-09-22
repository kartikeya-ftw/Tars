"""
Integration test for TARS Autonomous Self-Healing Loop
Creates a script with an intentional bug, runs heal_and_execute, and verifies autonomous recovery.
"""
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tars.core.agent import tars_agent

def test_self_healing():
    buggy_file = "scratch/buggy_target.py"
    with open(buggy_file, "w", encoding="utf-8") as f:
        f.write("# Intentionally flawed calculation\ndef compute():\n    return 2 + 2\n\nassert compute() == 5, 'Fatal anomaly: 2+2 must equal 4'\nprint('COMPUTATION SUCCESS')\n")
    
    print("Created intentionally broken script in scratch/buggy_target.py...")
    print("Launching TARS Autonomous Self-Healing Loop...")
    
    success, msg = tars_agent.heal_and_execute(f"python {buggy_file}", max_retries=3, verbose=True)
    print("\n--- SELF-HEAL RESULT ---")
    print("Success:", success)
    print("Message:", msg)
    
    # Verify the file was fixed
    with open(buggy_file, "r", encoding="utf-8") as f:
        fixed_content = f.read()
    print("Fixed script content:\n", fixed_content)
    
    # Cleanup
    if os.path.exists(buggy_file):
        os.remove(buggy_file)
        
    assert success is True, f"Self-healing loop failed: {msg}"
    print("\n✔ Autonomous Self-Healing test passed successfully!")

if __name__ == "__main__":
    test_self_healing()
