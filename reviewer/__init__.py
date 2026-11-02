"""Reviewer package compatibility alias."""
import sys
from pathlib import Path

_root = str(Path(__file__).parent.parent.resolve())
if _root not in sys.path:
    sys.path.insert(0, _root)

from src import *

