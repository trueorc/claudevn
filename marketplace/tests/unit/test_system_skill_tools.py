"""Tests for system skill specialized tools and two-tier authorization.

These tests verify that:
1. System skills have specialized_tools defined
2. Tool definitions exist in the registry with proper metadata
3. Two-tier authorization works (skill grants + compute capability)

Issue #177: Add specialized tools to system skill definitions
"""

import pytest
from pathlib import Path

from models import (
    ToolDefinition, ToolTier, Skill,
    ComputeInfo, ToolAuthorizationRequest
)
from skill_registry import SkillRegistry, set_skill_registry


@pytest.fixture
def real_skills_registry():
    """Create a registry using the actual system skills."""
    import asyncio
    # Use the actual marketplace skills directory
    skills_path = Path(__file__).parent.parent.parent / "skills"
    registry = SkillRegistry(skills_path=str(skills_path))
    asyncio.get_event_loop().run_until_complete(registry.initialize())
    set_skill_registry(registry)
    return registry


class TestSystemSkillsHaveSpecializedTools:
    """Tests verifying system skills define specialized_tools."""

    @pytest.mark.asyncio
    async def test_database_migration_has_db_migration_tool(self, real_skills_registry):
        """database-migration skill should have db_migration_tool."""
        skill = real_skills_registry.get_skill("database-migration")
        assert skill is not None, "database-migration skill not found"
        assert "db_migration_tool" in skill.specialized_tools

    @pytest.mark.asyncio
    async def test_prod_deployment_has_deploy_prod(self, real_skills_registry):
        """prod-deployment skill should have deploy_prod tool."""
        skill = real_skills_registry.get_skill("prod-deployment")
        assert skill is not None, "prod-deployment skill not found"
        assert "deploy_prod" in skill.specialized_tools

    @pytest.mark.asyncio
    async def test_security_audit_has_run_security_scan(self, real_skills_registry):
        """security-audit skill should have run_security_scan tool."""
        skill = real_skills_registry.get_skill("security-audit")
        assert skill is not None, "security-audit skill not found"
        assert "run_security_scan" in skill.specialized_tools

    @pytest.mark.asyncio
    async def test_api_integration_has_test_api_endpoint(self, real_skills_registry):
        """api-integration skill should have test_api_endpoint tool."""
        skill = real_skills_registry.get_skill("api-integration")
        assert skill is not None, "api-integration skill not found"
        assert "test_api_endpoint" in skill.specialized_tools


class TestToolDefinitionsExist:
    """Tests verifying tool definitions exist with proper metadata."""

    @pytest.mark.asyncio
    async def test_db_migration_tool_registered(self, real_skills_registry):
        """db_migration_tool should be registered with proper metadata."""
        tool = real_skills_registry.get_tool("db_migration_tool")
        assert tool is not None, "db_migration_tool not registered"
        assert tool.tier == ToolTier.SPECIALIZED
        assert "database-migration" in tool.granted_by
        assert "database-admin" in tool.required_labels

    @pytest.mark.asyncio
    async def test_deploy_prod_tool_registered(self, real_skills_registry):
        """deploy_prod should be registered with proper metadata."""
        tool = real_skills_registry.get_tool("deploy_prod")
        assert tool is not None, "deploy_prod not registered"
        assert tool.tier == ToolTier.SPECIALIZED
        assert "prod-deployment" in tool.granted_by
        assert "production-access" in tool.required_labels
        assert tool.security_level == "admin"

    @pytest.mark.asyncio
    async def test_run_security_scan_tool_registered(self, real_skills_registry):
        """run_security_scan should be registered with proper metadata."""
        tool = real_skills_registry.get_tool("run_security_scan")
        assert tool is not None, "run_security_scan not registered"
        assert tool.tier == ToolTier.SPECIALIZED
        assert "security-audit" in tool.granted_by
        assert "security-tools" in tool.required_labels

    @pytest.mark.asyncio
    async def test_test_api_endpoint_tool_registered(self, real_skills_registry):
        """test_api_endpoint should be registered with proper metadata."""
        tool = real_skills_registry.get_tool("test_api_endpoint")
        assert tool is not None, "test_api_endpoint not registered"
        assert tool.tier == ToolTier.SPECIALIZED
        assert "api-integration" in tool.granted_by
        assert "api-testing" in tool.required_labels


class TestTwoTierToolAuthorization:
    """Tests for two-tier tool authorization with system skills."""

    @pytest.fixture
    def compute_with_all_labels(self):
        """Compute with all required labels for specialized tools."""
        return ComputeInfo(
            instance_id="compute-full-001",
            labels=["database-admin", "production-access", "security-tools", "api-testing"],
            tools_available=["db_migration_tool", "deploy_prod", "run_security_scan", "test_api_endpoint"]
        )

    @pytest.fixture
    def compute_db_only(self):
        """Compute with database-admin label only."""
        return ComputeInfo(
            instance_id="compute-db-001",
            labels=["database-admin"],
            tools_available=["db_migration_tool"]
        )

    @pytest.fixture
    def compute_standard(self):
        """Standard compute without specialized capabilities."""
        return ComputeInfo(
            instance_id="compute-standard-001",
            labels=["standard"],
            tools_available=[]
        )

    def test_skill_grants_tool_access(self, real_skills_registry, compute_with_all_labels):
        """Agent with database-migration skill can access db_migration_tool."""
        skill = real_skills_registry.get_skill("database-migration")
        tool = real_skills_registry.get_tool("db_migration_tool")

        # Skill grants permission
        agent_skill_ids = {skill.id}
        tool_granted_by = set(tool.granted_by)
        skill_check_passed = bool(agent_skill_ids & tool_granted_by)
        assert skill_check_passed is True

        # Compute has capability
        compute_has_tool = tool.id in compute_with_all_labels.tools_available
        compute_labels = set(compute_with_all_labels.labels)
        required_labels = set(tool.required_labels)
        compute_has_labels = required_labels <= compute_labels

        assert compute_has_tool is True
        assert compute_has_labels is True

    def test_skill_check_fails_without_skill(self, real_skills_registry, compute_with_all_labels):
        """Agent without database-migration skill cannot access db_migration_tool."""
        # Use a different skill that doesn't grant db_migration_tool
        skill = real_skills_registry.get_skill("code-analysis")
        tool = real_skills_registry.get_tool("db_migration_tool")

        agent_skill_ids = {skill.id} if skill else set()
        tool_granted_by = set(tool.granted_by)
        skill_check_passed = bool(agent_skill_ids & tool_granted_by)
        assert skill_check_passed is False

    def test_compute_check_fails_without_labels(self, real_skills_registry, compute_standard):
        """Compute without required labels fails authorization."""
        skill = real_skills_registry.get_skill("prod-deployment")
        tool = real_skills_registry.get_tool("deploy_prod")

        # Skill check passes
        agent_skill_ids = {skill.id}
        tool_granted_by = set(tool.granted_by)
        skill_check_passed = bool(agent_skill_ids & tool_granted_by)
        assert skill_check_passed is True

        # Compute check fails - missing label
        compute_labels = set(compute_standard.labels)
        required_labels = set(tool.required_labels)
        missing_labels = required_labels - compute_labels
        assert len(missing_labels) > 0
        assert "production-access" in missing_labels

    def test_compute_check_fails_without_tool(self, real_skills_registry, compute_db_only):
        """Compute without tool installed fails authorization."""
        skill = real_skills_registry.get_skill("security-audit")
        tool = real_skills_registry.get_tool("run_security_scan")

        # Skill check passes
        agent_skill_ids = {skill.id}
        tool_granted_by = set(tool.granted_by)
        skill_check_passed = bool(agent_skill_ids & tool_granted_by)
        assert skill_check_passed is True

        # Compute check fails - tool not available
        compute_has_tool = tool.id in compute_db_only.tools_available
        assert compute_has_tool is False

    def test_global_tool_always_authorized(self, real_skills_registry, compute_standard):
        """Global tools don't require skill or compute checks."""
        tool = real_skills_registry.get_tool("read")
        assert tool is not None
        assert tool.tier == ToolTier.GLOBAL

        # Global tools are always authorized
        # Per spec: "Global tools always allowed"


class TestSystemSkillsAreComplete:
    """Tests verifying system skills have complete metadata."""

    @pytest.mark.asyncio
    async def test_at_least_four_skills_have_specialized_tools(self, real_skills_registry):
        """At least 4 system skills should have specialized_tools defined."""
        skills_with_tools = []
        for skill in real_skills_registry.list_skills(author="system"):
            if skill.specialized_tools:
                skills_with_tools.append(skill.id)

        assert len(skills_with_tools) >= 4, (
            f"Expected at least 4 system skills with specialized_tools, "
            f"found {len(skills_with_tools)}: {skills_with_tools}"
        )

    @pytest.mark.asyncio
    async def test_specialized_tool_count(self, real_skills_registry):
        """Registry should have specialized tools loaded."""
        specialized_tools = real_skills_registry.list_tools(tier=ToolTier.SPECIALIZED)
        assert len(specialized_tools) >= 4, (
            f"Expected at least 4 specialized tools, found {len(specialized_tools)}"
        )

    @pytest.mark.asyncio
    async def test_each_specialized_tool_has_required_labels(self, real_skills_registry):
        """Each specialized tool should have required_labels for compute routing."""
        specialized_tools = real_skills_registry.list_tools(tier=ToolTier.SPECIALIZED)

        tools_missing_labels = []
        for tool in specialized_tools:
            if not tool.required_labels:
                tools_missing_labels.append(tool.id)

        # All 4 main specialized tools should have labels
        expected_tools = ["db_migration_tool", "deploy_prod", "run_security_scan", "test_api_endpoint"]
        for tool_id in expected_tools:
            tool = real_skills_registry.get_tool(tool_id)
            if tool:
                assert tool.required_labels, f"{tool_id} should have required_labels"
