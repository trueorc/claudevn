"""Characterization stage data models.

The characterization stage is the critical translation layer between raw
decomposed tasks and plannable work. Every task passes through characterization
before entering the planner's backlog.

For each work item, characterization produces:
  A. Universal ontology tags (fixed vocabulary)
  B. Project-specific semantic tags (adaptive domain clusters)
  C. Meaning assessments (business, technical, contextual)
  D. Contextual dependencies (semantic relationships beyond parent/child)

Reference: docs/work_management_framework.md — Section 5
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from models.ontology import OntologyTags


# =============================================================================
# Meaning Assessment Enums
# =============================================================================


class ContextualRole(str, Enum):
    """The role a work item plays in the broader project context."""
    FOUNDATIONAL = "foundational"   # Core building block other work depends on
    INCREMENTAL = "incremental"     # Adds to existing capability
    ENABLING = "enabling"           # Unblocks or enables other work
    BLOCKING = "blocking"           # Currently blocking progress elsewhere


# =============================================================================
# Meaning Assessment Models (Section 5.1C)
# =============================================================================


class BusinessMeaning(BaseModel):
    """What a task contributes to product, UX, or business outcome.

    Assessed independently of other tasks — intrinsic business value.
    """
    summary: str = Field(
        ...,
        description="Brief description of business contribution"
    )
    user_impact: str = Field(
        default="",
        description="How this affects end users"
    )
    business_value: str = Field(
        default="",
        description="Revenue, retention, compliance, or strategic value"
    )


class TechnicalMeaning(BaseModel):
    """What a task accomplishes technically.

    What it builds, fixes, validates, or enables from an engineering perspective.
    """
    summary: str = Field(
        ...,
        description="Brief description of technical accomplishment"
    )
    components_affected: List[str] = Field(
        default_factory=list,
        description="System components this work touches"
    )
    technical_risk: str = Field(
        default="",
        description="Technical risk assessment (complexity, unknowns)"
    )


class ContextualMeaning(BaseModel):
    """The role a task plays given everything else in the project.

    Requires awareness of the full work topology.
    """
    summary: str = Field(
        ...,
        description="Brief description of contextual role"
    )
    role: ContextualRole = Field(
        ...,
        description="Structural role in the project"
    )
    related_work_summary: str = Field(
        default="",
        description="How this relates to other active work"
    )


class MeaningAssessment(BaseModel):
    """Combined meaning assessment for a work item (all three dimensions)."""
    business: BusinessMeaning = Field(..., description="Business meaning")
    technical: TechnicalMeaning = Field(..., description="Technical meaning")
    contextual: ContextualMeaning = Field(..., description="Contextual meaning")


# =============================================================================
# Contextual Dependency Models (Section 5.1D)
# =============================================================================


class DependencyType(str, Enum):
    """Classification of dependency relationships."""
    STRUCTURAL = "structural"   # Hard prerequisite — must complete first
    CONTEXTUAL = "contextual"   # Soft — related, beneficial to sequence together


class DependencyRelation(str, Enum):
    """The nature of the relationship between work items."""
    BLOCKS = "blocks"               # Target cannot start until source completes
    ENABLES = "enables"             # Completing source makes target easier/possible
    RELATED_TO = "related_to"       # Shared domain context, beneficial to co-schedule
    EXTENDS = "extends"             # Builds on work done by the related item
    CONFLICTS_WITH = "conflicts_with"  # May have merge conflicts or design tension


class ContextualDependency(BaseModel):
    """A dependency relationship discovered during characterization.

    Goes beyond explicit parent/child — includes semantic relationships
    discovered by analyzing the work in project context.
    """
    target_item_id: str = Field(
        ...,
        description="ID of the related work item"
    )
    relation: DependencyRelation = Field(
        ...,
        description="Nature of the relationship"
    )
    dependency_type: DependencyType = Field(
        ...,
        description="Structural (hard) or contextual (soft)"
    )
    reasoning: str = Field(
        default="",
        description="Why this relationship was identified"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence in this dependency (0.0-1.0)"
    )


# =============================================================================
# Characterization Result (the full output for one work item)
# =============================================================================


class CharacterizationStatus(str, Enum):
    """Status of characterization for a work item."""
    PENDING = "pending"           # Not yet characterized
    IN_PROGRESS = "in_progress"   # Characterization running
    COMPLETED = "completed"       # Successfully characterized
    FAILED = "failed"             # Characterization failed


class CharacterizationResult(BaseModel):
    """Complete characterization output for a single work item.

    This is the core output of the characterization stage, containing
    all four components described in the framework (Section 5.1).
    """
    # Identity
    item_id: str = Field(..., description="Work item being characterized")
    project_id: str = Field(..., description="Project context")

    # A. Ontology tags (Layer 1 + Layer 2) — None while PENDING
    ontology_tags: Optional[OntologyTags] = Field(
        None,
        description="Universal and project-specific tags (populated during characterization)"
    )

    # B. (Project-specific tags are included in ontology_tags.project_specific)

    # C. Meaning assessments — None while PENDING
    meaning: Optional[MeaningAssessment] = Field(
        None,
        description="Business, technical, and contextual meaning (populated during characterization)"
    )

    # D. Contextual dependencies
    dependencies: List[ContextualDependency] = Field(
        default_factory=list,
        description="Discovered dependency relationships"
    )

    # Characterization metadata
    status: CharacterizationStatus = Field(
        default=CharacterizationStatus.COMPLETED,
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall confidence in characterization quality"
    )
    characterizer_version: str = Field(
        default="1.0",
        description="Version of the characterization pipeline"
    )
    error: Optional[str] = Field(
        None,
        description="Error message if characterization failed"
    )

    # Evaluation frames
    evaluated_in_isolation: bool = Field(
        default=True,
        description="Whether the item was evaluated on its own merits"
    )
    evaluated_in_context: bool = Field(
        default=False,
        description="Whether the item was evaluated against existing work topology"
    )
    topology_item_count: int = Field(
        default=0,
        description="Number of existing characterized items in topology at evaluation time"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def structural_dependencies(self) -> List[ContextualDependency]:
        """Get only hard/structural dependencies."""
        return [d for d in self.dependencies if d.dependency_type == DependencyType.STRUCTURAL]

    @property
    def contextual_dependencies_only(self) -> List[ContextualDependency]:
        """Get only soft/contextual dependencies."""
        return [d for d in self.dependencies if d.dependency_type == DependencyType.CONTEXTUAL]


# =============================================================================
# Batch Characterization Models
# =============================================================================


class CharacterizationRequest(BaseModel):
    """Request to characterize a single work item."""
    item_id: str = Field(..., description="Work item to characterize")
    project_id: str = Field(..., description="Project context for Layer 2 tags")
    title: str = Field(..., description="Work item title")
    description: str = Field(..., description="Work item description")
    # Optional hints from decomposition
    issue_type_hint: Optional[str] = Field(None, description="Hint from decomposer (e.g., 'feature')")
    area_hint: Optional[str] = Field(None, description="Hint from decomposer (e.g., 'api')")
    parent_item_id: Optional[str] = Field(None, description="Parent item if known")


class BatchCharacterizationRequest(BaseModel):
    """Request to characterize multiple work items (e.g., from a decomposition batch)."""
    project_id: str = Field(..., description="Project context")
    items: List[CharacterizationRequest] = Field(
        ...,
        min_length=1,
        description="Work items to characterize"
    )
    source_goal_id: Optional[str] = Field(None, description="Goal that produced these items")


class BatchCharacterizationResponse(BaseModel):
    """Response for batch characterization."""
    project_id: str
    results: List[CharacterizationResult] = Field(default_factory=list)
    total: int = 0
    completed: int = 0
    failed: int = 0
    new_clusters_created: List[str] = Field(
        default_factory=list,
        description="New domain cluster IDs created during characterization"
    )


# =============================================================================
# Work Topology Models (read-access for in-context evaluation)
# =============================================================================


class TopologyItem(BaseModel):
    """A summarized view of a characterized work item in the topology.

    Used by the characterizer when evaluating new items in project context.
    Contains only the information needed for comparison, not full details.
    """
    item_id: str = Field(..., description="Work item ID")
    title: str = Field(..., description="Work item title")
    description_summary: str = Field(
        default="",
        description="Abbreviated description (first ~200 chars)"
    )
    ontology_tags: OntologyTags = Field(..., description="Assigned ontology tags")
    contextual_role: ContextualRole = Field(..., description="Role in the project")
    cluster_ids: List[str] = Field(default_factory=list, description="Domain cluster IDs")
    status: str = Field(default="", description="Current work status")


class WorkTopology(BaseModel):
    """The full set of characterized work in the system for a project.

    The characterizer needs read access to this when evaluating new items
    'in project context' (Section 5.2, frame 2).
    """
    project_id: str = Field(..., description="Project this topology belongs to")
    items: List[TopologyItem] = Field(default_factory=list)
    cluster_names: List[str] = Field(
        default_factory=list,
        description="Active domain cluster names"
    )

    @property
    def item_count(self) -> int:
        return len(self.items)

    @property
    def items_by_cluster(self) -> Dict[str, List[TopologyItem]]:
        """Group topology items by cluster ID."""
        result: Dict[str, List[TopologyItem]] = {}
        for item in self.items:
            for cid in item.cluster_ids:
                if cid not in result:
                    result[cid] = []
                result[cid].append(item)
        return result
