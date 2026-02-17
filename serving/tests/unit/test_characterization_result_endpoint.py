"""Unit tests for POST /compute/characterization/{id}/result endpoint.

Tests the REST endpoint that receives characterization results from compute
instances (mirroring the MCP tool claudevn_submit_characterization).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.compute import router


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_submit_characterization():
    """Mock the MCP submit_characterization function."""
    response = MagicMock()
    response.acknowledged = True
    response.status = "stored"

    with patch(
        "api.compute.submit_characterization",
        new_callable=AsyncMock,
        return_value=(response, None),
    ) as mock_fn:
        # Also patch the imports inside the endpoint
        with patch(
            "mcp.tools.characterization.submit_characterization",
            new_callable=AsyncMock,
            return_value=(response, None),
        ):
            yield mock_fn


@pytest.fixture
def mock_registry():
    """Mock the compute registry dependency."""
    registry = MagicMock()
    registry.get_instance = AsyncMock(return_value=None)
    return registry


@pytest.fixture
def client(mock_registry):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    yield TestClient(app)


# =============================================================================
# Tests
# =============================================================================


class TestSubmitCharacterizationResult:
    """Tests for POST /compute/characterization/{id}/result."""

    def test_success_single_item(self, client):
        """Test successful submission of a single characterization."""
        response_obj = MagicMock()
        response_obj.acknowledged = True
        response_obj.status = "stored"

        with patch(
            "mcp.tools.characterization.submit_characterization",
            new_callable=AsyncMock,
            return_value=(response_obj, None),
        ):
            payload = {
                "characterization_id": "char-abc123",
                "project_id": "proj-1",
                "characterizations": [
                    {
                        "item_id": "item-001",
                        "project_id": "proj-1",
                        "ontology_tags": {
                            "work_type": "feature",
                            "lifecycle_stage": "build",
                            "technical_domains": ["backend"],
                        },
                        "meaning": {
                            "business_summary": "Adds REST endpoint",
                            "technical_summary": "New FastAPI route",
                        },
                        "confidence": 0.9,
                        "evaluated_in_isolation": True,
                        "evaluated_in_context": False,
                    }
                ],
            }

            response = client.post(
                "/api/v1/compute/characterization/char-abc123/result",
                json=payload,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stored"
        assert data["characterization_id"] == "char-abc123"
        assert data["stored_count"] == 1
        assert data["total_count"] == 1
        assert data["errors"] is None

    def test_success_multiple_items(self, client):
        """Test successful submission of multiple characterizations."""
        response_obj = MagicMock()
        response_obj.acknowledged = True
        response_obj.status = "stored"

        with patch(
            "mcp.tools.characterization.submit_characterization",
            new_callable=AsyncMock,
            return_value=(response_obj, None),
        ):
            payload = {
                "characterization_id": "char-multi",
                "project_id": "proj-1",
                "characterizations": [
                    {
                        "item_id": "item-001",
                        "ontology_tags": {
                            "work_type": "feature",
                            "lifecycle_stage": "build",
                            "technical_domains": ["backend"],
                        },
                        "meaning": {
                            "business_summary": "Feature A",
                            "technical_summary": "Impl A",
                        },
                        "confidence": 0.85,
                    },
                    {
                        "item_id": "item-002",
                        "ontology_tags": {
                            "work_type": "bug_fix",
                            "lifecycle_stage": "test",
                            "technical_domains": ["frontend"],
                        },
                        "meaning": {
                            "business_summary": "Fix B",
                            "technical_summary": "Patch B",
                        },
                        "confidence": 0.9,
                    },
                ],
            }

            response = client.post(
                "/api/v1/compute/characterization/char-multi/result",
                json=payload,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["stored_count"] == 2
        assert data["total_count"] == 2

    def test_empty_characterizations_rejected(self, client):
        """Test that empty characterizations list is rejected."""
        payload = {
            "characterization_id": "char-empty",
            "project_id": "proj-1",
            "characterizations": [],
        }

        response = client.post(
            "/api/v1/compute/characterization/char-empty/result",
            json=payload,
        )

        assert response.status_code == 400
        assert "No characterizations" in response.json()["detail"]

    def test_with_dependencies(self, client):
        """Test submission with dependency information."""
        response_obj = MagicMock()
        response_obj.acknowledged = True
        response_obj.status = "stored"

        with patch(
            "mcp.tools.characterization.submit_characterization",
            new_callable=AsyncMock,
            return_value=(response_obj, None),
        ):
            payload = {
                "characterization_id": "char-deps",
                "project_id": "proj-1",
                "characterizations": [
                    {
                        "item_id": "item-001",
                        "ontology_tags": {
                            "work_type": "feature",
                            "lifecycle_stage": "build",
                            "technical_domains": ["api"],
                        },
                        "meaning": {
                            "business_summary": "API endpoint",
                            "technical_summary": "REST route",
                        },
                        "dependencies": [
                            {
                                "target_item_id": "item-002",
                                "relation": "blocks",
                                "dependency_type": "structural",
                                "reasoning": "API must exist first",
                                "confidence": 0.95,
                            }
                        ],
                        "confidence": 0.88,
                        "evaluated_in_context": True,
                        "topology_item_count": 5,
                    }
                ],
            }

            response = client.post(
                "/api/v1/compute/characterization/char-deps/result",
                json=payload,
            )

        assert response.status_code == 200
        assert response.json()["stored_count"] == 1

    def test_with_string_dependencies(self, client):
        """Test submission with dependencies as plain strings (#827)."""
        response_obj = MagicMock()
        response_obj.acknowledged = True
        response_obj.status = "stored"

        with patch(
            "mcp.tools.characterization.submit_characterization",
            new_callable=AsyncMock,
            return_value=(response_obj, None),
        ) as mock_submit:
            payload = {
                "characterization_id": "char-str-deps",
                "project_id": "proj-1",
                "characterizations": [
                    {
                        "item_id": "item-001",
                        "ontology_tags": {
                            "work_type": "feature",
                            "lifecycle_stage": "build",
                            "technical_domains": ["api"],
                        },
                        "meaning": {
                            "business_summary": "API endpoint",
                            "technical_summary": "REST route",
                        },
                        "dependencies": ["item-002", "item-003"],
                        "confidence": 0.88,
                    }
                ],
            }

            response = client.post(
                "/api/v1/compute/characterization/char-str-deps/result",
                json=payload,
            )

        assert response.status_code == 200
        assert response.json()["stored_count"] == 1

        # Verify string deps were converted to DependencyInput with defaults
        call_args = mock_submit.call_args[0][0]
        assert len(call_args.dependencies) == 2
        assert call_args.dependencies[0].target_item_id == "item-002"
        assert call_args.dependencies[0].relation == "related_to"
        assert call_args.dependencies[1].target_item_id == "item-003"

    def test_with_mixed_dependencies(self, client):
        """Test submission with mix of dict and string dependencies (#827)."""
        response_obj = MagicMock()
        response_obj.acknowledged = True
        response_obj.status = "stored"

        with patch(
            "mcp.tools.characterization.submit_characterization",
            new_callable=AsyncMock,
            return_value=(response_obj, None),
        ) as mock_submit:
            payload = {
                "characterization_id": "char-mixed-deps",
                "project_id": "proj-1",
                "characterizations": [
                    {
                        "item_id": "item-001",
                        "ontology_tags": {
                            "work_type": "feature",
                            "lifecycle_stage": "build",
                            "technical_domains": ["api"],
                        },
                        "meaning": {
                            "business_summary": "API endpoint",
                            "technical_summary": "REST route",
                        },
                        "dependencies": [
                            "item-002",
                            {
                                "target_item_id": "item-003",
                                "relation": "blocks",
                                "dependency_type": "structural",
                                "reasoning": "Must exist first",
                                "confidence": 0.95,
                            },
                        ],
                        "confidence": 0.88,
                    }
                ],
            }

            response = client.post(
                "/api/v1/compute/characterization/char-mixed-deps/result",
                json=payload,
            )

        assert response.status_code == 200
        call_args = mock_submit.call_args[0][0]
        assert len(call_args.dependencies) == 2
        # String dep gets defaults
        assert call_args.dependencies[0].target_item_id == "item-002"
        assert call_args.dependencies[0].relation == "related_to"
        # Dict dep preserves values
        assert call_args.dependencies[1].target_item_id == "item-003"
        assert call_args.dependencies[1].relation == "blocks"
        assert call_args.dependencies[1].confidence == 0.95

    def test_partial_failure(self, client):
        """Test partial failure where some items succeed and some fail."""
        from mcp.models import MCPError

        response_obj = MagicMock()
        response_obj.acknowledged = True
        response_obj.status = "stored"

        error_obj = MCPError(code="INTERNAL_ERROR", message="Storage failed")

        with patch(
            "mcp.tools.characterization.submit_characterization",
            new_callable=AsyncMock,
            side_effect=[
                (response_obj, None),  # First item succeeds
                (None, error_obj),     # Second item fails
            ],
        ):
            payload = {
                "characterization_id": "char-partial",
                "project_id": "proj-1",
                "characterizations": [
                    {
                        "item_id": "item-001",
                        "ontology_tags": {
                            "work_type": "feature",
                            "lifecycle_stage": "build",
                            "technical_domains": ["backend"],
                        },
                        "meaning": {
                            "business_summary": "OK",
                            "technical_summary": "OK",
                        },
                    },
                    {
                        "item_id": "item-002",
                        "ontology_tags": {
                            "work_type": "feature",
                            "lifecycle_stage": "build",
                            "technical_domains": ["backend"],
                        },
                        "meaning": {
                            "business_summary": "Fail",
                            "technical_summary": "Fail",
                        },
                    },
                ],
            }

            response = client.post(
                "/api/v1/compute/characterization/char-partial/result",
                json=payload,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["stored_count"] == 1
        assert data["total_count"] == 2
        assert len(data["errors"]) == 1

    def test_all_items_fail(self, client):
        """Test that 500 is returned when all items fail."""
        from mcp.models import MCPError

        error_obj = MCPError(code="INTERNAL_ERROR", message="Storage failed")

        with patch(
            "mcp.tools.characterization.submit_characterization",
            new_callable=AsyncMock,
            return_value=(None, error_obj),
        ):
            payload = {
                "characterization_id": "char-allfail",
                "project_id": "proj-1",
                "characterizations": [
                    {
                        "item_id": "item-001",
                        "ontology_tags": {
                            "work_type": "feature",
                            "lifecycle_stage": "build",
                            "technical_domains": ["backend"],
                        },
                        "meaning": {
                            "business_summary": "Fail",
                            "technical_summary": "Fail",
                        },
                    },
                ],
            }

            response = client.post(
                "/api/v1/compute/characterization/char-allfail/result",
                json=payload,
            )

        assert response.status_code == 500
        assert "All characterizations failed" in response.json()["detail"]

    def test_default_values(self, client):
        """Test that missing optional fields get reasonable defaults."""
        response_obj = MagicMock()
        response_obj.acknowledged = True
        response_obj.status = "stored"

        with patch(
            "mcp.tools.characterization.submit_characterization",
            new_callable=AsyncMock,
            return_value=(response_obj, None),
        ):
            payload = {
                "characterization_id": "char-defaults",
                "project_id": "proj-1",
                "characterizations": [
                    {
                        "item_id": "item-001",
                        # Minimal: no ontology_tags, meaning, dependencies
                    }
                ],
            }

            response = client.post(
                "/api/v1/compute/characterization/char-defaults/result",
                json=payload,
            )

        assert response.status_code == 200
