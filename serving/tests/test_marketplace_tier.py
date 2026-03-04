"""Unit tests for marketplace tier and skill count in serving models."""

import pytest
from datetime import datetime, timezone

from models.marketplace import (
    MarketplaceInstance,
    MarketplaceStatus,
    MarketplaceTier,
    MarketplaceCapabilities,
    MarketplaceRegistrationRequest,
    MarketplaceHeartbeatRequest
)


class TestMarketplaceTier:
    """Tests for MarketplaceTier enum in serving."""

    def test_tier_values(self):
        """MarketplaceTier should have root and extended values."""
        assert MarketplaceTier.ROOT.value == "root"
        assert MarketplaceTier.EXTENDED.value == "extended"

    def test_tier_from_string(self):
        """MarketplaceTier can be created from string value."""
        assert MarketplaceTier("root") == MarketplaceTier.ROOT
        assert MarketplaceTier("extended") == MarketplaceTier.EXTENDED

    def test_only_two_tiers(self):
        """Only ROOT and EXTENDED tiers should exist."""
        assert len(MarketplaceTier) == 2


class TestMarketplaceCapabilities:
    """Tests for MarketplaceCapabilities model."""

    def test_skill_count_field_exists(self):
        """MarketplaceCapabilities should have skill_count field."""
        caps = MarketplaceCapabilities()
        assert hasattr(caps, "skill_count")
        assert caps.skill_count == 0

    def test_skill_count_with_value(self):
        """skill_count can be set to a value."""
        caps = MarketplaceCapabilities(
            agent_count=5,
            tool_count=10,
            skill_count=15
        )
        assert caps.skill_count == 15
        assert caps.agent_count == 5
        assert caps.tool_count == 10


class TestMarketplaceInstance:
    """Tests for MarketplaceInstance with tier field."""

    def test_tier_field_exists(self):
        """MarketplaceInstance should have tier field."""
        marketplace = MarketplaceInstance(
            marketplace_id="mp-001",
            name="Test Marketplace",
            endpoint="http://localhost:8003"
        )
        assert hasattr(marketplace, "tier")

    def test_tier_default_value(self):
        """tier should default to EXTENDED."""
        marketplace = MarketplaceInstance(
            marketplace_id="mp-001",
            name="Test Marketplace",
            endpoint="http://localhost:8003"
        )
        assert marketplace.tier == MarketplaceTier.EXTENDED

    def test_tier_can_be_set(self):
        """tier can be set to any MarketplaceTier value."""
        marketplace = MarketplaceInstance(
            marketplace_id="mp-001",
            name="Core Marketplace",
            endpoint="http://localhost:8003",
            tier=MarketplaceTier.ROOT
        )
        assert marketplace.tier == MarketplaceTier.ROOT

    def test_marketplace_serialization_includes_tier(self):
        """Marketplace serialization should include tier field."""
        marketplace = MarketplaceInstance(
            marketplace_id="mp-001",
            name="Backoffice Skills",
            endpoint="http://localhost:8003",
            tier=MarketplaceTier.EXTENDED
        )

        data = marketplace.model_dump()

        assert "tier" in data
        assert data["tier"] == "extended"


class TestMarketplaceRegistrationRequest:
    """Tests for MarketplaceRegistrationRequest with tier."""

    def test_tier_in_registration(self):
        """Registration request should accept tier field."""
        request = MarketplaceRegistrationRequest(
            name="Backoffice Skills",
            endpoint="http://localhost:8003",
            tier=MarketplaceTier.EXTENDED
        )
        assert request.tier == MarketplaceTier.EXTENDED

    def test_tier_default_in_registration(self):
        """tier should default to EXTENDED in registration."""
        request = MarketplaceRegistrationRequest(
            name="My Marketplace",
            endpoint="http://localhost:8003"
        )
        assert request.tier == MarketplaceTier.EXTENDED


class TestMarketplaceHeartbeatRequest:
    """Tests for MarketplaceHeartbeatRequest with skill_count."""

    def test_skill_count_in_heartbeat(self):
        """Heartbeat request should accept skill_count field."""
        request = MarketplaceHeartbeatRequest(
            agent_count=5,
            tool_count=10,
            skill_count=20
        )
        assert request.skill_count == 20

    def test_skill_count_optional_in_heartbeat(self):
        """skill_count should be optional in heartbeat."""
        request = MarketplaceHeartbeatRequest(
            agent_count=5
        )
        assert request.skill_count is None
