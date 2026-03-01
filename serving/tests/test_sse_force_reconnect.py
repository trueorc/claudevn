"""Unit tests for SSE force-reconnect (#85).

Tests the force=true query parameter on GET /api/v1/compute/connect.
"""

import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import HTTPException

from api.compute import connect_sse


class TestForceReconnect:
    """Tests for force-reconnect behavior on /connect."""

    @pytest.mark.asyncio
    async def test_409_without_force_when_already_connected(self):
        """Without force=true, existing connection returns 409."""
        mock_registry = AsyncMock()
        mock_registry.get_instance = AsyncMock(return_value=MagicMock())
        mock_registry.has_sse_connection = MagicMock(return_value=True)

        mock_request = MagicMock()

        with patch.dict(os.environ, {}, clear=True), \
             pytest.raises(HTTPException) as exc_info:
            await connect_sse(
                request=mock_request,
                force=False,
                x_compute_id="compute-001",
                x_capabilities=None,
                x_resources=None,
                x_labels=None,
                x_tools_available=None,
                authorization=None,
                registry=mock_registry,
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_force_closes_existing_connection(self):
        """force=true closes existing connection and proceeds."""
        mock_registry = AsyncMock()
        mock_instance = MagicMock()
        mock_registry.get_instance = AsyncMock(return_value=mock_instance)
        mock_registry.has_sse_connection = MagicMock(return_value=True)
        mock_registry.remove_instance = AsyncMock(return_value=True)
        mock_registry.add_instance = AsyncMock()

        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=True)

        mock_sse = AsyncMock()

        with patch.dict(os.environ, {}, clear=True), \
             patch("api.compute.get_sse_connection_manager", return_value=mock_sse), \
             patch("api.compute.event_generator", return_value=iter([])), \
             patch("services.observability_event_bus.get_event_bus", return_value=None):
            # This will proceed past the 409 check due to force=True
            # It will eventually try to set up SSE streaming, which we can't
            # fully test in unit tests - we just verify the force path was taken
            mock_sse.unregister_connection.assert_not_awaited()

            # Trigger the function - it will fail at StreamingResponse but the
            # force logic runs before that
            try:
                await connect_sse(
                    request=mock_request,
                    force=True,
                    x_compute_id="compute-001",
                    x_capabilities=None,
                    x_resources=None,
                    x_labels=None,
                    x_tools_available=None,
                    authorization=None,
                    registry=mock_registry,
                )
            except Exception:
                pass  # Expected - can't complete SSE setup in unit test

            # Verify the force-close path was taken
            mock_sse.unregister_connection.assert_awaited_once_with("compute-001")
            mock_registry.remove_instance.assert_awaited_once_with("compute-001")
