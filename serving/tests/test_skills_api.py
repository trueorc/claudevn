"""Unit tests for skills API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.skills import (
    AggregatedSkill,
    AggregatedSkillsResponse,
    SkillUpdateRequest
)


class TestSkillUpdateRequest:
    """Tests for SkillUpdateRequest model."""

    def test_all_fields_optional(self):
        """All fields in SkillUpdateRequest should be optional."""
        request = SkillUpdateRequest()
        assert request.name is None
        assert request.description is None
        assert request.instructions is None
        assert request.version is None
        assert request.tags is None
        assert request.changelog is None

    def test_partial_update(self):
        """SkillUpdateRequest can have partial fields."""
        request = SkillUpdateRequest(
            name="Updated Name",
            version="2.0.0",
            changelog="Bumped version"
        )
        assert request.name == "Updated Name"
        assert request.version == "2.0.0"
        assert request.changelog == "Bumped version"
        assert request.description is None
        assert request.instructions is None


class TestAggregatedSkill:
    """Tests for AggregatedSkill model."""

    def test_required_fields(self):
        """AggregatedSkill should have required fields."""
        skill = AggregatedSkill(
            id="test-skill",
            name="Test Skill",
            description="A test skill"
        )
        assert skill.id == "test-skill"
        assert skill.name == "Test Skill"
        assert skill.description == "A test skill"

    def test_marketplace_fields(self):
        """AggregatedSkill should have marketplace source fields."""
        skill = AggregatedSkill(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            marketplace_id="mp-001",
            marketplace_name="Test Market",
            marketplace_tier="root",
            namespace="test"
        )
        assert skill.marketplace_id == "mp-001"
        assert skill.marketplace_name == "Test Market"
        assert skill.marketplace_tier == "root"
        assert skill.namespace == "test"

    def test_default_values(self):
        """AggregatedSkill should have sensible defaults."""
        skill = AggregatedSkill(
            id="test-skill",
            name="Test Skill",
            description="A test skill"
        )
        assert skill.version == "1.0.0"
        assert skill.author == "system"
        assert skill.instructions == ""
        assert skill.tags == []
        assert skill.specialized_tools == []
        assert skill.marketplace_id is None


class TestAggregatedSkillsResponse:
    """Tests for AggregatedSkillsResponse model."""

    def test_response_structure(self):
        """AggregatedSkillsResponse should have correct structure."""
        response = AggregatedSkillsResponse(
            skills=[
                AggregatedSkill(
                    id="skill-1",
                    name="Skill 1",
                    description="First skill"
                ),
                AggregatedSkill(
                    id="skill-2",
                    name="Skill 2",
                    description="Second skill"
                )
            ],
            total=2,
            by_marketplace={"mp-001": 1, "mp-002": 1},
            by_tier={"root": 1, "user": 1},
            by_author={"system": 1, "user": 1}
        )

        assert len(response.skills) == 2
        assert response.total == 2
        assert response.by_marketplace["mp-001"] == 1
        assert response.by_tier["root"] == 1
        assert response.by_author["system"] == 1

    def test_empty_response(self):
        """AggregatedSkillsResponse can be empty."""
        response = AggregatedSkillsResponse(
            skills=[],
            total=0,
            by_marketplace={},
            by_tier={},
            by_author={}
        )

        assert len(response.skills) == 0
        assert response.total == 0
