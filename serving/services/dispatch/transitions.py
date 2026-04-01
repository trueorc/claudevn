"""Transition table and action functions for the state machine engine.

Every valid state transition, its conditions, and its action.
The transition table IS the system definition.
"""

import asyncio
import logging
from typing import List

from models.work_unit import WorkUnit, WorkUnitStatus
from .engine import (
    PermanentError,
    RetryPolicy,
    Snapshot,
    StateRedirectError,
    Transition,
    TransientError,
    WorkUnitEngine,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Conditions — pure checks against the snapshot, no side effects
# =============================================================================

def deps_satisfied(unit: WorkUnit, snap: Snapshot) -> bool:
    if not unit.independence.depends_on:
        return True
    return all(dep in snap.completed_unit_ids for dep in unit.independence.depends_on)


def compute_available(unit: WorkUnit, snap: Snapshot) -> bool:
    return not snap.paused and len(snap.idle_compute_ids) > 0


def no_compute_available(unit: WorkUnit, snap: Snapshot) -> bool:
    return not snap.paused and len(snap.idle_compute_ids) == 0


def compute_now_available(unit: WorkUnit, snap: Snapshot) -> bool:
    return not snap.paused and len(snap.idle_compute_ids) > 0


def merge_slot_available(unit: WorkUnit, snap: Snapshot) -> bool:
    return True


# =============================================================================
# Actions
# =============================================================================

async def action_enqueue(unit: WorkUnit, snap: Snapshot, engine: WorkUnitEngine) -> None:
    pass


async def action_mark_waiting(unit: WorkUnit, snap: Snapshot, engine: WorkUnitEngine) -> None:
    pass


async def action_dispatch_to_compute(unit: WorkUnit, snap: Snapshot, engine: WorkUnitEngine) -> None:
    """Send work to an idle compute. Updates compute state atomically."""
    if not snap.idle_compute_ids:
        raise TransientError("No idle compute")

    compute_id = snap.idle_compute_ids[0]
    unit_short = unit.id.replace("wu-", "")
    branch = f"f/work_{unit_short}/{compute_id}"

    # Look up repo URL, auto-create if needed
    repo_url = ""
    try:
        from services.project_service import get_project_service
        ps = get_project_service()
        project = await ps.get_project(unit.project_id)
        if project and not project.repos:
            from models.project import RepoCreateInternalRequest
            await ps.create_internal_repo(
                unit.project_id,
                RepoCreateInternalRequest(name=project.name or "repo", default_branch="main"),
            )
            project = await ps.get_project(unit.project_id)
        if project and project.repos:
            primary = next(
                (r for r in project.repos if r.repo_id == project.primary_repo_id),
                project.repos[0]
            )
            from git.url_utils import externalize_url
            repo_url = externalize_url(primary.url)
    except Exception as e:
        logger.warning(f"Could not look up repo URL: {e}")

    complexity_map = {"xs": "simple", "s": "simple", "m": "standard", "l": "complex", "xl": "complex"}
    complexity = complexity_map.get((unit.estimated_complexity or "m").lower(), "standard")

    target_files = unit.formal_spec.target_files if unit.formal_spec else []
    acceptance_criteria = unit.acceptance_criteria or []
    interface_produces = unit.interface_produces or []
    interface_consumes = unit.interface_consumes or []

    logger.info(
        f"Dispatch {unit.id}: target_files={len(target_files)}, "
        f"criteria={len(acceptance_criteria)}, produces={len(interface_produces)}, "
        f"formal_spec={'yes' if unit.formal_spec else 'NO'}, complexity={complexity}"
    )

    task_data = {
        "task_id": unit.id,
        "title": unit.description[:120],
        "description": unit.description,
        "branch_name": branch,
        "work_type": "feature",
        "complexity_hint": complexity,
        "context": {
            "repository": repo_url,
            "repo_url": repo_url,
            "base_branch": "main",
            "branch": branch,
            "target_files": target_files,
            "acceptance_criteria": acceptance_criteria,
            "interface_produces": interface_produces,
            "interface_consumes": interface_consumes,
            "estimated_complexity": unit.estimated_complexity or "m",
        },
        "work_unit_id": unit.id,
        "goal_id": unit.goal_ref,
        "project_id": unit.project_id,
    }

    # Send to compute
    from services.sse_connection_manager import get_sse_connection_manager
    sse = get_sse_connection_manager()
    if not sse:
        raise PermanentError("SSE manager not available")

    success = await sse.send_event(compute_id=compute_id, event_type="work_assigned", data=task_data)
    if not success:
        raise PermanentError(f"Failed to send to {compute_id}")

    # Mark connection busy (SSE level)
    conn = sse.get_connection(compute_id)
    if conn:
        conn.status = "busy"
        conn.current_task_id = unit.id

    # Update engine's compute state — this compute is now busy
    engine.set_compute_state(compute_id, "busy", assigned_unit_id=unit.id)
    unit.assigned_instance = compute_id
    unit.branch = branch


async def action_enter_merge(unit: WorkUnit, snap: Snapshot, engine: WorkUnitEngine) -> None:
    """Lightweight entry into merge phase. Validates preconditions, then
    kicks off the actual merge as a background task.

    The unit enters MERGING state immediately (visible in UI).
    The background task calls back into the engine when done.
    """
    from services.project_service import get_project_service
    ps = get_project_service()
    project = await ps.get_project(unit.project_id)

    if not project or not project.repos:
        _release_compute(engine, unit)
        engine.mark_completed(unit.id)
        raise StateRedirectError("No repo — completed without merge", target_state=WorkUnitStatus.COMPLETED)

    if not unit.branch:
        raise PermanentError(f"No branch on unit {unit.id}")

    # Start merge in background — unit is now MERGING (observable)
    asyncio.create_task(_run_merge(unit, project, engine))


async def _run_merge(unit: WorkUnit, project, engine: WorkUnitEngine) -> None:
    """Execute the actual merge. Calls back into the engine when done.

    NOT fire-and-forget — every outcome transitions the unit to a new state.
    """
    repo_name = f"{project.project_id}_{project.repos[0].repo_id}"
    branch = unit.branch
    compute_id = unit.assigned_instance or "v2-engine"

    try:
        from git.pr_service import PRService
        pr_service = PRService()

        try:
            await pr_service.create_pr(
                project=repo_name, branch=branch, compute_id=compute_id,
                task_id=unit.id, title=unit.description[:120],
                description=f"Work unit: {unit.id}",
            )
        except Exception as e:
            logger.warning(f"PR creation for {unit.id}: {e}")

        try:
            await pr_service.approve(repo_name, branch, reviewed_by="v2-engine")
        except Exception as e:
            logger.warning(f"PR approval for {unit.id}: {e}")

        result = await pr_service.merge(project=repo_name, branch=branch)

        if result.get("success"):
            _release_compute(engine, unit)
            engine.mark_completed(unit.id)
            await engine._transition_to(unit, WorkUnitStatus.COMPLETED, "merged to main")
            await engine.evaluate()  # Unblock dependents
        elif result.get("reason") == "conflict":
            conflicts = result.get("conflicts", [])[:3]
            unit._conflict_files = conflicts
            await engine._transition_to(
                unit, WorkUnitStatus.MERGE_CONFLICT,
                f"merge conflict: {', '.join(conflicts)}",
            )
            # Dispatch conflict resolution to compute immediately
            await _dispatch_conflict_to_compute(unit)
            await engine.evaluate()
        else:
            reason = result.get("reason", "unknown")
            await engine._transition_to(unit, WorkUnitStatus.FAILED, f"merge failed: {reason}")
            await engine.evaluate()

    except Exception as e:
        logger.error(f"Merge error for {unit.id}: {e}")
        await engine._transition_to(unit, WorkUnitStatus.FAILED, f"merge error: {e}")
        await engine.evaluate()


async def _dispatch_conflict_to_compute(unit: WorkUnit) -> None:
    """Send merge conflict details to the compute for resolution."""
    compute_id = unit.assigned_instance
    if not compute_id:
        logger.error(f"No compute for conflict resolution on {unit.id}")
        return

    try:
        from services.sse_connection_manager import get_sse_connection_manager
        sse = get_sse_connection_manager()
        if sse:
            await sse.send_event(compute_id, "merge_conflict", {
                "issue_id": unit.id,
                "branch": unit.branch or "",
                "conflicting_files": getattr(unit, '_conflict_files', []),
                "message": f"Merge conflict on {unit.branch}",
            })
    except Exception as e:
        logger.error(f"Failed to send conflict to compute {compute_id}: {e}")


def _release_compute(engine: WorkUnitEngine, unit: WorkUnit) -> None:
    """Release a compute back to idle state."""
    if unit.assigned_instance:
        engine.set_compute_state(unit.assigned_instance, "idle", assigned_unit_id=None)
        try:
            from services.sse_connection_manager import get_sse_connection_manager
            sse = get_sse_connection_manager()
            conn = sse.get_connection(unit.assigned_instance) if sse else None
            if conn:
                conn.status = "idle"
                conn.current_task_id = None
        except Exception:
            pass


# =============================================================================
# Transition table
# =============================================================================

def build_transition_table() -> List[Transition]:
    return [
        Transition(
            from_state=WorkUnitStatus.READY, to_state=WorkUnitStatus.QUEUED,
            condition=deps_satisfied, action=action_enqueue,
            description="dependencies satisfied",
        ),
        Transition(
            from_state=WorkUnitStatus.QUEUED, to_state=WorkUnitStatus.EXECUTING,
            condition=compute_available, action=action_dispatch_to_compute,
            description="dispatched to compute",
        ),
        Transition(
            from_state=WorkUnitStatus.QUEUED, to_state=WorkUnitStatus.WAITING_COMPUTE,
            condition=no_compute_available, action=action_mark_waiting,
            description="no compute available",
        ),
        Transition(
            from_state=WorkUnitStatus.WAITING_COMPUTE, to_state=WorkUnitStatus.EXECUTING,
            condition=compute_now_available, action=action_dispatch_to_compute,
            description="compute became available",
        ),
        Transition(
            from_state=WorkUnitStatus.SUBMITTED, to_state=WorkUnitStatus.MERGING,
            condition=merge_slot_available, action=action_enter_merge,
            description="merge started",
        ),
    ]
