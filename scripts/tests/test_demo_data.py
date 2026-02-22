"""Tests for demo data package.

Unit tests for the demo data definitions, phase aggregation,
and data relationship integrity. Tests don't require API calls.
"""

import pytest
from pathlib import Path
import sys

# Add scripts to path so demo_data package can be imported
SCRIPT_DIR = Path(__file__).parent.parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from demo_data.phase1_foundation import (
    DEMO_PROJECTS,
    PHASE1_GOALS,
    PHASE1_ISSUES,
)
from demo_data.phase2_execution import (
    PHASE2_GOALS,
    PHASE2_ISSUES,
    PHASE2_WORK_ITEMS,
)
from demo_data.phase3_growth import (
    PHASE3_GOALS,
    PHASE3_ISSUES,
    PHASE3_WORK_ITEMS,
)
from demo_data.compute import DEMO_COMPUTE_INSTANCES
from demo_data.skills import DEMO_SKILLS
from demo_data.cli import (
    get_goals_for_phases,
    get_issues_for_phases,
    get_work_items_for_phases,
    generate_timestamps,
)

# Aggregate all data for cross-entity tests
ALL_GOALS = PHASE1_GOALS + PHASE2_GOALS + PHASE3_GOALS
ALL_ISSUES = PHASE1_ISSUES + PHASE2_ISSUES + PHASE3_ISSUES
ALL_WORK_ITEMS = PHASE2_WORK_ITEMS + PHASE3_WORK_ITEMS


# =============================================================================
# Test: Demo Data Definitions
# =============================================================================

class TestDemoDataDefinitions:
    """Test that demo data definitions are well-formed."""

    def test_projects_have_required_fields(self):
        for project in DEMO_PROJECTS:
            assert "project_id" in project
            assert "name" in project
            assert "description" in project
            assert project["project_id"].startswith("demo-")

    def test_goals_have_required_fields(self):
        for goal in ALL_GOALS:
            assert "goal_id" in goal
            assert "title" in goal
            assert "description" in goal
            assert "priority" in goal
            assert "status" in goal
            assert goal["goal_id"].startswith("goal-demo-")

    def test_issues_have_required_fields(self):
        for issue in ALL_ISSUES:
            assert "issue_id" in issue
            assert "title" in issue
            assert "description" in issue
            assert "issue_type" in issue
            assert "area" in issue
            assert "priority" in issue
            assert "status" in issue
            assert issue["issue_id"].startswith("issue-demo-")

    def test_work_items_have_required_fields(self):
        for work in ALL_WORK_ITEMS:
            assert "work_id" in work
            assert "title" in work
            assert "description" in work
            assert "project_id" in work
            assert "status" in work
            assert work["work_id"].startswith("work-demo-")

    def test_compute_instances_have_required_fields(self):
        for instance in DEMO_COMPUTE_INSTANCES:
            assert "instance_id" in instance
            assert "name" in instance
            assert "endpoint" in instance
            assert "status" in instance
            assert instance["instance_id"].startswith("compute-")

    def test_skills_have_required_fields(self):
        for skill in DEMO_SKILLS:
            assert "id" in skill
            assert "name" in skill
            assert "description" in skill
            assert "instructions" in skill
            assert skill["id"].startswith("demo-")

    def test_issue_ids_are_unique(self):
        ids = [i["issue_id"] for i in ALL_ISSUES]
        assert len(ids) == len(set(ids)), "Duplicate issue IDs found"

    def test_work_ids_are_unique(self):
        ids = [w["work_id"] for w in ALL_WORK_ITEMS]
        assert len(ids) == len(set(ids)), "Duplicate work item IDs found"

    def test_goal_ids_are_unique(self):
        ids = [g["goal_id"] for g in ALL_GOALS]
        assert len(ids) == len(set(ids)), "Duplicate goal IDs found"

    def test_compute_ids_are_unique(self):
        ids = [c["instance_id"] for c in DEMO_COMPUTE_INSTANCES]
        assert len(ids) == len(set(ids)), "Duplicate compute IDs found"

    def test_skill_ids_are_unique(self):
        ids = [s["id"] for s in DEMO_SKILLS]
        assert len(ids) == len(set(ids)), "Duplicate skill IDs found"


# =============================================================================
# Test: Data Counts
# =============================================================================

class TestDataCounts:
    """Test that we have sufficient demo data for a rich demo."""

    def test_project_count(self):
        assert len(DEMO_PROJECTS) >= 1

    def test_goal_count(self):
        assert len(ALL_GOALS) >= 6

    def test_issue_count(self):
        assert len(ALL_ISSUES) >= 40

    def test_work_item_count(self):
        assert len(ALL_WORK_ITEMS) >= 15

    def test_compute_count(self):
        assert len(DEMO_COMPUTE_INSTANCES) >= 6

    def test_skill_count(self):
        assert len(DEMO_SKILLS) >= 15

    def test_phase1_has_goals(self):
        assert len(PHASE1_GOALS) >= 2

    def test_phase2_has_goals(self):
        assert len(PHASE2_GOALS) >= 2

    def test_phase3_has_goals(self):
        assert len(PHASE3_GOALS) >= 2


# =============================================================================
# Test: Phase Aggregation
# =============================================================================

class TestPhaseAggregation:
    """Test phase-based data selection."""

    def test_phase1_only(self):
        goals = get_goals_for_phases([1])
        issues = get_issues_for_phases([1])
        work = get_work_items_for_phases([1])

        assert len(goals) == len(PHASE1_GOALS)
        assert len(issues) == len(PHASE1_ISSUES)
        assert len(work) == 0  # Phase 1 has no work items

    def test_phase2_only(self):
        goals = get_goals_for_phases([2])
        issues = get_issues_for_phases([2])
        work = get_work_items_for_phases([2])

        assert len(goals) == len(PHASE2_GOALS)
        assert len(issues) == len(PHASE2_ISSUES)
        assert len(work) == len(PHASE2_WORK_ITEMS)

    def test_phase3_only(self):
        goals = get_goals_for_phases([3])
        issues = get_issues_for_phases([3])
        work = get_work_items_for_phases([3])

        assert len(goals) == len(PHASE3_GOALS)
        assert len(issues) == len(PHASE3_ISSUES)
        assert len(work) == len(PHASE3_WORK_ITEMS)

    def test_all_phases(self):
        goals = get_goals_for_phases([1, 2, 3])
        issues = get_issues_for_phases([1, 2, 3])
        work = get_work_items_for_phases([1, 2, 3])

        assert len(goals) == len(ALL_GOALS)
        assert len(issues) == len(ALL_ISSUES)
        assert len(work) == len(ALL_WORK_ITEMS)

    def test_empty_phases(self):
        goals = get_goals_for_phases([])
        assert len(goals) == 0


# =============================================================================
# Test: Timestamp Generation
# =============================================================================

class TestTimestampGeneration:
    """Test timestamp generation utilities."""

    def test_generate_timestamps_returns_dict(self):
        from datetime import datetime
        timestamps = generate_timestamps()
        assert "created_at" in timestamps
        assert "updated_at" in timestamps
        assert isinstance(timestamps["created_at"], datetime)

    def test_timestamps_are_in_past(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        timestamps = generate_timestamps()
        assert timestamps["created_at"] < now
        assert timestamps["updated_at"] <= now

    def test_updated_after_created(self):
        timestamps = generate_timestamps()
        assert timestamps["updated_at"] >= timestamps["created_at"]

    def test_offset_creates_older_timestamps(self):
        recent = generate_timestamps(base_offset_days=0)
        older = generate_timestamps(base_offset_days=30)
        assert older["created_at"] < recent["created_at"]


# =============================================================================
# Test: Data Relationships
# =============================================================================

class TestDataRelationships:
    """Test relationships between demo data entities."""

    def test_issues_reference_valid_goals(self):
        goal_ids = {g["goal_id"] for g in ALL_GOALS}
        for issue in ALL_ISSUES:
            if issue.get("goal_id"):
                assert issue["goal_id"] in goal_ids, (
                    f"Issue {issue['issue_id']} references unknown goal {issue['goal_id']}"
                )

    def test_issue_dependencies_reference_valid_issues(self):
        issue_ids = {i["issue_id"] for i in ALL_ISSUES}
        for issue in ALL_ISSUES:
            for dep in issue.get("depends_on", []):
                assert dep in issue_ids, (
                    f"Issue {issue['issue_id']} depends on unknown issue {dep}"
                )

    def test_work_items_reference_valid_projects(self):
        project_ids = {p["project_id"] for p in DEMO_PROJECTS}
        for work in ALL_WORK_ITEMS:
            assert work["project_id"] in project_ids, (
                f"Work item {work['work_id']} references unknown project {work['project_id']}"
            )

    def test_work_items_reference_valid_compute(self):
        compute_ids = {c["instance_id"] for c in DEMO_COMPUTE_INSTANCES}
        for work in ALL_WORK_ITEMS:
            if work.get("assigned_to"):
                assert work["assigned_to"] in compute_ids, (
                    f"Work item {work['work_id']} assigned to unknown compute {work['assigned_to']}"
                )

    def test_issues_reference_valid_compute(self):
        compute_ids = {c["instance_id"] for c in DEMO_COMPUTE_INSTANCES}
        for issue in ALL_ISSUES:
            if issue.get("assigned_compute_id"):
                assert issue["assigned_compute_id"] in compute_ids, (
                    f"Issue {issue['issue_id']} assigned to unknown compute {issue['assigned_compute_id']}"
                )


# =============================================================================
# Test: Data Variety
# =============================================================================

class TestDemoDataVariety:
    """Test that demo data provides good variety for demos."""

    def test_multiple_goal_statuses(self):
        statuses = {g["status"] for g in ALL_GOALS}
        assert "in_progress" in statuses
        assert "done" in statuses

    def test_multiple_issue_statuses(self):
        statuses = {i["status"] for i in ALL_ISSUES}
        assert len(statuses) >= 4, f"Only {len(statuses)} issue statuses: {statuses}"
        assert "done" in statuses
        assert "in_progress" in statuses
        assert "ready" in statuses
        assert "backlog" in statuses

    def test_multiple_issue_types(self):
        types = {i["issue_type"] for i in ALL_ISSUES}
        assert "feature" in types
        assert "bug" in types
        assert "test" in types
        assert "docs" in types

    def test_multiple_issue_areas(self):
        areas = {i["area"] for i in ALL_ISSUES}
        assert "api" in areas
        assert "frontend" in areas
        assert "infra" in areas

    def test_multiple_issue_priorities(self):
        priorities = {i["priority"] for i in ALL_ISSUES}
        assert "P0" in priorities
        assert "P1" in priorities
        assert "P2" in priorities

    def test_multiple_work_item_statuses(self):
        statuses = {w["status"] for w in ALL_WORK_ITEMS}
        assert "in_progress" in statuses
        assert "completed" in statuses
        assert "pending" in statuses
        assert "blocked" in statuses
        assert "review" in statuses

    def test_multiple_compute_statuses(self):
        statuses = {c["status"] for c in DEMO_COMPUTE_INSTANCES}
        assert "online" in statuses
        assert "degraded" in statuses
        assert "offline" in statuses
        assert "draining" in statuses

    def test_compute_with_special_access(self):
        has_prod = any(
            "production-access" in c.get("capabilities", {}).get("labels", [])
            for c in DEMO_COMPUTE_INSTANCES
        )
        assert has_prod, "Should have compute with production access"

    def test_compute_with_resources(self):
        has_resources = any(
            c.get("capabilities", {}).get("resources")
            for c in DEMO_COMPUTE_INSTANCES
        )
        assert has_resources, "Should have compute with resource specs"

    def test_compute_demo_metadata(self):
        for c in DEMO_COMPUTE_INSTANCES:
            assert c.get("metadata", {}).get("demo") is True

    def test_work_items_with_blockers(self):
        blocked = [w for w in ALL_WORK_ITEMS if w.get("blockers")]
        assert len(blocked) >= 2, "Should have at least 2 blocked work items"

    def test_work_items_with_branches(self):
        with_branches = [w for w in ALL_WORK_ITEMS if w.get("branch_name")]
        assert len(with_branches) >= 5, "Should have work items with branch names"

    def test_skills_have_dependencies(self):
        with_deps = [s for s in DEMO_SKILLS if s.get("dependencies")]
        assert len(with_deps) >= 5, "Should have skills with dependencies"

    def test_skills_cover_key_roles(self):
        skill_ids = {s["id"] for s in DEMO_SKILLS}
        assert "demo-code-writer" in skill_ids
        assert "demo-test-automator" in skill_ids
        assert "demo-debugger" in skill_ids
        assert "demo-code-reviewer" in skill_ids
