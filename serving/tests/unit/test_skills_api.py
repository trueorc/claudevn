"""Tests for Skills API endpoints (proxy to Marketplace service).

Unit tests for the FastAPI router that proxies skill requests to the Marketplace service.
Tests cover all endpoints with mocked MarketplaceClient to avoid real HTTP calls.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.skills import router
from services.marketplace_client import MarketplaceClient
from fastapi import FastAPI


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_marketplace_client():
    """Create a mock MarketplaceClient for testing."""
    client = MagicMock(spec=MarketplaceClient)
    # Set all methods as AsyncMocks by default
    client.list_skills = AsyncMock()
    client.get_skill = AsyncMock()
    client.get_stats = AsyncMock()
    return client


@pytest.fixture
def app(mock_marketplace_client):
    """Create a FastAPI app with the skills router for testing."""
    app = FastAPI()
    app.include_router(router)

    # Override the marketplace client dependency
    def override_get_marketplace_client():
        return mock_marketplace_client

    from api.skills import get_marketplace_client
    app.dependency_overrides[get_marketplace_client] = override_get_marketplace_client

    return app


@pytest.fixture
def client(app):
    """Create a test client for the FastAPI app."""
    return TestClient(app)


# =============================================================================
# Test: List Skills Endpoint (GET /skills)
# =============================================================================

class TestListSkillsEndpoint:
    """Test GET /skills endpoint."""

    def test_list_skills_no_filters(self, client, mock_marketplace_client):
        """Test listing all skills without filters."""
        # Arrange
        expected_response = {
            "skills": [
                {
                    "id": "code-writer",
                    "name": "Code Writer",
                    "author": "system",
                    "description": "Writes code"
                },
                {
                    "id": "test-automator",
                    "name": "Test Automator",
                    "author": "system",
                    "description": "Writes tests"
                }
            ],
            "total": 2,
            "by_author": {"system": 2}
        }
        mock_marketplace_client.list_skills.return_value = expected_response

        # Act
        response = client.get("/skills")

        # Assert
        assert response.status_code == 200
        assert response.json() == expected_response
        mock_marketplace_client.list_skills.assert_called_once_with(tags=None)

    def test_list_skills_with_single_tag(self, client, mock_marketplace_client):
        """Test listing skills filtered by a single tag."""
        # Arrange
        expected_response = {
            "skills": [
                {
                    "id": "code-writer",
                    "name": "Code Writer",
                    "tags": ["coding"]
                }
            ],
            "total": 1
        }
        mock_marketplace_client.list_skills.return_value = expected_response

        # Act
        response = client.get("/skills?tags=coding")

        # Assert
        assert response.status_code == 200
        assert response.json() == expected_response
        mock_marketplace_client.list_skills.assert_called_once_with(tags=["coding"])

    def test_list_skills_with_multiple_tags(self, client, mock_marketplace_client):
        """Test listing skills filtered by multiple comma-separated tags."""
        # Arrange
        expected_response = {
            "skills": [
                {
                    "id": "code-writer",
                    "name": "Code Writer",
                    "tags": ["coding", "python"]
                }
            ],
            "total": 1
        }
        mock_marketplace_client.list_skills.return_value = expected_response

        # Act
        response = client.get("/skills?tags=coding,python")

        # Assert
        assert response.status_code == 200
        assert response.json() == expected_response
        mock_marketplace_client.list_skills.assert_called_once_with(tags=["coding", "python"])

    def test_list_skills_with_author_filter(self, client, mock_marketplace_client):
        """Test listing skills filtered by author (client-side filtering)."""
        # Arrange
        marketplace_response = {
            "skills": [
                {"id": "skill-1", "author": "system", "name": "Skill 1"},
                {"id": "skill-2", "author": "custom", "name": "Skill 2"},
                {"id": "skill-3", "author": "system", "name": "Skill 3"}
            ],
            "total": 3,
            "by_author": {"system": 2, "custom": 1}
        }
        mock_marketplace_client.list_skills.return_value = marketplace_response

        # Act
        response = client.get("/skills?author=system")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["skills"]) == 2
        assert all(skill["author"] == "system" for skill in data["skills"])
        mock_marketplace_client.list_skills.assert_called_once_with(tags=None)

    def test_list_skills_with_tags_and_author(self, client, mock_marketplace_client):
        """Test listing skills with both tag and author filters."""
        # Arrange - marketplace returns skills matching tag filter
        # Then API applies author filter client-side
        marketplace_response = {
            "skills": [
                {"id": "skill-1", "author": "system", "tags": ["coding"]},
                {"id": "skill-2", "author": "custom", "tags": ["coding"]}
            ],
            "total": 2  # Total from marketplace (tag-filtered only)
        }
        mock_marketplace_client.list_skills.return_value = marketplace_response

        # Act
        response = client.get("/skills?tags=coding&author=system")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1  # After author filter
        assert len(data["skills"]) == 1
        assert data["skills"][0]["id"] == "skill-1"
        mock_marketplace_client.list_skills.assert_called_once_with(tags=["coding"])

    def test_list_skills_error_handling(self, client, mock_marketplace_client):
        """Test error handling when marketplace client raises exception."""
        # Arrange
        mock_marketplace_client.list_skills.side_effect = Exception("Marketplace unavailable")

        # Act
        response = client.get("/skills")

        # Assert
        assert response.status_code == 500
        assert "Failed to list skills" in response.json()["detail"]


# =============================================================================
# Test: Get Skill Endpoint (GET /skills/{skill_id})
# =============================================================================

class TestGetSkillEndpoint:
    """Test GET /skills/{skill_id} endpoint."""

    def test_get_skill_success(self, client, mock_marketplace_client):
        """Test getting a specific skill successfully."""
        # Arrange
        expected_skill = {
            "id": "code-writer",
            "name": "Code Writer",
            "author": "system",
            "description": "Expert code writer",
            "capabilities": ["python", "javascript"],
            "claude_md": "# Code Writer\nYou are an expert..."
        }
        mock_marketplace_client.get_skill.return_value = expected_skill

        # Act
        response = client.get("/skills/code-writer")

        # Assert
        assert response.status_code == 200
        assert response.json() == expected_skill
        mock_marketplace_client.get_skill.assert_called_once_with("code-writer")

    def test_get_skill_not_found(self, client, mock_marketplace_client):
        """Test getting a non-existent skill returns 404."""
        # Arrange
        mock_marketplace_client.get_skill.side_effect = Exception("Skill not found")

        # Act
        response = client.get("/skills/nonexistent-skill")

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
        mock_marketplace_client.get_skill.assert_called_once_with("nonexistent-skill")

    def test_get_skill_with_special_characters(self, client, mock_marketplace_client):
        """Test getting a skill with special characters in ID."""
        # Arrange
        skill_id = "custom-skill-v2"
        expected_skill = {
            "id": skill_id,
            "name": "Custom Skill v2",
            "author": "custom"
        }
        mock_marketplace_client.get_skill.return_value = expected_skill

        # Act
        response = client.get(f"/skills/{skill_id}")

        # Assert
        assert response.status_code == 200
        assert response.json() == expected_skill
        mock_marketplace_client.get_skill.assert_called_once_with(skill_id)


# =============================================================================
# Test: Get Stats Endpoint (GET /skills/stats/summary)
# =============================================================================

class TestGetStatsEndpoint:
    """Test GET /skills/stats/summary endpoint."""

    def test_get_stats_success(self, client, mock_marketplace_client):
        """Test getting skill statistics successfully."""
        # Arrange
        expected_stats = {
            "total_skills": 10,
            "by_author": {
                "system": 6,
                "custom": 4
            },
            "by_tag": {
                "coding": 5,
                "testing": 3,
                "review": 2
            },
            "total_tags": 8
        }
        mock_marketplace_client.get_stats.return_value = expected_stats

        # Act
        response = client.get("/skills/stats/summary")

        # Assert
        assert response.status_code == 200
        assert response.json() == expected_stats
        mock_marketplace_client.get_stats.assert_called_once()

    def test_get_stats_empty_marketplace(self, client, mock_marketplace_client):
        """Test getting stats when marketplace has no skills."""
        # Arrange
        expected_stats = {
            "total_skills": 0,
            "by_author": {},
            "by_tag": {},
            "total_tags": 0
        }
        mock_marketplace_client.get_stats.return_value = expected_stats

        # Act
        response = client.get("/skills/stats/summary")

        # Assert
        assert response.status_code == 200
        assert response.json() == expected_stats
        assert response.json()["total_skills"] == 0

    def test_get_stats_error_handling(self, client, mock_marketplace_client):
        """Test error handling when stats endpoint fails."""
        # Arrange
        mock_marketplace_client.get_stats.side_effect = Exception("Stats service unavailable")

        # Act
        response = client.get("/skills/stats/summary")

        # Assert
        assert response.status_code == 500
        assert "Failed to get skill stats" in response.json()["detail"]


# =============================================================================
# Test: Tag Parsing Edge Cases
# =============================================================================

class TestTagParsing:
    """Test edge cases in tag parsing."""

    def test_tags_with_whitespace(self, client, mock_marketplace_client):
        """Test that tags with whitespace are properly trimmed."""
        # Arrange
        mock_marketplace_client.list_skills.return_value = {"skills": [], "total": 0}

        # Act
        response = client.get("/skills?tags=coding,%20testing,%20%20review")

        # Assert
        assert response.status_code == 200
        # Verify that tags are trimmed
        call_args = mock_marketplace_client.list_skills.call_args
        tags = call_args.kwargs.get("tags")
        assert tags == ["coding", "testing", "review"]

    def test_empty_tags_parameter(self, client, mock_marketplace_client):
        """Test that empty tags parameter is handled correctly."""
        # Arrange
        mock_marketplace_client.list_skills.return_value = {"skills": [], "total": 0}

        # Act
        response = client.get("/skills?tags=")

        # Assert
        assert response.status_code == 200
        # Empty string is falsy, so tags=None (no filtering)
        call_args = mock_marketplace_client.list_skills.call_args
        tags = call_args.kwargs.get("tags")
        assert tags is None


# =============================================================================
# Test: Author Filter Edge Cases
# =============================================================================

class TestAuthorFiltering:
    """Test edge cases in author filtering."""

    def test_author_filter_no_matches(self, client, mock_marketplace_client):
        """Test author filter when no skills match."""
        # Arrange
        marketplace_response = {
            "skills": [
                {"id": "skill-1", "author": "system"},
                {"id": "skill-2", "author": "system"}
            ],
            "total": 2
        }
        mock_marketplace_client.list_skills.return_value = marketplace_response

        # Act
        response = client.get("/skills?author=nonexistent")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["skills"]) == 0

    def test_author_filter_case_sensitive(self, client, mock_marketplace_client):
        """Test that author filter is case-sensitive."""
        # Arrange
        marketplace_response = {
            "skills": [
                {"id": "skill-1", "author": "System"},
                {"id": "skill-2", "author": "system"}
            ],
            "total": 2
        }
        mock_marketplace_client.list_skills.return_value = marketplace_response

        # Act
        response = client.get("/skills?author=system")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["skills"][0]["author"] == "system"

    def test_author_filter_missing_author_field(self, client, mock_marketplace_client):
        """Test author filter when some skills don't have author field."""
        # Arrange
        marketplace_response = {
            "skills": [
                {"id": "skill-1", "author": "system"},
                {"id": "skill-2", "name": "No Author"},  # Missing author field
                {"id": "skill-3", "author": "custom"}
            ],
            "total": 3
        }
        mock_marketplace_client.list_skills.return_value = marketplace_response

        # Act
        response = client.get("/skills?author=system")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["skills"][0]["id"] == "skill-1"
