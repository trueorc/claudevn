"""Tests for work orchestrator service."""

import time
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from services.work_orchestrator import (
    WorkOrchestrator,
    get_work_orchestrator,
    set_work_orchestrator
)
from models.work_map import (
    WorkItem,
    WorkListResponse,
    WorkStatus,
    WorkPriority,
)
from models.conflict import ConflictType


@pytest.fixture
def orchestrator():
    """Create an orchestrator for testing."""
    return WorkOrchestrator(
        poll_interval=1,
        max_concurrent_spawns=3,
        max_retries=2,
        retry_delay=5
    )


class TestWorkOrchestrator:
    """Test WorkOrchestrator class."""

    def test_init(self, orchestrator):
        """Test orchestrator initialization."""
        assert orchestrator.poll_interval == 1
        assert orchestrator.max_concurrent_spawns == 3
        assert orchestrator.max_retries == 2
        assert orchestrator.retry_delay == 5
        assert not orchestrator.is_running()
        assert not orchestrator.is_paused()

    def test_init_has_skill_cache(self, orchestrator):
        """Test orchestrator initializes with skill cache."""
        assert orchestrator._skill_cache == {}
        assert orchestrator._skill_cache_ttl == 300

    def test_get_stats_initial(self, orchestrator):
        """Test initial stats."""
        stats = orchestrator.get_stats()
        assert stats["total_spawned"] == 0
        assert stats["total_assigned"] == 0
        assert stats["total_failed"] == 0
        assert stats["running"] is False
        assert stats["paused"] is False
        assert stats["active_spawns"] == 0

    def test_pause_resume(self, orchestrator):
        """Test pause and resume."""
        assert not orchestrator.is_paused()

        orchestrator.pause()
        assert orchestrator.is_paused()

        orchestrator.resume()
        assert not orchestrator.is_paused()

    @pytest.mark.asyncio
    async def test_start_stop(self, orchestrator):
        """Test start and stop."""
        assert not orchestrator.is_running()

        await orchestrator.start()
        assert orchestrator.is_running()

        await orchestrator.stop()
        assert not orchestrator.is_running()

    @pytest.mark.asyncio
    async def test_start_twice_warns(self, orchestrator, caplog):
        """Test starting twice logs warning."""
        await orchestrator.start()
        await orchestrator.start()  # Should warn

        await orchestrator.stop()
        assert "already running" in caplog.text.lower()

    def test_handle_spawn_failure_retry(self, orchestrator):
        """Test spawn failure handling with retry tracking."""
        work_id = "work_test123"

        # First failure
        orchestrator._handle_spawn_failure(work_id, "Test error")
        assert orchestrator._retry_counts[work_id] == 1
        assert work_id in orchestrator._retry_after

        # Second failure
        orchestrator._handle_spawn_failure(work_id, "Test error 2")
        assert orchestrator._retry_counts[work_id] == 2

    def test_handle_spawn_failure_max_retries(self, orchestrator):
        """Test spawn failure exceeds max retries."""
        work_id = "work_maxretry"

        # Exceed max retries
        for i in range(orchestrator.max_retries + 1):
            orchestrator._handle_spawn_failure(work_id, f"Error {i}")

        assert orchestrator._retry_counts[work_id] == orchestrator.max_retries + 1
        assert orchestrator._stats["total_failed"] == orchestrator.max_retries + 1


class TestWorkOrchestratorGlobals:
    """Test global instance management."""

    def test_set_get_orchestrator(self):
        """Test setting and getting global orchestrator."""
        orch = WorkOrchestrator()
        set_work_orchestrator(orch)

        retrieved = get_work_orchestrator()
        assert retrieved is orch

    def test_get_orchestrator_none(self):
        """Test getting orchestrator when not set returns None."""
        set_work_orchestrator(None)
        result = get_work_orchestrator()
        assert result is None


class TestOrchestratorSkillSelection:
    """Test skill selection logic (now sync, no HTTP calls)."""

    def test_select_skills_with_skill_ids(self, orchestrator):
        """Test skill selection prefers pre-resolved skill_ids."""
        mock_work = MagicMock()
        mock_work.skill_ids = ["pre-resolved-a", "pre-resolved-b"]
        mock_work.required_skills = ["skill-a"]
        mock_work.work_type = "feature"

        skills = orchestrator._select_skills_for_work(mock_work)
        assert skills == ["pre-resolved-a", "pre-resolved-b"]

    def test_select_skills_with_required_skills(self, orchestrator):
        """Test skill selection falls back to required_skills when no skill_ids."""
        mock_work = MagicMock()
        mock_work.skill_ids = []
        mock_work.required_skills = ["skill-a", "skill-b"]
        mock_work.work_type = "feature"

        skills = orchestrator._select_skills_for_work(mock_work)
        assert skills == ["skill-a", "skill-b"]

    def test_select_skills_fallback_by_type(self, orchestrator):
        """Test skill selection falls back to work type mapping."""
        mock_work = MagicMock()
        mock_work.skill_ids = []
        mock_work.required_skills = []
        mock_work.work_type = "bug"

        skills = orchestrator._select_skills_for_work(mock_work)
        assert skills == ["debugger"]

    def test_select_skills_default_code_writer(self, orchestrator):
        """Test skill selection defaults to code-writer for unknown type."""
        mock_work = MagicMock()
        mock_work.skill_ids = []
        mock_work.required_skills = []
        mock_work.work_type = "unknown"

        skills = orchestrator._select_skills_for_work(mock_work)
        assert skills == ["code-writer"]

    def test_select_skills_all_work_types(self, orchestrator):
        """Test deterministic fallback for all known work types."""
        expected = {
            "feature": ["code-writer"],
            "bug": ["debugger"],
            "refactor": ["refactorer"],
            "test": ["test-automator"],
            "docs": ["doc-writer"],
            "review": ["code-reviewer"],
        }
        for work_type, expected_skills in expected.items():
            mock_work = MagicMock()
            mock_work.skill_ids = []
            mock_work.required_skills = []
            mock_work.work_type = work_type

            skills = orchestrator._select_skills_for_work(mock_work)
            assert skills == expected_skills, f"Failed for work_type={work_type}"

    def test_select_skills_is_sync(self, orchestrator):
        """Verify _select_skills_for_work is not a coroutine."""
        import asyncio
        mock_work = MagicMock()
        mock_work.skill_ids = ["a"]
        mock_work.required_skills = []
        mock_work.work_type = "feature"

        result = orchestrator._select_skills_for_work(mock_work)
        assert not asyncio.iscoroutine(result)
        assert result == ["a"]


class TestOrchestratorTrigger:
    """Test immediate trigger functionality."""

    @pytest.mark.asyncio
    async def test_trigger_when_paused(self, orchestrator):
        """Test trigger when paused returns paused status."""
        orchestrator.pause()
        result = await orchestrator.trigger_immediate()

        assert result["status"] == "paused"

    @pytest.mark.asyncio
    async def test_trigger_immediate(self, orchestrator):
        """Test trigger immediate processes work."""
        with patch.object(orchestrator, "_process_pending_work", new_callable=AsyncMock) as mock_process:
            result = await orchestrator.trigger_immediate()

        mock_process.assert_called_once()
        assert result["status"] == "completed"


class TestOrchestratorTimeoutConfig:
    """Test timeout configuration for stuck-work detection."""

    def test_init_with_timeout_config(self):
        """Test orchestrator initialization with timeout config."""
        orch = WorkOrchestrator(
            poll_interval=10,
            timeout_minutes=45,
            timeout_check_interval=120,
            timeout_max_retries=5,
            timeout_enabled=True
        )
        assert orch.timeout_minutes == 45
        assert orch.timeout_check_interval == 120
        assert orch.timeout_max_retries == 5
        assert orch.timeout_enabled is True

    def test_init_with_timeout_disabled(self):
        """Test orchestrator initialization with timeout disabled."""
        orch = WorkOrchestrator(timeout_enabled=False)
        assert orch.timeout_enabled is False

    def test_get_stats_includes_timeout_info(self):
        """Test stats include timeout monitoring info."""
        orch = WorkOrchestrator(timeout_minutes=60, timeout_enabled=True)
        stats = orch.get_stats()

        assert "timeout_monitoring_enabled" in stats
        assert stats["timeout_monitoring_enabled"] is True
        assert "timeout_minutes" in stats
        assert stats["timeout_minutes"] == 60
        assert "total_timeouts" in stats
        assert "total_timeout_retries" in stats

    @pytest.mark.asyncio
    async def test_start_with_timeout_enabled(self):
        """Test start creates timeout monitoring task when enabled."""
        orch = WorkOrchestrator(timeout_enabled=True)
        await orch.start()

        assert orch._timeout_task is not None
        assert not orch._timeout_task.done()

        await orch.stop()

    @pytest.mark.asyncio
    async def test_start_with_timeout_disabled(self):
        """Test start does not create timeout task when disabled."""
        orch = WorkOrchestrator(timeout_enabled=False)
        await orch.start()

        assert orch._timeout_task is None

        await orch.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_timeout_task(self):
        """Test stop properly cancels timeout monitoring task."""
        orch = WorkOrchestrator(timeout_enabled=True)
        await orch.start()

        timeout_task = orch._timeout_task
        await orch.stop()

        assert timeout_task.cancelled() or timeout_task.done()


class TestOrchestratorStaleWorkDetection:
    """Test stale work detection and handling."""

    @pytest.mark.asyncio
    async def test_detect_and_handle_stale_work(self):
        """Test stale work detection calls work map service."""
        orch = WorkOrchestrator(timeout_minutes=30, timeout_max_retries=3)

        mock_work = MagicMock()
        mock_work.work_id = "work_stale123"
        mock_work.status = WorkStatus.IN_PROGRESS

        with patch("services.work_map_service.get_work_map_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_stale_work = AsyncMock(return_value=[mock_work])
            mock_service.get_stale_assigned_work = AsyncMock(return_value=[])
            mock_service.mark_work_timed_out = AsyncMock(return_value=MagicMock(
                status=WorkStatus.PENDING,
                retry_count=1
            ))
            mock_get_service.return_value = mock_service

            await orch._detect_and_handle_stale_work()

            mock_service.get_stale_work.assert_called_once_with(30)
            mock_service.mark_work_timed_out.assert_called_once_with("work_stale123", 3)

    @pytest.mark.asyncio
    async def test_detect_stale_work_increments_stats(self):
        """Test that detecting stale work updates statistics."""
        orch = WorkOrchestrator(timeout_minutes=30)

        mock_work = MagicMock()
        mock_work.work_id = "work_timeout1"

        with patch("services.work_map_service.get_work_map_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_stale_work = AsyncMock(return_value=[mock_work])
            mock_service.get_stale_assigned_work = AsyncMock(return_value=[])
            mock_service.mark_work_timed_out = AsyncMock(return_value=MagicMock(
                status=WorkStatus.PENDING,
                retry_count=1
            ))
            mock_get_service.return_value = mock_service

            await orch._detect_and_handle_stale_work()

            assert orch._stats["total_timeouts"] == 1
            assert orch._stats["total_timeout_retries"] == 1

    @pytest.mark.asyncio
    async def test_detect_stale_work_no_stale_items(self):
        """Test detection with no stale work items."""
        orch = WorkOrchestrator(timeout_minutes=30)

        with patch("services.work_map_service.get_work_map_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_stale_work = AsyncMock(return_value=[])
            mock_service.get_stale_assigned_work = AsyncMock(return_value=[])
            mock_get_service.return_value = mock_service

            await orch._detect_and_handle_stale_work()

            assert orch._stats["total_timeouts"] == 0

    @pytest.mark.asyncio
    async def test_detect_stale_work_failed_status(self):
        """Test that work marked FAILED doesn't count as retry."""
        orch = WorkOrchestrator(timeout_minutes=30)

        mock_work = MagicMock()
        mock_work.work_id = "work_maxed"

        with patch("services.work_map_service.get_work_map_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_stale_work = AsyncMock(return_value=[mock_work])
            mock_service.get_stale_assigned_work = AsyncMock(return_value=[])
            mock_service.mark_work_timed_out = AsyncMock(return_value=MagicMock(
                status=WorkStatus.FAILED,
                retry_count=3
            ))
            mock_get_service.return_value = mock_service

            await orch._detect_and_handle_stale_work()

            assert orch._stats["total_timeouts"] == 1
            # FAILED status should not increment retry count
            assert orch._stats["total_timeout_retries"] == 0

    @pytest.mark.asyncio
    async def test_detect_stale_assigned_work_recovers(self):
        """Test that stale ASSIGNED items are recovered to PENDING."""
        orch = WorkOrchestrator(timeout_minutes=30, assigned_timeout_minutes=3)

        mock_stale = MagicMock()
        mock_stale.work_id = "work_orphan"
        mock_stale.assigned_to = "compute-001"
        mock_stale.assigned_at = "2026-01-01T00:00:00Z"
        mock_stale.issue_id = None
        mock_stale.context = None

        with patch("services.work_map_service.get_work_map_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_stale_work = AsyncMock(return_value=[])
            mock_service.get_stale_assigned_work = AsyncMock(return_value=[mock_stale])
            mock_service.reset_assigned_to_pending = AsyncMock(return_value=MagicMock(
                status=WorkStatus.PENDING
            ))
            mock_get_service.return_value = mock_service

            await orch._detect_and_handle_stale_work()

            mock_service.get_stale_assigned_work.assert_called_once_with(3)
            mock_service.reset_assigned_to_pending.assert_called_once_with("work_orphan")
            assert orch._stats["total_assigned_recoveries"] == 1


class TestOrchestratorSSEWorkAssignment:
    """Test SSE-based work assignment flow."""

    @pytest.fixture
    def orchestrator(self):
        """Create an orchestrator for testing."""
        return WorkOrchestrator(poll_interval=1, max_concurrent_spawns=3)

    @pytest.fixture
    def mock_work(self):
        """Create a mock work item."""
        work = MagicMock()
        work.work_id = "work_sse123"
        work.title = "Test SSE Work"
        work.description = "Test description"
        work.required_capabilities = ["coding"]
        work.required_skills = []
        work.skill_ids = []
        work.work_type = "feature"
        work.project_id = "project-1"
        work.base_branch = "main"
        work.repo_url = "git@test:repo.git"
        work.issue_id = None
        work.context = {}
        return work

    @pytest.mark.asyncio
    async def test_try_assign_via_sse_success(self, orchestrator, mock_work):
        """Test successful work assignment via SSE."""
        with patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse, \
             patch("services.work_map_service.get_work_map_service") as mock_work_map, \
             patch("services.marketplace_client.get_marketplace_client") as mock_marketplace:

            # Set up SSE connection manager with an idle connection
            mock_connection = MagicMock()
            mock_connection.compute_id = "compute-001"
            mock_connection.status = "idle"

            mock_sse_manager = MagicMock()
            mock_sse_manager.find_matching_connection.return_value = mock_connection
            mock_sse_manager.send_work_assigned = AsyncMock(return_value=True)
            mock_sse.return_value = mock_sse_manager

            # Set up work map service
            mock_map_service = MagicMock()
            mock_map_service.assign_work = AsyncMock()
            mock_map_service.set_issue_compute_id = AsyncMock()
            mock_map_service.update_issue_status = AsyncMock()
            mock_work_map.return_value = mock_map_service

            # Set up marketplace client
            mock_marketplace.return_value.get_skill = AsyncMock(return_value={
                "name": "Code Writer",
                "instructions": "Write code"
            })

            result = await orchestrator._try_assign_via_sse(mock_work, ["code-writer"])

            assert result is True
            mock_sse_manager.find_matching_connection.assert_called_once()
            mock_sse_manager.send_work_assigned.assert_called_once()
            mock_map_service.assign_work.assert_called_once_with(
                work_id="work_sse123",
                compute_id="compute-001",
                skills=["code-writer"],
                branch_name="f/work_sse123/compute-001"
            )

    @pytest.mark.asyncio
    async def test_try_assign_via_sse_no_connection(self, orchestrator, mock_work):
        """Test SSE assignment fails when no connection available."""
        with patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse:
            mock_sse_manager = MagicMock()
            mock_sse_manager.find_matching_connection.return_value = None
            mock_sse.return_value = mock_sse_manager

            result = await orchestrator._try_assign_via_sse(mock_work, ["code-writer"])

            assert result is False

    @pytest.mark.asyncio
    async def test_try_assign_via_sse_send_fails(self, orchestrator, mock_work):
        """Test SSE assignment fails when send fails."""
        with patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse, \
             patch("services.marketplace_client.get_marketplace_client") as mock_marketplace:

            mock_connection = MagicMock()
            mock_connection.compute_id = "compute-001"

            mock_sse_manager = MagicMock()
            mock_sse_manager.find_matching_connection.return_value = mock_connection
            mock_sse_manager.send_work_assigned = AsyncMock(return_value=False)
            mock_sse.return_value = mock_sse_manager

            mock_marketplace.return_value.get_skill = AsyncMock(return_value=None)

            result = await orchestrator._try_assign_via_sse(mock_work, ["code-writer"])

            assert result is False

    @pytest.mark.asyncio
    async def test_spawn_for_work_uses_sse_first(self, orchestrator, mock_work):
        """Test that _spawn_for_work tries SSE assignment first."""
        with patch.object(orchestrator, "_select_skills_for_work", return_value=["code-writer"]) as mock_select, \
             patch.object(orchestrator, "_resolve_model_for_skills", new_callable=AsyncMock, return_value=None), \
             patch.object(orchestrator, "_try_assign_via_sse", new_callable=AsyncMock) as mock_sse, \
             patch.object(orchestrator, "_spawn_new_compute", new_callable=AsyncMock) as mock_spawn:

            mock_sse.return_value = True  # SSE assignment succeeds

            await orchestrator._spawn_for_work(mock_work)

            mock_sse.assert_called_once_with(mock_work, ["code-writer"], None, None)
            mock_spawn.assert_not_called()
            assert orchestrator._stats["total_assigned"] == 1

    @pytest.mark.asyncio
    async def test_spawn_for_work_falls_back_to_spawning(self, orchestrator, mock_work):
        """Test that _spawn_for_work falls back to direct spawning."""
        with patch.object(orchestrator, "_select_skills_for_work", return_value=["code-writer"]) as mock_select, \
             patch.object(orchestrator, "_resolve_model_for_skills", new_callable=AsyncMock, return_value=None), \
             patch.object(orchestrator, "_try_assign_via_sse", new_callable=AsyncMock) as mock_sse, \
             patch.object(orchestrator, "_spawn_new_compute", new_callable=AsyncMock) as mock_spawn:

            mock_sse.return_value = False  # No SSE connection available

            await orchestrator._spawn_for_work(mock_work)

            mock_sse.assert_called_once()
            mock_spawn.assert_called_once_with(mock_work, ["code-writer"], None)

    @pytest.mark.asyncio
    async def test_spawn_new_compute(self, orchestrator, mock_work):
        """Test direct compute spawning fallback."""
        with patch("services.compute_spawner.get_compute_spawner") as mock_spawner:
            mock_spawn_response = MagicMock()
            mock_spawn_response.compute_id = "compute-new"
            mock_spawn_response.state = "running"
            mock_spawn_response.initial_work = {"work_id": "work_sse123"}

            spawner_instance = MagicMock()
            spawner_instance.spawn = AsyncMock(return_value=mock_spawn_response)
            mock_spawner.return_value = spawner_instance

            await orchestrator._spawn_new_compute(mock_work, ["code-writer"])

            spawner_instance.spawn.assert_called_once()
            assert orchestrator._stats["total_spawned"] == 1
            assert orchestrator._stats["total_assigned"] == 1

    @pytest.mark.asyncio
    async def test_spawn_new_compute_with_labels_and_tools(self, orchestrator):
        """Test direct compute spawning includes labels and tools in spawn request."""
        mock_work = MagicMock()
        mock_work.work_id = "work_labeled"
        mock_work.required_capabilities = ["coding"]
        mock_work.required_labels = ["production-access", "database-admin"]
        mock_work.required_tools = ["deploy_prod", "db_migrate"]
        mock_work.project_id = "project-1"
        mock_work.base_branch = "main"

        with patch("services.compute_spawner.get_compute_spawner") as mock_spawner:
            mock_spawn_response = MagicMock()
            mock_spawn_response.compute_id = "compute-prod"
            mock_spawn_response.state = "running"
            mock_spawn_response.initial_work = None

            spawner_instance = MagicMock()
            spawner_instance.spawn = AsyncMock(return_value=mock_spawn_response)
            mock_spawner.return_value = spawner_instance

            await orchestrator._spawn_new_compute(mock_work, ["deployer"])

            # Verify spawn was called with labels and tools in the request
            spawner_instance.spawn.assert_called_once()
            spawn_request = spawner_instance.spawn.call_args[0][0]
            assert spawn_request.capabilities == ["coding"]
            assert spawn_request.labels == ["production-access", "database-admin"]
            assert spawn_request.tools_available == ["deploy_prod", "db_migrate"]

    @pytest.mark.asyncio
    async def test_compose_skills_for_sse_uses_compose_endpoint(self, orchestrator):
        """Test skill composition uses marketplace compose endpoint."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_marketplace:
            mock_marketplace.return_value.compose_agent = AsyncMock(return_value={
                "merged_instructions": "# Agent Configuration\n\n**Active Skills:** Code Writer, Test Writer\n\n## Skill Instructions\n\n### Code Writer\nWrite clean code.\n\n### Test Writer\nWrite tests.",
                "tools": ["read", "write"],
                "conflict_warnings": {"has_conflicts": False, "conflicts": [], "warnings": []}
            })

            result = await orchestrator._compose_skills_for_sse(
                ["code-writer", "test-writer"],
                "compute-001",
                work_id="work-123",
                task_description="Implement feature X"
            )

            assert "Agent Configuration" in result
            assert "Code Writer" in result
            assert "Test Writer" in result
            mock_marketplace.return_value.compose_agent.assert_called_once_with(
                task_id="work-123",
                task_description="Implement feature X",
                required_capabilities=[],
                skill_ids=["code-writer", "test-writer"],
            )

    @pytest.mark.asyncio
    async def test_compose_skills_for_sse_logs_conflicts(self, orchestrator):
        """Test that conflict warnings from compose endpoint are logged."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_marketplace:
            mock_marketplace.return_value.compose_agent = AsyncMock(return_value={
                "merged_instructions": "# Config\nInstructions here.",
                "conflict_warnings": {
                    "has_conflicts": True,
                    "conflicts": [{"skill_a": "a", "skill_b": "b", "reason": "test conflict"}],
                    "warnings": ["Tool overlap warning"]
                }
            })

            with patch("services.work_orchestrator.logger") as mock_logger:
                result = await orchestrator._compose_skills_for_sse(
                    ["skill-a", "skill-b"], "compute-001"
                )

                assert "Config" in result
                # Verify conflict and warning logs
                warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
                assert any("conflicts detected" in w.lower() or "conflict" in w.lower() for w in warning_calls)

    @pytest.mark.asyncio
    async def test_compose_skills_for_sse_empty(self, orchestrator):
        """Test skill composition with no skills."""
        result = await orchestrator._compose_skills_for_sse([], "compute-001")

        assert "Execute the assigned work" in result

    @pytest.mark.asyncio
    async def test_compose_skills_for_sse_fallback_on_compose_error(self, orchestrator):
        """Test fallback to inline fetching when compose endpoint fails."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_marketplace:
            # Compose endpoint fails
            mock_marketplace.return_value.compose_agent = AsyncMock(
                side_effect=Exception("Compose API error")
            )
            # Fallback individual get_skill works
            mock_marketplace.return_value.get_skill = AsyncMock(side_effect=[
                {"name": "Code Writer", "instructions": "Write clean code."},
            ])

            result = await orchestrator._compose_skills_for_sse(
                ["code-writer"], "compute-001"
            )

            # Should use fallback inline approach
            assert "# Code Writer" in result
            assert "Write clean code." in result

    @pytest.mark.asyncio
    async def test_compose_skills_for_sse_full_fallback_on_all_errors(self, orchestrator):
        """Test graceful degradation when both compose and individual fetch fail."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_marketplace:
            mock_marketplace.return_value.compose_agent = AsyncMock(
                side_effect=Exception("Compose API error")
            )
            mock_marketplace.return_value.get_skill = AsyncMock(
                side_effect=Exception("Get skill error")
            )

            result = await orchestrator._compose_skills_for_sse(
                ["code-writer"], "compute-001"
            )

            # Should return fallback message
            assert "Execute the assigned work" in result

    @pytest.mark.asyncio
    async def test_compose_skills_fallback_uses_cache(self, orchestrator):
        """Test that fallback path uses cached skill content."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_marketplace:
            # Compose endpoint fails
            mock_marketplace.return_value.compose_agent = AsyncMock(
                side_effect=Exception("Compose unavailable")
            )
            mock_get_skill = AsyncMock(return_value={
                "name": "Cached Skill",
                "instructions": "Cached instructions."
            })
            mock_marketplace.return_value.get_skill = mock_get_skill

            # First call — fetches from marketplace via fallback
            result1 = await orchestrator._compose_skills_for_sse(["skill-1"], "compute-001")
            assert "# Cached Skill" in result1
            assert mock_get_skill.call_count == 1

            # Second call — should use cache, no additional marketplace call
            result2 = await orchestrator._compose_skills_for_sse(["skill-1"], "compute-002")
            assert "# Cached Skill" in result2
            assert mock_get_skill.call_count == 1  # Still 1 — cache hit

    @pytest.mark.asyncio
    async def test_compose_skills_fallback_cache_expires(self, orchestrator):
        """Test that skill cache entries expire after TTL in fallback path."""
        orchestrator._skill_cache_ttl = 0  # Expire immediately

        with patch("services.marketplace_client.get_marketplace_client") as mock_marketplace:
            mock_marketplace.return_value.compose_agent = AsyncMock(
                side_effect=Exception("Compose unavailable")
            )
            mock_get_skill = AsyncMock(return_value={
                "name": "Expiring Skill",
                "instructions": "Will expire."
            })
            mock_marketplace.return_value.get_skill = mock_get_skill

            await orchestrator._compose_skills_for_sse(["skill-exp"], "compute-001")
            assert mock_get_skill.call_count == 1

            # Cache should be expired, so this should fetch again
            await orchestrator._compose_skills_for_sse(["skill-exp"], "compute-002")
            assert mock_get_skill.call_count == 2

    def test_get_cached_skill_returns_none_for_missing(self, orchestrator):
        """Test cache miss returns None."""
        assert orchestrator._get_cached_skill("nonexistent") is None

    def test_get_cached_skill_returns_data(self, orchestrator):
        """Test cache hit returns data."""
        orchestrator._set_cached_skill("test-skill", {"name": "Test"})
        result = orchestrator._get_cached_skill("test-skill")
        assert result == {"name": "Test"}

    def test_get_cached_skill_expired(self, orchestrator):
        """Test expired cache returns None."""
        orchestrator._skill_cache["expired-skill"] = ({"name": "Old"}, time.time() - 1)
        assert orchestrator._get_cached_skill("expired-skill") is None

    @pytest.mark.asyncio
    async def test_try_assign_via_sse_with_labels_and_tools(self, orchestrator):
        """Test SSE assignment respects labels and tools requirements."""
        mock_work = MagicMock()
        mock_work.work_id = "work_labeled"
        mock_work.title = "Labeled Work"
        mock_work.description = "Needs special access"
        mock_work.required_capabilities = ["coding"]
        mock_work.required_labels = ["production-access"]
        mock_work.required_tools = ["deploy_prod"]
        mock_work.base_branch = "main"

        with patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse, \
             patch("services.work_map_service.get_work_map_service") as mock_work_map, \
             patch("services.marketplace_client.get_marketplace_client") as mock_marketplace:

            mock_connection = MagicMock()
            mock_connection.compute_id = "compute-prod"

            mock_sse_manager = MagicMock()
            mock_sse_manager.find_matching_connection.return_value = mock_connection
            mock_sse_manager.send_work_assigned = AsyncMock(return_value=True)
            mock_sse.return_value = mock_sse_manager

            mock_map_service = MagicMock()
            mock_map_service.assign_work = AsyncMock()
            mock_work_map.return_value = mock_map_service

            mock_marketplace.return_value.get_skill = AsyncMock(return_value=None)

            await orchestrator._try_assign_via_sse(mock_work, ["deployer"])

            # Verify find_matching_connection was called with the right requirements
            mock_sse_manager.find_matching_connection.assert_called_once()
            call_kwargs = mock_sse_manager.find_matching_connection.call_args[1]
            assert call_kwargs["required_capabilities"] == ["coding"]
            assert call_kwargs["required_labels"] == ["production-access"]
            assert call_kwargs["required_tools"] == ["deploy_prod"]
            assert call_kwargs["idle_only"] is True

    @pytest.mark.asyncio
    async def test_try_assign_via_sse_no_requirements_fallback(self, orchestrator):
        """Test SSE assignment falls back to any available compute when no requirements."""
        mock_work = MagicMock()
        mock_work.work_id = "work_generic"
        mock_work.title = "Generic Work"
        mock_work.description = "No special requirements"
        mock_work.required_capabilities = []
        mock_work.required_labels = []
        mock_work.required_tools = []
        mock_work.base_branch = "main"

        with patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse, \
             patch("services.work_map_service.get_work_map_service") as mock_work_map, \
             patch("services.marketplace_client.get_marketplace_client") as mock_marketplace:

            mock_connection = MagicMock()
            mock_connection.compute_id = "compute-any"

            mock_sse_manager = MagicMock()
            mock_sse_manager.find_matching_connection.return_value = mock_connection
            mock_sse_manager.send_work_assigned = AsyncMock(return_value=True)
            mock_sse.return_value = mock_sse_manager

            mock_map_service = MagicMock()
            mock_map_service.assign_work = AsyncMock()
            mock_work_map.return_value = mock_map_service

            mock_marketplace.return_value.get_skill = AsyncMock(return_value=None)

            await orchestrator._try_assign_via_sse(mock_work, ["code-writer"])

            # Verify find_matching_connection was called with None for empty lists
            mock_sse_manager.find_matching_connection.assert_called_once()
            call_kwargs = mock_sse_manager.find_matching_connection.call_args[1]
            assert call_kwargs["required_capabilities"] is None
            assert call_kwargs["required_labels"] is None
            assert call_kwargs["required_tools"] is None
            assert call_kwargs["idle_only"] is True


class TestOrchestratorBatchDependencyCheck:
    """Test that the orchestrator uses batch dependency checks."""

    @pytest.fixture
    def orchestrator(self):
        return WorkOrchestrator(poll_interval=1, max_concurrent_spawns=3)

    @pytest.mark.asyncio
    async def test_process_pending_uses_batch_deps(self, orchestrator):
        """Test _process_pending_work calls get_dependencies_bulk instead of get_dependencies."""
        work1 = MagicMock()
        work1.work_id = "work-1"
        work1.priority = WorkPriority.NORMAL
        work1.created_at = datetime.now()
        work1.skill_ids = ["code-writer"]
        work1.required_skills = []
        work1.work_type = "feature"
        work1.issue_id = None
        work1.context = None

        work2 = MagicMock()
        work2.work_id = "work-2"
        work2.priority = WorkPriority.HIGH
        work2.created_at = datetime.now()
        work2.skill_ids = ["debugger"]
        work2.required_skills = []
        work2.work_type = "bug"
        work2.issue_id = None
        work2.context = None

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(
                items=[work1, work2]
            ))
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_work_map.get_failed_work = AsyncMock(return_value=[])
            # Batch dependency check
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={
                "work-1": True,
                "work-2": False,  # work-2 has unmet deps
            })
            mock_get_wms.return_value = mock_work_map

            with patch.object(orchestrator, "_spawn_for_work", new_callable=AsyncMock) as mock_spawn:
                await orchestrator._process_pending_work()

                # get_dependencies_bulk should be called once with both IDs
                mock_work_map.get_dependencies_bulk.assert_called_once_with(
                    ["work-1", "work-2"]
                )
                # Only work-1 should be spawned (work-2 has unmet deps)
                mock_spawn.assert_called_once()
                assert mock_spawn.call_args[0][0].work_id == "work-1"

    @pytest.mark.asyncio
    async def test_process_pending_no_candidates_skips_batch_check(self, orchestrator):
        """Test that batch dep check is skipped when no candidates pass local checks."""
        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(items=[]))
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_work_map.get_dependencies_bulk = AsyncMock()
            mock_get_wms.return_value = mock_work_map

            await orchestrator._process_pending_work()

            mock_work_map.get_dependencies_bulk.assert_not_called()


# ============================================================================
# Helpers for resource conflict tests
# ============================================================================


def _make_work_item(
    work_id="work_1",
    project_id="project_1",
    required_capabilities=None,
    priority=WorkPriority.NORMAL,
    status=WorkStatus.PENDING,
):
    """Create a WorkItem for testing."""
    return WorkItem(
        work_id=work_id,
        title=f"Test work {work_id}",
        description="Test description",
        project_id=project_id,
        required_capabilities=required_capabilities or [],
        priority=priority,
        status=status,
    )


def _make_sse_connection(
    compute_id="compute_1",
    capabilities=None,
    status="idle",
):
    """Create a mock SSE connection."""
    conn = MagicMock()
    conn.compute_id = compute_id
    conn.capabilities = capabilities or ["coding"]
    conn.status = status
    conn.labels = []
    conn.tools_available = []
    conn.current_task_id = None
    return conn


# ============================================================================
# Test _check_resource_conflicts
# ============================================================================


class TestCheckResourceConflicts:
    """Test the orchestrator's resource conflict detection integration."""

    @pytest.fixture
    def orch(self):
        return WorkOrchestrator(
            poll_interval=1, max_concurrent_spawns=5, timeout_enabled=False
        )

    @pytest.mark.asyncio
    async def test_skips_when_conflict_service_not_initialized(self, orch):
        """Should silently return when ConflictDetectionService is not available."""
        processable = [_make_work_item(required_capabilities=["coding"])]

        with patch(
            "services.conflict_detection_service.get_conflict_detection_service",
            side_effect=RuntimeError("Not initialized"),
        ):
            await orch._check_resource_conflicts(processable)

    @pytest.mark.asyncio
    async def test_skips_when_no_compute_connected(self, orch):
        """Should return early when no SSE connections exist."""
        processable = [_make_work_item(required_capabilities=["coding"])]

        mock_conflict_service = MagicMock()
        mock_sse_manager = MagicMock()
        mock_sse_manager.list_connections.return_value = []

        with patch(
            "services.conflict_detection_service.get_conflict_detection_service",
            return_value=mock_conflict_service,
        ), patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse_manager,
        ):
            await orch._check_resource_conflicts(processable)

        mock_conflict_service.detect_resource_conflicts.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_work_without_capabilities(self, orch):
        """Should skip projects where no work items have required capabilities."""
        processable = [_make_work_item(required_capabilities=[])]

        mock_conflict_service = MagicMock()
        mock_conflict_service.detect_resource_conflicts.return_value = []
        mock_conflict_service.store_resource_conflicts = AsyncMock()

        mock_sse_manager = MagicMock()
        mock_sse_manager.list_connections.return_value = [_make_sse_connection()]

        mock_work_map = MagicMock()
        mock_work_map.list_work = AsyncMock(
            return_value=WorkListResponse(
                items=[], total=0, by_status={}, by_priority={}
            )
        )

        with patch(
            "services.conflict_detection_service.get_conflict_detection_service",
            return_value=mock_conflict_service,
        ), patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse_manager,
        ), patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map,
        ):
            await orch._check_resource_conflicts(processable)

        mock_conflict_service.detect_resource_conflicts.assert_not_called()

    @pytest.mark.asyncio
    async def test_detects_capability_gap(self, orch):
        """Should detect when work requires a capability no compute provides."""
        processable = [
            _make_work_item(
                work_id="work_1",
                required_capabilities=["gpu_compute"],
                priority=WorkPriority.HIGH,
            )
        ]

        mock_report = MagicMock()
        mock_report.conflict_type = ConflictType.RESOURCE
        mock_conflict_service = MagicMock()
        mock_conflict_service.detect_resource_conflicts.return_value = [mock_report]
        mock_conflict_service.store_resource_conflicts = AsyncMock()

        mock_sse_manager = MagicMock()
        mock_sse_manager.list_connections.return_value = [
            _make_sse_connection(compute_id="c1", capabilities=["coding"])
        ]

        mock_work_map = MagicMock()
        mock_work_map.list_work = AsyncMock(
            return_value=WorkListResponse(
                items=[], total=0, by_status={}, by_priority={}
            )
        )

        with patch(
            "services.conflict_detection_service.get_conflict_detection_service",
            return_value=mock_conflict_service,
        ), patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse_manager,
        ), patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map,
        ):
            await orch._check_resource_conflicts(processable)

        call_args = mock_conflict_service.detect_resource_conflicts.call_args
        assert call_args.kwargs["project_id"] == "project_1"
        assert len(call_args.kwargs["resource_demands"]) == 1
        assert call_args.kwargs["resource_demands"][0]["capability"] == "gpu_compute"
        assert call_args.kwargs["resource_demands"][0]["task_id"] == "work_1"

        mock_conflict_service.store_resource_conflicts.assert_awaited_once_with(
            "project_1", [mock_report]
        )
        assert orch._stats["total_resource_conflicts"] == 1

    @pytest.mark.asyncio
    async def test_includes_in_progress_work_as_demands(self, orch):
        """Should include in-progress work items in resource demand calculations."""
        processable = [
            _make_work_item(work_id="pending_1", required_capabilities=["testing"])
        ]

        in_progress_item = _make_work_item(
            work_id="active_1",
            required_capabilities=["testing"],
            status=WorkStatus.IN_PROGRESS,
        )

        mock_conflict_service = MagicMock()
        mock_conflict_service.detect_resource_conflicts.return_value = []
        mock_conflict_service.store_resource_conflicts = AsyncMock()

        mock_sse_manager = MagicMock()
        mock_sse_manager.list_connections.return_value = [
            _make_sse_connection(compute_id="c1", capabilities=["testing"])
        ]

        mock_work_map = MagicMock()
        mock_work_map.list_work = AsyncMock(
            return_value=WorkListResponse(
                items=[in_progress_item],
                total=1,
                by_status={"in_progress": 1},
                by_priority={"normal": 1},
            )
        )

        with patch(
            "services.conflict_detection_service.get_conflict_detection_service",
            return_value=mock_conflict_service,
        ), patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse_manager,
        ), patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map,
        ):
            await orch._check_resource_conflicts(processable)

        call_args = mock_conflict_service.detect_resource_conflicts.call_args
        demands = call_args.kwargs["resource_demands"]
        assert len(demands) == 2
        task_ids = {d["task_id"] for d in demands}
        assert task_ids == {"pending_1", "active_1"}

    @pytest.mark.asyncio
    async def test_worker_contention_detected(self, orch):
        """Should pass correct demands/resources for contention detection."""
        processable = [
            _make_work_item(
                work_id=f"work_{i}",
                required_capabilities=["testing"],
                priority=WorkPriority.HIGH,
            )
            for i in range(3)
        ]

        mock_contention = MagicMock()
        mock_conflict_service = MagicMock()
        mock_conflict_service.detect_resource_conflicts.return_value = [mock_contention]
        mock_conflict_service.store_resource_conflicts = AsyncMock()

        mock_sse_manager = MagicMock()
        mock_sse_manager.list_connections.return_value = [
            _make_sse_connection(compute_id="c1", capabilities=["testing"])
        ]

        mock_work_map = MagicMock()
        mock_work_map.list_work = AsyncMock(
            return_value=WorkListResponse(
                items=[], total=0, by_status={}, by_priority={}
            )
        )

        with patch(
            "services.conflict_detection_service.get_conflict_detection_service",
            return_value=mock_conflict_service,
        ), patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse_manager,
        ), patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map,
        ):
            await orch._check_resource_conflicts(processable)

        call_args = mock_conflict_service.detect_resource_conflicts.call_args
        assert len(call_args.kwargs["resource_demands"]) == 3
        assert len(call_args.kwargs["available_resources"]) == 1

    @pytest.mark.asyncio
    async def test_no_conflicts_clears_previous(self, orch):
        """Should store empty list when no conflicts detected."""
        processable = [_make_work_item(required_capabilities=["coding"])]

        mock_conflict_service = MagicMock()
        mock_conflict_service.detect_resource_conflicts.return_value = []
        mock_conflict_service.store_resource_conflicts = AsyncMock()

        mock_sse_manager = MagicMock()
        mock_sse_manager.list_connections.return_value = [
            _make_sse_connection(capabilities=["coding"])
        ]

        mock_work_map = MagicMock()
        mock_work_map.list_work = AsyncMock(
            return_value=WorkListResponse(
                items=[], total=0, by_status={}, by_priority={}
            )
        )

        with patch(
            "services.conflict_detection_service.get_conflict_detection_service",
            return_value=mock_conflict_service,
        ), patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse_manager,
        ), patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map,
        ):
            await orch._check_resource_conflicts(processable)

        mock_conflict_service.store_resource_conflicts.assert_awaited_once_with(
            "project_1", []
        )

    @pytest.mark.asyncio
    async def test_multiple_projects_checked_independently(self, orch):
        """Should check resource conflicts per project independently."""
        processable = [
            _make_work_item(
                work_id="w1", project_id="proj_a", required_capabilities=["coding"]
            ),
            _make_work_item(
                work_id="w2", project_id="proj_b", required_capabilities=["testing"]
            ),
        ]

        mock_conflict_service = MagicMock()
        mock_conflict_service.detect_resource_conflicts.return_value = []
        mock_conflict_service.store_resource_conflicts = AsyncMock()

        mock_sse_manager = MagicMock()
        mock_sse_manager.list_connections.return_value = [
            _make_sse_connection(capabilities=["coding", "testing"])
        ]

        mock_work_map = MagicMock()
        mock_work_map.list_work = AsyncMock(
            return_value=WorkListResponse(
                items=[], total=0, by_status={}, by_priority={}
            )
        )

        with patch(
            "services.conflict_detection_service.get_conflict_detection_service",
            return_value=mock_conflict_service,
        ), patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse_manager,
        ), patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map,
        ):
            await orch._check_resource_conflicts(processable)

        assert mock_conflict_service.detect_resource_conflicts.call_count == 2
        project_ids = {
            call.kwargs["project_id"]
            for call in mock_conflict_service.detect_resource_conflicts.call_args_list
        }
        assert project_ids == {"proj_a", "proj_b"}

    @pytest.mark.asyncio
    async def test_updates_stats_timestamp(self, orch):
        """Should update last_resource_conflict_check timestamp."""
        processable = [_make_work_item(required_capabilities=["coding"])]

        mock_conflict_service = MagicMock()
        mock_conflict_service.detect_resource_conflicts.return_value = []
        mock_conflict_service.store_resource_conflicts = AsyncMock()

        mock_sse_manager = MagicMock()
        mock_sse_manager.list_connections.return_value = [
            _make_sse_connection(capabilities=["coding"])
        ]

        mock_work_map = MagicMock()
        mock_work_map.list_work = AsyncMock(
            return_value=WorkListResponse(
                items=[], total=0, by_status={}, by_priority={}
            )
        )

        assert orch._stats["last_resource_conflict_check"] is None

        with patch(
            "services.conflict_detection_service.get_conflict_detection_service",
            return_value=mock_conflict_service,
        ), patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse_manager,
        ), patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map,
        ):
            await orch._check_resource_conflicts(processable)

        assert orch._stats["last_resource_conflict_check"] is not None


# ============================================================================
# Test store_resource_conflicts on ConflictDetectionService
# ============================================================================


class TestStoreResourceConflicts:
    """Test the incremental resource conflict storage method."""

    @pytest.mark.asyncio
    async def test_stores_resource_conflicts(self):
        from services.conflict_detection_service import ConflictDetectionService
        from models.conflict import ConflictReport, ConflictSeverity, PlannerHandling, ResolutionAuthority

        service = ConflictDetectionService(redis_client=None)

        report = ConflictReport(
            conflict_id="rc_1",
            project_id="project_1",
            conflict_type=ConflictType.RESOURCE,
            severity=ConflictSeverity.HIGH,
            severity_score=0.8,
            title="No workers for gpu",
            description="Test",
            tension_elements=[],
            planner_handling=PlannerHandling(approach="blocked", reasoning="no workers"),
            suggested_resolutions=[],
            resolution_authority=ResolutionAuthority.USER_REQUIRED,
        )

        await service.store_resource_conflicts("project_1", [report])
        assert len(service._conflicts["project_1"]) == 1
        assert service._conflicts["project_1"][0].conflict_id == "rc_1"

    @pytest.mark.asyncio
    async def test_preserves_non_resource_conflicts(self):
        from services.conflict_detection_service import ConflictDetectionService
        from models.conflict import ConflictReport, ConflictSeverity, PlannerHandling, ResolutionAuthority

        service = ConflictDetectionService(redis_client=None)

        goal_conflict = ConflictReport(
            conflict_id="gc_1",
            project_id="project_1",
            conflict_type=ConflictType.GOAL_TO_GOAL,
            severity=ConflictSeverity.MEDIUM,
            severity_score=0.5,
            title="Goal conflict",
            description="Test",
            tension_elements=[],
            planner_handling=PlannerHandling(approach="balancing", reasoning="equal"),
            suggested_resolutions=[],
            resolution_authority=ResolutionAuthority.AUTONOMOUS,
        )
        service._conflicts["project_1"] = [goal_conflict]

        resource_conflict = ConflictReport(
            conflict_id="rc_1",
            project_id="project_1",
            conflict_type=ConflictType.RESOURCE,
            severity=ConflictSeverity.HIGH,
            severity_score=0.8,
            title="Worker contention",
            description="Test",
            tension_elements=[],
            planner_handling=PlannerHandling(approach="sequencing", reasoning="limited"),
            suggested_resolutions=[],
            resolution_authority=ResolutionAuthority.USER_REQUIRED,
        )
        await service.store_resource_conflicts("project_1", [resource_conflict])

        assert len(service._conflicts["project_1"]) == 2
        types = {c.conflict_type for c in service._conflicts["project_1"]}
        assert types == {ConflictType.GOAL_TO_GOAL, ConflictType.RESOURCE}

    @pytest.mark.asyncio
    async def test_replaces_old_resource_conflicts(self):
        from services.conflict_detection_service import ConflictDetectionService
        from models.conflict import ConflictReport, ConflictSeverity, PlannerHandling, ResolutionAuthority

        service = ConflictDetectionService(redis_client=None)

        old_rc = ConflictReport(
            conflict_id="old_rc",
            project_id="project_1",
            conflict_type=ConflictType.RESOURCE,
            severity=ConflictSeverity.MEDIUM,
            severity_score=0.5,
            title="Old conflict",
            description="Test",
            tension_elements=[],
            planner_handling=PlannerHandling(approach="old", reasoning="old"),
            suggested_resolutions=[],
            resolution_authority=ResolutionAuthority.AUTONOMOUS,
        )
        service._conflicts["project_1"] = [old_rc]

        new_rc = ConflictReport(
            conflict_id="new_rc",
            project_id="project_1",
            conflict_type=ConflictType.RESOURCE,
            severity=ConflictSeverity.HIGH,
            severity_score=0.8,
            title="New conflict",
            description="Test",
            tension_elements=[],
            planner_handling=PlannerHandling(approach="new", reasoning="new"),
            suggested_resolutions=[],
            resolution_authority=ResolutionAuthority.USER_REQUIRED,
        )
        await service.store_resource_conflicts("project_1", [new_rc])

        assert len(service._conflicts["project_1"]) == 1
        assert service._conflicts["project_1"][0].conflict_id == "new_rc"

    @pytest.mark.asyncio
    async def test_empty_list_clears_resource_conflicts(self):
        from services.conflict_detection_service import ConflictDetectionService
        from models.conflict import ConflictReport, ConflictSeverity, PlannerHandling, ResolutionAuthority

        service = ConflictDetectionService(redis_client=None)

        rc = ConflictReport(
            conflict_id="rc_1",
            project_id="project_1",
            conflict_type=ConflictType.RESOURCE,
            severity=ConflictSeverity.MEDIUM,
            severity_score=0.5,
            title="Resource conflict",
            description="Test",
            tension_elements=[],
            planner_handling=PlannerHandling(approach="a", reasoning="b"),
            suggested_resolutions=[],
            resolution_authority=ResolutionAuthority.AUTONOMOUS,
        )
        gc = ConflictReport(
            conflict_id="gc_1",
            project_id="project_1",
            conflict_type=ConflictType.GOAL_TO_GOAL,
            severity=ConflictSeverity.MEDIUM,
            severity_score=0.5,
            title="Goal conflict",
            description="Test",
            tension_elements=[],
            planner_handling=PlannerHandling(approach="a", reasoning="b"),
            suggested_resolutions=[],
            resolution_authority=ResolutionAuthority.AUTONOMOUS,
        )
        service._conflicts["project_1"] = [rc, gc]

        await service.store_resource_conflicts("project_1", [])

        assert len(service._conflicts["project_1"]) == 1
        assert service._conflicts["project_1"][0].conflict_type == ConflictType.GOAL_TO_GOAL


# ============================================================================
# Test _spawn_for_work single failure handling (fix for double increment)
# ============================================================================


class TestSpawnFailureSingleIncrement:
    """Test that _handle_spawn_failure is called only once per failure."""

    @pytest.fixture
    def orchestrator(self):
        return WorkOrchestrator(
            poll_interval=1, max_concurrent_spawns=3, max_retries=3, retry_delay=5
        )

    @pytest.mark.asyncio
    async def test_spawn_failure_increments_retry_once(self, orchestrator):
        """Test that a spawn failure only increments retry count once."""
        mock_work = MagicMock()
        mock_work.work_id = "work_single"
        mock_work.title = "Test Work"
        mock_work.skill_ids = ["code-writer"]
        mock_work.required_skills = []
        mock_work.work_type = "feature"
        mock_work.priority = WorkPriority.NORMAL
        mock_work.created_at = datetime.now()
        mock_work.project_id = "project-1"
        mock_work.issue_id = None
        mock_work.context = None

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(items=[mock_work]))
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_work_map.get_failed_work = AsyncMock(return_value=[])
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={"work_single": True})
            mock_get_wms.return_value = mock_work_map

            with patch.object(orchestrator, "_spawn_for_work", new_callable=AsyncMock) as mock_spawn:
                mock_spawn.side_effect = Exception("Git clone failed")

                await orchestrator._process_pending_work()

                # Retry count should be exactly 1, not 2
                assert orchestrator._retry_counts.get("work_single") == 1

    @pytest.mark.asyncio
    async def test_spawn_failure_respects_max_retries(self, orchestrator):
        """Test that after max_retries failures, work is skipped."""
        mock_work = MagicMock()
        mock_work.work_id = "work_maxed"
        mock_work.title = "Test Work"
        mock_work.skill_ids = ["code-writer"]
        mock_work.required_skills = []
        mock_work.work_type = "feature"
        mock_work.priority = WorkPriority.NORMAL
        mock_work.created_at = datetime.now()
        mock_work.project_id = "project-1"

        # Simulate 3 prior failures
        orchestrator._retry_counts["work_maxed"] = 3

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(items=[mock_work]))
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_work_map.get_failed_work = AsyncMock(return_value=[])
            mock_work_map.get_dependencies_bulk = AsyncMock()
            mock_get_wms.return_value = mock_work_map

            with patch.object(orchestrator, "_spawn_for_work", new_callable=AsyncMock) as mock_spawn:
                await orchestrator._process_pending_work()

                # Should not attempt to spawn — max retries exceeded
                mock_spawn.assert_not_called()
                # Deps check should not be called (no candidates pass filter)
                mock_work_map.get_dependencies_bulk.assert_not_called()


# ============================================================================
# Test _retry_failed_work
# ============================================================================


class TestRetryFailedWork:
    """Test failed work retry mechanism."""

    @pytest.fixture
    def orchestrator(self):
        return WorkOrchestrator(
            poll_interval=1, max_concurrent_spawns=3, max_retries=3, retry_delay=10
        )

    @pytest.mark.asyncio
    async def test_retry_failed_work_returns_to_pending(self, orchestrator):
        """Test that eligible failed work is returned to PENDING."""
        failed_item = MagicMock()
        failed_item.work_id = "work_failed1"
        failed_item.retry_count = 0
        failed_item.status = WorkStatus.FAILED
        failed_item.issue_id = None
        failed_item.context = None

        updated_item = MagicMock()
        updated_item.work_id = "work_failed1"
        updated_item.retry_count = 1
        updated_item.status = WorkStatus.PENDING

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item])
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=updated_item)
            mock_get_wms.return_value = mock_work_map

            retried = await orchestrator._retry_failed_work()

            assert retried == 1
            assert orchestrator._stats["total_failed_retries"] == 1
            mock_work_map.mark_work_for_retry.assert_called_once_with(
                "work_failed1", 3
            )

    @pytest.mark.asyncio
    async def test_retry_failed_work_no_eligible_items(self, orchestrator):
        """Test retry with no failed items returns 0."""
        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[])
            mock_get_wms.return_value = mock_work_map

            retried = await orchestrator._retry_failed_work()

            assert retried == 0
            assert orchestrator._stats["total_failed_retries"] == 0

    @pytest.mark.asyncio
    async def test_retry_failed_work_respects_backoff(self, orchestrator):
        """Test that retry respects exponential backoff delay."""
        from datetime import timezone as tz

        failed_item = MagicMock()
        failed_item.work_id = "work_backoff"
        failed_item.retry_count = 1
        failed_item.status = WorkStatus.FAILED

        # Set a future retry time using bare work_id key (consistent with _process_pending_work)
        orchestrator._retry_after["work_backoff"] = \
            datetime.now(tz.utc) + timedelta(hours=1)

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item])
            mock_work_map.mark_work_for_retry = AsyncMock()
            mock_get_wms.return_value = mock_work_map

            retried = await orchestrator._retry_failed_work()

            assert retried == 0
            mock_work_map.mark_work_for_retry.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_failed_work_sets_backoff_delay(self, orchestrator):
        """Test that retry sets exponential backoff for next attempt."""
        failed_item = MagicMock()
        failed_item.work_id = "work_delay"
        failed_item.retry_count = 0
        failed_item.status = WorkStatus.FAILED
        failed_item.issue_id = None
        failed_item.context = None

        updated_item = MagicMock()
        updated_item.work_id = "work_delay"
        updated_item.retry_count = 1
        updated_item.status = WorkStatus.PENDING

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item])
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=updated_item)
            mock_get_wms.return_value = mock_work_map

            await orchestrator._retry_failed_work()

            # Backoff key should use bare work_id (consistent with _process_pending_work)
            assert "work_delay" in orchestrator._retry_after

    @pytest.mark.asyncio
    async def test_retry_failed_work_handles_exhausted_retries(self, orchestrator):
        """Test that exhausted retries don't count as successful retry."""
        failed_item = MagicMock()
        failed_item.work_id = "work_exhausted"
        failed_item.retry_count = 2
        failed_item.status = WorkStatus.FAILED

        # mark_work_for_retry returns FAILED when retries exhausted
        still_failed = MagicMock()
        still_failed.work_id = "work_exhausted"
        still_failed.retry_count = 3
        still_failed.status = WorkStatus.FAILED

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item])
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=still_failed)
            mock_get_wms.return_value = mock_work_map

            retried = await orchestrator._retry_failed_work()

            assert retried == 0
            assert orchestrator._stats["total_failed_retries"] == 0

    @pytest.mark.asyncio
    async def test_retry_failed_work_in_poll_cycle(self, orchestrator):
        """Test that _retry_failed_work is called during _process_pending_work."""
        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(items=[]))
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_work_map.get_failed_work = AsyncMock(return_value=[])
            mock_get_wms.return_value = mock_work_map

            with patch.object(orchestrator, "_retry_failed_work", new_callable=AsyncMock) as mock_retry:
                mock_retry.return_value = 0
                await orchestrator._process_pending_work()

                mock_retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_backoff_key_matches_process_pending(self, orchestrator):
        """Regression test: backoff set by _retry_failed_work must be
        respected by _process_pending_work.

        Previously, _retry_failed_work stored backoff under 'failed:{work_id}'
        but _process_pending_work checked bare '{work_id}', so the backoff was
        never enforced and retries fired immediately.

        See: https://github.com/Guarrdon/claudevn/issues/661
        """
        from datetime import timezone as tz

        work_id = "work_backoff_regression"

        # Step 1: Simulate _retry_failed_work setting a backoff
        failed_item = MagicMock()
        failed_item.work_id = work_id
        failed_item.retry_count = 0
        failed_item.status = WorkStatus.FAILED
        failed_item.issue_id = None
        failed_item.context = None

        updated_item = MagicMock()
        updated_item.work_id = work_id
        updated_item.retry_count = 1
        updated_item.status = WorkStatus.PENDING

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item])
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=updated_item)
            mock_get_wms.return_value = mock_work_map

            await orchestrator._retry_failed_work()

        # The backoff should be stored under the bare work_id
        assert work_id in orchestrator._retry_after
        backoff_time = orchestrator._retry_after[work_id]
        assert backoff_time > datetime.now(tz.utc)

        # Step 2: Simulate _process_pending_work seeing the same item as PENDING
        pending_item = MagicMock()
        pending_item.work_id = work_id
        pending_item.priority = WorkPriority.NORMAL
        pending_item.created_at = datetime.now()
        pending_item.skill_ids = ["code-writer"]
        pending_item.required_skills = []
        pending_item.issue_id = None
        pending_item.context = None
        pending_item.work_type = "feature"

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(items=[pending_item]))
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_work_map.get_dependencies_bulk = AsyncMock()
            mock_get_wms.return_value = mock_work_map

            with patch.object(orchestrator, "_spawn_for_work", new_callable=AsyncMock) as mock_spawn, \
                 patch.object(orchestrator, "_retry_failed_work", new_callable=AsyncMock, return_value=0):
                await orchestrator._process_pending_work()

                # Work should NOT be spawned because it's still in backoff
                mock_spawn.assert_not_called()
                # Dependencies check should not even be reached
                mock_work_map.get_dependencies_bulk.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_failed_work_error_handling(self, orchestrator):
        """Test that errors in _retry_failed_work don't crash the loop."""
        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_get_wms.side_effect = RuntimeError("Service unavailable")

            retried = await orchestrator._retry_failed_work()

            # Should handle error gracefully
            assert retried == 0

    @pytest.mark.asyncio
    async def test_retry_multiple_failed_items(self, orchestrator):
        """Test retrying multiple failed items in one cycle."""
        failed1 = MagicMock()
        failed1.work_id = "work_f1"
        failed1.retry_count = 0
        failed1.status = WorkStatus.FAILED
        failed1.issue_id = None
        failed1.context = None

        failed2 = MagicMock()
        failed2.work_id = "work_f2"
        failed2.retry_count = 1
        failed2.status = WorkStatus.FAILED
        failed2.issue_id = None
        failed2.context = None

        updated1 = MagicMock()
        updated1.work_id = "work_f1"
        updated1.retry_count = 1
        updated1.status = WorkStatus.PENDING

        updated2 = MagicMock()
        updated2.work_id = "work_f2"
        updated2.retry_count = 2
        updated2.status = WorkStatus.PENDING

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed1, failed2])
            mock_work_map.mark_work_for_retry = AsyncMock(side_effect=[updated1, updated2])
            mock_get_wms.return_value = mock_work_map

            retried = await orchestrator._retry_failed_work()

            assert retried == 2
            assert orchestrator._stats["total_failed_retries"] == 2


# ============================================================================
# Test stats include failed_retries
# ============================================================================


class TestOrchestratorStatsUpdate:
    """Test that stats include the new total_failed_retries field."""

    def test_stats_include_failed_retries(self):
        """Test initial stats include total_failed_retries."""
        orch = WorkOrchestrator()
        stats = orch.get_stats()
        assert "total_failed_retries" in stats
        assert stats["total_failed_retries"] == 0


# ============================================================================
# Test _decompose_planning_goals (fix for #677)
# ============================================================================


class TestDecomposePlanningGoals:
    """Test automatic decomposition of planning goals."""

    @pytest.fixture
    def orchestrator(self):
        return WorkOrchestrator(poll_interval=1, max_concurrent_spawns=3)

    @pytest.mark.asyncio
    async def test_triggers_decomposition_for_planning_goals(self, orchestrator):
        """Goals in PLANNING status with no planning_started_at get decomposed."""
        from models.work_map import GoalStatus

        mock_goal = MagicMock()
        mock_goal.goal_id = "goal_new"
        mock_goal.project_id = "project-001"
        mock_goal.planning_started_at = None
        mock_goal.status = GoalStatus.PLANNING

        mock_goal_service = MagicMock()
        mock_goal_service.list_goals = AsyncMock(
            return_value=MagicMock(items=[mock_goal])
        )

        with patch("services.goal_service.get_goal_service", return_value=mock_goal_service), \
             patch("api.slim_claude_code._auto_process_background", new_callable=AsyncMock) as mock_auto:
            queued = await orchestrator._decompose_planning_goals()

        assert queued == 1
        assert orchestrator._stats.get("total_decompositions_triggered") == 1

    @pytest.mark.asyncio
    async def test_skips_goals_already_being_decomposed(self, orchestrator):
        """Goals with planning_started_at set are already being processed."""
        from models.work_map import GoalStatus

        mock_goal = MagicMock()
        mock_goal.goal_id = "goal_active"
        mock_goal.project_id = "project-001"
        mock_goal.planning_started_at = datetime.now()  # Already started
        mock_goal.status = GoalStatus.PLANNING

        mock_goal_service = MagicMock()
        mock_goal_service.list_goals = AsyncMock(
            return_value=MagicMock(items=[mock_goal])
        )

        with patch("services.goal_service.get_goal_service", return_value=mock_goal_service), \
             patch("api.slim_claude_code._auto_process_background", new_callable=AsyncMock) as mock_auto:
            queued = await orchestrator._decompose_planning_goals()

        assert queued == 0
        mock_auto.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_goals_without_project_id(self, orchestrator):
        """Goals without a project_id can't be decomposed."""
        from models.work_map import GoalStatus

        mock_goal = MagicMock()
        mock_goal.goal_id = "goal_orphan"
        mock_goal.project_id = None
        mock_goal.planning_started_at = None
        mock_goal.status = GoalStatus.PLANNING

        mock_goal_service = MagicMock()
        mock_goal_service.list_goals = AsyncMock(
            return_value=MagicMock(items=[mock_goal])
        )

        with patch("services.goal_service.get_goal_service", return_value=mock_goal_service), \
             patch("api.slim_claude_code._auto_process_background", new_callable=AsyncMock) as mock_auto:
            queued = await orchestrator._decompose_planning_goals()

        assert queued == 0
        mock_auto.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_planning_goals_returns_zero(self, orchestrator):
        """Returns 0 when no planning goals exist."""
        mock_goal_service = MagicMock()
        mock_goal_service.list_goals = AsyncMock(
            return_value=MagicMock(items=[])
        )

        with patch("services.goal_service.get_goal_service", return_value=mock_goal_service):
            queued = await orchestrator._decompose_planning_goals()

        assert queued == 0

    @pytest.mark.asyncio
    async def test_handles_goal_service_error_gracefully(self, orchestrator):
        """Errors in goal listing don't crash the orchestrator."""
        with patch("services.goal_service.get_goal_service", side_effect=RuntimeError("Not initialized")):
            queued = await orchestrator._decompose_planning_goals()

        assert queued == 0

    @pytest.mark.asyncio
    async def test_called_during_process_pending_work(self, orchestrator):
        """_decompose_planning_goals is called during _process_pending_work."""
        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(items=[]))
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_work_map.get_failed_work = AsyncMock(return_value=[])
            mock_get_wms.return_value = mock_work_map

            with patch.object(orchestrator, "_decompose_planning_goals", new_callable=AsyncMock) as mock_decompose:
                mock_decompose.return_value = 0
                await orchestrator._process_pending_work()

                mock_decompose.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_planning_goals(self, orchestrator):
        """Multiple planning goals all get queued for decomposition."""
        from models.work_map import GoalStatus

        goals = []
        for i in range(3):
            g = MagicMock()
            g.goal_id = f"goal_{i}"
            g.project_id = f"project-{i}"
            g.planning_started_at = None
            g.status = GoalStatus.PLANNING
            goals.append(g)

        mock_goal_service = MagicMock()
        mock_goal_service.list_goals = AsyncMock(
            return_value=MagicMock(items=goals)
        )

        with patch("services.goal_service.get_goal_service", return_value=mock_goal_service), \
             patch("api.slim_claude_code._auto_process_background", new_callable=AsyncMock):
            queued = await orchestrator._decompose_planning_goals()

        assert queued == 3
        assert orchestrator._stats.get("total_decompositions_triggered") == 3


# ============================================================================
# Test failed node tracking across retries (fix for #691)
# ============================================================================


class TestFailedNodeRotation:
    """Test that failed compute nodes are excluded from retry assignments.

    Regression tests for issue #691: Work retry was assigning to the same
    failed compute instance because _failed_nodes was cleared on assignment
    instead of on completion/exhaustion.
    """

    @pytest.fixture
    def orchestrator(self):
        return WorkOrchestrator(
            poll_interval=1, max_concurrent_spawns=3, max_retries=3, retry_delay=5
        )

    @pytest.mark.asyncio
    async def test_failed_nodes_preserved_after_sse_assignment(self, orchestrator):
        """_failed_nodes should NOT be cleared when work is assigned via SSE.

        Previously, _spawn_for_work cleared _failed_nodes on assignment,
        which meant the orchestrator forgot which computes had failed
        when the work was retried.
        """
        work_id = "work_preserve_nodes"

        # Pre-populate failed nodes (simulating a prior failure)
        orchestrator._failed_nodes[work_id] = {"compute-001"}

        mock_work = MagicMock()
        mock_work.work_id = work_id
        mock_work.title = "Test"
        mock_work.skill_ids = ["code-writer"]
        mock_work.required_skills = []
        mock_work.work_type = "feature"
        mock_work.project_id = "project-1"

        with patch.object(orchestrator, "_select_skills_for_work", return_value=["code-writer"]), \
             patch.object(orchestrator, "_try_assign_via_sse", new_callable=AsyncMock, return_value=True):
            await orchestrator._spawn_for_work(mock_work)

        # Failed nodes should still be tracked
        assert work_id in orchestrator._failed_nodes
        assert "compute-001" in orchestrator._failed_nodes[work_id]

    @pytest.mark.asyncio
    async def test_failed_nodes_preserved_after_direct_spawn(self, orchestrator):
        """_failed_nodes should NOT be cleared when work is spawned directly."""
        work_id = "work_preserve_spawn"

        orchestrator._failed_nodes[work_id] = {"compute-002"}

        mock_work = MagicMock()
        mock_work.work_id = work_id
        mock_work.title = "Test"
        mock_work.skill_ids = ["code-writer"]
        mock_work.required_skills = []
        mock_work.work_type = "feature"
        mock_work.project_id = "project-1"

        with patch.object(orchestrator, "_select_skills_for_work", return_value=["code-writer"]), \
             patch.object(orchestrator, "_try_assign_via_sse", new_callable=AsyncMock, return_value=False), \
             patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse, \
             patch.object(orchestrator, "_spawn_new_compute", new_callable=AsyncMock):

            mock_sse.return_value.list_connections.return_value = []  # No SSE — triggers fallback
            await orchestrator._spawn_for_work(mock_work)

        assert work_id in orchestrator._failed_nodes
        assert "compute-002" in orchestrator._failed_nodes[work_id]

    @pytest.mark.asyncio
    async def test_failed_nodes_passed_as_exclude_on_retry(self, orchestrator):
        """When retrying work with multiple computes, _failed_nodes should be passed to _try_assign_via_sse."""
        work_id = "work_exclude_test"
        orchestrator._failed_nodes[work_id] = {"compute-003"}

        mock_work = MagicMock()
        mock_work.work_id = work_id
        mock_work.title = "Test"
        mock_work.skill_ids = ["code-writer"]
        mock_work.required_skills = []
        mock_work.work_type = "feature"
        mock_work.project_id = "project-1"
        mock_work.issue_id = None
        mock_work.context = None

        # Mock multiple compute instances so exclusion logic activates
        mock_sse_manager = MagicMock()
        mock_sse_manager.list_connections.return_value = [
            MagicMock(compute_id="compute-001"),
            MagicMock(compute_id="compute-002")
        ]

        with patch.object(orchestrator, "_select_skills_for_work", return_value=["code-writer"]), \
             patch.object(orchestrator, "_resolve_model_for_skills", new_callable=AsyncMock, return_value=None), \
             patch.object(orchestrator, "_try_assign_via_sse", new_callable=AsyncMock, return_value=True) as mock_sse, \
             patch("services.sse_connection_manager.get_sse_connection_manager", return_value=mock_sse_manager):
            await orchestrator._spawn_for_work(mock_work)

        # Verify exclude_compute_ids was passed with the failed node (only when multiple computes exist)
        mock_sse.assert_called_once_with(
            mock_work, ["code-writer"], {"compute-003"}, None
        )

    @pytest.mark.asyncio
    async def test_failed_nodes_not_excluded_with_single_compute(self, orchestrator):
        """When only 1 compute exists, _failed_nodes should NOT be excluded (pass None instead)."""
        work_id = "work_single_compute"
        orchestrator._failed_nodes[work_id] = {"compute-001"}

        mock_work = MagicMock()
        mock_work.work_id = work_id
        mock_work.title = "Test"
        mock_work.skill_ids = ["code-writer"]
        mock_work.required_skills = []
        mock_work.work_type = "feature"
        mock_work.project_id = "project-1"
        mock_work.issue_id = None
        mock_work.context = None

        # Mock single compute instance - exclusion should be skipped
        mock_sse_manager = MagicMock()
        mock_sse_manager.list_connections.return_value = [
            MagicMock(compute_id="compute-001")
        ]

        with patch.object(orchestrator, "_select_skills_for_work", return_value=["code-writer"]), \
             patch.object(orchestrator, "_resolve_model_for_skills", new_callable=AsyncMock, return_value=None), \
             patch.object(orchestrator, "_try_assign_via_sse", new_callable=AsyncMock, return_value=True) as mock_sse, \
             patch("services.sse_connection_manager.get_sse_connection_manager", return_value=mock_sse_manager):
            await orchestrator._spawn_for_work(mock_work)

        # Verify exclude_compute_ids was None (not excluded) since there's only 1 compute
        mock_sse.assert_called_once_with(
            mock_work, ["code-writer"], None, None
        )

    @pytest.mark.asyncio
    async def test_failed_nodes_accumulate_across_retries(self, orchestrator):
        """Multiple failures should accumulate different compute IDs."""
        from datetime import timezone as tz

        work_id = "work_accumulate"

        # First failure recorded by _retry_failed_work
        failed_item1 = MagicMock()
        failed_item1.work_id = work_id
        failed_item1.retry_count = 0
        failed_item1.status = WorkStatus.FAILED
        failed_item1.assigned_to = "compute-001"
        failed_item1.issue_id = None
        failed_item1.context = None

        updated1 = MagicMock()
        updated1.work_id = work_id
        updated1.retry_count = 1
        updated1.status = WorkStatus.PENDING

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item1])
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=updated1)
            mock_get_wms.return_value = mock_work_map

            await orchestrator._retry_failed_work()

        assert orchestrator._failed_nodes[work_id] == {"compute-001"}

        # Clear the backoff so the second retry isn't skipped
        orchestrator._retry_after.pop(work_id, None)

        # Second failure on a different compute
        failed_item2 = MagicMock()
        failed_item2.work_id = work_id
        failed_item2.retry_count = 1
        failed_item2.status = WorkStatus.FAILED
        failed_item2.assigned_to = "compute-002"
        failed_item2.issue_id = None
        failed_item2.context = None

        updated2 = MagicMock()
        updated2.work_id = work_id
        updated2.retry_count = 2
        updated2.status = WorkStatus.PENDING

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item2])
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=updated2)
            mock_get_wms.return_value = mock_work_map

            await orchestrator._retry_failed_work()

        # Both failed computes should be tracked
        assert orchestrator._failed_nodes[work_id] == {"compute-001", "compute-002"}

    @pytest.mark.asyncio
    async def test_failed_nodes_cleaned_on_exhausted_retries(self, orchestrator):
        """_failed_nodes should be cleaned up when retries are exhausted."""
        from datetime import timezone as tz

        work_id = "work_exhausted_cleanup"

        orchestrator._failed_nodes[work_id] = {"compute-001", "compute-002"}
        # Use past time so backoff doesn't block the retry
        orchestrator._retry_after[work_id] = datetime.now(tz.utc) - timedelta(seconds=1)

        failed_item = MagicMock()
        failed_item.work_id = work_id
        failed_item.retry_count = 2
        failed_item.status = WorkStatus.FAILED
        failed_item.assigned_to = "compute-003"
        failed_item.issue_id = None
        failed_item.context = None

        # Retries exhausted — stays FAILED
        still_failed = MagicMock()
        still_failed.work_id = work_id
        still_failed.retry_count = 3
        still_failed.status = WorkStatus.FAILED

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item])
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=still_failed)
            mock_get_wms.return_value = mock_work_map

            await orchestrator._retry_failed_work()

        # Tracking state should be cleaned up
        assert work_id not in orchestrator._failed_nodes
        assert work_id not in orchestrator._retry_after


class TestOrchestratorMCPAuth:
    """Test that SSE work assignments use real MCP API keys."""

    @pytest.fixture
    def orchestrator(self):
        return WorkOrchestrator(poll_interval=1, max_concurrent_spawns=3)

    @pytest.fixture
    def mock_work(self):
        work = MagicMock()
        work.work_id = "work_auth_test"
        work.title = "Auth Test Work"
        work.description = "Test description"
        work.required_capabilities = ["coding"]
        work.required_skills = []
        work.skill_ids = []
        work.work_type = "feature"
        work.project_id = "project-1"
        work.base_branch = "main"
        work.context = {"repo_url": "git@test:repo.git"}
        return work

    @pytest.mark.asyncio
    async def test_sse_assignment_generates_real_api_key(self, orchestrator, mock_work):
        """SSE work assignment must generate a real troc_* API key, not a fake one."""
        with patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse, \
             patch("services.work_map_service.get_work_map_service") as mock_work_map, \
             patch("services.marketplace_client.get_marketplace_client") as mock_marketplace, \
             patch("mcp.auth.register_compute_key", new_callable=AsyncMock) as mock_register:

            mock_connection = MagicMock()
            mock_connection.compute_id = "compute-auth-001"

            mock_sse_manager = MagicMock()
            mock_sse_manager.find_matching_connection.return_value = mock_connection
            mock_sse_manager.send_work_assigned = AsyncMock(return_value=True)
            mock_sse.return_value = mock_sse_manager

            mock_map_service = MagicMock()
            mock_map_service.assign_work = AsyncMock()
            mock_map_service.set_issue_compute_id = AsyncMock()
            mock_map_service.update_issue_status = AsyncMock()
            mock_work_map.return_value = mock_map_service

            mock_marketplace.return_value.get_skill = AsyncMock(return_value={
                "name": "Code Writer", "instructions": "Write code"
            })

            result = await orchestrator._try_assign_via_sse(mock_work, ["code-writer"])

            assert result is True

            # Verify register_compute_key was called with a real troc_* key
            mock_register.assert_called_once()
            call_args = mock_register.call_args
            assert call_args[0][0] == "compute-auth-001"
            api_key = call_args[0][1]
            assert api_key.startswith("troc_"), f"Expected troc_* key, got: {api_key}"

            # Verify the same key was passed in mcp_config to send_work_assigned
            send_call = mock_sse_manager.send_work_assigned.call_args
            mcp_config = send_call.kwargs.get("mcp_config") or send_call[1].get("mcp_config")
            assert mcp_config["api_key"] == api_key
            assert "task-" not in mcp_config["api_key"]


# ============================================================================
# Characterization Gate Tests (#841)
# ============================================================================


class TestCharacterizationGate:
    """Tests that work items are gated until characterization completes."""

    @pytest.mark.asyncio
    async def test_skips_work_when_characterization_pending(self, orchestrator):
        """Work items are skipped when their project has pending characterizations (#841)."""
        work = MagicMock()
        work.work_id = "work-1"
        work.project_id = "proj-1"
        work.priority = WorkPriority.NORMAL
        work.created_at = datetime.now()
        work.skill_ids = ["code-writer"]
        work.required_skills = []
        work.work_type = "feature"

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(items=[work]))
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={"work-1": True})
            mock_get_wms.return_value = mock_work_map

            mock_char_svc = MagicMock()
            mock_char_svc.has_pending_characterizations = AsyncMock(return_value=True)

            with patch(
                "services.characterization_service.get_characterization_service",
                return_value=mock_char_svc,
            ), patch.object(
                orchestrator, "_spawn_for_work", new_callable=AsyncMock
            ) as mock_spawn:
                await orchestrator._process_pending_work()

                # Work should NOT be spawned because characterization is pending
                mock_spawn.assert_not_called()

    @pytest.mark.asyncio
    async def test_processes_work_when_characterization_complete(self, orchestrator):
        """Work items proceed when characterization is complete (#841)."""
        work = MagicMock()
        work.work_id = "work-1"
        work.project_id = "proj-1"
        work.priority = WorkPriority.NORMAL
        work.created_at = datetime.now()
        work.skill_ids = ["code-writer"]
        work.required_skills = []
        work.work_type = "feature"
        work.tags = []
        work.issue_id = None
        work.context = None

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(items=[work]))
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_work_map.get_failed_work = AsyncMock(return_value=[])
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={"work-1": True})
            mock_get_wms.return_value = mock_work_map

            mock_char_svc = MagicMock()
            mock_char_svc.has_pending_characterizations = AsyncMock(return_value=False)

            with patch(
                "services.characterization_service.get_characterization_service",
                return_value=mock_char_svc,
            ), patch.object(
                orchestrator, "_spawn_for_work", new_callable=AsyncMock
            ) as mock_spawn:
                await orchestrator._process_pending_work()

                # Work SHOULD be spawned because characterization is done
                mock_spawn.assert_called_once()

    @pytest.mark.asyncio
    async def test_mixed_projects_only_gates_pending(self, orchestrator):
        """Only work items from projects with pending characterization are gated."""
        work_gated = MagicMock()
        work_gated.work_id = "work-gated"
        work_gated.project_id = "proj-pending"
        work_gated.priority = WorkPriority.NORMAL
        work_gated.created_at = datetime.now()
        work_gated.skill_ids = []
        work_gated.required_skills = []
        work_gated.work_type = "feature"
        work_gated.issue_id = None
        work_gated.context = None

        work_ready = MagicMock()
        work_ready.work_id = "work-ready"
        work_ready.project_id = "proj-done"
        work_ready.priority = WorkPriority.NORMAL
        work_ready.created_at = datetime.now()
        work_ready.skill_ids = []
        work_ready.required_skills = []
        work_ready.work_type = "feature"
        work_ready.tags = []
        work_ready.issue_id = None
        work_ready.context = None

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.list_work = AsyncMock(
                return_value=MagicMock(items=[work_gated, work_ready])
            )
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_work_map.get_failed_work = AsyncMock(return_value=[])
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={
                "work-gated": True,
                "work-ready": True,
            })
            mock_get_wms.return_value = mock_work_map

            async def mock_has_pending(pid):
                return pid == "proj-pending"

            mock_char_svc = MagicMock()
            mock_char_svc.has_pending_characterizations = AsyncMock(
                side_effect=mock_has_pending
            )

            with patch(
                "services.characterization_service.get_characterization_service",
                return_value=mock_char_svc,
            ), patch.object(
                orchestrator, "_spawn_for_work", new_callable=AsyncMock
            ) as mock_spawn:
                await orchestrator._process_pending_work()

                # Only work-ready should be spawned
                mock_spawn.assert_called_once()
                assert mock_spawn.call_args[0][0].work_id == "work-ready"
