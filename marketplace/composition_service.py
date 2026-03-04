"""Composition Service - composes skills into agent bundles."""

import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from cachetools import TTLCache

from models import (
    Skill, Agent, ProjectContext, TaskAssignment,
    ComposeRequest, ComposePreviewResponse, ConflictCheckRequest, ConflictCheckResponse,
    AddSkillResult, AgentCacheStats,
    ConflictResolution, ResolveConflictResult
)
from skill_registry import get_skill_registry
from config import get_config
from services.skill_usage_service import get_skill_usage_service

logger = logging.getLogger(__name__)


class CompositionService:
    """Service for composing skills into deployable agent bundles."""

    def __init__(
        self,
        cache_max_size: Optional[int] = None,
        cache_ttl: Optional[int] = None
    ):
        """Initialize the composition service with bounded agent cache.

        Args:
            cache_max_size: Maximum number of agents to cache. Defaults to config value.
            cache_ttl: Time-to-live in seconds for cached agents. Defaults to config value.
        """
        config = get_config()
        self._cache_max_size = cache_max_size or config.agent_cache_max_size
        self._cache_ttl = cache_ttl or config.agent_cache_ttl

        # Bounded TTL cache for composed agents
        self._agents: TTLCache = TTLCache(
            maxsize=self._cache_max_size,
            ttl=self._cache_ttl
        )

        # Cache statistics
        self._evictions = 0
        self._hits = 0
        self._misses = 0

    def resolve_dependencies(self, skill_ids: List[str]) -> List[str]:
        """Resolve skill dependencies and return complete list of skill IDs.

        Recursively adds implied skills based on dependencies declared in skills.
        For example, if 'prod-deployment' depends on 'code-analysis', selecting
        'prod-deployment' will automatically include 'code-analysis'.

        Supports namespace-qualified IDs (e.g., "acme:code-writer"). Both bare
        and namespaced lookups are resolved transparently via get_skill().

        The order is preserved: original skill IDs maintain their order, with
        dependencies appended after the skills that require them.

        Args:
            skill_ids: Initial list of skill IDs selected

        Returns:
            Complete list of resolved skill IDs including all dependencies
            (no duplicates), with original order preserved and dependencies appended
        """
        registry = get_skill_registry()
        seen = set()
        result = []
        to_process = list(skill_ids)

        while to_process:
            skill_id = to_process.pop(0)
            if skill_id in seen:
                continue

            skill = registry.get_skill(skill_id)
            if skill is None:
                continue

            # Use the actual skill ID (may be namespaced) for dedup and result
            resolved_id = skill.id
            if resolved_id in seen:
                continue

            seen.add(skill_id)
            seen.add(resolved_id)
            result.append(resolved_id)

            for dep_id in skill.dependencies:
                if dep_id not in seen:
                    dep_skill = registry.get_skill(dep_id)
                    if dep_skill is not None:
                        to_process.append(dep_skill.id)
                        logger.info(f"Added dependency '{dep_skill.id}' for skill '{resolved_id}'")
                    else:
                        logger.warning(f"Dependency '{dep_id}' not found for skill '{resolved_id}'")

        return result

    def select_skills_for_task(self, task: TaskAssignment) -> List[Skill]:
        """Select appropriate skills based on task requirements.

        Uses tiered matching strategy:
        1. Exact tag matches
        2. Partial/substring tag matches
        3. Token-based fuzzy matches
        4. Default fallback (never returns empty)

        Args:
            task: Task assignment with required capabilities

        Returns:
            List of matching skills, sorted by relevance. Always returns
            at least the default skill to prevent silent failures.
        """
        registry = get_skill_registry()

        if not task.required_capabilities:
            # Return a default set if no capabilities specified
            default_skill = registry.get_skill("code-writer")
            return [default_skill] if default_skill else []

        # Use enhanced search with fallback matching
        selected = registry.search_by_capabilities_with_fallback(
            capabilities=task.required_capabilities,
            default_skill_id="code-writer",
            max_results=5,
        )

        return selected

    def check_conflicts(self, skill_ids: List[str]) -> ConflictCheckResponse:
        """Check for conflicts between skills."""
        registry = get_skill_registry()

        conflicts = []
        warnings = []

        skills = [registry.get_skill(sid) for sid in skill_ids]
        skills = [s for s in skills if s is not None]

        # Check explicit conflicts
        for i, skill in enumerate(skills):
            for conflict_id in skill.conflicts_with:
                if conflict_id in skill_ids:
                    conflicts.append({
                        "skill_a": skill.id,
                        "skill_b": conflict_id,
                        "reason": f"{skill.id} declares conflict with {conflict_id}"
                    })

        # Check for overlapping specialized tools (warning only)
        tool_grants = {}
        for skill in skills:
            for tool_id in skill.specialized_tools:
                if tool_id in tool_grants:
                    warnings.append(
                        f"Tool '{tool_id}' granted by both {tool_grants[tool_id]} and {skill.id}"
                    )
                else:
                    tool_grants[tool_id] = skill.id

        return ConflictCheckResponse(
            has_conflicts=len(conflicts) > 0,
            conflicts=conflicts,
            warnings=warnings
        )

    def add_skill(
        self, existing_skill_ids: List[str], new_skill_id: str, force: bool = False
    ) -> AddSkillResult:
        """Add a skill to a composition with conflict detection.

        This method provides a decision point for handling conflicts. Conflicts
        are advisory - the caller can proceed despite conflicts if intentional
        (e.g., combining writer + reviewer for thorough work).

        Args:
            existing_skill_ids: List of skill IDs already in the composition
            new_skill_id: Skill ID to add
            force: If True, add the skill despite conflicts

        Returns:
            AddSkillResult with:
            - added: Whether the skill was added
            - has_conflicts: Whether conflicts were detected
            - conflicts: List of conflict details
            - warnings: Advisory warnings (e.g., overlapping tools)
            - can_proceed: Always True (decision point, not rejection)
            - message: Human-readable status

        Example:
            result = service.add_skill(["code-writer"], "code-reviewer")
            if result.has_conflicts:
                print(f"Warning: {result.conflicts}")
                # Decision: keep both for thorough review
                result = service.add_skill(["code-writer"], "code-reviewer", force=True)
        """
        registry = get_skill_registry()

        # Validate new skill exists
        new_skill = registry.get_skill(new_skill_id)
        if new_skill is None:
            return AddSkillResult(
                skill_id=new_skill_id,
                skill_name="",
                added=False,
                has_conflicts=False,
                conflicts=[],
                warnings=[],
                can_proceed=False,
                message=f"Skill '{new_skill_id}' not found"
            )

        # Check if skill is already in the composition
        if new_skill_id in existing_skill_ids:
            return AddSkillResult(
                skill_id=new_skill_id,
                skill_name=new_skill.name,
                added=False,
                has_conflicts=False,
                conflicts=[],
                warnings=[],
                can_proceed=True,
                message=f"Skill '{new_skill.name}' is already in the composition"
            )

        # Check for conflicts with existing skills
        conflicts = []
        warnings = []

        existing_skills = [registry.get_skill(sid) for sid in existing_skill_ids]
        existing_skills = [s for s in existing_skills if s is not None]

        # Check explicit conflicts (bidirectional)
        for existing_skill in existing_skills:
            # Check if new skill declares conflict with existing
            if existing_skill.id in new_skill.conflicts_with:
                conflicts.append({
                    "skill": existing_skill.id,
                    "reason": f"{new_skill.name} conflicts with {existing_skill.name}"
                })
            # Check if existing skill declares conflict with new
            if new_skill_id in existing_skill.conflicts_with:
                conflicts.append({
                    "skill": existing_skill.id,
                    "reason": f"{existing_skill.name} conflicts with {new_skill.name}"
                })

        # Check for overlapping specialized tools (warning only)
        existing_tool_grants = {}
        for skill in existing_skills:
            for tool_id in skill.specialized_tools:
                existing_tool_grants[tool_id] = skill.id

        for tool_id in new_skill.specialized_tools:
            if tool_id in existing_tool_grants:
                warnings.append(
                    f"Tool '{tool_id}' is granted by both {existing_tool_grants[tool_id]} and {new_skill.id}"
                )

        has_conflicts = len(conflicts) > 0

        # Determine if we should add the skill
        if has_conflicts and not force:
            return AddSkillResult(
                skill_id=new_skill_id,
                skill_name=new_skill.name,
                added=False,
                has_conflicts=True,
                conflicts=conflicts,
                warnings=warnings,
                can_proceed=True,
                message=f"Conflicts detected. Use force=True to add '{new_skill.name}' anyway."
            )

        # Add the skill (no conflicts or force=True)
        if has_conflicts:
            logger.warning(
                f"Adding skill '{new_skill.name}' despite conflicts: {conflicts}"
            )
            message = f"Skill '{new_skill.name}' added with conflicts (forced)"
        elif warnings:
            message = f"Skill '{new_skill.name}' added with warnings"
        else:
            message = f"Skill '{new_skill.name}' added successfully"

        return AddSkillResult(
            skill_id=new_skill_id,
            skill_name=new_skill.name,
            added=True,
            has_conflicts=has_conflicts,
            conflicts=conflicts,
            warnings=warnings,
            can_proceed=True,
            message=message
        )

    def resolve_conflict(
        self,
        new_skill_id: str,
        existing_skill_ids: List[str],
        conflicting_skill_ids: List[str],
        resolution: ConflictResolution,
        reason: Optional[str] = None
    ) -> ResolveConflictResult:
        """Apply conflict resolution decision.

        This method provides a formal workflow for handling conflicts detected
        by add_skill(). Instead of just using force=True, callers can explicitly
        choose how to handle the conflict with full audit logging.

        Args:
            new_skill_id: Skill ID that was being added
            existing_skill_ids: Current skill IDs in the composition
            conflicting_skill_ids: Skill IDs that conflict with the new skill
            resolution: How to resolve the conflict (KEEP_BOTH, REMOVE_EXISTING, CANCEL)
            reason: Optional user-provided reason for the decision (for audit)

        Returns:
            ResolveConflictResult with:
            - resolution: The applied resolution
            - resulting_skill_ids: Final composition after resolution
            - removed_skill_ids: Any skills that were removed
            - success: Whether resolution was applied
            - message: Human-readable status
            - timestamp: When resolution was applied
            - reason: User-provided reason

        Example:
            result = service.resolve_conflict(
                new_skill_id="code-reviewer",
                existing_skill_ids=["code-writer", "rapid-prototyper"],
                conflicting_skill_ids=["rapid-prototyper"],
                resolution=ConflictResolution.KEEP_BOTH,
                reason="Intentional combination for thorough review"
            )
        """
        registry = get_skill_registry()

        # Validate the new skill exists
        new_skill = registry.get_skill(new_skill_id)
        if new_skill is None:
            return ResolveConflictResult(
                resolution=resolution,
                new_skill_id=new_skill_id,
                new_skill_name="",
                resulting_skill_ids=existing_skill_ids,
                removed_skill_ids=[],
                success=False,
                message=f"Skill '{new_skill_id}' not found",
                reason=reason
            )

        # Process based on resolution type
        if resolution == ConflictResolution.CANCEL:
            # Cancel: return existing composition unchanged
            logger.info(
                f"Conflict resolution CANCEL: skill '{new_skill.name}' not added "
                f"(reason: {reason or 'not provided'})"
            )
            return ResolveConflictResult(
                resolution=resolution,
                new_skill_id=new_skill_id,
                new_skill_name=new_skill.name,
                resulting_skill_ids=list(existing_skill_ids),
                removed_skill_ids=[],
                success=True,
                message=f"Addition of '{new_skill.name}' cancelled",
                reason=reason
            )

        elif resolution == ConflictResolution.KEEP_BOTH:
            # Keep both: add new skill to existing composition
            resulting_ids = list(existing_skill_ids)
            if new_skill_id not in resulting_ids:
                resulting_ids.append(new_skill_id)

            reason_suffix = f" (reason: {reason})" if reason else ""
            logger.info(
                f"Conflict resolution KEEP_BOTH: added skill '{new_skill.name}' "
                f"despite conflicts with {conflicting_skill_ids}{reason_suffix}"
            )
            return ResolveConflictResult(
                resolution=resolution,
                new_skill_id=new_skill_id,
                new_skill_name=new_skill.name,
                resulting_skill_ids=resulting_ids,
                removed_skill_ids=[],
                success=True,
                message=f"Kept both skills despite conflict{reason_suffix}",
                reason=reason
            )

        elif resolution == ConflictResolution.REMOVE_EXISTING:
            # Remove existing: remove conflicting skills, add new skill
            removed_ids = []
            resulting_ids = []

            for skill_id in existing_skill_ids:
                if skill_id in conflicting_skill_ids:
                    removed_ids.append(skill_id)
                else:
                    resulting_ids.append(skill_id)

            # Add the new skill
            if new_skill_id not in resulting_ids:
                resulting_ids.append(new_skill_id)

            reason_suffix = f" (reason: {reason})" if reason else ""
            logger.info(
                f"Conflict resolution REMOVE_EXISTING: removed {removed_ids}, "
                f"added skill '{new_skill.name}'{reason_suffix}"
            )
            return ResolveConflictResult(
                resolution=resolution,
                new_skill_id=new_skill_id,
                new_skill_name=new_skill.name,
                resulting_skill_ids=resulting_ids,
                removed_skill_ids=removed_ids,
                success=True,
                message=f"Removed {removed_ids}, added '{new_skill.name}'{reason_suffix}",
                reason=reason
            )

        else:
            # Unknown resolution type
            return ResolveConflictResult(
                resolution=resolution,
                new_skill_id=new_skill_id,
                new_skill_name=new_skill.name,
                resulting_skill_ids=existing_skill_ids,
                removed_skill_ids=[],
                success=False,
                message=f"Unknown resolution type: {resolution}",
                reason=reason
            )

    def merge_instructions(self, skills: List[Skill], context: Optional[ProjectContext] = None) -> str:
        """Merge skill instructions into a coherent CLAUDE.md document."""
        sections = []

        # Header
        skill_names = ", ".join(s.name for s in skills)
        sections.append(f"# Agent Configuration\n")
        sections.append(f"**Active Skills:** {skill_names}\n")

        # Project context (if provided)
        if context:
            sections.append("\n## Project Context\n")
            if context.conventions:
                sections.append(f"### Conventions\n{context.conventions}\n")
            if context.tech_stack:
                sections.append(f"### Tech Stack\n- " + "\n- ".join(context.tech_stack) + "\n")
            if context.domain_context:
                sections.append(f"### Domain\n{context.domain_context}\n")
            if context.custom_rules:
                sections.append(f"### Rules\n- " + "\n- ".join(context.custom_rules) + "\n")

        # Skill instructions
        sections.append("\n## Skill Instructions\n")
        for skill in skills:
            sections.append(f"\n### {skill.name}\n")
            sections.append(skill.instructions)
            sections.append("\n")

        # Aggregated constraints
        all_constraints = []
        for skill in skills:
            all_constraints.extend(skill.constraints)

        if all_constraints:
            sections.append("\n## Constraints\n")
            for constraint in all_constraints:
                sections.append(f"- {constraint}\n")

        return "\n".join(sections)

    def aggregate_tools(self, skills: List[Skill]) -> List[str]:
        """Aggregate tools from all skills (global + specialized)."""
        registry = get_skill_registry()

        # Start with global tools
        tools = set(registry.get_global_tools())

        # Add specialized tools from selected skills
        for skill in skills:
            tools.update(skill.specialized_tools)

        return sorted(list(tools))

    def compose_skills(
        self, skill_ids: List[str], context: Optional[ProjectContext] = None,
        resolve_deps: bool = True
    ) -> str:
        """Compose skills into merged CLAUDE.md via concatenation.

        This is a convenience method for direct skill composition without
        creating a full Agent object. Use this when you only need the
        merged instructions string.

        Args:
            skill_ids: List of skill IDs to compose
            context: Optional project context to inject
            resolve_deps: Whether to resolve dependencies (default True)

        Returns:
            Merged CLAUDE.md string with:
            - Project context header (if provided)
            - Concatenated skill instructions with section headers
            - Aggregated constraints from all skills

        Raises:
            ValueError: If no valid skills found for the given IDs
        """
        registry = get_skill_registry()

        # Resolve dependencies if enabled
        resolved_ids = self.resolve_dependencies(skill_ids) if resolve_deps else skill_ids

        # Resolve skill IDs to skill objects
        skills = []
        for skill_id in resolved_ids:
            skill = registry.get_skill(skill_id)
            if skill is not None:
                skills.append(skill)

        if not skills:
            raise ValueError(f"No valid skills found for IDs: {skill_ids}")

        # Check for conflicts (advisory only - log warning but proceed)
        conflict_check = self.check_conflicts(skill_ids)
        if conflict_check.has_conflicts:
            logger.warning(f"Composing skills with conflicts: {conflict_check.conflicts}")
        if conflict_check.warnings:
            for warning in conflict_check.warnings:
                logger.warning(f"Skill composition warning: {warning}")

        # Merge instructions using existing method
        return self.merge_instructions(skills, context)

    def aggregate_tools_for_skills(self, skill_ids: List[str], resolve_deps: bool = True) -> List[str]:
        """Collect all tools granted by skills.

        This is a convenience method to get tools without creating a full Agent.

        Args:
            skill_ids: List of skill IDs to aggregate tools from
            resolve_deps: Whether to resolve dependencies (default True)

        Returns:
            List of all tool IDs (global + specialized from all skills)
        """
        registry = get_skill_registry()

        # Resolve dependencies if enabled
        resolved_ids = self.resolve_dependencies(skill_ids) if resolve_deps else skill_ids

        # Start with global tools
        tools = set(registry.get_global_tools())

        # Add specialized tools from each skill
        for skill_id in resolved_ids:
            skill = registry.get_skill(skill_id)
            if skill is not None:
                tools.update(skill.specialized_tools)

        return sorted(list(tools))

    async def compose(self, request: ComposeRequest) -> Agent:
        """Compose an agent bundle from skills for a task."""
        registry = get_skill_registry()

        # Get skills - either explicit or auto-selected
        if request.skill_ids:
            # Resolve dependencies for explicit skill IDs
            resolved_ids = self.resolve_dependencies(request.skill_ids)
            skills = [registry.get_skill(sid) for sid in resolved_ids]
            skills = [s for s in skills if s is not None]
        else:
            # Auto-select and resolve dependencies
            selected_skills = self.select_skills_for_task(request.task)
            selected_ids = [s.id for s in selected_skills]
            resolved_ids = self.resolve_dependencies(selected_ids)
            skills = [registry.get_skill(sid) for sid in resolved_ids]
            skills = [s for s in skills if s is not None]

        if not skills:
            raise ValueError("No skills available for this task")

        # Check for conflicts (advisory)
        skill_ids = [s.id for s in skills]
        conflict_check = self.check_conflicts(skill_ids)
        if conflict_check.has_conflicts:
            logger.warning(f"Composing agent with conflicts: {conflict_check.conflicts}")

        # Merge instructions
        merged = self.merge_instructions(skills, request.context)

        # Aggregate tools
        tools = self.aggregate_tools(skills)

        # Create agent
        agent = Agent(
            id=f"agent-{uuid.uuid4().hex[:8]}",
            skills=skills,
            merged_instructions=merged,
            tools=tools,
            context=request.context,
            task=request.task,
            created_at=datetime.now(timezone.utc)
        )

        # Track skill usage for analytics
        usage_service = get_skill_usage_service()
        usage_service.record_usage(skill_ids)

        # Store agent for later authorization lookups
        # Track evictions when cache is at capacity
        size_before = len(self._agents)
        at_capacity = size_before >= self._cache_max_size
        self._agents[agent.id] = agent
        size_after = len(self._agents)

        # If we were at capacity and size didn't increase, an eviction occurred
        if at_capacity and size_after <= size_before:
            self._evictions += 1
            logger.debug(f"Cache eviction occurred, total evictions: {self._evictions}")

        logger.info(f"Composed agent {agent.id} with {len(skills)} skills (cache size: {size_after}/{self._cache_max_size})")
        return agent

    async def compose_preview(self, request: ComposeRequest) -> ComposePreviewResponse:
        """Preview agent composition without persisting.

        Performs the same composition logic as compose() but does not:
        - Generate an agent ID
        - Store the agent in the cache
        - Affect cache statistics

        This allows users to validate skill combinations before committing
        to a full composition.

        Args:
            request: Composition request with task and optional skill IDs

        Returns:
            ComposePreviewResponse with:
            - preview: True (indicates this is a preview)
            - merged_instructions: What the final CLAUDE.md would look like
            - tools: All tools that would be granted
            - skills: Skills that would be included (with dependencies resolved)
            - conflict_warnings: Any conflicts or warnings detected

        Raises:
            ValueError: If no skills available for the task
        """
        registry = get_skill_registry()

        # Get skills - either explicit or auto-selected (same logic as compose)
        if request.skill_ids:
            resolved_ids = self.resolve_dependencies(request.skill_ids)
            skills = [registry.get_skill(sid) for sid in resolved_ids]
            skills = [s for s in skills if s is not None]
        else:
            selected_skills = self.select_skills_for_task(request.task)
            selected_ids = [s.id for s in selected_skills]
            resolved_ids = self.resolve_dependencies(selected_ids)
            skills = [registry.get_skill(sid) for sid in resolved_ids]
            skills = [s for s in skills if s is not None]

        if not skills:
            raise ValueError("No skills available for this task")

        # Check for conflicts
        skill_ids = [s.id for s in skills]
        conflict_check = self.check_conflicts(skill_ids)

        # Merge instructions
        merged = self.merge_instructions(skills, request.context)

        # Aggregate tools
        tools = self.aggregate_tools(skills)

        # Return preview without persisting
        return ComposePreviewResponse(
            preview=True,
            merged_instructions=merged,
            tools=tools,
            skills=skills,
            conflict_warnings=conflict_check
        )

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get a previously composed agent by ID.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent if found and not expired, None otherwise
        """
        agent = self._agents.get(agent_id)
        if agent is not None:
            self._hits += 1
        else:
            self._misses += 1
        return agent

    def list_agents(self) -> List[Agent]:
        """List all composed agents currently in cache.

        Note: This only returns non-expired agents. Agents may be evicted
        due to TTL expiration or cache size limits.

        Returns:
            List of all agents currently in the cache
        """
        return list(self._agents.values())

    def get_cache_stats(self) -> AgentCacheStats:
        """Get statistics about the agent cache.

        Returns:
            AgentCacheStats with current cache metrics
        """
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

        # Calculate evictions: agents that were removed due to TTL or capacity
        # TTLCache doesn't track evictions directly, so we count when currsize < maxsize
        # after items have been added. For simplicity, we track manually in compose().
        return AgentCacheStats(
            size=len(self._agents),
            max_size=self._cache_max_size,
            ttl_seconds=self._cache_ttl,
            evictions=self._evictions,
            hits=self._hits,
            misses=self._misses,
            hit_rate=hit_rate
        )

    def clear_cache(self) -> int:
        """Clear all agents from the cache.

        Returns:
            Number of agents that were cleared
        """
        count = len(self._agents)
        self._agents.clear()
        logger.info(f"Cleared {count} agents from cache")
        return count


# Global instance
_composition_service: Optional[CompositionService] = None


def get_composition_service() -> CompositionService:
    """Get the global composition service instance."""
    global _composition_service
    if _composition_service is None:
        _composition_service = CompositionService()
    return _composition_service
