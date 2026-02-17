"""Pytest configuration for compute tests."""

import sys
from pathlib import Path

# Add compute directory to path FIRST for imports (services, config, etc)
compute_dir = Path(__file__).parent.parent
if str(compute_dir) not in sys.path:
    sys.path.insert(0, str(compute_dir))

# Add shared directory to path
shared_dir = compute_dir.parent / "shared"
if str(shared_dir) not in sys.path:
    sys.path.append(str(shared_dir))
