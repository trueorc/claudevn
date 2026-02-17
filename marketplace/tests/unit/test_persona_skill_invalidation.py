"""Tests for persona invalidation when skills change.

This tests the lazy regeneration pattern (Issue #202):
- When a skill is updated, personas referencing it are marked as stale
- Stale personas are lazily regenerated on next get_persona() call
- No manual intervention required after skill updates
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from models import Skill, SkillUpdateRequest, Persona, PersonaCreateRequest
from skill_registry import SkillRegistry
from persona_registry import PersonaRegistry


@pytest.fixture
def temp_skills_path(tmp_path):
    """Create a temporary skills directory with test skills."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "system").mkdir()
    (skills_dir / "user").mkdir()

    # Create test skill A
    skill_a = skills_dir / "system" / "skill-a.yaml"
    skill_a.write_text("""id: skill-a
name: Skill A
description: Test skill A
version: "1.0.0"
author: system

instructions: |
  # Skill A Instructions

  Original instructions for skill A.

specialized_tools: []

tags:
  - testing

constraints:
  - Constraint A
""")

    # Create test skill B
    skill_b = skills_dir / "system" / "skill-b.yaml"
    skill_b.write_text("""id: skill-b
name: Skill B
description: Test skill B
version: "1.0.0"
author: system

instructions: |
  # Skill B Instructions

  Original instructions for skill B.

specialized_tools: []

tags:
  - testing

constraints:
  - Constraint B
""")

    return str(skills_dir)


@pytest.fixture
def temp_personas_path(tmp_path):
    """Create a temporary personas directory."""
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "system").mkdir()
    (personas_dir / "user").mkdir()
    (personas_dir / "versions").mkdir()
    return str(personas_dir)


@pytest.fixture
async def skill_registry(temp_skills_path):
    """Create an initialized skill registry."""
    reg = SkillRegistry(skills_path=temp_skills_path)
    await reg.initialize()
    return reg


@pytest.fixture
async def persona_registry(temp_personas_path, skill_registry):
    """Create an initialized persona registry with skill registry wired."""
    reg = PersonaRegistry(personas_path=temp_personas_path)
    await reg.initialize()
    reg.set_skill_registry(skill_registry)
    skill_registry.set_persona_registry(reg)
    return reg


class TestPersonaInvalidationOnSkillUpdate:
    """Tests for automatic persona invalidation when skills are updated."""

    @pytest.mark.asyncio
    async def test_skill_update_marks_referencing_personas_stale(
        self, skill_registry, persona_registry
    ):
        """Test that updating a skill marks personas referencing it as stale."""
        # Create a persona referencing skill-a
        request = PersonaCreateRequest(
            id="test-persona",
            name="Test Persona",
            description="Test persona",
            instructions="Test instructions",
            references_skills=["skill-a"]
        )
        persona = await persona_registry.create_persona(request)
        assert persona.instructions_stale is False
        original_merged = persona.merged_instructions
        assert "Skill A Instructions" in original_merged

        # Update skill-a instructions
        update_request = SkillUpdateRequest(
            instructions="# Updated Skill A\n\nNew instructions for skill A."
        )
        await skill_registry.update_skill("skill-a", update_request)

        # Verify persona is now marked as stale (directly check, not via get_persona)
        stale_persona = persona_registry.personas.get("test-persona")
        assert stale_persona.instructions_stale is True

    @pytest.mark.asyncio
    async def test_get_persona_regenerates_stale_instructions(
        self, skill_registry, persona_registry
    ):
        """Test that get_persona() lazily regenerates stale merged_instructions."""
        # Create a persona referencing skill-a
        request = PersonaCreateRequest(
            id="test-persona",
            name="Test Persona",
            description="Test persona",
            instructions="Test instructions",
            references_skills=["skill-a"]
        )
        persona = await persona_registry.create_persona(request)
        original_merged = persona.merged_instructions
        assert "Original instructions for skill A" in original_merged

        # Update skill-a
        update_request = SkillUpdateRequest(
            instructions="# Updated Skill A\n\nCompletely new content."
        )
        await skill_registry.update_skill("skill-a", update_request)

        # Get the persona - should regenerate
        refreshed_persona = persona_registry.get_persona("test-persona")

        # Verify merged instructions were updated
        assert refreshed_persona.instructions_stale is False
        assert "Completely new content" in refreshed_persona.merged_instructions
        assert "Original instructions" not in refreshed_persona.merged_instructions

    @pytest.mark.asyncio
    async def test_multiple_personas_invalidated(
        self, skill_registry, persona_registry
    ):
        """Test that all personas referencing an updated skill are invalidated."""
        # Create persona 1 referencing skill-a
        persona1 = await persona_registry.create_persona(PersonaCreateRequest(
            id="persona-1",
            name="Persona 1",
            description="First persona",
            instructions="Instructions 1",
            references_skills=["skill-a"]
        ))

        # Create persona 2 referencing skill-a and skill-b
        persona2 = await persona_registry.create_persona(PersonaCreateRequest(
            id="persona-2",
            name="Persona 2",
            description="Second persona",
            instructions="Instructions 2",
            references_skills=["skill-a", "skill-b"]
        ))

        # Create persona 3 referencing only skill-b
        persona3 = await persona_registry.create_persona(PersonaCreateRequest(
            id="persona-3",
            name="Persona 3",
            description="Third persona",
            instructions="Instructions 3",
            references_skills=["skill-b"]
        ))

        # Update skill-a
        await skill_registry.update_skill("skill-a", SkillUpdateRequest(
            instructions="Updated skill A"
        ))

        # Verify persona-1 and persona-2 are stale, persona-3 is not
        assert persona_registry.personas["persona-1"].instructions_stale is True
        assert persona_registry.personas["persona-2"].instructions_stale is True
        assert persona_registry.personas["persona-3"].instructions_stale is False

    @pytest.mark.asyncio
    async def test_non_instruction_updates_dont_invalidate(
        self, skill_registry, persona_registry
    ):
        """Test that updating non-instruction fields doesn't invalidate personas."""
        # Create a persona referencing skill-a
        await persona_registry.create_persona(PersonaCreateRequest(
            id="test-persona",
            name="Test Persona",
            description="Test persona",
            instructions="Test instructions",
            references_skills=["skill-a"]
        ))

        # Update only tags (not instructions/constraints/name)
        await skill_registry.update_skill("skill-a", SkillUpdateRequest(
            tags=["updated-tag", "testing"]
        ))

        # Persona should NOT be stale
        assert persona_registry.personas["test-persona"].instructions_stale is False

    @pytest.mark.asyncio
    async def test_constraint_update_invalidates(
        self, skill_registry, persona_registry
    ):
        """Test that updating skill constraints invalidates personas."""
        await persona_registry.create_persona(PersonaCreateRequest(
            id="test-persona",
            name="Test Persona",
            description="Test persona",
            instructions="Test instructions",
            references_skills=["skill-a"]
        ))

        # Update constraints
        await skill_registry.update_skill("skill-a", SkillUpdateRequest(
            constraints=["New constraint"]
        ))

        # Persona SHOULD be stale (constraints affect merged_instructions)
        assert persona_registry.personas["test-persona"].instructions_stale is True

    @pytest.mark.asyncio
    async def test_skill_name_update_invalidates(
        self, skill_registry, persona_registry
    ):
        """Test that updating skill name invalidates personas."""
        await persona_registry.create_persona(PersonaCreateRequest(
            id="test-persona",
            name="Test Persona",
            description="Test persona",
            instructions="Test instructions",
            references_skills=["skill-a"]
        ))

        # Update name
        await skill_registry.update_skill("skill-a", SkillUpdateRequest(
            name="Renamed Skill A"
        ))

        # Persona SHOULD be stale (name appears in merged_instructions)
        assert persona_registry.personas["test-persona"].instructions_stale is True


class TestInvalidatePersonasMethod:
    """Tests for the invalidate_personas_referencing_skill method."""

    @pytest.mark.asyncio
    async def test_invalidate_returns_affected_persona_ids(
        self, skill_registry, persona_registry
    ):
        """Test that invalidate method returns list of affected persona IDs."""
        # Create multiple personas
        await persona_registry.create_persona(PersonaCreateRequest(
            id="persona-1",
            name="Persona 1",
            description="Test",
            instructions="Test",
            references_skills=["skill-a"]
        ))
        await persona_registry.create_persona(PersonaCreateRequest(
            id="persona-2",
            name="Persona 2",
            description="Test",
            instructions="Test",
            references_skills=["skill-a", "skill-b"]
        ))
        await persona_registry.create_persona(PersonaCreateRequest(
            id="persona-3",
            name="Persona 3",
            description="Test",
            instructions="Test",
            references_skills=["skill-b"]
        ))

        # Invalidate personas referencing skill-a
        affected = persona_registry.invalidate_personas_referencing_skill("skill-a")

        assert len(affected) == 2
        assert "persona-1" in affected
        assert "persona-2" in affected
        assert "persona-3" not in affected

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent_skill_returns_empty(
        self, persona_registry
    ):
        """Test that invalidating non-referenced skill returns empty list."""
        await persona_registry.create_persona(PersonaCreateRequest(
            id="persona-1",
            name="Persona 1",
            description="Test",
            instructions="Test",
            references_skills=["skill-a"]
        ))

        affected = persona_registry.invalidate_personas_referencing_skill("nonexistent-skill")
        assert affected == []

    @pytest.mark.asyncio
    async def test_already_stale_personas_not_double_counted(
        self, persona_registry, skill_registry
    ):
        """Test that already-stale personas aren't returned again."""
        await persona_registry.create_persona(PersonaCreateRequest(
            id="persona-1",
            name="Persona 1",
            description="Test",
            instructions="Test",
            references_skills=["skill-a"]
        ))

        # First invalidation
        affected1 = persona_registry.invalidate_personas_referencing_skill("skill-a")
        assert len(affected1) == 1

        # Second invalidation (persona already stale)
        affected2 = persona_registry.invalidate_personas_referencing_skill("skill-a")
        assert len(affected2) == 0


class TestLazyRegenerationDetails:
    """Tests for lazy regeneration behavior details."""

    @pytest.mark.asyncio
    async def test_regeneration_updates_updated_at(
        self, skill_registry, persona_registry
    ):
        """Test that lazy regeneration updates the updated_at timestamp."""
        persona = await persona_registry.create_persona(PersonaCreateRequest(
            id="test-persona",
            name="Test Persona",
            description="Test",
            instructions="Test",
            references_skills=["skill-a"]
        ))
        original_updated_at = persona.updated_at

        # Update skill to mark persona stale
        await skill_registry.update_skill("skill-a", SkillUpdateRequest(
            instructions="New instructions"
        ))

        # Get persona to trigger regeneration
        refreshed = persona_registry.get_persona("test-persona")

        # updated_at should be newer
        assert refreshed.updated_at >= original_updated_at

    @pytest.mark.asyncio
    async def test_non_stale_persona_not_regenerated(
        self, skill_registry, persona_registry
    ):
        """Test that non-stale personas aren't regenerated on get."""
        persona = await persona_registry.create_persona(PersonaCreateRequest(
            id="test-persona",
            name="Test Persona",
            description="Test",
            instructions="Test",
            references_skills=["skill-a"]
        ))
        original_merged = persona.merged_instructions

        # Get persona without any skill updates
        retrieved = persona_registry.get_persona("test-persona")

        # Should return same merged instructions (not regenerated)
        assert retrieved.merged_instructions == original_merged

    @pytest.mark.asyncio
    async def test_regeneration_includes_all_current_skills(
        self, skill_registry, persona_registry
    ):
        """Test that regeneration uses current state of ALL referenced skills."""
        # Create persona with both skills
        persona = await persona_registry.create_persona(PersonaCreateRequest(
            id="test-persona",
            name="Test Persona",
            description="Test",
            instructions="Test",
            references_skills=["skill-a", "skill-b"]
        ))

        # Update skill-a (marks persona stale)
        await skill_registry.update_skill("skill-a", SkillUpdateRequest(
            instructions="Updated A"
        ))

        # Update skill-b (persona already stale from first update)
        await skill_registry.update_skill("skill-b", SkillUpdateRequest(
            instructions="Updated B"
        ))

        # Get persona - should include both updated skills
        refreshed = persona_registry.get_persona("test-persona")

        assert "Updated A" in refreshed.merged_instructions
        assert "Updated B" in refreshed.merged_instructions


class TestNoPersonaRegistrySet:
    """Tests for behavior when persona registry is not set in skill registry."""

    @pytest.mark.asyncio
    async def test_skill_update_without_persona_registry(self, temp_skills_path):
        """Test that skill update works when no persona registry is wired."""
        skill_registry = SkillRegistry(skills_path=temp_skills_path)
        await skill_registry.initialize()

        # Should not raise even without persona registry set
        result = await skill_registry.update_skill("skill-a", SkillUpdateRequest(
            instructions="Updated instructions"
        ))

        assert result is not None
        assert result.instructions == "Updated instructions"
