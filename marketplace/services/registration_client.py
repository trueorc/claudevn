"""Client for registering marketplace with Serving component."""

import asyncio
import logging
from typing import Optional
import httpx
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class MarketplaceRegistrationClient:
    """Client for managing marketplace registration with Serving component."""

    def __init__(
        self,
        serving_url: str,
        marketplace_id: str,
        marketplace_name: str,
        endpoint: str,
        version: str = "1.0.0",
        heartbeat_interval: int = 60,
        tier: str = "root",
    ):
        """Initialize registration client.

        Args:
            serving_url: Base URL of serving component
            marketplace_id: Unique identifier for this marketplace
            marketplace_name: Human-readable name
            endpoint: This marketplace's API endpoint
            version: Marketplace version
            heartbeat_interval: Heartbeat interval in seconds
            tier: Marketplace tier (root, enterprise, team, project, user)
        """
        self.serving_url = serving_url.rstrip('/')
        self.marketplace_id = marketplace_id
        self.marketplace_name = marketplace_name
        self.endpoint = endpoint
        self.version = version
        self.heartbeat_interval = heartbeat_interval
        self.tier = tier
        self.is_registered = False
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.heartbeat_endpoint: Optional[str] = None

        # Capability counts (updated dynamically)
        self.skill_count = 0
        self.persona_count = 0
        self.tool_count = 0

    def update_capabilities(self, skill_count: int = 0, persona_count: int = 0, tool_count: int = 0):
        """Update capability counts for heartbeat reporting."""
        self.skill_count = skill_count
        self.persona_count = persona_count
        self.tool_count = tool_count

    async def register(self) -> bool:
        """Register with serving component.

        Returns:
            True if registration successful, False otherwise
        """
        try:
            registration_data = {
                "marketplace_id": self.marketplace_id,
                "name": self.marketplace_name,
                "endpoint": self.endpoint,
                "version": self.version,
                "heartbeat_interval": self.heartbeat_interval,
                "tier": self.tier,
                "capabilities": {
                    "agent_count": self.skill_count + self.persona_count,
                    "tool_count": self.tool_count,
                    "supports_search": True,
                    "supports_categories": True,
                    "supports_access_control": False,
                    "supports_organizations": False,
                    "features": ["skills", "personas", "composition"]
                },
                "metadata": {
                    "skill_count": self.skill_count,
                    "persona_count": self.persona_count,
                }
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.serving_url}/api/v1/marketplaces/register",
                    json=registration_data
                )

                if response.status_code == 201:
                    result = response.json()
                    self.heartbeat_endpoint = result.get("heartbeat_endpoint")
                    self.heartbeat_interval = result.get("heartbeat_interval", self.heartbeat_interval)
                    self.is_registered = True

                    logger.info(
                        f"Successfully registered marketplace '{self.marketplace_name}' "
                        f"({self.marketplace_id}) with serving at {self.serving_url}"
                    )
                    logger.info(f"Heartbeat endpoint: {self.heartbeat_endpoint}")
                    logger.info(f"Heartbeat interval: {self.heartbeat_interval}s")

                    return True
                elif response.status_code == 400 and "already registered" in response.text.lower():
                    logger.warning(
                        f"Marketplace {self.marketplace_id} already registered. "
                        "Attempting to deregister and re-register..."
                    )

                    if await self.deregister(force=True):
                        logger.info("Successfully deregistered. Attempting re-registration...")
                        await asyncio.sleep(1)

                        response = await client.post(
                            f"{self.serving_url}/api/v1/marketplaces/register",
                            json=registration_data
                        )

                        if response.status_code == 201:
                            result = response.json()
                            self.heartbeat_endpoint = result.get("heartbeat_endpoint")
                            self.heartbeat_interval = result.get("heartbeat_interval", self.heartbeat_interval)
                            self.is_registered = True

                            logger.info(
                                f"Successfully re-registered marketplace '{self.marketplace_name}' "
                                f"with serving at {self.serving_url}"
                            )
                            return True
                        else:
                            logger.error(
                                f"Re-registration failed: {response.status_code} - {response.text}"
                            )
                            return False
                    else:
                        logger.error("Failed to deregister existing marketplace")
                        return False
                else:
                    logger.error(
                        f"Registration failed: {response.status_code} - {response.text}"
                    )
                    return False

        except httpx.ConnectError:
            logger.warning(
                f"Could not connect to serving component at {self.serving_url}. "
                "Marketplace will operate in standalone mode."
            )
            return False
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return False

    async def deregister(self, force: bool = False) -> bool:
        """Deregister from serving component.

        Args:
            force: If True, attempt deregistration even if not marked as registered locally

        Returns:
            True if deregistration successful, False otherwise
        """
        if not force and not self.is_registered:
            logger.debug("Not registered locally, skipping deregistration")
            return True

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.delete(
                    f"{self.serving_url}/api/v1/marketplaces/{self.marketplace_id}"
                )

                if response.status_code == 200:
                    logger.info("Successfully deregistered from serving component")
                    self.is_registered = False
                    return True
                elif response.status_code == 404:
                    logger.info("Marketplace not found on server (already deregistered)")
                    self.is_registered = False
                    return True
                else:
                    logger.error(f"Deregistration failed: {response.status_code} - {response.text}")
                    return False

        except httpx.ConnectError:
            logger.warning("Could not connect to serving component for deregistration")
            return False
        except Exception as e:
            logger.error(f"Deregistration error: {e}")
            return False

    async def send_heartbeat(self) -> bool:
        """Send heartbeat to serving component.

        Returns:
            True if heartbeat successful, False otherwise
        """
        if not self.is_registered or not self.heartbeat_endpoint:
            return False

        try:
            heartbeat_data = {
                "agent_count": self.skill_count + self.persona_count,
                "tool_count": self.tool_count,
                "status": "healthy",
                "metadata": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "skill_count": self.skill_count,
                    "persona_count": self.persona_count,
                }
            }

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self.serving_url}{self.heartbeat_endpoint}",
                    json=heartbeat_data
                )

                if response.status_code == 200:
                    logger.debug("Heartbeat sent successfully")
                    return True
                else:
                    logger.warning(f"Heartbeat failed: {response.status_code}")
                    return False

        except Exception as e:
            logger.warning(f"Heartbeat error: {e}")
            return False

    async def start_heartbeat(self):
        """Start periodic heartbeat task."""
        if self.heartbeat_task and not self.heartbeat_task.done():
            logger.warning("Heartbeat task already running")
            return

        logger.info(f"Starting heartbeat task (interval: {self.heartbeat_interval}s)")
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop_heartbeat(self):
        """Stop heartbeat task."""
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
            self.heartbeat_task = None
            logger.info("Heartbeat task stopped")

    async def _heartbeat_loop(self):
        """Periodic heartbeat loop."""
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                await self.send_heartbeat()
        except asyncio.CancelledError:
            logger.debug("Heartbeat loop cancelled")
        except Exception as e:
            logger.error(f"Heartbeat loop error: {e}")
