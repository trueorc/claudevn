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
