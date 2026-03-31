"""v2.0 Dispatch API — queue visibility, execution graph, timing, and controls.

Layer 2 endpoints for execution observability and control.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


# -- Response models --

class QueueEntryResponse(BaseModel):
    work_unit_id: str
    goal_id: str
    project_id: str
    priority: int = 0
    description: str = ""
    complexity: str = ""


class ActiveExecutionResponse(BaseModel):
    work_unit_id: str
    goal_id: str
    project_id: str
    instance_id: str
    branch: str = ""
    description: str = ""
    started_at: Optional[str] = None


class GraphNode(BaseModel):
    id: str
    description: str
    status: str
    complexity: str = ""
    goal_id: str = ""
    source_directive_id: Optional[str] = None
    instance_id: Optional[str] = None
    depends_on: List[str] = []
    depended_by: List[str] = []
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class GraphEdge(BaseModel):
    from_id: str  # the dependent unit
    to_id: str    # the prerequisite


class DispatchGraphResponse(BaseModel):
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
    critical_path: List[str] = []


class TimingEntry(BaseModel):
    id: str
    status: str
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    queue_wait_ms: Optional[int] = None
    exec_duration_ms: Optional[int] = None


class DispatchTimingResponse(BaseModel):
    per_unit: List[TimingEntry] = []
    throughput: float = 0.0
    estimated_remaining_ms: Optional[int] = None
    active_count: int = 0
    queued_count: int = 0
    pending_count: int = 0


class DispatchStatusResponse(BaseModel):
    paused: bool = False
    active_count: int = 0
    queue_size: int = 0
    pending_count: int = 0


# -- Endpoints --

@router.get("/queue")
async def get_dispatch_queue(project_id: Optional[str] = None):
    """Get the current dispatch queue — work units waiting for execution."""
    from services.dispatch.dispatcher import get_dispatcher
    dispatcher = get_dispatcher()
    if not dispatcher:
        return []

    items = []
    for unit in dispatcher.queue.queued_items:
        if project_id and unit.project_id != project_id:
            continue
        items.append(QueueEntryResponse(
            work_unit_id=unit.id,
            goal_id=unit.goal_ref,
            project_id=unit.project_id,
            description=unit.description[:80],
            complexity=unit.estimated_complexity or "",
        ))
    return items


@router.get("/active")
async def get_active_executions(project_id: Optional[str] = None):
    """Get currently executing work units."""
    from services.dispatch.dispatcher import get_dispatcher
    dispatcher = get_dispatcher()
    if not dispatcher:
        return []

    items = []
    for unit in dispatcher.active_units:
        if project_id and unit.project_id != project_id:
            continue
        items.append(ActiveExecutionResponse(
            work_unit_id=unit.id,
            goal_id=unit.goal_ref,
            project_id=unit.project_id,
            instance_id=unit.assigned_instance or "",
            branch=unit.branch or "",
            description=unit.description[:80],
            started_at=unit.updated_at.isoformat() if unit.updated_at else None,
        ))
    return items


@router.get("/graph")
async def get_dispatch_graph(project_id: str):
    """Get the full dependency DAG for graph visualization.

    Reads from the unified project plan and builds graph nodes/edges
    with current execution status.
    """
    from services.decomposition.storage import get_project_units
    from services.dispatch.dispatcher import get_dispatcher

    all_units = await get_project_units(project_id)
    if not all_units:
        return DispatchGraphResponse()

    # Filter to active units only (not superseded/cancelled)
    active = [u for u in all_units if u.get("status") not in ("superseded", "cancelled")]

    # Redis IS the source of truth — engine persists every transition there.
    # No overlay needed. Just read what's in Redis.

    active_ids = {u.get("id") for u in active}
    nodes = []
    edges = []

    for u in active:
        uid = u.get("id", "")
        deps = [d for d in u.get("independence", {}).get("depends_on", []) if d in active_ids]
        depby = [d for d in u.get("independence", {}).get("depended_by", []) if d in active_ids]

        # Redis is the source of truth — engine writes every transition there
        status = u.get("status", "draft")
        instance_id = u.get("assigned_instance")

        nodes.append(GraphNode(
            id=uid,
            description=u.get("description", ""),
            status=status,
            complexity=u.get("estimated_complexity", ""),
            goal_id=u.get("goal_ref", ""),
            source_directive_id=u.get("source_directive_id"),
            instance_id=instance_id,
            depends_on=deps,
            depended_by=depby,
            started_at=u.get("updated_at") if status in ("executing", "completed", "verified") else None,
            completed_at=u.get("updated_at") if status in ("completed", "verified") else None,
        ))

        for dep in deps:
            edges.append(GraphEdge(from_id=uid, to_id=dep))

    # Compute critical path (longest chain through non-completed nodes)
    critical_path = _compute_critical_path(nodes)

    return DispatchGraphResponse(nodes=nodes, edges=edges, critical_path=critical_path)


@router.get("/timing")
async def get_dispatch_timing(project_id: str):
    """Get execution timing metrics."""
    from services.decomposition.storage import get_project_units
    from services.dispatch.dispatcher import get_dispatcher

    all_units = await get_project_units(project_id)
    active = [u for u in all_units if u.get("status") not in ("superseded", "cancelled")]

    dispatcher = get_dispatcher()
    active_count = dispatcher.active_count if dispatcher else 0
    queue_size = dispatcher.queue.size if dispatcher else 0
    pending_count = dispatcher.queue.pending_count if dispatcher else 0

    # Build per-unit timing
    per_unit = []
    completed_count = 0
    for u in active:
        status = u.get("status", "draft")
        entry = TimingEntry(
            id=u.get("id", ""),
            status=status,
        )
        if status in ("completed", "verified"):
            completed_count += 1
        per_unit.append(entry)

    # Estimate throughput and remaining time
    remaining = len(active) - completed_count - active_count
    estimated = None
    if completed_count > 0 and remaining > 0:
        # Rough estimate: avg time per unit * remaining
        estimated = remaining * 60000  # placeholder: 1 min per unit

    return DispatchTimingResponse(
        per_unit=per_unit,
        throughput=completed_count / max(1, 1),  # units per session
        estimated_remaining_ms=estimated,
        active_count=active_count,
        queued_count=queue_size,
        pending_count=pending_count,
    )


@router.get("/status")
async def get_dispatch_status():
    """Get dispatcher status — paused, counts."""
    from services.dispatch.dispatcher import get_dispatcher
    dispatcher = get_dispatcher()
    if not dispatcher:
        return DispatchStatusResponse()
    return DispatchStatusResponse(
        paused=dispatcher.is_paused,
        active_count=dispatcher.active_count,
        queue_size=dispatcher.queue.size,
        pending_count=dispatcher.queue.pending_count,
    )


@router.post("/pause")
async def pause_dispatch():
    """Pause the dispatcher — no new work will be assigned."""
    from services.dispatch.dispatcher import get_dispatcher
    dispatcher = get_dispatcher()
    if not dispatcher:
        raise HTTPException(status_code=503, detail="Dispatcher not running")
    dispatcher.pause()
    return {"paused": True}


@router.post("/resume")
async def resume_dispatch():
    """Resume the dispatcher — new work can be assigned."""
    from services.dispatch.dispatcher import get_dispatcher
    dispatcher = get_dispatcher()
    if not dispatcher:
        raise HTTPException(status_code=503, detail="Dispatcher not running")
    dispatcher.resume()
    return {"paused": False}


@router.get("/activity-log")
async def get_activity_log(project_id: str, limit: int = 200):
    """Get persisted activity log for a project. Survives page navigation."""
    import json
    try:
        from services.decomposition.storage import _get_redis
        redis = await _get_redis()
        key = f"claudevn:v2:activity_log:{project_id}"
        raw = await redis.lrange(key, 0, limit - 1)
        events = []
        for item in raw:
            try:
                data = item.decode() if isinstance(item, bytes) else item
                events.append(json.loads(data))
            except Exception:
                pass
        return {"events": events, "count": len(events)}
    except Exception as e:
        return {"events": [], "count": 0, "error": str(e)}


def _compute_critical_path(nodes: List[GraphNode]) -> List[str]:
    """Find the longest chain through non-completed nodes."""
    node_map = {n.id: n for n in nodes}
    # Only consider nodes that haven't completed
    active_ids = {n.id for n in nodes if n.status not in ("completed", "verified")}

    if not active_ids:
        return []

    # Build adjacency (reverse: from dep to dependent)
    dependents_of: Dict[str, List[str]] = {}
    for n in nodes:
        if n.id not in active_ids:
            continue
        for dep in n.depends_on:
            if dep in active_ids:
                dependents_of.setdefault(dep, []).append(n.id)

    # Find roots (no deps among active nodes)
    roots = [nid for nid in active_ids if not any(
        d in active_ids for d in node_map[nid].depends_on
    )]

    # BFS longest path from each root
    longest = []
    for root in roots:
        path = _longest_path_from(root, dependents_of, active_ids)
        if len(path) > len(longest):
            longest = path

    return longest


def _longest_path_from(start: str, dependents_of: Dict[str, List[str]], valid_ids: set) -> List[str]:
    """DFS to find longest path from a starting node."""
    best = [start]
    for dep in dependents_of.get(start, []):
        if dep in valid_ids:
            sub = _longest_path_from(dep, dependents_of, valid_ids)
            candidate = [start] + sub
            if len(candidate) > len(best):
                best = candidate
    return best
