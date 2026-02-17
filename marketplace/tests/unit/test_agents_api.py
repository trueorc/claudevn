"""Tests for agents API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from models import (
    Agent, Skill, AgentListResponse, TaskAssignment
)
from composition_service import CompositionService


@pytest.fixture
def mock_skill():
    """Create a mock skill for testing."""
    return Skill(
        id="code-writer",
        name="Code Writer",
        description="Writes production code",
        instructions="# Code Writer\nYou write code.",
        specialized_tools=[],
        tags=["coding"],
        version="1.0.0",
        author="system"
    )


@pytest.fixture
def mock_agent(mock_skill):
    """Create a mock agent for testing."""
    return Agent(
        id="agent-test123",
        skills=[mock_skill],
        merged_instructions="# Agent Instructions\nTest instructions",
        tools=["read", "write", "bash"],
        context=None,
        task=TaskAssignment(
            task_id="task-456",
            description="Test task",
            required_capabilities=["coding"]
        ),
        created_at=datetime.now(timezone.utc)
    )


class TestAgentListResponseModel:
    """Tests for AgentListResponse model."""

    def test_agent_list_response_creation(self, mock_agent):
        """Test AgentListResponse model creation."""
        response = AgentListResponse(
            agents=[mock_agent],
            total=1
        )
        assert response.total == 1
        assert len(response.agents) == 1
        assert response.agents[0].id == "agent-test123"

    def test_agent_list_response_empty(self):
        """Test AgentListResponse with no agents."""
        response = AgentListResponse(
            agents=[],
            total=0
        )
        assert response.total == 0
        assert len(response.agents) == 0


class TestCompositionServiceAgentMethods:
    """Tests for agent methods in CompositionService."""

    def test_get_agent_returns_cached_agent(self, mock_agent):
        """Test get_agent returns cached agent."""
        service = CompositionService()
        service._agents[mock_agent.id] = mock_agent

        result = service.get_agent(mock_agent.id)
        assert result is not None
        assert result.id == mock_agent.id
        assert result.skills[0].id == "code-writer"

    def test_get_agent_returns_none_for_unknown(self):
        """Test get_agent returns None for unknown agent ID."""
        service = CompositionService()
        result = service.get_agent("nonexistent-agent")
        assert result is None

    def test_list_agents_returns_all_cached(self, mock_agent):
        """Test list_agents returns all cached agents."""
        service = CompositionService()
        service._agents.clear()
        service._agents[mock_agent.id] = mock_agent

        agents = service.list_agents()
        assert len(agents) == 1
        assert agents[0].id == mock_agent.id

    def test_list_agents_empty_cache(self):
        """Test list_agents with empty cache."""
        service = CompositionService()
        service._agents.clear()

        agents = service.list_agents()
        assert len(agents) == 0


class TestGetAgentEndpointLogic:
    """Tests for GET /agents/{agent_id} endpoint logic."""

    def test_agent_found_returns_agent(self, mock_agent):
        """Test endpoint returns agent when found."""
        service = CompositionService()
        service._agents[mock_agent.id] = mock_agent

        # Simulate endpoint logic
        agent = service.get_agent(mock_agent.id)
        assert agent is not None
        assert agent.id == mock_agent.id
        assert agent.merged_instructions == "# Agent Instructions\nTest instructions"
        assert "read" in agent.tools

    def test_agent_not_found_returns_none(self):
        """Test endpoint logic when agent not found."""
        service = CompositionService()
        service._agents.clear()

        # Simulate endpoint logic - would raise HTTPException 404
        agent = service.get_agent("nonexistent-agent")
        assert agent is None


class TestListAgentsEndpointLogic:
    """Tests for GET /agents endpoint logic."""

    def test_list_agents_returns_all(self, mock_agent, mock_skill):
        """Test endpoint returns all agents."""
        service = CompositionService()
        service._agents.clear()
        service._agents[mock_agent.id] = mock_agent

        # Create another agent
        agent2 = Agent(
            id="agent-test456",
            skills=[mock_skill],
            merged_instructions="# Agent 2",
            tools=["read"],
            created_at=datetime.now(timezone.utc)
        )
        service._agents[agent2.id] = agent2

        agents = service.list_agents()
        assert len(agents) == 2
        agent_ids = {a.id for a in agents}
        assert "agent-test123" in agent_ids
        assert "agent-test456" in agent_ids

    def test_list_agents_empty(self):
        """Test endpoint with no agents."""
        service = CompositionService()
        service._agents.clear()

        agents = service.list_agents()
        assert len(agents) == 0

    def test_response_model_construction(self, mock_agent):
        """Test constructing AgentListResponse from service output."""
        service = CompositionService()
        service._agents.clear()
        service._agents[mock_agent.id] = mock_agent

        agents = service.list_agents()
        response = AgentListResponse(agents=agents, total=len(agents))

        assert response.total == 1
        assert response.agents[0].id == mock_agent.id


class TestAgentModelFields:
    """Tests for Agent model fields in response."""

    def test_agent_has_required_fields(self, mock_agent):
        """Test Agent model has all required fields for API response."""
        # Required fields as per spec
        assert hasattr(mock_agent, "id")
        assert hasattr(mock_agent, "skills")
        assert hasattr(mock_agent, "merged_instructions")
        assert hasattr(mock_agent, "tools")
        assert hasattr(mock_agent, "created_at")

    def test_agent_skills_are_accessible(self, mock_agent):
        """Test agent skills list is accessible."""
        assert len(mock_agent.skills) > 0
        assert mock_agent.skills[0].id == "code-writer"
        assert mock_agent.skills[0].name == "Code Writer"

    def test_agent_tools_are_listed(self, mock_agent):
        """Test agent tools are accessible."""
        assert len(mock_agent.tools) == 3
        assert "read" in mock_agent.tools
        assert "write" in mock_agent.tools
        assert "bash" in mock_agent.tools

    def test_agent_serialization(self, mock_agent):
        """Test agent can be serialized to dict (for JSON response)."""
        agent_dict = mock_agent.model_dump()
        assert agent_dict["id"] == "agent-test123"
        assert len(agent_dict["skills"]) == 1
        assert agent_dict["skills"][0]["id"] == "code-writer"
        assert "read" in agent_dict["tools"]
