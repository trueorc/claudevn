"""Work Context Enrichment Service.

Enriches work item context before compute assignment with:
- Parent goal description and reasoning
- Dependency context (what this work depends on, what it blocks)
- Sibling work items in the same goal (for awareness)
- Project conventions and tech stack info

This provides compute instances with broader system awareness so they
can make better technical decisions and avoid conflicts.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WorkContextEnrichmentService:
    """Enriches work item context before dispatch to compute instances.

    Pulls relevant information from goals, issues, and project metadata
    to give compute instances broader awareness of the work they're doing.
    """

    async def enrich(
        self,
        work_context: Dict[str, Any],
        work_id: str,
        project_id: str,
    ) -> Dict[str, Any]:
        """Enrich a work item's context dict with additional information.

        Args:
            work_context: The existing context dict from WorkItem.context
            work_id: Work item ID for lookups
            project_id: Project ID for project-level context

        Returns:
            Enriched context dict (original dict is not mutated)
        """
        enriched = dict(work_context)

        # Enrich with goal context
        goal_context = await self._get_goal_context(enriched)
        if goal_context:
            enriched["goal_context"] = goal_context

        # Enrich with dependency context
        dep_context = await self._get_dependency_context(work_id)
        if dep_context:
            enriched["dependency_context"] = dep_context

        # Enrich with sibling issue context
        sibling_context = await self._get_sibling_context(enriched)
        if sibling_context:
            enriched["sibling_issues"] = sibling_context

        # Enrich with project metadata
        project_context = await self._get_project_context(project_id)
        if project_context:
            enriched["project_context"] = project_context

        return enriched

    async def _get_goal_context(self, work_context: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Fetch parent goal description and intent."""
        goal_id = work_context.get("goal_id")
        if not goal_id:
            return None

        try:
            from services.goal_service import get_goal_service
            goal_service = get_goal_service()
            goal = await goal_service.get_goal(goal_id)
            if not goal:
                return None

            result: Dict[str, str] = {
                "goal_title": goal.title,
                "goal_description": goal.description[:1000] if goal.description else "",
            }

            # Include intent if available
            if hasattr(goal, "intent_type") and goal.intent_type:
                result["goal_intent"] = goal.intent_type.value

            return result

        except Exception as e:
            logger.debug(f"Could not fetch goal context for {goal_id}: {e}")
            return None

    async def _get_dependency_context(self, work_id: str) -> Optional[Dict[str, Any]]:
        """Fetch information about work dependencies (what this depends on / blocks)."""
        try:
            from services.work_map_service import get_work_map_service
            wm = get_work_map_service()

            work = await wm.get_work(work_id)
            if not work:
                return None

            dep_info: Dict[str, Any] = {}

            # What this work depends on
            if work.depends_on:
                depends_on_summaries = []
                for dep_id in work.depends_on[:5]:  # Limit to avoid bloat
                    dep_work = await wm.get_work(dep_id)
                    if dep_work:
                        depends_on_summaries.append({
                            "work_id": dep_id,
                            "title": dep_work.title,
                            "status": dep_work.status.value,
                        })
                if depends_on_summaries:
                    dep_info["depends_on"] = depends_on_summaries

            # What this work blocks
            if work.blocks:
                blocks_summaries = []
                for block_id in work.blocks[:5]:
                    blocked_work = await wm.get_work(block_id)
                    if blocked_work:
                        blocks_summaries.append({
                            "work_id": block_id,
                            "title": blocked_work.title,
                        })
                if blocks_summaries:
                    dep_info["blocks"] = blocks_summaries

            return dep_info if dep_info else None

        except Exception as e:
            logger.debug(f"Could not fetch dependency context for {work_id}: {e}")
            return None

    async def _get_sibling_context(self, work_context: Dict[str, Any]) -> Optional[List[Dict[str, str]]]:
        """Fetch sibling issues from the same goal for awareness."""
        goal_id = work_context.get("goal_id")
        issue_id = work_context.get("issue_id")
        if not goal_id:
            return None

        try:
            from services.issue_service import get_issue_service
            issue_service = get_issue_service()
            issues = await issue_service.list_issues(goal_id=goal_id)

            if not issues:
                return None

            siblings = []
            for issue in issues[:10]:  # Limit to avoid token bloat
                if issue.issue_id == issue_id:
                    continue  # Skip self
                siblings.append({
                    "issue_id": issue.issue_id,
                    "title": issue.title,
                    "status": issue.status.value,
                    "area": issue.area.value if hasattr(issue, "area") and issue.area else "",
                })

            return siblings if siblings else None

        except Exception as e:
            logger.debug(f"Could not fetch sibling context for goal {goal_id}: {e}")
            return None

    async def _get_project_context(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Fetch project-level metadata (tech stack, conventions)."""
        try:
            from services.project_service import get_project_service
            project_service = get_project_service()
            project = await project_service.get_project(project_id)
            if not project:
                return None

            result: Dict[str, Any] = {}

            if hasattr(project, "tech_stack") and project.tech_stack:
                result["tech_stack"] = project.tech_stack
            if hasattr(project, "conventions") and project.conventions:
                result["conventions"] = project.conventions
            if hasattr(project, "description") and project.description:
                result["project_description"] = project.description[:500]

            return result if result else None

        except Exception as e:
            logger.debug(f"Could not fetch project context for {project_id}: {e}")
            return None


# Module-level singleton
_service: Optional[WorkContextEnrichmentService] = None


def get_work_context_enrichment_service() -> WorkContextEnrichmentService:
    """Get the singleton WorkContextEnrichmentService."""
    global _service
    if _service is None:
        _service = WorkContextEnrichmentService()
    return _service
