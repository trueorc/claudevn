"""Event handlers for the decomposition subsystem.

Registers handlers on the EventBus to trigger coherence analysis
when decomposition results change.
"""

import asyncio
import json
import logging

from services.events.event_bus import get_event_bus

logger = logging.getLogger(__name__)


def register_decomposition_handlers():
    """Register all decomposition event handlers on the EventBus.

    Call this during application startup (lifespan).
    """
    bus = get_event_bus()

    # Re-run coherence analysis when a decomposition completes
    bus.on("decomposition.updated", _on_decomposition_updated)

    # Enqueue approved work units for dispatch (Plan → Execute bridge)
    bus.on("decomposition.approved", _on_decomposition_approved)

    # On startup, rebuild unified indexes for all projects with pipeline data
    asyncio.create_task(_rebuild_all_project_indexes())

    logger.info("Registered decomposition event handlers")


async def _rebuild_all_project_indexes():
    """Rebuild unified project indexes on startup.

    Ensures the unified plan index reflects the latest per-goal data,
    including approvals that happened on a previous build.
    """
    try:
        from services.decomposition.storage import (
            rebuild_project_units_index,
            rebuild_project_environment,
        )
        from services.decomposition.storage import _get_redis

        redis = await _get_redis()
        # Find all project goal sets
        keys = []
        cursor = 0
        while True:
            cursor, batch = await redis.scan(cursor, match="claudevn:v2:goals:*", count=100)
            keys.extend(batch)
            if cursor == 0:
                break

        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            project_id = key_str.split(":")[-1]
            try:
                await rebuild_project_units_index(project_id)
                await rebuild_project_environment(project_id)
            except Exception as e:
                logger.warning(f"Failed to rebuild index for {project_id}: {e}")

        if keys:
            logger.info(f"Rebuilt unified indexes for {len(keys)} projects on startup")

        # Also enqueue any ready units that were never dispatched
        # (e.g., approved on a previous build before the event handler existed)
        await _enqueue_ready_units_on_startup()
    except Exception as e:
        logger.warning(f"Failed to rebuild project indexes on startup: {e}")


async def _enqueue_ready_units_on_startup():
    """Find work units in 'ready' status and enqueue them for dispatch.

    Handles the case where units were approved but the dispatch queue
    was never populated (e.g., code was deployed after approval).
    """
    try:
        from services.decomposition.storage import get_project_goals, get_work_units, _get_redis
        from services.dispatch.dispatcher import get_dispatcher
        from models.work_unit import WorkUnit

        dispatcher = get_dispatcher()
        if not dispatcher:
            return

        redis = await _get_redis()
        cursor = 0
        project_ids = []
        while True:
            cursor, batch = await redis.scan(cursor, match="claudevn:v2:goals:*", count=100)
            for key in batch:
                key_str = key.decode() if isinstance(key, bytes) else key
                project_ids.append(key_str.split(":")[-1])
            if cursor == 0:
                break

        total_enqueued = 0
        for project_id in project_ids:
            goal_ids = await get_project_goals(project_id)
            for goal_id in goal_ids:
                units_data = await get_work_units(project_id, goal_id)
                ready_units = [u for u in units_data if u.get("status") == "ready"]
                if ready_units:
                    work_units = []
                    for ud in ready_units:
                        try:
                            work_units.append(WorkUnit(**ud))
                        except Exception:
                            pass
                    if work_units:
                        dispatcher.queue.enqueue_batch(work_units)
                        total_enqueued += len(work_units)

        if total_enqueued > 0:
            logger.info(f"Startup: enqueued {total_enqueued} ready work units for dispatch")
    except Exception as e:
        logger.warning(f"Failed to enqueue ready units on startup: {e}")


async def _on_decomposition_approved(event):
    """When a decomposition is approved, enqueue work units for dispatch.

    This is the critical bridge between Layer 1 (Plan) and Layer 2 (Execute).
    Approved work units transition from the plan into the dispatch queue
    for execution by compute instances.
    """
    project_id = getattr(event, "project_id", None)
    goal_id = getattr(event, "goal_id", None)
    work_unit_ids = getattr(event, "work_unit_ids", [])

    if not project_id or not goal_id:
        return

    asyncio.create_task(_enqueue_approved_units(project_id, goal_id, work_unit_ids))


async def _enqueue_approved_units(project_id: str, goal_id: str, work_unit_ids: list):
    """Load approved work units and enqueue them for dispatch."""
    try:
        from services.decomposition.storage import get_work_units
        from services.dispatch.dispatcher import get_dispatcher
        from models.work_unit import WorkUnit

        dispatcher = get_dispatcher()
        if not dispatcher:
            logger.warning("Dispatcher not available — approved units will not be dispatched")
            return

        # Load work units from Redis
        units_data = await get_work_units(project_id, goal_id)
        if not units_data:
            logger.warning(f"No work units found for {goal_id} after approval")
            return

        # Filter to approved (ready) units
        ready_data = [u for u in units_data if u.get("status") == "ready"]
        if not ready_data:
            logger.info(f"No ready units to enqueue for {goal_id}")
            return

        # Convert dicts to WorkUnit objects and enqueue
        work_units = []
        for ud in ready_data:
            try:
                wu = WorkUnit(**ud)
                work_units.append(wu)
            except Exception as e:
                logger.warning(f"Could not parse work unit {ud.get('id', '?')}: {e}")

        if work_units:
            dispatcher.queue.enqueue_batch(work_units)
            logger.info(
                f"Enqueued {len(work_units)} approved work units from {goal_id} "
                f"for project {project_id}"
            )

            # Emit work.ready_for_dispatch events
            bus = get_event_bus()
            from services.events.event_types import WorkReadyForDispatch
            for wu in work_units:
                await bus.publish(WorkReadyForDispatch(
                    project_id=project_id,
                    work_unit_id=wu.id,
                    goal_id=goal_id,
                ))

    except Exception as e:
        logger.error(f"Failed to enqueue approved units for {goal_id}: {e}")


async def _on_decomposition_updated(event):
    """When work units change, schedule coherence re-analysis.

    Runs asynchronously so it doesn't block the pipeline.
    Only triggers if the project has 2+ goals with pipeline results.
    """
    project_id = getattr(event, "project_id", None)
    if not project_id:
        return

    # Run in background to avoid blocking the event publish
    asyncio.create_task(_run_coherence_if_needed(project_id))


async def _run_coherence_if_needed(project_id: str):
    """Check if coherence analysis should run and execute it."""
    try:
        from services.decomposition.storage import (
            get_project_goals,
            get_work_units,
            store_coherence,
        )

        # Check if we have enough goals
        goal_ids = await get_project_goals(project_id)
        if len(goal_ids) < 2:
            return

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
            logger.warning(f"Could not load goals for auto-coherence: {e}")
            return

        if len(goals) < 2:
            return

        # Collect work units per goal
        work_units_by_goal = {}
        for gid in goal_ids:
            units = await get_work_units(project_id, gid)
            if units:
                work_units_by_goal[gid] = units

        # Run analysis
        from services.decomposition.coherence_analyzer import CoherenceAnalyzer
        analyzer = CoherenceAnalyzer()
        analysis = await analyzer.analyze(project_id, goals, work_units_by_goal)

        # Store results
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

        logger.info(
            f"Auto-coherence for {project_id}: "
            f"{len(analysis.insights)} insights across {analysis.goals_analyzed} goals"
        )
    except Exception as e:
        logger.error(f"Auto-coherence analysis failed for {project_id}: {e}")
