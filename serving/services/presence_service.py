"""Presence service — tracks which users are online in which project view."""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from models.presence import UserPresence

logger = logging.getLogger(__name__)

# Redis TTL for a presence key (seconds). After this the user is considered offline.
PRESENCE_TTL = 60
# Boundary between "online" and "idle" (seconds since last heartbeat)
IDLE_THRESHOLD = 30


class PresenceService:
    """Manages per-project user presence in Redis.

    Key format: ``{prefix}presence:{project_id}:{user_id}``

    Each key is a Redis hash with fields:
        user_id, project_id, display_name, current_view, connected_at, last_heartbeat

    The key expires after PRESENCE_TTL seconds — the frontend must send
    heartbeats at least every 30 s to keep the entry alive.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prefix(self) -> str:
        return getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'

    def _key(self, project_id: str, user_id: str) -> str:
        return f"{self._prefix()}presence:{project_id}:{user_id}"

    def _pattern(self, project_id: str) -> str:
        return f"{self._prefix()}presence:{project_id}:*"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def heartbeat(
        self,
        project_id: str,
        user_id: str,
        display_name: str,
        current_view: Optional[str] = None,
    ) -> None:
        """Record or refresh a user's presence for *project_id*.

        Sets the Redis hash fields and refreshes the TTL to PRESENCE_TTL seconds.
        After updating, broadcasts a ``presence_update`` event via the event bus.
        """
        if not self._redis:
            return

        key = self._key(project_id, user_id)
        now = datetime.now(timezone.utc).isoformat()

        try:
            raw = self._redis._redis
            # Read existing connected_at so we don't reset it on refresh
            existing_connected_at = await raw.hget(key, "connected_at")
            connected_at = (
                existing_connected_at.decode() if existing_connected_at else now
            )

            mapping = {
                "user_id": user_id,
                "project_id": project_id,
                "display_name": display_name,
                "current_view": current_view or "",
                "last_heartbeat": now,
                "connected_at": connected_at,
            }
            await raw.hset(key, mapping=mapping)
            await raw.expire(key, PRESENCE_TTL)
        except Exception as e:
            logger.warning(f"Presence heartbeat failed for {user_id}: {e}")
            return

        # Broadcast after successful write
        await self._broadcast_update(project_id)

    async def get_active_users(self, project_id: str) -> list[UserPresence]:
        """Return all users currently present in *project_id*.

        Status is derived from time since last heartbeat:
        - ``online`` — last heartbeat < IDLE_THRESHOLD seconds ago
        - ``idle`` — last heartbeat IDLE_THRESHOLD..PRESENCE_TTL seconds ago
        """
        if not self._redis:
            return []

        try:
            raw = self._redis._redis
            pattern = self._pattern(project_id)
            keys = await raw.keys(pattern)
        except Exception as e:
            logger.warning(f"Failed to list presence keys for {project_id}: {e}")
            return []

        users: list[UserPresence] = []
        now = datetime.now(timezone.utc)

        for key in keys:
            try:
                data = await raw.hgetall(key)
                if not data:
                    continue

                # Decode bytes keys/values
                decoded = {
                    (k.decode() if isinstance(k, bytes) else k): (
                        v.decode() if isinstance(v, bytes) else v
                    )
                    for k, v in data.items()
                }

                last_hb_str = decoded.get("last_heartbeat", "")
                try:
                    last_hb = datetime.fromisoformat(last_hb_str)
                    if last_hb.tzinfo is None:
                        last_hb = last_hb.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    last_hb = now

                age = (now - last_hb).total_seconds()
                if age < IDLE_THRESHOLD:
                    status = "online"
                else:
                    status = "idle"

                connected_at_str = decoded.get("connected_at", "")
                try:
                    connected_at = datetime.fromisoformat(connected_at_str)
                    if connected_at.tzinfo is None:
                        connected_at = connected_at.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    connected_at = now

                presence = UserPresence(
                    user_id=decoded.get("user_id", ""),
                    project_id=decoded.get("project_id", project_id),
                    display_name=decoded.get("display_name", "Unknown"),
                    status=status,
                    current_view=decoded.get("current_view") or None,
                    last_heartbeat=last_hb,
                    connected_at=connected_at,
                )
                users.append(presence)
            except Exception as e:
                logger.debug(f"Failed to parse presence key {key}: {e}")

        return users

    # ------------------------------------------------------------------
    # Internal broadcast
    # ------------------------------------------------------------------

    async def _broadcast_update(self, project_id: str) -> None:
        """Push a presence_update event to all WebSocket clients."""
        try:
            users = await self.get_active_users(project_id)
            from services.observability_event_bus import get_event_bus
            bus = get_event_bus()
            if not bus:
                return

            payload = json.dumps(
                {
                    "type": "presence_update",
                    "event": {
                        "project_id": project_id,
                        "users": [u.model_dump(mode="json") for u in users],
                    },
                },
                default=str,
            )
            await bus._broadcast_raw(payload)
        except Exception as e:
            logger.debug(f"Presence broadcast failed: {e}")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_presence_service: Optional[PresenceService] = None


def get_presence_service() -> Optional[PresenceService]:
    """Return the global PresenceService instance."""
    return _presence_service


def set_presence_service(service: Optional[PresenceService]) -> None:
    """Set the global PresenceService instance."""
    global _presence_service
    _presence_service = service
