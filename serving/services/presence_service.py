"""Presence service — tracks which users are online across all projects."""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from models.presence import UserPresence

logger = logging.getLogger(__name__)

# Redis TTL for a presence key (seconds).  Users are removed after 3 days of
# inactivity (no heartbeat).
PRESENCE_TTL = 3 * 24 * 60 * 60  # 259 200 s  (3 days)

# Status thresholds (seconds since last heartbeat)
ONLINE_THRESHOLD = 60       # green:  active within last 60 s
IDLE_THRESHOLD = 10 * 60    # yellow: 1–10 minutes since last heartbeat
# > IDLE_THRESHOLD → red (offline), retained until PRESENCE_TTL expires


class PresenceService:
    """Manages global user presence in Redis.

    Key format: ``{prefix}presence:user:{user_id}``

    Each key is a Redis hash with fields:
        user_id, project_id, project_name, display_name, current_view,
        connected_at, last_heartbeat

    The key expires after PRESENCE_TTL (3 days) — the frontend must send
    heartbeats at least every 30 s to keep the entry fresh.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prefix(self) -> str:
        return getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'

    def _user_key(self, user_id: str) -> str:
        return f"{self._prefix()}presence:user:{user_id}"

    def _all_users_pattern(self) -> str:
        return f"{self._prefix()}presence:user:*"

    # Legacy per-project helpers (for backward compat during migration)
    def _key(self, project_id: str, user_id: str) -> str:
        return self._user_key(user_id)

    def _pattern(self, project_id: str) -> str:
        return self._all_users_pattern()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def heartbeat(
        self,
        project_id: str,
        user_id: str,
        display_name: str,
        current_view: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> None:
        """Record or refresh a user's global presence.

        Stores the user's current project and view so teammates can see
        what they're working on.  The Redis key expires after PRESENCE_TTL
        (3 days).  After updating, broadcasts a ``presence_update`` event.
        """
        if not self._redis:
            return

        key = self._user_key(user_id)
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
                "project_id": project_id or "",
                "project_name": project_name or "",
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

        # Broadcast after successful write (global — no project filter)
        await self._broadcast_update(project_id)

    async def get_active_users(self, project_id: Optional[str] = None) -> list[UserPresence]:
        """Return all globally tracked users.

        If *project_id* is given the list is filtered to users whose last
        heartbeat was for that project.  Pass ``None`` to get everyone.

        Status is derived from time since last heartbeat:
        - ``online``  — within the last 60 s  (green)
        - ``idle``    — 1–10 minutes ago       (yellow)
        - ``offline`` — >10 minutes ago        (red, retained up to 3 days)
        """
        if not self._redis:
            return []

        try:
            raw = self._redis._redis
            pattern = self._all_users_pattern()
            keys = await raw.keys(pattern)
        except Exception as e:
            logger.warning(f"Failed to list presence keys: {e}")
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
                if age < ONLINE_THRESHOLD:
                    status = "online"
                elif age < IDLE_THRESHOLD:
                    status = "idle"
                else:
                    status = "offline"

                user_project = decoded.get("project_id", "")

                # Optional project filter
                if project_id and user_project != project_id:
                    continue

                connected_at_str = decoded.get("connected_at", "")
                try:
                    connected_at = datetime.fromisoformat(connected_at_str)
                    if connected_at.tzinfo is None:
                        connected_at = connected_at.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    connected_at = now

                presence = UserPresence(
                    user_id=decoded.get("user_id", ""),
                    project_id=user_project,
                    project_name=decoded.get("project_name") or None,
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

    async def _broadcast_update(self, project_id: Optional[str] = None) -> None:
        """Push a presence_update event to all WebSocket clients.

        Broadcasts the full global user list so every client can update its
        team panel regardless of which project it is viewing.
        """
        try:
            users = await self.get_active_users()  # global — no filter
            from services.observability_event_bus import get_event_bus
            bus = get_event_bus()
            if not bus:
                return

            payload = json.dumps(
                {
                    "type": "presence_update",
                    "event": {
                        "project_id": project_id or "",
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
