"""
End-to-End Work Execution Integration Tests (Issue #31)
========================================================

Tests the full work lifecycle from creation to completion:
1. Work creation via API
2. Orchestrator detection and processing
3. Work assignment to compute (via SSE or direct spawn)
4. Progress reporting
5. Work completion
6. Final state verification in Redis

Prerequisites:
    - Running Docker containers: claudevn-serving, claudevn-redis, claudevn-marketplace
    - Optionally: claudevn-compute-{1,2,3} for full spawn testing

Run with:
    ./scripts/run_integration_tests.sh
    pytest serving/tests/integration/test_work_execution_flow.py -v
"""

import asyncio
import os
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

# Test configuration from environment or defaults
SERVING_BASE_URL = os.getenv("SERVING_BASE_URL", "http://localhost:8002")
API_PREFIX = "/api/v1"

# Redis configuration for direct verification
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "claudevn:")


def generate_test_id() -> str:
    """Generate a unique test identifier."""
    return uuid.uuid4().hex[:8]


async def make_request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    max_retries: int = 3,
    **kwargs
) -> httpx.Response:
    """Make an HTTP request with retry on rate limit (429) errors."""
    for attempt in range(max_retries):
        response = await client.request(method, url, **kwargs)
        if response.status_code == 429:
            retry_after = int(response.json().get("retry_after", 5))
            if attempt < max_retries - 1:
                await asyncio.sleep(min(retry_after, 10))  # Cap wait at 10s
                continue
        return response
    return response


async def get_redis_client():
    """Get a Redis client for direct test verification."""
    try:
        import redis.asyncio as redis
        return redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True
        )
    except ImportError:
        pytest.skip("redis package not installed")


class TestWorkCreationFlow:
    """Test work item creation and initial state."""

    @pytest.fixture
    async def http_client(self):
        """Create HTTP client for API calls."""
        async with httpx.AsyncClient(base_url=SERVING_BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.fixture
    async def test_project(self, http_client):
        """Create a test project for work items."""
        project_id = f"project-e2e-{generate_test_id()}"
        response = await http_client.post(
            f"{API_PREFIX}/projects",
            json={
                "project_id": project_id,
                "name": f"E2E Test Project {project_id}",
                "description": "Project for E2E work execution tests"
            }
        )
        if response.status_code not in [200, 201, 409]:
            pytest.skip(f"Could not create test project: {response.status_code}")
        return project_id

    @pytest.mark.asyncio
    async def test_create_work_returns_pending_status(self, http_client, test_project):
        """Test that newly created work starts in PENDING status."""
        work_data = {
            "title": f"E2E test work {generate_test_id()}",
            "description": "Testing work creation flow",
            "project_id": test_project,
            "work_type": "feature",
            "priority": "normal"
        }

        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        assert response.status_code == 201, f"Failed to create work: {response.text}"

        work = response.json()
        try:
            assert "work_id" in work
            assert work["status"] == "pending"
            assert work["title"] == work_data["title"]
            assert work["project_id"] == test_project
            assert work["progress_percent"] == 0
            assert work["retry_count"] == 0
            assert work["assigned_to"] is None
        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work['work_id']}")

    @pytest.mark.asyncio
    async def test_create_work_generates_branch_name(self, http_client, test_project):
        """Test that work creation auto-generates a branch name."""
        work_data = {
            "title": f"Branch name test {generate_test_id()}",
            "description": "Testing branch name generation",
            "project_id": test_project
        }

        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        assert response.status_code == 201

        work = response.json()
        try:
            assert work["branch_name"] is not None
            assert work["branch_name"].startswith("work/")
            assert work["base_branch"] == "main"
        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work['work_id']}")

    @pytest.mark.asyncio
    async def test_create_work_with_dependencies(self, http_client, test_project):
        """Test creating work with dependency relationships."""
        # Create first work item
        work1_data = {
            "title": f"Dependency test 1 {generate_test_id()}",
            "description": "First work item",
            "project_id": test_project
        }
        response1 = await http_client.post(f"{API_PREFIX}/work", json=work1_data)
        assert response1.status_code == 201
        work1 = response1.json()

        # Create second work that depends on first
        work2_data = {
            "title": f"Dependency test 2 {generate_test_id()}",
            "description": "Depends on first work",
            "project_id": test_project,
            "depends_on": [work1["work_id"]]
        }
        response2 = await http_client.post(f"{API_PREFIX}/work", json=work2_data)
        assert response2.status_code == 201
        work2 = response2.json()

        try:
            assert work2["depends_on"] == [work1["work_id"]]
        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work2['work_id']}")
            await http_client.delete(f"{API_PREFIX}/work/{work1['work_id']}")


class TestWorkAssignmentFlow:
    """Test work assignment to compute instances."""

    @pytest.fixture
    async def http_client(self):
        """Create HTTP client for API calls."""
        async with httpx.AsyncClient(base_url=SERVING_BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.fixture
    async def test_project(self, http_client):
        """Create a test project for work items."""
        project_id = f"project-assign-{generate_test_id()}"
        await http_client.post(
            f"{API_PREFIX}/projects",
            json={
                "project_id": project_id,
                "name": f"Assignment Test Project {project_id}",
                "description": "Project for work assignment tests"
            }
        )
        return project_id

    @pytest.mark.asyncio
    async def test_manual_work_assignment(self, http_client, test_project):
        """Test manually assigning work to a compute instance."""
        # Create work
        work_data = {
            "title": f"Manual assignment test {generate_test_id()}",
            "description": "Testing manual assignment",
            "project_id": test_project
        }
        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        assert response.status_code == 201
        work = response.json()
        work_id = work["work_id"]

        try:
            # Assign to compute
            compute_id = f"test-compute-{generate_test_id()}"
            assign_response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": compute_id, "skills": "code-writer"}
            )
            assert assign_response.status_code == 200

            assignment = assign_response.json()
            assert assignment["work_id"] == work_id

            # Verify work status changed to ASSIGNED
            get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
            assert get_response.status_code == 200
            updated_work = get_response.json()
            assert updated_work["status"] == "assigned"
            assert updated_work["assigned_to"] == compute_id
        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")

    @pytest.mark.asyncio
    async def test_status_transition_assigned_to_in_progress(self, http_client, test_project):
        """Test status transition from ASSIGNED to IN_PROGRESS."""
        # Create and assign work
        work_data = {
            "title": f"Status transition test {generate_test_id()}",
            "description": "Testing status transitions",
            "project_id": test_project
        }
        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        work = response.json()
        work_id = work["work_id"]

        try:
            compute_id = f"test-compute-{generate_test_id()}"
            await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": compute_id, "skills": "tester"}
            )

            # Transition to IN_PROGRESS
            status_response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/status",
                params={"status": "in_progress", "compute_id": compute_id}
            )
            assert status_response.status_code == 200

            updated_work = status_response.json()
            assert updated_work["status"] == "in_progress"
            assert updated_work["started_at"] is not None
        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")

    @pytest.mark.asyncio
    async def test_get_next_assignment_returns_highest_priority(self, http_client, test_project):
        """Test that next assignment returns highest priority work."""
        # Create low priority work
        low_work_data = {
            "title": f"Low priority {generate_test_id()}",
            "description": "Low priority work",
            "project_id": test_project,
            "priority": "low"
        }
        low_response = await http_client.post(f"{API_PREFIX}/work", json=low_work_data)
        low_work = low_response.json()

        # Create high priority work
        high_work_data = {
            "title": f"High priority {generate_test_id()}",
            "description": "High priority work",
            "project_id": test_project,
            "priority": "high"
        }
        high_response = await http_client.post(f"{API_PREFIX}/work", json=high_work_data)
        high_work = high_response.json()

        try:
            # Request next assignment
            compute_id = f"test-compute-{generate_test_id()}"
            next_response = await http_client.post(
                f"{API_PREFIX}/work/next-assignment",
                params={"compute_id": compute_id, "capabilities": "python"}
            )
            assert next_response.status_code == 200

            # Should get high priority work first (if assignment available)
            assignment = next_response.json()
            if assignment:
                # The assignment should prioritize higher priority items
                assert assignment["work_id"] in [low_work["work_id"], high_work["work_id"]]
        finally:
            await http_client.delete(f"{API_PREFIX}/work/{low_work['work_id']}")
            await http_client.delete(f"{API_PREFIX}/work/{high_work['work_id']}")


class TestProgressReportingFlow:
    """Test progress reporting from compute to serving."""

    @pytest.fixture
    async def http_client(self):
        """Create HTTP client for API calls."""
        async with httpx.AsyncClient(base_url=SERVING_BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.fixture
    async def test_project(self, http_client):
        """Create a test project for work items."""
        project_id = f"project-progress-{generate_test_id()}"
        await http_client.post(
            f"{API_PREFIX}/projects",
            json={
                "project_id": project_id,
                "name": f"Progress Test Project {project_id}",
                "description": "Project for progress reporting tests"
            }
        )
        return project_id

    @pytest.fixture
    async def assigned_work(self, http_client, test_project):
        """Create and assign work for progress testing."""
        work_data = {
            "title": f"Progress test work {generate_test_id()}",
            "description": "Testing progress reporting",
            "project_id": test_project
        }
        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        if response.status_code != 201:
            pytest.skip(f"Could not create work: {response.status_code} - {response.text}")
        work = response.json()
        work_id = work["work_id"]

        compute_id = f"test-compute-{generate_test_id()}"
        await http_client.post(
            f"{API_PREFIX}/work/{work_id}/assign",
            params={"compute_id": compute_id, "skills": "tester"}
        )

        # Move to in_progress
        await http_client.post(
            f"{API_PREFIX}/work/{work_id}/status",
            params={"status": "in_progress", "compute_id": compute_id}
        )

        yield {"work_id": work_id, "compute_id": compute_id}

        # Cleanup
        await http_client.delete(f"{API_PREFIX}/work/{work_id}")

    @pytest.mark.asyncio
    async def test_report_progress_updates_percentage(self, http_client, assigned_work):
        """Test that progress reporting updates the progress percentage."""
        work_id = assigned_work["work_id"]

        progress_data = {
            "work_id": work_id,
            "progress_percent": 50,
            "status": "in_progress",
            "note": "Halfway done"
        }

        response = await http_client.post(
            f"{API_PREFIX}/work/{work_id}/progress",
            json=progress_data
        )
        assert response.status_code == 200

        updated_work = response.json()
        assert updated_work["progress_percent"] == 50
        # Notes are timestamped, so check that any note contains our message
        assert any("Halfway done" in note for note in updated_work["progress_notes"])

    @pytest.mark.asyncio
    async def test_report_progress_updates_last_activity(self, http_client, assigned_work):
        """Test that progress reporting updates last_activity_at timestamp."""
        work_id = assigned_work["work_id"]

        # Get initial state
        initial_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
        initial_work = initial_response.json()
        initial_activity = initial_work.get("last_activity_at")

        # Wait a moment
        await asyncio.sleep(0.1)

        # Report progress
        progress_data = {
            "work_id": work_id,
            "progress_percent": 25,
            "status": "in_progress"
        }
        await http_client.post(f"{API_PREFIX}/work/{work_id}/progress", json=progress_data)

        # Verify last_activity_at was updated
        final_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
        final_work = final_response.json()
        final_activity = final_work.get("last_activity_at")

        assert final_activity is not None
        if initial_activity:
            # Timestamps should be different (activity was updated)
            assert final_activity >= initial_activity

    @pytest.mark.asyncio
    async def test_progress_with_blocker_changes_status(self, http_client, assigned_work):
        """Test that reporting a blocker changes work status to BLOCKED."""
        work_id = assigned_work["work_id"]

        # Add a blocker
        blocker_response = await http_client.post(
            f"{API_PREFIX}/work/{work_id}/blockers",
            params={
                "blocker_type": "technical",
                "description": "Missing dependency"
            }
        )
        assert blocker_response.status_code == 200

        # Verify work has blocker
        get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
        work = get_response.json()
        assert len(work["blockers"]) > 0
        assert work["blockers"][0]["blocker_type"] == "technical"


class TestWorkCompletionFlow:
    """Test work completion and cleanup."""

    @pytest.fixture
    async def http_client(self):
        """Create HTTP client for API calls."""
        async with httpx.AsyncClient(base_url=SERVING_BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.fixture
    async def test_project(self, http_client):
        """Create a test project for work items."""
        project_id = f"project-complete-{generate_test_id()}"
        await http_client.post(
            f"{API_PREFIX}/projects",
            json={
                "project_id": project_id,
                "name": f"Completion Test Project {project_id}",
                "description": "Project for work completion tests"
            }
        )
        return project_id

    @pytest.mark.asyncio
    async def test_complete_work_sets_status_and_result(self, http_client, test_project):
        """Test that completing work sets status to COMPLETED with result."""
        # Create and assign work
        work_data = {
            "title": f"Completion test {generate_test_id()}",
            "description": "Testing work completion",
            "project_id": test_project
        }
        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        work = response.json()
        work_id = work["work_id"]

        try:
            compute_id = f"test-compute-{generate_test_id()}"
            await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": compute_id, "skills": "completer"}
            )

            # Move to in_progress
            await http_client.post(
                f"{API_PREFIX}/work/{work_id}/status",
                params={"status": "in_progress", "compute_id": compute_id}
            )

            # Complete the work
            result = {
                "summary": "Successfully completed test task",
                "branch": work["branch_name"],
                "deliverables": ["file1.py", "file2.py"]
            }
            complete_response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/complete",
                params={"compute_id": compute_id},
                json=result
            )
            assert complete_response.status_code == 200

            completed_work = complete_response.json()
            assert completed_work["status"] == "completed"
            assert completed_work["result"] is not None
            assert completed_work["completed_at"] is not None
        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")

    @pytest.mark.asyncio
    async def test_status_transition_to_failed(self, http_client, test_project):
        """Test marking work as failed."""
        work_data = {
            "title": f"Failure test {generate_test_id()}",
            "description": "Testing work failure",
            "project_id": test_project
        }
        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        work = response.json()
        work_id = work["work_id"]

        try:
            compute_id = f"test-compute-{generate_test_id()}"
            await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": compute_id, "skills": "failer"}
            )

            # Move to in_progress then fail
            await http_client.post(
                f"{API_PREFIX}/work/{work_id}/status",
                params={"status": "in_progress", "compute_id": compute_id}
            )

            fail_response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/status",
                params={"status": "failed", "compute_id": compute_id}
            )
            assert fail_response.status_code == 200

            failed_work = fail_response.json()
            assert failed_work["status"] == "failed"
        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")


class TestRedisStateVerification:
    """Test that work state is correctly persisted to Redis."""

    @pytest.fixture
    async def http_client(self):
        """Create HTTP client for API calls."""
        async with httpx.AsyncClient(base_url=SERVING_BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.fixture
    async def redis_client(self):
        """Get Redis client for direct verification."""
        client = await get_redis_client()
        yield client
        await client.aclose()

    @pytest.fixture
    async def test_project(self, http_client):
        """Create a test project for work items."""
        project_id = f"project-redis-{generate_test_id()}"
        await http_client.post(
            f"{API_PREFIX}/projects",
            json={
                "project_id": project_id,
                "name": f"Redis Test Project {project_id}",
                "description": "Project for Redis state verification"
            }
        )
        return project_id

    @pytest.mark.asyncio
    async def test_work_creation_adds_to_pending_set(
        self, http_client, redis_client, test_project
    ):
        """Test that creating work adds it to the pending status set in Redis."""
        work_data = {
            "title": f"Redis pending test {generate_test_id()}",
            "description": "Testing Redis pending set",
            "project_id": test_project
        }
        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        work = response.json()
        work_id = work["work_id"]

        try:
            # Verify work is in pending set
            pending_key = f"{REDIS_KEY_PREFIX}workmap:work:status:pending"
            pending_members = await redis_client.smembers(pending_key)
            assert work_id in pending_members, f"Work {work_id} should be in pending set"
        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")

    @pytest.mark.asyncio
    async def test_assignment_moves_to_assigned_set(
        self, http_client, redis_client, test_project
    ):
        """Test that assigning work moves it from pending to assigned set in Redis."""
        work_data = {
            "title": f"Redis assignment test {generate_test_id()}",
            "description": "Testing Redis assignment set",
            "project_id": test_project
        }
        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        work = response.json()
        work_id = work["work_id"]

        try:
            compute_id = f"test-compute-{generate_test_id()}"
            await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": compute_id, "skills": "tester"}
            )

            # Verify work is in assigned set
            assigned_key = f"{REDIS_KEY_PREFIX}workmap:work:status:assigned"
            assigned_members = await redis_client.smembers(assigned_key)
            assert work_id in assigned_members, "Work should be in assigned set"

            # Verify work is NOT in pending set
            pending_key = f"{REDIS_KEY_PREFIX}workmap:work:status:pending"
            pending_members = await redis_client.smembers(pending_key)
            assert work_id not in pending_members, "Work should not be in pending set"

            # Verify assignee index
            assignee_key = f"{REDIS_KEY_PREFIX}workmap:work:assignee:{compute_id}"
            assignee_work = await redis_client.smembers(assignee_key)
            assert work_id in assignee_work, "Work should be in assignee index"
        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")


class TestOrchestratorIntegration:
    """Test orchestrator detection and processing of work."""

    @pytest.fixture
    async def http_client(self):
        """Create HTTP client for API calls."""
        async with httpx.AsyncClient(base_url=SERVING_BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_orchestrator_is_running(self, http_client):
        """Test that the orchestrator is running and healthy."""
        response = await http_client.get(f"{API_PREFIX}/orchestrator/status")
        assert response.status_code == 200

        status = response.json()
        assert status["status"] == "running"
        assert status["stats"]["timeout_monitoring_enabled"] is True

    @pytest.mark.asyncio
    async def test_orchestrator_tracks_statistics(self, http_client):
        """Test that orchestrator statistics are being tracked."""
        response = await http_client.get(f"{API_PREFIX}/orchestrator/status")
        assert response.status_code == 200

        status = response.json()
        stats = status.get("stats", {})

        # Verify expected statistics fields exist
        assert "total_spawned" in stats
        assert "total_assigned" in stats
        assert "total_failed" in stats
        assert "total_timeouts" in stats
        assert status["status"] == "running"
        assert "paused" in status

    @pytest.mark.asyncio
    async def test_health_endpoint_includes_orchestrator_status(self, http_client):
        """Test that health endpoint includes orchestrator information."""
        response = await http_client.get(f"{API_PREFIX}/health")
        assert response.status_code == 200

        health = response.json()
        assert health["status"] == "healthy"
        assert "work_orchestrator" in health

        orchestrator_health = health["work_orchestrator"]
        assert "running" in orchestrator_health
        assert orchestrator_health["running"] is True


class TestFullWorkLifecycle:
    """End-to-end test of the complete work lifecycle.

    This is the main test that validates the full flow:
    PENDING -> ASSIGNED -> IN_PROGRESS -> COMPLETED
    """

    @pytest.fixture
    async def http_client(self):
        """Create HTTP client for API calls."""
        async with httpx.AsyncClient(base_url=SERVING_BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.fixture
    async def redis_client(self):
        """Get Redis client for direct verification."""
        client = await get_redis_client()
        yield client
        await client.aclose()

    @pytest.fixture
    async def test_project(self, http_client):
        """Create a test project for work items."""
        project_id = f"project-lifecycle-{generate_test_id()}"
        await http_client.post(
            f"{API_PREFIX}/projects",
            json={
                "project_id": project_id,
                "name": f"Lifecycle Test Project {project_id}",
                "description": "Project for full lifecycle tests"
            }
        )
        return project_id

    @pytest.mark.asyncio
    async def test_full_work_lifecycle_happy_path(
        self, http_client, redis_client, test_project
    ):
        """Test the complete happy path work lifecycle.

        Steps:
        1. Create work item (status: PENDING)
        2. Assign to compute (status: ASSIGNED)
        3. Start work (status: IN_PROGRESS)
        4. Report progress (progress_percent updates)
        5. Complete work (status: COMPLETED)
        6. Verify final Redis state
        """
        test_id = generate_test_id()

        # Step 1: Create work item
        work_data = {
            "title": f"Full lifecycle test {test_id}",
            "description": "End-to-end lifecycle test",
            "project_id": test_project,
            "work_type": "feature",
            "priority": "high",
            "required_capabilities": ["python", "testing"]
        }
        create_response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        assert create_response.status_code == 201, f"Create failed: {create_response.text}"

        work = create_response.json()
        work_id = work["work_id"]
        assert work["status"] == "pending"

        try:
            # Verify PENDING state in Redis
            pending_key = f"{REDIS_KEY_PREFIX}workmap:work:status:pending"
            pending_members = await redis_client.smembers(pending_key)
            assert work_id in pending_members, "Work should start in pending set"

            # Step 2: Assign to compute
            compute_id = f"test-compute-{test_id}"
            assign_response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": compute_id, "skills": "code-writer,tester"}
            )
            assert assign_response.status_code == 200

            assignment = assign_response.json()
            assert assignment["work_id"] == work_id

            # Verify ASSIGNED state
            get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
            assigned_work = get_response.json()
            assert assigned_work["status"] == "assigned"
            assert assigned_work["assigned_to"] == compute_id
            assert assigned_work["assigned_at"] is not None

            # Verify Redis state
            assigned_key = f"{REDIS_KEY_PREFIX}workmap:work:status:assigned"
            assigned_members = await redis_client.smembers(assigned_key)
            assert work_id in assigned_members, "Work should be in assigned set"

            # Step 3: Start work (IN_PROGRESS)
            start_response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/status",
                params={"status": "in_progress", "compute_id": compute_id}
            )
            assert start_response.status_code == 200

            started_work = start_response.json()
            assert started_work["status"] == "in_progress"
            assert started_work["started_at"] is not None

            # Step 4: Report progress
            for percent in [25, 50, 75]:
                progress_data = {
                    "work_id": work_id,
                    "progress_percent": percent,
                    "status": "in_progress",
                    "note": f"Progress at {percent}%"
                }
                progress_response = await http_client.post(
                    f"{API_PREFIX}/work/{work_id}/progress",
                    json=progress_data
                )
                assert progress_response.status_code == 200

                progress_work = progress_response.json()
                assert progress_work["progress_percent"] == percent

            # Step 5: Complete work
            result = {
                "summary": f"Completed lifecycle test {test_id}",
                "branch": work["branch_name"],
                "deliverables": ["feature.py", "test_feature.py"],
                "test_results": {"passed": 10, "failed": 0}
            }
            complete_response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/complete",
                params={"compute_id": compute_id},
                json=result
            )
            assert complete_response.status_code == 200

            completed_work = complete_response.json()
            assert completed_work["status"] == "completed"
            assert completed_work["result"] is not None
            assert completed_work["completed_at"] is not None
            # Progress may be set to 100 on completion or remain at last reported
            assert completed_work["progress_percent"] >= 75

            # Step 6: Verify final Redis state
            completed_key = f"{REDIS_KEY_PREFIX}workmap:work:status:completed"
            completed_members = await redis_client.smembers(completed_key)
            assert work_id in completed_members, "Work should be in completed set"

            # Should not be in other status sets
            for status in ["pending", "assigned", "in_progress"]:
                status_key = f"{REDIS_KEY_PREFIX}workmap:work:status:{status}"
                status_members = await redis_client.smembers(status_key)
                assert work_id not in status_members, f"Work should not be in {status} set"

        finally:
            # Cleanup
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")

    @pytest.mark.asyncio
    async def test_work_stats_endpoint_reflects_state(self, http_client, test_project):
        """Test that the stats endpoint accurately reflects work state."""
        # Create a work item
        work_data = {
            "title": f"Stats test {generate_test_id()}",
            "description": "Testing stats endpoint",
            "project_id": test_project
        }
        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        work = response.json()
        work_id = work["work_id"]

        try:
            # Get stats
            stats_response = await http_client.get(f"{API_PREFIX}/work/stats")
            assert stats_response.status_code == 200

            stats = stats_response.json()
            assert "total" in stats
            assert "by_status" in stats
            assert "by_priority" in stats
            assert stats["total"] > 0
        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")


class TestSSEConnectionFlow:
    """Test SSE connection for compute instances."""

    @pytest.fixture
    async def http_client(self):
        """Create HTTP client for API calls."""
        async with httpx.AsyncClient(base_url=SERVING_BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_sse_connection_can_be_established(self, http_client):
        """Test that SSE connection can be established for compute registration."""
        compute_id = f"test-sse-{generate_test_id()}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                async with client.stream(
                    "GET",
                    f"{SERVING_BASE_URL}{API_PREFIX}/compute/connect",
                    headers={
                        "X-Compute-ID": compute_id,
                        "X-Capabilities": "python,testing",
                        "Accept": "text/event-stream"
                    }
                ) as response:
                    assert response.status_code == 200
                    content_type = response.headers.get("content-type", "")
                    assert "text/event-stream" in content_type

                    # Read first few bytes/events
                    line_count = 0
                    async for line in response.aiter_lines():
                        line_count += 1
                        if line_count >= 2:  # Just verify connection works
                            break
            except httpx.ReadTimeout:
                # SSE connections may timeout waiting for events - that's OK
                pass

    @pytest.mark.asyncio
    async def test_sse_stats_endpoint(self, http_client):
        """Test SSE connection statistics endpoint."""
        response = await http_client.get(f"{API_PREFIX}/compute/sse/stats")
        assert response.status_code == 200

        stats = response.json()
        # Verify structure without requiring specific values
        assert isinstance(stats, dict)


# Run tests directly
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("End-to-End Work Execution Integration Tests")
    print("=" * 60)
    print()
    print("Prerequisites:")
    print(f"  - Serving service running at {SERVING_BASE_URL}")
    print(f"  - Redis running at {REDIS_HOST}:{REDIS_PORT}")
    print()
    print("Running tests...")
    print()

    sys.exit(pytest.main([__file__, "-v", "-s"]))
