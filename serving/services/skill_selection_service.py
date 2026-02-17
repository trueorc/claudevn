"""Skill Selection Service for selecting best-fit skills for work items.

This service implements the skill selection algorithm that matches
work requirements to available skill capabilities.
"""

import logging
from typing import Dict, List, Optional, Tuple

from models.work_map import WorkItem
from services.marketplace_client import get_marketplace_client

logger = logging.getLogger(__name__)


class SkillSelectionService:
    """Service for selecting skills based on work requirements.

    Implements capability-based matching to find the best skills
    for a given work item.
    """

    def __init__(self):
        """Initialize the skill selection service."""
        self.marketplace_client = get_marketplace_client()

    async def select_skills(self, work: WorkItem) -> List[str]:
        """Select the best skills for a work item.

        Args:
            work: Work item to select skills for

        Returns:
            List of skill IDs matching the work requirements
        """
        required_caps = work.required_capabilities

        if not required_caps:
            # No specific requirements, return general skill
            logger.info(f"No required capabilities for work {work.work_id}, using general skill")
            return ["general"]

        try:
            # Get available skills from marketplace
            skills_response = await self.marketplace_client.list_skills()
            skills = skills_response.get("skills", [])

            if not skills:
                logger.warning("No skills available in marketplace, using general skill")
                return ["general"]

            # Find candidates with matching capabilities
            candidates = []
            for skill in skills:
                skill_id = skill.get("skill_id")
                capabilities = skill.get("capabilities", [])

                match_score = self.calculate_match(capabilities, required_caps)
                if match_score > 0:
                    candidates.append((skill_id, match_score))
                    logger.debug(f"Skill {skill_id} scored {match_score} for work {work.work_id}")

            # Sort by match score (descending)
            candidates.sort(key=lambda x: x[1], reverse=True)

            if candidates:
                # Return top matching skills (those with score > 0)
                selected_skills = [skill_id for skill_id, score in candidates if score > 0]
                logger.info(
                    f"Selected skills {selected_skills} for work {work.work_id} "
                    f"(required: {required_caps})"
                )
                return selected_skills
            else:
                # No matches found, fall back to general
                logger.info(
                    f"No skill matches for work {work.work_id} "
                    f"(required: {required_caps}), using general skill"
                )
                return ["general"]

        except Exception as e:
            logger.error(f"Error selecting skills for work {work.work_id}: {e}")
            # On error, fall back to general skill
            return ["general"]

    def calculate_match(
        self,
        skill_caps: List[str],
        required_caps: List[str]
    ) -> float:
        """Calculate capability match score (0.0 to 1.0).

        Args:
            skill_caps: Capabilities the skill has
            required_caps: Capabilities required by the work

        Returns:
            Match score from 0.0 (no match) to 1.0 (perfect match)
        """
        if not required_caps:
            return 0.5  # Neutral score for unspecified requirements

        if not skill_caps:
            return 0.0  # No capabilities means no match

        # Calculate intersection
        matched = set(skill_caps) & set(required_caps)
        score = len(matched) / len(required_caps)

        return score


# Global instance
_skill_selection_service: Optional[SkillSelectionService] = None


def get_skill_selection_service() -> SkillSelectionService:
    """Get the global skill selection service instance."""
    global _skill_selection_service
    if _skill_selection_service is None:
        _skill_selection_service = SkillSelectionService()
    return _skill_selection_service


def set_skill_selection_service(service: SkillSelectionService) -> None:
    """Set the global skill selection service instance."""
    global _skill_selection_service
    _skill_selection_service = service
