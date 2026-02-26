"""Unit tests for Claude Code spawner functionality."""

import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call

import pytest

from services.claude_code_spawner import (
    ClaudeCodeSpawner,
    get_claude_code_spawner,
    set_claude_code_spawner,
    initialize_claude_code_spawner,
    _extract_json_from_output,
    _extract_json_with_key,
    _extract_characterization_json_from_output,
)
from services.claude_sdk_executor import ExecutionResult


def make_spawner(tmp_path, **kwargs):
    """Helper to create a ClaudeCodeSpawner without patching _find_claude_cli."""
    workspace = str(tmp_path / "workspace")
    defaults = dict(
        workspace_path=workspace,
        compute_id="compute-001",
        api_key="test-key",
    )
    defaults.update(kwargs)
    return ClaudeCodeSpawner(**defaults)


class TestClaudeCodeSpawnerInitialization:
    """Tests for ClaudeCodeSpawner initialization."""

    def test_init_with_defaults(self, tmp_path):
        """Test initialization with default parameters."""
        spawner = make_spawner(tmp_path)

        assert spawner.workspace_path == tmp_path / "workspace"
        assert spawner.serving_url == "http://localhost:8002"
        assert spawner.compute_id == "compute-001"
        assert spawner.api_key == "test-key"
        assert spawner.event_max_retries == 5
        assert spawner.event_base_delay == 1.0
        assert spawner._failed_events_count == 0
        assert len(spawner._instances) == 0
        assert len(spawner._execution_tasks) == 0
        assert spawner.workspace_path.exists()

    def test_init_with_custom_params(self, tmp_path):
        """Test initialization with custom parameters."""
        spawner = make_spawner(
            tmp_path,
            serving_url="http://serving:9000/",
            compute_id="compute-002",
            api_key="custom-key",
            event_max_retries=10,
            event_base_delay=2.0,
        )

        assert spawner.serving_url == "http://serving:9000"
        assert spawner.compute_id == "compute-002"
        assert spawner.event_max_retries == 10
        assert spawner.event_base_delay == 2.0

    def test_init_strips_trailing_slash(self, tmp_path):
        """Test that trailing slash is removed from serving_url."""
        spawner = make_spawner(tmp_path, serving_url="http://localhost:8002///")
        assert spawner.serving_url == "http://localhost:8002"

    def test_init_does_not_have_processes_or_monitor_tasks(self, tmp_path):
        """Test that the old subprocess attributes are not present."""
        spawner = make_spawner(tmp_path)
        assert not hasattr(spawner, "_processes")
        assert not hasattr(spawner, "_monitor_tasks")

    def test_init_has_execution_tasks(self, tmp_path):
        """Test that _execution_tasks dict is present."""
        spawner = make_spawner(tmp_path)
        assert hasattr(spawner, "_execution_tasks")
        assert isinstance(spawner._execution_tasks, dict)

    def test_init_claude_cli_path_deprecated_accepted(self, tmp_path):
        """Test that claude_cli_path is accepted (deprecated) but not stored as an attribute."""
        # Should not raise even when passing the deprecated param
        spawner = ClaudeCodeSpawner(
            workspace_path=str(tmp_path / "workspace"),
            compute_id="compute-001",
            api_key="test-key",
            claude_cli_path="/custom/path/claude",
        )
        # The attribute may or may not exist — what matters is no error and no
        # _find_claude_cli call. We just verify the spawner was created.
        assert spawner.compute_id == "compute-001"

    def test_init_serving_repo_url_none_by_default(self, tmp_path):
        """Test that serving_repo_url defaults to None."""
        spawner = make_spawner(tmp_path)
        assert spawner.serving_repo_url is None

    def test_init_serving_repo_url_stored(self, tmp_path):
        """Test that serving_repo_url is stored when provided."""
        spawner = make_spawner(tmp_path, serving_repo_url="git@github.com:Guarrdon/trueorc.git")
        assert spawner.serving_repo_url == "git@github.com:Guarrdon/trueorc.git"

    def test_serving_repo_path_constant(self, tmp_path):
        """Test that SERVING_REPO_PATH points to the standardized location."""
        spawner = make_spawner(tmp_path)
        assert str(spawner.SERVING_REPO_PATH).endswith(".claudevn/repos/serving")


class TestEnsureServingRepo:
    """Tests for _ensure_serving_repo method."""

    def test_no_op_when_no_url_configured(self, tmp_path):
        """Does nothing when serving_repo_url is not set."""
        spawner = make_spawner(tmp_path)
        with patch.object(spawner, "_run_git_command") as mock_git:
            spawner._ensure_serving_repo()
            mock_git.assert_not_called()

    def test_clones_when_repo_missing(self, tmp_path):
        """Performs shallow clone when repo path does not exist."""
        spawner = make_spawner(tmp_path, serving_repo_url="git@github.com:Guarrdon/trueorc.git")
        fake_repo_path = tmp_path / "serving_repo"

        with patch.object(ClaudeCodeSpawner, "SERVING_REPO_PATH", new=fake_repo_path):
            with patch.object(spawner, "_run_git_command") as mock_git:
                spawner._ensure_serving_repo()

                mock_git.assert_called_once_with(
                    ["clone", "--depth", "1", "git@github.com:Guarrdon/trueorc.git", str(fake_repo_path)],
                    git_token=None,
                )

    def test_pulls_when_repo_exists(self, tmp_path):
        """Runs git pull when repo path already exists."""
        spawner = make_spawner(tmp_path, serving_repo_url="git@github.com:Guarrdon/trueorc.git")
        fake_repo_path = tmp_path / "serving_repo"
        fake_repo_path.mkdir(parents=True)

        with patch.object(ClaudeCodeSpawner, "SERVING_REPO_PATH", new=fake_repo_path):
            with patch.object(spawner, "_run_git_command") as mock_git:
                spawner._ensure_serving_repo()

                mock_git.assert_called_once_with(
                    ["pull", "--ff-only", "origin", "main"],
                    cwd=fake_repo_path,
                    git_token=None,
                )

    def test_non_blocking_on_git_failure(self, tmp_path):
        """CalledProcessError during sync does not raise — logged as warning."""
        spawner = make_spawner(tmp_path, serving_repo_url="git@github.com:Guarrdon/trueorc.git")
        fake_repo_path = tmp_path / "serving_repo"

        err = subprocess.CalledProcessError(1, "git", stderr="fatal: not found")
        with patch.object(ClaudeCodeSpawner, "SERVING_REPO_PATH", new=fake_repo_path):
            with patch.object(spawner, "_run_git_command", side_effect=err):
                # Must not raise
                spawner._ensure_serving_repo()

    def test_non_blocking_on_unexpected_error(self, tmp_path):
        """Any exception during sync does not raise — logged as warning."""
        spawner = make_spawner(tmp_path, serving_repo_url="git@github.com:Guarrdon/trueorc.git")
        fake_repo_path = tmp_path / "serving_repo"

        with patch.object(ClaudeCodeSpawner, "SERVING_REPO_PATH", new=fake_repo_path):
            with patch.object(spawner, "_run_git_command", side_effect=OSError("disk full")):
                spawner._ensure_serving_repo()

    def test_uses_git_token_when_set(self, tmp_path):
        """Git token is forwarded to git commands when configured."""
        spawner = make_spawner(
            tmp_path,
            serving_repo_url="http://serving:8002/git/trueorc.git",
            git_token="cvn-ct-testtoken123",
        )
        fake_repo_path = tmp_path / "serving_repo"

        with patch.object(ClaudeCodeSpawner, "SERVING_REPO_PATH", new=fake_repo_path):
            with patch.object(spawner, "_run_git_command") as mock_git:
                spawner._ensure_serving_repo()

                mock_git.assert_called_once_with(
                    ["clone", "--depth", "1", "http://serving:8002/git/trueorc.git", str(fake_repo_path)],
                    git_token="cvn-ct-testtoken123",
                )


class TestCreateClaudeMd:
    """Tests for _create_claude_md method."""

    def test_create_claude_md_basic(self, tmp_path):
        """Test creating basic CLAUDE.md content."""
        spawner = make_spawner(tmp_path)

        event = {
            "task_id": "task-123",
            "title": "Test Task",
            "description": "This is a test task",
            "skills": {
                "merged_instructions": "# Skills\n\nUse pytest for testing."
            },
            "context": {}
        }

        content = spawner._create_claude_md(event)

        assert "# Task: Test Task" in content
        assert "**Task ID:** task-123" in content
        assert "## Description" in content
        assert "This is a test task" in content
        assert "## Skills" in content
        assert "Use pytest for testing." in content
        assert "## Output Format" in content

    def test_create_claude_md_with_context(self, tmp_path):
        """Test creating CLAUDE.md with full context."""
        spawner = make_spawner(tmp_path)

        event = {
            "task_id": "task-456",
            "title": "Feature Task",
            "description": "Implement new feature",
            "skills": {
                "merged_instructions": "Follow coding standards"
            },
            "context": {
                "repository": "https://github.com/test/repo",
                "base_branch": "main",
                "relevant_files": ["src/app.py", "tests/test_app.py"],
                "requirements": "Must maintain backward compatibility"
            }
        }

        content = spawner._create_claude_md(event)

        assert "**Repository:** https://github.com/test/repo" in content
        assert "**Base Branch:** main" in content
        assert "**Relevant Files:**" in content
        assert "  - src/app.py" in content
        assert "  - tests/test_app.py" in content
        assert "**Requirements:**" in content
        assert "Must maintain backward compatibility" in content

    def test_create_claude_md_no_skills(self, tmp_path):
        """Test creating CLAUDE.md with no merged instructions."""
        spawner = make_spawner(tmp_path)

        event = {
            "task_id": "task-789",
            "title": "Simple Task",
            "description": "Do something",
            "skills": {},
            "context": {}
        }

        content = spawner._create_claude_md(event)

        assert "## Skills" in content
        assert "No specific skills provided." in content

    def test_create_claude_md_includes_serving_repo_when_present(self, tmp_path):
        """Serving Repository section appears when repo is configured and cloned."""
        fake_repo_path = tmp_path / "serving_repo"
        fake_repo_path.mkdir(parents=True)

        spawner = make_spawner(
            tmp_path,
            serving_repo_url="git@github.com:Guarrdon/trueorc.git",
        )
        event = {
            "task_id": "task-decomp",
            "title": "Decompose Goal",
            "description": "Break down the goal",
            "skills": {},
            "context": {},
        }

        with patch.object(ClaudeCodeSpawner, "SERVING_REPO_PATH", new=fake_repo_path):
            content = spawner._create_claude_md(event)

        assert "## Serving Repository" in content
        assert str(fake_repo_path) in content

    def test_create_claude_md_omits_serving_repo_when_not_configured(self, tmp_path):
        """No Serving Repository section when serving_repo_url is None."""
        spawner = make_spawner(tmp_path)
        event = {
            "task_id": "task-plain",
            "title": "Plain Task",
            "description": "Do work",
            "skills": {},
            "context": {},
        }

        content = spawner._create_claude_md(event)
        assert "## Serving Repository" not in content

    def test_create_claude_md_omits_serving_repo_when_not_yet_cloned(self, tmp_path):
        """No Serving Repository section when URL is set but clone hasn't happened yet."""
        fake_repo_path = tmp_path / "not_cloned_yet"
        # Do NOT create the directory

        spawner = make_spawner(
            tmp_path,
            serving_repo_url="git@github.com:Guarrdon/trueorc.git",
        )
        event = {
            "task_id": "task-no-clone",
            "title": "Task before clone",
            "description": "Work",
            "skills": {},
            "context": {},
        }

        with patch.object(ClaudeCodeSpawner, "SERVING_REPO_PATH", new=fake_repo_path):
            content = spawner._create_claude_md(event)

        assert "## Serving Repository" not in content


class TestSpawnMethod:
    """Tests for spawn method."""

    @pytest.mark.asyncio
    async def test_spawn_no_task_id(self, tmp_path):
        """Test spawn with missing task_id."""
        spawner = make_spawner(tmp_path)

        event = {"title": "Task without ID"}
        result = await spawner.spawn(event)

        assert result is False

    @pytest.mark.asyncio
    async def test_spawn_duplicate_task(self, tmp_path):
        """Test spawn with already running task."""
        spawner = make_spawner(tmp_path)

        # Simulate existing instance
        spawner._instances["task-123"] = {
            "instance_id": "cc-existing",
            "task_id": "task-123"
        }

        event = {"task_id": "task-123"}
        result = await spawner.spawn(event)

        assert result is False

    @pytest.mark.asyncio
    async def test_spawn_success(self, tmp_path):
        """Test successful spawn."""
        spawner = make_spawner(tmp_path)

        event = {
            "task_id": "task-123",
            "title": "Test Task",
            "description": "Test description",
            "skills": {"merged_instructions": "Test skills"},
            "context": {},
            "mcp_config": {}
        }

        with patch.object(spawner, '_start_task', new_callable=AsyncMock) as mock_start, \
             patch.object(spawner, '_setup_mcp_tools', return_value={}) as mock_mcp, \
             patch.object(spawner, 'send_claude_code_started', new_callable=AsyncMock) as mock_started:

            result = await spawner.spawn(event)

        assert result is True
        assert "task-123" in spawner._instances

        # Verify instance metadata
        instance = spawner._instances["task-123"]
        assert instance["task_id"] == "task-123"
        assert "instance_id" in instance
        assert instance["instance_id"].startswith("cc-")
        assert "workspace" in instance
        assert "started_at" in instance

        # Verify workspace was created
        workspace_path = Path(instance["workspace"])
        assert workspace_path.exists()

        # Verify CLAUDE.md was created
        claude_md = workspace_path / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text()
        assert "Test Task" in content

        # Verify _start_task was called
        mock_start.assert_called_once()
        mock_started.assert_called_once()

    @pytest.mark.asyncio
    async def test_spawn_task_fails(self, tmp_path):
        """Test spawn when task start fails."""
        spawner = make_spawner(tmp_path)

        event = {
            "task_id": "task-123",
            "title": "Test Task",
            "description": "Test",
            "skills": {},
            "context": {},
            "mcp_config": {}
        }

        with patch.object(spawner, '_start_task', new_callable=AsyncMock) as mock_start, \
             patch.object(spawner, '_setup_mcp_tools', return_value={}) as mock_mcp, \
             patch.object(spawner, 'send_claude_code_failed', new_callable=AsyncMock) as mock_failed:

            mock_start.side_effect = Exception("Task failed")
            result = await spawner.spawn(event)

        assert result is False
        assert "task-123" not in spawner._instances
        mock_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_spawn_setup_mcp_tools_returns_dict(self, tmp_path):
        """Test that _setup_mcp_tools returns a dict passed to _start_task."""
        spawner = make_spawner(tmp_path)

        event = {
            "task_id": "task-mcp",
            "title": "MCP Task",
            "description": "Test MCP",
            "skills": {},
            "context": {},
            "mcp_config": {}
        }

        mcp_config = {"claudevn": {"type": "stdio", "command": "python"}}

        captured_args = {}

        async def capture_start_task(task_id, instance_id, working_dir, event, mcp_servers):
            captured_args["mcp_servers"] = mcp_servers

        with patch.object(spawner, '_setup_mcp_tools', return_value=mcp_config), \
             patch.object(spawner, '_start_task', side_effect=capture_start_task), \
             patch.object(spawner, 'send_claude_code_started', new_callable=AsyncMock):

            result = await spawner.spawn(event)

        assert result is True
        assert captured_args["mcp_servers"] == mcp_config


class TestStartTask:
    """Tests for _start_task method — launches _run_and_handle_result as an async task."""

    @pytest.mark.asyncio
    async def test_start_task_creates_execution_task(self, tmp_path):
        """Test that _start_task creates an asyncio.Task in _execution_tasks."""
        spawner = make_spawner(tmp_path)

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()

        event = {
            "task_id": "task-123",
            "context": {}
        }

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "task_id": "task-123",
            "workspace": str(instance_workspace),
            "started_at": datetime.now(timezone.utc)
        }

        mcp_servers = {}

        # Patch _run_and_handle_result so the task doesn't actually run
        with patch.object(spawner, '_run_and_handle_result', new_callable=AsyncMock):
            await spawner._start_task(
                "task-123", "cc-instance", instance_workspace, event, mcp_servers
            )

        assert "task-123" in spawner._execution_tasks
        task = spawner._execution_tasks["task-123"]
        assert isinstance(task, asyncio.Task)

        # Cancel to clean up
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    @pytest.mark.asyncio
    async def test_start_task_sets_env_vars(self, tmp_path):
        """Test that _start_task passes correct env_vars to _run_and_handle_result."""
        spawner = make_spawner(
            tmp_path,
            serving_url="http://localhost:8002",
            compute_id="compute-001",
        )

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()

        event = {
            "task_id": "task-123",
            "context": {
                "repository": "https://github.com/test/repo",
                "base_branch": "develop"
            }
        }

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "task_id": "task-123",
            "workspace": str(instance_workspace),
            "started_at": datetime.now(timezone.utc)
        }

        captured = {}

        async def capture_run(task_id, instance_id, prompt, cwd, mcp_servers, env_vars):
            captured["env_vars"] = env_vars

        with patch.object(spawner, '_run_and_handle_result', side_effect=capture_run):
            await spawner._start_task(
                "task-123", "cc-instance", instance_workspace, event, {}
            )

        # Let the task run
        task = spawner._execution_tasks.get("task-123")
        if task:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass

        env = captured.get("env_vars", {})
        assert env.get("CLAUDEVN_COMPUTE_ID") == "compute-001"
        assert env.get("CLAUDEVN_TASK_ID") == "task-123"
        assert env.get("CLAUDEVN_INSTANCE_ID") == "cc-instance"
        assert env.get("CLAUDEVN_SERVING_URL") == "http://localhost:8002"
        assert env.get("CLAUDEVN_REPOSITORY") == "https://github.com/test/repo"
        assert env.get("CLAUDEVN_BASE_BRANCH") == "develop"

    @pytest.mark.asyncio
    async def test_start_task_sets_git_askpass_from_context(self, tmp_path):
        """Test that GIT_ASKPASS is set when git_token is in context."""
        spawner = make_spawner(tmp_path)

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()

        # Create the directory where GIT_ASKPASS script will be written
        askpass_dir = tmp_path / "workspace" / "cc-token"
        askpass_dir.mkdir(parents=True, exist_ok=True)

        event = {
            "task_id": "task-token",
            "context": {
                "git_token": "cvn-ct-testtoken123",
                "repository": "http://serving:8002/git/repo.git"
            }
        }

        spawner._instances["task-token"] = {
            "instance_id": "cc-token",
            "task_id": "task-token",
            "workspace": str(instance_workspace),
            "started_at": datetime.now(timezone.utc)
        }

        captured = {}

        async def capture_run(task_id, instance_id, prompt, cwd, mcp_servers, env_vars):
            captured["env_vars"] = env_vars

        with patch.object(spawner, '_run_and_handle_result', side_effect=capture_run):
            await spawner._start_task("task-token", "cc-token", instance_workspace, event, {})

        task = spawner._execution_tasks.get("task-token")
        if task:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass

        env = captured.get("env_vars", {})
        assert "GIT_ASKPASS" in env
        assert "GIT_TERMINAL_PROMPT" in env
        assert env["GIT_TERMINAL_PROMPT"] == "0"

    @pytest.mark.asyncio
    async def test_start_task_sets_git_askpass_from_spawner_token(self, tmp_path):
        """Test that GIT_ASKPASS falls back to spawner's git_token."""
        spawner = make_spawner(tmp_path, git_token="cvn-ct-spawnertoken")

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()

        # Create the directory where GIT_ASKPASS script will be written
        askpass_dir = tmp_path / "workspace" / "cc-fb"
        askpass_dir.mkdir(parents=True, exist_ok=True)

        event = {
            "task_id": "task-fb",
            "context": {}  # No git_token in context
        }

        spawner._instances["task-fb"] = {
            "instance_id": "cc-fb",
            "task_id": "task-fb",
            "workspace": str(instance_workspace),
            "started_at": datetime.now(timezone.utc)
        }

        captured = {}

        async def capture_run(task_id, instance_id, prompt, cwd, mcp_servers, env_vars):
            captured["env_vars"] = env_vars

        with patch.object(spawner, '_run_and_handle_result', side_effect=capture_run):
            await spawner._start_task("task-fb", "cc-fb", instance_workspace, event, {})

        task = spawner._execution_tasks.get("task-fb")
        if task:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass

        env = captured.get("env_vars", {})
        assert "GIT_ASKPASS" in env

    @pytest.mark.asyncio
    async def test_start_task_no_git_askpass_without_token(self, tmp_path):
        """Test that GIT_ASKPASS is NOT set when no Git token is available."""
        spawner = make_spawner(tmp_path)  # No git_token

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()

        event = {
            "task_id": "task-nokey",
            "context": {}
        }

        spawner._instances["task-nokey"] = {
            "instance_id": "cc-nokey",
            "task_id": "task-nokey",
            "workspace": str(instance_workspace),
            "started_at": datetime.now(timezone.utc)
        }

        captured = {}

        async def capture_run(task_id, instance_id, prompt, cwd, mcp_servers, env_vars):
            captured["env_vars"] = env_vars

        with patch.object(spawner, '_run_and_handle_result', side_effect=capture_run):
            await spawner._start_task("task-nokey", "cc-nokey", instance_workspace, event, {})

        task = spawner._execution_tasks.get("task-nokey")
        if task:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass

        env = captured.get("env_vars", {})
        assert "GIT_ASKPASS" not in env


class TestRunAndHandleResult:
    """Tests for _run_and_handle_result method."""

    @pytest.mark.asyncio
    async def test_run_and_handle_result_success(self, tmp_path):
        """Test that a successful ExecutionResult sends completed event."""
        spawner = make_spawner(tmp_path)

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "started_at": datetime.now(timezone.utc),
            "repo_path": None,
        }

        success_result = ExecutionResult(
            success=True,
            exit_code=0,
            output="done",
            duration_ms=5000,
            tool_calls=[]
        )

        with patch('services.claude_code_spawner.execute_task',
                   new_callable=AsyncMock, return_value=success_result), \
             patch.object(spawner, '_submit_result', new_callable=AsyncMock), \
             patch.object(spawner, 'send_claude_code_completed',
                          new_callable=AsyncMock) as mock_completed, \
             patch.object(spawner, '_cleanup_instance') as mock_cleanup:

            await spawner._run_and_handle_result(
                task_id="task-123",
                instance_id="cc-instance",
                prompt="Read CLAUDE.md and do the work.",
                cwd=tmp_path,
                mcp_servers={},
                env_vars={},
            )

        mock_completed.assert_called_once()
        call_kwargs = mock_completed.call_args.kwargs
        assert call_kwargs["task_id"] == "task-123"
        assert call_kwargs["instance_id"] == "cc-instance"
        assert call_kwargs["exit_code"] == 0
        mock_cleanup.assert_called_once_with("task-123")

    @pytest.mark.asyncio
    async def test_run_and_handle_result_failure(self, tmp_path):
        """Test that a failed ExecutionResult sends failed event."""
        spawner = make_spawner(tmp_path)

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "started_at": datetime.now(timezone.utc),
            "repo_path": None,
        }

        fail_result = ExecutionResult(
            success=False,
            exit_code=1,
            output="",
            error="SDK execution failed",
            tool_calls=[]
        )

        with patch('services.claude_code_spawner.execute_task',
                   new_callable=AsyncMock, return_value=fail_result), \
             patch.object(spawner, 'send_claude_code_failed',
                          new_callable=AsyncMock) as mock_failed, \
             patch.object(spawner, '_cleanup_instance') as mock_cleanup:

            await spawner._run_and_handle_result(
                task_id="task-123",
                instance_id="cc-instance",
                prompt="Read CLAUDE.md and do the work.",
                cwd=tmp_path,
                mcp_servers={},
                env_vars={},
            )

        mock_failed.assert_called_once()
        call_kwargs = mock_failed.call_args.kwargs
        assert call_kwargs["task_id"] == "task-123"
        assert call_kwargs["exit_code"] == 1
        mock_cleanup.assert_called_once_with("task-123")

    @pytest.mark.asyncio
    async def test_run_and_handle_result_cancelled(self, tmp_path):
        """Test that CancelledError is handled gracefully."""
        spawner = make_spawner(tmp_path)

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "started_at": datetime.now(timezone.utc),
            "repo_path": None,
        }

        with patch('services.claude_code_spawner.execute_task',
                   new_callable=AsyncMock, side_effect=asyncio.CancelledError), \
             patch.object(spawner, '_cleanup_instance') as mock_cleanup:

            await spawner._run_and_handle_result(
                task_id="task-123",
                instance_id="cc-instance",
                prompt="Read CLAUDE.md.",
                cwd=tmp_path,
                mcp_servers={},
                env_vars={},
            )

        mock_cleanup.assert_called_once_with("task-123")

    @pytest.mark.asyncio
    async def test_run_and_handle_result_exception(self, tmp_path):
        """Test that unexpected exceptions send failed event."""
        spawner = make_spawner(tmp_path)

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "started_at": datetime.now(timezone.utc),
            "repo_path": None,
        }

        with patch('services.claude_code_spawner.execute_task',
                   new_callable=AsyncMock, side_effect=Exception("Unexpected error")), \
             patch.object(spawner, 'send_claude_code_failed',
                          new_callable=AsyncMock) as mock_failed, \
             patch.object(spawner, '_cleanup_instance') as mock_cleanup:

            await spawner._run_and_handle_result(
                task_id="task-123",
                instance_id="cc-instance",
                prompt="Read CLAUDE.md.",
                cwd=tmp_path,
                mcp_servers={},
                env_vars={},
            )

        mock_failed.assert_called_once()
        call_kwargs = mock_failed.call_args.kwargs
        assert "Unexpected error" in call_kwargs["error"]
        assert call_kwargs["exit_code"] == -1
        mock_cleanup.assert_called_once_with("task-123")

    @pytest.mark.asyncio
    async def test_run_and_handle_result_push_failure_sends_failed(self, tmp_path):
        """Test that git push failure sends failed event even when execution succeeded."""
        spawner = make_spawner(tmp_path)
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "started_at": datetime.now(timezone.utc),
            "repo_path": str(repo_dir),
            "branch_name": "feat/test",
        }

        success_result = ExecutionResult(
            success=True,
            exit_code=0,
            output="done",
            tool_calls=[]
        )

        with patch('services.claude_code_spawner.execute_task',
                   new_callable=AsyncMock, return_value=success_result), \
             patch.object(spawner, '_commit_and_push_changes',
                          new_callable=AsyncMock, return_value=False), \
             patch.object(spawner, 'send_claude_code_failed',
                          new_callable=AsyncMock) as mock_failed, \
             patch.object(spawner, '_cleanup_instance'):

            await spawner._run_and_handle_result(
                task_id="task-123",
                instance_id="cc-instance",
                prompt="Read CLAUDE.md.",
                cwd=tmp_path,
                mcp_servers={},
                env_vars={},
            )

        mock_failed.assert_called_once()
        call_kwargs = mock_failed.call_args.kwargs
        assert "push failed" in call_kwargs["error"].lower() or "push" in call_kwargs["error"].lower()


class TestStopMethod:
    """Tests for stop method."""

    @pytest.mark.asyncio
    async def test_stop_nonexistent_task(self, tmp_path):
        """Test stopping a task that doesn't exist."""
        spawner = make_spawner(tmp_path)

        result = await spawner.stop("nonexistent-task")
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_no_execution_task(self, tmp_path):
        """Test stopping a task with no associated execution task."""
        spawner = make_spawner(tmp_path)

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "task_id": "task-123"
        }

        with patch.object(spawner, '_cleanup_instance') as mock_cleanup:
            result = await spawner.stop("task-123")

        assert result is True
        mock_cleanup.assert_called_once_with("task-123")

    @pytest.mark.asyncio
    async def test_stop_cancels_execution_task(self, tmp_path):
        """Test that stop cancels the async execution task."""
        spawner = make_spawner(tmp_path)

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "task_id": "task-123"
        }

        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.cancel = Mock()
        spawner._execution_tasks["task-123"] = mock_task

        with patch('asyncio.wait_for', new_callable=AsyncMock) as mock_wait, \
             patch.object(spawner, '_cleanup_instance') as mock_cleanup:

            result = await spawner.stop("task-123")

        assert result is True
        mock_task.cancel.assert_called_once()
        mock_cleanup.assert_called_once_with("task-123")

    @pytest.mark.asyncio
    async def test_stop_handles_cancelled_error(self, tmp_path):
        """Test that stop handles CancelledError from the task gracefully."""
        spawner = make_spawner(tmp_path)

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "task_id": "task-123"
        }

        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.cancel = Mock()
        spawner._execution_tasks["task-123"] = mock_task

        with patch('asyncio.wait_for',
                   new_callable=AsyncMock, side_effect=asyncio.CancelledError), \
             patch.object(spawner, '_cleanup_instance') as mock_cleanup:

            result = await spawner.stop("task-123")

        assert result is True
        mock_cleanup.assert_called_once_with("task-123")

    @pytest.mark.asyncio
    async def test_stop_handles_timeout_error(self, tmp_path):
        """Test that stop handles TimeoutError gracefully."""
        spawner = make_spawner(tmp_path)

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "task_id": "task-123"
        }

        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.cancel = Mock()
        spawner._execution_tasks["task-123"] = mock_task

        with patch('asyncio.wait_for',
                   new_callable=AsyncMock, side_effect=asyncio.TimeoutError), \
             patch.object(spawner, '_cleanup_instance') as mock_cleanup:

            result = await spawner.stop("task-123")

        assert result is True
        mock_cleanup.assert_called_once_with("task-123")


class TestCleanupInstance:
    """Tests for _cleanup_instance method."""

    def test_cleanup_instance(self, tmp_path):
        """Test cleaning up instance resources."""
        spawner = make_spawner(tmp_path)

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "workspace": str(tmp_path / "instance")
        }
        mock_task = MagicMock(spec=asyncio.Task)
        spawner._execution_tasks["task-123"] = mock_task

        spawner._cleanup_instance("task-123")

        assert "task-123" not in spawner._instances
        assert "task-123" not in spawner._execution_tasks

    def test_cleanup_nonexistent_instance(self, tmp_path):
        """Test cleanup of nonexistent instance doesn't raise error."""
        spawner = make_spawner(tmp_path)

        # Should not raise
        spawner._cleanup_instance("nonexistent")

    def test_cleanup_instance_no_execution_task(self, tmp_path):
        """Test cleanup when no execution task is tracked."""
        spawner = make_spawner(tmp_path)

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "workspace": str(tmp_path / "instance")
        }
        # No entry in _execution_tasks

        spawner._cleanup_instance("task-123")

        assert "task-123" not in spawner._instances


class TestLifecycleEvents:
    """Tests for lifecycle event methods."""

    @pytest.mark.asyncio
    async def test_send_claude_code_started(self, tmp_path):
        """Test sending claude_code_started event."""
        spawner = make_spawner(
            tmp_path,
            serving_url="http://localhost:8002",
            compute_id="compute-001",
        )

        with patch.object(spawner, '_send_event', new_callable=AsyncMock) as mock_send:
            await spawner.send_claude_code_started("task-123", "cc-instance")

        mock_send.assert_called_once()
        event = mock_send.call_args[0][0]

        assert event["event"] == "claude_code_started"
        assert event["compute_id"] == "compute-001"
        assert event["task_id"] == "task-123"
        assert event["instance_id"] == "cc-instance"
        assert "timestamp" in event

    @pytest.mark.asyncio
    async def test_send_claude_code_completed(self, tmp_path):
        """Test sending claude_code_completed event."""
        spawner = make_spawner(tmp_path)

        with patch.object(spawner, '_send_event', new_callable=AsyncMock) as mock_send:
            await spawner.send_claude_code_completed(
                task_id="task-123",
                instance_id="cc-instance",
                exit_code=0,
                duration_seconds=120
            )

        event = mock_send.call_args[0][0]

        assert event["event"] == "claude_code_completed"
        assert event["task_id"] == "task-123"
        assert event["exit_code"] == 0
        assert event["duration_seconds"] == 120

    @pytest.mark.asyncio
    async def test_send_claude_code_failed(self, tmp_path):
        """Test sending claude_code_failed event."""
        spawner = make_spawner(tmp_path)

        with patch.object(spawner, '_send_event', new_callable=AsyncMock) as mock_send:
            await spawner.send_claude_code_failed(
                task_id="task-123",
                instance_id="cc-instance",
                error="Process crashed",
                exit_code=1
            )

        event = mock_send.call_args[0][0]

        assert event["event"] == "claude_code_failed"
        assert event["error"] == "Process crashed"
        assert event["exit_code"] == 1


class TestSendEvent:
    """Tests for _send_event method with retry logic."""

    @pytest.mark.asyncio
    async def test_send_event_success_first_attempt(self, tmp_path):
        """Test successfully sending an event on first attempt."""
        spawner = make_spawner(
            tmp_path,
            serving_url="http://localhost:8002",
            compute_id="compute-001",
        )

        event = {
            "event": "test_event",
            "data": "test"
        }

        mock_response = Mock()
        mock_response.status_code = 200

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock()

            result = await spawner._send_event(event)

        assert result is True
        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args

        assert args[0] == "http://localhost:8002/api/v1/compute/events"
        assert kwargs["json"] == event
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
        assert spawner._failed_events_count == 0

    @pytest.mark.asyncio
    async def test_send_event_retry_on_http_error(self, tmp_path):
        """Test retry on HTTP error with eventual success."""
        spawner = make_spawner(
            tmp_path,
            serving_url="http://localhost:8002",
            event_max_retries=3,
            event_base_delay=0.01,
        )

        event = {"event": "test_event"}

        mock_fail = Mock()
        mock_fail.status_code = 500
        mock_success = Mock()
        mock_success.status_code = 200

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[mock_fail, mock_fail, mock_success])
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock()

            result = await spawner._send_event(event)

        assert result is True
        assert mock_client.post.call_count == 3
        assert spawner._failed_events_count == 0

    @pytest.mark.asyncio
    async def test_send_event_retry_on_exception(self, tmp_path):
        """Test retry on network exception with eventual success."""
        spawner = make_spawner(
            tmp_path,
            serving_url="http://localhost:8002",
            event_max_retries=3,
            event_base_delay=0.01,
        )

        event = {"event": "test_event"}

        mock_success = Mock()
        mock_success.status_code = 200

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[
                Exception("Connection refused"),
                mock_success
            ])
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock()

            result = await spawner._send_event(event)

        assert result is True
        assert mock_client.post.call_count == 2
        assert spawner._failed_events_count == 0

    @pytest.mark.asyncio
    async def test_send_event_all_retries_exhausted(self, tmp_path):
        """Test event is lost after all retries exhausted."""
        spawner = make_spawner(
            tmp_path,
            serving_url="http://localhost:8002",
            event_max_retries=3,
            event_base_delay=0.01,
        )

        event = {"event": "test_event"}

        mock_fail = Mock()
        mock_fail.status_code = 500

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_fail)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock()

            result = await spawner._send_event(event)

        assert result is False
        assert mock_client.post.call_count == 3  # All retries attempted
        assert spawner._failed_events_count == 1

    @pytest.mark.asyncio
    async def test_send_event_exception_all_retries_exhausted(self, tmp_path):
        """Test event is lost after all retries exhausted due to exceptions."""
        spawner = make_spawner(
            tmp_path,
            serving_url="http://localhost:8002",
            event_max_retries=2,
            event_base_delay=0.01,
        )

        event = {"event": "test_event"}

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("Network error"))
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock()

            result = await spawner._send_event(event)

        assert result is False
        assert mock_client.post.call_count == 2
        assert spawner._failed_events_count == 1

    @pytest.mark.asyncio
    async def test_send_event_failed_count_accumulates(self, tmp_path):
        """Test failed event count accumulates across multiple failed events."""
        spawner = make_spawner(
            tmp_path,
            serving_url="http://localhost:8002",
            event_max_retries=1,
            event_base_delay=0.01,
        )

        mock_fail = Mock()
        mock_fail.status_code = 503

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_fail)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock()

            await spawner._send_event({"event": "event1"})
            await spawner._send_event({"event": "event2"})
            await spawner._send_event({"event": "event3"})

        assert spawner._failed_events_count == 3

    @pytest.mark.asyncio
    async def test_send_event_custom_retry_config(self, tmp_path):
        """Test custom retry configuration is respected."""
        spawner = make_spawner(
            tmp_path,
            serving_url="http://localhost:8002",
            event_max_retries=7,
            event_base_delay=0.5,
        )

        assert spawner.event_max_retries == 7
        assert spawner.event_base_delay == 0.5

    @pytest.mark.asyncio
    async def test_send_event_exponential_backoff_timing(self, tmp_path):
        """Test exponential backoff delay increases correctly."""
        spawner = make_spawner(
            tmp_path,
            serving_url="http://localhost:8002",
            event_max_retries=4,
            event_base_delay=0.01,
        )

        event = {"event": "test_event"}

        mock_fail = Mock()
        mock_fail.status_code = 500

        sleep_calls = []

        async def mock_sleep(delay):
            sleep_calls.append(delay)

        with patch('httpx.AsyncClient') as mock_client_class, \
             patch('asyncio.sleep', side_effect=mock_sleep):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_fail)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock()

            await spawner._send_event(event)

        # Should have 3 sleeps (before retries 2, 3, 4 - not after last attempt)
        assert len(sleep_calls) == 3
        # Delays should follow exponential pattern: 0.01, 0.02, 0.04
        assert sleep_calls[0] == pytest.approx(0.01)  # 0.01 * 2^0
        assert sleep_calls[1] == pytest.approx(0.02)  # 0.01 * 2^1
        assert sleep_calls[2] == pytest.approx(0.04)  # 0.01 * 2^2


class TestShutdown:
    """Tests for shutdown method."""

    @pytest.mark.asyncio
    async def test_shutdown_all_instances(self, tmp_path):
        """Test shutting down all instances."""
        spawner = make_spawner(tmp_path)

        spawner._instances["task-1"] = {"instance_id": "cc-1"}
        spawner._instances["task-2"] = {"instance_id": "cc-2"}
        spawner._instances["task-3"] = {"instance_id": "cc-3"}

        with patch.object(spawner, 'stop', new_callable=AsyncMock) as mock_stop:
            await spawner.shutdown()

        assert mock_stop.call_count == 3

        # Verify stop was called with force=True and timeout=10
        for call_args in mock_stop.call_args_list:
            assert call_args.kwargs["force"] is True
            assert call_args.kwargs["timeout"] == 10


class TestGetStatus:
    """Tests for get_status method."""

    def test_get_status_empty(self, tmp_path):
        """Test status with no running instances."""
        spawner = make_spawner(tmp_path)

        status = spawner.get_status()

        assert status["running_instances"] == 0
        assert status["failed_events_count"] == 0
        assert status["instances"] == []

    def test_get_status_with_instances(self, tmp_path):
        """Test status with running instances."""
        spawner = make_spawner(tmp_path)

        now = datetime.now(timezone.utc)
        spawner._instances["task-1"] = {
            "task_id": "task-1",
            "instance_id": "cc-1",
            "started_at": now,
            "working_dir": "/workspace/cc-1/repo",
            "branch_name": None,
        }
        spawner._instances["task-2"] = {
            "task_id": "task-2",
            "instance_id": "cc-2",
            "started_at": now,
            "working_dir": "/workspace/cc-2/repo",
            "branch_name": None,
        }

        status = spawner.get_status()

        assert status["running_instances"] == 2
        assert len(status["instances"]) == 2

        instance_1 = status["instances"][0]
        assert instance_1["task_id"] == "task-1"
        assert instance_1["instance_id"] == "cc-1"
        # No pid field expected in SDK-based spawner
        assert "pid" not in instance_1

    def test_get_status_includes_failed_events(self, tmp_path):
        """Test status includes failed events count."""
        spawner = make_spawner(tmp_path)

        spawner._failed_events_count = 5

        status = spawner.get_status()

        assert status["failed_events_count"] == 5

    def test_get_status_no_pid_field(self, tmp_path):
        """Test that get_status does not include pid field (SDK-based, no subprocess)."""
        spawner = make_spawner(tmp_path)

        now = datetime.now(timezone.utc)
        spawner._instances["task-1"] = {
            "task_id": "task-1",
            "instance_id": "cc-1",
            "started_at": now,
            "working_dir": "/workspace/cc-1/repo",
            "branch_name": "feat/test",
        }

        status = spawner.get_status()

        instance = status["instances"][0]
        assert "pid" not in instance
        assert instance["working_dir"] == "/workspace/cc-1/repo"
        assert instance["branch_name"] == "feat/test"


class TestGlobalSpawnerFunctions:
    """Tests for global spawner management functions."""

    def test_get_spawner_returns_none_initially(self):
        """Test that get_claude_code_spawner returns None initially."""
        set_claude_code_spawner(None)
        spawner = get_claude_code_spawner()
        assert spawner is None

    def test_set_and_get_spawner(self, tmp_path):
        """Test setting and getting global spawner."""
        spawner = make_spawner(tmp_path)

        set_claude_code_spawner(spawner)
        retrieved = get_claude_code_spawner()

        assert retrieved is spawner

        # Cleanup
        set_claude_code_spawner(None)

    def test_initialize_claude_code_spawner(self, tmp_path):
        """Test initialize_claude_code_spawner function."""
        workspace = str(tmp_path / "workspace")

        spawner = initialize_claude_code_spawner(
            workspace_path=workspace,
            serving_url="http://localhost:9000",
            compute_id="compute-002",
            api_key="init-key"
        )

        assert spawner is not None
        assert spawner.serving_url == "http://localhost:9000"
        assert spawner.compute_id == "compute-002"
        assert spawner.api_key == "init-key"
        assert get_claude_code_spawner() is spawner

        # Cleanup
        set_claude_code_spawner(None)

    def test_initialize_claude_code_spawner_with_git_token(self, tmp_path):
        """Test that initialize_claude_code_spawner accepts git_token."""
        workspace = str(tmp_path / "workspace")

        spawner = initialize_claude_code_spawner(
            workspace_path=workspace,
            compute_id="compute-002",
            api_key="init-key",
            git_token="cvn-ct-testtoken",
        )

        assert spawner is not None
        assert get_claude_code_spawner() is spawner
        assert spawner.git_token == "cvn-ct-testtoken"

        # Cleanup
        set_claude_code_spawner(None)

    def test_initialize_with_retry_config(self, tmp_path):
        """Test initialize_claude_code_spawner with retry configuration."""
        workspace = str(tmp_path / "workspace")

        spawner = initialize_claude_code_spawner(
            workspace_path=workspace,
            compute_id="compute-003",
            api_key="test-key",
            event_max_retries=10,
            event_base_delay=2.5
        )

        assert spawner.event_max_retries == 10
        assert spawner.event_base_delay == 2.5
        assert get_claude_code_spawner() is spawner

        # Cleanup
        set_claude_code_spawner(None)


class TestRunGitCommand:
    """Tests for _run_git_command helper method."""

    def test_run_git_command_success(self, tmp_path):
        """Test running a git command successfully."""
        spawner = make_spawner(tmp_path)

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            spawner._run_git_command(["status"], cwd=tmp_path)

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == ["git", "status"]
        assert kwargs["cwd"] == str(tmp_path)
        assert kwargs["check"] is True

    def test_run_git_command_sets_askpass_with_token(self, tmp_path):
        """Test that git commands use GIT_ASKPASS when a token is provided."""
        spawner = make_spawner(tmp_path)

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            spawner._run_git_command(["clone", "http://serving:8002/git/repo.git"], git_token="cvn-ct-testtoken")

        args, kwargs = mock_run.call_args
        env = kwargs["env"]
        assert "GIT_ASKPASS" in env
        assert "GIT_TERMINAL_PROMPT" in env
        assert env["GIT_TERMINAL_PROMPT"] == "0"

    def test_run_git_command_no_askpass_without_token(self, tmp_path):
        """Test that GIT_ASKPASS is not set when no token is provided."""
        spawner = make_spawner(tmp_path)

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            spawner._run_git_command(["clone", "http://serving:8002/git/repo.git"])

        args, kwargs = mock_run.call_args
        env = kwargs["env"]
        assert "GIT_ASKPASS" not in env

    def test_run_git_command_failure(self, tmp_path):
        """Test that failed git commands raise CalledProcessError."""
        spawner = make_spawner(tmp_path)

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "git", stderr="error")

            with pytest.raises(subprocess.CalledProcessError):
                spawner._run_git_command(["invalid-command"])


class TestSetupBranch:
    """Tests for _setup_branch method."""

    def test_setup_branch_success(self, tmp_path):
        """Test successful branch setup."""
        spawner = make_spawner(tmp_path)

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()

        with patch.object(spawner, '_run_git_command') as mock_git:
            result = spawner._setup_branch(
                instance_workspace=instance_workspace,
                repo_url="git@github.com:test/repo.git",
                base_branch="main",
                feature_branch="work/compute-001/task-123",
                git_token="cvn-ct-testtoken"
            )

        assert result == instance_workspace / "repo"

        # Verify git commands were called in order
        assert mock_git.call_count == 2

        # First call: clone
        clone_call = mock_git.call_args_list[0]
        assert "clone" in clone_call.args[0]
        assert "--branch" in clone_call.args[0]
        assert "main" in clone_call.args[0]
        assert "git@github.com:test/repo.git" in clone_call.args[0]
        assert str(instance_workspace / "repo") in clone_call.args[0]
        assert clone_call.kwargs["git_token"] == "cvn-ct-testtoken"

        # Second call: checkout -b feature branch
        checkout_call = mock_git.call_args_list[1]
        assert "checkout" in checkout_call.args[0]
        assert "-b" in checkout_call.args[0]
        assert "work/compute-001/task-123" in checkout_call.args[0]

    def test_setup_branch_clone_failure(self, tmp_path):
        """Test branch setup when clone fails."""
        spawner = make_spawner(tmp_path)

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()

        with patch.object(spawner, '_run_git_command') as mock_git:
            mock_git.side_effect = subprocess.CalledProcessError(
                1, "git clone", stderr="Authentication failed"
            )

            with pytest.raises(subprocess.CalledProcessError):
                spawner._setup_branch(
                    instance_workspace=instance_workspace,
                    repo_url="git@github.com:test/repo.git",
                    base_branch="main",
                    feature_branch="work/compute-001/task-123"
                )


class TestDeleteLocalBranch:
    """Tests for delete_local_branch method."""

    def test_delete_branch_success(self, tmp_path):
        """Branch is deleted when instance is tracked and git succeeds."""
        spawner = make_spawner(tmp_path)
        fake_repo = tmp_path / "repo"
        fake_repo.mkdir()

        spawner._instances["task-1"] = {
            "branch_name": "feat/issue-100",
            "repo_path": str(fake_repo),
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            result = spawner.delete_local_branch("feat/issue-100")

        assert result is True
        mock_run.assert_called_once_with(
            ["git", "branch", "-d", "feat/issue-100"],
            cwd=str(fake_repo),
            capture_output=True,
            text=True,
        )

    def test_delete_branch_not_found_locally(self, tmp_path):
        """Returns False gracefully when git says branch not found."""
        spawner = make_spawner(tmp_path)
        fake_repo = tmp_path / "repo"
        fake_repo.mkdir()

        spawner._instances["task-1"] = {
            "branch_name": "feat/issue-100",
            "repo_path": str(fake_repo),
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="error: branch 'feat/issue-100' not found."
            )
            result = spawner.delete_local_branch("feat/issue-100")

        assert result is False

    def test_delete_branch_no_tracked_instance(self, tmp_path):
        """Returns False gracefully when no instance tracks the branch."""
        spawner = make_spawner(tmp_path)
        # No instances tracked

        with patch("subprocess.run") as mock_run:
            result = spawner.delete_local_branch("feat/issue-999")

        assert result is False
        mock_run.assert_not_called()

    def test_delete_branch_repo_path_missing(self, tmp_path):
        """Returns False gracefully when repo_path directory doesn't exist."""
        spawner = make_spawner(tmp_path)
        # Instance tracked but workspace already removed
        spawner._instances["task-1"] = {
            "branch_name": "feat/issue-100",
            "repo_path": str(tmp_path / "nonexistent" / "repo"),
        }

        with patch("subprocess.run") as mock_run:
            result = spawner.delete_local_branch("feat/issue-100")

        assert result is False
        mock_run.assert_not_called()

    def test_delete_branch_no_repo_path_in_instance(self, tmp_path):
        """Returns False gracefully when instance has no repo_path."""
        spawner = make_spawner(tmp_path)
        spawner._instances["task-1"] = {
            "branch_name": "feat/issue-100",
            # no repo_path key
        }

        with patch("subprocess.run") as mock_run:
            result = spawner.delete_local_branch("feat/issue-100")

        assert result is False
        mock_run.assert_not_called()

    def test_delete_branch_subprocess_exception(self, tmp_path):
        """Returns False gracefully when subprocess raises an exception."""
        spawner = make_spawner(tmp_path)
        fake_repo = tmp_path / "repo"
        fake_repo.mkdir()

        spawner._instances["task-1"] = {
            "branch_name": "feat/issue-100",
            "repo_path": str(fake_repo),
        }

        with patch("subprocess.run", side_effect=OSError("git not found")):
            result = spawner.delete_local_branch("feat/issue-100")

        assert result is False

    def test_delete_branch_only_matches_exact_name(self, tmp_path):
        """Does not delete branch with similar but different name."""
        spawner = make_spawner(tmp_path)
        fake_repo = tmp_path / "repo"
        fake_repo.mkdir()

        spawner._instances["task-1"] = {
            "branch_name": "feat/issue-100",
            "repo_path": str(fake_repo),
        }

        with patch("subprocess.run") as mock_run:
            result = spawner.delete_local_branch("feat/issue-1000")

        # No instance matches "feat/issue-1000"
        assert result is False
        mock_run.assert_not_called()


class TestCleanupWorkspace:
    """Tests for _cleanup_workspace method."""

    def test_cleanup_workspace_success(self, tmp_path):
        """Test successful workspace cleanup."""
        spawner = make_spawner(tmp_path)

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()
        (instance_workspace / "test.txt").write_text("test")

        spawner._cleanup_workspace(instance_workspace)

        # Verify workspace was removed
        assert not instance_workspace.exists()

    def test_cleanup_workspace_nonexistent(self, tmp_path):
        """Test cleanup when workspace doesn't exist."""
        spawner = make_spawner(tmp_path)

        instance_workspace = tmp_path / "instance"

        # Should not raise error when cleaning nonexistent directory
        spawner._cleanup_workspace(instance_workspace)


class TestSpawnWithGitBranch:
    """Tests for spawn method with Git branch functionality."""

    @pytest.mark.asyncio
    async def test_spawn_with_repository_context(self, tmp_path):
        """Test spawn with repository URL creates branch."""
        spawner = make_spawner(tmp_path)

        event = {
            "task_id": "task-123",
            "title": "Test Task",
            "description": "Test description",
            "branch_name": "feat/issue-123/compute-001",
            "skills": {"merged_instructions": "Test skills"},
            "context": {
                "repository": "git@github.com:test/repo.git",
                "base_branch": "main"
            },
            "mcp_config": {}
        }

        # Create a mock repo path (must exist for writing CLAUDE.md)
        mock_repo_path = tmp_path / "workspace" / "cc-12345678" / "repo"
        mock_repo_path.mkdir(parents=True)

        with patch.object(spawner, '_setup_branch', return_value=mock_repo_path) as mock_setup, \
             patch.object(spawner, '_setup_mcp_tools', return_value={}) as mock_mcp, \
             patch.object(spawner, '_start_task', new_callable=AsyncMock) as mock_start, \
             patch.object(spawner, 'send_claude_code_started', new_callable=AsyncMock):

            result = await spawner.spawn(event)

        assert result is True

        # Verify branch was set up
        mock_setup.assert_called_once()
        call_kwargs = mock_setup.call_args.kwargs
        assert call_kwargs["repo_url"] == "git@github.com:test/repo.git"
        assert call_kwargs["base_branch"] == "main"
        assert call_kwargs["feature_branch"] == "feat/issue-123/compute-001"

        # Verify instance metadata includes repo info
        instance = spawner._instances["task-123"]
        assert instance["repo_path"] == str(mock_repo_path)
        assert instance["branch_name"] == "feat/issue-123/compute-001"

        # Verify _start_task was called with repo path
        start_call_args = mock_start.call_args
        assert start_call_args.args[2] == mock_repo_path

    @pytest.mark.asyncio
    async def test_spawn_generates_branch_name_if_not_provided(self, tmp_path):
        """Test that spawn generates a branch name if not provided."""
        spawner = make_spawner(tmp_path)

        event = {
            "task_id": "task-456",
            "title": "Test Task",
            "description": "Test",
            "skills": {},
            "context": {
                "repository": "git@github.com:test/repo.git",
                "base_branch": "develop"
            },
            "mcp_config": {}
        }

        # Create mock repo directory
        mock_repo_path = tmp_path / "repo"
        mock_repo_path.mkdir(parents=True)

        with patch.object(spawner, '_setup_branch', return_value=mock_repo_path) as mock_setup, \
             patch.object(spawner, '_setup_mcp_tools', return_value={}) as mock_mcp, \
             patch.object(spawner, '_start_task', new_callable=AsyncMock), \
             patch.object(spawner, 'send_claude_code_started', new_callable=AsyncMock):

            await spawner.spawn(event)

        # Verify generated branch name follows expected pattern
        call_kwargs = mock_setup.call_args.kwargs
        assert call_kwargs["feature_branch"] == "work/compute-001/task-456"

    @pytest.mark.asyncio
    async def test_spawn_git_setup_failure(self, tmp_path):
        """Test spawn handles Git setup failure gracefully."""
        spawner = make_spawner(tmp_path)

        event = {
            "task_id": "task-789",
            "title": "Test Task",
            "skills": {},
            "context": {
                "repository": "git@github.com:test/repo.git",
                "base_branch": "main"
            },
            "mcp_config": {}
        }

        with patch.object(spawner, '_setup_branch') as mock_setup, \
             patch.object(spawner, '_cleanup_workspace') as mock_cleanup, \
             patch.object(spawner, 'send_claude_code_failed', new_callable=AsyncMock) as mock_failed:

            mock_setup.side_effect = subprocess.CalledProcessError(
                1, "git clone", stderr="Repository not found"
            )

            result = await spawner.spawn(event)

        assert result is False
        assert "task-789" not in spawner._instances

        # Verify cleanup was called
        mock_cleanup.assert_called_once()

        # Verify failure event was sent (called with positional args)
        mock_failed.assert_called_once()
        call_args = mock_failed.call_args[0]  # Positional args
        assert call_args[0] == "task-789"  # task_id
        assert "Git setup failed" in call_args[2]  # error message

    @pytest.mark.asyncio
    async def test_spawn_without_repository_skips_git_setup(self, tmp_path):
        """Test spawn without repository URL skips git setup."""
        spawner = make_spawner(tmp_path)

        event = {
            "task_id": "task-999",
            "title": "Test Task",
            "description": "No repo",
            "skills": {},
            "context": {},  # No repository
            "mcp_config": {}
        }

        with patch.object(spawner, '_setup_branch') as mock_setup, \
             patch.object(spawner, '_setup_mcp_tools', return_value={}) as mock_mcp, \
             patch.object(spawner, '_start_task', new_callable=AsyncMock), \
             patch.object(spawner, 'send_claude_code_started', new_callable=AsyncMock):

            result = await spawner.spawn(event)

        assert result is True

        # Branch setup should not be called
        mock_setup.assert_not_called()

        # Instance should not have repo metadata
        instance = spawner._instances["task-999"]
        assert instance["repo_path"] is None
        assert instance["branch_name"] is None


class TestSpawnWithConflictResolution:
    """Tests for spawn() with is_conflict_resolution=True context flag."""

    @pytest.mark.asyncio
    async def test_spawn_conflict_resolution_calls_setup_existing_branch(self, tmp_path):
        """When is_conflict_resolution=True, spawn uses _setup_existing_branch."""
        spawner = make_spawner(tmp_path)

        event = {
            "task_id": "conflict-work_abc-deadbeef",
            "title": "Resolve conflicts: feat/my-branch",
            "description": "Resolve merge conflicts",
            "branch_name": "feat/my-branch",
            "skills": {"merged_instructions": "resolve conflicts"},
            "context": {
                "repository": "git@serving:repos/proj-1.git",
                "base_branch": "main",
                "is_conflict_resolution": True,
                "conflicting_files": ["CLAUDE.md"],
            },
            "mcp_config": {"server_url": "http://serving:8002", "api_key": "troc_key"},
        }

        mock_repo_path = tmp_path / "workspace" / "cc-test" / "repo"
        mock_repo_path.mkdir(parents=True)

        with patch.object(spawner, "_setup_existing_branch", return_value=mock_repo_path) as mock_existing, \
             patch.object(spawner, "_setup_branch") as mock_new, \
             patch.object(spawner, "_setup_mcp_tools", return_value={}), \
             patch.object(spawner, "_start_task", new_callable=AsyncMock), \
             patch.object(spawner, "send_claude_code_started", new_callable=AsyncMock):
            result = await spawner.spawn(event)

        assert result is True
        mock_existing.assert_called_once()
        call_kwargs = mock_existing.call_args.kwargs
        assert call_kwargs["repo_url"] == "git@serving:repos/proj-1.git"
        assert call_kwargs["branch"] == "feat/my-branch"
        mock_new.assert_not_called()

    @pytest.mark.asyncio
    async def test_spawn_regular_task_calls_setup_branch_not_existing(self, tmp_path):
        """Without is_conflict_resolution, spawn uses _setup_branch (creates new branch)."""
        spawner = make_spawner(tmp_path)

        event = {
            "task_id": "work_abc123",
            "title": "Implement feature",
            "description": "Do the thing",
            "branch_name": "feat/my-branch",
            "skills": {"merged_instructions": "implement feature"},
            "context": {
                "repository": "git@serving:repos/proj-1.git",
                "base_branch": "main",
                # no is_conflict_resolution
            },
            "mcp_config": {"server_url": "http://serving:8002", "api_key": "troc_key"},
        }

        mock_repo_path = tmp_path / "workspace" / "cc-test" / "repo"
        mock_repo_path.mkdir(parents=True)

        with patch.object(spawner, "_setup_branch", return_value=mock_repo_path) as mock_new, \
             patch.object(spawner, "_setup_existing_branch") as mock_existing, \
             patch.object(spawner, "_setup_mcp_tools", return_value={}), \
             patch.object(spawner, "_start_task", new_callable=AsyncMock), \
             patch.object(spawner, "send_claude_code_started", new_callable=AsyncMock):
            result = await spawner.spawn(event)

        assert result is True
        mock_new.assert_called_once()
        mock_existing.assert_not_called()

    @pytest.mark.asyncio
    async def test_spawn_conflict_resolution_false_uses_setup_branch(self, tmp_path):
        """Explicit is_conflict_resolution=False also uses _setup_branch."""
        spawner = make_spawner(tmp_path)

        event = {
            "task_id": "work_abc123",
            "title": "Implement feature",
            "description": "Do the thing",
            "branch_name": "feat/my-branch",
            "skills": {},
            "context": {
                "repository": "git@serving:repos/proj-1.git",
                "base_branch": "main",
                "is_conflict_resolution": False,
            },
            "mcp_config": {},
        }

        mock_repo_path = tmp_path / "workspace" / "cc-test" / "repo"
        mock_repo_path.mkdir(parents=True)

        with patch.object(spawner, "_setup_branch", return_value=mock_repo_path) as mock_new, \
             patch.object(spawner, "_setup_existing_branch") as mock_existing, \
             patch.object(spawner, "_setup_mcp_tools", return_value={}), \
             patch.object(spawner, "_start_task", new_callable=AsyncMock), \
             patch.object(spawner, "send_claude_code_started", new_callable=AsyncMock):
            result = await spawner.spawn(event)

        assert result is True
        mock_new.assert_called_once()
        mock_existing.assert_not_called()


class TestCleanupInstanceWithWorkspace:
    """Tests for _cleanup_instance with workspace cleanup."""

    def test_cleanup_instance_with_workspace(self, tmp_path):
        """Test cleaning up instance that has a repo."""
        spawner = make_spawner(tmp_path)

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "workspace": str(instance_workspace),
            "repo_path": str(instance_workspace / "repo")
        }

        with patch.object(spawner, '_cleanup_workspace') as mock_cleanup:
            spawner._cleanup_instance("task-123", cleanup_workspace=True)

        # Should use workspace cleanup
        mock_cleanup.assert_called_once_with(instance_workspace)
        assert "task-123" not in spawner._instances

    def test_cleanup_instance_without_repo(self, tmp_path):
        """Test cleaning up instance without repo."""
        spawner = make_spawner(tmp_path)

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()
        (instance_workspace / "test.txt").write_text("test")

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "workspace": str(instance_workspace),
            "repo_path": None  # No repo
        }

        with patch.object(spawner, '_cleanup_workspace') as mock_cleanup:
            spawner._cleanup_instance("task-123", cleanup_workspace=True)

        # Should use workspace cleanup
        mock_cleanup.assert_called_once_with(instance_workspace)
        assert "task-123" not in spawner._instances

    def test_cleanup_instance_no_cleanup_flag(self, tmp_path):
        """Test cleanup instance without cleanup_workspace flag."""
        spawner = make_spawner(tmp_path)

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "workspace": str(instance_workspace),
            "repo_path": str(instance_workspace / "repo")
        }

        with patch.object(spawner, '_cleanup_workspace') as mock_cleanup:
            spawner._cleanup_instance("task-123", cleanup_workspace=False)

        # Should NOT clean up workspace
        mock_cleanup.assert_not_called()
        assert instance_workspace.exists()

    def test_cleanup_instance_removes_execution_task(self, tmp_path):
        """Test cleanup removes entry from _execution_tasks."""
        spawner = make_spawner(tmp_path)

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()

        spawner._instances["task-123"] = {
            "instance_id": "cc-instance",
            "workspace": str(instance_workspace),
        }
        mock_task = MagicMock(spec=asyncio.Task)
        spawner._execution_tasks["task-123"] = mock_task

        spawner._cleanup_instance("task-123")

        assert "task-123" not in spawner._execution_tasks


class TestInitializeWithGitToken:
    """Tests for initialization with Git token."""

    def test_init_with_git_token(self, tmp_path):
        """Test initialization with Git token."""
        spawner = make_spawner(tmp_path, git_token="cvn-ct-testtoken")
        assert spawner.git_token == "cvn-ct-testtoken"

    def test_initialize_function_with_git_token(self, tmp_path):
        """Test initialize_claude_code_spawner with Git token."""
        workspace = str(tmp_path / "workspace")

        spawner = initialize_claude_code_spawner(
            workspace_path=workspace,
            compute_id="compute-002",
            api_key="test-key",
            git_token="cvn-ct-mytoken"
        )

        assert spawner.git_token == "cvn-ct-mytoken"
        assert get_claude_code_spawner() is spawner

        # Cleanup
        set_claude_code_spawner(None)


class TestGetStatusWithBranchInfo:
    """Tests for get_status including branch information."""

    def test_get_status_with_branch_info(self, tmp_path):
        """Test status includes branch information."""
        spawner = make_spawner(tmp_path)

        now = datetime.now(timezone.utc)
        spawner._instances["task-1"] = {
            "task_id": "task-1",
            "instance_id": "cc-1",
            "started_at": now,
            "working_dir": "/workspace/cc-1/repo",
            "branch_name": "feat/issue-123/compute-001"
        }

        status = spawner.get_status()

        instance = status["instances"][0]
        assert instance["working_dir"] == "/workspace/cc-1/repo"
        assert instance["branch_name"] == "feat/issue-123/compute-001"
        # Verify active_worktree is not in status
        assert "active_worktree" not in instance
        # Verify pid is not in status (SDK-based spawner)
        assert "pid" not in instance


class TestExtractJsonFromOutput:
    """Tests for _extract_json_from_output helper function."""

    def test_single_line_json(self):
        """Test extracting JSON from a single line."""
        output = 'Some text\n{"issues": [{"temp_id": "issue-1", "title": "Test"}], "confidence": 0.9, "reasoning": "ok"}\n'
        result = _extract_json_from_output(output)
        assert result is not None
        assert result["confidence"] == 0.9
        assert len(result["issues"]) == 1

    def test_json_in_code_fence(self):
        """Test extracting JSON from markdown code fence."""
        output = (
            "Here is the decomposition:\n\n"
            "```json\n"
            '{"issues": [{"temp_id": "issue-1", "title": "Data models"}], "confidence": 0.85, "reasoning": "test"}\n'
            "```\n"
        )
        result = _extract_json_from_output(output)
        assert result is not None
        assert result["confidence"] == 0.85

    def test_json_in_plain_code_fence(self):
        """Test extracting JSON from code fence without json tag."""
        output = (
            "Result:\n\n"
            "```\n"
            '{"issues": [{"temp_id": "issue-1", "title": "Test"}], "confidence": 0.7, "reasoning": "ok"}\n'
            "```\n"
        )
        result = _extract_json_from_output(output)
        assert result is not None
        assert result["confidence"] == 0.7

    def test_multiline_json_in_code_fence(self):
        """Test extracting multi-line JSON from code fence."""
        output = (
            "Decomposition:\n\n"
            "```json\n"
            "{\n"
            '  "issues": [\n'
            '    {"temp_id": "issue-1", "title": "Models", "description": "Create models", '
            '"issue_type": "feature", "area": "api", "priority": "P0", '
            '"required_skills": ["code-writer"], "estimated_complexity": "s", '
            '"blocked_by": [], "acceptance_criteria": ["Models exist"]}\n'
            "  ],\n"
            '  "confidence": 0.9,\n'
            '  "reasoning": "Bottom-up approach"\n'
            "}\n"
            "```\n"
        )
        result = _extract_json_from_output(output)
        assert result is not None
        assert result["confidence"] == 0.9
        assert result["issues"][0]["title"] == "Models"

    def test_brace_balanced_extraction(self):
        """Test brace-balanced extraction for embedded JSON."""
        output = (
            "The decomposition breaks the goal into 2 issues:\n\n"
            '1. **Models** - Data models\n\n'
            'Here is the structured result: {"issues": [{"temp_id": "issue-1", "title": "Models", '
            '"description": "d", "issue_type": "feature", "area": "api", "priority": "P0", '
            '"required_skills": [], "estimated_complexity": "s", "blocked_by": [], '
            '"acceptance_criteria": []}], "confidence": 0.8, "reasoning": "test"}\n'
        )
        result = _extract_json_from_output(output)
        assert result is not None
        assert result["confidence"] == 0.8

    def test_no_json_in_output(self):
        """Test returns None when no JSON is found."""
        output = (
            "The decomposition breaks the weather script goal into 7 issues:\n\n"
            "1. **Weather data models** (P0) - WeatherResult dataclass\n"
            "2. **Abstract provider interface** (P0) - WeatherProvider ABC\n"
        )
        result = _extract_json_from_output(output)
        assert result is None

    def test_empty_output(self):
        """Test returns None for empty output."""
        assert _extract_json_from_output("") is None
        assert _extract_json_from_output(None) is None

    def test_json_without_issues_key_ignored(self):
        """Test that JSON without 'issues' key is not returned."""
        output = '{"name": "test", "value": 42}\n'
        result = _extract_json_from_output(output)
        assert result is None

    def test_invalid_json_skipped(self):
        """Test that invalid JSON is skipped gracefully."""
        output = (
            '{this is not valid json}\n'
            '{"issues": [{"temp_id": "issue-1", "title": "Real"}], "confidence": 0.9, "reasoning": "ok"}\n'
        )
        result = _extract_json_from_output(output)
        assert result is not None
        assert result["issues"][0]["title"] == "Real"

    def test_prefers_last_single_line_json(self):
        """Test that scanning from end finds the last JSON line."""
        output = (
            '{"issues": [{"temp_id": "old"}], "confidence": 0.5, "reasoning": "first"}\n'
            'Some text in between\n'
            '{"issues": [{"temp_id": "new"}], "confidence": 0.95, "reasoning": "final"}\n'
        )
        result = _extract_json_from_output(output)
        assert result is not None
        assert result["confidence"] == 0.95

    def test_nested_objects_in_issues(self):
        """Test handling JSON with nested objects inside issues."""
        issue = {
            "temp_id": "issue-1",
            "title": "Test",
            "description": "desc",
            "issue_type": "feature",
            "area": "api",
            "priority": "P0",
            "required_skills": ["code-writer"],
            "estimated_complexity": "m",
            "blocked_by": [],
            "acceptance_criteria": ["Test passes"]
        }
        data = {"issues": [issue], "confidence": 0.85, "reasoning": "ok"}
        output = f"Result:\n{json.dumps(data)}\n"
        result = _extract_json_from_output(output)
        assert result is not None
        assert result["issues"][0]["acceptance_criteria"] == ["Test passes"]


class TestExtractJsonWithKey:
    """Tests for _extract_json_with_key helper function."""

    def test_extract_with_custom_key(self):
        """Test extracting JSON with a non-issues key."""
        output = '{"characterizations": [{"item_id": "item-1"}], "confidence": 0.9}\n'
        result = _extract_json_with_key(output, "characterizations")
        assert result is not None
        assert len(result["characterizations"]) == 1

    def test_extract_ignores_wrong_key(self):
        """Test that JSON without the required key is ignored."""
        output = '{"issues": [{"temp_id": "issue-1"}], "confidence": 0.9}\n'
        result = _extract_json_with_key(output, "characterizations")
        assert result is None

    def test_extract_empty_output(self):
        """Test returns None for empty output."""
        assert _extract_json_with_key("", "key") is None
        assert _extract_json_with_key(None, "key") is None

    def test_extract_from_code_fence(self):
        """Test extracting from markdown code fence."""
        output = (
            "Result:\n\n"
            "```json\n"
            '{"ontology_tags": {"work_type": "feature"}, "item_id": "item-1"}\n'
            "```\n"
        )
        result = _extract_json_with_key(output, "ontology_tags")
        assert result is not None
        assert result["ontology_tags"]["work_type"] == "feature"


class TestExtractCharacterizationJsonFromOutput:
    """Tests for _extract_characterization_json_from_output helper."""

    def test_extract_multi_item_format(self):
        """Test extracting characterizations list format."""
        data = {
            "characterizations": [
                {
                    "item_id": "item-1",
                    "ontology_tags": {"work_type": "feature"},
                    "meaning": {"business_summary": "Test"},
                    "confidence": 0.9,
                }
            ]
        }
        output = json.dumps(data) + "\n"
        result = _extract_characterization_json_from_output(output)
        assert result is not None
        assert "characterizations" in result
        assert result["characterizations"][0]["item_id"] == "item-1"

    def test_extract_single_item_format(self):
        """Test extracting single-item format with ontology_tags at top level."""
        data = {
            "item_id": "item-1",
            "ontology_tags": {"work_type": "bug_fix", "lifecycle_stage": "build"},
            "meaning": {"business_summary": "Fix crash"},
            "confidence": 0.85,
        }
        output = json.dumps(data) + "\n"
        result = _extract_characterization_json_from_output(output)
        assert result is not None
        assert result["ontology_tags"]["work_type"] == "bug_fix"

    def test_extract_no_characterization_json(self):
        """Test returns None when no characterization JSON is found."""
        output = "The task has been completed successfully.\n"
        result = _extract_characterization_json_from_output(output)
        assert result is None

    def test_extract_prefers_characterizations_over_ontology_tags(self):
        """Test that characterizations key is preferred over ontology_tags."""
        data = {
            "characterizations": [
                {"item_id": "item-1", "ontology_tags": {"work_type": "feature"}}
            ]
        }
        output = json.dumps(data) + "\n"
        result = _extract_characterization_json_from_output(output)
        assert result is not None
        assert "characterizations" in result

    def test_extract_empty_output(self):
        """Test returns None for empty output."""
        assert _extract_characterization_json_from_output("") is None
        assert _extract_characterization_json_from_output(None) is None


class TestSubmitResultDispatch:
    """Tests for _submit_result dispatch logic (decomp- vs char- vs other)."""

    @pytest.mark.asyncio
    async def test_submit_result_decomp_task(self, tmp_path):
        """Test that decomp- tasks are routed to _submit_decomposition_result."""
        spawner = make_spawner(tmp_path)

        with patch.object(spawner, '_submit_decomposition_result', new_callable=AsyncMock) as mock_decomp, \
             patch.object(spawner, '_submit_characterization_result', new_callable=AsyncMock) as mock_char:

            await spawner._submit_result("decomp-abc123", "cc-inst", "output", None)

        mock_decomp.assert_called_once_with("decomp-abc123", "cc-inst", "output", None)
        mock_char.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_result_char_task(self, tmp_path):
        """Test that char- tasks are routed to _submit_characterization_result."""
        spawner = make_spawner(tmp_path)

        with patch.object(spawner, '_submit_decomposition_result', new_callable=AsyncMock) as mock_decomp, \
             patch.object(spawner, '_submit_characterization_result', new_callable=AsyncMock) as mock_char:

            await spawner._submit_result("char-9063a523b4f4", "cc-inst", "output", None)

        mock_char.assert_called_once_with("char-9063a523b4f4", "cc-inst", "output", None)
        mock_decomp.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_result_other_task(self, tmp_path):
        """Test that other task types are skipped."""
        spawner = make_spawner(tmp_path)

        with patch.object(spawner, '_submit_decomposition_result', new_callable=AsyncMock) as mock_decomp, \
             patch.object(spawner, '_submit_characterization_result', new_callable=AsyncMock) as mock_char:

            await spawner._submit_result("work-abc123", "cc-inst", "output", None)

        mock_decomp.assert_not_called()
        mock_char.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_result_empty_output(self, tmp_path):
        """Test that empty output short-circuits before dispatch."""
        spawner = make_spawner(tmp_path)

        with patch.object(spawner, '_submit_decomposition_result', new_callable=AsyncMock) as mock_decomp, \
             patch.object(spawner, '_submit_characterization_result', new_callable=AsyncMock) as mock_char:

            await spawner._submit_result("char-abc123", "cc-inst", "", None)

        mock_decomp.assert_not_called()
        mock_char.assert_not_called()


class TestSubmitCharacterizationResult:
    """Tests for _submit_characterization_result method."""

    @pytest.mark.asyncio
    async def test_submit_characterization_success(self, tmp_path):
        """Test successful characterization result submission."""
        spawner = make_spawner(tmp_path, serving_url="http://localhost:8002")

        char_data = {
            "characterizations": [
                {
                    "item_id": "item-1",
                    "ontology_tags": {"work_type": "feature", "lifecycle_stage": "build", "technical_domains": ["api"]},
                    "meaning": {"business_summary": "New API endpoint"},
                    "confidence": 0.9,
                }
            ]
        }
        output = json.dumps(char_data) + "\n"

        instance = {
            "event": {
                "context": {"project_id": "proj-123", "task_type": "characterization"}
            }
        }

        mock_response = Mock()
        mock_response.status_code = 200

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock()

            await spawner._submit_characterization_result(
                "char-abc123", "cc-inst", output, instance
            )

        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        assert args[0] == "http://localhost:8002/api/v1/compute/characterization/char-abc123/result"
        assert kwargs["json"]["characterization_id"] == "char-abc123"
        assert kwargs["json"]["project_id"] == "proj-123"
        assert len(kwargs["json"]["characterizations"]) == 1
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"

    @pytest.mark.asyncio
    async def test_submit_characterization_single_item_wrapped(self, tmp_path):
        """Test single-item characterization output is wrapped into list."""
        spawner = make_spawner(tmp_path, serving_url="http://localhost:8002")

        # Single-item format (ontology_tags at top level, no characterizations key)
        char_data = {
            "item_id": "item-1",
            "ontology_tags": {"work_type": "bug_fix"},
            "meaning": {"business_summary": "Fix crash"},
            "confidence": 0.85,
        }
        output = json.dumps(char_data) + "\n"

        instance = {
            "event": {"context": {"project_id": "proj-456"}}
        }

        mock_response = Mock()
        mock_response.status_code = 200

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock()

            await spawner._submit_characterization_result(
                "char-def456", "cc-inst", output, instance
            )

        args, kwargs = mock_client.post.call_args
        # Single item should be wrapped in a list
        submitted_chars = kwargs["json"]["characterizations"]
        assert len(submitted_chars) == 1
        assert submitted_chars[0]["item_id"] == "item-1"

    @pytest.mark.asyncio
    async def test_submit_characterization_no_json_found(self, tmp_path):
        """Test handling when no characterization JSON is found in output."""
        spawner = make_spawner(tmp_path)

        output = "The characterization task is complete. No JSON output here.\n"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock()

            await spawner._submit_characterization_result(
                "char-xyz789", "cc-inst", output, None
            )

        # Should not attempt to POST
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_characterization_no_project_id(self, tmp_path):
        """Test submission when no project_id is in instance context."""
        spawner = make_spawner(tmp_path, serving_url="http://localhost:8002")

        char_data = {
            "characterizations": [{"item_id": "item-1", "ontology_tags": {"work_type": "feature"}}]
        }
        output = json.dumps(char_data) + "\n"

        mock_response = Mock()
        mock_response.status_code = 200

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock()

            # Pass None for instance (no event context)
            await spawner._submit_characterization_result(
                "char-noproj", "cc-inst", output, None
            )

        # Should still submit with "unknown" project_id
        args, kwargs = mock_client.post.call_args
        assert kwargs["json"]["project_id"] == "unknown"

    @pytest.mark.asyncio
    async def test_submit_characterization_http_failure(self, tmp_path):
        """Test handling HTTP failure when submitting characterization."""
        spawner = make_spawner(tmp_path, serving_url="http://localhost:8002")

        char_data = {
            "characterizations": [{"item_id": "item-1", "ontology_tags": {"work_type": "feature"}}]
        }
        output = json.dumps(char_data) + "\n"

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock()

            # Should not raise, just log warning
            await spawner._submit_characterization_result(
                "char-fail", "cc-inst", output, None
            )

    @pytest.mark.asyncio
    async def test_submit_characterization_network_error(self, tmp_path):
        """Test handling network error when submitting characterization."""
        spawner = make_spawner(tmp_path, serving_url="http://localhost:8002")

        char_data = {
            "characterizations": [{"item_id": "item-1", "ontology_tags": {"work_type": "feature"}}]
        }
        output = json.dumps(char_data) + "\n"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock()

            # Should not raise, just log error
            await spawner._submit_characterization_result(
                "char-err", "cc-inst", output, None
            )


class TestCommitAndPushRetry:
    """Tests for _commit_and_push_changes retry and failure reporting (#831)."""

    @pytest.mark.asyncio
    async def test_push_succeeds_returns_true(self, tmp_path):
        """Successful push returns True."""
        spawner = make_spawner(tmp_path)

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        instance = {"repo_path": str(repo_dir), "event": {"context": {}}}

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(stdout=""),  # git status (no changes)
                Mock(),           # git push
            ]
            result = await spawner._commit_and_push_changes("task-1", "cc-1", instance)

        assert result is True

    @pytest.mark.asyncio
    async def test_push_fails_retries_then_returns_false(self, tmp_path):
        """Push failure after retries returns False."""
        spawner = make_spawner(tmp_path)

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        instance = {"repo_path": str(repo_dir), "event": {"context": {}}}

        push_error = subprocess.CalledProcessError(1, "git push", stderr="Permission denied")

        with patch('subprocess.run') as mock_run, \
             patch('asyncio.sleep', new_callable=AsyncMock):
            mock_run.side_effect = [
                Mock(stdout=""),  # git status
                push_error,      # push attempt 1
                push_error,      # push attempt 2
                push_error,      # push attempt 3
            ]
            result = await spawner._commit_and_push_changes(
                "task-1", "cc-1", instance, max_retries=3, base_delay=0.01
            )

        assert result is False
        # 1 status + 3 push attempts = 4 calls
        assert mock_run.call_count == 4

    @pytest.mark.asyncio
    async def test_push_succeeds_on_retry(self, tmp_path):
        """Push succeeds on second attempt after transient failure."""
        spawner = make_spawner(tmp_path)

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        instance = {"repo_path": str(repo_dir), "event": {"context": {}}}

        with patch('subprocess.run') as mock_run, \
             patch('asyncio.sleep', new_callable=AsyncMock):
            mock_run.side_effect = [
                Mock(stdout=""),  # git status
                subprocess.CalledProcessError(1, "git push", stderr="Connection reset"),
                Mock(),           # push attempt 2 succeeds
            ]
            result = await spawner._commit_and_push_changes(
                "task-1", "cc-1", instance, max_retries=3, base_delay=0.01
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_no_repo_path_returns_true(self, tmp_path):
        """No repo_path means nothing to push — returns True."""
        spawner = make_spawner(tmp_path)

        instance = {"event": {"context": {}}}
        result = await spawner._commit_and_push_changes("task-1", "cc-1", instance)
        assert result is True

    @pytest.mark.asyncio
    async def test_commit_failure_returns_false(self, tmp_path):
        """Git commit failure returns False."""
        spawner = make_spawner(tmp_path)

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        instance = {"repo_path": str(repo_dir), "event": {"context": {}}}

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(stdout="M file.py"),  # git status (has changes)
                Mock(),                     # git add
                subprocess.CalledProcessError(1, "git commit", stderr="Nothing to commit"),
            ]
            result = await spawner._commit_and_push_changes("task-1", "cc-1", instance)

        assert result is False


class TestCommitAndPushSshKey:
    """Tests for _commit_and_push_changes using per-task SSH key (#815)."""

    @pytest.mark.asyncio
    async def test_uses_task_specific_ssh_key(self, tmp_path):
        """Test that _commit_and_push_changes uses SSH key from event context."""
        spawner = make_spawner(tmp_path, git_token="cvn-ct-defaulttoken")

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        instance = {
            "repo_path": str(repo_dir),
            "event": {
                "context": {
                    "git_token": "cvn-ct-tasktoken"
                }
            }
        }

        with patch('subprocess.run') as mock_run:
            status_result = Mock()
            status_result.stdout = ""
            push_result = Mock()
            mock_run.side_effect = [status_result, push_result]

            await spawner._commit_and_push_changes("task-1", "cc-1", instance)

        # The push call (second call) should use the task-specific token
        push_call = mock_run.call_args_list[1]
        env = push_call.kwargs.get("env") or push_call[1].get("env", {})
        assert "GIT_ASKPASS" in env
        assert "GIT_TERMINAL_PROMPT" in env

    @pytest.mark.asyncio
    async def test_falls_back_to_spawner_git_token(self, tmp_path):
        """Test fallback to spawner git_token when event context has no token."""
        spawner = make_spawner(tmp_path, git_token="cvn-ct-defaulttoken")

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        instance = {
            "repo_path": str(repo_dir),
            "event": {
                "context": {}
            }
        }

        with patch('subprocess.run') as mock_run:
            status_result = Mock()
            status_result.stdout = ""
            push_result = Mock()
            mock_run.side_effect = [status_result, push_result]

            await spawner._commit_and_push_changes("task-1", "cc-1", instance)

        push_call = mock_run.call_args_list[1]
        env = push_call.kwargs.get("env") or push_call[1].get("env", {})
        assert "GIT_ASKPASS" in env

    @pytest.mark.asyncio
    async def test_falls_back_when_no_event(self, tmp_path):
        """Test fallback when instance has no event key."""
        spawner = make_spawner(tmp_path, git_token="cvn-ct-defaulttoken")

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        instance = {
            "repo_path": str(repo_dir),
        }

        with patch('subprocess.run') as mock_run:
            status_result = Mock()
            status_result.stdout = ""
            push_result = Mock()
            mock_run.side_effect = [status_result, push_result]

            await spawner._commit_and_push_changes("task-1", "cc-1", instance)

        push_call = mock_run.call_args_list[1]
        env = push_call.kwargs.get("env") or push_call[1].get("env", {})
        assert "GIT_ASKPASS" in env


class TestSpawnNoChownNeeded:
    """Tests that spawn() does NOT chown since service runs as compute user (#825)."""

    @pytest.mark.asyncio
    async def test_spawn_does_not_call_chown(self, tmp_path):
        """Test that spawn() does not call chown — unnecessary when running as compute."""
        spawner = make_spawner(tmp_path)

        event = {
            "task_id": "task-nochown",
            "context": {
                "repository": "ssh://git@serving:2222/app/data/repos/project.git",
                "base_branch": "main",
                "git_token": "cvn-ct-tmptoken"
            },
            "branch_name": "feat/test"
        }

        repo_path = tmp_path / "workspace" / "cc-fake" / "repo"
        repo_path.mkdir(parents=True, exist_ok=True)

        with patch.object(spawner, '_setup_branch', return_value=repo_path), \
             patch.object(spawner, '_create_claude_md', return_value="# Test"), \
             patch.object(spawner, '_setup_mcp_tools', return_value={}), \
             patch('subprocess.run') as mock_run, \
             patch.object(spawner, '_start_task', new_callable=AsyncMock), \
             patch.object(spawner, 'send_claude_code_started', new_callable=AsyncMock):

            mock_run.return_value = Mock()
            await spawner.spawn(event)

        # Verify subprocess.run was NOT called with chown
        for call in mock_run.call_args_list:
            args = call[0][0] if call[0] else []
            assert not (isinstance(args, list) and len(args) > 0 and args[0] == "chown"), \
                f"chown should not be called — service runs as compute user. Got: {args}"


class TestMaxInstancesCapacity:
    """Tests for max_instances capacity enforcement (#826)."""

    def test_default_max_instances_is_one(self, tmp_path):
        """Test that default max_instances is 1."""
        spawner = make_spawner(tmp_path)
        assert spawner.max_instances == 1

    def test_custom_max_instances(self, tmp_path):
        """Test that max_instances can be configured."""
        spawner = make_spawner(tmp_path, max_instances=3)
        assert spawner.max_instances == 3

    @pytest.mark.asyncio
    async def test_spawn_rejected_at_capacity(self, tmp_path):
        """Test that spawn() returns False when at max capacity."""
        spawner = make_spawner(tmp_path, max_instances=1)

        # Simulate an existing running instance
        spawner._instances["existing-task"] = {
            "instance_id": "cc-existing",
            "started_at": datetime.now(timezone.utc)
        }

        event = {"task_id": "new-task", "context": {}}
        result = await spawner.spawn(event)

        assert result is False

    @pytest.mark.asyncio
    async def test_spawn_allowed_below_capacity(self, tmp_path):
        """Test that spawn() proceeds when below max capacity."""
        spawner = make_spawner(tmp_path, max_instances=2)

        # One instance already running
        spawner._instances["existing-task"] = {
            "instance_id": "cc-existing",
            "started_at": datetime.now(timezone.utc)
        }

        repo_path = tmp_path / "workspace" / "cc-fake" / "repo"
        repo_path.mkdir(parents=True, exist_ok=True)

        event = {
            "task_id": "new-task",
            "context": {
                "repository": "ssh://git@serving:2222/repo.git",
                "base_branch": "main"
            },
            "branch_name": "feat/test"
        }

        with patch.object(spawner, '_setup_branch', return_value=repo_path), \
             patch.object(spawner, '_create_claude_md', return_value="# Test"), \
             patch.object(spawner, '_setup_mcp_tools', return_value={}), \
             patch.object(spawner, '_start_task', new_callable=AsyncMock), \
             patch.object(spawner, 'send_claude_code_started', new_callable=AsyncMock):

            result = await spawner.spawn(event)

        assert result is True

    @pytest.mark.asyncio
    async def test_spawn_conflict_resolution_rejected_at_capacity(self, tmp_path):
        """Test that spawn_conflict_resolution() returns False at capacity."""
        spawner = make_spawner(tmp_path, max_instances=1)

        spawner._instances["existing-task"] = {
            "instance_id": "cc-existing",
            "event": {"context": {"repository": "git@server:repo.git"}}
        }

        conflict_data = {
            "branch": "feat/test",
            "issue_id": "issue-1",
            "conflicting_files": ["f.py"],
            "main_head": "abc",
            "message": "fix"
        }

        result = await spawner.spawn_conflict_resolution(conflict_data)
        assert result is False

    def test_get_status_includes_capacity(self, tmp_path):
        """Test that get_status() includes max_instances and available_capacity."""
        spawner = make_spawner(tmp_path, max_instances=3)

        status = spawner.get_status()
        assert status["max_instances"] == 3
        assert status["available_capacity"] == 3

        # Add an instance
        spawner._instances["task-1"] = {
            "instance_id": "cc-1",
            "started_at": datetime.now(timezone.utc),
        }

        status = spawner.get_status()
        assert status["available_capacity"] == 2

    def test_initialize_with_max_instances(self, tmp_path):
        """Test that initialize_claude_code_spawner passes max_instances."""
        workspace = str(tmp_path / "workspace")

        spawner = initialize_claude_code_spawner(
            workspace_path=workspace,
            max_instances=5
        )

        assert spawner.max_instances == 5
        # Cleanup global
        set_claude_code_spawner(None)


class TestSetupExistingBranch:
    """Tests for _setup_existing_branch method."""

    def test_setup_existing_branch_clones_and_checks_out(self, tmp_path):
        """Test that _setup_existing_branch clones repo and checks out existing branch."""
        spawner = make_spawner(tmp_path)

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()

        git_calls = []

        def mock_run_git(args, cwd=None, git_token=None):
            git_calls.append(args)
            # Create the repo directory for clone
            if args[0] == "clone":
                repo_dir = Path(args[-1])
                repo_dir.mkdir(parents=True, exist_ok=True)
            return MagicMock(returncode=0)

        with patch.object(spawner, '_run_git_command', side_effect=mock_run_git):
            result = spawner._setup_existing_branch(
                instance_workspace=instance_workspace,
                repo_url="git@server:repo.git",
                branch="feat/existing-branch",
                git_token="cvn-ct-tmptoken"
            )

        # Should have cloned and checked out
        assert len(git_calls) == 2
        assert git_calls[0][0] == "clone"
        assert "git@server:repo.git" in git_calls[0]
        assert git_calls[1] == ["checkout", "feat/existing-branch"]
        assert result == instance_workspace / "repo"

    def test_setup_existing_branch_clone_failure(self, tmp_path):
        """Test _setup_existing_branch when clone fails."""
        spawner = make_spawner(tmp_path)

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()

        def mock_run_git(args, cwd=None, git_token=None):
            raise subprocess.CalledProcessError(128, "git clone", stderr="fatal: repo not found")

        with patch.object(spawner, '_run_git_command', side_effect=mock_run_git):
            with pytest.raises(subprocess.CalledProcessError):
                spawner._setup_existing_branch(
                    instance_workspace=instance_workspace,
                    repo_url="git@server:repo.git",
                    branch="feat/test"
                )


class TestSpawnConflictResolution:
    """Tests for spawn_conflict_resolution method."""

    @pytest.mark.asyncio
    async def test_spawn_conflict_resolution_success(self, tmp_path):
        """Test successful conflict resolution spawn."""
        spawner = make_spawner(
            tmp_path,
            serving_url="http://serving:8002",
            compute_id="compute-001",
            max_instances=2,
        )

        # Set up an existing instance with repo info
        spawner._instances["task-original"] = {
            "instance_id": "cc-original",
            "branch_name": "feat/some-work",
            "event": {
                "context": {
                    "repository": "git@server:project.git",
                    "git_token": "cvn-ct-tmptoken"
                }
            }
        }

        conflict_data = {
            "issue_id": "issue-123",
            "branch": "feat/some-work",
            "conflicting_files": ["src/app.py", "tests/test_app.py"],
            "main_head": "abc123",
            "message": "Resolve conflicts please"
        }

        with patch.object(spawner, '_setup_existing_branch') as mock_setup, \
             patch.object(spawner, '_create_claude_md', return_value="# CLAUDE.md"), \
             patch.object(spawner, '_setup_mcp_tools', return_value={}) as mock_mcp, \
             patch.object(spawner, '_start_task', new_callable=AsyncMock) as mock_start, \
             patch.object(spawner, 'send_claude_code_started', new_callable=AsyncMock) as mock_event, \
             patch('services.claude_code_spawner.subprocess.run') as mock_subproc:

            repo_path = tmp_path / "repo"
            repo_path.mkdir()
            mock_setup.return_value = repo_path

            result = await spawner.spawn_conflict_resolution(conflict_data)

        assert result is True
        mock_setup.assert_called_once()
        assert mock_setup.call_args[1]["branch"] == "feat/some-work"
        assert mock_setup.call_args[1]["repo_url"] == "git@server:project.git"
        mock_start.assert_called_once()
        mock_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_spawn_conflict_resolution_no_branch(self, tmp_path):
        """Test spawn_conflict_resolution fails without branch."""
        spawner = make_spawner(tmp_path)

        result = await spawner.spawn_conflict_resolution({
            "issue_id": "issue-123",
            "conflicting_files": ["file.py"],
            "main_head": "abc123",
            "message": "Resolve"
        })

        assert result is False

    @pytest.mark.asyncio
    async def test_spawn_conflict_resolution_no_repo_url(self, tmp_path):
        """Test spawn_conflict_resolution fails when no repo URL is available."""
        spawner = make_spawner(tmp_path)

        # No instances with repo info
        spawner._instances = {}

        result = await spawner.spawn_conflict_resolution({
            "issue_id": "issue-123",
            "branch": "feat/test",
            "conflicting_files": ["file.py"],
            "main_head": "abc123",
            "message": "Resolve"
        })

        assert result is False

    @pytest.mark.asyncio
    async def test_spawn_conflict_resolution_git_setup_failure(self, tmp_path):
        """Test spawn_conflict_resolution handles git setup failure."""
        spawner = make_spawner(tmp_path, max_instances=2)

        spawner._instances["task-original"] = {
            "instance_id": "cc-original",
            "event": {
                "context": {"repository": "git@server:repo.git"}
            }
        }

        conflict_data = {
            "issue_id": "issue-123",
            "branch": "feat/test",
            "conflicting_files": ["file.py"],
            "main_head": "abc123",
            "message": "Resolve"
        }

        with patch.object(spawner, '_setup_existing_branch',
                         side_effect=subprocess.CalledProcessError(128, "git", stderr="fatal")):
            result = await spawner.spawn_conflict_resolution(conflict_data)

        assert result is False

    @pytest.mark.asyncio
    async def test_spawn_conflict_resolution_start_task_failure(self, tmp_path):
        """Test spawn_conflict_resolution handles task start failure."""
        spawner = make_spawner(
            tmp_path,
            serving_url="http://serving:8002",
            compute_id="compute-001",
            max_instances=2,
        )

        spawner._instances["task-original"] = {
            "instance_id": "cc-original",
            "event": {
                "context": {"repository": "git@server:repo.git"}
            }
        }

        conflict_data = {
            "issue_id": "issue-123",
            "branch": "feat/test",
            "conflicting_files": ["file.py"],
            "main_head": "abc123",
            "message": "Resolve"
        }

        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        with patch.object(spawner, '_setup_existing_branch', return_value=repo_path), \
             patch.object(spawner, '_create_claude_md', return_value="# CLAUDE.md"), \
             patch.object(spawner, '_setup_mcp_tools', return_value={}), \
             patch.object(spawner, '_start_task', new_callable=AsyncMock,
                         side_effect=Exception("Task failed")), \
             patch.object(spawner, 'send_claude_code_failed', new_callable=AsyncMock) as mock_fail, \
             patch('services.claude_code_spawner.subprocess.run'):

            result = await spawner.spawn_conflict_resolution(conflict_data)

        assert result is False
        mock_fail.assert_called_once()

    @pytest.mark.asyncio
    async def test_spawn_conflict_resolution_creates_correct_claude_md(self, tmp_path):
        """Test that conflict resolution CLAUDE.md contains resolution instructions."""
        spawner = make_spawner(tmp_path, max_instances=2)

        spawner._instances["task-original"] = {
            "instance_id": "cc-original",
            "event": {
                "context": {"repository": "git@server:repo.git"}
            }
        }

        conflict_data = {
            "issue_id": "issue-123",
            "branch": "feat/feature-branch",
            "conflicting_files": ["src/main.py", "src/utils.py"],
            "main_head": "def456",
            "message": "Please fix conflicts"
        }

        captured_event = {}

        def capture_claude_md(event):
            captured_event.update(event)
            return "# CLAUDE.md"

        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        with patch.object(spawner, '_setup_existing_branch', return_value=repo_path), \
             patch.object(spawner, '_create_claude_md', side_effect=capture_claude_md), \
             patch.object(spawner, '_setup_mcp_tools', return_value={}), \
             patch.object(spawner, '_start_task', new_callable=AsyncMock), \
             patch.object(spawner, 'send_claude_code_started', new_callable=AsyncMock), \
             patch('services.claude_code_spawner.subprocess.run'):

            await spawner.spawn_conflict_resolution(conflict_data)

        # Verify the work event passed to _create_claude_md
        assert "Conflict Resolution Task" in captured_event["description"]
        assert "feat/feature-branch" in captured_event["description"]
        assert "src/main.py" in captured_event["description"]
        assert "src/utils.py" in captured_event["description"]
        assert "git push --force-with-lease" in captured_event["description"]
        assert "Please fix conflicts" in captured_event["description"]
        assert captured_event["branch_name"] == "feat/feature-branch"
        assert "conflict resolution specialist" in captured_event["skills"]["merged_instructions"]


# =============================================================================
# Git User Context — No su/chown in git operations (#830)
# =============================================================================


class TestGitOpsRunAsCurrentUser:
    """Tests that git operations run as the current process user, not via su.

    After #825 (run entire service as compute user via gosu), all git ops
    should run directly — no su wrapper, no chown needed. These tests verify
    the spawner's git methods invoke git directly without user switching.

    Gap coverage for #830: the e2e test (test_git_workflow_e2e.py) validates
    git logic (hooks, merge, conflict) but runs everything as the same user,
    missing the ownership/permission bugs that caused 100% push failure in test7.
    """

    def test_run_git_command_invokes_git_directly(self, tmp_path):
        """_run_git_command runs ['git', ...] — no su, no sudo wrapper."""
        spawner = make_spawner(tmp_path)

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            spawner._run_git_command(
                ["clone", "ssh://git@serving:2222/repo.git", "/workspace/repo"],
                git_token="cvn-ct-compute001token"
            )

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "git", "Git command must start with 'git', not 'su' or 'sudo'"
        assert "su" not in cmd, "Git commands must not use 'su' wrapper"
        assert "sudo" not in cmd, "Git commands must not use 'sudo' wrapper"

    def test_run_git_command_uses_http_token_auth(self, tmp_path):
        """_run_git_command sets GIT_ASKPASS for HTTP token auth."""
        spawner = make_spawner(tmp_path)

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            spawner._run_git_command(
                ["clone", "http://serving:8002/git/repo.git"],
                git_token="cvn-ct-compute001token"
            )

        env = mock_run.call_args[1]["env"]
        assert "GIT_ASKPASS" in env
        assert "GIT_TERMINAL_PROMPT" in env

    @pytest.mark.asyncio
    async def test_commit_and_push_runs_git_directly(self, tmp_path):
        """_commit_and_push_changes runs git commands directly, no su."""
        spawner = make_spawner(tmp_path)

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        instance = {
            "repo_path": str(repo_dir),
            "event": {
                "context": {
                    "git_token": "cvn-ct-compute001token"
                }
            }
        }

        with patch('subprocess.run') as mock_run:
            # git status shows changes, then git add, git commit, git push
            status_result = Mock()
            status_result.stdout = "M src/app.py"
            mock_run.side_effect = [status_result, Mock(), Mock(), Mock()]

            await spawner._commit_and_push_changes("task-1", "cc-1", instance)

        # All subprocess calls should be git commands, not su-wrapped
        for call_obj in mock_run.call_args_list:
            cmd = call_obj[0][0]
            assert cmd[0] == "git", f"Expected 'git' command, got: {cmd}"
            assert "su" not in cmd

    @pytest.mark.asyncio
    async def test_commit_and_push_uses_token_for_push(self, tmp_path):
        """_commit_and_push_changes sets GIT_ASKPASS on the push call."""
        spawner = make_spawner(tmp_path)

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        instance = {
            "repo_path": str(repo_dir),
            "event": {
                "context": {
                    "git_token": "cvn-ct-compute001token"
                }
            }
        }

        with patch('subprocess.run') as mock_run:
            # No changes, just push
            status_result = Mock()
            status_result.stdout = ""
            mock_run.side_effect = [status_result, Mock()]

            await spawner._commit_and_push_changes("task-1", "cc-1", instance)

        # Push call (last) should have token auth env
        push_call = mock_run.call_args_list[-1]
        push_cmd = push_call[0][0]
        assert push_cmd == ["git", "push", "origin", "HEAD"]
        env = push_call[1].get("env") or push_call.kwargs.get("env", {})
        assert "GIT_ASKPASS" in env


class TestGitAskpassAbsolutePath:
    """Regression tests for #53: GIT_ASKPASS must use absolute paths."""

    @pytest.mark.asyncio
    async def test_start_task_askpass_is_absolute_path(self, tmp_path):
        """GIT_ASKPASS set during SDK launch must be an absolute path."""
        spawner = make_spawner(tmp_path)

        instance_workspace = tmp_path / "instance"
        instance_workspace.mkdir()

        askpass_dir = tmp_path / "workspace" / "cc-abs"
        askpass_dir.mkdir(parents=True, exist_ok=True)

        event = {
            "task_id": "task-abs",
            "context": {
                "git_token": "cvn-ct-testtoken",
                "repository": "http://serving:8002/git/repo.git",
            },
        }

        spawner._instances["task-abs"] = {
            "instance_id": "cc-abs",
            "task_id": "task-abs",
            "workspace": str(instance_workspace),
            "started_at": datetime.now(timezone.utc),
        }

        captured = {}

        async def capture_run(task_id, instance_id, prompt, cwd, mcp_servers, env_vars):
            captured["env_vars"] = env_vars

        with patch.object(spawner, "_run_and_handle_result", side_effect=capture_run):
            await spawner._start_task("task-abs", "cc-abs", instance_workspace, event, {})

        task = spawner._execution_tasks.get("task-abs")
        if task:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass

        env = captured.get("env_vars", {})
        askpass_path = env.get("GIT_ASKPASS", "")
        assert os.path.isabs(askpass_path), (
            f"GIT_ASKPASS must be absolute, got: {askpass_path}"
        )

    @pytest.mark.asyncio
    async def test_fallback_push_askpass_is_absolute_path(self, tmp_path):
        """GIT_ASKPASS set during fallback push must be an absolute path."""
        spawner = make_spawner(tmp_path)

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        instance = {
            "repo_path": str(repo_dir),
            "event": {
                "context": {
                    "git_token": "cvn-ct-compute001token",
                },
            },
        }

        with patch("subprocess.run") as mock_run:
            status_result = Mock()
            status_result.stdout = ""
            mock_run.side_effect = [status_result, Mock()]

            await spawner._commit_and_push_changes("task-1", "cc-1", instance)

        push_call = mock_run.call_args_list[-1]
        env = push_call[1].get("env") or push_call.kwargs.get("env", {})
        askpass_path = env.get("GIT_ASKPASS", "")
        assert os.path.isabs(askpass_path), (
            f"GIT_ASKPASS must be absolute, got: {askpass_path}"
        )
