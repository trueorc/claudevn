"""Unit tests for preferred_model field on Skill model (#59).

Tests that the Skill model correctly accepts and serializes the
preferred_model field.
"""

import pytest

from models import Skill


class TestSkillPreferredModel:
    """Tests for Skill.preferred_model field."""

    def test_skill_without_preferred_model(self):
        """Skill can be created without preferred_model (defaults to None)."""
        skill = Skill(
            id="doc-writer",
            name="Doc Writer",
            description="Writes docs",
            instructions="# Doc Writer\nWrite documentation.",
        )
        assert skill.preferred_model is None

    def test_skill_with_preferred_model(self):
        """Skill can be created with preferred_model set."""
        skill = Skill(
            id="code-writer",
            name="Code Writer",
            description="Writes code",
            instructions="# Code Writer\nWrite code.",
            preferred_model="opus",
        )
        assert skill.preferred_model == "opus"

    def test_skill_preferred_model_serialization(self):
        """preferred_model is included in model_dump output."""
        skill = Skill(
            id="code-writer",
            name="Code Writer",
            description="Writes code",
            instructions="# Code Writer",
            preferred_model="opus",
        )
        data = skill.model_dump()
        assert data["preferred_model"] == "opus"

    def test_skill_preferred_model_from_dict(self):
        """Skill can be created from dict (simulates YAML loading)."""
        yaml_data = {
            "id": "code-writer",
            "name": "Code Writer",
            "description": "Writes code",
            "instructions": "# Code Writer",
            "preferred_model": "opus",
        }
        skill = Skill(**yaml_data)
        assert skill.preferred_model == "opus"

    def test_skill_without_preferred_model_from_dict(self):
        """Skill from dict without preferred_model defaults to None."""
        yaml_data = {
            "id": "doc-writer",
            "name": "Doc Writer",
            "description": "Writes docs",
            "instructions": "# Doc Writer",
        }
        skill = Skill(**yaml_data)
        assert skill.preferred_model is None
