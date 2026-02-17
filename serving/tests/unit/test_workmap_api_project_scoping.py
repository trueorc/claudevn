"""Tests for WorkMap API project scoping functionality.

Verifies that workmap_router endpoints correctly pass project_id
query parameters to the service layer for proper data isolation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.work_map import workmap_router
from models.work_map import Issue, IssueStatus, IssueStats


# =============================================================================
# Mock Data Helpers
# =============================================================================

def make_mock_issue(issue_id, project_id, status="backlog"):
    """Create a mock issue object with attributes for client-side filtering."""
    issue = MagicMock()
    issue.issue_id = issue_id
    issue.project_id = project_id
    issue.status = MagicMock()
    issue.status.value = status
    issue.priority = MagicMock()
    issue.priority.value = "P1"
    issue.area = MagicMock()
    issue.area.value = "api"
    return issue


def make_real_issue(issue_id, project_id, status="ready"):
    """Create a real Issue model instance (for response_model validated endpoints)."""
    return Issue(
        issue_id=issue_id,
        title=f"Test issue {issue_id}",
        description="Test description",
        project_id=project_id,
        status=status,
    )


def make_issue_list_response(items=None, total=None):
    """Create a mock IssueListResponse."""
    response = MagicMock()
    response.items = items or []
    response.total = total if total is not None else len(response.items)
    response.by_status = {}
    response.by_priority = {}
    return response


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_service():
    """Create a mock WorkMapService."""
    service = MagicMock()
    service.list_goals = AsyncMock()
    service.list_issues = AsyncMock()
    service.list_work = AsyncMock()
    service.get_issue_stats = AsyncMock()
    service.get_ready_queue = AsyncMock()
    return service


@pytest.fixture
def app():
    """Create a FastAPI app with the workmap router."""
    test_app = FastAPI()
    test_app.include_router(workmap_router)
    return test_app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


# =============================================================================
# Test: GET /workmap
# =============================================================================

class TestGetWorkmap:

    @patch("api.work_map.get_work_map_service")
    def test_without_project_id(self, mock_get_service, client, mock_service):
        mock_get_service.return_value = mock_service
        mock_service.list_goals.return_value = {"items": [], "total": 0}
        mock_service.list_issues.return_value = {"items": [], "total": 0, "by_status": {}, "by_priority": {}}
        mock_service.list_work.return_value = {"items": [], "total": 0, "stats": {}}
        mock_service.get_issue_stats.return_value = {
            "total": 0, "by_status": {}, "by_priority": {}, "by_area": {},
            "by_release": {}, "ready_count": 0, "in_progress_count": 0, "blocked_count": 0
        }

        response = client.get("/workmap")

        assert response.status_code == 200
        data = response.json()
        assert "goals" in data
        assert "issues" in data
        assert "work_items" in data
        assert "stats" in data

        # project_id=None passed when no query param
        mock_service.list_goals.assert_called_once_with(project_id=None)
        mock_service.list_issues.assert_called_once_with(project_id=None)
        mock_service.list_work.assert_called_once_with(project_id=None)

    @patch("api.work_map.get_work_map_service")
    def test_with_project_id(self, mock_get_service, client, mock_service):
        mock_get_service.return_value = mock_service
        mock_service.list_goals.return_value = {"items": [], "total": 0}
        mock_service.list_issues.return_value = {"items": [], "total": 0, "by_status": {}, "by_priority": {}}
        mock_service.list_work.return_value = {"items": [], "total": 0, "stats": {}}
        mock_service.get_issue_stats.return_value = {
            "total": 0, "by_status": {}, "by_priority": {}, "by_area": {},
            "by_release": {}, "ready_count": 0, "in_progress_count": 0, "blocked_count": 0
        }

        response = client.get("/workmap?project_id=proj-123")

        assert response.status_code == 200
        mock_service.list_goals.assert_called_once_with(project_id="proj-123")
        mock_service.list_issues.assert_called_once_with(project_id="proj-123")
        mock_service.list_work.assert_called_once_with(project_id="proj-123")


# =============================================================================
# Test: GET /workmap/stats
# =============================================================================

class TestGetWorkmapStats:

    @patch("api.work_map.get_work_map_service")
    def test_without_project_id_calls_get_issue_stats(self, mock_get_service, client, mock_service):
        mock_get_service.return_value = mock_service
        mock_service.get_issue_stats.return_value = IssueStats(
            total=10, by_status={"backlog": 5, "ready": 3, "in_progress": 2},
            by_priority={"P0": 2, "P1": 5, "P2": 3},
            by_area={"api": 6, "frontend": 4},
            ready_count=3, in_progress_count=2, blocked_count=0
        )

        response = client.get("/workmap/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 10
        assert data["ready_count"] == 3
        mock_service.get_issue_stats.assert_called_once()
        mock_service.list_issues.assert_not_called()

    @patch("api.work_map.get_work_map_service")
    def test_with_project_id_computes_stats_from_issues(self, mock_get_service, client, mock_service):
        mock_get_service.return_value = mock_service

        issues = [
            make_mock_issue("issue-1", "proj-123", "backlog"),
            make_mock_issue("issue-2", "proj-123", "ready"),
            make_mock_issue("issue-3", "proj-123", "in_progress"),
        ]
        mock_service.list_issues.return_value = make_issue_list_response(issues)

        response = client.get("/workmap/stats?project_id=proj-123")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["by_status"]["backlog"] == 1
        assert data["by_status"]["ready"] == 1
        assert data["by_status"]["in_progress"] == 1
        assert data["ready_count"] == 1
        assert data["in_progress_count"] == 1
        assert data["blocked_count"] == 0

        mock_service.list_issues.assert_called_once_with(project_id="proj-123", limit=1000)
        mock_service.get_issue_stats.assert_not_called()


# =============================================================================
# Test: GET /workmap/in-progress
# =============================================================================

class TestGetInProgress:

    @patch("api.work_map.get_work_map_service")
    def test_without_project_id(self, mock_get_service, client, mock_service):
        mock_get_service.return_value = mock_service
        mock_service.list_issues.return_value = {
            "items": [], "total": 0, "by_status": {}, "by_priority": {}
        }

        response = client.get("/workmap/in-progress")

        assert response.status_code == 200
        mock_service.list_issues.assert_called_once_with(
            status=IssueStatus.IN_PROGRESS, project_id=None
        )

    @patch("api.work_map.get_work_map_service")
    def test_with_project_id(self, mock_get_service, client, mock_service):
        mock_get_service.return_value = mock_service
        mock_service.list_issues.return_value = {
            "items": [], "total": 0, "by_status": {}, "by_priority": {}
        }

        response = client.get("/workmap/in-progress?project_id=proj-123")

        assert response.status_code == 200
        mock_service.list_issues.assert_called_once_with(
            status=IssueStatus.IN_PROGRESS, project_id="proj-123"
        )


# =============================================================================
# Test: GET /workmap/blocked
# =============================================================================

class TestGetBlocked:

    @patch("api.work_map.get_work_map_service")
    def test_without_project_id(self, mock_get_service, client, mock_service):
        mock_get_service.return_value = mock_service
        mock_service.list_issues.return_value = {
            "items": [], "total": 0, "by_status": {}, "by_priority": {}
        }

        response = client.get("/workmap/blocked")

        assert response.status_code == 200
        mock_service.list_issues.assert_called_once_with(
            status=IssueStatus.BLOCKED, project_id=None
        )

    @patch("api.work_map.get_work_map_service")
    def test_with_project_id(self, mock_get_service, client, mock_service):
        mock_get_service.return_value = mock_service
        mock_service.list_issues.return_value = {
            "items": [], "total": 0, "by_status": {}, "by_priority": {}
        }

        response = client.get("/workmap/blocked?project_id=proj-123")

        assert response.status_code == 200
        mock_service.list_issues.assert_called_once_with(
            status=IssueStatus.BLOCKED, project_id="proj-123"
        )


# =============================================================================
# Test: GET /workmap/ready
# =============================================================================

class TestGetReady:

    @patch("api.work_map.get_work_map_service")
    def test_without_project_id_returns_all(self, mock_get_service, client, mock_service):
        mock_get_service.return_value = mock_service
        issues = [
            make_real_issue("issue-1", "proj-123"),
            make_real_issue("issue-2", "proj-456"),
        ]
        mock_service.get_ready_queue.return_value = issues

        response = client.get("/workmap/ready")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        mock_service.get_ready_queue.assert_called_once_with(limit=50)

    @patch("api.work_map.get_work_map_service")
    def test_with_project_id_filters_results(self, mock_get_service, client, mock_service):
        mock_get_service.return_value = mock_service
        issues = [
            make_real_issue("issue-1", "proj-123"),
            make_real_issue("issue-2", "proj-456"),
            make_real_issue("issue-3", "proj-123"),
        ]
        mock_service.get_ready_queue.return_value = issues

        response = client.get("/workmap/ready?project_id=proj-123")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(i["project_id"] == "proj-123" for i in data)
        mock_service.get_ready_queue.assert_called_once_with(limit=50)

    @patch("api.work_map.get_work_map_service")
    def test_with_project_id_no_matches(self, mock_get_service, client, mock_service):
        mock_get_service.return_value = mock_service
        issues = [
            make_real_issue("issue-1", "proj-456"),
        ]
        mock_service.get_ready_queue.return_value = issues

        response = client.get("/workmap/ready?project_id=proj-123")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0
