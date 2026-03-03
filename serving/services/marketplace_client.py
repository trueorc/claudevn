"""HTTP client for Marketplace service with caching and fallback support."""

import asyncio
import httpx
import logging
import time
import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import yaml

logger = logging.getLogger(__name__)

# Tier priority: more specific wins (lower value = higher priority)
_TIER_PRIORITY = {"user": 0, "project": 1, "team": 2, "enterprise": 3, "root": 4}


class MarketplaceClient:
    """Client for interacting with the Marketplace service.

    Features:
    - API key authentication support
    - In-memory caching with configurable TTL
    - Offline fallback with bundled default personas
    - Multi-marketplace support with tier-based skill resolution
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8003",
        api_key: Optional[str] = None,
        cache_ttl: int = 300,
        fallback_personas_path: Optional[str] = None,
        additional_marketplaces: Optional[List[Dict[str, Any]]] = None,
    ):
        """Initialize the marketplace client.

        Args:
            base_url: Primary marketplace URL
            api_key: Optional API key for authentication
            cache_ttl: Cache TTL in seconds
            fallback_personas_path: Path to fallback persona YAML files
            additional_marketplaces: Optional list of additional marketplace configs,
                each with keys: url, tier (str), name (optional)
        """
        self.base_url = base_url.rstrip('/')
        self.api_prefix = "/api/v1"
        self.api_key = api_key
        self.cache_ttl = cache_ttl

        # Ordered list of (url, tier, name) for multi-marketplace resolution
        # Primary marketplace is included as ROOT by default
        self._marketplace_endpoints: List[Tuple[str, str, str]] = [
            (self.base_url, "root", "primary"),
        ]
        if additional_marketplaces:
            for mp in additional_marketplaces:
                url = mp.get("url", "").rstrip("/")
                tier = mp.get("tier", "user")
                name = mp.get("name", url)
                if url:
                    self._marketplace_endpoints.append((url, tier, name))

        # Cache storage: {key: (data, expiry_time)}
        self._cache: Dict[str, tuple] = {}

        # Load fallback personas
        self._fallback_personas: Dict[str, Dict[str, Any]] = {}
        if fallback_personas_path is None:
            # Default path relative to this file
            fallback_personas_path = Path(__file__).parent.parent / "fallback_personas"
        self._load_fallback_personas(Path(fallback_personas_path))

    def _load_fallback_personas(self, path: Path) -> None:
        """Load fallback persona definitions from YAML files."""
        if not path.exists():
            logger.warning(f"Fallback personas directory not found: {path}")
            return

        for yaml_file in path.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    persona_data = yaml.safe_load(f)
                    if persona_data and 'id' in persona_data:
                        self._fallback_personas[persona_data['id']] = persona_data
                        logger.debug(f"Loaded fallback persona: {persona_data['id']}")
            except Exception as e:
                logger.error(f"Failed to load fallback persona {yaml_file}: {e}")

        if self._fallback_personas:
            logger.info(f"Loaded {len(self._fallback_personas)} fallback personas")

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers including API key if configured."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key in self._cache:
            data, expiry = self._cache[key]
            if time.time() < expiry:
                return data
            # Expired, remove from cache
            del self._cache[key]
        return None

    def _set_cached(self, key: str, data: Any) -> None:
        """Set value in cache with TTL."""
        if self.cache_ttl > 0:
            expiry = time.time() + self.cache_ttl
            self._cache[key] = (data, expiry)

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        logger.debug("Marketplace client cache cleared")

    def _get_fallback_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Get a skill from fallback personas."""
        if skill_id in self._fallback_personas:
            persona = self._fallback_personas[skill_id].copy()
            persona["source"] = "fallback"
            persona["fallback_mode"] = True
            logger.warning(f"Using fallback persona for skill: {skill_id}")
            return persona
        return None

    def _get_fallback_skills_list(self) -> Dict[str, Any]:
        """Get list of all fallback skills."""
        skills = []
        for skill_id, skill_data in self._fallback_personas.items():
            skill = skill_data.copy()
            skill["source"] = "fallback"
            skill["fallback_mode"] = True
            skills.append(skill)

        logger.warning(f"Using fallback mode: returning {len(skills)} bundled personas")
        return {
            "skills": skills,
            "total": len(skills),
            "by_author": {"system": len(skills)},
            "source": "fallback",
            "fallback_mode": True
        }

    async def health_check(self) -> Dict[str, Any]:
        """Check marketplace health."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/health",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def list_skills(self, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """List skills from marketplace with caching and fallback support."""
        # Check cache first
        cache_key = f"list_skills:{','.join(tags) if tags else ''}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        params = {}
        if tags:
            params["tags"] = ",".join(tags)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}{self.api_prefix}/skills",
                    params=params,
                    headers=self._get_headers(),
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                self._set_cached(cache_key, data)
                return data
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"Marketplace unavailable for list_skills: {e}")
            return self._get_fallback_skills_list()

    async def get_skill(self, skill_id: str) -> Dict[str, Any]:
        """Get a specific skill with caching and fallback support."""
        # Check cache first
        cache_key = f"skill:{skill_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}{self.api_prefix}/skills/{skill_id}",
                    headers=self._get_headers(),
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                self._set_cached(cache_key, data)
                return data
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"Marketplace unavailable for get_skill({skill_id}): {e}")
            fallback = self._get_fallback_skill(skill_id)
            if fallback:
                return fallback
            raise httpx.HTTPStatusError(
                f"Skill '{skill_id}' not found in marketplace or fallback",
                request=None,
                response=None
            )

    async def compose_agent(
        self,
        task_id: str,
        task_description: str,
        required_capabilities: List[str],
        skill_ids: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Compose an agent from skills for a task."""
        payload = {
            "task": {
                "task_id": task_id,
                "description": task_description,
                "required_capabilities": required_capabilities
            }
        }
        if skill_ids:
            payload["skill_ids"] = skill_ids
        if context:
            payload["context"] = context

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{self.api_prefix}/skills/compose",
                json=payload,
                headers=self._get_headers(),
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    async def _fetch_skill_from_endpoint(
        self, url: str, tier: str, name: str, skill_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch a skill from a specific marketplace endpoint.

        Args:
            url: Marketplace base URL
            tier: Marketplace tier string
            name: Marketplace name
            skill_id: Skill ID to fetch

        Returns:
            Skill data enriched with marketplace metadata, or None if not found
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{url}{self.api_prefix}/skills/{skill_id}",
                    headers=self._get_headers(),
                    timeout=10.0,
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                data = response.json()
                data["marketplace_tier"] = tier
                data["marketplace_name"] = name
                data["marketplace_url"] = url
                return data
        except httpx.HTTPStatusError:
            return None
        except Exception as e:
            logger.debug(f"Failed to fetch skill '{skill_id}' from {name} ({url}): {e}")
            return None

    async def resolve_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Resolve a skill across all configured marketplaces with tier-based priority.

        Queries all marketplace endpoints concurrently. When the same skill
        exists in multiple marketplaces, the most specific tier wins:
        USER > PROJECT > TEAM > ENTERPRISE > ROOT.

        Args:
            skill_id: Skill ID to resolve

        Returns:
            Skill data from the highest-priority (most specific) tier, or None
        """
        # Check cache first
        cache_key = f"resolved_skill:{skill_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # If only one marketplace, just use get_skill directly
        if len(self._marketplace_endpoints) <= 1:
            try:
                skill = await self.get_skill(skill_id)
                return skill
            except Exception:
                return None

        # Query all marketplaces concurrently
        tasks = [
            self._fetch_skill_from_endpoint(url, tier, name, skill_id)
            for url, tier, name in self._marketplace_endpoints
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Select by tier priority (most specific wins)
        best: Optional[Dict[str, Any]] = None
        best_priority = 999

        for result in results:
            if isinstance(result, Exception) or result is None:
                continue
            tier_str = result.get("marketplace_tier", "root")
            priority = _TIER_PRIORITY.get(tier_str, 4)
            if priority < best_priority:
                best = result
                best_priority = priority

        if best is not None:
            self._set_cached(cache_key, best)

        return best

    async def resolve_skills(
        self, skill_ids: List[str]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Resolve multiple skills across all configured marketplaces.

        Each skill is resolved independently with tier-based priority.

        Args:
            skill_ids: List of skill IDs to resolve

        Returns:
            Dict mapping skill_id to resolved skill data (or None if not found)
        """
        if not skill_ids:
            return {}

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

    async def get_stats(self) -> Dict[str, Any]:
        """Get marketplace statistics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/skills/stats",
                headers=self._get_headers(),
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()

    async def update_skill(self, skill_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a skill in the marketplace.

        Args:
            skill_id: ID of the skill to update
            update_data: Dictionary of fields to update

        Returns:
            Updated skill data
        """
        # Invalidate cache for this skill and list
        cache_key = f"skill:{skill_id}"
        if cache_key in self._cache:
            del self._cache[cache_key]
        # Clear list caches
        keys_to_remove = [k for k in self._cache if k.startswith("list_skills:")]
        for k in keys_to_remove:
            del self._cache[k]

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.base_url}{self.api_prefix}/skills/{skill_id}",
                json=update_data,
                headers=self._get_headers(),
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()

    async def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill from the marketplace.

        Args:
            skill_id: ID of the skill to delete

        Returns:
            True if deleted successfully
        """
        # Invalidate cache
        cache_key = f"skill:{skill_id}"
        if cache_key in self._cache:
            del self._cache[cache_key]
        keys_to_remove = [k for k in self._cache if k.startswith("list_skills:")]
        for k in keys_to_remove:
            del self._cache[k]

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}{self.api_prefix}/skills/{skill_id}",
                headers=self._get_headers(),
                timeout=10.0
            )
            response.raise_for_status()
            return True

    async def create_skill(self, skill_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new skill in the marketplace.

        Args:
            skill_data: Skill data to create

        Returns:
            Created skill data
        """
        # Clear list caches
        keys_to_remove = [k for k in self._cache if k.startswith("list_skills:")]
        for k in keys_to_remove:
            del self._cache[k]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{self.api_prefix}/skills",
                json=skill_data,
                headers=self._get_headers(),
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()


# Global instance
_marketplace_client: Optional[MarketplaceClient] = None


def get_marketplace_client() -> MarketplaceClient:
    """Get the global marketplace client instance."""
    global _marketplace_client
    if _marketplace_client is None:
        from config import get_config
        config = get_config()
        _marketplace_client = MarketplaceClient(
            base_url=config.marketplace.url,
            api_key=config.marketplace.api_key,
            cache_ttl=config.marketplace.cache_ttl
        )
    return _marketplace_client


def set_marketplace_client(client: MarketplaceClient) -> None:
    """Set the global marketplace client instance."""
    global _marketplace_client
    _marketplace_client = client
