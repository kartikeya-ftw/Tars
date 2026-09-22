"""
Unit test suite for Extended TARS Tools: Pandas Data, Matplotlib Charts, AST Symbols, Git
"""
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tars.core.tools import (
    analyze_data,
    generate_chart,
    find_symbols,
    git_ops
)
import pandas as pd

def test_ast_symbols():
    res = find_symbols("tars/core")
    assert "[CLASS] TarsAgent" in res, f"find_symbols failed: {res}"
    assert "[FUNC]" in res, f"find_symbols failed to find functions: {res}"
    print("✔ AST symbol extraction test passed.")

def test_data_and_chart():
    test_csv = "scratch/temp_data.csv"
    test_chart = "scratch/temp_chart.png"
    
    df = pd.DataFrame({
        "Planet": ["Miller", "Mann", "Edmunds"],
        "Habitability": [15.2, 4.0, 92.5]
    })
    df.to_csv(test_csv, index=False)
    
    analysis = analyze_data(test_csv)
    assert "Habitability" in analysis and "3 rows" in analysis, f"analyze_data failed: {analysis}"
    
    chart_res = generate_chart(test_csv, chart_type="bar", x_col="Planet", y_col="Habitability", output_path=test_chart)
    assert "Successfully generated" in chart_res, f"generate_chart failed: {chart_res}"
    assert os.path.exists(test_chart), f"Chart PNG file not found on disk"
    
    # Cleanup
    if os.path.exists(test_csv):
        os.remove(test_csv)
    if os.path.exists(test_chart):
        os.remove(test_chart)
    print("✔ Pandas dataset analysis & Matplotlib chart generation test passed.")

def test_git_ops():
    res = git_ops("status")
    assert len(res) > 0, "Git status returned empty output"
    print("✔ Git integration test passed.")

if __name__ == "__main__":
    print("Running Extended Tools Test Suite...")
    test_ast_symbols()
    test_data_and_chart()
    test_git_ops()
    print("ALL EXTENDED TOOL TESTS PASSED SUCCESSFULLY! ✔")
