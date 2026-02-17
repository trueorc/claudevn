"""Tests for work status updates in compute event endpoint.

Verifies that claude_code_started, claude_code_completed, and claude_code_failed
events properly transition work items and trigger the dependency cascade.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.compute import router, _handle_work_status_update
from services.registry_service import get_compute_registry
from models.compute import (
    ComputeEventType,
    ComputeEventRequest,
    ComputeInstance,
    InstanceCapabilities,
)
from models.work_map import WorkItem, WorkStatus, WorkPriority


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_work_item():
    """Create a mock work item in ASSIGNED status (just assigned by orchestrator)."""
    return WorkItem(
        work_id="work_abc123",
        title="Implement feature",
        description="Test work item",
        work_type="feature",
        priority=WorkPriority.NORMAL,
        status=WorkStatus.ASSIGNED,
        issue_id="issue_def456",
        project_id="proj-1",
        assigned_to="compute-001",
        context={"issue_id": "issue_def456", "goal_id": "goal_xyz"},
    )


@pytest.fixture
def in_progress_work_item():
    """Create a mock work item already in IN_PROGRESS status."""
    return WorkItem(
        work_id="work_abc123",
        title="Implement feature",
        description="Test work item",
        work_type="feature",
        priority=WorkPriority.NORMAL,
        status=WorkStatus.IN_PROGRESS,
        issue_id="issue_def456",
        project_id="proj-1",
        assigned_to="compute-001",
        context={"issue_id": "issue_def456", "goal_id": "goal_xyz"},
    )


@pytest.fixture
def mock_registry():
    """Create a mock compute registry."""
    registry = MagicMock()
    instance = ComputeInstance(
        instance_id="compute-001",
        name="Test Compute",
        endpoint="sse",
        capabilities=InstanceCapabilities(agents=[]),
    )
    registry.get_instance = AsyncMock(return_value=instance)
    registry.update_instance = AsyncMock(return_value=instance)
    return registry


def _make_work_map_service(work_item):
    """Create a mock work map service returning the given work item."""
    service = MagicMock()
    service.get_work = AsyncMock(return_value=work_item)
    service.update_status = AsyncMock(return_value=work_item)
    service.complete_work = AsyncMock(return_value=work_item)
    service.fail_work_and_update_issue = AsyncMock(return_value=work_item)
    service.cascade_dependents = AsyncMock(return_value=[])
    return service


@pytest.fixture
def mock_work_map_service(mock_work_item):
    """Create a mock work map service with ASSIGNED work item."""
    return _make_work_map_service(mock_work_item)


@pytest.fixture
def app(mock_registry):
    """Create a FastAPI test app with dependency overrides."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_compute_registry] = lambda: mock_registry
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


# =============================================================================
# _handle_work_status_update Unit Tests — Started Events
# =============================================================================


class TestHandleWorkStarted:
    """Tests for claude_code_started event handling."""

    @pytest.mark.asyncio
    async def test_started_transitions_assigned_to_in_progress(
        self, mock_work_map_service, mock_work_item
    ):
        """Started event transitions ASSIGNED work to IN_PROGRESS."""
        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_STARTED,
            compute_id="compute-001",
            task_id="work_abc123",
            instance_id="cc-789",
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map_service,
        ):
            await _handle_work_status_update(event)

        mock_work_map_service.update_status.assert_awaited_once_with(
            "work_abc123", WorkStatus.IN_PROGRESS, "compute-001"
        )
        mock_work_map_service.complete_work.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_started_skips_already_in_progress(self, in_progress_work_item):
        """Started event is no-op if work already IN_PROGRESS."""
        service = _make_work_map_service(in_progress_work_item)

        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_STARTED,
            compute_id="compute-001",
            task_id="work_abc123",
            instance_id="cc-789",
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=service,
        ):
            await _handle_work_status_update(event)

        service.update_status.assert_not_awaited()


# =============================================================================
# _handle_work_status_update Unit Tests — Completed/Failed Events
# =============================================================================


class TestHandleWorkCompletion:
    """Tests for claude_code_completed and claude_code_failed event handling."""

    @pytest.mark.asyncio
    async def test_completed_exit_0_triggers_complete_work(
        self, in_progress_work_item
    ):
        """Completed event with exit_code=0 calls complete_work."""
        service = _make_work_map_service(in_progress_work_item)

        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_COMPLETED,
            compute_id="compute-001",
            task_id="work_abc123",
            exit_code=0,
            duration_seconds=120,
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=service,
        ):
            await _handle_work_status_update(event)

        service.complete_work.assert_awaited_once_with(
            work_id="work_abc123",
            result={
                "summary": "Completed by compute-001",
                "exit_code": 0,
                "duration_seconds": 120,
                "branch_name": None,
            },
            compute_id="compute-001",
            trigger_cascade=False,
        )
        service.fail_work_and_update_issue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_completed_from_assigned_transitions_through_in_progress(
        self, mock_work_map_service, mock_work_item
    ):
        """Completed event on ASSIGNED work first transitions to IN_PROGRESS."""
        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_COMPLETED,
            compute_id="compute-001",
            task_id="work_abc123",
            exit_code=0,
            duration_seconds=120,
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map_service,
        ):
            await _handle_work_status_update(event)

        # Should first transition ASSIGNED -> IN_PROGRESS
        mock_work_map_service.update_status.assert_awaited_once_with(
            "work_abc123", WorkStatus.IN_PROGRESS, "compute-001"
        )
        # Then complete
        mock_work_map_service.complete_work.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_completed_nonzero_exit_triggers_failure(
        self, in_progress_work_item
    ):
        """Completed event with exit_code != 0 calls fail_work_and_update_issue."""
        service = _make_work_map_service(in_progress_work_item)

        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_COMPLETED,
            compute_id="compute-001",
            task_id="work_abc123",
            exit_code=1,
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=service,
        ):
            await _handle_work_status_update(event)

        service.fail_work_and_update_issue.assert_awaited_once_with(
            work_id="work_abc123",
            error="Exit code 1",
            compute_id="compute-001",
        )
        service.complete_work.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_event_triggers_failure(self, in_progress_work_item):
        """Failed event calls fail_work_and_update_issue with error message."""
        service = _make_work_map_service(in_progress_work_item)

        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_FAILED,
            compute_id="compute-001",
            task_id="work_abc123",
            exit_code=137,
            error="Out of memory",
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=service,
        ):
            await _handle_work_status_update(event)

        service.fail_work_and_update_issue.assert_awaited_once_with(
            work_id="work_abc123",
            error="Out of memory",
            compute_id="compute-001",
        )
        service.complete_work.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_completed_no_exit_code_triggers_failure(
        self, in_progress_work_item
    ):
        """Completed event with no exit_code triggers failure path."""
        service = _make_work_map_service(in_progress_work_item)

        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_COMPLETED,
            compute_id="compute-001",
            task_id="work_abc123",
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=service,
        ):
            await _handle_work_status_update(event)

        service.fail_work_and_update_issue.assert_awaited_once()
        service.complete_work.assert_not_awaited()


# =============================================================================
# Already-Terminal State — Double Completion Race (#829)
# =============================================================================


class TestAlreadyTerminalSkipsTransition:
    """Tests that already-completed/failed work skips redundant status transitions (#829)."""

    @pytest.fixture
    def completed_work_item(self):
        """Work item already in COMPLETED state (set by MCP report_progress)."""
        return WorkItem(
            work_id="work_abc123",
            title="Implement feature",
            description="Test work item",
            work_type="feature",
            priority=WorkPriority.NORMAL,
            status=WorkStatus.COMPLETED,
            issue_id="issue_def456",
            project_id="proj-1",
            assigned_to="compute-001",
            branch_name="feat/task-001/compute-001",
            context={"issue_id": "issue_def456"},
        )

    @pytest.fixture
    def failed_work_item(self):
        """Work item already in FAILED state."""
        return WorkItem(
            work_id="work_abc123",
            title="Implement feature",
            description="Test work item",
            work_type="feature",
            priority=WorkPriority.NORMAL,
            status=WorkStatus.FAILED,
            issue_id="issue_def456",
            project_id="proj-1",
            assigned_to="compute-001",
            context={"issue_id": "issue_def456"},
        )

    @pytest.mark.asyncio
    async def test_completed_event_skips_already_completed_work(
        self, completed_work_item
    ):
        """claude_code_completed skips complete_work when work already COMPLETED."""
        service = _make_work_map_service(completed_work_item)

        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_COMPLETED,
            compute_id="compute-001",
            task_id="work_abc123",
            exit_code=0,
            duration_seconds=120,
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=service,
        ):
            await _handle_work_status_update(event)

        # Should NOT call complete_work or update_status again
        service.complete_work.assert_not_awaited()
        service.update_status.assert_not_awaited()
        service.fail_work_and_update_issue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_completed_event_on_failed_work_skips_transition(
        self, failed_work_item
    ):
        """claude_code_completed skips transition when work already FAILED."""
        service = _make_work_map_service(failed_work_item)

        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_COMPLETED,
            compute_id="compute-001",
            task_id="work_abc123",
            exit_code=0,
            duration_seconds=120,
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=service,
        ):
            await _handle_work_status_update(event)

        service.complete_work.assert_not_awaited()
        service.update_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_event_skips_already_completed_work(
        self, completed_work_item
    ):
        """claude_code_failed skips fail_work when work already COMPLETED."""
        service = _make_work_map_service(completed_work_item)

        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_FAILED,
            compute_id="compute-001",
            task_id="work_abc123",
            exit_code=1,
            error="Timeout",
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=service,
        ):
            await _handle_work_status_update(event)

        service.fail_work_and_update_issue.assert_not_awaited()
        service.complete_work.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_already_completed_still_triggers_pr_creation(
        self, completed_work_item
    ):
        """PR creation still runs even when work was already COMPLETED by MCP (#829)."""
        service = _make_work_map_service(completed_work_item)

        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_COMPLETED,
            compute_id="compute-001",
            task_id="work_abc123",
            exit_code=0,
            duration_seconds=120,
            branch_name="feat/task-001/compute-001",
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=service,
        ), patch(
            "api.compute._auto_create_and_merge_pr",
            new_callable=AsyncMock,
        ) as mock_pr:
            await _handle_work_status_update(event)

        # PR creation should still be triggered
        mock_pr.assert_awaited_once_with(
            completed_work_item, "feat/task-001/compute-001", "compute-001"
        )


# =============================================================================
# Branch Verification — Fail work if branch not pushed (#831)
# =============================================================================


class TestBranchVerification:
    """Tests that work fails if branch doesn't exist on remote (#831)."""

    @pytest.mark.asyncio
    async def test_missing_branch_fails_work(self, in_progress_work_item):
        """Work with branch_name that doesn't exist on remote is FAILED."""
        in_progress_work_item.project_id = "proj-1"
        in_progress_work_item.branch_name = "feat/task-001/compute-001"
        service = _make_work_map_service(in_progress_work_item)

        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_COMPLETED,
            compute_id="compute-001",
            task_id="work_abc123",
            exit_code=0,
            duration_seconds=120,
            branch_name="feat/task-001/compute-001",
        )

        mock_repo_mgr = MagicMock()
        mock_repo_mgr.get_branches.return_value = ["main"]  # Branch missing

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=service,
        ), patch(
            "git.repo_manager.RepoManager",
            return_value=mock_repo_mgr,
        ):
            await _handle_work_status_update(event)

        service.fail_work_and_update_issue.assert_awaited_once()
        service.complete_work.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_existing_branch_completes_work(self, in_progress_work_item):
        """Work with branch that exists on remote is COMPLETED normally."""
        in_progress_work_item.project_id = "proj-1"
        service = _make_work_map_service(in_progress_work_item)

        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_COMPLETED,
            compute_id="compute-001",
            task_id="work_abc123",
            exit_code=0,
            duration_seconds=120,
            branch_name="feat/task-001/compute-001",
        )

        mock_repo_mgr = MagicMock()
        mock_repo_mgr.get_branches.return_value = [
            "main", "feat/task-001/compute-001"
        ]

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=service,
        ), patch(
            "git.repo_manager.RepoManager",
            return_value=mock_repo_mgr,
        ):
            await _handle_work_status_update(event)

        service.complete_work.assert_awaited_once()
        service.fail_work_and_update_issue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_branch_name_skips_verification(self, in_progress_work_item):
        """Work without branch_name skips verification and completes."""
        in_progress_work_item.project_id = "proj-1"
        in_progress_work_item.branch_name = None
        service = _make_work_map_service(in_progress_work_item)

        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_COMPLETED,
            compute_id="compute-001",
            task_id="work_abc123",
            exit_code=0,
            duration_seconds=120,
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=service,
        ):
            await _handle_work_status_update(event)

        service.complete_work.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_branch_verification_error_still_completes(self, in_progress_work_item):
        """If branch verification throws, work still completes (fail-open)."""
        in_progress_work_item.project_id = "proj-1"
        service = _make_work_map_service(in_progress_work_item)

        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_COMPLETED,
            compute_id="compute-001",
            task_id="work_abc123",
            exit_code=0,
            duration_seconds=120,
            branch_name="feat/task-001/compute-001",
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=service,
        ), patch(
            "git.repo_manager.RepoManager",
            side_effect=Exception("RepoManager init failed"),
        ):
            await _handle_work_status_update(event)

        # Should still complete (fail-open on verification error)
        service.complete_work.assert_awaited_once()


# =============================================================================
# Edge Cases
# =============================================================================


class TestHandleWorkEdgeCases:
    """Tests for edge cases in work status update handling."""

    @pytest.mark.asyncio
    async def test_missing_work_item_handled_gracefully(self):
        """No crash when work item not found for task_id."""
        service = MagicMock()
        service.get_work = AsyncMock(return_value=None)
        service.complete_work = AsyncMock()
        service.fail_work_and_update_issue = AsyncMock()

        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_COMPLETED,
            compute_id="compute-001",
            task_id="nonexistent-task",
            exit_code=0,
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=service,
        ):
            await _handle_work_status_update(event)

        service.get_work.assert_awaited_once_with("nonexistent-task")
        service.complete_work.assert_not_awaited()
        service.fail_work_and_update_issue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_work_map_service_unavailable_handled_gracefully(self):
        """No crash when work map service is not initialized."""
        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_COMPLETED,
            compute_id="compute-001",
            task_id="work_abc123",
            exit_code=0,
        )

        with patch(
            "services.work_map_service.get_work_map_service",
            side_effect=RuntimeError("Work map service not initialized"),
        ):
            await _handle_work_status_update(event)


# =============================================================================
# Endpoint Integration Tests
# =============================================================================


class TestComputeEventEndpointCompletion:
    """Tests for compute event endpoint work completion integration."""

    def test_completed_event_returns_acknowledged(
        self, client, mock_work_map_service
    ):
        """POST /events with completed event returns 200 acknowledged."""
        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map_service,
        ):
            response = client.post(
                "/compute/events",
                json={
                    "event": "claude_code_completed",
                    "compute_id": "compute-001",
                    "task_id": "work_abc123",
                    "exit_code": 0,
                    "duration_seconds": 135,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "acknowledged"
        assert data["event"] == "claude_code_completed"

    def test_failed_event_returns_acknowledged(
        self, client, mock_work_map_service
    ):
        """POST /events with failed event returns 200 acknowledged."""
        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map_service,
        ):
            response = client.post(
                "/compute/events",
                json={
                    "event": "claude_code_failed",
                    "compute_id": "compute-001",
                    "task_id": "work_abc123",
                    "exit_code": 137,
                    "error": "OOM killed",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "acknowledged"
        assert data["event"] == "claude_code_failed"

    def test_started_event_transitions_work(self, client, mock_work_map_service):
        """POST /events with started event transitions work to IN_PROGRESS."""
        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map_service,
        ):
            response = client.post(
                "/compute/events",
                json={
                    "event": "claude_code_started",
                    "compute_id": "compute-001",
                    "task_id": "work_abc123",
                    "instance_id": "cc-789",
                },
            )

        assert response.status_code == 200
        mock_work_map_service.update_status.assert_awaited_once()


# =============================================================================
# SSE Connection Reset Tests (#842)
# =============================================================================


class TestSSEResetOnNonWorkTaskCompletion:
    """Tests that SSE connection resets to idle for non-work tasks (e.g. char-*, decomp-*).

    Regression tests for #842: Compute not recognized as available after
    characterization task completes. The root cause was the SSE reset living
    inside _handle_work_status_update(), which returns early when the task_id
    has no corresponding work item.
    """

    def test_sse_resets_to_idle_on_characterization_completion(
        self, client
    ):
        """SSE connection resets to idle when characterization task completes (#842)."""
        mock_connection = MagicMock()
        mock_connection.status = "busy"
        mock_connection.current_task_id = "char-abc123"

        mock_sse_manager = MagicMock()
        mock_sse_manager.get_connection.return_value = mock_connection

        mock_work_map = MagicMock()
        mock_work_map.get_work = AsyncMock(return_value=None)  # char-* has no work item

        with patch(
            "api.compute.get_sse_connection_manager",
            return_value=mock_sse_manager,
        ), patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map,
        ):
            response = client.post(
                "/compute/events",
                json={
                    "event": "claude_code_completed",
                    "compute_id": "compute-001",
                    "task_id": "char-abc123",
                    "exit_code": 0,
                    "duration_seconds": 225,
                },
            )

        assert response.status_code == 200
        assert mock_connection.status == "idle"
        assert mock_connection.current_task_id is None

    def test_sse_resets_to_idle_on_decomposition_completion(
        self, client
    ):
        """SSE connection resets to idle when decomposition task completes."""
        mock_connection = MagicMock()
        mock_connection.status = "busy"
        mock_connection.current_task_id = "decomp-xyz789"

        mock_sse_manager = MagicMock()
        mock_sse_manager.get_connection.return_value = mock_connection

        mock_work_map = MagicMock()
        mock_work_map.get_work = AsyncMock(return_value=None)

        with patch(
            "api.compute.get_sse_connection_manager",
            return_value=mock_sse_manager,
        ), patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map,
        ):
            response = client.post(
                "/compute/events",
                json={
                    "event": "claude_code_completed",
                    "compute_id": "compute-001",
                    "task_id": "decomp-xyz789",
                    "exit_code": 0,
                },
            )

        assert response.status_code == 200
        assert mock_connection.status == "idle"
        assert mock_connection.current_task_id is None

    def test_sse_resets_to_idle_on_failed_non_work_task(
        self, client
    ):
        """SSE connection resets to idle even when non-work task fails."""
        mock_connection = MagicMock()
        mock_connection.status = "busy"
        mock_connection.current_task_id = "char-fail456"

        mock_sse_manager = MagicMock()
        mock_sse_manager.get_connection.return_value = mock_connection

        mock_work_map = MagicMock()
        mock_work_map.get_work = AsyncMock(return_value=None)

        with patch(
            "api.compute.get_sse_connection_manager",
            return_value=mock_sse_manager,
        ), patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_work_map,
        ):
            response = client.post(
                "/compute/events",
                json={
                    "event": "claude_code_failed",
                    "compute_id": "compute-001",
                    "task_id": "char-fail456",
                    "error": "Out of memory",
                },
            )

        assert response.status_code == 200
        assert mock_connection.status == "idle"
        assert mock_connection.current_task_id is None
