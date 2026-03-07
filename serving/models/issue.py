"""Issue and Goal models for WorkMap system.

Git-backed persistent storage for issues and goals with YAML serialization.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import yaml


class IssueType(str, Enum):
    """Type of issue."""
    FEATURE = "feature"
    BUG = "bug"
    REFACTOR = "refactor"
    DOCS = "docs"
    TEST = "test"


class IssueArea(str, Enum):
    """Area of codebase the issue affects."""
    API = "api"
    DATABASE = "database"
    FRONTEND = "frontend"
    INFRA = "infra"


class IssuePriority(str, Enum):
    """Issue priority level."""
    P0 = "P0"  # Critical
    P1 = "P1"  # High
    P2 = "P2"  # Medium
    P3 = "P3"  # Low


class IssueStatus(str, Enum):
    """Issue lifecycle status."""
    BACKLOG = "backlog"          # Has unmet dependencies or not ready
    READY = "ready"              # All dependencies met, ready for assignment
    IN_PROGRESS = "in_progress"  # Assigned to a compute instance
    BLOCKED = "blocked"          # Work is blocked by external factor
    DONE = "done"                # Successfully completed
    FAILED = "failed"            # Failed after retries


class GoalStatus(str, Enum):
    """Goal lifecycle status."""
    PLANNING = "planning"        # Being broken into issues by planner
    IN_PROGRESS = "in_progress"  # Issues are being worked
    DONE = "done"                # All issues complete


class IssueResult(BaseModel):
    """Result of completed issue."""
    branch: str = Field(..., description="Git branch where work was done")
    summary: str = Field(..., description="Summary of work completed")
    commits: List[str] = Field(default_factory=list, description="Commit SHAs")


class Issue(BaseModel):
    """A unit of work in the WorkMap system.

    Issues are persistent, stored as YAML files in Git for full history.
    """
    # Identity
    id: str = Field(..., description="Unique issue identifier (issue-NNN)")
    title: str = Field(..., description="Brief title")
    description: str = Field(..., description="Detailed description")

    # Classification
    type: IssueType = Field(default=IssueType.FEATURE)
    area: IssueArea = Field(..., description="Area of codebase")
    priority: IssuePriority = Field(default=IssuePriority.P2)
    status: IssueStatus = Field(default=IssueStatus.BACKLOG)

    # Requirements
    required_skills: List[str] = Field(default_factory=list, description="Skill IDs needed")

    # Dependencies
    depends_on: List[str] = Field(default_factory=list, description="Issue IDs this depends on")
    blocks: List[str] = Field(default_factory=list, description="Issue IDs blocked by this (computed)")

    # Lineage
    goal_id: Optional[str] = Field(None, description="Parent goal ID")
    parent_issue_id: Optional[str] = Field(None, description="Parent issue if subtask")

    # User attribution
    created_by: Optional[str] = Field(None, description="User ID who created the issue")
    created_by_name: Optional[str] = Field(None, description="Display name of creator")
    modified_by: Optional[str] = Field(None, description="User ID who last modified")
    modified_by_name: Optional[str] = Field(None, description="Display name of last modifier")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Result (populated on completion)
    result: Optional[IssueResult] = None

    def to_yaml(self) -> str:
        """Convert issue to YAML string for Git storage.

        Returns:
            YAML string representation
        """
        data = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "type": self.type.value,
            "area": self.area.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "required_skills": self.required_skills,
            "depends_on": self.depends_on,
            "blocks": self.blocks,
        }

        # Optional fields
        if self.goal_id:
            data["goal_id"] = self.goal_id
        if self.parent_issue_id:
            data["parent_issue_id"] = self.parent_issue_id

        # Timestamps
        data["created_at"] = self.created_at.isoformat()
        if self.started_at:
            data["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            data["completed_at"] = self.completed_at.isoformat()

        # Result
        if self.result:
            data["result"] = {
                "branch": self.result.branch,
                "summary": self.result.summary,
                "commits": self.result.commits
            }

        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "Issue":
        """Parse issue from YAML string.

        Args:
            yaml_str: YAML string representation

        Returns:
            Issue instance
        """
        data = yaml.safe_load(yaml_str)

        # Parse enums
        data["type"] = IssueType(data["type"])
        data["area"] = IssueArea(data["area"])
        data["priority"] = IssuePriority(data["priority"])
        data["status"] = IssueStatus(data["status"])

        # Parse timestamps
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "started_at" in data and data["started_at"]:
            data["started_at"] = datetime.fromisoformat(data["started_at"])
        if "completed_at" in data and data["completed_at"]:
            data["completed_at"] = datetime.fromisoformat(data["completed_at"])

        # Parse result
        if "result" in data and data["result"]:
            data["result"] = IssueResult(**data["result"])

        return cls(**data)


class Goal(BaseModel):
    """A high-level objective that is broken into Issues by a Planner.

    Goals are persistent, stored as YAML files in Git.
    """
    # Identity
    id: str = Field(..., description="Unique goal identifier (goal-NNN)")
    title: str = Field(..., description="Brief title")
    description: str = Field(..., description="Detailed description")

    # Classification
    priority: IssuePriority = Field(default=IssuePriority.P2)
    status: GoalStatus = Field(default=GoalStatus.PLANNING)

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(..., description="User or system that created the goal")

    # Issues (populated after planning)
    issue_ids: List[str] = Field(default_factory=list, description="Issue IDs in this goal")

    def to_yaml(self) -> str:
        """Convert goal to YAML string for Git storage.

        Returns:
            YAML string representation
        """
        data = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "issue_ids": self.issue_ids,
        }

        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "Goal":
        """Parse goal from YAML string.

        Args:
            yaml_str: YAML string representation

        Returns:
            Goal instance
        """
        data = yaml.safe_load(yaml_str)

        # Parse enums
        data["priority"] = IssuePriority(data["priority"])
        data["status"] = GoalStatus(data["status"])

        # Parse timestamp
        data["created_at"] = datetime.fromisoformat(data["created_at"])

        return cls(**data)


# ============================================================================
# Request/Response Models
# ============================================================================

class IssueCreateRequest(BaseModel):
    """Request to create a new issue."""
    title: str
    description: str
    type: IssueType = IssueType.FEATURE
    area: IssueArea
    priority: IssuePriority = IssuePriority.P2
    required_skills: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    goal_id: Optional[str] = None
    parent_issue_id: Optional[str] = None


class IssueUpdateRequest(BaseModel):
    """Request to update an issue."""
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[IssueType] = None
    area: Optional[IssueArea] = None
    priority: Optional[IssuePriority] = None
    required_skills: Optional[List[str]] = None
    depends_on: Optional[List[str]] = None


class GoalCreateRequest(BaseModel):
    """Request to create a new goal."""
    title: str
    description: str
    priority: IssuePriority = IssuePriority.P2
    created_by: str = "user"


class GoalUpdateRequest(BaseModel):
    """Request to update a goal."""
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[IssuePriority] = None
    status: Optional[GoalStatus] = None
    issue_ids: Optional[List[str]] = None


class IssueListResponse(BaseModel):
    """Response for listing issues."""
    items: List[Issue]
    total: int
    by_status: Dict[str, int]
    by_priority: Dict[str, int]


class GoalListResponse(BaseModel):
    """Response for listing goals."""
    items: List[Goal]
    total: int
    by_status: Dict[str, int]
