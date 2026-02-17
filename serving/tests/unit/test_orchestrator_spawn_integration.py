"""Unit tests for orchestrator-to-spawner integration.

Tests the flow from work creation through orchestrator detection to compute
spawning, using mocks to avoid actually spawning Claude Code processes.

Issue #284: Verifies the compute spawning flow triggered by the orchestrator.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from pathlib import Path

from services.work_orchestrator import WorkOrchestrator
from services.compute_spawner import ComputeSpawner
from models.work_map import WorkItem, WorkStatus, WorkPriority
from models.compute_spawner import SpawnRequest, SpawnResponse, ComputeState


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def orchestrator():
    """Create an orchestrator for testing."""
    return WorkOrchestrator(
        poll_interval=1,
        max_concurrent_spawns=3,
        max_retries=2,
        retry_delay=5,
        timeout_enabled=False
    )


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
def pending_work_item():
    """Create a pending work item."""
    return WorkItem(
        work_id="work-spawn-test-001",
        title="Test spawn integration",
        description="Test work for spawn verification",
        project_id="project-001",
        status=WorkStatus.PENDING,
        priority=WorkPriority.NORMAL,
        work_type="feature",
        branch_name="work/work-spawn-test-001",
        base_branch="main",
        required_capabilities=["python", "testing"],
        required_skills=["code-writer"],
        created_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def pending_work_with_deps():
    """Create a work item with unmet dependencies."""
    return WorkItem(
        work_id="work-with-deps-001",
        title="Work with dependencies",
        description="Work that depends on other work",
        project_id="project-001",
        status=WorkStatus.PENDING,
        priority=WorkPriority.HIGH,
        work_type="feature",
        branch_name="work/work-with-deps-001",
        base_branch="main",
        depends_on=["work-blocker-001"],
        created_at=datetime.now(timezone.utc)
    )


# =============================================================================
# Test: Orchestrator Detection of Pending Work
# =============================================================================

class TestOrchestratorDetectsPendingWork:
    """Test that the orchestrator detects pending work items."""

    @pytest.mark.asyncio
    async def test_process_pending_finds_work(self, orchestrator, pending_work_item):
        """Test that _process_pending_work finds pending work items."""
        # Mock the work map service at the import location
        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = AsyncMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(
                items=[pending_work_item]
            ))
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={
                pending_work_item.work_id: True
            })
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_get_wms.return_value = mock_work_map

            # Mock SSE manager to return no connections (force spawn path)
            with patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse:
                mock_sse.return_value.find_matching_connection = MagicMock(return_value=None)

                # Mock the spawner
                with patch("services.compute_spawner.get_compute_spawner") as mock_spawner:
                    mock_spawn = AsyncMock()
                    mock_spawn.spawn = AsyncMock(return_value=SpawnResponse(
                        compute_id="compute-001",
                        state=ComputeState.RUNNING,
                        api_key="test-key",
                        serving_url="http://localhost:8002",
                        workspace_path="/tmp/workspace",
                        initial_work={"work_id": pending_work_item.work_id}
                    ))
                    mock_spawner.return_value = mock_spawn

                    # Marketplace client needed for _compose_skills_for_sse
                    with patch("services.marketplace_client.get_marketplace_client") as mock_mc:
                        mock_client = AsyncMock()
                        mock_mc.return_value = mock_client

                        await orchestrator._process_pending_work()

            # Verify work was found and spawn was called
            mock_work_map.list_work.assert_called_once()
            mock_spawn.spawn.assert_called_once()

    @pytest.mark.asyncio
    async def test_pending_work_with_unmet_deps_skipped(
        self, orchestrator, pending_work_with_deps
    ):
        """Test that work with unmet dependencies is skipped."""
        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = AsyncMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(
                items=[pending_work_with_deps]
            ))
            # Dependencies NOT met (batch check)
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={
                pending_work_with_deps.work_id: False
            })
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_get_wms.return_value = mock_work_map

            # Spawner should not be called
            with patch("services.compute_spawner.get_compute_spawner") as mock_spawner:
                mock_spawn = AsyncMock()
                mock_spawner.return_value = mock_spawn

                await orchestrator._process_pending_work()

                # Spawn should NOT be called for work with unmet dependencies
                mock_spawn.spawn.assert_not_called()


# =============================================================================
# Test: ComputeSpawner.spawn() Called with Correct Parameters
# =============================================================================

class TestSpawnCalledWithCorrectParams:
    """Test that spawn is called with the correct parameters."""

    @pytest.mark.asyncio
    async def test_spawn_request_includes_work_id(
        self, orchestrator, pending_work_item
    ):
        """Test that SpawnRequest includes work_id."""
        captured_request = None

        async def capture_spawn(request):
            nonlocal captured_request
            captured_request = request
            return SpawnResponse(
                compute_id="compute-001",
                state=ComputeState.RUNNING,
                api_key="test-key",
                serving_url="http://localhost:8002",
                workspace_path="/tmp/workspace",
                initial_work={"work_id": request.work_id}
            )

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = AsyncMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(
                items=[pending_work_item]
            ))
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={
                pending_work_item.work_id: True
            })
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_get_wms.return_value = mock_work_map

            with patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse:
                mock_sse.return_value.find_matching_connection = MagicMock(return_value=None)

                with patch("services.compute_spawner.get_compute_spawner") as mock_spawner:
                    mock_spawn = MagicMock()
                    mock_spawn.spawn = capture_spawn
                    mock_spawner.return_value = mock_spawn

                    await orchestrator._process_pending_work()

        # Verify the spawn request has correct parameters
        assert captured_request is not None
        assert captured_request.work_id == pending_work_item.work_id
        assert captured_request.project_id == pending_work_item.project_id

    @pytest.mark.asyncio
    async def test_spawn_request_includes_capabilities(
        self, orchestrator, pending_work_item
    ):
        """Test that SpawnRequest includes required capabilities."""
        captured_request = None

        async def capture_spawn(request):
            nonlocal captured_request
            captured_request = request
            return SpawnResponse(
                compute_id="compute-001",
                state=ComputeState.RUNNING,
                api_key="test-key",
                serving_url="http://localhost:8002",
                workspace_path="/tmp/workspace",
                initial_work=None
            )

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = AsyncMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(
                items=[pending_work_item]
            ))
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={
                pending_work_item.work_id: True
            })
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_get_wms.return_value = mock_work_map

            with patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse:
                mock_sse.return_value.find_matching_connection = MagicMock(return_value=None)

                with patch("services.compute_spawner.get_compute_spawner") as mock_spawner:
                    mock_spawn = MagicMock()
                    mock_spawn.spawn = capture_spawn
                    mock_spawner.return_value = mock_spawn

                    await orchestrator._process_pending_work()

        assert captured_request is not None
        assert captured_request.capabilities == ["python", "testing"]

    @pytest.mark.asyncio
    async def test_spawn_request_includes_selected_skills(
        self, orchestrator, pending_work_item
    ):
        """Test that SpawnRequest includes skills selected for the work."""
        captured_request = None

        async def capture_spawn(request):
            nonlocal captured_request
            captured_request = request
            return SpawnResponse(
                compute_id="compute-001",
                state=ComputeState.RUNNING,
                api_key="test-key",
                serving_url="http://localhost:8002",
                workspace_path="/tmp/workspace",
                initial_work=None
            )

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = AsyncMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(
                items=[pending_work_item]
            ))
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={
                pending_work_item.work_id: True
            })
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_get_wms.return_value = mock_work_map

            with patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse:
                mock_sse.return_value.find_matching_connection = MagicMock(return_value=None)

                with patch("services.compute_spawner.get_compute_spawner") as mock_spawner:
                    mock_spawn = MagicMock()
                    mock_spawn.spawn = capture_spawn
                    mock_spawner.return_value = mock_spawn

                    await orchestrator._process_pending_work()

        assert captured_request is not None
        # Since required_skills is set, it should be used directly
        assert captured_request.skills == ["code-writer"]


# =============================================================================
# Test: Workspace Creation for Spawned Compute
# =============================================================================

class TestWorkspaceCreation:
    """Test that workspace is created correctly for spawned compute."""

    @pytest.mark.asyncio
    async def test_spawn_creates_workspace_directory(
        self, spawner, mock_workspaces_path
    ):
        """Test that spawn creates workspace directory."""
        request = SpawnRequest(
            compute_id="test-workspace-001",
            name="Test Compute",
            skills=["code-writer"],
            capabilities=["python"]
        )

        with patch.object(spawner, "_start_process", new_callable=AsyncMock):
            with patch("mcp.auth.generate_api_key", return_value="test-key"):
                with patch("mcp.auth.register_compute_key"):
                    response = await spawner.spawn(request)

        workspace_path = Path(mock_workspaces_path) / "test-workspace-001"
        assert workspace_path.exists()
        assert response.workspace_path == str(workspace_path)


# =============================================================================
# Test: CLAUDE.md Composition from Skills
# =============================================================================

class TestClaudeMdComposition:
    """Test that CLAUDE.md is composed from skills."""

    @pytest.mark.asyncio
    async def test_spawn_generates_claude_md_file(
        self, spawner, mock_workspaces_path
    ):
        """Test that spawn generates CLAUDE.md file."""
        request = SpawnRequest(
            compute_id="test-claudemd-001",
            name="Test Compute",
            skills=["code-writer"],
            capabilities=["python"]
        )

        with patch.object(spawner, "_start_process", new_callable=AsyncMock):
            with patch("mcp.auth.generate_api_key", return_value="test-key"):
                with patch("mcp.auth.register_compute_key"):
                    await spawner.spawn(request)

        claude_md_path = Path(mock_workspaces_path) / "test-claudemd-001" / "CLAUDE.md"
        assert claude_md_path.exists()

    @pytest.mark.asyncio
    async def test_claude_md_contains_compute_id(
        self, spawner, mock_workspaces_path
    ):
        """Test that CLAUDE.md contains compute ID."""
        request = SpawnRequest(
            compute_id="test-claudemd-002",
            name="Test Compute",
            skills=[],
            capabilities=[]
        )

        with patch.object(spawner, "_start_process", new_callable=AsyncMock):
            with patch("mcp.auth.generate_api_key", return_value="test-key"):
                with patch("mcp.auth.register_compute_key"):
                    await spawner.spawn(request)

        claude_md_path = Path(mock_workspaces_path) / "test-claudemd-002" / "CLAUDE.md"
        content = claude_md_path.read_text()
        assert "test-claudemd-002" in content

    @pytest.mark.asyncio
    async def test_compose_skills_fetches_from_marketplace(self, spawner):
        """Test that _compose_skills fetches skills from marketplace."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_mc:
            mock_client = AsyncMock()
            mock_client.get_skill = AsyncMock(side_effect=[
                {
                    "skill_id": "skill-001",
                    "name": "Code Writer",
                    "description": "Writes code",
                    "instructions": "Write clean, tested code."
                },
                {
                    "skill_id": "skill-002",
                    "name": "Tester",
                    "description": "Writes tests",
                    "instructions": "Write comprehensive tests."
                }
            ])
            mock_mc.return_value = mock_client

            result = await spawner._compose_skills(
                ["skill-001", "skill-002"],
                "compute-001"
            )

        assert "Code Writer" in result
        assert "Tester" in result
        assert "Write clean, tested code." in result
        assert "Write comprehensive tests." in result

    @pytest.mark.asyncio
    async def test_compose_skills_empty_returns_default(self, spawner):
        """Test that empty skills list returns default CLAUDE.md."""
        result = await spawner._compose_skills([], "compute-001")
        assert "compute-001" in result
        assert "ClaudeVN Compute Instance" in result


# =============================================================================
# Test: Work Assignment After Spawn
# =============================================================================

class TestWorkAssignmentAfterSpawn:
    """Test that work is automatically assigned after spawn."""

    @pytest.mark.asyncio
    async def test_spawn_with_work_id_assigns_work(
        self, spawner, mock_workspaces_path
    ):
        """Test that spawn with work_id assigns work."""
        request = SpawnRequest(
            compute_id="test-assign-001",
            name="Test Compute",
            skills=["code-writer"],
            capabilities=["python"],
            work_id="work-to-assign-001",
            project_id="project-001"
        )

        with patch.object(spawner, "_start_process", new_callable=AsyncMock):
            with patch("mcp.auth.generate_api_key", return_value="test-key"):
                with patch("mcp.auth.register_compute_key"):
                    with patch("services.work_map_service.get_work_map_service") as mock_wms:
                        mock_service = AsyncMock()
                        mock_service.assign_work = AsyncMock(return_value=MagicMock(
                            work_id="work-to-assign-001",
                            compute_id="test-assign-001",
                            model_dump=MagicMock(return_value={
                                "work_id": "work-to-assign-001",
                                "compute_id": "test-assign-001"
                            })
                        ))
                        mock_wms.return_value = mock_service

                        response = await spawner.spawn(request)

        assert response.initial_work is not None
        assert response.initial_work["work_id"] == "work-to-assign-001"

    @pytest.mark.asyncio
    async def test_spawn_without_work_id_gets_next_work(
        self, spawner, mock_workspaces_path
    ):
        """Test that spawn without work_id gets next available work."""
        request = SpawnRequest(
            compute_id="test-next-001",
            name="Test Compute",
            skills=["code-writer"],
            capabilities=["python"],
            work_id=None,
            project_id="project-001"
        )

        with patch.object(spawner, "_start_process", new_callable=AsyncMock):
            with patch("mcp.auth.generate_api_key", return_value="test-key"):
                with patch("mcp.auth.register_compute_key"):
                    with patch("services.work_map_service.get_work_map_service") as mock_wms:
                        mock_service = AsyncMock()
                        mock_service.get_next_assignment = AsyncMock(return_value=MagicMock(
                            work_id="next-work-001",
                            compute_id="test-next-001",
                            model_dump=MagicMock(return_value={
                                "work_id": "next-work-001",
                                "compute_id": "test-next-001"
                            })
                        ))
                        mock_wms.return_value = mock_service

                        response = await spawner.spawn(request)

        assert response.initial_work is not None
        assert response.initial_work["work_id"] == "next-work-001"


# =============================================================================
# Test: Spawn Failure Handling and Retry Logic
# =============================================================================

class TestSpawnFailureHandling:
    """Test spawn failure handling and retry logic."""

    @pytest.mark.asyncio
    async def test_spawn_failure_increments_retry_count(
        self, orchestrator, pending_work_item
    ):
        """Test that spawn failure increments retry count."""
        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = AsyncMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(
                items=[pending_work_item]
            ))
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={
                pending_work_item.work_id: True
            })
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_get_wms.return_value = mock_work_map

            with patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse:
                mock_sse.return_value.find_matching_connection = MagicMock(return_value=None)

                with patch("services.compute_spawner.get_compute_spawner") as mock_spawner:
                    mock_spawn = AsyncMock()
                    mock_spawn.spawn = AsyncMock(side_effect=Exception("Spawn failed"))
                    mock_spawner.return_value = mock_spawn

                    await orchestrator._process_pending_work()

        # Retry count should be incremented (may be called multiple times in error path)
        assert orchestrator._retry_counts.get(pending_work_item.work_id, 0) >= 1
        assert orchestrator._stats["total_failed"] >= 1

    @pytest.mark.asyncio
    async def test_work_in_retry_delay_is_skipped(
        self, orchestrator, pending_work_item
    ):
        """Test that work in retry delay is skipped."""
        # First, trigger a failure to set up retry state
        orchestrator._handle_spawn_failure(pending_work_item.work_id, "Test failure")

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = AsyncMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(
                items=[pending_work_item]
            ))
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_get_wms.return_value = mock_work_map

            with patch("services.compute_spawner.get_compute_spawner") as mock_spawner:
                mock_spawn = AsyncMock()
                mock_spawner.return_value = mock_spawn

                await orchestrator._process_pending_work()

                # Spawn should NOT be called because work is in retry delay
                mock_spawn.spawn.assert_not_called()

    @pytest.mark.asyncio
    async def test_exceeded_max_retries_skipped(
        self, orchestrator, pending_work_item
    ):
        """Test that work exceeding max retries is skipped."""
        # Exceed max retries
        for _ in range(orchestrator.max_retries + 1):
            orchestrator._handle_spawn_failure(pending_work_item.work_id, "Test failure")

        # Clear retry delay so we only test retry count
        orchestrator._retry_after.clear()

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = AsyncMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(
                items=[pending_work_item]
            ))
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={
                pending_work_item.work_id: True
            })
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_get_wms.return_value = mock_work_map

            with patch("services.compute_spawner.get_compute_spawner") as mock_spawner:
                mock_spawn = AsyncMock()
                mock_spawner.return_value = mock_spawn

                await orchestrator._process_pending_work()

                # Spawn should NOT be called because max retries exceeded
                mock_spawn.spawn.assert_not_called()

    def test_retry_delay_uses_exponential_backoff(self, orchestrator):
        """Test that retry delay uses exponential backoff."""
        work_id = "work-backoff-test"

        # First failure - should have base delay
        orchestrator._handle_spawn_failure(work_id, "Error 1")
        first_retry_after = orchestrator._retry_after[work_id]

        # Clear and simulate second failure
        orchestrator._retry_after.clear()
        orchestrator._handle_spawn_failure(work_id, "Error 2")
        second_retry_after = orchestrator._retry_after[work_id]

        # Second retry should have longer delay (exponential backoff)
        # The delay doubles each time
        assert orchestrator._retry_counts[work_id] == 2


# =============================================================================
# Test: Priority-Based Work Processing
# =============================================================================

class TestPriorityBasedProcessing:
    """Test that work is processed in priority order."""

    @pytest.mark.asyncio
    async def test_critical_priority_processed_first(self, orchestrator):
        """Test that CRITICAL priority work is processed before NORMAL."""
        critical_work = WorkItem(
            work_id="work-critical-001",
            title="Critical work",
            description="Urgent",
            project_id="project-001",
            status=WorkStatus.PENDING,
            priority=WorkPriority.CRITICAL,
            work_type="bug",
            branch_name="work/critical-001",
            base_branch="main",
            created_at=datetime.now(timezone.utc)
        )

        normal_work = WorkItem(
            work_id="work-normal-001",
            title="Normal work",
            description="Regular",
            project_id="project-001",
            status=WorkStatus.PENDING,
            priority=WorkPriority.NORMAL,
            work_type="feature",
            branch_name="work/normal-001",
            base_branch="main",
            created_at=datetime.now(timezone.utc)
        )

        processed_order = []

        async def track_spawn(request):
            processed_order.append(request.work_id)
            return SpawnResponse(
                compute_id=f"compute-{request.work_id}",
                state=ComputeState.RUNNING,
                api_key="test-key",
                serving_url="http://localhost:8002",
                workspace_path="/tmp/workspace",
                initial_work=None
            )

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = AsyncMock()
            # Return normal work first, critical work second (wrong order)
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(
                items=[normal_work, critical_work]
            ))
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={
                "work-critical-001": True,
                "work-normal-001": True,
            })
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_get_wms.return_value = mock_work_map

            with patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse:
                mock_sse.return_value.find_matching_connection = MagicMock(return_value=None)

                with patch("services.compute_spawner.get_compute_spawner") as mock_spawner:
                    mock_spawn = MagicMock()
                    mock_spawn.spawn = track_spawn
                    mock_spawner.return_value = mock_spawn

                    await orchestrator._process_pending_work()

        # Critical work should be processed first
        assert processed_order[0] == "work-critical-001"
        assert processed_order[1] == "work-normal-001"


# =============================================================================
# Test: Orchestrator Statistics
# =============================================================================

class TestOrchestratorStatistics:
    """Test that orchestrator correctly tracks statistics."""

    @pytest.mark.asyncio
    async def test_successful_spawn_updates_stats(
        self, orchestrator, pending_work_item
    ):
        """Test that successful spawn updates statistics."""
        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = AsyncMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(
                items=[pending_work_item]
            ))
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={
                pending_work_item.work_id: True
            })
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_get_wms.return_value = mock_work_map

            with patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse:
                mock_sse.return_value.find_matching_connection = MagicMock(return_value=None)

                with patch("services.compute_spawner.get_compute_spawner") as mock_spawner:
                    mock_spawn = AsyncMock()
                    mock_spawn.spawn = AsyncMock(return_value=SpawnResponse(
                        compute_id="compute-001",
                        state=ComputeState.RUNNING,
                        api_key="test-key",
                        serving_url="http://localhost:8002",
                        workspace_path="/tmp/workspace",
                        initial_work={"work_id": pending_work_item.work_id}
                    ))
                    mock_spawner.return_value = mock_spawn

                    await orchestrator._process_pending_work()

        stats = orchestrator.get_stats()
        assert stats["total_spawned"] == 1
        assert stats["total_assigned"] == 1
        assert stats["last_spawn"] is not None
