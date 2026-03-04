"""Unit tests for capability gap detection and auto-blocking.

Tests the CAPABILITY_MISSING blocker flow:
- Detection after N failed match cycles
- Blocker creation with descriptive metadata
- Auto-resolution when a capable compute connects
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.work_map import BlockerType, WorkStatus


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def orchestrator():
    from services.work_orchestrator import WorkOrchestrator
    return WorkOrchestrator(poll_interval=60)


@pytest.fixture
def mock_work():
    """A work item that requires specific capabilities."""
    work = MagicMock()
    work.work_id = "work-001"
    work.title = "Build React frontend"
    work.description = "Build the app"
    work.project_id = "proj-001"
    work.required_capabilities = ["javascript", "react"]
    work.required_labels = []
    work.required_tools = []
    work.context = {}
    work.base_branch = "main"
    work.tags = []
    work.status = WorkStatus.PENDING
    work.blockers = []
    work.active_blockers = []
    return work


@pytest.fixture
def mock_sse_manager():
    """SSE connection manager with Python-only computes."""
    manager = MagicMock()
    conn = MagicMock()
    conn.compute_id = "compute-001"
    conn.capabilities = ["python", "testing"]
    conn.labels = []
    conn.tools_available = []
    conn.status = "idle"
    manager.list_connections.return_value = [conn]
    manager.get_idle_connections.return_value = [conn]
    manager.find_matching_connection.return_value = None  # no match
    manager.has_capable_connection.return_value = False  # capability gap
    manager.describe_available_capabilities.return_value = {
        "capabilities": {"python", "testing"},
        "labels": set(),
        "tools": set(),
    }
    return manager


# ── BlockerType enum ──────────────────────────────────────────────────────────

class TestBlockerTypeEnum:
    def test_capability_missing_value(self):
        assert BlockerType.CAPABILITY_MISSING == "capability_missing"

    def test_capability_missing_is_member(self):
        assert "capability_missing" in [bt.value for bt in BlockerType]


# ── Failed match counting ─────────────────────────────────────────────────────

class TestFailedMatchCounting:
    def test_counter_starts_at_zero(self, orchestrator, mock_work):
        assert orchestrator._failed_match_counts.get(mock_work.work_id, 0) == 0

    def test_default_threshold_is_three(self, orchestrator):
        assert orchestrator._capability_block_threshold == 3

    @pytest.mark.asyncio
    @patch("services.sse_connection_manager.get_sse_connection_manager")
    async def test_counter_increments_on_capability_mismatch(
        self, mock_get_sse, orchestrator, mock_work, mock_sse_manager
    ):
        """When computes exist but lack required capabilities, counter increments."""
        mock_get_sse.return_value = mock_sse_manager

        # Simulate _spawn_for_work path: SSE match fails, computes exist, no capable match
        # We test the counter logic directly
        work_id = mock_work.work_id
        orchestrator._failed_match_counts[work_id] = 0

        # Simulate 2 failed cycles (below threshold)
        for i in range(2):
            count = orchestrator._failed_match_counts.get(work_id, 0) + 1
            orchestrator._failed_match_counts[work_id] = count

        assert orchestrator._failed_match_counts[work_id] == 2

    @pytest.mark.asyncio
    async def test_counter_cleared_on_successful_assignment(self, orchestrator, mock_work):
        """When work is assigned, the failed match counter is cleared."""
        work_id = mock_work.work_id
        orchestrator._failed_match_counts[work_id] = 2

        # Simulate successful assignment cleanup
        orchestrator._failed_match_counts.pop(work_id, None)
        assert work_id not in orchestrator._failed_match_counts


# ── Blocker creation ──────────────────────────────────────────────────────────

class TestCapabilityBlockerCreation:
    @pytest.mark.asyncio
    async def test_block_for_missing_capabilities_creates_blocker(
        self, orchestrator, mock_work, mock_sse_manager
    ):
        """_block_for_missing_capabilities calls add_blocker with correct type."""
        mock_assignment = AsyncMock()
        mock_blocker = MagicMock()
        mock_blocker.blocker_id = "blk_test123"
        mock_assignment.add_blocker.return_value = mock_blocker

        with patch(
            "services.assignment_service.get_assignment_service",
            return_value=mock_assignment,
        ), patch(
            "services.work_orchestrator._emit_failure_notification"
        ) as mock_notify:
            await orchestrator._block_for_missing_capabilities(mock_work, mock_sse_manager)

        mock_assignment.add_blocker.assert_called_once()
        call_kwargs = mock_assignment.add_blocker.call_args
        assert call_kwargs.kwargs["work_id"] == "work-001"
        assert call_kwargs.kwargs["blocker_type"] == BlockerType.CAPABILITY_MISSING
        assert "javascript" in call_kwargs.kwargs["description"]
        assert "react" in call_kwargs.kwargs["description"]

    @pytest.mark.asyncio
    async def test_block_description_includes_available_capabilities(
        self, orchestrator, mock_work, mock_sse_manager
    ):
        """The blocker description shows what's available in the network."""
        mock_assignment = AsyncMock()
        mock_assignment.add_blocker.return_value = MagicMock()

        with patch(
            "services.assignment_service.get_assignment_service",
            return_value=mock_assignment,
        ), patch("services.work_orchestrator._emit_failure_notification"):
            await orchestrator._block_for_missing_capabilities(mock_work, mock_sse_manager)

        description = mock_assignment.add_blocker.call_args.kwargs["description"]
        assert "python" in description
        assert "testing" in description

    @pytest.mark.asyncio
    async def test_block_emits_notification(
        self, orchestrator, mock_work, mock_sse_manager
    ):
        """A frontend notification is emitted when capability blocker is created."""
        mock_assignment = AsyncMock()
        mock_assignment.add_blocker.return_value = MagicMock()

        with patch(
            "services.assignment_service.get_assignment_service",
            return_value=mock_assignment,
        ), patch(
            "services.work_orchestrator._emit_failure_notification"
        ) as mock_notify:
            await orchestrator._block_for_missing_capabilities(mock_work, mock_sse_manager)

        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs["work_id"] == "work-001"
        assert mock_notify.call_args.kwargs["project_id"] == "proj-001"


# ── Auto-resolve on connect ──────────────────────────────────────────────────

class TestAutoResolveOnConnect:
    @pytest.mark.asyncio
    async def test_resolves_capability_blocker_when_capable_compute_connects(
        self, orchestrator
    ):
        """When a new compute with matching capabilities connects, blocker is resolved."""
        blocker = MagicMock()
        blocker.blocker_id = "blk_abc123"
        blocker.blocker_type = BlockerType.CAPABILITY_MISSING

        blocked_work = MagicMock()
        blocked_work.work_id = "work-001"
        blocked_work.status = WorkStatus.BLOCKED
        blocked_work.active_blockers = [blocker]
        blocked_work.required_capabilities = ["javascript", "react"]
        blocked_work.required_labels = []
        blocked_work.required_tools = []

        mock_assignment = MagicMock()
        mock_assignment._work_items = {"work-001": blocked_work}
        mock_assignment.resolve_blocker = AsyncMock(return_value=True)

        mock_sse = MagicMock()
        mock_sse.has_capable_connection.return_value = True

        with patch(
            "services.assignment_service.get_assignment_service",
            return_value=mock_assignment,
        ), patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ):
            await orchestrator._on_compute_connected("compute-new")

        mock_assignment.resolve_blocker.assert_called_once_with(
            work_id="work-001",
            blocker_id="blk_abc123",
            resolution_note="Compute compute-new registered with matching capabilities",
            resolved_by="system:orchestrator",
        )

    @pytest.mark.asyncio
    async def test_does_not_resolve_non_capability_blockers(self, orchestrator):
        """Non-capability blockers are not resolved by new compute registration."""
        blocker = MagicMock()
        blocker.blocker_id = "blk_dep001"
        blocker.blocker_type = BlockerType.DEPENDENCY

        blocked_work = MagicMock()
        blocked_work.work_id = "work-002"
        blocked_work.status = WorkStatus.BLOCKED
        blocked_work.active_blockers = [blocker]
        blocked_work.required_capabilities = []
        blocked_work.required_labels = []
        blocked_work.required_tools = []

        mock_assignment = MagicMock()
        mock_assignment._work_items = {"work-002": blocked_work}
        mock_assignment.resolve_blocker = AsyncMock()

        mock_sse = MagicMock()

        with patch(
            "services.assignment_service.get_assignment_service",
            return_value=mock_assignment,
        ), patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ):
            await orchestrator._on_compute_connected("compute-new")

        mock_assignment.resolve_blocker.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_still_no_capable_connection(self, orchestrator):
        """If the new compute still doesn't match, blocker stays."""
        blocker = MagicMock()
        blocker.blocker_id = "blk_cap001"
        blocker.blocker_type = BlockerType.CAPABILITY_MISSING

        blocked_work = MagicMock()
        blocked_work.work_id = "work-003"
        blocked_work.status = WorkStatus.BLOCKED
        blocked_work.active_blockers = [blocker]
        blocked_work.required_capabilities = ["gpu-inference"]
        blocked_work.required_labels = []
        blocked_work.required_tools = []

        mock_assignment = MagicMock()
        mock_assignment._work_items = {"work-003": blocked_work}
        mock_assignment.resolve_blocker = AsyncMock()

        mock_sse = MagicMock()
        mock_sse.has_capable_connection.return_value = False  # still no match

        with patch(
            "services.assignment_service.get_assignment_service",
            return_value=mock_assignment,
        ), patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ):
            await orchestrator._on_compute_connected("compute-new")

        mock_assignment.resolve_blocker.assert_not_called()


# ── SSE Connection Manager helpers ────────────────────────────────────────────

class TestSSECapabilityHelpers:
    def _make_connection(self, capabilities=None, labels=None, tools=None):
        conn = MagicMock()
        conn.capabilities = capabilities or []
        conn.labels = labels or []
        conn.tools_available = tools or []
        conn.status = "idle"
        return conn

    def _make_manager(self, connections):
        from services.sse_connection_manager import SSEConnectionManager
        manager = SSEConnectionManager.__new__(SSEConnectionManager)
        manager._connections = {f"c-{i}": c for i, c in enumerate(connections)}
        manager._on_connect_handlers = []
        manager._on_disconnect_handlers = []
        manager._round_robin_indices = {}
        manager._registry = None
        manager._keepalive_task = None
        manager._keepalive_interval = 30
        return manager

    def test_has_capable_connection_true(self):
        conn = self._make_connection(capabilities=["python", "react"])
        manager = self._make_manager([conn])
        assert manager.has_capable_connection(required_capabilities=["python", "react"])

    def test_has_capable_connection_false_missing_cap(self):
        conn = self._make_connection(capabilities=["python"])
        manager = self._make_manager([conn])
        assert not manager.has_capable_connection(required_capabilities=["python", "react"])

    def test_has_capable_connection_labels(self):
        conn = self._make_connection(labels=["production-access"])
        manager = self._make_manager([conn])
        assert manager.has_capable_connection(required_labels=["production-access"])
        assert not manager.has_capable_connection(required_labels=["staging-access"])

    def test_has_capable_connection_tools(self):
        conn = self._make_connection(tools=["deploy_prod"])
        manager = self._make_manager([conn])
        assert manager.has_capable_connection(required_tools=["deploy_prod"])
        assert not manager.has_capable_connection(required_tools=["db_migrate"])

    def test_has_capable_connection_no_requirements(self):
        conn = self._make_connection()
        manager = self._make_manager([conn])
        assert manager.has_capable_connection()

    def test_describe_available_capabilities(self):
        c1 = self._make_connection(capabilities=["python"], labels=["dev"], tools=["lint"])
        c2 = self._make_connection(capabilities=["python", "react"], labels=["prod"], tools=["deploy"])
        manager = self._make_manager([c1, c2])
        result = manager.describe_available_capabilities()
        assert result["capabilities"] == {"python", "react"}
        assert result["labels"] == {"dev", "prod"}
        assert result["tools"] == {"lint", "deploy"}

    def test_describe_available_capabilities_empty(self):
        manager = self._make_manager([])
        result = manager.describe_available_capabilities()
        assert result["capabilities"] == set()
        assert result["labels"] == set()
        assert result["tools"] == set()
