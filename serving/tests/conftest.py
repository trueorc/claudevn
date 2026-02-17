"""Pytest configuration for serving tests."""

import sys
from pathlib import Path

# Add serving directory to path FIRST for imports (models, config, services)
serving_dir = Path(__file__).parent.parent
if str(serving_dir) not in sys.path:
    sys.path.insert(0, str(serving_dir))

# Add shared directory to path
shared_dir = serving_dir.parent / "shared"
if str(shared_dir) not in sys.path:
    sys.path.append(str(shared_dir))
