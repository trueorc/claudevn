"""Decomposition Validation Service.

Validates goal decomposition results before issue creation:
- Circular dependency detection
- temp_id reference validation (all blocked_by refs exist)
- Duplicate temp_id detection
- Scope checks (empty issues, missing fields)

Called after decompose_goal() returns and before map_to_issue_models().
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from models.goal_decomposer import DecomposedIssue, GoalDecompositionResult

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """A single validation problem found in a decomposition."""
    severity: str  # "error" or "warning"
    issue_temp_id: Optional[str]  # Which issue has the problem (None if global)
    code: str  # Machine-readable code (e.g., "circular_dependency")
    message: str  # Human-readable description


@dataclass
class DecompositionValidationResult:
    """Result of validating a decomposition."""
    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    fixed_result: Optional[GoalDecompositionResult] = None

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]


def validate_decomposition(
    result: GoalDecompositionResult,
    auto_fix: bool = True,
) -> DecompositionValidationResult:
    """Validate a GoalDecompositionResult for structural issues.

    Args:
        result: The decomposition result to validate
        auto_fix: If True, attempt to fix issues and return fixed_result

    Returns:
        DecompositionValidationResult with validation findings
    """
    issues: List[ValidationIssue] = []

    if not result.issues:
        return DecompositionValidationResult(valid=True, issues=[])

    # Collect all temp_ids
    temp_ids: Set[str] = set()
    temp_id_counts: Dict[str, int] = {}
    for di in result.issues:
        temp_id_counts[di.temp_id] = temp_id_counts.get(di.temp_id, 0) + 1
        temp_ids.add(di.temp_id)

    # 1. Duplicate temp_id detection
    for tid, count in temp_id_counts.items():
        if count > 1:
            issues.append(ValidationIssue(
                severity="error",
                issue_temp_id=tid,
                code="duplicate_temp_id",
                message=f"temp_id '{tid}' appears {count} times",
            ))

    # 2. Invalid blocked_by references
    for di in result.issues:
        for dep in di.blocked_by:
            if dep not in temp_ids:
                issues.append(ValidationIssue(
                    severity="error",
                    issue_temp_id=di.temp_id,
                    code="invalid_dependency_ref",
                    message=f"'{di.temp_id}' depends on '{dep}' which does not exist",
                ))

    # 3. Self-references
    for di in result.issues:
        if di.temp_id in di.blocked_by:
            issues.append(ValidationIssue(
                severity="error",
                issue_temp_id=di.temp_id,
                code="self_dependency",
                message=f"'{di.temp_id}' depends on itself",
            ))

    # 4. Circular dependency detection (DFS)
    cycles = _detect_cycles(result.issues)
    for cycle in cycles:
        cycle_str = " -> ".join(cycle)
        issues.append(ValidationIssue(
            severity="error",
            issue_temp_id=cycle[0],
            code="circular_dependency",
            message=f"Circular dependency: {cycle_str}",
        ))

    # 5. Scope warnings
    for di in result.issues:
        if not di.title.strip():
            issues.append(ValidationIssue(
                severity="error",
                issue_temp_id=di.temp_id,
                code="empty_title",
                message=f"'{di.temp_id}' has an empty title",
            ))
        if not di.description.strip():
            issues.append(ValidationIssue(
                severity="warning",
                issue_temp_id=di.temp_id,
                code="empty_description",
                message=f"'{di.temp_id}' has an empty description",
            ))
        if not di.acceptance_criteria:
            issues.append(ValidationIssue(
                severity="warning",
                issue_temp_id=di.temp_id,
                code="no_acceptance_criteria",
                message=f"'{di.temp_id}' has no acceptance criteria",
            ))

    has_errors = any(i.severity == "error" for i in issues)

    validation_result = DecompositionValidationResult(
        valid=not has_errors,
        issues=issues,
    )

    # Auto-fix: remove invalid dependency refs and self-refs
    if auto_fix and issues:
        fixed = _auto_fix(result, temp_ids)
        if fixed:
            validation_result.fixed_result = fixed
            logger.info(
                f"Auto-fixed decomposition {result.decomposition_id}: "
                f"resolved {len(issues)} issue(s)"
            )

    if issues:
        error_count = len(validation_result.errors)
        warn_count = len(validation_result.warnings)
        logger.warning(
            f"Decomposition {result.decomposition_id} validation: "
            f"{error_count} error(s), {warn_count} warning(s)"
        )

    return validation_result


def _detect_cycles(issues: List[DecomposedIssue]) -> List[List[str]]:
    """Detect circular dependencies using DFS.

    Returns:
        List of cycles, each cycle is a list of temp_ids forming the loop
    """
    # Build adjacency: node -> list of nodes it depends on
    graph: Dict[str, List[str]] = {}
    valid_ids = {di.temp_id for di in issues}

    for di in issues:
        # Only include valid refs (skip missing ones, they're caught separately)
        graph[di.temp_id] = [dep for dep in di.blocked_by if dep in valid_ids]

    cycles: List[List[str]] = []
    visited: Set[str] = set()
    in_stack: Set[str] = set()
    path: List[str] = []

    def dfs(node: str) -> None:
        if node in in_stack:
            # Found a cycle — extract it
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            cycles.append(cycle)
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


def _auto_fix(
    result: GoalDecompositionResult,
    valid_ids: Set[str],
) -> Optional[GoalDecompositionResult]:
    """Attempt to auto-fix a decomposition by removing invalid references.

    Fixes:
    - Removes blocked_by refs to non-existent temp_ids
    - Removes self-references from blocked_by
    - Breaks circular dependencies by removing the back-edge

    Returns:
        Fixed GoalDecompositionResult, or None if no fixable issues
    """
    changed = False
    fixed_issues: List[DecomposedIssue] = []

    for di in result.issues:
        new_blocked_by = []
        for dep in di.blocked_by:
            if dep == di.temp_id:
                changed = True  # Remove self-ref
                continue
            if dep not in valid_ids:
                changed = True  # Remove invalid ref
                continue
            new_blocked_by.append(dep)

        if new_blocked_by != di.blocked_by:
            fixed_issues.append(di.model_copy(update={"blocked_by": new_blocked_by}))
        else:
            fixed_issues.append(di.model_copy())

    # Break cycles by removing back-edges
    cycles = _detect_cycles(fixed_issues)
    if cycles:
        changed = True
        # Build a set of edges to remove (last edge in each cycle)
        edges_to_remove: Set[tuple] = set()
        for cycle in cycles:
            # Remove the back-edge: last node depends on first
            edges_to_remove.add((cycle[-2], cycle[0]))

        final_issues = []
        for di in fixed_issues:
            new_blocked = [
                dep for dep in di.blocked_by
                if (di.temp_id, dep) not in edges_to_remove
            ]
            if new_blocked != di.blocked_by:
                final_issues.append(di.model_copy(update={"blocked_by": new_blocked}))
            else:
                final_issues.append(di)
        fixed_issues = final_issues

    if not changed:
        return None

    return result.model_copy(update={"issues": fixed_issues})


# Module-level singleton
_service: Optional["DecompositionValidationService"] = None


class DecompositionValidationService:
    """Service wrapper for decomposition validation.

    Provides the singleton pattern consistent with other services.
    """

    def validate(
        self,
        result: GoalDecompositionResult,
        auto_fix: bool = True,
    ) -> DecompositionValidationResult:
        """Validate a decomposition result."""
        return validate_decomposition(result, auto_fix=auto_fix)


def get_decomposition_validation_service() -> DecompositionValidationService:
    """Get the singleton DecompositionValidationService."""
    global _service
    if _service is None:
        _service = DecompositionValidationService()
    return _service
