#!/usr/bin/env python3
"""
Python Code Review Tool - Root Entrypoint
"""

import sys
from pathlib import Path

# Ensure src package is in sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from src.cli import main

if __name__ == "__main__":
    main()
