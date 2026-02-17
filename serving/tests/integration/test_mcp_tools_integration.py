"""
Integration Tests for MCP Tool Progress Reporting (Issue #285)
==============================================================

Tests MCP tool-based progress reporting and work management:
1. claudevn_report_progress updates work status
2. claudevn_complete_task completes work correctly
3. claudevn_get_assignment returns work assignment
4. claudevn_signal_blocker creates blockers
5. Status transitions match expected flow
6. Error handling for invalid MCP requests

Prerequisites:
    - Running Docker containers: claudevn-serving, claudevn-redis, claudevn-marketplace
    - MCP server available at /api/v1/mcp/tools/call

Run with:
    ./scripts/run_integration_tests.sh
    pytest serving/tests/integration/test_mcp_tools_integration.py -v
"""

import os
import pytest
import uuid

import httpx

# Test configuration from environment or defaults
SERVING_BASE_URL = os.getenv("SERVING_BASE_URL", "http://localhost:8002")
API_PREFIX = "/api/v1"
MCP_ENDPOINT = f"{API_PREFIX}/mcp/tools/call"


def generate_test_id() -> str:
    """Generate a unique test identifier."""
    return uuid.uuid4().hex[:8]


def get_mcp_headers(compute_id: str, api_key: str = "test-key") -> dict:
    """Get headers required for MCP tool calls."""
    return {
        "Authorization": f"Bearer {api_key}",
        "X-Compute-ID": compute_id,
        "Content-Type": "application/json"
    }


async def call_mcp_tool(
    client: httpx.AsyncClient,
    tool_name: str,
    arguments: dict,
    compute_id: str,
    api_key: str = "test-key"
) -> httpx.Response:
    """Make an MCP tool call."""
    return await client.post(
        MCP_ENDPOINT,
        json={
            "name": tool_name,
            "arguments": arguments
        },
        headers=get_mcp_headers(compute_id, api_key)
    )


# =============================================================================
# Module-level Fixtures
# =============================================================================

@pytest.fixture
async def http_client():
    """Create HTTP client for API calls."""
    async with httpx.AsyncClient(
        base_url=SERVING_BASE_URL,
        timeout=30.0
    ) as client:
        yield client


@pytest.fixture
async def test_project(http_client):
    """Create a test project for work items with cleanup."""
    project_id = f"project-mcp-test-{generate_test_id()}"
    response = await http_client.post(
        f"{API_PREFIX}/projects",
        json={
            "project_id": project_id,
            "name": f"MCP Tools Test Project {project_id}",
            "description": "Project for MCP tools integration tests"
        }
    )
    if response.status_code not in [200, 201, 409]:
        pytest.skip(f"Could not create test project: {response.status_code}")

    yield project_id

    # Cleanup: attempt to delete project
    try:
        await http_client.delete(f"{API_PREFIX}/projects/{project_id}")
    except Exception:
        pass


@pytest.fixture
async def assigned_work(http_client, test_project):
    """Create and assign work for MCP tool testing."""
    test_id = generate_test_id()
    compute_id = f"test-compute-{test_id}"

    # Create work
    work_data = {
        "title": f"MCP tool test work {test_id}",
        "description": "Testing MCP tool progress reporting",
        "project_id": test_project,
        "work_type": "feature"
    }
    response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
    if response.status_code != 201:
        pytest.skip(f"Could not create work: {response.status_code}")
    work = response.json()
    work_id = work["work_id"]

    # Assign to compute
    assign_response = await http_client.post(
        f"{API_PREFIX}/work/{work_id}/assign",
        params={"compute_id": compute_id}
    )
    if assign_response.status_code != 200:
        await http_client.delete(f"{API_PREFIX}/work/{work_id}")
        pytest.skip(f"Could not assign work: {assign_response.status_code}")

    yield {
        "work_id": work_id,
        "compute_id": compute_id,
        "branch_name": work.get("branch_name", f"work/{work_id}")
    }

    # Cleanup
    try:
        await http_client.delete(f"{API_PREFIX}/work/{work_id}")
    except Exception:
        pass


# =============================================================================
# Test Classes
# =============================================================================

class TestMCPServerHealth:
    """Test MCP server availability and basic operations."""

    @pytest.mark.asyncio
    async def test_mcp_health_endpoint(self, http_client):
        """Test that MCP health endpoint is accessible."""
        response = await http_client.get(f"{API_PREFIX}/mcp/health")
        if response.status_code != 200:
            pytest.skip(f"MCP server not available: {response.status_code}")

        health = response.json()
        assert health.get("status") == "healthy"
        assert health.get("tools_available", 0) > 0

    @pytest.mark.asyncio
    async def test_mcp_tools_list(self, http_client):
        """Test that MCP tools list endpoint returns available tools."""
        response = await http_client.get(f"{API_PREFIX}/mcp/tools/list")
        if response.status_code != 200:
            pytest.skip(f"MCP tools list not available: {response.status_code}")

        tools_data = response.json()
        assert "tools" in tools_data

        # Verify expected tools are available (per issue #285 acceptance criteria)
        tool_names = [t["name"] for t in tools_data["tools"]]
        expected_tools = [
            "claudevn_report_progress",
            "claudevn_complete_task",
            "claudevn_get_assignment",
            "claudevn_signal_blocker"
        ]
        for tool in expected_tools:
            assert tool in tool_names, f"Expected tool {tool} not found"


class TestMCPAuthentication:
    """Test MCP authentication requirements."""

    @pytest.mark.asyncio
    async def test_mcp_call_requires_auth_header(self, http_client):
        """Test that MCP calls require Authorization header."""
        response = await http_client.post(
            MCP_ENDPOINT,
            json={
                "name": "claudevn_report_progress",
                "arguments": {"task_id": "test", "status": "in_progress"}
            },
            headers={"X-Compute-ID": "test-compute"}  # Missing Authorization
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_mcp_call_requires_compute_id_header(self, http_client):
        """Test that MCP calls require X-Compute-ID header."""
        response = await http_client.post(
            MCP_ENDPOINT,
            json={
                "name": "claudevn_report_progress",
                "arguments": {"task_id": "test", "status": "in_progress"}
            },
            headers={"Authorization": "Bearer test-key"}  # Missing X-Compute-ID
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_mcp_call_requires_bearer_format(self, http_client):
        """Test that MCP calls require Bearer token format."""
        response = await http_client.post(
            MCP_ENDPOINT,
            json={
                "name": "claudevn_report_progress",
                "arguments": {"task_id": "test", "status": "in_progress"}
            },
            headers={
                "Authorization": "Basic test-key",  # Wrong format
                "X-Compute-ID": "test-compute"
            }
        )
        assert response.status_code == 401


class TestMCPReportProgress:
    """Test claudevn_report_progress MCP tool."""

    @pytest.mark.asyncio
    async def test_report_progress_updates_work_status(
        self, http_client, assigned_work
    ):
        """Test that report_progress updates work status to in_progress.

        Verifies acceptance criteria #1: MCP claudevn_report_progress tool
        updates work status.
        """
        work_id = assigned_work["work_id"]
        compute_id = assigned_work["compute_id"]

        # Call MCP tool to report progress
        response = await call_mcp_tool(
            http_client,
            "claudevn_report_progress",
            {
                "task_id": work_id,
                "status": "in_progress",
                "progress_percent": 25,
                "message": "Started working on feature"
            },
            compute_id
        )
        assert response.status_code == 200

        mcp_response = response.json()
        assert mcp_response["success"] is True
        assert mcp_response["result"]["acknowledged"] is True
        assert mcp_response["result"]["task_id"] == work_id

        # Verify work status was updated via REST API
        get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
        assert get_response.status_code == 200
        work = get_response.json()
        assert work["status"] == "in_progress"
        assert work["progress_percent"] == 25

    @pytest.mark.asyncio
    async def test_report_progress_with_started_status(
        self, http_client, assigned_work
    ):
        """Test that 'started' status maps to in_progress."""
        work_id = assigned_work["work_id"]
        compute_id = assigned_work["compute_id"]

        response = await call_mcp_tool(
            http_client,
            "claudevn_report_progress",
            {
                "task_id": work_id,
                "status": "started",
                "message": "Beginning work"
            },
            compute_id
        )
        assert response.status_code == 200

        mcp_response = response.json()
        assert mcp_response["success"] is True

        # Verify status
        get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
        work = get_response.json()
        assert work["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_report_progress_incremental_updates(
        self, http_client, assigned_work
    ):
        """Test multiple progress updates with increasing percentages."""
        work_id = assigned_work["work_id"]
        compute_id = assigned_work["compute_id"]

        # Report progress at 25%, 50%, 75%
        for percent in [25, 50, 75]:
            response = await call_mcp_tool(
                http_client,
                "claudevn_report_progress",
                {
                    "task_id": work_id,
                    "status": "in_progress",
                    "progress_percent": percent,
                    "message": f"Progress at {percent}%"
                },
                compute_id
            )
            assert response.status_code == 200
            assert response.json()["success"] is True

        # Verify final progress
        get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
        work = get_response.json()
        assert work["progress_percent"] == 75

    @pytest.mark.asyncio
    async def test_report_progress_with_commits(
        self, http_client, assigned_work
    ):
        """Test that commits field is accepted in progress report."""
        work_id = assigned_work["work_id"]
        compute_id = assigned_work["compute_id"]

        response = await call_mcp_tool(
            http_client,
            "claudevn_report_progress",
            {
                "task_id": work_id,
                "status": "in_progress",
                "progress_percent": 50,
                "commits": ["abc123", "def456"]
            },
            compute_id
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_report_progress_invalid_task_id(self, http_client):
        """Test error handling for non-existent task ID.

        Verifies acceptance criteria #6: Error handling for invalid MCP requests.
        """
        compute_id = f"test-compute-{generate_test_id()}"

        response = await call_mcp_tool(
            http_client,
            "claudevn_report_progress",
            {
                "task_id": "nonexistent-task-xyz123",
                "status": "in_progress"
            },
            compute_id
        )
        assert response.status_code == 200

        mcp_response = response.json()
        assert mcp_response["success"] is False
        assert mcp_response["error"]["code"] == "TASK_NOT_FOUND"


class TestMCPSignalBlocker:
    """Test claudevn_signal_blocker MCP tool."""

    @pytest.mark.asyncio
    async def test_signal_blocker_creates_blocker(
        self, http_client, assigned_work
    ):
        """Test that signal_blocker creates a blocker on work.

        Verifies acceptance criteria #4: MCP claudevn_signal_blocker tool
        creates blockers.
        """
        work_id = assigned_work["work_id"]
        compute_id = assigned_work["compute_id"]

        # First set work to in_progress
        await call_mcp_tool(
            http_client,
            "claudevn_report_progress",
            {"task_id": work_id, "status": "in_progress"},
            compute_id
        )

        # Signal a blocker
        response = await call_mcp_tool(
            http_client,
            "claudevn_signal_blocker",
            {
                "task_id": work_id,
                "blocker_type": "technical",
                "description": "Missing dependency library",
                "suggested_resolution": "Install missing package"
            },
            compute_id
        )
        assert response.status_code == 200

        mcp_response = response.json()
        assert mcp_response["success"] is True
        assert mcp_response["result"]["acknowledged"] is True
        assert "blocker_id" in mcp_response["result"]

        # Verify blocker was created via REST API
        get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
        work = get_response.json()
        assert len(work.get("blockers", [])) > 0
        blocker = work["blockers"][0]
        assert blocker["blocker_type"] == "technical"

    @pytest.mark.asyncio
    async def test_signal_blocker_dependency_type(
        self, http_client, assigned_work
    ):
        """Test dependency blocker type with blocking_task_id."""
        work_id = assigned_work["work_id"]
        compute_id = assigned_work["compute_id"]

        # Set work to in_progress first
        await call_mcp_tool(
            http_client,
            "claudevn_report_progress",
            {"task_id": work_id, "status": "in_progress"},
            compute_id
        )

        # Signal a dependency blocker
        response = await call_mcp_tool(
            http_client,
            "claudevn_signal_blocker",
            {
                "task_id": work_id,
                "blocker_type": "dependency",
                "description": "Waiting for API changes",
                "blocking_task_id": "other-task-123"
            },
            compute_id
        )
        assert response.status_code == 200

        mcp_response = response.json()
        assert mcp_response["success"] is True

    @pytest.mark.asyncio
    async def test_signal_blocker_all_types(self, http_client, test_project):
        """Test all blocker types are accepted."""
        blocker_types = ["dependency", "clarification", "access", "technical", "other"]

        for blocker_type in blocker_types:
            test_id = generate_test_id()
            compute_id = f"test-compute-{test_id}"

            # Create and assign work
            work_data = {
                "title": f"Blocker type test {test_id}",
                "description": f"Testing {blocker_type} blocker",
                "project_id": test_project
            }
            create_response = await http_client.post(
                f"{API_PREFIX}/work", json=work_data
            )
            if create_response.status_code != 201:
                continue

            work = create_response.json()
            work_id = work["work_id"]

            try:
                # Assign work
                await http_client.post(
                    f"{API_PREFIX}/work/{work_id}/assign",
                    params={"compute_id": compute_id}
                )

                # Set to in_progress
                await call_mcp_tool(
                    http_client,
                    "claudevn_report_progress",
                    {"task_id": work_id, "status": "in_progress"},
                    compute_id
                )

                # Signal blocker
                response = await call_mcp_tool(
                    http_client,
                    "claudevn_signal_blocker",
                    {
                        "task_id": work_id,
                        "blocker_type": blocker_type,
                        "description": f"Test {blocker_type} blocker"
                    },
                    compute_id
                )

                assert response.status_code == 200, f"Failed for {blocker_type}"
                assert response.json()["success"] is True, f"Failed for {blocker_type}"

            finally:
                await http_client.delete(f"{API_PREFIX}/work/{work_id}")


class TestMCPCompleteTask:
    """Test claudevn_complete_task MCP tool."""

    @pytest.mark.asyncio
    async def test_complete_task_sets_completed_status(
        self, http_client, assigned_work
    ):
        """Test that complete_task sets work to completed status.

        Verifies acceptance criteria #2: MCP claudevn_complete_task tool
        completes work correctly.
        """
        work_id = assigned_work["work_id"]
        compute_id = assigned_work["compute_id"]
        branch_name = assigned_work["branch_name"]

        # First set work to in_progress
        await call_mcp_tool(
            http_client,
            "claudevn_report_progress",
            {"task_id": work_id, "status": "in_progress", "progress_percent": 50},
            compute_id
        )

        # Complete the task
        response = await call_mcp_tool(
            http_client,
            "claudevn_complete_task",
            {
                "task_id": work_id,
                "branch": branch_name,
                "summary": "Implemented feature successfully",
                "deliverables": ["file1.py", "file2.py"],
                "test_results": {"passed": 10, "failed": 0}
            },
            compute_id
        )
        assert response.status_code == 200

        mcp_response = response.json()
        assert mcp_response["success"] is True
        assert mcp_response["result"]["task_id"] == work_id
        assert mcp_response["result"]["status"] == "completed"
        # merge_status depends on Git state, accept any valid value
        assert mcp_response["result"]["merge_status"] in [
            "queued", "merged", "conflict", "review_required"
        ]

        # Verify work is completed via REST API
        get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
        work = get_response.json()
        assert work["status"] == "completed"

    @pytest.mark.asyncio
    async def test_complete_task_returns_next_assignment(
        self, http_client, test_project
    ):
        """Test that complete_task may return next task assignment."""
        test_id = generate_test_id()
        compute_id = f"test-compute-{test_id}"

        # Create two work items
        work1_response = await http_client.post(
            f"{API_PREFIX}/work",
            json={
                "title": f"First work {test_id}",
                "description": "First work item",
                "project_id": test_project
            }
        )
        work1 = work1_response.json()
        work1_id = work1["work_id"]

        work2_response = await http_client.post(
            f"{API_PREFIX}/work",
            json={
                "title": f"Second work {test_id}",
                "description": "Second work item",
                "project_id": test_project
            }
        )
        work2 = work2_response.json()
        work2_id = work2["work_id"]

        try:
            # Assign first work
            await http_client.post(
                f"{API_PREFIX}/work/{work1_id}/assign",
                params={"compute_id": compute_id}
            )

            # Progress and complete first work
            await call_mcp_tool(
                http_client,
                "claudevn_report_progress",
                {"task_id": work1_id, "status": "in_progress"},
                compute_id
            )

            response = await call_mcp_tool(
                http_client,
                "claudevn_complete_task",
                {
                    "task_id": work1_id,
                    "branch": work1.get("branch_name", f"work/{work1_id}"),
                    "summary": "Completed first task"
                },
                compute_id
            )

            assert response.status_code == 200
            mcp_response = response.json()
            assert mcp_response["success"] is True

            # next_task may or may not be present depending on orchestrator
            # Just verify the response structure is valid

        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work1_id}")
            await http_client.delete(f"{API_PREFIX}/work/{work2_id}")


class TestMCPGetAssignment:
    """Test claudevn_get_assignment MCP tool."""

    @pytest.mark.asyncio
    async def test_get_assignment_returns_pending_work(
        self, http_client, test_project
    ):
        """Test that get_assignment returns available work.

        Verifies acceptance criteria #3: MCP claudevn_get_assignment tool
        returns work assignment.
        """
        test_id = generate_test_id()
        compute_id = f"test-compute-{test_id}"

        # Create work item
        work_response = await http_client.post(
            f"{API_PREFIX}/work",
            json={
                "title": f"Assignment test {test_id}",
                "description": "Testing get_assignment tool",
                "project_id": test_project,
                "required_capabilities": ["python"]
            }
        )
        work = work_response.json()
        work_id = work["work_id"]

        try:
            # Request assignment via MCP
            response = await call_mcp_tool(
                http_client,
                "claudevn_get_assignment",
                {
                    "compute_id": compute_id,
                    "capabilities": ["python"]
                },
                compute_id
            )
            assert response.status_code == 200

            mcp_response = response.json()
            # May or may not have work available depending on orchestrator state
            if mcp_response["success"]:
                result = mcp_response["result"]
                assert "task_id" in result
                assert "title" in result
                assert "branch_name" in result
            else:
                # NO_WORK_AVAILABLE is acceptable
                assert mcp_response["error"]["code"] in [
                    "NO_WORK_AVAILABLE", "SERVICE_UNAVAILABLE"
                ]

        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")

    @pytest.mark.asyncio
    async def test_get_assignment_no_work_available(self, http_client):
        """Test get_assignment when no work is available."""
        compute_id = f"test-compute-{generate_test_id()}"

        response = await call_mcp_tool(
            http_client,
            "claudevn_get_assignment",
            {
                "compute_id": compute_id,
                "capabilities": ["nonexistent-capability-xyz"]
            },
            compute_id
        )
        assert response.status_code == 200

        mcp_response = response.json()
        # Either no work or service unavailable is acceptable
        if not mcp_response["success"]:
            assert mcp_response["error"]["code"] in [
                "NO_WORK_AVAILABLE", "SERVICE_UNAVAILABLE"
            ]


class TestMCPStatusTransitions:
    """Test status transition flow via MCP tools.

    Verifies acceptance criteria #5: Status transitions match expected flow.
    """

    @pytest.mark.asyncio
    async def test_full_status_flow_via_mcp(
        self, http_client, assigned_work
    ):
        """Test complete status flow: assigned -> started -> in_progress -> completed."""
        work_id = assigned_work["work_id"]
        compute_id = assigned_work["compute_id"]
        branch_name = assigned_work["branch_name"]

        # Verify initial state (assigned)
        get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
        assert get_response.json()["status"] == "assigned"

        # Transition to started (maps to in_progress)
        response = await call_mcp_tool(
            http_client,
            "claudevn_report_progress",
            {"task_id": work_id, "status": "started"},
            compute_id
        )
        assert response.json()["success"] is True

        get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
        assert get_response.json()["status"] == "in_progress"

        # Report incremental progress
        for percent in [25, 50, 75]:
            response = await call_mcp_tool(
                http_client,
                "claudevn_report_progress",
                {
                    "task_id": work_id,
                    "status": "in_progress",
                    "progress_percent": percent
                },
                compute_id
            )
            assert response.json()["success"] is True

        # Complete the task
        response = await call_mcp_tool(
            http_client,
            "claudevn_complete_task",
            {
                "task_id": work_id,
                "branch": branch_name,
                "summary": "Completed via MCP status flow test"
            },
            compute_id
        )
        assert response.json()["success"] is True

        # Verify final state
        get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
        assert get_response.json()["status"] == "completed"

    @pytest.mark.asyncio
    async def test_blocked_status_transition(
        self, http_client, assigned_work
    ):
        """Test transition to blocked status via signal_blocker."""
        work_id = assigned_work["work_id"]
        compute_id = assigned_work["compute_id"]

        # Start work
        await call_mcp_tool(
            http_client,
            "claudevn_report_progress",
            {"task_id": work_id, "status": "in_progress"},
            compute_id
        )

        # Signal blocker
        response = await call_mcp_tool(
            http_client,
            "claudevn_signal_blocker",
            {
                "task_id": work_id,
                "blocker_type": "clarification",
                "description": "Need clarification on requirements"
            },
            compute_id
        )
        assert response.json()["success"] is True

        # Work should have blocker (status may or may not change to blocked
        # depending on implementation)
        get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
        work = get_response.json()
        assert len(work.get("blockers", [])) > 0


class TestMCPErrorHandling:
    """Test error handling for invalid MCP requests.

    Verifies acceptance criteria #6: Error handling for invalid MCP requests.
    """

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, http_client):
        """Test that calling an unknown tool returns an error."""
        compute_id = f"test-compute-{generate_test_id()}"

        response = await call_mcp_tool(
            http_client,
            "claudevn_nonexistent_tool",
            {"some_arg": "value"},
            compute_id
        )
        assert response.status_code == 200

        mcp_response = response.json()
        assert mcp_response["success"] is False
        assert mcp_response["error"]["code"] == "UNKNOWN_TOOL"

    @pytest.mark.asyncio
    async def test_invalid_arguments_returns_error(self, http_client):
        """Test that invalid arguments return a validation error."""
        compute_id = f"test-compute-{generate_test_id()}"

        response = await call_mcp_tool(
            http_client,
            "claudevn_report_progress",
            {
                # Missing required 'task_id' and 'status'
                "progress_percent": 50
            },
            compute_id
        )
        assert response.status_code == 200

        mcp_response = response.json()
        assert mcp_response["success"] is False
        assert mcp_response["error"]["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_invalid_status_enum_returns_error(self, http_client):
        """Test that invalid status value returns a validation error."""
        compute_id = f"test-compute-{generate_test_id()}"

        response = await call_mcp_tool(
            http_client,
            "claudevn_report_progress",
            {
                "task_id": "test-task",
                "status": "invalid_status_value"
            },
            compute_id
        )
        assert response.status_code == 200

        mcp_response = response.json()
        assert mcp_response["success"] is False
        assert mcp_response["error"]["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_invalid_blocker_type_returns_error(self, http_client):
        """Test that invalid blocker type returns a validation error."""
        compute_id = f"test-compute-{generate_test_id()}"

        response = await call_mcp_tool(
            http_client,
            "claudevn_signal_blocker",
            {
                "task_id": "test-task",
                "blocker_type": "invalid_type",
                "description": "Test blocker"
            },
            compute_id
        )
        assert response.status_code == 200

        mcp_response = response.json()
        assert mcp_response["success"] is False
        assert mcp_response["error"]["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_progress_percent_above_100_returns_error(self, http_client):
        """Test that progress_percent > 100 returns validation error."""
        compute_id = f"test-compute-{generate_test_id()}"

        response = await call_mcp_tool(
            http_client,
            "claudevn_report_progress",
            {
                "task_id": "test-task",
                "status": "in_progress",
                "progress_percent": 150  # Invalid: > 100
            },
            compute_id
        )
        assert response.status_code == 200

        mcp_response = response.json()
        assert mcp_response["success"] is False
        assert mcp_response["error"]["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_progress_percent_below_0_returns_error(self, http_client):
        """Test that progress_percent < 0 returns validation error."""
        compute_id = f"test-compute-{generate_test_id()}"

        response = await call_mcp_tool(
            http_client,
            "claudevn_report_progress",
            {
                "task_id": "test-task",
                "status": "in_progress",
                "progress_percent": -10  # Invalid: < 0
            },
            compute_id
        )
        assert response.status_code == 200

        mcp_response = response.json()
        assert mcp_response["success"] is False
        assert mcp_response["error"]["code"] == "INVALID_INPUT"


# =============================================================================
# Test Runner
# =============================================================================

if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("Integration Tests for MCP Tool Progress Reporting (#285)")
    print("=" * 70)
    print()
    print("Prerequisites:")
    print(f"  - Serving service running at {SERVING_BASE_URL}")
    print(f"  - MCP endpoint at {MCP_ENDPOINT}")
    print()
    print("Running tests...")
    print()

    sys.exit(pytest.main([__file__, "-v", "-s"]))
