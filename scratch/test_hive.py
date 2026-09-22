"""
Integration test for Multi-Agent Hive subsystem: TARS, CASE, KIPP
"""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tars.systems.hive import run_case_task, run_kipp_research

def test_subagents():
    print("Testing CASE tactical coding subagent...")
    case_res = run_case_task("Check what python version we are running using run_python.")
    print("CASE result preview:", case_res[:150])
    assert len(case_res) > 0, "CASE returned empty response"

    print("\nTesting KIPP research specialist subagent...")
    kipp_res = run_kipp_research("Look up the Schwarzschild radius formula using your knowledge or tools.")
    print("KIPP result preview:", kipp_res[:150])
    assert len(kipp_res) > 0, "KIPP returned empty response"

    print("\n✔ Subagents CASE and KIPP test passed successfully!")

if __name__ == "__main__":
    test_subagents()
