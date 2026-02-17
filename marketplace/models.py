"""Data models for the Skill Marketplace."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class ToolTier(str, Enum):
    """Tool permission tier."""
    GLOBAL = "global"
    SPECIALIZED = "specialized"


class SkillAuthor(str, Enum):
    """Skill author type."""
    SYSTEM = "system"
    USER = "user"


class SkillVersion(BaseModel):
    """Version history entry for a skill."""
    skill_id: str = Field(..., description="Skill identifier")
    version: str = Field(..., description="Semantic version")
    instructions: str = Field(..., description="Instructions at this version")
    specialized_tools: List[str] = Field(default_factory=list, description="Tools at this version")
    changelog: Optional[str] = Field(None, description="Description of changes in this version")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "skill_id": "code-writer",
            "version": "1.1.0",
            "instructions": "# Code Writer\n\nUpdated instructions...",
            "specialized_tools": ["lint_code"],
            "changelog": "Added linting support",
            "created_at": "2026-01-31T12:00:00Z"
        }
    })


class PersonaVersion(BaseModel):
    """Version history entry for a persona."""
    persona_id: str = Field(..., description="Persona identifier")
    version: str = Field(..., description="Semantic version")
    instructions: str = Field(..., description="Instructions at this version")
    references_skills: List[str] = Field(default_factory=list, description="Skills at this version")
    changelog: Optional[str] = Field(None, description="Description of changes in this version")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "persona_id": "fullstack-developer",
            "version": "1.1.0",
            "instructions": "# Full-Stack Developer\n\nUpdated instructions...",
            "references_skills": ["code-writer", "test-automator"],
            "changelog": "Added test automation skill",
            "created_at": "2026-01-31T12:00:00Z"
        }
    })


class MarketplaceTier(str, Enum):
    """Marketplace hierarchy tier."""
    ROOT = "root"           # Default ClaudeVN skills shipped with the platform
    ENTERPRISE = "enterprise"  # Organization-approved skill library
    TEAM = "team"           # Team-specific skills and customizations
    PROJECT = "project"     # Project-scoped skills
    USER = "user"           # Individual user's custom skills


class Skill(BaseModel):
    """Atomic capability unit."""
    id: str = Field(..., description="Unique skill identifier")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="What this skill does")
    version: str = Field(default="1.0.0", description="Semantic version")
    author: str = Field(default="system", description="system or user:{id}")

    instructions: str = Field(..., description="CLAUDE.md instruction fragment")
    specialized_tools: List[str] = Field(default_factory=list, description="Tool IDs this skill grants")
    tags: List[str] = Field(default_factory=list, description="Tags for discovery")
    conflicts_with: List[str] = Field(default_factory=list, description="Skill IDs (advisory)")
    constraints: List[str] = Field(default_factory=list, description="What NOT to do")
    dependencies: List[str] = Field(default_factory=list, description="Skill IDs that are automatically included when this skill is selected")

    # Usage tracking
    usage_count: int = Field(default=0, description="Number of times used in agent composition")
    last_used_at: Optional[datetime] = Field(None, description="Last time this skill was used in composition")

    # Marketplace source tracking
    marketplace_id: Optional[str] = Field(None, description="Source marketplace ID")
    marketplace_name: Optional[str] = Field(None, description="Human-readable source marketplace name")
    marketplace_tier: Optional[MarketplaceTier] = Field(None, description="Marketplace hierarchy tier")
    namespace: Optional[str] = Field(None, description="Optional namespace prefix for skill ID")

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "code-writer",
            "name": "Code Writer",
            "description": "Implements features and writes production-quality code",
            "version": "1.0.0",
            "author": "system",
            "instructions": "# Code Writer\n\nYou implement features...",
            "specialized_tools": [],
            "tags": ["coding", "implementation"],
            "conflicts_with": [],
            "constraints": ["Do not refactor unrelated code"],
            "dependencies": [],
            "marketplace_id": "marketplace-001",
            "marketplace_name": "ClaudeVN Central",
            "marketplace_tier": "root",
            "namespace": None
        }
    })


class ToolDefinition(BaseModel):
    """Tool definition with permissions."""
    id: str = Field(..., description="Tool identifier")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="What this tool does")
    tier: ToolTier = Field(..., description="global or specialized")
    granted_by: List[str] = Field(default_factory=list, description="Skills that grant this tool")
    required_labels: List[str] = Field(
        default_factory=list,
        description="Compute labels required to run this tool"
    )
    security_level: str = Field(default="standard", description="Security classification")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "deploy_prod",
            "name": "Deploy to Production",
            "description": "Deploy code to production environment",
            "tier": "specialized",
            "granted_by": ["deploy-engineer"],
            "required_labels": ["production-access"],
            "security_level": "elevated"
        }
    })


class ProjectContext(BaseModel):
    """Project-specific context for agent composition."""
    project_id: str = Field(..., description="Project identifier")
    conventions: str = Field(default="", description="Code style and patterns")
    tech_stack: List[str] = Field(default_factory=list, description="Technologies used")
    domain_context: str = Field(default="", description="Domain knowledge")
    custom_rules: List[str] = Field(default_factory=list, description="Project-specific rules")


class TaskAssignment(BaseModel):
    """Task assigned to an agent."""
    task_id: str = Field(..., description="Task identifier")
    description: str = Field(..., description="Task description")
    required_capabilities: List[str] = Field(default_factory=list, description="Required tags/capabilities")
    priority: int = Field(default=1, description="Task priority")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional task data")


class Agent(BaseModel):
    """Composed agent bundle for Claude Code deployment."""
    id: str = Field(..., description="Agent instance identifier")
    skills: List[Skill] = Field(..., description="Selected skills")
    merged_instructions: str = Field(..., description="Final CLAUDE.md content")
    tools: List[str] = Field(..., description="All granted tools (global + specialized)")
    context: Optional[ProjectContext] = Field(None, description="Project context")
    task: Optional[TaskAssignment] = Field(None, description="Assigned task")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "agent-abc123",
            "skills": [],
            "merged_instructions": "# Agent Instructions\n...",
            "tools": ["read", "write", "bash"],
            "context": None,
            "task": None
        }
    })


# Request/Response models


class AgentListResponse(BaseModel):
    """Response for listing composed agents."""
    agents: List[Agent] = Field(..., description="List of composed agents")
    total: int = Field(..., description="Total number of agents")


class SkillCreateRequest(BaseModel):
    """Request to create a new skill."""
    id: str = Field(..., description="Unique skill ID")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Skill description")
    instructions: str = Field(..., description="CLAUDE.md instruction fragment")
    specialized_tools: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    conflicts_with: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    version: str = Field(default="1.0.0")


class SkillUpdateRequest(BaseModel):
    """Request to update a skill."""
    name: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    specialized_tools: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    conflicts_with: Optional[List[str]] = None
    constraints: Optional[List[str]] = None
    dependencies: Optional[List[str]] = None
    version: Optional[str] = None
    changelog: Optional[str] = Field(None, description="Description of changes for version history")


class SkillSearchRequest(BaseModel):
    """Request to search skills."""
    tags: Optional[List[str]] = Field(None, description="Filter by tags")
    capabilities: Optional[List[str]] = Field(None, description="Filter by capabilities")
    author: Optional[str] = Field(None, description="Filter by author")


class ComposeRequest(BaseModel):
    """Request to compose an agent from skills."""
    task: TaskAssignment = Field(..., description="Task to compose agent for")
    skill_ids: Optional[List[str]] = Field(None, description="Explicit skill IDs (overrides auto-selection)")
    context: Optional[ProjectContext] = Field(None, description="Project context")


class ConflictCheckRequest(BaseModel):
    """Request to check for skill conflicts."""
    skill_ids: List[str] = Field(..., description="Skills to check")


class ConflictCheckResponse(BaseModel):
    """Response from conflict check."""
    has_conflicts: bool = Field(..., description="Whether conflicts exist")
    conflicts: List[Dict[str, Any]] = Field(default_factory=list, description="Conflict details")
    warnings: List[str] = Field(default_factory=list, description="Advisory warnings")


class ComposePreviewResponse(BaseModel):
    """Response from composition preview (no agent persisted)."""
    preview: bool = Field(default=True, description="Indicates this is a preview only")
    merged_instructions: str = Field(..., description="Preview of merged CLAUDE.md content")
    tools: List[str] = Field(..., description="All tools that would be granted")
    skills: List[Skill] = Field(..., description="Skills that would be included")
    conflict_warnings: ConflictCheckResponse = Field(..., description="Conflict check results")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "preview": True,
            "merged_instructions": "# Agent Configuration\n...",
            "tools": ["read", "write", "bash"],
            "skills": [],
            "conflict_warnings": {
                "has_conflicts": False,
                "conflicts": [],
                "warnings": []
            }
        }
    })


class AddSkillRequest(BaseModel):
    """Request to add a skill to a composition."""
    skill_id: str = Field(..., description="Skill ID to add")
    force: bool = Field(default=False, description="Proceed despite conflicts")


class ConflictResolution(str, Enum):
    """Resolution decision for skill conflicts.

    When conflicts are detected during skill addition, the user/system
    must decide how to proceed:
    - KEEP_BOTH: Accept the conflict, keep both skills (intentional)
    - REMOVE_EXISTING: Remove the conflicting existing skill(s)
    - CANCEL: Cancel the addition, keep existing composition unchanged
    """
    KEEP_BOTH = "keep_both"
    REMOVE_EXISTING = "remove_existing"
    CANCEL = "cancel"


class ResolveConflictRequest(BaseModel):
    """Request to resolve a skill conflict.

    After add_skill() detects conflicts, this endpoint applies
    the user's resolution decision.
    """
    new_skill_id: str = Field(..., description="Skill ID that was being added")
    existing_skill_ids: List[str] = Field(..., description="Current skill IDs in the composition")
    conflicting_skill_ids: List[str] = Field(..., description="Skill IDs that conflict with the new skill")
    resolution: ConflictResolution = Field(..., description="How to resolve the conflict")
    reason: Optional[str] = Field(None, description="Optional reason for the decision (for audit)")


class ResolveConflictResult(BaseModel):
    """Result from resolving a skill conflict.

    Captures the outcome of applying a conflict resolution decision,
    including audit information.
    """
    resolution: ConflictResolution = Field(..., description="Resolution that was applied")
    new_skill_id: str = Field(..., description="Skill ID that was being added")
    new_skill_name: str = Field(default="", description="Display name of the new skill")
    resulting_skill_ids: List[str] = Field(..., description="Final skill IDs after resolution")
    removed_skill_ids: List[str] = Field(default_factory=list, description="Skill IDs that were removed")
    success: bool = Field(..., description="Whether the resolution was applied successfully")
    message: str = Field(default="", description="Human-readable status message")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When resolution was applied")
    reason: Optional[str] = Field(None, description="User-provided reason for the decision")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "resolution": "keep_both",
            "new_skill_id": "code-reviewer",
            "new_skill_name": "Code Reviewer",
            "resulting_skill_ids": ["code-writer", "code-reviewer"],
            "removed_skill_ids": [],
            "success": True,
            "message": "Kept both skills despite conflict",
            "timestamp": "2026-01-31T12:00:00Z",
            "reason": "Intentional combination for thorough review"
        }
    })


class AddSkillResult(BaseModel):
    """Result from adding a skill to a composition.

    Conflicts are advisory - the caller can decide to:
    1. Keep both skills (intentional, e.g., writer + reviewer)
    2. Remove conflicting skill
    3. Cancel the addition

    Example:
        result = composition.add_skill("code-reviewer")
        if result.has_conflicts:
            print(f"Warning: {result.conflicts}")
            # Decision: keep both for thorough review
            composition.confirm_addition(result.skill_id, force=True)
    """
    skill_id: str = Field(..., description="Skill ID that was evaluated")
    skill_name: str = Field(default="", description="Display name of the skill")
    added: bool = Field(..., description="Whether the skill was added")
    has_conflicts: bool = Field(..., description="Whether conflicts were detected")
    conflicts: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Conflict details with existing skills"
    )
    warnings: List[str] = Field(default_factory=list, description="Advisory warnings")
    can_proceed: bool = Field(
        default=True,
        description="Whether addition can proceed (always True - decision point, not rejection)"
    )
    message: str = Field(default="", description="Human-readable status message")


class SkillListResponse(BaseModel):
    """Response for listing skills."""
    skills: List[Skill]
    total: int
    skip: int = Field(default=0, description="Number of records skipped")
    limit: int = Field(default=100, description="Max records returned")
    has_more: bool = Field(default=False, description="More records available")
    by_author: Dict[str, int]


class SkillUsageSummary(BaseModel):
    """Usage summary for a single skill."""
    skill_id: str = Field(..., description="Skill identifier")
    skill_name: str = Field(..., description="Skill display name")
    usage_count: int = Field(default=0, description="Total times used in composition")
    last_used_at: Optional[datetime] = Field(None, description="Last composition time")


class SkillAnalyticsResponse(BaseModel):
    """Response for skill usage analytics."""
    most_used: List[SkillUsageSummary] = Field(
        default_factory=list,
        description="Top skills by usage count"
    )
    never_used: List[SkillUsageSummary] = Field(
        default_factory=list,
        description="Skills with zero usage"
    )
    total_compositions: int = Field(
        default=0,
        description="Sum of all skill usage counts"
    )
    total_skills: int = Field(default=0, description="Total skills in registry")


class SkillVersionListResponse(BaseModel):
    """Response for listing skill versions."""
    skill_id: str = Field(..., description="Skill identifier")
    versions: List[SkillVersion] = Field(..., description="Version history (newest first)")
    total: int = Field(..., description="Total number of versions")
    current_version: str = Field(..., description="Current (latest) version")


class PersonaVersionListResponse(BaseModel):
    """Response for listing persona versions."""
    persona_id: str = Field(..., description="Persona identifier")
    versions: List[PersonaVersion] = Field(..., description="Version history (newest first)")
    total: int = Field(..., description="Total number of versions")
    current_version: str = Field(..., description="Current (latest) version")


# ============ Catalog Models (Lightweight for Discovery) ============


class CatalogSkillEntry(BaseModel):
    """Lightweight skill entry for catalog discovery."""
    id: str = Field(..., description="Unique skill identifier")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="What this skill does")
    tags: List[str] = Field(default_factory=list, description="Tags for discovery")
    grants_tools: List[str] = Field(default_factory=list, description="Tool IDs this skill grants")
    dependencies: List[str] = Field(default_factory=list, description="Skill IDs automatically included")


class CatalogPersonaEntry(BaseModel):
    """Lightweight persona entry for catalog discovery."""
    id: str = Field(..., description="Unique persona identifier")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="What this persona does")
    skills: List[str] = Field(default_factory=list, description="Skill IDs this persona combines")
    grants_tools: List[str] = Field(default_factory=list, description="Aggregated tools from all skills")


class CatalogResponse(BaseModel):
    """Complete skill and persona catalog for discovery."""
    skills: List[CatalogSkillEntry] = Field(..., description="Available skills")
    personas: List[CatalogPersonaEntry] = Field(..., description="Available personas")
    total_skills: int = Field(default=0, description="Total skills available")
    total_personas: int = Field(default=0, description="Total personas available")
    skip: int = Field(default=0, description="Number of records skipped")
    limit: int = Field(default=100, description="Max records returned")
    has_more: bool = Field(default=False, description="More records available")


# ============ Persona Models ============


class Persona(BaseModel):
    """Persona definition - a pre-combined skill bundle for common work scenarios."""
    id: str = Field(..., description="Unique persona identifier")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="What this persona does")
    version: str = Field(default="1.0.0", description="Semantic version")
    author: str = Field(default="system", description="system or user:{id}")

    instructions: str = Field(..., description="CLAUDE.md instruction fragment for persona behavior")
    references_skills: List[str] = Field(default_factory=list, description="Skill IDs this persona combines")
    merged_instructions: str = Field(default="", description="Pre-merged instructions from all referenced skills")
    instructions_stale: bool = Field(default=False, description="True when referenced skills have changed and merged_instructions needs regeneration")
    tags: List[str] = Field(default_factory=list, description="Tags for discovery")
    constraints: List[str] = Field(default_factory=list, description="What NOT to do")

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "fullstack-developer",
            "name": "Full-Stack Developer",
            "description": "Complete development capability",
            "version": "1.0.0",
            "author": "system",
            "instructions": "# Full-Stack Developer\n\nYou are a full-stack developer...",
            "references_skills": ["code-writer", "test-automator", "db-engineer"],
            "merged_instructions": "# Persona: Full-Stack Developer\n\n## Skills\n...",
            "tags": ["development", "full-stack"],
            "constraints": ["Follow project conventions"]
        }
    })


class PersonaCreateRequest(BaseModel):
    """Request to create a new persona."""
    id: str = Field(..., description="Unique persona ID")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Persona description")
    instructions: str = Field(..., description="CLAUDE.md instruction fragment")
    references_skills: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    version: str = Field(default="1.0.0")


class PersonaUpdateRequest(BaseModel):
    """Request to update a persona."""
    name: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    references_skills: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    constraints: Optional[List[str]] = None
    version: Optional[str] = None
    changelog: Optional[str] = Field(None, description="Description of changes for version history")


class PersonaListResponse(BaseModel):
    """Response for listing personas."""
    personas: List[Persona]
    total: int
    skip: int = Field(default=0, description="Number of records skipped")
    limit: int = Field(default=100, description="Max records returned")
    has_more: bool = Field(default=False, description="More records available")
    by_author: Dict[str, int]


class ExpandedPersona(BaseModel):
    """Persona expanded with its constituent skills."""
    persona: Persona = Field(..., description="The persona definition")
    skills: List[Skill] = Field(default_factory=list, description="Expanded skill objects")
    missing_skills: List[str] = Field(default_factory=list, description="Skill IDs that could not be found")


# ============ Tool Authorization Models ============


class ComputeInfo(BaseModel):
    """Compute instance information for authorization checks."""
    instance_id: str = Field(..., description="Compute instance identifier")
    labels: List[str] = Field(
        default_factory=list,
        description="Routing labels (e.g., production-access)"
    )
    tools_available: List[str] = Field(
        default_factory=list,
        description="Specialized tools available on this compute"
    )


class AuthorizationFailure(str, Enum):
    """Specific reason for authorization failure."""
    TOOL_NOT_FOUND = "tool_not_found"
    AGENT_NOT_FOUND = "agent_not_found"
    SKILL_NOT_GRANTED = "skill_not_granted"
    COMPUTE_MISSING_TOOL = "compute_missing_tool"
    COMPUTE_MISSING_LABELS = "compute_missing_labels"


class ToolAuthorizationRequest(BaseModel):
    """Request to check tool authorization for an agent."""
    agent_id: str = Field(..., description="Agent instance identifier")
    tool_id: str = Field(..., description="Tool identifier to check")
    compute: Optional[ComputeInfo] = Field(
        None,
        description="Compute instance info for two-part authorization"
    )


class ToolAuthorizationResponse(BaseModel):
    """Response from tool authorization check."""
    authorized: bool = Field(..., description="Whether agent is authorized to use the tool")
    granted_by: List[str] = Field(
        default_factory=list,
        description="Skill IDs that grant access (for specialized tools)"
    )
    tool: Optional[ToolDefinition] = Field(None, description="Tool details if found")
    reason: str = Field(default="", description="Human-readable explanation")
    failure_type: Optional[AuthorizationFailure] = Field(
        None,
        description="Specific failure type when authorized=False"
    )
    skill_check_passed: bool = Field(
        default=False,
        description="Whether skill-level authorization passed"
    )
    compute_check_passed: Optional[bool] = Field(
        None,
        description="Whether compute-level authorization passed (None if not checked)"
    )
    missing_labels: List[str] = Field(
        default_factory=list,
        description="Labels required but not present on compute"
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "authorized": True,
            "granted_by": ["prod-deployment"],
            "tool": {
                "id": "deploy_prod",
                "name": "Deploy to Production",
                "tier": "specialized",
                "required_labels": ["production-access"]
            },
            "reason": "Agent has prod-deployment skill which grants deploy_prod",
            "failure_type": None,
            "skill_check_passed": True,
            "compute_check_passed": True,
            "missing_labels": []
        }
    })


class ToolListResponse(BaseModel):
    """Response for listing tools."""
    tools: List[ToolDefinition]
    total: int
    skip: int = Field(default=0, description="Number of records skipped")
    limit: int = Field(default=100, description="Max records returned")
    has_more: bool = Field(default=False, description="More records available")
    by_tier: Dict[str, int] = Field(default_factory=dict)


class AuthorizationAuditEntry(BaseModel):
    """Audit log entry for a tool authorization check."""
    id: str = Field(..., description="Unique audit entry identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the authorization check occurred"
    )
    agent_id: str = Field(..., description="Agent that requested authorization")
    tool_id: str = Field(..., description="Tool being authorized")
    compute_id: Optional[str] = Field(
        None,
        description="Compute instance involved (if provided)"
    )
    authorized: bool = Field(..., description="Whether authorization was granted")
    failure_type: Optional[AuthorizationFailure] = Field(
        None,
        description="Specific failure reason (if denied)"
    )
    granted_by: List[str] = Field(
        default_factory=list,
        description="Skills that granted access"
    )
    reason: str = Field(default="", description="Human-readable explanation")


class AuthorizationAuditQueryResponse(BaseModel):
    """Response for authorization audit log queries."""
    entries: List[AuthorizationAuditEntry] = Field(default_factory=list)
    total: int = Field(default=0, description="Total matching entries")
    skip: int = Field(default=0, description="Number of records skipped")
    limit: int = Field(default=100, description="Max records returned")
    has_more: bool = Field(default=False, description="More records available")
    failed_count: int = Field(
        default=0,
        description="Number of failed authorization attempts in result set"
    )


class AuthorizationAuditStats(BaseModel):
    """Summary statistics for authorization audit logs."""
    total_checks: int = Field(default=0, description="Total authorization checks logged")
    total_authorized: int = Field(default=0, description="Total authorized checks")
    total_denied: int = Field(default=0, description="Total denied checks")
    denial_rate: float = Field(default=0.0, description="Ratio of denied to total (0.0-1.0)")
    top_denied_tools: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Most frequently denied tools"
    )
    top_denied_agents: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Agents with most denials"
    )


class AgentCacheStats(BaseModel):
    """Statistics for the agent cache."""
    size: int = Field(..., description="Current number of agents in cache")
    max_size: int = Field(..., description="Maximum cache capacity")
    ttl_seconds: int = Field(..., description="Time-to-live for cached agents in seconds")
    evictions: int = Field(..., description="Total number of evictions since service start")
    hits: int = Field(..., description="Total cache hits since service start")
    misses: int = Field(..., description="Total cache misses since service start")
    hit_rate: float = Field(..., description="Cache hit rate (0.0 to 1.0)")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "size": 150,
            "max_size": 10000,
            "ttl_seconds": 86400,
            "evictions": 25,
            "hits": 1000,
            "misses": 50,
            "hit_rate": 0.95
        }
    })
