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

    # Persist all decomposition events to activity log (survives navigation)
    bus.on("decomposition.started", _persist_project_event)
    bus.on("decomposition.updated", _persist_project_event)
    bus.on("decomposition.approved", _persist_project_event)
    bus.on("decomposition.completed", _persist_project_event)
    bus.on("decomposition.plan_reconciled", _persist_project_event)
    bus.on("coherence.updated", _persist_project_event)

    # Re-run coherence analysis when a decomposition completes
    bus.on("decomposition.updated", _on_decomposition_updated)

    # Enqueue approved work units for dispatch (Plan → Execute bridge)
    bus.on("decomposition.approved", _on_decomposition_approved)

    # Wake the dispatcher when a compute connects or is approved
    bus.on("compute.connected", _on_compute_connected)
    bus.on("compute.instance_approved", _on_compute_available)

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

        # Wait for computes to reconnect before enqueuing work
        # (avoids the race condition where units are dispatched before any compute connects)
        logger.info("Waiting 15s for computes to reconnect before enqueuing ready work...")
        await asyncio.sleep(15)

        # Enqueue any ready units that were never dispatched
        await _enqueue_ready_units_on_startup()
    except Exception as e:
        logger.warning(f"Failed to rebuild project indexes on startup: {e}")


async def _enqueue_ready_units_on_startup():
    """Load all work units into the engine on startup.

    The engine is the sole authority. Load everything from Redis
    so the engine has the full picture and can evaluate correctly.

    After loading, recover stale in-flight units. On restart, no compute
    is running — units stuck in EXECUTING/MERGING/WAITING_COMPUTE must
    be reset so the engine can re-dispatch them.
    """
    try:
        from services.decomposition.storage import get_project_goals, get_work_units, _get_redis
        from services.dispatch.engine import get_engine
        from models.work_unit import WorkUnit, WorkUnitStatus

        engine = get_engine()
        if not engine:
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

        total_tracked = 0
        for project_id in project_ids:
            goal_ids = await get_project_goals(project_id)

            # Load ALL units into the engine — every status, every goal
            for goal_id in goal_ids:
                units_data = await get_work_units(project_id, goal_id)
                for ud in units_data:
                    try:
                        wu = WorkUnit(**ud)
                        engine.track_unit(wu)
                        total_tracked += 1
                    except Exception:
                        pass

        if total_tracked > 0:
            logger.info(f"Startup: loaded {total_tracked} work units into engine")

        # Recover stale in-flight units.
        # On restart, all computes start offline. Any unit in an in-flight
        # state has no compute running it — reset so the engine can act.
        recovered = 0
        for unit_id, unit in list(engine._units.items()):
            if unit.status == WorkUnitStatus.EXECUTING:
                old = unit.status
                unit.status = WorkUnitStatus.QUEUED
                unit.assigned_instance = None
                unit.branch = None
                await engine._persist_and_emit(unit, old, WorkUnitStatus.QUEUED, "startup recovery: stale executing")
                recovered += 1
            elif unit.status == WorkUnitStatus.MERGING:
                old = unit.status
                unit.status = WorkUnitStatus.SUBMITTED
                await engine._persist_and_emit(unit, old, WorkUnitStatus.SUBMITTED, "startup recovery: stale merging")
                recovered += 1
            elif unit.status == WorkUnitStatus.WAITING_COMPUTE:
                old = unit.status
                unit.status = WorkUnitStatus.QUEUED
                await engine._persist_and_emit(unit, old, WorkUnitStatus.QUEUED, "startup recovery: stale waiting")
                recovered += 1

        if recovered > 0:
            logger.info(f"Startup recovery: reset {recovered} stale in-flight units")

        if total_tracked > 0:
            await engine.evaluate()
    except Exception as e:
        logger.warning(f"Failed to load units on startup: {e}")


async def _persist_project_event(event):
    """Persist any project-scoped event to the activity log in Redis."""
    project_id = getattr(event, "project_id", None)
    if not project_id:
        return
    try:
        import json
        from services.decomposition.storage import _get_redis
        redis = await _get_redis()
        event_data = {}
        if hasattr(event, 'model_dump'):
            event_data = json.loads(event.model_dump_json())
        else:
            event_data = {"event": getattr(event, "event", "unknown"), "project_id": project_id}
        log_key = f"claudevn:v2:activity_log:{project_id}"
        await redis.lpush(log_key, json.dumps(event_data))
        await redis.ltrim(log_key, 0, 199)
    except Exception:
        pass


async def _on_compute_connected(event):
    """When a compute connects, evaluate for dispatch."""
    await _trigger_engine_evaluation(getattr(event, "instance_id", ""), "connected")


async def _on_compute_available(event):
    """When a compute is approved, evaluate for dispatch."""
    await _trigger_engine_evaluation(getattr(event, "instance_id", ""), "approved")


async def _trigger_engine_evaluation(instance_id: str, reason: str):
    """Trigger state machine evaluation when compute state changes."""
    logger.info(f"Compute {reason} ({instance_id}) — triggering evaluation")
    try:
        from services.dispatch.engine import get_engine
        engine = get_engine()
        if engine:
            await engine.on_event("compute_available", compute_id=instance_id)
        else:
            logger.error("Engine not available — compute event dropped")
    except Exception as e:
        logger.error(f"Engine evaluation failed: {e}")


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
    """Load approved work units and enqueue them for dispatch.

    Loads ALL units for this goal into the engine — not just ready ones.
    The engine needs to know about superseded/completed units too, because
    other units may depend on them. Terminal units go into _completed_ids
    so deps_satisfied works correctly.
    """
    try:
        from services.decomposition.storage import get_work_units
        from services.dispatch.engine import get_engine
        from models.work_unit import WorkUnit

        engine = get_engine()
        if not engine:
            logger.warning("Engine not available — approved units will not be dispatched")
            return

        # Load ALL work units for this goal — engine needs the complete picture
        units_data = await get_work_units(project_id, goal_id)
        if not units_data:
            logger.warning(f"No work units found for {goal_id} after approval")
            return

        # Convert to WorkUnit objects and track ALL in engine
        work_units = []
        for ud in units_data:
            try:
                wu = WorkUnit(**ud)
                work_units.append(wu)
            except Exception as e:
                logger.warning(f"Could not parse work unit {ud.get('id', '?')}: {e}")

        ready_count = sum(1 for wu in work_units if wu.status.value == "ready")
        if work_units:
            engine.track_units(work_units)
            logger.info(
                f"Loaded {len(work_units)} units ({ready_count} ready) from {goal_id} "
                f"for project {project_id}"
            )

            # State changed (work ready) — trigger evaluation
            await engine.evaluate()

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
