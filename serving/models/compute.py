"""Data models for compute instance registration and management."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from claudevn_shared.version import get_version


class InstanceStatus(str, Enum):
    """Status of a compute instance."""
    PENDING = "pending"
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    DRAINING = "draining"
    ERROR = "error"


class ComputeAuthStatus(str, Enum):
    """Authentication status of a compute instance."""
    UNAUTHORIZED = "unauthorized"
    AUTHORIZED = "authorized"
    EXPIRED = "expired"


class InstanceResources(BaseModel):
    """Resource capabilities of a compute instance."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "cpu_count": 8,
            "memory_gb": 32.0,
            "gpu_count": 1,
            "gpu_type": "NVIDIA RTX 4090",
            "storage_gb": 500.0
        }
    })

    cpu_count: Optional[int] = Field(None, description="Number of CPU cores")
    memory_gb: Optional[float] = Field(None, description="Total memory in GB")
    gpu_count: Optional[int] = Field(None, description="Number of GPUs")
    gpu_type: Optional[str] = Field(None, description="GPU type/model")
    storage_gb: Optional[float] = Field(None, description="Available storage in GB")


class InstanceCapabilities(BaseModel):
    """Capabilities of a compute instance."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "agents": ["data-analyst", "content-writer", "code-reviewer"],
            "tools": ["python-executor", "file-reader", "web-scraper"],
            "resources": {
                "cpu_count": 8,
                "memory_gb": 32.0
            },
            "features": ["gpu-acceleration", "fast-storage"],
            "labels": ["production-access", "database-admin"],
            "tools_available": ["deploy_prod", "db_migrate"]
        }
    })

    agents: List[str] = Field(default_factory=list, description="List of agent IDs available")
    tools: List[str] = Field(default_factory=list, description="List of tool IDs available")
    resources: Optional[InstanceResources] = Field(None, description="Hardware resources")
    features: List[str] = Field(default_factory=list, description="Special features/capabilities")
    labels: List[str] = Field(default_factory=list, description="Routing labels for work assignment (e.g., production-access, database-admin)")
    tools_available: List[str] = Field(default_factory=list, description="Specialized tools available on this compute (e.g., deploy_prod, db_migrate)")


class AffinityEntry(BaseModel):
    """A single domain affinity record for a compute instance."""
    cluster_id: str = Field(..., description="Domain cluster ID")
    tasks_completed: int = Field(default=0, description="Number of tasks completed in this domain")
    last_completed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of most recent completion in this domain"
    )
    work_types: List[str] = Field(
        default_factory=list,
        description="Work types completed in this domain (e.g., feature, bug_fix)"
    )


class ContextAffinityProfile(BaseModel):
    """Context affinity profile tracking domain experience for a compute instance."""
    compute_id: str = Field(..., description="Compute instance ID")
    entries: List[AffinityEntry] = Field(
        default_factory=list,
        description="Domain affinity entries"
    )
    total_tasks_completed: int = Field(default=0, description="Total tasks completed across all domains")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last profile update timestamp"
    )


class AffinityProfileResponse(BaseModel):
    """API response for a compute instance's affinity profile."""
    compute_id: str = Field(..., description="Compute instance ID")
    entries: List[AffinityEntry] = Field(default_factory=list, description="Domain affinity entries")
    total_tasks_completed: int = Field(default=0, description="Total tasks completed")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")


class ComputeInstance(BaseModel):
    """Complete compute instance information."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "instance_id": "compute-laptop-001",
            "name": "Developer Laptop",
            "endpoint": "http://localhost:8003",
            "health_endpoint": "http://localhost:8003/health",
            "status": "online",
            "capabilities": {
                "agents": ["content-writer", "data-analyst"],
                "tools": ["python-executor"],
                "resources": {
                    "cpu_count": 8,
                    "memory_gb": 16.0
                }
            },
            "metadata": {
                "location": "local",
                "owner": "developer@example.com",
                "environment": "development"
            },
            "version": "0.2.0"
        }
    })

    instance_id: str = Field(..., description="Unique instance identifier")
    name: str = Field(..., description="Human-readable instance name")
    endpoint: str = Field(..., description="Instance base URL endpoint")
    health_endpoint: Optional[str] = Field(None, description="Health check endpoint URL")
    status: InstanceStatus = Field(default=InstanceStatus.ONLINE, description="Current status")
    capabilities: InstanceCapabilities = Field(default_factory=InstanceCapabilities, description="Instance capabilities")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    version: str = Field(default_factory=get_version, description="Compute component version")
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Registration timestamp")
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Last heartbeat timestamp")
    project_ids: List[str] = Field(default_factory=lambda: ["*"], description="Project IDs this compute can receive work from. ['*'] = all projects (default). Empty = no work (benched).")
    heartbeat_interval: int = Field(default=30, description="Expected heartbeat interval in seconds")
    failed_health_checks: int = Field(default=0, description="Consecutive failed health checks")
    drain_started_at: Optional[datetime] = Field(None, description="Timestamp when drain was initiated")
    owner_id: Optional[str] = Field(None, description="User ID of the component owner")
    claimed_at: Optional[datetime] = Field(None, description="When ownership was claimed")
    auth_status: ComputeAuthStatus = Field(default=ComputeAuthStatus.UNAUTHORIZED, description="Authentication status")
    auth_expires_at: Optional[datetime] = Field(None, description="When the auth token expires")
    auth_authorized_at: Optional[datetime] = Field(None, description="When the auth token was submitted")
    
    pending_since: Optional[datetime] = Field(None, description="When instance entered PENDING state")

    def is_healthy(self, max_heartbeat_age: int = 90) -> bool:
        """Check if instance is healthy based on last heartbeat.

        Args:
            max_heartbeat_age: Maximum seconds since last heartbeat

        Returns:
            True if healthy, False otherwise
        """
        if self.status in (InstanceStatus.OFFLINE, InstanceStatus.PENDING):
            return False

        age = (datetime.now(timezone.utc) - self.last_heartbeat).total_seconds()
        return age <= max_heartbeat_age

    def is_authorized(self) -> bool:
        """Check if instance has valid auth credentials."""
        return self.auth_status == ComputeAuthStatus.AUTHORIZED

    def is_work_eligible(self, max_heartbeat_age: int = 90) -> bool:
        """Check if instance can be assigned work (healthy + authorized + not pending)."""
        if self.status == InstanceStatus.PENDING:
            return False
        return self.is_healthy(max_heartbeat_age) and self.is_authorized()

    def update_heartbeat(self):
        """Update last heartbeat timestamp and reset failed checks."""
        self.last_heartbeat = datetime.now(timezone.utc)
        self.failed_health_checks = 0
        if self.status == InstanceStatus.DEGRADED:
            self.status = InstanceStatus.ONLINE


class RegistrationRequest(BaseModel):
    """Request to register a compute instance."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "instance_id": "compute-laptop-001",
            "name": "Developer Laptop",
            "endpoint": "http://localhost:8003",
            "health_endpoint": "http://localhost:8003/health",
            "capabilities": {
                "agents": ["content-writer", "data-analyst"],
                "tools": ["python-executor"]
            },
            "metadata": {
                "location": "local",
                "owner": "developer@example.com"
            },
            "version": "0.2.0",
            "heartbeat_interval": 30
        }
    })

    instance_id: str = Field(..., description="Unique instance identifier")
    name: str = Field(..., description="Human-readable instance name")
    endpoint: str = Field(..., description="Instance base URL endpoint")
    health_endpoint: Optional[str] = Field(None, description="Health check endpoint URL")
    capabilities: InstanceCapabilities = Field(default_factory=InstanceCapabilities, description="Instance capabilities")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    version: str = Field(default_factory=get_version, description="Compute component version")
    heartbeat_interval: int = Field(default=30, ge=10, le=300, description="Preferred heartbeat interval in seconds")


class RegistrationResponse(BaseModel):
    """Response to a registration request."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "registered",
            "instance_id": "compute-laptop-001",
            "heartbeat_interval": 30,
            "heartbeat_endpoint": "/api/v1/compute/compute-laptop-001/health",
            "message": "Successfully registered compute instance"
        }
    })

    status: str = Field(..., description="Registration status")
    instance_id: str = Field(..., description="Registered instance ID")
    heartbeat_interval: int = Field(..., description="Required heartbeat interval in seconds")
    heartbeat_endpoint: str = Field(..., description="Endpoint for sending heartbeats")
    message: str = Field(default="", description="Additional message")


class HeartbeatRequest(BaseModel):
    """Heartbeat request from compute instance."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "online",
            "metadata": {
                "active_tasks": 3,
                "cpu_usage": 45.2,
                "memory_usage": 12.5
            }
        }
    })

    status: Optional[InstanceStatus] = Field(None, description="Current instance status")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional status metadata")


class UpdateInstanceRequest(BaseModel):
    """Request to update instance metadata."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "name": "Production Server 1",
            "capabilities": {
                "agents": ["agent-a", "agent-b", "agent-c"]
            },
            "metadata": {
                "location": "cloud-us-east-1"
            }
        }
    })

    name: Optional[str] = Field(None, description="New instance name")
    capabilities: Optional[InstanceCapabilities] = Field(None, description="Updated capabilities")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Updated metadata")


class UpdateProjectTagsRequest(BaseModel):
    """Request to update project tags for a compute instance."""
    project_ids: List[str] = Field(..., description="Project IDs this compute can receive work from. Empty = benched. Use ['*'] for all projects.")


class DrainRequest(BaseModel):
    """Request to initiate graceful drain of a compute instance."""
    auto_deregister: bool = Field(default=False, description="Automatically deregister when drain completes (all work finished)")


class DrainStatusResponse(BaseModel):
    """Response for drain status check."""
    instance_id: str = Field(..., description="Compute instance ID")
    is_draining: bool = Field(..., description="Whether instance is currently draining")
    drain_started_at: Optional[str] = Field(None, description="ISO timestamp when drain started")
    in_flight_work_ids: List[str] = Field(default_factory=list, description="Work IDs still in progress")
    in_flight_count: int = Field(0, description="Number of in-flight work items")
    drain_complete: bool = Field(False, description="Whether drain is complete (no in-flight work)")
    auto_deregister: bool = Field(False, description="Whether auto-deregister is enabled")


class InstanceListResponse(BaseModel):
    """Response for listing instances."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "instances": [
                {
                    "instance_id": "compute-001",
                    "name": "Compute 1",
                    "status": "online"
                }
            ],
            "total": 1,
            "online": 1,
            "offline": 0
        }
    })

    instances: List[ComputeInstance] = Field(..., description="List of compute instances")
    total: int = Field(..., description="Total number of instances")
    online: int = Field(..., description="Number of online instances")
    offline: int = Field(..., description="Number of offline instances")
    authorized: int = Field(default=0, description="Number of authorized instances")
    unauthorized: int = Field(default=0, description="Number of unauthorized instances")


class AggregatedCapabilities(BaseModel):
    """Aggregated capabilities across all compute instances."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "total_instances": 3,
            "online_instances": 2,
            "agents": {
                "data-analyst": ["compute-001", "compute-002"],
                "content-writer": ["compute-001"]
            },
            "tools": {
                "python-executor": ["compute-001", "compute-002", "compute-003"]
            },
            "labels": {
                "production-access": ["compute-001"],
                "database-admin": ["compute-001", "compute-002"]
            },
            "tools_available": {
                "deploy_prod": ["compute-001"],
                "db_migrate": ["compute-001", "compute-002"]
            },
            "total_resources": {
                "cpu_count": 24,
                "memory_gb": 96.0
            }
        }
    })

    total_instances: int = Field(..., description="Total number of instances")
    online_instances: int = Field(..., description="Number of online instances")
    agents: Dict[str, List[str]] = Field(default_factory=dict, description="Map of agent_id -> [instance_ids]")
    tools: Dict[str, List[str]] = Field(default_factory=dict, description="Map of tool_id -> [instance_ids]")
    labels: Dict[str, List[str]] = Field(default_factory=dict, description="Map of label -> [instance_ids]")
    tools_available: Dict[str, List[str]] = Field(default_factory=dict, description="Map of available_tool -> [instance_ids]")
    total_resources: InstanceResources = Field(default_factory=InstanceResources, description="Sum of all resources")


# =============================================================================
# SSE Event Models (Serving -> Compute)
# =============================================================================


class SSEEventType(str, Enum):
    """Types of SSE events from Serving to Compute."""
    WORK_ASSIGNED = "work_assigned"
    WORK_CANCELLED = "work_cancelled"
    SHUTDOWN = "shutdown"
    MERGE_CONFLICT = "merge_conflict"
    WORK_COMPLETED = "work_completed"
    KEEPALIVE = "keepalive"
    CREDENTIALS_REFRESH = "credentials_refresh"
    DRAIN = "drain"


class WorkAssignedEvent(BaseModel):
    """Work assignment event pushed to compute via SSE."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "task_id": "task-456",
            "title": "Implement user authentication",
            "description": "Add login/logout endpoints with JWT support",
            "branch_name": "f/implement-auth/compute-001",
            "skills": {
                "ids": ["code-writer", "test-automator"],
                "merged_instructions": "# Code Writer\nYou are an expert developer..."
            },
            "context": {
                "repository": "git@serving:project.git",
                "base_branch": "main",
                "relevant_files": ["src/api/routes.py", "src/models/user.py"]
            },
            "mcp_config": {
                "server_url": "http://serving:8002",
                "api_key": "task-scoped-key-xyz"
            }
        }
    })

    task_id: str = Field(..., description="Unique task identifier")
    title: str = Field(..., description="Task title")
    description: str = Field(default="", description="Task description")
    branch_name: str = Field(..., description="Git branch for this task")
    skills: Dict[str, Any] = Field(default_factory=dict, description="Skills configuration")
    context: Dict[str, Any] = Field(default_factory=dict, description="Task context")
    mcp_config: Dict[str, Any] = Field(default_factory=dict, description="MCP server configuration")

    # Repository details for linked repos
    git_project_name: Optional[str] = Field(
        None,
        description="Composite bare repo name for git operations (e.g. proj_abc_repo_def)"
    )
    clone_url: Optional[str] = Field(
        None,
        description="Full HTTP clone URL for the repository"
    )
    default_branch: Optional[str] = Field(
        None,
        description="Repository's configured default branch name"
    )


class WorkCancelledEvent(BaseModel):
    """Work cancellation event pushed to compute via SSE."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "task_id": "task-456",
            "reason": "Higher priority work assigned",
            "action": "stop_gracefully"
        }
    })

    task_id: str = Field(..., description="Task ID being cancelled")
    reason: str = Field(default="", description="Reason for cancellation")
    action: str = Field(default="stop_gracefully", description="Requested action")


class ShutdownEvent(BaseModel):
    """Shutdown request event pushed to compute via SSE."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "reason": "Maintenance window",
            "grace_period_seconds": 60
        }
    })

    reason: str = Field(default="", description="Reason for shutdown")
    grace_period_seconds: int = Field(default=60, description="Grace period before forced shutdown")


class MergeConflictEvent(BaseModel):
    """Merge conflict notification pushed to compute via SSE."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "issue_id": "issue-100",
            "branch": "f/issue-100/compute-001",
            "conflicting_files": ["src/models/user.py", "src/api/auth.py"],
            "main_head": "abc123def",
            "message": "Resolve conflicts with main and push again"
        }
    })

    issue_id: str = Field(..., description="Related issue ID")
    branch: str = Field(..., description="Branch with conflicts")
    conflicting_files: List[str] = Field(default_factory=list, description="Files with conflicts")
    main_head: str = Field(..., description="Current main branch HEAD commit")
    message: str = Field(default="", description="Human-readable message")


class WorkCompletedEvent(BaseModel):
    """Work completion confirmation pushed to compute via SSE."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "issue_id": "issue-100",
            "branch": "f/issue-100/compute-001",
            "merge_commit": "def456abc",
            "merged_at": "2026-01-30T10:30:00Z"
        }
    })

    issue_id: str = Field(..., description="Related issue ID")
    branch: str = Field(..., description="Branch that was merged")
    merge_commit: str = Field(..., description="Merge commit SHA")
    merged_at: str = Field(..., description="ISO timestamp of merge")


class CredentialsRefreshEvent(BaseModel):
    """Credentials refresh request pushed to compute via SSE."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "reason": "Credentials refreshed on host",
            "timestamp": "2026-01-30T10:00:00Z"
        }
    })

    reason: str = Field(default="Credentials refreshed", description="Reason for refresh")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp"
    )


class DrainEvent(BaseModel):
    """Drain request pushed to compute via SSE."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "reason": "Credential refresh failed, draining for restart",
            "grace_period_seconds": 300,
            "timestamp": "2026-01-30T10:00:00Z"
        }
    })

    reason: str = Field(default="", description="Reason for drain")
    grace_period_seconds: int = Field(
        default=300, description="Grace period before forced stop"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp"
    )


class RefreshCredentialsRequest(BaseModel):
    """Request to refresh credentials on compute instances."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "instance_ids": ["compute-001", "compute-002"],
            "reason": "Host credentials refreshed via claude /login"
        }
    })

    instance_ids: Optional[List[str]] = Field(
        None,
        description="Specific instance IDs to refresh. None = all connected instances."
    )
    reason: str = Field(
        default="Credentials refreshed",
        description="Reason for the refresh"
    )


class RefreshCredentialsResponse(BaseModel):
    """Response for credential refresh request."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "sent",
            "instances_notified": ["compute-001", "compute-002"],
            "instances_failed": [],
            "total_notified": 2
        }
    })

    status: str = Field(..., description="Overall status")
    instances_notified: List[str] = Field(
        default_factory=list, description="Instance IDs that were notified"
    )
    instances_failed: List[str] = Field(
        default_factory=list, description="Instance IDs that failed to notify"
    )
    total_notified: int = Field(0, description="Total instances notified")


class KeepaliveEvent(BaseModel):
    """Keepalive pulse pushed to compute via SSE."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "timestamp": "2026-01-30T10:00:00Z"
        }
    })

    timestamp: str = Field(..., description="ISO timestamp of keepalive")


# =============================================================================
# Compute Event Models (Compute -> Serving via HTTP POST)
# =============================================================================


class ComputeEventType(str, Enum):
    """Types of events from Compute to Serving."""
    CLAUDE_CODE_STARTED = "claude_code_started"
    CLAUDE_CODE_COMPLETED = "claude_code_completed"
    CLAUDE_CODE_FAILED = "claude_code_failed"
    CLAUDE_CODE_REJECTED = "claude_code_rejected"


class ComputeEventRequest(BaseModel):
    """Event sent from Compute to Serving via HTTP POST."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "event": "claude_code_started",
            "compute_id": "compute-001",
            "task_id": "task-456",
            "instance_id": "cc-789",
            "timestamp": "2026-01-30T10:01:00Z"
        }
    })

    event: ComputeEventType = Field(..., description="Event type")
    compute_id: str = Field(..., description="Compute infrastructure ID")
    task_id: str = Field(..., description="Associated task ID")
    instance_id: Optional[str] = Field(None, description="Claude Code instance ID")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="Event timestamp")
    exit_code: Optional[int] = Field(None, description="Exit code (for completed/failed)")
    duration_seconds: Optional[int] = Field(None, description="Duration in seconds (for completed/failed)")
    error: Optional[str] = Field(None, description="Error message (for failed)")
    branch_name: Optional[str] = Field(None, description="Git branch name with work commits (for completed)")


class ComputeEventResponse(BaseModel):
    """Response to compute event."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "acknowledged",
            "event": "claude_code_started",
            "compute_id": "compute-001",
            "task_id": "task-456"
        }
    })

    status: str = Field(default="acknowledged", description="Response status")
    event: str = Field(..., description="Event type that was processed")
    compute_id: str = Field(..., description="Compute ID that sent the event")
    task_id: str = Field(..., description="Associated task ID")

