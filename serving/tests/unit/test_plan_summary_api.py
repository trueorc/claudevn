"""Unit tests for plan summary API endpoint."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.plan_summary import router
from models.decision_trace import (
    DecisionPointType,
    DecisionTrace,
    DecisionTrigger,
)
from models.planner_focus import PlannerFocusSummary
from models.work_map import Issue, IssueStatus, IssuePriority


# =============================================================================
# Test Setup
# =============================================================================


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_issue_in_progress():
    return Issue(
        issue_id="issue_1",
        title="Build authentication",
        description="Implement user authentication",
        status=IssueStatus.IN_PROGRESS,
        priority=IssuePriority.P1,
        assigned_compute_id="compute_1",
        goal_id="goal_1",
        depends_on=[],
        blocks=[],
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_issue_ready():
    return Issue(
        issue_id="issue_2",
        title="Add OAuth support",
        description="Implement OAuth 2.0",
        status=IssueStatus.READY,
        priority=IssuePriority.P2,
        goal_id="goal_1",
        depends_on=[],
        blocks=[],
        created_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_issue_blocked():
    return Issue(
        issue_id="issue_3",
        title="Add session management",
        description="Implement session storage",
        status=IssueStatus.BLOCKED,
        priority=IssuePriority.P1,
        goal_id="goal_1",
        depends_on=["issue_1"],
        blocks=[],
        created_at=datetime(2024, 1, 3, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_focus_summary():
    return PlannerFocusSummary(
        project_id="proj_1",
        has_profile=True,
        optimization_target="Primary focus: Building new features.",
        primary_intent="expansion",
    )


@pytest.fixture
def mock_decision_trace():
    return DecisionTrace(
        trace_id="trace_1",
        project_id="proj_1",
        decision_type=DecisionPointType.TASK_MOVEMENT,
        trigger=DecisionTrigger(
            trigger_type="new_goal",
            source_id="goal_1",
            source_type="goal",
            description="Goal created: Build authentication",
        ),
        decision_summary="Moved task to ready queue",
        key_factors=["Dependencies met", "High priority"],
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


# =============================================================================
# Plan Summary Endpoint Tests
# =============================================================================


class TestGetPlanSummaryEndpoint:
    """Tests for GET /plan/summary."""

    def test_requires_project_id(self, client):
        """Test that project_id is required."""
        response = client.get("/plan/summary")
        assert response.status_code == 400
        assert "project_id is required" in response.json()["detail"]

    @patch("api.plan_summary.get_decision_trace_service")
    @patch("api.plan_summary.get_planner_focus_service")
    @patch("api.plan_summary.get_planner_profile_service")
    @patch("api.plan_summary.get_work_map_service")
    def test_returns_complete_summary(
        self,
        mock_wm_getter,
        mock_pps_getter,
        mock_pfs_getter,
        mock_dts_getter,
        client,
        mock_issue_in_progress,
        mock_issue_ready,
        mock_issue_blocked,
        mock_focus_summary,
        mock_decision_trace,
    ):
        """Test that the endpoint returns a complete plan summary."""
        # Mock work map service — single call returns all project issues
        mock_wm_svc = AsyncMock()

        mock_done_issue = Issue(
            issue_id="issue_done_1",
            title="Setup repo",
            description="Initial setup",
            status=IssueStatus.DONE,
            priority=IssuePriority.P2,
            goal_id="goal_1",
            depends_on=[],
            blocks=[],
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        mock_done_issue2 = Issue(
            issue_id="issue_done_2",
            title="Add CI",
            description="CI pipeline",
            status=IssueStatus.DONE,
            priority=IssuePriority.P3,
            goal_id="goal_1",
            depends_on=[],
            blocks=[],
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        all_issues = [
            mock_issue_in_progress,
            mock_issue_ready,
            mock_issue_blocked,
            mock_done_issue,
            mock_done_issue2,
        ]
        mock_all_list = MagicMock()
        mock_all_list.items = all_issues

        mock_wm_svc.list_issues = AsyncMock(return_value=mock_all_list)

        # Mock goal list
        mock_goal_list = MagicMock()
        mock_goal_list.items = []
        mock_wm_svc.list_goals = AsyncMock(return_value=mock_goal_list)
        mock_wm_getter.return_value = mock_wm_svc

        # Mock planner profile service
        mock_profile_svc = AsyncMock()
        mock_profile_svc.get_profile = AsyncMock(return_value=None)
        mock_pps_getter.return_value = mock_profile_svc

        # Mock planner focus service
        mock_focus_svc = AsyncMock()
        mock_focus_svc.get_focus_summary = AsyncMock(return_value=mock_focus_summary)
        mock_pfs_getter.return_value = mock_focus_svc

        # Mock decision trace service
        mock_trace_svc = AsyncMock()
        mock_trace_svc.get_traces = AsyncMock(return_value=[mock_decision_trace])
        mock_dts_getter.return_value = mock_trace_svc

        response = client.get("/plan/summary?project_id=proj_1")
        assert response.status_code == 200

        data = response.json()

        # Check project_id
        assert data["project_id"] == "proj_1"

        # Check counts match actual issue statuses
        assert data["in_progress_count"] == 1
        assert data["ready_count"] == 1
        assert data["blocked_count"] == 1
        assert data["done_count"] == 2
        assert data["total_count"] == 5

        # Check focus summary
        assert data["focus_summary"] == "Primary focus: Building new features."
        assert data["primary_intent"] == "expansion"

        # Check active items
        assert len(data["running_items"]) == 1
        assert data["running_items"][0]["issue_id"] == "issue_1"
        assert data["running_items"][0]["assigned_to"] == "compute_1"

        assert len(data["queued_items"]) == 1
        assert data["queued_items"][0]["issue_id"] == "issue_2"

        assert len(data["blocked_items"]) == 1
        assert data["blocked_items"][0]["issue_id"] == "issue_3"
        assert data["blocked_items"][0]["depends_on"] == ["issue_1"]

        # Check decision traces
        assert len(data["recent_traces"]) == 1
        assert data["recent_traces"][0]["trace_id"] == "trace_1"
        assert data["recent_traces"][0]["decision_summary"] == "Moved task to ready queue"
        assert data["recent_traces"][0]["trigger"] == "Goal created: Build authentication"
        assert data["trace_count"] == 1

    @patch("api.plan_summary.get_work_map_service")
    def test_backlog_and_failed_not_double_counted(
        self,
        mock_wm_getter,
        client,
    ):
        """Test that backlog/failed issues are not miscounted as ready or done.

        Regression test for #681: 54 backlog+failed issues were reported as
        ready_count=54, done_count=54, total_count=108.
        """
        mock_wm_svc = AsyncMock()

        # Create 51 backlog + 3 failed issues (matches the original bug scenario)
        issues = []
        for i in range(51):
            issues.append(Issue(
                issue_id=f"issue_backlog_{i}",
                title=f"Backlog issue {i}",
                description="Backlog item",
                status=IssueStatus.BACKLOG,
                priority=IssuePriority.P2,
                goal_id="goal_1",
            ))
        for i in range(3):
            issues.append(Issue(
                issue_id=f"issue_failed_{i}",
                title=f"Failed issue {i}",
                description="Failed item",
                status=IssueStatus.FAILED,
                priority=IssuePriority.P1,
                goal_id="goal_1",
            ))

        mock_all_list = MagicMock()
        mock_all_list.items = issues
        mock_wm_svc.list_issues = AsyncMock(return_value=mock_all_list)
        mock_wm_svc.list_goals = AsyncMock(return_value=MagicMock(items=[]))
        mock_wm_getter.return_value = mock_wm_svc

        response = client.get("/plan/summary?project_id=proj_1")
        assert response.status_code == 200

        data = response.json()

        # Active/ready/blocked/done counts should be zero
        assert data["in_progress_count"] == 0
        assert data["ready_count"] == 0
        assert data["blocked_count"] == 0
        assert data["done_count"] == 0
        # Backlog and failed should have correct counts and items
        assert data["backlog_count"] == 51
        assert data["failed_count"] == 3
        assert len(data["backlog_items"]) == 20  # capped at 20 for UI
        assert len(data["failed_items"]) == 3
        # Total reflects all issues regardless of status
        assert data["total_count"] == 54

    @patch("api.plan_summary.get_work_map_service")
    def test_graceful_degradation_on_service_failures(
        self,
        mock_wm_getter,
        client,
    ):
        """Test that the endpoint returns a degraded response when services fail."""
        # Mock work map service to raise exceptions
        mock_wm_svc = AsyncMock()
        mock_wm_svc.list_issues = AsyncMock(side_effect=Exception("Service error"))
        mock_wm_svc.list_goals = AsyncMock(side_effect=Exception("Service error"))
        mock_wm_getter.return_value = mock_wm_svc

        response = client.get("/plan/summary?project_id=proj_1")
        assert response.status_code == 200

        data = response.json()

        # Check that counts are zero
        assert data["project_id"] == "proj_1"
        assert data["in_progress_count"] == 0
        assert data["ready_count"] == 0
        assert data["blocked_count"] == 0
        assert data["total_count"] == 0

        # Check that items are empty
        assert len(data["running_items"]) == 0
        assert len(data["queued_items"]) == 0
        assert len(data["blocked_items"]) == 0

    @patch("api.plan_summary.get_planner_focus_service")
    @patch("api.plan_summary.get_planner_profile_service")
    @patch("api.plan_summary.get_work_map_service")
    def test_graceful_degradation_on_focus_service_failure(
        self,
        mock_wm_getter,
        mock_pps_getter,
        mock_pfs_getter,
        client,
        mock_issue_in_progress,
    ):
        """Test graceful degradation when planner focus service fails."""
        # Mock work map service — all project issues in one call
        mock_wm_svc = AsyncMock()
        mock_all_list = MagicMock()
        mock_all_list.items = [mock_issue_in_progress]
        mock_wm_svc.list_issues = AsyncMock(return_value=mock_all_list)
        mock_wm_svc.list_goals = AsyncMock(return_value=MagicMock(items=[]))
        mock_wm_getter.return_value = mock_wm_svc

        # Mock planner focus service to fail
        mock_pfs_getter.side_effect = RuntimeError("Service not initialized")

        response = client.get("/plan/summary?project_id=proj_1")
        assert response.status_code == 200

        data = response.json()

        # Check that focus summary shows degraded state
        assert "unavailable" in data["focus_summary"].lower()
        assert data["primary_intent"] is None

        # Check that work items are still returned
        assert data["in_progress_count"] == 1
        assert len(data["running_items"]) == 1

    @patch("api.plan_summary.get_decision_trace_service")
    @patch("api.plan_summary.get_work_map_service")
    def test_graceful_degradation_on_trace_service_failure(
        self,
        mock_wm_getter,
        mock_dts_getter,
        client,
        mock_issue_ready,
    ):
        """Test graceful degradation when decision trace service fails."""
        # Mock work map service — all project issues in one call
        mock_wm_svc = AsyncMock()
        mock_all_list = MagicMock()
        mock_all_list.items = [mock_issue_ready]
        mock_wm_svc.list_issues = AsyncMock(return_value=mock_all_list)
        mock_wm_svc.list_goals = AsyncMock(return_value=MagicMock(items=[]))
        mock_wm_getter.return_value = mock_wm_svc

        # Mock decision trace service to fail
        mock_dts_getter.side_effect = RuntimeError("Service not initialized")

        response = client.get("/plan/summary?project_id=proj_1")
        assert response.status_code == 200

        data = response.json()

        # Check that traces are empty
        assert len(data["recent_traces"]) == 0
        assert data["trace_count"] == 0

        # Check that work items are still returned
        assert len(data["queued_items"]) == 1
