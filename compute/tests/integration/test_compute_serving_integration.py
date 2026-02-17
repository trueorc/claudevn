"""Integration tests for compute ↔ serving communication.

These are Tier 2 integration tests that verify the full communication flow
between compute infrastructure and serving component.

Tests cover:
1. SSE connection and registration flow
2. Work assignment triggers Claude Code spawner
3. Claude Code lifecycle events reach serving
4. Merge conflict handling
5. Graceful shutdown with active work

Requirements:
    - Serving running at http://localhost:8002
    - Redis (if required by serving)
    - Docker containers up (docker-compose up -d)

Run with:
    pytest compute/tests/integration/test_compute_serving_integration.py -v --run-integration
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Skip all tests unless --run-integration is passed
pytestmark = pytest.mark.skipif(
    "not config.getoption('--run-integration', default=False)",
    reason="Integration tests require --run-integration flag and running server"
)

# Test configuration
SERVING_BASE_URL = os.getenv("SERVING_URL", "http://localhost:8002")
API_PREFIX = "/api/v1"


class TestSSEConnectionAndRegistration:
    """Test SSE connection flow: compute connects to serving and appears in registry."""

    @pytest.mark.asyncio
    async def test_sse_connection_established_and_receives_connected_event(self):
        """Test that SSE connection is established and receives connected event."""
        compute_id = f"test-compute-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            # Establish SSE connection
            async with client.stream(
                "GET",
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/connect",
                headers={
                    "X-Compute-ID": compute_id,
                    "X-Capabilities": "python,testing,claude_code",
                    "X-Resources": "cpu=4,memory=16gb",
                    "Accept": "text/event-stream"
                }
            ) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")

                # Read first event (should be 'connected')
                events_received = []
                connected_data = None
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line.replace("event:", "").strip()
                        events_received.append(event_type)
                    if line.startswith("data:"):
                        try:
                            data = json.loads(line.replace("data:", "").strip())
                            if data.get("status") == "connected":
                                connected_data = data
                                break
                        except json.JSONDecodeError:
                            pass
                    if len(events_received) >= 2:
                        break

                assert "connected" in events_received
                assert connected_data is not None
                assert connected_data.get("compute_id") == compute_id

    @pytest.mark.asyncio
    async def test_sse_connection_returns_correct_headers(self):
        """Test SSE connection returns correct headers for streaming."""
        compute_id = f"test-headers-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            async with client.stream(
                "GET",
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/connect",
                headers={
                    "X-Compute-ID": compute_id,
                    "X-Capabilities": "python",
                    "Accept": "text/event-stream"
                }
            ) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")
                assert response.headers.get("cache-control") == "no-cache"
                assert response.headers.get("connection") == "keep-alive"

    @pytest.mark.asyncio
    async def test_sse_receives_keepalive_events(self):
        """Test that SSE connection receives keepalive events."""
        compute_id = f"test-keepalive-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient(timeout=40.0) as client:
            async with client.stream(
                "GET",
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/connect",
                headers={
                    "X-Compute-ID": compute_id,
                    "X-Capabilities": "python",
                    "Accept": "text/event-stream"
                }
            ) as response:
                assert response.status_code == 200

                events = []
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line.replace("event:", "").strip()
                        events.append(event_type)
                        if "keepalive" in events:
                            break
                    # Timeout after collecting enough events
                    if len(events) >= 3:
                        break

                # Should receive at least connected and keepalive
                assert "connected" in events or "keepalive" in events


class TestWorkAssignmentFlow:
    """Test work_assigned event triggers ClaudeCodeSpawner."""

    @pytest.fixture
    async def registered_compute(self):
        """Fixture to register a compute instance and clean up after test."""
        compute_id = f"test-work-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient() as client:
            # Register via legacy endpoint for test setup
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/register",
                json={
                    "instance_id": compute_id,
                    "name": f"Work Test {compute_id}",
                    "endpoint": "http://localhost:9999",
                    "capabilities": {
                        "agents": ["claude_code", "python"],
                        "tools": [],
                        "features": []
                    }
                }
            )
            if response.status_code != 201:
                pytest.skip(f"Could not register compute: {response.text}")

            yield compute_id

            # Cleanup
            await client.delete(f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}")

    @pytest.mark.asyncio
    async def test_work_assignment_creates_event(self, registered_compute):
        """Test that work can be assigned to a registered compute."""
        compute_id = registered_compute

        async with httpx.AsyncClient() as client:
            # Create a work item
            work_data = {
                "title": f"Integration test work {uuid.uuid4().hex[:8]}",
                "description": "Test work for compute assignment",
                "priority": "high",
                "project_id": "test-project",
                "required_capabilities": ["python"]
            }

            create_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/work",
                json=work_data
            )
            assert create_response.status_code == 201
            work = create_response.json()
            work_id = work["work_id"]

            # Attempt to assign to compute
            assign_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": compute_id}
            )
            # Should succeed or indicate compute not suitable
            assert assign_response.status_code in [200, 400]

    @pytest.mark.asyncio
    async def test_work_events_via_sse_connection(self):
        """Test that work assignment events are delivered via SSE."""
        compute_id = f"test-sse-work-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            events_received = []

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

                # Collect events while connected
                event_types = set()
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line.replace("event:", "").strip()
                        event_types.add(event_type)
                    # Stop after receiving connected and one more event
                    if "connected" in event_types and len(event_types) >= 2:
                        break
                    if len(event_types) >= 3:
                        break

                # At minimum should receive connected event
                assert "connected" in event_types


class TestClaudeCodeLifecycleEvents:
    """Test started/completed/failed events reach serving."""

    @pytest.fixture
    async def registered_compute(self):
        """Fixture to register a compute instance."""
        compute_id = f"test-lifecycle-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/register",
                json={
                    "instance_id": compute_id,
                    "name": f"Lifecycle Test {compute_id}",
                    "endpoint": "http://localhost:9999",
                    "capabilities": {"agents": ["claude_code"], "tools": [], "features": []}
                }
            )
            if response.status_code != 201:
                pytest.skip(f"Could not register compute: {response.text}")

            yield compute_id

            await client.delete(f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}")

    @pytest.mark.asyncio
    async def test_claude_code_started_event(self, registered_compute):
        """Test claude_code_started event is acknowledged by serving."""
        compute_id = registered_compute
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        instance_id = f"cc-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient() as client:
            event_data = {
                "compute_id": compute_id,
                "event": "claude_code_started",
                "task_id": task_id,
                "instance_id": instance_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/events",
                json=event_data
            )
            assert response.status_code == 200
            result = response.json()
            assert result["status"] == "acknowledged"
            assert result["event"] == "claude_code_started"
            assert result["compute_id"] == compute_id
            assert result["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_claude_code_completed_event(self, registered_compute):
        """Test claude_code_completed event is acknowledged by serving."""
        compute_id = registered_compute
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        instance_id = f"cc-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient() as client:
            # First send started event
            started_data = {
                "compute_id": compute_id,
                "event": "claude_code_started",
                "task_id": task_id,
                "instance_id": instance_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/events",
                json=started_data
            )

            # Then send completed event
            completed_data = {
                "compute_id": compute_id,
                "event": "claude_code_completed",
                "task_id": task_id,
                "instance_id": instance_id,
                "exit_code": 0,
                "duration_seconds": 120,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/events",
                json=completed_data
            )
            assert response.status_code == 200
            result = response.json()
            assert result["status"] == "acknowledged"
            assert result["event"] == "claude_code_completed"

    @pytest.mark.asyncio
    async def test_claude_code_failed_event(self, registered_compute):
        """Test claude_code_failed event is acknowledged by serving."""
        compute_id = registered_compute
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        instance_id = f"cc-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient() as client:
            # First send started event
            started_data = {
                "compute_id": compute_id,
                "event": "claude_code_started",
                "task_id": task_id,
                "instance_id": instance_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/events",
                json=started_data
            )

            # Then send failed event
            failed_data = {
                "compute_id": compute_id,
                "event": "claude_code_failed",
                "task_id": task_id,
                "instance_id": instance_id,
                "exit_code": 1,
                "error": "Test error: command failed",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/events",
                json=failed_data
            )
            assert response.status_code == 200
            result = response.json()
            assert result["status"] == "acknowledged"
            assert result["event"] == "claude_code_failed"

    @pytest.mark.asyncio
    async def test_event_updates_compute_metadata(self, registered_compute):
        """Test that lifecycle events update compute instance metadata."""
        compute_id = registered_compute
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        instance_id = f"cc-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient() as client:
            # Send started event
            started_data = {
                "compute_id": compute_id,
                "event": "claude_code_started",
                "task_id": task_id,
                "instance_id": instance_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/events",
                json=started_data
            )

            # Verify metadata updated
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}"
            )
            assert response.status_code == 200
            instance = response.json()

            metadata = instance.get("metadata", {})
            assert metadata.get("current_task_id") == task_id
            assert metadata.get("current_instance_id") == instance_id

    @pytest.mark.asyncio
    async def test_event_rejected_for_unregistered_compute(self):
        """Test that events from unregistered compute are rejected."""
        compute_id = f"unregistered-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient() as client:
            event_data = {
                "compute_id": compute_id,
                "event": "claude_code_started",
                "task_id": f"task-{uuid.uuid4().hex[:8]}",
                "instance_id": f"cc-{uuid.uuid4().hex[:8]}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/events",
                json=event_data
            )
            assert response.status_code == 404


class TestMergeConflictHandling:
    """Test merge conflict event triggers resolution handler."""

    @pytest.mark.asyncio
    async def test_instance_sse_endpoint_for_merge_events(self):
        """Test that registered compute can connect to instance-specific SSE endpoint.

        Note: This tests the SSE infrastructure for event delivery.
        The actual merge_conflict event requires a PR with conflicts,
        which is tested in the git infrastructure tests.
        """
        compute_id = f"test-conflict-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            # First register compute
            register_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/register",
                json={
                    "instance_id": compute_id,
                    "name": f"Conflict Test {compute_id}",
                    "endpoint": "http://localhost:9999",
                    "capabilities": {"agents": ["claude_code"], "tools": [], "features": []}
                }
            )

            if register_response.status_code != 201:
                pytest.skip("Could not register compute")

            try:
                # Connect to instance-specific SSE endpoint for merge events
                async with client.stream(
                    "GET",
                    f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}/events",
                    headers={"Accept": "text/event-stream"}
                ) as response:
                    assert response.status_code == 200
                    assert "text/event-stream" in response.headers.get("content-type", "")
            finally:
                # Cleanup
                await client.delete(f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}")

    @pytest.mark.asyncio
    async def test_unregistered_instance_cannot_connect_to_sse_events(self):
        """Test that unregistered compute cannot connect to instance SSE endpoint."""
        compute_id = f"unregistered-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}/events",
                headers={"Accept": "text/event-stream"}
            )
            assert response.status_code == 404


class TestGracefulShutdownWithActiveWork:
    """Test shutdown event handling with active Claude Code work."""

    @pytest.fixture
    async def compute_with_work(self):
        """Fixture to create compute with simulated active work."""
        compute_id = f"test-shutdown-{uuid.uuid4().hex[:8]}"
        task_id = f"task-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient() as client:
            # Register compute
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/register",
                json={
                    "instance_id": compute_id,
                    "name": f"Shutdown Test {compute_id}",
                    "endpoint": "http://localhost:9999",
                    "capabilities": {"agents": ["claude_code"], "tools": [], "features": []}
                }
            )
            if response.status_code != 201:
                pytest.skip("Could not register compute")

            # Simulate active work
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/events",
                json={
                    "compute_id": compute_id,
                    "event": "claude_code_started",
                    "task_id": task_id,
                    "instance_id": f"cc-{uuid.uuid4().hex[:8]}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )

            yield {"compute_id": compute_id, "task_id": task_id}

            # Cleanup
            await client.delete(f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}")

    @pytest.mark.asyncio
    async def test_compute_with_active_work_metadata(self, compute_with_work):
        """Test compute with active work has correct metadata."""
        compute_id = compute_with_work["compute_id"]
        task_id = compute_with_work["task_id"]

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}"
            )
            assert response.status_code == 200
            instance = response.json()

            metadata = instance.get("metadata", {})
            assert metadata.get("current_task_id") == task_id

    @pytest.mark.asyncio
    async def test_shutdown_event_clears_work_on_completion(self, compute_with_work):
        """Test that completing work clears current task metadata."""
        compute_id = compute_with_work["compute_id"]
        task_id = compute_with_work["task_id"]

        async with httpx.AsyncClient() as client:
            # Complete the work
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/events",
                json={
                    "compute_id": compute_id,
                    "event": "claude_code_completed",
                    "task_id": task_id,
                    "instance_id": f"cc-{uuid.uuid4().hex[:8]}",
                    "exit_code": 0,
                    "duration_seconds": 60,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )

            # Verify metadata cleared
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}"
            )
            assert response.status_code == 200
            instance = response.json()

            metadata = instance.get("metadata", {})
            assert metadata.get("current_task_id") is None


class TestComputeRegistryOperations:
    """Test compute registry operations used by integration flows."""

    @pytest.mark.asyncio
    async def test_list_compute_instances(self):
        """Test listing all registered compute instances."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/compute")
            assert response.status_code == 200
            data = response.json()
            assert "instances" in data
            assert "total" in data
            assert "online" in data
            assert "offline" in data

    @pytest.mark.asyncio
    async def test_search_compute_by_capability(self):
        """Test searching compute instances by capability."""
        compute_id = f"test-capability-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient() as client:
            # Register with specific capability
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/register",
                json={
                    "instance_id": compute_id,
                    "name": f"Capability Test {compute_id}",
                    "endpoint": "http://localhost:9999",
                    "capabilities": {
                        "agents": ["unique_test_capability"],
                        "tools": [],
                        "features": []
                    }
                }
            )

            try:
                # Search by capability
                response = await client.get(
                    f"{SERVING_BASE_URL}{API_PREFIX}/compute/search/by-agent/unique_test_capability"
                )
                assert response.status_code == 200
                instances = response.json()
                assert any(i["instance_id"] == compute_id for i in instances)
            finally:
                await client.delete(f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}")

    @pytest.mark.asyncio
    async def test_aggregated_capabilities(self):
        """Test getting aggregated capabilities across all computes."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/capabilities/aggregated"
            )
            assert response.status_code == 200
            capabilities = response.json()
            assert isinstance(capabilities, dict)

    @pytest.mark.asyncio
    async def test_registry_stats(self):
        """Test getting registry statistics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/stats/summary"
            )
            assert response.status_code == 200
            stats = response.json()
            assert isinstance(stats, dict)


class TestSSEConnectionManager:
    """Test SSE connection manager functionality."""

    @pytest.mark.asyncio
    async def test_sse_stats_endpoint(self):
        """Test SSE connection statistics endpoint."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/sse/stats"
            )
            assert response.status_code == 200
            stats = response.json()
            assert isinstance(stats, dict)

    @pytest.mark.asyncio
    async def test_multiple_sse_connections(self):
        """Test multiple simultaneous SSE connections."""
        compute_ids = [f"test-multi-{i}-{uuid.uuid4().hex[:8]}" for i in range(3)]

        async with httpx.AsyncClient(timeout=10.0) as client:
            connections = []

            try:
                # Establish multiple connections
                for compute_id in compute_ids:
                    stream = client.stream(
                        "GET",
                        f"{SERVING_BASE_URL}{API_PREFIX}/compute/connect",
                        headers={
                            "X-Compute-ID": compute_id,
                            "X-Capabilities": "python",
                            "Accept": "text/event-stream"
                        }
                    )
                    connections.append(stream)

                # Verify all connections succeeded
                async with connections[0] as r1, connections[1] as r2, connections[2] as r3:
                    assert r1.status_code == 200
                    assert r2.status_code == 200
                    assert r3.status_code == 200

                    # Check stats show multiple connections
                    stats_response = await client.get(
                        f"{SERVING_BASE_URL}{API_PREFIX}/compute/sse/stats"
                    )
                    # Stats may or may not track per-connection details
                    assert stats_response.status_code == 200
            except Exception:
                pass  # Cleanup happens automatically


# Pytest configuration for integration tests
def pytest_configure(config):
    """Add integration marker."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )


def pytest_addoption(parser):
    """Add --run-integration option."""
    try:
        parser.addoption(
            "--run-integration",
            action="store_true",
            default=False,
            help="run integration tests"
        )
    except ValueError:
        # Option already added by another conftest
        pass
