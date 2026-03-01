"""Tests for SSE keepalive heartbeat reconciliation with registry (#88)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.sse_connection_manager import SSEConnectionManager


@pytest.fixture
def mock_registry():
    registry = AsyncMock()
    registry.update_heartbeat = AsyncMock()
    return registry


@pytest.fixture
def manager_with_registry(mock_registry):
    return SSEConnectionManager(keepalive_interval=1, registry=mock_registry)


@pytest.fixture
def manager_without_registry():
    return SSEConnectionManager(keepalive_interval=1)


class TestHeartbeatReconciliation:
    """Verify that the keepalive loop refreshes registry heartbeats."""

    @pytest.mark.asyncio
    async def test_keepalive_refreshes_heartbeats(self, manager_with_registry, mock_registry):
        """Heartbeats should be sent for all SSE-connected instances."""
        # Register two fake connections
        manager_with_registry._connections["compute-1"] = MagicMock()
        manager_with_registry._connections["compute-2"] = MagicMock()
        # Mock broadcast_event to avoid queue issues
        manager_with_registry.broadcast_event = AsyncMock()

        # Run one keepalive iteration then cancel
        task = asyncio.create_task(manager_with_registry._keepalive_loop())
        await asyncio.sleep(1.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Both instances should have had heartbeats refreshed
        calls = mock_registry.update_heartbeat.call_args_list
        compute_ids = [c.args[0] for c in calls]
        assert "compute-1" in compute_ids
        assert "compute-2" in compute_ids

    @pytest.mark.asyncio
    async def test_keepalive_skips_heartbeat_without_registry(self, manager_without_registry):
        """Without registry, keepalive should still broadcast but not call heartbeat."""
        manager_without_registry._connections["compute-1"] = MagicMock()
        manager_without_registry.broadcast_event = AsyncMock()

        task = asyncio.create_task(manager_without_registry._keepalive_loop())
        await asyncio.sleep(1.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # broadcast_event should have been called (keepalive still works)
        assert manager_without_registry.broadcast_event.called

    @pytest.mark.asyncio
    async def test_heartbeat_failure_does_not_break_loop(self, manager_with_registry, mock_registry):
        """A failed heartbeat for one instance should not stop others."""
        manager_with_registry._connections["compute-ok"] = MagicMock()
        manager_with_registry._connections["compute-fail"] = MagicMock()
        manager_with_registry.broadcast_event = AsyncMock()

        # Fail on compute-fail, succeed on compute-ok
        async def selective_heartbeat(compute_id, **kwargs):
            if compute_id == "compute-fail":
                raise Exception("Connection lost")

        mock_registry.update_heartbeat = AsyncMock(side_effect=selective_heartbeat)

        task = asyncio.create_task(manager_with_registry._keepalive_loop())
        await asyncio.sleep(1.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Both should have been attempted
        calls = mock_registry.update_heartbeat.call_args_list
        compute_ids = [c.args[0] for c in calls]
        assert "compute-ok" in compute_ids
        assert "compute-fail" in compute_ids

    @pytest.mark.asyncio
    async def test_registry_passed_in_constructor(self, mock_registry):
        """SSEConnectionManager should accept and store registry reference."""
        mgr = SSEConnectionManager(keepalive_interval=10, registry=mock_registry)
        assert mgr._registry is mock_registry

    @pytest.mark.asyncio
    async def test_registry_defaults_to_none(self):
        """Without registry parameter, _registry should be None."""
        mgr = SSEConnectionManager(keepalive_interval=10)
        assert mgr._registry is None
