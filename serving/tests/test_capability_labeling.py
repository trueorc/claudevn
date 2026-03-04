"""Unit tests for BYOC capability labeling and runtime detection.

Tests the runtime capability naming convention, capability index updates
on PATCH, and SSE routing with runtime labels.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.compute import ComputeInstance, InstanceCapabilities


class TestRuntimeCapabilityConvention:
    """Verify the runtime:name:version naming convention works with existing models."""

    def test_tools_available_accepts_runtime_labels(self):
        caps = InstanceCapabilities(
            tools_available=["runtime:node:22", "runtime:python:3.12", "deploy_prod"]
        )
        assert "runtime:node:22" in caps.tools_available
        assert len(caps.tools_available) == 3

    def test_compute_instance_with_runtime_capabilities(self):
        instance = ComputeInstance(
            instance_id="byoc-001",
            name="BYOC Node Server",
            endpoint="http://localhost:9000",
            capabilities=InstanceCapabilities(
                agents=["code-writer"],
                tools_available=["runtime:node:22", "runtime:python:3.12"],
                labels=["production-access"],
            ),
        )
        runtimes = [t for t in instance.capabilities.tools_available if t.startswith("runtime:")]
        assert len(runtimes) == 2
        assert "runtime:node:22" in runtimes

    def test_runtime_label_format(self):
        """Verify convention: runtime:<name>:<major_version>"""
        valid_labels = [
            "runtime:node:22",
            "runtime:python:3.12",
            "runtime:go:1.22",
            "runtime:rust:1.77",
            "runtime:java:21",
            "runtime:ruby:3.3",
            "runtime:docker",
        ]
        for label in valid_labels:
            parts = label.split(":")
            assert parts[0] == "runtime"
            assert len(parts) >= 2  # at least runtime:name


class TestCapabilityIndexReindex:
    """Verify that updating capabilities re-indexes correctly."""

    @pytest.mark.asyncio
    async def test_update_instance_reindexes_tools_available(self):
        """When capabilities are updated via PATCH, the index reflects new tools."""
        from services.registry_service import ComputeRegistry

        registry = ComputeRegistry.__new__(ComputeRegistry)
        from collections import defaultdict
        registry._instances = {}
        registry._capability_index = defaultdict(list)
        registry._project_index = defaultdict(list)
        registry._storage = None
        registry.logger = MagicMock()

        # Create instance with initial capabilities
        instance = ComputeInstance(
            instance_id="byoc-001",
            name="BYOC",
            endpoint="http://localhost:9000",
            capabilities=InstanceCapabilities(
                tools_available=["runtime:python:3.12"],
            ),
        )
        registry._instances["byoc-001"] = instance
        registry._update_capability_index(instance)

        assert "byoc-001" in registry._capability_index.get("tool_available:runtime:python:3.12", [])

        # Update with new capabilities
        new_caps = InstanceCapabilities(
            tools_available=["runtime:python:3.12", "runtime:node:22"],
        )
        updated = await registry.update_instance("byoc-001", capabilities=new_caps)

        assert updated is not None
        assert "byoc-001" in registry._capability_index.get("tool_available:runtime:node:22", [])
        assert "byoc-001" in registry._capability_index.get("tool_available:runtime:python:3.12", [])

    @pytest.mark.asyncio
    async def test_update_removes_old_index_entries(self):
        """When capabilities change, old index entries are removed."""
        from collections import defaultdict
        from services.registry_service import ComputeRegistry

        registry = ComputeRegistry.__new__(ComputeRegistry)
        registry._instances = {}
        registry._capability_index = defaultdict(list)
        registry._project_index = defaultdict(list)
        registry._storage = None
        registry.logger = MagicMock()

        instance = ComputeInstance(
            instance_id="byoc-001",
            name="BYOC",
            endpoint="http://localhost:9000",
            capabilities=InstanceCapabilities(
                tools_available=["runtime:go:1.21"],
            ),
        )
        registry._instances["byoc-001"] = instance
        registry._update_capability_index(instance)

        # Verify old entry exists
        assert "byoc-001" in registry._capability_index["tool_available:runtime:go:1.21"]

        # Update: replace go with node
        new_caps = InstanceCapabilities(
            tools_available=["runtime:node:22"],
        )
        await registry.update_instance("byoc-001", capabilities=new_caps)

        # Old entry removed, new entry present
        assert "byoc-001" not in registry._capability_index.get("tool_available:runtime:go:1.21", [])
        assert "byoc-001" in registry._capability_index["tool_available:runtime:node:22"]


class TestSSERoutingWithRuntimes:
    """Verify SSE connection manager routes work based on runtime capabilities."""

    def _make_connection(self, capabilities=None, labels=None, tools=None):
        conn = MagicMock()
        conn.capabilities = capabilities or []
        conn.labels = labels or []
        conn.tools_available = tools or []
        conn.status = "idle"
        return conn

    def _make_manager(self, connections):
        from services.sse_connection_manager import SSEConnectionManager
        manager = SSEConnectionManager.__new__(SSEConnectionManager)
        manager._connections = {f"c-{i}": c for i, c in enumerate(connections)}
        manager._on_connect_handlers = []
        manager._on_disconnect_handlers = []
        manager._round_robin_indices = {}
        manager._registry = None
        manager._keepalive_task = None
        manager._keepalive_interval = 30
        return manager

    def test_has_capable_connection_with_runtime_tool(self):
        conn = self._make_connection(tools=["runtime:node:22", "runtime:python:3.12"])
        manager = self._make_manager([conn])
        assert manager.has_capable_connection(required_tools=["runtime:node:22"])
        assert not manager.has_capable_connection(required_tools=["runtime:go:1.22"])

    def test_find_matching_connection_filters_by_runtime(self):
        node_conn = self._make_connection(tools=["runtime:node:22"])
        python_conn = self._make_connection(tools=["runtime:python:3.12"])
        manager = self._make_manager([node_conn, python_conn])

        match = manager.find_matching_connection(required_tools=["runtime:node:22"])
        assert match is not None
        assert "runtime:node:22" in match.tools_available
