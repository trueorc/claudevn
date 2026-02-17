"""Tests for persona versioning functionality."""

import pytest
from datetime import datetime, timezone

from models import (
    Persona, PersonaVersion, PersonaVersionListResponse,
    PersonaCreateRequest, PersonaUpdateRequest
)
from persona_registry import PersonaRegistry, set_persona_registry


@pytest.fixture
def temp_personas_path(tmp_path):
    """Create a temporary personas directory."""
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "system").mkdir()
    (personas_dir / "user").mkdir()
    (personas_dir / "versions").mkdir()

    # Create a sample system persona
    system_persona = personas_dir / "system" / "test-persona.yaml"
    system_persona.write_text("""id: test-persona
name: Test Persona
description: A test persona for unit tests
version: "1.0.0"
author: system

instructions: |
  # Test Persona

  You are a test persona.

references_skills: []

tags:
  - testing

constraints:
  - Test constraint

merged_instructions: ""
""")

    return str(personas_dir)


@pytest.fixture
async def registry(temp_personas_path):
    """Create a registry for testing."""
    reg = PersonaRegistry(personas_path=temp_personas_path)
    await reg.initialize()
    set_persona_registry(reg)
    return reg


# =============================================================================
# PersonaVersion Model Tests
# =============================================================================


def test_persona_version_model_defaults():
    """Test PersonaVersion model with default values."""
    version = PersonaVersion(
        persona_id="test-persona",
        version="1.0.0",
        instructions="Test instructions"
    )

    assert version.persona_id == "test-persona"
    assert version.version == "1.0.0"
    assert version.instructions == "Test instructions"
    assert version.references_skills == []
    assert version.changelog is None
    assert version.created_at is not None


def test_persona_version_model_full():
    """Test PersonaVersion model with all fields."""
    now = datetime.now(timezone.utc)
    version = PersonaVersion(
        persona_id="test-persona",
        version="1.1.0",
        instructions="Updated instructions",
        references_skills=["skill-a", "skill-b"],
        changelog="Added new skills",
        created_at=now
    )

    assert version.references_skills == ["skill-a", "skill-b"]
    assert version.changelog == "Added new skills"
    assert version.created_at == now


def test_persona_version_list_response_model():
    """Test PersonaVersionListResponse model structure."""
    version = PersonaVersion(
        persona_id="test",
        version="1.0.0",
        instructions="Test instructions",
        references_skills=["skill1"],
        changelog="Initial",
        created_at=datetime.now(timezone.utc)
    )

    response = PersonaVersionListResponse(
        persona_id="test",
        versions=[version],
        total=1,
        current_version="1.0.0"
    )

    assert response.persona_id == "test"
    assert len(response.versions) == 1
    assert response.total == 1
    assert response.current_version == "1.0.0"


# =============================================================================
# PersonaRegistry Versioning Tests
# =============================================================================


@pytest.mark.asyncio
async def test_create_persona_adds_initial_version(registry, temp_personas_path):
    """Test that creating a persona adds an initial version entry."""
    request = PersonaCreateRequest(
        id="versioned-persona",
        name="Versioned Persona",
        description="A persona with version tracking",
        instructions="# Versioned Persona\n\nInstructions here.",
        references_skills=["code-writer"],
        version="1.0.0"
    )

    persona = await registry.create_persona(request, author="testuser")

    # Check version history exists
    versions = registry.list_persona_versions("versioned-persona")
    assert len(versions) == 1
    assert versions[0].version == "1.0.0"
    assert versions[0].changelog == "Initial version"
    assert versions[0].instructions == "# Versioned Persona\n\nInstructions here."
    assert versions[0].references_skills == ["code-writer"]


@pytest.mark.asyncio
async def test_update_persona_with_version_change_adds_version(registry, temp_personas_path):
    """Test that updating a persona with version change adds version entry."""
    # Create persona first
    request = PersonaCreateRequest(
        id="update-version-persona",
        name="Update Version Persona",
        description="A persona to test version updates",
        instructions="Original instructions",
        references_skills=["skill-a"],
        version="1.0.0"
    )
    await registry.create_persona(request, author="testuser")

    # Update with new version
    update = PersonaUpdateRequest(
        version="1.1.0",
        instructions="Updated instructions",
        references_skills=["skill-a", "skill-b"],
        changelog="Added skill-b"
    )
    await registry.update_persona("update-version-persona", update)

    # Check version history
    versions = registry.list_persona_versions("update-version-persona")
    assert len(versions) == 2
    assert versions[0].version == "1.1.0"  # Newest first
    assert versions[0].changelog == "Added skill-b"
    assert versions[0].instructions == "Updated instructions"
    assert versions[0].references_skills == ["skill-a", "skill-b"]
    assert versions[1].version == "1.0.0"  # Initial version


@pytest.mark.asyncio
async def test_update_persona_with_changelog_adds_version(registry, temp_personas_path):
    """Test that update with changelog (but same version) adds version entry."""
    request = PersonaCreateRequest(
        id="changelog-persona",
        name="Changelog Persona",
        description="A persona to test changelog",
        instructions="Original",
        version="1.0.0"
    )
    await registry.create_persona(request, author="testuser")

    # Update with just changelog (no version bump)
    update = PersonaUpdateRequest(
        instructions="Improved instructions",
        changelog="Minor improvement"
    )
    await registry.update_persona("changelog-persona", update)

    versions = registry.list_persona_versions("changelog-persona")
    # Should have 2 versions - initial and the changelog update
    assert len(versions) == 2
    assert versions[0].changelog == "Minor improvement"


@pytest.mark.asyncio
async def test_update_persona_without_changelog_no_new_version(registry, temp_personas_path):
    """Test that update without version change or changelog doesn't add version."""
    request = PersonaCreateRequest(
        id="no-version-persona",
        name="No Version Persona",
        description="Test",
        instructions="Original",
        version="1.0.0"
    )
    await registry.create_persona(request, author="testuser")

    # Update without changelog or version bump (just description)
    update = PersonaUpdateRequest(
        description="Updated description"
    )
    await registry.update_persona("no-version-persona", update)

    versions = registry.list_persona_versions("no-version-persona")
    # Should still have only 1 version (initial)
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_get_persona_version_returns_specific_version(registry, temp_personas_path):
    """Test retrieving a specific version of a persona."""
    request = PersonaCreateRequest(
        id="multi-version-persona",
        name="Multi Version Persona",
        description="A persona with multiple versions",
        instructions="v1 instructions",
        references_skills=["skill-v1"],
        version="1.0.0"
    )
    await registry.create_persona(request, author="testuser")

    # Update to v1.1.0
    await registry.update_persona("multi-version-persona", PersonaUpdateRequest(
        version="1.1.0",
        instructions="v1.1 instructions",
        references_skills=["skill-v1", "skill-v2"],
        changelog="Added skill-v2"
    ))

    # Get v1.0.0
    v1_persona = registry.get_persona_version("multi-version-persona", "1.0.0")
    assert v1_persona is not None
    assert v1_persona.version == "1.0.0"
    assert v1_persona.instructions == "v1 instructions"
    assert v1_persona.references_skills == ["skill-v1"]

    # Get current (v1.1.0)
    current = registry.get_persona("multi-version-persona")
    assert current.version == "1.1.0"
    assert current.instructions == "v1.1 instructions"


@pytest.mark.asyncio
async def test_get_persona_version_nonexistent_version(registry, temp_personas_path):
    """Test that getting a nonexistent version returns None."""
    request = PersonaCreateRequest(
        id="version-test-persona",
        name="Version Test",
        description="Test persona",
        instructions="Test",
        version="1.0.0"
    )
    await registry.create_persona(request, author="testuser")

    result = registry.get_persona_version("version-test-persona", "99.0.0")
    assert result is None


@pytest.mark.asyncio
async def test_get_persona_version_nonexistent_persona(registry):
    """Test that getting version of nonexistent persona returns None."""
    result = registry.get_persona_version("nonexistent-persona", "1.0.0")
    assert result is None


@pytest.mark.asyncio
async def test_list_persona_versions_empty(registry):
    """Test listing versions for persona with no history."""
    versions = registry.list_persona_versions("nonexistent-persona")
    assert versions == []


@pytest.mark.asyncio
async def test_version_history_persists(temp_personas_path):
    """Test that version history is saved and loaded from disk."""
    # Create first registry and add persona
    registry1 = PersonaRegistry(personas_path=temp_personas_path)
    await registry1.initialize()

    request = PersonaCreateRequest(
        id="persist-persona",
        name="Persist Persona",
        description="Test persistence",
        instructions="v1",
        version="1.0.0"
    )
    await registry1.create_persona(request, author="testuser")

    await registry1.update_persona("persist-persona", PersonaUpdateRequest(
        version="1.1.0",
        instructions="v1.1",
        changelog="Updated"
    ))

    # Create second registry (simulating restart)
    registry2 = PersonaRegistry(personas_path=temp_personas_path)
    await registry2.initialize()

    # Version history should be loaded
    versions = registry2.list_persona_versions("persist-persona")
    assert len(versions) == 2
    assert versions[0].version == "1.1.0"
    assert versions[1].version == "1.0.0"


@pytest.mark.asyncio
async def test_version_history_sorted_newest_first(registry, temp_personas_path):
    """Test that version history is always sorted newest first."""
    request = PersonaCreateRequest(
        id="sorted-persona",
        name="Sorted Persona",
        description="Test sorting",
        instructions="v1",
        version="1.0.0"
    )
    await registry.create_persona(request, author="testuser")

    # Add multiple versions
    for i in range(2, 5):
        await registry.update_persona("sorted-persona", PersonaUpdateRequest(
            version=f"1.{i}.0",
            changelog=f"Version 1.{i}.0"
        ))

    versions = registry.list_persona_versions("sorted-persona")
    assert len(versions) == 4
    assert versions[0].version == "1.4.0"
    assert versions[1].version == "1.3.0"
    assert versions[2].version == "1.2.0"
    assert versions[3].version == "1.0.0"
