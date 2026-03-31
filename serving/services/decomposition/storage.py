"""Redis storage for v2.0 decomposition results.

Stores work units, pipeline results, and environment specs
so the Plan page can retrieve them.
"""

import json
import logging
from typing import Dict, List, Optional

from models.work_unit import WorkUnit, ComputeEnvironmentSpec

logger = logging.getLogger(__name__)

# Redis key patterns
_WU_KEY = "claudevn:v2:work_units:{project_id}:{goal_id}"
_PIPELINE_KEY = "claudevn:v2:pipeline:{project_id}:{goal_id}"
_ENV_KEY = "claudevn:v2:environment:{project_id}:{goal_id}"
_PROJECT_GOALS_KEY = "claudevn:v2:goals:{project_id}"
_COHERENCE_KEY = "claudevn:v2:coherence:{project_id}"
_PROJECT_UNITS_KEY = "claudevn:v2:project_units:{project_id}"
_PROJECT_ENV_KEY = "claudevn:v2:project_environment:{project_id}"
_RECONCILIATION_KEY = "claudevn:v2:reconciliation:{project_id}:{goal_id}"


async def _get_redis():
    from git.redis_client import get_redis
    return await get_redis()


async def store_pipeline_result(project_id: str, goal_id: str, result_dict: dict) -> None:
    """Store the full pipeline result (steps, work units, environment)."""
    redis = await _get_redis()

    # Store pipeline result
    key = _PIPELINE_KEY.format(project_id=project_id, goal_id=goal_id)
    await redis.set(key, json.dumps(result_dict))

    # Store individual work units
    wu_key = _WU_KEY.format(project_id=project_id, goal_id=goal_id)
    wu_data = json.dumps(result_dict.get("work_units", []))
    await redis.set(wu_key, wu_data)

    # Store environment spec
    env = result_dict.get("environment")
    if env:
        env_key = _ENV_KEY.format(project_id=project_id, goal_id=goal_id)
        await redis.set(env_key, json.dumps(env))

    # Track this goal in the project's goal set
    goals_key = _PROJECT_GOALS_KEY.format(project_id=project_id)
    await redis.sadd(goals_key, goal_id)

    logger.info(f"Stored pipeline result for {goal_id}: {result_dict.get('work_unit_count', 0)} units")


async def get_work_units(project_id: str, goal_id: str) -> List[dict]:
    """Get work units for a goal."""
    redis = await _get_redis()
    key = _WU_KEY.format(project_id=project_id, goal_id=goal_id)
    data = await redis.get(key)
    if not data:
        return []
    return json.loads(data)


async def get_pipeline_result(project_id: str, goal_id: str) -> Optional[dict]:
    """Get the full pipeline result for a goal."""
    redis = await _get_redis()
    key = _PIPELINE_KEY.format(project_id=project_id, goal_id=goal_id)
    data = await redis.get(key)
    if not data:
        return None
    return json.loads(data)


async def get_environment(project_id: str, goal_id: str) -> Optional[dict]:
    """Get the environment spec for a goal."""
    redis = await _get_redis()
    env_key = _ENV_KEY.format(project_id=project_id, goal_id=goal_id)
    data = await redis.get(env_key)
    if not data:
        return None
    return json.loads(data)


async def get_project_environment(project_id: str) -> Optional[dict]:
    """Get the project-level environment spec.

    Prefers an approved environment over a proposed one.
    If multiple environments exist across directives, returns
    the approved one (or the most recent proposed if none approved).
    """
    redis = await _get_redis()
    goals_key = _PROJECT_GOALS_KEY.format(project_id=project_id)
    goal_ids = await redis.smembers(goals_key)
    if not goal_ids:
        return None

    # Collect all environments, prefer approved
    approved_env = None
    latest_proposed = None
    for goal_id_raw in goal_ids:
        gid = goal_id_raw.decode() if isinstance(goal_id_raw, bytes) else goal_id_raw
        env = await get_environment(project_id, gid)
        if not env:
            continue
        if env.get("status") == "approved":
            approved_env = env
        elif not latest_proposed:
            latest_proposed = env

    return approved_env or latest_proposed


async def store_environment_update(project_id: str, goal_id: str, updates: dict) -> None:
    """Update fields on a stored environment spec (e.g., status on approval)."""
    redis = await _get_redis()
    env_key = _ENV_KEY.format(project_id=project_id, goal_id=goal_id)
    data = await redis.get(env_key)
    if not data:
        return
    env = json.loads(data)
    env.update(updates)
    await redis.set(env_key, json.dumps(env))
    logger.info(f"Updated environment for {goal_id}: {list(updates.keys())}")


async def cleanup_project(project_id: str) -> dict:
    """Delete all v2.0 data for a project (pipeline, work units, environments)."""
    redis = await _get_redis()
    goals_key = _PROJECT_GOALS_KEY.format(project_id=project_id)
    goal_ids = await redis.smembers(goals_key)

    deleted = 0
    for gid_raw in goal_ids:
        gid = gid_raw.decode() if isinstance(gid_raw, bytes) else gid_raw
        for pattern in [_WU_KEY, _PIPELINE_KEY, _ENV_KEY]:
            key = pattern.format(project_id=project_id, goal_id=gid)
            result = await redis.delete(key)
            deleted += result

    await redis.delete(goals_key)
    deleted += 1

    logger.info(f"Cleaned up {deleted} v2.0 keys for project {project_id}")
    return {"keys_deleted": deleted, "goals_cleaned": len(goal_ids)}


async def get_project_goals(project_id: str) -> List[str]:
    """Get all goal IDs with v2.0 pipeline results for a project."""
    redis = await _get_redis()
    goals_key = _PROJECT_GOALS_KEY.format(project_id=project_id)
    members = await redis.smembers(goals_key)
    return [m.decode() if isinstance(m, bytes) else m for m in members]


# -- Coherence analysis storage --

async def store_coherence(project_id: str, analysis_dict: dict) -> None:
    """Store coherence analysis results for a project."""
    redis = await _get_redis()
    key = _COHERENCE_KEY.format(project_id=project_id)
    await redis.set(key, json.dumps(analysis_dict))
    logger.info(f"Stored coherence analysis for {project_id}: {len(analysis_dict.get('insights', []))} insights")


async def get_coherence(project_id: str) -> Optional[dict]:
    """Get coherence analysis results for a project."""
    redis = await _get_redis()
    key = _COHERENCE_KEY.format(project_id=project_id)
    data = await redis.get(key)
    if not data:
        return None
    return json.loads(data)


# -- Unified project plan storage --

async def store_project_units(project_id: str, units: List[dict]) -> None:
    """Store the unified project work unit index (all active units across directives)."""
    redis = await _get_redis()
    key = _PROJECT_UNITS_KEY.format(project_id=project_id)
    await redis.set(key, json.dumps(units))
    logger.info(f"Stored unified project index for {project_id}: {len(units)} active units")


async def get_project_units(project_id: str) -> List[dict]:
    """Get the unified active work units for a project."""
    redis = await _get_redis()
    key = _PROJECT_UNITS_KEY.format(project_id=project_id)
    data = await redis.get(key)
    if not data:
        return []
    return json.loads(data)


async def rebuild_project_units_index(project_id: str) -> List[dict]:
    """Rebuild the unified project index by scanning all goals.

    Collects all work units across all goals, filters out
    superseded and cancelled units, and writes the unified index.
    """
    goal_ids = await get_project_goals(project_id)
    all_units = []
    for gid in goal_ids:
        units = await get_work_units(project_id, gid)
        for u in units:
            # Tag with source directive if not already set
            if not u.get("source_directive_id"):
                u["source_directive_id"] = gid
            all_units.append(u)

    # Unified index includes ALL units (active + superseded) for the plan view
    # Frontend filters by status
    await store_project_units(project_id, all_units)
    active = [u for u in all_units if u.get("status") not in ("superseded", "cancelled")]
    logger.info(
        f"Rebuilt project index for {project_id}: "
        f"{len(active)} active, {len(all_units) - len(active)} superseded/cancelled"
    )
    return all_units


async def update_work_unit_status(project_id: str, goal_id: str, unit_id: str, updates: dict) -> None:
    """Update specific fields on a work unit in its per-goal Redis key."""
    redis = await _get_redis()
    wu_key = _WU_KEY.format(project_id=project_id, goal_id=goal_id)
    data = await redis.get(wu_key)
    if not data:
        return
    units = json.loads(data)
    for u in units:
        if u.get("id") == unit_id:
            u.update(updates)
            break
    await redis.set(wu_key, json.dumps(units))


# -- Unified project environment --

async def store_project_environment(project_id: str, env_dict: dict) -> None:
    """Store the unified project-level environment spec."""
    redis = await _get_redis()
    key = _PROJECT_ENV_KEY.format(project_id=project_id)
    await redis.set(key, json.dumps(env_dict))
    logger.info(f"Stored project environment for {project_id}: status={env_dict.get('status')}, {len(env_dict.get('requirements', []))} requirements")


async def get_unified_project_environment(project_id: str) -> Optional[dict]:
    """Get the unified project-level environment spec."""
    redis = await _get_redis()
    key = _PROJECT_ENV_KEY.format(project_id=project_id)
    data = await redis.get(key)
    if not data:
        return None
    return json.loads(data)


async def rebuild_project_environment(project_id: str) -> Optional[dict]:
    """Rebuild the unified project environment by merging requirements from all directives.

    Collects requirements from all per-directive environments, deduplicates
    by name, and produces a single project-level environment. If an approved
    environment already exists, preserves its approval status when requirements
    haven't changed.
    """
    goal_ids = await get_project_goals(project_id)
    if not goal_ids:
        return None

    # Collect all per-directive environments
    all_envs = []
    for gid in goal_ids:
        env = await get_environment(project_id, gid)
        if env:
            all_envs.append(env)

    if not all_envs:
        return None

    # Merge requirements by name (deduplicate, keep most specific version)
    merged_reqs = {}
    all_goal_refs = set()
    all_work_unit_ids = set()
    base_image = "ubuntu:24.04"
    dockerfile_content = ""

    for env in all_envs:
        for req in env.get("requirements", []):
            name = req.get("name", "")
            if name not in merged_reqs:
                merged_reqs[name] = req
            else:
                # Keep the one with a version, or the more specific reason
                existing = merged_reqs[name]
                if req.get("version") and not existing.get("version"):
                    merged_reqs[name] = req

        for gref in env.get("goal_refs", []):
            all_goal_refs.add(gref)
        for wuid in env.get("work_unit_ids", []):
            all_work_unit_ids.add(wuid)

        # Use the most detailed Dockerfile (longest)
        dc = env.get("dockerfile_content", "")
        if len(dc) > len(dockerfile_content):
            dockerfile_content = dc
            base_image = env.get("base_image", base_image)

    # Check if existing project env is still valid
    existing_project_env = await get_unified_project_environment(project_id)
    existing_req_names = set()
    if existing_project_env:
        existing_req_names = {r.get("name") for r in existing_project_env.get("requirements", [])}

    new_req_names = set(merged_reqs.keys())
    requirements_changed = new_req_names != existing_req_names

    # Determine status
    if existing_project_env and not requirements_changed:
        # Requirements unchanged — preserve existing status (approved, etc.)
        status = existing_project_env.get("status", "proposed")
        project_name = existing_project_env.get("project_name")
        run_command = existing_project_env.get("run_command")
    elif existing_project_env and existing_project_env.get("status") == "approved" and new_req_names <= existing_req_names:
        # New requirements are a subset — still approved
        status = "approved"
        project_name = existing_project_env.get("project_name")
        run_command = existing_project_env.get("run_command")
    else:
        status = "proposed"
        project_name = None
        run_command = None

    unified = {
        "id": f"env-project-{project_id}",
        "project_id": project_id,
        "goal_refs": sorted(all_goal_refs),
        "requirements": list(merged_reqs.values()),
        "base_image": base_image,
        "dockerfile_content": dockerfile_content,
        "work_unit_ids": sorted(all_work_unit_ids),
        "status": status,
        "project_name": project_name,
        "run_command": run_command,
    }

    await store_project_environment(project_id, unified)

    logger.info(
        f"Rebuilt project environment for {project_id}: "
        f"{len(merged_reqs)} requirements from {len(all_envs)} directives, "
        f"status={status}, changed={requirements_changed}"
    )
    return unified


# -- Reconciliation storage --

async def store_reconciliation_result(project_id: str, goal_id: str, result_dict: dict) -> None:
    """Store reconciliation result for a directive."""
    redis = await _get_redis()
    key = _RECONCILIATION_KEY.format(project_id=project_id, goal_id=goal_id)
    await redis.set(key, json.dumps(result_dict))
    logger.info(
        f"Stored reconciliation for {goal_id}: "
        f"{len(result_dict.get('supersessions', []))} supersessions, "
        f"{len(result_dict.get('conflicts', []))} conflicts"
    )


async def get_reconciliation_result(project_id: str, goal_id: str) -> Optional[dict]:
    """Get reconciliation result for a specific directive."""
    redis = await _get_redis()
    key = _RECONCILIATION_KEY.format(project_id=project_id, goal_id=goal_id)
    data = await redis.get(key)
    if not data:
        return None
    return json.loads(data)


async def get_reconciliation_history(project_id: str) -> List[dict]:
    """Get all reconciliation results for a project (one per directive)."""
    goal_ids = await get_project_goals(project_id)
    results = []
    for gid in goal_ids:
        r = await get_reconciliation_result(project_id, gid)
        if r:
            results.append(r)
    return results
