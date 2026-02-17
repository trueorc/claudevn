"""Unit tests for MCP stdio server.

Tests the JSON-RPC 2.0 protocol implementation and tool handling.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

import sys
from pathlib import Path

# Add serving to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.stdio_server import MCPServer, TOOLS, PROTOCOL_VERSION


class TestMCPServer:
    """Test cases for the MCPServer class."""

    @pytest.fixture
    def server(self):
        """Create an MCP server instance for testing."""
        return MCPServer(
            serving_url="http://localhost:8002",
            compute_id="test-compute",
            api_key="test-api-key"
        )

    def test_init(self, server):
        """Test server initialization."""
        assert server.serving_url == "http://localhost:8002"
        assert server.compute_id == "test-compute"
        assert server.api_key == "test-api-key"
        assert not server.initialized

    def test_protocol_version(self):
        """Test MCP protocol version is set."""
        assert PROTOCOL_VERSION == "2024-11-05"

    def test_tools_defined(self):
        """Test all required tools are defined.

        Note: claudevn_get_assignment is NOT included here because it's used by
        Compute Infra (via HTTP API), not by Claude Code (via stdio).
        See ADR-003 for the notification + fetch pattern.
        """
        tool_names = [t["name"] for t in TOOLS]
        expected_tools = [
            "claudevn_report_progress",
            "claudevn_request_review",
            "claudevn_get_context",
            "claudevn_signal_blocker",
            "claudevn_complete_task",
            "claudevn_get_persona",
            "claudevn_submit_characterization",
        ]
        for tool in expected_tools:
            assert tool in tool_names, f"Missing tool: {tool}"

        # Verify claudevn_get_assignment is NOT in stdio server tools
        assert "claudevn_get_assignment" not in tool_names, \
            "claudevn_get_assignment should not be in stdio server (it's for Compute Infra HTTP API)"

    def test_tools_have_input_schema(self):
        """Test all tools have proper input schemas."""
        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"
            assert "properties" in tool["inputSchema"]
            assert "required" in tool["inputSchema"]


class TestJSONRPCProtocol:
    """Test JSON-RPC 2.0 protocol handling."""

    @pytest.fixture
    def server(self):
        """Create an MCP server instance for testing."""
        return MCPServer(
            serving_url="http://localhost:8002",
            compute_id="test-compute",
            api_key="test-api-key"
        )

    def test_send_response_format(self, server, capsys):
        """Test response format is valid JSON."""
        response = {"jsonrpc": "2.0", "id": 1, "result": {}}
        server._send_response(response)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed == response

    def test_send_error_format(self, server, capsys):
        """Test error response format."""
        server._send_error(1, -32600, "Invalid Request")
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert parsed["error"]["code"] == -32600
        assert parsed["error"]["message"] == "Invalid Request"

    def test_send_error_with_data(self, server, capsys):
        """Test error response with additional data."""
        server._send_error(1, -32602, "Invalid params", {"detail": "missing field"})
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["error"]["data"] == {"detail": "missing field"}

    def test_send_result_format(self, server, capsys):
        """Test success response format."""
        server._send_result(1, {"status": "ok"})
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert parsed["result"] == {"status": "ok"}


class TestInitializeHandler:
    """Test the initialize method handler."""

    @pytest.fixture
    def server(self):
        """Create an MCP server instance for testing."""
        return MCPServer(
            serving_url="http://localhost:8002",
            compute_id="test-compute",
            api_key="test-api-key"
        )

    def test_handle_initialize(self, server, capsys):
        """Test initialize handler returns correct capabilities."""
        server.handle_initialize(1, {"clientInfo": {"name": "test-client"}})
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())

        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert parsed["result"]["protocolVersion"] == PROTOCOL_VERSION
        assert "tools" in parsed["result"]["capabilities"]
        assert parsed["result"]["serverInfo"]["name"] == "claudevn-mcp-server"
        assert server.initialized is True


class TestToolsListHandler:
    """Test the tools/list method handler."""

    @pytest.fixture
    def server(self):
        """Create an MCP server instance for testing."""
        return MCPServer(
            serving_url="http://localhost:8002",
            compute_id="test-compute",
            api_key="test-api-key"
        )

    def test_handle_tools_list(self, server, capsys):
        """Test tools/list returns all tools with schemas."""
        server.handle_tools_list(1)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())

        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert "tools" in parsed["result"]
        assert len(parsed["result"]["tools"]) == 9

        # Verify each tool has required fields
        for tool in parsed["result"]["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool


class TestToolsCallHandler:
    """Test the tools/call method handler."""

    @pytest.fixture
    def server(self):
        """Create an MCP server instance for testing."""
        return MCPServer(
            serving_url="http://localhost:8002",
            compute_id="test-compute",
            api_key="test-api-key"
        )

    def test_handle_tools_call_unknown_tool(self, server, capsys):
        """Test tools/call with unknown tool returns error."""
        server.handle_tools_call(1, {"name": "unknown_tool", "arguments": {}})
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())

        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert parsed["error"]["code"] == -32602
        assert "unknown_tool" in parsed["error"]["message"].lower()

    @patch.object(MCPServer, '_call_http_api')
    def test_handle_tools_call_success(self, mock_api, server, capsys):
        """Test tools/call success response format."""
        mock_api.return_value = {
            "success": True,
            "result": {"acknowledged": True, "task_id": "task-123"}
        }

        server.handle_tools_call(1, {
            "name": "claudevn_report_progress",
            "arguments": {"task_id": "task-123", "status": "in_progress"}
        })

        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())

        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert "content" in parsed["result"]
        assert parsed["result"]["content"][0]["type"] == "text"

    @patch.object(MCPServer, '_call_http_api')
    def test_handle_tools_call_error(self, mock_api, server, capsys):
        """Test tools/call error response format."""
        mock_api.return_value = {
            "success": False,
            "error": {
                "code": "TASK_NOT_FOUND",
                "message": "Task not found"
            }
        }

        server.handle_tools_call(1, {
            "name": "claudevn_report_progress",
            "arguments": {"task_id": "unknown", "status": "in_progress"}
        })

        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())

        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert "content" in parsed["result"]
        assert parsed["result"].get("isError") is True


class TestRequestRouter:
    """Test the request routing logic."""

    @pytest.fixture
    def server(self):
        """Create an MCP server instance for testing."""
        return MCPServer(
            serving_url="http://localhost:8002",
            compute_id="test-compute",
            api_key="test-api-key"
        )

    def test_route_initialize(self, server, capsys):
        """Test routing initialize method."""
        server.handle_request({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"clientInfo": {"name": "test"}}
        })
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert "protocolVersion" in parsed["result"]

    def test_route_tools_list(self, server, capsys):
        """Test routing tools/list method."""
        server.handle_request({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        })
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert "tools" in parsed["result"]

    def test_route_ping(self, server, capsys):
        """Test routing ping method."""
        server.handle_request({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "ping",
            "params": {}
        })
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["result"] == {}

    def test_route_unknown_method(self, server, capsys):
        """Test routing unknown method returns error."""
        server.handle_request({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "unknown/method",
            "params": {}
        })
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["error"]["code"] == -32601

    def test_route_notification(self, server, capsys):
        """Test notifications don't produce response."""
        server.handle_request({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        })
        captured = capsys.readouterr()
        # Notifications should not produce output
        assert captured.out.strip() == ""
