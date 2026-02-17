"""Pytest configuration for marketplace tests."""

import sys
from pathlib import Path

# Add marketplace directory to path FIRST for imports (models, config, etc)
marketplace_dir = Path(__file__).parent.parent
if str(marketplace_dir) not in sys.path:
    sys.path.insert(0, str(marketplace_dir))

# Add shared directory to path
shared_dir = marketplace_dir.parent / "shared"
if str(shared_dir) not in sys.path:
    sys.path.append(str(shared_dir))
