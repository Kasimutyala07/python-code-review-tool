"""CLI entrypoint compatibility alias for reviewer.cli."""
import sys
from pathlib import Path

# Fix Windows console UTF-8 output encoding
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_root = str(Path(__file__).parent.parent.resolve())
if _root not in sys.path:
    sys.path.insert(0, _root)

from src.cli import main

if __name__ == "__main__":
    main()
