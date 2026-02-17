# MCP Server Implementation

HTTP-based MCP (Model Context Protocol) server for ClaudeVN compute communication.

## Overview

This module implements the MCP server that allows Claude Code compute instances to communicate with the ClaudeVN Serving component. It exposes 7 tools for task management, progress reporting, and persona retrieval.

## Architecture

```
serving/mcp/
├── __init__.py          # Module exports
├── server.py            # FastAPI router with MCP endpoints
├── models.py            # Pydantic request/response models
├── auth.py              # API key authentication
├── test_mcp.py          # Test suite
└── tools/               # Tool implementations
    ├── __init__.py
    ├── assignment.py    # claudevn_get_assignment
    ├── progress.py      # claudevn_report_progress
    ├── review.py        # claudevn_request_review
    ├── context.py       # claudevn_get_context
    ├── blocker.py       # claudevn_signal_blocker
    ├── complete.py      # claudevn_complete_task
    └── persona.py       # claudevn_get_persona
```

## API Endpoints

### Main MCP Endpoint

**POST** `/api/v1/mcp/tools/call`

Execute an MCP tool call.

**Headers:**
- `Authorization: Bearer <api_key>`
- `X-Compute-ID: <compute_instance_id>`

**Request Body:**
```json
{
  "name": "claudevn_get_assignment",
  "arguments": {
    "compute_id": "compute-001"
  }
}
```

**Response:**
```json
{
  "success": true,
  "result": {
    "task_id": "task-123",
    "title": "Implement feature X",
    "description": "...",
    "persona": "code-writer",
    "branch_name": "f/feature-x/compute-001"
  }
}
```

### List Available Tools

**GET** `/api/v1/mcp/tools/list`

Returns list of available MCP tools with descriptions.

### Health Check

**GET** `/api/v1/mcp/health`

Returns MCP server health status.

## Tools

### 1. claudevn_get_assignment

Get next task assignment for a compute instance.

**Status:** Stub (Work Map integration pending)

**Input:**
- `compute_id` (string): Compute instance ID
- `capabilities` (list, optional): Filter by capabilities

**Output:**
- `task_id`: Unique task identifier
- `title`: Task title
- `description`: Task description
- `persona`: Persona ID to use
- `branch_name`: Suggested branch name
- `context`: Additional context
- `dependencies`: Task dependencies

### 2. claudevn_report_progress

Report task progress and status updates.

**Status:** Stub (Work Map integration pending)

**Input:**
- `task_id` (string): Task being updated
- `status` (enum): started | in_progress | blocked | review_requested | completed
- `progress_percent` (int, optional): 0-100
- `message` (string, optional): Status message
- `commits` (list, optional): Commit SHAs

**Output:**
- `acknowledged`: boolean
- `task_id`: Task ID
- `updated_at`: Timestamp

### 3. claudevn_request_review

Request code review and merge for a branch.

**Status:** Integrated with Git PR service

**Input:**
- `branch` (string): Branch name
- `task_id` (string): Associated task ID
- `title` (string, optional): PR title
- `description` (string, optional): PR description
- `test_results` (object, optional): Test results

**Output:**
- `pr_id`: Pull request ID
- `branch`: Branch name
- `status`: PR status
- `queue_position`: Position in review queue

### 4. claudevn_get_context

Fetch relevant context for a task (files, history, related tasks).

**Status:** Stub (Work Map integration pending)

**Input:**
- `task_id` (string): Task to get context for
- `context_types` (list, optional): files | history | related_tasks | dependencies | all
- `file_patterns` (list, optional): Glob patterns

**Output:**
- `task`: Task details
- `relevant_files`: List of relevant files
- `related_tasks`: Related tasks
- `recent_commits`: Recent commit history

### 5. claudevn_signal_blocker

Signal a blocker preventing task completion.

**Status:** Stub (Work Map integration pending)

**Input:**
- `task_id` (string): Task that is blocked
- `blocker_type` (enum): dependency | clarification | access | technical | other
- `description` (string): Blocker description
- `suggested_resolution` (string, optional): How to resolve
- `blocking_task_id` (string, optional): ID of blocking task

**Output:**
- `acknowledged`: boolean
- `blocker_id`: Blocker identifier
- `resolution_task_id`: New task created to resolve (if applicable)
- `status`: Blocker status

### 6. claudevn_complete_task

Complete a task and request merge.

**Status:** Stub (Work Map integration pending)

**Input:**
- `task_id` (string): Task being completed
- `branch` (string): Branch with the work
- `summary` (string): Work summary
- `deliverables` (list, optional): List of deliverables
- `test_results` (object, optional): Test results

**Output:**
- `task_id`: Task ID
- `status`: Completion status
- `merge_status`: queued | merged | conflict | review_required
- `next_task`: Next assignment (if available)

### 7. claudevn_get_persona

Fetch persona/skill definition (CLAUDE.md content).

**Status:** Fully implemented - integrates with Marketplace service

**Input:**
- `persona_id` (string): Persona identifier

**Output:**
- `persona_id`: Persona ID
- `name`: Persona name
- `claude_md_content`: Full CLAUDE.md content
- `capabilities`: List of capabilities

## Authentication

API key based authentication with compute instance identification.

**Headers Required:**
- `Authorization: Bearer <api_key>`
- `X-Compute-ID: <compute_id>`

**Development Mode:**
If no API keys are registered, the server allows any key (with warning log).

**Production:**
API keys must be registered via `register_compute_key(compute_id, api_key)`.

## Error Handling

All tools return a tuple: `(result, error)`

**Error Response Format:**
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": {
      "additional": "context"
    }
  }
}
```

**Error Codes:**
- `UNKNOWN_TOOL`: Tool not found
- `INVALID_INPUT`: Invalid arguments
- `INTERNAL_ERROR`: Server-side error
- `PERSONA_NOT_FOUND`: Persona doesn't exist
- `MISSING_AUTH`: Missing authentication
- `INVALID_AUTH`: Invalid authentication
- `UNKNOWN_COMPUTE`: Compute not registered

## Integration Status

| Tool | Status | Integration |
|------|--------|-------------|
| get_assignment | Stub | Needs Work Map service |
| report_progress | Stub | Needs Work Map service |
| request_review | ✅ Working | Integrated with Git PR service |
| get_context | Stub | Needs Work Map service |
| signal_blocker | Stub | Needs Work Map service |
| complete_task | Stub | Needs Work Map service |
| get_persona | ✅ Working | Integrated with Marketplace service |

## Testing

Run the test suite:

```bash
cd serving
python3 mcp/test_mcp.py
```

The test suite validates:
- Tool execution
- Request/response models
- Error handling
- Stub implementations

## Future Work

1. **Work Map Integration**: Replace stubs in assignment, progress, context, blocker, and complete tools
2. **Enhanced Authentication**: Integrate with proper key management system
3. **Rate Limiting**: Add rate limiting per compute instance
4. **Metrics**: Add tool usage metrics and performance monitoring
5. **WebSocket Support**: Consider WebSocket transport for real-time updates

## Related Documentation

- [MCP Tools Specification](/docs/design/specifications/mcp-tools.md)
- [v1.0 Architecture](/docs/design/architecture/v1.0-architecture.md)
- [Git Infrastructure](/docs/design/specifications/git-infrastructure.md)
