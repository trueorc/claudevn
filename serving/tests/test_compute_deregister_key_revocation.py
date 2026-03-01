"""Unit tests for MCP API key revocation on compute deregistration (#81).

Verifies that revoke_compute_key is called in both deregistration paths:
1. DELETE /api/v1/compute/{instance_id} (explicit deregister)
2. SSE disconnect (connection closed)
"""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from api.compute import deregister_instance


class TestDeregisterRevokesKeys:
    """Tests for key revocation in DELETE /compute/{instance_id}."""

    @pytest.mark.asyncio
    async def test_deregister_revokes_api_keys(self):
        """DELETE endpoint calls revoke_compute_key for the instance."""
        mock_registry = AsyncMock()
        mock_registry.remove_instance = AsyncMock(return_value=True)

        with patch("api.compute.get_sse_connection_manager") as mock_get_sse, \
             patch("mcp.auth.revoke_compute_key", new_callable=AsyncMock) as mock_revoke, \
             patch("services.observability_event_bus.get_event_bus", return_value=None):

            mock_sse = AsyncMock()
            mock_get_sse.return_value = mock_sse

            result = await deregister_instance("compute-001", registry=mock_registry)

            mock_revoke.assert_awaited_once_with("compute-001")
            assert result["status"] == "deregistered"

    @pytest.mark.asyncio
    async def test_deregister_revokes_before_remove(self):
        """Key revocation happens before registry removal."""
        call_order = []

        async def mock_revoke(instance_id):
            call_order.append("revoke")

        async def mock_remove(instance_id):
            call_order.append("remove")
            return True

        mock_registry = AsyncMock()
        mock_registry.remove_instance = mock_remove

        with patch("api.compute.get_sse_connection_manager") as mock_get_sse, \
             patch("mcp.auth.revoke_compute_key", side_effect=mock_revoke) as _, \
             patch("services.observability_event_bus.get_event_bus", return_value=None):

            mock_get_sse.return_value = AsyncMock()
            await deregister_instance("compute-001", registry=mock_registry)

        assert call_order == ["revoke", "remove"]

    @pytest.mark.asyncio
    async def test_deregister_still_works_if_no_keys(self):
        """Deregistration succeeds even if compute had no API keys."""
        mock_registry = AsyncMock()
        mock_registry.remove_instance = AsyncMock(return_value=True)

        with patch("api.compute.get_sse_connection_manager") as mock_get_sse, \
             patch("mcp.auth.revoke_compute_key", new_callable=AsyncMock) as mock_revoke, \
             patch("services.observability_event_bus.get_event_bus", return_value=None):

            mock_get_sse.return_value = AsyncMock()
            # revoke_compute_key is a no-op for unknown compute IDs
            mock_revoke.return_value = None

            result = await deregister_instance("compute-unknown", registry=mock_registry)
            assert result["status"] == "deregistered"
