"""Unit tests for marketplace source tracking in skills."""

import pytest
from datetime import datetime, timezone

from models import Skill, MarketplaceTier


class TestSkillMarketplaceFields:
    """Tests for Skill model marketplace source fields."""

    def test_skill_has_marketplace_fields(self):
        """Skill model should have marketplace source fields."""
        skill = Skill(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            instructions="# Test\n\nDo something"
        )

        assert hasattr(skill, "marketplace_id")
        assert hasattr(skill, "marketplace_name")
        assert hasattr(skill, "marketplace_tier")
        assert hasattr(skill, "namespace")

    def test_skill_marketplace_fields_default_none(self):
        """Marketplace fields should default to None."""
        skill = Skill(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            instructions="# Test"
        )

        assert skill.marketplace_id is None
        assert skill.marketplace_name is None
        assert skill.marketplace_tier is None
        assert skill.namespace is None

    def test_skill_with_marketplace_source(self):
        """Skill can be created with marketplace source metadata."""
        skill = Skill(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            instructions="# Test",
            marketplace_id="marketplace-001",
            marketplace_name="ClaudeVN Central",
            marketplace_tier=MarketplaceTier.ROOT,
            namespace="claudevn"
        )

        assert skill.marketplace_id == "marketplace-001"
        assert skill.marketplace_name == "ClaudeVN Central"
        assert skill.marketplace_tier == MarketplaceTier.ROOT
        assert skill.namespace == "claudevn"

    def test_skill_serialization_includes_marketplace(self):
        """Skill serialization should include marketplace fields."""
        skill = Skill(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            instructions="# Test",
            marketplace_id="mp-001",
            marketplace_name="Backoffice Skills",
            marketplace_tier=MarketplaceTier.EXTENDED
        )

        data = skill.model_dump()

        assert "marketplace_id" in data
        assert "marketplace_name" in data
        assert "marketplace_tier" in data
        assert "namespace" in data
        assert data["marketplace_id"] == "mp-001"
        assert data["marketplace_name"] == "Backoffice Skills"
        assert data["marketplace_tier"] == "extended"


class TestMarketplaceTierEnum:
    """Tests for MarketplaceTier enum."""

    def test_tier_values(self):
        """MarketplaceTier should have root and extended values."""
        assert MarketplaceTier.ROOT.value == "root"
        assert MarketplaceTier.EXTENDED.value == "extended"

    def test_tier_from_string(self):
        """MarketplaceTier can be created from string value."""
        assert MarketplaceTier("root") == MarketplaceTier.ROOT
        assert MarketplaceTier("extended") == MarketplaceTier.EXTENDED

    def test_extended_is_specialized(self):
        """Extended marketplaces provide specialized capabilities on top of root."""
        # Both tiers exist
        assert len(MarketplaceTier) == 2
        # They are distinct
        assert MarketplaceTier.ROOT != MarketplaceTier.EXTENDED
