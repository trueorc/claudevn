"""Unit tests for characterization REST API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.characterization import router
from models.characterization import (
    BatchCharacterizationResponse,
    CharacterizationResult,
    CharacterizationStatus,
    MeaningAssessment,
    BusinessMeaning,
    TechnicalMeaning,
    ContextualMeaning,
    ContextualRole,
)
from models.ontology import (
    LifecycleStage,
    OntologyTags,
    ProjectSpecificTags,
    TechnicalDomain,
    UniversalTags,
    WorkType,
)


# =============================================================================
# Helpers
# =============================================================================


def make_ontology_tags():
    return OntologyTags(
        universal=UniversalTags(
            work_type=WorkType.FEATURE,
            lifecycle_stage=LifecycleStage.BUILD,
            technical_domains=[TechnicalDomain.BACKEND],
        ),
        project_specific=ProjectSpecificTags(cluster_ids=[]),
    )


def make_meaning():
    return MeaningAssessment(
        business=BusinessMeaning(summary="Adds value"),
        technical=TechnicalMeaning(summary="Implements feature"),
        contextual=ContextualMeaning(
            summary="Core work",
            role=ContextualRole.FOUNDATIONAL,
        ),
    )


def make_result(item_id="item-001", project_id="proj-1", **overrides):
    defaults = dict(
        item_id=item_id,
        project_id=project_id,
        ontology_tags=make_ontology_tags(),
        meaning=make_meaning(),
        status=CharacterizationStatus.COMPLETED,
        confidence=0.85,
    )
    defaults.update(overrides)
    return CharacterizationResult(**defaults)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.get_results_for_project = AsyncMock(return_value=[])
    service.get_result = AsyncMock(return_value=None)
    service.get_stats = AsyncMock(return_value={
        "total": 0, "pending": 0, "in_progress": 0, "completed": 0, "failed": 0
    })
    service.characterize_items = AsyncMock()
    return service


@pytest.fixture
def client(mock_service):
    app = FastAPI()
    app.include_router(router)

    with patch(
        "api.characterization.get_characterization_service",
        return_value=mock_service,
    ):
        yield TestClient(app)


# =============================================================================
# GET /{project_id} — List Characterizations
# =============================================================================


class TestListCharacterizations:
    def test_empty_project(self, client, mock_service):
        mock_service.get_results_for_project.return_value = []
        mock_service.get_stats.return_value = {
            "total": 0, "pending": 0, "in_progress": 0, "completed": 0, "failed": 0
        }

        response = client.get("/characterization/proj-1")
        assert response.status_code == 200

        data = response.json()
        assert data["project_id"] == "proj-1"
        assert data["results"] == []
        assert data["total"] == 0

    def test_with_results(self, client, mock_service):
        results = [
            make_result("item-001"),
            make_result("item-002"),
        ]
        mock_service.get_results_for_project.return_value = results
        mock_service.get_stats.return_value = {
            "total": 2, "pending": 0, "in_progress": 0, "completed": 2, "failed": 0
        }

        response = client.get("/characterization/proj-1")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 2
        assert len(data["results"]) == 2
        assert data["stats"]["completed"] == 2

    def test_status_filter(self, client, mock_service):
        results = [
            make_result("item-001", status=CharacterizationStatus.COMPLETED),
            make_result("item-002", status=CharacterizationStatus.PENDING),
            make_result("item-003", status=CharacterizationStatus.FAILED),
        ]
        mock_service.get_results_for_project.return_value = results

        response = client.get("/characterization/proj-1?status=completed")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert data["results"][0]["item_id"] == "item-001"

    def test_invalid_status_filter(self, client, mock_service):
        mock_service.get_results_for_project.return_value = [make_result()]

        response = client.get("/characterization/proj-1?status=invalid_status")
        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]

    def test_limit(self, client, mock_service):
        results = [make_result(f"item-{i:03d}") for i in range(10)]
        mock_service.get_results_for_project.return_value = results

        response = client.get("/characterization/proj-1?limit=3")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 3


# =============================================================================
# GET /{project_id}/stats — Statistics
# =============================================================================


class TestGetStats:
    def test_returns_stats(self, client, mock_service):
        mock_service.get_stats.return_value = {
            "total": 5, "pending": 1, "in_progress": 1, "completed": 2, "failed": 1
        }

        response = client.get("/characterization/proj-1/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["project_id"] == "proj-1"
        assert data["stats"]["total"] == 5
        assert data["stats"]["completed"] == 2

    def test_empty_project(self, client, mock_service):
        response = client.get("/characterization/proj-1/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["stats"]["total"] == 0


# =============================================================================
# GET /{project_id}/{item_id} — Single Result
# =============================================================================


class TestGetCharacterization:
    def test_found(self, client, mock_service):
        result = make_result()
        mock_service.get_result.return_value = result

        response = client.get("/characterization/proj-1/item-001")
        assert response.status_code == 200

        data = response.json()
        assert data["item_id"] == "item-001"
        assert data["confidence"] == 0.85

    def test_not_found(self, client, mock_service):
        mock_service.get_result.return_value = None

        response = client.get("/characterization/proj-1/nonexistent")
        assert response.status_code == 404
        assert "No characterization found" in response.json()["detail"]


# =============================================================================
# POST /trigger — Manual Trigger
# =============================================================================


class TestTriggerCharacterization:
    def test_success(self, client, mock_service):
        batch_response = BatchCharacterizationResponse(
            project_id="proj-1",
            results=[make_result(status=CharacterizationStatus.PENDING)],
            total=1,
            completed=0,
            failed=0,
        )
        mock_service.characterize_items.return_value = batch_response

        payload = {
            "project_id": "proj-1",
            "items": [
                {
                    "item_id": "item-001",
                    "title": "Add endpoint",
                    "description": "REST API endpoint",
                }
            ],
        }

        response = client.post("/characterization/trigger", json=payload)
        assert response.status_code == 202

        data = response.json()
        assert data["project_id"] == "proj-1"
        assert data["total"] == 1

    def test_multiple_items(self, client, mock_service):
        batch_response = BatchCharacterizationResponse(
            project_id="proj-1",
            results=[
                make_result("item-001", status=CharacterizationStatus.PENDING),
                make_result("item-002", status=CharacterizationStatus.PENDING),
            ],
            total=2,
            completed=0,
            failed=0,
        )
        mock_service.characterize_items.return_value = batch_response

        payload = {
            "project_id": "proj-1",
            "items": [
                {"item_id": "item-001", "title": "Task A", "description": "Do A"},
                {"item_id": "item-002", "title": "Task B", "description": "Do B"},
            ],
        }

        response = client.post("/characterization/trigger", json=payload)
        assert response.status_code == 202
        assert response.json()["total"] == 2

    def test_with_hints(self, client, mock_service):
        batch_response = BatchCharacterizationResponse(
            project_id="proj-1",
            results=[],
            total=1,
            completed=0,
            failed=0,
        )
        mock_service.characterize_items.return_value = batch_response

        payload = {
            "project_id": "proj-1",
            "items": [
                {
                    "item_id": "item-001",
                    "title": "Fix login",
                    "description": "Fix bug",
                    "issue_type_hint": "bug_fix",
                    "area_hint": "auth",
                }
            ],
            "source_goal_id": "goal-42",
        }

        response = client.post("/characterization/trigger", json=payload)
        assert response.status_code == 202

    def test_empty_items_rejected(self, client, mock_service):
        payload = {
            "project_id": "proj-1",
            "items": [],
        }

        response = client.post("/characterization/trigger", json=payload)
        assert response.status_code == 422

    def test_no_compute_available(self, client, mock_service):
        mock_service.characterize_items.side_effect = RuntimeError(
            "No idle compute instances available"
        )

        payload = {
            "project_id": "proj-1",
            "items": [
                {"item_id": "item-001", "title": "Task", "description": "Desc"}
            ],
        }

        response = client.post("/characterization/trigger", json=payload)
        assert response.status_code == 503
        assert "No idle compute" in response.json()["detail"]
