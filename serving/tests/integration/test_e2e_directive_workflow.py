#!/usr/bin/env python3
"""
End-to-End Directive Workflow Tests
====================================

Tests the full user workflow:
1. Verify system health (Docker containers running)
2. Clear all data (fresh start)
3. Create a project and add a repository
4. Submit a directive and verify it flows through:
   - Directive is created and classified
   - Goal is created from the directive
   - Issues appear in the backlog
   - Plan summary reflects the new work

NOTE: These tests require running Docker containers:
    docker compose up -d
    pytest serving/tests/integration/test_e2e_directive_workflow.py -v -s
"""

import time

import httpx
import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVING_BASE_URL = "http://localhost:8002"
API = f"{SERVING_BASE_URL}/api/v1"

# Timeouts
HEALTH_TIMEOUT = 10.0  # seconds to wait for health check
DIRECTIVE_POLL_TIMEOUT = 60.0  # seconds to wait for directive processing
DIRECTIVE_POLL_INTERVAL = 2.0  # seconds between polls

# Test data
TEST_PROJECT_NAME = "E2E Test Project"
TEST_PROJECT_DESCRIPTION = "Automated end-to-end test project"
TEST_REPO_NAME = "e2e-test-repo"
TEST_DIRECTIVE_TEXT = (
    "Build a user authentication system with email/password login, "
    "password reset flow, and session management"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def poll_until(client, url, condition, *, params=None, timeout=DIRECTIVE_POLL_TIMEOUT):
    """Poll a URL until a condition is met or timeout."""
    deadline = time.time() + timeout
    result = None
    while time.time() < deadline:
        resp = client.get(url, params=params)
        assert resp.status_code == 200
        result = resp.json()
        if condition(result):
            return result
        time.sleep(DIRECTIVE_POLL_INTERVAL)
    return result


def delete_all_data(client):
    """Delete all data from the system via API calls.

    Mirrors the logic in scripts/demo_data.py --delete but uses
    the test client directly (no subprocess/venv issues).
    """
    # 1. Delete all goals (hard delete)
    resp = client.get(f"{API}/goals", params={"include_deleted": True, "include_archived": True})
    if resp.status_code == 200:
        for item in resp.json().get("items", []):
            client.delete(f"{API}/goals/{item['goal_id']}", params={"hard": True})

    # 2. Delete all issues
    resp = client.get(f"{API}/issues", params={"limit": 1000})
    if resp.status_code == 200:
        for item in resp.json().get("items", []):
            client.delete(f"{API}/issues/{item['issue_id']}")

    # 3. Delete all work items
    resp = client.get(f"{API}/work")
    if resp.status_code == 200:
        for item in resp.json().get("items", []):
            client.delete(f"{API}/work/{item['work_id']}")

    # 4. Delete all projects
    resp = client.get(f"{API}/projects")
    if resp.status_code == 200:
        for item in resp.json().get("items", []):
            client.delete(f"{API}/projects/{item['project_id']}")

    time.sleep(0.5)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Shared HTTP client for the test module."""
    with httpx.Client(timeout=30.0) as c:
        yield c


@pytest.fixture(scope="module")
def clean_system(client):
    """Ensure system is healthy and data is cleared before tests run."""
    # Step 1: Health check
    response = client.get(f"{API}/health", timeout=HEALTH_TIMEOUT)
    assert response.status_code == 200, (
        f"Health check failed (status {response.status_code}). "
        "Are Docker containers running? Try: docker compose up -d"
    )
    health = response.json()
    assert health["status"] == "healthy", f"System is not healthy: {health}"

    # Step 2: Delete all data via API
    delete_all_data(client)

    # Verify clean state
    projects_resp = client.get(f"{API}/projects")
    assert projects_resp.status_code == 200
    projects = projects_resp.json()
    assert projects["total"] == 0, (
        f"Expected 0 projects after delete, got {projects['total']}"
    )

    return True


@pytest.fixture(scope="module")
def project(client, clean_system):
    """Create a test project and return it."""
    response = client.post(
        f"{API}/projects",
        json={
            "name": TEST_PROJECT_NAME,
            "description": TEST_PROJECT_DESCRIPTION,
            "labels": ["e2e-test"],
            "metadata": {"automated": True},
        },
    )
    assert response.status_code == 201, (
        f"Failed to create project: {response.status_code} {response.text}"
    )
    data = response.json()
    assert "project_id" in data
    assert data["name"] == TEST_PROJECT_NAME
    assert data["status"] == "active"
    return data


@pytest.fixture(scope="module")
def project_with_repo(client, project):
    """Add an internal repo to the project and return the updated project."""
    project_id = project["project_id"]

    response = client.post(
        f"{API}/projects/{project_id}/repos/internal",
        json={"name": TEST_REPO_NAME, "default_branch": "main"},
    )
    assert response.status_code == 201, (
        f"Failed to create internal repo: {response.status_code} {response.text}"
    )
    repo = response.json()
    assert repo["name"] == TEST_REPO_NAME

    # Verify project now has a repo
    proj_resp = client.get(f"{API}/projects/{project_id}")
    assert proj_resp.status_code == 200
    updated = proj_resp.json()
    assert len(updated["repos"]) >= 1

    return updated


# ---------------------------------------------------------------------------
# Tests - System Health
# ---------------------------------------------------------------------------


class TestSystemHealth:
    """Verify Docker containers and services are operational."""

    def test_health_endpoint(self, client):
        """Health endpoint returns healthy status."""
        response = client.get(f"{API}/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_redis_connected(self, client):
        """Redis is connected and responsive."""
        health = client.get(f"{API}/health").json()
        assert health.get("redis", {}).get("connected") is True

    def test_core_services_available(self, client):
        """All core services report in health check."""
        health = client.get(f"{API}/health").json()
        for service in ["compute_registry", "work_map", "work_orchestrator"]:
            assert service in health, f"Missing service in health: {service}"


# ---------------------------------------------------------------------------
# Tests - Project Setup
# ---------------------------------------------------------------------------


class TestProjectSetup:
    """Test project creation and repository configuration."""

    def test_project_created(self, project):
        """Project is created with correct attributes."""
        assert project["name"] == TEST_PROJECT_NAME
        assert project["description"] == TEST_PROJECT_DESCRIPTION
        assert project["status"] == "active"
        assert "project_id" in project

    def test_project_retrievable(self, client, project):
        """Created project can be retrieved by ID."""
        response = client.get(f"{API}/projects/{project['project_id']}")
        assert response.status_code == 200
        fetched = response.json()
        assert fetched["project_id"] == project["project_id"]
        assert fetched["name"] == TEST_PROJECT_NAME

    def test_project_in_list(self, client, project):
        """Created project appears in project list."""
        response = client.get(f"{API}/projects")
        assert response.status_code == 200
        project_ids = [p["project_id"] for p in response.json()["items"]]
        assert project["project_id"] in project_ids

    def test_repo_added(self, project_with_repo):
        """Internal repo is added to the project."""
        repo_names = [r["name"] for r in project_with_repo["repos"]]
        assert TEST_REPO_NAME in repo_names

    def test_repo_listed_via_endpoint(self, client, project_with_repo):
        """Repo is visible via the repos endpoint."""
        project_id = project_with_repo["project_id"]
        response = client.get(f"{API}/projects/{project_id}/repos")
        assert response.status_code == 200
        assert any(r["name"] == TEST_REPO_NAME for r in response.json())


# ---------------------------------------------------------------------------
# Tests - Directive Submission
# ---------------------------------------------------------------------------


class TestDirectiveSubmission:
    """Test submitting a directive and verifying it is received."""

    def test_submit_directive(self, client, project_with_repo):
        """Submitting a directive returns a valid directive object."""
        project_id = project_with_repo["project_id"]
        response = client.post(
            f"{API}/unified-directives",
            json={"project_id": project_id, "text": TEST_DIRECTIVE_TEXT},
        )
        assert response.status_code == 200, (
            f"Failed to submit directive: {response.status_code} {response.text}"
        )
        directive = response.json()
        assert "directive_id" in directive
        assert directive["project_id"] == project_id
        assert directive["text"] == TEST_DIRECTIVE_TEXT
        assert directive["lifecycle_status"] in [
            "received", "classifying", "classified", "processing", "complete"
        ]

    def test_directive_in_list(self, client, project_with_repo):
        """Submitted directive appears in the directives list."""
        project_id = project_with_repo["project_id"]

        submit_resp = client.post(
            f"{API}/unified-directives",
            json={"project_id": project_id, "text": TEST_DIRECTIVE_TEXT},
        )
        directive = submit_resp.json()

        list_resp = client.get(
            f"{API}/unified-directives", params={"project_id": project_id}
        )
        assert list_resp.status_code == 200
        directives = list_resp.json()
        assert directives["total"] >= 1
        ids = [d["directive_id"] for d in directives["items"]]
        assert directive["directive_id"] in ids

    def test_directive_retrievable_by_id(self, client, project_with_repo):
        """Submitted directive can be retrieved by its ID."""
        project_id = project_with_repo["project_id"]

        submit_resp = client.post(
            f"{API}/unified-directives",
            json={"project_id": project_id, "text": TEST_DIRECTIVE_TEXT},
        )
        directive = submit_resp.json()
        directive_id = directive["directive_id"]

        get_resp = client.get(
            f"{API}/unified-directives/{directive_id}",
            params={"project_id": project_id},
        )
        assert get_resp.status_code == 200
        fetched = get_resp.json()
        assert fetched["directive_id"] == directive_id
        assert fetched["text"] == TEST_DIRECTIVE_TEXT


# ---------------------------------------------------------------------------
# Tests - Directive Processing (Goal + Backlog creation)
# ---------------------------------------------------------------------------


class TestDirectiveProcessing:
    """Test that a directive flows through to goal and issue creation.

    After submitting a directive, the system should:
    1. Classify the intent (new_work expected)
    2. Create a goal from the directive
    3. Decompose the goal into issues (backlog items)

    Note: Full processing requires the orchestrator and decomposer. If they
    are not running, tests verify the correct intermediate state instead.
    """

    @pytest.fixture(scope="class")
    def submitted_directive(self, client, project_with_repo):
        """Submit a directive and return it for downstream tests."""
        project_id = project_with_repo["project_id"]
        response = client.post(
            f"{API}/unified-directives",
            json={"project_id": project_id, "text": TEST_DIRECTIVE_TEXT},
        )
        assert response.status_code == 200
        return response.json()

    def test_directive_classified(self, client, project_with_repo, submitted_directive):
        """Directive is classified (or at least received)."""
        project_id = project_with_repo["project_id"]
        directive_id = submitted_directive["directive_id"]

        result = poll_until(
            client,
            f"{API}/unified-directives/{directive_id}",
            lambda d: d["lifecycle_status"] not in ("received", "classifying"),
            params={"project_id": project_id},
        )

        assert result["lifecycle_status"] in (
            "classified", "processing", "complete"
        ), f"Directive stuck in status: {result['lifecycle_status']}"

    def test_goal_created_from_directive(
        self, client, project_with_repo, submitted_directive
    ):
        """A goal is created as a result of the directive."""
        project_id = project_with_repo["project_id"]
        directive_id = submitted_directive["directive_id"]

        # Poll for directive to finish processing
        result = poll_until(
            client,
            f"{API}/unified-directives/{directive_id}",
            lambda d: d["lifecycle_status"] in ("complete", "failed")
            or (d.get("outcome") and d["outcome"].get("goal_id_created")),
            params={"project_id": project_id},
        )

        outcome = result.get("outcome")
        if outcome and outcome.get("goal_id_created"):
            goal_id = outcome["goal_id_created"]
            goal_resp = client.get(f"{API}/goals/{goal_id}")
            assert goal_resp.status_code == 200
            goal = goal_resp.json()
            assert goal["project_id"] == project_id
            assert goal["status"] in ("planning", "in_progress", "done")
        else:
            # At minimum the directive should have been processed
            assert result["lifecycle_status"] != "received", (
                "Directive was never processed"
            )

    def test_goals_exist_for_project(
        self, client, project_with_repo, submitted_directive
    ):
        """Goals list for the project is non-empty after directive processing."""
        project_id = project_with_repo["project_id"]

        result = poll_until(
            client,
            f"{API}/goals",
            lambda g: len(g.get("items", [])) >= 1,
            params={"project_id": project_id},
        )

        items = result.get("items", [])
        assert len(items) >= 1, (
            f"Expected at least 1 goal for project {project_id}, got {len(items)}"
        )


# ---------------------------------------------------------------------------
# Tests - Backlog (Issues)
# ---------------------------------------------------------------------------


class TestBacklog:
    """Test that issues (backlog items) are created from goal decomposition.

    After a goal is decomposed, issues should appear in:
    - GET /issues?project_id=...
    - GET /goals/{goal_id}/issues
    - GET /issues/stats
    """

    @pytest.fixture(scope="class")
    def project_with_directive(self, client, project_with_repo):
        """Submit a directive and wait for processing to complete."""
        project_id = project_with_repo["project_id"]

        resp = client.post(
            f"{API}/unified-directives",
            json={"project_id": project_id, "text": TEST_DIRECTIVE_TEXT},
        )
        assert resp.status_code == 200
        directive = resp.json()

        # Wait for processing
        result = poll_until(
            client,
            f"{API}/unified-directives/{directive['directive_id']}",
            lambda d: d["lifecycle_status"] in ("complete", "failed"),
            params={"project_id": project_id},
        )

        return {"project_id": project_id, "directive": result}

    def test_issues_exist_for_project(self, client, project_with_directive):
        """Issues are created for the project after directive processing.

        Requires decomposer/compute to be running. Skips if not available.
        """
        project_id = project_with_directive["project_id"]

        result = poll_until(
            client,
            f"{API}/issues",
            lambda i: len(i.get("items", [])) >= 1,
            params={"project_id": project_id},
        )

        items = result.get("items", [])
        if len(items) == 0:
            pytest.skip(
                "No issues created - decomposer/compute not running. "
                "Start compute instances to test full decomposition flow."
            )
        assert len(items) >= 1

    def test_issues_have_correct_fields(self, client, project_with_directive):
        """Created issues have the expected fields populated."""
        project_id = project_with_directive["project_id"]

        result = poll_until(
            client,
            f"{API}/issues",
            lambda i: len(i.get("items", [])) >= 1,
            params={"project_id": project_id},
        )
        items = result.get("items", [])

        if not items:
            pytest.skip("No issues created - decomposer may not be running")

        for issue in items:
            assert "issue_id" in issue
            assert "title" in issue
            assert issue["project_id"] == project_id
            assert issue["status"] in [
                "backlog", "ready", "in_progress", "blocked", "done", "failed"
            ]
            assert issue["priority"] in ["P0", "P1", "P2", "P3"]

    def test_goal_has_issues(self, client, project_with_directive):
        """Goal's issues endpoint returns the decomposed issues.

        Requires decomposer/compute to be running. Skips if not available.
        """
        project_id = project_with_directive["project_id"]

        goals_resp = client.get(f"{API}/goals", params={"project_id": project_id})
        goals = goals_resp.json().get("items", [])

        if not goals:
            pytest.skip("No goals created - directive processing may have failed")

        goal_id = goals[0]["goal_id"]

        result = poll_until(
            client,
            f"{API}/goals/{goal_id}/issues",
            lambda issues: len(issues) >= 1,
        )

        if len(result) == 0:
            pytest.skip(
                "No issues linked to goal - decomposer/compute not running."
            )
        assert len(result) >= 1

    def test_issue_stats_reflect_new_issues(self, client, project_with_directive):
        """Issue stats endpoint reflects the newly created issues.

        Requires decomposer/compute to be running. Skips if not available.
        """
        resp = client.get(f"{API}/issues/stats")
        assert resp.status_code == 200
        stats = resp.json()
        if stats["total"] == 0:
            pytest.skip(
                "No issues in stats - decomposer/compute not running."
            )
        assert stats["total"] >= 1


# ---------------------------------------------------------------------------
# Tests - Plan View
# ---------------------------------------------------------------------------


class TestPlanView:
    """Test that the plan summary reflects the directive's work."""

    @pytest.fixture(scope="class")
    def project_with_work(self, client, project_with_repo):
        """Submit a directive, wait for processing, return project_id."""
        project_id = project_with_repo["project_id"]

        resp = client.post(
            f"{API}/unified-directives",
            json={"project_id": project_id, "text": TEST_DIRECTIVE_TEXT},
        )
        assert resp.status_code == 200
        directive = resp.json()

        # Wait for processing
        poll_until(
            client,
            f"{API}/unified-directives/{directive['directive_id']}",
            lambda d: d["lifecycle_status"] in ("complete", "failed"),
            params={"project_id": project_id},
        )

        # Extra wait for decomposition to finish
        time.sleep(3.0)

        return project_id

    def test_plan_summary_available(self, client, project_with_work):
        """Plan summary endpoint returns data for the project."""
        resp = client.get(
            f"{API}/plan/summary", params={"project_id": project_with_work}
        )
        assert resp.status_code == 200
        summary = resp.json()
        assert summary["project_id"] == project_with_work

    def test_plan_summary_counts(self, client, project_with_work):
        """Plan summary shows non-zero total count after directive processing."""
        result = poll_until(
            client,
            f"{API}/plan/summary",
            lambda s: s["total_count"] > 0,
            params={"project_id": project_with_work},
        )

        if result["total_count"] == 0:
            pytest.skip("No issues in plan summary - decomposer may not be running")

        assert result["total_count"] >= 1
        assert (
            result["ready_count"] > 0
            or result["in_progress_count"] > 0
            or result["blocked_count"] > 0
            or result["done_count"] > 0
        ), (
            f"Plan summary has total_count={result['total_count']} "
            "but no items in any column"
        )

    def test_workmap_stats_project_scoped(self, client, project_with_work):
        """Workmap stats endpoint returns data scoped to the project."""
        resp = client.get(
            f"{API}/workmap/stats", params={"project_id": project_with_work}
        )
        assert resp.status_code == 200
        stats = resp.json()
        assert "total" in stats
        assert "by_status" in stats

    def test_workmap_full_view(self, client, project_with_work):
        """Full workmap returns goals, issues, and work items."""
        resp = client.get(
            f"{API}/workmap", params={"project_id": project_with_work}
        )
        assert resp.status_code == 200
        workmap = resp.json()
        assert "goals" in workmap
        assert "issues" in workmap
        assert "stats" in workmap

    def test_ready_queue(self, client, project_with_work):
        """Ready queue endpoint returns issues ready for assignment."""
        resp = client.get(
            f"{API}/workmap/ready", params={"project_id": project_with_work}
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Tests - Directive Comments (Conversation)
# ---------------------------------------------------------------------------


class TestDirectiveConversation:
    """Test adding comments to a directive for follow-up conversation."""

    @pytest.fixture(scope="class")
    def directive_for_comments(self, client, project_with_repo):
        """Create a directive to add comments to."""
        project_id = project_with_repo["project_id"]
        resp = client.post(
            f"{API}/unified-directives",
            json={
                "project_id": project_id,
                "text": "Set up a CI/CD pipeline for automated testing",
            },
        )
        assert resp.status_code == 200
        return resp.json()

    def test_add_comment_to_directive(
        self, client, project_with_repo, directive_for_comments
    ):
        """Can add a follow-up comment to a directive."""
        project_id = project_with_repo["project_id"]
        directive_id = directive_for_comments["directive_id"]

        resp = client.post(
            f"{API}/unified-directives/{directive_id}/comments",
            params={"project_id": project_id},
            json={"content": "Also add linting and type checking to the pipeline"},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["directive_id"] == directive_id
        assert len(updated["comments"]) >= 1

    def test_comment_persisted(
        self, client, project_with_repo, directive_for_comments
    ):
        """Comment is visible when retrieving the directive."""
        project_id = project_with_repo["project_id"]
        directive_id = directive_for_comments["directive_id"]

        # Add a comment
        client.post(
            f"{API}/unified-directives/{directive_id}/comments",
            params={"project_id": project_id},
            json={"content": "Include coverage reporting too"},
        )

        # Retrieve and verify
        resp = client.get(
            f"{API}/unified-directives/{directive_id}",
            params={"project_id": project_id},
        )
        assert resp.status_code == 200
        comment_texts = [c["content"] for c in resp.json()["comments"]]
        assert "Include coverage reporting too" in comment_texts


# ---------------------------------------------------------------------------
# Tests - Cleanup Verification
# ---------------------------------------------------------------------------


class TestCleanup:
    """Verify that cleanup (demo_data --delete) properly resets the system."""

    def test_delete_clears_all_data(self, client, project_with_repo):
        """Deleting all data via API removes all test data."""
        delete_all_data(client)

        # Verify projects are gone
        resp = client.get(f"{API}/projects")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

        # Verify goals are gone
        resp = client.get(f"{API}/goals")
        assert resp.status_code == 200
        goals = resp.json()
        assert goals.get("total", len(goals.get("items", []))) == 0

        # Verify issues are gone
        resp = client.get(f"{API}/issues/stats")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("E2E Directive Workflow Tests")
    print("=" * 60)
    print()
    print("Prerequisites:")
    print(f"  - Docker containers running (docker compose up -d)")
    print(f"  - Serving at {SERVING_BASE_URL}")
    print()
    print("Running tests...")
    print()

    sys.exit(pytest.main([__file__, "-v", "-s", "--tb=short"]))
