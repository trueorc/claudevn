"""Tests for conflict surfacing API endpoints."""

import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from models.conflict import (
    ConflictReport,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    PlannerHandling,
    ResolutionAuthority,
    SuggestedResolution,
    TensionElement,
    UserResponse,
    UserResponseType,
)
from api.conflicts import router
from services.conflict_detection_service import (
    ConflictDetectionService,
    set_conflict_detection_service,
)


def _make_conflict(
    conflict_id="conflict-001",
    project_id="proj-001",
    conflict_type=ConflictType.GOAL_TO_GOAL,
    severity=ConflictSeverity.HIGH,
    severity_score=0.7,
    status=ConflictStatus.ACTIVE,
    resolution_authority=ResolutionAuthority.USER_REQUIRED,
):
    """Helper to create a ConflictReport for testing."""
    return ConflictReport(
        conflict_id=conflict_id,
        project_id=project_id,
        conflict_type=conflict_type,
        severity=severity,
        severity_score=severity_score,
        status=status,
        title=f"Test conflict {conflict_id}",
        description=f"Description for {conflict_id}",
        tension_elements=[
            TensionElement(
                element_type="goal",
                element_id="goal-a",
                label="Goal A",
                detail="Primary intent: expansion",
            ),
            TensionElement(
                element_type="goal",
                element_id="goal-b",
                label="Goal B",
                detail="Primary intent: consolidation",
            ),
        ],
        planner_handling=PlannerHandling(
            approach="Balancing both goals equally",
            reasoning="Both have equal intent strength",
        ),
        suggested_resolutions=[
            SuggestedResolution(
                response_type=UserResponseType.SET_PRIORITY,
                description="Set explicit priorities",
                expected_impact="Planner will weight accordingly",
            ),
            SuggestedResolution(
                response_type=UserResponseType.ACCEPT_TRADEOFF,
                description="Accept current handling",
                expected_impact="Conflict marked as resolved",
            ),
        ],
        resolution_authority=resolution_authority,
        detected_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def service():
    """Create a conflict detection service for testing."""
    svc = ConflictDetectionService(redis_client=None)
    set_conflict_detection_service(svc)
    return svc


@pytest.fixture
def client(service):
    """Create a test client with the conflicts router."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestListConflicts:
    """Test GET /{project_id} endpoint."""

    def test_empty_project(self, client):
        resp = client.get("/conflicts/proj-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == "proj-001"
        assert data["conflicts"] == []
        assert data["total"] == 0

    def test_list_with_conflicts(self, client, service):
        service._conflicts["proj-001"] = [
            _make_conflict("c-001", severity=ConflictSeverity.CRITICAL),
            _make_conflict("c-002", severity=ConflictSeverity.LOW,
                           resolution_authority=ResolutionAuthority.AUTONOMOUS),
        ]

        resp = client.get("/conflicts/proj-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["surfaceable_count"] == 1  # Only CRITICAL should_surface
        assert "critical" in data["by_severity"]

    def test_filter_by_type(self, client, service):
        service._conflicts["proj-001"] = [
            _make_conflict("c-001", conflict_type=ConflictType.GOAL_TO_GOAL),
            _make_conflict("c-002", conflict_type=ConflictType.RESOURCE),
        ]

        resp = client.get("/conflicts/proj-001?conflict_type=resource")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["conflicts"][0]["conflict_type"] == "resource"

    def test_filter_by_status(self, client, service):
        service._conflicts["proj-001"] = [
            _make_conflict("c-001", status=ConflictStatus.ACTIVE),
            _make_conflict("c-002", status=ConflictStatus.USER_RESOLVED),
        ]

        resp = client.get("/conflicts/proj-001?status=active")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["conflicts"][0]["status"] == "active"

    def test_filter_by_severity(self, client, service):
        service._conflicts["proj-001"] = [
            _make_conflict("c-001", severity=ConflictSeverity.HIGH),
            _make_conflict("c-002", severity=ConflictSeverity.LOW),
        ]

        resp = client.get("/conflicts/proj-001?severity=high")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["conflicts"][0]["severity"] == "high"

    def test_surfaceable_only(self, client, service):
        service._conflicts["proj-001"] = [
            _make_conflict("c-001", severity=ConflictSeverity.HIGH,
                           resolution_authority=ResolutionAuthority.USER_REQUIRED),
            _make_conflict("c-002", severity=ConflictSeverity.LOW,
                           resolution_authority=ResolutionAuthority.AUTONOMOUS),
        ]

        resp = client.get("/conflicts/proj-001?surfaceable_only=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_invalid_type_returns_400(self, client):
        resp = client.get("/conflicts/proj-001?conflict_type=invalid")
        assert resp.status_code == 400

    def test_invalid_status_returns_400(self, client):
        resp = client.get("/conflicts/proj-001?status=invalid")
        assert resp.status_code == 400

    def test_invalid_severity_returns_400(self, client, service):
        service._conflicts["proj-001"] = [_make_conflict("c-001")]
        resp = client.get("/conflicts/proj-001?severity=invalid")
        assert resp.status_code == 400


class TestGetConflictCount:
    """Test GET /{project_id}/count endpoint."""

    def test_empty_counts(self, client):
        resp = client.get("/conflicts/proj-001/count")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["surfaceable"] == 0
        assert data["critical"] == 0
        assert data["high"] == 0

    def test_counts_with_conflicts(self, client, service):
        service._conflicts["proj-001"] = [
            _make_conflict("c-001", severity=ConflictSeverity.CRITICAL),
            _make_conflict("c-002", severity=ConflictSeverity.HIGH),
            _make_conflict("c-003", severity=ConflictSeverity.LOW,
                           resolution_authority=ResolutionAuthority.AUTONOMOUS),
        ]

        resp = client.get("/conflicts/proj-001/count")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["critical"] == 1
        assert data["high"] == 1
        assert data["surfaceable"] == 2  # CRITICAL + HIGH (both should_surface)


class TestGetConflict:
    """Test GET /{project_id}/{conflict_id} endpoint."""

    def test_get_existing(self, client, service):
        service._conflicts["proj-001"] = [_make_conflict("c-001")]

        resp = client.get("/conflicts/proj-001/c-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["conflict_id"] == "c-001"
        assert data["title"] == "Test conflict c-001"
        assert len(data["tension_elements"]) == 2

    def test_not_found(self, client):
        resp = client.get("/conflicts/proj-001/nonexistent")
        assert resp.status_code == 404

    def test_conflict_includes_suggested_resolutions(self, client, service):
        service._conflicts["proj-001"] = [_make_conflict("c-001")]

        resp = client.get("/conflicts/proj-001/c-001")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["suggested_resolutions"]) == 2
        assert data["suggested_resolutions"][0]["response_type"] == "set_priority"


class TestResolveConflict:
    """Test POST /{project_id}/{conflict_id}/resolve endpoint."""

    def test_resolve_success(self, client, service):
        service._conflicts["proj-001"] = [_make_conflict("c-001")]
        service._save_conflicts_to_redis = AsyncMock()

        resp = client.post(
            "/conflicts/proj-001/c-001/resolve",
            json={
                "response_type": "accept_tradeoff",
                "description": "I accept the current handling",
                "affected_goal_ids": ["goal-a"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "user_resolved"
        assert data["user_response"]["response_type"] == "accept_tradeoff"
        assert data["resolved_at"] is not None

    def test_resolve_not_found(self, client, service):
        resp = client.post(
            "/conflicts/proj-001/nonexistent/resolve",
            json={"response_type": "accept_tradeoff"},
        )
        assert resp.status_code == 404

    def test_resolve_with_set_priority(self, client, service):
        service._conflicts["proj-001"] = [_make_conflict("c-001")]
        service._save_conflicts_to_redis = AsyncMock()

        resp = client.post(
            "/conflicts/proj-001/c-001/resolve",
            json={
                "response_type": "set_priority",
                "description": "Prioritize Goal A",
                "affected_goal_ids": ["goal-a", "goal-b"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_response"]["response_type"] == "set_priority"
        assert data["user_response"]["affected_goal_ids"] == ["goal-a", "goal-b"]

    def test_resolve_with_adjust_goal(self, client, service):
        service._conflicts["proj-001"] = [_make_conflict("c-001")]
        service._save_conflicts_to_redis = AsyncMock()

        resp = client.post(
            "/conflicts/proj-001/c-001/resolve",
            json={
                "response_type": "adjust_goal",
                "description": "Reduced scope of Goal B",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "user_resolved"

    def test_resolve_with_clarify_intent(self, client, service):
        service._conflicts["proj-001"] = [_make_conflict("c-001")]
        service._save_conflicts_to_redis = AsyncMock()

        resp = client.post(
            "/conflicts/proj-001/c-001/resolve",
            json={
                "response_type": "clarify_intent",
                "description": "I want quality over speed",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "user_resolved"


class TestServiceUnavailable:
    """Test behavior when service is not initialized."""

    def test_list_returns_503(self):
        """When service not initialized, endpoints return 503."""
        from services import conflict_detection_service as mod
        old = mod._conflict_detection_service
        try:
            mod._conflict_detection_service = None
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            resp = client.get("/conflicts/proj-001")
            assert resp.status_code == 503
        finally:
            mod._conflict_detection_service = old

    def test_count_returns_503(self):
        from services import conflict_detection_service as mod
        old = mod._conflict_detection_service
        try:
            mod._conflict_detection_service = None
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            resp = client.get("/conflicts/proj-001/count")
            assert resp.status_code == 503
        finally:
            mod._conflict_detection_service = old

    def test_resolve_returns_503(self):
        from services import conflict_detection_service as mod
        old = mod._conflict_detection_service
        try:
            mod._conflict_detection_service = None
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            resp = client.post(
                "/conflicts/proj-001/c-001/resolve",
                json={"response_type": "accept_tradeoff"},
            )
            assert resp.status_code == 503
        finally:
            mod._conflict_detection_service = old
