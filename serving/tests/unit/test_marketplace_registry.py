"""Tests for MarketplaceRegistry service."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from services.marketplace_registry import (
    MarketplaceRegistry,
    get_marketplace_registry,
    set_marketplace_registry
)
from models.marketplace import (
    MarketplaceInstance,
    MarketplaceStatus,
    MarketplaceTier,
    MarketplaceCapabilities,
)


@pytest.fixture
def mock_storage():
    """Create mock storage backend."""
    storage = MagicMock()
    storage.save_marketplace = AsyncMock()
    storage.delete_marketplace = AsyncMock()
    storage.load_all_instances = AsyncMock(return_value={})
    return storage


@pytest.fixture
def mock_cache():
    """Create mock cache backend."""
    cache = MagicMock()
    return cache


@pytest.fixture
def registry():
    """Create registry without backends for in-memory testing."""
    return MarketplaceRegistry(storage_backend=None, cache_backend=None)


@pytest.fixture
def registry_with_storage(mock_storage, mock_cache):
    """Create registry with mocked storage."""
    return MarketplaceRegistry(storage_backend=mock_storage, cache_backend=mock_cache)


@pytest.fixture
def sample_marketplace():
    """Create a sample marketplace instance."""
    return MarketplaceInstance(
        marketplace_id="marketplace-001",
        name="Test Marketplace",
        endpoint="http://localhost:8001",
        capabilities=MarketplaceCapabilities(
            agent_count=10,
            tool_count=5,
            supports_search=True,
            supports_categories=True
        ),
        priority=1
    )


@pytest.fixture
def sample_marketplace_2():
    """Create a second sample marketplace instance."""
    return MarketplaceInstance(
        marketplace_id="marketplace-002",
        name="Test Marketplace 2",
        endpoint="http://localhost:8002",
        capabilities=MarketplaceCapabilities(
            agent_count=20,
            tool_count=10
        ),
        priority=2
    )


class TestMarketplaceRegistryInit:
    """Test MarketplaceRegistry initialization."""

    def test_init_without_backends(self):
        """Test initialization without storage/cache backends."""
        registry = MarketplaceRegistry()
        assert registry._marketplaces == {}
        assert registry._storage is None

    def test_init_with_storage(self, mock_storage, mock_cache):
        """Test initialization with storage backend."""
        registry = MarketplaceRegistry(
            storage_backend=mock_storage,
            cache_backend=mock_cache
        )
        assert registry._storage is mock_storage
        assert registry._cache is mock_cache

    @pytest.mark.asyncio
    async def test_initialize_loads_from_storage(self, mock_storage, mock_cache):
        """Test initialization loads marketplaces from storage."""
        mock_storage.load_all_instances = AsyncMock(return_value={
            "marketplace-001": {
                "marketplace_id": "marketplace-001",
                "name": "Stored Marketplace",
                "endpoint": "http://localhost:8001",
                "status": "healthy",
                "capabilities": {"agent_count": 5, "tool_count": 2},
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                "failed_health_checks": 0,
                "priority": 1,
                "metadata": {},
                "version": "0.1.0",
                "heartbeat_interval": 60
            }
        })

        registry = MarketplaceRegistry(
            storage_backend=mock_storage,
            cache_backend=mock_cache
        )
        await registry.initialize()

        assert "marketplace-001" in registry._marketplaces
        mock_storage.load_all_instances.assert_called_once_with("marketplaces")

    @pytest.mark.asyncio
    async def test_initialize_skips_stale_marketplaces(self, mock_storage, mock_cache):
        """Test initialization skips marketplaces with old heartbeats."""
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
        fresh_time = datetime.now(timezone.utc).isoformat()

        mock_storage.load_all_instances = AsyncMock(return_value={
            "stale-001": {
                "marketplace_id": "stale-001",
                "name": "Stale Marketplace",
                "endpoint": "http://localhost:8001",
                "status": "healthy",
                "capabilities": {"agent_count": 5, "tool_count": 2},
                "registered_at": stale_time,
                "last_heartbeat": stale_time,
                "failed_health_checks": 0,
                "priority": 1,
                "metadata": {},
                "version": "0.1.0",
                "heartbeat_interval": 60
            },
            "fresh-001": {
                "marketplace_id": "fresh-001",
                "name": "Fresh Marketplace",
                "endpoint": "http://localhost:8002",
                "status": "healthy",
                "capabilities": {"agent_count": 10, "tool_count": 5},
                "registered_at": fresh_time,
                "last_heartbeat": fresh_time,
                "failed_health_checks": 0,
                "priority": 1,
                "metadata": {},
                "version": "0.1.0",
                "heartbeat_interval": 60
            }
        })

        registry = MarketplaceRegistry(
            storage_backend=mock_storage,
            cache_backend=mock_cache
        )
        await registry.initialize()

        # Fresh marketplace loaded, stale one skipped
        assert "fresh-001" in registry._marketplaces
        assert "stale-001" not in registry._marketplaces
        # Stale entry deleted from disk
        mock_storage.delete_marketplace.assert_called_once_with("stale-001")

    @pytest.mark.asyncio
    async def test_initialize_stale_threshold_is_configurable(self, mock_storage, mock_cache):
        """Test that the stale threshold can be customized."""
        # Heartbeat 60s ago - stale with low threshold, fresh with high
        borderline_time = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()

        mock_storage.load_all_instances = AsyncMock(return_value={
            "marketplace-001": {
                "marketplace_id": "marketplace-001",
                "name": "Borderline Marketplace",
                "endpoint": "http://localhost:8001",
                "status": "healthy",
                "capabilities": {"agent_count": 5, "tool_count": 2},
                "registered_at": borderline_time,
                "last_heartbeat": borderline_time,
                "failed_health_checks": 0,
                "priority": 1,
                "metadata": {},
                "version": "0.1.0",
                "heartbeat_interval": 60
            }
        })

        # With low threshold (30s) - should be considered stale
        registry = MarketplaceRegistry(
            storage_backend=mock_storage,
            cache_backend=mock_cache,
            startup_stale_threshold=30
        )
        await registry.initialize()
        assert "marketplace-001" not in registry._marketplaces

        # Reset mock for second test
        mock_storage.load_all_instances.reset_mock()
        mock_storage.delete_marketplace.reset_mock()

        # With high threshold (120s) - should be loaded
        registry2 = MarketplaceRegistry(
            storage_backend=mock_storage,
            cache_backend=mock_cache,
            startup_stale_threshold=120
        )
        await registry2.initialize()
        assert "marketplace-001" in registry2._marketplaces


class TestMarketplaceRegistryAddMarketplace:
    """Test add_marketplace operation."""

    @pytest.mark.asyncio
    async def test_add_marketplace(self, registry, sample_marketplace):
        """Test registering a new marketplace."""
        result = await registry.add_marketplace(sample_marketplace)

        assert result.marketplace_id == "marketplace-001"
        assert result.name == "Test Marketplace"
        assert result.status == MarketplaceStatus.HEALTHY
        assert result.registered_at is not None
        assert result.last_heartbeat is not None
        assert result.failed_health_checks == 0

    @pytest.mark.asyncio
    async def test_add_marketplace_persists_to_storage(
        self, registry_with_storage, sample_marketplace, mock_storage
    ):
        """Test that adding marketplace saves to storage."""
        await registry_with_storage.add_marketplace(sample_marketplace)

        mock_storage.save_marketplace.assert_called_once()
        call_args = mock_storage.save_marketplace.call_args
        assert call_args[0][0] == "marketplace-001"

    @pytest.mark.asyncio
    async def test_add_marketplace_duplicate_raises_error(
        self, registry, sample_marketplace
    ):
        """Test that adding duplicate marketplace raises ValueError."""
        await registry.add_marketplace(sample_marketplace)

        with pytest.raises(ValueError, match="already registered"):
            await registry.add_marketplace(sample_marketplace)


class TestMarketplaceRegistryRemoveMarketplace:
    """Test remove_marketplace operation."""

    @pytest.mark.asyncio
    async def test_remove_marketplace(self, registry, sample_marketplace):
        """Test removing a marketplace."""
        await registry.add_marketplace(sample_marketplace)

        result = await registry.remove_marketplace("marketplace-001")

        assert result is True
        assert await registry.get_marketplace("marketplace-001") is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent_marketplace(self, registry):
        """Test removing nonexistent marketplace returns False."""
        result = await registry.remove_marketplace("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_marketplace_deletes_from_storage(
        self, registry_with_storage, sample_marketplace, mock_storage
    ):
        """Test that removing marketplace deletes from storage."""
        await registry_with_storage.add_marketplace(sample_marketplace)

        await registry_with_storage.remove_marketplace("marketplace-001")

        mock_storage.delete_marketplace.assert_called_once_with("marketplace-001")


class TestMarketplaceRegistryGetMarketplace:
    """Test get_marketplace operation."""

    @pytest.mark.asyncio
    async def test_get_marketplace(self, registry, sample_marketplace):
        """Test getting a marketplace by ID."""
        await registry.add_marketplace(sample_marketplace)

        result = await registry.get_marketplace("marketplace-001")

        assert result is not None
        assert result.marketplace_id == "marketplace-001"
        assert result.name == "Test Marketplace"

    @pytest.mark.asyncio
    async def test_get_nonexistent_marketplace(self, registry):
        """Test getting nonexistent marketplace returns None."""
        result = await registry.get_marketplace("nonexistent")
        assert result is None


class TestMarketplaceRegistryListMarketplaces:
    """Test list_marketplaces operation."""

    @pytest.mark.asyncio
    async def test_list_marketplaces_empty(self, registry):
        """Test listing marketplaces when empty."""
        result = await registry.list_marketplaces()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_marketplaces(
        self, registry, sample_marketplace, sample_marketplace_2
    ):
        """Test listing all marketplaces."""
        await registry.add_marketplace(sample_marketplace)
        await registry.add_marketplace(sample_marketplace_2)

        result = await registry.list_marketplaces()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_marketplaces_sorted_by_priority(
        self, registry, sample_marketplace, sample_marketplace_2
    ):
        """Test marketplaces are sorted by priority."""
        # Add higher priority (2) first
        await registry.add_marketplace(sample_marketplace_2)
        # Add lower priority (1) second
        await registry.add_marketplace(sample_marketplace)

        result = await registry.list_marketplaces()

        # Lower priority number should come first
        assert result[0].marketplace_id == "marketplace-001"
        assert result[1].marketplace_id == "marketplace-002"

    @pytest.mark.asyncio
    async def test_list_marketplaces_filter_by_status(self, registry, sample_marketplace):
        """Test filtering marketplaces by status."""
        await registry.add_marketplace(sample_marketplace)

        # Set one to degraded
        marketplace = await registry.get_marketplace("marketplace-001")
        marketplace.status = MarketplaceStatus.DEGRADED

        healthy_result = await registry.list_marketplaces(status=MarketplaceStatus.HEALTHY)
        degraded_result = await registry.list_marketplaces(status=MarketplaceStatus.DEGRADED)

        assert len(healthy_result) == 0
        assert len(degraded_result) == 1

    @pytest.mark.asyncio
    async def test_list_marketplaces_with_limit(
        self, registry, sample_marketplace, sample_marketplace_2
    ):
        """Test listing marketplaces with limit."""
        await registry.add_marketplace(sample_marketplace)
        await registry.add_marketplace(sample_marketplace_2)

        result = await registry.list_marketplaces(limit=1)

        assert len(result) == 1


class TestMarketplaceRegistryUpdateHeartbeat:
    """Test heartbeat and status update operations."""

    @pytest.mark.asyncio
    async def test_update_heartbeat(self, registry, sample_marketplace):
        """Test updating marketplace heartbeat."""
        await registry.add_marketplace(sample_marketplace)
        original = await registry.get_marketplace("marketplace-001")
        original_heartbeat = original.last_heartbeat

        result = await registry.update_heartbeat("marketplace-001")

        assert result is True
        updated = await registry.get_marketplace("marketplace-001")
        assert updated.last_heartbeat >= original_heartbeat

    @pytest.mark.asyncio
    async def test_update_heartbeat_nonexistent(self, registry):
        """Test updating heartbeat for nonexistent marketplace."""
        result = await registry.update_heartbeat("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_update_heartbeat_with_metadata(self, registry, sample_marketplace):
        """Test updating heartbeat with metadata updates."""
        await registry.add_marketplace(sample_marketplace)

        result = await registry.update_heartbeat(
            "marketplace-001",
            metadata={"agent_count": 25, "tool_count": 15}
        )

        assert result is True
        updated = await registry.get_marketplace("marketplace-001")
        assert updated.capabilities.agent_count == 25
        assert updated.capabilities.tool_count == 15

    @pytest.mark.asyncio
    async def test_update_heartbeat_resets_failed_checks(
        self, registry, sample_marketplace
    ):
        """Test heartbeat resets failed health checks."""
        await registry.add_marketplace(sample_marketplace)
        marketplace = await registry.get_marketplace("marketplace-001")
        marketplace.failed_health_checks = 2
        marketplace.status = MarketplaceStatus.DEGRADED

        await registry.update_heartbeat("marketplace-001")

        updated = await registry.get_marketplace("marketplace-001")
        assert updated.failed_health_checks == 0
        assert updated.status == MarketplaceStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_update_marketplace_fields(self, registry, sample_marketplace):
        """Test updating marketplace fields."""
        await registry.add_marketplace(sample_marketplace)

        result = await registry.update_marketplace(
            "marketplace-001",
            name="Updated Name",
            priority=5
        )

        assert result is not None
        assert result.name == "Updated Name"
        assert result.priority == 5

    @pytest.mark.asyncio
    async def test_update_nonexistent_marketplace(self, registry):
        """Test updating nonexistent marketplace returns None."""
        result = await registry.update_marketplace("nonexistent", name="New Name")
        assert result is None


class TestMarketplaceRegistryHealthCheck:
    """Test health check operations."""

    @pytest.mark.asyncio
    async def test_check_health_healthy_marketplace(self, registry, sample_marketplace):
        """Test health check for healthy marketplace."""
        await registry.add_marketplace(sample_marketplace)

        changes = await registry.check_health(
            degraded_threshold=90,
            offline_threshold=180
        )

        assert changes["degraded"] == 0
        assert changes["offline"] == 0
        assert changes["deregistered"] == 0

    @pytest.mark.asyncio
    async def test_check_health_marks_degraded(self, registry, sample_marketplace):
        """Test health check marks marketplace as degraded."""
        await registry.add_marketplace(sample_marketplace)
        marketplace = await registry.get_marketplace("marketplace-001")
        # Set last heartbeat to 2 minutes ago
        marketplace.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=120)

        changes = await registry.check_health(
            degraded_threshold=90,
            offline_threshold=180
        )

        assert changes["degraded"] == 1
        updated = await registry.get_marketplace("marketplace-001")
        assert updated.status == MarketplaceStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_check_health_marks_offline(self, registry, sample_marketplace):
        """Test health check marks marketplace as offline."""
        await registry.add_marketplace(sample_marketplace)
        marketplace = await registry.get_marketplace("marketplace-001")
        # Set last heartbeat to 4 minutes ago
        marketplace.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=240)

        changes = await registry.check_health(
            degraded_threshold=90,
            offline_threshold=180
        )

        assert changes["offline"] == 1
        updated = await registry.get_marketplace("marketplace-001")
        assert updated.status == MarketplaceStatus.OFFLINE
        assert updated.failed_health_checks == 1

    @pytest.mark.asyncio
    async def test_check_health_deregisters_stale_marketplace(
        self, registry, sample_marketplace
    ):
        """Test health check auto-deregisters marketplace after max failures."""
        await registry.add_marketplace(sample_marketplace)
        marketplace = await registry.get_marketplace("marketplace-001")
        # Set last heartbeat to old and simulate previous failures
        marketplace.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=240)
        marketplace.failed_health_checks = 2  # Already at 2, next will be 3

        changes = await registry.check_health(
            degraded_threshold=90,
            offline_threshold=180,
            max_failed_checks=3
        )

        assert changes["deregistered"] == 1
        assert await registry.get_marketplace("marketplace-001") is None


class TestMarketplaceRegistryGetStats:
    """Test statistics operations."""

    @pytest.mark.asyncio
    async def test_get_stats_empty(self, registry):
        """Test getting stats with no marketplaces."""
        stats = registry.get_stats()

        assert stats["total_marketplaces"] == 0
        assert stats["healthy"] == 0
        assert stats["degraded"] == 0
        assert stats["offline"] == 0
        assert stats["total_agents"] == 0
        assert stats["total_tools"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_with_marketplaces(
        self, registry, sample_marketplace, sample_marketplace_2
    ):
        """Test getting stats with multiple marketplaces."""
        await registry.add_marketplace(sample_marketplace)
        await registry.add_marketplace(sample_marketplace_2)

        stats = registry.get_stats()

        assert stats["total_marketplaces"] == 2
        assert stats["healthy"] == 2
        assert stats["total_agents"] == 30  # 10 + 20
        assert stats["total_tools"] == 15  # 5 + 10

    @pytest.mark.asyncio
    async def test_get_stats_by_status(self, registry, sample_marketplace):
        """Test stats include status breakdown."""
        await registry.add_marketplace(sample_marketplace)
        marketplace = await registry.get_marketplace("marketplace-001")
        marketplace.status = MarketplaceStatus.DEGRADED

        stats = registry.get_stats()

        assert stats["by_status"]["degraded"] == 1
        assert stats["healthy"] == 0
        assert stats["degraded"] == 1

    @pytest.mark.asyncio
    async def test_get_aggregated_stats(
        self, registry, sample_marketplace, sample_marketplace_2
    ):
        """Test getting aggregated statistics model."""
        await registry.add_marketplace(sample_marketplace)
        await registry.add_marketplace(sample_marketplace_2)

        stats = await registry.get_aggregated_stats()

        assert stats.total_marketplaces == 2
        assert stats.healthy_marketplaces == 2
        assert stats.degraded_marketplaces == 0
        assert stats.offline_marketplaces == 0
        assert stats.total_agents == 30
        assert stats.total_tools == 15


class TestMarketplaceRegistryQuerySelection:
    """Test marketplace selection for queries."""

    @pytest.mark.asyncio
    async def test_get_marketplace_for_query_returns_preferred(
        self, registry, sample_marketplace, sample_marketplace_2
    ):
        """Test get_marketplace_for_query returns preferred if healthy."""
        await registry.add_marketplace(sample_marketplace)
        await registry.add_marketplace(sample_marketplace_2)

        result = await registry.get_marketplace_for_query(
            preferred_marketplace_id="marketplace-002"
        )

        assert result.marketplace_id == "marketplace-002"

    @pytest.mark.asyncio
    async def test_get_marketplace_for_query_skips_unhealthy_preferred(
        self, registry, sample_marketplace, sample_marketplace_2
    ):
        """Test skips unhealthy preferred marketplace."""
        await registry.add_marketplace(sample_marketplace)
        await registry.add_marketplace(sample_marketplace_2)

        # Make preferred marketplace unhealthy
        marketplace_2 = await registry.get_marketplace("marketplace-002")
        marketplace_2.status = MarketplaceStatus.OFFLINE

        result = await registry.get_marketplace_for_query(
            preferred_marketplace_id="marketplace-002"
        )

        # Should get marketplace-001 instead (highest priority healthy)
        assert result.marketplace_id == "marketplace-001"

    @pytest.mark.asyncio
    async def test_get_marketplace_for_query_by_priority(
        self, registry, sample_marketplace, sample_marketplace_2
    ):
        """Test returns highest priority healthy marketplace."""
        await registry.add_marketplace(sample_marketplace)  # priority 1
        await registry.add_marketplace(sample_marketplace_2)  # priority 2

        result = await registry.get_marketplace_for_query()

        assert result.marketplace_id == "marketplace-001"

    @pytest.mark.asyncio
    async def test_get_marketplace_for_query_fallback_to_degraded(
        self, registry, sample_marketplace
    ):
        """Test falls back to degraded if no healthy marketplaces."""
        await registry.add_marketplace(sample_marketplace)
        marketplace = await registry.get_marketplace("marketplace-001")
        marketplace.status = MarketplaceStatus.DEGRADED

        result = await registry.get_marketplace_for_query()

        assert result is not None
        assert result.marketplace_id == "marketplace-001"

    @pytest.mark.asyncio
    async def test_get_marketplace_for_query_returns_none_if_all_offline(
        self, registry, sample_marketplace
    ):
        """Test returns None if all marketplaces are offline."""
        await registry.add_marketplace(sample_marketplace)
        marketplace = await registry.get_marketplace("marketplace-001")
        marketplace.status = MarketplaceStatus.OFFLINE

        result = await registry.get_marketplace_for_query()

        assert result is None


class TestMarketplaceRegistryGlobals:
    """Test global instance management."""

    def test_set_get_registry(self):
        """Test setting and getting global registry."""
        registry = MarketplaceRegistry()
        set_marketplace_registry(registry)

        retrieved = get_marketplace_registry()
        assert retrieved is registry

    def test_get_registry_not_initialized(self):
        """Test getting registry when not initialized raises error."""
        set_marketplace_registry(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_marketplace_registry()


# =============================================================================
# Multi-Marketplace Skill Resolution Tests
# =============================================================================

class TestMarketplaceRegistrySkillResolution:
    """Test tier-based skill resolution across multiple marketplaces."""

    @pytest.fixture
    def registry_with_marketplaces(self, mock_storage, mock_cache):
        """Create a registry with ROOT and EXTENDED marketplaces."""
        registry = MarketplaceRegistry(
            storage_backend=mock_storage,
            cache_backend=mock_cache,
        )
        root_mp = MarketplaceInstance(
            marketplace_id="root-mp",
            name="Core Marketplace",
            endpoint="http://root:8003",
            tier=MarketplaceTier.ROOT,
            status=MarketplaceStatus.HEALTHY,
            priority=10,
        )
        extended_mp = MarketplaceInstance(
            marketplace_id="extended-mp",
            name="Backoffice Skills",
            endpoint="http://extended:8003",
            tier=MarketplaceTier.EXTENDED,
            status=MarketplaceStatus.HEALTHY,
            priority=5,
        )
        registry._marketplaces["root-mp"] = root_mp
        registry._marketplaces["extended-mp"] = extended_mp
        return registry

    @pytest.mark.asyncio
    async def test_resolve_skill_extended_overrides_root(self, registry_with_marketplaces):
        """Test that extended marketplace skill overrides root."""
        root_skill = {"id": "code-writer", "name": "Root Writer"}
        extended_skill = {"id": "code-writer", "name": "Extended Writer"}

        async def mock_fetch(mp, skill_id):
            if mp.tier == MarketplaceTier.ROOT:
                return {**root_skill, "marketplace_id": mp.marketplace_id,
                        "marketplace_name": mp.name, "marketplace_tier": mp.tier.value}
            if mp.tier == MarketplaceTier.EXTENDED:
                return {**extended_skill, "marketplace_id": mp.marketplace_id,
                        "marketplace_name": mp.name, "marketplace_tier": mp.tier.value}
            return None

        with patch.object(registry_with_marketplaces, "_fetch_skill_from_marketplace",
                          side_effect=mock_fetch):
            result = await registry_with_marketplaces.resolve_skill("code-writer")

        assert result is not None
        assert result["name"] == "Extended Writer"
        assert result["marketplace_tier"] == "extended"

    @pytest.mark.asyncio
    async def test_resolve_skill_root_fallback(self, registry_with_marketplaces):
        """Test fallback to root when skill only exists in root."""
        async def mock_fetch(mp, skill_id):
            if mp.tier == MarketplaceTier.ROOT:
                return {"id": skill_id, "name": "Root Only",
                        "marketplace_id": mp.marketplace_id,
                        "marketplace_name": mp.name, "marketplace_tier": mp.tier.value}
            return None

        with patch.object(registry_with_marketplaces, "_fetch_skill_from_marketplace",
                          side_effect=mock_fetch):
            result = await registry_with_marketplaces.resolve_skill("root-only-skill")

        assert result is not None
        assert result["marketplace_tier"] == "root"

    @pytest.mark.asyncio
    async def test_resolve_skill_not_found(self, registry_with_marketplaces):
        """Test resolve returns None when no marketplace has the skill."""
        async def mock_fetch(mp, skill_id):
            return None

        with patch.object(registry_with_marketplaces, "_fetch_skill_from_marketplace",
                          side_effect=mock_fetch):
            result = await registry_with_marketplaces.resolve_skill("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_skills_bulk(self, registry_with_marketplaces):
        """Test bulk resolution across marketplaces."""
        async def mock_fetch(mp, skill_id):
            if skill_id == "s1" and mp.tier == MarketplaceTier.EXTENDED:
                return {"id": "s1", "name": "Extended S1", "marketplace_tier": "extended",
                        "marketplace_id": mp.marketplace_id, "marketplace_name": mp.name}
            if skill_id == "s2" and mp.tier == MarketplaceTier.ROOT:
                return {"id": "s2", "name": "Root S2", "marketplace_tier": "root",
                        "marketplace_id": mp.marketplace_id, "marketplace_name": mp.name}
            return None

        with patch.object(registry_with_marketplaces, "_fetch_skill_from_marketplace",
                          side_effect=mock_fetch):
            result = await registry_with_marketplaces.resolve_skills(["s1", "s2"])

        assert result["s1"]["name"] == "Extended S1"
        assert result["s2"]["name"] == "Root S2"

    @pytest.mark.asyncio
    async def test_resolve_skill_no_marketplaces(self, mock_storage, mock_cache):
        """Test resolve returns None when no marketplaces are registered."""
        registry = MarketplaceRegistry(
            storage_backend=mock_storage, cache_backend=mock_cache
        )
        result = await registry.resolve_skill("any-skill")
        assert result is None

    def test_get_marketplaces_by_tier(self, registry_with_marketplaces):
        """Test filtering marketplaces by tier."""
        root_mps = registry_with_marketplaces.get_marketplaces_by_tier(MarketplaceTier.ROOT)
        assert len(root_mps) == 1
        assert root_mps[0].marketplace_id == "root-mp"

        extended_mps = registry_with_marketplaces.get_marketplaces_by_tier(MarketplaceTier.EXTENDED)
        assert len(extended_mps) == 1
        assert extended_mps[0].marketplace_id == "extended-mp"
