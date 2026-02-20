"""SSE connection manager for Compute Infra instances.

Manages Server-Sent Events connections from Compute Infra instances.
This enables real-time push notifications from Serving to Compute.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional, TYPE_CHECKING
from collections.abc import Callable, Awaitable

if TYPE_CHECKING:
    from services.registry_service import ComputeRegistry

logger = logging.getLogger(__name__)


@dataclass
class SSEConnection:
    """Represents an active SSE connection from a Compute Infra instance."""
    compute_id: str
    capabilities: list[str]
    resources: dict[str, Any]
    labels: list[str] = field(default_factory=list)
    tools_available: list[str] = field(default_factory=list)
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    current_task_id: Optional[str] = None
    status: str = "idle"  # idle, busy, draining
    last_work_assigned_data: Optional[dict[str, Any]] = None
    _queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue())

    async def send_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Queue an event to be sent to this connection."""
        await self._queue.put({
            "event": event_type,
            "data": data
        })

    async def get_event(self) -> dict[str, Any]:
        """Get the next event to send (blocks until available)."""
        return await self._queue.get()


class SSEConnectionManager:
    """Manages SSE connections from Compute Infra instances.

    Provides methods to:
    - Register/unregister connections
    - Send events to specific compute instances
    - Broadcast events to all connected instances
    - Query connection status
    """

    def __init__(
        self,
        keepalive_interval: int = 30,
        registry: Optional["ComputeRegistry"] = None
    ):
        """Initialize the connection manager.

        Args:
            keepalive_interval: Seconds between keepalive pulses
            registry: Optional ComputeRegistry for auth status filtering
        """
        self._connections: dict[str, SSEConnection] = {}
        self._keepalive_interval = keepalive_interval
        self._keepalive_task: Optional[asyncio.Task] = None
        self._on_connect_handlers: list[Callable[[str], Awaitable[None]]] = []
        self._on_disconnect_handlers: list[Callable[[str], Awaitable[None]]] = []
        self._round_robin_indices: dict[str, int] = {}
        self._registry = registry

        logger.info("SSEConnectionManager initialized")

    async def start(self) -> None:
        """Start the connection manager (keepalive task)."""
        if self._keepalive_task is None:
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            logger.info(f"SSE keepalive started (interval: {self._keepalive_interval}s)")

    async def stop(self) -> None:
        """Stop the connection manager."""
        if self._keepalive_task:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
            self._keepalive_task = None
            logger.info("SSE keepalive stopped")

    def on_connect(self, handler: Callable[[str], Awaitable[None]]) -> None:
        """Register a handler to be called when a compute connects."""
        self._on_connect_handlers.append(handler)

    def on_disconnect(self, handler: Callable[[str], Awaitable[None]]) -> None:
        """Register a handler to be called when a compute disconnects."""
        self._on_disconnect_handlers.append(handler)

    async def register_connection(
        self,
        compute_id: str,
        capabilities: list[str],
        resources: dict[str, Any],
        labels: Optional[list[str]] = None,
        tools_available: Optional[list[str]] = None
    ) -> SSEConnection:
        """Register a new SSE connection.

        Args:
            compute_id: Unique identifier for the compute instance
            capabilities: List of capabilities (e.g., ["coding", "testing"])
            resources: Resource specifications (e.g., {"cpu": 4, "memory": "16gb"})
            labels: Routing labels for work assignment (e.g., ["production-access", "database-admin"])
            tools_available: Specialized tools available (e.g., ["deploy_prod", "db_migrate"])

        Returns:
            The created SSE connection
        """
        # Remove existing connection if any
        if compute_id in self._connections:
            logger.warning(f"Replacing existing connection for {compute_id}")
            await self.unregister_connection(compute_id)

        connection = SSEConnection(
            compute_id=compute_id,
            capabilities=capabilities,
            resources=resources,
            labels=labels or [],
            tools_available=tools_available or []
        )
        self._connections[compute_id] = connection

        logger.info(f"SSE connection registered: {compute_id} (capabilities: {capabilities}, labels: {labels or []})")

        # Call connect handlers
        for handler in self._on_connect_handlers:
            try:
                await handler(compute_id)
            except Exception as e:
                logger.error(f"Error in connect handler: {e}")

        return connection

    async def unregister_connection(self, compute_id: str) -> bool:
        """Unregister an SSE connection.

        Args:
            compute_id: ID of the compute instance to unregister

        Returns:
            True if connection was found and removed
        """
        connection = self._connections.pop(compute_id, None)
        if connection:
            logger.info(f"SSE connection unregistered: {compute_id}")

            # Call disconnect handlers
            for handler in self._on_disconnect_handlers:
                try:
                    await handler(compute_id)
                except Exception as e:
                    logger.error(f"Error in disconnect handler: {e}")

            return True
        return False

    def get_connection(self, compute_id: str) -> Optional[SSEConnection]:
        """Get a specific connection by compute ID."""
        return self._connections.get(compute_id)

    def list_connections(self) -> list[SSEConnection]:
        """List all active connections."""
        return list(self._connections.values())

    def get_idle_connections(self) -> list[SSEConnection]:
        """Get all idle (available for work) connections."""
        return [c for c in self._connections.values() if c.status == "idle"]

    def get_connections_by_label(self, label: str) -> list[SSEConnection]:
        """Get all connections with a specific routing label.

        Args:
            label: The label to filter by

        Returns:
            List of connections with the specified label
        """
        return [c for c in self._connections.values() if label in c.labels]

    def get_connections_by_tool(self, tool: str) -> list[SSEConnection]:
        """Get all connections with a specific available tool.

        Args:
            tool: The tool to filter by

        Returns:
            List of connections with the specified tool available
        """
        return [c for c in self._connections.values() if tool in c.tools_available]

    def find_matching_connection(
        self,
        required_labels: Optional[list[str]] = None,
        required_tools: Optional[list[str]] = None,
        required_capabilities: Optional[list[str]] = None,
        idle_only: bool = True,
        specialization_scores: Optional[dict[str, float]] = None,
        phase: Optional[str] = None,
        exclude_compute_ids: Optional[set] = None,
    ) -> Optional[SSEConnection]:
        """Find a connection that matches all requirements.

        This is the main routing method that matches work requirements to
        connected compute instances based on labels, tools_available, and capabilities.
        When specialization_scores are provided, candidates are sorted by score
        (highest first) instead of returning the first match.

        Args:
            required_labels: Labels the compute must have
            required_tools: Specialized tools the compute must have available
            required_capabilities: Capability tags the compute must have
            idle_only: Only return idle connections
            specialization_scores: Optional dict of compute_id -> specialization
                score (0.0-1.0). When provided, the best-scoring candidate is
                returned instead of the first match.
            phase: Pipeline phase for round-robin counter isolation.
                Each phase maintains its own rotation index so that
                decomposition, characterization, and work execution
                distribute independently. When None, uses a default counter.
            exclude_compute_ids: Compute IDs to deprioritize (e.g., nodes that
                previously failed for a work item). These nodes are only used
                as a last resort when no other candidates are available.

        Returns:
            A matching SSEConnection or None if no match found
        """
        candidates = list(self._connections.values())

        # Filter by idle status
        if idle_only:
            candidates = [c for c in candidates if c.status == "idle"]

        # Filter by required labels
        if required_labels:
            candidates = [
                c for c in candidates
                if all(label in c.labels for label in required_labels)
            ]

        # Filter by required tools
        if required_tools:
            candidates = [
                c for c in candidates
                if all(tool in c.tools_available for tool in required_tools)
            ]

        # Filter by required capabilities
        if required_capabilities:
            candidates = [
                c for c in candidates
                if all(cap in c.capabilities for cap in required_capabilities)
            ]

        if not candidates:
            return None

        # Filter by auth status if registry is available
        if self._registry:
            from models.compute import ComputeAuthStatus
            authorized_candidates = []
            for conn in candidates:
                # Cross-reference with registry to check auth status
                instance = self._registry._instances.get(conn.compute_id)
                if instance and instance.auth_status == ComputeAuthStatus.AUTHORIZED:
                    authorized_candidates.append(conn)
            candidates = authorized_candidates

            if not candidates:
                logger.warning(
                    "No authorized compute instances available for work assignment. "
                    "All candidates were filtered due to auth_status != AUTHORIZED"
                )
                return None

        # Deprioritize excluded nodes (previously failed), but use them as last resort
        if exclude_compute_ids:
            preferred = [c for c in candidates if c.compute_id not in exclude_compute_ids]
            if preferred:
                candidates = preferred

        # Sort by specialization score if provided
        if specialization_scores:
            candidates.sort(
                key=lambda c: specialization_scores.get(c.compute_id, 0.0),
                reverse=True,
            )
            return candidates[0]

        # Round-robin selection with phase-specific counter
        key = phase or "_default"
        index = self._round_robin_indices.get(key, 0) % len(candidates)
        self._round_robin_indices[key] = self._round_robin_indices.get(key, 0) + 1
        return candidates[index]

    async def send_event(
        self,
        compute_id: str,
        event_type: str,
        data: dict[str, Any]
    ) -> bool:
        """Send an event to a specific compute instance.

        Args:
            compute_id: Target compute instance
            event_type: Event type (e.g., "work_assigned", "merge_conflict")
            data: Event payload

        Returns:
            True if event was queued successfully
        """
        connection = self._connections.get(compute_id)
        if not connection:
            logger.warning(f"Cannot send event: compute {compute_id} not connected")
            return False

        await connection.send_event(event_type, data)
        logger.debug(f"Event {event_type} queued for {compute_id}")
        return True

    async def broadcast_event(
        self,
        event_type: str,
        data: dict[str, Any],
        filter_fn: Optional[Callable[[SSEConnection], bool]] = None
    ) -> int:
        """Broadcast an event to all (or filtered) connections.

        Args:
            event_type: Event type
            data: Event payload
            filter_fn: Optional filter function to select recipients

        Returns:
            Number of connections that received the event
        """
        count = 0
        for connection in self._connections.values():
            if filter_fn is None or filter_fn(connection):
                await connection.send_event(event_type, data)
                count += 1

        logger.debug(f"Broadcast {event_type} to {count} connections")
        return count

    async def send_merge_conflict(
        self,
        compute_id: str,
        issue_id: str,
        branch: str,
        conflicting_files: list[str],
        main_head: str,
        message: str = "Resolve conflicts with main and push again",
        task_id: Optional[str] = None,
        repository: Optional[str] = None,
    ) -> bool:
        """Send a merge_conflict event to a compute instance.

        Args:
            compute_id: Target compute instance
            issue_id: Issue ID associated with the branch
            branch: Branch name with conflicts
            conflicting_files: List of files with conflicts
            main_head: Current HEAD of main branch
            message: Human-readable message
            task_id: Task ID for the conflicting branch (read by conflict_handler)
            repository: Repo URL so spawner can use it without scanning instances

        Returns:
            True if event was queued successfully
        """
        data = {
            "issue_id": issue_id,
            "task_id": task_id,
            "repository": repository,
            "branch": branch,
            "conflicting_files": conflicting_files,
            "main_head": main_head,
            "message": message
        }
        return await self.send_event(compute_id, "merge_conflict", data)

    async def send_work_assigned(
        self,
        compute_id: str,
        task_id: str,
        title: str,
        description: str,
        branch_name: str,
        skills: dict[str, Any],
        context: dict[str, Any],
        mcp_config: dict[str, Any]
    ) -> bool:
        """Send a work_assigned event to a compute instance.

        Args:
            compute_id: Target compute instance
            task_id: Task identifier
            title: Task title
            description: Task description
            branch_name: Branch to work on
            skills: Skill configuration
            context: Work context
            mcp_config: MCP configuration

        Returns:
            True if event was queued successfully
        """
        # Update connection status
        connection = self._connections.get(compute_id)
        if connection:
            connection.status = "busy"
            connection.current_task_id = task_id

        data = {
            "task_id": task_id,
            "title": title,
            "description": description,
            "branch_name": branch_name,
            "skills": skills,
            "context": context,
            "mcp_config": mcp_config
        }

        # Store work data for potential re-dispatch on rejection
        if connection:
            connection.last_work_assigned_data = data

        return await self.send_event(compute_id, "work_assigned", data)

    async def send_work_cancelled(
        self,
        compute_id: str,
        task_id: str,
        reason: str,
        action: str = "stop_gracefully"
    ) -> bool:
        """Send a work_cancelled event to a compute instance."""
        data = {
            "task_id": task_id,
            "reason": reason,
            "action": action
        }
        return await self.send_event(compute_id, "work_cancelled", data)

    async def send_work_completed(
        self,
        compute_id: str,
        issue_id: str,
        branch: str,
        merge_commit: str
    ) -> bool:
        """Send a work_completed event to a compute instance."""
        # Update connection status
        connection = self._connections.get(compute_id)
        if connection:
            connection.status = "idle"
            connection.current_task_id = None

        data = {
            "issue_id": issue_id,
            "branch": branch,
            "merge_commit": merge_commit,
            "merged_at": datetime.now(timezone.utc).isoformat()
        }
        return await self.send_event(compute_id, "work_completed", data)

    async def send_shutdown(
        self,
        compute_id: str,
        reason: str,
        grace_period_seconds: int = 60
    ) -> bool:
        """Send a shutdown event to a compute instance."""
        data = {
            "reason": reason,
            "grace_period_seconds": grace_period_seconds
        }
        return await self.send_event(compute_id, "shutdown", data)

    async def _keepalive_loop(self) -> None:
        """Send periodic keepalive events to all connections."""
        while True:
            try:
                await asyncio.sleep(self._keepalive_interval)
                timestamp = datetime.now(timezone.utc).isoformat()
                await self.broadcast_event("keepalive", {"timestamp": timestamp})
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in keepalive loop: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Get connection statistics."""
        connections = list(self._connections.values())
        return {
            "total_connections": len(connections),
            "idle": sum(1 for c in connections if c.status == "idle"),
            "busy": sum(1 for c in connections if c.status == "busy"),
            "draining": sum(1 for c in connections if c.status == "draining")
        }


# Global instance
_sse_manager: Optional[SSEConnectionManager] = None


def get_sse_connection_manager() -> SSEConnectionManager:
    """Get the global SSE connection manager."""
    global _sse_manager
    if _sse_manager is None:
        # Import here to avoid circular dependency
        from services.registry_service import get_compute_registry
        registry = get_compute_registry()
        _sse_manager = SSEConnectionManager(registry=registry)
    return _sse_manager


def set_sse_connection_manager(manager: SSEConnectionManager) -> None:
    """Set the global SSE connection manager."""
    global _sse_manager
    _sse_manager = manager


async def event_generator(connection: SSEConnection) -> AsyncGenerator[str, None]:
    """Generate SSE events for a connection.

    This is used by the SSE endpoint to stream events to the client.

    Args:
        connection: The SSE connection to generate events for

    Yields:
        SSE-formatted event strings
    """
    try:
        while True:
            event = await connection.get_event()
            event_type = event["event"]
            data = json.dumps(event["data"])
            yield f"event: {event_type}\ndata: {data}\n\n"
    except asyncio.CancelledError:
        logger.debug(f"Event generator cancelled for {connection.compute_id}")
        raise
