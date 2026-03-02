"""Tests for compute connection approval/deny API."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.compute import (
    ComputeInstance,
    InstanceStatus,
    ComputeAuthStatus,
    InstanceCapabilities,
)


def _make_pending_instance(instance_id="pending-001"):
    """Create a pending test instance."""
    return ComputeInstance(
        instance_id=instance_id,
        name=f"Compute {instance_id}",
        endpoint="sse",
        status=InstanceStatus.PENDING,
        pending_since=datetime.now(timezone.utc),
        capabilities=InstanceCapabilities(
            agents=["code-writer"],
            labels=["test"],
            tools_available=["deploy"],
        ),
        last_heartbeat=datetime.now(timezone.utc),
        metadata={"connected_at": datetime.now(timezone.utc).isoformat()},
    )


class TestListPendingConnections:
    """Test GET /compute/pending endpoint."""

    @pytest.mark.asyncio
    async def test_returns_pending_instances(self):
        from api.compute_approval import list_pending_connections

        mock_registry = MagicMock()
        mock_registry.get_pending_instances = AsyncMock(
            return_value=[_make_pending_instance("p1"), _make_pending_instance("p2")]
        )

        result = await list_pending_connections(registry=mock_registry)
        assert result["count"] == 2
        assert len(result["pending"]) == 2
        assert result["pending"][0].instance_id == "p1"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_pending(self):
        from api.compute_approval import list_pending_connections

        mock_registry = MagicMock()
        mock_registry.get_pending_instances = AsyncMock(return_value=[])

        result = await list_pending_connections(registry=mock_registry)
        assert result["count"] == 0
        assert result["pending"] == []


class TestApproveConnection:
    """Test POST /compute/{id}/approve endpoint."""

    @pytest.mark.asyncio
    async def test_approve_pending_instance(self):
        from api.compute_approval import approve_connection
        from fastapi import HTTPException

        instance = _make_pending_instance()
        approved_instance = _make_pending_instance()
        approved_instance.status = InstanceStatus.ONLINE

        mock_registry = MagicMock()
        mock_registry.get_instance = AsyncMock(return_value=instance)
        mock_registry.approve_instance = AsyncMock(return_value=approved_instance)

        with patch("api.compute_approval.get_sse_connection_manager") as mock_sse:
            mock_sse.return_value = MagicMock()
            mock_sse.return_value.send_event = AsyncMock()

            result = await approve_connection("pending-001", body=None, registry=mock_registry)

        assert result["approved"] is True
        assert result["status"] == "online"

    @pytest.mark.asyncio
    async def test_approve_nonexistent_raises_404(self):
        from api.compute_approval import approve_connection
        from fastapi import HTTPException

        mock_registry = MagicMock()
        mock_registry.get_instance = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await approve_connection("nonexistent", body=None, registry=mock_registry)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_non_pending_raises_409(self):
        from api.compute_approval import approve_connection
        from fastapi import HTTPException

        instance = _make_pending_instance()
        instance.status = InstanceStatus.ONLINE

        mock_registry = MagicMock()
        mock_registry.get_instance = AsyncMock(return_value=instance)

        with pytest.raises(HTTPException) as exc_info:
            await approve_connection("pending-001", body=None, registry=mock_registry)
        assert exc_info.value.status_code == 409


class TestRejectConnection:
    """Test POST /compute/{id}/reject endpoint."""

    @pytest.mark.asyncio
    async def test_reject_pending_instance(self):
        from api.compute_approval import reject_connection

        instance = _make_pending_instance()

        mock_registry = MagicMock()
        mock_registry.get_instance = AsyncMock(return_value=instance)
        mock_registry.reject_instance = AsyncMock(return_value=True)

        with patch("api.compute_approval.get_sse_connection_manager") as mock_sse:
            mock_sse.return_value = MagicMock()
            mock_sse.return_value.send_event = AsyncMock()
            mock_sse.return_value.unregister_connection = AsyncMock()

            result = await reject_connection("pending-001", registry=mock_registry)

        assert result["rejected"] is True

    @pytest.mark.asyncio
    async def test_reject_nonexistent_raises_404(self):
        from api.compute_approval import reject_connection
        from fastapi import HTTPException

        mock_registry = MagicMock()
        mock_registry.get_instance = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await reject_connection("nonexistent", registry=mock_registry)
        assert exc_info.value.status_code == 404
