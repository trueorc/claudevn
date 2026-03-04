"""Unit tests for managed vs unmanaged compute lifecycle mode.

Tests the LifecycleMode enum, model defaults, and registration propagation.
"""

from unittest.mock import MagicMock

import pytest

from models.compute import (
    ComputeInstance,
    LifecycleMode,
    InstanceCapabilities,
    RegistrationRequest,
)


class TestLifecycleModeEnum:
    def test_managed_value(self):
        assert LifecycleMode.MANAGED == "managed"

    def test_unmanaged_value(self):
        assert LifecycleMode.UNMANAGED == "unmanaged"

    def test_both_members_present(self):
        values = [m.value for m in LifecycleMode]
        assert "managed" in values
        assert "unmanaged" in values


class TestComputeInstanceLifecycle:
    def test_default_is_unmanaged(self):
        """New instances default to unmanaged (BYOC) for backwards compatibility."""
        instance = ComputeInstance(
            instance_id="test-001",
            name="Test",
            endpoint="http://localhost:8003",
        )
        assert instance.lifecycle_mode == LifecycleMode.UNMANAGED

    def test_can_set_managed(self):
        instance = ComputeInstance(
            instance_id="test-001",
            name="Test",
            endpoint="http://localhost:8003",
            lifecycle_mode=LifecycleMode.MANAGED,
        )
        assert instance.lifecycle_mode == LifecycleMode.MANAGED

    def test_serializes_to_json(self):
        instance = ComputeInstance(
            instance_id="test-001",
            name="Test",
            endpoint="http://localhost:8003",
            lifecycle_mode=LifecycleMode.MANAGED,
        )
        data = instance.model_dump()
        assert data["lifecycle_mode"] == "managed"

    def test_deserializes_from_string(self):
        instance = ComputeInstance(
            instance_id="test-001",
            name="Test",
            endpoint="http://localhost:8003",
            lifecycle_mode="managed",
        )
        assert instance.lifecycle_mode == LifecycleMode.MANAGED


class TestRegistrationRequestLifecycle:
    def test_default_is_unmanaged(self):
        req = RegistrationRequest(
            instance_id="test-001",
            name="Test",
            endpoint="http://localhost:8003",
        )
        assert req.lifecycle_mode == LifecycleMode.UNMANAGED

    def test_can_set_managed(self):
        req = RegistrationRequest(
            instance_id="test-001",
            name="Test",
            endpoint="http://localhost:8003",
            lifecycle_mode=LifecycleMode.MANAGED,
        )
        assert req.lifecycle_mode == LifecycleMode.MANAGED

    def test_backwards_compatible_without_field(self):
        """Existing registrations without lifecycle_mode should still work."""
        data = {
            "instance_id": "test-001",
            "name": "Test",
            "endpoint": "http://localhost:8003",
        }
        req = RegistrationRequest(**data)
        assert req.lifecycle_mode == LifecycleMode.UNMANAGED
