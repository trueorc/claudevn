"""Compute connection approval/deny API endpoints.

Manages pending compute connections: list, approve, reject.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from models.compute import ComputeInstance, InstanceStatus
from services.registry_service import ComputeRegistry, get_compute_registry
from services.sse_connection_manager import get_sse_connection_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compute", tags=["compute-approval"])


class ApproveRequest(BaseModel):
    project_ids: Optional[List[str]] = None


class PendingConnectionResponse(BaseModel):
    instance_id: str
    name: str
    capabilities: list
    resources: dict
    labels: list
    tools_available: list
    connected_at: Optional[str] = None
    pending_since: Optional[str] = None


class PendingListResponse(BaseModel):
    pending: list[PendingConnectionResponse]
    count: int


@router.get("/pending", response_model=PendingListResponse)
async def list_pending_connections(
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """List all pending compute connections awaiting approval."""
    pending = await registry.get_pending_instances()
    items = []
    for inst in pending:
        items.append(PendingConnectionResponse(
            instance_id=inst.instance_id,
            name=inst.name,
            capabilities=inst.capabilities.agents if inst.capabilities else [],
            resources=inst.capabilities.resources.model_dump() if inst.capabilities and inst.capabilities.resources else {},
            labels=inst.capabilities.labels if inst.capabilities else [],
            tools_available=inst.capabilities.tools_available if inst.capabilities else [],
            connected_at=inst.metadata.get("connected_at"),
            pending_since=inst.pending_since.isoformat() if inst.pending_since else None,
        ))
    return {"pending": items, "count": len(items)}


@router.post("/{instance_id}/approve")
async def approve_connection(
    instance_id: str,
    body: Optional[ApproveRequest] = None,
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Approve a pending compute connection.

    Transitions the instance from PENDING to ONLINE and sends an
    'approved' SSE event to the compute instance.
    """
    instance = await registry.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")

    if instance.status != InstanceStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Instance {instance_id} is not pending (status: {instance.status.value})",
        )

    project_ids = body.project_ids if body else None
    result = await registry.approve_instance(instance_id, project_ids=project_ids)

    # Send approved SSE event to the compute instance
    sse_manager = get_sse_connection_manager()
    if sse_manager:
        await sse_manager.send_event(instance_id, "approved", {
            "status": "online",
            "project_ids": project_ids or [],
        })

    # Emit observability event
    try:
        from services.observability_event_bus import get_event_bus
        event_bus = get_event_bus()
        if event_bus:
            from models.observability import SystemEvent
            import uuid
            event = SystemEvent(
                event_id=f"ca_{uuid.uuid4().hex[:12]}",
                event_type="compute_approved",
                message=f"Compute instance {instance_id} approved",
                metadata={"instance_id": instance_id},
            )
            await event_bus.emit_event(event)
    except Exception:
        pass  # Non-critical

    return {"approved": True, "instance_id": instance_id, "status": "online"}


@router.post("/{instance_id}/reject")
async def reject_connection(
    instance_id: str,
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Reject a pending compute connection.

    Sends a 'rejected' SSE event, closes the connection, and removes
    the instance from the registry.
    """
    instance = await registry.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")

    # Send rejected SSE event before removing
    sse_manager = get_sse_connection_manager()
    if sse_manager:
        await sse_manager.send_event(instance_id, "rejected", {
            "status": "rejected",
            "message": "Connection denied by administrator",
        })
        # Unregister from SSE manager to close connection
        await sse_manager.unregister_connection(instance_id)

    # Remove from registry
    removed = await registry.reject_instance(instance_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")

    return {"rejected": True, "instance_id": instance_id}
