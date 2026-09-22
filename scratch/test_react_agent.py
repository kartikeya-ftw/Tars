"""
Integration test for TARS ReAct Agent with Tool Execution
"""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tars.core.agent import tars_agent

def test_react_agent():
    print("Testing TarsAgent ReAct execution with tool calling...")
    query = "Check the files in the current directory and give me a 1-sentence deadpan report."
    reply, cue = tars_agent.run(query, verbose=True)
    print("\n--- AGENT RESPONSE ---")
    print("Cue Light:", cue)
    print("Reply:\n", reply)
    assert len(reply) > 0, "Agent returned empty reply"
    print("\n✔ ReAct Agent test passed.")

if __name__ == "__main__":
    test_react_agent()
