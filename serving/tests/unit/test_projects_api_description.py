"""Tests for project creation API with various description values (#589).

Verifies that the POST /api/projects endpoint correctly handles:
- description: null in payload
- no description field in payload
- description with a valid string
- description with whitespace only
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from models.project import Project, ProjectCreateRequest, ProjectStatus
from api.projects import router


@pytest.fixture
def mock_project_service():
    """Create a mock project service that returns a Project from any create request."""
    service = AsyncMock()

    async def fake_create(request: ProjectCreateRequest):
        return Project(
            project_id="proj_test123",
            name=request.name,
            description=request.description or "",
            status=ProjectStatus.ACTIVE,
        )

    service.create_project = AsyncMock(side_effect=fake_create)
    return service


@pytest.fixture
def client(mock_project_service):
    """Create a test client with mocked project service."""
    app = FastAPI()
    app.include_router(router, prefix="/api")

    with patch("api.projects.get_project_service", return_value=mock_project_service):
        yield TestClient(app)


class TestCreateProjectDescription:
    """Test POST /api/projects with various description values."""

    def test_create_project_description_null(self, client, mock_project_service):
        """POST with description: null creates project successfully."""
        response = client.post("/api/projects", json={
            "name": "Test Project",
            "description": None,
        })

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["description"] == ""

        # Verify service received None description
        call_args = mock_project_service.create_project.call_args[0][0]
        assert call_args.description is None

    def test_create_project_description_omitted(self, client, mock_project_service):
        """POST with no description field creates project successfully."""
        response = client.post("/api/projects", json={
            "name": "Test Project",
        })

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["description"] == ""

        # Verify service received None description (default)
        call_args = mock_project_service.create_project.call_args[0][0]
        assert call_args.description is None

    def test_create_project_description_provided(self, client, mock_project_service):
        """POST with description string creates project with that description."""
        response = client.post("/api/projects", json={
            "name": "Test Project",
            "description": "A great project",
        })

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["description"] == "A great project"

        # Verify service received the description
        call_args = mock_project_service.create_project.call_args[0][0]
        assert call_args.description == "A great project"

    def test_create_project_description_empty_string(self, client, mock_project_service):
        """POST with description: '' creates project with empty description."""
        response = client.post("/api/projects", json={
            "name": "Test Project",
            "description": "",
        })

        assert response.status_code == 201
        data = response.json()
        assert data["description"] == ""

    def test_create_project_description_whitespace(self, client, mock_project_service):
        """POST with whitespace-only description is accepted."""
        response = client.post("/api/projects", json={
            "name": "Test Project",
            "description": "   ",
        })

        assert response.status_code == 201
