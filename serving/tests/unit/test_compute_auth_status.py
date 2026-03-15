"""Tests for compute instance auth status fields and behavior."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from models.compute import (
    ComputeInstance,
    ComputeAuthStatus,
    InstanceCapabilities,
    InstanceStatus,
)
from services.registry_service import ComputeRegistry


@pytest.fixture
def registry():
    """Create a registry for testing."""
    return ComputeRegistry()


def _make_instance(instance_id="test-001", auth_status=ComputeAuthStatus.UNAUTHORIZED, **kwargs):
    """Helper to create a compute instance."""
    kwargs.setdefault("status", InstanceStatus.ONLINE)
    return ComputeInstance(
        instance_id=instance_id,
        name=f"Test {instance_id}",
        endpoint="http://localhost:8003",
        auth_status=auth_status,
        **kwargs,
    )


# =========================================================================
# Model Tests
# =========================================================================


class TestComputeAuthStatusModel:
    """Tests for auth status fields on ComputeInstance model."""

    def test_default_auth_status_is_unauthorized(self):
        instance = _make_instance()
        assert instance.auth_status == ComputeAuthStatus.UNAUTHORIZED
        assert instance.auth_expires_at is None
        assert instance.auth_authorized_at is None

    def test_set_authorized(self):
        now = datetime.now(timezone.utc)
        instance = _make_instance(
            auth_status=ComputeAuthStatus.AUTHORIZED,
            auth_authorized_at=now,
            auth_expires_at=now + timedelta(days=365),
        )
        assert instance.auth_status == ComputeAuthStatus.AUTHORIZED
        assert instance.auth_authorized_at == now
        assert instance.auth_expires_at is not None

    def test_set_expired(self):
        instance = _make_instance(auth_status=ComputeAuthStatus.EXPIRED)
        assert instance.auth_status == ComputeAuthStatus.EXPIRED

    def test_is_authorized(self):
        instance = _make_instance(auth_status=ComputeAuthStatus.AUTHORIZED)
        assert instance.is_authorized() is True

        instance2 = _make_instance(auth_status=ComputeAuthStatus.UNAUTHORIZED)
        assert instance2.is_authorized() is False

        instance3 = _make_instance(auth_status=ComputeAuthStatus.EXPIRED)
        assert instance3.is_authorized() is False

    def test_is_work_eligible_requires_healthy_and_authorized(self):
        # Authorized + online = eligible
        instance = _make_instance(auth_status=ComputeAuthStatus.AUTHORIZED)
        assert instance.is_work_eligible() is True

        # Unauthorized + online = not eligible
        instance2 = _make_instance(auth_status=ComputeAuthStatus.UNAUTHORIZED)
        assert instance2.is_work_eligible() is False

        # Authorized + offline = not eligible
        instance3 = _make_instance(
            auth_status=ComputeAuthStatus.AUTHORIZED,
            status=InstanceStatus.OFFLINE,
        )
        assert instance3.is_work_eligible() is False

    def test_serialization_includes_auth_fields(self):
        now = datetime.now(timezone.utc)
        instance = _make_instance(
            auth_status=ComputeAuthStatus.AUTHORIZED,
            auth_authorized_at=now,
            auth_expires_at=now + timedelta(days=365),
        )
        data = instance.model_dump()
        assert data["auth_status"] == "authorized"
        assert data["auth_authorized_at"] is not None
        assert data["auth_expires_at"] is not None

    def test_deserialization_with_auth_fields(self):
        now = datetime.now(timezone.utc)
        data = {
            "instance_id": "test-001",
            "name": "Test",
            "endpoint": "http://localhost:8003",
            "auth_status": "authorized",
            "auth_authorized_at": now.isoformat(),
            "auth_expires_at": (now + timedelta(days=365)).isoformat(),
        }
        instance = ComputeInstance(**data)
        assert instance.auth_status == ComputeAuthStatus.AUTHORIZED


# =========================================================================
# Registry Service Tests
# =========================================================================


class TestRegistryAuthStatus:
    """Tests for auth status in registry service."""

    @pytest.mark.asyncio
    async def test_new_instance_starts_unauthorized(self, registry):
        instance = _make_instance()
        added = await registry.add_instance(instance)
        assert added.auth_status == ComputeAuthStatus.UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_update_auth_status_to_authorized(self, registry):
        instance = _make_instance()
        await registry.add_instance(instance)

        expires = datetime.now(timezone.utc) + timedelta(days=365)
        updated = await registry.update_auth_status(
            "test-001", ComputeAuthStatus.AUTHORIZED, auth_expires_at=expires
        )

        assert updated is not None
        assert updated.auth_status == ComputeAuthStatus.AUTHORIZED
        assert updated.auth_authorized_at is not None
        assert updated.auth_expires_at == expires

    @pytest.mark.asyncio
    async def test_update_auth_status_to_unauthorized_clears_fields(self, registry):
        instance = _make_instance(
            auth_status=ComputeAuthStatus.AUTHORIZED,
            auth_authorized_at=datetime.now(timezone.utc),
            auth_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        await registry.add_instance(instance)

        updated = await registry.update_auth_status("test-001", ComputeAuthStatus.UNAUTHORIZED)

        assert updated.auth_status == ComputeAuthStatus.UNAUTHORIZED
        assert updated.auth_authorized_at is None
        assert updated.auth_expires_at is None

    @pytest.mark.asyncio
    async def test_update_auth_status_nonexistent(self, registry):
        result = await registry.update_auth_status("nonexistent", ComputeAuthStatus.AUTHORIZED)
        assert result is None

    @pytest.mark.asyncio
    async def test_find_matching_compute_requires_authorized(self, registry):
        """Unauthorized instances should not be returned by find_matching_compute."""
        # Add unauthorized instance
        unauth = _make_instance(instance_id="unauth-001")
        await registry.add_instance(unauth)

        # Add authorized instance
        auth = _make_instance(
            instance_id="auth-001",
            auth_status=ComputeAuthStatus.AUTHORIZED,
        )
        await registry.add_instance(auth)

        result = await registry.find_matching_compute()
        assert result is not None
        assert result.instance_id == "auth-001"

    @pytest.mark.asyncio
    async def test_find_matching_compute_no_authorized(self, registry):
        """No match when all instances are unauthorized."""
        instance = _make_instance()
        await registry.add_instance(instance)

        result = await registry.find_matching_compute()
        assert result is None

    @pytest.mark.asyncio
    async def test_find_matching_compute_expired_excluded(self, registry):
        """Expired auth instances should not match."""
        instance = _make_instance(auth_status=ComputeAuthStatus.EXPIRED)
        await registry.add_instance(instance)

        result = await registry.find_matching_compute()
        assert result is None

    @pytest.mark.asyncio
    async def test_check_auth_expiry(self, registry):
        """Instances with expired auth_expires_at should be marked expired."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        instance = _make_instance(
            auth_status=ComputeAuthStatus.AUTHORIZED,
            auth_expires_at=past,
            auth_authorized_at=past - timedelta(days=365),
        )
        await registry.add_instance(instance)

        expired_ids = await registry.check_auth_expiry()
        assert "test-001" in expired_ids

        retrieved = await registry.get_instance("test-001")
        assert retrieved.auth_status == ComputeAuthStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_check_auth_expiry_not_expired(self, registry):
        """Instances with future expiry should remain authorized."""
        future = datetime.now(timezone.utc) + timedelta(days=365)
        instance = _make_instance(
            auth_status=ComputeAuthStatus.AUTHORIZED,
            auth_expires_at=future,
            auth_authorized_at=datetime.now(timezone.utc),
        )
        await registry.add_instance(instance)

        expired_ids = await registry.check_auth_expiry()
        assert len(expired_ids) == 0

        retrieved = await registry.get_instance("test-001")
        assert retrieved.auth_status == ComputeAuthStatus.AUTHORIZED

    @pytest.mark.asyncio
    async def test_register_syncs_auth_status_from_existing_token(self, registry):
        """Registration should sync auth_status when an active token exists."""
        from api.compute import register_instance
        from models.compute import RegistrationRequest, InstanceCapabilities

        request = RegistrationRequest(
            instance_id="node-001",
            name="Node 001",
            endpoint="http://compute:8000",
            capabilities=InstanceCapabilities(agents=["agent-a"]),
        )

        mock_instance = _make_instance(instance_id="node-001")
        registry.add_instance = AsyncMock(return_value=mock_instance)
        registry.update_auth_status = AsyncMock(return_value=mock_instance)

        mock_auth_svc = MagicMock()
        mock_auth_svc.get_token_info.return_value = {
            "component_id": "node-001",
            "status": "active",
            "expires_at": "2027-03-04T03:56:23.900627+00:00",
            "component_type": "compute",
        }

        with patch("services.claude_auth_service.get_claude_auth_service", return_value=mock_auth_svc), \
             patch("services.observability_event_bus.get_event_bus", return_value=None):
            await register_instance(request, registry=registry)

        registry.update_auth_status.assert_called_once()
        call_args = registry.update_auth_status.call_args
        assert call_args[0][0] == "node-001"
        assert call_args[0][1] == ComputeAuthStatus.AUTHORIZED

    @pytest.mark.asyncio
    async def test_register_stays_unauthorized_without_token(self, registry):
        """Registration should not set AUTHORIZED when no token exists."""
        from api.compute import register_instance
        from models.compute import RegistrationRequest, InstanceCapabilities

        request = RegistrationRequest(
            instance_id="node-002",
            name="Node 002",
            endpoint="http://compute:8000",
            capabilities=InstanceCapabilities(agents=["agent-a"]),
        )

        mock_instance = _make_instance(instance_id="node-002")
        registry.add_instance = AsyncMock(return_value=mock_instance)
        registry.update_auth_status = AsyncMock()

        mock_auth_svc = MagicMock()
        mock_auth_svc.get_token_info.return_value = None

        with patch("services.claude_auth_service.get_claude_auth_service", return_value=mock_auth_svc), \
             patch("services.observability_event_bus.get_event_bus", return_value=None):
            await register_instance(request, registry=registry)

        registry.update_auth_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_stats_include_auth_breakdown(self, registry):
        """get_stats should include by_auth_status counts."""
        await registry.add_instance(_make_instance(instance_id="unauth-001"))
        await registry.add_instance(
            _make_instance(instance_id="auth-001", auth_status=ComputeAuthStatus.AUTHORIZED)
        )
        await registry.add_instance(
            _make_instance(instance_id="expired-001", auth_status=ComputeAuthStatus.EXPIRED)
        )

        stats = registry.get_stats()
        assert stats["by_auth_status"]["unauthorized"] == 1
        assert stats["by_auth_status"]["authorized"] == 1
        assert stats["by_auth_status"]["expired"] == 1
