"""Goal Intent Service for parsing and tracking strategic intent.

Analyzes goal text and conversation comments to extract intent signals,
track intent shifts over time, and detect conflicts between goals.

Intent types:
- expansion: Building new features/capabilities
- consolidation: Quality, stability, testing focus
- targeted_investment: Focused capability investment
- quality_focused: Deep quality improvement

Reference: docs/work_management_framework.md - Section 3 (Goal as Intent)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from models.work_map import (
    Goal,
    GoalConflict,
    GoalIntentType,
    IntentSignal,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Intent Detection Keywords
# =============================================================================

# Keywords map to intent types. Shared with planner_profile_service but
# authoritative here for intent parsing.
INTENT_KEYWORDS: Dict[GoalIntentType, List[str]] = {
    GoalIntentType.EXPANSION: [
        "add", "new", "create", "build", "implement", "introduce", "expand",
        "develop", "launch", "extend", "grow", "feature", "capability",
    ],
    GoalIntentType.CONSOLIDATION: [
        "harden", "stabilize", "fix", "secure", "reliability", "robust",
        "strengthen", "maintain", "sustain", "consolidate",
    ],
    GoalIntentType.TARGETED_INVESTMENT: [
        "focus", "prioritize", "invest", "concentrate", "target", "specific",
        "particular", "dedicated", "emphasis", "specialize",
    ],
    GoalIntentType.QUALITY_FOCUSED: [
        "test", "validate", "quality", "coverage", "regression", "bug",
        "improve", "refactor", "clean", "polish", "performance",
    ],
}

# Intent pairs that create tension when coexisting
CONFLICTING_INTENTS: List[Tuple[GoalIntentType, GoalIntentType, str]] = [
    (
        GoalIntentType.EXPANSION,
        GoalIntentType.CONSOLIDATION,
        "Expansion wants new features while consolidation wants stability",
    ),
    (
        GoalIntentType.EXPANSION,
        GoalIntentType.QUALITY_FOCUSED,
        "Expansion prioritizes building while quality focus prioritizes testing/polish",
    ),
]


class GoalIntentService:
    """Service for parsing and managing goal intent signals.

    Provides:
    - Intent detection from goal text and comments
    - Intent strength calculation
    - Multi-goal conflict detection
    - Intent shift tracking when comments change direction
    """

    def parse_intent(self, text: str, source: str = "goal_text",
                     source_id: Optional[str] = None) -> List[IntentSignal]:
        """Parse text to extract intent signals.

        Analyzes text for keyword patterns and returns all detected
        intent signals with their relative strengths.

        Args:
            text: Text to analyze (goal title+description or comment content)
            source: Source type ("goal_text", "comment", "manual")
            source_id: Optional source identifier (e.g., comment_id)

        Returns:
            List of IntentSignal objects, sorted by strength descending
        """
        text_lower = text.lower()
        signals: List[IntentSignal] = []

        for intent_type, keywords in INTENT_KEYWORDS.items():
            matched = [kw for kw in keywords if kw in text_lower]
            if matched:
                # Strength based on proportion of keywords matched
                strength = min(1.0, len(matched) / max(3.0, len(keywords) * 0.4))
                signals.append(IntentSignal(
                    intent_type=intent_type,
                    strength=round(strength, 3),
                    detected_from=source,
                    source_id=source_id,
                    keywords_matched=matched,
                ))

        # Sort by strength descending
        signals.sort(key=lambda s: s.strength, reverse=True)
        return signals

    def classify_goal(self, goal: Goal) -> Tuple[Optional[GoalIntentType], float, List[IntentSignal]]:
        """Classify a goal's intent from its text.

        Parses goal title and description to determine primary intent,
        overall strength, and all detected signals.

        Args:
            goal: Goal to classify

        Returns:
            Tuple of (primary_intent, intent_strength, all_signals)
        """
        text = f"{goal.title} {goal.description}"
        signals = self.parse_intent(text, source="goal_text")

        if not signals:
            return None, 0.0, []

        primary = signals[0].intent_type
        strength = signals[0].strength
        return primary, strength, signals

    def update_goal_intent(self, goal: Goal) -> Goal:
        """Update a goal's intent classification in-place.

        Parses the goal text, sets intent_signals, primary_intent,
        and intent_strength on the goal model.

        Args:
            goal: Goal to update (modified in-place)

        Returns:
            The updated goal
        """
        primary, strength, signals = self.classify_goal(goal)
        goal.intent_signals = signals
        goal.primary_intent = primary
        goal.intent_strength = strength
        goal.updated_at = datetime.now(timezone.utc)
        return goal

    def apply_comment_intent(
        self,
        goal: Goal,
        comment_text: str,
        comment_id: str,
    ) -> Tuple[bool, List[IntentSignal]]:
        """Analyze a comment for intent shift signals.

        If the comment introduces new intent signals, merges them with
        the goal's existing signals. Returns whether the intent shifted.

        Args:
            goal: Goal to potentially update
            comment_text: Text of the new comment
            comment_id: Comment identifier

        Returns:
            Tuple of (intent_shifted, new_signals)
        """
        new_signals = self.parse_intent(
            comment_text, source="comment", source_id=comment_id
        )

        if not new_signals:
            return False, []

        old_primary = goal.primary_intent

        # Add new signals to the goal
        goal.intent_signals.extend(new_signals)

        # Recalculate primary intent from all signals
        self._recalculate_primary_intent(goal)

        intent_shifted = goal.primary_intent != old_primary
        if intent_shifted:
            logger.info(
                f"Intent shifted for goal {goal.goal_id}: "
                f"{old_primary} -> {goal.primary_intent}"
            )

        return intent_shifted, new_signals

    def _recalculate_primary_intent(self, goal: Goal) -> None:
        """Recalculate primary intent from all signals with recency weighting.

        More recent signals get a recency boost. The strongest combined
        signal becomes the primary intent.
        """
        if not goal.intent_signals:
            goal.primary_intent = None
            goal.intent_strength = 0.0
            return

        # Aggregate strengths per intent type with recency weighting
        now = datetime.now(timezone.utc)
        intent_scores: Dict[GoalIntentType, float] = {}

        for signal in goal.intent_signals:
            age_hours = max(0.0, (now - signal.detected_at).total_seconds() / 3600)
            # Recency decay: signals lose 10% per hour, minimum 0.3x
            recency_factor = max(0.3, 1.0 - (age_hours * 0.1))
            weighted_strength = signal.strength * recency_factor

            if signal.intent_type in intent_scores:
                # Use max rather than sum to avoid signal flooding
                intent_scores[signal.intent_type] = max(
                    intent_scores[signal.intent_type], weighted_strength
                )
            else:
                intent_scores[signal.intent_type] = weighted_strength

        if not intent_scores:
            goal.primary_intent = None
            goal.intent_strength = 0.0
            return

        # Find the strongest intent
        primary = max(intent_scores, key=intent_scores.get)
        goal.primary_intent = primary
        goal.intent_strength = round(min(1.0, intent_scores[primary]), 3)

    def detect_conflicts(
        self,
        goals: List[Goal],
    ) -> List[GoalConflict]:
        """Detect tensions between active goals based on their intents.

        Checks pairs of goals for conflicting intent types and generates
        conflict objects with severity proportional to both goals' strengths.
        Severity also factors in recency — conflicts between two recent,
        strong goals are rated higher.

        Conflicts with severity >= 0.7 are marked as irreconcilable,
        meaning automatic reconciliation may produce poor results and
        user intervention (setting reconciliation_weight) is recommended.

        Args:
            goals: List of active goals to check

        Returns:
            List of GoalConflict objects
        """
        conflicts: List[GoalConflict] = []
        now = datetime.now(timezone.utc)

        for i, goal_a in enumerate(goals):
            for goal_b in goals[i + 1:]:
                if not goal_a.primary_intent or not goal_b.primary_intent:
                    continue

                for intent_a, intent_b, desc_template in CONFLICTING_INTENTS:
                    if (
                        (goal_a.primary_intent == intent_a and goal_b.primary_intent == intent_b)
                        or (goal_a.primary_intent == intent_b and goal_b.primary_intent == intent_a)
                    ):
                        # Base severity from intent strengths
                        base_severity = (goal_a.intent_strength + goal_b.intent_strength) / 2

                        # Recency boost: conflicts between recent goals are more urgent
                        age_a_hours = max(0.0, (now - goal_a.created_at).total_seconds() / 3600)
                        age_b_hours = max(0.0, (now - goal_b.created_at).total_seconds() / 3600)
                        # Both within 48 hours -> 1.2x, both > 7 days -> 1.0x
                        recency_boost = 1.0
                        if age_a_hours <= 48 and age_b_hours <= 48:
                            recency_boost = 1.2
                        elif age_a_hours <= 48 or age_b_hours <= 48:
                            recency_boost = 1.1

                        severity = round(min(1.0, base_severity * recency_boost), 3)
                        is_irreconcilable = severity >= 0.7

                        # Generate resolution hint when irreconcilable
                        resolution_hint = None
                        if is_irreconcilable:
                            # Check if either goal already has a user weight
                            has_weight_a = goal_a.reconciliation_weight is not None
                            has_weight_b = goal_b.reconciliation_weight is not None
                            if not has_weight_a and not has_weight_b:
                                resolution_hint = (
                                    f"Set reconciliation_weight on one goal to indicate "
                                    f"which should dominate. Higher weight = more influence."
                                )
                            elif has_weight_a and has_weight_b:
                                resolution_hint = (
                                    f"Both goals have reconciliation weights set. "
                                    f"Adjust weights to change balance."
                                )

                        conflicts.append(GoalConflict(
                            conflict_id=f"conflict_{uuid.uuid4().hex[:12]}",
                            goal_id_a=goal_a.goal_id,
                            goal_id_b=goal_b.goal_id,
                            description=desc_template,
                            severity=severity,
                            is_irreconcilable=is_irreconcilable,
                            resolution_hint=resolution_hint,
                        ))

        return conflicts


# =============================================================================
# Global Instance
# =============================================================================


_goal_intent_service: Optional[GoalIntentService] = None


def get_goal_intent_service() -> GoalIntentService:
    """Get the global goal intent service instance."""
    global _goal_intent_service
    if _goal_intent_service is None:
        _goal_intent_service = GoalIntentService()
    return _goal_intent_service


def set_goal_intent_service(service: Optional[GoalIntentService]) -> None:
    """Set the global goal intent service instance."""
    global _goal_intent_service
    _goal_intent_service = service
