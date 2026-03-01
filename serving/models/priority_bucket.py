"""Priority bucket tree data structure for work management.

Replaces flat ranked lists with a hierarchical priority bucket tree where
buckets represent strategic groupings defined by the current planner profile.

Key properties:
- Buckets cut across the ontology (tasks from multiple domains in one bucket)
- Buckets are ranked against each other (macro-level priority)
- Tasks within each bucket are ordered by dependency readiness, ontology
  weights, and contextual priority
- When the planner profile shifts, bucket boundaries redefine — tasks
  redistribute based on new bucket definitions

Reference: docs/work_management_framework.md — Sections 7.3, 7.4
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# Bucket Membership Criteria
# =============================================================================


class BucketCriterionType(str, Enum):
    """Types of criteria that determine bucket membership.

    Criteria can reference ontology tags, work item state, or
    contextual conditions. Multiple criteria on a bucket are ANDed
    unless grouped via MATCH_ANY.
    """
    WORK_TYPE_IN = "work_type_in"
    LIFECYCLE_STAGE_IN = "lifecycle_stage_in"
    TECHNICAL_DOMAIN_IN = "technical_domain_in"
    CLUSTER_IN = "cluster_in"
    WEIGHT_ABOVE = "weight_above"
    WEIGHT_BELOW = "weight_below"
    COMPLETION_ABOVE = "completion_above"
    COMPLETION_BELOW = "completion_below"
    IS_BLOCKING = "is_blocking"
    IS_BLOCKED = "is_blocked"
    DEPENDENCY_READY = "dependency_ready"
    MATCH_ANY = "match_any"


class BucketCriterion(BaseModel):
    """A single criterion for bucket membership.

    Buckets define their membership through criteria that reference
    ontology tags, work item state, or contextual conditions.
    Multiple criteria on a bucket are ANDed by default.
    Use MATCH_ANY with nested criteria for OR logic.
    """
    criterion_type: BucketCriterionType = Field(
        ...,
        description="Type of membership criterion"
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the criterion (e.g., {'values': ['test', 'bug_fix']})"
    )
    nested: List["BucketCriterion"] = Field(
        default_factory=list,
        description="Nested criteria (used with MATCH_ANY for OR logic)"
    )


class BucketDefinition(BaseModel):
    """Defines what a bucket represents and how items qualify for it.

    A bucket definition captures the strategic purpose and the
    inclusion criteria. Criteria cut across the ontology — a single
    bucket may match tasks from multiple domains and work types.
    """
    name: str = Field(
        ...,
        description="Human-readable strategic label (e.g., 'Validate what is built')"
    )
    description: str = Field(
        default="",
        description="Detailed explanation of the bucket's strategic purpose"
    )
    criteria: List[BucketCriterion] = Field(
        default_factory=list,
        description="Membership criteria (ANDed together)"
    )
    is_default: bool = Field(
        default=False,
        description="If True, catches items that don't match any other bucket"
    )


# =============================================================================
# Intra-Bucket Ordering
# =============================================================================


class ItemReadiness(str, Enum):
    """Dependency readiness state of a work item within a bucket."""
    READY = "ready"
    BLOCKED = "blocked"
    PARTIALLY_BLOCKED = "partially_blocked"


class BucketItem(BaseModel):
    """A work item placed within a priority bucket.

    Contains the item reference and ordering metadata used for
    intra-bucket sorting: dependency readiness, computed priority
    score, and contextual signals.
    """
    item_id: str = Field(..., description="Work item / issue temp_id")
    readiness: ItemReadiness = Field(
        default=ItemReadiness.BLOCKED,
        description="Current dependency readiness state"
    )
    priority_score: float = Field(
        default=0.0,
        description="Computed priority score from ontology weights (higher = more priority)"
    )
    blocking_count: int = Field(
        default=0,
        ge=0,
        description="Number of other items this item blocks"
    )
    completion_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Estimated completion percentage (0.0-1.0)"
    )
    context_affinity_worker: Optional[str] = Field(
        default=None,
        description="Worker ID with context affinity for this item"
    )

    @property
    def sort_key(self) -> tuple:
        """Sort key for intra-bucket ordering.

        Priority: readiness (ready first) > blocking_count (high first) >
        priority_score (high first) > completion_pct (high first, finish what's started)
        """
        readiness_order = {
            ItemReadiness.READY: 0,
            ItemReadiness.PARTIALLY_BLOCKED: 1,
            ItemReadiness.BLOCKED: 2,
        }
        return (
            readiness_order.get(self.readiness, 2),
            -self.blocking_count,
            -self.priority_score,
            -self.completion_pct,
        )


# =============================================================================
# Priority Bucket
# =============================================================================


class PriorityBucket(BaseModel):
    """A ranked bucket in the priority bucket tree.

    Contains a strategic definition and ordered work items.
    Buckets are ranked by their rank field (lower = higher priority).
    """
    bucket_id: str = Field(..., description="Unique bucket identifier")
    rank: int = Field(
        ...,
        ge=1,
        description="Bucket rank (1 = highest priority)"
    )
    definition: BucketDefinition = Field(
        ...,
        description="What this bucket represents and membership criteria"
    )
    items: List[BucketItem] = Field(
        default_factory=list,
        description="Work items in this bucket, ordered by intra-bucket priority"
    )

    @property
    def ready_items(self) -> List[BucketItem]:
        """Get items that are dependency-ready for assignment."""
        return [i for i in self.items if i.readiness == ItemReadiness.READY]

    @property
    def blocked_items(self) -> List[BucketItem]:
        """Get items that are currently blocked."""
        return [
            i for i in self.items
            if i.readiness in (ItemReadiness.BLOCKED, ItemReadiness.PARTIALLY_BLOCKED)
        ]

    @property
    def item_count(self) -> int:
        """Total number of items in this bucket."""
        return len(self.items)

    def sort_items(self) -> None:
        """Sort items by intra-bucket ordering rules.

        Ordering: ready items first, then by blocking count (desc),
        priority score (desc), completion percentage (desc).
        """
        self.items.sort(key=lambda item: item.sort_key)


# =============================================================================
# Bucket Reorganization
# =============================================================================


class ReorganizationTriggerType(str, Enum):
    """What caused bucket boundaries to be redefined."""
    PROFILE_SHIFT = "profile_shift"
    NEW_ITEMS_ADDED = "new_items_added"
    ITEMS_COMPLETED = "items_completed"
    DEPENDENCY_RESOLVED = "dependency_resolved"
    RESOURCE_CHANGE = "resource_change"
    MANUAL = "manual"


class ReorganizationEvent(BaseModel):
    """Record of a bucket reorganization.

    When the planner profile shifts, bucket boundaries change —
    not individual task scores. Tasks fall into different buckets
    because the definition of what each bucket represents has changed.
    """
    event_id: str = Field(..., description="Unique event identifier")
    trigger_type: ReorganizationTriggerType = Field(
        ...,
        description="What caused this reorganization"
    )
    trigger_source_id: str = Field(
        default="",
        description="ID of the goal, worker, or resource that triggered it"
    )
    description: str = Field(
        default="",
        description="Human-readable description of what changed"
    )
    buckets_added: int = Field(default=0, ge=0)
    buckets_removed: int = Field(default=0, ge=0)
    items_moved: int = Field(default=0, ge=0)
    items_preserved: int = Field(
        default=0,
        ge=0,
        description="Number of in-progress items protected during reorganization"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ItemMovement(BaseModel):
    """Record of a single item's movement between buckets during reorganization."""
    item_id: str = Field(..., description="Work item that moved")
    from_bucket_id: str = Field(..., description="Source bucket ID")
    to_bucket_id: str = Field(..., description="Destination bucket ID")


class ReorganizationResult(BaseModel):
    """Complete result of a bucket reorganization operation.

    Contains the new tree, the event record, and detailed movement
    information for auditing and traceability.
    """
    tree: "BucketTree" = Field(..., description="The reorganized bucket tree")
    event: ReorganizationEvent = Field(..., description="Event record for this reorganization")
    items_moved_detail: List[ItemMovement] = Field(
        default_factory=list,
        description="Detailed movement records for each item that changed buckets"
    )
    items_preserved_ids: List[str] = Field(
        default_factory=list,
        description="IDs of in-progress items that were protected from movement"
    )
    previous_version: int = Field(
        default=0,
        description="Tree version before reorganization"
    )


# =============================================================================
# Bucket Tree (top-level)
# =============================================================================


class BucketTree(BaseModel):
    """The complete priority bucket tree for a project.

    Organizes work into ranked strategic buckets. This is the planner's
    primary output structure — replacing flat phase-based plans with
    a hierarchical grouping where buckets cut across the ontology.

    The tree maps to a work assignment queue by flattening: ready items
    from the highest-priority bucket are assigned first, then the next
    bucket, and so on.
    """
    tree_id: str = Field(..., description="Unique tree identifier")
    project_id: str = Field(..., description="Project this tree belongs to")
    profile_id: Optional[str] = Field(
        default=None,
        description="PlannerProfile ID that defined these buckets"
    )

    buckets: List[PriorityBucket] = Field(
        default_factory=list,
        description="Ranked priority buckets (sorted by rank)"
    )

    # Lifecycle
    reorganization_history: List[ReorganizationEvent] = Field(
        default_factory=list,
        description="History of bucket reorganizations"
    )
    version: int = Field(
        default=1,
        description="Tree version, incremented on each reorganization"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @model_validator(mode="after")
    def validate_bucket_ids_unique(self) -> "BucketTree":
        """Ensure all bucket IDs are unique within the tree."""
        bucket_ids = [b.bucket_id for b in self.buckets]
        if len(bucket_ids) != len(set(bucket_ids)):
            duplicates = [bid for bid in bucket_ids if bucket_ids.count(bid) > 1]
            raise ValueError(f"Duplicate bucket IDs: {set(duplicates)}")
        return self

    @model_validator(mode="after")
    def validate_ranks_unique(self) -> "BucketTree":
        """Ensure all bucket ranks are unique."""
        ranks = [b.rank for b in self.buckets]
        if len(ranks) != len(set(ranks)):
            duplicates = [r for r in ranks if ranks.count(r) > 1]
            raise ValueError(f"Duplicate bucket ranks: {set(duplicates)}")
        return self

    @model_validator(mode="after")
    def validate_at_most_one_default(self) -> "BucketTree":
        """Ensure at most one default bucket exists."""
        defaults = [b for b in self.buckets if b.definition.is_default]
        if len(defaults) > 1:
            raise ValueError(
                f"Multiple default buckets: "
                f"{[b.bucket_id for b in defaults]}"
            )
        return self

    def get_bucket(self, bucket_id: str) -> Optional[PriorityBucket]:
        """Get a bucket by its ID."""
        for bucket in self.buckets:
            if bucket.bucket_id == bucket_id:
                return bucket
        return None

    def get_ranked_buckets(self) -> List[PriorityBucket]:
        """Get buckets sorted by rank (highest priority first)."""
        return sorted(self.buckets, key=lambda b: b.rank)

    def get_assignment_queue(self) -> List[BucketItem]:
        """Flatten the tree into an ordered work assignment queue.

        Takes ready items from the highest-priority bucket first,
        then the next bucket, and so on. Within each bucket, items
        are ordered by intra-bucket priority. Deduplicates items that
        appear in multiple buckets (assigned from highest-priority bucket).
        """
        queue: List[BucketItem] = []
        seen_item_ids: set = set()
        for bucket in self.get_ranked_buckets():
            bucket.sort_items()
            for item in bucket.ready_items:
                if item.item_id not in seen_item_ids:
                    queue.append(item)
                    seen_item_ids.add(item.item_id)
        return queue

    def find_item(self, item_id: str) -> Optional[tuple]:
        """Find the highest-ranked bucket containing a given item.

        Returns:
            Tuple of (PriorityBucket, BucketItem) or None if not found.
            When an item exists in multiple buckets, returns from the
            highest-ranked (lowest rank number) bucket.
        """
        results = self.find_item_buckets(item_id)
        return results[0] if results else None

    def find_item_buckets(self, item_id: str) -> List[tuple]:
        """Find all buckets containing a given item.

        Supports multi-bucket membership where an item can appear in
        multiple buckets simultaneously.

        Returns:
            List of (PriorityBucket, BucketItem) tuples sorted by bucket rank,
            or empty list if not found.
        """
        results = []
        for bucket in self.get_ranked_buckets():
            for item in bucket.items:
                if item.item_id == item_id:
                    results.append((bucket, item))
        return results

    @property
    def total_items(self) -> int:
        """Total number of unique items across all buckets."""
        seen = set()
        for bucket in self.buckets:
            for item in bucket.items:
                seen.add(item.item_id)
        return len(seen)

    @property
    def total_ready(self) -> int:
        """Total number of ready items across all buckets."""
        return sum(len(b.ready_items) for b in self.buckets)

    @property
    def default_bucket(self) -> Optional[PriorityBucket]:
        """Get the default catch-all bucket, if any."""
        for bucket in self.buckets:
            if bucket.definition.is_default:
                return bucket
        return None
