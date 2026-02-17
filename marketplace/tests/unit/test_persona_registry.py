"""Tests for persona registry service."""

import pytest
from pathlib import Path
from datetime import datetime

from models import Persona, PersonaCreateRequest, PersonaUpdateRequest
from persona_registry import PersonaRegistry


@pytest.fixture
def temp_personas_path(tmp_path):
    """Create a temporary personas directory."""
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "system").mkdir()
    (personas_dir / "user").mkdir()

    # Create a sample system persona
    system_persona = personas_dir / "system" / "test-persona.yaml"
    system_persona.write_text("""id: test-persona
name: Test Persona
description: A test persona for unit tests
version: "1.0.0"
author: system

instructions: |
  # Test Persona

  You are a test persona used in unit tests.

references_skills:
  - skill-a
  - skill-b

tags:
  - testing
  - automation

constraints:
  - Do not modify production code
""")

    # Create a sample user persona
    user_persona = personas_dir / "user" / "custom-persona.yaml"
    user_persona.write_text("""id: custom-persona
name: Custom Persona
description: A user-created persona
version: "1.0.0"
author: user:johndoe

instructions: |
  # Custom Persona

  Custom instructions here.

references_skills:
  - skill-c

tags:
  - custom
  - user-created

constraints:
  - Follow user guidelines
""")

    return str(personas_dir)


@pytest.fixture
async def registry(temp_personas_path):
    """Create a registry for testing."""
    reg = PersonaRegistry(personas_path=temp_personas_path)
    await reg.initialize()
    return reg


@pytest.mark.asyncio
async def test_initialize_loads_personas(temp_personas_path):
    """Test that initialize loads personas from disk."""
    registry = PersonaRegistry(personas_path=temp_personas_path)
    await registry.initialize()

    assert registry._initialized is True
    assert len(registry.personas) == 2
    assert "test-persona" in registry.personas
    assert "custom-persona" in registry.personas


@pytest.mark.asyncio
async def test_list_personas_no_filters(registry):
    """Test listing all personas without filters."""
    personas = registry.list_personas()

    assert len(personas) == 2
    persona_ids = [p.id for p in personas]
    assert "test-persona" in persona_ids
    assert "custom-persona" in persona_ids


@pytest.mark.asyncio
async def test_list_personas_with_tag_filter(registry):
    """Test listing personas filtered by tags."""
    personas = registry.list_personas(tags=["testing"])

    assert len(personas) == 1
    assert personas[0].id == "test-persona"

    personas = registry.list_personas(tags=["custom"])
    assert len(personas) == 1
    assert personas[0].id == "custom-persona"


@pytest.mark.asyncio
async def test_list_personas_with_author_filter(registry):
    """Test listing personas filtered by author."""
    personas = registry.list_personas(author="system")

    assert len(personas) == 1
    assert personas[0].id == "test-persona"
    assert personas[0].author == "system"

    personas = registry.list_personas(author="user")
    assert len(personas) == 1
    assert personas[0].id == "custom-persona"
    assert personas[0].author.startswith("user:")


@pytest.mark.asyncio
async def test_get_persona_existing(registry):
    """Test getting an existing persona by ID."""
    persona = registry.get_persona("test-persona")

    assert persona is not None
    assert persona.id == "test-persona"
    assert persona.name == "Test Persona"
    assert persona.author == "system"
    assert "skill-a" in persona.references_skills
    assert "testing" in persona.tags


@pytest.mark.asyncio
async def test_get_persona_nonexistent(registry):
    """Test getting a nonexistent persona returns None."""
    persona = registry.get_persona("nonexistent")
    assert persona is None


@pytest.mark.asyncio
async def test_create_persona(registry, temp_personas_path):
    """Test creating a new persona."""
    request = PersonaCreateRequest(
        id="new-persona",
        name="New Persona",
        description="A newly created persona",
        instructions="# New Persona\n\nInstructions here.",
        references_skills=["skill-x"],
        tags=["new", "test"],
        constraints=["Be careful"],
        version="1.0.0"
    )

    persona = await registry.create_persona(request, author="testuser")

    assert persona.id == "new-persona"
    assert persona.name == "New Persona"
    assert persona.author == "user:testuser"
    assert "skill-x" in persona.references_skills
    assert "new" in persona.tags

    # Verify it was added to registry
    assert "new-persona" in registry.personas

    # Verify it was saved to disk
    file_path = Path(temp_personas_path) / "user" / "new-persona.yaml"
    assert file_path.exists()


@pytest.mark.asyncio
async def test_create_duplicate_persona_raises_error(registry):
    """Test creating a duplicate persona raises ValueError."""
    request = PersonaCreateRequest(
        id="test-persona",  # Already exists
        name="Duplicate",
        description="Should fail",
        instructions="Test"
    )

    with pytest.raises(ValueError, match="already exists"):
        await registry.create_persona(request)


@pytest.mark.asyncio
async def test_update_persona(registry, temp_personas_path):
    """Test updating an existing persona."""
    request = PersonaUpdateRequest(
        name="Updated Name",
        description="Updated description",
        tags=["updated", "modified"]
    )

    persona = await registry.update_persona("test-persona", request)

    assert persona is not None
    assert persona.name == "Updated Name"
    assert persona.description == "Updated description"
    assert "updated" in persona.tags

    # Verify update timestamp changed
    assert persona.updated_at > persona.created_at

    # Verify it was saved to disk
    file_path = Path(temp_personas_path) / "system" / "test-persona.yaml"
    assert file_path.exists()


@pytest.mark.asyncio
async def test_update_nonexistent_persona(registry):
    """Test updating a nonexistent persona returns None."""
    request = PersonaUpdateRequest(name="Should fail")
    persona = await registry.update_persona("nonexistent", request)
    assert persona is None


@pytest.mark.asyncio
async def test_delete_user_persona(registry, temp_personas_path):
    """Test deleting a user persona."""
    result = await registry.delete_persona("custom-persona")

    assert result is True
    assert "custom-persona" not in registry.personas

    # Verify file was deleted
    file_path = Path(temp_personas_path) / "user" / "custom-persona.yaml"
    assert not file_path.exists()


@pytest.mark.asyncio
async def test_delete_system_persona_raises_error(registry):
    """Test deleting a system persona raises ValueError."""
    with pytest.raises(ValueError, match="Cannot delete system personas"):
        await registry.delete_persona("test-persona")

    # Persona should still exist
    assert "test-persona" in registry.personas


@pytest.mark.asyncio
async def test_delete_nonexistent_persona(registry):
    """Test deleting a nonexistent persona returns False."""
    result = await registry.delete_persona("nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_get_stats(registry):
    """Test getting registry statistics."""
    stats = registry.get_stats()

    assert stats["total_personas"] == 2
    assert stats["by_author"]["system"] == 1
    assert stats["by_author"]["user"] == 1


# ============ Merged Instructions Tests ============


@pytest.mark.asyncio
async def test_create_persona_generates_merged_instructions(registry, temp_personas_path):
    """Test that creating a persona generates merged_instructions."""
    request = PersonaCreateRequest(
        id="merge-test-persona",
        name="Merge Test Persona",
        description="Tests merged instructions",
        instructions="# Persona Instructions\n\nBase persona instructions here.",
        references_skills=["skill-a", "skill-b"],
        tags=["test"],
        constraints=["Persona constraint"]
    )

    persona = await registry.create_persona(request, author="testuser")

    assert persona.merged_instructions != ""
    assert "# Persona: Merge Test Persona" in persona.merged_instructions
    assert "## Persona Instructions" in persona.merged_instructions
    assert "Base persona instructions here." in persona.merged_instructions


@pytest.mark.asyncio
async def test_generate_merged_instructions_format(registry):
    """Test the format of generated merged instructions."""
    from models import Skill

    # Create mock skills
    skill1 = Skill(
        id="skill-1",
        name="Skill One",
        description="First skill",
        instructions="# Skill One\n\nDo skill one things.",
        constraints=["Skill one constraint"]
    )
    skill2 = Skill(
        id="skill-2",
        name="Skill Two",
        description="Second skill",
        instructions="# Skill Two\n\nDo skill two things.",
        constraints=["Skill two constraint"]
    )

    merged = registry._generate_merged_instructions(
        persona_name="Test Persona",
        persona_instructions="Base persona instructions.",
        skills=[skill1, skill2],
        constraints=["Persona constraint"]
    )

    # Check structure
    assert "# Persona: Test Persona" in merged
    assert "## Persona Instructions" in merged
    assert "Base persona instructions." in merged
    assert "## Skill Instructions" in merged
    assert "### Skill One" in merged
    assert "### Skill Two" in merged
    assert "## Constraints" in merged
    assert "- Persona constraint" in merged
    assert "- Skill one constraint" in merged
    assert "- Skill two constraint" in merged


@pytest.mark.asyncio
async def test_expand_persona_returns_expanded_details(registry):
    """Test expanding a persona returns skill details."""
    expanded = registry.expand_persona("test-persona")

    assert expanded is not None
    assert expanded.persona.id == "test-persona"
    # Skills are missing since no skill registry is set
    assert len(expanded.missing_skills) == 2
    assert "skill-a" in expanded.missing_skills
    assert "skill-b" in expanded.missing_skills


@pytest.mark.asyncio
async def test_expand_nonexistent_persona(registry):
    """Test expanding a nonexistent persona returns None."""
    expanded = registry.expand_persona("nonexistent")
    assert expanded is None


@pytest.mark.asyncio
async def test_set_skill_registry(registry):
    """Test setting the skill registry."""
    from unittest.mock import Mock

    mock_skill_registry = Mock()
    registry.set_skill_registry(mock_skill_registry)

    assert registry._skill_registry is mock_skill_registry


@pytest.mark.asyncio
async def test_get_skills_with_skill_registry(registry):
    """Test getting skills when skill registry is set."""
    from unittest.mock import Mock
    from models import Skill

    # Create a mock skill
    mock_skill = Skill(
        id="skill-a",
        name="Skill A",
        description="A skill",
        instructions="Do skill A things."
    )

    mock_skill_registry = Mock()
    mock_skill_registry.get_skill.side_effect = lambda sid: mock_skill if sid == "skill-a" else None

    registry.set_skill_registry(mock_skill_registry)

    found, missing = registry._get_skills_for_persona(["skill-a", "skill-b"])

    assert len(found) == 1
    assert found[0].id == "skill-a"
    assert len(missing) == 1
    assert "skill-b" in missing
