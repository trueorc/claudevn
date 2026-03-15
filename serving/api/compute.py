"""Compute instance registry API endpoints."""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, Depends, Header, Request, status
from fastapi.responses import StreamingResponse

from models.compute import (
    AffinityProfileResponse,
    ComputeAuthStatus,
    ComputeInstance,
    InstanceStatus,
    InstanceCapabilities,
    RegistrationRequest,
    RegistrationResponse,
    HeartbeatRequest,
    UpdateInstanceRequest,
    UpdateProjectTagsRequest,
    DrainRequest,
    DrainStatusResponse,
    InstanceListResponse,
    AggregatedCapabilities,
    ComputeEventRequest,
    ComputeEventResponse,
    KeepaliveEvent,
    CredentialsRefreshEvent,
    DrainEvent,
    RefreshCredentialsRequest,
    RefreshCredentialsResponse,
)
from services.registry_service import ComputeRegistry, get_compute_registry
from services.sse_connection_manager import (
    SSEConnectionManager,
    get_sse_connection_manager,
    event_generator,
)


logger = logging.getLogger(__name__)

# SSE keepalive interval in seconds (configurable via env, default 15s for NAT survival)
SSE_KEEPALIVE_INTERVAL = int(os.getenv("SSE_KEEPALIVE_INTERVAL", "15"))
# SSE event check interval in seconds (how often to check for queued events)
SSE_EVENT_CHECK_INTERVAL = 0.5

router = APIRouter(prefix="/compute", tags=["compute"])



# =============================================================================
# SSE Connection Endpoint (Primary registration method)
# =============================================================================


async def _sse_event_generator(
    compute_id: str,
    registry: ComputeRegistry,
    request: Request,
    sse_manager: Optional[SSEConnectionManager] = None,
) -> AsyncGenerator[str, None]:
    """Generate SSE events for a connected compute instance.

    This generator yields SSE-formatted events and handles the connection lifecycle.
    When the connection is opened, the compute is registered.
    When the connection closes, the compute is deregistered.

    Args:
        compute_id: The compute instance ID
        registry: The compute registry
        request: The FastAPI request (for disconnect detection)
        sse_manager: The SSE connection manager for work assignment events

    Yields:
        SSE-formatted event strings
    """
    try:
        # Send initial connected event with pending status
        instance = await registry.get_instance(compute_id)
        initial_status = instance.status.value if instance else "connected"
        connected_data = json.dumps({
            "status": initial_status,
            "compute_id": compute_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Send pending_approval event if instance starts in PENDING state
        if instance and instance.status == InstanceStatus.PENDING:
            yield f"event: pending_approval\ndata: {connected_data}\n\n"
        else:
            yield f"event: connected\ndata: {connected_data}\n\n"

        # Track when to send next keepalive
        last_keepalive = datetime.now(timezone.utc)

        # Main event loop - check for events frequently, send keepalives periodically
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                logger.info(f"SSE client {compute_id} disconnected")
                break

            # Check if there's an event to send from the registry
            event = await registry.get_pending_event(compute_id)
            if event:
                event_type = event.get("event_type", "unknown")
                event_data = json.dumps(event.get("data", {}))
                yield f"event: {event_type}\ndata: {event_data}\n\n"

            # Check for events from SSE connection manager (work assignments, etc.)
            if sse_manager:
                connection = sse_manager.get_connection(compute_id)
                if connection:
                    try:
                        # Non-blocking check for pending events
                        sse_event = connection._queue.get_nowait()
                        event_type = sse_event.get("event", "unknown")
                        event_data = json.dumps(sse_event.get("data", {}))
                        yield f"event: {event_type}\ndata: {event_data}\n\n"
                    except asyncio.QueueEmpty:
                        pass  # No pending events

            # Check if it's time for a keepalive
            now = datetime.now(timezone.utc)
            elapsed = (now - last_keepalive).total_seconds()
            if elapsed >= SSE_KEEPALIVE_INTERVAL:
                # Update heartbeat in registry to keep instance marked as online
                await registry.update_heartbeat(compute_id)

                # Send keepalive
                keepalive = KeepaliveEvent(
                    timestamp=now.isoformat()
                )
                yield f"event: keepalive\ndata: {keepalive.model_dump_json()}\n\n"
                last_keepalive = now

            # Short wait before next event check (responsive to work assignments)
            await asyncio.sleep(SSE_EVENT_CHECK_INTERVAL)

    except asyncio.CancelledError:
        logger.info(f"SSE connection for {compute_id} was cancelled")
    except Exception as e:
        logger.error(f"SSE error for {compute_id}: {e}")
    finally:
        # Deregister on disconnect
        logger.info(f"Deregistering compute {compute_id} (SSE connection closed)")
        await registry.remove_instance(compute_id)
        # Also unregister from SSE connection manager
        if sse_manager:
            await sse_manager.unregister_connection(compute_id)
        # Revoke MCP API keys so deregistered compute cannot make further calls
        from mcp.auth import revoke_compute_key
        await revoke_compute_key(compute_id)

        # Emit compute_deregistered event for instant UI update
        from services.observability_event_bus import get_event_bus
        from models.observability import ComputeDeregisteredEvent
        import uuid

        event_bus = get_event_bus()
        if event_bus:
            event = ComputeDeregisteredEvent(
                event_id=f"cd_{uuid.uuid4().hex[:12]}",
                compute_id=compute_id,
                reason="sse_disconnect",
                metadata={}
            )
            await event_bus.emit_event(event)
            logger.debug(f"Emitted compute_deregistered event for {compute_id}")


def _parse_capabilities(capabilities_header: Optional[str]) -> list[str]:
    """Parse capabilities from header string.

    Args:
        capabilities_header: Comma-separated capability string

    Returns:
        List of capability strings
    """
    if not capabilities_header:
        return []
    return [c.strip() for c in capabilities_header.split(",") if c.strip()]


def _parse_resources(resources_header: Optional[str]) -> dict:
    """Parse resources from header string.

    Args:
        resources_header: JSON string or comma-separated key=value pairs

    Returns:
        Dictionary of resource values
    """
    if not resources_header:
        return {}

    # Try JSON first (compute sends json.dumps)
    try:
        parsed = json.loads(resources_header)
        if isinstance(parsed, dict):
            # Normalize values like "16gb" -> extract numeric part
            resources = {}
            for key, value in parsed.items():
                if isinstance(value, (int, float)):
                    resources[key] = value
                elif isinstance(value, str):
                    numeric = "".join(c for c in value if c.isdigit() or c == ".")
                    if numeric:
                        resources[key] = float(numeric) if "." in numeric else int(numeric)
                    else:
                        resources[key] = value
            return resources
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: comma-separated key=value pairs
    resources = {}
    for pair in resources_header.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            key = key.strip()
            value = value.strip()
            if value.isdigit():
                resources[key] = int(value)
            elif value.replace(".", "").isdigit():
                resources[key] = float(value)
            else:
                numeric = "".join(c for c in value if c.isdigit() or c == ".")
                if numeric:
                    if "." in numeric:
                        resources[key] = float(numeric)
                    else:
                        resources[key] = int(numeric)
                else:
                    resources[key] = value
    return resources


def _parse_labels(labels_header: Optional[str]) -> list[str]:
    """Parse labels from header string.

    Args:
        labels_header: Comma-separated label string

    Returns:
        List of label strings
    """
    if not labels_header:
        return []
    return [label.strip() for label in labels_header.split(",") if label.strip()]


def _parse_tools_available(tools_header: Optional[str]) -> list[str]:
    """Parse tools_available from header string.

    Args:
        tools_header: Comma-separated tool string

    Returns:
        List of tool strings
    """
    if not tools_header:
        return []
    return [tool.strip() for tool in tools_header.split(",") if tool.strip()]


@router.get("/connect")
async def connect_sse(
    request: Request,
    force: bool = Query(False, description="Force-close existing SSE connection for this compute_id before reconnecting"),
    x_compute_id: str = Header(..., alias="X-Compute-ID", description="Unique compute instance ID"),
    x_capabilities: Optional[str] = Header(None, alias="X-Capabilities", description="Comma-separated capabilities"),
    x_resources: Optional[str] = Header(None, alias="X-Resources", description="Resources as key=value pairs"),
    x_labels: Optional[str] = Header(None, alias="X-Labels", description="Routing labels for work assignment (e.g., production-access,database-admin)"),
    x_tools_available: Optional[str] = Header(None, alias="X-Tools-Available", description="Specialized tools available (e.g., deploy_prod,db_migrate)"),
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Establish SSE connection for compute registration.

    This endpoint establishes a Server-Sent Events (SSE) connection that serves
    as both registration and health signal. The connection itself indicates the
    compute instance is alive - no separate heartbeat polling is needed.

    Instances start in PENDING status and must be approved by an admin before
    receiving work assignments.

    Headers:
        X-Compute-ID: Unique compute instance identifier (required)
        X-Capabilities: Comma-separated list of capabilities (optional)
        X-Resources: Resource specs as key=value pairs, e.g., "cpu=4,memory=16gb" (optional)
        X-Labels: Routing labels for work assignment, e.g., "production-access,database-admin" (optional)
        X-Tools-Available: Specialized tools available, e.g., "deploy_prod,db_migrate" (optional)

    Events sent from server:
        - connected: Initial connection confirmation
        - keepalive: Periodic pulse (every 30 seconds)
        - work_assigned: Work assignment notification
        - work_cancelled: Work cancellation notification
        - shutdown: Graceful shutdown request
        - merge_conflict: Merge conflict notification
        - work_completed: Work completion confirmation

    Returns:
        SSE stream (text/event-stream)
    """
    compute_id = x_compute_id

    # Check network capacity limit
    from config import get_config
    config = get_config()
    max_instances = config.network_capacity.max_compute_instances
    if max_instances > 0:
        current_count = registry.get_instance_count()
        # Only block if this is a new instance (not a reconnect)
        existing_check = await registry.get_instance(compute_id)
        if existing_check is None and current_count >= max_instances:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "CAPACITY_REACHED",
                    "message": f"Network capacity limit reached ({current_count}/{max_instances} instances)",
                    "current": current_count,
                    "max": max_instances,
                }
            )

    # Check if already registered
    existing = await registry.get_instance(compute_id)
    if existing:
        if registry.has_sse_connection(compute_id):
            if force:
                # Force-close the stale server-side connection so this one can proceed
                logger.info(f"Force-closing existing SSE connection for {compute_id}")
                sse_manager = get_sse_connection_manager()
                await sse_manager.unregister_connection(compute_id)
                await registry.remove_instance(compute_id)
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Compute {compute_id} is already connected"
                )
        else:
            # Instance exists but no SSE connection - could be pre-registered via POST /register
            # Don't remove it; just update connection state below
            logger.info(f"Compute {compute_id} already in registry, will update with SSE connection")

    # Parse capabilities, resources, labels, and tools_available from headers
    capabilities = _parse_capabilities(x_capabilities)
    resources = _parse_resources(x_resources)
    labels = _parse_labels(x_labels)
    tools_available = _parse_tools_available(x_tools_available)

    # Build instance capabilities
    instance_capabilities = InstanceCapabilities(
        agents=capabilities,  # For now, capabilities map to agents
        tools=[],
        features=[],
        labels=labels,
        tools_available=tools_available,
    )

    # Apply parsed resources
    if resources:
        from models.compute import InstanceResources
        instance_capabilities.resources = InstanceResources(
            cpu_count=resources.get("cpu"),
            memory_gb=resources.get("memory"),
            gpu_count=resources.get("gpu"),
        )

    # Create and register the instance (starts as PENDING until approved)
    instance = ComputeInstance(
        instance_id=compute_id,
        name=f"Compute {compute_id}",
        endpoint="sse",  # SSE-connected instances don't have HTTP endpoints
        status=InstanceStatus.PENDING,
        pending_since=datetime.now(timezone.utc),
        capabilities=instance_capabilities,
        metadata={
            "connection_type": "sse",
            "connected_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    # Check if instance was pre-registered via POST /register
    already_registered = existing is not None

    try:
        if not already_registered:
            await registry.add_instance(instance)
            logger.info(f"Registered compute {compute_id} via SSE connection")

            # Emit compute_registered event for instant UI update (only if not pre-registered)
            from services.observability_event_bus import get_event_bus
            from models.observability import ComputeRegisteredEvent
            import uuid

            event_bus = get_event_bus()
            if event_bus:
                event = ComputeRegisteredEvent(
                    event_id=f"cr_{uuid.uuid4().hex[:12]}",
                    compute_id=compute_id,
                    name=instance.name,
                    capabilities=capabilities,
                    labels=labels,
                    tools_available=tools_available,
                    metadata={
                        "connection_type": "sse",
                        "endpoint": instance.endpoint,
                    }
                )
                await event_bus.emit_event(event)
                logger.debug(f"Emitted compute_registered event for {compute_id}")
        else:
            # Instance already in registry (pre-registered or loaded from storage after restart).
            was_previously_approved = existing.status != InstanceStatus.PENDING

            if was_previously_approved:
                # Reconnect after restart: preserve approved status, update capabilities
                reconnect_metadata = {
                    "connection_type": "sse",
                    "connected_at": datetime.now(timezone.utc).isoformat(),
                    "sse_reconnected": True,
                }
                await registry.update_instance(
                    compute_id,
                    capabilities=instance_capabilities,
                    metadata=reconnect_metadata,
                )
                await registry.update_heartbeat(compute_id)
                logger.info(
                    f"Compute {compute_id} reconnected — "
                    f"preserved {existing.status.value} status "
                    f"(auth={existing.auth_status.value})"
                )
            else:
                # Genuinely pending — preserve PENDING status but update capabilities
                # (resources are only sent via X-Resources header on SSE connect).
                # update_heartbeat() only updates the timestamp; it does NOT promote
                # PENDING → ONLINE. Only explicit approval via POST /{id}/approve does that.
                await registry.update_instance(
                    compute_id,
                    capabilities=instance_capabilities,
                    metadata={"sse_connected": True},
                )
                await registry.update_heartbeat(compute_id)
                logger.info(f"Compute {compute_id} pre-registered (PENDING preserved), SSE connected")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Also register with SSE connection manager for work assignment
    sse_manager = get_sse_connection_manager()
    await sse_manager.register_connection(
        compute_id=compute_id,
        capabilities=capabilities,
        resources=resources,
        labels=labels,
        tools_available=tools_available
    )
    logger.info(f"Registered compute {compute_id} with SSE connection manager")

    # Return SSE streaming response
    return StreamingResponse(
        _sse_event_generator(compute_id, registry, request, sse_manager),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# =============================================================================
# Compute Events Endpoint (Compute -> Serving)
# =============================================================================


@router.post("/events", response_model=ComputeEventResponse)
async def receive_compute_event(
    event: ComputeEventRequest,
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Receive events from compute instances.

    This endpoint receives events from compute instances about Claude Code
    execution status (started, completed, failed).

    Args:
        event: The compute event
        registry: Compute registry (injected)

    Returns:
        Event acknowledgment

    Raises:
        HTTPException: If compute is not registered
    """
    # Verify compute is registered
    instance = await registry.get_instance(event.compute_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Compute {event.compute_id} is not registered"
        )

    # Process the event
    logger.info(
        f"Received {event.event.value} event from {event.compute_id} "
        f"for task {event.task_id}"
    )

    # Update instance metadata with task status
    metadata_update = {
        f"last_{event.event.value}": event.timestamp,
        "last_task_id": event.task_id,
    }

    if event.event.value == "claude_code_started":
        metadata_update["current_task_id"] = event.task_id
        metadata_update["current_instance_id"] = event.instance_id
    elif event.event.value in ("claude_code_completed", "claude_code_failed"):
        metadata_update["current_task_id"] = None
        metadata_update["current_instance_id"] = None
        if event.exit_code is not None:
            metadata_update["last_exit_code"] = event.exit_code
        if event.duration_seconds is not None:
            metadata_update["last_duration_seconds"] = event.duration_seconds
        if event.error:
            metadata_update["last_error"] = event.error
    elif event.event.value == "claude_code_rejected":
        metadata_update["current_task_id"] = None
        metadata_update["current_instance_id"] = None
        if event.error:
            metadata_update["last_error"] = event.error

    await registry.update_instance(
        instance_id=event.compute_id,
        metadata=metadata_update
    )

    # Record SDK timing telemetry
    if event.event.value == "claude_code_completed":
        try:
            from services.timing_service import get_timing_service
            from models.timing import TimingPhase
            timing_svc = get_timing_service()
            now = datetime.now(timezone.utc)

            # Record API_INFERENCE phase (LLM time)
            if event.duration_api_ms and event.duration_api_ms > 0:
                api_start = now - timedelta(milliseconds=event.duration_api_ms)
                await timing_svc.record_phase(
                    work_id=event.task_id,
                    instance_id=event.compute_id,
                    phase=TimingPhase.API_INFERENCE,
                    start=api_start,
                    end=now,
                )

            # Record SDK_EXECUTION phase (total compute wall time)
            if event.duration_ms and event.duration_ms > 0:
                sdk_start = now - timedelta(milliseconds=event.duration_ms)
                await timing_svc.record_phase(
                    work_id=event.task_id,
                    instance_id=event.compute_id,
                    phase=TimingPhase.SDK_EXECUTION,
                    start=sdk_start,
                    end=now,
                )

            # Record per-tool timing from SDK hooks
            if event.tool_timings:
                for tool_timing in event.tool_timings:
                    tool_name = tool_timing.get("tool_name", "unknown")
                    tool_duration_ms = tool_timing.get("duration_ms", 0)
                    if tool_duration_ms > 0:
                        tool_end = now
                        tool_start = now - timedelta(milliseconds=tool_duration_ms)
                        await timing_svc.record_phase(
                            work_id=event.task_id,
                            instance_id=event.compute_id,
                            phase=TimingPhase.TOOL_USE,
                            start=tool_start,
                            end=tool_end,
                            metadata={"tool_name": tool_name},
                        )

            # Update session-level metrics
            if any([event.cost_usd, event.input_tokens, event.output_tokens,
                    event.num_turns, event.session_id]):
                await timing_svc.update_session_metrics(
                    work_id=event.task_id,
                    instance_id=event.compute_id,
                    cost_usd=event.cost_usd,
                    input_tokens=event.input_tokens,
                    output_tokens=event.output_tokens,
                    cache_read_tokens=event.cache_read_tokens,
                    cache_creation_tokens=event.cache_creation_tokens,
                    num_turns=event.num_turns,
                    session_id=event.session_id,
                )
        except Exception as e:
            logger.warning(f"Failed to record SDK timing telemetry: {e}")

    # Update work item status and trigger dependency cascade
    # Skip for rejected events — re-dispatch handles the task lifecycle
    if event.event.value != "claude_code_rejected":
        await _handle_work_status_update(event)

    # Reset SSE connection to idle so compute can pick up new work.
    # This MUST be here (not inside _handle_work_status_update) because
    # characterization/decomposition tasks (char-*, decomp-*) are not work
    # items — _handle_work_status_update returns early when get_work() is
    # None, skipping the reset if it lived there.
    if event.event.value in ("claude_code_completed", "claude_code_failed", "claude_code_rejected"):
        try:
            sse_manager = get_sse_connection_manager()
            connection = sse_manager.get_connection(event.compute_id)
            if connection:
                connection.status = "idle"
                connection.current_task_id = None
                logger.info(f"Reset SSE connection {event.compute_id} to idle")
        except Exception as e:
            logger.warning(
                f"Failed to reset SSE connection for {event.compute_id}: {e}"
            )

        # Fire the WorkDispatcher — compute is now idle, may have work waiting
        # (characterization tasks, decomposition tasks, or execution work items).
        # This replaces the 2-second polling loop with an immediate push signal.
        try:
            from services.work_dispatcher import get_work_dispatcher
            get_work_dispatcher().trigger(
                reason=f"compute_idle:{event.compute_id}"
            )
        except RuntimeError:
            pass  # Dispatcher not initialized (e.g., test environment)
        except Exception as e:
            logger.debug(f"Could not fire dispatcher on compute idle: {e}")

    # On rejection, attempt to re-dispatch the task to another compute
    if event.event.value == "claude_code_rejected":
        await _handle_rejection_redispatch(event)

    return ComputeEventResponse(
        status="acknowledged",
        event=event.event.value,
        compute_id=event.compute_id,
        task_id=event.task_id,
    )


async def _handle_work_status_update(event: ComputeEventRequest) -> None:
    """Handle work item lifecycle transitions for all compute events.

    - started: ASSIGNED -> IN_PROGRESS
    - completed (exit_code=0): ensure IN_PROGRESS, then COMPLETED + cascade
    - completed (exit_code!=0) or failed: ensure IN_PROGRESS, then FAILED

    Args:
        event: The compute event with task_id, exit_code, etc.
    """
    from services.work_map_service import get_work_map_service
    from models.work_map import WorkStatus

    try:
        work_map = get_work_map_service()
    except RuntimeError:
        logger.warning("Work map service not available, skipping work status update")
        return

    work = await work_map.get_work(event.task_id)
    if not work:
        # Conflict resolution tasks have synthetic IDs: conflict-{work_id}-{random}
        # Extract the original work_id and handle post-conflict re-merge (#55)
        if event.task_id.startswith("conflict-"):
            await _handle_conflict_resolution_completed(event, work_map)
        else:
            logger.debug(
                f"No work item found for task_id={event.task_id}, "
                "skipping work/issue transition"
            )
        return

    # Handle started event
    if event.event.value == "claude_code_started":
        if work.status == WorkStatus.ASSIGNED:
            await work_map.update_status(
                work.work_id, WorkStatus.IN_PROGRESS, event.compute_id
            )
            logger.info(f"Work {work.work_id} started (ASSIGNED -> IN_PROGRESS)")
        return

    # Determine if this is a success or failure event
    is_success = (
        event.event.value == "claude_code_completed"
        and event.exit_code is not None
        and event.exit_code == 0
    )

    # Check if work is already in a terminal/near-terminal state (#829)
    # MCP report_progress(status=COMPLETED) may have already marked it implemented
    already_terminal = work.status in (WorkStatus.IMPLEMENTED, WorkStatus.COMPLETED, WorkStatus.FAILED)

    if already_terminal:
        logger.info(
            f"Work {work.work_id} already {work.status.value}, "
            f"skipping status transition from {event.event.value}"
        )
    elif work.status == WorkStatus.ASSIGNED:
        # Ensure work is IN_PROGRESS before completing/failing
        await work_map.update_status(
            work.work_id, WorkStatus.IN_PROGRESS, event.compute_id
        )
        logger.info(f"Work {work.work_id} auto-transitioned ASSIGNED -> IN_PROGRESS")

    # Perform status transition (unless already terminal)
    if not already_terminal:
        if is_success:
            # Verify branch was actually pushed before marking as completed (#831)
            branch_name = event.branch_name or work.branch_name
            branch_verified = True
            if branch_name and work.project_id:
                try:
                    from git.repo_manager import RepoManager
                    repo_mgr = RepoManager()
                    git_project_name = _resolve_git_project_name(work.project_id)
                    branches = repo_mgr.get_branches(git_project_name)
                    if branch_name not in branches:
                        logger.error(
                            f"Branch {branch_name} not found in {work.project_id} — "
                            f"marking work {work.work_id} as FAILED (#831)"
                        )
                        branch_verified = False
                except Exception as e:
                    logger.warning(f"Branch verification skipped for {work.work_id}: {e}")

            if not branch_verified:
                await work_map.fail_work_and_update_issue(
                    work_id=work.work_id,
                    error=f"Branch {branch_name} not pushed to remote",
                    compute_id=event.compute_id,
                )
                logger.info(
                    f"Work {work.work_id} failed — branch not pushed (task {event.task_id})"
                )
            else:
                # Complete work WITHOUT cascade — PR must merge first (#832)
                await work_map.complete_work(
                    work_id=work.work_id,
                    result={
                        "summary": f"Completed by {event.compute_id}",
                        "exit_code": event.exit_code,
                        "duration_seconds": event.duration_seconds,
                        "branch_name": event.branch_name,
                    },
                    compute_id=event.compute_id,
                    trigger_cascade=False,
                )
                logger.info(
                    f"Work {work.work_id} completed (task {event.task_id}), "
                    "cascade deferred until after PR merge"
                )
        else:
            error = event.error or f"Exit code {event.exit_code}"
            await work_map.fail_work_and_update_issue(
                work_id=work.work_id,
                error=error,
                compute_id=event.compute_id,
            )
            logger.info(
                f"Work {work.work_id} failed (task {event.task_id}): {error}"
            )

    # Post-completion side effects run regardless of who set the terminal state,
    # since MCP progress doesn't handle PR creation or tracking (#829)
    if is_success or (already_terminal and work.status in (WorkStatus.IMPLEMENTED, WorkStatus.COMPLETED)):
        # Record specialization utilization
        try:
            from services.specialization_service import get_specialization_service
            spec_service = get_specialization_service()
            cluster_ids = work.tags if hasattr(work, 'tags') and work.tags else []
            if cluster_ids:
                spec_service.record_completion(event.compute_id, cluster_ids)
        except Exception as e:
            logger.debug(f"Specialization tracking skipped: {e}")

        # Record context affinity
        try:
            from services.context_affinity_service import get_context_affinity_service
            affinity_service = get_context_affinity_service()
            affinity_cluster_ids = work.tags if hasattr(work, 'tags') and work.tags else []
            work_type = getattr(work, 'work_type', None)
            if affinity_cluster_ids:
                affinity_service.record_completion(event.compute_id, affinity_cluster_ids, work_type)
        except Exception as e:
            logger.debug(f"Context affinity tracking skipped: {e}")

        # Auto-create PR and trigger merge if branch exists (#832)
        # finalize_work() inside _auto_create_and_merge_pr handles
        # IMPLEMENTED → COMPLETED + DONE transitions and dependency cascade
        branch_name = event.branch_name or work.branch_name
        merge_ok = False
        if branch_name and work.project_id:
            merge_ok = await _auto_create_and_merge_pr(work, branch_name, event.compute_id)

        if not merge_ok and not already_terminal and branch_name and work.project_id:
            # Merge or quality gates failed on the FIRST attempt — revert so they don't appear done.
            # Skip revert when already_terminal: a duplicate event finding a PR mid-review
            # should not undo the prior event's IMPLEMENTED status.
            logger.warning(
                f"Reverting work {work.work_id} to IN_PROGRESS — PR merge did not succeed"
            )
            await work_map.revert_completed_work(work.work_id)


async def _handle_rejection_redispatch(event: ComputeEventRequest) -> None:
    """Re-dispatch a rejected task to another idle compute.

    When a compute instance rejects a task (e.g., at capacity), this finds
    another idle compute and re-sends the work_assigned event. For work items,
    the rejecting compute is added to the failed_nodes exclusion list.

    Args:
        event: The rejection event with compute_id and task_id
    """
    task_id = event.task_id
    rejecting_compute = event.compute_id

    try:
        sse_manager = get_sse_connection_manager()
    except Exception as e:
        logger.warning(f"SSE manager not available for rejection re-dispatch: {e}")
        return

    # Retrieve the original work_assigned data from the rejecting connection
    rejecting_connection = sse_manager.get_connection(rejecting_compute)
    work_data = rejecting_connection.last_work_assigned_data if rejecting_connection else None

    if not work_data or work_data.get("task_id") != task_id:
        logger.warning(
            f"No stored work_assigned data for task {task_id} on {rejecting_compute}, "
            "cannot re-dispatch"
        )
        # For work items, the orchestrator will eventually retry via its loop
        return

    # Clear stored data on the rejecting connection
    if rejecting_connection:
        rejecting_connection.last_work_assigned_data = None

    # Find another idle compute, excluding the rejector
    new_connection = sse_manager.find_matching_connection(
        idle_only=True,
        exclude_compute_ids={rejecting_compute},
    )

    if not new_connection:
        logger.warning(
            f"No alternative compute available for rejected task {task_id} "
            f"(rejected by {rejecting_compute})"
        )
        # For work items, add rejector to failed_nodes so orchestrator skips it
        _track_rejection_for_orchestrator(task_id, rejecting_compute)
        return

    # Re-dispatch to the new compute — rewrite branch name for the new assignee
    # Branch format is {type}/{issue_id}/{compute_id}, so replace the last segment
    original_branch = work_data["branch_name"]
    branch_parts = original_branch.rsplit("/", 1)
    new_branch = f"{branch_parts[0]}/{new_connection.compute_id}" if len(branch_parts) == 2 else original_branch

    logger.info(
        f"Re-dispatching rejected task {task_id} from {rejecting_compute} "
        f"to {new_connection.compute_id} (branch: {original_branch} -> {new_branch})"
    )
    success = await sse_manager.send_work_assigned(
        compute_id=new_connection.compute_id,
        task_id=work_data["task_id"],
        title=work_data["title"],
        description=work_data["description"],
        branch_name=new_branch,
        skills=work_data["skills"],
        context=work_data["context"],
        mcp_config=work_data["mcp_config"],
    )

    if success:
        logger.info(
            f"Successfully re-dispatched task {task_id} to {new_connection.compute_id}"
        )
    else:
        logger.error(
            f"Failed to re-dispatch task {task_id} to {new_connection.compute_id}"
        )
        _track_rejection_for_orchestrator(task_id, rejecting_compute)


def _track_rejection_for_orchestrator(task_id: str, compute_id: str) -> None:
    """Track a rejection in the work orchestrator's failed_nodes for future exclusion.

    Only applies to work items (not char-*/decomp-* tasks).

    Args:
        task_id: Task ID that was rejected
        compute_id: Compute that rejected the task
    """
    # Characterization/decomposition tasks don't go through the orchestrator
    if task_id.startswith(("char-", "decomp-")):
        return

    try:
        from services.work_orchestrator import get_work_orchestrator
        orchestrator = get_work_orchestrator()
        if task_id not in orchestrator._failed_nodes:
            orchestrator._failed_nodes[task_id] = set()
        orchestrator._failed_nodes[task_id].add(compute_id)
        logger.info(
            f"Tracked rejection of {task_id} by {compute_id} in orchestrator failed_nodes"
        )
    except Exception as e:
        logger.debug(f"Could not track rejection in orchestrator: {e}")


def _resolve_git_project_name(project_id: str) -> str:
    """Resolve a project_id to the git repo name used on disk.

    Git bare repos are named "{project_id}_{repo_id}" (e.g. proj_abc_repo_def),
    not just "{project_id}".  Scans the repos directory for a matching directory
    since this is the most reliable source of truth.
    """
    from git.repo_manager import RepoManager
    repos_path = RepoManager()._repos_path

    # Look for {project_id}.git first (exact match)
    exact = repos_path / f"{project_id}.git"
    if exact.exists():
        return project_id

    # Scan for {project_id}_*.git (compound name)
    matches = list(repos_path.glob(f"{project_id}_*.git"))
    if len(matches) == 1:
        resolved = matches[0].name.replace(".git", "")
        logger.info(f"Resolved git project name: {project_id} -> {resolved}")
        return resolved
    elif len(matches) > 1:
        resolved = matches[0].name.replace(".git", "")
        logger.warning(
            f"Multiple repos for {project_id}: {[m.name for m in matches]}, using {resolved}"
        )
        return resolved

    logger.warning(f"No repo found for project {project_id} in {repos_path}")
    return project_id


async def _dispatch_conflict_resolution_work(
    work, branch_name: str, compute_id: str, pr
) -> None:
    """Dispatch a conflict resolution task to the best available compute.

    Tries the original compute first. If it's disconnected, falls back to
    any idle compute via the SSE connection manager.

    Sends a work_assigned SSE event with is_conflict_resolution=True so the
    spawner checks out the existing conflicting branch rather than creating a new one.

    Args:
        work: Original WorkItem (provides project_id and work_id)
        branch_name: Branch name that has merge conflicts
        compute_id: Compute instance that owns the branch
        pr: PullRequest object (provides conflicting_files)
    """
    from uuid import uuid4
    from git.repo_manager import RepoManager
    from mcp.auth import generate_api_key, register_compute_key

    try:
        git_project_name = _resolve_git_project_name(work.project_id)
        repo_mgr = RepoManager()
        repo_url = repo_mgr.get_repo_url(git_project_name)
        main_head = repo_mgr.get_branch_head(git_project_name, "main") or ""
        conflicting_files = pr.conflicting_files or []

        # Determine target compute: prefer original, fallback to any idle
        sse_manager = get_sse_connection_manager()
        target_compute_id = compute_id

        original_conn = sse_manager.get_connection(compute_id)
        if not original_conn:
            # Original compute disconnected — find any idle compute
            idle_connections = sse_manager.get_idle_connections()
            if idle_connections:
                target_compute_id = idle_connections[0].compute_id
                logger.info(
                    f"Original compute {compute_id} disconnected, "
                    f"routing conflict resolution to {target_compute_id}"
                )
            else:
                logger.warning(
                    f"No available compute for conflict resolution of {branch_name} "
                    f"(original {compute_id} disconnected, no idle computes)"
                )
                return

        task_id = f"conflict-{work.work_id}-{uuid4().hex[:8]}"
        task_api_key = generate_api_key()
        await register_compute_key(target_compute_id, task_api_key)

        files_list = "\n".join(f"  - `{f}`" for f in conflicting_files)
        description = (
            f"## Conflict Resolution Required\n\n"
            f"Branch `{branch_name}` has merge conflicts with main.\n\n"
            f"### Conflicting Files\n{files_list}\n\n"
            f"### Steps\n"
            f"1. `git fetch origin main`\n"
            f"2. `git rebase origin/main`\n"
            f"3. Resolve conflicts in each file (remove `<<<<<<<`, `=======`, `>>>>>>>` markers)\n"
            f"4. `git add <file> && git rebase --continue` for each file\n"
            f"5. `git push --force-with-lease origin {branch_name}`\n"
            f"6. Call `claudevn_complete_task` when done\n\n"
            f"Do NOT create new features or modify behavior."
        )

        success = await sse_manager.send_work_assigned(
            compute_id=target_compute_id,
            task_id=task_id,
            title=f"Resolve conflicts: {branch_name}",
            description=description,
            branch_name=branch_name,
            skills={
                "merged_instructions": (
                    "You are a conflict resolution specialist. Rebase the current branch "
                    "onto main, resolve all merge conflicts, and push. Do NOT add features."
                )
            },
            context={
                "repository": repo_url,
                "base_branch": "main",
                "is_conflict_resolution": True,
                "conflicting_files": conflicting_files,
                "main_head": main_head,
                "original_task_id": work.work_id,
                "original_branch": branch_name,
            },
            mcp_config={
                "server_url": "http://serving:8002",
                "api_key": task_api_key,
            },
        )

        if success:
            logger.info(
                f"Dispatched conflict resolution task {task_id} to {target_compute_id}"
            )
        else:
            logger.warning(
                f"Failed to dispatch conflict resolution to {target_compute_id} "
                f"for {branch_name}"
            )

    except Exception as e:
        logger.error(f"Error dispatching conflict resolution work: {e}")


async def _handle_conflict_resolution_completed(event, work_map) -> None:
    """Handle completion of a conflict resolution task by re-triggering merge.

    Conflict resolution tasks have synthetic IDs: conflict-{work_id}-{random}.
    After the compute rebases and pushes, we need to look up the original work
    item and call _auto_create_and_merge_pr so the PR gets re-approved and
    merged. Without this, resolved PRs stay stuck in 'conflict' status (#55).
    """
    from models.work_map import WorkStatus

    task_id = event.task_id
    is_success = (
        event.event.value == "claude_code_completed"
        and event.exit_code is not None
        and event.exit_code == 0
    )

    # Extract original work_id: "conflict-{work_id}-{random_hex}"
    parts = task_id.split("-", 1)  # ["conflict", "{work_id}-{random}"]
    if len(parts) < 2:
        logger.warning(f"Malformed conflict task_id: {task_id}")
        return

    # work_id format is "work_{hex}" — rejoin everything except the last segment
    remainder = parts[1]  # e.g. "work_abc123-7d65ee98"
    # Split from the right to separate the random suffix
    segments = remainder.rsplit("-", 1)
    if len(segments) == 2:
        original_work_id = segments[0]  # "work_abc123"
    else:
        original_work_id = remainder

    work = await work_map.get_work(original_work_id)
    if not work:
        logger.warning(
            f"Conflict resolution completed ({task_id}) but original work "
            f"{original_work_id} not found"
        )
        return

    if not is_success:
        logger.warning(
            f"Conflict resolution failed for {task_id} "
            f"(exit_code={event.exit_code}), work {original_work_id} unchanged"
        )
        return

    logger.info(
        f"Conflict resolution succeeded ({task_id}), "
        f"re-triggering merge for work {original_work_id}"
    )

    # Re-trigger the PR merge pipeline with the original work item
    # finalize_work() inside _auto_create_and_merge_pr handles cascade
    branch_name = event.branch_name or work.branch_name
    merge_ok = False
    if branch_name and work.project_id:
        merge_ok = await _auto_create_and_merge_pr(work, branch_name, event.compute_id)

    if not merge_ok and branch_name and work.project_id:
        # Merge or quality gates failed after conflict resolution — revert
        logger.warning(
            f"Reverting work {original_work_id} to IN_PROGRESS — "
            f"PR merge did not succeed after conflict resolution"
        )
        await work_map.revert_completed_work(original_work_id)


async def _auto_create_and_merge_pr(work, branch_name: str, compute_id: str) -> bool:
    """Auto-create a PR and trigger merge queue processing after work completion.

    Handles both fresh PRs and post-conflict-resolution re-entry (where
    the PR already exists in CONFLICT status after rebase+push).

    Args:
        work: Completed WorkItem
        branch_name: Branch name with the work's commits
        compute_id: Compute instance that completed the work

    Returns:
        True if the PR was merged successfully, False otherwise.
    """
    from git.pr_service import PRService, PRStatus
    from services.work_map_service import get_work_map_service

    try:
        pr_service = PRService()
        git_project_name = _resolve_git_project_name(work.project_id)

        pr = None
        conflict_resolved = False
        try:
            # Create PR (first time)
            pr = await pr_service.create_pr(
                project=git_project_name,
                branch=branch_name,
                compute_id=compute_id,
                task_id=work.work_id,
                title=work.title,
            )
            logger.info(f"Auto-created PR for branch {branch_name} (work {work.work_id})")
        except ValueError:
            # PR already exists — likely post-conflict-resolution re-entry.
            # Check if the existing PR was in CONFLICT status and conflicts
            # are now resolved after the compute rebased and pushed.
            existing_pr = await pr_service.get_pr(git_project_name, branch_name)
            if existing_pr and existing_pr.status == PRStatus.CONFLICT:
                # Verify conflicts are resolved by running dry-run merge
                dry_run = await pr_service.dry_run_merge(git_project_name, branch_name)
                if dry_run.get("can_merge"):
                    logger.info(
                        f"Conflicts resolved for {branch_name}, re-approving PR"
                    )
                    pr = existing_pr
                    conflict_resolved = True
                else:
                    # Still conflicting — re-dispatch resolution
                    logger.warning(
                        f"PR {branch_name} still has conflicts after resolution attempt"
                    )
                    await _dispatch_conflict_resolution_work(
                        work, branch_name, compute_id, existing_pr
                    )
                    return False
            else:
                # PR exists in a non-conflict state — nothing to do
                logger.info(
                    f"PR already exists for {branch_name} "
                    f"(status: {existing_pr.status.value if existing_pr else 'unknown'})"
                )
                return False

        # If the PR has conflicts on creation (not post-resolution), dispatch resolution.
        if not conflict_resolved and pr.status == PRStatus.CONFLICT:
            logger.warning(
                f"PR has conflicts on creation, dispatching conflict resolution for {branch_name}"
            )
            await _dispatch_conflict_resolution_work(work, branch_name, compute_id, pr)
            return False

        # Run quality gates before auto-approve
        from services.quality_gate_service import get_quality_gate_service
        quality_gate = get_quality_gate_service()
        validation = await quality_gate.validate_branch(git_project_name, branch_name)

        if not validation.passed:
            logger.warning(
                f"Quality gates failed for {branch_name}: "
                + ", ".join(f"{g.gate}={g.status.value}" for g in validation.gates if g.status.value != "passed")
            )
            # Store validation results on PR
            await pr_service.update_status(
                project=git_project_name,
                branch=branch_name,
                status=PRStatus.VALIDATION_FAILED,
                reviewed_by="quality-gate",
            )
            # Store validation details in Redis
            redis = await pr_service._get_redis()
            await redis.set_branch_metadata(
                git_project_name, branch_name, "validation_results", validation.to_dict()
            )
            # Notify compute of validation failure
            sse_manager = pr_service._get_sse_manager()
            await sse_manager.send_event(
                compute_id,
                "validation_failed",
                {
                    "branch": branch_name,
                    "task_id": work.work_id,
                    "validation": validation.to_dict(),
                },
            )
            # Post quality gate failure to project chat so users see it
            failed_gates = [g.gate for g in validation.gates if g.status.value != "passed"]
            failure_msg = (
                f"Quality gates failed for **{work.title}** "
                f"(branch `{branch_name}`): {', '.join(failed_gates)}. "
                "Work reverted to in-progress."
            )
            try:
                from services.conversation_service import get_conversation_service
                conv_service = get_conversation_service()
                await conv_service.add_message(
                    project_id=work.project_id,
                    user_id="system",
                    display_name="System",
                    type="error",
                    content=failure_msg,
                    metadata={"work_id": work.work_id, "branch": branch_name, "event_type": "quality_gate_failed"},
                )
            except Exception as e:
                logger.warning(f"Failed to post quality gate failure to chat: {e}")
            # Emit notification for the notification feed
            try:
                from services.notification_service import get_notification_service
                from models.notification import NotificationLevel, NotificationCategory
                notification_service = get_notification_service()
                if notification_service:
                    notification_service.emit(
                        title=f"Quality gates failed: {work.title}",
                        message=failure_msg,
                        level=NotificationLevel.ERROR,
                        category=NotificationCategory.WORK,
                        project_id=work.project_id,
                        entity_id=work.work_id,
                    )
            except Exception as e:
                logger.debug(f"Could not emit quality gate notification: {e}")
            return False

        logger.info(f"Quality gates passed for {branch_name}")

        # Lead compute review gate — dispatch review to a separate compute
        # instance before auto-approving. If review is unavailable or times
        # out, auto-approve to avoid blocking the pipeline.
        reviewed_by = "auto-approved"
        try:
            from services.lead_compute_service import get_lead_compute_service
            lead_service = get_lead_compute_service()
            if lead_service.enabled:
                review_result = await lead_service.review_pr(
                    project=git_project_name,
                    branch=branch_name,
                    compute_id=compute_id,
                    work_title=work.title,
                    work_description=work.description or "",
                    project_id=work.project_id,
                )
                reviewed_by = f"lead:{review_result.reviewer_id}"

                if not review_result.approved:
                    logger.warning(
                        f"Lead review rejected {branch_name}: {review_result.summary}"
                    )
                    await pr_service.update_status(
                        project=git_project_name,
                        branch=branch_name,
                        status=PRStatus.REJECTED,
                        reviewed_by=reviewed_by,
                    )
                    return False
        except Exception as e:
            logger.debug(f"Lead review skipped for {branch_name}: {e}")

        # Auto-approve (work completed successfully, no conflicts, gates passed)
        await pr_service.update_status(
            project=git_project_name,
            branch=branch_name,
            status=PRStatus.APPROVED,
            reviewed_by=reviewed_by,
        )

        # Add to merge queue (needed for post-resolution re-entry where the
        # branch was popped from the queue during the original failed merge)
        redis = await pr_service._get_redis()
        await redis.add_to_merge_queue(git_project_name, branch_name)

        # Trigger merge queue processing
        results = await pr_service.process_merge_queue(git_project_name)
        for result in results:
            if result.get("success"):
                merged_branch = result.get("branch", branch_name)
                logger.info(f"Auto-merged branch {merged_branch}")

                # Finalize work: IMPLEMENTED → COMPLETED + DONE + cascade
                if merged_branch == branch_name:
                    try:
                        work_map = get_work_map_service()
                        await work_map.finalize_work(work.work_id)
                    except Exception as fin_err:
                        logger.warning(
                            f"Failed to finalize work {work.work_id} after merge: {fin_err}"
                        )

                    # Post completion to project chat
                    try:
                        from services.conversation_service import get_conversation_service
                        conv_service = get_conversation_service()
                        await conv_service.add_message(
                            project_id=work.project_id,
                            user_id="system",
                            display_name="System",
                            type="assistant",
                            content=f"**{work.title}** completed and merged successfully.",
                            metadata={
                                "work_id": work.work_id,
                                "branch": branch_name,
                                "event_type": "work_completed",
                            },
                        )
                    except Exception as chat_err:
                        logger.debug(f"Could not post completion to chat: {chat_err}")
            elif result.get("reason") == "conflict":
                # Merge conflict — dispatch resolution to the branch's compute
                conflict_branch = result.get("branch", branch_name)
                conflict_pr = await pr_service.get_pr(git_project_name, conflict_branch)
                if conflict_pr:
                    dispatch_compute = conflict_pr.compute_id or compute_id
                    await _dispatch_conflict_resolution_work(
                        work, conflict_branch, dispatch_compute, conflict_pr
                    )
            else:
                logger.warning(f"Auto-merge failed for {result.get('branch', branch_name)}: {result.get('error')}")

        # Check if OUR branch was successfully merged
        our_merged = any(
            r.get("success") and r.get("branch", "") == branch_name
            for r in results
        )
        return our_merged

    except Exception as e:
        logger.warning(f"Auto PR/merge failed for {branch_name}: {e}")
        return False


# =============================================================================
# Decomposition Result Endpoint (Compute -> Serving)
# =============================================================================


@router.post("/decomposition/{decomposition_id}/result")
async def submit_decomposition_result(
    decomposition_id: str,
    result: dict,
):
    """Submit decomposition result from compute instance.

    This endpoint allows compute instances to submit goal decomposition results
    without using MCP (which has issues with --print mode in Claude Code 2.1.30).

    Args:
        decomposition_id: The decomposition ID
        result: The decomposition result with issues, confidence, reasoning

    Returns:
        Acknowledgment
    """
    from mcp.tools.decomposition import submit_decomposition, SubmitDecompositionInput, DecomposedIssueInput

    logger.info(f"Received decomposition result for {decomposition_id}")

    try:
        # Convert dict to SubmitDecompositionInput
        issues = []
        for issue_dict in result.get("issues", []):
            issues.append(DecomposedIssueInput(
                temp_id=issue_dict.get("temp_id", ""),
                title=issue_dict.get("title", ""),
                description=issue_dict.get("description", ""),
                issue_type=issue_dict.get("issue_type", "feature"),
                priority=issue_dict.get("priority", "P2"),
                area=issue_dict.get("area", "api"),
                required_skills=issue_dict.get("required_skills", []),
                estimated_complexity=issue_dict.get("estimated_complexity", "m"),
                blocked_by=issue_dict.get("blocked_by", []),
                acceptance_criteria=issue_dict.get("acceptance_criteria", []),
            ))

        input_data = SubmitDecompositionInput(
            decomposition_id=decomposition_id,
            goal_id=result.get("goal_id", "unknown"),
            issues=issues,
            confidence=result.get("confidence", 0.5),
            reasoning=result.get("reasoning", ""),
        )

        response, error = await submit_decomposition(input_data)

        if error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error.message
            )

        return {
            "status": response.status if response else "stored",
            "decomposition_id": decomposition_id,
            "issues_count": response.issues_count if response else len(issues),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing decomposition result: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# =============================================================================
# Characterization Result Endpoint (Compute -> Serving)
# =============================================================================


@router.post("/characterization/{characterization_id}/result")
async def submit_characterization_result(
    characterization_id: str,
    result: dict,
):
    """Submit characterization result from compute instance.

    This endpoint allows compute instances to submit characterization results
    without using MCP (which has issues with --print mode in Claude Code).

    Mirrors the MCP tool ``claudevn_submit_characterization`` but via REST,
    enabling the compute-side spawner to POST results after parsing stdout.

    Args:
        characterization_id: The characterization ID (format: char-{uuid})
        result: The characterization result containing:
            - characterization_id: Tracking ID
            - project_id: Project context
            - characterizations: List of per-item characterization dicts

    Returns:
        Acknowledgment with stored item count
    """
    from mcp.tools.characterization import (
        submit_characterization,
        SubmitCharacterizationInput,
        MeaningInput,
        OntologyTagsInput,
        DependencyInput,
    )

    logger.info(f"Received characterization result for {characterization_id}")

    project_id = result.get("project_id", "unknown")
    characterizations = result.get("characterizations", [])

    if not characterizations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No characterizations provided in result",
        )

    stored_count = 0
    errors = []

    for char_item in characterizations:
        try:
            # Build ontology tags input
            raw_tags = char_item.get("ontology_tags", {})
            ontology_tags = OntologyTagsInput(
                work_type=raw_tags.get("work_type", "feature"),
                lifecycle_stage=raw_tags.get("lifecycle_stage", "build"),
                technical_domains=raw_tags.get("technical_domains", ["backend"]),
                cluster_ids=raw_tags.get("cluster_ids", []),
            )

            # Build meaning input
            raw_meaning = char_item.get("meaning", {})
            meaning = MeaningInput(
                business_summary=raw_meaning.get("business_summary", ""),
                business_user_impact=raw_meaning.get("business_user_impact", ""),
                business_value=raw_meaning.get("business_value", ""),
                technical_summary=raw_meaning.get("technical_summary", ""),
                technical_components=raw_meaning.get("technical_components", []),
                technical_risk=raw_meaning.get("technical_risk", ""),
                contextual_summary=raw_meaning.get("contextual_summary", ""),
                contextual_role=raw_meaning.get("contextual_role", "incremental"),
                related_work_summary=raw_meaning.get("related_work_summary", ""),
            )

            # Build dependencies input — handle both dict and plain string formats.
            # Claude may return deps as ["issue-1"] or [{"target_item_id": "issue-1", ...}]
            dependencies = []
            for dep in char_item.get("dependencies", []):
                if isinstance(dep, str):
                    dependencies.append(DependencyInput(
                        target_item_id=dep,
                        relation="related_to",
                    ))
                else:
                    dependencies.append(DependencyInput(
                        target_item_id=dep.get("target_item_id", ""),
                        relation=dep.get("relation", "related_to"),
                        dependency_type=dep.get("dependency_type", "contextual"),
                        reasoning=dep.get("reasoning", ""),
                        confidence=dep.get("confidence", 0.8),
                    ))

            input_data = SubmitCharacterizationInput(
                characterization_id=characterization_id,
                project_id=char_item.get("project_id", project_id),
                item_id=char_item.get("item_id", ""),
                ontology_tags=ontology_tags,
                meaning=meaning,
                dependencies=dependencies,
                confidence=char_item.get("confidence", 0.8),
                evaluated_in_isolation=char_item.get("evaluated_in_isolation", True),
                evaluated_in_context=char_item.get("evaluated_in_context", False),
                topology_item_count=char_item.get("topology_item_count", 0),
            )

            response, error = await submit_characterization(input_data)

            if error:
                item_id = char_item.get("item_id", "unknown")
                errors.append(f"Item {item_id}: {error.message}")
                logger.warning(f"Failed to store characterization for item {item_id}: {error.message}")
            else:
                stored_count += 1

        except Exception as e:
            item_id = char_item.get("item_id", "unknown")
            errors.append(f"Item {item_id}: {str(e)}")
            logger.error(f"Error processing characterization item {item_id}: {e}", exc_info=True)

    if stored_count == 0 and errors:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"All characterizations failed: {'; '.join(errors)}",
        )

    return {
        "status": "stored",
        "characterization_id": characterization_id,
        "stored_count": stored_count,
        "total_count": len(characterizations),
        "errors": errors if errors else None,
    }


# =============================================================================
# SSE Event Stream Endpoint (For merge notifications - uses SSEConnectionManager)
# =============================================================================


@router.get("/sse/stats")
async def get_sse_stats(
    sse_manager: SSEConnectionManager = Depends(get_sse_connection_manager)
):
    """Get SSE connection statistics.

    Args:
        sse_manager: SSE connection manager (injected)

    Returns:
        SSE connection statistics
    """
    return sse_manager.get_stats()


@router.get("/{instance_id}/events")
async def connect_instance_sse(
    instance_id: str,
    registry: ComputeRegistry = Depends(get_compute_registry),
    sse_manager: SSEConnectionManager = Depends(get_sse_connection_manager)
):
    """Establish SSE connection for receiving events (merge notifications).

    This endpoint allows registered compute instances to receive real-time
    events from Serving, including:
    - merge_conflict: When a branch has conflicts with main
    - work_completed: When a branch is successfully merged
    - keepalive: Periodic ping to maintain connection

    Note: This is separate from the /connect registration endpoint.
    Use this endpoint after registration to receive merge-related events.

    Args:
        instance_id: Compute instance ID (must be registered)
        registry: Compute registry (injected)
        sse_manager: SSE connection manager (injected)

    Returns:
        StreamingResponse with SSE event stream

    Raises:
        HTTPException: If instance not registered
    """
    # Verify instance is registered
    instance = await registry.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found. Please register first."
        )

    # Register SSE connection with capabilities from the instance
    connection = await sse_manager.register_connection(
        compute_id=instance_id,
        capabilities=instance.capabilities.agents if instance.capabilities else [],
        resources={},
        labels=instance.capabilities.labels if instance.capabilities else [],
        tools_available=instance.capabilities.tools_available if instance.capabilities else []
    )

    logger.info(f"SSE event stream established for {instance_id}")

    return StreamingResponse(
        event_generator(connection),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# =============================================================================
# Project Tagging Endpoints
# =============================================================================


@router.put("/{instance_id}/projects", response_model=ComputeInstance)
async def update_project_tags(
    instance_id: str,
    request: UpdateProjectTagsRequest,
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Set project tags for a compute instance.

    Controls which projects this compute can receive work from.
    - Empty list `[]` = benched (no work assigned)
    - Specific IDs `["proj-1", "proj-2"]` = only those projects
    - Wildcard `["*"]` = receives work from any project

    Args:
        instance_id: Compute instance ID
        request: Project tags update request
        registry: Compute registry (injected)

    Returns:
        Updated compute instance

    Raises:
        HTTPException: If instance not found
    """
    instance = await registry.update_project_tags(
        instance_id=instance_id,
        project_ids=request.project_ids,
    )

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )

    logger.info(f"Updated project tags for {instance_id}: {request.project_ids}")
    return instance


@router.get("/search/by-project/{project_id}", response_model=list[ComputeInstance])
async def find_instances_by_project(
    project_id: str,
    online_only: bool = Query(True, description="Only return online instances"),
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Find compute instances tagged for a specific project.

    Returns instances explicitly tagged for this project plus those with
    the '*' wildcard (all projects).

    Args:
        project_id: Project ID to search for
        online_only: Only return online instances
        registry: Compute registry (injected)

    Returns:
        List of instances tagged for the project
    """
    return await registry.get_by_project(
        project_id=project_id,
        online_only=online_only,
    )


# =============================================================================
# Graceful Drain Endpoints
# =============================================================================


@router.post("/{instance_id}/drain", response_model=ComputeInstance)
async def drain_instance(
    instance_id: str,
    request: DrainRequest = DrainRequest(),
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Start graceful drain of a compute instance.

    Removes all project tags (stops new work assignment) and sets status
    to DRAINING. In-flight work continues to completion naturally.

    Args:
        instance_id: Compute instance ID
        request: Drain options (auto_deregister)
        registry: Compute registry (injected)

    Returns:
        Updated compute instance

    Raises:
        HTTPException: If instance not found
    """
    instance = await registry.drain_instance(
        instance_id=instance_id,
        auto_deregister=request.auto_deregister,
    )

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )

    logger.info(f"Initiated drain for {instance_id} (auto_deregister={request.auto_deregister})")
    return instance


@router.get("/{instance_id}/drain", response_model=DrainStatusResponse)
async def get_drain_status(
    instance_id: str,
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Get drain status for a compute instance.

    Returns whether the instance is draining and how many work items
    are still in-flight.

    Args:
        instance_id: Compute instance ID
        registry: Compute registry (injected)

    Returns:
        Drain status with in-flight work details

    Raises:
        HTTPException: If instance not found
    """
    instance = await registry.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )

    is_draining = instance.status == InstanceStatus.DRAINING

    # Find in-flight work for this compute
    in_flight_work_ids = []
    try:
        from services.work_map_service import get_work_map_service
        from models.work_map import WorkStatus

        work_map = get_work_map_service()
        work_response = await work_map.list_work()
        in_flight_work_ids = [
            w.work_id for w in work_response.items
            if w.assigned_to == instance_id
            and w.status in [WorkStatus.ASSIGNED, WorkStatus.IN_PROGRESS, WorkStatus.BLOCKED]
        ]
    except RuntimeError:
        pass  # Work map service not available

    drain_complete = is_draining and len(in_flight_work_ids) == 0
    auto_deregister = instance.metadata.get("auto_deregister_on_drain", False)

    # Auto-deregister if drain is complete and auto_deregister is enabled
    if drain_complete and auto_deregister:
        logger.info(f"Drain complete for {instance_id}, auto-deregistering")
        await registry.remove_instance(instance_id)
    elif drain_complete:
        logger.info(f"Drain complete for {instance_id}, transitioning to OFFLINE")
        instance.status = InstanceStatus.OFFLINE
        instance.drain_started_at = None
        instance.metadata.pop("auto_deregister_on_drain", None)
        await registry._save_to_storage(instance)

    return DrainStatusResponse(
        instance_id=instance_id,
        is_draining=is_draining,
        drain_started_at=instance.drain_started_at.isoformat() if instance.drain_started_at else None,
        in_flight_work_ids=in_flight_work_ids,
        in_flight_count=len(in_flight_work_ids),
        drain_complete=drain_complete,
        auto_deregister=auto_deregister,
    )


@router.delete("/{instance_id}/drain", response_model=ComputeInstance)
async def cancel_drain(
    instance_id: str,
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Cancel an in-progress drain operation.

    Restores the instance to ONLINE status. Project tags remain empty
    and must be re-assigned manually.

    Args:
        instance_id: Compute instance ID
        registry: Compute registry (injected)

    Returns:
        Updated compute instance

    Raises:
        HTTPException: If instance not found
    """
    instance = await registry.cancel_drain(instance_id)

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )

    logger.info(f"Cancelled drain for {instance_id}")
    return instance


# =============================================================================
# Context Affinity Endpoints
# =============================================================================


@router.get("/{instance_id}/affinity", response_model=AffinityProfileResponse)
async def get_affinity_profile(
    instance_id: str,
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Get context affinity profile for a compute instance.

    Returns the domain clusters this instance has built context in,
    with recency and depth information.

    Args:
        instance_id: Compute instance ID
        registry: Compute registry (injected)

    Returns:
        Affinity profile with domain entries

    Raises:
        HTTPException: If instance not found
    """
    instance = await registry.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )

    from services.context_affinity_service import get_context_affinity_service
    affinity_service = get_context_affinity_service()
    profile = affinity_service.get_profile(instance_id)

    if not profile:
        return AffinityProfileResponse(
            compute_id=instance_id,
            entries=[],
            total_tasks_completed=0,
            updated_at=None,
        )

    return AffinityProfileResponse(
        compute_id=profile.compute_id,
        entries=profile.entries,
        total_tasks_completed=profile.total_tasks_completed,
        updated_at=profile.updated_at,
    )


# =============================================================================
# Fleet Credential Management Endpoints
# =============================================================================


@router.post("/refresh-credentials", response_model=RefreshCredentialsResponse)
async def refresh_credentials(
    request: RefreshCredentialsRequest = RefreshCredentialsRequest(),
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Send credential refresh signal to compute instances.

    Sends a credentials_refresh SSE event to connected compute instances,
    triggering them to reload credentials from disk (equivalent to SIGHUP).

    If instance_ids is None, refreshes all connected instances.
    If instance_ids is provided, refreshes only those specific instances.

    Args:
        request: Refresh request with optional instance_ids and reason
        registry: Compute registry (injected)

    Returns:
        Response with list of notified and failed instances
    """
    sse_manager = get_sse_connection_manager()

    # Determine target instances
    if request.instance_ids:
        target_ids = request.instance_ids
    else:
        # All connected instances
        target_ids = list(sse_manager._connections.keys())

    notified = []
    failed = []

    refresh_event = CredentialsRefreshEvent(reason=request.reason)

    for compute_id in target_ids:
        connection = sse_manager.get_connection(compute_id)
        if connection:
            try:
                await connection.send_event(
                    "credentials_refresh", refresh_event.model_dump()
                )
                notified.append(compute_id)
                logger.info(f"Sent credentials_refresh to {compute_id}")
            except Exception as e:
                failed.append(compute_id)
                logger.error(f"Failed to send credentials_refresh to {compute_id}: {e}")
        else:
            failed.append(compute_id)
            logger.warning(f"No SSE connection for {compute_id}, cannot send refresh")

    status_str = "sent" if notified else "no_instances"
    if failed:
        status_str = "partial" if notified else "failed"

    logger.info(
        f"Credential refresh: {len(notified)} notified, {len(failed)} failed"
    )

    return RefreshCredentialsResponse(
        status=status_str,
        instances_notified=notified,
        instances_failed=failed,
        total_notified=len(notified),
    )


@router.post("/{instance_id}/drain-for-restart")
async def drain_for_restart(
    instance_id: str,
    grace_period: int = 300,
    reason: str = "Credential refresh failed, draining for restart",
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Send drain event to a compute instance for graceful restart.

    This is a fallback when runtime credential reload fails. The compute
    instance stops accepting new work, waits for running tasks to complete,
    then can be safely restarted.

    Args:
        instance_id: Compute instance ID
        grace_period: Seconds to wait before forced stop
        reason: Reason for the drain
        registry: Compute registry (injected)

    Returns:
        Acknowledgment

    Raises:
        HTTPException: If instance not found or not connected
    """
    sse_manager = get_sse_connection_manager()
    connection = sse_manager.get_connection(instance_id)

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No SSE connection for {instance_id}"
        )

    drain_event = DrainEvent(
        reason=reason,
        grace_period_seconds=grace_period,
    )

    try:
        await connection.send_event("drain", drain_event.model_dump())
        logger.info(
            f"Sent drain event to {instance_id} "
            f"(grace_period={grace_period}s, reason={reason})"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send drain event: {e}"
        )

    # Also update registry status
    await registry.drain_instance(instance_id=instance_id, auto_deregister=False)

    return {
        "status": "drain_sent",
        "instance_id": instance_id,
        "grace_period_seconds": grace_period,
        "reason": reason,
    }


# =============================================================================
# Approval Endpoints
# =============================================================================


@router.get("/pending")
async def list_pending_instances(
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """List all compute instances awaiting approval.

    Returns:
        List of instances in PENDING status, oldest first.
    """
    pending = await registry.list_pending_instances()
    return {
        "instances": [inst.model_dump(mode="json") for inst in pending],
        "total": len(pending),
    }


@router.post("/{instance_id}/approve")
async def approve_instance(
    instance_id: str,
    project_ids: Optional[List[str]] = None,
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Approve a pending compute instance, transitioning it to ONLINE.

    Args:
        instance_id: Compute instance to approve
        project_ids: Project IDs to assign. Defaults to ["*"] (all projects).

    Returns:
        The approved instance.
    """
    instance = await registry.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )

    try:
        approved = await registry.approve_instance(instance_id, project_ids)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    logger.info(f"Approved compute instance {instance_id}")
    return approved.model_dump(mode="json")


@router.post("/{instance_id}/reject")
async def reject_instance(
    instance_id: str,
    reason: str = "",
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Reject a pending compute instance and remove it from the registry.

    Args:
        instance_id: Compute instance to reject
        reason: Optional rejection reason

    Returns:
        Acknowledgment with rejection status.
    """
    instance = await registry.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )

    try:
        await registry.reject_instance(instance_id, reason)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    logger.info(f"Rejected compute instance {instance_id}: {reason}")
    return {"status": "rejected", "instance_id": instance_id, "reason": reason}


# =============================================================================
# Legacy Registration Endpoints (Deprecated - use SSE /connect instead)
# =============================================================================


@router.post("/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_instance(
    request: RegistrationRequest,
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Register a new compute instance.

    This endpoint allows compute instances to register before establishing an SSE connection.
    Instances are created in PENDING status with empty project_ids until explicitly approved.

    Args:
        request: Registration request
        registry: Compute registry (injected)

    Returns:
        Registration response with heartbeat details

    Raises:
        HTTPException: If instance_id already exists or validation fails
    """

    try:
        # Check if instance already exists (e.g., loaded from storage after restart)
        existing = await registry.get_instance(request.instance_id)

        if existing:
            # Instance already in registry — update capabilities, preserve approval state
            await registry.update_instance(
                request.instance_id,
                capabilities=request.capabilities,
                metadata=request.metadata,
            )
            await registry.update_heartbeat(request.instance_id)

            # Re-sync auth_status on reconnect (token may have been
            # added/refreshed while compute was disconnected)
            from services.claude_auth_service import get_claude_auth_service
            from models.compute import ComputeAuthStatus

            auth_svc = get_claude_auth_service()
            if auth_svc:
                token_info = auth_svc.get_token_info(request.instance_id)
                if token_info and token_info.get("status") == "active":
                    expires_at_str = token_info.get("expires_at")
                    expires_at = (
                        datetime.fromisoformat(expires_at_str)
                        if expires_at_str
                        else None
                    )
                    await registry.update_auth_status(
                        request.instance_id,
                        ComputeAuthStatus.AUTHORIZED,
                        auth_expires_at=expires_at,
                    )

            logger.info(
                f"Compute {request.instance_id} re-registered — "
                f"preserved {existing.status.value} status"
            )
            return RegistrationResponse(
                status=existing.status.value,
                instance_id=existing.instance_id,
                heartbeat_interval=existing.heartbeat_interval,
                heartbeat_endpoint=f"/api/v1/compute/{existing.instance_id}/health",
                message=(
                    f"Instance {existing.instance_id} reconnected — "
                    f"{existing.status.value} status preserved"
                ),
            )

        # New instance — create as PENDING with no projects
        instance = ComputeInstance(
            instance_id=request.instance_id,
            name=request.name,
            endpoint=request.endpoint,
            health_endpoint=request.health_endpoint,
            status=InstanceStatus.PENDING,
            pending_since=datetime.now(timezone.utc),
            capabilities=request.capabilities,
            metadata=request.metadata,
            version=request.version,
            heartbeat_interval=request.heartbeat_interval,
            lifecycle_mode=request.lifecycle_mode,
        )

        registered = await registry.add_instance(instance)

        # Sync auth_status from existing tokens (fixes startup ordering:
        # _sync_registry_auth_status runs before compute nodes register,
        # so newly registered nodes default to UNAUTHORIZED even when
        # active tokens exist in Redis)
        from services.claude_auth_service import get_claude_auth_service
        from models.compute import ComputeAuthStatus

        auth_svc = get_claude_auth_service()
        if auth_svc:
            token_info = auth_svc.get_token_info(request.instance_id)
            if token_info and token_info.get("status") == "active":
                expires_at_str = token_info.get("expires_at")
                expires_at = (
                    datetime.fromisoformat(expires_at_str)
                    if expires_at_str
                    else None
                )
                await registry.update_auth_status(
                    request.instance_id,
                    ComputeAuthStatus.AUTHORIZED,
                    auth_expires_at=expires_at,
                )
                logger.info(
                    f"Synced auth_status to AUTHORIZED for newly registered {request.instance_id}"
                )

        logger.info(
            f"Registered compute instance {request.instance_id} "
            f"with {len(request.capabilities.agents)} agents"
        )

        # Emit compute_registered event for instant UI update
        from services.observability_event_bus import get_event_bus
        from models.observability import ComputeRegisteredEvent
        import uuid

        event_bus = get_event_bus()
        if event_bus:
            event = ComputeRegisteredEvent(
                event_id=f"cr_{uuid.uuid4().hex[:12]}",
                compute_id=registered.instance_id,
                name=registered.name,
                capabilities=request.capabilities.agents,
                labels=request.capabilities.labels if request.capabilities.labels else [],
                tools_available=request.capabilities.tools_available if request.capabilities.tools_available else [],
                metadata={
                    "connection_type": "http",
                    "endpoint": registered.endpoint,
                }
            )
            await event_bus.emit_event(event)
            logger.debug(f"Emitted compute_registered event for {registered.instance_id}")

        return RegistrationResponse(
            status="pending",
            instance_id=registered.instance_id,
            heartbeat_interval=registered.heartbeat_interval,
            heartbeat_endpoint=f"/api/v1/compute/{registered.instance_id}/health",
            message=f"Instance {registered.instance_id} registered as PENDING — awaiting approval"
        )

    except ValueError as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error registering instance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during registration"
        )


@router.delete("/{instance_id}", status_code=status.HTTP_200_OK)
async def deregister_instance(
    instance_id: str,
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """Deregister a compute instance.

    Args:
        instance_id: Instance ID to deregister
        registry: Compute registry (injected)

    Returns:
        Success message

    Raises:
        HTTPException: If instance not found
    """
    # Disconnect SSE connection first to prevent work assignment to this instance
    sse_manager = get_sse_connection_manager()
    await sse_manager.unregister_connection(instance_id)

    # Revoke MCP API keys so deregistered compute cannot make further calls
    from mcp.auth import revoke_compute_key
    await revoke_compute_key(instance_id)

    removed = await registry.remove_instance(instance_id)

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found"
        )

    logger.info(f"Deregistered compute instance {instance_id}")

    # Emit compute_deregistered event for instant UI update
    from services.observability_event_bus import get_event_bus
    from models.observability import ComputeDeregisteredEvent
    import uuid

    event_bus = get_event_bus()
    if event_bus:
        event = ComputeDeregisteredEvent(
            event_id=f"cd_{uuid.uuid4().hex[:12]}",
            compute_id=instance_id,
            reason="manual_deregister",
            metadata={}
        )
        await event_bus.emit_event(event)
        logger.debug(f"Emitted compute_deregistered event for {instance_id}")

    return {
        "status": "deregistered",
        "instance_id": instance_id,
        "message": f"Successfully deregistered instance {instance_id}"
    }


@router.get("", response_model=InstanceListResponse)
async def list_instances(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of instances"),
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """List registered compute instances.

    Args:
        status: Optional status filter
        limit: Maximum number of instances
        registry: Compute registry (injected)

    Returns:
        List of instances with summary stats

    Raises:
        HTTPException: If status is invalid
    """
    # Validate status
    status_enum = None
    if status:
        try:
            status_enum = InstanceStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status}. Must be one of: {[s.value for s in InstanceStatus]}"
            )

    # Get instances
    instances = await registry.list_instances(status=status_enum, limit=limit)

    # Calculate stats
    total = len(instances)
    online = sum(1 for i in instances if i.status == InstanceStatus.ONLINE)
    offline = sum(1 for i in instances if i.status == InstanceStatus.OFFLINE)
    authorized = sum(1 for i in instances if i.auth_status == ComputeAuthStatus.AUTHORIZED)
    unauthorized = sum(1 for i in instances if i.auth_status == ComputeAuthStatus.UNAUTHORIZED)

    return InstanceListResponse(
        instances=instances,
        total=total,
        online=online,
        offline=offline,
        authorized=authorized,
        unauthorized=unauthorized
    )


@router.get("/{instance_id}", response_model=ComputeInstance)
async def get_instance(
    instance_id: str,
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """Get details for a specific compute instance.

    Args:
        instance_id: Instance ID
        registry: Compute registry (injected)

    Returns:
        Instance details

    Raises:
        HTTPException: If instance not found
    """
    instance = await registry.get_instance(instance_id)

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found"
        )

    return instance


@router.patch("/{instance_id}", response_model=ComputeInstance)
async def update_instance(
    instance_id: str,
    request: UpdateInstanceRequest,
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """Update instance metadata.

    Args:
        instance_id: Instance ID
        request: Update request
        registry: Compute registry (injected)

    Returns:
        Updated instance

    Raises:
        HTTPException: If instance not found
    """
    instance = await registry.update_instance(
        instance_id=instance_id,
        name=request.name,
        capabilities=request.capabilities,
        metadata=request.metadata
    )

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found"
        )

    logger.info(f"Updated compute instance {instance_id}")

    return instance


@router.post("/{instance_id}/health", status_code=status.HTTP_200_OK, deprecated=True)
async def heartbeat(
    instance_id: str,
    request: Optional[HeartbeatRequest] = None,
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """Receive heartbeat from compute instance.

    DEPRECATED: Use GET /connect with SSE instead. SSE connection serves as health signal.

    This endpoint is called by compute instances to indicate they are alive.

    Args:
        instance_id: Instance ID
        request: Optional heartbeat metadata
        registry: Compute registry (injected)

    Returns:
        Acknowledgment

    Raises:
        HTTPException: If instance not found
    """
    metadata = request.metadata if request else None

    updated = await registry.update_heartbeat(
        instance_id=instance_id,
        metadata=metadata
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found. Please register first."
        )

    logger.debug(f"Received heartbeat from {instance_id}")

    return {
        "status": "acknowledged",
        "instance_id": instance_id,
        "message": "Heartbeat received"
    }


@router.get("/capabilities/aggregated", response_model=AggregatedCapabilities)
async def get_aggregated_capabilities(
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """Get aggregated capabilities across all compute instances.

    Args:
        registry: Compute registry (injected)

    Returns:
        Aggregated capabilities
    """
    return await registry.get_aggregated_capabilities()


@router.get("/search/by-agent/{agent_id}", response_model=list[ComputeInstance])
async def find_instances_by_agent(
    agent_id: str,
    online_only: bool = Query(True, description="Only return online instances"),
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """Find compute instances that have a specific agent.

    Args:
        agent_id: Agent ID to search for
        online_only: Only return online instances
        registry: Compute registry (injected)

    Returns:
        List of instances with the agent
    """
    instances = await registry.get_by_capability(
        agent_id=agent_id,
        online_only=online_only
    )

    return instances


@router.get("/search/by-tool/{tool_id}", response_model=list[ComputeInstance])
async def find_instances_by_tool(
    tool_id: str,
    online_only: bool = Query(True, description="Only return online instances"),
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """Find compute instances that have a specific tool.

    Args:
        tool_id: Tool ID to search for
        online_only: Only return online instances
        registry: Compute registry (injected)

    Returns:
        List of instances with the tool
    """
    instances = await registry.get_by_capability(
        tool_id=tool_id,
        online_only=online_only
    )

    return instances


@router.get("/search/by-label/{label}", response_model=list[ComputeInstance])
async def find_instances_by_label(
    label: str,
    online_only: bool = Query(True, description="Only return online instances"),
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """Find compute instances that have a specific routing label.

    Labels are used for routing specialized work to appropriate compute instances.
    Common labels include: production-access, database-admin, security-tools, gpu, standard.

    Args:
        label: Label to search for (e.g., "production-access")
        online_only: Only return online instances
        registry: Compute registry (injected)

    Returns:
        List of instances with the label
    """
    instances = await registry.get_by_label(
        label=label,
        online_only=online_only
    )

    return instances


@router.get("/search/by-tool-available/{tool}", response_model=list[ComputeInstance])
async def find_instances_by_tool_available(
    tool: str,
    online_only: bool = Query(True, description="Only return online instances"),
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """Find compute instances that have a specific specialized tool available.

    Tools_available indicates specialized tools the compute can run
    (e.g., deploy_prod, db_migrate, security_scan).

    Args:
        tool: Tool to search for (e.g., "deploy_prod")
        online_only: Only return online instances
        registry: Compute registry (injected)

    Returns:
        List of instances with the tool available
    """
    instances = await registry.get_by_tool_available(
        tool=tool,
        online_only=online_only
    )

    return instances


@router.get("/stats/summary")
async def get_registry_stats(
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """Get registry statistics.

    Args:
        registry: Compute registry (injected)

    Returns:
        Registry statistics
    """
    return registry.get_stats()
