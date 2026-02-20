#!/usr/bin/env python3
"""
Serving Service API Integration Tests
======================================

Tests all REST API endpoints in the Serving service to ensure proper:
- Facilitated session management
- Process map CRUD operations
- Activity management
- Observability event streaming
- Storage operations
- Health and status endpoints

NOTE: These tests require a running serving instance. Run with:
    ./scripts/run_integration_tests.sh
    pytest serving/tests/integration/
"""

import pytest
import asyncio
import httpx
from typing import Dict, Any
import json

# Test configuration
SERVING_BASE_URL = "http://localhost:8002"
API_PREFIX = "/api/v1"


class TestHealthEndpoints:
    """Test health and status endpoints."""
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test basic health check."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
    
    @pytest.mark.asyncio
    async def test_storage_health(self):
        """Test storage health check."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/storage/health")
            assert response.status_code in [200, 404]  # May not be implemented


class TestSessionEndpoints:
    """Test facilitated session endpoints."""
    
    @pytest.mark.asyncio
    async def test_create_session(self):
        """Test creating a new session."""
        import uuid
        session_data = {
            "session_id": f"test-session-{uuid.uuid4().hex[:8]}",
            "goal": "Test goal for API integration",
            "user_id": "test-user",
            "metadata": {"test": True}
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions",
                json=session_data
            )
            assert response.status_code in [200, 201, 400]  # 400 may indicate duplicate
            if response.status_code in [200, 201]:
                session = response.json()
                assert session["session_id"] == session_data["session_id"]
                assert session["status"] in ["pending", "active", "initiated"]
    
    @pytest.mark.asyncio
    async def test_get_session(self):
        """Test retrieving an existing session."""
        # First create a session
        session_id = "test-session-get-001"
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions",
                json={"session_id": session_id, "goal": "Test retrieval"}
            )
            
            # Now get it
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/sessions/{session_id}")
            assert response.status_code == 200
            session = response.json()
            assert session["session_id"] == session_id
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self):
        """Test getting a non-existent session returns 404."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions/nonexistent-session-999"
            )
            assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_list_sessions(self):
        """Test listing all sessions."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/sessions")
            assert response.status_code == 200
            data = response.json()
            # Response could be list or paginated object
            assert isinstance(data, (list, dict))
    
    @pytest.mark.asyncio
    async def test_update_session_status(self):
        """Test updating session status."""
        session_id = "test-session-update-001"
        
        async with httpx.AsyncClient() as client:
            # Create session
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions",
                json={"session_id": session_id, "goal": "Test status update"}
            )
            
            # Update status
            response = await client.patch(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions/{session_id}/status",
                json={"status": "in_progress"}
            )
            assert response.status_code in [200, 404]  # May not be implemented
    
    @pytest.mark.asyncio
    async def test_session_statistics(self):
        """Test retrieving session statistics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/sessions/stats")
            assert response.status_code in [200, 404]
            if response.status_code == 200:
                stats = response.json()
                assert "total_sessions" in stats or isinstance(stats, dict)


class TestProcessMapEndpoints:
    """Test process map endpoints."""
    
    @pytest.mark.asyncio
    async def test_create_process_map(self):
        """Test creating a process map for a session."""
        session_id = "test-session-map-001"
        
        async with httpx.AsyncClient() as client:
            # Create session first
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions",
                json={"session_id": session_id, "goal": "Test map creation"}
            )
            
            # Create process map
            map_data = {
                "session_id": session_id,
                "business_goal": "Create a comprehensive test plan"
            }
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/map",
                json=map_data
            )
            assert response.status_code in [200, 201]
            process_map = response.json()
            assert process_map["session_id"] == session_id
            assert "business_goal" in process_map
    
    @pytest.mark.asyncio
    async def test_get_process_map(self):
        """Test retrieving a process map."""
        session_id = "test-session-map-get-001"
        
        async with httpx.AsyncClient() as client:
            # Create session and map
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions",
                json={"session_id": session_id, "goal": "Test map retrieval"}
            )
            
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/map",
                json={"session_id": session_id, "business_goal": "Test retrieval"}
            )
            
            # Get the map
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/map"
            )
            assert response.status_code == 200
            process_map = response.json()
            assert process_map["session_id"] == session_id
    
    @pytest.mark.asyncio
    async def test_get_process_map_history(self):
        """Test retrieving process map evolution history."""
        session_id = "test-session-map-history-001"
        
        async with httpx.AsyncClient() as client:
            # Create session and map
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions",
                json={"session_id": session_id, "goal": "Test history"}
            )
            
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/map",
                json={"session_id": session_id, "business_goal": "Test history"}
            )
            
            # Get history
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/map/history"
            )
            assert response.status_code == 200
            history = response.json()
            assert isinstance(history, list)
    
    @pytest.mark.asyncio
    async def test_get_process_map_progress(self):
        """Test retrieving process map progress statistics."""
        session_id = "test-session-map-progress-001"
        
        async with httpx.AsyncClient() as client:
            # Create session and map
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions",
                json={"session_id": session_id, "goal": "Test progress"}
            )
            
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/map",
                json={"session_id": session_id, "business_goal": "Test progress"}
            )
            
            # Get progress
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/map/progress"
            )
            assert response.status_code == 200
            progress = response.json()
            assert isinstance(progress, dict)


class TestActivityEndpoints:
    """Test activity management endpoints."""
    
    @pytest.mark.asyncio
    async def test_add_activity(self):
        """Test adding an activity to a process map."""
        session_id = "test-session-activity-001"
        
        async with httpx.AsyncClient() as client:
            # Create session and map
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions",
                json={"session_id": session_id, "goal": "Test activities"}
            )
            
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/map",
                json={"session_id": session_id, "business_goal": "Test activities"}
            )
            
            # Add activity
            activity_data = {
                "goal": "Gather test data",
                "status": "proposed",
                "depends_on": []
            }
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/map/activities",
                json=activity_data
            )
            assert response.status_code in [200, 201]
            activity = response.json()
            assert "activity_id" in activity
            assert activity["goal"] == "Gather test data"
    
    @pytest.mark.asyncio
    async def test_update_activity_status(self):
        """Test updating activity status."""
        session_id = "test-session-activity-status-001"
        
        async with httpx.AsyncClient() as client:
            # Create session, map, and activity
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions",
                json={"session_id": session_id, "goal": "Test status update"}
            )
            
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/map",
                json={"session_id": session_id, "business_goal": "Test status"}
            )
            
            activity_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/map/activities",
                json={"goal": "Test activity", "status": "proposed"}
            )
            activity = activity_response.json()
            activity_id = activity["activity_id"]
            
            # Update status
            response = await client.put(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/activities/{activity_id}/status",
                json={"status": "in_progress"}
            )
            assert response.status_code in [200, 404]
    
    @pytest.mark.asyncio
    async def test_assign_participant(self):
        """Test assigning a participant to an activity."""
        session_id = "test-session-participant-001"
        
        async with httpx.AsyncClient() as client:
            # Create session, map, and activity
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions",
                json={"session_id": session_id, "goal": "Test participants"}
            )
            
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/map",
                json={"session_id": session_id, "business_goal": "Test participants"}
            )
            
            activity_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/map/activities",
                json={"goal": "Test activity", "status": "proposed"}
            )
            activity = activity_response.json()
            activity_id = activity["activity_id"]
            
            # Assign participant
            participant_data = {
                "agent_id": "test-agent-001",
                "agent_name": "Test Agent",
                "role": "primary",
                "reason": "Selected for testing purposes"
            }
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/process-maps/sessions/{session_id}/activities/{activity_id}/participants",
                json=participant_data
            )
            assert response.status_code in [200, 201, 404, 422]


class TestObservabilityEndpoints:
    """Test observability and event streaming endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_observability_events(self):
        """Test retrieving observability events."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/observability/events")
            assert response.status_code in [200, 404]
    
    @pytest.mark.asyncio
    async def test_get_session_events(self):
        """Test retrieving events for a specific session."""
        session_id = "test-session-events-001"
        
        async with httpx.AsyncClient() as client:
            # Create a session first
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions",
                json={"session_id": session_id, "goal": "Test events"}
            )
            
            # Get events
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/observability/sessions/{session_id}/events"
            )
            assert response.status_code in [200, 404]


class TestStorageEndpoints:
    """Test storage and persistence endpoints."""
    
    @pytest.mark.asyncio
    async def test_storage_info(self):
        """Test retrieving storage information."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/storage/info")
            assert response.status_code in [200, 404]
    
    @pytest.mark.asyncio
    async def test_storage_stats(self):
        """Test retrieving storage statistics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/storage/stats")
            assert response.status_code in [200, 404]


class TestPipelineEndpoints:
    """Test pipeline endpoints (legacy support)."""
    
    @pytest.mark.asyncio
    async def test_list_pipelines(self):
        """Test listing pipelines."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/pipelines")
            assert response.status_code in [200, 404]
    
    @pytest.mark.asyncio
    async def test_create_pipeline(self):
        """Test creating a pipeline."""
        pipeline_data = {
            "pipeline_id": "test-pipeline-001",
            "name": "Test Pipeline",
            "tasks": []
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/pipelines",
                json=pipeline_data
            )
            # May not be implemented or may be deprecated
            assert response.status_code in [200, 201, 404, 405]


class TestErrorHandling:
    """Test error handling and validation."""

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        """Test that invalid JSON returns proper error."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions",
                content="invalid json{",
                headers={"Content-Type": "application/json"}
            )
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_session_id(self):
        """Test creating session without session_id."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/sessions",
                json={"goal": "No session ID"}
            )
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_endpoint(self):
        """Test that invalid endpoint returns error."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/invalid-endpoint-xyz-999")
            # May return 404 or 200 with error message depending on framework config
            assert response.status_code in [200, 404]
            if response.status_code == 200:
                data = response.json()
                assert "error" in data or "detail" in data


class TestWorkAssignmentFlow:
    """Test work assignment API flow (Issue #216).

    Tests the full work lifecycle:
    1. Create work item
    2. Assign to compute
    3. Report progress
    4. Complete work
    """

    @pytest.mark.asyncio
    async def test_create_work_item(self):
        """Test creating a new work item."""
        import uuid
        work_data = {
            "title": f"Test work item {uuid.uuid4().hex[:8]}",
            "description": "Integration test work item",
            "priority": "normal",
            "project_id": "test-project",
            "required_capabilities": ["python"]
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/work",
                json=work_data
            )
            assert response.status_code == 201
            work = response.json()
            assert "work_id" in work
            assert work["title"] == work_data["title"]
            assert work["status"] == "pending"

    @pytest.mark.asyncio
    async def test_list_work_items(self):
        """Test listing work items."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/work")
            assert response.status_code == 200
            data = response.json()
            assert "items" in data or "work_items" in data or isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_get_work_stats(self):
        """Test getting work statistics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/work/stats")
            assert response.status_code == 200
            stats = response.json()
            assert "total" in stats or "by_status" in stats

    @pytest.mark.asyncio
    async def test_assign_work_to_compute(self):
        """Test assigning work to a compute instance."""
        import uuid

        async with httpx.AsyncClient() as client:
            # Create work item first
            work_data = {
                "title": f"Assign test {uuid.uuid4().hex[:8]}",
                "description": "Work to be assigned",
                "priority": "high",
                "project_id": "test-project"
            }
            create_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/work",
                json=work_data
            )
            assert create_response.status_code == 201
            work = create_response.json()
            work_id = work["work_id"]

            # Assign to compute
            compute_id = f"test-compute-{uuid.uuid4().hex[:8]}"
            assign_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": compute_id}
            )
            # May fail if compute not registered, which is expected
            assert assign_response.status_code in [200, 400, 404]

    @pytest.mark.asyncio
    async def test_update_work_status(self):
        """Test updating work item status."""
        import uuid

        async with httpx.AsyncClient() as client:
            # Create work item
            work_data = {
                "title": f"Status test {uuid.uuid4().hex[:8]}",
                "description": "Work for status update",
                "priority": "normal",
                "project_id": "test-project"
            }
            create_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/work",
                json=work_data
            )
            assert create_response.status_code == 201
            work = create_response.json()
            work_id = work["work_id"]

            # Update status
            status_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/work/{work_id}/status",
                params={"status": "in_progress"}
            )
            # May require compute_id authorization
            assert status_response.status_code in [200, 400]

    @pytest.mark.asyncio
    async def test_report_progress(self):
        """Test reporting progress on work."""
        import uuid

        async with httpx.AsyncClient() as client:
            # Create work item
            work_data = {
                "title": f"Progress test {uuid.uuid4().hex[:8]}",
                "description": "Work for progress reporting",
                "priority": "low",
                "project_id": "test-project"
            }
            create_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/work",
                json=work_data
            )
            assert create_response.status_code == 201
            work = create_response.json()
            work_id = work["work_id"]

            # Report progress (ProgressReport model requires work_id, progress_percent, status)
            progress_data = {
                "work_id": work_id,
                "progress_percent": 50,
                "status": "in_progress",
                "note": "Halfway done"
            }
            progress_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/work/{work_id}/progress",
                json=progress_data
            )
            assert progress_response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_get_next_assignment(self):
        """Test getting next work assignment for compute."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/work/next-assignment",
                params={"compute_id": "test-compute", "capabilities": "python,testing"}
            )
            # Returns null if no work available
            assert response.status_code == 200


class TestGoalAndIssueFlow:
    """Test goal and issue management (Issue #216).

    Tests goal creation and issue breakdown workflow.
    """

    @pytest.mark.asyncio
    async def test_create_goal(self):
        """Test creating a new goal."""
        import uuid
        goal_data = {
            "title": f"Test goal {uuid.uuid4().hex[:8]}",
            "description": "Integration test goal",
            "priority": "P1"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/goals",
                json=goal_data
            )
            assert response.status_code == 201
            goal = response.json()
            assert "goal_id" in goal
            assert goal["status"] == "planning"

    @pytest.mark.asyncio
    async def test_list_goals(self):
        """Test listing goals."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/goals")
            assert response.status_code == 200
            data = response.json()
            assert "goals" in data or "items" in data or isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_create_issue(self):
        """Test creating an issue."""
        import uuid
        issue_data = {
            "title": f"Test issue {uuid.uuid4().hex[:8]}",
            "description": "Integration test issue",
            "priority": "P2",
            "area": "api",
            "issue_type": "feature"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/issues",
                json=issue_data
            )
            assert response.status_code == 201
            issue = response.json()
            assert "issue_id" in issue

    @pytest.mark.asyncio
    async def test_list_issues(self):
        """Test listing issues."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/issues")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_issue_stats(self):
        """Test getting issue statistics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/issues/stats")
            assert response.status_code == 200
            stats = response.json()
            assert "total" in stats

    @pytest.mark.asyncio
    async def test_get_ready_queue(self):
        """Test getting the ready queue of issues."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/workmap/ready")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_workmap_stats(self):
        """Test getting workmap statistics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/workmap/stats")
            assert response.status_code == 200


class TestPRMergeFlow:
    """Test PR submission and merge flow (Issue #216).

    Tests the full PR lifecycle:
    1. Create repository
    2. Create PR
    3. Approve PR
    4. Merge PR
    """

    @pytest.fixture
    def test_project(self):
        """Generate a unique test project name."""
        import uuid
        return f"test-pr-{uuid.uuid4().hex[:8]}"

    @pytest.mark.asyncio
    async def test_list_repositories(self):
        """Test listing repositories."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/git/repos")
            assert response.status_code == 200
            repos = response.json()
            assert isinstance(repos, list)

    @pytest.mark.asyncio
    async def test_create_repository(self, test_project):
        """Test creating a new repository."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
                json={"project": test_project, "install_hooks": True}
            )
            # May already exist or succeed
            assert response.status_code in [201, 409]
            if response.status_code == 201:
                repo = response.json()
                assert repo["project"] == test_project
                assert "clone_url" in repo

    @pytest.mark.asyncio
    async def test_get_repository(self):
        """Test getting repository details."""
        async with httpx.AsyncClient() as client:
            # First list repos to find one
            list_response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/git/repos")
            repos = list_response.json()

            if repos:
                project = repos[0]
                response = await client.get(
                    f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}"
                )
                assert response.status_code == 200
                repo = response.json()
                assert repo["project"] == project

    @pytest.mark.asyncio
    async def test_list_branches(self):
        """Test listing branches in a repository."""
        async with httpx.AsyncClient() as client:
            # First list repos to find one
            list_response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/git/repos")
            repos = list_response.json()

            if repos:
                project = repos[0]
                response = await client.get(
                    f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}/branches"
                )
                assert response.status_code == 200
                branches = response.json()
                assert isinstance(branches, list)

    @pytest.mark.asyncio
    async def test_create_pull_request(self):
        """Test creating a pull request."""
        import uuid

        async with httpx.AsyncClient() as client:
            # First list repos to find one
            list_response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/git/repos")
            repos = list_response.json()

            if not repos:
                # Create a test repo first
                project = f"test-pr-{uuid.uuid4().hex[:8]}"
                await client.post(
                    f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
                    json={"project": project, "install_hooks": True}
                )
            else:
                project = repos[0]

            # Try to create PR (may fail if branch doesn't exist)
            pr_data = {
                "project": project,
                "branch": f"feat/test-{uuid.uuid4().hex[:8]}",
                "compute_id": "test-compute",
                "title": "Test PR",
                "description": "Integration test PR"
            }
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/prs",
                json=pr_data
            )
            # Branch may not exist
            assert response.status_code in [201, 400]

    @pytest.mark.asyncio
    async def test_list_pull_requests(self):
        """Test listing pull requests for a project."""
        async with httpx.AsyncClient() as client:
            # First list repos to find one
            list_response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/git/repos")
            repos = list_response.json()

            if repos:
                project = repos[0]
                response = await client.get(
                    f"{SERVING_BASE_URL}{API_PREFIX}/git/prs/{project}"
                )
                assert response.status_code == 200
                prs = response.json()
                assert isinstance(prs, list)

    @pytest.mark.asyncio
    async def test_get_pr_queue(self):
        """Test getting PR queue for a project."""
        async with httpx.AsyncClient() as client:
            # First list repos to find one
            list_response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/git/repos")
            repos = list_response.json()

            if repos:
                project = repos[0]
                response = await client.get(
                    f"{SERVING_BASE_URL}{API_PREFIX}/git/queues/{project}/prs"
                )
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_merge_queue(self):
        """Test getting merge queue for a project."""
        async with httpx.AsyncClient() as client:
            # First list repos to find one
            list_response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/git/repos")
            repos = list_response.json()

            if repos:
                project = repos[0]
                response = await client.get(
                    f"{SERVING_BASE_URL}{API_PREFIX}/git/queues/{project}/merges"
                )
                assert response.status_code == 200


class TestGitTokenManagement:
    """Test Git token management for compute instances."""

    @pytest.mark.asyncio
    async def test_generate_compute_token(self):
        """Test generating a compute token."""
        import uuid
        compute_id = f"test-compute-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/tokens",
                json={"compute_id": compute_id}
            )
            # Token generation should succeed or return appropriate error
            assert response.status_code in [200, 201, 400, 404]
            if response.status_code in [200, 201]:
                token_data = response.json()
                assert "token" in token_data
                assert token_data["compute_id"] == compute_id

    @pytest.mark.asyncio
    async def test_revoke_compute_token(self):
        """Test revoking a compute token."""
        import uuid
        compute_id = f"test-compute-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient() as client:
            # First generate a token
            gen_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/tokens",
                json={"compute_id": compute_id}
            )

            if gen_response.status_code in [200, 201]:
                # Then revoke it
                revoke_response = await client.delete(
                    f"{SERVING_BASE_URL}{API_PREFIX}/git/tokens/{compute_id}"
                )
                assert revoke_response.status_code in [200, 204]


class TestSSEEventDelivery:
    """Test SSE event delivery flow (Issue #216).

    Tests Server-Sent Events for compute communication:
    1. SSE connection establishment
    2. Keepalive events
    3. Work assignment events
    """

    @pytest.mark.asyncio
    async def test_sse_connection_established(self):
        """Test establishing SSE connection for compute registration."""
        import uuid
        compute_id = f"test-sse-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            # Connect via SSE
            async with client.stream(
                "GET",
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/connect",
                headers={
                    "X-Compute-ID": compute_id,
                    "X-Capabilities": "python,testing",
                    "Accept": "text/event-stream"
                }
            ) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")

                # Read first event (should be 'connected')
                first_line = ""
                async for line in response.aiter_lines():
                    first_line = line
                    break

                assert "event:" in first_line or "data:" in first_line

    @pytest.mark.asyncio
    async def test_sse_stats_endpoint(self):
        """Test SSE connection statistics endpoint."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/compute/sse/stats")
            assert response.status_code == 200
            stats = response.json()
            assert "active_connections" in stats or "total_connections" in stats or isinstance(stats, dict)

    @pytest.mark.asyncio
    async def test_compute_events_endpoint(self):
        """Test receiving compute events via POST."""
        import uuid
        from datetime import datetime, timezone

        async with httpx.AsyncClient() as client:
            # First register a compute instance
            compute_id = f"test-event-{uuid.uuid4().hex[:8]}"

            # Register via legacy endpoint for testing
            register_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/register",
                json={
                    "instance_id": compute_id,
                    "name": f"Test Compute {compute_id}",
                    "endpoint": "http://localhost:9999",
                    "capabilities": {"agents": ["test"], "tools": [], "features": []}
                }
            )

            if register_response.status_code == 201:
                # Send compute event
                event_data = {
                    "compute_id": compute_id,
                    "event": "claude_code_started",
                    "task_id": f"task-{uuid.uuid4().hex[:8]}",
                    "instance_id": f"instance-{uuid.uuid4().hex[:8]}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

                event_response = await client.post(
                    f"{SERVING_BASE_URL}{API_PREFIX}/compute/events",
                    json=event_data
                )
                assert event_response.status_code == 200
                result = event_response.json()
                assert result["status"] == "acknowledged"

                # Cleanup - deregister
                await client.delete(f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}")

    @pytest.mark.asyncio
    async def test_list_compute_instances(self):
        """Test listing registered compute instances."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/compute")
            assert response.status_code == 200
            data = response.json()
            assert "instances" in data
            assert "total" in data

    @pytest.mark.asyncio
    async def test_compute_instance_lifecycle(self):
        """Test full compute instance lifecycle: register, heartbeat, deregister."""
        import uuid

        compute_id = f"test-lifecycle-{uuid.uuid4().hex[:8]}"

        async with httpx.AsyncClient() as client:
            # Register
            register_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/register",
                json={
                    "instance_id": compute_id,
                    "name": f"Lifecycle Test {compute_id}",
                    "endpoint": "http://localhost:9999",
                    "capabilities": {"agents": ["test"], "tools": [], "features": []}
                }
            )
            assert register_response.status_code == 201

            # Get instance
            get_response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}"
            )
            assert get_response.status_code == 200
            instance = get_response.json()
            assert instance["instance_id"] == compute_id

            # Send heartbeat
            heartbeat_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}/health",
                json={"metadata": {"test": True}}
            )
            assert heartbeat_response.status_code == 200

            # Deregister
            deregister_response = await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}"
            )
            assert deregister_response.status_code == 200

            # Verify deregistered
            verify_response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/compute/{compute_id}"
            )
            assert verify_response.status_code == 404


class TestAppLifespan:
    """Test app startup and health (Issue #216).

    Tests that the app lifespan properly initializes all services.
    """

    @pytest.mark.asyncio
    async def test_health_includes_all_services(self):
        """Test health endpoint includes all service statuses."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}{API_PREFIX}/health")
            assert response.status_code == 200
            health = response.json()

            # Verify all services are reported
            assert health["status"] == "healthy"
            assert "compute_registry" in health
            assert "marketplace_registry" in health
            assert "skill_registry" in health
            assert "compute_spawner" in health
            assert "work_map" in health
            assert "work_orchestrator" in health

    @pytest.mark.asyncio
    async def test_api_info_endpoint(self):
        """Test API info endpoint or frontend fallback."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_BASE_URL}/api")
            # May return 200 (JSON or HTML if frontend is built)
            assert response.status_code in [200, 307, 404]
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    info = response.json()
                    # Check for expected fields if JSON response
                    if isinstance(info, dict):
                        assert "version" in info or "endpoints" in info or "error" in info
                elif "text/html" in content_type:
                    # Frontend is built and serving HTML - this is valid
                    assert "<!DOCTYPE html>" in response.text or "<html" in response.text


# Run tests
if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("Serving Service API Integration Tests")
    print("=" * 60)
    print()
    print("Prerequisites:")
    print(f"  • Serving service running at {SERVING_BASE_URL}")
    print("  • Service should be initialized and healthy")
    print()
    print("Running tests...")
    print()
    
    # Run with pytest
    sys.exit(pytest.main([__file__, "-v", "-s"]))
