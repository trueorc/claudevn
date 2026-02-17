"""Tests for composition service."""

import pytest
from pathlib import Path

from models import Skill, ProjectContext
from skill_registry import SkillRegistry, set_skill_registry
from composition_service import CompositionService, get_composition_service


@pytest.fixture
def temp_skills_path(tmp_path):
    """Create a temporary skills directory with test skills."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "system").mkdir()
    (skills_dir / "user").mkdir()

    # Create a code-writer skill
    code_writer = skills_dir / "system" / "code-writer.yaml"
    code_writer.write_text("""id: code-writer
name: Code Writer
description: Writes code following best practices
version: "1.0.0"
author: system

instructions: |
  # Code Writer

  You write clean, maintainable code.

  ## Guidelines
  - Follow project conventions
  - Write readable code
  - Keep changes minimal

specialized_tools: []

tags:
  - coding
  - implementation

conflicts_with: []

constraints:
  - Do not refactor unrelated code
  - Keep changes focused
""")

    # Create a test-automator skill
    test_automator = skills_dir / "system" / "test-automator.yaml"
    test_automator.write_text("""id: test-automator
name: Test Automator
description: Creates automated tests
version: "1.0.0"
author: system

instructions: |
  # Test Automator

  You create comprehensive automated tests.

  ## Guidelines
  - Test behavior, not implementation
  - Cover edge cases
  - Keep tests fast

specialized_tools:
  - run_tests
  - test_coverage

tags:
  - testing
  - automation

conflicts_with: []

constraints:
  - Do not write production code
  - Focus on test quality
""")

    # Create a skill with conflicts
    rapid_prototyper = skills_dir / "system" / "rapid-prototyper.yaml"
    rapid_prototyper.write_text("""id: rapid-prototyper
name: Rapid Prototyper
description: Quickly creates prototypes
version: "1.0.0"
author: system

instructions: |
  # Rapid Prototyper

  You quickly build prototypes to validate ideas.

specialized_tools:
  - quick_deploy

tags:
  - prototyping
  - speed

conflicts_with:
  - code-reviewer

constraints:
  - Skip extensive tests for speed
""")

    return str(skills_dir)


@pytest.fixture
async def registry(temp_skills_path):
    """Create and initialize a skill registry for testing."""
    reg = SkillRegistry(skills_path=temp_skills_path)
    await reg.initialize()
    set_skill_registry(reg)
    return reg


@pytest.fixture
def composition_service():
    """Create a composition service instance."""
    return CompositionService()


@pytest.fixture
def sample_context():
    """Create a sample project context."""
    return ProjectContext(
        project_id="test-project",
        conventions="- Use 4 spaces for indentation\n- Follow PEP 8",
        tech_stack=["Python 3.10+", "FastAPI", "PostgreSQL"],
        domain_context="A test project for unit testing",
        custom_rules=["All code must have tests", "No direct database access"]
    )


# =============================================================================
# select_skills_for_task() Tests
# =============================================================================


@pytest.mark.asyncio
async def test_select_skills_for_task_exact_match(registry, composition_service):
    """Test skill selection with exact capability match."""
    from models import TaskAssignment

    task = TaskAssignment(
        task_id="test-1",
        description="Write tests for the API",
        required_capabilities=["testing"],
    )

    skills = composition_service.select_skills_for_task(task)

    assert len(skills) >= 1
    assert skills[0].id == "test-automator"


@pytest.mark.asyncio
async def test_select_skills_for_task_no_capabilities_returns_default(registry, composition_service):
    """Test that no capabilities returns default code-writer skill."""
    from models import TaskAssignment

    task = TaskAssignment(
        task_id="test-2",
        description="Do some work",
        required_capabilities=[],
    )

    skills = composition_service.select_skills_for_task(task)

    assert len(skills) == 1
    assert skills[0].id == "code-writer"


@pytest.mark.asyncio
async def test_select_skills_for_task_partial_match_fallback(registry, composition_service):
    """Test that partial matches work when exact match fails."""
    from models import TaskAssignment

    task = TaskAssignment(
        task_id="test-3",
        description="Write some tests",
        required_capabilities=["test"],  # Should partial match "testing"
    )

    skills = composition_service.select_skills_for_task(task)

    assert len(skills) >= 1
    # Should find test-automator via partial match on "testing"
    assert any(s.id == "test-automator" for s in skills)


@pytest.mark.asyncio
async def test_select_skills_for_task_never_returns_empty(registry, composition_service):
    """Test that skill selection never returns empty list."""
    from models import TaskAssignment

    task = TaskAssignment(
        task_id="test-4",
        description="Do something completely random",
        required_capabilities=["xyz-nonexistent-capability"],
    )

    skills = composition_service.select_skills_for_task(task)

    # Should return default fallback
    assert len(skills) >= 1
    assert skills[0].id == "code-writer"


@pytest.mark.asyncio
async def test_select_skills_for_task_multiple_capabilities(registry, composition_service):
    """Test skill selection with multiple capabilities."""
    from models import TaskAssignment

    task = TaskAssignment(
        task_id="test-5",
        description="Write and test code",
        required_capabilities=["coding", "testing"],
    )

    skills = composition_service.select_skills_for_task(task)

    assert len(skills) >= 1
    # Should return skills that match either capability
    skill_ids = [s.id for s in skills]
    assert "code-writer" in skill_ids or "test-automator" in skill_ids


# =============================================================================
# compose_skills() Tests
# =============================================================================


@pytest.mark.asyncio
async def test_compose_skills_single_skill(registry, composition_service):
    """Test composing a single skill returns valid CLAUDE.md."""
    result = composition_service.compose_skills(["code-writer"])

    assert "# Agent Configuration" in result
    assert "Code Writer" in result
    assert "clean, maintainable code" in result
    assert "## Constraints" in result
    assert "Do not refactor unrelated code" in result


@pytest.mark.asyncio
async def test_compose_skills_multiple_skills(registry, composition_service):
    """Test composing multiple skills concatenates them with section headers."""
    result = composition_service.compose_skills(["code-writer", "test-automator"])

    # Check header
    assert "# Agent Configuration" in result
    assert "**Active Skills:** Code Writer, Test Automator" in result

    # Check both skills are included
    assert "### Code Writer" in result
    assert "### Test Automator" in result

    # Check instructions from both skills
    assert "clean, maintainable code" in result
    assert "comprehensive automated tests" in result

    # Check constraints from both skills
    assert "Do not refactor unrelated code" in result
    assert "Do not write production code" in result


@pytest.mark.asyncio
async def test_compose_skills_with_context(registry, composition_service, sample_context):
    """Test composing skills with project context includes context section."""
    result = composition_service.compose_skills(["code-writer"], context=sample_context)

    # Check project context section
    assert "## Project Context" in result
    assert "### Conventions" in result
    assert "4 spaces for indentation" in result
    assert "### Tech Stack" in result
    assert "Python 3.10+" in result
    assert "FastAPI" in result
    assert "### Domain" in result
    assert "test project for unit testing" in result
    assert "### Rules" in result
    assert "All code must have tests" in result


@pytest.mark.asyncio
async def test_compose_skills_no_context(registry, composition_service):
    """Test composing skills without context omits context section."""
    result = composition_service.compose_skills(["code-writer"])

    assert "## Project Context" not in result
    assert "### Conventions" not in result


@pytest.mark.asyncio
async def test_compose_skills_invalid_skill_id_raises_error(registry, composition_service):
    """Test composing with all invalid skill IDs raises ValueError."""
    with pytest.raises(ValueError, match="No valid skills found"):
        composition_service.compose_skills(["nonexistent-skill"])


@pytest.mark.asyncio
async def test_compose_skills_partial_invalid_ids(registry, composition_service):
    """Test composing with some invalid IDs ignores them and uses valid ones."""
    result = composition_service.compose_skills(["code-writer", "nonexistent-skill"])

    # Should still work with the valid skill
    assert "Code Writer" in result
    assert "clean, maintainable code" in result


@pytest.mark.asyncio
async def test_compose_skills_empty_list_raises_error(registry, composition_service):
    """Test composing with empty skill list raises ValueError."""
    with pytest.raises(ValueError, match="No valid skills found"):
        composition_service.compose_skills([])


@pytest.mark.asyncio
async def test_compose_skills_preserves_order(registry, composition_service):
    """Test skills are composed in the order provided."""
    result = composition_service.compose_skills(["test-automator", "code-writer"])

    # Test Automator should appear before Code Writer
    ta_pos = result.find("### Test Automator")
    cw_pos = result.find("### Code Writer")
    assert ta_pos < cw_pos, "Skills should be in the order provided"


@pytest.mark.asyncio
async def test_compose_skills_with_conflicts_logs_warning(temp_skills_path, composition_service, caplog):
    """Test composing skills with conflicts logs a warning but proceeds."""
    # Create a code-reviewer skill to conflict with rapid-prototyper
    reviewer = Path(temp_skills_path) / "system" / "code-reviewer.yaml"
    reviewer.write_text("""id: code-reviewer
name: Code Reviewer
description: Reviews code for quality
version: "1.0.0"
author: system
instructions: |
  # Code Reviewer
  You review code thoroughly.
specialized_tools: []
tags:
  - review
conflicts_with: []
constraints: []
""")
    # Create a fresh registry to load the new skill
    fresh_registry = SkillRegistry(skills_path=temp_skills_path)
    await fresh_registry.initialize()
    set_skill_registry(fresh_registry)

    import logging
    with caplog.at_level(logging.WARNING):
        result = composition_service.compose_skills(["rapid-prototyper", "code-reviewer"])

    # Should still produce a result
    assert "Rapid Prototyper" in result
    assert "Code Reviewer" in result

    # Should have logged a warning about conflicts
    assert "conflicts" in caplog.text.lower()


# =============================================================================
# aggregate_tools_for_skills() Tests
# =============================================================================


@pytest.mark.asyncio
async def test_aggregate_tools_includes_global_tools(registry, composition_service):
    """Test that aggregate_tools_for_skills includes global tools."""
    tools = composition_service.aggregate_tools_for_skills(["code-writer"])

    # Global tools should be included
    assert "read" in tools
    assert "write" in tools
    assert "edit" in tools
    assert "bash" in tools
    assert "glob" in tools
    assert "grep" in tools


@pytest.mark.asyncio
async def test_aggregate_tools_includes_specialized_tools(registry, composition_service):
    """Test that aggregate_tools_for_skills includes specialized tools from skills."""
    tools = composition_service.aggregate_tools_for_skills(["test-automator"])

    # Should include specialized tools from test-automator
    assert "run_tests" in tools
    assert "test_coverage" in tools


@pytest.mark.asyncio
async def test_aggregate_tools_multiple_skills(registry, composition_service):
    """Test aggregating tools from multiple skills combines all tools."""
    tools = composition_service.aggregate_tools_for_skills(
        ["code-writer", "test-automator", "rapid-prototyper"]
    )

    # Global tools
    assert "read" in tools
    assert "write" in tools

    # From test-automator
    assert "run_tests" in tools
    assert "test_coverage" in tools

    # From rapid-prototyper
    assert "quick_deploy" in tools


@pytest.mark.asyncio
async def test_aggregate_tools_no_duplicates(registry, composition_service):
    """Test that tools are not duplicated in the result."""
    tools = composition_service.aggregate_tools_for_skills(
        ["code-writer", "test-automator"]
    )

    # Should be unique
    assert len(tools) == len(set(tools))


@pytest.mark.asyncio
async def test_aggregate_tools_sorted(registry, composition_service):
    """Test that tools are returned in sorted order."""
    tools = composition_service.aggregate_tools_for_skills(
        ["test-automator", "rapid-prototyper"]
    )

    assert tools == sorted(tools)


@pytest.mark.asyncio
async def test_aggregate_tools_invalid_skill_ignored(registry, composition_service):
    """Test that invalid skill IDs are ignored."""
    tools = composition_service.aggregate_tools_for_skills(
        ["code-writer", "nonexistent-skill"]
    )

    # Should still return global tools from valid skill
    assert "read" in tools
    assert "write" in tools


@pytest.mark.asyncio
async def test_aggregate_tools_empty_list(registry, composition_service):
    """Test aggregating tools with empty list returns global tools only."""
    tools = composition_service.aggregate_tools_for_skills([])

    # Should return global tools
    assert "read" in tools
    assert "write" in tools
    assert "edit" in tools


# =============================================================================
# Integration Tests: compose_skills + aggregate_tools_for_skills
# =============================================================================


@pytest.mark.asyncio
async def test_compose_and_aggregate_consistency(registry, composition_service):
    """Test that compose_skills and aggregate_tools_for_skills are consistent."""
    skill_ids = ["code-writer", "test-automator"]

    # Both methods should work with the same skill IDs
    instructions = composition_service.compose_skills(skill_ids)
    tools = composition_service.aggregate_tools_for_skills(skill_ids)

    assert instructions is not None
    assert len(tools) > 0

    # The tools should include specialized tools from skills mentioned in instructions
    assert "run_tests" in tools  # From test-automator
    assert "Test Automator" in instructions


@pytest.mark.asyncio
async def test_compose_output_matches_spec_format(registry, composition_service, sample_context):
    """Test that compose_skills output matches the expected format from the spec."""
    result = composition_service.compose_skills(
        ["code-writer", "test-automator"],
        context=sample_context
    )

    # Expected sections from the specification
    sections_expected = [
        "# Agent Configuration",
        "**Active Skills:**",
        "## Project Context",
        "### Conventions",
        "### Tech Stack",
        "### Domain",
        "### Rules",
        "## Skill Instructions",
        "### Code Writer",
        "### Test Automator",
        "## Constraints",
    ]

    for section in sections_expected:
        assert section in result, f"Missing expected section: {section}"


# =============================================================================
# add_skill() Tests - Conflict Detection at Skill Addition
# =============================================================================


@pytest.mark.asyncio
async def test_add_skill_no_conflicts(registry, composition_service):
    """Test adding a skill with no conflicts succeeds."""
    result = composition_service.add_skill(
        existing_skill_ids=["code-writer"],
        new_skill_id="test-automator"
    )

    assert result.added is True
    assert result.has_conflicts is False
    assert result.skill_id == "test-automator"
    assert result.skill_name == "Test Automator"
    assert result.can_proceed is True
    assert len(result.conflicts) == 0
    assert "added successfully" in result.message


@pytest.mark.asyncio
async def test_add_skill_with_conflicts_not_added_without_force(temp_skills_path, composition_service):
    """Test adding a skill with conflicts returns warning but doesn't add without force."""
    # Create a code-reviewer skill to conflict with rapid-prototyper
    reviewer = Path(temp_skills_path) / "system" / "code-reviewer.yaml"
    reviewer.write_text("""id: code-reviewer
name: Code Reviewer
description: Reviews code for quality
version: "1.0.0"
author: system
instructions: |
  # Code Reviewer
  You review code thoroughly.
specialized_tools: []
tags:
  - review
conflicts_with: []
constraints: []
""")
    # Create a fresh registry to load the new skill
    fresh_registry = SkillRegistry(skills_path=temp_skills_path)
    await fresh_registry.initialize()
    set_skill_registry(fresh_registry)

    # rapid-prototyper declares conflict with code-reviewer
    result = composition_service.add_skill(
        existing_skill_ids=["code-reviewer"],
        new_skill_id="rapid-prototyper"
    )

    assert result.added is False
    assert result.has_conflicts is True
    assert result.skill_id == "rapid-prototyper"
    assert result.skill_name == "Rapid Prototyper"
    assert result.can_proceed is True  # Decision point, not rejection
    assert len(result.conflicts) > 0
    assert "code-reviewer" in str(result.conflicts)
    assert "force=True" in result.message


@pytest.mark.asyncio
async def test_add_skill_with_conflicts_added_with_force(temp_skills_path, composition_service, caplog):
    """Test adding a skill with conflicts succeeds when force=True."""
    # Create a code-reviewer skill to conflict with rapid-prototyper
    reviewer = Path(temp_skills_path) / "system" / "code-reviewer.yaml"
    reviewer.write_text("""id: code-reviewer
name: Code Reviewer
description: Reviews code for quality
version: "1.0.0"
author: system
instructions: |
  # Code Reviewer
  You review code thoroughly.
specialized_tools: []
tags:
  - review
conflicts_with: []
constraints: []
""")
    fresh_registry = SkillRegistry(skills_path=temp_skills_path)
    await fresh_registry.initialize()
    set_skill_registry(fresh_registry)

    import logging
    with caplog.at_level(logging.WARNING):
        result = composition_service.add_skill(
            existing_skill_ids=["code-reviewer"],
            new_skill_id="rapid-prototyper",
            force=True
        )

    assert result.added is True
    assert result.has_conflicts is True
    assert result.skill_id == "rapid-prototyper"
    assert result.can_proceed is True
    assert "forced" in result.message
    # Should log a warning
    assert "conflicts" in caplog.text.lower()


@pytest.mark.asyncio
async def test_add_skill_not_found(registry, composition_service):
    """Test adding a non-existent skill returns appropriate error."""
    result = composition_service.add_skill(
        existing_skill_ids=["code-writer"],
        new_skill_id="nonexistent-skill"
    )

    assert result.added is False
    assert result.has_conflicts is False
    assert result.can_proceed is False
    assert "not found" in result.message


@pytest.mark.asyncio
async def test_add_skill_already_in_composition(registry, composition_service):
    """Test adding a skill that's already in the composition."""
    result = composition_service.add_skill(
        existing_skill_ids=["code-writer", "test-automator"],
        new_skill_id="code-writer"
    )

    assert result.added is False
    assert result.has_conflicts is False
    assert result.can_proceed is True
    assert "already in the composition" in result.message


@pytest.mark.asyncio
async def test_add_skill_bidirectional_conflicts(temp_skills_path, composition_service):
    """Test that conflicts are detected bidirectionally."""
    # Create skills with bidirectional conflicts
    skill_a = Path(temp_skills_path) / "system" / "skill-a.yaml"
    skill_a.write_text("""id: skill-a
name: Skill A
description: Test skill A
version: "1.0.0"
author: system
instructions: |
  # Skill A
specialized_tools: []
tags: []
conflicts_with:
  - skill-b
constraints: []
""")
    skill_b = Path(temp_skills_path) / "system" / "skill-b.yaml"
    skill_b.write_text("""id: skill-b
name: Skill B
description: Test skill B
version: "1.0.0"
author: system
instructions: |
  # Skill B
specialized_tools: []
tags: []
conflicts_with:
  - skill-a
constraints: []
""")
    fresh_registry = SkillRegistry(skills_path=temp_skills_path)
    await fresh_registry.initialize()
    set_skill_registry(fresh_registry)

    # Adding skill-b to [skill-a] should detect both conflict directions
    result = composition_service.add_skill(
        existing_skill_ids=["skill-a"],
        new_skill_id="skill-b"
    )

    assert result.has_conflicts is True
    # Should have conflicts from both directions
    assert len(result.conflicts) == 2


@pytest.mark.asyncio
async def test_add_skill_tool_overlap_warning(temp_skills_path, composition_service):
    """Test that overlapping tools generate warnings."""
    # Create skills with overlapping tools
    skill_x = Path(temp_skills_path) / "system" / "skill-x.yaml"
    skill_x.write_text("""id: skill-x
name: Skill X
description: Test skill X
version: "1.0.0"
author: system
instructions: |
  # Skill X
specialized_tools:
  - shared_tool
tags: []
conflicts_with: []
constraints: []
""")
    skill_y = Path(temp_skills_path) / "system" / "skill-y.yaml"
    skill_y.write_text("""id: skill-y
name: Skill Y
description: Test skill Y
version: "1.0.0"
author: system
instructions: |
  # Skill Y
specialized_tools:
  - shared_tool
tags: []
conflicts_with: []
constraints: []
""")
    fresh_registry = SkillRegistry(skills_path=temp_skills_path)
    await fresh_registry.initialize()
    set_skill_registry(fresh_registry)

    result = composition_service.add_skill(
        existing_skill_ids=["skill-x"],
        new_skill_id="skill-y"
    )

    # Should add (no explicit conflicts) but with warning
    assert result.added is True
    assert result.has_conflicts is False
    assert len(result.warnings) > 0
    assert "shared_tool" in str(result.warnings)


@pytest.mark.asyncio
async def test_add_skill_empty_existing_skills(registry, composition_service):
    """Test adding a skill to an empty composition."""
    result = composition_service.add_skill(
        existing_skill_ids=[],
        new_skill_id="code-writer"
    )

    assert result.added is True
    assert result.has_conflicts is False
    assert result.skill_id == "code-writer"


# =============================================================================
# resolve_dependencies() Tests - Skill Dependency Resolution
# =============================================================================


@pytest.fixture
def temp_skills_with_dependencies(tmp_path):
    """Create skills with dependency relationships for testing."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "system").mkdir()
    (skills_dir / "user").mkdir()

    # Base skill with no dependencies
    code_analysis = skills_dir / "system" / "code-analysis.yaml"
    code_analysis.write_text("""id: code-analysis
name: Code Analysis
description: Reviews code for quality
version: "1.0.0"
author: system
instructions: |
  # Code Analysis
  You review code quality.
specialized_tools: []
tags:
  - review
  - analysis
conflicts_with: []
constraints: []
dependencies: []
""")

    # Skill depending on code-analysis
    prod_deployment = skills_dir / "system" / "prod-deployment.yaml"
    prod_deployment.write_text("""id: prod-deployment
name: Production Deployment
description: Deploys to production
version: "1.0.0"
author: system
instructions: |
  # Production Deployment
  You deploy safely.
specialized_tools:
  - deploy_prod
tags:
  - deployment
conflicts_with: []
constraints: []
dependencies:
  - code-analysis
""")

    # Base skill for chain testing
    code_implementation = skills_dir / "system" / "code-implementation.yaml"
    code_implementation.write_text("""id: code-implementation
name: Code Implementation
description: Writes code
version: "1.0.0"
author: system
instructions: |
  # Code Implementation
  You write code.
specialized_tools: []
tags:
  - coding
conflicts_with: []
constraints: []
dependencies: []
""")

    # Skill depending on code-implementation
    database_migration = skills_dir / "system" / "database-migration.yaml"
    database_migration.write_text("""id: database-migration
name: Database Migration
description: Manages database migrations
version: "1.0.0"
author: system
instructions: |
  # Database Migration
  You manage migrations.
specialized_tools:
  - db_migration_tool
tags:
  - database
conflicts_with: []
constraints: []
dependencies:
  - code-implementation
""")

    # Base skill for chain testing
    test_creation = skills_dir / "system" / "test-creation.yaml"
    test_creation.write_text("""id: test-creation
name: Test Creation
description: Creates tests
version: "1.0.0"
author: system
instructions: |
  # Test Creation
  You write tests.
specialized_tools:
  - run_tests
tags:
  - testing
conflicts_with: []
constraints: []
dependencies: []
""")

    # Skill depending on test-creation
    api_integration = skills_dir / "system" / "api-integration.yaml"
    api_integration.write_text("""id: api-integration
name: API Integration
description: Integrates with APIs
version: "1.0.0"
author: system
instructions: |
  # API Integration
  You integrate APIs.
specialized_tools:
  - test_api_endpoint
tags:
  - api
conflicts_with: []
constraints: []
dependencies:
  - test-creation
""")

    # Multi-level dependency chain: skill-c -> skill-b -> skill-a
    skill_a = skills_dir / "system" / "skill-chain-a.yaml"
    skill_a.write_text("""id: skill-chain-a
name: Skill Chain A
description: Base of chain
version: "1.0.0"
author: system
instructions: |
  # Skill Chain A
specialized_tools: []
tags: []
conflicts_with: []
constraints: []
dependencies: []
""")

    skill_b = skills_dir / "system" / "skill-chain-b.yaml"
    skill_b.write_text("""id: skill-chain-b
name: Skill Chain B
description: Depends on A
version: "1.0.0"
author: system
instructions: |
  # Skill Chain B
specialized_tools: []
tags: []
conflicts_with: []
constraints: []
dependencies:
  - skill-chain-a
""")

    skill_c = skills_dir / "system" / "skill-chain-c.yaml"
    skill_c.write_text("""id: skill-chain-c
name: Skill Chain C
description: Depends on B (and transitively A)
version: "1.0.0"
author: system
instructions: |
  # Skill Chain C
specialized_tools: []
tags: []
conflicts_with: []
constraints: []
dependencies:
  - skill-chain-b
""")

    return str(skills_dir)


@pytest.fixture
async def registry_with_deps(temp_skills_with_dependencies):
    """Create and initialize registry with dependency test skills."""
    reg = SkillRegistry(skills_path=temp_skills_with_dependencies)
    await reg.initialize()
    set_skill_registry(reg)
    return reg


@pytest.mark.asyncio
async def test_resolve_dependencies_single_skill_no_deps(registry_with_deps, composition_service):
    """Test resolving dependencies for a skill with no dependencies."""
    resolved = composition_service.resolve_dependencies(["code-analysis"])

    assert "code-analysis" in resolved
    assert len(resolved) == 1


@pytest.mark.asyncio
async def test_resolve_dependencies_adds_dependency(registry_with_deps, composition_service):
    """Test that dependencies are automatically added."""
    # prod-deployment depends on code-analysis
    resolved = composition_service.resolve_dependencies(["prod-deployment"])

    assert "prod-deployment" in resolved
    assert "code-analysis" in resolved
    assert len(resolved) == 2


@pytest.mark.asyncio
async def test_resolve_dependencies_transitive_chain(registry_with_deps, composition_service):
    """Test that transitive dependencies are resolved (C -> B -> A)."""
    # skill-chain-c -> skill-chain-b -> skill-chain-a
    resolved = composition_service.resolve_dependencies(["skill-chain-c"])

    assert "skill-chain-c" in resolved
    assert "skill-chain-b" in resolved
    assert "skill-chain-a" in resolved
    assert len(resolved) == 3


@pytest.mark.asyncio
async def test_resolve_dependencies_no_duplicates(registry_with_deps, composition_service):
    """Test that duplicate skills are not added when already in list."""
    # If we request both prod-deployment and code-analysis, code-analysis should appear once
    resolved = composition_service.resolve_dependencies(["prod-deployment", "code-analysis"])

    assert resolved.count("code-analysis") == 1 or len([x for x in resolved if x == "code-analysis"]) == 1
    assert "prod-deployment" in resolved
    assert len(set(resolved)) == len(resolved)  # All unique


@pytest.mark.asyncio
async def test_resolve_dependencies_multiple_skills_with_shared_deps(registry_with_deps, composition_service):
    """Test resolving dependencies for multiple skills with overlapping dependencies."""
    # Request multiple skills that have independent dependencies
    resolved = composition_service.resolve_dependencies([
        "prod-deployment",  # depends on code-analysis
        "database-migration"  # depends on code-implementation
    ])

    assert "prod-deployment" in resolved
    assert "code-analysis" in resolved
    assert "database-migration" in resolved
    assert "code-implementation" in resolved
    assert len(set(resolved)) == 4


@pytest.mark.asyncio
async def test_resolve_dependencies_missing_dependency_logged(temp_skills_with_dependencies, composition_service, caplog):
    """Test that missing dependencies are logged as warnings."""
    from pathlib import Path

    # Add a skill with a non-existent dependency to the skills dir before initialization
    bad_skill = Path(temp_skills_with_dependencies) / "system" / "bad-dependency.yaml"
    bad_skill.write_text("""id: bad-dependency
name: Bad Dependency
description: Has missing dependency
version: "1.0.0"
author: system
instructions: |
  # Bad
specialized_tools: []
tags: []
conflicts_with: []
constraints: []
dependencies:
  - nonexistent-skill
""")

    # Create a fresh registry that will load the bad-dependency skill
    fresh_registry = SkillRegistry(skills_path=temp_skills_with_dependencies)
    await fresh_registry.initialize()
    set_skill_registry(fresh_registry)

    import logging
    with caplog.at_level(logging.WARNING):
        resolved = composition_service.resolve_dependencies(["bad-dependency"])

    assert "bad-dependency" in resolved
    assert "nonexistent-skill" not in resolved
    assert "not found" in caplog.text.lower()


@pytest.mark.asyncio
async def test_resolve_dependencies_empty_list(registry_with_deps, composition_service):
    """Test resolving dependencies for empty list returns empty list."""
    resolved = composition_service.resolve_dependencies([])

    assert len(resolved) == 0


@pytest.mark.asyncio
async def test_compose_with_dependency_resolution(registry_with_deps, composition_service):
    """Test that compose() automatically resolves dependencies."""
    from models import TaskAssignment, ComposeRequest

    task = TaskAssignment(
        task_id="test-task",
        description="Test deployment task"
    )
    request = ComposeRequest(
        task=task,
        skill_ids=["prod-deployment"]  # Only request prod-deployment
    )

    agent = await composition_service.compose(request)

    # Should have both prod-deployment and its dependency code-analysis
    skill_ids = [s.id for s in agent.skills]
    assert "prod-deployment" in skill_ids
    assert "code-analysis" in skill_ids


@pytest.mark.asyncio
async def test_compose_skills_with_dependency_resolution(registry_with_deps, composition_service):
    """Test that compose_skills() resolves dependencies by default."""
    result = composition_service.compose_skills(["prod-deployment"])

    # Should include both skills in the composed instructions
    assert "Production Deployment" in result
    assert "Code Analysis" in result


@pytest.mark.asyncio
async def test_compose_skills_without_dependency_resolution(registry_with_deps, composition_service):
    """Test that compose_skills() can skip dependency resolution."""
    result = composition_service.compose_skills(["prod-deployment"], resolve_deps=False)

    # Should only include the requested skill
    assert "Production Deployment" in result
    assert "Code Analysis" not in result


@pytest.mark.asyncio
async def test_aggregate_tools_with_dependencies(registry_with_deps, composition_service):
    """Test that aggregate_tools_for_skills includes tools from dependencies."""
    # prod-deployment has deploy_prod tool, code-analysis has no special tools
    tools = composition_service.aggregate_tools_for_skills(["prod-deployment"])

    assert "deploy_prod" in tools
    # Global tools should still be included
    assert "read" in tools


@pytest.mark.asyncio
async def test_aggregate_tools_chain_dependencies(registry_with_deps, composition_service):
    """Test that tools from transitive dependencies are included."""
    # api-integration -> test-creation
    # api-integration has test_api_endpoint, test-creation has run_tests
    tools = composition_service.aggregate_tools_for_skills(["api-integration"])

    assert "test_api_endpoint" in tools
    assert "run_tests" in tools  # From dependency test-creation


# =============================================================================
# Agent Cache Eviction Tests
# =============================================================================


@pytest.fixture
def small_cache_service():
    """Create a composition service with a small cache for testing eviction."""
    return CompositionService(cache_max_size=3, cache_ttl=1)  # 1 second TTL for testing


@pytest.mark.asyncio
async def test_cache_stats_initial(small_cache_service):
    """Test that cache stats are correct on initialization."""
    stats = small_cache_service.get_cache_stats()

    assert stats.size == 0
    assert stats.max_size == 3
    assert stats.ttl_seconds == 1
    assert stats.evictions == 0
    assert stats.hits == 0
    assert stats.misses == 0
    assert stats.hit_rate == 0.0


@pytest.mark.asyncio
async def test_cache_hit_miss_tracking(registry, small_cache_service):
    """Test that cache hits and misses are tracked correctly."""
    from models import TaskAssignment, ComposeRequest

    task = TaskAssignment(task_id="test-task", description="Test task")
    request = ComposeRequest(task=task, skill_ids=["code-writer"])

    # Create an agent
    agent = await small_cache_service.compose(request)

    # Hit: get existing agent
    result = small_cache_service.get_agent(agent.id)
    assert result is not None
    stats = small_cache_service.get_cache_stats()
    assert stats.hits == 1
    assert stats.misses == 0

    # Miss: get non-existent agent
    result = small_cache_service.get_agent("nonexistent-agent")
    assert result is None
    stats = small_cache_service.get_cache_stats()
    assert stats.hits == 1
    assert stats.misses == 1

    # Check hit rate
    assert stats.hit_rate == 0.5


@pytest.mark.asyncio
async def test_cache_eviction_on_capacity(registry, small_cache_service):
    """Test that old agents are evicted when cache reaches capacity."""
    from models import TaskAssignment, ComposeRequest

    agent_ids = []

    # Fill the cache (max_size=3)
    for i in range(3):
        task = TaskAssignment(task_id=f"test-task-{i}", description=f"Test task {i}")
        request = ComposeRequest(task=task, skill_ids=["code-writer"])
        agent = await small_cache_service.compose(request)
        agent_ids.append(agent.id)

    stats = small_cache_service.get_cache_stats()
    assert stats.size == 3
    assert stats.evictions == 0

    # Add one more agent - should trigger eviction
    task = TaskAssignment(task_id="test-task-overflow", description="Overflow task")
    request = ComposeRequest(task=task, skill_ids=["code-writer"])
    new_agent = await small_cache_service.compose(request)

    stats = small_cache_service.get_cache_stats()
    assert stats.size == 3  # Still at capacity
    assert stats.evictions == 1  # One agent was evicted

    # The new agent should be in the cache
    assert small_cache_service.get_agent(new_agent.id) is not None


@pytest.mark.asyncio
async def test_cache_ttl_expiration(registry, small_cache_service):
    """Test that agents are evicted after TTL expires."""
    import asyncio
    from models import TaskAssignment, ComposeRequest

    task = TaskAssignment(task_id="test-task", description="Test task")
    request = ComposeRequest(task=task, skill_ids=["code-writer"])
    agent = await small_cache_service.compose(request)

    # Agent should be in cache immediately
    assert small_cache_service.get_agent(agent.id) is not None

    # Wait for TTL to expire (1 second + buffer)
    await asyncio.sleep(1.5)

    # Agent should be expired now
    result = small_cache_service.get_agent(agent.id)
    assert result is None

    stats = small_cache_service.get_cache_stats()
    assert stats.misses >= 1  # The expired lookup counts as a miss


@pytest.mark.asyncio
async def test_cache_clear(registry, small_cache_service):
    """Test that clear_cache removes all agents."""
    from models import TaskAssignment, ComposeRequest

    # Add some agents
    for i in range(2):
        task = TaskAssignment(task_id=f"test-task-{i}", description=f"Test task {i}")
        request = ComposeRequest(task=task, skill_ids=["code-writer"])
        await small_cache_service.compose(request)

    stats = small_cache_service.get_cache_stats()
    assert stats.size == 2

    # Clear the cache
    cleared = small_cache_service.clear_cache()
    assert cleared == 2

    stats = small_cache_service.get_cache_stats()
    assert stats.size == 0


@pytest.mark.asyncio
async def test_cache_list_agents_excludes_expired(registry, small_cache_service):
    """Test that list_agents only returns non-expired agents."""
    import asyncio
    from models import TaskAssignment, ComposeRequest

    task = TaskAssignment(task_id="test-task", description="Test task")
    request = ComposeRequest(task=task, skill_ids=["code-writer"])
    await small_cache_service.compose(request)

    # Agent should be in list immediately
    agents = small_cache_service.list_agents()
    assert len(agents) == 1

    # Wait for TTL to expire
    await asyncio.sleep(1.5)

    # Expired agents should not appear in list
    agents = small_cache_service.list_agents()
    assert len(agents) == 0


@pytest.mark.asyncio
async def test_cache_config_from_environment(monkeypatch):
    """Test that cache config can be set via environment variables."""
    monkeypatch.setenv('AGENT_CACHE_MAX_SIZE', '5000')
    monkeypatch.setenv('AGENT_CACHE_TTL', '3600')

    # Reset config singleton to pick up new env vars
    import config
    config._config = None

    service = CompositionService()
    stats = service.get_cache_stats()

    assert stats.max_size == 5000
    assert stats.ttl_seconds == 3600


@pytest.mark.asyncio
async def test_cache_constructor_override(registry):
    """Test that cache settings can be overridden in constructor."""
    service = CompositionService(cache_max_size=100, cache_ttl=7200)
    stats = service.get_cache_stats()

    assert stats.max_size == 100
    assert stats.ttl_seconds == 7200


# =============================================================================
# resolve_conflict() Tests - Conflict Resolution Workflow
# =============================================================================


@pytest.fixture
def temp_skills_with_conflicts(tmp_path):
    """Create skills with explicit conflicts for resolution testing."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "system").mkdir()
    (skills_dir / "user").mkdir()

    # Code Writer skill
    code_writer = skills_dir / "system" / "code-writer.yaml"
    code_writer.write_text("""id: code-writer
name: Code Writer
description: Writes code following best practices
version: "1.0.0"
author: system
instructions: |
  # Code Writer
  You write clean, maintainable code.
specialized_tools: []
tags:
  - coding
conflicts_with: []
constraints: []
""")

    # Code Reviewer skill - conflicts with rapid-prototyper
    code_reviewer = skills_dir / "system" / "code-reviewer.yaml"
    code_reviewer.write_text("""id: code-reviewer
name: Code Reviewer
description: Reviews code for quality
version: "1.0.0"
author: system
instructions: |
  # Code Reviewer
  You review code thoroughly.
specialized_tools: []
tags:
  - review
conflicts_with: []
constraints: []
""")

    # Rapid Prototyper skill - declares conflict with code-reviewer
    rapid_prototyper = skills_dir / "system" / "rapid-prototyper.yaml"
    rapid_prototyper.write_text("""id: rapid-prototyper
name: Rapid Prototyper
description: Quickly creates prototypes
version: "1.0.0"
author: system
instructions: |
  # Rapid Prototyper
  You build prototypes fast.
specialized_tools:
  - quick_deploy
tags:
  - prototyping
conflicts_with:
  - code-reviewer
constraints: []
""")

    return str(skills_dir)


@pytest.fixture
async def registry_with_conflicts(temp_skills_with_conflicts):
    """Create and initialize registry with conflict test skills."""
    reg = SkillRegistry(skills_path=temp_skills_with_conflicts)
    await reg.initialize()
    set_skill_registry(reg)
    return reg


@pytest.mark.asyncio
async def test_resolve_conflict_cancel(registry_with_conflicts, composition_service):
    """Test resolving a conflict by cancelling the addition."""
    from models import ConflictResolution

    result = composition_service.resolve_conflict(
        new_skill_id="code-reviewer",
        existing_skill_ids=["code-writer", "rapid-prototyper"],
        conflicting_skill_ids=["rapid-prototyper"],
        resolution=ConflictResolution.CANCEL,
        reason="Changed my mind"
    )

    assert result.success is True
    assert result.resolution == ConflictResolution.CANCEL
    assert result.new_skill_id == "code-reviewer"
    assert result.new_skill_name == "Code Reviewer"
    # Existing composition unchanged
    assert result.resulting_skill_ids == ["code-writer", "rapid-prototyper"]
    assert result.removed_skill_ids == []
    assert "cancelled" in result.message.lower()
    assert result.reason == "Changed my mind"


@pytest.mark.asyncio
async def test_resolve_conflict_keep_both(registry_with_conflicts, composition_service):
    """Test resolving a conflict by keeping both skills."""
    from models import ConflictResolution

    result = composition_service.resolve_conflict(
        new_skill_id="code-reviewer",
        existing_skill_ids=["code-writer", "rapid-prototyper"],
        conflicting_skill_ids=["rapid-prototyper"],
        resolution=ConflictResolution.KEEP_BOTH,
        reason="Intentional combination"
    )

    assert result.success is True
    assert result.resolution == ConflictResolution.KEEP_BOTH
    assert result.new_skill_id == "code-reviewer"
    assert result.new_skill_name == "Code Reviewer"
    # New skill added to composition
    assert "code-reviewer" in result.resulting_skill_ids
    assert "code-writer" in result.resulting_skill_ids
    assert "rapid-prototyper" in result.resulting_skill_ids
    assert result.removed_skill_ids == []
    assert "kept both" in result.message.lower()
    assert result.reason == "Intentional combination"


@pytest.mark.asyncio
async def test_resolve_conflict_remove_existing(registry_with_conflicts, composition_service):
    """Test resolving a conflict by removing the conflicting skill."""
    from models import ConflictResolution

    result = composition_service.resolve_conflict(
        new_skill_id="code-reviewer",
        existing_skill_ids=["code-writer", "rapid-prototyper"],
        conflicting_skill_ids=["rapid-prototyper"],
        resolution=ConflictResolution.REMOVE_EXISTING,
        reason="Prefer thorough review"
    )

    assert result.success is True
    assert result.resolution == ConflictResolution.REMOVE_EXISTING
    assert result.new_skill_id == "code-reviewer"
    assert result.new_skill_name == "Code Reviewer"
    # Conflicting skill removed, new skill added
    assert "code-reviewer" in result.resulting_skill_ids
    assert "code-writer" in result.resulting_skill_ids
    assert "rapid-prototyper" not in result.resulting_skill_ids
    assert result.removed_skill_ids == ["rapid-prototyper"]
    assert "removed" in result.message.lower()
    assert result.reason == "Prefer thorough review"


@pytest.mark.asyncio
async def test_resolve_conflict_remove_multiple_existing(registry_with_conflicts, composition_service):
    """Test removing multiple conflicting skills."""
    from models import ConflictResolution

    result = composition_service.resolve_conflict(
        new_skill_id="code-reviewer",
        existing_skill_ids=["code-writer", "rapid-prototyper", "code-writer"],
        conflicting_skill_ids=["rapid-prototyper", "code-writer"],
        resolution=ConflictResolution.REMOVE_EXISTING,
        reason="Start fresh"
    )

    assert result.success is True
    assert result.resolution == ConflictResolution.REMOVE_EXISTING
    # Both conflicting skills removed
    assert "rapid-prototyper" in result.removed_skill_ids
    assert "code-writer" in result.removed_skill_ids
    # Only new skill remains
    assert result.resulting_skill_ids == ["code-reviewer"]


@pytest.mark.asyncio
async def test_resolve_conflict_nonexistent_skill(registry_with_conflicts, composition_service):
    """Test resolving conflict with a nonexistent new skill."""
    from models import ConflictResolution

    result = composition_service.resolve_conflict(
        new_skill_id="nonexistent-skill",
        existing_skill_ids=["code-writer"],
        conflicting_skill_ids=[],
        resolution=ConflictResolution.KEEP_BOTH
    )

    assert result.success is False
    assert "not found" in result.message.lower()
    # Existing composition unchanged
    assert result.resulting_skill_ids == ["code-writer"]


@pytest.mark.asyncio
async def test_resolve_conflict_no_reason(registry_with_conflicts, composition_service):
    """Test resolving conflict without providing a reason."""
    from models import ConflictResolution

    result = composition_service.resolve_conflict(
        new_skill_id="code-reviewer",
        existing_skill_ids=["code-writer"],
        conflicting_skill_ids=[],
        resolution=ConflictResolution.KEEP_BOTH
        # No reason provided
    )

    assert result.success is True
    assert result.reason is None


@pytest.mark.asyncio
async def test_resolve_conflict_keep_both_no_duplicate(registry_with_conflicts, composition_service):
    """Test that KEEP_BOTH doesn't add duplicate if skill already in composition."""
    from models import ConflictResolution

    result = composition_service.resolve_conflict(
        new_skill_id="code-writer",
        existing_skill_ids=["code-writer", "rapid-prototyper"],
        conflicting_skill_ids=[],
        resolution=ConflictResolution.KEEP_BOTH
    )

    assert result.success is True
    # Should not duplicate code-writer
    assert result.resulting_skill_ids.count("code-writer") == 1


@pytest.mark.asyncio
async def test_resolve_conflict_timestamp_set(registry_with_conflicts, composition_service):
    """Test that resolution result includes timestamp."""
    from models import ConflictResolution
    from datetime import datetime, timezone

    before = datetime.now(timezone.utc)
    result = composition_service.resolve_conflict(
        new_skill_id="code-reviewer",
        existing_skill_ids=["code-writer"],
        conflicting_skill_ids=[],
        resolution=ConflictResolution.KEEP_BOTH
    )
    after = datetime.now(timezone.utc)

    assert result.timestamp is not None
    assert before <= result.timestamp <= after


@pytest.mark.asyncio
async def test_resolve_conflict_audit_logging_cancel(registry_with_conflicts, composition_service, caplog):
    """Test that CANCEL resolution is audit logged."""
    from models import ConflictResolution
    import logging

    with caplog.at_level(logging.INFO):
        composition_service.resolve_conflict(
            new_skill_id="code-reviewer",
            existing_skill_ids=["code-writer"],
            conflicting_skill_ids=[],
            resolution=ConflictResolution.CANCEL,
            reason="Test reason"
        )

    assert "CANCEL" in caplog.text
    assert "code-reviewer" in caplog.text or "Code Reviewer" in caplog.text


@pytest.mark.asyncio
async def test_resolve_conflict_audit_logging_keep_both(registry_with_conflicts, composition_service, caplog):
    """Test that KEEP_BOTH resolution is audit logged with conflicts."""
    from models import ConflictResolution
    import logging

    with caplog.at_level(logging.INFO):
        composition_service.resolve_conflict(
            new_skill_id="code-reviewer",
            existing_skill_ids=["code-writer", "rapid-prototyper"],
            conflicting_skill_ids=["rapid-prototyper"],
            resolution=ConflictResolution.KEEP_BOTH,
            reason="Intentional"
        )

    assert "KEEP_BOTH" in caplog.text
    assert "rapid-prototyper" in caplog.text


@pytest.mark.asyncio
async def test_resolve_conflict_audit_logging_remove_existing(registry_with_conflicts, composition_service, caplog):
    """Test that REMOVE_EXISTING resolution is audit logged."""
    from models import ConflictResolution
    import logging

    with caplog.at_level(logging.INFO):
        composition_service.resolve_conflict(
            new_skill_id="code-reviewer",
            existing_skill_ids=["code-writer", "rapid-prototyper"],
            conflicting_skill_ids=["rapid-prototyper"],
            resolution=ConflictResolution.REMOVE_EXISTING,
            reason="Prefer review"
        )

    assert "REMOVE_EXISTING" in caplog.text
    assert "rapid-prototyper" in caplog.text


# =============================================================================
# compose_preview() Tests
# =============================================================================


@pytest.mark.asyncio
async def test_compose_preview_returns_preview_response(registry, composition_service):
    """Test that compose_preview returns a ComposePreviewResponse with preview=True."""
    from models import TaskAssignment, ComposeRequest, ComposePreviewResponse

    task = TaskAssignment(
        task_id="preview-test-1",
        description="Test task for preview",
        required_capabilities=["coding"],
    )
    request = ComposeRequest(task=task)

    result = await composition_service.compose_preview(request)

    assert isinstance(result, ComposePreviewResponse)
    assert result.preview is True


@pytest.mark.asyncio
async def test_compose_preview_includes_merged_instructions(registry, composition_service):
    """Test that compose_preview returns merged instructions."""
    from models import TaskAssignment, ComposeRequest

    task = TaskAssignment(
        task_id="preview-test-2",
        description="Test task for preview",
        required_capabilities=["coding"],
    )
    request = ComposeRequest(task=task)

    result = await composition_service.compose_preview(request)

    assert result.merged_instructions is not None
    assert len(result.merged_instructions) > 0
    assert "Code Writer" in result.merged_instructions


@pytest.mark.asyncio
async def test_compose_preview_includes_tools(registry, composition_service):
    """Test that compose_preview returns aggregated tools."""
    from models import TaskAssignment, ComposeRequest

    task = TaskAssignment(
        task_id="preview-test-3",
        description="Test automation task",
        required_capabilities=["testing"],
    )
    request = ComposeRequest(task=task)

    result = await composition_service.compose_preview(request)

    assert result.tools is not None
    assert isinstance(result.tools, list)
    # test-automator has run_tests and test_coverage specialized tools
    assert "run_tests" in result.tools
    assert "test_coverage" in result.tools


@pytest.mark.asyncio
async def test_compose_preview_includes_skills(registry, composition_service):
    """Test that compose_preview returns the selected skills."""
    from models import TaskAssignment, ComposeRequest

    task = TaskAssignment(
        task_id="preview-test-4",
        description="Test task",
        required_capabilities=["coding"],
    )
    request = ComposeRequest(task=task, skill_ids=["code-writer"])

    result = await composition_service.compose_preview(request)

    assert result.skills is not None
    assert len(result.skills) >= 1
    assert result.skills[0].id == "code-writer"


@pytest.mark.asyncio
async def test_compose_preview_includes_conflict_warnings(registry, composition_service):
    """Test that compose_preview returns conflict check results."""
    from models import TaskAssignment, ComposeRequest, ConflictCheckResponse

    task = TaskAssignment(
        task_id="preview-test-5",
        description="Test task",
        required_capabilities=["coding"],
    )
    request = ComposeRequest(task=task, skill_ids=["code-writer"])

    result = await composition_service.compose_preview(request)

    assert result.conflict_warnings is not None
    assert isinstance(result.conflict_warnings, ConflictCheckResponse)
    # No conflicts expected for single skill
    assert result.conflict_warnings.has_conflicts is False


@pytest.mark.asyncio
async def test_compose_preview_does_not_persist_agent(registry, composition_service):
    """Test that compose_preview does not store agent in cache."""
    from models import TaskAssignment, ComposeRequest

    task = TaskAssignment(
        task_id="preview-test-6",
        description="Test task",
        required_capabilities=["coding"],
    )
    request = ComposeRequest(task=task, skill_ids=["code-writer"])

    # Get cache stats before
    stats_before = composition_service.get_cache_stats()
    initial_size = stats_before.size

    # Generate preview
    await composition_service.compose_preview(request)

    # Get cache stats after
    stats_after = composition_service.get_cache_stats()

    # Cache size should not have increased
    assert stats_after.size == initial_size


@pytest.mark.asyncio
async def test_compose_preview_does_not_affect_cache_stats(registry, composition_service):
    """Test that compose_preview does not increment cache hits/misses."""
    from models import TaskAssignment, ComposeRequest

    task = TaskAssignment(
        task_id="preview-test-7",
        description="Test task",
        required_capabilities=["coding"],
    )
    request = ComposeRequest(task=task)

    # Get cache stats before
    stats_before = composition_service.get_cache_stats()
    hits_before = stats_before.hits
    misses_before = stats_before.misses

    # Generate preview
    await composition_service.compose_preview(request)

    # Get cache stats after
    stats_after = composition_service.get_cache_stats()

    # Hits and misses should not have changed
    assert stats_after.hits == hits_before
    assert stats_after.misses == misses_before


@pytest.mark.asyncio
async def test_compose_preview_raises_for_no_skills(registry, composition_service):
    """Test that compose_preview raises ValueError when no skills available."""
    from models import TaskAssignment, ComposeRequest

    task = TaskAssignment(
        task_id="preview-test-8",
        description="Test task",
        required_capabilities=["coding"],
    )
    # Request a non-existent skill
    request = ComposeRequest(task=task, skill_ids=["nonexistent-skill"])

    with pytest.raises(ValueError) as exc_info:
        await composition_service.compose_preview(request)

    assert "No skills available" in str(exc_info.value)


@pytest.mark.asyncio
async def test_compose_preview_resolves_dependencies(registry_with_deps, composition_service):
    """Test that compose_preview includes resolved dependencies."""
    from models import TaskAssignment, ComposeRequest

    task = TaskAssignment(
        task_id="preview-test-9",
        description="Deployment task",
        required_capabilities=[],
    )
    # prod-deployment depends on code-analysis
    request = ComposeRequest(task=task, skill_ids=["prod-deployment"])

    result = await composition_service.compose_preview(request)

    skill_ids = [s.id for s in result.skills]
    assert "prod-deployment" in skill_ids
    assert "code-analysis" in skill_ids


@pytest.mark.asyncio
async def test_compose_preview_with_conflicts_shows_warnings(registry_with_conflicts, composition_service):
    """Test that compose_preview shows conflict warnings when skills conflict."""
    from models import TaskAssignment, ComposeRequest

    task = TaskAssignment(
        task_id="preview-test-10",
        description="Test task",
        required_capabilities=[],
    )
    # rapid-prototyper conflicts with code-reviewer
    request = ComposeRequest(task=task, skill_ids=["rapid-prototyper", "code-reviewer"])

    result = await composition_service.compose_preview(request)

    assert result.conflict_warnings.has_conflicts is True
    assert len(result.conflict_warnings.conflicts) > 0


@pytest.mark.asyncio
async def test_compose_preview_with_context(registry, composition_service, sample_context):
    """Test that compose_preview includes project context in merged instructions."""
    from models import TaskAssignment, ComposeRequest

    task = TaskAssignment(
        task_id="preview-test-11",
        description="Test task",
        required_capabilities=["coding"],
    )
    request = ComposeRequest(task=task, skill_ids=["code-writer"], context=sample_context)

    result = await composition_service.compose_preview(request)

    # Context should be included in merged instructions
    assert "Project Context" in result.merged_instructions
    assert "FastAPI" in result.merged_instructions  # from tech_stack


@pytest.mark.asyncio
async def test_compose_preview_vs_compose_same_output(registry, composition_service):
    """Test that compose_preview produces same merged_instructions and tools as compose."""
    from models import TaskAssignment, ComposeRequest

    task = TaskAssignment(
        task_id="preview-vs-compose",
        description="Test task",
        required_capabilities=["coding"],
    )
    request = ComposeRequest(task=task, skill_ids=["code-writer"])

    # Get preview
    preview_result = await composition_service.compose_preview(request)

    # Get actual composition
    compose_result = await composition_service.compose(request)

    # Compare outputs (excluding agent-specific fields)
    assert preview_result.merged_instructions == compose_result.merged_instructions
    assert preview_result.tools == compose_result.tools
    assert len(preview_result.skills) == len(compose_result.skills)
    assert preview_result.skills[0].id == compose_result.skills[0].id
