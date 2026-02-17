"""Tests for the catalog API endpoint."""

import pytest
from pathlib import Path

from models import CatalogSkillEntry, CatalogPersonaEntry, CatalogResponse
from skill_registry import SkillRegistry
from persona_registry import PersonaRegistry


@pytest.fixture
def temp_skills_path(tmp_path):
    """Create a temporary skills directory."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "system").mkdir()
    (skills_dir / "user").mkdir()

    # Create a sample system skill with specialized tools
    system_skill = skills_dir / "system" / "code-writer.yaml"
    system_skill.write_text("""id: code-writer
name: Code Writer
description: Implements features and writes production-quality code
version: "1.0.0"
author: system

instructions: |
  # Code Writer

  You implement features and write code.

specialized_tools:
  - read
  - write
  - bash

tags:
  - coding
  - implementation

constraints:
  - Do not modify unrelated code
""")

    # Create another skill
    test_skill = skills_dir / "system" / "test-automator.yaml"
    test_skill.write_text("""id: test-automator
name: Test Automator
description: Writes and runs tests
version: "1.0.0"
author: system

instructions: |
  # Test Automator

  You write and run tests.

specialized_tools:
  - pytest_run

tags:
  - testing
  - quality

constraints:
  - Focus on test coverage
""")

    return str(skills_dir)


@pytest.fixture
def temp_personas_path(tmp_path):
    """Create a temporary personas directory."""
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "system").mkdir()
    (personas_dir / "user").mkdir()

    # Create a sample persona that references skills
    system_persona = personas_dir / "system" / "fullstack-developer.yaml"
    system_persona.write_text("""id: fullstack-developer
name: Full-Stack Developer
description: Complete development capability
version: "1.0.0"
author: system

instructions: |
  # Full-Stack Developer

  You are a full-stack developer.

references_skills:
  - code-writer
  - test-automator

tags:
  - development
  - full-stack

constraints:
  - Follow project conventions
""")

    return str(personas_dir)


@pytest.fixture
async def skill_registry(temp_skills_path):
    """Create a skill registry for testing."""
    reg = SkillRegistry(skills_path=temp_skills_path)
    await reg.initialize()
    return reg


@pytest.fixture
async def persona_registry(temp_personas_path, skill_registry):
    """Create a persona registry for testing."""
    reg = PersonaRegistry(personas_path=temp_personas_path)
    reg.set_skill_registry(skill_registry)
    await reg.initialize()
    return reg


@pytest.mark.asyncio
async def test_catalog_skill_entry_model():
    """Test CatalogSkillEntry model creation."""
    entry = CatalogSkillEntry(
        id="test-skill",
        name="Test Skill",
        description="A test skill",
        tags=["testing"],
        grants_tools=["read", "write"]
    )

    assert entry.id == "test-skill"
    assert entry.name == "Test Skill"
    assert entry.description == "A test skill"
    assert "testing" in entry.tags
    assert "read" in entry.grants_tools
    assert "write" in entry.grants_tools


@pytest.mark.asyncio
async def test_catalog_persona_entry_model():
    """Test CatalogPersonaEntry model creation."""
    entry = CatalogPersonaEntry(
        id="test-persona",
        name="Test Persona",
        description="A test persona",
        skills=["code-writer", "test-automator"],
        grants_tools=["read", "write", "pytest_run"]
    )

    assert entry.id == "test-persona"
    assert entry.name == "Test Persona"
    assert entry.description == "A test persona"
    assert "code-writer" in entry.skills
    assert "test-automator" in entry.skills
    assert "read" in entry.grants_tools


@pytest.mark.asyncio
async def test_catalog_response_model():
    """Test CatalogResponse model creation."""
    skill_entry = CatalogSkillEntry(
        id="code-writer",
        name="Code Writer",
        description="Writes code",
        tags=["coding"],
        grants_tools=["read", "write"]
    )

    persona_entry = CatalogPersonaEntry(
        id="fullstack-developer",
        name="Full-Stack Developer",
        description="Full-stack capability",
        skills=["code-writer"],
        grants_tools=["read", "write"]
    )

    response = CatalogResponse(
        skills=[skill_entry],
        personas=[persona_entry]
    )

    assert len(response.skills) == 1
    assert len(response.personas) == 1
    assert response.skills[0].id == "code-writer"
    assert response.personas[0].id == "fullstack-developer"


@pytest.mark.asyncio
async def test_catalog_builds_skill_entries(skill_registry):
    """Test that catalog correctly builds skill entries from registry."""
    skills = skill_registry.list_skills()

    # Build catalog entries like the API does
    catalog_skills = [
        CatalogSkillEntry(
            id=s.id,
            name=s.name,
            description=s.description,
            tags=s.tags,
            grants_tools=s.specialized_tools
        )
        for s in skills
    ]

    assert len(catalog_skills) == 2

    # Find code-writer entry
    code_writer = next((s for s in catalog_skills if s.id == "code-writer"), None)
    assert code_writer is not None
    assert code_writer.name == "Code Writer"
    assert "coding" in code_writer.tags
    assert "read" in code_writer.grants_tools
    assert "write" in code_writer.grants_tools
    assert "bash" in code_writer.grants_tools


@pytest.mark.asyncio
async def test_catalog_builds_persona_entries_with_aggregated_tools(skill_registry, persona_registry):
    """Test that catalog correctly aggregates tools from persona's skills."""
    personas = persona_registry.list_personas()

    # Build catalog entries like the API does
    catalog_personas = []
    for p in personas:
        aggregated_tools = set()
        for skill_id in p.references_skills:
            skill = skill_registry.get_skill(skill_id)
            if skill:
                aggregated_tools.update(skill.specialized_tools)

        catalog_personas.append(
            CatalogPersonaEntry(
                id=p.id,
                name=p.name,
                description=p.description,
                skills=p.references_skills,
                grants_tools=sorted(list(aggregated_tools))
            )
        )

    assert len(catalog_personas) == 1

    fullstack = catalog_personas[0]
    assert fullstack.id == "fullstack-developer"
    assert fullstack.name == "Full-Stack Developer"
    assert "code-writer" in fullstack.skills
    assert "test-automator" in fullstack.skills

    # Should have aggregated tools from both skills
    assert "read" in fullstack.grants_tools
    assert "write" in fullstack.grants_tools
    assert "bash" in fullstack.grants_tools
    assert "pytest_run" in fullstack.grants_tools


@pytest.mark.asyncio
async def test_catalog_persona_handles_missing_skills(skill_registry, persona_registry):
    """Test that catalog handles personas referencing non-existent skills."""
    # Create a persona with a missing skill reference
    from models import PersonaCreateRequest

    request = PersonaCreateRequest(
        id="broken-persona",
        name="Broken Persona",
        description="References non-existent skill",
        instructions="Test",
        references_skills=["code-writer", "nonexistent-skill"]
    )

    await persona_registry.create_persona(request, author="user")

    # Build catalog entries
    personas = persona_registry.list_personas()
    broken = next((p for p in personas if p.id == "broken-persona"), None)
    assert broken is not None

    # Aggregate tools - should only get tools from existing skills
    aggregated_tools = set()
    for skill_id in broken.references_skills:
        skill = skill_registry.get_skill(skill_id)
        if skill:
            aggregated_tools.update(skill.specialized_tools)

    # Should have tools from code-writer but not from nonexistent-skill
    assert "read" in aggregated_tools
    assert "write" in aggregated_tools
    assert len(aggregated_tools) == 3  # read, write, bash from code-writer


@pytest.mark.asyncio
async def test_catalog_response_is_lightweight():
    """Test that catalog response doesn't include full instructions."""
    skill_entry = CatalogSkillEntry(
        id="test",
        name="Test",
        description="Test skill",
        tags=[],
        grants_tools=[]
    )

    # CatalogSkillEntry should not have an 'instructions' field
    assert not hasattr(skill_entry, 'instructions') or 'instructions' not in skill_entry.model_fields

    persona_entry = CatalogPersonaEntry(
        id="test",
        name="Test",
        description="Test persona",
        skills=[],
        grants_tools=[]
    )

    # CatalogPersonaEntry should not have an 'instructions' field
    assert not hasattr(persona_entry, 'instructions') or 'instructions' not in persona_entry.model_fields
