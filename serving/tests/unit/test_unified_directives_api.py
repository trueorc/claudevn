"""Tests for unified directives API endpoints.

Tests cover:
- POST /unified-directives (submit)
- POST /unified-directives/{id}/comments (add comment)
- GET /unified-directives (list)
- GET /unified-directives/{id} (get)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.unified_directives import router
from models.unified_directive import (
    DirectiveComment,
    DirectiveIntent,
    DirectiveLifecycleStatus,
    DirectiveOutcome,
    UnifiedDirective,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_directive():
    """A sample unified directive for test responses."""
    now = datetime.now(timezone.utc)
    return UnifiedDirective(
        directive_id="udir_test_001",
        project_id="project-001",
        text="Create a login page",
        intent=DirectiveIntent.NEW_WORK,
        lifecycle_status=DirectiveLifecycleStatus.COMPLETE,
        outcome=DirectiveOutcome(goal_id_created="goal_test_001"),
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def mock_service(sample_directive):
    """Mocked unified directive service."""
    service = MagicMock()
    service.submit = AsyncMock(return_value=sample_directive)
    service.add_comment = AsyncMock(return_value=sample_directive)
    service.get_directive = AsyncMock(return_value=sample_directive)
    service.list_directives = AsyncMock(return_value=[sample_directive])
    return service


@pytest.fixture
def client(mock_service):
    """Test client with mocked service."""
    app = FastAPI()
    app.include_router(router)

    with patch(
        "api.unified_directives.get_unified_directive_service",
        return_value=mock_service,
    ):
        yield TestClient(app)


# ============================================================================
# POST /unified-directives
# ============================================================================


class TestSubmitEndpoint:
    """Tests for the submit directive endpoint."""

    def test_submit_success(self, client, mock_service):
        response = client.post(
            "/unified-directives",
            json={"text": "Create a login page", "project_id": "project-001"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["directive_id"] == "udir_test_001"
        assert data["intent"] == "new_work"
        assert data["lifecycle_status"] == "complete"
        mock_service.submit.assert_called_once_with(
            project_id="project-001",
            text="Create a login page",
            parent_directive_id=None,
        )

    def test_submit_with_parent(self, client, mock_service):
        response = client.post(
            "/unified-directives",
            json={
                "text": "Also add OAuth",
                "project_id": "project-001",
                "parent_directive_id": "udir_parent_001",
            },
        )
        assert response.status_code == 200
        mock_service.submit.assert_called_once_with(
            project_id="project-001",
            text="Also add OAuth",
            parent_directive_id="udir_parent_001",
        )

    def test_submit_empty_text_rejected(self, client):
        response = client.post(
            "/unified-directives",
            json={"text": "", "project_id": "project-001"},
        )
        assert response.status_code == 422

    def test_submit_missing_project_id(self, client):
        response = client.post(
            "/unified-directives",
            json={"text": "Create something"},
        )
        assert response.status_code == 422


# ============================================================================
# POST /unified-directives/{id}/comments
# ============================================================================


class TestAddCommentEndpoint:
    """Tests for the add comment endpoint."""

    def test_add_comment_success(self, client, mock_service):
        response = client.post(
            "/unified-directives/udir_test_001/comments?project_id=project-001",
            json={"content": "What about SSO?"},
        )
        assert response.status_code == 200
        mock_service.add_comment.assert_called_once_with(
            project_id="project-001",
            directive_id="udir_test_001",
            content="What about SSO?",
        )

    def test_add_comment_not_found(self, client, mock_service):
        mock_service.add_comment.side_effect = ValueError("Directive not found")
        response = client.post(
            "/unified-directives/nonexistent/comments?project_id=project-001",
            json={"content": "test"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_add_comment_empty_content_rejected(self, client):
        response = client.post(
            "/unified-directives/udir_test_001/comments?project_id=project-001",
            json={"content": ""},
        )
        assert response.status_code == 422


# ============================================================================
# GET /unified-directives
# ============================================================================


class TestListEndpoint:
    """Tests for the list directives endpoint."""

    def test_list_success(self, client, mock_service):
        response = client.get(
            "/unified-directives?project_id=project-001",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["directive_id"] == "udir_test_001"

    def test_list_missing_project_id(self, client):
        response = client.get("/unified-directives")
        assert response.status_code == 422

    def test_list_with_limit(self, client, mock_service):
        response = client.get(
            "/unified-directives?project_id=project-001&limit=10",
        )
        assert response.status_code == 200
        mock_service.list_directives.assert_called_once_with(
            project_id="project-001",
            limit=10,
        )


# ============================================================================
# GET /unified-directives/{id}
# ============================================================================


# ============================================================================
# DELETE /unified-directives
# ============================================================================


class TestDeleteEndpoint:
    """Tests for the delete directives endpoint."""

    def test_delete_success(self, client, mock_service):
        mock_service.delete_project_directives = AsyncMock(return_value=3)
        response = client.delete(
            "/unified-directives?project_id=project-001",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] == 3
        assert data["project_id"] == "project-001"

    def test_delete_requires_project_id(self, client, mock_service):
        response = client.delete("/unified-directives")
        assert response.status_code == 422  # missing required query param


# ============================================================================
# GET /unified-directives/{id}
# ============================================================================


class TestGetEndpoint:
    """Tests for the get directive endpoint."""

    def test_get_success(self, client, mock_service):
        response = client.get(
            "/unified-directives/udir_test_001?project_id=project-001",
        )
        assert response.status_code == 200
        assert response.json()["directive_id"] == "udir_test_001"

    def test_get_not_found(self, client, mock_service):
        mock_service.get_directive.return_value = None
        response = client.get(
            "/unified-directives/nonexistent?project_id=project-001",
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
