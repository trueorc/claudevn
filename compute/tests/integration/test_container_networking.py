"""Integration tests for compute container networking.

These are Tier 2 integration tests that verify network connectivity between
compute containers and other services (Serving, Marketplace, SSH Git server).

Tests cover:
1. Compute can reach Serving at configured URL
2. Compute can reach Marketplace service
3. SSH Git server connectivity

Requirements:
    - Docker containers running (docker compose up -d)
    - All services healthy

Run with:
    pytest compute/tests/integration/test_container_networking.py -v --run-integration
"""

import subprocess
from typing import Optional

import httpx
import pytest

# Skip all tests unless --run-integration is passed
pytestmark = pytest.mark.skipif(
    "not config.getoption('--run-integration', default=False)",
    reason="Integration tests require --run-integration flag and running containers"
)

# Container configuration
COMPUTE_CONTAINER_NAME = "claudevn-compute-1"
SERVING_CONTAINER_NAME = "claudevn-serving"
MARKETPLACE_CONTAINER_NAME = "claudevn-marketplace"
REDIS_CONTAINER_NAME = "claudevn-redis"

# Internal network URLs (as seen from compute container)
SERVING_INTERNAL_URL = "http://serving:8002"
MARKETPLACE_INTERNAL_URL = "http://marketplace:8003"

# External URLs (as seen from host)
SERVING_EXTERNAL_URL = "http://localhost:8002"
MARKETPLACE_EXTERNAL_URL = "http://localhost:8003"
COMPUTE_EXTERNAL_URL = "http://localhost:8010"


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


def exec_in_container(container_name: str, command: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Execute a command inside a container.

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    try:
        result = subprocess.run(
            ["docker", "exec", container_name] + command,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except FileNotFoundError:
        return -1, "", "Docker not found"


class TestComputeToServingConnectivity:
    """Test network connectivity from compute to serving."""

    @pytest.fixture(autouse=True)
    def check_prerequisites(self):
        """Check that required containers are running."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")
        if not is_container_running(SERVING_CONTAINER_NAME):
            pytest.skip(f"Container {SERVING_CONTAINER_NAME} is not running")

    def test_compute_can_resolve_serving_dns(self):
        """Test compute container can resolve 'serving' hostname."""
        returncode, stdout, stderr = exec_in_container(
            COMPUTE_CONTAINER_NAME,
            ["getent", "hosts", "serving"]
        )
        assert returncode == 0, f"DNS resolution failed: {stderr}"
        assert "serving" in stdout.lower(), f"Unexpected DNS response: {stdout}"

    def test_compute_can_ping_serving(self):
        """Test compute container can ping serving (if ping is available)."""
        returncode, stdout, stderr = exec_in_container(
            COMPUTE_CONTAINER_NAME,
            ["ping", "-c", "1", "-W", "5", "serving"]
        )
        # ping may not be installed, which is OK
        if "not found" in stderr.lower() or returncode == 127:
            pytest.skip("ping not available in container")
        assert returncode == 0, f"Ping failed: {stderr}"

    def test_compute_can_reach_serving_health(self):
        """Test compute container can reach serving health endpoint."""
        returncode, stdout, stderr = exec_in_container(
            COMPUTE_CONTAINER_NAME,
            ["curl", "-sf", f"{SERVING_INTERNAL_URL}/api/v1/health"]
        )
        assert returncode == 0, f"Failed to reach serving health: {stderr}"
        assert "status" in stdout.lower() or "healthy" in stdout.lower(), \
            f"Unexpected health response: {stdout}"

    def test_compute_can_reach_serving_root(self):
        """Test compute container can reach serving root endpoint."""
        returncode, stdout, stderr = exec_in_container(
            COMPUTE_CONTAINER_NAME,
            ["curl", "-sf", f"{SERVING_INTERNAL_URL}/"]
        )
        assert returncode == 0, f"Failed to reach serving root: {stderr}"
        assert "claudevn" in stdout.lower() or "serving" in stdout.lower(), \
            f"Unexpected root response: {stdout}"


class TestComputeToMarketplaceConnectivity:
    """Test network connectivity from compute to marketplace."""

    @pytest.fixture(autouse=True)
    def check_prerequisites(self):
        """Check that required containers are running."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")
        if not is_container_running(MARKETPLACE_CONTAINER_NAME):
            pytest.skip(f"Container {MARKETPLACE_CONTAINER_NAME} is not running")

    def test_compute_can_resolve_marketplace_dns(self):
        """Test compute container can resolve 'marketplace' hostname."""
        returncode, stdout, stderr = exec_in_container(
            COMPUTE_CONTAINER_NAME,
            ["getent", "hosts", "marketplace"]
        )
        assert returncode == 0, f"DNS resolution failed: {stderr}"
        assert "marketplace" in stdout.lower(), f"Unexpected DNS response: {stdout}"

    def test_compute_can_reach_marketplace_health(self):
        """Test compute container can reach marketplace health endpoint."""
        returncode, stdout, stderr = exec_in_container(
            COMPUTE_CONTAINER_NAME,
            ["curl", "-sf", f"{MARKETPLACE_INTERNAL_URL}/api/v1/health"]
        )
        assert returncode == 0, f"Failed to reach marketplace health: {stderr}"


class TestComputeToRedisConnectivity:
    """Test network connectivity from compute to Redis."""

    @pytest.fixture(autouse=True)
    def check_prerequisites(self):
        """Check that required containers are running."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")
        if not is_container_running(REDIS_CONTAINER_NAME):
            pytest.skip(f"Container {REDIS_CONTAINER_NAME} is not running")

    def test_compute_can_resolve_redis_dns(self):
        """Test compute container can resolve 'redis' hostname."""
        returncode, stdout, stderr = exec_in_container(
            COMPUTE_CONTAINER_NAME,
            ["getent", "hosts", "redis"]
        )
        assert returncode == 0, f"DNS resolution failed: {stderr}"
        assert "redis" in stdout.lower(), f"Unexpected DNS response: {stdout}"


class TestSSHGitServerConnectivity:
    """Test SSH Git server connectivity from compute."""

    @pytest.fixture(autouse=True)
    def check_prerequisites(self):
        """Check that required containers are running."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")
        if not is_container_running(SERVING_CONTAINER_NAME):
            pytest.skip(f"Container {SERVING_CONTAINER_NAME} is not running")

    def test_compute_can_reach_ssh_port(self):
        """Test compute container can reach SSH Git port on serving."""
        # SSH port is 2222 inside the network
        returncode, stdout, stderr = exec_in_container(
            COMPUTE_CONTAINER_NAME,
            ["nc", "-zv", "-w", "5", "serving", "2222"],
            timeout=15
        )
        # nc may not be installed
        if "not found" in stderr.lower() or returncode == 127:
            pytest.skip("nc (netcat) not available in container")

        # Check if connection succeeded (return code 0) or "open" in output
        if returncode == 0 or "open" in stderr.lower() or "succeeded" in stderr.lower():
            return
        pytest.fail(f"SSH port not reachable: {stderr}")


class TestExternalEndpointAccessibility:
    """Test that services are accessible from outside (host perspective)."""

    @pytest.fixture(autouse=True)
    def check_docker(self):
        """Check Docker is available."""
        if not is_docker_available():
            pytest.skip("Docker is not available")

    @pytest.mark.asyncio
    async def test_compute_accessible_from_host(self):
        """Test compute health endpoint is accessible from host."""
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMPUTE_EXTERNAL_URL}/api/v1/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_serving_accessible_from_host(self):
        """Test serving health endpoint is accessible from host."""
        if not is_container_running(SERVING_CONTAINER_NAME):
            pytest.skip(f"Container {SERVING_CONTAINER_NAME} is not running")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{SERVING_EXTERNAL_URL}/api/v1/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_marketplace_accessible_from_host(self):
        """Test marketplace health endpoint is accessible from host."""
        if not is_container_running(MARKETPLACE_CONTAINER_NAME):
            pytest.skip(f"Container {MARKETPLACE_CONTAINER_NAME} is not running")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{MARKETPLACE_EXTERNAL_URL}/api/v1/health")
            assert response.status_code == 200


class TestDockerNetworkConfiguration:
    """Test Docker network configuration is correct."""

    @pytest.fixture(autouse=True)
    def check_docker(self):
        """Check Docker is available."""
        if not is_docker_available():
            pytest.skip("Docker is not available")

    def test_claudevn_network_exists(self):
        """Test claudevn-network exists."""
        result = subprocess.run(
            ["docker", "network", "inspect", "claudevn-network"],
            capture_output=True,
            timeout=10
        )
        # Network may be named differently (claudevn_claudevn-network with compose)
        if result.returncode != 0:
            # Try with compose prefix
            result = subprocess.run(
                ["docker", "network", "ls", "--filter", "name=claudevn"],
                capture_output=True,
                text=True,
                timeout=10
            )
            assert "claudevn" in result.stdout.lower(), \
                "No claudevn network found"

    def test_compute_on_claudevn_network(self):
        """Test compute container is on the claudevn network."""
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

        result = subprocess.run(
            [
                "docker", "inspect", "-f",
                "{{range $key, $value := .NetworkSettings.Networks}}{{$key}} {{end}}",
                COMPUTE_CONTAINER_NAME
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0
        networks = result.stdout.strip()
        assert "claudevn" in networks.lower(), \
            f"Compute not on claudevn network: {networks}"

    def test_serving_on_claudevn_network(self):
        """Test serving container is on the claudevn network."""
        if not is_container_running(SERVING_CONTAINER_NAME):
            pytest.skip(f"Container {SERVING_CONTAINER_NAME} is not running")

        result = subprocess.run(
            [
                "docker", "inspect", "-f",
                "{{range $key, $value := .NetworkSettings.Networks}}{{$key}} {{end}}",
                SERVING_CONTAINER_NAME
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0
        networks = result.stdout.strip()
        assert "claudevn" in networks.lower(), \
            f"Serving not on claudevn network: {networks}"


class TestContainerDependencies:
    """Test container dependency chain is correct."""

    @pytest.fixture(autouse=True)
    def check_docker(self):
        """Check Docker is available."""
        if not is_docker_available():
            pytest.skip("Docker is not available")

    def test_redis_starts_before_serving(self):
        """Test Redis container started before Serving."""
        if not is_container_running(REDIS_CONTAINER_NAME):
            pytest.skip(f"Container {REDIS_CONTAINER_NAME} is not running")
        if not is_container_running(SERVING_CONTAINER_NAME):
            pytest.skip(f"Container {SERVING_CONTAINER_NAME} is not running")

        # Get start times
        redis_result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.StartedAt}}", REDIS_CONTAINER_NAME],
            capture_output=True,
            text=True,
            timeout=10
        )
        serving_result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.StartedAt}}", SERVING_CONTAINER_NAME],
            capture_output=True,
            text=True,
            timeout=10
        )

        if redis_result.returncode == 0 and serving_result.returncode == 0:
            redis_start = redis_result.stdout.strip()
            serving_start = serving_result.stdout.strip()
            # Redis should have started before or at same time as serving
            assert redis_start <= serving_start, \
                f"Redis ({redis_start}) should start before Serving ({serving_start})"

    def test_serving_starts_before_compute(self):
        """Test Serving container started before Compute."""
        if not is_container_running(SERVING_CONTAINER_NAME):
            pytest.skip(f"Container {SERVING_CONTAINER_NAME} is not running")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

        # Get start times
        serving_result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.StartedAt}}", SERVING_CONTAINER_NAME],
            capture_output=True,
            text=True,
            timeout=10
        )
        compute_result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.StartedAt}}", COMPUTE_CONTAINER_NAME],
            capture_output=True,
            text=True,
            timeout=10
        )

        if serving_result.returncode == 0 and compute_result.returncode == 0:
            serving_start = serving_result.stdout.strip()
            compute_start = compute_result.stdout.strip()
            # Serving should have started before or at same time as compute
            assert serving_start <= compute_start, \
                f"Serving ({serving_start}) should start before Compute ({compute_start})"
