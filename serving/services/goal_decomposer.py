"""Goal Decomposer Service for ClaudeVN.

Transforms natural language goals into structured issues with dependencies
by delegating to Claude Code compute instances. This follows the v1.0
architecture where serving orchestrates work but does NOT call Anthropic
APIs directly.

The actual LLM work is performed by compute instances using their OAuth
credentials (~/.claude), not by serving component directly.
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from models.characterization import CharacterizationRequest, CharacterizationResult
from models.goal_decomposer import (
    DecomposedIssue,
    EstimatedComplexity,
    GoalDecomposerConfig,
    GoalDecompositionResult,
)
from models.issue import Issue, IssueArea, IssuePriority, IssueType

logger = logging.getLogger(__name__)

# Default timeout for decomposition (5 minutes)
DEFAULT_DECOMPOSITION_TIMEOUT = 300

# Polling interval for checking decomposition completion
POLL_INTERVAL_SECONDS = 2


class NoComputeAvailableError(Exception):
    """Raised when no compute instances are available for decomposition."""
    pass


class DecompositionTimeoutError(Exception):
    """Raised when decomposition times out waiting for compute result."""
    pass


class GoalDecomposerService:
    """Service for decomposing goals into structured issues.

    Delegates decomposition work to Claude Code compute instances, which
    have OAuth credentials and can call the Anthropic API. This follows
    the v1.0 architecture where serving orchestrates but does not execute
    LLM work directly.
    """

    def __init__(
        self,
        config: Optional[GoalDecomposerConfig] = None,
        timeout: int = DEFAULT_DECOMPOSITION_TIMEOUT,
    ):
        """Initialize the Goal Decomposer service.

        Args:
            config: Service configuration
            timeout: Timeout in seconds for decomposition
        """
        self._config = config or GoalDecomposerConfig()
        self._timeout = timeout
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the service."""
        if self._initialized:
            return

        self._initialized = True
        logger.info("Goal Decomposer service initialized (delegated mode)")

    async def decompose_goal(
        self,
        goal_id: str,
        goal_text: str,
        project_context: Optional[Dict[str, Any]] = None,
        existing_issues: Optional[List[Issue]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        conversation_comments: Optional[List[Dict[str, Any]]] = None,
        existing_decomposition: Optional[Dict[str, Any]] = None,
        supplemental_context: Optional[Dict[str, Any]] = None,
    ) -> GoalDecompositionResult:
        """Decompose a goal into structured issues.

        This method spawns a compute instance with the goal-decomposer skill
        to perform the actual decomposition. The compute instance uses Claude
        Code with OAuth credentials to call the Anthropic API.

        Args:
            goal_id: ID of the goal to decompose
            goal_text: Natural language goal description
            project_context: Project metadata (tech stack, conventions, etc.)
            existing_issues: Current backlog for awareness
            constraints: Optional constraints (max_issues, focus_areas, etc.)
            conversation_comments: All goal comments for full context
            existing_decomposition: Previous decomposition results if any
            supplemental_context: Context for supplemental decomposition
                (trigger, gap_description, triggered_by, pass_number)

        Returns:
            GoalDecompositionResult with structured issues and dependencies

        Raises:
            NoComputeAvailableError: If no compute instances can be spawned
            DecompositionTimeoutError: If decomposition times out
        """
        if not self._initialized:
            await self.initialize()

        # Generate decomposition ID
        decomposition_id = f"decomp-{uuid.uuid4().hex[:12]}"

        logger.info(f"Decomposing goal {goal_id} via compute delegation")

        # Build the task context for the compute instance
        task_context = self._build_task_context(
            goal_id=goal_id,
            goal_text=goal_text,
            decomposition_id=decomposition_id,
            project_context=project_context,
            existing_issues=existing_issues,
            constraints=constraints,
            conversation_comments=conversation_comments,
            existing_decomposition=existing_decomposition,
            supplemental_context=supplemental_context,
        )

        # Infer runtime requirements from the goal text for compute routing
        from services.runtime_inference import infer_runtime_tools
        inferred_tools = infer_runtime_tools(goal_text, goal_text)

        # Enqueue decomposition task to WorkDispatcher (event-driven, no polling)
        await self._spawn_decomposition_compute(
            decomposition_id=decomposition_id,
            task_context=task_context,
            goal_id=goal_id,
            required_tools=inferred_tools,
        )

        # Wait for result from compute instance via asyncio.Event (no polling)
        result = await self._wait_for_result(
            decomposition_id=decomposition_id,
            goal_id=goal_id,
        )

        logger.info(
            f"Decomposed goal {goal_id} into {len(result.issues)} issues "
            f"with confidence {result.confidence:.2f}"
        )

        return result

    async def decompose_and_characterize(
        self,
        goal_id: str,
        goal_text: str,
        project_id: str,
        project_context: Optional[Dict[str, Any]] = None,
        existing_issues: Optional[List[Issue]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        conversation_comments: Optional[List[Dict[str, Any]]] = None,
        existing_decomposition: Optional[Dict[str, Any]] = None,
        supplemental_context: Optional[Dict[str, Any]] = None,
    ) -> tuple[GoalDecompositionResult, Dict[str, CharacterizationResult]]:
        """Decompose a goal and characterize the resulting items before issue creation.

        Follows the spec pipeline: Decomposition -> Characterization -> Planner Backlog.
        Every task passes through characterization before entering the planner's backlog.

        Args:
            goal_id: ID of the goal to decompose
            goal_text: Natural language goal description
            project_id: Project context for characterization
            project_context: Project metadata (tech stack, conventions, etc.)
            existing_issues: Current backlog for awareness
            constraints: Optional constraints (max_issues, focus_areas, etc.)
            conversation_comments: All goal comments for full context
            existing_decomposition: Previous decomposition results if any
            supplemental_context: Context for supplemental decomposition

        Returns:
            Tuple of (GoalDecompositionResult, dict mapping temp_id to CharacterizationResult)
            The characterization dict may be empty if no compute is available.
        """
        # Step 1: Decompose
        decomposition = await self.decompose_goal(
            goal_id=goal_id,
            goal_text=goal_text,
            project_context=project_context,
            existing_issues=existing_issues,
            constraints=constraints,
            conversation_comments=conversation_comments,
            existing_decomposition=existing_decomposition,
            supplemental_context=supplemental_context,
        )

        # Step 2: Characterize decomposed items (before issue creation)
        characterization_map: Dict[str, CharacterizationResult] = {}

        if not decomposition.issues:
            return decomposition, characterization_map

        try:
            from services.characterization_service import get_characterization_service

            char_service = get_characterization_service()

            # Build characterization requests from decomposed issues using temp_ids
            char_items = [
                CharacterizationRequest(
                    item_id=issue.temp_id,
                    project_id=project_id,
                    title=issue.title,
                    description=issue.description,
                    issue_type_hint=issue.issue_type,
                    area_hint=issue.area,
                )
                for issue in decomposition.issues
            ]

            char_response = await char_service.characterize_items(
                project_id=project_id,
                items=char_items,
                source_goal_id=goal_id,
            )

            # Build temp_id -> CharacterizationResult mapping
            for result in char_response.results:
                characterization_map[result.item_id] = result

            logger.info(
                f"Characterized {char_response.completed}/{char_response.total} "
                f"items for goal {goal_id} (before issue creation)"
            )

        except RuntimeError as e:
            # No compute available for characterization — non-fatal
            logger.warning(
                f"Skipping characterization for goal {goal_id}: {e}. "
                "Issues will be created without characterization metadata."
            )
        except Exception as e:
            logger.warning(f"Characterization failed for goal {goal_id}: {e}")

        return decomposition, characterization_map

    def _build_task_context(
        self,
        goal_id: str,
        goal_text: str,
        decomposition_id: str,
        project_context: Optional[Dict[str, Any]] = None,
        existing_issues: Optional[List[Issue]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        conversation_comments: Optional[List[Dict[str, Any]]] = None,
        existing_decomposition: Optional[Dict[str, Any]] = None,
        supplemental_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the task context for the compute instance.

        This creates a prompt that will be passed to the compute instance
        describing what needs to be done.

        Args:
            goal_id: Goal ID
            goal_text: Natural language goal description
            decomposition_id: Assigned decomposition ID
            project_context: Project metadata
            existing_issues: Current backlog
            constraints: Decomposition constraints
            conversation_comments: All goal comments for full context
            existing_decomposition: Previous decomposition results if any
            supplemental_context: Context for supplemental decomposition

        Returns:
            Task context string for compute instance
        """
        # Project context section
        context_section = ""
        if project_context:
            tech_stack = project_context.get("tech_stack", "Not specified")
            conventions = project_context.get("conventions", "Not specified")
            context_section = f"""
## Project Context
Tech Stack: {tech_stack}
Conventions: {conventions}
"""

        # Existing issues section
        issues_section = ""
        if existing_issues:
            issue_summaries = [
                f"- {i.id}: {i.title} ({i.status.value})"
                for i in existing_issues[:20]  # Limit to avoid token overflow
            ]
            issues_section = f"""
## Existing Backlog
{chr(10).join(issue_summaries)}
"""

        # Conversation comments section (full context passthrough)
        comments_section = ""
        if conversation_comments:
            comment_lines = []
            for c in conversation_comments[:50]:  # Limit to avoid token overflow
                by = c.get("created_by", "user")
                content = c.get("content", "")
                status_str = c.get("evaluation_status", "not_evaluated")
                comment_lines.append(f"- [{by}] ({status_str}): {content[:500]}")
            comments_section = f"""
## Conversation History
The following comments have been added to this goal:
{chr(10).join(comment_lines)}
"""

        # Existing decomposition section
        decomp_section = ""
        if existing_decomposition:
            prev_issues = existing_decomposition.get("issues", [])
            prev_reasoning = existing_decomposition.get("reasoning", "")
            if prev_issues:
                decomp_lines = [f"- {i.get('title', 'Untitled')}" for i in prev_issues[:20]]
                decomp_section = f"""
## Previous Decomposition
A prior decomposition exists with {len(prev_issues)} issues:
Reasoning: {prev_reasoning[:500]}
Issues:
{chr(10).join(decomp_lines)}

Consider this context when creating the updated decomposition.
"""

        # Supplemental decomposition context section
        supplemental_section = ""
        if supplemental_context:
            trigger = supplemental_context.get("trigger", "manual")
            pass_number = supplemental_context.get("pass_number", 1)
            gap_desc = supplemental_context.get("gap_description", "")
            extra_context = supplemental_context.get("context", "")
            triggered_by = supplemental_context.get("triggered_by", "")

            supplemental_section = f"""
## Supplemental Decomposition (Pass #{pass_number})
This is a **supplemental decomposition pass**, not an initial decomposition.
- **Trigger:** {trigger}
- **Triggered by:** {triggered_by or 'user'}

IMPORTANT: Only identify NEW issues that are missing from the existing work.
Do NOT duplicate existing issues listed above. Focus on gaps and missing work.
"""
            if gap_desc:
                supplemental_section += f"""
### Gap Description
{gap_desc}
"""
            if extra_context:
                supplemental_section += f"""
### Additional Context
{extra_context}
"""

        # Constraints section
        max_issues = self._config.default_max_issues
        focus_areas = None
        if constraints:
            max_issues = min(
                constraints.get("max_issues", max_issues),
                self._config.max_issues_per_goal,
            )
            focus_areas = constraints.get("focus_areas")

        constraints_section = f"""
## Constraints
Maximum issues: {max_issues}
"""
        if focus_areas:
            constraints_section += f"Focus areas: {', '.join(focus_areas)}\n"

        # Determine task title based on whether this is supplemental
        is_supplemental = supplemental_context is not None
        task_title = "Supplemental Goal Decomposition Task" if is_supplemental else "Goal Decomposition Task"
        task_instruction = (
            "identify ADDITIONAL issues that are missing from the existing work"
            if is_supplemental
            else "decompose a goal into structured issues"
        )

        task_context = f"""# {task_title}

You have been assigned to {task_instruction}.

## Assignment Details
- **Goal ID:** {goal_id}
- **Decomposition ID:** {decomposition_id}

{context_section}

## Goal to Decompose
{goal_text}

{comments_section}

{decomp_section}

{issues_section}

{supplemental_section}

{constraints_section}

## Runtime Requirements
For each issue, infer what runtime tools are needed based on the work description.
Use the `required_tools` field with `runtime:<name>` or `runtime:<name>:<version>` format.

Common mappings:
- React, Vite, npm, Node.js, Express, Next.js, TypeScript → `runtime:node`
- Django, Flask, pip, Python scripts, FastAPI → `runtime:python`
- Go modules, Go binaries, go build → `runtime:go`
- Cargo, Rust, rustc → `runtime:rust`
- Maven, Gradle, Java, Spring → `runtime:java`

Include version when explicitly specified (e.g., "Node 22" → `runtime:node:22`).
If the runtime is ambiguous or unclear, leave `required_tools` empty — the system
will detect capability gaps at execution time.

## Your Task
1. Analyze this goal thoroughly
2. Break it into discrete, implementable issues
3. For each issue, infer required runtime tools from the description
4. Submit results using `claudevn_submit_decomposition` with:
   - decomposition_id: "{decomposition_id}"
   - goal_id: "{goal_id}"
   - issues: [list of issues with temp_ids, titles, descriptions, required_tools, etc.]
   - confidence: your confidence score (0-1)
   - reasoning: explanation of your approach

Follow the guidelines in your goal-decomposer skill for proper issue structure.
"""

        return task_context

    async def _spawn_decomposition_compute(
        self,
        decomposition_id: str,
        task_context: str,
        goal_id: str = "",
        required_tools: list[str] | None = None,
    ) -> None:
        """Enqueue decomposition work to the event-driven WorkDispatcher.

        Registers the completion event and enqueues the task. The dispatcher
        assigns it to the next idle compute without polling.

        Args:
            decomposition_id: Decomposition ID for tracking
            task_context: Task description for the compute instance
            goal_id: Goal ID for context propagation
            required_tools: Inferred runtime tools for compute routing

        Raises:
            NoComputeAvailableError: If WorkDispatcher is not initialized
        """
        try:
            from services.work_dispatcher import get_work_dispatcher, DecompositionTask
            from services.completion_events import create_event

            # Register completion event before enqueuing (so signal() is never missed)
            create_event(decomposition_id)

            # Get skill instructions for the task
            skill_instructions = await self._get_decomposer_skill_instructions()

            dispatcher = get_work_dispatcher()
            dispatcher.enqueue_decomposition(DecompositionTask(
                decomp_id=decomposition_id,
                goal_id=goal_id,
                task_context=task_context,
                skill_instructions=skill_instructions,
                required_tools=required_tools or [],
            ))
            logger.info(
                f"Decomposition {decomposition_id} enqueued to WorkDispatcher "
                f"for goal {goal_id}"
            )

        except RuntimeError as e:
            raise NoComputeAvailableError(
                f"WorkDispatcher not available for decomposition: {e}"
            )
        except Exception as e:
            logger.error(f"Failed to enqueue decomposition task: {e}")
            raise NoComputeAvailableError(
                f"Unable to enqueue decomposition task: {e}"
            )

    async def _get_decomposer_skill_instructions(self) -> str:
        """Get the goal-decomposer skill instructions from marketplace.

        Returns:
            Skill instructions or default if unavailable
        """
        from services.marketplace_client import get_marketplace_client

        try:
            client = get_marketplace_client()
            skill = await client.get_skill("goal-decomposer")

            if skill and skill.get("instructions"):
                return skill["instructions"]

        except Exception as e:
            logger.warning(f"Could not fetch goal-decomposer skill: {e}")

        # Return minimal default instructions
        return """# Goal Decomposer

You are decomposing a goal into structured issues.

1. Analyze the goal in your task description
2. Break it into discrete, implementable issues
3. Use `claudevn_submit_decomposition` MCP tool to submit results

Include: decomposition_id, goal_id, issues array, confidence score, and reasoning.
"""

    async def _wait_for_result(
        self,
        decomposition_id: str,
        goal_id: str,
    ) -> GoalDecompositionResult:
        """Wait for the compute instance to return decomposition results.

        Uses an in-process asyncio.Event registered by _spawn_decomposition_compute
        and signaled by the claudevn_submit_decomposition MCP tool. No polling.

        Args:
            decomposition_id: Decomposition ID to wait for
            goal_id: Goal ID for error messages

        Returns:
            GoalDecompositionResult from compute

        Raises:
            DecompositionTimeoutError: If timeout exceeded
        """
        from services.completion_events import get_event, cleanup as cleanup_event
        from git.redis_client import get_redis

        event = get_event(decomposition_id)
        if event is None:
            raise DecompositionTimeoutError(
                f"No completion event registered for decomposition {decomposition_id}"
            )

        try:
            # Wait for MCP tool to signal completion (no polling)
            await asyncio.wait_for(event.wait(), timeout=self._timeout)
        except asyncio.TimeoutError:
            cleanup_event(decomposition_id)
            raise DecompositionTimeoutError(
                f"Decomposition {decomposition_id} timed out after {self._timeout}s"
            )
        finally:
            cleanup_event(decomposition_id)

        # Fetch result from Redis (written by MCP tool before signaling event)
        redis = await get_redis()
        result_key = f"claudevn:decomposition:{decomposition_id}"
        result_data = await redis.get(result_key)

        if not result_data:
            raise DecompositionTimeoutError(
                f"Decomposition {decomposition_id} signaled but result not found in Redis"
            )

        result = GoalDecompositionResult.model_validate_json(result_data)
        logger.info(
            f"Retrieved decomposition result {decomposition_id}: "
            f"{len(result.issues)} issues"
        )
        return result

    def map_to_issue_models(
        self,
        decomposed_issues: List[DecomposedIssue],
        goal_id: str,
        characterization_results: Optional[Dict[str, CharacterizationResult]] = None,
    ) -> List[Dict[str, Any]]:
        """Map decomposed issues to IssueCreateRequest format.

        Args:
            decomposed_issues: List of DecomposedIssue from decomposition
            goal_id: Parent goal ID
            characterization_results: Optional mapping of temp_id to CharacterizationResult.
                When provided, ontology_tags from characterization are included in
                the issue data for richer classification.

        Returns:
            List of dicts suitable for IssueCreateRequest
        """
        result = []

        for issue in decomposed_issues:
            # Map issue type
            type_map = {
                "feature": IssueType.FEATURE,
                "bug": IssueType.BUG,
                "refactor": IssueType.REFACTOR,
                "test": IssueType.TEST,
                "docs": IssueType.DOCS,
            }
            issue_type = type_map.get(issue.issue_type, IssueType.FEATURE)

            # Map area
            area_map = {
                "api": IssueArea.API,
                "database": IssueArea.DATABASE,
                "frontend": IssueArea.FRONTEND,
                "infra": IssueArea.INFRA,
            }
            area = area_map.get(issue.area, IssueArea.API)

            # Map priority
            priority_map = {
                "P0": IssuePriority.P0,
                "P1": IssuePriority.P1,
                "P2": IssuePriority.P2,
                "P3": IssuePriority.P3,
            }
            priority = priority_map.get(issue.priority, IssuePriority.P2)

            # Combine LLM-inferred tools with keyword-based fallback
            from services.runtime_inference import infer_runtime_tools
            inferred_tools = infer_runtime_tools(issue.title, issue.description)
            combined_tools = list(dict.fromkeys(issue.required_tools + inferred_tools))

            issue_data: Dict[str, Any] = {
                "temp_id": issue.temp_id,
                "title": issue.title,
                "description": issue.description,
                "type": issue_type,
                "area": area,
                "priority": priority,
                "required_skills": issue.required_skills,
                "required_tools": combined_tools,
                "goal_id": goal_id,
                "blocked_by_temp_ids": issue.blocked_by,
                "acceptance_criteria": issue.acceptance_criteria,
            }

            # Include ontology_tags from characterization if available
            if characterization_results:
                char_result = characterization_results.get(issue.temp_id)
                if char_result and char_result.ontology_tags:
                    issue_data["ontology_tags"] = char_result.ontology_tags

            result.append(issue_data)

        return result


# Global service instance
_goal_decomposer_service: Optional[GoalDecomposerService] = None


def get_goal_decomposer_service() -> GoalDecomposerService:
    """Get the global Goal Decomposer service instance."""
    global _goal_decomposer_service
    if _goal_decomposer_service is None:
        _goal_decomposer_service = GoalDecomposerService()
    return _goal_decomposer_service


def set_goal_decomposer_service(service: GoalDecomposerService) -> None:
    """Set the global Goal Decomposer service instance."""
    global _goal_decomposer_service
    _goal_decomposer_service = service
