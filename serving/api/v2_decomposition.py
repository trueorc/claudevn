"""v2.0 Decomposition API — work units, pipeline status, approval, coherence.

Layer 1 endpoints backed by Redis storage from the decomposition pipeline.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.events.event_bus import get_event_bus
from services.events.event_types import DecompositionApproved


async def _get_redis():
    from git.redis_client import get_redis
    return await get_redis()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/decomposition", tags=["decomposition"])


async def _resolve_project_id(goal_id: str) -> str:
    """Look up project_id from a goal."""
    try:
        from services.work_map_service import get_work_map_service
        wm = get_work_map_service()
        goal = await wm.get_goal(goal_id)
        return goal.project_id if goal else ""
    except Exception:
        return ""


@router.get("/{goal_id}/work-units")
async def get_work_units(goal_id: str):
    """Get all work units for a goal's decomposition."""
    from services.decomposition.storage import get_work_units as fetch_units
    project_id = await _resolve_project_id(goal_id)
    units = await fetch_units(project_id, goal_id)
    return {"work_units": units, "count": len(units)}


@router.get("/{goal_id}/pipeline")
async def get_pipeline_status(goal_id: str):
    """Get the full pipeline result — steps with status, work units, environment.

    This is what the Plan page uses to show pipeline step progress.
    """
    from services.decomposition.storage import get_pipeline_result
    project_id = await _resolve_project_id(goal_id)
    result = await get_pipeline_result(project_id, goal_id)
    if not result:
        return {"steps": [], "work_units": [], "success": False, "error": "No pipeline result"}
    return result


@router.post("/{goal_id}/approve")
async def approve_decomposition(goal_id: str):
    """Approve a decomposition — transition work units from draft to ready.

    Updates all draft work units to ready status in Redis,
    then publishes a DecompositionApproved event.
    """
    from services.decomposition.storage import (
        get_work_units,
        get_pipeline_result,
    )
    import json as _json

    project_id = await _resolve_project_id(goal_id)

    # Load and update work units
    units = await get_work_units(project_id, goal_id)
    if not units:
        raise HTTPException(status_code=404, detail="No work units found for this goal")

    approved_ids = []
    for u in units:
        if u.get("status") == "draft":
            u["status"] = "ready"
            approved_ids.append(u.get("id", ""))

    if not approved_ids:
        return {"approved": True, "goal_id": goal_id, "transitioned": 0, "message": "No draft units to approve"}

    # Save updated work units back to Redis
    redis = await _get_redis()
    wu_key = f"claudevn:v2:work_units:{project_id}:{goal_id}"
    await redis.set(wu_key, _json.dumps(units))

    # Also update the pipeline result's work_units
    pipeline_key = f"claudevn:v2:pipeline:{project_id}:{goal_id}"
    pipeline_raw = await redis.get(pipeline_key)
    if pipeline_raw:
        pipeline = _json.loads(pipeline_raw)
        for wu in pipeline.get("work_units", []):
            if wu.get("id") in approved_ids:
                wu["status"] = "ready"
        await redis.set(pipeline_key, _json.dumps(pipeline))

    # Rebuild unified project index so plan/execute pages see the updated status
    from services.decomposition.storage import rebuild_project_units_index
    await rebuild_project_units_index(project_id)

    # Publish event — triggers dispatch queue population via event handler
    bus = get_event_bus()
    await bus.publish(DecompositionApproved(
        project_id=project_id,
        goal_id=goal_id,
        work_unit_ids=approved_ids,
    ))

    logger.info(f"Approved decomposition for {goal_id}: {len(approved_ids)} units transitioned draft → ready")
    return {"approved": True, "goal_id": goal_id, "transitioned": len(approved_ids)}


class RecomposeRequest(BaseModel):
    """Request body for recomposition."""
    refinement: str = Field(..., description="What to change (e.g., 'split the frontend unit')")
    context: Optional[str] = Field(default=None, description="Additional context for the refinement")


@router.post("/{goal_id}/recompose")
async def trigger_recomposition(goal_id: str, body: RecomposeRequest):
    """Trigger a supplemental decomposition pass with refinement context.

    Re-runs the pipeline with the existing decomposition as reference
    plus the specific refinement request. This is not a fresh decomposition —
    the LLM sees what exists and adjusts.
    """
    from services.decomposition.pipeline import DecompositionPipeline
    from services.decomposition.storage import (
        get_pipeline_result,
        get_work_units,
        store_pipeline_result,
    )

    project_id = await _resolve_project_id(goal_id)

    # Get existing decomposition for context
    existing_result = await get_pipeline_result(project_id, goal_id)
    existing_units = await get_work_units(project_id, goal_id)

    # Get the goal
    try:
        from services.work_map_service import get_work_map_service
        wm = get_work_map_service()
        goal = await wm.get_goal(goal_id)
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")
        goal_text = goal.description
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load goal: {e}")

    # Build recomposition context as a conversation comment
    recompose_context = [
        {"content": f"REFINEMENT REQUEST: {body.refinement}"},
    ]
    if body.context:
        recompose_context.append({"content": f"Additional context: {body.context}"})

    # Include existing decomposition as context
    if existing_units:
        unit_summary = "\n".join(
            f"- [{u.get('id', '?')}] {u.get('description', '')} "
            f"(files: {', '.join(u.get('formal_spec', {}).get('target_files', [])[:3])})"
            for u in existing_units[:10]
        )
        recompose_context.append({
            "content": f"EXISTING DECOMPOSITION (adjust, don't start from scratch):\n{unit_summary}"
        })

    # Re-run pipeline
    pipeline = DecompositionPipeline(repo_path=".")
    result = await pipeline.run(
        goal_id=goal_id,
        project_id=project_id,
        goal_text=goal_text,
        conversation_comments=recompose_context,
    )

    # Store updated result
    await store_pipeline_result(
        project_id=project_id,
        goal_id=goal_id,
        result_dict=result.to_dict(),
    )

    # Emit update event
    bus = get_event_bus()
    from services.events.event_types import DecompositionUpdated
    await bus.publish(DecompositionUpdated(
        project_id=project_id,
        goal_id=goal_id,
        work_unit_ids=[wu.id for wu in result.work_units],
        change_type="recomposed",
    ))

    return {
        "success": result.success,
        "work_unit_count": len(result.work_units),
        "refinement": body.refinement,
        "quality_scores": result.quality_scores,
    }


@router.get("/{goal_id}/scores")
async def get_quality_scores(goal_id: str):
    """Get quality scores and confidence for a goal's decomposition."""
    from services.decomposition.storage import get_pipeline_result
    project_id = await _resolve_project_id(goal_id)
    result = await get_pipeline_result(project_id, goal_id)
    if not result:
        raise HTTPException(status_code=404, detail="No pipeline result found")
    scores = result.get("quality_scores")
    if not scores:
        return {"score": 0, "level": "red", "factors": [], "unit_scores": [], "recommendations": []}
    return scores


@router.get("/{goal_id}/chains")
async def get_dependency_chains(goal_id: str):
    """Get dependency chain analysis for a goal's decomposition."""
    from services.decomposition.storage import get_pipeline_result
    project_id = await _resolve_project_id(goal_id)
    result = await get_pipeline_result(project_id, goal_id)
    if not result:
        raise HTTPException(status_code=404, detail="No pipeline result found")
    chains = result.get("chain_analysis")
    if not chains:
        return {"chains": [], "critical_path_id": None, "parallel_groups": [], "max_depth": 0, "total_chains": 0}
    return chains


@router.get("/{goal_id}/environment")
async def get_compute_environment(goal_id: str):
    """Get the compute environment spec for a goal's work units."""
    from services.decomposition.storage import get_environment, get_project_environment
    project_id = await _resolve_project_id(goal_id)

    env = await get_environment(project_id, goal_id)
    if env:
        return env

    # Fall back to project-level environment
    env = await get_project_environment(project_id or goal_id)
    if env:
        return env

    return {
        "id": f"env-{goal_id}", "project_id": project_id,
        "status": "proposed", "requirements": [],
        "base_image": "", "dockerfile_content": "", "work_unit_ids": [],
    }


@router.post("/{goal_id}/environment/approve")
async def approve_environment(goal_id: str):
    """Approve a compute environment — writes Dockerfile + metadata to disk.

    After approval, run ./compute-envs/start.sh <project_name> on the host
    to build and start the compute container.
    """
    from services.decomposition.storage import get_environment
    from services.decomposition.provisioner import write_environment

    project_id = await _resolve_project_id(goal_id)

    # Get the environment spec
    env = await get_environment(project_id, goal_id)
    if not env:
        raise HTTPException(status_code=404, detail="No environment spec found for this goal")

    # Get project name for the directory
    try:
        from services.work_map_service import get_work_map_service
        wm = get_work_map_service()
        goal = await wm.get_goal(goal_id)
        from services.project_service import get_project_service
        ps = get_project_service()
        project = await ps.get_project(goal.project_id) if goal else None
        project_name = project.name if project else project_id
    except Exception:
        project_name = project_id

    # Determine a description from requirements
    runtimes = [r["name"] for r in env.get("requirements", []) if r["name"] not in ("python-packages", "node-packages")]
    desc = "_".join(runtimes[:3]) if runtimes else "default"

    # Write to mounted volume
    safe_name = project_name.lower().replace(' ', '_')
    env_dir = await write_environment(
        project_name=project_name,
        project_id=project_id,
        goal_id=goal_id,
        dockerfile_content=env.get("dockerfile_content", ""),
        requirements=env.get("requirements", []),
        description=desc,
    )

    # Update environment status in Redis to "approved" with project_name
    from services.decomposition.storage import store_environment_update
    await store_environment_update(project_id, goal_id, {
        "status": "approved",
        "project_name": safe_name,
        "run_command": f"./compute-envs/start.sh {safe_name}",
    })

    return {
        "approved": True,
        "goal_id": goal_id,
        "project_name": safe_name,
        "run_command": f"./compute-envs/start.sh {safe_name}",
    }


@router.get("/coherence/{project_id}")
async def get_coherence_insights(project_id: str):
    """Get goal coherence analysis for a project."""
    from services.decomposition.storage import get_coherence
    result = await get_coherence(project_id)
    if not result:
        return {"insights": [], "goals_analyzed": 0}
    return result


@router.post("/coherence/{project_id}/analyze")
async def trigger_coherence_analysis(project_id: str):
    """Trigger coherence analysis across all goals for a project.

    Collects all goals and their work units, runs LLM analysis,
    stores results, and emits an event.
    """
    from services.decomposition.coherence_analyzer import CoherenceAnalyzer
    from services.decomposition.storage import (
        get_project_goals,
        get_work_units,
        store_coherence,
    )

    # Collect goals
    try:
        from services.work_map_service import get_work_map_service
        wm = get_work_map_service()
        goal_list = await wm.list_goals(project_id=project_id)
        goals_data = goal_list.goals if hasattr(goal_list, 'goals') else []
        goals = [
            {
                "goal_id": g.goal_id,
                "title": getattr(g, 'title', '') or getattr(g, 'description', '')[:80],
                "description": getattr(g, 'description', ''),
            }
            for g in goals_data
        ]
    except Exception as e:
        logger.warning(f"Could not load goals for coherence: {e}")
        goals = []

    if len(goals) < 2:
        return {"insights": [], "goals_analyzed": len(goals), "message": "Need at least 2 goals"}

    # Collect work units per goal
    goal_ids = await get_project_goals(project_id)
    work_units_by_goal = {}
    for gid in goal_ids:
        units = await get_work_units(project_id, gid)
        if units:
            work_units_by_goal[gid] = units

    # Run analysis
    analyzer = CoherenceAnalyzer()
    analysis = await analyzer.analyze(project_id, goals, work_units_by_goal)

    # Store results
    import json
    analysis_dict = json.loads(analysis.model_dump_json())
    await store_coherence(project_id, analysis_dict)

    # Emit event
    bus = get_event_bus()
    from services.events.event_types import CoherenceUpdated
    await bus.publish(CoherenceUpdated(
        project_id=project_id,
        insight_count=len(analysis.insights),
        goals_analyzed=analysis.goals_analyzed,
    ))

    return analysis_dict


# -- Project-level Environment endpoints --

@router.get("/project/{project_id}/environment")
async def get_project_environment_unified(project_id: str):
    """Get the unified project-level compute environment.

    Merges requirements from all directives into a single environment.
    This is the canonical environment for the project.
    """
    from services.decomposition.storage import get_unified_project_environment, rebuild_project_environment

    env = await get_unified_project_environment(project_id)
    if not env:
        # Try to build it from per-directive environments
        env = await rebuild_project_environment(project_id)
    if not env:
        return {
            "id": f"env-project-{project_id}", "project_id": project_id,
            "status": "proposed", "requirements": [],
            "base_image": "", "dockerfile_content": "", "work_unit_ids": [],
            "goal_refs": [],
        }
    return env


@router.post("/project/{project_id}/environment/approve")
async def approve_project_environment(project_id: str):
    """Approve the unified project environment.

    Writes Dockerfile + metadata to disk and updates status to approved.
    """
    from services.decomposition.storage import get_unified_project_environment, store_project_environment
    from services.decomposition.provisioner import write_environment

    env = await get_unified_project_environment(project_id)
    if not env:
        raise HTTPException(status_code=404, detail="No project environment found")

    if env.get("status") == "approved":
        return {"approved": True, "project_id": project_id, "message": "Already approved"}

    # Get project name
    try:
        from services.project_service import get_project_service
        ps = get_project_service()
        project = await ps.get_project(project_id)
        project_name = project.name if project else project_id
    except Exception:
        project_name = project_id

    # Determine description from requirements
    runtimes = [r.get("name", "") for r in env.get("requirements", []) if r.get("name") not in ("python-packages", "node-packages")]
    desc = "_".join(runtimes[:3]) if runtimes else "default"

    safe_name = project_name.lower().replace(' ', '_')
    await write_environment(
        project_name=project_name,
        project_id=project_id,
        goal_id=f"project-{project_id}",
        dockerfile_content=env.get("dockerfile_content", ""),
        requirements=env.get("requirements", []),
        description=desc,
    )

    # Update project environment status
    env["status"] = "approved"
    env["project_name"] = safe_name
    env["run_command"] = f"./compute-envs/start.sh {safe_name}"
    await store_project_environment(project_id, env)

    return {
        "approved": True,
        "project_id": project_id,
        "project_name": safe_name,
        "run_command": f"./compute-envs/start.sh {safe_name}",
    }


# -- Unified Project Plan endpoints --

@router.get("/project/{project_id}/plan")
async def get_project_plan(project_id: str):
    """Get the unified project plan — all work units across all directives.

    Returns active units (the current plan) and superseded units (history),
    plus any unresolved conflicts.
    """
    from services.decomposition.storage import get_project_units, get_reconciliation_history

    all_units = await get_project_units(project_id)
    active = [u for u in all_units if u.get("status") not in ("superseded", "cancelled")]
    superseded = [u for u in all_units if u.get("status") == "superseded"]

    # Collect unresolved conflicts from reconciliation history
    recon_history = await get_reconciliation_history(project_id)
    conflicts = []
    for r in recon_history:
        for c in r.get("conflicts", []):
            if not c.get("resolved", False):
                conflicts.append(c)

    # Identify contributing directives
    directive_ids = sorted(set(
        u.get("source_directive_id") or u.get("goal_ref", "")
        for u in all_units
        if u.get("source_directive_id") or u.get("goal_ref")
    ))

    return {
        "active_units": active,
        "superseded_units": superseded,
        "conflicts": conflicts,
        "total_active": len(active),
        "total_superseded": len(superseded),
        "unresolved_conflicts": len(conflicts),
        "directives_contributing": directive_ids,
    }


@router.get("/project/{project_id}/plan/conflicts")
async def get_plan_conflicts(project_id: str):
    """Get unresolved conflicts in the project plan."""
    from services.decomposition.storage import get_reconciliation_history

    recon_history = await get_reconciliation_history(project_id)
    conflicts = []
    for r in recon_history:
        for c in r.get("conflicts", []):
            if not c.get("resolved", False):
                c["directive_id"] = r.get("directive_id", "")
                conflicts.append(c)

    return {"conflicts": conflicts, "count": len(conflicts)}


class ConflictResolutionRequest(BaseModel):
    resolution: str = Field(description="supersede | keep_both | merge")
    supersede_unit_id: Optional[str] = Field(default=None, description="Which unit to supersede (if resolution=supersede)")


@router.post("/project/{project_id}/plan/conflicts/{conflict_id}/resolve")
async def resolve_conflict(project_id: str, conflict_id: str, body: ConflictResolutionRequest):
    """Resolve a plan conflict."""
    import json as _json
    from services.decomposition.storage import (
        get_reconciliation_history,
        get_project_goals,
        rebuild_project_units_index,
        update_work_unit_status,
    )

    # Find the conflict
    recon_history = await get_reconciliation_history(project_id)
    found = False
    for r in recon_history:
        for c in r.get("conflicts", []):
            if c.get("conflict_id") == conflict_id:
                c["resolved"] = True
                c["resolution"] = body.resolution
                found = True

                # Apply supersession if requested
                if body.resolution == "supersede" and body.supersede_unit_id:
                    unit_ids = c.get("unit_ids", [])
                    keep_id = [uid for uid in unit_ids if uid != body.supersede_unit_id]
                    # Find the goal that owns the superseded unit
                    all_units = []
                    for gid in await get_project_goals(project_id):
                        from services.decomposition.storage import get_work_units
                        units = await get_work_units(project_id, gid)
                        for u in units:
                            if u.get("id") == body.supersede_unit_id:
                                await update_work_unit_status(project_id, gid, body.supersede_unit_id, {
                                    "status": "superseded",
                                    "superseded_by": keep_id[0] if keep_id else "",
                                })

                # Re-store the reconciliation result
                from services.decomposition.storage import store_reconciliation_result
                await store_reconciliation_result(project_id, r.get("directive_id", ""), r)
                break
        if found:
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Conflict {conflict_id} not found")

    # Rebuild unified index
    await rebuild_project_units_index(project_id)

    return {"resolved": True, "conflict_id": conflict_id, "resolution": body.resolution}


@router.get("/project/{project_id}/plan/history")
async def get_plan_history(project_id: str):
    """Get reconciliation audit trail — how each directive shaped the plan."""
    from services.decomposition.storage import get_reconciliation_history
    history = await get_reconciliation_history(project_id)
    return {"history": history, "count": len(history)}
