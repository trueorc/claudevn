"""Models for compute lifecycle timing instrumentation."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TimingPhase(str, Enum):
    """Phases of the compute lifecycle to instrument."""
    WORKSPACE_SETUP = "workspace_setup"
    REPO_CLONE = "repo_clone"
    SDK_LAUNCH = "sdk_launch"
    MCP_TOOL_CALL = "mcp_tool_call"
    API_INFERENCE = "api_inference"
    SDK_EXECUTION = "sdk_execution"
    GIT_PUSH = "git_push"
    TOTAL_WALL_TIME = "total_wall_time"


class TimingEntry(BaseModel):
    """A single timing measurement for a lifecycle phase."""
    phase: TimingPhase = Field(..., description="Lifecycle phase being timed")
    start: datetime = Field(..., description="Phase start timestamp")
    end: Optional[datetime] = Field(None, description="Phase end timestamp")
    duration_ms: Optional[float] = Field(None, description="Duration in milliseconds")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Phase-specific metadata")


class WorkItemTiming(BaseModel):
    """Timing data for a single work item across its lifecycle."""
    work_id: str = Field(..., description="Work item identifier")
    instance_id: str = Field(..., description="Compute instance identifier")
    entries: List[TimingEntry] = Field(default_factory=list, description="Timing entries for each phase")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When timing collection started"
    )
    issue_id: Optional[str] = Field(None, description="Associated issue identifier")
    issue_title: Optional[str] = Field(None, description="Associated issue title")
    directive_id: Optional[str] = Field(None, description="Associated directive identifier")
    directive_title: Optional[str] = Field(None, description="Associated directive title")
    total_cost_usd: Optional[float] = Field(None, description="Total cost in USD")
    input_tokens: Optional[int] = Field(None, description="Total input tokens")
    output_tokens: Optional[int] = Field(None, description="Total output tokens")
    cache_read_tokens: Optional[int] = Field(None, description="Cache read tokens")
    cache_creation_tokens: Optional[int] = Field(None, description="Cache creation tokens")
    num_turns: Optional[int] = Field(None, description="Number of conversation turns")
    session_id: Optional[str] = Field(None, description="SDK session ID")


class AggregateStats(BaseModel):
    """Aggregate timing statistics across recent work items.

    For MCP tool calls, `phase` is MCP_TOOL_CALL and `tool_name` identifies
    the specific tool.  For non-MCP phases, `tool_name` is None.
    """
    phase: TimingPhase = Field(..., description="Lifecycle phase")
    tool_name: Optional[str] = Field(None, description="MCP tool name (cleaned, without claudevn_ prefix)")
    count: int = Field(0, description="Number of measurements")
    avg_ms: float = Field(0.0, description="Average duration in milliseconds")
    p50_ms: float = Field(0.0, description="Median duration in milliseconds")
    p95_ms: float = Field(0.0, description="95th percentile duration in milliseconds")
    p99_ms: float = Field(0.0, description="99th percentile duration in milliseconds")
    min_ms: float = Field(0.0, description="Minimum duration in milliseconds")
    max_ms: float = Field(0.0, description="Maximum duration in milliseconds")


class TimingDashboardResponse(BaseModel):
    """Response for the timing dashboard API."""
    work_items: List[WorkItemTiming] = Field(default_factory=list, description="Recent work item timings")
    aggregates: List[AggregateStats] = Field(default_factory=list, description="Aggregate stats by phase")
    total_work_items: int = Field(0, description="Total work items with timing data")
