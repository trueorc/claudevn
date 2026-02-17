"""Two-layer ontology system for structured work characterization.

Layer 1 — Universal (fixed, cross-project):
  Work type, lifecycle stage, technical domain.
  Predefined categories that apply to any software project.

Layer 2 — Project-Specific (seeded, adaptive):
  Domain clusters seeded from initial decomposition.
  Grows as new goals introduce new capability areas.
  Categories may consolidate over time.

Reference: docs/work_management_framework.md — Section 6
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Layer 1 — Universal Ontology (fixed, cross-project)
# =============================================================================


class WorkType(str, Enum):
    """Type of work being performed. Fixed across all projects."""
    FEATURE = "feature"
    BUG_FIX = "bug_fix"
    REFACTOR = "refactor"
    TEST = "test"
    DOCUMENTATION = "documentation"
    INFRASTRUCTURE = "infrastructure"
    INTEGRATION = "integration"


class LifecycleStage(str, Enum):
    """Stage in the work lifecycle. Fixed across all projects."""
    DESIGN = "design"
    BUILD = "build"
    TEST = "test"
    VALIDATE = "validate"
    DEPLOY = "deploy"


class TechnicalDomain(str, Enum):
    """Technical domain of the work. Fixed across all projects."""
    FRONTEND = "frontend"
    BACKEND = "backend"
    DATA = "data"
    API = "api"
    SECURITY = "security"
    DEVOPS = "devops"
    TESTING = "testing"
    DOCUMENTATION = "documentation"


class UniversalTags(BaseModel):
    """Layer 1 ontology tags — fixed vocabulary for deterministic filtering.

    Every work item gets tagged with these. The planner uses them for
    broad-stroke decisions like "prioritize all testing" or "deprioritize
    new feature development".
    """
    work_type: WorkType = Field(..., description="Primary work type classification")
    lifecycle_stage: LifecycleStage = Field(..., description="Current lifecycle stage")
    technical_domains: List[TechnicalDomain] = Field(
        ...,
        description="Technical domains involved (may span multiple, at least one required)"
    )

    @field_validator('technical_domains')
    @classmethod
    def at_least_one_domain(cls, v: List[TechnicalDomain]) -> List[TechnicalDomain]:
        if not v:
            raise ValueError('At least one technical domain is required')
        return v


# =============================================================================
# Layer 2 — Project-Specific Ontology (seeded, adaptive)
# =============================================================================


class DomainClusterStatus(str, Enum):
    """Status of a project-specific domain cluster."""
    ACTIVE = "active"          # In use, receiving new work
    CONSOLIDATED = "consolidated"  # Merged into another cluster
    ARCHIVED = "archived"      # No longer receiving work


class DomainCluster(BaseModel):
    """A project-specific domain cluster.

    Seeded from initial decomposition and grows as new goals introduce
    new capability areas. May consolidate over time.
    """
    cluster_id: str = Field(..., description="Unique cluster identifier")
    name: str = Field(..., description="Human-readable cluster name (e.g., 'payment processing')")
    description: str = Field(default="", description="What this domain cluster covers")
    status: DomainClusterStatus = Field(default=DomainClusterStatus.ACTIVE)

    # Evolution tracking
    created_from: Optional[str] = Field(
        None,
        description="Goal ID or work item ID that seeded this cluster"
    )
    consolidated_into: Optional[str] = Field(
        None,
        description="Cluster ID this was merged into (if consolidated)"
    )

    # Usage stats for evolution decisions
    work_item_count: int = Field(default=0, description="Number of work items tagged with this cluster")
    work_item_ids: List[str] = Field(
        default_factory=list,
        description="IDs of work items tagged with this cluster"
    )
    last_activity_at: Optional[datetime] = Field(
        None,
        description="When this cluster last had a work item added"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvolutionEventType(str, Enum):
    """Types of ontology evolution events."""
    CLUSTER_CREATED = "cluster_created"
    CLUSTER_CONSOLIDATED = "cluster_consolidated"
    CLUSTER_ARCHIVED = "cluster_archived"
    CLUSTER_RENAMED = "cluster_renamed"
    CLUSTER_AUTO_CREATED = "cluster_auto_created"
    CLUSTER_AUTO_CONSOLIDATED = "cluster_auto_consolidated"
    STALE_FLAGGED = "stale_flagged"


class ClusterEvolutionEvent(BaseModel):
    """A recorded event in the ontology evolution history."""
    event_id: str = Field(..., description="Unique event identifier")
    event_type: EvolutionEventType = Field(..., description="Type of evolution event")
    cluster_id: str = Field(..., description="Primary cluster involved")
    related_cluster_ids: List[str] = Field(
        default_factory=list,
        description="Other clusters involved (e.g., source clusters in a merge)"
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific details (e.g., old_name, new_name for rename)"
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ClusterMaturity(str, Enum):
    """Maturity level of a cluster based on activity and age."""
    NASCENT = "nascent"        # Recently created, few items
    GROWING = "growing"        # Actively receiving work
    MATURE = "mature"          # Stable, consistent work flow
    STALE = "stale"            # No recent activity


class ClusterHealthMetrics(BaseModel):
    """Health metrics for a single domain cluster."""
    cluster_id: str
    cluster_name: str
    status: DomainClusterStatus
    member_count: int = Field(description="Number of work items")
    maturity: ClusterMaturity
    age_days: float = Field(description="Days since cluster creation")
    days_since_last_activity: Optional[float] = Field(
        None,
        description="Days since last work item was added"
    )
    is_stale: bool = Field(default=False, description="Whether cluster is flagged as stale")


class MergeCandidate(BaseModel):
    """A pair of clusters detected as potential merge candidates."""
    cluster_a_id: str
    cluster_a_name: str
    cluster_b_id: str
    cluster_b_name: str
    similarity_score: float = Field(
        description="Similarity score between 0.0 and 1.0"
    )
    reason: str = Field(description="Why these clusters are merge candidates")


class ConsolidationSuggestionStatus(str, Enum):
    """Status of a consolidation suggestion."""
    PENDING = "pending"
    APPROVED = "approved"
    DISMISSED = "dismissed"


class ConsolidationSuggestion(BaseModel):
    """A suggestion to consolidate two clusters based on usage patterns."""
    suggestion_id: str = Field(..., description="Unique suggestion identifier")
    cluster_a_id: str
    cluster_a_name: str
    cluster_b_id: str
    cluster_b_name: str
    composite_score: float = Field(description="Weighted composite similarity score (0.0-1.0)")
    name_similarity: float = Field(description="Name-based similarity score (0.0-1.0)")
    work_item_overlap: float = Field(description="Jaccard similarity of shared work items (0.0-1.0)")
    shared_item_count: int = Field(default=0, description="Number of work items shared between clusters")
    status: ConsolidationSuggestionStatus = Field(
        default=ConsolidationSuggestionStatus.PENDING
    )
    suggested_target_id: str = Field(
        description="Recommended target cluster (the one with more work items)"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectOntology(BaseModel):
    """Layer 2 ontology state for a specific project.

    Contains all domain clusters and their evolution history.
    Stored per-project in Redis.
    """
    project_id: str = Field(..., description="Project this ontology belongs to")
    clusters: Dict[str, DomainCluster] = Field(
        default_factory=dict,
        description="Active domain clusters keyed by cluster_id"
    )
    evolution_history: List[ClusterEvolutionEvent] = Field(
        default_factory=list,
        description="History of evolution events for this ontology"
    )
    consolidation_suggestions: List[ConsolidationSuggestion] = Field(
        default_factory=list,
        description="Pending consolidation suggestions from automatic detection"
    )
    unclassified_count: int = Field(
        default=0,
        description="Number of items that could not be classified into existing clusters"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def active_clusters(self) -> Dict[str, DomainCluster]:
        """Get only active (non-consolidated, non-archived) clusters."""
        return {
            k: v for k, v in self.clusters.items()
            if v.status == DomainClusterStatus.ACTIVE
        }

    @property
    def cluster_names(self) -> List[str]:
        """Get names of all active clusters."""
        return [c.name for c in self.active_clusters.values()]


class ProjectSpecificTags(BaseModel):
    """Layer 2 ontology tags — adaptive, project-scoped.

    Applied to work items to indicate which project-specific domain
    clusters they belong to.
    """
    cluster_ids: List[str] = Field(
        default_factory=list,
        description="Domain cluster IDs this work item belongs to"
    )


# =============================================================================
# Combined Ontology Tags (applied to work items)
# =============================================================================


class OntologyTags(BaseModel):
    """Complete ontology tags for a work item — both layers combined.

    This is the tag structure applied to each characterized work item
    before it enters the planner's backlog.
    """
    universal: UniversalTags = Field(..., description="Layer 1 fixed tags")
    project_specific: ProjectSpecificTags = Field(
        default_factory=ProjectSpecificTags,
        description="Layer 2 adaptive tags"
    )


# =============================================================================
# Ontology Weights (used by Planner profile)
# =============================================================================


class OntologyWeights(BaseModel):
    """Weights the planner assigns to ontology categories.

    Used in the planner's dynamic profile to express current priorities.
    Values range from 0.0 (deprioritized) to 1.0 (highest priority).
    """
    # Layer 1 weights
    work_type_weights: Dict[str, float] = Field(
        default_factory=dict,
        description="Weight per WorkType value (0.0-1.0)"
    )
    lifecycle_stage_weights: Dict[str, float] = Field(
        default_factory=dict,
        description="Weight per LifecycleStage value (0.0-1.0)"
    )
    technical_domain_weights: Dict[str, float] = Field(
        default_factory=dict,
        description="Weight per TechnicalDomain value (0.0-1.0)"
    )

    # Layer 2 weights
    cluster_weights: Dict[str, float] = Field(
        default_factory=dict,
        description="Weight per cluster_id (0.0-1.0)"
    )

    @field_validator(
        'work_type_weights',
        'lifecycle_stage_weights',
        'technical_domain_weights',
        'cluster_weights',
    )
    @classmethod
    def weights_in_range(cls, v: Dict[str, float]) -> Dict[str, float]:
        for key, weight in v.items():
            if not 0.0 <= weight <= 1.0:
                raise ValueError(f'Weight for {key} must be between 0.0 and 1.0, got {weight}')
        return v

    def get_work_type_weight(self, work_type: WorkType) -> float:
        """Get weight for a work type, defaulting to 0.5."""
        return self.work_type_weights.get(work_type.value, 0.5)

    def get_lifecycle_stage_weight(self, stage: LifecycleStage) -> float:
        """Get weight for a lifecycle stage, defaulting to 0.5."""
        return self.lifecycle_stage_weights.get(stage.value, 0.5)

    def get_technical_domain_weight(self, domain: TechnicalDomain) -> float:
        """Get weight for a technical domain, defaulting to 0.5."""
        return self.technical_domain_weights.get(domain.value, 0.5)

    def get_cluster_weight(self, cluster_id: str) -> float:
        """Get weight for a project-specific cluster, defaulting to 0.5."""
        return self.cluster_weights.get(cluster_id, 0.5)


# =============================================================================
# Migration helpers — map legacy enums to ontology values
# =============================================================================


ISSUE_TYPE_TO_WORK_TYPE: Dict[str, WorkType] = {
    "feature": WorkType.FEATURE,
    "bug": WorkType.BUG_FIX,
    "refactor": WorkType.REFACTOR,
    "docs": WorkType.DOCUMENTATION,
    "test": WorkType.TEST,
}

ISSUE_AREA_TO_TECHNICAL_DOMAIN: Dict[str, TechnicalDomain] = {
    "api": TechnicalDomain.API,
    "database": TechnicalDomain.DATA,
    "frontend": TechnicalDomain.FRONTEND,
    "infra": TechnicalDomain.DEVOPS,
    "other": TechnicalDomain.BACKEND,  # Default fallback
}


# =============================================================================
# Request/Response Models
# =============================================================================


class DomainClusterCreateRequest(BaseModel):
    """Request to create a new domain cluster."""
    name: str = Field(..., min_length=1, max_length=100, description="Cluster name")
    description: str = Field(default="", description="What this cluster covers")
    created_from: Optional[str] = Field(None, description="Goal or work item ID that seeded this")


class DomainClusterUpdateRequest(BaseModel):
    """Request to update a domain cluster."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    status: Optional[DomainClusterStatus] = None
    consolidated_into: Optional[str] = None


class ConsolidateClustersRequest(BaseModel):
    """Request to merge source clusters into a target cluster."""
    source_cluster_ids: List[str] = Field(
        ...,
        min_length=1,
        description="Cluster IDs to consolidate"
    )
    target_cluster_id: str = Field(..., description="Cluster ID to merge into")


class ProjectOntologyResponse(BaseModel):
    """Response for project ontology state."""
    project_id: str
    clusters: List[DomainCluster]
    active_count: int
    consolidated_count: int
    archived_count: int
    unclassified_count: int = 0
    evolution_event_count: int = 0


class ClusterHealthResponse(BaseModel):
    """Response for cluster health metrics across a project."""
    project_id: str
    metrics: List[ClusterHealthMetrics]
    stale_count: int
    total_active: int


class EvolutionHistoryResponse(BaseModel):
    """Response for ontology evolution history."""
    project_id: str
    events: List[ClusterEvolutionEvent]
    total: int


class MergeCandidatesResponse(BaseModel):
    """Response for detected merge candidates."""
    project_id: str
    candidates: List[MergeCandidate]
    total: int


class ReportUnclassifiedRequest(BaseModel):
    """Request to report items that could not be classified."""
    item_ids: List[str] = Field(
        ...,
        min_length=1,
        description="IDs of work items that could not be classified"
    )
    suggested_cluster_name: Optional[str] = Field(
        None,
        description="Suggested name for a new cluster if auto-creation is triggered"
    )
    suggested_description: Optional[str] = Field(
        None,
        description="Suggested description for a new cluster"
    )


class ConsolidationSuggestionsResponse(BaseModel):
    """Response for consolidation suggestions."""
    project_id: str
    suggestions: List[ConsolidationSuggestion]
    pending_count: int
    total: int


class DetectConsolidationResponse(BaseModel):
    """Response from running consolidation detection."""
    project_id: str
    new_suggestions: List[ConsolidationSuggestion]
    new_count: int
