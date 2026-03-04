"""Tests for skill registry service."""

import pytest
from pathlib import Path
from datetime import datetime

from models import Skill, SkillCreateRequest, SkillUpdateRequest, ToolTier
from skill_registry import SkillRegistry


@pytest.fixture
def temp_skills_path(tmp_path):
    """Create a temporary skills directory."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "system").mkdir()
    (skills_dir / "user").mkdir()

    # Create a sample system skill
    system_skill = skills_dir / "system" / "test-skill.yaml"
    system_skill.write_text("""id: test-skill
name: Test Skill
description: A test skill for unit tests
version: "1.0.0"
author: system

instructions: |
  # Test Skill

  You are a test skill used in unit tests.

specialized_tools:
  - test_tool

tags:
  - testing
  - automation

constraints:
  - Do not modify production code
""")

    # Create a sample user skill
    user_skill = skills_dir / "user" / "custom-skill.yaml"
    user_skill.write_text("""id: custom-skill
name: Custom Skill
description: A user-created skill
version: "1.0.0"
author: user:johndoe

instructions: |
  # Custom Skill

  Custom instructions here.

specialized_tools: []

tags:
  - custom
  - user-created

constraints:
  - Follow user guidelines
""")

    return str(skills_dir)


@pytest.fixture
async def registry(temp_skills_path):
    """Create a registry for testing."""
    reg = SkillRegistry(skills_path=temp_skills_path)
    await reg.initialize()
    return reg


@pytest.mark.asyncio
async def test_initialize_loads_skills(temp_skills_path):
    """Test that initialize loads skills from disk."""
    registry = SkillRegistry(skills_path=temp_skills_path)
    await registry.initialize()

    assert registry._initialized is True
    assert len(registry.skills) == 2
    assert "test-skill" in registry.skills
    assert "custom-skill" in registry.skills


@pytest.mark.asyncio
async def test_initialize_registers_specialized_tools(temp_skills_path):
    """Test that initialize registers specialized tools from skills."""
    registry = SkillRegistry(skills_path=temp_skills_path)
    await registry.initialize()

    # test_tool should be registered from test-skill
    tool = registry.get_tool("test_tool")
    assert tool is not None
    assert tool.tier == ToolTier.SPECIALIZED
    assert "test-skill" in tool.granted_by


@pytest.mark.asyncio
async def test_list_skills_no_filters(registry):
    """Test listing all skills without filters."""
    skills = registry.list_skills()

    assert len(skills) == 2
    skill_ids = [s.id for s in skills]
    assert "test-skill" in skill_ids
    assert "custom-skill" in skill_ids


@pytest.mark.asyncio
async def test_list_skills_with_tag_filter(registry):
    """Test listing skills filtered by tags."""
    skills = registry.list_skills(tags=["testing"])

    assert len(skills) == 1
    assert skills[0].id == "test-skill"

    skills = registry.list_skills(tags=["custom"])
    assert len(skills) == 1
    assert skills[0].id == "custom-skill"


@pytest.mark.asyncio
async def test_list_skills_with_author_filter(registry):
    """Test listing skills filtered by author."""
    skills = registry.list_skills(author="system")

    assert len(skills) == 1
    assert skills[0].id == "test-skill"
    assert skills[0].author == "system"

    skills = registry.list_skills(author="user")
    assert len(skills) == 1
    assert skills[0].id == "custom-skill"
    assert skills[0].author.startswith("user:")


@pytest.mark.asyncio
async def test_get_skill_existing(registry):
    """Test getting an existing skill by ID."""
    skill = registry.get_skill("test-skill")

    assert skill is not None
    assert skill.id == "test-skill"
    assert skill.name == "Test Skill"
    assert skill.author == "system"
    assert "test_tool" in skill.specialized_tools
    assert "testing" in skill.tags


@pytest.mark.asyncio
async def test_get_skill_nonexistent(registry):
    """Test getting a nonexistent skill returns None."""
    skill = registry.get_skill("nonexistent")
    assert skill is None


@pytest.mark.asyncio
async def test_search_by_capabilities(registry):
    """Test searching skills by capabilities (tags)."""
    skills = registry.search_by_capabilities(["automation"])

    assert len(skills) == 1
    assert skills[0].id == "test-skill"

    skills = registry.search_by_capabilities(["custom"])
    assert len(skills) == 1
    assert skills[0].id == "custom-skill"


# =============================================================================
# Enhanced Skill Matching Tests (search_by_capabilities_with_fallback)
# =============================================================================


@pytest.fixture
async def registry_with_diverse_skills(tmp_path):
    """Create a registry with diverse skills for matching tests."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "system").mkdir()
    (skills_dir / "user").mkdir()

    # Create skills with various tags for testing matching
    skills_data = [
        {
            "id": "code-writer",
            "name": "Code Writer",
            "tags": ["coding", "implementation", "feature-development", "bug-fix"],
        },
        {
            "id": "test-automator",
            "name": "Test Automator",
            "tags": ["testing", "quality-assurance", "unit-tests", "integration-tests"],
        },
        {
            "id": "security-reviewer",
            "name": "Security Reviewer",
            "tags": ["security", "security-review", "vulnerability-scan", "access-control"],
        },
        {
            "id": "api-integrator",
            "name": "API Integrator",
            "tags": ["api", "integration", "rest", "http", "external-services"],
        },
        {
            "id": "database-expert",
            "name": "Database Expert",
            "tags": ["database", "migration", "schema", "sql", "data-transformation"],
        },
    ]

    for skill_data in skills_data:
        file_path = skills_dir / "system" / f"{skill_data['id']}.yaml"
        file_path.write_text(f"""id: {skill_data['id']}
name: {skill_data['name']}
description: A skill for {skill_data['id']}
version: "1.0.0"
author: system
instructions: |
  # {skill_data['name']}
  Instructions for this skill.
specialized_tools: []
tags:
{chr(10).join(f"  - {tag}" for tag in skill_data['tags'])}
constraints: []
""")

    reg = SkillRegistry(skills_path=str(skills_dir))
    await reg.initialize()
    return reg


@pytest.mark.asyncio
async def test_search_with_fallback_exact_match(registry_with_diverse_skills):
    """Test that exact tag matches are found and scored highest."""
    registry = registry_with_diverse_skills

    # Exact match for "testing"
    skills = registry.search_by_capabilities_with_fallback(["testing"])

    assert len(skills) >= 1
    assert skills[0].id == "test-automator"


@pytest.mark.asyncio
async def test_search_with_fallback_partial_match(registry_with_diverse_skills):
    """Test partial/substring matching when exact match fails."""
    registry = registry_with_diverse_skills

    # "test" should partially match "testing" and "unit-tests"
    skills = registry.search_by_capabilities_with_fallback(["test"])

    assert len(skills) >= 1
    # test-automator has multiple tags containing "test"
    assert skills[0].id == "test-automator"


@pytest.mark.asyncio
async def test_search_with_fallback_token_match(registry_with_diverse_skills):
    """Test token-based matching for hyphenated tags."""
    registry = registry_with_diverse_skills

    # "security" should match "security-review" via token overlap
    skills = registry.search_by_capabilities_with_fallback(["security"])

    assert len(skills) >= 1
    assert skills[0].id == "security-reviewer"


@pytest.mark.asyncio
async def test_search_with_fallback_returns_default_when_no_match(registry_with_diverse_skills):
    """Test that fallback returns default skill when no match found."""
    registry = registry_with_diverse_skills

    # Completely unrelated capability
    skills = registry.search_by_capabilities_with_fallback(["zzz-nonexistent-xyz"])

    assert len(skills) == 1
    assert skills[0].id == "code-writer"  # Default fallback


@pytest.mark.asyncio
async def test_search_with_fallback_empty_capabilities_returns_default(registry_with_diverse_skills):
    """Test that empty capabilities returns default skill."""
    registry = registry_with_diverse_skills

    skills = registry.search_by_capabilities_with_fallback([])

    assert len(skills) == 1
    assert skills[0].id == "code-writer"


@pytest.mark.asyncio
async def test_search_with_fallback_multiple_capabilities(registry_with_diverse_skills):
    """Test matching with multiple capabilities."""
    registry = registry_with_diverse_skills

    # Should match api-integrator (has both "api" and "integration")
    skills = registry.search_by_capabilities_with_fallback(["api", "integration"])

    assert len(skills) >= 1
    assert skills[0].id == "api-integrator"


@pytest.mark.asyncio
async def test_search_with_fallback_respects_max_results(registry_with_diverse_skills):
    """Test that max_results limits output."""
    registry = registry_with_diverse_skills

    # A broad capability that might match multiple skills
    skills = registry.search_by_capabilities_with_fallback(
        ["development"],
        max_results=2,
    )

    assert len(skills) <= 2


@pytest.mark.asyncio
async def test_search_with_fallback_case_insensitive(registry_with_diverse_skills):
    """Test that matching is case-insensitive."""
    registry = registry_with_diverse_skills

    # Uppercase should still match
    skills = registry.search_by_capabilities_with_fallback(["TESTING"])

    assert len(skills) >= 1
    assert skills[0].id == "test-automator"


@pytest.mark.asyncio
async def test_search_with_fallback_custom_default(registry_with_diverse_skills):
    """Test using a custom default skill ID."""
    registry = registry_with_diverse_skills

    # Non-matching capability with custom default
    skills = registry.search_by_capabilities_with_fallback(
        ["zzz-nonexistent"],
        default_skill_id="security-reviewer",
    )

    assert len(skills) == 1
    assert skills[0].id == "security-reviewer"


@pytest.mark.asyncio
async def test_search_with_fallback_relevance_ordering(registry_with_diverse_skills):
    """Test that results are ordered by relevance score."""
    registry = registry_with_diverse_skills

    # "unit-tests" should score higher for test-automator than partial matches
    skills = registry.search_by_capabilities_with_fallback(["unit-tests"])

    assert len(skills) >= 1
    # test-automator has exact match for "unit-tests"
    assert skills[0].id == "test-automator"


@pytest.mark.asyncio
async def test_tokenize_splits_on_hyphens(registry_with_diverse_skills):
    """Test that tokenization correctly handles hyphenated terms."""
    registry = registry_with_diverse_skills

    # Test internal tokenize method
    tokens = registry._tokenize("feature-development")
    assert "feature" in tokens
    assert "development" in tokens


@pytest.mark.asyncio
async def test_tokenize_splits_on_underscores(registry_with_diverse_skills):
    """Test that tokenization handles underscore-separated terms."""
    registry = registry_with_diverse_skills

    tokens = registry._tokenize("code_review_tool")
    assert "code" in tokens
    assert "review" in tokens
    assert "tool" in tokens


@pytest.mark.asyncio
async def test_calculate_match_score_exact_beats_partial_single_tag(registry_with_diverse_skills):
    """Test that exact match on single tag scores higher than partial match on same tag."""
    registry = registry_with_diverse_skills

    # Create a skill with just one tag for isolated testing
    from models import Skill

    single_tag_skill = Skill(
        id="single-tag",
        name="Single Tag Skill",
        description="Test skill",
        version="1.0.0",
        author="system",
        instructions="Test",
        specialized_tools=[],
        tags=["testing"],  # Only one tag
        conflicts_with=[],
        constraints=[],
        dependencies=[],
    )

    # Exact match score (testing == testing)
    exact_score = registry._calculate_match_score(single_tag_skill, ["testing"])

    # Partial match score (test in testing)
    partial_score = registry._calculate_match_score(single_tag_skill, ["test"])

    # Exact should score 10, partial should score 5
    assert exact_score > partial_score
    assert exact_score == 10.0
    assert partial_score == 5.0


@pytest.mark.asyncio
async def test_search_with_fallback_never_returns_empty(registry_with_diverse_skills):
    """Test that search never returns empty list when default exists."""
    registry = registry_with_diverse_skills

    # Various non-matching capabilities
    test_cases = [
        ["xyz123"],
        ["completely-random"],
        ["no-such-capability"],
        ["!!!"],
    ]

    for caps in test_cases:
        skills = registry.search_by_capabilities_with_fallback(caps)
        assert len(skills) >= 1, f"Should return default for {caps}"


@pytest.mark.asyncio
async def test_create_skill(registry, temp_skills_path):
    """Test creating a new skill."""
    request = SkillCreateRequest(
        id="new-skill",
        name="New Skill",
        description="A newly created skill",
        instructions="# New Skill\n\nInstructions here.",
        specialized_tools=["new_tool"],
        tags=["new", "test"],
        constraints=["Be careful"],
        version="1.0.0"
    )

    skill = await registry.create_skill(request, author="testuser")

    assert skill.id == "new-skill"
    assert skill.name == "New Skill"
    assert skill.author == "user:testuser"
    assert "new_tool" in skill.specialized_tools
    assert "new" in skill.tags

    # Verify it was added to registry
    assert "new-skill" in registry.skills

    # Verify it was saved to disk
    file_path = Path(temp_skills_path) / "user" / "new-skill.yaml"
    assert file_path.exists()


@pytest.mark.asyncio
async def test_create_duplicate_skill_raises_error(registry):
    """Test creating a duplicate skill raises ValueError."""
    request = SkillCreateRequest(
        id="test-skill",  # Already exists
        name="Duplicate",
        description="Should fail",
        instructions="Test"
    )

    with pytest.raises(ValueError, match="already exists"):
        await registry.create_skill(request)


@pytest.mark.asyncio
async def test_update_skill(registry, temp_skills_path):
    """Test updating an existing skill."""
    request = SkillUpdateRequest(
        name="Updated Name",
        description="Updated description",
        tags=["updated", "modified"]
    )

    skill = await registry.update_skill("test-skill", request)

    assert skill is not None
    assert skill.name == "Updated Name"
    assert skill.description == "Updated description"
    assert "updated" in skill.tags

    # Verify update timestamp changed
    assert skill.updated_at > skill.created_at

    # Verify it was saved to disk
    file_path = Path(temp_skills_path) / "system" / "test-skill.yaml"
    assert file_path.exists()


@pytest.mark.asyncio
async def test_update_nonexistent_skill(registry):
    """Test updating a nonexistent skill returns None."""
    request = SkillUpdateRequest(name="Should fail")
    skill = await registry.update_skill("nonexistent", request)
    assert skill is None


@pytest.mark.asyncio
async def test_delete_user_skill(registry, temp_skills_path):
    """Test deleting a user skill."""
    result = await registry.delete_skill("custom-skill")

    assert result is True
    assert "custom-skill" not in registry.skills

    # Verify file was deleted
    file_path = Path(temp_skills_path) / "user" / "custom-skill.yaml"
    assert not file_path.exists()


@pytest.mark.asyncio
async def test_delete_system_skill_raises_error(registry):
    """Test deleting a system skill raises ValueError."""
    with pytest.raises(ValueError, match="Cannot delete system skills"):
        await registry.delete_skill("test-skill")

    # Skill should still exist
    assert "test-skill" in registry.skills


@pytest.mark.asyncio
async def test_delete_nonexistent_skill(registry):
    """Test deleting a nonexistent skill returns False."""
    result = await registry.delete_skill("nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_get_stats(registry):
    """Test getting registry statistics."""
    stats = registry.get_stats()

    assert stats["total_skills"] == 2
    assert stats["total_tools"] > 0  # Global tools + specialized
    assert stats["by_author"]["system"] == 1
    assert stats["by_author"]["user"] == 1


@pytest.mark.asyncio
async def test_get_global_tools(registry):
    """Test getting global tools."""
    global_tools = registry.get_global_tools()

    # Should include the default global tools
    assert "read" in global_tools
    assert "write" in global_tools
    assert "edit" in global_tools
    assert "bash" in global_tools
    assert "glob" in global_tools
    assert "grep" in global_tools


@pytest.mark.asyncio
async def test_list_tools_with_tier_filter(registry):
    """Test listing tools filtered by tier."""
    global_tools = registry.list_tools(tier=ToolTier.GLOBAL)
    assert all(t.tier == ToolTier.GLOBAL for t in global_tools)

    specialized_tools = registry.list_tools(tier=ToolTier.SPECIALIZED)
    assert all(t.tier == ToolTier.SPECIALIZED for t in specialized_tools)


# =============================================================================
# Planner Skill Integration Tests
# =============================================================================


@pytest.fixture
def planner_skills_path(tmp_path):
    """Create a skills directory with the planner skill."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "system").mkdir()
    (skills_dir / "user").mkdir()

    # Copy the planner skill content
    planner_skill = skills_dir / "system" / "planner.yaml"
    planner_skill.write_text("""id: planner
name: Planner
description: Analyzes high-level goals and creates detailed implementation plans with properly scoped, dependency-ordered issues.
version: "1.0.0"
author: system

instructions: |
  # Planner

  ## Role
  You analyze high-level goals and break them down into discrete, implementable issues.

  ## Planning Process
  1. Understand the Goal
  2. Analyze Requirements
  3. Design the Decomposition
  4. Map Dependencies
  5. Assign Skills and Priorities
  6. Submit the Plan via claudevn_add_issues

  ## Issue Guidelines
  - One concern per issue
  - Use integer indices for batch-internal dependencies

specialized_tools:
  - claudevn_add_issues

tags:
  - planning
  - decomposition
  - architecture
  - goal-breakdown
  - project-management

conflicts_with: []

constraints:
  - Do not implement code - only plan and decompose
  - Do not create circular dependencies
  - Each issue must be independently verifiable
  - Keep dependency chains shallow
  - Include testing issues for all feature work
  - Ensure all issues link back to the parent goal
""")

    return str(skills_dir)


@pytest.fixture
async def planner_registry(planner_skills_path):
    """Create a registry with planner skill for testing."""
    reg = SkillRegistry(skills_path=planner_skills_path)
    await reg.initialize()
    return reg


@pytest.mark.asyncio
async def test_planner_skill_loads(planner_registry):
    """Test that the planner skill loads correctly."""
    planner = planner_registry.get_skill("planner")

    assert planner is not None
    assert planner.id == "planner"
    assert planner.name == "Planner"
    assert planner.author == "system"
    assert planner.version == "1.0.0"


@pytest.mark.asyncio
async def test_planner_skill_has_claudevn_add_issues_tool(planner_registry):
    """Test that planner skill includes claudevn_add_issues specialized tool."""
    planner = planner_registry.get_skill("planner")

    assert "claudevn_add_issues" in planner.specialized_tools


@pytest.mark.asyncio
async def test_planner_skill_registers_claudevn_add_issues_tool(planner_registry):
    """Test that claudevn_add_issues tool is registered in the registry."""
    tool = planner_registry.get_tool("claudevn_add_issues")

    assert tool is not None
    assert tool.id == "claudevn_add_issues"
    assert tool.tier == ToolTier.SPECIALIZED
    assert "planner" in tool.granted_by


@pytest.mark.asyncio
async def test_planner_skill_has_planning_tags(planner_registry):
    """Test that planner skill has expected tags."""
    planner = planner_registry.get_skill("planner")

    expected_tags = ["planning", "decomposition", "architecture"]
    for tag in expected_tags:
        assert tag in planner.tags


@pytest.mark.asyncio
async def test_planner_skill_searchable_by_planning_capability(planner_registry):
    """Test that planner skill can be found by planning capability."""
    skills = planner_registry.search_by_capabilities(["planning"])

    assert len(skills) == 1
    assert skills[0].id == "planner"


@pytest.mark.asyncio
async def test_planner_skill_has_instructions(planner_registry):
    """Test that planner skill has meaningful instructions."""
    planner = planner_registry.get_skill("planner")

    assert len(planner.instructions) > 100
    assert "Goal" in planner.instructions
    assert "claudevn_add_issues" in planner.instructions


@pytest.mark.asyncio
async def test_planner_skill_has_constraints(planner_registry):
    """Test that planner skill has constraints."""
    planner = planner_registry.get_skill("planner")

    assert len(planner.constraints) > 0
    # Check for key constraints
    constraint_text = " ".join(planner.constraints)
    assert "implement" in constraint_text.lower() or "code" in constraint_text.lower()
    assert "circular" in constraint_text.lower()


@pytest.mark.asyncio
async def test_planner_skill_cannot_be_deleted(planner_registry):
    """Test that planner skill (system skill) cannot be deleted."""
    with pytest.raises(ValueError, match="Cannot delete system skills"):
        await planner_registry.delete_skill("planner")

    # Skill should still exist
    assert planner_registry.get_skill("planner") is not None


# =============================================================================
# Skill Versioning Tests
# NOTE: Full versioning requires Git storage. See test_skill_registry_git.py
# for comprehensive versioning tests with Git-backed storage.
# =============================================================================


@pytest.mark.asyncio
async def test_list_skill_versions_returns_empty_without_git(registry):
    """Test that list_skill_versions returns empty without Git storage.

    Versioning is powered by Git history for user skills.
    Without Git storage, no version history is available.
    See test_skill_registry_git.py for tests with Git-backed versioning.
    """
    # Create a user skill
    request = SkillCreateRequest(
        id="no-git-skill",
        name="No Git Skill",
        description="A skill without Git versioning",
        instructions="# Test",
        version="1.0.0"
    )
    await registry.create_skill(request, author="testuser")

    # Without Git storage, no version history is tracked
    versions = registry.list_skill_versions("no-git-skill")
    assert versions == [], "Without Git storage, version history should be empty"


@pytest.mark.asyncio
async def test_get_skill_version_without_git_returns_current_or_none(registry):
    """Test get_skill_version behavior without Git storage.

    Without Git storage, both system and user skills return current if version matches.
    There is no historical version access - only the current version is available.
    See test_skill_registry_git.py for tests with Git-backed versioning.
    """
    # System skill - current version matches
    skill = registry.get_skill_version("test-skill", "1.0.0")
    assert skill is not None
    assert skill.version == "1.0.0"

    # System skill - version doesn't match
    skill = registry.get_skill_version("test-skill", "2.0.0")
    assert skill is None

    # Create user skill
    request = SkillCreateRequest(
        id="version-check-skill",
        name="Version Check",
        description="Test",
        instructions="Test",
        version="1.0.0"
    )
    await registry.create_skill(request, author="testuser")

    # Without Git, user skills also return current if version matches (fallback behavior)
    skill = registry.get_skill_version("version-check-skill", "1.0.0")
    assert skill is not None
    assert skill.version == "1.0.0"

    # User skill - version doesn't match
    skill = registry.get_skill_version("version-check-skill", "2.0.0")
    assert skill is None, "Non-matching version returns None"


@pytest.mark.asyncio
async def test_get_skill_version_nonexistent_skill(registry):
    """Test that getting version of nonexistent skill returns None."""
    result = registry.get_skill_version("nonexistent-skill", "1.0.0")
    assert result is None


@pytest.mark.asyncio
async def test_list_skill_versions_nonexistent_skill(registry):
    """Test listing versions for nonexistent skill."""
    versions = registry.list_skill_versions("nonexistent-skill")
    assert versions == []


# =============================================================================
# Test: Namespace-Qualified Skill Lookups
# =============================================================================

@pytest.fixture
def namespaced_skills_path(tmp_path):
    """Create a skills directory with namespace-testable skills."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "system").mkdir()
    (skills_dir / "user").mkdir()

    # System skill (should NOT get namespaced)
    system_skill = skills_dir / "system" / "code-writer.yaml"
    system_skill.write_text("""id: code-writer
name: Code Writer
description: Writes code
version: "1.0.0"
author: system
instructions: Write code.
specialized_tools: []
tags: [coding]
conflicts_with: []
constraints: []
dependencies: []
""")

    # User skill (SHOULD get namespaced)
    user_skill = skills_dir / "user" / "custom-linter.yaml"
    user_skill.write_text("""id: custom-linter
name: Custom Linter
description: Team linting rules
version: "1.0.0"
author: user:teamlead
instructions: Apply linting rules.
specialized_tools: []
tags: [linting]
conflicts_with: []
constraints: []
dependencies: []
""")

    return skills_dir


@pytest.mark.asyncio
async def test_namespace_applied_to_user_skills(namespaced_skills_path):
    """Test that namespace prefix is applied to non-ROOT (user) skills."""
    registry = SkillRegistry(
        skills_path=str(namespaced_skills_path),
        namespace="acme",
    )
    await registry.initialize()

    # System skill should NOT be namespaced
    assert "code-writer" in registry.skills
    assert "acme:code-writer" not in registry.skills

    # User skill SHOULD be namespaced
    assert "acme:custom-linter" in registry.skills
    assert "custom-linter" not in registry.skills


@pytest.mark.asyncio
async def test_get_skill_bare_lookup_resolves_namespaced(namespaced_skills_path):
    """Test that bare ID lookup finds a namespaced skill."""
    registry = SkillRegistry(
        skills_path=str(namespaced_skills_path),
        namespace="acme",
    )
    await registry.initialize()

    # Bare lookup should find the namespaced skill
    skill = registry.get_skill("custom-linter")
    assert skill is not None
    assert skill.id == "acme:custom-linter"
    assert skill.namespace == "acme"


@pytest.mark.asyncio
async def test_get_skill_namespaced_lookup(namespaced_skills_path):
    """Test that full namespaced ID lookup works."""
    registry = SkillRegistry(
        skills_path=str(namespaced_skills_path),
        namespace="acme",
    )
    await registry.initialize()

    skill = registry.get_skill("acme:custom-linter")
    assert skill is not None
    assert skill.id == "acme:custom-linter"


@pytest.mark.asyncio
async def test_get_skill_namespaced_fallback_to_bare(namespaced_skills_path):
    """Test that namespaced lookup falls back to bare ID for system skills."""
    registry = SkillRegistry(
        skills_path=str(namespaced_skills_path),
        namespace="acme",
    )
    await registry.initialize()

    # "acme:code-writer" doesn't exist, but "code-writer" does (system skill)
    skill = registry.get_skill("acme:code-writer")
    assert skill is not None
    assert skill.id == "code-writer"


@pytest.mark.asyncio
async def test_no_namespace_no_prefixing(namespaced_skills_path):
    """Test that without namespace, no prefixing occurs."""
    registry = SkillRegistry(
        skills_path=str(namespaced_skills_path),
    )
    await registry.initialize()

    # Both should be stored under bare IDs
    assert "code-writer" in registry.skills
    assert "custom-linter" in registry.skills
    assert not any(":" in k for k in registry.skills.keys())


@pytest.mark.asyncio
async def test_namespace_set_on_skill_object(namespaced_skills_path):
    """Test that the namespace field is set on the Skill object."""
    registry = SkillRegistry(
        skills_path=str(namespaced_skills_path),
        namespace="acme",
    )
    await registry.initialize()

    skill = registry.get_skill("acme:custom-linter")
    assert skill.namespace == "acme"

    # System skill should not have namespace
    system_skill = registry.get_skill("code-writer")
    assert system_skill.namespace is None
