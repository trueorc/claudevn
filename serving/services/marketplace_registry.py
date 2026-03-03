"""Marketplace registry service."""

import asyncio
import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from collections import defaultdict

import httpx

from models.marketplace import (
    MarketplaceInstance,
    MarketplaceStatus,
    MarketplaceTier,
    AggregatedMarketplaceStats,
)
from storage.registry_storage import RegistryStorage
from storage.cache_backend import CacheBackend, get_cache_backend

logger = logging.getLogger(__name__)

# Tier priority: more specific (user) wins over more general (root)
# Higher tier = more specific = wins on conflict
TIER_PRIORITY = {
    MarketplaceTier.USER: 0,      # Highest priority (most specific)
    MarketplaceTier.PROJECT: 1,
    MarketplaceTier.TEAM: 2,
    MarketplaceTier.ENTERPRISE: 3,
    MarketplaceTier.ROOT: 4,      # Lowest priority (most general)
}


class MarketplaceRegistry:
    """Registry for managing marketplace instances.
    
    This service maintains the registry of all marketplaces,
    tracks their status, and provides discovery capabilities.
    """
    
    def __init__(
        self,
        storage_backend: Optional[RegistryStorage] = None,
        cache_backend: Optional[CacheBackend] = None,
        startup_stale_threshold: int = 120
    ):
        """Initialize the registry.

        Args:
            storage_backend: Optional storage backend for persistence
            cache_backend: Optional cache backend for marketplace data
            startup_stale_threshold: Seconds since last heartbeat before a
                persisted marketplace is considered stale on startup and
                skipped. Active marketplaces will re-register themselves.
        """
        self._marketplaces: Dict[str, MarketplaceInstance] = {}
        self._storage = storage_backend
        self._cache = cache_backend or get_cache_backend()
        self._startup_stale_threshold = startup_stale_threshold

        logger.info("Initialized MarketplaceRegistry")
    
    async def initialize(self):
        """Initialize registry and load from storage if available."""
        if self._storage:
            await self._load_from_storage()
    
    async def _load_from_storage(self):
        """Load marketplaces from storage backend.

        Filters out stale entries from previous sessions. Active marketplaces
        will re-register themselves, so persisted entries with old heartbeats
        are safely discarded.
        """
        try:
            if not self._storage:
                return

            # Load from marketplaces subdirectory
            marketplaces_data = await self._storage.load_all_instances("marketplaces")
            now = datetime.now(timezone.utc)
            loaded = 0
            stale = 0

            for marketplace_id, marketplace_data in marketplaces_data.items():
                try:
                    # Create MarketplaceInstance from stored data
                    marketplace = MarketplaceInstance(**marketplace_data)

                    # Skip stale entries from previous sessions
                    time_since_heartbeat = (now - marketplace.last_heartbeat).total_seconds()
                    if time_since_heartbeat > self._startup_stale_threshold:
                        logger.info(
                            f"Skipping stale marketplace {marketplace_id} "
                            f"(last heartbeat {time_since_heartbeat:.0f}s ago)"
                        )
                        await self._storage.delete_marketplace(marketplace_id)
                        stale += 1
                        continue

                    self._marketplaces[marketplace_id] = marketplace
                    loaded += 1

                except Exception as e:
                    logger.error(f"Failed to load marketplace {marketplace_id}: {e}")
                    continue

            logger.info(
                f"Loaded {loaded} marketplaces from storage"
                + (f" (skipped {stale} stale)" if stale else "")
            )

        except Exception as e:
            logger.error(f"Failed to load marketplaces from storage: {e}")
    
    async def _save_to_storage(self, marketplace: MarketplaceInstance):
        """Save marketplace to storage backend.
        
        Args:
            marketplace: Marketplace to save
        """
        try:
            if self._storage:
                marketplace_dict = marketplace.model_dump()
                await self._storage.save_marketplace(marketplace.marketplace_id, marketplace_dict)
                logger.debug(f"Saved marketplace {marketplace.marketplace_id} to storage")
        except Exception as e:
            logger.error(f"Failed to save marketplace to storage: {e}")
    
    async def add_marketplace(self, marketplace: MarketplaceInstance) -> MarketplaceInstance:
        """Register a new marketplace.
        
        Args:
            marketplace: Marketplace instance to register
            
        Returns:
            Registered marketplace instance
            
        Raises:
            ValueError: If marketplace_id already exists
        """
        marketplace_id = marketplace.marketplace_id
        
        # Check if already registered
        if marketplace_id in self._marketplaces:
            raise ValueError(f"Marketplace {marketplace_id} is already registered")
        
        # Set registration timestamp
        marketplace.registered_at = datetime.now(timezone.utc)
        marketplace.last_heartbeat = datetime.now(timezone.utc)
        marketplace.status = MarketplaceStatus.HEALTHY
        marketplace.failed_health_checks = 0
        
        # Store marketplace
        self._marketplaces[marketplace_id] = marketplace
        
        # Persist to storage
        await self._save_to_storage(marketplace)
        
        logger.info(
            f"Registered marketplace {marketplace_id} ({marketplace.name}) "
            f"with {marketplace.capabilities.agent_count} agents"
        )
        
        return marketplace
    
    async def remove_marketplace(self, marketplace_id: str) -> bool:
        """Deregister a marketplace.
        
        Args:
            marketplace_id: ID of marketplace to remove
            
        Returns:
            True if removed, False if not found
        """
        if marketplace_id not in self._marketplaces:
            return False
        
        # Remove from registry
        del self._marketplaces[marketplace_id]
        
        # Remove from storage
        if self._storage:
            await self._storage.delete_marketplace(marketplace_id)
        
        logger.info(f"Deregistered marketplace {marketplace_id}")
        
        return True
    
    async def get_marketplace(self, marketplace_id: str) -> Optional[MarketplaceInstance]:
        """Get a marketplace by ID.
        
        Args:
            marketplace_id: Marketplace ID
            
        Returns:
            Marketplace instance or None if not found
        """
        return self._marketplaces.get(marketplace_id)
    
    async def list_marketplaces(
        self,
        status: Optional[MarketplaceStatus] = None,
        limit: int = 100
    ) -> List[MarketplaceInstance]:
        """List registered marketplaces.
        
        Args:
            status: Optional status filter
            limit: Maximum number of marketplaces to return
            
        Returns:
            List of marketplaces (sorted by priority, then registration time)
        """
        marketplaces = list(self._marketplaces.values())
        
        # Filter by status if specified
        if status:
            marketplaces = [m for m in marketplaces if m.status == status]
        
        # Sort by priority (lower = higher priority) then registration time
        marketplaces.sort(key=lambda m: (m.priority, m.registered_at))
        
        # Apply limit
        return marketplaces[:limit]
    
    async def update_marketplace(
        self,
        marketplace_id: str,
        **updates
    ) -> Optional[MarketplaceInstance]:
        """Update marketplace information.
        
        Args:
            marketplace_id: Marketplace ID
            **updates: Fields to update
            
        Returns:
            Updated marketplace or None if not found
        """
        marketplace = self._marketplaces.get(marketplace_id)
        if not marketplace:
            return None
        
        # Update fields
        for key, value in updates.items():
            if value is not None and hasattr(marketplace, key):
                setattr(marketplace, key, value)
        
        # Persist changes
        await self._save_to_storage(marketplace)
        
        logger.info(f"Updated marketplace {marketplace_id}: {list(updates.keys())}")
        
        return marketplace
    
    async def update_heartbeat(
        self,
        marketplace_id: str,
        metadata: Optional[Dict] = None
    ) -> bool:
        """Update marketplace heartbeat.
        
        Args:
            marketplace_id: Marketplace ID
            metadata: Optional updated metadata (agent_count, tool_count, etc.)
            
        Returns:
            True if successful, False if marketplace not found
        """
        marketplace = self._marketplaces.get(marketplace_id)
        if not marketplace:
            return False
        
        # Update heartbeat timestamp
        marketplace.last_heartbeat = datetime.now(timezone.utc)
        
        # Reset failed health checks on successful heartbeat
        if marketplace.failed_health_checks > 0:
            marketplace.failed_health_checks = 0
            logger.info(f"Marketplace {marketplace_id} recovered (failed checks reset)")
        
        # Update status to healthy if it was degraded/offline
        if marketplace.status != MarketplaceStatus.HEALTHY:
            old_status = marketplace.status
            marketplace.status = MarketplaceStatus.HEALTHY
            logger.info(f"Marketplace {marketplace_id} status changed: {old_status} -> healthy")
        
        # Update metadata if provided
        if metadata:
            if "agent_count" in metadata:
                marketplace.capabilities.agent_count = metadata["agent_count"]
            if "tool_count" in metadata:
                marketplace.capabilities.tool_count = metadata["tool_count"]
            if "skill_count" in metadata:
                marketplace.capabilities.skill_count = metadata["skill_count"]
            if "status" in metadata and metadata["status"] in [s.value for s in MarketplaceStatus]:
                marketplace.status = MarketplaceStatus(metadata["status"])
            if "metadata" in metadata:
                marketplace.metadata.update(metadata["metadata"])
        
        # Persist changes
        await self._save_to_storage(marketplace)
        
        logger.debug(f"Updated heartbeat for marketplace {marketplace_id}")
        
        return True
    
    async def check_health(
        self,
        degraded_threshold: int = 90,
        offline_threshold: int = 180,
        max_failed_checks: int = 3
    ) -> Dict[str, int]:
        """Check health of all marketplaces.
        
        Args:
            degraded_threshold: Seconds without heartbeat before marking degraded
            offline_threshold: Seconds without heartbeat before marking offline
            max_failed_checks: Maximum failed checks before auto-deregistration
            
        Returns:
            Dictionary with counts of status changes
        """
        now = datetime.now(timezone.utc)
        changes = {
            "degraded": 0,
            "offline": 0,
            "deregistered": 0
        }
        
        to_remove = []
        
        for marketplace_id, marketplace in self._marketplaces.items():
            time_since_heartbeat = (now - marketplace.last_heartbeat).total_seconds()
            old_status = marketplace.status
            
            # Determine new status
            if time_since_heartbeat >= offline_threshold:
                marketplace.status = MarketplaceStatus.OFFLINE
                marketplace.failed_health_checks += 1
                
                # Auto-deregister if too many failures
                if marketplace.failed_health_checks >= max_failed_checks:
                    logger.warning(
                        f"Marketplace {marketplace_id} exceeded max failed checks, "
                        "marking for deregistration"
                    )
                    to_remove.append(marketplace_id)
                    changes["deregistered"] += 1
                    continue
                
            elif time_since_heartbeat >= degraded_threshold:
                marketplace.status = MarketplaceStatus.DEGRADED
            else:
                marketplace.status = MarketplaceStatus.HEALTHY
            
            # Log status changes
            if old_status != marketplace.status:
                logger.warning(
                    f"Marketplace {marketplace_id} status changed: "
                    f"{old_status} -> {marketplace.status} "
                    f"(last heartbeat: {time_since_heartbeat:.0f}s ago)"
                )
                
                if marketplace.status == MarketplaceStatus.DEGRADED:
                    changes["degraded"] += 1
                elif marketplace.status == MarketplaceStatus.OFFLINE:
                    changes["offline"] += 1
            
            # Save updated status
            await self._save_to_storage(marketplace)
        
        # Remove marketplaces that exceeded max failures
        for marketplace_id in to_remove:
            await self.remove_marketplace(marketplace_id)
        
        return changes
    
    def get_stats(self) -> Dict:
        """Get registry statistics.
        
        Returns:
            Dictionary with marketplace counts by status
        """
        total = len(self._marketplaces)
        by_status = defaultdict(int)
        
        total_agents = 0
        total_tools = 0
        
        for marketplace in self._marketplaces.values():
            by_status[marketplace.status.value] += 1
            total_agents += marketplace.capabilities.agent_count
            total_tools += marketplace.capabilities.tool_count
        
        return {
            "total_marketplaces": total,
            "healthy": by_status.get("healthy", 0),
            "degraded": by_status.get("degraded", 0),
            "offline": by_status.get("offline", 0),
            "total_agents": total_agents,
            "total_tools": total_tools,
            "by_status": dict(by_status)
        }
    
    async def get_aggregated_stats(self) -> AggregatedMarketplaceStats:
        """Get aggregated statistics across all marketplaces.
        
        Returns:
            Aggregated statistics
        """
        stats = self.get_stats()
        
        return AggregatedMarketplaceStats(
            total_marketplaces=stats["total_marketplaces"],
            healthy_marketplaces=stats["healthy"],
            degraded_marketplaces=stats["degraded"],
            offline_marketplaces=stats["offline"],
            total_agents=stats["total_agents"],
            total_tools=stats["total_tools"],
            by_status=stats["by_status"]
        )
    
    async def get_marketplace_for_query(
        self,
        preferred_marketplace_id: Optional[str] = None
    ) -> Optional[MarketplaceInstance]:
        """Get the best marketplace for an agent query.

        Uses priority and health status to select marketplace.

        Args:
            preferred_marketplace_id: Optional preferred marketplace ID

        Returns:
            Selected marketplace or None if none available
        """
        # If preferred marketplace specified and healthy, use it
        if preferred_marketplace_id:
            marketplace = self._marketplaces.get(preferred_marketplace_id)
            if marketplace and marketplace.status == MarketplaceStatus.HEALTHY:
                return marketplace

        # Get all healthy marketplaces sorted by priority
        healthy = await self.list_marketplaces(status=MarketplaceStatus.HEALTHY)

        if healthy:
            return healthy[0]  # Return highest priority

        # Fallback to degraded if no healthy marketplaces
        degraded = await self.list_marketplaces(status=MarketplaceStatus.DEGRADED)
        if degraded:
            logger.warning("No healthy marketplaces, using degraded marketplace")
            return degraded[0]

        return None

    async def _fetch_skill_from_marketplace(
        self, marketplace: MarketplaceInstance, skill_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch a skill from a specific marketplace.

        Args:
            marketplace: Marketplace instance to query
            skill_id: Skill ID to fetch

        Returns:
            Skill data dict with marketplace metadata, or None if not found
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{marketplace.endpoint}/api/v1/skills/{skill_id}",
                    timeout=10.0,
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                skill = response.json()
                # Enrich with marketplace source metadata
                skill["marketplace_id"] = marketplace.marketplace_id
                skill["marketplace_name"] = marketplace.name
                skill["marketplace_tier"] = marketplace.tier.value
                return skill
        except httpx.HTTPStatusError:
            return None
        except Exception as e:
            logger.warning(
                f"Failed to fetch skill '{skill_id}' from "
                f"{marketplace.marketplace_id}: {e}"
            )
            return None

    async def resolve_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Resolve a skill across all marketplaces using tier-based priority.

        Queries all healthy marketplaces concurrently for the given skill ID.
        When the same skill exists in multiple marketplaces, the most specific
        tier wins: USER > PROJECT > TEAM > ENTERPRISE > ROOT.

        Args:
            skill_id: Skill ID to resolve

        Returns:
            Skill data from the highest-priority tier, or None if not found
        """
        marketplaces = await self.list_marketplaces(status=MarketplaceStatus.HEALTHY)
        if not marketplaces:
            # Try degraded
            marketplaces = await self.list_marketplaces(status=MarketplaceStatus.DEGRADED)
        if not marketplaces:
            return None

        # Fetch from all marketplaces concurrently
        tasks = [
            self._fetch_skill_from_marketplace(mp, skill_id)
            for mp in marketplaces
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Select by tier priority (most specific wins)
        best: Optional[Dict[str, Any]] = None
        best_priority = 999

        for result in results:
            if isinstance(result, Exception) or result is None:
                continue
            tier_str = result.get("marketplace_tier", "root")
            try:
                tier = MarketplaceTier(tier_str)
            except ValueError:
                tier = MarketplaceTier.ROOT
            priority = TIER_PRIORITY.get(tier, 4)
            if priority < best_priority:
                best = result
                best_priority = priority

        return best

    async def resolve_skills(
        self, skill_ids: List[str]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Resolve multiple skills across all marketplaces.

        Queries all healthy marketplaces for each skill ID, applying
        tier-based override semantics.

        Args:
            skill_ids: List of skill IDs to resolve

        Returns:
            Dict mapping skill_id to resolved skill data (or None if not found)
        """
        if not skill_ids:
            return {}

        # Resolve each skill concurrently
        tasks = [self.resolve_skill(sid) for sid in skill_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        resolved = {}
        for skill_id, result in zip(skill_ids, results):
            if isinstance(result, Exception):
                logger.warning(f"Error resolving skill '{skill_id}': {result}")
                resolved[skill_id] = None
            else:
                resolved[skill_id] = result

        return resolved

    def get_marketplaces_by_tier(
        self, tier: MarketplaceTier
    ) -> List[MarketplaceInstance]:
        """Get all marketplaces at a specific tier.

        Args:
            tier: Marketplace tier to filter by

        Returns:
            List of marketplaces at the given tier, sorted by priority
        """
        return sorted(
            [m for m in self._marketplaces.values() if m.tier == tier],
            key=lambda m: (m.priority, m.registered_at),
        )


# Global registry instance
_marketplace_registry: Optional[MarketplaceRegistry] = None


def set_marketplace_registry(registry: MarketplaceRegistry):
    """Set the global marketplace registry instance."""
    global _marketplace_registry
    _marketplace_registry = registry


def get_marketplace_registry() -> MarketplaceRegistry:
    """Get the global marketplace registry instance."""
    if _marketplace_registry is None:
        raise RuntimeError("Marketplace registry not initialized")
    return _marketplace_registry

