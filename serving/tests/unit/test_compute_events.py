"""Unit tests for compute registration/deregistration event emission.

Tests that compute endpoints emit observability events at the right times
with correct data (issue #791).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from datetime import datetime, timezone

from models.compute import (
    ComputeInstance,
    InstanceCapabilities,
    RegistrationRequest,
)
from models.observability import (
    EventType,
    ComputeRegisteredEvent,
    ComputeDeregisteredEvent,
)
from services.registry_service import ComputeRegistry


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_registry():
    """Mock compute registry."""
    registry = MagicMock(spec=ComputeRegistry)
    registry.add_instance = AsyncMock(return_value=MagicMock())
    registry.remove_instance = AsyncMock(return_value=True)
    registry.get_instance = AsyncMock(return_value=None)
    registry.has_sse_connection = MagicMock(return_value=False)
    return registry


@pytest.fixture
def mock_event_bus():
    """Mock observability event bus."""
    bus = AsyncMock()
    bus.emit_event = AsyncMock()
    return bus


@pytest.fixture
def sample_registration():
    """Sample registration request."""
    return RegistrationRequest(
        instance_id="compute-001",
        name="Compute 001",
        endpoint="http://compute:8000",
        capabilities=InstanceCapabilities(
            agents=["agent-a", "agent-b"],
            tools=[],
            features=[],
            labels=["production-access"],
            tools_available=["deploy_prod"],
        ),
        metadata={"zone": "us-east-1"},
    )


# =============================================================================
# POST /register Event Emission Tests
# =============================================================================


class TestRegisterInstanceEvents:
    """Test event emission during POST /compute/register."""

    @pytest.mark.asyncio
    async def test_register_emits_compute_registered_event(
        self, mock_registry, mock_event_bus, sample_registration
    ):
        """POST /register should emit COMPUTE_REGISTERED event."""
        from api.compute import register_instance

        # Mock the instance returned by registry
        mock_instance = ComputeInstance(
            instance_id=sample_registration.instance_id,
            name=sample_registration.name,
            endpoint=sample_registration.endpoint,
            capabilities=sample_registration.capabilities,
        )
        mock_registry.add_instance.return_value = mock_instance

        # Patch dependencies - get_event_bus is imported locally in the function
        with patch("services.observability_event_bus.get_event_bus", return_value=mock_event_bus):
            response = await register_instance(sample_registration, mock_registry)

        # Verify event emitted
        assert mock_event_bus.emit_event.called
        emitted_event = mock_event_bus.emit_event.call_args[0][0]

        assert isinstance(emitted_event, ComputeRegisteredEvent)
        assert emitted_event.compute_id == "compute-001"
        assert emitted_event.name == "Compute 001"
        assert emitted_event.capabilities == ["agent-a", "agent-b"]
        assert emitted_event.labels == ["production-access"]
        assert emitted_event.tools_available == ["deploy_prod"]
        assert emitted_event.metadata["connection_type"] == "http"
        assert emitted_event.metadata["endpoint"] == "http://compute:8000"

    @pytest.mark.asyncio
    async def test_register_event_has_correct_structure(
        self, mock_registry, mock_event_bus, sample_registration
    ):
        """Emitted event should have correct structure."""
        from api.compute import register_instance

        mock_instance = ComputeInstance(
            instance_id=sample_registration.instance_id,
            name=sample_registration.name,
            endpoint=sample_registration.endpoint,
            capabilities=sample_registration.capabilities,
        )
        mock_registry.add_instance.return_value = mock_instance

        with patch("services.observability_event_bus.get_event_bus", return_value=mock_event_bus):
            await register_instance(sample_registration, mock_registry)

        emitted_event = mock_event_bus.emit_event.call_args[0][0]

        # Check required fields
        assert emitted_event.event_type == EventType.COMPUTE_REGISTERED
        assert emitted_event.event_id.startswith("cr_")
        assert emitted_event.session_id == "global"
        assert isinstance(emitted_event.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_register_no_event_if_bus_unavailable(
        self, mock_registry, sample_registration
    ):
        """Should not fail if event bus is unavailable."""
        from api.compute import register_instance

        mock_instance = ComputeInstance(
            instance_id=sample_registration.instance_id,
            name=sample_registration.name,
            endpoint=sample_registration.endpoint,
            capabilities=sample_registration.capabilities,
        )
        mock_registry.add_instance.return_value = mock_instance

        with patch("services.observability_event_bus.get_event_bus", return_value=None):
            # Should not raise
            response = await register_instance(sample_registration, mock_registry)

        assert response.status == "registered"


# =============================================================================
# SSE /connect Event Emission Tests
# =============================================================================


class TestSSEConnectEvents:
    """Test event emission during SSE connection."""

    @pytest.mark.asyncio
    async def test_sse_connect_emits_event_new_instance(
        self, mock_registry, mock_event_bus
    ):
        """SSE connect for new instance should emit COMPUTE_REGISTERED event."""
        from api.compute import connect_sse
        from fastapi import Request

        # No existing instance
        mock_registry.get_instance.return_value = None

        mock_request = MagicMock(spec=Request)
        mock_request.is_disconnected = AsyncMock(return_value=False)

        with patch("services.observability_event_bus.get_event_bus", return_value=mock_event_bus):
            with patch("api.compute.get_sse_connection_manager") as mock_sse_mgr:
                mock_sse_mgr.return_value.register_connection = AsyncMock()

                # Trigger connection (will fail quickly but that's OK for event test)
                try:
                    response = await connect_sse(
                        request=mock_request,
                        x_compute_id="compute-001",
                        x_capabilities="agent-a,agent-b",
                        x_resources="cpu=4,memory=16",
                        x_labels="production-access",
                        x_tools_available="deploy_prod",
                        registry=mock_registry,
                    )
                except:
                    pass  # Ignore streaming errors for this test

        # Verify instance was registered
        assert mock_registry.add_instance.called

        # Verify event emitted
        assert mock_event_bus.emit_event.called
        emitted_event = mock_event_bus.emit_event.call_args[0][0]

        assert isinstance(emitted_event, ComputeRegisteredEvent)
        assert emitted_event.compute_id == "compute-001"
        assert "agent-a" in emitted_event.capabilities
        assert "production-access" in emitted_event.labels
        assert "deploy_prod" in emitted_event.tools_available

    @pytest.mark.asyncio
    async def test_sse_connect_no_event_if_already_registered(
        self, mock_registry, mock_event_bus
    ):
        """SSE connect for existing instance should not re-emit event."""
        from api.compute import connect_sse
        from fastapi import Request

        # Existing instance
        existing = ComputeInstance(
            instance_id="compute-001",
            name="Compute 001",
            endpoint="sse",
            capabilities=InstanceCapabilities(agents=["agent-a"]),
        )
        mock_registry.get_instance.return_value = existing

        mock_request = MagicMock(spec=Request)
        mock_request.is_disconnected = AsyncMock(return_value=False)

        with patch("services.observability_event_bus.get_event_bus", return_value=mock_event_bus):
            with patch("api.compute.get_sse_connection_manager") as mock_sse_mgr:
                mock_sse_mgr.return_value.register_connection = AsyncMock()

                try:
                    response = await connect_sse(
                        request=mock_request,
                        x_compute_id="compute-001",
                        x_capabilities="agent-a",
                        registry=mock_registry,
                    )
                except:
                    pass  # Ignore streaming errors

        # Verify instance was NOT added (already exists)
        assert not mock_registry.add_instance.called

        # Verify event was NOT emitted (backward compatibility)
        assert not mock_event_bus.emit_event.called


# =============================================================================
# DELETE /{instance_id} Deregistration Event Tests
# =============================================================================


class TestDeregisterInstanceEvents:
    """Test event emission during DELETE /compute/{instance_id}."""

    @pytest.mark.asyncio
    async def test_deregister_emits_compute_deregistered_event(
        self, mock_registry, mock_event_bus
    ):
        """DELETE /{instance_id} should emit COMPUTE_DEREGISTERED event."""
        from api.compute import deregister_instance

        mock_registry.remove_instance.return_value = True

        with patch("services.observability_event_bus.get_event_bus", return_value=mock_event_bus):
            with patch("api.compute.get_sse_connection_manager") as mock_sse_mgr:
                    mock_sse_mgr.return_value.unregister_connection = AsyncMock()

                    response = await deregister_instance("compute-001", mock_registry)

        # Verify event emitted
        assert mock_event_bus.emit_event.called
        emitted_event = mock_event_bus.emit_event.call_args[0][0]

        assert isinstance(emitted_event, ComputeDeregisteredEvent)
        assert emitted_event.compute_id == "compute-001"
        assert emitted_event.reason == "manual_deregister"

    @pytest.mark.asyncio
    async def test_deregister_event_has_correct_structure(
        self, mock_registry, mock_event_bus
    ):
        """Emitted event should have correct structure."""
        from api.compute import deregister_instance

        mock_registry.remove_instance.return_value = True

        with patch("services.observability_event_bus.get_event_bus", return_value=mock_event_bus):
            with patch("api.compute.get_sse_connection_manager") as mock_sse_mgr:
                    mock_sse_mgr.return_value.unregister_connection = AsyncMock()

                    await deregister_instance("compute-001", mock_registry)

        emitted_event = mock_event_bus.emit_event.call_args[0][0]

        # Check required fields
        assert emitted_event.event_type == EventType.COMPUTE_DEREGISTERED
        assert emitted_event.event_id.startswith("cd_")
        assert emitted_event.session_id == "global"
        assert isinstance(emitted_event.timestamp, datetime)


# =============================================================================
# SSE Disconnect Event Tests
# =============================================================================


class TestSSEDisconnectEvents:
    """Test event emission during SSE disconnection."""

    @pytest.mark.asyncio
    async def test_sse_disconnect_emits_deregistered_event(
        self, mock_registry, mock_event_bus
    ):
        """SSE disconnect should emit COMPUTE_DEREGISTERED event."""
        from api.compute import _sse_event_generator
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        # Simulate immediate disconnect
        mock_request.is_disconnected = AsyncMock(return_value=True)

        with patch("services.observability_event_bus.get_event_bus", return_value=mock_event_bus):
            # Run generator until completion
            generator = _sse_event_generator(
                compute_id="compute-001",
                registry=mock_registry,
                request=mock_request,
                sse_manager=None,
            )

            try:
                async for _ in generator:
                    pass  # Consume all events
            except StopAsyncIteration:
                pass

        # Verify registry removal
        assert mock_registry.remove_instance.called
        assert mock_registry.remove_instance.call_args[0][0] == "compute-001"

        # Verify event emitted
        assert mock_event_bus.emit_event.called
        emitted_event = mock_event_bus.emit_event.call_args[0][0]

        assert isinstance(emitted_event, ComputeDeregisteredEvent)
        assert emitted_event.compute_id == "compute-001"
        assert emitted_event.reason == "sse_disconnect"

    @pytest.mark.asyncio
    async def test_sse_disconnect_event_structure(
        self, mock_registry, mock_event_bus
    ):
        """SSE disconnect event should have correct structure."""
        from api.compute import _sse_event_generator
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.is_disconnected = AsyncMock(return_value=True)

        with patch("services.observability_event_bus.get_event_bus", return_value=mock_event_bus):
            generator = _sse_event_generator(
                compute_id="compute-001",
                registry=mock_registry,
                request=mock_request,
                sse_manager=None,
            )

            try:
                async for _ in generator:
                    pass
            except StopAsyncIteration:
                pass

        emitted_event = mock_event_bus.emit_event.call_args[0][0]

        # Check required fields
        assert emitted_event.event_type == EventType.COMPUTE_DEREGISTERED
        assert emitted_event.event_id.startswith("cd_")
        assert emitted_event.session_id == "global"
        assert isinstance(emitted_event.timestamp, datetime)
        assert emitted_event.reason == "sse_disconnect"


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestEventEmissionErrorHandling:
    """Test graceful handling when event bus is unavailable."""

    @pytest.mark.asyncio
    async def test_register_with_no_event_bus(
        self, mock_registry, sample_registration
    ):
        """Registration should succeed when event bus is unavailable."""
        from api.compute import register_instance

        mock_instance = ComputeInstance(
            instance_id=sample_registration.instance_id,
            name=sample_registration.name,
            endpoint=sample_registration.endpoint,
            capabilities=sample_registration.capabilities,
        )
        mock_registry.add_instance.return_value = mock_instance

        # Event bus unavailable (None) - should not fail
        with patch("services.observability_event_bus.get_event_bus", return_value=None):
            # Should not raise - registration completes without event
            response = await register_instance(sample_registration, mock_registry)

        assert response.status == "registered"

    @pytest.mark.asyncio
    async def test_deregister_with_no_event_bus(
        self, mock_registry
    ):
        """Deregistration should succeed when event bus is unavailable."""
        from api.compute import deregister_instance

        mock_registry.remove_instance.return_value = True

        # Event bus unavailable (None)
        with patch("services.observability_event_bus.get_event_bus", return_value=None):
            with patch("api.compute.get_sse_connection_manager") as mock_sse_mgr:
                mock_sse_mgr.return_value.unregister_connection = AsyncMock()

                # Should not raise
                response = await deregister_instance("compute-001", mock_registry)

        assert response["status"] == "deregistered"
