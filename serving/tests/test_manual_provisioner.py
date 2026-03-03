"""Tests for ManualProvisioner — notification-based fallback provider."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.providers.manual_provisioner import ManualProvisioner
from services.compute_provisioner import ProvisioningRequest, ProvisioningResult


@pytest.fixture
def provisioner():
    return ManualProvisioner()


@pytest.fixture
def sample_request():
    return ProvisioningRequest(
        triggered_by_work_id="work-abc",
        project_id="proj-1",
        required_tools=["runtime:python:3.11"],
        required_labels=["gpu"],
        required_capabilities=["cuda"],
    )


@pytest.fixture
def minimal_request():
    return ProvisioningRequest(
        triggered_by_work_id="work-xyz",
        project_id="proj-2",
    )


class TestManualProvisionerProperties:
    def test_name(self, provisioner):
        assert provisioner.name == "manual"

    def test_description(self, provisioner):
        assert "manually" in provisioner.description.lower()


class TestCanProvision:
    @pytest.mark.asyncio
    async def test_always_returns_true(self, provisioner, sample_request):
        assert await provisioner.can_provision(sample_request) is True

    @pytest.mark.asyncio
    async def test_returns_true_for_minimal_request(self, provisioner, minimal_request):
        assert await provisioner.can_provision(minimal_request) is True


class TestProvision:
    @pytest.mark.asyncio
    async def test_returns_success(self, provisioner, sample_request):
        with patch("services.notification_service.get_notification_service"), \
             patch("services.sse_connection_manager.get_sse_connection_manager"):
            result = await provisioner.provision(sample_request)
        assert isinstance(result, ProvisioningResult)
        assert result.success is True
        assert result.provider == "manual"
        assert result.instance_id is None
        assert result.estimated_ready_seconds == -1

    @pytest.mark.asyncio
    async def test_emits_notification(self, provisioner, sample_request):
        mock_svc = MagicMock()
        with patch("services.notification_service.get_notification_service", return_value=mock_svc), \
             patch("services.sse_connection_manager.get_sse_connection_manager"):
            await provisioner.provision(sample_request)
        mock_svc.emit.assert_called_once()
        call_kwargs = mock_svc.emit.call_args
        assert call_kwargs[1]["title"] == "Compute needed"
        assert "work-abc" in call_kwargs[1]["message"]

    @pytest.mark.asyncio
    async def test_broadcasts_sse_event(self, provisioner, sample_request):
        mock_sse = AsyncMock()
        with patch("services.notification_service.get_notification_service"), \
             patch("services.sse_connection_manager.get_sse_connection_manager", return_value=mock_sse):
            await provisioner.provision(sample_request)
        mock_sse.broadcast_event.assert_called_once()
        event_name, event_data = mock_sse.broadcast_event.call_args[0]
        assert event_name == "compute_needed"
        assert event_data["work_id"] == "work-abc"
        assert event_data["project_id"] == "proj-1"

    @pytest.mark.asyncio
    async def test_message_includes_all_requirements(self, provisioner, sample_request):
        mock_svc = MagicMock()
        with patch("services.notification_service.get_notification_service", return_value=mock_svc), \
             patch("services.sse_connection_manager.get_sse_connection_manager"):
            await provisioner.provision(sample_request)
        message = mock_svc.emit.call_args[1]["message"]
        assert "runtime:python:3.11" in message
        assert "gpu" in message
        assert "cuda" in message

    @pytest.mark.asyncio
    async def test_minimal_request_uses_general_compute(self, provisioner, minimal_request):
        mock_svc = MagicMock()
        with patch("services.notification_service.get_notification_service", return_value=mock_svc), \
             patch("services.sse_connection_manager.get_sse_connection_manager"):
            await provisioner.provision(minimal_request)
        message = mock_svc.emit.call_args[1]["message"]
        assert "general compute" in message

    @pytest.mark.asyncio
    async def test_notification_failure_does_not_break(self, provisioner, sample_request):
        with patch("services.notification_service.get_notification_service", side_effect=RuntimeError("no service")), \
             patch("services.sse_connection_manager.get_sse_connection_manager"):
            result = await provisioner.provision(sample_request)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_sse_failure_does_not_break(self, provisioner, sample_request):
        mock_sse = AsyncMock()
        mock_sse.broadcast_event.side_effect = RuntimeError("sse down")
        with patch("services.notification_service.get_notification_service"), \
             patch("services.sse_connection_manager.get_sse_connection_manager", return_value=mock_sse):
            result = await provisioner.provision(sample_request)
        assert result.success is True


class TestDeprovision:
    @pytest.mark.asyncio
    async def test_returns_false(self, provisioner):
        assert await provisioner.deprovision("any-id") is False


class TestListAvailableImages:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self, provisioner):
        images = await provisioner.list_available_images()
        assert images == []
