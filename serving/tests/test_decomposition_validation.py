"""Unit tests for DecompositionValidationService.

Tests circular dependency detection, invalid reference handling,
auto-fix behavior, and scope warning generation.
"""

import pytest

from models.goal_decomposer import DecomposedIssue, GoalDecompositionResult
from services.decomposition_validation_service import (
    DecompositionValidationResult,
    DecompositionValidationService,
    validate_decomposition,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _issue(temp_id: str, blocked_by: list[str] | None = None, **kwargs) -> DecomposedIssue:
    """Helper to build a DecomposedIssue with minimal boilerplate."""
    defaults = {
        "temp_id": temp_id,
        "title": kwargs.pop("title", f"Issue {temp_id}"),
        "description": kwargs.pop("description", f"Description for {temp_id}"),
        "blocked_by": blocked_by or [],
        "acceptance_criteria": kwargs.pop("acceptance_criteria", ["AC1"]),
    }
    defaults.update(kwargs)
    return DecomposedIssue(**defaults)


def _result(issues: list[DecomposedIssue]) -> GoalDecompositionResult:
    """Helper to build a GoalDecompositionResult."""
    return GoalDecompositionResult(
        goal_id="goal-1",
        decomposition_id="decomp-1",
        issues=issues,
        confidence=0.8,
        reasoning="test",
    )


@pytest.fixture
def service():
    return DecompositionValidationService()


# ---------------------------------------------------------------------------
# Valid decompositions
# ---------------------------------------------------------------------------

class TestValidDecomposition:
    """Tests for valid decomposition results."""

    def test_empty_issues(self, service):
        result = _result([])
        v = service.validate(result)
        assert v.valid
        assert not v.issues

    def test_simple_chain(self, service):
        """A -> B -> C is valid."""
        issues = [
            _issue("a"),
            _issue("b", blocked_by=["a"]),
            _issue("c", blocked_by=["b"]),
        ]
        v = service.validate(_result(issues))
        assert v.valid
        assert not v.errors

    def test_diamond_dependency(self, service):
        """A -> B, A -> C, B -> D, C -> D is valid."""
        issues = [
            _issue("a"),
            _issue("b", blocked_by=["a"]),
            _issue("c", blocked_by=["a"]),
            _issue("d", blocked_by=["b", "c"]),
        ]
        v = service.validate(_result(issues))
        assert v.valid

    def test_no_dependencies(self, service):
        """All independent issues are valid."""
        issues = [_issue("a"), _issue("b"), _issue("c")]
        v = service.validate(_result(issues))
        assert v.valid


# ---------------------------------------------------------------------------
# Circular dependency detection
# ---------------------------------------------------------------------------

class TestCircularDependency:
    """Tests for circular dependency detection."""

    def test_simple_cycle(self, service):
        """A -> B -> A is a cycle."""
        issues = [
            _issue("a", blocked_by=["b"]),
            _issue("b", blocked_by=["a"]),
        ]
        v = service.validate(_result(issues), auto_fix=False)
        assert not v.valid
        assert any(e.code == "circular_dependency" for e in v.errors)

    def test_three_node_cycle(self, service):
        """A -> B -> C -> A is a cycle."""
        issues = [
            _issue("a", blocked_by=["c"]),
            _issue("b", blocked_by=["a"]),
            _issue("c", blocked_by=["b"]),
        ]
        v = service.validate(_result(issues), auto_fix=False)
        assert not v.valid
        assert any(e.code == "circular_dependency" for e in v.errors)

    def test_self_dependency(self, service):
        """A -> A is a self-ref."""
        issues = [_issue("a", blocked_by=["a"])]
        v = service.validate(_result(issues), auto_fix=False)
        assert not v.valid
        assert any(e.code == "self_dependency" for e in v.errors)

    def test_cycle_auto_fix(self, service):
        """Auto-fix breaks cycles by removing back-edges."""
        issues = [
            _issue("a", blocked_by=["b"]),
            _issue("b", blocked_by=["a"]),
        ]
        v = service.validate(_result(issues), auto_fix=True)
        assert v.fixed_result is not None
        # After fix, at least one of the cycle edges should be removed
        fixed_deps = {
            di.temp_id: di.blocked_by for di in v.fixed_result.issues
        }
        # Not both can still point to each other
        assert not (
            "b" in fixed_deps.get("a", []) and "a" in fixed_deps.get("b", [])
        )


# ---------------------------------------------------------------------------
# Invalid reference detection
# ---------------------------------------------------------------------------

class TestInvalidReferences:
    """Tests for blocked_by references to non-existent temp_ids."""

    def test_missing_dependency(self, service):
        """Reference to non-existent temp_id."""
        issues = [_issue("a", blocked_by=["nonexistent"])]
        v = service.validate(_result(issues), auto_fix=False)
        assert not v.valid
        assert any(e.code == "invalid_dependency_ref" for e in v.errors)

    def test_missing_dependency_auto_fix(self, service):
        """Auto-fix removes invalid references."""
        issues = [_issue("a", blocked_by=["nonexistent", "also_missing"])]
        v = service.validate(_result(issues), auto_fix=True)
        assert v.fixed_result is not None
        fixed_a = next(di for di in v.fixed_result.issues if di.temp_id == "a")
        assert fixed_a.blocked_by == []


# ---------------------------------------------------------------------------
# Duplicate temp_id detection
# ---------------------------------------------------------------------------

class TestDuplicateTempIds:
    """Tests for duplicate temp_id detection."""

    def test_duplicate_detected(self, service):
        issues = [_issue("a"), _issue("a", title="Different title")]
        v = service.validate(_result(issues), auto_fix=False)
        assert not v.valid
        assert any(e.code == "duplicate_temp_id" for e in v.errors)


# ---------------------------------------------------------------------------
# Scope warnings
# ---------------------------------------------------------------------------

class TestScopeWarnings:
    """Tests for scope-related warnings."""

    def test_empty_title_is_error(self, service):
        issues = [_issue("a", title="")]
        v = service.validate(_result(issues))
        assert any(e.code == "empty_title" and e.severity == "error" for e in v.issues)

    def test_empty_description_is_warning(self, service):
        issues = [_issue("a", description="")]
        v = service.validate(_result(issues))
        assert any(e.code == "empty_description" and e.severity == "warning" for e in v.issues)

    def test_no_acceptance_criteria_is_warning(self, service):
        issues = [_issue("a", acceptance_criteria=[])]
        v = service.validate(_result(issues))
        assert any(e.code == "no_acceptance_criteria" and e.severity == "warning" for e in v.issues)

    def test_warnings_dont_fail_validation(self, service):
        """Warnings alone should not make the result invalid."""
        issues = [_issue("a", description="", acceptance_criteria=[])]
        v = service.validate(_result(issues))
        assert v.valid  # Only errors cause invalid


# ---------------------------------------------------------------------------
# Self-reference auto-fix
# ---------------------------------------------------------------------------

class TestSelfRefAutoFix:
    """Tests for self-reference auto-fix."""

    def test_self_ref_removed(self, service):
        issues = [_issue("a", blocked_by=["a"])]
        v = service.validate(_result(issues), auto_fix=True)
        assert v.fixed_result is not None
        fixed_a = v.fixed_result.issues[0]
        assert "a" not in fixed_a.blocked_by


# ---------------------------------------------------------------------------
# Integration: validate_decomposition function
# ---------------------------------------------------------------------------

class TestValidateFunction:
    """Tests for the module-level validate_decomposition function."""

    def test_direct_call(self):
        issues = [_issue("a"), _issue("b", blocked_by=["a"])]
        v = validate_decomposition(_result(issues))
        assert v.valid

    def test_mixed_errors_and_warnings(self):
        issues = [
            _issue("a", blocked_by=["missing"], description="", acceptance_criteria=[]),
        ]
        v = validate_decomposition(_result(issues), auto_fix=False)
        assert not v.valid
        assert len(v.errors) >= 1
        assert len(v.warnings) >= 1
