"""
ClaudeVN Compute Infrastructure (v1.0) — standalone asyncio application.

No HTTP server. Compute connects outbound to Serving via SSE and receives
work assignments. Docker healthcheck uses a heartbeat file updated on each
SSE keepalive.
"""

import asyncio
import os
import signal
import logging
import subprocess
from pathlib import Path

from config import load_config, get_version
from services.sse_event_client import initialize_sse_event_client
from services.conflict_handler import initialize_conflict_handler
from services.claude_code_spawner import initialize_claude_code_spawner, get_claude_code_spawner
from services.credential_monitor import initialize_credential_monitor, get_credential_monitor


# Configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
log_file = os.getenv('COMPUTE_LOG_FILE')

handlers = [logging.StreamHandler()]
if log_file:
    # Create log directory if it doesn't exist
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handlers.append(logging.FileHandler(log_file))

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)

# Heartbeat file path for Docker healthcheck
HEARTBEAT_FILE = Path(os.getenv("COMPUTE_HEARTBEAT_FILE", "/tmp/compute-heartbeat"))

# Global state
config = None
sse_event_client = None
conflict_handler = None
claude_code_spawner = None
credential_monitor = None
_shutdown_event: asyncio.Event = None


def _detect_runtime_tools(capabilities: list[str]) -> list[str]:
    """Detect installed runtimes and return as tools_available labels.

    Tries detect-runtimes.sh first, then falls back to extracting
    runtime:* entries from the capabilities list (set by detect-capabilities.sh
    in the entrypoint).
    """
    tools = []

    # Try running detect-runtimes.sh
    detect_script = Path("/app/detect-runtimes.sh")
    if detect_script.exists():
        try:
            result = subprocess.run(
                [str(detect_script), "--comma"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                tools = [t.strip() for t in result.stdout.strip().split(",") if t.strip()]
        except Exception as e:
            logger.debug(f"detect-runtimes.sh failed: {e}")

    # Fallback: extract runtime:* entries from capabilities (set by detect-capabilities.sh)
    if not tools:
        tools = [c for c in capabilities if c.startswith("runtime:")]

    return tools


def _touch_heartbeat() -> None:
    """Update heartbeat file timestamp for Docker healthcheck."""
    try:
        HEARTBEAT_FILE.touch()
    except OSError:
        pass


async def _handle_keepalive(event_type: str, data: dict) -> None:
    """Handle keepalive events from Serving."""
    logger.debug(f"Received keepalive: {data.get('timestamp')}")
    _touch_heartbeat()


async def _handle_credentials_refresh(event_type: str, data: dict) -> None:
    """Handle credentials_refresh event from Serving.

    Triggers credential reload, equivalent to receiving SIGHUP.
    """
    reason = data.get("reason", "No reason provided")
    logger.info(f"Received credentials_refresh from Serving: {reason}")
    monitor = get_credential_monitor()
    if monitor:
        new_status = await monitor.reload_credentials()
        logger.info(f"Credential refresh complete: status={new_status.value}")
    else:
        logger.warning("No credential monitor, cannot refresh credentials")


async def _handle_drain(event_type: str, data: dict) -> None:
    """Handle drain event from Serving.

    Stops accepting new work and waits for running tasks to complete
    before allowing restart.
    """
    reason = data.get("reason", "No reason provided")
    grace_period = data.get("grace_period_seconds", 300)
    logger.warning(
        f"Received drain event: {reason} (grace_period={grace_period}s)"
    )
    # Delegate to the existing graceful shutdown callback
    await _graceful_shutdown_callback(grace_period)


async def _graceful_shutdown_callback(grace_period_seconds: int) -> None:
    """Callback for graceful shutdown with work completion.

    This is called when a shutdown event is received from Serving.
    It waits for current work to complete (up to grace_period_seconds)
    then initiates shutdown.

    Args:
        grace_period_seconds: Maximum time to wait for work to complete
    """
    logger.info(f"Graceful shutdown initiated with {grace_period_seconds}s grace period")

    spawner = get_claude_code_spawner()
    if spawner:
        # Get current running instances
        status = spawner.get_status()
        running_instances = status.get("running_instances", 0)

        if running_instances > 0:
            logger.info(f"Waiting for {running_instances} Claude Code instances to complete...")

            # Wait for instances to complete (poll until no active instances or timeout)
            start_time = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start_time < grace_period_seconds:
                status = spawner.get_status()
                running = status.get("running_instances", 0)
                if running > 0:
                    logger.info(f"Waiting for {running} active Claude Code instances to complete...")
                    await asyncio.sleep(1)
                else:
                    logger.info("No active Claude Code instances, proceeding with shutdown")
                    break
            else:
                logger.warning(f"Grace period expired, forcing shutdown with {status.get('running_instances', 0)} active instances")
        else:
            logger.info("No active Claude Code instances, proceeding with shutdown")
    else:
        logger.info("No Claude Code spawner, proceeding with immediate shutdown")
        await asyncio.sleep(min(grace_period_seconds, 5))

    logger.info("Graceful shutdown callback completed")


def _handle_sighup() -> None:
    """Handle SIGHUP signal to trigger credential reload.

    This is a sync callback registered with the event loop's signal handler.
    It schedules the async reload as a task.
    """
    logger.info("Received SIGHUP signal, scheduling credential reload...")
    monitor = get_credential_monitor()
    if monitor:
        asyncio.get_event_loop().create_task(_async_sighup_reload())
    else:
        logger.warning("No credential monitor available, ignoring SIGHUP")


async def _async_sighup_reload() -> None:
    """Async handler for SIGHUP credential reload."""
    monitor = get_credential_monitor()
    if monitor:
        new_status = await monitor.reload_credentials()
        logger.info(f"SIGHUP credential reload complete: status={new_status.value}")


async def startup() -> None:
    """Initialize all services."""
    global config, sse_event_client, conflict_handler, claude_code_spawner, credential_monitor

    logger.info("Starting ClaudeVN Compute Infrastructure (v1.0)...")

    # Load configuration
    config = load_config()
    logger.info(f"Loaded configuration: compute_id={config.instance_id}")

    # Create workspace directory
    workspace_path = Path(config.workspace_path)
    workspace_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Workspace path: {workspace_path}")

    # Initialize Claude Code spawner
    max_instances = int(os.getenv("MAX_CLAUDE_INSTANCES", "1"))
    claude_code_spawner = initialize_claude_code_spawner(
        workspace_path=str(workspace_path),
        serving_url=config.serving_url,
        compute_id=config.instance_id,
        api_key=config.api_key,
        max_instances=max_instances,
        serving_repo_url=config.serving_repo_url,
        tls_verify=config.tls_verify,
    )
    logger.info(f"Claude Code spawner initialized (max_instances={max_instances})")
    if config.serving_repo_url:
        logger.info(f"Serving repo sync enabled: {config.serving_repo_url}")

    # Initialize credential monitor
    credential_monitor = await initialize_credential_monitor(
        credentials_path=config.credentials_path,
        check_interval=config.credential_check_interval,
        expiry_warning_days=config.credential_expiry_warning_days,
        auth_mode=config.auth_mode,
        serving_auth_url=config.serving_auth_url,
        tls_verify=config.tls_verify,
    )
    logger.info(f"Credential monitor initialized (status={credential_monitor.status.value})")

    # Register SIGHUP handler for credential reload
    try:
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGHUP, _handle_sighup)
        logger.info("SIGHUP handler registered for credential reload")
    except (NotImplementedError, OSError) as e:
        # Windows doesn't support SIGHUP
        logger.warning(f"Could not register SIGHUP handler: {e}")

    # Initialize conflict handler
    conflict_handler = initialize_conflict_handler(
        workspace_path=str(workspace_path),
        mcp_client=None,  # Will be set when MCP client is available
        progress_callback=None
    )
    logger.info("Conflict resolution handler initialized")

    # Initialize SSE event client for receiving events from Serving
    try:
        capabilities_list = [c.strip() for c in config.capabilities.split(",") if c.strip()]
        resources = {
            "cpu": config.resources_cpu,
            "memory": config.resources_memory
        }

        # Detect installed runtimes to populate tools_available
        tools_available = _detect_runtime_tools(capabilities_list)
        if tools_available:
            logger.info(f"Detected runtime tools: {tools_available}")

        sse_event_client = await initialize_sse_event_client(
            serving_url=config.serving_url,
            compute_id=config.instance_id,
            api_key=config.api_key,
            capabilities=capabilities_list,
            resources=resources,
            reconnect_delay=config.sse_reconnect_delay,
            max_reconnect_delay=config.sse_max_reconnect_delay,
            tls_verify=config.tls_verify,
            tools_available=tools_available,
        )

        # Register event handlers
        # work_assigned and work_cancelled are handled by built-in handlers
        sse_event_client.on("merge_conflict", conflict_handler.handle_merge_conflict)
        sse_event_client.on("keepalive", _handle_keepalive)
        sse_event_client.on("shutdown", sse_event_client._handle_shutdown_event)
        sse_event_client.on("credentials_refresh", _handle_credentials_refresh)
        sse_event_client.on("drain", _handle_drain)

        # Set graceful shutdown callback
        sse_event_client.set_shutdown_callback(_graceful_shutdown_callback)

        logger.info("SSE event client initialized and connected")
    except Exception as e:
        logger.error(f"Failed to initialize SSE event client: {e}")
        logger.error("Compute infrastructure cannot function without SSE connection")
        raise

    # Touch heartbeat on successful startup
    _touch_heartbeat()

    logger.info("Compute infrastructure started successfully")


async def shutdown() -> None:
    """Shut down all services cleanly."""
    logger.info("Shutting down Compute infrastructure...")

    # Stop credential monitor
    if credential_monitor:
        try:
            await credential_monitor.stop()
            logger.info("Credential monitor stopped")
        except Exception as e:
            logger.error(f"Error stopping credential monitor: {e}")

    # Remove SIGHUP handler
    try:
        loop = asyncio.get_event_loop()
        loop.remove_signal_handler(signal.SIGHUP)
    except (NotImplementedError, OSError):
        pass

    # Shutdown all Claude Code instances
    if claude_code_spawner:
        try:
            await claude_code_spawner.shutdown()
            logger.info("All Claude Code instances stopped")
        except Exception as e:
            logger.error(f"Error stopping Claude Code instances: {e}")

    # Stop SSE event client
    if sse_event_client:
        try:
            await sse_event_client.stop()
            logger.info("SSE event client stopped")
        except Exception as e:
            logger.error(f"Error stopping SSE client: {e}")

    # Remove heartbeat file on clean shutdown
    try:
        HEARTBEAT_FILE.unlink(missing_ok=True)
    except OSError:
        pass

    logger.info("Compute infrastructure shutdown complete")


async def main() -> None:
    """Run the compute infrastructure as a standalone asyncio application."""
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    loop = asyncio.get_event_loop()

    # Register signal handlers for graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown_event.set)

    await startup()

    try:
        # Wait until shutdown is signaled
        await _shutdown_event.wait()
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
