"""Unit tests for decision traces API router.

Tests the REST endpoints for querying decision traces.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.decision_traces import router
from models.decision_trace import (
    DecisionImpact,
    DecisionPointType,
    DecisionTrace,
    DecisionTrigger,
)
from services.decision_trace_service import DecisionTraceService


# =============================================================================
# Fixtures
# =============================================================================


def make_trace(
    trace_id="trace-test-001",
    project_id="proj-1",
    decision_type=DecisionPointType.PROFILE_SHIFT,
    related_trace_ids=None,
    affected_items=None,
):
    """Helper to create a DecisionTrace for testing."""
    return DecisionTrace(
        trace_id=trace_id,
        project_id=project_id,
        decision_type=decision_type,
        trigger=DecisionTrigger(trigger_type="test"),
        decision_summary="Test decision",
        impact=DecisionImpact(affected_item_ids=affected_items or []),
        related_trace_ids=related_trace_ids or [],
    )


def create_test_app(mock_service):
    """Create a test FastAPI app with mocked service dependency."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[DecisionTraceService] = lambda: mock_service
    return app


@pytest.fixture
def mock_service():
    """Create a mock DecisionTraceService."""
    service = MagicMock(spec=DecisionTraceService)
    service.get_traces = AsyncMock(return_value=[])
    service.get_traces_for_item = AsyncMock(return_value=[])
    service.get_trace_by_id = AsyncMock(return_value=None)
    service.get_trace_chain = AsyncMock(return_value=[])
    return service


@pytest.fixture
def client(mock_service):
    """Create a test client with mocked service."""
    app = FastAPI()
    app.include_router(router)

    from services.decision_trace_service import get_decision_trace_service
    app.dependency_overrides[get_decision_trace_service] = lambda: mock_service

    return TestClient(app)


# =============================================================================
# TestGetProjectTraces
# =============================================================================


class TestGetProjectTraces:
    """Tests for GET /api/v1/decision-traces/projects/{project_id}."""

    def test_get_traces_empty(self, client, mock_service):
        """Returns empty list when no traces exist."""
        response = client.get("/api/v1/decision-traces/projects/proj-1")
        assert response.status_code == 200
        data = response.json()
        assert data["traces"] == []
        assert data["count"] == 0

    def test_get_traces_returns_results(self, client, mock_service):
        """Returns traces for a project."""
        mock_service.get_traces.return_value = [make_trace()]
        response = client.get("/api/v1/decision-traces/projects/proj-1")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["traces"][0]["trace_id"] == "trace-test-001"

    def test_get_traces_with_type_filter(self, client, mock_service):
        """Filters traces by decision type."""
        response = client.get(
            "/api/v1/decision-traces/projects/proj-1?decision_type=profile_shift"
        )
        assert response.status_code == 200
        mock_service.get_traces.assert_called_once()
        call_kwargs = mock_service.get_traces.call_args[1]
        assert call_kwargs["decision_type"] == DecisionPointType.PROFILE_SHIFT

    def test_get_traces_with_limit(self, client, mock_service):
        """Respects limit parameter."""
        response = client.get(
            "/api/v1/decision-traces/projects/proj-1?limit=10"
        )
        assert response.status_code == 200
        call_kwargs = mock_service.get_traces.call_args[1]
        assert call_kwargs["limit"] == 10


# =============================================================================
# TestGetItemTraces
# =============================================================================


class TestGetItemTraces:
    """Tests for GET /api/v1/decision-traces/projects/{project_id}/items/{item_id}."""

    def test_get_item_traces_empty(self, client, mock_service):
        """Returns empty list when no traces for item."""
        response = client.get(
            "/api/v1/decision-traces/projects/proj-1/items/item-1"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["traces"] == []
        assert data["count"] == 0

    def test_get_item_traces_returns_results(self, client, mock_service):
        """Returns traces for a specific item."""
        mock_service.get_traces_for_item.return_value = [
            make_trace(affected_items=["item-1"])
        ]
        response = client.get(
            "/api/v1/decision-traces/projects/proj-1/items/item-1"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1

    def test_get_item_traces_passes_correct_params(self, client, mock_service):
        """Passes correct project_id and item_id to service."""
        response = client.get(
            "/api/v1/decision-traces/projects/proj-1/items/item-42?limit=5"
        )
        mock_service.get_traces_for_item.assert_called_once_with(
            project_id="proj-1",
            item_id="item-42",
            limit=5,
        )


# =============================================================================
# TestGetTrace
# =============================================================================


class TestGetTrace:
    """Tests for GET /api/v1/decision-traces/projects/{project_id}/traces/{trace_id}."""

    def test_get_trace_found(self, client, mock_service):
        """Returns trace when found."""
        mock_service.get_trace_by_id.return_value = make_trace()
        response = client.get(
            "/api/v1/decision-traces/projects/proj-1/traces/trace-test-001"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trace_id"] == "trace-test-001"

    def test_get_trace_not_found(self, client, mock_service):
        """Returns 404 when trace not found."""
        mock_service.get_trace_by_id.return_value = None
        response = client.get(
            "/api/v1/decision-traces/projects/proj-1/traces/nonexistent"
        )
        assert response.status_code == 404


# =============================================================================
# TestGetTraceChain
# =============================================================================


class TestGetTraceChain:
    """Tests for GET /api/v1/decision-traces/projects/{project_id}/traces/{trace_id}/chain."""

    def test_get_chain_found(self, client, mock_service):
        """Returns chain when trace found."""
        mock_service.get_trace_chain.return_value = [
            make_trace(trace_id="t1", related_trace_ids=["t2"]),
            make_trace(trace_id="t2"),
        ]
        response = client.get(
            "/api/v1/decision-traces/projects/proj-1/traces/t1/chain"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["depth"] == 2
        assert len(data["chain"]) == 2

    def test_get_chain_not_found(self, client, mock_service):
        """Returns 404 when starting trace not found."""
        mock_service.get_trace_chain.return_value = []
        response = client.get(
            "/api/v1/decision-traces/projects/proj-1/traces/nonexistent/chain"
        )
        assert response.status_code == 404

    def test_get_chain_with_max_depth(self, client, mock_service):
        """Passes max_depth parameter to service."""
        mock_service.get_trace_chain.return_value = [make_trace()]
        response = client.get(
            "/api/v1/decision-traces/projects/proj-1/traces/t1/chain?max_depth=3"
        )
        assert response.status_code == 200
        mock_service.get_trace_chain.assert_called_once_with(
            project_id="proj-1",
            trace_id="t1",
            max_depth=3,
        )
