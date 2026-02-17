"""Tests for demo data script.

Unit tests for the demo data generation functions and models.
Tests focus on data object creation without actual API calls.
"""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

# Add scripts to path
SCRIPT_DIR = Path(__file__).parent.parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "serving"))
sys.path.insert(0, str(PROJECT_ROOT / "marketplace"))
sys.path.insert(0, str(PROJECT_ROOT / "shared"))

from demo_data import (
    DEMO_PROJECTS,
    DEMO_GOALS,
    DEMO_ISSUES,
    DEMO_WORK_ITEMS,
    DEMO_COMPUTE_INSTANCES,
    DEMO_SKILLS,
    create_project,
    create_goal,
    create_issue,
    create_work_item,
    create_compute_instance,
    create_skill,
    generate_timestamps,
)
from serving.models.project import Project, ProjectStatus
from serving.models.work_map import (
    Goal, GoalStatus, Issue, IssueStatus, IssueType, IssuePriority,
    WorkItem, WorkStatus, WorkPriority, Blocker, BlockerType
)
from serving.models.compute import ComputeInstance, InstanceStatus
from marketplace.models import Skill


# =============================================================================
# Test: Demo Data Definitions
# =============================================================================

class TestDemoDataDefinitions:
    """Test that demo data definitions are well-formed."""

    def test_projects_have_required_fields(self):
        """All projects have required fields."""
        for project in DEMO_PROJECTS:
            assert "project_id" in project
            assert "name" in project
            assert project["project_id"].startswith("demo-")

    def test_goals_have_required_fields(self):
        """All goals have required fields."""
        for goal in DEMO_GOALS:
            assert "goal_id" in goal
            assert "title" in goal
            assert "description" in goal
            assert goal["goal_id"].startswith("goal-")

    def test_issues_have_required_fields(self):
        """All issues have required fields."""
        for issue in DEMO_ISSUES:
            assert "issue_id" in issue
            assert "title" in issue
            assert "description" in issue
            assert issue["issue_id"].startswith("issue-")

    def test_work_items_have_required_fields(self):
        """All work items have required fields."""
        for work in DEMO_WORK_ITEMS:
            assert "work_id" in work
            assert "title" in work
            assert "description" in work
            assert "project_id" in work
            assert work["work_id"].startswith("work-")

    def test_compute_instances_have_required_fields(self):
        """All compute instances have required fields."""
        for instance in DEMO_COMPUTE_INSTANCES:
            assert "instance_id" in instance
            assert "name" in instance
            assert "endpoint" in instance
            assert instance["instance_id"].startswith("compute-demo-")

    def test_skills_have_required_fields(self):
        """All skills have required fields."""
        for skill in DEMO_SKILLS:
            assert "id" in skill
            assert "name" in skill
            assert "description" in skill
            assert "instructions" in skill
            assert skill["id"].startswith("demo-")

    def test_issue_dependencies_reference_valid_issues(self):
        """Issue dependencies reference existing issues."""
        issue_ids = {i["issue_id"] for i in DEMO_ISSUES}
        for issue in DEMO_ISSUES:
            for dep in issue.get("depends_on", []):
                assert dep in issue_ids, f"Issue {issue['issue_id']} depends on unknown issue {dep}"


# =============================================================================
# Test: Timestamp Generation
# =============================================================================

class TestTimestampGeneration:
    """Test timestamp generation utilities."""

    def test_generate_timestamps_returns_dict(self):
        """generate_timestamps returns dict with created_at and updated_at."""
        timestamps = generate_timestamps()
        assert "created_at" in timestamps
        assert "updated_at" in timestamps
        assert isinstance(timestamps["created_at"], datetime)
        assert isinstance(timestamps["updated_at"], datetime)

    def test_timestamps_are_in_past(self):
        """Generated timestamps are in the past."""
        now = datetime.now(timezone.utc)
        timestamps = generate_timestamps()
        assert timestamps["created_at"] < now
        assert timestamps["updated_at"] <= now

    def test_updated_after_created(self):
        """Updated timestamp is after or equal to created timestamp."""
        timestamps = generate_timestamps()
        assert timestamps["updated_at"] >= timestamps["created_at"]

    def test_offset_creates_older_timestamps(self):
        """Base offset creates older timestamps."""
        recent = generate_timestamps(base_offset_days=0)
        older = generate_timestamps(base_offset_days=30)

        # Older timestamps should be further in the past
        assert older["created_at"] < recent["created_at"]


# =============================================================================
# Test: Project Creation
# =============================================================================

class TestCreateProject:
    """Test project creation from demo data."""

    def test_create_basic_project(self):
        """Create a project with basic fields."""
        data = DEMO_PROJECTS[0]
        project = create_project(data)

        assert isinstance(project, Project)
        assert project.project_id == data["project_id"]
        assert project.name == data["name"]
        assert project.description == data["description"]
        assert project.status == ProjectStatus.ACTIVE

    def test_project_has_repos(self):
        """Project is created with repository configurations."""
        data = DEMO_PROJECTS[0]
        project = create_project(data)

        assert len(project.repos) == len(data["repos"])
        assert project.repos[0].name == data["repos"][0]["name"]
        assert project.repos[0].url == data["repos"][0]["url"]

    def test_project_has_primary_repo(self):
        """Project has primary repo set if repos exist."""
        data = DEMO_PROJECTS[0]
        project = create_project(data)

        assert project.primary_repo_id is not None
        assert project.primary_repo_id == data["repos"][0]["repo_id"]

    def test_project_has_metadata(self):
        """Project includes metadata from definition."""
        data = DEMO_PROJECTS[0]
        project = create_project(data)

        assert project.metadata.get("demo") is True

    def test_project_has_timestamps(self):
        """Project has created_at and updated_at timestamps."""
        data = DEMO_PROJECTS[0]
        project = create_project(data)

        assert project.created_at is not None
        assert project.updated_at is not None
        assert project.created_at <= datetime.now(timezone.utc)


# =============================================================================
# Test: Goal Creation
# =============================================================================

class TestCreateGoal:
    """Test goal creation from demo data."""

    def test_create_basic_goal(self):
        """Create a goal with basic fields."""
        data = DEMO_GOALS[0]
        goal = create_goal(data)

        assert isinstance(goal, Goal)
        assert goal.goal_id == data["goal_id"]
        assert goal.title == data["title"]
        assert goal.description == data["description"]

    def test_goal_status_mapping(self):
        """Goal status is correctly mapped."""
        # Test planning
        planning_goal = [g for g in DEMO_GOALS if g["status"] == "planning"][0]
        goal = create_goal(planning_goal)
        assert goal.status == GoalStatus.PLANNING

        # Test in_progress
        progress_goal = [g for g in DEMO_GOALS if g["status"] == "in_progress"][0]
        goal = create_goal(progress_goal)
        assert goal.status == GoalStatus.IN_PROGRESS

        # Test done
        done_goal = [g for g in DEMO_GOALS if g["status"] == "done"][0]
        goal = create_goal(done_goal)
        assert goal.status == GoalStatus.DONE

    def test_goal_priority_mapping(self):
        """Goal priority is correctly mapped."""
        p0_goal = [g for g in DEMO_GOALS if g["priority"] == "P0"][0]
        goal = create_goal(p0_goal)
        assert goal.priority == IssuePriority.P0


# =============================================================================
# Test: Issue Creation
# =============================================================================

class TestCreateIssue:
    """Test issue creation from demo data."""

    def test_create_basic_issue(self):
        """Create an issue with basic fields."""
        data = DEMO_ISSUES[0]
        issue = create_issue(data)

        assert isinstance(issue, Issue)
        assert issue.issue_id == data["issue_id"]
        assert issue.title == data["title"]
        assert issue.description == data["description"]

    def test_issue_status_mapping(self):
        """Issue status is correctly mapped."""
        # Check various statuses exist in demo data
        status_tests = [
            ("done", IssueStatus.DONE),
            ("in_progress", IssueStatus.IN_PROGRESS),
            ("ready", IssueStatus.READY),
            ("backlog", IssueStatus.BACKLOG),
            ("blocked", IssueStatus.BLOCKED),
        ]

        for status_str, status_enum in status_tests:
            issues = [i for i in DEMO_ISSUES if i["status"] == status_str]
            if issues:
                issue = create_issue(issues[0])
                assert issue.status == status_enum, f"Status {status_str} should map to {status_enum}"

    def test_issue_type_mapping(self):
        """Issue type is correctly mapped."""
        type_tests = [
            ("feature", IssueType.FEATURE),
            ("bug", IssueType.BUG),
            ("docs", IssueType.DOCS),
            ("test", IssueType.TEST),
            ("refactor", IssueType.REFACTOR),
        ]

        for type_str, type_enum in type_tests:
            issues = [i for i in DEMO_ISSUES if i.get("issue_type") == type_str]
            if issues:
                issue = create_issue(issues[0])
                assert issue.issue_type == type_enum, f"Type {type_str} should map to {type_enum}"

    def test_issue_has_dependencies(self):
        """Issue preserves dependency references."""
        dep_issue = [i for i in DEMO_ISSUES if i.get("depends_on")][0]
        issue = create_issue(dep_issue)

        assert len(issue.depends_on) > 0
        assert issue.depends_on == dep_issue["depends_on"]

    def test_issue_has_required_skills(self):
        """Issue preserves required skills."""
        skill_issue = [i for i in DEMO_ISSUES if i.get("required_skills")][0]
        issue = create_issue(skill_issue)

        assert len(issue.required_skills) > 0
        assert issue.required_skills == skill_issue["required_skills"]

    def test_in_progress_issue_has_started_at(self):
        """In-progress issues have started_at timestamp."""
        progress_issue = [i for i in DEMO_ISSUES if i["status"] == "in_progress"][0]
        issue = create_issue(progress_issue)

        assert issue.started_at is not None

    def test_done_issue_has_completed_at(self):
        """Done issues have completed_at timestamp."""
        done_issue = [i for i in DEMO_ISSUES if i["status"] == "done"][0]
        issue = create_issue(done_issue)

        assert issue.completed_at is not None


# =============================================================================
# Test: Work Item Creation
# =============================================================================

class TestCreateWorkItem:
    """Test work item creation from demo data."""

    def test_create_basic_work_item(self):
        """Create a work item with basic fields."""
        data = DEMO_WORK_ITEMS[0]
        work = create_work_item(data)

        assert isinstance(work, WorkItem)
        assert work.work_id == data["work_id"]
        assert work.title == data["title"]
        assert work.description == data["description"]

    def test_work_item_status_mapping(self):
        """Work item status is correctly mapped."""
        status_tests = [
            ("pending", WorkStatus.PENDING),
            ("in_progress", WorkStatus.IN_PROGRESS),
            ("completed", WorkStatus.COMPLETED),
            ("blocked", WorkStatus.BLOCKED),
        ]

        for status_str, status_enum in status_tests:
            items = [w for w in DEMO_WORK_ITEMS if w["status"] == status_str]
            if items:
                work = create_work_item(items[0])
                assert work.status == status_enum

    def test_work_item_priority_mapping(self):
        """Work item priority is correctly mapped."""
        priority_tests = [
            ("critical", WorkPriority.CRITICAL),
            ("high", WorkPriority.HIGH),
            ("normal", WorkPriority.NORMAL),
        ]

        for priority_str, priority_enum in priority_tests:
            items = [w for w in DEMO_WORK_ITEMS if w.get("priority") == priority_str]
            if items:
                work = create_work_item(items[0])
                assert work.priority == priority_enum

    def test_work_item_has_blockers(self):
        """Work item with blockers has Blocker objects."""
        blocked_item = [w for w in DEMO_WORK_ITEMS if w.get("blockers")][0]
        work = create_work_item(blocked_item)

        assert len(work.blockers) > 0
        assert isinstance(work.blockers[0], Blocker)
        assert work.blockers[0].blocker_type == BlockerType.EXTERNAL

    def test_work_item_has_tags(self):
        """Work item preserves tags."""
        tagged_item = [w for w in DEMO_WORK_ITEMS if w.get("tags")][0]
        work = create_work_item(tagged_item)

        assert len(work.tags) > 0
        assert work.tags == tagged_item["tags"]

    def test_assigned_work_has_timestamps(self):
        """Assigned work items have assignment timestamps."""
        assigned_item = [w for w in DEMO_WORK_ITEMS if w.get("assigned_to")][0]
        work = create_work_item(assigned_item)

        assert work.assigned_to is not None
        assert work.assigned_at is not None

    def test_in_progress_work_has_activity(self):
        """In-progress work items have activity tracking."""
        progress_item = [w for w in DEMO_WORK_ITEMS if w["status"] == "in_progress"][0]
        work = create_work_item(progress_item)

        assert work.started_at is not None
        assert work.last_activity_at is not None


# =============================================================================
# Test: Compute Instance Creation
# =============================================================================

class TestCreateComputeInstance:
    """Test compute instance creation from demo data."""

    def test_create_basic_instance(self):
        """Create a compute instance with basic fields."""
        data = DEMO_COMPUTE_INSTANCES[0]
        instance = create_compute_instance(data)

        assert isinstance(instance, ComputeInstance)
        assert instance.instance_id == data["instance_id"]
        assert instance.name == data["name"]
        assert instance.endpoint == data["endpoint"]

    def test_instance_status_mapping(self):
        """Instance status is correctly mapped."""
        status_tests = [
            ("online", InstanceStatus.ONLINE),
            ("degraded", InstanceStatus.DEGRADED),
            ("offline", InstanceStatus.OFFLINE),
        ]

        for status_str, status_enum in status_tests:
            instances = [i for i in DEMO_COMPUTE_INSTANCES if i["status"] == status_str]
            if instances:
                instance = create_compute_instance(instances[0])
                assert instance.status == status_enum

    def test_instance_has_capabilities(self):
        """Instance has capabilities object."""
        data = DEMO_COMPUTE_INSTANCES[0]
        instance = create_compute_instance(data)

        assert instance.capabilities is not None
        assert len(instance.capabilities.agents) > 0
        assert len(instance.capabilities.tools) > 0

    def test_instance_has_labels(self):
        """Instance with labels has them in capabilities."""
        labeled_instance = [i for i in DEMO_COMPUTE_INSTANCES if i.get("capabilities", {}).get("labels")][0]
        instance = create_compute_instance(labeled_instance)

        assert len(instance.capabilities.labels) > 0

    def test_instance_has_tools_available(self):
        """Instance with tools_available has them in capabilities."""
        tool_instance = [i for i in DEMO_COMPUTE_INSTANCES if i.get("capabilities", {}).get("tools_available")][0]
        instance = create_compute_instance(tool_instance)

        assert len(instance.capabilities.tools_available) > 0

    def test_instance_has_resources(self):
        """Instance with resources has InstanceResources object."""
        resource_instance = [i for i in DEMO_COMPUTE_INSTANCES if i.get("capabilities", {}).get("resources")][0]
        instance = create_compute_instance(resource_instance)

        assert instance.capabilities.resources is not None
        assert instance.capabilities.resources.cpu_count is not None

    def test_instance_has_timestamps(self):
        """Instance has registration and heartbeat timestamps."""
        data = DEMO_COMPUTE_INSTANCES[0]
        instance = create_compute_instance(data)

        assert instance.registered_at is not None
        assert instance.last_heartbeat is not None


# =============================================================================
# Test: Skill Creation
# =============================================================================

class TestCreateSkill:
    """Test skill creation from demo data."""

    def test_create_basic_skill(self):
        """Create a skill with basic fields."""
        data = DEMO_SKILLS[0]
        skill = create_skill(data)

        assert isinstance(skill, Skill)
        assert skill.id == data["id"]
        assert skill.name == data["name"]
        assert skill.description == data["description"]

    def test_skill_has_instructions(self):
        """Skill has instructions content."""
        data = DEMO_SKILLS[0]
        skill = create_skill(data)

        assert skill.instructions is not None
        assert len(skill.instructions) > 0
        assert "#" in skill.instructions  # Markdown header

    def test_skill_has_tags(self):
        """Skill has tags for discovery."""
        data = DEMO_SKILLS[0]
        skill = create_skill(data)

        assert len(skill.tags) > 0

    def test_skill_has_author(self):
        """Skill has user author prefix."""
        data = DEMO_SKILLS[0]
        skill = create_skill(data)

        assert skill.author == "user:demo"

    def test_skill_has_version(self):
        """Skill has version."""
        data = DEMO_SKILLS[0]
        skill = create_skill(data)

        assert skill.version == "1.0.0"

    def test_skill_has_timestamps(self):
        """Skill has timestamps."""
        data = DEMO_SKILLS[0]
        skill = create_skill(data)

        assert skill.created_at is not None
        assert skill.updated_at is not None


# =============================================================================
# Test: Data Relationships
# =============================================================================

class TestDataRelationships:
    """Test relationships between demo data entities."""

    def test_issues_reference_valid_goals(self):
        """Issues with goal_id reference existing goals."""
        goal_ids = {g["goal_id"] for g in DEMO_GOALS}
        for issue in DEMO_ISSUES:
            if issue.get("goal_id"):
                assert issue["goal_id"] in goal_ids, f"Issue {issue['issue_id']} references unknown goal"

    def test_work_items_reference_valid_projects(self):
        """Work items reference existing projects."""
        project_ids = {p["project_id"] for p in DEMO_PROJECTS}
        for work in DEMO_WORK_ITEMS:
            assert work["project_id"] in project_ids, f"Work item {work['work_id']} references unknown project"

    def test_work_items_reference_valid_compute(self):
        """Assigned work items reference existing compute instances."""
        compute_ids = {c["instance_id"] for c in DEMO_COMPUTE_INSTANCES}
        for work in DEMO_WORK_ITEMS:
            if work.get("assigned_to"):
                assert work["assigned_to"] in compute_ids, f"Work item {work['work_id']} assigned to unknown compute"

    def test_issues_reference_valid_compute(self):
        """Assigned issues reference existing compute instances."""
        compute_ids = {c["instance_id"] for c in DEMO_COMPUTE_INSTANCES}
        for issue in DEMO_ISSUES:
            if issue.get("assigned_compute_id"):
                assert issue["assigned_compute_id"] in compute_ids, f"Issue {issue['issue_id']} assigned to unknown compute"


# =============================================================================
# Test: Demo Data Variety
# =============================================================================

class TestDemoDataVariety:
    """Test that demo data provides good variety for testing."""

    def test_multiple_projects(self):
        """There are multiple projects."""
        assert len(DEMO_PROJECTS) >= 3

    def test_multiple_goal_statuses(self):
        """Goals cover multiple statuses."""
        statuses = {g["status"] for g in DEMO_GOALS}
        assert "planning" in statuses
        assert "in_progress" in statuses
        assert "done" in statuses

    def test_multiple_issue_statuses(self):
        """Issues cover multiple statuses."""
        statuses = {i["status"] for i in DEMO_ISSUES}
        assert len(statuses) >= 4  # At least 4 different statuses

    def test_multiple_issue_types(self):
        """Issues cover multiple types."""
        types = {i.get("issue_type") for i in DEMO_ISSUES}
        assert "feature" in types
        assert "bug" in types

    def test_multiple_compute_statuses(self):
        """Compute instances cover multiple statuses."""
        statuses = {c["status"] for c in DEMO_COMPUTE_INSTANCES}
        assert "online" in statuses
        assert "offline" in statuses or "degraded" in statuses

    def test_compute_with_special_access(self):
        """Some compute instances have special access labels."""
        has_special = any(
            "production-access" in c.get("capabilities", {}).get("labels", [])
            for c in DEMO_COMPUTE_INSTANCES
        )
        assert has_special, "Should have compute with production access"
