"""Spec validator — validates work unit specs before execution.

Extends v1.0 decomposition validation with v2.0 independence checks:
- Cycle detection (retained from v1.0)
- File overlap detection (new — independence assertion)
- Missing verification criteria warnings (new)
- Target file existence checks (new)
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from models.work_unit import WorkUnit

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """A single validation problem found in a work unit set."""
    severity: str  # "error" or "warning"
    work_unit_id: Optional[str]
    code: str
    message: str


@dataclass
class SpecValidationResult:
    """Result of validating a set of work units."""
    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]


class SpecValidator:
    """Validates a set of work unit specs for structural correctness.

    Checks for issues that would cause execution or integration
    failures. Run this before approving a decomposition.
    """

    def __init__(self, repo_path: Optional[str] = None):
        """
        Args:
            repo_path: If provided, validates target file existence.
        """
        self._repo_path = repo_path

    def validate(self, units: List[WorkUnit]) -> SpecValidationResult:
        """Validate a set of work units.

        Args:
            units: Work units to validate.

        Returns:
            SpecValidationResult with findings.
        """
        issues: List[ValidationIssue] = []

        if not units:
            return SpecValidationResult(valid=True)

        unit_ids = {u.id for u in units}

        # 1. Duplicate ID detection
        id_counts: Dict[str, int] = {}
        for u in units:
            id_counts[u.id] = id_counts.get(u.id, 0) + 1
        for uid, count in id_counts.items():
            if count > 1:
                issues.append(ValidationIssue(
                    severity="error",
                    work_unit_id=uid,
                    code="duplicate_id",
                    message=f"Work unit ID '{uid}' appears {count} times",
                ))

        # 2. Dependency reference validation
        for u in units:
            for dep in u.independence.depends_on:
                if dep not in unit_ids:
                    issues.append(ValidationIssue(
                        severity="error",
                        work_unit_id=u.id,
                        code="invalid_dependency",
                        message=f"'{u.id}' depends on '{dep}' which does not exist",
                    ))
            # Self-dependency
            if u.id in u.independence.depends_on:
                issues.append(ValidationIssue(
                    severity="error",
                    work_unit_id=u.id,
                    code="self_dependency",
                    message=f"'{u.id}' depends on itself",
                ))

        # 3. Cycle detection
        cycles = self._detect_cycles(units)
        for cycle in cycles:
            issues.append(ValidationIssue(
                severity="error",
                work_unit_id=cycle[0],
                code="circular_dependency",
                message=f"Circular dependency: {' -> '.join(cycle)}",
            ))

        # 4. File overlap warnings (independence check)
        file_owners = self._build_file_ownership(units)
        for filepath, owners in file_owners.items():
            if len(owners) > 1:
                issues.append(ValidationIssue(
                    severity="warning",
                    work_unit_id=owners[0],
                    code="file_overlap",
                    message=(
                        f"File '{filepath}' is targeted by multiple units: "
                        f"{', '.join(owners)}"
                    ),
                ))

        # 5. Empty target files
        for u in units:
            if not u.formal_spec.target_files:
                issues.append(ValidationIssue(
                    severity="warning",
                    work_unit_id=u.id,
                    code="no_target_files",
                    message=f"'{u.id}' has no target files specified",
                ))

        # 6. Missing verification criteria
        for u in units:
            if not u.verification_criteria.automated:
                issues.append(ValidationIssue(
                    severity="warning",
                    work_unit_id=u.id,
                    code="no_verification",
                    message=f"'{u.id}' has no automated verification criteria",
                ))

        # 7. Target file existence (if repo_path provided)
        if self._repo_path:
            for u in units:
                for f in u.formal_spec.target_files:
                    full_path = os.path.join(self._repo_path, f)
                    # Only warn for FILE_MODIFIED — new files won't exist yet
                    for output in u.formal_spec.expected_outputs:
                        if output.path == f and output.type.value == "file_modified":
                            if not os.path.exists(full_path):
                                issues.append(ValidationIssue(
                                    severity="warning",
                                    work_unit_id=u.id,
                                    code="target_file_missing",
                                    message=f"Target file '{f}' does not exist in repo",
                                ))

        has_errors = any(i.severity == "error" for i in issues)
        return SpecValidationResult(valid=not has_errors, issues=issues)

    def _detect_cycles(self, units: List[WorkUnit]) -> List[List[str]]:
        """Detect circular dependencies using DFS."""
        graph: Dict[str, List[str]] = {}
        valid_ids = {u.id for u in units}

        for u in units:
            graph[u.id] = [d for d in u.independence.depends_on if d in valid_ids]

        cycles: List[List[str]] = []
        visited: Set[str] = set()
        in_stack: Set[str] = set()
        path: List[str] = []

        def dfs(node: str) -> None:
            if node in in_stack:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            if node in visited:
                return

            visited.add(node)
            in_stack.add(node)
            path.append(node)

            for dep in graph.get(node, []):
                dfs(dep)

            path.pop()
            in_stack.remove(node)

        for node in graph:
            if node not in visited:
                dfs(node)

        return cycles

    def _build_file_ownership(
        self, units: List[WorkUnit]
    ) -> Dict[str, List[str]]:
        """Map files to the work units that target them."""
        ownership: Dict[str, List[str]] = {}
        for u in units:
            for f in u.formal_spec.target_files:
                ownership.setdefault(f, []).append(u.id)
        return ownership
