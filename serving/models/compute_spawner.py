"""Models for Compute Spawner."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ComputeState(str, Enum):
    """State of a compute instance."""
    PENDING = "pending"        # Created, not yet started
    STARTING = "starting"      # Process being spawned
    RUNNING = "running"        # Active and working
    IDLE = "idle"              # Running but no work assigned
    STOPPING = "stopping"      # Shutdown initiated
    STOPPED = "stopped"        # Process terminated
    FAILED = "failed"          # Failed to start or crashed


class SpawnRequest(BaseModel):
    """Request to spawn a new compute instance."""
    # Identity
    compute_id: Optional[str] = Field(None, description="Optional custom ID, auto-generated if not provided")
    name: Optional[str] = Field(None, description="Human-readable name")

    # Capabilities
    skills: List[str] = Field(default_factory=list, description="Skill IDs to compose")
    capabilities: List[str] = Field(default_factory=list, description="Capability tags")
    labels: List[str] = Field(default_factory=list, description="Routing labels for work matching (e.g., production-access)")
    tools_available: List[str] = Field(default_factory=list, description="Specialized tools available (e.g., deploy_prod)")

    # Work assignment
    work_id: Optional[str] = Field(None, description="Immediately assign this work")
    project_id: Optional[str] = Field(None, description="Restrict to work from this project")

    # Git configuration
    repo_url: Optional[str] = Field(None, description="Repository URL to clone")
    base_branch: str = Field(default="main", description="Base branch to work from")

    # Resource limits
    max_concurrent_work: int = Field(default=1, ge=1, le=10, description="Max concurrent work items")
    idle_timeout: int = Field(default=300, ge=0, description="Seconds to wait idle before stopping (0=never)")


class SpawnedCompute(BaseModel):
    """A spawned compute instance."""
    compute_id: str
    name: str
    state: ComputeState

    # Process info
    pid: Optional[int] = None
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None

    # Configuration
    skills: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    labels: List[str] = Field(default_factory=list, description="Routing labels for work matching")
    tools_available: List[str] = Field(default_factory=list, description="Specialized tools available")
    project_id: Optional[str] = None

    # Serving connection
    serving_url: str
    api_key: str

    # Work tracking
    current_work: List[str] = Field(default_factory=list, description="Currently assigned work IDs")
    completed_work: int = 0
    failed_work: int = 0

    # Metrics
    last_heartbeat: Optional[datetime] = None
    last_work_started: Optional[datetime] = None
    last_work_completed: Optional[datetime] = None

    # Workspace
    workspace_path: Optional[str] = None
    worktree_active: Optional[str] = None


class SpawnResponse(BaseModel):
    """Response from spawn request."""
    compute_id: str
    state: ComputeState
    api_key: str
    serving_url: str
    workspace_path: Optional[str] = None
    worktree_active: Optional[str] = Field(None, description="Path to active worktree for code work")
    initial_work: Optional[Dict[str, Any]] = None


class ComputeListResponse(BaseModel):
    """Response for listing compute instances."""
    instances: List[SpawnedCompute]
    total: int
    by_state: Dict[str, int]


class StopRequest(BaseModel):
    """Request to stop a compute instance."""
    compute_id: str
    force: bool = Field(default=False, description="Force kill if graceful stop fails")
    timeout: int = Field(default=30, ge=1, le=300, description="Seconds to wait for graceful stop")


class ComputeMetrics(BaseModel):
    """Metrics from a compute instance."""
    compute_id: str
    uptime_seconds: float
    work_completed: int
    work_failed: int
    current_work_count: int
    last_heartbeat: Optional[datetime] = None
