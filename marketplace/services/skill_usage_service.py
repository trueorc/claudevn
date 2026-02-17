"""Skill usage tracking service.

Tracks how many times each skill is used during agent composition,
providing analytics for marketplace optimization.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class SkillUsageService:
    """Tracks skill usage during agent composition.

    Updates the skill's usage_count and last_used_at fields directly
    on the in-memory Skill objects in the registry.
    """

    def __init__(self):
        self._total_compositions = 0

    def record_usage(self, skill_ids: list[str]) -> None:
        """Record that skills were used in a composition.

        Args:
            skill_ids: List of skill IDs that were composed into an agent
        """
        from skill_registry import get_skill_registry

        registry = get_skill_registry()
        now = datetime.now(timezone.utc)

        for skill_id in skill_ids:
            skill = registry.get_skill(skill_id)
            if skill is not None:
                skill.usage_count += 1
                skill.last_used_at = now
                logger.debug(
                    f"Recorded usage for skill '{skill_id}': "
                    f"count={skill.usage_count}"
                )

        self._total_compositions += 1

    def get_analytics(self) -> dict:
        """Get skill usage analytics.

        Returns:
            Dictionary with most_used, never_used, total_compositions,
            and total_skills.
        """
        from skill_registry import get_skill_registry

        registry = get_skill_registry()
        skills = registry.list_skills()

        most_used = sorted(
            [s for s in skills if s.usage_count > 0],
            key=lambda s: s.usage_count,
            reverse=True,
        )[:10]

        never_used = [s for s in skills if s.usage_count == 0]

        total_compositions = sum(s.usage_count for s in skills)

        return {
            "most_used": [
                {
                    "skill_id": s.id,
                    "skill_name": s.name,
                    "usage_count": s.usage_count,
                    "last_used_at": s.last_used_at,
                }
                for s in most_used
            ],
            "never_used": [
                {
                    "skill_id": s.id,
                    "skill_name": s.name,
                    "usage_count": 0,
                    "last_used_at": None,
                }
                for s in never_used
            ],
            "total_compositions": total_compositions,
            "total_skills": len(skills),
        }


# Module-level singleton
_usage_service: Optional[SkillUsageService] = None


def get_skill_usage_service() -> SkillUsageService:
    """Get the global skill usage service instance."""
    global _usage_service
    if _usage_service is None:
        _usage_service = SkillUsageService()
    return _usage_service
