#!/usr/bin/env python3
"""
Python Code Review Tool - Root Entrypoint
"""

import sys
from pathlib import Path

# Fix Windows console UTF-8 output encoding for emojis and rich characters
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure src package is in sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from src.cli import main

if __name__ == "__main__":
    main()
