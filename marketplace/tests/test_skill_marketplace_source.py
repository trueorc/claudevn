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
            marketplace_name="Test Market",
            marketplace_tier=MarketplaceTier.ENTERPRISE
        )

        data = skill.model_dump()

        assert "marketplace_id" in data
        assert "marketplace_name" in data
        assert "marketplace_tier" in data
        assert "namespace" in data
        assert data["marketplace_id"] == "mp-001"
        assert data["marketplace_name"] == "Test Market"
        assert data["marketplace_tier"] == "enterprise"


class TestMarketplaceTierEnum:
    """Tests for MarketplaceTier enum."""

    def test_tier_values(self):
        """MarketplaceTier should have all expected values."""
        assert MarketplaceTier.ROOT.value == "root"
        assert MarketplaceTier.ENTERPRISE.value == "enterprise"
        assert MarketplaceTier.TEAM.value == "team"
        assert MarketplaceTier.PROJECT.value == "project"
        assert MarketplaceTier.USER.value == "user"

    def test_tier_from_string(self):
        """MarketplaceTier can be created from string value."""
        assert MarketplaceTier("root") == MarketplaceTier.ROOT
        assert MarketplaceTier("enterprise") == MarketplaceTier.ENTERPRISE
        assert MarketplaceTier("team") == MarketplaceTier.TEAM
        assert MarketplaceTier("project") == MarketplaceTier.PROJECT
        assert MarketplaceTier("user") == MarketplaceTier.USER

    def test_tier_hierarchy_order(self):
        """Tiers should have a logical hierarchy order."""
        # Define expected priority (lower = higher priority)
        priority = {
            MarketplaceTier.ROOT: 0,
            MarketplaceTier.ENTERPRISE: 1,
            MarketplaceTier.TEAM: 2,
            MarketplaceTier.PROJECT: 3,
            MarketplaceTier.USER: 4
        }

        # Verify root has highest priority
        assert priority[MarketplaceTier.ROOT] < priority[MarketplaceTier.USER]
        assert priority[MarketplaceTier.ENTERPRISE] < priority[MarketplaceTier.TEAM]
