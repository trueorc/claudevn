"""MCP Server module for ClaudeVN compute communication.

This module provides two interfaces for MCP communication:
1. HTTP API (server.py) - FastAPI router for HTTP-based MCP
2. stdio server (stdio_server.py) - JSON-RPC 2.0 over stdio for Claude Code

Claude Code compute instances use the stdio server for proper MCP protocol
compliance, which bridges to the HTTP API internally.
"""

# Import router only when needed (not at module level to avoid FastAPI dependency)
def get_router():
    """Get the MCP router (imports FastAPI on demand)."""
    from .server import router
    return router


def get_stdio_server():
    """Get the MCPServer class for stdio communication."""
    from .stdio_server import MCPServer
    return MCPServer


__all__ = ["get_router", "get_stdio_server"]
