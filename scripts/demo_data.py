#!/usr/bin/env python3
"""Demo data script for ClaudeVN development testing.

This is a thin wrapper that delegates to the demo_data package.
Run directly: python scripts/demo_data.py [args]
Or as module: python -m demo_data [args]  (from scripts/ directory)
"""
import sys
from pathlib import Path

# Ensure scripts/ is on the path so demo_data package can be imported
SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from demo_data.__main__ import main

if __name__ == "__main__":
    main()
