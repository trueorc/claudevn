"""Tests for user-to-component ownership model."""

import pytest
from datetime import datetime, timezone

from models.compute import ComputeInstance, InstanceCapabilities
from services.registry_service import ComputeRegistry


@pytest.fixture
def registry():
    return ComputeRegistry()


def _make_instance(instance_id="test-001", owner_id=None, **kwargs):
    return ComputeInstance(
        instance_id=instance_id,
        name=f"Test {instance_id}",
        endpoint="http://localhost:8003",
        owner_id=owner_id,
        **kwargs,
    )


class TestOwnershipFields:
    def test_default_no_owner(self):
        instance = _make_instance()
        assert instance.owner_id is None
        assert instance.claimed_at is None

    def test_set_owner(self):
        instance = _make_instance(owner_id="user-001")
        assert instance.owner_id == "user-001"

    def test_serialization_includes_ownership(self):
        now = datetime.now(timezone.utc)
        instance = _make_instance(owner_id="user-001")
        instance.claimed_at = now
        data = instance.model_dump()
        assert data["owner_id"] == "user-001"
        assert data["claimed_at"] is not None


class TestClaimInstance:
    @pytest.mark.asyncio
    async def test_claim_unclaimed_instance(self, registry):
        instance = _make_instance()
        await registry.add_instance(instance)

        claimed = await registry.claim_instance("test-001", "user-001")
        assert claimed is not None
        assert claimed.owner_id == "user-001"
        assert claimed.claimed_at is not None

    @pytest.mark.asyncio
    async def test_claim_own_instance_idempotent(self, registry):
        instance = _make_instance(owner_id="user-001")
        await registry.add_instance(instance)

        # Re-claiming by same user should work
        claimed = await registry.claim_instance("test-001", "user-001")
        assert claimed.owner_id == "user-001"

    @pytest.mark.asyncio
    async def test_claim_other_users_instance_raises(self, registry):
        instance = _make_instance(owner_id="user-001")
        await registry.add_instance(instance)

        with pytest.raises(ValueError, match="already claimed"):
            await registry.claim_instance("test-001", "user-002")

    @pytest.mark.asyncio
    async def test_claim_nonexistent_instance(self, registry):
        result = await registry.claim_instance("nonexistent", "user-001")
        assert result is None


class TestOwnershipQueries:
    @pytest.mark.asyncio
    async def test_get_instances_by_owner(self, registry):
        await registry.add_instance(_make_instance("comp-1", owner_id="user-001"))
        await registry.add_instance(_make_instance("comp-2", owner_id="user-001"))
        await registry.add_instance(_make_instance("comp-3", owner_id="user-002"))

        owned = await registry.get_instances_by_owner("user-001")
        assert len(owned) == 2
        assert all(i.owner_id == "user-001" for i in owned)

    @pytest.mark.asyncio
    async def test_get_instances_by_owner_none(self, registry):
        await registry.add_instance(_make_instance("comp-1", owner_id="user-002"))

        owned = await registry.get_instances_by_owner("user-001")
        assert len(owned) == 0

    @pytest.mark.asyncio
    async def test_get_unclaimed_instances(self, registry):
        await registry.add_instance(_make_instance("comp-1"))
        await registry.add_instance(_make_instance("comp-2", owner_id="user-001"))
        await registry.add_instance(_make_instance("comp-3"))

        unclaimed = await registry.get_unclaimed_instances()
        assert len(unclaimed) == 2
        assert all(i.owner_id is None for i in unclaimed)

    @pytest.mark.asyncio
    async def test_get_unclaimed_instances_all_claimed(self, registry):
        await registry.add_instance(_make_instance("comp-1", owner_id="user-001"))

        unclaimed = await registry.get_unclaimed_instances()
        assert len(unclaimed) == 0


class TestOwnershipPersistence:
    @pytest.mark.asyncio
    async def test_claim_persists_on_get(self, registry):
        """After claiming, get_instance should reflect ownership."""
        await registry.add_instance(_make_instance("comp-1"))
        await registry.claim_instance("comp-1", "user-001")

        instance = await registry.get_instance("comp-1")
        assert instance.owner_id == "user-001"

    @pytest.mark.asyncio
    async def test_ownership_survives_in_list(self, registry):
        await registry.add_instance(_make_instance("comp-1", owner_id="user-001"))

        instances = await registry.list_instances()
        assert instances[0].owner_id == "user-001"
