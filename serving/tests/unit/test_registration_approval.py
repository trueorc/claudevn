"""Unit tests for compute registration approval workflow (#129).

Tests that:
- New instances default to PENDING status with empty project_ids
- POST /register enforces PENDING status and registration token
- SSE /connect preserves PENDING for pre-registered instances
- Approval transitions PENDING → ONLINE with project assignment
- Rejection removes the instance from the registry
"""

import pytest
from datetime import datetime, timezone

from models.compute import (
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
# Model Defaults
# =============================================================================


class TestModelDefaults:
    """Verify ComputeInstance model defaults match the security contract."""

    def test_default_status_is_pending(self):
        instance = _make_instance("c-001")
        assert instance.status == InstanceStatus.PENDING

    def test_default_project_ids_is_empty(self):
        instance = _make_instance("c-001")
        assert instance.project_ids == []

    def test_pending_instance_not_healthy(self):
        instance = _make_instance("c-001")
        assert instance.is_healthy() is False

    def test_pending_instance_not_work_eligible(self):
        instance = _make_instance("c-001")
        assert instance.is_work_eligible() is False

    def test_explicit_online_still_works(self):
        """Callers can still explicitly set ONLINE if needed."""
        instance = _make_instance("c-001", status=InstanceStatus.ONLINE)
        assert instance.status == InstanceStatus.ONLINE


# =============================================================================
# Registry: Approval Flow
# =============================================================================


class TestApproveInstance:
    """Tests for registry.approve_instance()."""

    @pytest.mark.asyncio
    async def test_approve_transitions_to_online(self, registry):
        instance = _make_instance(
            "c-001",
            status=InstanceStatus.PENDING,
            pending_since=datetime.now(timezone.utc),
        )
        await registry.add_instance(instance)

        approved = await registry.approve_instance("c-001")

        assert approved is not None
        assert approved.status == InstanceStatus.ONLINE
        assert approved.pending_since is None

    @pytest.mark.asyncio
    async def test_approve_assigns_default_projects(self, registry):
        """Without explicit project_ids, approval leaves instance benched ([])."""
        instance = _make_instance(
            "c-001",
            status=InstanceStatus.PENDING,
            pending_since=datetime.now(timezone.utc),
        )
        await registry.add_instance(instance)

        approved = await registry.approve_instance("c-001")

        assert approved.project_ids == []

    @pytest.mark.asyncio
    async def test_approve_assigns_specific_projects(self, registry):
        instance = _make_instance(
            "c-001",
            status=InstanceStatus.PENDING,
            pending_since=datetime.now(timezone.utc),
        )
        await registry.add_instance(instance)

        approved = await registry.approve_instance("c-001", project_ids=["proj-a", "proj-b"])

        assert approved.project_ids == ["proj-a", "proj-b"]

    @pytest.mark.asyncio
    async def test_approve_non_pending_raises(self, registry):
        """Approving an ONLINE instance raises ValueError."""
        instance = _make_instance("c-001", status=InstanceStatus.ONLINE)
        await registry.add_instance(instance)

        with pytest.raises(ValueError, match="not pending"):
            await registry.approve_instance("c-001")

    @pytest.mark.asyncio
    async def test_approve_nonexistent_returns_none(self, registry):
        result = await registry.approve_instance("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_approve_updates_project_index(self, registry):
        """After approval, instance appears in project lookups."""
        instance = _make_instance(
            "c-001",
            status=InstanceStatus.PENDING,
            pending_since=datetime.now(timezone.utc),
        )
        await registry.add_instance(instance)

        # Before approval — empty project_ids, no project index match
        by_project = await registry.get_by_project("proj-a", online_only=False)
        assert len(by_project) == 0

        await registry.approve_instance("c-001", project_ids=["proj-a"])

        by_project = await registry.get_by_project("proj-a", online_only=False)
        assert any(i.instance_id == "c-001" for i in by_project)


# =============================================================================
# Registry: Rejection Flow
# =============================================================================


class TestRejectInstance:
    """Tests for registry.reject_instance()."""

    @pytest.mark.asyncio
    async def test_reject_removes_instance(self, registry):
        instance = _make_instance(
            "c-001",
            status=InstanceStatus.PENDING,
            pending_since=datetime.now(timezone.utc),
        )
        await registry.add_instance(instance)

        result = await registry.reject_instance("c-001", reason="Not authorized")
        assert result is True

        found = await registry.get_instance("c-001")
        assert found is None

    @pytest.mark.asyncio
    async def test_reject_non_pending_raises(self, registry):
        instance = _make_instance("c-001", status=InstanceStatus.ONLINE)
        await registry.add_instance(instance)

        with pytest.raises(ValueError, match="not pending"):
            await registry.reject_instance("c-001")

    @pytest.mark.asyncio
    async def test_reject_nonexistent_returns_false(self, registry):
        result = await registry.reject_instance("nonexistent")
        assert result is False


# =============================================================================
# Registry: Listing Pending
# =============================================================================


class TestListPendingInstances:
    """Tests for registry.list_pending_instances()."""

    @pytest.mark.asyncio
    async def test_list_only_pending(self, registry):
        pending = _make_instance(
            "c-pending",
            status=InstanceStatus.PENDING,
            pending_since=datetime.now(timezone.utc),
        )
        online = _make_instance("c-online", status=InstanceStatus.ONLINE)
        await registry.add_instance(pending)
        await registry.add_instance(online)

        result = await registry.list_pending_instances()

        assert len(result) == 1
        assert result[0].instance_id == "c-pending"

    @pytest.mark.asyncio
    async def test_list_pending_sorted_oldest_first(self, registry):
        older = _make_instance(
            "c-older",
            status=InstanceStatus.PENDING,
            pending_since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        newer = _make_instance(
            "c-newer",
            status=InstanceStatus.PENDING,
            pending_since=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )
        await registry.add_instance(newer)
        await registry.add_instance(older)

        result = await registry.list_pending_instances()

        assert result[0].instance_id == "c-older"
        assert result[1].instance_id == "c-newer"

    @pytest.mark.asyncio
    async def test_empty_when_none_pending(self, registry):
        result = await registry.list_pending_instances()
        assert result == []


# =============================================================================
# Registration: PENDING Enforcement
# =============================================================================


class TestRegistrationEnforcesPending:
    """Verify that add_instance preserves PENDING status and empty project_ids."""

    @pytest.mark.asyncio
    async def test_registered_instance_stays_pending(self, registry):
        """Instance created with model defaults stays PENDING after registration."""
        instance = _make_instance("c-001")
        registered = await registry.add_instance(instance)

        assert registered.status == InstanceStatus.PENDING
        assert registered.project_ids == []

    @pytest.mark.asyncio
    async def test_registered_pending_not_in_work_eligible(self, registry):
        """A PENDING instance with empty projects should never match work routing."""
        instance = _make_instance("c-001")
        await registry.add_instance(instance)

        match = await registry.find_matching_compute()
        assert match is None

    @pytest.mark.asyncio
    async def test_heartbeat_does_not_promote_pending(self, registry):
        """Heartbeat on a PENDING instance must not change status to ONLINE."""
        instance = _make_instance(
            "c-001",
            status=InstanceStatus.PENDING,
            pending_since=datetime.now(timezone.utc),
        )
        await registry.add_instance(instance)

        await registry.update_heartbeat("c-001", metadata={"sse_connected": True})

        refreshed = await registry.get_instance("c-001")
        assert refreshed.status == InstanceStatus.PENDING
