"""Observability event models for real-time process map monitoring."""

from enum import Enum
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field

from models.decision_trace import DecisionPointType
from models.process_map import (
    ActivityStatus,
    Exchange,
    Blocker,
    ReevaluationEvent,
    ParticipantAssignment
)


class EventType(str, Enum):
    """Types of observability events."""
    ACTIVITY_STATE_CHANGE = "activity_state_change"
    EXCHANGE = "exchange"
    PROCESS_MAP_REEVALUATION = "process_map_reevaluation"
    BLOCKER_IDENTIFIED = "blocker_identified"
    ACTIVITY_GROUPING = "activity_grouping"
    SESSION_CREATED = "session_created"
    SESSION_COMPLETED = "session_completed"
    AGENT_EXECUTION_STARTED = "agent_execution_started"
    AGENT_EXECUTION_COMPLETED = "agent_execution_completed"
    LLM_CALL_MADE = "llm_call_made"
    WORK_STATUS_CHANGE = "work_status_change"
    COMMENT_EVALUATION_STATUS = "comment_evaluation_status"
    ISSUE_EVALUATION_STATUS = "issue_evaluation_status"
    DECISION_TRACE = "decision_trace"
    COMPUTE_REGISTERED = "compute_registered"
    COMPUTE_DEREGISTERED = "compute_deregistered"


class ActivityStateChangeEvent(BaseModel):
    """Event emitted when activity status changes."""
    event_type: str = Field(default=EventType.ACTIVITY_STATE_CHANGE, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")
    session_id: str = Field(..., description="Parent session ID")
    activity_id: str = Field(..., description="Activity that changed")
    
    # State change
    old_status: ActivityStatus = Field(..., description="Previous status")
    new_status: ActivityStatus = Field(..., description="New status")
    
    # Execution context
    compute_instance_id: str = Field(..., description="Compute instance executing this activity")
    agent_id: Optional[str] = Field(None, description="Primary agent assigned")
    
    # Progress details
    exchange_count: Optional[int] = Field(None, description="Number of exchanges so far")
    duration_seconds: Optional[int] = Field(None, description="Duration if completed")
    
    # Blocker info (if status = blocked)
    blocker: Optional[Blocker] = Field(None, description="Blocker details if blocked")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class ExchangeEvent(BaseModel):
    """Event emitted after important exchanges (throttled)."""
    event_type: str = Field(default=EventType.EXCHANGE, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")
    session_id: str = Field(..., description="Parent session ID")
    activity_id: str = Field(..., description="Activity this exchange belongs to")
    
    # Exchange details
    exchange: Exchange = Field(..., description="The exchange that occurred")
    
    # Context
    compute_instance_id: str = Field(..., description="Compute instance")
    exchange_number: int = Field(..., description="Exchange number (1-indexed)")
    total_exchanges: int = Field(..., description="Total exchanges so far")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class ProcessMapReevaluationEvent(BaseModel):
    """Event emitted when process map is reevaluated."""
    event_type: str = Field(default=EventType.PROCESS_MAP_REEVALUATION, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")
    session_id: str = Field(..., description="Parent session ID")
    
    # Reevaluation details
    reevaluation: ReevaluationEvent = Field(..., description="Reevaluation details")
    previous_version: int = Field(..., description="Map version before")
    new_version: int = Field(..., description="Map version after")
    
    # What changed
    activities_added: List[str] = Field(default_factory=list, description="Activity IDs added")
    activities_removed: List[str] = Field(default_factory=list, description="Activity IDs removed")
    activities_modified: List[str] = Field(default_factory=list, description="Activity IDs modified")
    dependencies_changed: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="activity_id -> new dependencies"
    )
    
    # Context
    triggered_by: str = Field(..., description="What triggered this reevaluation")
    reasoning: str = Field(..., description="Why the map was restructured")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class BlockerEvent(BaseModel):
    """Event emitted when blocker is identified."""
    event_type: str = Field(default=EventType.BLOCKER_IDENTIFIED, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")
    session_id: str = Field(..., description="Parent session ID")
    activity_id: str = Field(..., description="Activity that is blocked")
    
    # Blocker details
    blocker: Blocker = Field(..., description="The blocker")
    
    # Impact
    affected_activities: List[str] = Field(
        default_factory=list,
        description="Other activities this blocks"
    )
    severity: str = Field(..., description="critical, moderate, minor")
    
    # Context
    identified_by: str = Field(..., description="Agent ID that identified blocker")
    compute_instance_id: str = Field(..., description="Compute instance")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class ActivityGroup(BaseModel):
    """A semantic grouping of related activities."""
    group_id: str = Field(..., description="Unique group identifier")
    group_name: str = Field(..., description="Human-readable group name")
    group_description: Optional[str] = Field(None, description="What this group represents")
    
    # Activities in this group
    activity_ids: List[str] = Field(default_factory=list, description="Activity IDs in group")
    
    # Status (derived from activities)
    status: str = Field(..., description="proposed, in_progress, completed, blocked")
    
    # Progress (derived)
    total_activities: int = Field(0, description="Total activities in group")
    completed_activities: int = Field(0, description="Completed activities in group")
    progress_percent: float = Field(0.0, description="Percentage complete")
    
    # Hierarchy (optional)
    parent_group: Optional[str] = Field(None, description="Parent group ID if nested")
    sub_groups: List[str] = Field(default_factory=list, description="Sub-group IDs")
    
    # UI behavior
    collapsible: bool = Field(True, description="Can this group be collapsed in UI?")
    collapsed_by_default: bool = Field(False, description="Should UI collapse by default?")
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(default="process-mapper-v1")
    
    # Visual styling (optional)
    color: Optional[str] = Field(None, description="UI color hint")
    icon: Optional[str] = Field(None, description="UI icon hint")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class ActivityGroupingEvent(BaseModel):
    """Event emitted when activities are grouped."""
    event_type: str = Field(default=EventType.ACTIVITY_GROUPING, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")
    session_id: str = Field(..., description="Parent session ID")
    
    # Grouping details
    group: ActivityGroup = Field(..., description="The activity group")
    
    # Context
    created_by: str = Field(..., description="Who created this group")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class SessionCreatedEvent(BaseModel):
    """Event emitted when session is created."""
    event_type: str = Field(default=EventType.SESSION_CREATED, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")
    session_id: str = Field(..., description="Session ID")
    
    # Session details
    business_goal: str = Field(..., description="Business goal")
    created_by: str = Field(..., description="Who created this session")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class SessionCompletedEvent(BaseModel):
    """Event emitted when session completes."""
    event_type: str = Field(default=EventType.SESSION_COMPLETED, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")
    session_id: str = Field(..., description="Session ID")
    
    # Completion details
    total_activities: int = Field(..., description="Total activities")
    duration_seconds: int = Field(..., description="Total duration")
    map_versions: int = Field(..., description="Number of reevaluations")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class AgentExecutionStartedEvent(BaseModel):
    """Event emitted when agent execution starts."""
    event_type: str = Field(default=EventType.AGENT_EXECUTION_STARTED, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")
    
    # Context
    compute_instance_id: str = Field(..., description="Compute instance executing agent")
    session_id: Optional[str] = Field(None, description="Session ID if part of session")
    task_id: str = Field(..., description="Task ID")
    
    # Agent details
    agent_id: str = Field(..., description="Agent ID")
    agent_name: str = Field(..., description="Agent name")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class AgentExecutionCompletedEvent(BaseModel):
    """Event emitted when agent execution completes."""
    event_type: str = Field(default=EventType.AGENT_EXECUTION_COMPLETED, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")
    
    # Context
    compute_instance_id: str = Field(..., description="Compute instance executing agent")
    session_id: Optional[str] = Field(None, description="Session ID if part of session")
    task_id: str = Field(..., description="Task ID")
    
    # Agent details
    agent_id: str = Field(..., description="Agent ID")
    agent_name: str = Field(..., description="Agent name")
    
    # Execution results
    duration_seconds: float = Field(..., description="Execution duration")
    tokens_used: Optional[int] = Field(None, description="Total tokens used")
    cost_estimate: Optional[float] = Field(None, description="Estimated cost")
    llm_provider: Optional[str] = Field(None, description="LLM provider used")
    llm_model: Optional[str] = Field(None, description="LLM model used")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class LLMCallMadeEvent(BaseModel):
    """Event emitted when LLM call is made."""
    event_type: str = Field(default=EventType.LLM_CALL_MADE, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")
    
    # Context
    compute_instance_id: str = Field(..., description="Compute instance making call")
    session_id: Optional[str] = Field(None, description="Session ID if part of session")
    task_id: str = Field(..., description="Task ID")
    agent_id: str = Field(..., description="Agent making the call")
    
    # LLM details
    provider: str = Field(..., description="LLM provider (openai, anthropic, mock)")
    model: str = Field(..., description="Model name")
    
    # Token usage
    prompt_tokens: int = Field(..., description="Tokens in prompt")
    completion_tokens: int = Field(..., description="Tokens in completion")
    total_tokens: int = Field(..., description="Total tokens")
    
    # Cost and performance
    cost_estimate: float = Field(..., description="Estimated cost")
    duration_seconds: float = Field(..., description="Call duration")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class WorkStatusChangeEvent(BaseModel):
    """Event emitted when work item status changes."""
    event_type: str = Field(default=EventType.WORK_STATUS_CHANGE, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")

    # Work item context - use project_id as session_id for subscription key
    session_id: str = Field(..., description="Project ID (used as subscription key)")
    work_id: str = Field(..., description="Work item ID")

    # Status change
    old_status: str = Field(..., description="Previous status")
    new_status: str = Field(..., description="New status")

    # Work details for UI update
    title: str = Field(..., description="Work title")
    assigned_to: Optional[str] = Field(None, description="Compute instance ID")
    progress_percent: int = Field(default=0, description="Progress percentage")

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class CommentEvaluationStatusEvent(BaseModel):
    """Event emitted when a goal comment's evaluation status changes."""
    event_type: str = Field(default=EventType.COMMENT_EVALUATION_STATUS, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")

    # Use goal_id as session_id for subscription key (all goal events on same channel)
    session_id: str = Field(..., description="Goal ID (used as subscription key)")
    comment_id: str = Field(..., description="Comment ID")

    # Status change
    old_status: str = Field(..., description="Previous evaluation status")
    new_status: str = Field(..., description="New evaluation status")

    # Evaluation result summary (if available)
    comment_type: Optional[str] = Field(None, description="Identified comment type")
    confidence: Optional[float] = Field(None, description="Evaluation confidence score")
    summary: Optional[str] = Field(None, description="Brief evaluation summary")

    # Error info (if failed)
    error: Optional[str] = Field(None, description="Error message if evaluation failed")

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class IssueEvaluationStatusEvent(BaseModel):
    """Event emitted when an issue's post-completion evaluation status changes."""
    event_type: str = Field(default=EventType.ISSUE_EVALUATION_STATUS, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")

    # Use goal_id as session_id for subscription key
    session_id: str = Field(..., description="Goal ID (used as subscription key)")
    issue_id: str = Field(..., description="Issue ID")

    # Status change
    old_status: str = Field(..., description="Previous evaluation status")
    new_status: str = Field(..., description="New evaluation status")

    # Evaluation result summary (if available)
    outcome: Optional[str] = Field(None, description="Evaluation outcome (success/partial/failure)")
    confidence: Optional[float] = Field(None, description="Evaluation confidence score")
    summary: Optional[str] = Field(None, description="Brief evaluation summary")
    followup_issue_id: Optional[str] = Field(None, description="Follow-up issue ID if created")

    # Error info (if failed)
    error: Optional[str] = Field(None, description="Error message if evaluation failed")

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class DecisionTraceEvent(BaseModel):
    """Event emitted when a planning decision is traced."""
    event_type: str = Field(default=EventType.DECISION_TRACE, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")

    # Use project_id as session_id for subscription key
    session_id: str = Field(..., description="Project ID (used as subscription key)")
    trace_id: str = Field(..., description="Decision trace ID")

    # Decision summary
    decision_type: DecisionPointType = Field(..., description="Type of planning decision")
    decision_summary: str = Field(..., description="Concise description of the decision")

    # Trigger info
    trigger_type: str = Field(..., description="What triggered this decision")
    trigger_source_id: str = Field(default="", description="Source entity ID")

    # Impact summary
    affected_item_count: int = Field(default=0, description="Number of items affected")
    affected_bucket_count: int = Field(default=0, description="Number of buckets affected")

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class ComputeRegisteredEvent(BaseModel):
    """Event emitted when a compute instance registers."""
    event_type: str = Field(default=EventType.COMPUTE_REGISTERED, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")

    # Use global session_id for broadcast to all subscribers
    session_id: str = Field(default="global", description="Global session for broadcast")
    compute_id: str = Field(..., description="Compute instance ID")

    # Instance details
    name: str = Field(..., description="Compute instance name")
    capabilities: List[str] = Field(default_factory=list, description="Capabilities")
    labels: List[str] = Field(default_factory=list, description="Routing labels")
    tools_available: List[str] = Field(default_factory=list, description="Available tools")

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class ComputeDeregisteredEvent(BaseModel):
    """Event emitted when a compute instance deregisters."""
    event_type: str = Field(default=EventType.COMPUTE_DEREGISTERED, description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When event occurred")

    # Use global session_id for broadcast to all subscribers
    session_id: str = Field(default="global", description="Global session for broadcast")
    compute_id: str = Field(..., description="Compute instance ID")

    # Deregistration reason
    reason: str = Field(default="normal", description="Deregistration reason")

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


# Union type for all event types
ObservabilityEvent = Union[
    ActivityStateChangeEvent,
    ExchangeEvent,
    ProcessMapReevaluationEvent,
    BlockerEvent,
    ActivityGroupingEvent,
    SessionCreatedEvent,
    SessionCompletedEvent,
    AgentExecutionStartedEvent,
    AgentExecutionCompletedEvent,
    LLMCallMadeEvent,
    WorkStatusChangeEvent,
    CommentEvaluationStatusEvent,
    IssueEvaluationStatusEvent,
    DecisionTraceEvent,
    ComputeRegisteredEvent,
    ComputeDeregisteredEvent
]


# Request/Response models

class EventSubmissionResponse(BaseModel):
    """Response to event submission."""
    status: str = Field(..., description="accepted or rejected")
    event_id: str = Field(..., description="Event ID")
    timestamp: datetime = Field(..., description="When event was processed")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class WebSocketSubscription(BaseModel):
    """WebSocket subscription request."""
    action: str = Field(..., description="subscribe or unsubscribe")
    session_ids: List[str] = Field(..., description="Session IDs to subscribe to")


class WebSocketMessage(BaseModel):
    """WebSocket message from server to client."""
    type: str = Field(..., description="Message type (event_type or control)")
    event: Optional[Dict[str, Any]] = Field(None, description="Event data")
    timestamp: Optional[datetime] = Field(None, description="Server timestamp")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


