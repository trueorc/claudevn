"""Tests for AuthorizationAuditService.

Tests authorization audit logging, querying, pagination,
statistics, alert thresholds, and deque eviction.
"""

import logging
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from models import AuthorizationAuditEntry, AuthorizationFailure
from services.authorization_audit_service import (
    AuthorizationAuditService,
    get_authorization_audit_service,
    _audit_service,
)


@pytest.fixture
def audit_service():
    """Create a fresh AuthorizationAuditService instance."""
    return AuthorizationAuditService(
        max_entries=100,
        alert_threshold=5,
        alert_window_seconds=300,
    )


@pytest.fixture
def populated_service(audit_service):
    """Create a service with a mix of granted and denied entries."""
    # 3 granted entries
    audit_service.log_authorization(
        agent_id="agent-1",
        tool_id="tool-a",
        authorized=True,
        reason="Skill grants access",
        compute_id="compute-1",
        granted_by=["skill-deploy"],
    )
    audit_service.log_authorization(
        agent_id="agent-2",
        tool_id="tool-b",
        authorized=True,
        reason="Global tool",
        compute_id="compute-2",
    )
    audit_service.log_authorization(
        agent_id="agent-1",
        tool_id="tool-c",
        authorized=True,
        reason="Global tool",
    )

    # 2 denied entries
    audit_service.log_authorization(
        agent_id="agent-3",
        tool_id="tool-a",
        authorized=False,
        reason="No skill grants access",
        failure_type=AuthorizationFailure.SKILL_NOT_GRANTED,
    )
    audit_service.log_authorization(
        agent_id="agent-3",
        tool_id="tool-d",
        authorized=False,
        reason="Tool not found",
        failure_type=AuthorizationFailure.TOOL_NOT_FOUND,
        compute_id="compute-1",
    )

    return audit_service


class TestLogAuthorization:
    """Tests for log_authorization method."""

    def test_creates_entry_with_correct_fields(self, audit_service):
        entry = audit_service.log_authorization(
            agent_id="agent-1",
            tool_id="tool-a",
            authorized=True,
            reason="Skill grants access",
            compute_id="compute-1",
            granted_by=["skill-deploy"],
        )

        assert isinstance(entry, AuthorizationAuditEntry)
        assert entry.id.startswith("audit-")
        assert entry.agent_id == "agent-1"
        assert entry.tool_id == "tool-a"
        assert entry.authorized is True
        assert entry.reason == "Skill grants access"
        assert entry.compute_id == "compute-1"
        assert entry.granted_by == ["skill-deploy"]
        assert entry.failure_type is None
        assert isinstance(entry.timestamp, datetime)

    def test_denied_entry_with_failure_type(self, audit_service):
        entry = audit_service.log_authorization(
            agent_id="agent-2",
            tool_id="tool-b",
            authorized=False,
            reason="No skill grants tool-b",
            failure_type=AuthorizationFailure.SKILL_NOT_GRANTED,
        )

        assert entry.authorized is False
        assert entry.failure_type == AuthorizationFailure.SKILL_NOT_GRANTED
        assert entry.compute_id is None
        assert entry.granted_by == []

    def test_increments_total_checks(self, audit_service):
        audit_service.log_authorization(
            agent_id="a", tool_id="t", authorized=True, reason="ok"
        )
        audit_service.log_authorization(
            agent_id="a", tool_id="t", authorized=False, reason="no",
            failure_type=AuthorizationFailure.TOOL_NOT_FOUND,
        )

        assert audit_service._total_checks == 2
        assert audit_service._total_authorized == 1
        assert audit_service._total_denied == 1

    def test_defaults_granted_by_to_empty_list(self, audit_service):
        entry = audit_service.log_authorization(
            agent_id="a", tool_id="t", authorized=True, reason="ok"
        )
        assert entry.granted_by == []

    def test_entries_appended_to_deque(self, audit_service):
        audit_service.log_authorization(
            agent_id="a", tool_id="t1", authorized=True, reason="ok"
        )
        audit_service.log_authorization(
            agent_id="a", tool_id="t2", authorized=True, reason="ok"
        )

        assert len(audit_service._entries) == 2
        assert audit_service._entries[0].tool_id == "t1"
        assert audit_service._entries[1].tool_id == "t2"

    def test_each_entry_gets_unique_id(self, audit_service):
        ids = set()
        for i in range(20):
            entry = audit_service.log_authorization(
                agent_id="a", tool_id=f"t{i}", authorized=True, reason="ok"
            )
            ids.add(entry.id)

        assert len(ids) == 20


class TestQueryFiltering:
    """Tests for query method filtering."""

    def test_no_filters_returns_all(self, populated_service):
        entries, total = populated_service.query()
        assert total == 5
        assert len(entries) == 5

    def test_filter_by_agent_id(self, populated_service):
        entries, total = populated_service.query(agent_id="agent-1")
        assert total == 2
        assert all(e.agent_id == "agent-1" for e in entries)

    def test_filter_by_tool_id(self, populated_service):
        entries, total = populated_service.query(tool_id="tool-a")
        assert total == 2
        assert all(e.tool_id == "tool-a" for e in entries)

    def test_filter_by_authorized_true(self, populated_service):
        entries, total = populated_service.query(authorized=True)
        assert total == 3
        assert all(e.authorized is True for e in entries)

    def test_filter_by_authorized_false(self, populated_service):
        entries, total = populated_service.query(authorized=False)
        assert total == 2
        assert all(e.authorized is False for e in entries)

    def test_filter_by_compute_id(self, populated_service):
        entries, total = populated_service.query(compute_id="compute-1")
        assert total == 2
        assert all(e.compute_id == "compute-1" for e in entries)

    def test_combined_filters(self, populated_service):
        entries, total = populated_service.query(
            agent_id="agent-3", authorized=False
        )
        assert total == 2
        assert all(
            e.agent_id == "agent-3" and e.authorized is False for e in entries
        )

    def test_filter_by_since_timestamp(self, audit_service):
        # Log entries with known timing
        before = datetime.now(timezone.utc)
        audit_service.log_authorization(
            agent_id="a", tool_id="t1", authorized=True, reason="old"
        )
        midpoint = datetime.now(timezone.utc)
        audit_service.log_authorization(
            agent_id="a", tool_id="t2", authorized=True, reason="new"
        )

        entries, total = audit_service.query(since=midpoint)
        assert total == 1
        assert entries[0].tool_id == "t2"

    def test_results_sorted_newest_first(self, populated_service):
        entries, _ = populated_service.query()
        for i in range(len(entries) - 1):
            assert entries[i].timestamp >= entries[i + 1].timestamp

    def test_no_matching_filters_returns_empty(self, populated_service):
        entries, total = populated_service.query(agent_id="nonexistent")
        assert total == 0
        assert entries == []


class TestQueryPagination:
    """Tests for query pagination (skip/limit, has_more)."""

    def test_limit_restricts_results(self, populated_service):
        entries, total = populated_service.query(limit=2)
        assert len(entries) == 2
        assert total == 5

    def test_skip_offsets_results(self, populated_service):
        all_entries, _ = populated_service.query()
        skipped, total = populated_service.query(skip=2)
        assert len(skipped) == 3
        assert total == 5
        assert skipped[0].id == all_entries[2].id

    def test_skip_and_limit_combined(self, populated_service):
        all_entries, _ = populated_service.query()
        page, total = populated_service.query(skip=1, limit=2)
        assert len(page) == 2
        assert total == 5
        assert page[0].id == all_entries[1].id
        assert page[1].id == all_entries[2].id

    def test_skip_beyond_total_returns_empty(self, populated_service):
        entries, total = populated_service.query(skip=100)
        assert entries == []
        assert total == 5

    def test_default_limit_is_100(self):
        service = AuthorizationAuditService(max_entries=200)
        for i in range(150):
            service.log_authorization(
                agent_id="a", tool_id=f"t{i}", authorized=True, reason="ok"
            )
        entries, total = service.query()
        assert len(entries) == 100
        assert total == 150


class TestGetStats:
    """Tests for get_stats method."""

    def test_returns_correct_counts(self, populated_service):
        stats = populated_service.get_stats()
        assert stats["total_checks"] == 5
        assert stats["total_authorized"] == 3
        assert stats["total_denied"] == 2

    def test_denial_rate_calculation(self, populated_service):
        stats = populated_service.get_stats()
        assert stats["denial_rate"] == round(2 / 5, 4)

    def test_top_denied_tools(self, populated_service):
        stats = populated_service.get_stats()
        tool_ids = [t["tool_id"] for t in stats["top_denied_tools"]]
        assert "tool-a" in tool_ids
        assert "tool-d" in tool_ids

    def test_top_denied_agents(self, populated_service):
        stats = populated_service.get_stats()
        agents = stats["top_denied_agents"]
        assert len(agents) == 1
        assert agents[0]["agent_id"] == "agent-3"
        assert agents[0]["count"] == 2

    def test_top_denied_limited_to_5(self, audit_service):
        for i in range(10):
            audit_service.log_authorization(
                agent_id=f"agent-{i}",
                tool_id=f"tool-{i}",
                authorized=False,
                reason="denied",
                failure_type=AuthorizationFailure.TOOL_NOT_FOUND,
            )
        stats = audit_service.get_stats()
        assert len(stats["top_denied_tools"]) == 5
        assert len(stats["top_denied_agents"]) == 5

    def test_top_denied_sorted_by_count_descending(self, audit_service):
        # tool-x denied 3 times, tool-y denied 1 time
        for _ in range(3):
            audit_service.log_authorization(
                agent_id="a", tool_id="tool-x", authorized=False,
                reason="no", failure_type=AuthorizationFailure.SKILL_NOT_GRANTED,
            )
        audit_service.log_authorization(
            agent_id="a", tool_id="tool-y", authorized=False,
            reason="no", failure_type=AuthorizationFailure.SKILL_NOT_GRANTED,
        )

        stats = audit_service.get_stats()
        tools = stats["top_denied_tools"]
        assert tools[0]["tool_id"] == "tool-x"
        assert tools[0]["count"] == 3
        assert tools[1]["tool_id"] == "tool-y"
        assert tools[1]["count"] == 1


class TestAlertThreshold:
    """Tests for alert threshold logging."""

    def test_alert_triggered_when_threshold_exceeded(self, audit_service, caplog):
        with caplog.at_level(logging.ERROR):
            for i in range(5):
                audit_service.log_authorization(
                    agent_id="bad-agent",
                    tool_id=f"tool-{i}",
                    authorized=False,
                    reason="denied",
                    failure_type=AuthorizationFailure.SKILL_NOT_GRANTED,
                )

        alert_messages = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(alert_messages) >= 1
        assert "ALERT" in alert_messages[0].message
        assert "failed authorization attempts" in alert_messages[0].message

    def test_no_alert_below_threshold(self, audit_service, caplog):
        with caplog.at_level(logging.ERROR):
            for i in range(4):
                audit_service.log_authorization(
                    agent_id="agent",
                    tool_id=f"tool-{i}",
                    authorized=False,
                    reason="denied",
                    failure_type=AuthorizationFailure.TOOL_NOT_FOUND,
                )

        alert_messages = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(alert_messages) == 0

    def test_no_alert_for_authorized_entries(self, audit_service, caplog):
        with caplog.at_level(logging.ERROR):
            for i in range(10):
                audit_service.log_authorization(
                    agent_id="agent",
                    tool_id=f"tool-{i}",
                    authorized=True,
                    reason="granted",
                )

        alert_messages = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(alert_messages) == 0

    def test_alert_includes_latest_agent_and_tool(self, audit_service, caplog):
        with caplog.at_level(logging.ERROR):
            for i in range(5):
                audit_service.log_authorization(
                    agent_id="bad-agent",
                    tool_id="restricted-tool",
                    authorized=False,
                    reason="denied",
                    failure_type=AuthorizationFailure.SKILL_NOT_GRANTED,
                )

        alert_messages = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert "bad-agent" in alert_messages[0].message
        assert "restricted-tool" in alert_messages[0].message


class TestDequeEviction:
    """Tests for deque maxlen eviction behavior."""

    def test_entries_evicted_beyond_max(self):
        service = AuthorizationAuditService(max_entries=5)
        entries = []
        for i in range(8):
            entry = service.log_authorization(
                agent_id="a", tool_id=f"tool-{i}", authorized=True, reason="ok"
            )
            entries.append(entry)

        assert len(service._entries) == 5
        # Oldest 3 should be evicted
        remaining_ids = [e.id for e in service._entries]
        for i in range(3):
            assert entries[i].id not in remaining_ids
        # Newest 5 should remain
        for i in range(3, 8):
            assert entries[i].id in remaining_ids

    def test_counters_reflect_all_entries_including_evicted(self):
        service = AuthorizationAuditService(max_entries=3)
        for i in range(5):
            service.log_authorization(
                agent_id="a", tool_id=f"t{i}", authorized=True, reason="ok"
            )

        # Counters track all entries, not just in-deque
        assert service._total_checks == 5
        assert service._total_authorized == 5
        assert len(service._entries) == 3

    def test_stats_denial_rate_uses_counters_not_deque(self):
        service = AuthorizationAuditService(max_entries=3)
        # 3 granted, then 2 denied - first 2 granted evicted
        for i in range(3):
            service.log_authorization(
                agent_id="a", tool_id=f"t{i}", authorized=True, reason="ok"
            )
        for i in range(2):
            service.log_authorization(
                agent_id="a", tool_id=f"d{i}", authorized=False,
                reason="no", failure_type=AuthorizationFailure.TOOL_NOT_FOUND,
            )

        stats = service.get_stats()
        assert stats["total_checks"] == 5
        assert stats["total_authorized"] == 3
        assert stats["total_denied"] == 2
        assert stats["denial_rate"] == round(2 / 5, 4)


class TestEdgeCases:
    """Tests for edge case behavior."""

    def test_empty_audit_log_returns_empty_results(self, audit_service):
        entries, total = audit_service.query()
        assert entries == []
        assert total == 0

    def test_empty_stats_returns_zero_denial_rate(self, audit_service):
        stats = audit_service.get_stats()
        assert stats["total_checks"] == 0
        assert stats["total_authorized"] == 0
        assert stats["total_denied"] == 0
        assert stats["denial_rate"] == 0.0
        assert stats["top_denied_tools"] == []
        assert stats["top_denied_agents"] == []

    def test_query_with_no_matching_filters_returns_empty(self, populated_service):
        entries, total = populated_service.query(
            agent_id="nonexistent", tool_id="also-nonexistent"
        )
        assert entries == []
        assert total == 0

    def test_all_failure_types_can_be_logged(self, audit_service):
        for failure_type in AuthorizationFailure:
            entry = audit_service.log_authorization(
                agent_id="a",
                tool_id="t",
                authorized=False,
                reason=f"failed: {failure_type.value}",
                failure_type=failure_type,
            )
            assert entry.failure_type == failure_type

    def test_only_authorized_entries(self, audit_service):
        for i in range(5):
            audit_service.log_authorization(
                agent_id="a", tool_id=f"t{i}", authorized=True, reason="ok"
            )

        stats = audit_service.get_stats()
        assert stats["denial_rate"] == 0.0
        assert stats["top_denied_tools"] == []
        assert stats["top_denied_agents"] == []

    def test_only_denied_entries(self, audit_service):
        for i in range(5):
            audit_service.log_authorization(
                agent_id="a", tool_id=f"t{i}", authorized=False,
                reason="no", failure_type=AuthorizationFailure.TOOL_NOT_FOUND,
            )

        stats = audit_service.get_stats()
        assert stats["denial_rate"] == 1.0


class TestSingleton:
    """Tests for the module-level singleton."""

    def test_get_authorization_audit_service_returns_instance(self):
        import services.authorization_audit_service as mod
        # Reset singleton for isolated test
        mod._audit_service = None
        service = mod.get_authorization_audit_service()
        assert isinstance(service, AuthorizationAuditService)

    def test_singleton_returns_same_instance(self):
        import services.authorization_audit_service as mod
        mod._audit_service = None
        first = mod.get_authorization_audit_service()
        second = mod.get_authorization_audit_service()
        assert first is second
        # Cleanup
        mod._audit_service = None
