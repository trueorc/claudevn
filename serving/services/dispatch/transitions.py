"""Transition table and action functions for the state machine engine.

Defines every valid state transition, its conditions, and its action.
The transition table IS the system definition.

See docs/design/specifications/state-machine-engine.md
"""

import logging
from typing import List

from models.work_unit import WorkUnit, WorkUnitStatus
from .engine import (
    EvaluationContext,
    PermanentError,
    RetryPolicy,
    StateRedirectError,
    Transition,
    TransientError,
    WorkUnitEngine,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Condition functions — pure checks, no side effects
# =============================================================================

def deps_satisfied(unit: WorkUnit, ctx: EvaluationContext) -> bool:
    """All dependencies are in completed state."""
    if not unit.independence.depends_on:
        return True
    return all(dep in ctx.completed_unit_ids for dep in unit.independence.depends_on)


def compute_available(unit: WorkUnit, ctx: EvaluationContext) -> bool:
    """An idle compute exists and system is not paused.

    idle_computes is already filtered to exclude busy computes.
    If a compute is idle, it can accept work. Period.
    """
    return not ctx.paused and len(ctx.idle_computes) > 0


def no_compute_available(unit: WorkUnit, ctx: EvaluationContext) -> bool:
    """No idle compute available."""
    return not ctx.paused and len(ctx.idle_computes) == 0


def compute_now_available(unit: WorkUnit, ctx: EvaluationContext) -> bool:
    """A compute became available for a waiting unit."""
    return not ctx.paused and len(ctx.idle_computes) > 0


def always_true(unit: WorkUnit, ctx: EvaluationContext) -> bool:
    return True


def merge_slot_available(unit: WorkUnit, ctx: EvaluationContext) -> bool:
    """No other unit is merging for this project."""
    return unit.project_id not in ctx.merging_project_ids


def is_not_paused(unit: WorkUnit, ctx: EvaluationContext) -> bool:
    return not ctx.paused


# =============================================================================
# Action functions — execute the transition
# =============================================================================

async def action_enqueue(unit: WorkUnit, ctx: EvaluationContext, engine: WorkUnitEngine) -> None:
    """Move unit from ready to queued."""
    pass  # Status change is handled by the engine


async def action_mark_waiting(unit: WorkUnit, ctx: EvaluationContext, engine: WorkUnitEngine) -> None:
    """Mark unit as waiting for compute."""
    pass  # Status change handled by engine


async def action_requeue(unit: WorkUnit, ctx: EvaluationContext, engine: WorkUnitEngine) -> None:
    """Move unit from waiting back to queued."""
    pass  # Status change handled by engine


async def action_dispatch_to_compute(unit: WorkUnit, ctx: EvaluationContext, engine: WorkUnitEngine) -> None:
    """Send work to an idle compute instance via SSE."""
    if not ctx.idle_computes:
        raise TransientError("No idle compute available")

    compute_id = ctx.idle_computes[0]

    try:
        from services.sse_connection_manager import get_sse_connection_manager
        sse_manager = get_sse_connection_manager()
        if not sse_manager:
            raise TransientError("SSE manager not available")

        # Build branch name matching git hook convention
        unit_short = unit.id.replace("wu-", "")
        branch = f"f/work_{unit_short}/{compute_id}"

        # Base branch is always main — completed deps are merged there.
        # Feature branches are deleted after merge, so we can't branch from them.
        base_branch = "main"

        # Look up repo URL — auto-create if project has no repo
        repo_url = ""
        try:
            from services.project_service import get_project_service
            ps = get_project_service()
            project = await ps.get_project(unit.project_id)

            # Auto-create repo if none exists
            if project and not project.repos:
                logger.info(f"Auto-creating internal repo for project {unit.project_id}")
                try:
                    from models.project import RepoCreateInternalRequest
                    await ps.create_internal_repo(
                        unit.project_id,
                        RepoCreateInternalRequest(
                            name=project.name or "repo",
                            default_branch="main",
                        ),
                    )
                    # Reload project to get the new repo
                    project = await ps.get_project(unit.project_id)
                except Exception as e:
                    logger.warning(f"Failed to auto-create repo: {e}")

            if project and project.repos:
                primary = next(
                    (r for r in project.repos if r.repo_id == project.primary_repo_id),
                    project.repos[0]
                )
                from git.url_utils import externalize_url
                repo_url = externalize_url(primary.url)
        except Exception as e:
            logger.warning(f"Could not look up repo URL: {e}")

        # Map work unit complexity to compute effort
        complexity_map = {"xs": "simple", "s": "simple", "m": "standard", "l": "complex", "xl": "complex"}
        complexity = complexity_map.get((unit.estimated_complexity or "m").lower(), "standard")

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
                "base_branch": base_branch,
                "branch": branch,
                "target_files": unit.formal_spec.target_files if unit.formal_spec else [],
                "acceptance_criteria": unit.acceptance_criteria or [],
                "interface_produces": unit.interface_produces or [],
                "interface_consumes": unit.interface_consumes or [],
                "estimated_complexity": unit.estimated_complexity or "m",
            },
            "work_unit_id": unit.id,
            "goal_id": unit.goal_ref,
            "project_id": unit.project_id,
        }

        success = await sse_manager.send_event(
            compute_id=compute_id,
            event_type="work_assigned",
            data=task_data,
        )
        if not success:
            raise TransientError(f"Failed to send work_assigned to {compute_id}")

        # Mark the SSE connection as busy so get_idle_connections() excludes it
        conn = sse_manager.get_connection(compute_id)
        if conn:
            conn.status = "busy"
            conn.current_task_id = unit.id

        # Track assignment
        unit.assigned_instance = compute_id
        unit.branch = branch
        engine.assign_compute(unit.id, compute_id)

    except (TransientError, PermanentError):
        raise
    except Exception as e:
        raise TransientError(f"Dispatch failed: {e}")


async def action_mark_submitted(unit: WorkUnit, ctx: EvaluationContext, engine: WorkUnitEngine) -> None:
    """Code complete, branch pushed. Release compute for now."""
    # Compute is held in "merging" state by the SSE connection manager
    # but the engine tracks it as busy until merge completes
    pass


async def action_start_merge(unit: WorkUnit, ctx: EvaluationContext, engine: WorkUnitEngine) -> None:
    """Begin merge of unit's branch to main."""
    engine.start_merge(unit.project_id)

    try:
        from git.pr_service import PRService

        # Get project repo name
        from services.project_service import get_project_service
        ps = get_project_service()
        project = await ps.get_project(unit.project_id)
        if not project or not project.repos:
            # No repo — skip merge, complete directly
            logger.warning(f"No repo for project {unit.project_id} — completing without merge")
            engine.end_merge(unit.project_id)
            engine.release_compute(unit.id)
            engine.mark_completed(unit.id)
            raise StateRedirectError(
                "No repo — completed without merge",
                target_state=WorkUnitStatus.COMPLETED,
            )

        repo_name = f"{project.project_id}_{project.repos[0].repo_id}"
        branch = unit.branch
        if not branch:
            raise PermanentError(f"No branch on unit {unit.id}")

        pr_service = PRService()

        # Create PR
        compute_id = unit.assigned_instance or "v2-engine"
        try:
            await pr_service.create_pr(
                project=repo_name,
                branch=branch,
                compute_id=compute_id,
                task_id=unit.id,
                title=unit.description[:120],
                description=f"Work unit: {unit.id}\n\n{unit.description}",
            )
        except Exception as e:
            logger.warning(f"PR creation for {unit.id}: {e}")

        # Auto-approve (verification is a later state)
        try:
            await pr_service.approve(repo_name, branch, reviewed_by="v2-engine")
        except Exception as e:
            logger.warning(f"PR approval for {unit.id}: {e}")

        # Merge
        result = await pr_service.merge(project=repo_name, branch=branch)

        if result.get("success"):
            # Merge succeeded — action_finalize_merge will be called next
            unit.branch = branch
            logger.info(f"Engine: merge succeeded for {unit.id}")
        elif result.get("reason") == "conflict":
            # Conflict — redirect to MERGE_CONFLICT state
            conflicts = result.get("conflicts", [])
            unit._conflict_files = conflicts  # Store for resolution dispatch
            engine.end_merge(unit.project_id)  # Release merge slot
            raise StateRedirectError(
                f"Merge conflict: {', '.join(conflicts[:3])}",
                target_state=WorkUnitStatus.MERGE_CONFLICT,
            )
        else:
            raise TransientError(f"Merge failed: {result.get('reason', 'unknown')}")

    except (StateRedirectError, PermanentError):
        raise
    except TransientError:
        engine.end_merge(unit.project_id)
        raise
    except Exception as e:
        engine.end_merge(unit.project_id)
        raise TransientError(f"Merge error: {e}")


async def action_finalize_merge(unit: WorkUnit, ctx: EvaluationContext, engine: WorkUnitEngine) -> None:
    """Merge succeeded — finalize and release resources."""
    engine.end_merge(unit.project_id)
    engine.release_compute(unit.id)
    engine.mark_completed(unit.id)

    # Reset compute to idle
    compute_id = unit.assigned_instance
    if compute_id:
        try:
            from services.sse_connection_manager import get_sse_connection_manager
            sse = get_sse_connection_manager()
            conn = sse.get_connection(compute_id) if sse else None
            if conn:
                conn.status = "idle"
                conn.current_task_id = None
        except Exception:
            pass

    logger.info(f"Engine: {unit.id} completed (merged)")


async def action_dispatch_conflict_resolution(unit: WorkUnit, ctx: EvaluationContext, engine: WorkUnitEngine) -> None:
    """Send merge conflict back to compute for resolution."""
    compute_id = unit.assigned_instance
    if not compute_id:
        raise TransientError("No compute assigned for conflict resolution")

    try:
        from services.sse_connection_manager import get_sse_connection_manager
        sse = get_sse_connection_manager()
        if not sse:
            raise TransientError("SSE manager not available")

        await sse.send_event(compute_id, "merge_conflict", {
            "issue_id": unit.id,
            "branch": unit.branch or "",
            "conflicting_files": getattr(unit, '_conflict_files', []),
            "message": f"Merge conflict on {unit.branch}",
        })

        logger.info(f"Engine: sent merge_conflict to {compute_id} for {unit.id}")

    except (TransientError, PermanentError):
        raise
    except Exception as e:
        raise TransientError(f"Failed to dispatch conflict resolution: {e}")


async def action_mark_failed(unit: WorkUnit, ctx: EvaluationContext, engine: WorkUnitEngine) -> None:
    """Permanently fail a unit — release all resources."""
    engine.end_merge(unit.project_id)
    engine.release_compute(unit.id)


# =============================================================================
# Transition table — THE system definition
# =============================================================================

def build_transition_table() -> List[Transition]:
    """Build the complete transition table.

    Each row: from_state → to_state, condition, action, retry policy.
    """
    return [
        # Planning → Dispatch
        Transition(
            from_state=WorkUnitStatus.READY,
            to_state=WorkUnitStatus.QUEUED,
            condition=deps_satisfied,
            action=action_enqueue,
            description="dependencies satisfied",
        ),

        # Dispatch → Execution
        Transition(
            from_state=WorkUnitStatus.QUEUED,
            to_state=WorkUnitStatus.EXECUTING,
            condition=compute_available,
            action=action_dispatch_to_compute,
            retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=10),
            description="dispatched to compute",
        ),
        Transition(
            from_state=WorkUnitStatus.QUEUED,
            to_state=WorkUnitStatus.WAITING_COMPUTE,
            condition=no_compute_available,
            action=action_mark_waiting,
            description="no compute available",
        ),
        Transition(
            from_state=WorkUnitStatus.WAITING_COMPUTE,
            to_state=WorkUnitStatus.EXECUTING,
            condition=compute_now_available,
            action=action_dispatch_to_compute,
            retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=10),
            description="compute became available",
        ),

        # Execution → Merge
        # (SUBMITTED state is set externally when compute reports code_complete)
        Transition(
            from_state=WorkUnitStatus.SUBMITTED,
            to_state=WorkUnitStatus.MERGING,
            condition=merge_slot_available,
            action=action_start_merge,
            retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=5),
            description="merge started",
        ),

        # Merge outcomes
        Transition(
            from_state=WorkUnitStatus.MERGING,
            to_state=WorkUnitStatus.COMPLETED,
            condition=always_true,  # action_start_merge succeeds → this fires
            action=action_finalize_merge,
            description="merged to main",
        ),

        # Conflict resolution
        Transition(
            from_state=WorkUnitStatus.MERGE_CONFLICT,
            to_state=WorkUnitStatus.MERGE_CONFLICT,  # stays in conflict, dispatches resolution
            condition=always_true,
            action=action_dispatch_conflict_resolution,
            retry_policy=RetryPolicy(max_attempts=5, backoff_seconds=0),
            description="conflict resolution dispatched",
        ),
        # After conflict is resolved, compute reports code_complete again
        # which sets unit back to SUBMITTED externally → evaluate → merge retry
    ]
