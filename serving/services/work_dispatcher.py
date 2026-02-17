"""Event-driven work dispatcher.

Replaces polling-based task dispatch across decomposition, characterization,
and execution task types with a single signal-driven dispatch loop.

Two signal types wake the dispatch cycle:

  **Compute availability** — fired when:
  - A compute goes idle (claude_code_completed / claude_code_failed event)
  - A new compute registers via SSE

  **Work availability** — fired when:
  - A decomposition task is enqueued (new goal needs decomposing)
  - A characterization task is enqueued (new items need characterizing)
  - External work items become ready (called by WorkOrchestrator)

Both signals share a single asyncio.Event trigger so the dispatch cycle
runs once per event pulse rather than polling.

Dispatch priority:
  1. Decomposition tasks — highest priority, unblocks everything downstream
  2. Characterization tasks — high priority, unblocks issue creation
  3. Execution work items — delegated to WorkOrchestrator

Design reference: GitHub issue #874
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Module-level singleton
_work_dispatcher: Optional["WorkDispatcher"] = None


def get_work_dispatcher() -> "WorkDispatcher":
    """Get the singleton WorkDispatcher instance."""
    global _work_dispatcher
    if _work_dispatcher is None:
        raise RuntimeError(
            "WorkDispatcher not initialized. Call set_work_dispatcher() first."
        )
    return _work_dispatcher


def set_work_dispatcher(dispatcher: "WorkDispatcher") -> None:
    """Set the singleton WorkDispatcher instance."""
    global _work_dispatcher
    _work_dispatcher = dispatcher


@dataclass
class CharacterizationTask:
    """A pending characterization task waiting for a compute."""
    char_id: str
    item_id: str
    project_id: str
    task_context: str
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DecompositionTask:
    """A pending decomposition task waiting for a compute."""
    decomp_id: str
    goal_id: str
    task_context: str
    skill_instructions: str
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class WorkDispatcher:
    """Event-driven dispatcher for all task types.

    Maintains task queues (decomposition, characterization) and triggers
    a dispatch cycle whenever a compute becomes idle or new work arrives.
    No polling loops.
    """

    def __init__(self) -> None:
        self._trigger: asyncio.Event = asyncio.Event()
        self._decomp_queue: List[DecompositionTask] = []
        self._char_queue: List[CharacterizationTask] = []
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._stats: Dict[str, int] = {
            "decomp_assigned": 0,
            "char_assigned": 0,
            "execution_cycles": 0,
            "dispatch_cycles": 0,
        }

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """Start the dispatch loop coroutine."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._dispatch_loop(), name="work-dispatcher")
        logger.info("WorkDispatcher started")

    async def stop(self) -> None:
        """Stop the dispatch loop gracefully."""
        self._running = False
        self.trigger(reason="shutdown")
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        logger.info("WorkDispatcher stopped")

    def is_running(self) -> bool:
        return self._running

    # =========================================================================
    # Trigger (wakes dispatch cycle)
    # =========================================================================

    def trigger(self, reason: str = "") -> None:
        """Fire the dispatch trigger — wakes the dispatch loop for one cycle.

        Safe to call from any context (sync or async, any coroutine).

        Args:
            reason: Optional log label for debugging
        """
        if reason:
            logger.debug(f"Dispatch triggered: {reason}")
        self._trigger.set()

    # =========================================================================
    # Task Enqueueing
    # =========================================================================

    def enqueue_characterization(self, task: CharacterizationTask) -> None:
        """Add a characterization task to the queue and trigger dispatch.

        The task will be assigned to the next idle compute during a dispatch
        cycle. The caller should have already registered a completion event
        via services.completion_events.create_event(char_id) before calling
        this method.

        Args:
            task: CharacterizationTask to enqueue
        """
        self._char_queue.append(task)
        logger.debug(
            f"Enqueued characterization task {task.char_id} for item {task.item_id} "
            f"({len(self._char_queue)} pending)"
        )
        self.trigger(reason=f"char_task_enqueued:{task.char_id}")

    def enqueue_decomposition(self, task: DecompositionTask) -> None:
        """Add a decomposition task to the queue and trigger dispatch.

        Args:
            task: DecompositionTask to enqueue
        """
        self._decomp_queue.append(task)
        logger.debug(
            f"Enqueued decomposition task {task.decomp_id} for goal {task.goal_id} "
            f"({len(self._decomp_queue)} pending)"
        )
        self.trigger(reason=f"decomp_task_enqueued:{task.decomp_id}")

    def trigger_execution(self) -> None:
        """Trigger an execution dispatch cycle without enqueuing specific tasks.

        Used when execution work items become ready (new work created, dependency
        satisfied, etc.) and we want the orchestrator to pick them up promptly.
        """
        self.trigger(reason="execution_work_available")

    # =========================================================================
    # Dispatch Loop
    # =========================================================================

    async def _dispatch_loop(self) -> None:
        """Main dispatch loop — wait for trigger, run one cycle, repeat."""
        logger.info("WorkDispatcher loop running")

        while self._running:
            try:
                await self._trigger.wait()
                self._trigger.clear()

                if not self._running:
                    break

                self._stats["dispatch_cycles"] += 1
                await self._run_dispatch_cycle()

            except asyncio.CancelledError:
                logger.info("WorkDispatcher loop cancelled")
                break
            except Exception as e:
                logger.error(f"WorkDispatcher cycle error: {e}", exc_info=True)
                # Brief pause to avoid tight error loops, then continue
                await asyncio.sleep(1.0)

        logger.info("WorkDispatcher loop exited")

    async def _run_dispatch_cycle(self) -> None:
        """Run one dispatch cycle: assign pending tasks to idle computes.

        Priority order:
          1. Decomposition tasks (unblock everything downstream)
          2. Characterization tasks (unblock issue creation)
          3. Execution work items (delegated to WorkOrchestrator)
        """
        try:
            from services.sse_connection_manager import get_sse_connection_manager
        except Exception as e:
            logger.debug(f"SSE manager not available: {e}")
            return

        try:
            sse_manager = get_sse_connection_manager()
        except RuntimeError:
            logger.debug("SSE manager not initialized yet, skipping dispatch cycle")
            return

        # Assign decomposition tasks (highest priority)
        if self._decomp_queue:
            await self._assign_decomp_tasks(sse_manager)

        # Assign characterization tasks (high priority)
        if self._char_queue:
            await self._assign_char_tasks(sse_manager)

        # Trigger execution work dispatch (delegates to WorkOrchestrator)
        await self._trigger_execution_dispatch()

    async def _assign_decomp_tasks(self, sse_manager: Any) -> None:
        """Assign decomposition tasks to idle computes."""
        while self._decomp_queue:
            connection = sse_manager.find_matching_connection(
                idle_only=True, phase="decomposition"
            )
            if not connection:
                logger.debug("No idle compute for decomposition task")
                break

            task = self._decomp_queue.pop(0)
            try:
                await self._send_decomp_work(connection, task)
                self._stats["decomp_assigned"] += 1
            except Exception as e:
                logger.error(
                    f"Failed to assign decomp task {task.decomp_id} "
                    f"to {connection.compute_id}: {e}"
                )
                # Signal completion event with failure so caller unblocks
                from services.completion_events import signal as signal_event
                signal_event(task.decomp_id)

    async def _assign_char_tasks(self, sse_manager: Any) -> None:
        """Assign characterization tasks to idle computes."""
        while self._char_queue:
            connection = sse_manager.find_matching_connection(
                idle_only=True, phase="characterization"
            )
            if not connection:
                logger.debug("No idle compute for characterization task")
                break

            task = self._char_queue.pop(0)
            try:
                await self._send_char_work(connection, task)
                self._stats["char_assigned"] += 1
            except Exception as e:
                logger.error(
                    f"Failed to assign char task {task.char_id} "
                    f"to {connection.compute_id}: {e}"
                )
                from services.completion_events import signal as signal_event
                signal_event(task.char_id)

    async def _trigger_execution_dispatch(self) -> None:
        """Ask WorkOrchestrator to process pending execution work."""
        try:
            from services.work_orchestrator import get_work_orchestrator
            orchestrator = get_work_orchestrator()
            if orchestrator and orchestrator.is_running() and not orchestrator.is_paused():
                self._stats["execution_cycles"] += 1
                asyncio.create_task(
                    orchestrator._process_pending_work(),
                    name="execution-dispatch"
                )
        except RuntimeError:
            pass  # Orchestrator not initialized yet
        except Exception as e:
            logger.debug(f"Could not trigger execution dispatch: {e}")

    async def _send_decomp_work(self, connection: Any, task: DecompositionTask) -> None:
        """Send a decomposition task to a compute instance via SSE."""
        from mcp.auth import generate_api_key, register_compute_key

        task_api_key = generate_api_key()
        await register_compute_key(connection.compute_id, task_api_key)

        mcp_config = {
            "server_url": "http://serving:8002",
            "api_key": task_api_key,
        }

        from services.sse_connection_manager import get_sse_connection_manager
        sse_manager = get_sse_connection_manager()

        success = await sse_manager.send_work_assigned(
            compute_id=connection.compute_id,
            task_id=task.decomp_id,
            title=f"Goal Decomposition {task.decomp_id}",
            description=task.task_context,
            branch_name="",
            skills={
                "ids": ["goal-decomposer"],
                "merged_instructions": task.skill_instructions,
            },
            context={
                "decomposition_id": task.decomp_id,
                "task_type": "decomposition",
                "goal_id": task.goal_id,
            },
            mcp_config=mcp_config,
        )

        if not success:
            raise RuntimeError("Failed to send work_assigned event to compute")

        logger.info(
            f"Decomposition {task.decomp_id} assigned to compute {connection.compute_id}"
        )

    async def _send_char_work(self, connection: Any, task: CharacterizationTask) -> None:
        """Send a characterization task to a compute instance via SSE."""
        from mcp.auth import generate_api_key, register_compute_key

        task_api_key = generate_api_key()
        await register_compute_key(connection.compute_id, task_api_key)

        mcp_config = {
            "server_url": "http://serving:8002",
            "api_key": task_api_key,
        }

        from services.sse_connection_manager import get_sse_connection_manager
        sse_manager = get_sse_connection_manager()

        char_skill = _get_characterizer_skill_instructions()

        success = await sse_manager.send_work_assigned(
            compute_id=connection.compute_id,
            task_id=task.char_id,
            title=f"Work Item Characterization {task.char_id}",
            description=task.task_context,
            branch_name="",
            skills={
                "ids": ["characterizer"],
                "merged_instructions": char_skill,
            },
            context={
                "characterization_id": task.char_id,
                "task_type": "characterization",
                "project_id": task.project_id,
            },
            mcp_config=mcp_config,
        )

        if not success:
            raise RuntimeError("Failed to send work_assigned event to compute")

        logger.info(
            f"Characterization {task.char_id} (item {task.item_id}) assigned to "
            f"compute {connection.compute_id}"
        )

    # =========================================================================
    # Statistics and Introspection
    # =========================================================================

    def get_queue_depths(self) -> Dict[str, int]:
        """Return current queue depths for monitoring."""
        return {
            "decomp_queue": len(self._decomp_queue),
            "char_queue": len(self._char_queue),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return dispatcher statistics."""
        return {
            **self._stats,
            **self.get_queue_depths(),
            "running": self._running,
        }


def _get_characterizer_skill_instructions() -> str:
    """Minimal characterizer skill instructions for compute instances."""
    return """# Work Item Characterizer

You are characterizing a single work item for the planning pipeline.

Your task description contains ONE item to characterize.

1. Evaluate in isolation (Frame 1): assign ontology tags, business meaning, technical meaning
2. Evaluate in context (Frame 2): determine role, discover dependencies using the topology
3. Submit result using `claudevn_submit_characterization` MCP tool

Submit exactly ONE characterization. The characterization_id and item_id are specified in your task.
"""


async def start_work_dispatcher() -> WorkDispatcher:
    """Create, register, and start the WorkDispatcher singleton."""
    dispatcher = WorkDispatcher()
    set_work_dispatcher(dispatcher)
    await dispatcher.start()
    return dispatcher


async def stop_work_dispatcher() -> None:
    """Stop the WorkDispatcher singleton if running."""
    global _work_dispatcher
    if _work_dispatcher and _work_dispatcher.is_running():
        await _work_dispatcher.stop()
