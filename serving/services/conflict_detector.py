"""Conflict detection for multi-user directives."""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Keywords that indicate priority-related directives
PRIORITY_KEYWORDS = {'prioritize', 'deprioritize', 'focus', 'defer', 'urgent', 'critical', 'deprio'}
# Window for considering recent directives (1 hour)
CONFLICT_WINDOW_SECONDS = 3600


class RecentDirective:
    """Tracks a recently applied directive for conflict detection."""

    def __init__(self, user_id: str, display_name: str, text: str, project_id: str, timestamp: float):
        self.user_id = user_id
        self.display_name = display_name
        self.text = text
        self.project_id = project_id
        self.timestamp = timestamp


class ConflictDetector:
    """Detects potential conflicts between directives from different users."""

    def __init__(self):
        # In-memory ring buffer of recent directives per project
        self._recent: dict[str, list[RecentDirective]] = {}
        self._max_per_project = 20

    def record_directive(self, user_id: str, display_name: str, text: str, project_id: str):
        """Record a directive that was just submitted."""
        now = time.time()
        entry = RecentDirective(user_id, display_name, text, project_id, now)

        if project_id not in self._recent:
            self._recent[project_id] = []

        self._recent[project_id].append(entry)

        # Prune old entries and enforce ring buffer size
        cutoff = now - CONFLICT_WINDOW_SECONDS
        self._recent[project_id] = [
            d for d in self._recent[project_id]
            if d.timestamp > cutoff
        ][-self._max_per_project:]

    def check_conflicts(self, user_id: str, text: str, project_id: str) -> Optional[dict]:
        """Check if a new directive conflicts with recent ones from other users.

        Returns a conflict dict if detected, None otherwise.
        """
        if project_id not in self._recent:
            return None

        now = time.time()
        cutoff = now - CONFLICT_WINDOW_SECONDS
        text_lower = text.lower()

        # Only check directives with priority-related language
        new_has_priority = any(kw in text_lower for kw in PRIORITY_KEYWORDS)
        if not new_has_priority:
            return None

        for recent in self._recent[project_id]:
            if recent.user_id == user_id:
                continue
            if recent.timestamp < cutoff:
                continue

            recent_lower = recent.text.lower()
            recent_has_priority = any(kw in recent_lower for kw in PRIORITY_KEYWORDS)

            if recent_has_priority:
                # Check for contradiction: one says prioritize, other says deprioritize
                new_up = any(kw in text_lower for kw in {'prioritize', 'focus', 'urgent', 'critical'})
                new_down = any(kw in text_lower for kw in {'deprioritize', 'defer', 'deprio'})
                old_up = any(kw in recent_lower for kw in {'prioritize', 'focus', 'urgent', 'critical'})
                old_down = any(kw in recent_lower for kw in {'deprioritize', 'defer', 'deprio'})

                if (new_up and old_down) or (new_down and old_up):
                    # Find overlapping topic words (excluding stop words and priority keywords)
                    stop_words = {'the', 'a', 'an', 'on', 'for', 'to', 'and', 'or', 'in', 'of'}
                    new_words = set(text_lower.split())
                    old_words = set(recent_lower.split())
                    overlap = new_words & old_words - PRIORITY_KEYWORDS - stop_words

                    if len(overlap) >= 1:
                        return {
                            'type': 'priority_contradiction',
                            'other_user': recent.display_name,
                            'other_user_id': recent.user_id,
                            'other_text': recent.text,
                            'overlap_topics': list(overlap)[:5],
                        }

        return None


# Singleton
_detector: Optional[ConflictDetector] = None


def get_conflict_detector() -> ConflictDetector:
    global _detector
    if _detector is None:
        _detector = ConflictDetector()
    return _detector
