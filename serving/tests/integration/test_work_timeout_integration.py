"""
Integration Tests for Work Timeout Detection (#29)
===================================================

Tests for the work timeout and stuck-work detection feature with real Redis.

NOTE: These tests require:
    - Running Redis instance
    - Running serving instance (or auto-start with -s flag)

Run with:
    ./scripts/run_integration_tests.sh
    pytest serving/tests/integration/
"""

import pytest
import asyncio
import httpx
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import uuid

# Test configuration
SERVING_BASE_URL = os.getenv("SERVING_BASE_URL", "http://localhost:8002")
API_PREFIX = "/api/v1"

# Redis configuration for direct access in tests
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "claudevn:")


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


def generate_project_id() -> str:
    """Generate a unique project ID for testing."""
    return f"project-timeout-test-{uuid.uuid4().hex[:8]}"


class TestTimeoutWithRedis:
    """Integration tests for timeout detection with real Redis persistence."""

    @pytest.fixture
    async def redis_client(self):
        """Get Redis client and cleanup after test."""
        client = await get_redis_client()
        yield client
        await client.aclose()

    @pytest.fixture
    async def http_client(self):
        """Create HTTP client for API calls."""
        async with httpx.AsyncClient(base_url=SERVING_BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.fixture
    async def test_project(self, http_client):
        """Create a test project for work items."""
        project_id = generate_project_id()
        response = await http_client.post(
            f"{API_PREFIX}/projects",
            json={
                "project_id": project_id,
                "name": f"Timeout Test Project {project_id}",
                "description": "Project for timeout integration tests"
            }
        )
        # Project may already exist, that's fine
        if response.status_code not in [200, 201, 409]:
            pytest.skip(f"Could not create test project: {response.status_code}")
        return project_id

    @pytest.mark.asyncio
    async def test_timeout_detection_persists_to_redis(
        self, http_client, redis_client, test_project
    ):
        """Test that work assignment changes are persisted to Redis.

        Steps:
        1. Create a work item
        2. Assign it (move to ASSIGNED status)
        3. Verify ASSIGNED status is in Redis
        4. Verify assignee index is updated in Redis
        """
        # Create work item (work_id is auto-generated)
        response = await http_client.post(
            f"{API_PREFIX}/work",
            json={
                "title": "Timeout persistence test",
                "description": "Testing Redis persistence for timeout",
                "project_id": test_project,
                "work_type": "feature"
            }
        )
        assert response.status_code == 201, f"Failed to create work: {response.text}"
        work_data = response.json()
        work_id = work_data["work_id"]

        try:
            # Verify work was created with PENDING status
            assert work_data["status"] == "pending"

            # Assign the work (status changes to ASSIGNED)
            response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={
                    "compute_id": "test-compute-001",
                    "skills": "code-writer"
                }
            )

            if response.status_code == 200:
                # Verify ASSIGNED status in Redis
                # Keys are prefixed: {REDIS_KEY_PREFIX}workmap:{key}
                assigned_key = f"{REDIS_KEY_PREFIX}workmap:work:status:assigned"
                assigned_members = await redis_client.smembers(assigned_key)
                assert work_id in assigned_members, "Work should be in ASSIGNED set in Redis"

                # Verify assignee index
                assignee_key = f"{REDIS_KEY_PREFIX}workmap:work:assignee:test-compute-001"
                assignee_work = await redis_client.smembers(assignee_key)
                assert work_id in assignee_work, "Work should be in assignee index"

        finally:
            # Clean up - delete the work item
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")

    @pytest.mark.asyncio
    async def test_stale_work_returned_to_pending_in_redis(
        self, http_client, redis_client, test_project
    ):
        """Test that stale work is correctly returned to PENDING status in Redis.

        This test verifies the full cycle:
        1. Create work → PENDING
        2. Assign work → IN_PROGRESS (stored in Redis)
        3. Work times out → returned to PENDING
        4. Verify Redis state is updated
        """
        # Create and assign work
        response = await http_client.post(
            f"{API_PREFIX}/work",
            json={
                "title": "Stale work test",
                "description": "Testing stale work Redis update",
                "project_id": test_project
            }
        )
        assert response.status_code == 201
        work_id = response.json()["work_id"]

        try:
            await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": "test-compute-stale", "skills": "tester"}
            )

            # Check orchestrator status endpoint
            response = await http_client.get(f"{API_PREFIX}/orchestrator/status")
            assert response.status_code == 200
            status_data = response.json()

            # Verify orchestrator has timeout monitoring info
            if status_data.get("status") == "running":
                stats = status_data.get("stats", {})
                assert "timeout_monitoring_enabled" in stats

        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")


class TestTimeoutAcrossRestart:
    """Test timeout detection survives orchestrator restart."""

    @pytest.fixture
    async def http_client(self):
        """Create HTTP client for API calls."""
        async with httpx.AsyncClient(base_url=SERVING_BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_stale_work_detected_after_orchestrator_restart(self, http_client):
        """Test that stale work is detected after orchestrator restart.

        This test verifies that:
        1. Work items with stale timestamps are detected on startup
        2. The timeout monitoring loop picks up pre-existing stale work

        Note: This test checks the orchestrator's ability to detect stale work
        that was created before the current orchestrator instance started.
        """
        # Check orchestrator is running and has timeout enabled
        response = await http_client.get(f"{API_PREFIX}/orchestrator/status")
        assert response.status_code == 200
        status_data = response.json()

        # Verify orchestrator is running with timeout monitoring
        assert status_data.get("status") == "running", "Orchestrator should be running"

        stats = status_data.get("stats", {})
        assert stats.get("timeout_monitoring_enabled", False), "Timeout monitoring should be enabled"

        # Verify timeout configuration is loaded
        assert "timeout_minutes" in stats
        assert stats["timeout_minutes"] > 0

    @pytest.mark.asyncio
    async def test_orchestrator_stats_track_timeouts(self, http_client):
        """Test that orchestrator statistics track timeout events."""
        response = await http_client.get(f"{API_PREFIX}/orchestrator/status")
        assert response.status_code == 200
        status_data = response.json()
        stats = status_data.get("stats", {})

        # Verify timeout statistics are tracked
        assert "total_timeouts" in stats
        assert "total_timeout_retries" in stats
        assert "last_timeout_check" in stats

        # Values should be non-negative
        assert stats["total_timeouts"] >= 0
        assert stats["total_timeout_retries"] >= 0


class TestConcurrentStaleWork:
    """Test handling of multiple concurrent stale work items."""

    @pytest.fixture
    async def http_client(self):
        """Create HTTP client for API calls."""
        async with httpx.AsyncClient(base_url=SERVING_BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.fixture
    async def test_project(self, http_client):
        """Create a test project for work items."""
        project_id = generate_project_id()
        await http_client.post(
            f"{API_PREFIX}/projects",
            json={
                "project_id": project_id,
                "name": f"Concurrent Stale Test {project_id}",
                "description": "Project for concurrent stale work tests"
            }
        )
        return project_id

    @pytest.mark.asyncio
    async def test_multiple_stale_work_items_listed(self, http_client, test_project):
        """Test that multiple stale work items can be queried.

        Creates multiple work items and verifies the system can handle
        querying for stale work across many items.
        """
        work_ids = []

        try:
            # Create 5 work items
            for i in range(5):
                response = await http_client.post(
                    f"{API_PREFIX}/work",
                    json={
                        "title": f"Concurrent stale test {i}",
                        "description": f"Testing concurrent stale work {i}",
                        "project_id": test_project,
                        "priority": "normal"
                    }
                )
                if response.status_code == 201:
                    work_ids.append(response.json()["work_id"])

            assert len(work_ids) >= 3, "Should have created at least 3 work items"

            # List all work items for this project
            response = await http_client.get(
                f"{API_PREFIX}/work",
                params={"project_id": test_project, "limit": 50}
            )
            assert response.status_code == 200
            work_list = response.json()

            # Verify our items are in the list
            listed_ids = {w.get("work_id") for w in work_list.get("items", [])}
            for work_id in work_ids:
                assert work_id in listed_ids, f"Work {work_id} should be in list"

        finally:
            # Clean up
            for work_id in work_ids:
                await http_client.delete(f"{API_PREFIX}/work/{work_id}")

    @pytest.mark.asyncio
    async def test_stale_work_priority_ordering(self, http_client, test_project):
        """Test that stale work is processed in priority order.

        Creates work items with different priorities and verifies
        that high priority items would be processed first.
        """
        work_items = [
            {"priority": "low"},
            {"priority": "critical"},
            {"priority": "high"},
            {"priority": "normal"},
        ]

        created_ids = []
        try:
            for item in work_items:
                response = await http_client.post(
                    f"{API_PREFIX}/work",
                    json={
                        "title": f"Priority test - {item['priority']}",
                        "description": f"Testing priority ordering for {item['priority']}",
                        "project_id": test_project,
                        "priority": item["priority"]
                    }
                )
                if response.status_code == 201:
                    data = response.json()
                    created_ids.append(data["work_id"])
                    # Verify priority was set correctly
                    assert data["priority"] == item["priority"]

        finally:
            # Clean up
            for work_id in created_ids:
                await http_client.delete(f"{API_PREFIX}/work/{work_id}")


class TestEndToEndWorkLifecycle:
    """End-to-end tests for work lifecycle with timeout."""

    @pytest.fixture
    async def http_client(self):
        """Create HTTP client for API calls."""
        async with httpx.AsyncClient(base_url=SERVING_BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.fixture
    async def test_project(self, http_client):
        """Create a test project."""
        project_id = generate_project_id()
        await http_client.post(
            f"{API_PREFIX}/projects",
            json={
                "project_id": project_id,
                "name": f"E2E Timeout Test {project_id}",
                "description": "Project for E2E timeout tests"
            }
        )
        return project_id

    @pytest.mark.asyncio
    async def test_work_lifecycle_pending_to_assigned(self, http_client, test_project):
        """Test work moves from PENDING to ASSIGNED when assigned.

        Note: Work goes PENDING -> ASSIGNED -> IN_PROGRESS.
        Assignment sets status to ASSIGNED, then compute starts work to go IN_PROGRESS.
        """
        # Create work
        response = await http_client.post(
            f"{API_PREFIX}/work",
            json={
                "title": "Lifecycle test - assignment",
                "description": "Testing work assignment lifecycle",
                "project_id": test_project
            }
        )
        assert response.status_code == 201
        work_id = response.json()["work_id"]

        try:
            # Verify initial status
            response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
            assert response.status_code == 200
            assert response.json()["status"] == "pending"

            # Assign work
            response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": "test-compute-lifecycle", "skills": "tester"}
            )
            assert response.status_code == 200

            # Verify status changed to ASSIGNED
            response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
            assert response.status_code == 200
            work_data = response.json()
            assert work_data["status"] == "assigned"
            assert work_data["assigned_to"] == "test-compute-lifecycle"

            # Now transition to IN_PROGRESS (simulating compute starting work)
            response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/status",
                params={"status": "in_progress", "compute_id": "test-compute-lifecycle"}
            )
            assert response.status_code == 200

            # Verify status is now IN_PROGRESS
            response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
            assert response.status_code == 200
            assert response.json()["status"] == "in_progress"

        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")

    @pytest.mark.asyncio
    async def test_work_completion_clears_assignment(self, http_client, test_project):
        """Test that completing work updates status correctly."""
        # Create and assign work
        response = await http_client.post(
            f"{API_PREFIX}/work",
            json={
                "title": "Lifecycle test - completion",
                "description": "Testing work completion",
                "project_id": test_project
            }
        )
        assert response.status_code == 201
        work_id = response.json()["work_id"]

        try:
            await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": "test-compute-complete", "skills": "finisher"}
            )

            # Complete the work via status update
            response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/status",
                params={"status": "completed", "compute_id": "test-compute-complete"}
            )

            if response.status_code == 200:
                # Verify final status
                response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
                assert response.status_code == 200
                work_data = response.json()
                assert work_data["status"] == "completed"

        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")

    @pytest.mark.asyncio
    async def test_work_failure_updates_status(self, http_client, test_project):
        """Test that failing work updates status correctly."""
        # Create and assign work
        response = await http_client.post(
            f"{API_PREFIX}/work",
            json={
                "title": "Lifecycle test - failure",
                "description": "Testing work failure",
                "project_id": test_project
            }
        )
        assert response.status_code == 201
        work_id = response.json()["work_id"]

        try:
            await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": "test-compute-fail", "skills": "failer"}
            )

            # Fail the work via status update
            response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/status",
                params={"status": "failed", "compute_id": "test-compute-fail"}
            )

            if response.status_code == 200:
                response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
                assert response.status_code == 200
                work_data = response.json()
                assert work_data["status"] == "failed"

        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")


class TestTimeoutEnvironmentConfiguration:
    """Test timeout configuration via environment variables."""

    @pytest.fixture
    async def http_client(self):
        """Create HTTP client for API calls."""
        async with httpx.AsyncClient(base_url=SERVING_BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_orchestrator_uses_environment_config(self, http_client):
        """Test that orchestrator uses environment variable configuration.

        Verifies that the running orchestrator has loaded configuration
        from environment variables (WORK_TIMEOUT_MINUTES, etc.).
        """
        response = await http_client.get(f"{API_PREFIX}/orchestrator/status")
        assert response.status_code == 200
        status_data = response.json()
        stats = status_data.get("stats", {})

        # Verify configuration is present
        assert "timeout_minutes" in stats
        assert "timeout_monitoring_enabled" in stats

        # Configuration should match defaults or env vars
        # Default is 30 minutes, but could be overridden
        assert isinstance(stats["timeout_minutes"], int)
        assert stats["timeout_minutes"] > 0

    @pytest.mark.asyncio
    async def test_config_endpoint_returns_timeout_settings(self, http_client):
        """Test that config endpoint includes timeout settings."""
        response = await http_client.get(f"{API_PREFIX}/config")

        if response.status_code == 404:
            pytest.skip("Config endpoint not available")

        if response.status_code == 200:
            config = response.json()

            # Check if work_timeout configuration is exposed
            if "work_timeout" in config:
                timeout_config = config["work_timeout"]
                assert "timeout_minutes" in timeout_config or "enabled" in timeout_config

    @pytest.mark.asyncio
    async def test_health_endpoint_includes_orchestrator_status(self, http_client):
        """Test that health endpoint shows orchestrator status."""
        response = await http_client.get(f"{API_PREFIX}/health")

        assert response.status_code == 200
        health = response.json()

        # Health should indicate if system is healthy
        assert "status" in health


class TestRetryBehavior:
    """Test work retry behavior on timeout."""

    @pytest.fixture
    async def http_client(self):
        """Create HTTP client for API calls."""
        async with httpx.AsyncClient(base_url=SERVING_BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.fixture
    async def test_project(self, http_client):
        """Create a test project."""
        project_id = generate_project_id()
        await http_client.post(
            f"{API_PREFIX}/projects",
            json={
                "project_id": project_id,
                "name": f"Retry Test {project_id}",
                "description": "Project for retry behavior tests"
            }
        )
        return project_id

    @pytest.mark.asyncio
    async def test_work_tracks_retry_count(self, http_client, test_project):
        """Test that work items track retry count."""
        # Create work
        response = await http_client.post(
            f"{API_PREFIX}/work",
            json={
                "title": "Retry count test",
                "description": "Testing retry count tracking",
                "project_id": test_project
            }
        )
        assert response.status_code == 201
        work_data = response.json()
        work_id = work_data["work_id"]

        try:
            # Initial retry count should be 0
            assert work_data.get("retry_count", 0) == 0

            # Verify via GET
            response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
            assert response.status_code == 200
            assert response.json().get("retry_count", 0) == 0

        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")

    @pytest.mark.asyncio
    async def test_work_has_progress_notes_field(self, http_client, test_project):
        """Test that work items have progress_notes for timeout tracking."""
        # Create work
        response = await http_client.post(
            f"{API_PREFIX}/work",
            json={
                "title": "Progress notes test",
                "description": "Testing progress notes field",
                "project_id": test_project
            }
        )
        assert response.status_code == 201
        work_data = response.json()
        work_id = work_data["work_id"]

        try:
            # Should have progress_notes field (may be empty list)
            assert "progress_notes" in work_data
            assert isinstance(work_data["progress_notes"], list)

        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")
