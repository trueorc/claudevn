"""Integration tests for compute health endpoint.

These are Tier 2 integration tests that verify the compute service health endpoint
returns correct status and reflects actual service state.

Tests cover:
1. Health endpoint returns 200 when healthy
2. Health endpoint response structure
3. Health endpoint reflects service state (SSE connection, spawner status)

Requirements:
    - Docker containers running (docker compose up -d)
    - Compute container healthy

Run with:
    pytest compute/tests/integration/test_health_endpoint.py -v --run-integration
"""

import asyncio
import subprocess
import time
from typing import Optional

import httpx
import pytest

# Skip all tests unless --run-integration is passed
pytestmark = pytest.mark.skipif(
    "not config.getoption('--run-integration', default=False)",
    reason="Integration tests require --run-integration flag and running containers"
)

# Container and endpoint configuration
COMPUTE_CONTAINER_NAME = "claudevn-compute-1"
COMPUTE_PORT = 8010
COMPUTE_BASE_URL = f"http://localhost:{COMPUTE_PORT}"
SERVING_BASE_URL = "http://localhost:8002"


def is_docker_available() -> bool:
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def is_container_running(container_name: str) -> bool:
    """Check if a container is running."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_container_health(container_name: str) -> Optional[str]:
    """Get container health status."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", container_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


class TestHealthEndpointBasic:
    """Test basic health endpoint functionality."""

    @pytest.fixture(autouse=True)
    def check_prerequisites(self):
        """Check that Docker and container are available."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")
        # Wait for healthy state
        health = get_container_health(COMPUTE_CONTAINER_NAME)
        if health != "healthy":
            pytest.skip(f"Container health is '{health}', expected 'healthy'")

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_200(self):
        """Test /api/v1/health returns 200 status code."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/api/v1/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_json(self):
        """Test health endpoint returns valid JSON."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/api/v1/health")
            assert response.status_code == 200
            assert "application/json" in response.headers.get("content-type", "")

            data = response.json()
            assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_health_endpoint_has_status_field(self):
        """Test health response includes status field."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/api/v1/health")
            data = response.json()

            assert "status" in data
            assert data["status"] in ["healthy", "degraded", "unhealthy"]

    @pytest.mark.asyncio
    async def test_health_endpoint_has_timestamp(self):
        """Test health response includes timestamp."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/api/v1/health")
            data = response.json()

            assert "timestamp" in data
            # Should be ISO format timestamp
            assert "T" in data["timestamp"] or "-" in data["timestamp"]

    @pytest.mark.asyncio
    async def test_health_endpoint_has_architecture_version(self):
        """Test health response includes architecture version."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/api/v1/health")
            data = response.json()

            assert "architecture" in data
            assert data["architecture"] == "v1.0"


class TestHealthEndpointServiceState:
    """Test that health endpoint reflects actual service state."""

    @pytest.fixture(autouse=True)
    def check_prerequisites(self):
        """Check that Docker and container are available."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

    @pytest.mark.asyncio
    async def test_health_includes_sse_connection_status(self):
        """Test health response includes SSE connection status."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/api/v1/health")
            data = response.json()

            assert "sse_connected" in data
            assert isinstance(data["sse_connected"], bool)

    @pytest.mark.asyncio
    async def test_health_includes_running_instances(self):
        """Test health response includes running Claude Code instances count."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/api/v1/health")
            data = response.json()

            assert "running_instances" in data
            assert isinstance(data["running_instances"], int)
            assert data["running_instances"] >= 0

    @pytest.mark.asyncio
    async def test_health_status_reflects_sse_connection(self):
        """Test that health status reflects SSE connection state."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/api/v1/health")
            data = response.json()

            # If SSE is connected, status should be healthy
            # If SSE is not connected, status should be degraded
            if data.get("sse_connected"):
                assert data["status"] == "healthy"
            else:
                assert data["status"] in ["degraded", "unhealthy"]


class TestStatsEndpoint:
    """Test the detailed stats endpoint."""

    @pytest.fixture(autouse=True)
    def check_prerequisites(self):
        """Check that Docker and container are available."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

    @pytest.mark.asyncio
    async def test_stats_endpoint_returns_200(self):
        """Test /api/v1/stats returns 200 status code."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/api/v1/stats")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_stats_endpoint_includes_spawner_info(self):
        """Test stats response includes spawner information."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/api/v1/stats")
            data = response.json()

            assert "spawner" in data
            if data["spawner"] is not None:
                spawner = data["spawner"]
                assert isinstance(spawner, dict)

    @pytest.mark.asyncio
    async def test_stats_endpoint_includes_sse_client_info(self):
        """Test stats response includes SSE client information."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/api/v1/stats")
            data = response.json()

            assert "sse_client" in data
            if data["sse_client"] is not None:
                sse_client = data["sse_client"]
                assert isinstance(sse_client, dict)

    @pytest.mark.asyncio
    async def test_stats_endpoint_includes_timestamp(self):
        """Test stats response includes timestamp."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/api/v1/stats")
            data = response.json()

            assert "timestamp" in data


class TestRootEndpoint:
    """Test the root endpoint provides service information."""

    @pytest.fixture(autouse=True)
    def check_prerequisites(self):
        """Check that Docker and container are available."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

    @pytest.mark.asyncio
    async def test_root_endpoint_returns_200(self):
        """Test root endpoint returns 200."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_root_endpoint_includes_service_info(self):
        """Test root endpoint includes service information."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/")
            data = response.json()

            assert "service" in data
            assert "ClaudeVN" in data["service"] or "Compute" in data["service"]

    @pytest.mark.asyncio
    async def test_root_endpoint_includes_version(self):
        """Test root endpoint includes version."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/")
            data = response.json()

            assert "version" in data

    @pytest.mark.asyncio
    async def test_root_endpoint_includes_compute_id(self):
        """Test root endpoint includes compute_id."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/")
            data = response.json()

            assert "compute_id" in data
            # Should match expected compute ID
            assert data["compute_id"] == "compute-001"


class TestVersionEndpoint:
    """Test the version endpoint."""

    @pytest.fixture(autouse=True)
    def check_prerequisites(self):
        """Check that Docker and container are available."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

    @pytest.mark.asyncio
    async def test_version_endpoint_returns_200(self):
        """Test /version returns 200."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/version")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_version_endpoint_includes_version(self):
        """Test version endpoint includes version string."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/version")
            data = response.json()

            assert "version" in data
            # Version should be in semver format
            version = data["version"]
            assert "." in version

    @pytest.mark.asyncio
    async def test_version_endpoint_includes_service_name(self):
        """Test version endpoint includes service name."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/version")
            data = response.json()

            assert "service" in data
            assert data["service"] == "compute"


class TestStatusEndpoint:
    """Test the detailed status endpoint."""

    @pytest.fixture(autouse=True)
    def check_prerequisites(self):
        """Check that Docker and container are available."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

    @pytest.mark.asyncio
    async def test_status_endpoint_returns_200(self):
        """Test /status returns 200."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/status")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_status_includes_compute_id(self):
        """Test status includes compute_id."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/status")
            data = response.json()

            assert "compute_id" in data

    @pytest.mark.asyncio
    async def test_status_includes_serving_url(self):
        """Test status includes serving_url."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_BASE_URL}/status")
            data = response.json()

            assert "serving_url" in data
            assert "serving" in data["serving_url"]


class TestHealthEndpointConcurrency:
    """Test health endpoint under concurrent requests."""

    @pytest.fixture(autouse=True)
    def check_prerequisites(self):
        """Check that Docker and container are available."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

    @pytest.mark.asyncio
    async def test_concurrent_health_requests(self):
        """Test health endpoint handles concurrent requests."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Make 10 concurrent requests
            tasks = [
                client.get(f"{COMPUTE_BASE_URL}/api/v1/health")
                for _ in range(10)
            ]
            responses = await asyncio.gather(*tasks)

            # All should succeed
            for response in responses:
                assert response.status_code == 200
                data = response.json()
                assert "status" in data

    @pytest.mark.asyncio
    async def test_health_response_consistency(self):
        """Test that consecutive health responses are consistent."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            responses = []
            for _ in range(5):
                response = await client.get(f"{COMPUTE_BASE_URL}/api/v1/health")
                responses.append(response.json())
                await asyncio.sleep(0.1)

            # Status should be consistent across requests
            statuses = [r["status"] for r in responses]
            # Allow for status to be same or transition once
            unique_statuses = set(statuses)
            assert len(unique_statuses) <= 2, \
                f"Health status too unstable: {statuses}"
