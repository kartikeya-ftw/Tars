"""
TARS Tactical Automated Robot System - Console Edition
Inspired by Christopher Nolan's Interstellar.
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

__version__ = "4.2.0"
__robot__ = "TARS (USMC Surplus Unit 4)"

