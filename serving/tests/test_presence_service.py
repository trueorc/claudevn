"""Tests for presence service — global tracking, thresholds, and status."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from serving.services.presence_service import (
    PresenceService,
    PRESENCE_TTL,
    ONLINE_THRESHOLD,
    IDLE_THRESHOLD,
)
from serving.models.presence import UserPresence


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_redis_mock(data=None):
    """Create a mock Redis client wrapping an inner raw mock."""
    raw = AsyncMock()
    raw.keys = AsyncMock(return_value=[])
    raw.hgetall = AsyncMock(return_value={})
    raw.hget = AsyncMock(return_value=None)
    raw.hset = AsyncMock()
    raw.expire = AsyncMock()

    client = MagicMock()
    client._redis = raw
    client._prefix = "claudevn:"
    return client, raw


def _presence_hash(user_id, project_id="proj-1", display_name="Alice",
                   current_view="Backlog", project_name="MyProject",
                   last_heartbeat=None, connected_at=None):
    """Build a Redis hash dict (bytes keys/values) for a presence entry."""
    now = datetime.now(timezone.utc)
    hb = (last_heartbeat or now).isoformat()
    ca = (connected_at or now).isoformat()
    return {
        b"user_id": user_id.encode(),
        b"project_id": project_id.encode(),
        b"project_name": project_name.encode(),
        b"display_name": display_name.encode(),
        b"current_view": current_view.encode(),
        b"last_heartbeat": hb.encode(),
        b"connected_at": ca.encode(),
    }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify threshold constants match the spec."""

    def test_presence_ttl_is_3_days(self):
        assert PRESENCE_TTL == 3 * 24 * 60 * 60

    def test_online_threshold_is_60_seconds(self):
        assert ONLINE_THRESHOLD == 60

    def test_idle_threshold_is_10_minutes(self):
        assert IDLE_THRESHOLD == 10 * 60


# ---------------------------------------------------------------------------
# Key format (global, not per-project)
# ---------------------------------------------------------------------------

class TestKeyFormat:
    """Presence keys should be global: prefix + user_id only."""

    def test_user_key_format(self):
        client, _ = _make_redis_mock()
        svc = PresenceService(redis_client=client)
        assert svc._user_key("u-1") == "claudevn:presence:user:u-1"

    def test_all_users_pattern(self):
        client, _ = _make_redis_mock()
        svc = PresenceService(redis_client=client)
        assert svc._all_users_pattern() == "claudevn:presence:user:*"


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

class TestHeartbeat:
    """Heartbeat should store global user key with project context."""

    @pytest.mark.asyncio
    async def test_heartbeat_stores_project_name(self):
        client, raw = _make_redis_mock()
        svc = PresenceService(redis_client=client)

        with patch.object(svc, '_broadcast_update', new_callable=AsyncMock):
            await svc.heartbeat(
                project_id="proj-1",
                user_id="u-1",
                display_name="Alice",
                current_view="Backlog",
                project_name="MyProject",
            )

        raw.hset.assert_called_once()
        _, kwargs = raw.hset.call_args
        mapping = kwargs["mapping"]
        assert mapping["project_name"] == "MyProject"
        assert mapping["project_id"] == "proj-1"
        assert mapping["current_view"] == "Backlog"

    @pytest.mark.asyncio
    async def test_heartbeat_sets_3_day_ttl(self):
        client, raw = _make_redis_mock()
        svc = PresenceService(redis_client=client)

        with patch.object(svc, '_broadcast_update', new_callable=AsyncMock):
            await svc.heartbeat(
                project_id="proj-1",
                user_id="u-1",
                display_name="Alice",
            )

        raw.expire.assert_called_once()
        key, ttl = raw.expire.call_args[0]
        assert ttl == PRESENCE_TTL

    @pytest.mark.asyncio
    async def test_heartbeat_preserves_connected_at(self):
        client, raw = _make_redis_mock()
        original_time = "2024-06-01T12:00:00+00:00"
        raw.hget.return_value = original_time.encode()
        svc = PresenceService(redis_client=client)

        with patch.object(svc, '_broadcast_update', new_callable=AsyncMock):
            await svc.heartbeat(
                project_id="proj-1",
                user_id="u-1",
                display_name="Alice",
            )

        _, kwargs = raw.hset.call_args
        assert kwargs["mapping"]["connected_at"] == original_time

    @pytest.mark.asyncio
    async def test_heartbeat_uses_global_key(self):
        client, raw = _make_redis_mock()
        svc = PresenceService(redis_client=client)

        with patch.object(svc, '_broadcast_update', new_callable=AsyncMock):
            await svc.heartbeat(
                project_id="proj-1",
                user_id="u-1",
                display_name="Alice",
            )

        key = raw.hset.call_args[0][0]
        assert key == "claudevn:presence:user:u-1"
        assert "proj-1" not in key


# ---------------------------------------------------------------------------
# Status thresholds
# ---------------------------------------------------------------------------

class TestStatusThresholds:
    """Verify status assignment: online < 60s, idle 60s-10m, offline > 10m."""

    @pytest.mark.asyncio
    async def test_online_within_60_seconds(self):
        client, raw = _make_redis_mock()
        now = datetime.now(timezone.utc)
        raw.keys.return_value = [b"claudevn:presence:user:u-1"]
        raw.hgetall.return_value = _presence_hash(
            "u-1", last_heartbeat=now - timedelta(seconds=30),
        )
        svc = PresenceService(redis_client=client)
        users = await svc.get_active_users()
        assert len(users) == 1
        assert users[0].status == "online"

    @pytest.mark.asyncio
    async def test_idle_between_1_and_10_minutes(self):
        client, raw = _make_redis_mock()
        now = datetime.now(timezone.utc)
        raw.keys.return_value = [b"claudevn:presence:user:u-1"]
        raw.hgetall.return_value = _presence_hash(
            "u-1", last_heartbeat=now - timedelta(minutes=5),
        )
        svc = PresenceService(redis_client=client)
        users = await svc.get_active_users()
        assert len(users) == 1
        assert users[0].status == "idle"

    @pytest.mark.asyncio
    async def test_offline_after_10_minutes(self):
        client, raw = _make_redis_mock()
        now = datetime.now(timezone.utc)
        raw.keys.return_value = [b"claudevn:presence:user:u-1"]
        raw.hgetall.return_value = _presence_hash(
            "u-1", last_heartbeat=now - timedelta(minutes=30),
        )
        svc = PresenceService(redis_client=client)
        users = await svc.get_active_users()
        assert len(users) == 1
        assert users[0].status == "offline"

    @pytest.mark.asyncio
    async def test_boundary_at_60_seconds_is_idle(self):
        client, raw = _make_redis_mock()
        now = datetime.now(timezone.utc)
        raw.keys.return_value = [b"claudevn:presence:user:u-1"]
        raw.hgetall.return_value = _presence_hash(
            "u-1", last_heartbeat=now - timedelta(seconds=61),
        )
        svc = PresenceService(redis_client=client)
        users = await svc.get_active_users()
        assert users[0].status == "idle"

    @pytest.mark.asyncio
    async def test_boundary_at_10_minutes_is_offline(self):
        client, raw = _make_redis_mock()
        now = datetime.now(timezone.utc)
        raw.keys.return_value = [b"claudevn:presence:user:u-1"]
        raw.hgetall.return_value = _presence_hash(
            "u-1", last_heartbeat=now - timedelta(seconds=601),
        )
        svc = PresenceService(redis_client=client)
        users = await svc.get_active_users()
        assert users[0].status == "offline"


# ---------------------------------------------------------------------------
# Global vs per-project
# ---------------------------------------------------------------------------

class TestGlobalPresence:
    """Presence should be global with optional project filter."""

    @pytest.mark.asyncio
    async def test_get_active_users_returns_all_without_filter(self):
        client, raw = _make_redis_mock()
        now = datetime.now(timezone.utc)
        raw.keys.return_value = [
            b"claudevn:presence:user:u-1",
            b"claudevn:presence:user:u-2",
        ]

        async def hgetall_side_effect(key):
            if b"u-1" in key:
                return _presence_hash("u-1", project_id="proj-1",
                                      last_heartbeat=now)
            return _presence_hash("u-2", project_id="proj-2",
                                  last_heartbeat=now)

        raw.hgetall.side_effect = hgetall_side_effect
        svc = PresenceService(redis_client=client)
        users = await svc.get_active_users()
        assert len(users) == 2

    @pytest.mark.asyncio
    async def test_get_active_users_filters_by_project(self):
        client, raw = _make_redis_mock()
        now = datetime.now(timezone.utc)
        raw.keys.return_value = [
            b"claudevn:presence:user:u-1",
            b"claudevn:presence:user:u-2",
        ]

        async def hgetall_side_effect(key):
            if b"u-1" in key:
                return _presence_hash("u-1", project_id="proj-1",
                                      last_heartbeat=now)
            return _presence_hash("u-2", project_id="proj-2",
                                  last_heartbeat=now)

        raw.hgetall.side_effect = hgetall_side_effect
        svc = PresenceService(redis_client=client)
        users = await svc.get_active_users(project_id="proj-1")
        assert len(users) == 1
        assert users[0].user_id == "u-1"


# ---------------------------------------------------------------------------
# Project name in presence
# ---------------------------------------------------------------------------

class TestProjectName:
    """Users should have project_name populated from heartbeat."""

    @pytest.mark.asyncio
    async def test_project_name_returned(self):
        client, raw = _make_redis_mock()
        now = datetime.now(timezone.utc)
        raw.keys.return_value = [b"claudevn:presence:user:u-1"]
        raw.hgetall.return_value = _presence_hash(
            "u-1", project_name="MyProject", current_view="Backlog",
            last_heartbeat=now,
        )
        svc = PresenceService(redis_client=client)
        users = await svc.get_active_users()
        assert users[0].project_name == "MyProject"
        assert users[0].current_view == "Backlog"
