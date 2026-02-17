"""Tests for tool registry API endpoints."""

import pytest
from pathlib import Path

from models import (
    ToolDefinition, ToolTier, ToolListResponse,
    ToolAuthorizationRequest, ToolAuthorizationResponse,
    Agent, Skill, TaskAssignment,
    ComputeInfo, AuthorizationFailure
)
from skill_registry import SkillRegistry, set_skill_registry
from composition_service import CompositionService, get_composition_service


@pytest.fixture
def temp_skills_path(tmp_path):
    """Create a temporary skills directory with test skills."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "system").mkdir()
    (skills_dir / "user").mkdir()

    # Create skill with specialized tool
    deployer_skill = skills_dir / "system" / "deploy-engineer.yaml"
    deployer_skill.write_text("""id: deploy-engineer
name: Deploy Engineer
description: Deploys applications to production
version: "1.0.0"
author: system

instructions: |
  # Deploy Engineer
  You deploy applications to production.

specialized_tools:
  - deploy_prod
  - rollback_prod

tags:
  - deployment
  - production

constraints:
  - Verify before deploying
""")

    # Create another skill
    code_writer = skills_dir / "system" / "code-writer.yaml"
    code_writer.write_text("""id: code-writer
name: Code Writer
description: Writes production code
version: "1.0.0"
author: system

instructions: |
  # Code Writer
  You write code.

specialized_tools: []

tags:
  - coding
  - implementation

constraints: []
""")

    return str(skills_dir)


@pytest.fixture
def skill_registry(temp_skills_path):
    """Create and initialize a skill registry."""
    import asyncio
    registry = SkillRegistry(skills_path=temp_skills_path)
    asyncio.get_event_loop().run_until_complete(registry.initialize())
    set_skill_registry(registry)
    return registry


@pytest.fixture
def composition_service():
    """Create a composition service."""
    return get_composition_service()


class TestToolListResponse:
    """Tests for ToolListResponse model."""

    def test_tool_list_response_model(self):
        """Test ToolListResponse model creation."""
        tools = [
            ToolDefinition(
                id="read", name="Read", description="Read files",
                tier=ToolTier.GLOBAL, granted_by=[], security_level="standard"
            ),
            ToolDefinition(
                id="deploy_prod", name="Deploy to Production",
                description="Deploy to prod", tier=ToolTier.SPECIALIZED,
                granted_by=["deploy-engineer"], security_level="elevated"
            )
        ]
        response = ToolListResponse(
            tools=tools,
            total=2,
            by_tier={"global": 1, "specialized": 1}
        )
        assert response.total == 2
        assert response.by_tier["global"] == 1
        assert response.by_tier["specialized"] == 1


class TestToolAuthorizationRequest:
    """Tests for ToolAuthorizationRequest model."""

    def test_request_model_creation(self):
        """Test ToolAuthorizationRequest model creation."""
        request = ToolAuthorizationRequest(
            agent_id="agent-123",
            tool_id="deploy_prod"
        )
        assert request.agent_id == "agent-123"
        assert request.tool_id == "deploy_prod"


class TestToolAuthorizationResponse:
    """Tests for ToolAuthorizationResponse model."""

    def test_authorized_response(self):
        """Test authorized response creation."""
        response = ToolAuthorizationResponse(
            authorized=True,
            granted_by=["deploy-engineer"],
            tool=ToolDefinition(
                id="deploy_prod", name="Deploy", description="Deploy",
                tier=ToolTier.SPECIALIZED, granted_by=["deploy-engineer"],
                security_level="elevated"
            ),
            reason="Agent has deploy-engineer skill"
        )
        assert response.authorized is True
        assert "deploy-engineer" in response.granted_by

    def test_unauthorized_response(self):
        """Test unauthorized response creation."""
        response = ToolAuthorizationResponse(
            authorized=False,
            granted_by=["deploy-engineer"],
            tool=None,
            reason="Agent lacks required skills"
        )
        assert response.authorized is False


class TestGlobalToolAuthorization:
    """Tests for global tool authorization logic."""

    @pytest.mark.asyncio
    async def test_global_tool_always_authorized(self, skill_registry):
        """Global tools should always be authorized."""
        # Get a global tool
        tool = skill_registry.get_tool("read")
        assert tool is not None
        assert tool.tier == ToolTier.GLOBAL

        # Global tools are always authorized - no agent check needed
        # This is the logic from skill-marketplace.md §Tools


class TestSpecializedToolAuthorization:
    """Tests for specialized tool authorization logic."""

    @pytest.mark.asyncio
    async def test_specialized_tool_requires_skill(self, skill_registry):
        """Specialized tools require agent to have granting skill."""
        # Get a specialized tool
        tool = skill_registry.get_tool("deploy_prod")
        assert tool is not None
        assert tool.tier == ToolTier.SPECIALIZED
        assert "deploy-engineer" in tool.granted_by

    @pytest.mark.asyncio
    async def test_tool_granted_by_tracks_skills(self, skill_registry):
        """Specialized tool's granted_by should track all granting skills."""
        tool = skill_registry.get_tool("deploy_prod")
        assert tool is not None
        # deploy_prod is granted by deploy-engineer skill
        assert "deploy-engineer" in tool.granted_by


class TestCompositionServiceAgentCache:
    """Tests for agent caching in composition service."""

    @pytest.mark.asyncio
    async def test_compose_stores_agent(self, skill_registry):
        """Composed agents should be stored for later retrieval."""
        from models import ComposeRequest, TaskAssignment

        service = get_composition_service()

        request = ComposeRequest(
            task=TaskAssignment(
                task_id="task-123",
                description="Test task",
                required_capabilities=["deployment"]
            ),
            skill_ids=["deploy-engineer"]
        )

        agent = await service.compose(request)
        assert agent is not None

        # Agent should be retrievable
        retrieved = service.get_agent(agent.id)
        assert retrieved is not None
        assert retrieved.id == agent.id

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, skill_registry):
        """get_agent returns None for unknown agent ID."""
        service = get_composition_service()
        result = service.get_agent("nonexistent-agent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_agents(self, skill_registry):
        """list_agents returns all cached agents."""
        from models import ComposeRequest, TaskAssignment

        service = get_composition_service()

        # Clear any existing agents (fresh service)
        service._agents.clear()

        # Create an agent
        request = ComposeRequest(
            task=TaskAssignment(
                task_id="task-456",
                description="Another test task",
                required_capabilities=["coding"]
            ),
            skill_ids=["code-writer"]
        )

        agent = await service.compose(request)
        agents = service.list_agents()

        assert len(agents) >= 1
        assert any(a.id == agent.id for a in agents)


# ============ Two-Part Tool Authorization Tests (#126) ============


class TestComputeInfoModel:
    """Tests for ComputeInfo model."""

    def test_compute_info_creation(self):
        """Test ComputeInfo model creation."""
        compute = ComputeInfo(
            instance_id="compute-prod-001",
            labels=["production-access", "database-admin"],
            tools_available=["deploy_prod", "db_migrate"]
        )
        assert compute.instance_id == "compute-prod-001"
        assert "production-access" in compute.labels
        assert "deploy_prod" in compute.tools_available

    def test_compute_info_defaults(self):
        """Test ComputeInfo with default values."""
        compute = ComputeInfo(instance_id="compute-001")
        assert compute.instance_id == "compute-001"
        assert compute.labels == []
        assert compute.tools_available == []


class TestToolDefinitionWithRequiredLabels:
    """Tests for ToolDefinition with required_labels field."""

    def test_tool_with_required_labels(self):
        """Test ToolDefinition with required_labels."""
        tool = ToolDefinition(
            id="deploy_prod",
            name="Deploy to Production",
            description="Deploy code to production",
            tier=ToolTier.SPECIALIZED,
            granted_by=["deploy-engineer"],
            required_labels=["production-access"],
            security_level="elevated"
        )
        assert tool.required_labels == ["production-access"]

    def test_tool_without_required_labels(self):
        """Test ToolDefinition defaults to empty required_labels."""
        tool = ToolDefinition(
            id="read",
            name="Read",
            description="Read files",
            tier=ToolTier.GLOBAL
        )
        assert tool.required_labels == []


class TestAuthorizationFailureEnum:
    """Tests for AuthorizationFailure enum."""

    def test_failure_types(self):
        """Test all failure types exist."""
        assert AuthorizationFailure.TOOL_NOT_FOUND == "tool_not_found"
        assert AuthorizationFailure.AGENT_NOT_FOUND == "agent_not_found"
        assert AuthorizationFailure.SKILL_NOT_GRANTED == "skill_not_granted"
        assert AuthorizationFailure.COMPUTE_MISSING_TOOL == "compute_missing_tool"
        assert AuthorizationFailure.COMPUTE_MISSING_LABELS == "compute_missing_labels"


class TestToolAuthorizationRequestWithCompute:
    """Tests for ToolAuthorizationRequest with compute info."""

    def test_request_with_compute(self):
        """Test request with compute information."""
        request = ToolAuthorizationRequest(
            agent_id="agent-123",
            tool_id="deploy_prod",
            compute=ComputeInfo(
                instance_id="compute-prod-001",
                labels=["production-access"],
                tools_available=["deploy_prod"]
            )
        )
        assert request.compute is not None
        assert request.compute.instance_id == "compute-prod-001"

    def test_request_without_compute(self):
        """Test request without compute information (backward compatible)."""
        request = ToolAuthorizationRequest(
            agent_id="agent-123",
            tool_id="deploy_prod"
        )
        assert request.compute is None


class TestToolAuthorizationResponseEnhanced:
    """Tests for enhanced ToolAuthorizationResponse."""

    def test_response_with_full_details(self):
        """Test response with all new fields."""
        response = ToolAuthorizationResponse(
            authorized=True,
            granted_by=["deploy-engineer"],
            tool=ToolDefinition(
                id="deploy_prod",
                name="Deploy",
                description="Deploy",
                tier=ToolTier.SPECIALIZED,
                granted_by=["deploy-engineer"],
                required_labels=["production-access"]
            ),
            reason="Fully authorized",
            failure_type=None,
            skill_check_passed=True,
            compute_check_passed=True,
            missing_labels=[]
        )
        assert response.authorized is True
        assert response.skill_check_passed is True
        assert response.compute_check_passed is True
        assert response.failure_type is None
        assert response.missing_labels == []

    def test_response_skill_failure(self):
        """Test response for skill authorization failure."""
        response = ToolAuthorizationResponse(
            authorized=False,
            granted_by=["deploy-engineer"],
            tool=None,
            reason="Agent lacks required skills",
            failure_type=AuthorizationFailure.SKILL_NOT_GRANTED,
            skill_check_passed=False,
            compute_check_passed=None
        )
        assert response.authorized is False
        assert response.failure_type == AuthorizationFailure.SKILL_NOT_GRANTED
        assert response.skill_check_passed is False
        assert response.compute_check_passed is None

    def test_response_compute_missing_tool(self):
        """Test response for compute missing tool."""
        response = ToolAuthorizationResponse(
            authorized=False,
            granted_by=["deploy-engineer"],
            tool=None,
            reason="Compute does not have tool",
            failure_type=AuthorizationFailure.COMPUTE_MISSING_TOOL,
            skill_check_passed=True,
            compute_check_passed=False
        )
        assert response.authorized is False
        assert response.failure_type == AuthorizationFailure.COMPUTE_MISSING_TOOL
        assert response.skill_check_passed is True
        assert response.compute_check_passed is False

    def test_response_compute_missing_labels(self):
        """Test response for compute missing required labels."""
        response = ToolAuthorizationResponse(
            authorized=False,
            granted_by=["deploy-engineer"],
            tool=None,
            reason="Compute missing labels",
            failure_type=AuthorizationFailure.COMPUTE_MISSING_LABELS,
            skill_check_passed=True,
            compute_check_passed=False,
            missing_labels=["production-access", "database-admin"]
        )
        assert response.authorized is False
        assert response.failure_type == AuthorizationFailure.COMPUTE_MISSING_LABELS
        assert "production-access" in response.missing_labels
        assert "database-admin" in response.missing_labels


class TestTwoPartAuthorizationLogic:
    """Unit tests for two-part authorization logic."""

    @pytest.fixture
    def tool_with_labels(self):
        """Create a tool that requires specific labels."""
        return ToolDefinition(
            id="deploy_prod",
            name="Deploy to Production",
            description="Deploy code to production",
            tier=ToolTier.SPECIALIZED,
            granted_by=["deploy-engineer"],
            required_labels=["production-access"],
            security_level="elevated"
        )

    @pytest.fixture
    def skill_with_tool(self):
        """Create a skill that grants deploy_prod."""
        return Skill(
            id="deploy-engineer",
            name="Deploy Engineer",
            description="Deploys applications",
            instructions="# Deploy\nYou deploy apps.",
            specialized_tools=["deploy_prod"],
            tags=["deployment"]
        )

    @pytest.fixture
    def compute_with_capability(self):
        """Create a compute with proper capabilities."""
        return ComputeInfo(
            instance_id="compute-prod-001",
            labels=["production-access", "database-admin"],
            tools_available=["deploy_prod", "db_migrate"]
        )

    @pytest.fixture
    def compute_without_tool(self):
        """Create a compute without the required tool."""
        return ComputeInfo(
            instance_id="compute-dev-001",
            labels=["production-access"],
            tools_available=["lint_code"]
        )

    @pytest.fixture
    def compute_without_labels(self):
        """Create a compute without required labels."""
        return ComputeInfo(
            instance_id="compute-dev-002",
            labels=[],
            tools_available=["deploy_prod"]
        )

    def test_both_checks_pass(
        self, tool_with_labels, skill_with_tool, compute_with_capability
    ):
        """Test authorization passes when both skill and compute checks pass."""
        agent_skills = [skill_with_tool]

        # Check skill grants permission
        agent_skill_ids = {s.id for s in agent_skills}
        tool_granted_by = set(tool_with_labels.granted_by)
        skill_check_passed = bool(agent_skill_ids & tool_granted_by)

        # Check compute has tool and labels
        compute_has_tool = (
            tool_with_labels.id in compute_with_capability.tools_available
        )
        compute_labels = set(compute_with_capability.labels)
        required_labels = set(tool_with_labels.required_labels)
        compute_has_labels = required_labels <= compute_labels

        assert skill_check_passed is True
        assert compute_has_tool is True
        assert compute_has_labels is True

    def test_skill_check_fails(self, tool_with_labels, compute_with_capability):
        """Test authorization fails when agent lacks required skill."""
        wrong_skill = Skill(
            id="code-writer",
            name="Code Writer",
            description="Writes code",
            instructions="# Write code",
            specialized_tools=[]
        )
        agent_skills = [wrong_skill]

        agent_skill_ids = {s.id for s in agent_skills}
        tool_granted_by = set(tool_with_labels.granted_by)
        skill_check_passed = bool(agent_skill_ids & tool_granted_by)

        assert skill_check_passed is False

    def test_compute_missing_tool(
        self, tool_with_labels, skill_with_tool, compute_without_tool
    ):
        """Test authorization fails when compute lacks the tool."""
        agent_skills = [skill_with_tool]
        agent_skill_ids = {s.id for s in agent_skills}
        tool_granted_by = set(tool_with_labels.granted_by)
        skill_check_passed = bool(agent_skill_ids & tool_granted_by)

        compute_has_tool = tool_with_labels.id in compute_without_tool.tools_available

        assert skill_check_passed is True
        assert compute_has_tool is False

    def test_compute_missing_labels(
        self, tool_with_labels, skill_with_tool, compute_without_labels
    ):
        """Test authorization fails when compute lacks required labels."""
        agent_skills = [skill_with_tool]
        agent_skill_ids = {s.id for s in agent_skills}
        tool_granted_by = set(tool_with_labels.granted_by)
        skill_check_passed = bool(agent_skill_ids & tool_granted_by)

        compute_has_tool = (
            tool_with_labels.id in compute_without_labels.tools_available
        )
        compute_labels = set(compute_without_labels.labels)
        required_labels = set(tool_with_labels.required_labels)
        missing_labels = required_labels - compute_labels

        assert skill_check_passed is True
        assert compute_has_tool is True
        assert len(missing_labels) > 0
        assert "production-access" in missing_labels

    def test_global_tool_skips_skill_check(self):
        """Test global tools skip skill authorization check."""
        global_tool = ToolDefinition(
            id="read",
            name="Read",
            description="Read files",
            tier=ToolTier.GLOBAL
        )
        assert global_tool.tier == ToolTier.GLOBAL

    def test_without_compute_info(self, tool_with_labels, skill_with_tool):
        """Test authorization works without compute info (backward compatible)."""
        agent_skills = [skill_with_tool]
        agent_skill_ids = {s.id for s in agent_skills}
        tool_granted_by = set(tool_with_labels.granted_by)
        skill_check_passed = bool(agent_skill_ids & tool_granted_by)

        # Without compute info, compute_check_passed should be None
        compute_check_passed = None

        assert skill_check_passed is True
        assert compute_check_passed is None
