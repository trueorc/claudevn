#!/usr/bin/env python3
"""MCP Server - JSON-RPC 2.0 over stdio for Claude Code compute instances.

This script implements the Model Context Protocol (MCP) using JSON-RPC 2.0 over
stdio (reading from stdin, writing to stdout). It bridges Claude Code compute
instances to the ClaudeVN serving component's HTTP API.

Usage:
    python -m serving.mcp.stdio_server --serving-url http://localhost:8002

Environment Variables:
    CLAUDEVN_SERVING_URL: URL of the serving component (alternative to --serving-url)
    CLAUDEVN_COMPUTE_ID: Compute instance ID for authentication
    CLAUDEVN_API_KEY: API key for authentication
"""

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, Optional
import urllib.request
import urllib.error

# Configure logging to stderr (stdout is reserved for JSON-RPC)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# MCP Protocol version
PROTOCOL_VERSION = "2024-11-05"

# Tool definitions with proper MCP schema
# Note: claudevn_get_assignment is NOT included here as it's used by Compute Infra
# (via HTTP API), not by Claude Code. Work is pushed to Claude Code via SSE.
# See ADR-003 for the notification + fetch pattern.
TOOLS = [
    {
        "name": "claudevn_report_progress",
        "description": "Update task status and progress",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task being updated"
                },
                "status": {
                    "type": "string",
                    "enum": ["started", "in_progress", "blocked", "review_requested", "completed"],
                    "description": "Current task status"
                },
                "progress_percent": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Estimated completion percentage"
                },
                "message": {
                    "type": "string",
                    "description": "Status message or update"
                },
                "commits": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Commit SHAs made for this task"
                }
            },
            "required": ["task_id", "status"]
        }
    },
    {
        "name": "claudevn_request_review",
        "description": "Signal that a branch is ready for review/merge",
        "inputSchema": {
            "type": "object",
            "properties": {
                "branch": {
                    "type": "string",
                    "description": "Branch name to submit for review"
                },
                "task_id": {
                    "type": "string",
                    "description": "Associated task ID"
                },
                "title": {
                    "type": "string",
                    "description": "PR title"
                },
                "description": {
                    "type": "string",
                    "description": "PR description"
                },
                "test_results": {
                    "type": "object",
                    "description": "Test execution results if any"
                }
            },
            "required": ["branch", "task_id"]
        }
    },
    {
        "name": "claudevn_get_context",
        "description": "Fetch relevant context for a task (files, history, related work)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task to get context for"
                },
                "context_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["files", "history", "related_tasks", "dependencies", "all"]
                    },
                    "description": "Types of context to retrieve"
                },
                "file_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Glob patterns for files to include"
                }
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "claudevn_signal_blocker",
        "description": "Report a blocker preventing task completion",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task that is blocked"
                },
                "blocker_type": {
                    "type": "string",
                    "enum": ["dependency", "clarification", "access", "technical", "other"],
                    "description": "Type of blocker"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the blocker"
                },
                "suggested_resolution": {
                    "type": "string",
                    "description": "How this blocker might be resolved"
                },
                "blocking_task_id": {
                    "type": "string",
                    "description": "If blocked by another task, its ID"
                }
            },
            "required": ["task_id", "blocker_type", "description"]
        }
    },
    {
        "name": "claudevn_complete_task",
        "description": "Mark a task as complete and request merge",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task being completed"
                },
                "branch": {
                    "type": "string",
                    "description": "Branch containing the work"
                },
                "summary": {
                    "type": "string",
                    "description": "Summary of work completed"
                },
                "deliverables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of deliverables"
                },
                "test_results": {
                    "type": "object",
                    "description": "Final test results"
                }
            },
            "required": ["task_id", "branch", "summary"]
        }
    },
    {
        "name": "claudevn_get_persona",
        "description": "Fetch persona definition (CLAUDE.md content)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "persona_id": {
                    "type": "string",
                    "description": "Persona identifier"
                }
            },
            "required": ["persona_id"]
        }
    },
    {
        "name": "claudevn_add_requirement",
        "description": "Add new work discovered during task execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Brief title for the new work"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the requirement"
                },
                "parent_task_id": {
                    "type": "string",
                    "description": "Task ID that spawned this requirement"
                },
                "suggested_skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Skills that might be needed for this work"
                },
                "dependencies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs this requirement depends on"
                },
                "priority": {
                    "type": "string",
                    "enum": ["critical", "high", "normal", "low"],
                    "description": "Priority level for the requirement"
                }
            },
            "required": ["title", "description", "parent_task_id"]
        }
    },
    {
        "name": "claudevn_submit_decomposition",
        "description": "Submit goal decomposition results back to serving",
        "inputSchema": {
            "type": "object",
            "properties": {
                "decomposition_id": {
                    "type": "string",
                    "description": "Decomposition ID assigned by serving"
                },
                "goal_id": {
                    "type": "string",
                    "description": "Goal being decomposed"
                },
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "temp_id": {"type": "string", "description": "Temporary ID (e.g., 'issue-1')"},
                            "title": {"type": "string", "description": "Issue title"},
                            "description": {"type": "string", "description": "Issue description"},
                            "issue_type": {"type": "string", "enum": ["feature", "bug", "refactor", "test", "docs"]},
                            "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                            "area": {"type": "string", "enum": ["api", "database", "frontend", "infra", "other"]},
                            "required_skills": {"type": "array", "items": {"type": "string"}},
                            "estimated_complexity": {"type": "string", "enum": ["xs", "s", "m", "l", "xl"]},
                            "blocked_by": {"type": "array", "items": {"type": "string"}},
                            "acceptance_criteria": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["temp_id", "title"]
                    },
                    "description": "List of decomposed issues"
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Confidence score 0-1"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of decomposition approach"
                }
            },
            "required": ["decomposition_id", "goal_id", "issues"]
        }
    },
    {
        "name": "claudevn_submit_characterization",
        "description": "Submit characterization results for a work item back to serving",
        "inputSchema": {
            "type": "object",
            "properties": {
                "characterization_id": {
                    "type": "string",
                    "description": "Characterization ID assigned by serving"
                },
                "project_id": {
                    "type": "string",
                    "description": "Project this item belongs to"
                },
                "item_id": {
                    "type": "string",
                    "description": "Work item being characterized"
                },
                "ontology_tags": {
                    "type": "object",
                    "properties": {
                        "work_type": {
                            "type": "string",
                            "enum": ["feature", "bug_fix", "refactor", "test", "documentation", "infrastructure", "integration"],
                            "description": "Work type classification"
                        },
                        "lifecycle_stage": {
                            "type": "string",
                            "enum": ["design", "build", "test", "validate", "deploy"],
                            "description": "Lifecycle stage"
                        },
                        "technical_domains": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["frontend", "backend", "data", "api", "security", "devops", "testing", "documentation"]
                            },
                            "description": "Technical domains affected"
                        },
                        "cluster_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Project-specific cluster IDs"
                        }
                    },
                    "required": ["work_type", "lifecycle_stage", "technical_domains"],
                    "description": "Assigned ontology tags"
                },
                "meaning": {
                    "type": "object",
                    "properties": {
                        "business_summary": {
                            "type": "string",
                            "description": "Business value summary"
                        },
                        "business_user_impact": {
                            "type": "string",
                            "description": "How this affects end users"
                        },
                        "business_value": {
                            "type": "string",
                            "description": "Revenue, retention, compliance value"
                        },
                        "technical_summary": {
                            "type": "string",
                            "description": "Technical accomplishment summary"
                        },
                        "technical_components": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Components affected"
                        },
                        "technical_risk": {
                            "type": "string",
                            "description": "Complexity and unknowns assessment"
                        },
                        "contextual_summary": {
                            "type": "string",
                            "description": "Role in the broader project"
                        },
                        "contextual_role": {
                            "type": "string",
                            "enum": ["foundational", "incremental", "enabling", "blocking"],
                            "description": "Role in the project"
                        },
                        "related_work_summary": {
                            "type": "string",
                            "description": "Relationship to other work"
                        }
                    },
                    "required": ["business_summary", "technical_summary"],
                    "description": "Meaning assessments"
                },
                "dependencies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "target_item_id": {"type": "string", "description": "ID of the related work item"},
                            "relation": {
                                "type": "string",
                                "enum": ["blocks", "enables", "related_to", "extends", "conflicts_with"],
                                "description": "Relation type"
                            },
                            "dependency_type": {
                                "type": "string",
                                "enum": ["structural", "contextual"],
                                "description": "Structural or contextual"
                            },
                            "reasoning": {"type": "string", "description": "Why this relationship was identified"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1, "description": "Confidence 0-1"}
                        },
                        "required": ["target_item_id", "relation"]
                    },
                    "description": "Discovered contextual dependencies"
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Overall confidence 0-1"
                },
                "evaluated_in_isolation": {
                    "type": "boolean",
                    "description": "Was Frame 1 evaluation done"
                },
                "evaluated_in_context": {
                    "type": "boolean",
                    "description": "Was Frame 2 evaluation done"
                },
                "topology_item_count": {
                    "type": "integer",
                    "description": "Items in topology during evaluation"
                }
            },
            "required": ["characterization_id", "project_id", "item_id", "ontology_tags", "meaning"]
        }
    }
]


class MCPServer:
    """MCP Server that bridges stdio to HTTP API."""

    def __init__(self, serving_url: str, compute_id: str, api_key: str):
        """Initialize the MCP server.

        Args:
            serving_url: URL of the serving component
            compute_id: Compute instance ID
            api_key: API key for authentication
        """
        self.serving_url = serving_url.rstrip('/')
        self.compute_id = compute_id
        self.api_key = api_key
        self.initialized = False

    def _send_response(self, response: Dict[str, Any]) -> None:
        """Send a JSON-RPC response to stdout."""
        json_str = json.dumps(response)
        sys.stdout.write(json_str + '\n')
        sys.stdout.flush()
        logger.debug(f"Sent response: {json_str[:200]}...")

    def _send_error(self, request_id: Optional[Any], code: int, message: str,
                    data: Optional[Any] = None) -> None:
        """Send a JSON-RPC error response."""
        error: Dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        self._send_response({
            "jsonrpc": "2.0",
            "id": request_id,
            "error": error
        })

    def _send_result(self, request_id: Any, result: Any) -> None:
        """Send a JSON-RPC success response."""
        self._send_response({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        })

    def _call_http_api(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call the serving HTTP API for a tool.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            API response as dict
        """
        url = f"{self.serving_url}/api/v1/mcp/tools/call"
        payload = {
            "name": tool_name,
            "arguments": arguments
        }

        headers = {
            "Content-Type": "application/json",
            "X-Compute-ID": self.compute_id,
            "Authorization": f"Bearer {self.api_key}"
        }

        logger.info(f"Calling HTTP API: {tool_name}")
        logger.debug(f"URL: {url}, payload: {payload}")

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                logger.debug(f"API response: {result}")
                return result
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else str(e)
            logger.error(f"HTTP error {e.code}: {error_body}")
            return {
                "success": False,
                "error": {
                    "code": f"HTTP_{e.code}",
                    "message": f"HTTP error: {e.reason}",
                    "details": {"body": error_body}
                }
            }
        except urllib.error.URLError as e:
            logger.error(f"URL error: {e}")
            return {
                "success": False,
                "error": {
                    "code": "CONNECTION_ERROR",
                    "message": f"Failed to connect to serving: {e.reason}"
                }
            }
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(e)
                }
            }

    def handle_initialize(self, request_id: Any, params: Dict[str, Any]) -> None:
        """Handle the initialize request."""
        logger.info(f"Initialize request from: {params.get('clientInfo', {})}")

        self._send_result(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "claudevn-mcp-server",
                "version": "1.0.0"
            }
        })
        self.initialized = True

    def handle_tools_list(self, request_id: Any) -> None:
        """Handle tools/list request."""
        logger.info("Tools list request")
        self._send_result(request_id, {"tools": TOOLS})

    def handle_tools_call(self, request_id: Any, params: Dict[str, Any]) -> None:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        logger.info(f"Tool call: {tool_name}")

        # Validate tool exists
        tool_names = [t["name"] for t in TOOLS]
        if tool_name not in tool_names:
            self._send_error(request_id, -32602,
                            f"Unknown tool: {tool_name}",
                            {"available_tools": tool_names})
            return

        # Call the HTTP API
        response = self._call_http_api(tool_name, arguments)

        if response.get("success"):
            # Return result as text content
            self._send_result(request_id, {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(response.get("result", {}), indent=2)
                    }
                ]
            })
        else:
            error = response.get("error", {})
            self._send_result(request_id, {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({
                            "error": error.get("code", "UNKNOWN"),
                            "message": error.get("message", "Unknown error"),
                            "details": error.get("details")
                        }, indent=2)
                    }
                ],
                "isError": True
            })

    def handle_request(self, request: Dict[str, Any]) -> None:
        """Handle a single JSON-RPC request."""
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        logger.debug(f"Handling request: method={method}, id={request_id}")

        # Route to handler
        if method == "initialize":
            self.handle_initialize(request_id, params)
        elif method == "notifications/initialized":
            # This is a notification, no response needed
            logger.info("Received initialized notification")
        elif method == "tools/list":
            self.handle_tools_list(request_id)
        elif method == "tools/call":
            self.handle_tools_call(request_id, params)
        elif method == "ping":
            self._send_result(request_id, {})
        else:
            self._send_error(request_id, -32601, f"Method not found: {method}")

    def run(self) -> None:
        """Run the MCP server, reading from stdin."""
        logger.info(f"MCP Server starting (serving_url={self.serving_url})")

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                logger.debug(f"Received: {line[:200]}...")
                self.handle_request(request)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                self._send_error(None, -32700, f"Parse error: {e}")
            except Exception as e:
                logger.error(f"Error handling request: {e}", exc_info=True)
                self._send_error(None, -32603, f"Internal error: {e}")

        logger.info("MCP Server shutting down (stdin closed)")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="ClaudeVN MCP Server")
    parser.add_argument(
        "--serving-url",
        default=os.environ.get("CLAUDEVN_SERVING_URL", "http://localhost:8002"),
        help="URL of the serving component"
    )
    parser.add_argument(
        "--compute-id",
        default=os.environ.get("CLAUDEVN_COMPUTE_ID", ""),
        help="Compute instance ID"
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("CLAUDEVN_API_KEY", ""),
        help="API key for authentication"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.compute_id:
        logger.error("CLAUDEVN_COMPUTE_ID environment variable or --compute-id required")
        sys.exit(1)

    if not args.api_key:
        logger.error("CLAUDEVN_API_KEY environment variable or --api-key required")
        sys.exit(1)

    server = MCPServer(
        serving_url=args.serving_url,
        compute_id=args.compute_id,
        api_key=args.api_key
    )
    server.run()


if __name__ == "__main__":
    main()
