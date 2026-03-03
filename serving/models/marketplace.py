"""Data models for marketplace registration and management."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, List
from pydantic import BaseModel, ConfigDict, Field
from claudevn_shared.version import get_version


class MarketplaceStatus(str, Enum):
    """Marketplace connection status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class MarketplaceTier(str, Enum):
    """Marketplace hierarchy tier."""
    ROOT = "root"           # Default ClaudeVN skills shipped with the platform
    ENTERPRISE = "enterprise"  # Organization-approved skill library
    TEAM = "team"           # Team-specific skills and customizations
    PROJECT = "project"     # Project-scoped skills
    USER = "user"           # Individual user's custom skills


class MarketplaceCapabilities(BaseModel):
    """Capabilities and features of a marketplace."""
    agent_count: int = Field(0, description="Number of agents available")
    tool_count: int = Field(0, description="Number of tools available")
    skill_count: int = Field(0, description="Number of skills available")
    supports_search: bool = Field(True, description="Supports search functionality")
    supports_categories: bool = Field(True, description="Supports agent categories")
    supports_access_control: bool = Field(True, description="Supports access control")
    supports_organizations: bool = Field(True, description="Supports organizations")
    features: List[str] = Field(default_factory=list, description="Additional features")


class MarketplaceInstance(BaseModel):
    """Represents a registered marketplace instance."""
    marketplace_id: str = Field(..., description="Unique marketplace identifier")
    name: str = Field(..., description="Human-readable marketplace name")
    endpoint: str = Field(..., description="Internal API endpoint")
    public_endpoint: Optional[str] = Field(None, description="Public-facing endpoint if available")

    status: MarketplaceStatus = Field(
        default=MarketplaceStatus.HEALTHY,
        description="Current marketplace status"
    )

    tier: MarketplaceTier = Field(
        default=MarketplaceTier.USER,
        description="Marketplace hierarchy tier"
    )

    capabilities: MarketplaceCapabilities = Field(
        default_factory=MarketplaceCapabilities,
        description="Marketplace capabilities"
    )

    metadata: Dict = Field(
        default_factory=dict,
        description="Additional marketplace metadata"
    )

    version: str = Field(default_factory=get_version, description="Marketplace version")
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    heartbeat_interval: int = Field(60, description="Expected heartbeat interval in seconds")
    failed_health_checks: int = Field(0, description="Consecutive failed health checks")

    # Priority for multi-marketplace support
    priority: int = Field(1, description="Priority for agent discovery (lower = higher priority)")

    # Skill override declarations
    overrides: List["SkillOverrideDeclaration"] = Field(
        default_factory=list,
        description="Skill override/extend declarations"
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "marketplace_id": "marketplace-001",
            "name": "ClaudeVN Central Marketplace",
            "endpoint": "http://localhost:8001",
            "public_endpoint": "https://marketplace.example.com",
            "status": "healthy",
            "tier": "root",
            "capabilities": {
                "agent_count": 10,
                "tool_count": 5,
                "skill_count": 15,
                "supports_search": True,
                "supports_categories": True,
                "supports_access_control": True
            },
            "metadata": {
                "region": "us-west-2",
                "version": "0.1.4"
            },
            "version": "0.1.4",
            "priority": 1
        }
    })


class SkillOverrideDeclaration(BaseModel):
    """Declaration of how a marketplace's skills relate to another marketplace's skills."""
    target_marketplace_id: Optional[str] = Field(
        None,
        description="Marketplace whose skills are overridden (None = ROOT)"
    )
    mode: str = Field(
        "override",
        description="Override mode: 'override' replaces skill entirely, 'extend' merges instructions"
    )
    skill_pattern: Optional[str] = Field(
        None,
        description="Optional glob pattern to limit which skills are affected (e.g., 'acme-*')"
    )


class MarketplaceRegistrationRequest(BaseModel):
    """Request to register a marketplace."""
    marketplace_id: Optional[str] = Field(None, description="Unique ID (auto-generated if not provided)")
    name: str = Field(..., description="Marketplace name")
    endpoint: str = Field(..., description="API endpoint")
    public_endpoint: Optional[str] = Field(None, description="Public endpoint")
    tier: MarketplaceTier = Field(default=MarketplaceTier.USER, description="Marketplace tier")
    capabilities: Optional[MarketplaceCapabilities] = Field(None)
    metadata: Dict = Field(default_factory=dict)
    version: str = Field(default_factory=get_version)
    heartbeat_interval: int = Field(60, description="Desired heartbeat interval")
    priority: int = Field(1, description="Marketplace priority")
    overrides: List[SkillOverrideDeclaration] = Field(
        default_factory=list,
        description="Skill override/extend declarations for this marketplace"
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "marketplace_id": "marketplace-001",
            "name": "ClaudeVN Central Marketplace",
            "endpoint": "http://localhost:8001",
            "tier": "root",
            "capabilities": {
                "agent_count": 10,
                "tool_count": 5,
                "skill_count": 15,
                "supports_search": True
            },
            "metadata": {
                "region": "us-west-2"
            },
            "version": "0.1.4",
            "priority": 1
        }
    })


class MarketplaceRegistrationResponse(BaseModel):
    """Response to marketplace registration."""
    status: str = Field(..., description="Registration status")
    marketplace_id: str = Field(..., description="Assigned marketplace ID")
    heartbeat_interval: int = Field(..., description="Heartbeat interval in seconds")
    heartbeat_endpoint: str = Field(..., description="Endpoint for heartbeats")
    message: str = Field(..., description="Human-readable message")


class MarketplaceHeartbeatRequest(BaseModel):
    """Heartbeat update from marketplace."""
    agent_count: Optional[int] = Field(None, description="Updated agent count")
    tool_count: Optional[int] = Field(None, description="Updated tool count")
    skill_count: Optional[int] = Field(None, description="Updated skill count")
    status: Optional[str] = Field(None, description="Current status")
    metadata: Optional[Dict] = Field(None, description="Updated metadata")


class MarketplaceUpdateRequest(BaseModel):
    """Request to update marketplace information."""
    name: Optional[str] = None
    endpoint: Optional[str] = None
    public_endpoint: Optional[str] = None
    capabilities: Optional[MarketplaceCapabilities] = None
    metadata: Optional[Dict] = None
    priority: Optional[int] = None


class MarketplaceListResponse(BaseModel):
    """Response for listing marketplaces."""
    marketplaces: List[MarketplaceInstance]
    total: int
    healthy: int
    offline: int


class AggregatedMarketplaceStats(BaseModel):
    """Aggregated statistics across all marketplaces."""
    total_marketplaces: int
    healthy_marketplaces: int
    degraded_marketplaces: int
    offline_marketplaces: int
    total_agents: int
    total_tools: int
    by_status: Dict[str, int]

