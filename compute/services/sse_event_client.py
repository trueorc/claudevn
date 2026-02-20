"""SSE event client for receiving events from Serving.

Connects to Serving's SSE endpoint and handles incoming events
including work_assigned, work_cancelled, merge_conflict, etc.
Spawns Claude Code instances in response to work_assigned events.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class MergeConflictEvent:
    """Parsed merge_conflict event data."""
    issue_id: str
    branch: str
    conflicting_files: list[str]
    main_head: str
    message: str


@dataclass
class WorkAssignedEvent:
    """Parsed work_assigned event data."""
    task_id: str
    title: str
    description: str
    branch_name: str
    skills: dict[str, Any]
    context: dict[str, Any]
    mcp_config: dict[str, Any]


@dataclass
class WorkCancelledEvent:
    """Parsed work_cancelled event data."""
    task_id: str
    reason: str
    action: str


@dataclass
class WorkCompletedEvent:
    """Parsed work_completed event data."""
    issue_id: str
    branch: str
    merge_commit: str
    merged_at: str


@dataclass
class ShutdownEvent:
    """Parsed shutdown event data."""
    reason: str
    grace_period_seconds: int


EventHandler = Callable[[str, dict[str, Any]], Awaitable[None]]
ShutdownCallback = Callable[[int], Awaitable[None]]


class SSEEventClient:
    """Client for receiving SSE events from Serving.

    Connects to Serving's /api/v1/compute/connect endpoint and
    handles incoming events by dispatching to registered handlers.
    """

    def __init__(
        self,
        serving_url: str,
        compute_id: str,
        api_key: str,
        capabilities: list[str],
        resources: dict[str, Any],
        reconnect_delay: int = 5,
        max_reconnect_delay: int = 60
    ):
        """Initialize the SSE event client.

        Args:
            serving_url: Base URL of the Serving component
            compute_id: This compute instance's ID
            api_key: API key for authentication
            capabilities: List of capabilities to advertise
            resources: Resource specifications
            reconnect_delay: Initial delay between reconnection attempts
            max_reconnect_delay: Maximum delay between reconnection attempts
        """
        self.serving_url = serving_url.rstrip('/')
        self.compute_id = compute_id
        self.api_key = api_key
        self.capabilities = capabilities
        self.resources = resources
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay

        self._handlers: dict[str, list[EventHandler]] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._connected = False
        self._last_event_time: Optional[datetime] = None

        # Shutdown handling
        self._shutdown_requested = False
        self._shutdown_callback: Optional[ShutdownCallback] = None
        self._shutdown_task: Optional[asyncio.Task] = None

        # Git token received from Serving (for HTTP auth)
        self._git_token: Optional[str] = None

        # Register built-in handlers
        self._register_builtin_handlers()

    def _register_builtin_handlers(self) -> None:
        """Register built-in event handlers for work_assigned, work_cancelled, work_completed, merge_conflict, git_token_provisioned, credentials_refresh, and auth_token."""
        self.on("git_token_provisioned", self._handle_git_token_provisioned)
        self.on("work_assigned", self._handle_work_assigned)
        self.on("work_cancelled", self._handle_work_cancelled)
        self.on("work_completed", self._handle_work_completed)
        self.on("merge_conflict", self._handle_merge_conflict)
        self.on("credentials_refresh", self._handle_credentials_refresh)
        self.on("auth_token", self._handle_auth_token)

    async def _handle_git_token_provisioned(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle git_token_provisioned event by storing the token.

        Args:
            event_type: Event type (git_token_provisioned)
            data: Event data containing token
        """
        token = data.get("token")
        if not token:
            logger.error("Received git_token_provisioned without token")
            return

        self._git_token = token
        logger.info(f"Git token stored for {self.compute_id}")

    async def _handle_work_assigned(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle work_assigned event by spawning Claude Code.

        Args:
            event_type: Event type (work_assigned)
            data: Event data
        """
        from .claude_code_spawner import get_claude_code_spawner

        logger.info(f"Received work_assigned: task_id={data.get('task_id')}")

        # Inject Git token into context if available
        if self._git_token:
            context = data.get("context", {})
            context["git_token"] = self._git_token
            data = {**data, "context": context}

        spawner = get_claude_code_spawner()
        if not spawner:
            logger.error("No Claude Code spawner available")
            return

        try:
            success = await spawner.spawn(data)
            if success:
                logger.info(f"Successfully spawned Claude Code for task {data.get('task_id')}")
            else:
                logger.warning(f"Failed to spawn Claude Code for task {data.get('task_id')}")
        except Exception as e:
            logger.error(f"Error spawning Claude Code: {e}")

    async def _handle_work_cancelled(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle work_cancelled event by stopping Claude Code.

        Args:
            event_type: Event type (work_cancelled)
            data: Event data
        """
        from .claude_code_spawner import get_claude_code_spawner

        task_id = data.get("task_id")
        reason = data.get("reason", "No reason provided")

        logger.info(f"Received work_cancelled: task_id={task_id}, reason={reason}")

        spawner = get_claude_code_spawner()
        if not spawner:
            logger.error("No Claude Code spawner available")
            return

        try:
            success = await spawner.stop(task_id, force=False, timeout=30)
            if success:
                logger.info(f"Successfully stopped Claude Code for task {task_id}")
            else:
                logger.warning(f"Failed to stop Claude Code for task {task_id}")
        except Exception as e:
            logger.error(f"Error stopping Claude Code: {e}")

    async def _handle_work_completed(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle work_completed event from Serving.

        This event is sent when Serving has successfully merged the work
        branch to main. The handler:
        1. Deletes the local git branch explicitly by name (as specified in
           the signal — compute does not infer which branch to clean up).
        2. Cleans up the workspace directory if the instance is still tracked.

        The persistent serving repo at ~/.claudevn/repos/serving/ is never
        touched — only the merged feature branch in the instance workspace.

        Args:
            event_type: Event type (work_completed)
            data: Event data containing issue_id, branch, merge_commit, merged_at
        """
        from .claude_code_spawner import get_claude_code_spawner

        issue_id = data.get("issue_id")
        branch = data.get("branch")
        merge_commit = data.get("merge_commit")
        merged_at = data.get("merged_at")

        logger.info(
            f"Received work_completed: issue_id={issue_id}, branch={branch}, "
            f"merge_commit={merge_commit}, merged_at={merged_at}"
        )

        if not branch:
            logger.warning("work_completed event missing branch name — skipping cleanup")
            return

        spawner = get_claude_code_spawner()
        if not spawner:
            logger.warning("No Claude Code spawner available to clean up workspace")
            return

        # Explicitly delete the local branch by name as signalled by Serving.
        # delete_local_branch() handles the "branch not found" case gracefully.
        spawner.delete_local_branch(branch)

        # Find the task associated with this branch to clean up the workspace
        task_id = None
        for tid, instance in spawner._instances.items():
            if instance.get("branch_name") == branch:
                task_id = tid
                break

        if task_id:
            # Instance still tracked - it may have completed but cleanup pending
            logger.info(
                f"Work completed for task {task_id}: branch={branch} "
                f"merged as {merge_commit}"
            )
            # Clean up the workspace since work is merged
            spawner._cleanup_instance(task_id, cleanup_workspace=True)
            logger.info(f"Cleaned up workspace for task {task_id}")
        else:
            # No active instance for this branch - already cleaned up or never existed
            logger.info(
                f"Work completed for branch {branch} (no active instance found), "
                f"merged as {merge_commit}"
            )

    async def _handle_merge_conflict(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle merge_conflict event by delegating to ConflictResolutionHandler.

        When Serving detects a merge conflict on a branch, it sends this event.
        The handler initializes (or retrieves) the conflict resolution handler
        and delegates the resolution process. If no running Claude Code instance
        exists for the task, a new one is spawned with conflict-resolution
        instructions.

        Args:
            event_type: Event type (merge_conflict)
            data: Event data containing issue_id, branch, conflicting_files, main_head, message
        """
        from .conflict_handler import get_conflict_handler, initialize_conflict_handler
        from .claude_code_spawner import get_claude_code_spawner

        branch = data.get("branch", "unknown")
        conflicting_files = data.get("conflicting_files", [])

        logger.warning(
            f"Received merge_conflict: branch={branch}, "
            f"files={conflicting_files}"
        )

        # Get or initialize the conflict resolution handler.
        # Use the per-branch working_dir so git commands run in the right checkout,
        # not in the spawner's base workspace directory.
        handler = get_conflict_handler()
        if not handler:
            spawner = get_claude_code_spawner()
            workspace = "/workspace"  # fallback
            if spawner:
                for inst_data in spawner._instances.values():
                    if inst_data.get("branch_name") == branch:
                        workspace = inst_data.get("working_dir", str(spawner.workspace_path))
                        break
                else:
                    workspace = str(spawner.workspace_path)
            handler = initialize_conflict_handler(workspace_path=workspace)

        # Find the task_id for this branch from active spawner instances
        if "task_id" not in data:
            spawner = get_claude_code_spawner()
            if spawner:
                for tid, instance in spawner._instances.items():
                    if instance.get("branch_name") == branch:
                        data = {**data, "task_id": tid}
                        break

        try:
            result = await handler.handle_merge_conflict(event_type, data)
            if result.success:
                logger.info(
                    f"Merge conflict handling initiated for {branch} "
                    f"via {result.method}"
                )
            else:
                logger.warning(
                    f"Merge conflict handling failed for {branch}: "
                    f"{result.message}. Attempting to spawn conflict resolver."
                )
                # Fallback: spawn a new Claude Code instance for conflict resolution
                await self._spawn_conflict_resolver(data)
        except Exception as e:
            logger.error(f"Error handling merge_conflict for {branch}: {e}")

    async def _spawn_conflict_resolver(self, data: dict[str, Any]) -> None:
        """Spawn a new Claude Code instance to resolve merge conflicts.

        This is used as a last resort when no running instance can be
        injected with conflict resolution instructions.

        Args:
            data: merge_conflict event data
        """
        from .claude_code_spawner import get_claude_code_spawner

        spawner = get_claude_code_spawner()
        if not spawner:
            logger.error("No Claude Code spawner available for conflict resolution")
            return

        try:
            success = await spawner.spawn_conflict_resolution(data)
            if success:
                logger.info(
                    f"Spawned conflict resolver for branch {data.get('branch')}"
                )
            else:
                logger.error(
                    f"Failed to spawn conflict resolver for branch {data.get('branch')}"
                )
        except Exception as e:
            logger.error(f"Error spawning conflict resolver: {e}")

    async def _handle_credentials_refresh(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle credentials_refresh event from Serving.

        Fetches updated credentials from Serving (if auth_mode=serving)
        or reloads from disk (local/external).

        Args:
            event_type: Event type (credentials_refresh)
            data: Event data
        """
        import os
        from .credential_monitor import get_credential_monitor

        logger.info("Received credentials_refresh event")

        monitor = get_credential_monitor()
        if not monitor:
            logger.warning("No credential monitor available")
            return

        auth_mode = os.getenv("COMPUTE_AUTH_MODE", "serving")
        if auth_mode == "serving":
            serving_auth_url = os.getenv(
                "CLAUDEVN_SERVING_AUTH_URL",
                "http://serving:8002/api/v1/auth"
            )
            status = await monitor.fetch_from_serving(serving_auth_url)
            logger.info(f"Credentials refreshed from serving: {status.value}")
        else:
            status = await monitor.reload_credentials()
            logger.info(f"Credentials reloaded from disk: {status.value}")

    async def _handle_auth_token(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle auth_token event from Serving.

        Applies the received OAuth token so Claude Code instances can authenticate.
        Sets the CLAUDE_CODE_OAUTH_TOKEN environment variable and writes the
        onboarding flag to ~/.claude.json so Claude CLI skips first-run setup.

        Args:
            event_type: Event type (auth_token)
            data: Event data containing token, component_id, expires_at, authorized_at
        """
        import os
        from .credential_monitor import get_credential_monitor

        token = data.get("token")
        component_id = data.get("component_id")
        expires_at = data.get("expires_at")

        if not token:
            logger.error("Received auth_token event without token")
            return

        # Mask token in logs (show only last 8 chars)
        masked = f"...{token[-8:]}" if len(token) > 8 else "***"
        logger.info(f"Received auth_token for {component_id}: {masked}")

        # Set environment variable for Claude Code subprocess spawning
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = token

        # Write ~/.claude.json with onboarding flag so Claude CLI skips first-run wizard
        try:
            claude_dir = Path(os.path.expanduser("~/.claude"))
            claude_dir.mkdir(parents=True, exist_ok=True)
            claude_json_path = claude_dir / ".claude.json"

            # Merge with existing config if present
            existing = {}
            if claude_json_path.exists():
                try:
                    existing = json.loads(claude_json_path.read_text())
                except (json.JSONDecodeError, OSError):
                    pass

            existing["hasCompletedOnboarding"] = True
            claude_json_path.write_text(json.dumps(existing, indent=2))
            logger.info("Wrote onboarding flag to ~/.claude/.claude.json")
        except Exception as e:
            logger.error(f"Failed to write onboarding flag: {e}")

        # Update credential monitor with token info
        monitor = get_credential_monitor()
        if monitor:
            monitor.apply_token(token, expires_at=expires_at)
            logger.info(f"Applied token to credential monitor (status={monitor.status.value})")
        else:
            logger.warning("No credential monitor available to apply token")

    def on(self, event_type: str, handler: EventHandler) -> None:
        """Register an event handler.

        Args:
            event_type: Event type to handle (e.g., "merge_conflict")
            handler: Async function to call when event is received
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"Registered handler for event type: {event_type}")

    def off(self, event_type: str, handler: Optional[EventHandler] = None) -> None:
        """Unregister an event handler.

        Args:
            event_type: Event type
            handler: Specific handler to remove, or None to remove all
        """
        if event_type in self._handlers:
            if handler is None:
                del self._handlers[event_type]
            else:
                self._handlers[event_type] = [
                    h for h in self._handlers[event_type] if h != handler
                ]

    async def _register(self) -> bool:
        """Register with Serving before establishing SSE connection.

        This allows the compute instance to appear in the UI immediately,
        before the SSE connection and health checks complete.

        Returns:
            True if registration succeeded, False otherwise
        """
        url = f"{self.serving_url}/api/v1/compute/register"

        # Build registration payload (manual construction to avoid import issues)
        payload = {
            "instance_id": self.compute_id,
            "name": f"Compute {self.compute_id}",
            "endpoint": "sse",
            "capabilities": {
                "agents": self.capabilities,
                "tools": [],
                "features": [],
                "labels": [],
                "tools_available": [],
            },
            "metadata": {
                "connection_type": "sse",
                "pre_registered": True,
            },
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code == 201:
                    logger.info(f"Successfully registered {self.compute_id} with Serving")
                    return True
                elif response.status_code == 400:
                    # Already registered - that's okay
                    logger.info(f"Compute {self.compute_id} already registered")
                    return True
                else:
                    logger.warning(f"Registration failed with status {response.status_code}: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Failed to register with Serving: {e}")
            return False

    async def start(self) -> None:
        """Start the SSE client."""
        if self._running:
            logger.warning("SSE client already running")
            return

        # Register before establishing SSE connection for instant UI visibility
        await self._register()

        self._running = True
        self._task = asyncio.create_task(self._connection_loop())
        logger.info(f"SSE client started for compute {self.compute_id}")

    async def stop(self) -> None:
        """Stop the SSE client."""
        self._running = False
        if self._shutdown_task:
            self._shutdown_task.cancel()
            try:
                await self._shutdown_task
            except asyncio.CancelledError:
                pass
            self._shutdown_task = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._connected = False
        logger.info(f"SSE client stopped for compute {self.compute_id}")

    def set_shutdown_callback(self, callback: ShutdownCallback) -> None:
        """Set the callback to invoke when graceful shutdown is requested.

        Args:
            callback: Async function that takes grace_period_seconds as argument
        """
        self._shutdown_callback = callback

    @property
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_requested

    async def _handle_shutdown_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle shutdown event from Serving.

        Args:
            event_type: Event type (shutdown)
            data: Event data containing reason and grace_period_seconds
        """
        reason = data.get("reason", "Unknown reason")
        grace_period = data.get("grace_period_seconds", 60)

        logger.warning(f"Received shutdown request: {reason} (grace_period={grace_period}s)")

        if self._shutdown_requested:
            logger.warning("Shutdown already requested, ignoring duplicate")
            return

        self._shutdown_requested = True

        # Execute the shutdown callback if registered
        if self._shutdown_callback:
            self._shutdown_task = asyncio.create_task(
                self._execute_graceful_shutdown(grace_period)
            )
        else:
            logger.warning("No shutdown callback registered, will shutdown immediately")
            self._shutdown_task = asyncio.create_task(self._delayed_stop(grace_period))

    async def _execute_graceful_shutdown(self, grace_period_seconds: int) -> None:
        """Execute graceful shutdown with callback.

        Args:
            grace_period_seconds: Time to wait for graceful shutdown
        """
        try:
            logger.info(f"Starting graceful shutdown with {grace_period_seconds}s grace period")
            await self._shutdown_callback(grace_period_seconds)
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")
        finally:
            # After callback completes, stop the SSE client
            await self.stop()

    async def _delayed_stop(self, delay_seconds: int) -> None:
        """Stop after a delay.

        Args:
            delay_seconds: Seconds to wait before stopping
        """
        try:
            logger.info(f"Will stop SSE client in {delay_seconds}s")
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            logger.info("Delayed stop was cancelled")
            return
        await self.stop()

    @property
    def is_connected(self) -> bool:
        """Check if currently connected to Serving."""
        return self._connected

    async def _connection_loop(self) -> None:
        """Main connection loop with automatic reconnection."""
        delay = self.reconnect_delay

        while self._running:
            try:
                await self._connect_and_listen()
                # Reset delay on successful connection
                delay = self.reconnect_delay
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SSE connection error: {e}")
                self._connected = False

            if self._running:
                logger.info(f"Reconnecting in {delay}s...")
                await asyncio.sleep(delay)
                # Exponential backoff
                delay = min(delay * 2, self.max_reconnect_delay)

    async def _connect_and_listen(self) -> None:
        """Connect to SSE endpoint and listen for events."""
        url = f"{self.serving_url}/api/v1/compute/connect"
        headers = {
            "X-Compute-ID": self.compute_id,
            "X-Capabilities": ",".join(self.capabilities),
            "X-Resources": json.dumps(self.resources),
            "Accept": "text/event-stream"
        }
        # Only add Authorization header if api_key is provided
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        logger.info(f"Connecting to SSE endpoint: {url}")

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code != 200:
                    raise Exception(f"SSE connection failed: {response.status_code}")

                self._connected = True
                logger.info(f"SSE connected to {url}")

                # Parse SSE stream
                event_type = None
                data_lines = []

                async for line in response.aiter_lines():
                    if not self._running:
                        break

                    line = line.strip()

                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                    elif line == "":
                        # End of event
                        if event_type and data_lines:
                            data_str = "\n".join(data_lines)
                            await self._handle_event(event_type, data_str)
                        event_type = None
                        data_lines = []

        self._connected = False

    async def _handle_event(self, event_type: str, data_str: str) -> None:
        """Handle a received event.

        Args:
            event_type: Type of the event
            data_str: JSON-encoded event data
        """
        self._last_event_time = datetime.now(timezone.utc)

        try:
            data = json.loads(data_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse event data: {e}")
            return

        logger.debug(f"Received event: {event_type}")

        # Dispatch to handlers
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            # Check for catch-all handler
            handlers = self._handlers.get("*", [])

        if not handlers:
            logger.debug(f"No handlers for event type: {event_type}")
            return

        for handler in handlers:
            try:
                await handler(event_type, data)
            except Exception as e:
                logger.error(f"Error in event handler for {event_type}: {e}")

    def get_status(self) -> dict[str, Any]:
        """Get client status information."""
        return {
            "connected": self._connected,
            "running": self._running,
            "shutdown_requested": self._shutdown_requested,
            "compute_id": self.compute_id,
            "serving_url": self.serving_url,
            "last_event_time": (
                self._last_event_time.isoformat()
                if self._last_event_time else None
            ),
            "registered_handlers": list(self._handlers.keys())
        }


# Global instance
_sse_client: Optional[SSEEventClient] = None


def get_sse_event_client() -> Optional[SSEEventClient]:
    """Get the global SSE event client."""
    return _sse_client


def set_sse_event_client(client: SSEEventClient) -> None:
    """Set the global SSE event client."""
    global _sse_client
    _sse_client = client


async def initialize_sse_event_client(
    serving_url: str,
    compute_id: str,
    api_key: str,
    capabilities: list[str],
    resources: dict[str, Any],
    reconnect_delay: int = 5,
    max_reconnect_delay: int = 60
) -> SSEEventClient:
    """Initialize and start the global SSE event client.

    Args:
        serving_url: Base URL of the Serving component
        compute_id: This compute instance's ID
        api_key: API key for authentication
        capabilities: List of capabilities
        resources: Resource specifications
        reconnect_delay: Initial delay between reconnection attempts (default: 5)
        max_reconnect_delay: Maximum delay between reconnection attempts (default: 60)

    Returns:
        The initialized SSE event client
    """
    client = SSEEventClient(
        serving_url=serving_url,
        compute_id=compute_id,
        api_key=api_key,
        capabilities=capabilities,
        resources=resources,
        reconnect_delay=reconnect_delay,
        max_reconnect_delay=max_reconnect_delay
    )
    set_sse_event_client(client)
    await client.start()
    return client
