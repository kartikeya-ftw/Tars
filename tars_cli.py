#!/usr/bin/env python3
"""
TARS - Tactical Automated Robot System
NASA Endurance / USMC Unit 04 Console Edition
"""
import sys
import os

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        os.system("chcp 65001 >nul 2>&1")
    except Exception:
        pass

# Ensure local tars module is discoverable
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from tars.cli import run_tars_shell

if __name__ == "__main__":
    run_tars_shell()
