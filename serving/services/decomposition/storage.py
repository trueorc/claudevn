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
    """Get the most recent environment spec for a project (any goal)."""
    redis = await _get_redis()
    goals_key = _PROJECT_GOALS_KEY.format(project_id=project_id)
    goal_ids = await redis.smembers(goals_key)
    if not goal_ids:
        return None

    # Return the most recent environment
    for goal_id in sorted(goal_ids, reverse=True):
        gid = goal_id.decode() if isinstance(goal_id, bytes) else goal_id
        env = await get_environment(project_id, gid)
        if env:
            return env
    return None


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


async def get_project_goals(project_id: str) -> List[str]:
    """Get all goal IDs with v2.0 pipeline results for a project."""
    redis = await _get_redis()
    goals_key = _PROJECT_GOALS_KEY.format(project_id=project_id)
    members = await redis.smembers(goals_key)
    return [m.decode() if isinstance(m, bytes) else m for m in members]
