"""Characterization Service for the work management pipeline.

Translates raw decomposed tasks into fully characterized work items with
ontology tags, meaning assessments, and contextual dependencies.

The service operates in two evaluation frames:
1. In isolation — intrinsic assessment of the work item
2. In project context — against the existing body of characterized work

Pipeline: Decomposition → Characterization → Planner Backlog

Redis key structure:
  claudevn:characterization:{project_id}:{item_id}  — JSON(CharacterizationResult)
  claudevn:characterization:{project_id}:index       — Set of characterized item IDs

Reference: docs/work_management_framework.md — Section 5
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.characterization import (
    BatchCharacterizationRequest,
    BatchCharacterizationResponse,
    CharacterizationRequest,
    CharacterizationResult,
    CharacterizationStatus,
    ContextualDependency,
    TopologyItem,
    WorkTopology,
)
from models.ontology import OntologyTags

logger = logging.getLogger(__name__)

# Module-level singleton
_characterization_service: Optional["CharacterizationService"] = None


def get_characterization_service() -> "CharacterizationService":
    """Get the singleton CharacterizationService instance."""
    global _characterization_service
    if _characterization_service is None:
        raise RuntimeError(
            "CharacterizationService not initialized. Call set_characterization_service() first."
        )
    return _characterization_service


def set_characterization_service(service: "CharacterizationService") -> None:
    """Set the singleton CharacterizationService instance."""
    global _characterization_service
    _characterization_service = service


class CharacterizationService:
    """Service for characterizing work items before they enter the planner.

    Manages the characterization pipeline:
    - Accepts raw work items (from decomposition or direct creation)
    - Produces CharacterizationResult with ontology tags, meanings, dependencies
    - Stores results in Redis for planner consumption
    - Maintains work topology for in-context evaluation

    The actual AI-driven characterization logic (LLM prompts) is delegated to
    compute instances, following the v1.0 architecture. This service manages
    the pipeline state, storage, and topology access.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._results: Dict[str, Dict[str, CharacterizationResult]] = {}  # project_id → {item_id → result}
        self._initialized = False

    def _key(self, key: str) -> str:
        """Get prefixed Redis key."""
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}characterization:{key}"

    async def initialize(self) -> None:
        """Initialize service, loading state from Redis."""
        if self._initialized:
            return
        await self._load_from_redis()
        self._initialized = True
        logger.info("Characterization service initialized")

    # ========================================================================
    # Store and Retrieve Characterization Results
    # ========================================================================

    async def store_result(self, result: CharacterizationResult) -> None:
        """Store a characterization result.

        Called after characterization completes (either from compute callback
        or from batch processing).
        """
        project_id = result.project_id
        if project_id not in self._results:
            self._results[project_id] = {}

        result.updated_at = datetime.now(timezone.utc)
        self._results[project_id][result.item_id] = result
        await self._save_result_to_redis(project_id, result.item_id)

        logger.info(
            f"Stored characterization for item {result.item_id} "
            f"in project {project_id} (confidence={result.confidence:.2f})"
        )

    async def get_result(
        self,
        project_id: str,
        item_id: str,
    ) -> Optional[CharacterizationResult]:
        """Get characterization result for a specific work item."""
        project_results = self._results.get(project_id, {})
        return project_results.get(item_id)

    async def get_results_for_project(
        self,
        project_id: str,
    ) -> List[CharacterizationResult]:
        """Get all characterization results for a project."""
        project_results = self._results.get(project_id, {})
        return list(project_results.values())

    async def get_completed_results(
        self,
        project_id: str,
    ) -> List[CharacterizationResult]:
        """Get only successfully completed characterizations for a project."""
        project_results = self._results.get(project_id, {})
        return [
            r for r in project_results.values()
            if r.status == CharacterizationStatus.COMPLETED
        ]

    async def has_pending_characterizations(self, project_id: str) -> bool:
        """Check if a project has any pending or in-progress characterizations.

        Used by the work orchestrator to gate execution until characterization
        is complete (#841).
        """
        project_results = self._results.get(project_id, {})
        return any(
            r.status in (CharacterizationStatus.PENDING, CharacterizationStatus.IN_PROGRESS)
            for r in project_results.values()
        )

    # ========================================================================
    # Batch Operations
    # ========================================================================

    async def create_pending_batch(
        self,
        request: BatchCharacterizationRequest,
    ) -> BatchCharacterizationResponse:
        """Create pending characterization entries for a batch of items.

        Called after decomposition to register items for characterization.
        Actual characterization is performed by compute instances.
        """
        project_id = request.project_id
        results = []

        for item_req in request.items:
            result = CharacterizationResult(
                item_id=item_req.item_id,
                project_id=project_id,
                # Placeholder tags — will be filled during actual characterization
                ontology_tags=None,  # type: ignore[arg-type] — set during characterization
                meaning=None,  # type: ignore[arg-type] — set during characterization
                status=CharacterizationStatus.PENDING,
                confidence=0.0,
                evaluated_in_isolation=False,
                evaluated_in_context=False,
            )
            await self.store_result(result)
            results.append(result)

        return BatchCharacterizationResponse(
            project_id=project_id,
            results=results,
            total=len(results),
            completed=0,
            failed=0,
        )

    async def mark_in_progress(
        self,
        project_id: str,
        item_id: str,
    ) -> Optional[CharacterizationResult]:
        """Mark a characterization as in progress."""
        result = await self.get_result(project_id, item_id)
        if result and result.status == CharacterizationStatus.PENDING:
            result.status = CharacterizationStatus.IN_PROGRESS
            result.updated_at = datetime.now(timezone.utc)
            await self._save_result_to_redis(project_id, item_id)
        return result

    async def mark_failed(
        self,
        project_id: str,
        item_id: str,
        error: str,
    ) -> Optional[CharacterizationResult]:
        """Mark a characterization as failed."""
        result = await self.get_result(project_id, item_id)
        if result:
            result.status = CharacterizationStatus.FAILED
            result.error = error
            result.updated_at = datetime.now(timezone.utc)
            await self._save_result_to_redis(project_id, item_id)
        return result

    # ========================================================================
    # Work Topology (read access for in-context evaluation)
    # ========================================================================

    async def get_work_topology(self, project_id: str) -> WorkTopology:
        """Build the work topology for a project.

        Returns a summarized view of all completed characterizations,
        used by the characterizer when evaluating new items in context.
        """
        completed = await self.get_completed_results(project_id)

        items = []
        cluster_ids_seen = set()
        for r in completed:
            # Build topology item from characterization result
            cluster_ids = r.ontology_tags.project_specific.cluster_ids if r.ontology_tags else []
            cluster_ids_seen.update(cluster_ids)

            items.append(TopologyItem(
                item_id=r.item_id,
                title="",  # Title not stored in result — populated by caller if needed
                ontology_tags=r.ontology_tags,
                contextual_role=r.meaning.contextual.role if r.meaning else "incremental",
                cluster_ids=cluster_ids,
            ))

        return WorkTopology(
            project_id=project_id,
            items=items,
            cluster_names=[],  # Populated by caller from OntologyService
        )

    # ========================================================================
    # Compute Delegation (AI-powered characterization)
    # ========================================================================

    # Default timeout for characterization (5 minutes)
    CHARACTERIZATION_TIMEOUT = 300

    async def characterize_items(
        self,
        project_id: str,
        items: List[CharacterizationRequest],
        source_goal_id: Optional[str] = None,
    ) -> BatchCharacterizationResponse:
        """Characterize work items by delegating each to a separate compute instance.

        Creates one characterization task per item, spawning computes in parallel
        where capacity allows. Each compute receives exactly one item to evaluate,
        preventing the silent-drop issue where multi-item submissions were only
        partially accepted.

        Args:
            project_id: Project context
            items: Work items to characterize
            source_goal_id: Goal that produced these items (if from decomposition)

        Returns:
            Batch response with results (may still be PENDING if async)
        """
        # Create pending batch entries for all items
        batch_request = BatchCharacterizationRequest(
            project_id=project_id,
            items=items,
            source_goal_id=source_goal_id,
        )
        await self.create_pending_batch(batch_request)

        # Get topology for Frame 2 context (shared across all items)
        topology = await self.get_work_topology(project_id)

        # Enqueue one characterization task per item via WorkDispatcher (event-driven)
        assignments: List[tuple] = []  # (char_id, item_id)
        failed_items: List[str] = []

        for item in items:
            char_id = f"char-{uuid.uuid4().hex[:12]}"
            task_context = self._build_single_item_context(
                characterization_id=char_id,
                project_id=project_id,
                item=item,
                topology=topology,
            )
            try:
                self._enqueue_characterization_task(
                    characterization_id=char_id,
                    item_id=item.item_id,
                    task_context=task_context,
                    project_id=project_id,
                )
                await self.mark_in_progress(project_id, item.item_id)
                assignments.append((char_id, item.item_id))
                logger.info(
                    f"Characterization {char_id} for item {item.item_id} enqueued"
                )
            except Exception as e:
                logger.error(f"Failed to enqueue characterization for item {item.item_id}: {e}")
                await self.mark_failed(project_id, item.item_id, str(e))
                failed_items.append(item.item_id)

        # Wait for all characterizations via asyncio.Event (no polling)
        if assignments:
            await asyncio.gather(*[
                self._wait_for_characterization_result(
                    characterization_id=char_id,
                    project_id=project_id,
                    item_ids=[item_id],
                )
                for char_id, item_id in assignments
            ], return_exceptions=True)

        # Collect results — let the Redis state determine counts (avoids double-counting
        # items that failed to spawn, since mark_failed already wrote their FAILED status)
        completed = 0
        failed = 0
        results = []
        for item in items:
            result = await self.get_result(project_id, item.item_id)
            if result:
                results.append(result)
                if result.status == CharacterizationStatus.COMPLETED:
                    completed += 1
                elif result.status == CharacterizationStatus.FAILED:
                    failed += 1

        return BatchCharacterizationResponse(
            project_id=project_id,
            results=results,
            total=len(items),
            completed=completed,
            failed=failed,
        )

    def _build_characterization_task_context(
        self,
        characterization_id: str,
        project_id: str,
        items: List[CharacterizationRequest],
        topology: WorkTopology,
    ) -> str:
        """Build task context for the characterization compute instance.

        Args:
            characterization_id: Tracking ID
            project_id: Project context
            items: Items to characterize
            topology: Existing work topology for Frame 2

        Returns:
            Task context string for compute instance
        """
        # Build items section
        items_section = "\n".join(
            f"- **{item.item_id}**: {item.title}\n"
            f"  Description: {item.description[:500]}\n"
            f"  Hints: type={item.issue_type_hint or 'none'}, area={item.area_hint or 'none'}"
            for item in items
        )

        # Build topology section for Frame 2
        topology_section = ""
        if topology.items:
            topology_lines = []
            for t_item in topology.items[:50]:  # Limit to avoid token overflow
                tags_str = ""
                if t_item.ontology_tags:
                    tags_str = (
                        f"type={t_item.ontology_tags.universal.work_type.value}, "
                        f"stage={t_item.ontology_tags.universal.lifecycle_stage.value}"
                    )
                topology_lines.append(
                    f"- {t_item.item_id}: role={t_item.contextual_role}, {tags_str}"
                )
            topology_section = f"""
## Existing Work Topology ({len(topology.items)} items)
Use this for Frame 2 (in-context) evaluation:
{chr(10).join(topology_lines)}
"""

        # Valid enum values for the prompt
        ontology_enums = """
## Valid Ontology Values
- work_type: feature, bug_fix, refactor, test, documentation, infrastructure, integration
- lifecycle_stage: design, build, test, validate, deploy
- technical_domains: frontend, backend, data, api, security, devops, testing, documentation
- contextual_role: foundational, incremental, enabling, blocking
- dependency relation: blocks, enables, related_to, extends, conflicts_with
- dependency type: structural, contextual
"""

        task_context = f"""# Characterization Task

You have been assigned to characterize work items for project {project_id}.

## Assignment Details
- **Characterization ID:** {characterization_id}
- **Project ID:** {project_id}
- **Items to characterize:** {len(items)}

## Items to Characterize
{items_section}

{topology_section}

{ontology_enums}

## Your Task

For EACH item, perform two evaluation frames:

**Frame 1 (In Isolation):**
- Assign ontology tags (work_type, lifecycle_stage, technical_domains)
- Assess business meaning (value, user impact)
- Assess technical meaning (components, risk)

**Frame 2 (In Project Context):**
- Determine contextual role (foundational, incremental, enabling, blocking)
- Discover dependencies against existing work topology
- Classify dependencies as structural or contextual

Submit results for EACH item using `claudevn_submit_characterization` with:
- characterization_id: "{characterization_id}"
- project_id: "{project_id}"
- item_id: (the specific item ID)
- ontology_tags, meaning, dependencies, confidence

Submit one call per item. Set evaluated_in_context=true if topology was available.
"""

        return task_context

    def _build_single_item_context(
        self,
        characterization_id: str,
        project_id: str,
        item: CharacterizationRequest,
        topology: WorkTopology,
    ) -> str:
        """Build task context for characterizing a single work item.

        Each compute instance receives exactly one item to evaluate,
        preventing the silent-drop issue from multi-item submissions.

        Args:
            characterization_id: Tracking ID for this specific task
            project_id: Project context
            item: The single work item to characterize
            topology: Existing work topology for Frame 2

        Returns:
            Task context string for compute instance
        """
        # Build topology section for Frame 2 (same as multi-item version)
        topology_section = ""
        if topology.items:
            topology_lines = []
            for t_item in topology.items[:50]:  # Limit to avoid token overflow
                tags_str = ""
                if t_item.ontology_tags:
                    tags_str = (
                        f"type={t_item.ontology_tags.universal.work_type.value}, "
                        f"stage={t_item.ontology_tags.universal.lifecycle_stage.value}"
                    )
                topology_lines.append(
                    f"- {t_item.item_id}: role={t_item.contextual_role}, {tags_str}"
                )
            topology_section = f"""
## Existing Work Topology (Frame 2 Context)
{chr(10).join(topology_lines)}
"""

        return f"""# Work Item Characterization Task

## Task ID
{characterization_id}

## Project
{project_id}

## Your Assignment
Characterize the following work item using two evaluation frames:

**Frame 1 (Isolation):** Evaluate the item on its own — assign ontology tags, business meaning, technical meaning.
**Frame 2 (Context):** Evaluate how this item relates to existing work — determine contextual role, discover dependencies.

## Item to Characterize

- **{item.item_id}**: {item.title}
  Description: {item.description[:500]}
  Hints: type={item.issue_type_hint or 'none'}, area={item.area_hint or 'none'}

{topology_section}

## Submission Instructions

Submit your characterization using `claudevn_submit_characterization` with:
- characterization_id: "{characterization_id}"
- project_id: "{project_id}"
- item_id: "{item.item_id}"
- ontology_tags, meaning, dependencies, confidence
- evaluated_in_context: true (if topology was available)

Submit exactly ONE characterization for this task.
"""

    def _enqueue_characterization_task(
        self,
        characterization_id: str,
        item_id: str,
        task_context: str,
        project_id: str,
    ) -> None:
        """Register completion event and enqueue characterization task to WorkDispatcher.

        Replaces the polling spawn-wait loop with an event-driven enqueue:
        - Registers an asyncio.Event for this task (before enqueuing, to avoid
          race with the MCP tool signaling before the event is registered)
        - Enqueues the CharacterizationTask to the WorkDispatcher queue
        - The dispatcher assigns it to the next idle compute, no polling needed

        Rolling batches (4 items + 2 computes → 2+2) work naturally: the first 2
        tasks are assigned immediately; as each compute finishes, it goes idle, the
        dispatcher fires, and the next task is assigned.

        Args:
            characterization_id: Tracking ID
            item_id: Work item being characterized
            task_context: Task description for compute
            project_id: Project context
        """
        from services.completion_events import create_event
        from services.work_dispatcher import get_work_dispatcher, CharacterizationTask

        # Register event BEFORE enqueuing so signal() is never missed
        create_event(characterization_id)

        dispatcher = get_work_dispatcher()
        dispatcher.enqueue_characterization(CharacterizationTask(
            char_id=characterization_id,
            item_id=item_id,
            project_id=project_id,
            task_context=task_context,
        ))

    def _get_characterizer_skill_instructions(self) -> str:
        """Get minimal characterizer skill instructions."""
        return """# Work Item Characterizer

You are characterizing a single work item for the planning pipeline.

Your task description contains ONE item to characterize.

1. Evaluate in isolation (Frame 1): assign ontology tags, business meaning, technical meaning
2. Evaluate in context (Frame 2): determine role, discover dependencies using the topology
3. Submit result using `claudevn_submit_characterization` MCP tool

Submit exactly ONE characterization. The characterization_id and item_id are specified in your task.
"""

    async def _wait_for_characterization_result(
        self,
        characterization_id: str,
        project_id: str,
        item_ids: List[str],
    ) -> None:
        """Wait for compute to submit characterization results.

        Uses an in-process asyncio.Event registered by _enqueue_characterization_task
        and signaled by the claudevn_submit_characterization MCP tool. No polling.

        The idle reset for the compute is handled by the claude_code_completed
        event handler in api/compute.py — do NOT reset connection status here.

        Args:
            characterization_id: ID to wait for
            project_id: Project context
            item_ids: Items being characterized (for timeout cleanup)
        """
        from services.completion_events import get_event, cleanup as cleanup_event

        event = get_event(characterization_id)
        if event is None:
            logger.warning(
                f"No completion event for characterization {characterization_id} "
                "— was it registered before enqueuing?"
            )
            return

        try:
            await asyncio.wait_for(event.wait(), timeout=self.CHARACTERIZATION_TIMEOUT)
            logger.info(f"Characterization {characterization_id} completed")
        except asyncio.TimeoutError:
            logger.warning(
                f"Characterization {characterization_id} timed out "
                f"after {self.CHARACTERIZATION_TIMEOUT}s"
            )
            # Mark remaining items as failed
            for item_id in item_ids:
                result = await self.get_result(project_id, item_id)
                if result and result.status != CharacterizationStatus.COMPLETED:
                    await self.mark_failed(
                        project_id, item_id,
                        f"Characterization timed out after {self.CHARACTERIZATION_TIMEOUT}s"
                    )
        finally:
            cleanup_event(characterization_id)

    # ========================================================================
    # Statistics
    # ========================================================================

    async def get_stats(self, project_id: str) -> Dict[str, int]:
        """Get characterization statistics for a project."""
        project_results = self._results.get(project_id, {})
        stats = {
            "total": 0,
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "failed": 0,
        }
        for r in project_results.values():
            stats["total"] += 1
            stats[r.status.value] += 1
        return stats

    # ========================================================================
    # Redis Persistence
    # ========================================================================

    async def _load_from_redis(self) -> None:
        """Load all characterization results from Redis."""
        if not self._redis:
            return

        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis._redis.scan(
                    cursor,
                    match=self._key("*:index"),
                    count=100,
                )
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    # Extract project_id from: prefix:characterization:{project_id}:index
                    parts = key_str.split(":")
                    try:
                        char_idx = parts.index("characterization")
                        project_id = parts[char_idx + 1]
                    except (ValueError, IndexError):
                        continue

                    await self._load_project_from_redis(project_id)

                if cursor == 0:
                    break
        except Exception as e:
            logger.error(f"Failed to load characterizations from Redis: {e}")

    async def _load_project_from_redis(self, project_id: str) -> None:
        """Load characterization results for a single project."""
        if not self._redis:
            return

        try:
            index_key = self._key(f"{project_id}:index")
            item_ids = await self._redis._redis.smembers(index_key)

            if project_id not in self._results:
                self._results[project_id] = {}

            for item_id_raw in item_ids:
                item_id = item_id_raw.decode() if isinstance(item_id_raw, bytes) else item_id_raw
                result_key = self._key(f"{project_id}:{item_id}")
                data = await self._redis._redis.get(result_key)
                if data:
                    json_str = data.decode() if isinstance(data, bytes) else data
                    try:
                        result = CharacterizationResult.model_validate_json(json_str)
                        self._results[project_id][item_id] = result
                    except Exception as e:
                        logger.warning(f"Failed to parse characterization {item_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to load characterizations for project {project_id}: {e}")

    async def _save_result_to_redis(self, project_id: str, item_id: str) -> None:
        """Save a single characterization result to Redis."""
        if not self._redis:
            return

        try:
            result = self._results.get(project_id, {}).get(item_id)
            if not result:
                return

            # Save the result as JSON
            result_key = self._key(f"{project_id}:{item_id}")
            await self._redis._redis.set(result_key, result.model_dump_json())

            # Add to the index set
            index_key = self._key(f"{project_id}:index")
            await self._redis._redis.sadd(index_key, item_id)
        except Exception as e:
            logger.error(f"Failed to save characterization {item_id}: {e}")
