"""Tests for the characterizer skill definition.

Verifies the characterizer.yaml skill loads correctly, has required fields,
and is discoverable via the skill registry.
"""

import pytest
from pathlib import Path

from models import Skill
from skill_registry import SkillRegistry


@pytest.fixture
def characterizer_skills_path(tmp_path):
    """Create a skills directory with the characterizer skill from the real YAML."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "system").mkdir()
    (skills_dir / "user").mkdir()

    # Copy the real characterizer skill
    real_skill = Path(__file__).resolve().parents[2] / "skills" / "system" / "characterizer.yaml"
    target = skills_dir / "system" / "characterizer.yaml"
    target.write_text(real_skill.read_text())

    return str(skills_dir)


@pytest.fixture
async def characterizer_registry(characterizer_skills_path):
    """Create a registry with the characterizer skill loaded."""
    reg = SkillRegistry(skills_path=characterizer_skills_path)
    await reg.initialize()
    return reg


# =============================================================================
# Skill Loading Tests
# =============================================================================


@pytest.mark.asyncio
async def test_characterizer_skill_loads(characterizer_registry):
    """Test that the characterizer skill loads from YAML without errors."""
    skill = characterizer_registry.get_skill("characterizer")

    assert skill is not None
    assert skill.id == "characterizer"
    assert skill.name == "Work Item Characterizer"
    assert skill.author == "system"
    assert skill.version == "1.0.0"


@pytest.mark.asyncio
async def test_characterizer_skill_has_instructions(characterizer_registry):
    """Test that the characterizer skill has meaningful instructions."""
    skill = characterizer_registry.get_skill("characterizer")

    assert len(skill.instructions) > 500


@pytest.mark.asyncio
async def test_characterizer_instructions_cover_frame_1(characterizer_registry):
    """Test that instructions include Frame 1 (in isolation) evaluation."""
    skill = characterizer_registry.get_skill("characterizer")

    assert "Frame 1" in skill.instructions
    assert "In Isolation" in skill.instructions
    assert "work_type" in skill.instructions
    assert "lifecycle_stage" in skill.instructions
    assert "technical_domains" in skill.instructions


@pytest.mark.asyncio
async def test_characterizer_instructions_cover_frame_2(characterizer_registry):
    """Test that instructions include Frame 2 (in context) evaluation."""
    skill = characterizer_registry.get_skill("characterizer")

    assert "Frame 2" in skill.instructions
    assert "In Project Context" in skill.instructions
    assert "contextual_role" in skill.instructions
    assert "foundational" in skill.instructions
    assert "incremental" in skill.instructions
    assert "enabling" in skill.instructions
    assert "blocking" in skill.instructions


@pytest.mark.asyncio
async def test_characterizer_instructions_cover_ontology_values(characterizer_registry):
    """Test that instructions document all valid ontology enum values."""
    skill = characterizer_registry.get_skill("characterizer")

    # Work types
    for wt in ["feature", "bug_fix", "refactor", "test", "documentation", "infrastructure", "integration"]:
        assert wt in skill.instructions, f"Missing work_type: {wt}"

    # Lifecycle stages
    for ls in ["design", "build", "test", "validate", "deploy"]:
        assert ls in skill.instructions, f"Missing lifecycle_stage: {ls}"

    # Technical domains
    for td in ["frontend", "backend", "data", "api", "security", "devops", "testing", "documentation"]:
        assert td in skill.instructions, f"Missing technical_domain: {td}"


@pytest.mark.asyncio
async def test_characterizer_instructions_cover_meaning_assessment(characterizer_registry):
    """Test that instructions include meaning assessment guidance."""
    skill = characterizer_registry.get_skill("characterizer")

    assert "business_summary" in skill.instructions
    assert "technical_summary" in skill.instructions
    assert "contextual_summary" in skill.instructions


@pytest.mark.asyncio
async def test_characterizer_instructions_cover_dependency_discovery(characterizer_registry):
    """Test that instructions include dependency discovery logic."""
    skill = characterizer_registry.get_skill("characterizer")

    # Dependency relations
    for rel in ["blocks", "enables", "related_to", "extends", "conflicts_with"]:
        assert rel in skill.instructions, f"Missing dependency relation: {rel}"

    # Dependency types
    assert "structural" in skill.instructions
    assert "contextual" in skill.instructions


@pytest.mark.asyncio
async def test_characterizer_instructions_reference_mcp_tool(characterizer_registry):
    """Test that instructions reference the submission MCP tool."""
    skill = characterizer_registry.get_skill("characterizer")

    assert "claudevn_submit_characterization" in skill.instructions


# =============================================================================
# Tag and Searchability Tests
# =============================================================================


@pytest.mark.asyncio
async def test_characterizer_skill_has_characterization_tag(characterizer_registry):
    """Test that the characterizer skill has the characterization tag."""
    skill = characterizer_registry.get_skill("characterizer")

    assert "characterization" in skill.tags


@pytest.mark.asyncio
async def test_characterizer_skill_has_ontology_tag(characterizer_registry):
    """Test that the characterizer skill has the ontology tag."""
    skill = characterizer_registry.get_skill("characterizer")

    assert "ontology" in skill.tags


@pytest.mark.asyncio
async def test_characterizer_skill_searchable_by_characterization(characterizer_registry):
    """Test that the characterizer skill is found by 'characterization' capability."""
    skills = characterizer_registry.search_by_capabilities(["characterization"])

    assert len(skills) == 1
    assert skills[0].id == "characterizer"


@pytest.mark.asyncio
async def test_characterizer_skill_searchable_by_ontology(characterizer_registry):
    """Test that the characterizer skill is found by 'ontology' capability."""
    skills = characterizer_registry.search_by_capabilities(["ontology"])

    assert len(skills) == 1
    assert skills[0].id == "characterizer"


# =============================================================================
# Constraints Tests
# =============================================================================


@pytest.mark.asyncio
async def test_characterizer_skill_has_constraints(characterizer_registry):
    """Test that the characterizer skill has constraints defined."""
    skill = characterizer_registry.get_skill("characterizer")

    assert len(skill.constraints) > 0


@pytest.mark.asyncio
async def test_characterizer_skill_no_code_constraint(characterizer_registry):
    """Test that constraints prevent code implementation."""
    skill = characterizer_registry.get_skill("characterizer")

    constraint_text = " ".join(skill.constraints).lower()
    assert "implement" in constraint_text or "code" in constraint_text


@pytest.mark.asyncio
async def test_characterizer_skill_no_specialized_tools(characterizer_registry):
    """Test that the characterizer skill has no specialized tools."""
    skill = characterizer_registry.get_skill("characterizer")

    assert skill.specialized_tools == []


@pytest.mark.asyncio
async def test_characterizer_skill_cannot_be_deleted(characterizer_registry):
    """Test that the characterizer (system skill) cannot be deleted."""
    with pytest.raises(ValueError, match="Cannot delete system skills"):
        await characterizer_registry.delete_skill("characterizer")

    assert characterizer_registry.get_skill("characterizer") is not None
