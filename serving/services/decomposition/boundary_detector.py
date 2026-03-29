"""Independence boundary detection for decomposition.

Identifies natural seams where work can be split without shared
mutable state during execution. A seam is defined by: separate
files/modules, separate test suites, no shared mutable state,
well-defined interface contracts.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from .goal_analyzer import CodebaseAnalysis, ModuleBoundary

logger = logging.getLogger(__name__)


@dataclass
class FileOverlap:
    """Two proposed work scopes that touch the same file."""
    file_path: str
    scope_a: str  # Work unit description or ID
    scope_b: str


@dataclass
class IndependenceBoundary:
    """A detected boundary where work can be safely split."""
    name: str
    files: List[str] = field(default_factory=list)
    test_files: List[str] = field(default_factory=list)
    interfaces_with: List[str] = field(default_factory=list)


@dataclass
class BoundaryAnalysis:
    """Result of analyzing independence boundaries.

    Includes detected boundaries plus warnings about potential
    coupling that might prevent clean splits.
    """
    boundaries: List[IndependenceBoundary] = field(default_factory=list)
    file_overlaps: List[FileOverlap] = field(default_factory=list)
    coupling_warnings: List[str] = field(default_factory=list)


class BoundaryDetector:
    """Detects independence boundaries for work unit decomposition.

    Uses the codebase analysis to find natural seams. The goal is
    to identify groups of files that can be modified independently
    without conflicts.
    """

    def __init__(self, analysis: CodebaseAnalysis):
        self._analysis = analysis
        self._file_to_module: Dict[str, str] = {
            f.path: f.module for f in analysis.file_tree
        }

    def detect_boundaries(self) -> BoundaryAnalysis:
        """Detect independence boundaries from the codebase analysis.

        Returns:
            BoundaryAnalysis with detected boundaries and coupling warnings.
        """
        result = BoundaryAnalysis()

        # Each module is a candidate boundary
        for module in self._analysis.modules:
            module_files = [
                f.path for f in self._analysis.file_tree
                if f.module == module.root_path
            ]
            module_tests = [
                t for t in self._analysis.test_files
                if t.startswith(module.root_path)
            ]

            if module_files:
                result.boundaries.append(IndependenceBoundary(
                    name=module.name,
                    files=module_files,
                    test_files=module_tests,
                ))

        return result

    def check_independence(
        self,
        scope_a_files: List[str],
        scope_b_files: List[str],
        scope_a_name: str = "A",
        scope_b_name: str = "B",
    ) -> List[FileOverlap]:
        """Check if two proposed work scopes are independent.

        Args:
            scope_a_files: Files modified by work unit A.
            scope_b_files: Files modified by work unit B.
            scope_a_name: Name/ID for work unit A.
            scope_b_name: Name/ID for work unit B.

        Returns:
            List of file overlaps (empty means independent).
        """
        set_a = set(scope_a_files)
        set_b = set(scope_b_files)
        overlapping = set_a & set_b

        return [
            FileOverlap(
                file_path=f,
                scope_a=scope_a_name,
                scope_b=scope_b_name,
            )
            for f in sorted(overlapping)
        ]

    def find_shared_config_files(
        self, target_files: List[str]
    ) -> List[str]:
        """Find configuration files that might create implicit coupling.

        If multiple work units touch files in the same module, shared
        config files (like __init__.py, package.json) could create
        merge conflicts even though the work is logically independent.
        """
        modules_touched: Set[str] = set()
        for f in target_files:
            module = self._file_to_module.get(f, "")
            if module:
                modules_touched.add(module)

        shared = []
        for config in self._analysis.config_files:
            for module in modules_touched:
                if config.startswith(module):
                    shared.append(config)
                    break

        return shared
