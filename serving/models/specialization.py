"""Data models for worker specialization boundary management.

Defines per-worker specialization profiles that tie compute instances to
domain clusters from the project ontology. Supports utilization tracking
and imbalance detection.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ImbalanceSeverity(str, Enum):
    """Severity of a specialization imbalance."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SpecializationProfile(BaseModel):
    """Per-worker specialization profile.

    Links a compute instance to domain clusters from the project ontology,
    defining which types of work it should preferentially receive.
    """
    compute_id: str = Field(..., description="Compute instance ID")
    project_id: str = Field(..., description="Project ID this profile applies to")
    cluster_ids: List[str] = Field(
        default_factory=list,
        description="Ontology cluster IDs this worker specializes in"
    )
    preferred_work_types: List[str] = Field(
        default_factory=list,
        description="Preferred work types (e.g., 'bug_fix', 'feature', 'refactor')"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class UtilizationRecord(BaseModel):
    """Tracks utilization of a worker within a specific domain cluster."""
    compute_id: str = Field(..., description="Compute instance ID")
    cluster_id: str = Field(..., description="Domain cluster ID")
    tasks_completed: int = Field(default=0, description="Number of tasks completed")
    tasks_in_progress: int = Field(default=0, description="Number of tasks currently in progress")
    last_completed_at: Optional[datetime] = Field(
        None, description="Timestamp of last completion in this cluster"
    )


class SpecializationImbalance(BaseModel):
    """Detected imbalance in specialization coverage or utilization."""
    cluster_id: str = Field(..., description="Affected cluster ID")
    cluster_name: str = Field(default="", description="Human-readable cluster name")
    assigned_compute_ids: List[str] = Field(
        default_factory=list,
        description="Compute IDs specialized for this cluster"
    )
    unassigned_compute_ids: List[str] = Field(
        default_factory=list,
        description="Compute IDs NOT specialized for this cluster"
    )
    utilization_ratio: float = Field(
        default=0.0,
        description="Ratio of work in this cluster vs total (0.0-1.0)"
    )
    severity: ImbalanceSeverity = Field(
        default=ImbalanceSeverity.LOW,
        description="Severity of the imbalance"
    )
    description: str = Field(default="", description="Human-readable description")


class SpecializationSummary(BaseModel):
    """Summary of specialization state for a project."""
    project_id: str = Field(..., description="Project ID")
    profiles: List[SpecializationProfile] = Field(
        default_factory=list, description="All specialization profiles"
    )
    utilization: Dict[str, List[UtilizationRecord]] = Field(
        default_factory=dict,
        description="Utilization records keyed by compute_id"
    )
    imbalances: List[SpecializationImbalance] = Field(
        default_factory=list, description="Detected imbalances"
    )
    total_workers: int = Field(default=0, description="Total workers with profiles")
    total_clusters_covered: int = Field(default=0, description="Number of clusters covered")


class SpecializationProfileRequest(BaseModel):
    """Request to set or update a specialization profile."""
    cluster_ids: List[str] = Field(
        ..., description="Ontology cluster IDs this worker should specialize in"
    )
    preferred_work_types: List[str] = Field(
        default_factory=list,
        description="Preferred work types (optional)"
    )
