"""Unit tests for compute reconnect-after-restart (#161).

Tests that:
- Previously approved instances preserve ONLINE status on reconnect
- Previously approved instances preserve auth_status on reconnect
- PENDING instances remain PENDING on reconnect
- POST /register is idempotent (preserves approval for existing instances)
- Capabilities are updated on reconnect even when status is preserved
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.compute import (
    ComputeAuthStatus,
    ComputeInstance,
    InstanceCapabilities,
    InstanceStatus,
)
from services.registry_service import ComputeRegistry


@pytest.fixture
def registry():
    """Create a fresh ComputeRegistry for each test."""
    return ComputeRegistry()


def _make_instance(instance_id: str, **overrides) -> ComputeInstance:
    """Helper to build a ComputeInstance with sensible defaults."""
    kwargs = {
        "instance_id": instance_id,
        "name": f"Test {instance_id}",
        "endpoint": "sse",
        "capabilities": InstanceCapabilities(),
    }
    kwargs.update(overrides)
    return ComputeInstance(**kwargs)


# =============================================================================
# SSE Reconnect: Status Preservation
# =============================================================================


class TestReconnectPreservesStatus:
    """Verify that previously approved instances retain ONLINE status on reconnect."""

    @pytest.mark.asyncio
    async def test_update_heartbeat_preserves_online_status(self, registry):
        """update_heartbeat does not change an ONLINE instance to PENDING."""
        instance = _make_instance("c-001", status=InstanceStatus.ONLINE)
        await registry.add_instance(instance)

        await registry.update_heartbeat("c-001", metadata={"sse_connected": True})

        result = await registry.get_instance("c-001")
        assert result.status == InstanceStatus.ONLINE

    @pytest.mark.asyncio
    async def test_update_instance_preserves_online_status(self, registry):
        """update_instance updates capabilities without touching status."""
        instance = _make_instance(
            "c-001",
            status=InstanceStatus.ONLINE,
            capabilities=InstanceCapabilities(agents=["old-agent"]),
        )
        await registry.add_instance(instance)

        new_caps = InstanceCapabilities(agents=["new-agent"])
        await registry.update_instance(
            "c-001",
            capabilities=new_caps,
            metadata={"sse_reconnected": True},
        )

        result = await registry.get_instance("c-001")
        assert result.status == InstanceStatus.ONLINE
        assert result.capabilities.agents == ["new-agent"]
        assert result.metadata.get("sse_reconnected") is True

    @pytest.mark.asyncio
    async def test_update_heartbeat_preserves_pending_status(self, registry):
        """update_heartbeat does not promote a PENDING instance."""
        instance = _make_instance("c-001")  # defaults to PENDING
        await registry.add_instance(instance)

        await registry.update_heartbeat("c-001", metadata={"sse_connected": True})

        result = await registry.get_instance("c-001")
        assert result.status == InstanceStatus.PENDING


# =============================================================================
# SSE Reconnect: Auth Status Preservation
# =============================================================================


class TestReconnectPreservesAuthStatus:
    """Verify that auth_status is preserved across reconnect."""

    @pytest.mark.asyncio
    async def test_update_heartbeat_preserves_authorized_auth(self, registry):
        """AUTHORIZED auth_status survives heartbeat updates."""
        instance = _make_instance("c-001", status=InstanceStatus.ONLINE)
        await registry.add_instance(instance)

        await registry.update_auth_status(
            "c-001", ComputeAuthStatus.AUTHORIZED
        )

        await registry.update_heartbeat("c-001", metadata={"sse_connected": True})

        result = await registry.get_instance("c-001")
        assert result.auth_status == ComputeAuthStatus.AUTHORIZED

    @pytest.mark.asyncio
    async def test_update_instance_preserves_authorized_auth(self, registry):
        """update_instance does not reset auth_status."""
        instance = _make_instance("c-001", status=InstanceStatus.ONLINE)
        await registry.add_instance(instance)

        await registry.update_auth_status(
            "c-001", ComputeAuthStatus.AUTHORIZED
        )

        new_caps = InstanceCapabilities(agents=["updated-agent"])
        await registry.update_instance("c-001", capabilities=new_caps)

        result = await registry.get_instance("c-001")
        assert result.auth_status == ComputeAuthStatus.AUTHORIZED


# =============================================================================
# SSE Reconnect: Project IDs Preservation
# =============================================================================


class TestReconnectPreservesProjectIds:
    """Verify that project_ids are preserved across reconnect."""

    @pytest.mark.asyncio
    async def test_update_heartbeat_preserves_project_ids(self, registry):
        """project_ids survive heartbeat updates."""
        instance = _make_instance("c-001")  # PENDING
        await registry.add_instance(instance)
        await registry.approve_instance("c-001", project_ids=["proj-a", "proj-b"])

        await registry.update_heartbeat("c-001", metadata={"sse_connected": True})

        result = await registry.get_instance("c-001")
        assert result.project_ids == ["proj-a", "proj-b"]

    @pytest.mark.asyncio
    async def test_update_instance_preserves_project_ids(self, registry):
        """update_instance does not clear project_ids."""
        instance = _make_instance("c-001")  # PENDING
        await registry.add_instance(instance)
        await registry.approve_instance("c-001", project_ids=["proj-a"])

        new_caps = InstanceCapabilities(agents=["new-agent"])
        await registry.update_instance("c-001", capabilities=new_caps)

        result = await registry.get_instance("c-001")
        assert result.project_ids == ["proj-a"]


# =============================================================================
# POST /register: Idempotency
# =============================================================================


class TestRegisterIdempotency:
    """Verify that POST /register handles existing instances gracefully."""

    @pytest.mark.asyncio
    async def test_add_instance_rejects_duplicate(self, registry):
        """add_instance still raises ValueError for duplicates (guard)."""
        instance = _make_instance("c-001")
        await registry.add_instance(instance)

        with pytest.raises(ValueError, match="already registered"):
            await registry.add_instance(_make_instance("c-001"))

    @pytest.mark.asyncio
    async def test_get_then_update_preserves_online(self, registry):
        """Simulates the idempotent re-register: get → update path."""
        # Initial registration + approval
        instance = _make_instance("c-001")  # PENDING
        await registry.add_instance(instance)
        await registry.approve_instance("c-001")

        # Simulate reconnect: check if exists, then update
        existing = await registry.get_instance("c-001")
        assert existing is not None
        assert existing.status == InstanceStatus.ONLINE

        new_caps = InstanceCapabilities(agents=["reconnect-agent"])
        await registry.update_instance(
            "c-001",
            capabilities=new_caps,
            metadata={"reconnect": True},
        )
        await registry.update_heartbeat("c-001")

        result = await registry.get_instance("c-001")
        assert result.status == InstanceStatus.ONLINE
        assert result.capabilities.agents == ["reconnect-agent"]

    @pytest.mark.asyncio
    async def test_get_then_update_preserves_pending(self, registry):
        """Idempotent re-register for a PENDING instance keeps it PENDING."""
        instance = _make_instance("c-001")  # PENDING
        await registry.add_instance(instance)

        existing = await registry.get_instance("c-001")
        assert existing is not None
        assert existing.status == InstanceStatus.PENDING

        await registry.update_instance(
            "c-001",
            capabilities=InstanceCapabilities(agents=["agent-v2"]),
        )

        result = await registry.get_instance("c-001")
        assert result.status == InstanceStatus.PENDING


# =============================================================================
# Full Reconnect Simulation
# =============================================================================


class TestFullReconnectFlow:
    """End-to-end simulation of the reconnect-after-restart flow."""

    @pytest.mark.asyncio
    async def test_approved_instance_survives_restart(self, registry):
        """Simulate: register → approve → restart → reconnect → still approved."""
        # Phase 1: Initial registration and approval
        instance = _make_instance("c-001")
        await registry.add_instance(instance)
        await registry.approve_instance("c-001", project_ids=["proj-x"])
        await registry.update_auth_status("c-001", ComputeAuthStatus.AUTHORIZED)

        approved = await registry.get_instance("c-001")
        assert approved.status == InstanceStatus.ONLINE
        assert approved.auth_status == ComputeAuthStatus.AUTHORIZED
        assert approved.project_ids == ["proj-x"]

        # Phase 2: Simulate serving restart — new registry loads from same data
        # (In production, _load_from_storage populates _instances from JSON)
        restart_registry = ComputeRegistry()
        restart_registry._instances = {"c-001": approved}

        # Phase 3: Compute reconnects — POST /register finds existing
        existing = await restart_registry.get_instance("c-001")
        assert existing is not None
        assert existing.status == InstanceStatus.ONLINE

        # Update capabilities (may have changed) but preserve status
        new_caps = InstanceCapabilities(agents=["agent-v2"])
        await restart_registry.update_instance(
            "c-001",
            capabilities=new_caps,
            metadata={"sse_reconnected": True},
        )
        await restart_registry.update_heartbeat("c-001")

        # Phase 4: Verify everything preserved
        result = await restart_registry.get_instance("c-001")
        assert result.status == InstanceStatus.ONLINE
        assert result.auth_status == ComputeAuthStatus.AUTHORIZED
        assert result.project_ids == ["proj-x"]
        assert result.capabilities.agents == ["agent-v2"]
        assert result.metadata.get("sse_reconnected") is True

    @pytest.mark.asyncio
    async def test_pending_instance_stays_pending_after_restart(self, registry):
        """Pending instances don't get auto-approved on restart."""
        instance = _make_instance("c-001")
        await registry.add_instance(instance)

        pending = await registry.get_instance("c-001")
        assert pending.status == InstanceStatus.PENDING

        # Simulate restart
        restart_registry = ComputeRegistry()
        restart_registry._instances = {"c-001": pending}

        # Reconnect
        existing = await restart_registry.get_instance("c-001")
        assert existing.status == InstanceStatus.PENDING

        await restart_registry.update_heartbeat("c-001", metadata={"sse_connected": True})

        result = await restart_registry.get_instance("c-001")
        assert result.status == InstanceStatus.PENDING

    @pytest.mark.asyncio
    async def test_capabilities_updated_on_reconnect(self, registry):
        """Capabilities from reconnect headers replace stale capabilities."""
        instance = _make_instance(
            "c-001",
            status=InstanceStatus.ONLINE,
            capabilities=InstanceCapabilities(
                agents=["old-agent"],
                labels=["old-label"],
            ),
        )
        await registry.add_instance(instance)

        new_caps = InstanceCapabilities(
            agents=["new-agent-1", "new-agent-2"],
            labels=["new-label"],
            tools_available=["new-tool"],
        )
        await registry.update_instance("c-001", capabilities=new_caps)

        result = await registry.get_instance("c-001")
        assert result.capabilities.agents == ["new-agent-1", "new-agent-2"]
        assert result.capabilities.labels == ["new-label"]
        assert result.capabilities.tools_available == ["new-tool"]
        assert result.status == InstanceStatus.ONLINE
