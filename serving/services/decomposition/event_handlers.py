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
    logger.info("Registered decomposition event handlers")


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
