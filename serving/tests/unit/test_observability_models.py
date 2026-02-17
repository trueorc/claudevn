"""Unit tests for observability event models.

Tests compute registration/deregistration event models added in issue #791.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from models.observability import (
    EventType,
    ComputeRegisteredEvent,
    ComputeDeregisteredEvent,
)


class TestEventType:
    """Test EventType enum additions."""

    def test_compute_registered_event_type(self):
        """COMPUTE_REGISTERED is a valid EventType."""
        assert EventType.COMPUTE_REGISTERED == "compute_registered"
        assert EventType.COMPUTE_REGISTERED.value == "compute_registered"

    def test_compute_deregistered_event_type(self):
        """COMPUTE_DEREGISTERED is a valid EventType."""
        assert EventType.COMPUTE_DEREGISTERED == "compute_deregistered"
        assert EventType.COMPUTE_DEREGISTERED.value == "compute_deregistered"


class TestComputeRegisteredEvent:
    """Test ComputeRegisteredEvent model."""

    def test_create_with_all_fields(self):
        """Can create ComputeRegisteredEvent with all fields."""
        event = ComputeRegisteredEvent(
            event_id="cr_abc123",
            compute_id="compute-001",
            name="Compute 001",
            capabilities=["agent-a", "agent-b"],
            labels=["production-access", "database-admin"],
            tools_available=["deploy_prod", "db_migrate"],
            metadata={"connection_type": "sse", "endpoint": "sse"}
        )

        assert event.event_type == EventType.COMPUTE_REGISTERED
        assert event.event_id == "cr_abc123"
        assert event.compute_id == "compute-001"
        assert event.name == "Compute 001"
        assert event.capabilities == ["agent-a", "agent-b"]
        assert event.labels == ["production-access", "database-admin"]
        assert event.tools_available == ["deploy_prod", "db_migrate"]
        assert event.metadata["connection_type"] == "sse"

    def test_default_session_id_is_global(self):
        """session_id defaults to 'global' for broadcast."""
        event = ComputeRegisteredEvent(
            event_id="cr_abc123",
            compute_id="compute-001",
            name="Compute 001",
            capabilities=[],
            labels=[],
            tools_available=[],
        )

        assert event.session_id == "global"

    def test_timestamp_defaults_to_now(self):
        """timestamp defaults to current UTC time."""
        before = datetime.now(timezone.utc)
        event = ComputeRegisteredEvent(
            event_id="cr_abc123",
            compute_id="compute-001",
            name="Compute 001",
            capabilities=[],
            labels=[],
            tools_available=[],
        )
        after = datetime.now(timezone.utc)

        assert before <= event.timestamp <= after

    def test_serialization(self):
        """Event can be serialized to JSON."""
        event = ComputeRegisteredEvent(
            event_id="cr_abc123",
            compute_id="compute-001",
            name="Compute 001",
            capabilities=["agent-a"],
            labels=["production-access"],
            tools_available=["deploy_prod"],
            metadata={"connection_type": "sse"}
        )

        data = event.model_dump()
        assert data["event_type"] == "compute_registered"
        assert data["compute_id"] == "compute-001"
        assert data["capabilities"] == ["agent-a"]
        assert data["labels"] == ["production-access"]
        assert data["tools_available"] == ["deploy_prod"]

    def test_deserialization(self):
        """Event can be deserialized from JSON."""
        data = {
            "event_id": "cr_abc123",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": "global",
            "compute_id": "compute-001",
            "name": "Compute 001",
            "capabilities": ["agent-a"],
            "labels": ["production-access"],
            "tools_available": ["deploy_prod"],
            "metadata": {"connection_type": "sse"}
        }

        event = ComputeRegisteredEvent(**data)
        assert event.compute_id == "compute-001"
        assert event.capabilities == ["agent-a"]

    def test_empty_lists_allowed(self):
        """Empty lists are allowed for capabilities, labels, tools_available."""
        event = ComputeRegisteredEvent(
            event_id="cr_abc123",
            compute_id="compute-001",
            name="Compute 001",
            capabilities=[],
            labels=[],
            tools_available=[],
        )

        assert event.capabilities == []
        assert event.labels == []
        assert event.tools_available == []


class TestComputeDeregisteredEvent:
    """Test ComputeDeregisteredEvent model."""

    def test_create_with_all_fields(self):
        """Can create ComputeDeregisteredEvent with all fields."""
        event = ComputeDeregisteredEvent(
            event_id="cd_abc123",
            compute_id="compute-001",
            reason="manual_deregister",
            metadata={"last_seen": "2026-02-15T10:00:00+00:00"}
        )

        assert event.event_type == EventType.COMPUTE_DEREGISTERED
        assert event.event_id == "cd_abc123"
        assert event.compute_id == "compute-001"
        assert event.reason == "manual_deregister"
        assert event.metadata["last_seen"] == "2026-02-15T10:00:00+00:00"

    def test_default_session_id_is_global(self):
        """session_id defaults to 'global' for broadcast."""
        event = ComputeDeregisteredEvent(
            event_id="cd_abc123",
            compute_id="compute-001",
            reason="sse_disconnect"
        )

        assert event.session_id == "global"

    def test_default_reason_is_normal(self):
        """reason defaults to 'normal'."""
        event = ComputeDeregisteredEvent(
            event_id="cd_abc123",
            compute_id="compute-001"
        )

        assert event.reason == "normal"

    def test_timestamp_defaults_to_now(self):
        """timestamp defaults to current UTC time."""
        before = datetime.now(timezone.utc)
        event = ComputeDeregisteredEvent(
            event_id="cd_abc123",
            compute_id="compute-001",
            reason="sse_disconnect"
        )
        after = datetime.now(timezone.utc)

        assert before <= event.timestamp <= after

    def test_serialization(self):
        """Event can be serialized to JSON."""
        event = ComputeDeregisteredEvent(
            event_id="cd_abc123",
            compute_id="compute-001",
            reason="sse_disconnect",
            metadata={"connection_type": "sse"}
        )

        data = event.model_dump()
        assert data["event_type"] == "compute_deregistered"
        assert data["compute_id"] == "compute-001"
        assert data["reason"] == "sse_disconnect"

    def test_deserialization(self):
        """Event can be deserialized from JSON."""
        data = {
            "event_id": "cd_abc123",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": "global",
            "compute_id": "compute-001",
            "reason": "manual_deregister",
            "metadata": {}
        }

        event = ComputeDeregisteredEvent(**data)
        assert event.compute_id == "compute-001"
        assert event.reason == "manual_deregister"

    def test_common_deregister_reasons(self):
        """Common deregister reasons are valid."""
        reasons = [
            "normal",
            "sse_disconnect",
            "manual_deregister",
            "timeout",
            "drain_complete"
        ]

        for reason in reasons:
            event = ComputeDeregisteredEvent(
                event_id=f"cd_{uuid4().hex[:12]}",
                compute_id="compute-001",
                reason=reason
            )
            assert event.reason == reason
