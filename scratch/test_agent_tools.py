"""
Unit test suite for TARS AI Agent Tool Registry
"""
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tars.core.tools import (
    read_file,
    write_file,
    patch_file,
    list_dir,
    grep_search,
    run_command,
    run_python,
    web_search,
    fetch_url,
    get_system_telemetry,
    is_dangerous_command,
    execute_tool
)

def test_file_ops():
    test_file = "scratch/test_io_temp.txt"
    # Write
    w_res = write_file(test_file, "Line 1: Alpha\nLine 2: Beta\nLine 3: Gamma\n")
    assert "Successfully wrote" in w_res, f"write_file failed: {w_res}"
    
    # Read
    r_res = read_file(test_file, start_line=2, end_line=3)
    assert "Beta" in r_res and "Gamma" in r_res, f"read_file failed: {r_res}"
    
    # Patch
    p_res = patch_file(test_file, "Line 2: Beta", "Line 2: Bravo")
    assert "Successfully patched" in p_res, f"patch_file failed: {p_res}"
    
    # Verify patch
    r2_res = read_file(test_file)
    assert "Bravo" in r2_res and "Beta" not in r2_res, f"verify patch failed: {r2_res}"
    
    # Clean up
    if os.path.exists(test_file):
        os.remove(test_file)
    print("✔ File operations test passed.")

def test_list_and_grep():
    l_res = list_dir(".")
    assert "README.md" in l_res, f"list_dir failed: {l_res}"
    
    g_res = grep_search("Christopher Nolan", ".")
    assert "README.md" in g_res or "Interstellar" in g_res, f"grep_search failed: {g_res}"
    print("✔ Directory listing & grep test passed.")

def test_execution_tools():
    # Shell
    cmd_res = run_command("Get-Location")
    assert "Path" in cmd_res or "Process Exit Code: 0" in cmd_res, f"run_command failed: {cmd_res}"
    
    # Dangerous check
    assert is_dangerous_command("rmdir /s /q test") is True
    assert is_dangerous_command("dir") is False
    
    # Python
    py_res = run_python("import math; print(f'PI={math.pi:.4f}')")
    assert "PI=3.1416" in py_res, f"run_python failed: {py_res}"
    print("✔ Shell & Python execution tests passed.")

def test_telemetry():
    telem = get_system_telemetry()
    assert "SLAB 1" in telem and "SLAB 2" in telem, f"telemetry failed: {telem}"
    print("✔ Hardware telemetry test passed.")

def test_web_search():
    res = web_search("Interstellar movie Gargantua", num_results=2)
    assert "Gargantua" in res or "Interstellar" in res or "URL" in res, f"web_search failed: {res}"
    print("✔ Web search test passed.")

if __name__ == "__main__":
    print("Running TARS Tool Registry Tests...")
    test_file_ops()
    test_list_and_grep()
    test_execution_tools()
    test_telemetry()
    test_web_search()
    print("ALL TOOL TESTS PASSED SUCCESSFULLY! ✔")
