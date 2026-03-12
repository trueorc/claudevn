"""API endpoints for unified plan summary view.

Provides a consolidated /plan/summary endpoint that aggregates:
- Active work items (running, queued, blocked)
- Planner focus and current profile
- Recent decision traces
- Issue statistics

Reference: Issue #615
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models.decision_trace import DecisionTrace
from models.planner_focus import PlannerFocusSummary
from models.work_map import IssueStatus
from services.bucket_tree_store import get_bucket_tree_store
from services.decision_trace_service import get_decision_trace_service
from services.planner_focus_service import get_planner_focus_service
from services.planner_profile_service import get_planner_profile_service
from services.work_map_service import get_work_map_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plan", tags=["plan"])


class PlanSummaryResponse(BaseModel):
    """Unified plan summary response aggregating all plan view data."""
    project_id: str

    # Counts
    in_progress_count: int = 0
    ready_count: int = 0
    blocked_count: int = 0
    backlog_count: int = 0
    failed_count: int = 0
    implemented_count: int = 0
    done_count: int = 0
    total_count: int = 0

    # Focus
    focus_summary: Optional[str] = None  # optimization_target from PlannerFocusSummary
    primary_intent: Optional[str] = None

    # Active preset
    active_preset: Optional[str] = None
    active_preset_label: Optional[str] = None
    active_preset_color: Optional[str] = None

    # Active work items (the actual items for Running/Up Next/Blocked columns)
    running_items: List[dict] = Field(default_factory=list)  # in_progress issues
    queued_items: List[dict] = Field(default_factory=list)   # ready issues (up next)
    blocked_items: List[dict] = Field(default_factory=list)  # blocked issues
    backlog_items: List[dict] = Field(default_factory=list)  # backlog (waiting on deps)
    failed_items: List[dict] = Field(default_factory=list)   # failed issues
    implemented_items: List[dict] = Field(default_factory=list)  # implemented, pending merge

    # Done items
    done_items: List[dict] = Field(default_factory=list)      # merged to main

    # Decision traces
    recent_traces: List[dict] = Field(default_factory=list)  # last 10 traces
    trace_count: int = 0


def _serialize_issue(issue) -> dict:
    """Serialize an issue for the plan summary response."""
    return {
        "issue_id": issue.issue_id,
        "title": issue.title,
        "status": issue.status.value if hasattr(issue.status, "value") else issue.status,
        "priority": issue.priority.value if hasattr(issue.priority, "value") else issue.priority,
        "assigned_to": issue.assigned_compute_id,
        "goal_id": issue.goal_id,
        "depends_on": issue.depends_on,
        "blocks": issue.blocks,
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
        "started_at": issue.started_at.isoformat() if getattr(issue, "started_at", None) else None,
        "completed_at": issue.completed_at.isoformat() if getattr(issue, "completed_at", None) else None,
        "number": getattr(issue, "number", None),
    }


def _serialize_trace(trace: DecisionTrace) -> dict:
    """Serialize a decision trace for the plan summary response."""
    return {
        "trace_id": trace.trace_id,
        "decision_type": trace.decision_type.value if hasattr(trace.decision_type, "value") else trace.decision_type,
        "decision_summary": trace.decision_summary,
        "timestamp": trace.timestamp.isoformat() if trace.timestamp else None,
        "trigger": trace.trigger.description if trace.trigger else "",
    }


@router.get("/summary", response_model=PlanSummaryResponse)
async def get_plan_summary(
    project_id: Optional[str] = Query(None, description="Project ID to get plan summary for"),
):
    """Get unified plan summary for a project.

    Aggregates:
    - Active work items (in_progress, ready, blocked) with assignment status
    - Current planner profile summary (optimization_target)
    - Recent decision traces (last 10)
    - Issue stats (counts by status)

    Returns a degraded response if services are unavailable.
    """
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")

    response = PlanSummaryResponse(project_id=project_id)

    # Fetch work map data (all project issues, count locally)
    # Note: list_issues().total returns the global issue count, not filtered count.
    # Fetching all project issues in one call and counting locally is both more
    # correct and more efficient than 4 separate filtered queries.
    try:
        work_map_service = get_work_map_service()

        all_result = await work_map_service.list_issues(
            project_id=project_id,
            limit=10000,
        )
        all_issues = all_result.items if hasattr(all_result, "items") else []

        # Partition by status
        in_progress = [i for i in all_issues if i.status == IssueStatus.IN_PROGRESS]
        ready = [i for i in all_issues if i.status == IssueStatus.READY]
        blocked = [i for i in all_issues if i.status == IssueStatus.BLOCKED]
        backlog = [i for i in all_issues if i.status == IssueStatus.BACKLOG]
        failed = [i for i in all_issues if i.status == IssueStatus.FAILED]
        implemented = [i for i in all_issues if i.status == IssueStatus.IMPLEMENTED]
        done = [i for i in all_issues if i.status == IssueStatus.DONE]

        response.running_items = [_serialize_issue(i) for i in in_progress]
        response.queued_items = [_serialize_issue(i) for i in ready[:20]]  # Limit for UI
        response.blocked_items = [_serialize_issue(i) for i in blocked]
        response.backlog_items = [_serialize_issue(i) for i in backlog[:20]]
        response.failed_items = [_serialize_issue(i) for i in failed]
        response.implemented_items = [_serialize_issue(i) for i in implemented]
        response.done_items = [_serialize_issue(i) for i in done]

        response.in_progress_count = len(in_progress)
        response.ready_count = len(ready)
        response.blocked_count = len(blocked)
        response.backlog_count = len(backlog)
        response.failed_count = len(failed)
        response.implemented_count = len(implemented)
        response.done_count = len(done)
        response.total_count = len(all_issues)

    except Exception as e:
        logger.warning(f"Error fetching work map data: {e}")

    # Fetch planner focus summary
    try:
        profile_service = get_planner_profile_service()
        profile = await profile_service.get_profile(project_id)

        goal_list = await work_map_service.list_goals(project_id=project_id)
        active_goals = [
            g for g in (goal_list.items if hasattr(goal_list, "items") else [])
            if g.status not in ("done", "failed", "retired")
            and not getattr(g, "archived", False)
            and getattr(g, "deleted_at", None) is None
        ]

        focus_service = get_planner_focus_service()
        focus_summary = await focus_service.get_focus_summary(
            project_id=project_id,
            profile=profile,
            goals=active_goals,
        )

        response.focus_summary = focus_summary.optimization_target
        response.primary_intent = focus_summary.primary_intent
        response.active_preset = focus_summary.active_preset
        response.active_preset_label = focus_summary.active_preset_label
        response.active_preset_color = focus_summary.active_preset_color

    except RuntimeError as e:
        logger.warning(f"Planner focus service unavailable: {e}")
        response.focus_summary = "Planner focus service unavailable."
    except Exception as e:
        logger.warning(f"Error fetching planner focus: {e}")
        response.focus_summary = "Planner focus service unavailable."

    # Fetch recent decision traces
    try:
        trace_service = get_decision_trace_service()
        traces = await trace_service.get_traces(
            project_id=project_id,
            limit=10,
        )
        response.recent_traces = [_serialize_trace(trace) for trace in traces]
        response.trace_count = len(response.recent_traces)
    except RuntimeError as e:
        logger.warning(f"Decision trace service unavailable: {e}")
    except Exception as e:
        logger.warning(f"Error fetching decision traces: {e}")

    return response
