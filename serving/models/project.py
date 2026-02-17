"""Project models for repository and work organization."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ActivityIndicator(str, Enum):
    """Activity indicator based on recency of last activity."""
    GREEN = "green"    # Activity within 24 hours
    YELLOW = "yellow"  # Activity within 7 days
    RED = "red"        # No activity for 7+ days
    GRAY = "gray"      # No activity tracked


class ActivitySummary(BaseModel):
    """Summary of project activity metrics."""
    last_activity_at: Optional[datetime] = Field(
        None, description="Timestamp of last activity"
    )
    indicator: ActivityIndicator = Field(
        default=ActivityIndicator.GRAY,
        description="Visual activity indicator based on recency"
    )
    active_work_items: int = Field(
        default=0, description="Number of work items currently in progress"
    )
    completed_today: int = Field(
        default=0, description="Work items completed in last 24 hours"
    )
    completed_week: int = Field(
        default=0, description="Work items completed in last 7 days"
    )


class ProjectStatus(str, Enum):
    """Status of a project."""
    ACTIVE = "active"
    ARCHIVED = "archived"
    SUSPENDED = "suspended"


class RepoConfig(BaseModel):
    """Configuration for a repository within a project."""
    repo_id: str = Field(..., description="Unique repository identifier")
    name: str = Field(..., description="Repository name")
    url: str = Field(..., description="Git repository URL")
    default_branch: str = Field(default="main", description="Default branch name")
    is_internal: bool = Field(default=False, description="Whether repo is hosted by ClaudeVN's internal Git server")

    # Optional settings
    path: Optional[str] = Field(None, description="Local clone path")
    ssh_key_id: Optional[str] = Field(None, description="SSH key for auth")

    # Metadata
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Project(BaseModel):
    """A project containing one or more repositories."""
    project_id: str = Field(..., description="Unique project identifier")
    name: str = Field(..., description="Project name")
    description: str = Field(default="", description="Project description")

    # Status
    status: ProjectStatus = Field(default=ProjectStatus.ACTIVE)

    # Visual identification
    icon: Optional[str] = Field(None, description="Icon name or image URL")
    icon_color: Optional[str] = Field(None, description="Background color for icon (hex)")
    labels: List[str] = Field(default_factory=list, description="Project labels/tags")

    # Repositories
    repos: List[RepoConfig] = Field(default_factory=list)
    primary_repo_id: Optional[str] = Field(None, description="Primary repository ID")

    # Work configuration
    default_base_branch: str = Field(default="main")
    work_branch_pattern: str = Field(
        default="{type}/{task}/{compute-id}",
        description="Pattern for work branch names"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Activity tracking
    last_activity_at: Optional[datetime] = Field(
        None, description="Timestamp of last activity in this project"
    )
    activity_summary: Optional[ActivitySummary] = Field(
        None, description="Summary of project activity metrics"
    )

    @property
    def repo_count(self) -> int:
        return len(self.repos)

    @property
    def primary_repo(self) -> Optional[RepoConfig]:
        if not self.primary_repo_id:
            return self.repos[0] if self.repos else None
        return next((r for r in self.repos if r.repo_id == self.primary_repo_id), None)


class ProjectCreateRequest(BaseModel):
    """Request to create a new project."""
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    icon_color: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProjectUpdateRequest(BaseModel):
    """Request to update a project."""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None
    icon: Optional[str] = None
    icon_color: Optional[str] = None
    labels: Optional[List[str]] = None
    primary_repo_id: Optional[str] = None
    default_base_branch: Optional[str] = None
    work_branch_pattern: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class RepoAddRequest(BaseModel):
    """Request to add a repository to a project."""
    name: str
    url: str
    default_branch: str = "main"
    ssh_key_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RepoCreateInternalRequest(BaseModel):
    """Request to create an internal Git repository hosted by ClaudeVN."""
    name: str
    default_branch: str = "main"


class ProjectListResponse(BaseModel):
    """Response for listing projects."""
    items: List[Project]
    total: int


class ProjectStats(BaseModel):
    """Statistics about projects."""
    total: int
    by_status: Dict[str, int]
    total_repos: int


class RepoCloneStatus(str, Enum):
    """Status of a repository clone operation."""
    NOT_CLONED = "not_cloned"
    CLONING = "cloning"
    CLONED = "cloned"
    ERROR = "error"


class RepoStatusResponse(BaseModel):
    """Response for repository status."""
    repo_id: str
    name: str
    url: str
    clone_status: RepoCloneStatus = RepoCloneStatus.NOT_CLONED
    local_path: Optional[str] = None
    origin_url: Optional[str] = None
    default_branch: Optional[str] = None
    branches: List[str] = Field(default_factory=list)
    branch_count: int = 0
    is_mirror: bool = False
    last_sync: Optional[datetime] = None
    error_message: Optional[str] = None


class RepoSyncResponse(BaseModel):
    """Response for repository sync operations."""
    repo_id: str
    project_id: str
    operation: str  # "clone", "pull", "push"
    success: bool
    message: str
    output: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ActivityEventType(str, Enum):
    """Types of activity events tracked for projects."""
    WORK_CREATED = "work_created"
    WORK_STARTED = "work_started"
    WORK_COMPLETED = "work_completed"
    WORK_FAILED = "work_failed"
    BRANCH_CREATED = "branch_created"
    BRANCH_MERGED = "branch_merged"
    COMPUTE_ASSIGNED = "compute_assigned"


class ActivityEvent(BaseModel):
    """A single activity event in a project."""
    event_id: str = Field(..., description="Unique event identifier")
    event_type: ActivityEventType = Field(..., description="Type of activity event")
    project_id: str = Field(..., description="Project this event belongs to")
    description: str = Field(..., description="Human-readable event description")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the event occurred"
    )
    work_id: Optional[str] = Field(None, description="Related work item ID")
    compute_id: Optional[str] = Field(None, description="Related compute instance ID")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProjectActivityResponse(BaseModel):
    """Response for project activity endpoint."""
    project_id: str
    activity_summary: ActivitySummary
    recent_events: List[ActivityEvent] = Field(
        default_factory=list,
        description="Recent activity events (last 10 by default)"
    )
