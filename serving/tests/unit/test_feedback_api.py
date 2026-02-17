"""Tests for feedback API endpoints."""

import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from models.feedback import (
    FeedbackPattern,
    FeedbackSignal,
    FeedbackType,
    FeedbackSeverity,
)
from api.feedback import router


def _make_pattern(
    pattern_id="pat-001",
    project_id="proj-001",
    feedback_type=FeedbackType.BLOCKER,
    signal_count=3,
    description="Test pattern",
):
    return FeedbackPattern(
        pattern_id=pattern_id,
        project_id=project_id,
        feedback_type=feedback_type,
        signal_ids=[f"sig-{i}" for i in range(signal_count)],
        signal_count=signal_count,
        description=description,
        affected_clusters=["auth"],
        affected_work_types=["feature"],
        first_seen=datetime(2025, 1, 1, tzinfo=timezone.utc),
        last_seen=datetime(2025, 1, 2, tzinfo=timezone.utc),
    )


def _make_signal(
    signal_id="sig-001",
    project_id="proj-001",
    feedback_type=FeedbackType.BLOCKER,
    severity=FeedbackSeverity.HIGH,
):
    return FeedbackSignal(
        signal_id=signal_id,
        project_id=project_id,
        worker_id="worker-001",
        task_id="task-001",
        feedback_type=feedback_type,
        severity=severity,
        description="Test signal",
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.get_patterns = AsyncMock(return_value=[])
    service.get_signals = AsyncMock(return_value=[])
    return service


@pytest.fixture
def client(mock_service):
    app = FastAPI()
    app.include_router(router)

    with patch(
        "api.feedback.get_feedback_aggregation_service",
        return_value=mock_service,
    ):
        yield TestClient(app)


class TestListPatterns:
    """Tests for GET /feedback/{project_id}/patterns."""

    def test_returns_empty_patterns(self, client):
        resp = client.get("/feedback/proj-001/patterns")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == "proj-001"
        assert data["patterns"] == []
        assert data["total"] == 0
        assert data["by_type"] == {}

    def test_returns_patterns_with_by_type(self, client, mock_service):
        mock_service.get_patterns.return_value = [
            _make_pattern(pattern_id="p1", feedback_type=FeedbackType.BLOCKER),
            _make_pattern(pattern_id="p2", feedback_type=FeedbackType.BLOCKER),
            _make_pattern(pattern_id="p3", feedback_type=FeedbackType.CHALLENGE),
        ]
        resp = client.get("/feedback/proj-001/patterns")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["by_type"]["blocker"] == 2
        assert data["by_type"]["challenge"] == 1

    def test_returns_503_when_service_unavailable(self):
        app = FastAPI()
        app.include_router(router)
        with patch(
            "api.feedback.get_feedback_aggregation_service",
            side_effect=RuntimeError("not initialized"),
        ):
            c = TestClient(app)
            resp = c.get("/feedback/proj-001/patterns")
            assert resp.status_code == 503


class TestListSignals:
    """Tests for GET /feedback/{project_id}/signals."""

    def test_returns_empty_signals(self, client):
        resp = client.get("/feedback/proj-001/signals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == "proj-001"
        assert data["signals"] == []
        assert data["total"] == 0

    def test_returns_signals(self, client, mock_service):
        mock_service.get_signals.return_value = [
            _make_signal(signal_id="s1"),
            _make_signal(signal_id="s2"),
        ]
        resp = client.get("/feedback/proj-001/signals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["signals"]) == 2

    def test_filters_by_feedback_type(self, client, mock_service):
        mock_service.get_signals.return_value = [
            _make_signal(feedback_type=FeedbackType.CHALLENGE),
        ]
        resp = client.get("/feedback/proj-001/signals?feedback_type=challenge")
        assert resp.status_code == 200
        mock_service.get_signals.assert_called_once_with(
            "proj-001", feedback_type=FeedbackType.CHALLENGE, limit=50
        )

    def test_respects_limit_param(self, client, mock_service):
        resp = client.get("/feedback/proj-001/signals?limit=10")
        assert resp.status_code == 200
        mock_service.get_signals.assert_called_once_with(
            "proj-001", feedback_type=None, limit=10
        )

    def test_rejects_invalid_feedback_type(self, client):
        resp = client.get("/feedback/proj-001/signals?feedback_type=invalid_type")
        assert resp.status_code == 400
        assert "Invalid feedback type" in resp.json()["detail"]

    def test_rejects_limit_out_of_range(self, client):
        resp = client.get("/feedback/proj-001/signals?limit=0")
        assert resp.status_code == 422

        resp = client.get("/feedback/proj-001/signals?limit=500")
        assert resp.status_code == 422

    def test_returns_503_when_service_unavailable(self):
        app = FastAPI()
        app.include_router(router)
        with patch(
            "api.feedback.get_feedback_aggregation_service",
            side_effect=RuntimeError("not initialized"),
        ):
            c = TestClient(app)
            resp = c.get("/feedback/proj-001/signals")
            assert resp.status_code == 503
