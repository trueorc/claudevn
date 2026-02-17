"""Tests for compute spawner service.

Comprehensive unit tests for ComputeSpawner using mock-only patterns.
Tests all major functionality: initialization, spawning, skill composition,
instance management, and graceful shutdown.
"""

import asyncio
import json
import os
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from services.compute_spawner import (
    ComputeSpawner,
    get_compute_spawner,
    set_compute_spawner
)
from models.compute_spawner import (
    SpawnRequest, SpawnResponse, SpawnedCompute, ComputeState,
    ComputeListResponse, StopRequest, ComputeMetrics
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_workspaces_path(tmp_path):
    """Create a temporary workspaces directory."""
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir()
    return str(workspaces)


@pytest.fixture
def spawner(mock_workspaces_path):
    """Create a ComputeSpawner for testing."""
    return ComputeSpawner(
        serving_url="http://localhost:8002",
        workspaces_path=mock_workspaces_path,
        claude_path="/usr/bin/claude"
    )


@pytest.fixture
def mock_process():
    """Create a mock asyncio subprocess."""
    process = MagicMock()
    process.pid = 12345
    process.stdin = MagicMock()
    process.stdin.write = MagicMock()
    process.stdin.drain = AsyncMock()
    process.stdout = MagicMock()
    process.stderr = MagicMock()
    process.wait = AsyncMock(return_value=0)
    process.send_signal = MagicMock()
    process.kill = MagicMock()
    return process


@pytest.fixture
def spawn_request():
    """Create a basic spawn request."""
    return SpawnRequest(
        compute_id="test_compute_001",
        name="Test Compute",
        skills=["skill_001"],
        capabilities=["python", "testing"],
        work_id=None,
        project_id="project_001"
    )


# =============================================================================
# Test: Initialization
# =============================================================================

class TestComputeSpawnerInit:
    """Test ComputeSpawner initialization."""

    def test_init_defaults(self, mock_workspaces_path):
        """Test initialization with defaults."""
        spawner = ComputeSpawner(
            workspaces_path=mock_workspaces_path
        )

        assert spawner.serving_url == "http://localhost:8002"
        assert spawner.workspaces_path == Path(mock_workspaces_path)
        assert spawner._instances == {}
        assert spawner._processes == {}
        assert spawner._monitor_tasks == {}
        assert not spawner._initialized

    def test_init_custom_params(self, mock_workspaces_path):
        """Test initialization with custom parameters."""
        spawner = ComputeSpawner(
            serving_url="http://custom:9000",
            workspaces_path=mock_workspaces_path,
            claude_path="/custom/path/claude"
        )

        assert spawner.serving_url == "http://custom:9000"
        assert spawner.claude_path == "/custom/path/claude"

    def test_init_creates_workspaces_dir(self, tmp_path):
        """Test that init creates workspaces directory if missing."""
        workspaces = tmp_path / "new_workspaces"
        assert not workspaces.exists()

        ComputeSpawner(workspaces_path=str(workspaces))

        assert workspaces.exists()

    @patch('services.compute_spawner.shutil.which')
    @patch('services.compute_spawner.os.path.isfile')
    def test_find_claude_cli_from_path(self, mock_isfile, mock_which, mock_workspaces_path):
        """Test finding claude CLI from PATH via shutil.which."""
        # Make isfile return True only for the path found by which
        mock_which.return_value = "/custom/path/to/claude"
        mock_isfile.side_effect = lambda p: p == "/custom/path/to/claude"

        spawner = ComputeSpawner(workspaces_path=mock_workspaces_path)

        assert spawner.claude_path == "/custom/path/to/claude"

    @patch('services.compute_spawner.shutil.which')
    @patch('services.compute_spawner.os.path.isfile')
    def test_find_claude_cli_default(self, mock_isfile, mock_which, mock_workspaces_path):
        """Test default when claude CLI not found."""
        mock_isfile.return_value = False
        mock_which.return_value = None

        spawner = ComputeSpawner(workspaces_path=mock_workspaces_path)

        assert spawner.claude_path == "claude"

    @patch('services.compute_spawner.os.path.isfile')
    def test_find_claude_cli_standard_location(self, mock_isfile, mock_workspaces_path):
        """Test finding claude CLI in standard location."""
        def isfile_side_effect(path):
            return path == "/usr/local/bin/claude"
        mock_isfile.side_effect = isfile_side_effect

        spawner = ComputeSpawner(workspaces_path=mock_workspaces_path)

        assert spawner.claude_path == "/usr/local/bin/claude"

    @pytest.mark.asyncio
    async def test_initialize(self, spawner):
        """Test spawner initialization."""
        assert not spawner._initialized

        await spawner.initialize()

        assert spawner._initialized


# =============================================================================
# Test: Spawning
# =============================================================================

class TestComputeSpawnerSpawn:
    """Test compute instance spawning."""

    @pytest.mark.asyncio
    @patch('services.compute_spawner.ComputeSpawner._start_process')
    @patch('mcp.auth.generate_api_key')
    @patch('mcp.auth.register_compute_key')
    async def test_spawn_creates_workspace(
        self, mock_register, mock_gen_key, mock_start,
        spawner, spawn_request
    ):
        """Test that spawn creates workspace directory."""
        mock_gen_key.return_value = "test_api_key"
        mock_start.return_value = None

        response = await spawner.spawn(spawn_request)

        workspace_path = Path(spawner.workspaces_path) / spawn_request.compute_id
        assert workspace_path.exists()

    @pytest.mark.asyncio
    @patch('services.compute_spawner.ComputeSpawner._start_process')
    @patch('services.compute_spawner.ComputeSpawner._compose_skills')
    @patch('mcp.auth.generate_api_key')
    @patch('mcp.auth.register_compute_key')
    async def test_spawn_generates_claude_md(
        self, mock_register, mock_gen_key, mock_compose, mock_start,
        spawner, spawn_request
    ):
        """Test that spawn generates CLAUDE.md file."""
        mock_gen_key.return_value = "test_api_key"
        mock_compose.return_value = "# Test CLAUDE.md content"
        mock_start.return_value = None

        await spawner.spawn(spawn_request)

        workspace_path = Path(spawner.workspaces_path) / spawn_request.compute_id
        claude_md = workspace_path / "CLAUDE.md"
        assert claude_md.exists()
        assert claude_md.read_text() == "# Test CLAUDE.md content"

    @pytest.mark.asyncio
    @patch('services.compute_spawner.ComputeSpawner._start_process')
    @patch('services.compute_spawner.ComputeSpawner._compose_skills')
    @patch('mcp.auth.generate_api_key')
    @patch('mcp.auth.register_compute_key')
    async def test_spawn_creates_mcp_config(
        self, mock_register, mock_gen_key, mock_compose, mock_start,
        spawner, spawn_request
    ):
        """Test that spawn creates MCP config file."""
        mock_gen_key.return_value = "test_api_key"
        mock_compose.return_value = "# CLAUDE.md"
        mock_start.return_value = None

        await spawner.spawn(spawn_request)

        workspace_path = Path(spawner.workspaces_path) / spawn_request.compute_id
        mcp_config = workspace_path / "mcp.json"
        assert mcp_config.exists()

        config = json.loads(mcp_config.read_text())
        assert "mcpServers" in config
        assert "claudevn" in config["mcpServers"]

    @pytest.mark.asyncio
    @patch('services.compute_spawner.ComputeSpawner._start_process')
    @patch('services.compute_spawner.ComputeSpawner._compose_skills')
    @patch('mcp.auth.generate_api_key')
    @patch('mcp.auth.register_compute_key')
    async def test_spawn_returns_response(
        self, mock_register, mock_gen_key, mock_compose, mock_start,
        spawner, spawn_request
    ):
        """Test spawn response structure."""
        mock_gen_key.return_value = "test_api_key_123"
        mock_compose.return_value = "# CLAUDE.md"
        mock_start.return_value = None

        response = await spawner.spawn(spawn_request)

        assert isinstance(response, SpawnResponse)
        assert response.compute_id == spawn_request.compute_id
        assert response.api_key == "test_api_key_123"
        assert response.serving_url == spawner.serving_url

    @pytest.mark.asyncio
    @patch('services.compute_spawner.ComputeSpawner._start_process')
    @patch('services.compute_spawner.ComputeSpawner._compose_skills')
    @patch('mcp.auth.generate_api_key')
    @patch('mcp.auth.register_compute_key')
    async def test_spawn_registers_instance(
        self, mock_register, mock_gen_key, mock_compose, mock_start,
        spawner, spawn_request
    ):
        """Test that spawn registers the instance internally."""
        mock_gen_key.return_value = "test_api_key"
        mock_compose.return_value = "# CLAUDE.md"
        mock_start.return_value = None

        await spawner.spawn(spawn_request)

        assert spawn_request.compute_id in spawner._instances
        instance = spawner._instances[spawn_request.compute_id]
        assert instance.compute_id == spawn_request.compute_id
        assert instance.skills == spawn_request.skills

    @pytest.mark.asyncio
    @patch('services.compute_spawner.ComputeSpawner._start_process')
    @patch('services.compute_spawner.ComputeSpawner._compose_skills')
    @patch('mcp.auth.generate_api_key')
    @patch('mcp.auth.register_compute_key')
    async def test_spawn_auto_generates_id(
        self, mock_register, mock_gen_key, mock_compose, mock_start,
        spawner
    ):
        """Test spawn auto-generates compute ID if not provided."""
        mock_gen_key.return_value = "test_api_key"
        mock_compose.return_value = "# CLAUDE.md"
        mock_start.return_value = None

        request = SpawnRequest()  # No compute_id
        response = await spawner.spawn(request)

        assert response.compute_id.startswith("compute_")

    @pytest.mark.asyncio
    @patch('services.compute_spawner.ComputeSpawner._start_process')
    @patch('services.compute_spawner.ComputeSpawner._compose_skills')
    @patch('services.compute_spawner.ComputeSpawner._assign_initial_work')
    @patch('mcp.auth.generate_api_key')
    @patch('mcp.auth.register_compute_key')
    async def test_spawn_with_work_id(
        self, mock_register, mock_gen_key, mock_assign, mock_compose, mock_start,
        spawner
    ):
        """Test spawn with initial work assignment."""
        mock_gen_key.return_value = "test_api_key"
        mock_compose.return_value = "# CLAUDE.md"
        mock_start.return_value = None
        mock_assign.return_value = {"work_id": "work_123", "title": "Test Work"}

        request = SpawnRequest(
            compute_id="test_compute",
            work_id="work_123"
        )
        response = await spawner.spawn(request)

        mock_assign.assert_called_once()
        assert response.initial_work is not None
        assert response.initial_work["work_id"] == "work_123"

    @pytest.mark.asyncio
    @patch('services.compute_spawner.ComputeSpawner._start_process')
    @patch('services.compute_spawner.ComputeSpawner._compose_skills')
    @patch('mcp.auth.generate_api_key')
    @patch('mcp.auth.register_compute_key')
    async def test_spawn_with_project_id(
        self, mock_register, mock_gen_key, mock_compose, mock_start,
        spawner
    ):
        """Test spawn stores project_id in instance."""
        mock_gen_key.return_value = "test_api_key"
        mock_compose.return_value = "# CLAUDE.md"
        mock_start.return_value = None

        request = SpawnRequest(
            compute_id="test_compute",
            project_id="project_abc"
        )
        await spawner.spawn(request)

        instance = spawner._instances["test_compute"]
        assert instance.project_id == "project_abc"

    @pytest.mark.asyncio
    @patch('services.compute_spawner.ComputeSpawner._compose_skills')
    @patch('mcp.auth.generate_api_key')
    @patch('mcp.auth.register_compute_key')
    async def test_spawn_handles_start_failure(
        self, mock_register, mock_gen_key, mock_compose,
        spawner, spawn_request
    ):
        """Test spawn marks instance as failed on start error."""
        mock_gen_key.return_value = "test_api_key"
        mock_compose.return_value = "# CLAUDE.md"

        with patch.object(spawner, '_start_process', side_effect=Exception("Start failed")):
            with pytest.raises(Exception, match="Start failed"):
                await spawner.spawn(spawn_request)

            instance = spawner._instances[spawn_request.compute_id]
            assert instance.state == ComputeState.FAILED


# =============================================================================
# Test: Skill Composition
# =============================================================================

class TestSkillComposition:
    """Test skill composition functionality."""

    @pytest.mark.asyncio
    async def test_compose_skills_empty(self, spawner):
        """Test composing empty skill list returns default."""
        result = await spawner._compose_skills([], "compute_001")

        assert "ClaudeVN Compute Instance" in result
        assert "claudevn_report_progress" in result
        assert "claudevn_get_assignment" not in result  # Removed - work is pushed, not pulled

    @pytest.mark.asyncio
    @patch('services.marketplace_client.get_marketplace_client')
    async def test_compose_skills_single(self, mock_get_client, spawner):
        """Test composing a single skill."""
        mock_client = MagicMock()
        mock_client.get_skill = AsyncMock(return_value={
            "name": "Python Developer",
            "description": "Expert Python developer",
            "instructions": "Write clean Python code."
        })
        mock_get_client.return_value = mock_client

        result = await spawner._compose_skills(["skill_python"], "compute_001")

        assert "Python Developer" in result
        assert "Expert Python developer" in result
        assert "Write clean Python code" in result

    @pytest.mark.asyncio
    @patch('services.marketplace_client.get_marketplace_client')
    async def test_compose_skills_multiple(self, mock_get_client, spawner):
        """Test composing multiple skills."""
        skills_data = {
            "skill_python": {
                "name": "Python Developer",
                "description": "Python expertise",
                "instructions": "Python instructions"
            },
            "skill_testing": {
                "name": "Test Engineer",
                "description": "Testing expertise",
                "instructions": "Testing instructions"
            }
        }

        mock_client = MagicMock()
        mock_client.get_skill = AsyncMock(side_effect=lambda sid: skills_data.get(sid))
        mock_get_client.return_value = mock_client

        result = await spawner._compose_skills(
            ["skill_python", "skill_testing"],
            "compute_001"
        )

        assert "Python Developer" in result
        assert "Test Engineer" in result
        assert "Python instructions" in result
        assert "Testing instructions" in result

    @pytest.mark.asyncio
    @patch('services.marketplace_client.get_marketplace_client')
    async def test_compose_skills_handles_missing(self, mock_get_client, spawner):
        """Test compose handles missing skills gracefully."""
        mock_client = MagicMock()
        mock_client.get_skill = AsyncMock(return_value=None)
        mock_get_client.return_value = mock_client

        result = await spawner._compose_skills(["nonexistent"], "compute_001")

        # Should fall back to default
        assert "ClaudeVN Compute Instance" in result

    @pytest.mark.asyncio
    @patch('services.marketplace_client.get_marketplace_client')
    async def test_compose_skills_handles_error(self, mock_get_client, spawner):
        """Test compose handles API errors gracefully."""
        mock_get_client.side_effect = Exception("API error")

        result = await spawner._compose_skills(["skill_001"], "compute_001")

        # Should fall back to default
        assert "ClaudeVN Compute Instance" in result

    def test_default_claude_md_content(self, spawner):
        """Test default CLAUDE.md content structure."""
        result = spawner._default_claude_md("compute_test")

        assert "ClaudeVN Compute Instance: compute_test" in result
        assert "claudevn_report_progress" in result
        assert "claudevn_get_context" in result
        assert "claudevn_signal_blocker" in result
        assert "claudevn_complete_task" in result
        assert "claudevn_get_assignment" not in result  # Removed - work is pushed, not pulled
        assert "Your task assignment was provided" in result

    def test_create_mcp_config_structure(self, spawner):
        """Test MCP config structure."""
        config = spawner._create_mcp_config("compute_001", "api_key_123")

        assert "mcpServers" in config
        assert "claudevn" in config["mcpServers"]

        claudevn = config["mcpServers"]["claudevn"]
        assert claudevn["command"] == "python"
        assert "--serving-url" in claudevn["args"]
        assert "env" in claudevn
        assert claudevn["env"]["CLAUDEVN_COMPUTE_ID"] == "compute_001"
        assert claudevn["env"]["CLAUDEVN_API_KEY"] == "api_key_123"


# =============================================================================
# Test: Instance Management
# =============================================================================

class TestInstanceManagement:
    """Test instance management functionality."""

    @pytest.mark.asyncio
    async def test_get_instance_exists(self, spawner):
        """Test getting an existing instance."""
        instance = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.RUNNING,
            serving_url="http://localhost:8002",
            api_key="key_123"
        )
        spawner._instances["test_001"] = instance

        result = await spawner.get_instance("test_001")

        assert result is not None
        assert result.compute_id == "test_001"

    @pytest.mark.asyncio
    async def test_get_instance_not_found(self, spawner):
        """Test getting non-existent instance."""
        result = await spawner.get_instance("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_instances_empty(self, spawner):
        """Test listing instances when empty."""
        result = await spawner.list_instances()

        assert isinstance(result, ComputeListResponse)
        assert result.total == 0
        assert len(result.instances) == 0

    @pytest.mark.asyncio
    async def test_list_instances_all(self, spawner):
        """Test listing all instances."""
        # Add some test instances
        for i in range(3):
            spawner._instances[f"test_{i}"] = SpawnedCompute(
                compute_id=f"test_{i}",
                name=f"Test {i}",
                state=ComputeState.RUNNING,
                serving_url="http://localhost:8002",
                api_key=f"key_{i}"
            )

        result = await spawner.list_instances()

        assert result.total == 3
        assert len(result.instances) == 3

    @pytest.mark.asyncio
    async def test_list_instances_by_state(self, spawner):
        """Test listing instances filtered by state."""
        # Add instances with different states
        spawner._instances["running_1"] = SpawnedCompute(
            compute_id="running_1",
            name="Running 1",
            state=ComputeState.RUNNING,
            serving_url="http://localhost:8002",
            api_key="key_1"
        )
        spawner._instances["stopped_1"] = SpawnedCompute(
            compute_id="stopped_1",
            name="Stopped 1",
            state=ComputeState.STOPPED,
            serving_url="http://localhost:8002",
            api_key="key_2"
        )
        spawner._instances["running_2"] = SpawnedCompute(
            compute_id="running_2",
            name="Running 2",
            state=ComputeState.RUNNING,
            serving_url="http://localhost:8002",
            api_key="key_3"
        )

        result = await spawner.list_instances(state=ComputeState.RUNNING)

        assert len(result.instances) == 2
        assert all(i.state == ComputeState.RUNNING for i in result.instances)

    @pytest.mark.asyncio
    async def test_list_instances_by_state_stats(self, spawner):
        """Test that list returns correct by_state stats."""
        spawner._instances["running"] = SpawnedCompute(
            compute_id="running",
            name="Running",
            state=ComputeState.RUNNING,
            serving_url="http://localhost:8002",
            api_key="key_1"
        )
        spawner._instances["stopped"] = SpawnedCompute(
            compute_id="stopped",
            name="Stopped",
            state=ComputeState.STOPPED,
            serving_url="http://localhost:8002",
            api_key="key_2"
        )

        result = await spawner.list_instances()

        assert result.by_state["running"] == 1
        assert result.by_state["stopped"] == 1


# =============================================================================
# Test: Stop Instance
# =============================================================================

class TestStopInstance:
    """Test instance stopping functionality."""

    @pytest.mark.asyncio
    async def test_stop_instance_not_found(self, spawner):
        """Test stopping non-existent instance."""
        request = StopRequest(compute_id="nonexistent")
        result = await spawner.stop(request)

        assert result is False

    @pytest.mark.asyncio
    async def test_stop_instance_already_stopped(self, spawner):
        """Test stopping already stopped instance."""
        spawner._instances["test_001"] = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.STOPPED,
            serving_url="http://localhost:8002",
            api_key="key_123"
        )

        request = StopRequest(compute_id="test_001")
        result = await spawner.stop(request)

        assert result is True

    @pytest.mark.asyncio
    async def test_stop_instance_no_process(self, spawner):
        """Test stopping instance with no associated process."""
        spawner._instances["test_001"] = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.RUNNING,
            serving_url="http://localhost:8002",
            api_key="key_123"
        )

        request = StopRequest(compute_id="test_001")
        result = await spawner.stop(request)

        assert result is True
        assert spawner._instances["test_001"].state == ComputeState.STOPPED

    @pytest.mark.asyncio
    @patch('mcp.auth.revoke_compute_key')
    async def test_stop_instance_graceful(self, mock_revoke, spawner, mock_process):
        """Test graceful stop of instance."""
        spawner._instances["test_001"] = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.RUNNING,
            serving_url="http://localhost:8002",
            api_key="key_123"
        )
        spawner._processes["test_001"] = mock_process
        spawner._monitor_tasks["test_001"] = MagicMock()
        spawner._monitor_tasks["test_001"].cancel = MagicMock()

        request = StopRequest(compute_id="test_001", timeout=5)
        result = await spawner.stop(request)

        assert result is True
        mock_process.send_signal.assert_called_once()
        mock_revoke.assert_called_with("test_001")
        assert spawner._instances["test_001"].state == ComputeState.STOPPED

    @pytest.mark.asyncio
    @patch('mcp.auth.revoke_compute_key')
    async def test_stop_instance_force(self, mock_revoke, spawner):
        """Test force stop when graceful fails."""
        # Create instance
        spawner._instances["test_001"] = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.RUNNING,
            serving_url="http://localhost:8002",
            api_key="key_123"
        )

        # Create process that times out on graceful stop
        mock_process = MagicMock()
        mock_process.send_signal = MagicMock()
        mock_process.wait = AsyncMock(side_effect=[asyncio.TimeoutError(), None])
        mock_process.kill = MagicMock()
        spawner._processes["test_001"] = mock_process

        request = StopRequest(compute_id="test_001", force=True, timeout=1)
        result = await spawner.stop(request)

        assert result is True
        mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_instance_timeout_no_force(self, spawner):
        """Test timeout without force flag."""
        spawner._instances["test_001"] = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.RUNNING,
            serving_url="http://localhost:8002",
            api_key="key_123"
        )

        mock_process = MagicMock()
        mock_process.send_signal = MagicMock()
        mock_process.wait = AsyncMock(side_effect=asyncio.TimeoutError())
        spawner._processes["test_001"] = mock_process

        request = StopRequest(compute_id="test_001", force=False, timeout=1)
        result = await spawner.stop(request)

        assert result is False


# =============================================================================
# Test: Workspace Cleanup
# =============================================================================

class TestWorkspaceCleanup:
    """Test workspace and worktree cleanup functionality."""

    def test_cleanup_workspace_no_path(self, spawner):
        """Test cleanup when instance has no workspace path."""
        instance = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.STOPPED,
            serving_url="http://localhost:8002",
            api_key="test_key",
            workspace_path=None
        )

        # Should not raise, just return
        spawner._cleanup_workspace(instance)

    def test_cleanup_workspace_removes_worktrees(self, spawner, tmp_path):
        """Test that cleanup removes worktrees before directory."""
        # Create workspace structure
        workspace = tmp_path / "compute_001"
        workspace.mkdir()
        repo = workspace / "repo"
        repo.mkdir()
        active = workspace / "active"
        active.mkdir()
        main = workspace / "main"
        main.mkdir()

        instance = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.STOPPED,
            serving_url="http://localhost:8002",
            api_key="test_key",
            workspace_path=str(workspace),
            worktree_active=str(active)
        )

        # Mock repo_manager to track calls
        spawner._repo_manager.remove_worktree = MagicMock(return_value=True)
        spawner._repo_manager.prune_worktrees = MagicMock(return_value=True)

        spawner._cleanup_workspace(instance)

        # Verify worktree removal was attempted
        assert spawner._repo_manager.remove_worktree.call_count == 2
        spawner._repo_manager.prune_worktrees.assert_called_once_with(repo)

        # Verify workspace directory was removed
        assert not workspace.exists()

    def test_cleanup_workspace_continues_on_worktree_error(self, spawner, tmp_path):
        """Test cleanup continues even if worktree removal fails."""
        workspace = tmp_path / "compute_001"
        workspace.mkdir()
        repo = workspace / "repo"
        repo.mkdir()
        active = workspace / "active"
        active.mkdir()

        instance = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.STOPPED,
            serving_url="http://localhost:8002",
            api_key="test_key",
            workspace_path=str(workspace)
        )

        # Mock repo_manager to raise exception
        spawner._repo_manager.remove_worktree = MagicMock(
            side_effect=Exception("Git error")
        )
        spawner._repo_manager.prune_worktrees = MagicMock(return_value=True)

        # Should not raise, should continue to cleanup
        spawner._cleanup_workspace(instance)

        # Verify workspace was still removed despite worktree error
        assert not workspace.exists()

    def test_cleanup_workspace_no_repo_directory(self, spawner, tmp_path):
        """Test cleanup when repo directory doesn't exist."""
        workspace = tmp_path / "compute_001"
        workspace.mkdir()
        # Note: no repo subdirectory

        instance = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.STOPPED,
            serving_url="http://localhost:8002",
            api_key="test_key",
            workspace_path=str(workspace)
        )

        spawner._repo_manager.remove_worktree = MagicMock()

        spawner._cleanup_workspace(instance)

        # Should not attempt worktree removal if repo doesn't exist
        spawner._repo_manager.remove_worktree.assert_not_called()
        # But workspace should still be removed
        assert not workspace.exists()

    @pytest.mark.asyncio
    @patch('mcp.auth.revoke_compute_key')
    async def test_stop_triggers_cleanup(self, mock_revoke, spawner, mock_process, tmp_path):
        """Test that stop() calls cleanup on the workspace."""
        workspace = tmp_path / "compute_001"
        workspace.mkdir()

        spawner._instances["test_001"] = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.RUNNING,
            serving_url="http://localhost:8002",
            api_key="key_123",
            workspace_path=str(workspace)
        )
        spawner._processes["test_001"] = mock_process
        spawner._monitor_tasks["test_001"] = MagicMock()
        spawner._monitor_tasks["test_001"].cancel = MagicMock()

        request = StopRequest(compute_id="test_001", timeout=5)
        result = await spawner.stop(request)

        assert result is True
        # Verify workspace was cleaned up
        assert not workspace.exists()

    @pytest.mark.asyncio
    async def test_stop_no_process_still_cleans_workspace(self, spawner, tmp_path):
        """Test cleanup happens even when process is not tracked."""
        workspace = tmp_path / "compute_001"
        workspace.mkdir()

        spawner._instances["test_001"] = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.RUNNING,
            serving_url="http://localhost:8002",
            api_key="test_key",
            workspace_path=str(workspace)
        )
        # Note: no process registered

        request = StopRequest(compute_id="test_001")
        result = await spawner.stop(request)

        assert result is True
        assert not workspace.exists()


# =============================================================================
# Test: Metrics
# =============================================================================

class TestMetrics:
    """Test metrics functionality."""

    @pytest.mark.asyncio
    async def test_get_metrics_not_found(self, spawner):
        """Test getting metrics for non-existent instance."""
        result = await spawner.get_metrics("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_metrics_basic(self, spawner):
        """Test getting basic metrics."""
        now = datetime.now(timezone.utc)
        spawner._instances["test_001"] = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.RUNNING,
            serving_url="http://localhost:8002",
            api_key="key_123",
            started_at=now - timedelta(hours=1),
            completed_work=5,
            failed_work=1,
            current_work=["work_1", "work_2"]
        )

        result = await spawner.get_metrics("test_001")

        assert isinstance(result, ComputeMetrics)
        assert result.compute_id == "test_001"
        assert result.uptime_seconds >= 3600  # At least 1 hour
        assert result.work_completed == 5
        assert result.work_failed == 1
        assert result.current_work_count == 2

    @pytest.mark.asyncio
    async def test_get_metrics_stopped_instance(self, spawner):
        """Test getting metrics for stopped instance."""
        start = datetime.now(timezone.utc) - timedelta(hours=2)
        stop = datetime.now(timezone.utc) - timedelta(hours=1)

        spawner._instances["test_001"] = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.STOPPED,
            serving_url="http://localhost:8002",
            api_key="key_123",
            started_at=start,
            stopped_at=stop
        )

        result = await spawner.get_metrics("test_001")

        # Uptime should be ~1 hour (between start and stop)
        assert 3500 <= result.uptime_seconds <= 3700


# =============================================================================
# Test: Shutdown
# =============================================================================

class TestShutdown:
    """Test shutdown functionality."""

    @pytest.mark.asyncio
    async def test_shutdown_all_empty(self, spawner):
        """Test shutdown with no instances."""
        # Should not raise
        await spawner.shutdown()

    @pytest.mark.asyncio
    @patch.object(ComputeSpawner, 'stop')
    async def test_shutdown_all_instances(self, mock_stop, spawner):
        """Test shutdown stops all instances."""
        mock_stop.return_value = True

        # Add some instances
        for i in range(3):
            spawner._instances[f"test_{i}"] = SpawnedCompute(
                compute_id=f"test_{i}",
                name=f"Test {i}",
                state=ComputeState.RUNNING,
                serving_url="http://localhost:8002",
                api_key=f"key_{i}"
            )

        await spawner.shutdown()

        assert mock_stop.call_count == 3

    @pytest.mark.asyncio
    @patch.object(ComputeSpawner, 'stop')
    async def test_shutdown_continues_on_error(self, mock_stop, spawner):
        """Test shutdown continues even if individual stop fails."""
        mock_stop.side_effect = [Exception("Error"), True, True]

        for i in range(3):
            spawner._instances[f"test_{i}"] = SpawnedCompute(
                compute_id=f"test_{i}",
                name=f"Test {i}",
                state=ComputeState.RUNNING,
                serving_url="http://localhost:8002",
                api_key=f"key_{i}"
            )

        # Should not raise despite first stop failing
        await spawner.shutdown()

        assert mock_stop.call_count == 3


# =============================================================================
# Test: Start Process
# =============================================================================

class TestStartProcess:
    """Test process starting functionality."""

    @pytest.mark.asyncio
    @patch('asyncio.create_subprocess_exec')
    async def test_start_process_sets_environment(self, mock_subprocess, spawner, mock_process):
        """Test that start_process sets correct environment vars."""
        mock_subprocess.return_value = mock_process

        instance = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.PENDING,
            serving_url="http://localhost:8002",
            api_key="api_key_test",
            workspace_path=str(spawner.workspaces_path / "test_001")
        )
        spawner._instances["test_001"] = instance

        # Create workspace
        Path(instance.workspace_path).mkdir(parents=True, exist_ok=True)

        request = SpawnRequest(
            compute_id="test_001",
            work_id="work_123",
            project_id="project_456"
        )

        await spawner._start_process(instance, request)

        # Check that subprocess was called with environment containing our vars
        call_kwargs = mock_subprocess.call_args.kwargs
        env = call_kwargs['env']

        assert env["CLAUDEVN_COMPUTE_ID"] == "test_001"
        assert env["CLAUDEVN_SERVING_URL"] == "http://localhost:8002"
        assert env["CLAUDEVN_API_KEY"] == "api_key_test"
        assert env["CLAUDEVN_WORK_ID"] == "work_123"
        assert env["CLAUDEVN_PROJECT_ID"] == "project_456"

    @pytest.mark.asyncio
    @patch('asyncio.create_subprocess_exec')
    async def test_start_process_updates_state(self, mock_subprocess, spawner, mock_process):
        """Test that start_process updates instance state."""
        mock_subprocess.return_value = mock_process

        instance = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.PENDING,
            serving_url="http://localhost:8002",
            api_key="api_key_test",
            workspace_path=str(spawner.workspaces_path / "test_001")
        )
        spawner._instances["test_001"] = instance

        Path(instance.workspace_path).mkdir(parents=True, exist_ok=True)

        request = SpawnRequest(compute_id="test_001")
        await spawner._start_process(instance, request)

        assert instance.state == ComputeState.RUNNING
        assert instance.pid == 12345
        assert instance.started_at is not None

    @pytest.mark.asyncio
    @patch('asyncio.create_subprocess_exec')
    async def test_start_process_sends_initial_prompt(self, mock_subprocess, spawner, mock_process):
        """Test that start_process sends initial prompt."""
        mock_subprocess.return_value = mock_process

        instance = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.PENDING,
            serving_url="http://localhost:8002",
            api_key="api_key_test",
            workspace_path=str(spawner.workspaces_path / "test_001")
        )
        spawner._instances["test_001"] = instance

        Path(instance.workspace_path).mkdir(parents=True, exist_ok=True)

        request = SpawnRequest(compute_id="test_001")
        await spawner._start_process(instance, request)

        # Check that initial prompt was sent
        mock_process.stdin.write.assert_called()
        written = mock_process.stdin.write.call_args[0][0]
        assert b"Begin work" in written
        assert b"CLAUDE.md" in written

    @pytest.mark.asyncio
    @patch('asyncio.create_subprocess_exec')
    async def test_start_process_handles_failure(self, mock_subprocess, spawner):
        """Test start_process marks instance as failed on error."""
        mock_subprocess.side_effect = Exception("Process creation failed")

        instance = SpawnedCompute(
            compute_id="test_001",
            name="Test",
            state=ComputeState.PENDING,
            serving_url="http://localhost:8002",
            api_key="api_key_test",
            workspace_path=str(spawner.workspaces_path / "test_001")
        )
        spawner._instances["test_001"] = instance

        Path(instance.workspace_path).mkdir(parents=True, exist_ok=True)

        request = SpawnRequest(compute_id="test_001")

        with pytest.raises(Exception, match="Process creation failed"):
            await spawner._start_process(instance, request)

        assert instance.state == ComputeState.FAILED


# =============================================================================
# Test: Global Instance
# =============================================================================

class TestGlobalInstance:
    """Test global spawner instance management."""

    def test_set_get_spawner(self, spawner):
        """Test setting and getting global spawner."""
        set_compute_spawner(spawner)

        retrieved = get_compute_spawner()
        assert retrieved is spawner

    def test_get_spawner_not_initialized(self):
        """Test getting spawner when not initialized."""
        set_compute_spawner(None)

        with pytest.raises(RuntimeError, match="not initialized"):
            get_compute_spawner()


# =============================================================================
# Test: Git Worktree Setup
# =============================================================================

class TestWorktreeSetup:
    """Test Git worktree setup functionality."""

    @pytest.mark.asyncio
    @patch('services.compute_spawner.ComputeSpawner._start_process')
    @patch('services.compute_spawner.ComputeSpawner._setup_worktrees')
    @patch('services.compute_spawner.ComputeSpawner._compose_skills')
    @patch('mcp.auth.generate_api_key')
    @patch('mcp.auth.register_compute_key')
    async def test_spawn_with_repo_url_calls_setup_worktrees(
        self, mock_register, mock_gen_key, mock_compose, mock_setup_wt, mock_start,
        spawner
    ):
        """Test that spawn calls _setup_worktrees when repo_url is provided."""
        mock_gen_key.return_value = "test_api_key"
        mock_compose.return_value = "# CLAUDE.md"
        mock_start.return_value = None
        mock_setup_wt.return_value = "/path/to/workspace/active"

        request = SpawnRequest(
            compute_id="test_compute",
            repo_url="git@github.com:test/repo.git",
            base_branch="main"
        )
        response = await spawner.spawn(request)

        mock_setup_wt.assert_called_once()
        assert response.worktree_active == "/path/to/workspace/active"

    @pytest.mark.asyncio
    @patch('services.compute_spawner.ComputeSpawner._start_process')
    @patch('services.compute_spawner.ComputeSpawner._compose_skills')
    @patch('mcp.auth.generate_api_key')
    @patch('mcp.auth.register_compute_key')
    async def test_spawn_without_repo_url_skips_worktrees(
        self, mock_register, mock_gen_key, mock_compose, mock_start,
        spawner
    ):
        """Test that spawn skips worktree setup when no repo_url provided."""
        mock_gen_key.return_value = "test_api_key"
        mock_compose.return_value = "# CLAUDE.md"
        mock_start.return_value = None

        request = SpawnRequest(
            compute_id="test_compute"
            # No repo_url
        )
        response = await spawner.spawn(request)

        assert response.worktree_active is None

    @pytest.mark.asyncio
    @patch('services.compute_spawner.ComputeSpawner._compose_skills')
    @patch('mcp.auth.generate_api_key')
    @patch('mcp.auth.register_compute_key')
    async def test_spawn_worktree_setup_failure_raises(
        self, mock_register, mock_gen_key, mock_compose, spawner
    ):
        """Test that spawn fails when worktree setup fails."""
        mock_gen_key.return_value = "test_api_key"
        mock_compose.return_value = "# CLAUDE.md"

        with patch.object(
            spawner, '_setup_worktrees',
            side_effect=Exception("Clone failed")
        ):
            request = SpawnRequest(
                compute_id="test_compute",
                repo_url="git@github.com:test/repo.git"
            )

            with pytest.raises(Exception, match="Clone failed"):
                await spawner.spawn(request)

    @pytest.mark.asyncio
    async def test_setup_worktrees_creates_directory_structure(
        self, spawner, tmp_path
    ):
        """Test _setup_worktrees creates expected directory structure."""
        workspace = tmp_path / "test_workspace"
        workspace.mkdir()

        # Mock repo_manager methods
        with patch.object(
            spawner._repo_manager, 'clone_regular',
            return_value=workspace / "repo"
        ), patch.object(
            spawner._repo_manager, 'add_worktree',
            side_effect=[workspace / "main", workspace / "active"]
        ):
            result = await spawner._setup_worktrees(
                workspace=workspace,
                repo_url="git@github.com:test/repo.git",
                base_branch="main",
                compute_id="compute_001"
            )

            # Verify clone_regular was called correctly
            spawner._repo_manager.clone_regular.assert_called_once_with(
                url="git@github.com:test/repo.git",
                dest_path=workspace / "repo",
                ssh_key_path=None,
                branch="main"
            )

            # Verify worktrees were created
            assert spawner._repo_manager.add_worktree.call_count == 2

            # Verify the active worktree path is returned
            assert result == str(workspace / "active")

    @pytest.mark.asyncio
    async def test_setup_worktrees_uses_custom_base_branch(
        self, spawner, tmp_path
    ):
        """Test _setup_worktrees uses custom base branch."""
        workspace = tmp_path / "test_workspace"
        workspace.mkdir()

        with patch.object(
            spawner._repo_manager, 'clone_regular'
        ), patch.object(
            spawner._repo_manager, 'add_worktree'
        ):
            await spawner._setup_worktrees(
                workspace=workspace,
                repo_url="git@github.com:test/repo.git",
                base_branch="develop",
                compute_id="compute_001"
            )

            # Verify clone used custom branch
            spawner._repo_manager.clone_regular.assert_called_once()
            call_kwargs = spawner._repo_manager.clone_regular.call_args
            assert call_kwargs.kwargs['branch'] == "develop"

    @pytest.mark.asyncio
    async def test_setup_worktrees_creates_placeholder_branch(
        self, spawner, tmp_path
    ):
        """Test _setup_worktrees creates placeholder branch for active worktree."""
        workspace = tmp_path / "test_workspace"
        workspace.mkdir()

        with patch.object(
            spawner._repo_manager, 'clone_regular'
        ), patch.object(
            spawner._repo_manager, 'add_worktree'
        ):
            await spawner._setup_worktrees(
                workspace=workspace,
                repo_url="git@github.com:test/repo.git",
                base_branch="main",
                compute_id="compute_test_123"
            )

            # Find the call for the active worktree (second call)
            calls = spawner._repo_manager.add_worktree.call_args_list
            assert len(calls) == 2

            # Second call should create a new branch
            active_call = calls[1]
            assert active_call.kwargs.get('create_branch') is True
            assert "compute_test_123" in active_call.kwargs.get('branch', '')
            assert "work/" in active_call.kwargs.get('branch', '')
