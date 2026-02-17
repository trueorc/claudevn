"""Unit tests for claudevn_get_skill MCP tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

# Add serving to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.tools.skill import get_skill
from mcp.models import GetSkillInput, SkillResponse, MCPError


class TestGetSkillTool:
    """Test cases for the get_skill tool function."""

    @pytest.fixture
    def basic_input(self):
        """Create basic skill input."""
        return GetSkillInput(skill_id="python-backend")

    @pytest.fixture
    def mock_skill(self):
        """Create a mock skill from marketplace."""
        return {
            "id": "python-backend",
            "name": "Python Backend Developer",
            "instructions": "You are a Python backend developer skilled in FastAPI and async patterns.",
            "tags": ["python", "fastapi", "async"],
            "specialized_tools": ["run_tests", "deploy"]
        }

    @pytest.fixture
    def minimal_skill(self):
        """Create a minimal skill without optional fields."""
        return {
            "id": "general",
            "name": "General Assistant",
            "instructions": "You are a general-purpose assistant."
        }

    @pytest.mark.asyncio
    async def test_successful_skill_retrieval(self, basic_input, mock_skill):
        """Test successful skill retrieval from marketplace."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_skill = AsyncMock(return_value=mock_skill)
            mock_get_client.return_value = mock_client

            result, error = await get_skill(basic_input)

            assert error is None
            assert result is not None
            assert isinstance(result, SkillResponse)
            assert result.skill_id == "python-backend"
            assert result.name == "Python Backend Developer"
            assert "FastAPI" in result.instructions
            assert result.capabilities == ["python", "fastapi", "async"]
            assert result.specialized_tools == ["run_tests", "deploy"]

    @pytest.mark.asyncio
    async def test_skill_with_minimal_fields(self, minimal_skill):
        """Test skill retrieval with minimal fields."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_skill = AsyncMock(return_value=minimal_skill)
            mock_get_client.return_value = mock_client

            input_data = GetSkillInput(skill_id="general")
            result, error = await get_skill(input_data)

            assert error is None
            assert result is not None
            assert result.skill_id == "general"
            assert result.name == "General Assistant"
            assert result.capabilities == []
            assert result.specialized_tools == []

    @pytest.mark.asyncio
    async def test_skill_not_found(self, basic_input):
        """Test error when skill doesn't exist."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_skill = AsyncMock(
                side_effect=Exception("Skill not found in registry")
            )
            mock_get_client.return_value = mock_client

            result, error = await get_skill(basic_input)

            assert result is None
            assert error is not None
            assert error.code == "SKILL_NOT_FOUND"
            assert "python-backend" in error.message
            assert error.details["skill_id"] == "python-backend"

    @pytest.mark.asyncio
    async def test_marketplace_unavailable(self, basic_input):
        """Test error when marketplace service is unavailable."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_get_client:
            mock_get_client.side_effect = RuntimeError("Marketplace not initialized")

            result, error = await get_skill(basic_input)

            assert result is None
            assert error is not None
            assert error.code == "SKILL_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_network_error(self, basic_input):
        """Test error handling for network issues."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_skill = AsyncMock(
                side_effect=ConnectionError("Connection refused")
            )
            mock_get_client.return_value = mock_client

            result, error = await get_skill(basic_input)

            assert result is None
            assert error is not None
            assert error.code == "SKILL_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_client_get_skill_called_correctly(self, basic_input, mock_skill):
        """Test that marketplace client is called with correct skill ID."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_skill = AsyncMock(return_value=mock_skill)
            mock_get_client.return_value = mock_client

            await get_skill(basic_input)

            mock_client.get_skill.assert_called_once_with("python-backend")

    @pytest.mark.asyncio
    async def test_skill_with_empty_tags(self):
        """Test skill with empty tags array."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_get_client:
            skill = {
                "id": "empty-tags",
                "name": "Empty Tags Skill",
                "instructions": "Test skill",
                "tags": []
            }
            mock_client = AsyncMock()
            mock_client.get_skill = AsyncMock(return_value=skill)
            mock_get_client.return_value = mock_client

            input_data = GetSkillInput(skill_id="empty-tags")
            result, error = await get_skill(input_data)

            assert error is None
            assert result.capabilities == []

    @pytest.mark.asyncio
    async def test_skill_with_empty_specialized_tools(self):
        """Test skill with empty specialized_tools array."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_get_client:
            skill = {
                "id": "no-tools",
                "name": "No Tools Skill",
                "instructions": "Test skill",
                "tags": ["python"],
                "specialized_tools": []
            }
            mock_client = AsyncMock()
            mock_client.get_skill = AsyncMock(return_value=skill)
            mock_get_client.return_value = mock_client

            input_data = GetSkillInput(skill_id="no-tools")
            result, error = await get_skill(input_data)

            assert error is None
            assert result.specialized_tools == []

    @pytest.mark.asyncio
    async def test_error_details_included(self, basic_input):
        """Test that error includes skill_id in details."""
        with patch("services.marketplace_client.get_marketplace_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_skill = AsyncMock(side_effect=KeyError("id"))
            mock_get_client.return_value = mock_client

            result, error = await get_skill(basic_input)

            assert error is not None
            assert error.details is not None
            assert error.details["skill_id"] == "python-backend"


class TestGetSkillInputModel:
    """Test cases for the GetSkillInput model."""

    def test_required_skill_id(self):
        """Test that skill_id is required."""
        input_data = GetSkillInput(skill_id="python-backend")
        assert input_data.skill_id == "python-backend"

    def test_skill_id_validation(self):
        """Test various skill ID formats."""
        # Hyphenated
        input1 = GetSkillInput(skill_id="python-backend-dev")
        assert input1.skill_id == "python-backend-dev"

        # Underscored
        input2 = GetSkillInput(skill_id="python_backend")
        assert input2.skill_id == "python_backend"

        # Simple
        input3 = GetSkillInput(skill_id="general")
        assert input3.skill_id == "general"


class TestSkillResponseModel:
    """Test cases for the SkillResponse model."""

    def test_model_creation(self):
        """Test creating a skill response."""
        response = SkillResponse(
            skill_id="python-backend",
            name="Python Backend Developer",
            instructions="You are a Python backend developer.",
            capabilities=["python", "fastapi"],
            specialized_tools=["run_tests"]
        )

        assert response.skill_id == "python-backend"
        assert response.name == "Python Backend Developer"
        assert response.instructions == "You are a Python backend developer."
        assert response.capabilities == ["python", "fastapi"]
        assert response.specialized_tools == ["run_tests"]

    def test_optional_specialized_tools(self):
        """Test response without specialized tools."""
        response = SkillResponse(
            skill_id="general",
            name="General",
            instructions="General assistant",
            capabilities=[]
        )

        assert response.specialized_tools is None

    def test_empty_capabilities(self):
        """Test response with empty capabilities."""
        response = SkillResponse(
            skill_id="test",
            name="Test",
            instructions="Test",
            capabilities=[]
        )

        assert response.capabilities == []
