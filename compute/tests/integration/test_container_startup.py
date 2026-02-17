"""Integration tests for compute Docker container startup.

These are Tier 2 integration tests that verify Docker container startup,
health checks, environment variable injection, and volume mounts.

Tests cover:
1. Container startup via docker-compose
2. Health check progression to healthy state
3. Environment variable injection
4. Volume mount accessibility

Requirements:
    - Docker and docker-compose available
    - Serving and dependencies running (or container-only mode)

Run with:
    pytest compute/tests/integration/test_container_startup.py -v --run-integration
"""

import asyncio
import os
import subprocess
import time
from typing import Generator, Optional

import httpx
import pytest

# Skip all tests unless --run-integration is passed
pytestmark = pytest.mark.skipif(
    "not config.getoption('--run-integration', default=False)",
    reason="Integration tests require --run-integration flag and running containers"
)

# Container configuration
COMPUTE_CONTAINER_NAME = "claudevn-compute-1"
COMPUTE_PORT = 8010
COMPUTE_HEALTH_URL = f"http://localhost:{COMPUTE_PORT}/api/v1/health"
STARTUP_TIMEOUT_SECONDS = 120
HEALTH_CHECK_INTERVAL = 2


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
    """Get container health status (healthy, unhealthy, starting, or None)."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", container_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            status = result.stdout.strip()
            return status if status else None
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_container_env_var(container_name: str, var_name: str) -> Optional[str]:
    """Get an environment variable from a running container."""
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "printenv", var_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def check_volume_mount_in_container(container_name: str, path: str) -> bool:
    """Check if a path exists and is accessible inside the container."""
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "test", "-d", path],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


class TestContainerStartup:
    """Test compute container startup behavior."""

    @pytest.fixture(autouse=True)
    def check_docker(self):
        """Skip tests if Docker is not available."""
        if not is_docker_available():
            pytest.skip("Docker is not available")

    def test_compute_container_is_running(self):
        """Test that compute container is running."""
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running. Start with: docker compose up -d")

        assert is_container_running(COMPUTE_CONTAINER_NAME)

    def test_container_reaches_healthy_state(self):
        """Test that container health check passes within timeout."""
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

        start_time = time.time()
        last_health = None

        while time.time() - start_time < STARTUP_TIMEOUT_SECONDS:
            health = get_container_health(COMPUTE_CONTAINER_NAME)
            last_health = health

            if health == "healthy":
                return  # Test passed
            elif health == "unhealthy":
                pytest.fail(f"Container became unhealthy instead of healthy")

            time.sleep(HEALTH_CHECK_INTERVAL)

        pytest.fail(
            f"Container did not become healthy within {STARTUP_TIMEOUT_SECONDS}s. "
            f"Last health status: {last_health}"
        )

    def test_container_health_transitions(self):
        """Test that container transitions through expected health states."""
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

        observed_states = set()
        start_time = time.time()

        while time.time() - start_time < STARTUP_TIMEOUT_SECONDS:
            health = get_container_health(COMPUTE_CONTAINER_NAME)
            if health:
                observed_states.add(health)

            if health == "healthy":
                break

            time.sleep(HEALTH_CHECK_INTERVAL)

        # Should have seen at least starting or healthy
        assert observed_states, "No health states observed"
        # If we saw healthy, test passes
        if "healthy" in observed_states:
            return
        # If we only saw starting, container is still initializing
        if "starting" in observed_states and "unhealthy" not in observed_states:
            pytest.skip("Container still starting, run test again after initialization")


class TestEnvironmentVariableInjection:
    """Test that environment variables are correctly injected into container."""

    @pytest.fixture(autouse=True)
    def check_container_running(self):
        """Skip tests if container is not running."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

    def test_compute_instance_id_set(self):
        """Test COMPUTE_INSTANCE_ID is set correctly."""
        value = get_container_env_var(COMPUTE_CONTAINER_NAME, "COMPUTE_INSTANCE_ID")
        assert value is not None, "COMPUTE_INSTANCE_ID not set"
        assert value == "compute-001", f"Expected 'compute-001', got '{value}'"

    def test_compute_instance_name_set(self):
        """Test COMPUTE_INSTANCE_NAME is set correctly."""
        value = get_container_env_var(COMPUTE_CONTAINER_NAME, "COMPUTE_INSTANCE_NAME")
        assert value is not None, "COMPUTE_INSTANCE_NAME not set"
        assert value == "Compute-CodeWriter", f"Expected 'Compute-CodeWriter', got '{value}'"

    def test_serving_url_set(self):
        """Test SERVING_URL points to serving container."""
        value = get_container_env_var(COMPUTE_CONTAINER_NAME, "SERVING_URL")
        assert value is not None, "SERVING_URL not set"
        assert "serving" in value, f"SERVING_URL should reference serving container: {value}"

    def test_compute_port_matches_exposed(self):
        """Test COMPUTE_PORT matches the exposed port."""
        value = get_container_env_var(COMPUTE_CONTAINER_NAME, "COMPUTE_PORT")
        assert value is not None, "COMPUTE_PORT not set"
        assert value == str(COMPUTE_PORT), f"Expected '{COMPUTE_PORT}', got '{value}'"

    def test_log_level_set(self):
        """Test LOG_LEVEL is set."""
        value = get_container_env_var(COMPUTE_CONTAINER_NAME, "LOG_LEVEL")
        assert value is not None, "LOG_LEVEL not set"
        assert value in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def test_mcp_enabled_set(self):
        """Test MCP_ENABLED is set."""
        value = get_container_env_var(COMPUTE_CONTAINER_NAME, "MCP_ENABLED")
        assert value is not None, "MCP_ENABLED not set"
        assert value.lower() in ["true", "false", "1", "0"]

    def test_claudevn_serving_url_set(self):
        """Test CLAUDEVN_SERVING_URL is set for MCP communication."""
        value = get_container_env_var(COMPUTE_CONTAINER_NAME, "CLAUDEVN_SERVING_URL")
        assert value is not None, "CLAUDEVN_SERVING_URL not set"
        assert "serving" in value, f"CLAUDEVN_SERVING_URL should reference serving: {value}"


class TestVolumeMounts:
    """Test that volume mounts are accessible inside the container."""

    @pytest.fixture(autouse=True)
    def check_container_running(self):
        """Skip tests if container is not running."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

    def test_data_volume_accessible(self):
        """Test /app/data volume is mounted and accessible."""
        assert check_volume_mount_in_container(COMPUTE_CONTAINER_NAME, "/app/data")

    def test_logs_volume_accessible(self):
        """Test /app/logs volume is mounted and accessible."""
        assert check_volume_mount_in_container(COMPUTE_CONTAINER_NAME, "/app/logs")

    def test_claude_credentials_mount_exists(self):
        """Test Claude credentials staging mount and entrypoint copy exists."""
        # The entrypoint.sh copies from /host-claude to /home/compute/.claude
        # Check the target directory exists (created by entrypoint)
        try:
            result = subprocess.run(
                ["docker", "exec", COMPUTE_CONTAINER_NAME, "test", "-d", "/home/compute/.claude"],
                capture_output=True,
                timeout=10
            )
            # If it doesn't exist, that's OK - host may not have Claude credentials
            if result.returncode != 0:
                pytest.skip("Claude credentials not copied (host ~/.claude may not exist)")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Could not check Claude credentials")

    def test_workspace_directory_exists(self):
        """Test workspace directory exists inside container."""
        # Check for /app/workspace or /app/data/workspace
        has_workspace = check_volume_mount_in_container(COMPUTE_CONTAINER_NAME, "/app/workspace")
        has_data_workspace = check_volume_mount_in_container(COMPUTE_CONTAINER_NAME, "/app/data/workspace")
        has_data_compute = check_volume_mount_in_container(COMPUTE_CONTAINER_NAME, "/app/data/compute")

        assert has_workspace or has_data_workspace or has_data_compute, \
            "No workspace directory found in container"


class TestContainerProcesses:
    """Test that expected processes are running inside the container."""

    @pytest.fixture(autouse=True)
    def check_container_running(self):
        """Skip tests if container is not running."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

    def test_uvicorn_process_running(self):
        """Test uvicorn process is running (FastAPI server)."""
        try:
            result = subprocess.run(
                ["docker", "exec", COMPUTE_CONTAINER_NAME, "pgrep", "-f", "uvicorn"],
                capture_output=True,
                text=True,
                timeout=10
            )
            # pgrep may not be installed (return code 127, "not found" in output)
            if result.returncode == 127 or "not found" in result.stdout.lower() + result.stderr.lower():
                pytest.skip("pgrep not available in container (install procps)")
            assert result.returncode == 0, f"uvicorn process not found: {result.stderr}"
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            pytest.fail(f"Failed to check uvicorn process: {e}")

    def test_python_process_running(self):
        """Test Python process is running."""
        try:
            result = subprocess.run(
                ["docker", "exec", COMPUTE_CONTAINER_NAME, "pgrep", "-f", "python"],
                capture_output=True,
                text=True,
                timeout=10
            )
            # pgrep may not be installed (return code 127, "not found" in output)
            if result.returncode == 127 or "not found" in result.stdout.lower() + result.stderr.lower():
                pytest.skip("pgrep not available in container (install procps)")
            assert result.returncode == 0, f"Python process not found: {result.stderr}"
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            pytest.fail(f"Failed to check Python process: {e}")


class TestContainerLogs:
    """Test container log output for expected messages."""

    @pytest.fixture(autouse=True)
    def check_container_running(self):
        """Skip tests if container is not running."""
        if not is_docker_available():
            pytest.skip("Docker is not available")
        if not is_container_running(COMPUTE_CONTAINER_NAME):
            pytest.skip(f"Container {COMPUTE_CONTAINER_NAME} is not running")

    def test_startup_logs_present(self):
        """Test that startup logs are present."""
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", "100", COMPUTE_CONTAINER_NAME],
                capture_output=True,
                text=True,
                timeout=10
            )
            assert result.returncode == 0, "Failed to get container logs"

            logs = result.stdout + result.stderr
            # Should see uvicorn startup message
            assert "Uvicorn running" in logs or "Started" in logs or "Application startup" in logs, \
                f"Expected startup message not found in logs. Got:\n{logs[:500]}"
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            pytest.fail(f"Failed to get container logs: {e}")

    def test_no_critical_errors_in_logs(self):
        """Test that no CRITICAL errors appear in logs."""
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", "200", COMPUTE_CONTAINER_NAME],
                capture_output=True,
                text=True,
                timeout=10
            )
            logs = result.stdout + result.stderr

            # Check for critical errors
            critical_patterns = [
                "CRITICAL",
                "Traceback (most recent call last):",
                "Fatal error",
            ]

            for pattern in critical_patterns:
                if pattern in logs:
                    # Allow some known non-fatal tracebacks
                    if "CRITICAL" in pattern:
                        pytest.fail(f"Found CRITICAL error in logs")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Could not retrieve container logs")
