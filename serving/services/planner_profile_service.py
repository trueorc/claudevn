"""Planner Profile Service for dynamic profile construction and updates.

Builds and maintains the planner's operating profile from three influence sources:
- User goals (primary trigger — top-down intent)
- Worker feedback (secondary trigger — bottom-up signals)
- Resource conditions (tertiary trigger — environmental overrides)

The profile determines how the planner evaluates and sequences all work
through ontology weights, policy rules, and confidence bands.

Reference: docs/work_management_framework.md — Sections 7.1, 7.2
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models.planner_profile import (
    ConfidenceBand,
    ConfidenceLevel,
    PlannerProfile,
    PolicyActionType,
    PolicyConditionType,
    PolicyRule,
    ProfileTrigger,
    ProfileTriggerType,
    ProfileWeights,
    WeightedValue,
)
from models.work_map import Goal, GoalIntentType, GoalStatus

logger = logging.getLogger(__name__)


# =============================================================================
# Intent Signal Keywords
# =============================================================================

# Maps keywords found in goal text to ontology weight adjustments.
# Each entry: category -> key -> (weight, confidence_level)
INTENT_KEYWORDS: Dict[str, Dict[str, List[tuple]]] = {
    "expansion": {
        "work_type": [
            ("feature", 0.9, ConfidenceLevel.HIGH),
            ("integration", 0.7, ConfidenceLevel.MEDIUM),
        ],
        "lifecycle_stage": [
            ("build", 0.9, ConfidenceLevel.HIGH),
            ("design", 0.7, ConfidenceLevel.MEDIUM),
        ],
    },
    "consolidation": {
        "work_type": [
            ("test", 0.9, ConfidenceLevel.HIGH),
            ("bug_fix", 0.85, ConfidenceLevel.HIGH),
            ("refactor", 0.7, ConfidenceLevel.MEDIUM),
            ("feature", 0.15, ConfidenceLevel.MEDIUM),
        ],
        "lifecycle_stage": [
            ("test", 0.9, ConfidenceLevel.HIGH),
            ("validate", 0.85, ConfidenceLevel.HIGH),
            ("build", 0.3, ConfidenceLevel.LOW),
        ],
    },
    "targeted_investment": {
        "work_type": [
            ("feature", 0.7, ConfidenceLevel.MEDIUM),
            ("infrastructure", 0.6, ConfidenceLevel.MEDIUM),
        ],
        "lifecycle_stage": [
            ("build", 0.8, ConfidenceLevel.MEDIUM),
            ("design", 0.6, ConfidenceLevel.MEDIUM),
        ],
    },
    "quality_focused": {
        "work_type": [
            ("test", 0.9, ConfidenceLevel.HIGH),
            ("refactor", 0.8, ConfidenceLevel.HIGH),
            ("bug_fix", 0.7, ConfidenceLevel.MEDIUM),
            ("feature", 0.2, ConfidenceLevel.LOW),
        ],
        "lifecycle_stage": [
            ("test", 0.9, ConfidenceLevel.HIGH),
            ("validate", 0.9, ConfidenceLevel.HIGH),
            ("build", 0.2, ConfidenceLevel.LOW),
        ],
    },
}

# Keyword patterns for detecting goal intent
EXPANSION_KEYWORDS = [
    "add", "new", "create", "build", "implement", "introduce", "expand",
    "develop", "launch", "extend", "grow",
]
CONSOLIDATION_KEYWORDS = [
    "harden", "stabilize", "test", "fix", "validate", "secure", "improve",
    "quality", "reliability", "robust", "coverage", "bug", "regression",
    "strengthen",
]
TARGETED_KEYWORDS = [
    "focus", "prioritize", "invest", "concentrate", "target", "specific",
    "particular", "dedicated", "emphasis",
]


class PlannerProfileService:
    """Service for constructing and updating planner profiles.

    Manages the lifecycle of PlannerProfile objects:
    - Construction from goal intent signals
    - Updates from worker feedback and resource changes
    - Multi-goal reconciliation when goals coexist
    - Redis persistence for active profiles and history
    """

    def __init__(self, redis_client=None):
        """Initialize planner profile service.

        Args:
            redis_client: Optional Redis client for persistence
        """
        self._redis = redis_client
        self._profiles: Dict[str, PlannerProfile] = {}  # project_id -> active profile
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the service, loading profiles from Redis."""
        if self._initialized:
            return

        await self._load_profiles_from_redis()
        self._initialized = True
        logger.info("Planner profile service initialized")

    def _key(self, key: str) -> str:
        """Get prefixed Redis key."""
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}planner_profile:{key}"

    # =========================================================================
    # Profile Construction
    # =========================================================================

    async def construct_profile(
        self,
        project_id: str,
        goals: List[Goal],
    ) -> PlannerProfile:
        """Construct a new profile from one or more goals.

        Parses goal text to extract intent signals, translates them into
        ontology weights and policy rules, and reconciles multiple goals.

        Args:
            project_id: Project to build profile for
            goals: Active goals influencing the profile

        Returns:
            Constructed PlannerProfile
        """
        # Capture old profile before overwriting for reorganization comparison
        old_profile = self._profiles.get(project_id)

        profile_id = f"profile_{uuid.uuid4().hex[:12]}"

        # Parse intent from each goal and collect weight contributions
        all_weights: Dict[str, Dict[str, List[tuple]]] = {}
        all_rules: List[PolicyRule] = []
        triggers: List[ProfileTrigger] = []

        for goal in goals:
            intent = self._detect_intent(goal)
            goal_weights = self._intent_to_weights(intent, goal)
            goal_rules = self._generate_policy_rules(intent, goal)

            # Merge weights
            for category, entries in goal_weights.items():
                if category not in all_weights:
                    all_weights[category] = {}
                for key, weighted_values in entries.items():
                    if key not in all_weights[category]:
                        all_weights[category][key] = []
                    all_weights[category][key].extend(weighted_values)

            all_rules.extend(goal_rules)

            triggers.append(ProfileTrigger(
                trigger_type=ProfileTriggerType.NEW_GOAL,
                source_id=goal.goal_id,
                description=f"Profile constructed from goal: {goal.title}",
            ))

        # Reconcile weights from multiple goals
        reconciled_weights = self._reconcile_weights(all_weights)

        profile = PlannerProfile(
            profile_id=profile_id,
            project_id=project_id,
            weights=reconciled_weights,
            policy_rules=all_rules,
            active_goal_ids=[g.goal_id for g in goals],
            triggers=triggers,
            version=1,
        )

        self._profiles[project_id] = profile
        await self._save_profile_to_redis(profile)
        await self._save_profile_history(profile)

        # Record decision trace for profile construction
        await self._record_profile_shift_trace(
            project_id=project_id,
            trigger_type="new_goal",
            trigger_source_id=goals[0].goal_id if goals else "",
            trigger_description=f"Profile constructed from {len(goals)} goal(s)",
            decision_summary=(
                f"Constructed profile {profile_id} with {len(all_rules)} rules "
                f"and {len(goals)} goal(s)"
            ),
            key_factors=[
                f"Goal intents: {', '.join(g.primary_intent.value for g in goals if g.primary_intent)}",
                f"Active goals: {', '.join(g.title for g in goals)}",
            ],
            profile_version_before=old_profile.version if old_profile else 0,
            profile_version_after=profile.version,
            profile_id=profile_id,
            active_goal_ids=[g.goal_id for g in goals],
        )

        logger.info(
            f"Constructed profile {profile_id} for project {project_id} "
            f"from {len(goals)} goals"
        )

        # Trigger bucket tree reorganization if a tree exists
        await self._trigger_reorganization(project_id, old_profile, profile)

        return profile

    # =========================================================================
    # Profile Updates
    # =========================================================================

    async def update_for_new_goal(
        self,
        project_id: str,
        goal: Goal,
        existing_goals: List[Goal],
    ) -> PlannerProfile:
        """Update or rebuild profile when a new goal arrives.

        Primary trigger — reinterprets intent and adjusts weights/policies.

        Args:
            project_id: Project the goal belongs to
            goal: The new goal
            existing_goals: Other active goals for reconciliation

        Returns:
            Updated PlannerProfile
        """
        all_goals = existing_goals + [goal]
        profile = await self.construct_profile(project_id, all_goals)

        logger.info(
            f"Updated profile for project {project_id} after new goal: {goal.title}"
        )
        return profile

    async def update_for_worker_feedback(
        self,
        project_id: str,
        feedback_type: str,
        feedback_data: Dict,
    ) -> Optional[PlannerProfile]:
        """Adjust profile based on worker feedback signals.

        Secondary trigger — adjusts policies and may shift weights
        if blockers or challenges change the landscape.

        Args:
            project_id: Project to update
            feedback_type: Type of feedback (e.g., "blocker", "completion", "complexity")
            feedback_data: Feedback details

        Returns:
            Updated PlannerProfile, or None if no profile exists
        """
        profile = self._profiles.get(project_id)
        if not profile:
            return None

        old_profile_snapshot = profile.model_copy(deep=True)
        previous_version = profile.version
        new_rules: List[PolicyRule] = []

        if feedback_type == "blocker":
            # Worker hit a blocker — elevate blocking items
            blocking_item_id = feedback_data.get("blocking_item_id")
            if blocking_item_id:
                rule_id = f"rule_feedback_{uuid.uuid4().hex[:8]}"
                new_rules.append(PolicyRule(
                    rule_id=rule_id,
                    name=f"Elevate blocker from worker feedback",
                    description=f"Worker reported blocker on item {blocking_item_id}",
                    condition_type=PolicyConditionType.BLOCKING_COUNT_ABOVE,
                    condition_params={"item_id": blocking_item_id, "threshold": 0},
                    action_type=PolicyActionType.ELEVATE_PRIORITY,
                    action_params={"boost": 0.2},
                    confidence=ConfidenceBand(
                        level=ConfidenceLevel.MEDIUM,
                        rationale="Worker feedback signal",
                    ),
                    source_goal_id=None,
                ))

        elif feedback_type == "complexity_increase":
            # Worker reports task more complex than estimated
            cluster_id = feedback_data.get("cluster_id")
            if cluster_id and cluster_id in profile.weights.cluster_weights:
                current = profile.weights.cluster_weights[cluster_id]
                adjusted_weight = min(1.0, current.weight + 0.1)
                profile.weights.cluster_weights[cluster_id] = WeightedValue(
                    weight=adjusted_weight,
                    confidence=ConfidenceBand(
                        level=ConfidenceLevel.MEDIUM,
                        rationale=f"Weight increased due to complexity feedback (was {current.weight:.2f})",
                    ),
                )

        # Add new rules to existing profile
        existing_rule_ids = {r.rule_id for r in profile.policy_rules}
        for rule in new_rules:
            if rule.rule_id not in existing_rule_ids:
                profile.policy_rules.append(rule)

        profile.triggers.append(ProfileTrigger(
            trigger_type=ProfileTriggerType.WORKER_FEEDBACK,
            source_id=feedback_data.get("worker_id", "unknown"),
            description=f"Worker feedback: {feedback_type}",
        ))
        profile.version += 1
        profile.updated_at = datetime.now(timezone.utc)

        await self._save_profile_to_redis(profile)
        await self._save_profile_history(profile)

        # Record decision trace for profile shift
        worker_id = feedback_data.get("worker_id", "unknown")
        task_id = feedback_data.get("task_id", "unknown")
        await self._record_profile_shift_trace(
            project_id=project_id,
            trigger_type="worker_feedback",
            trigger_source_id=worker_id,
            trigger_description=f"Worker {worker_id} feedback: {feedback_type} on task {task_id}",
            decision_summary=(
                f"Profile updated from {feedback_type} feedback: "
                f"{len(new_rules)} rule(s) added"
            ),
            key_factors=[
                f"Feedback type: {feedback_type}",
                f"Worker: {worker_id}, Task: {task_id}",
            ],
            profile_version_before=previous_version,
            profile_version_after=profile.version,
            profile_id=profile.profile_id,
            active_goal_ids=profile.active_goal_ids,
        )

        logger.info(
            f"Updated profile for project {project_id} "
            f"from worker feedback: {feedback_type}"
        )

        # Trigger bucket tree reorganization
        await self._trigger_reorganization(project_id, old_profile_snapshot, profile)

        return profile

    async def update_for_resource_change(
        self,
        project_id: str,
        resource_data: Dict,
    ) -> Optional[PlannerProfile]:
        """Apply opportunistic policy overrides from resource changes.

        Tertiary trigger — introduces temporary policy overrides based
        on resource availability changes.

        Args:
            project_id: Project to update
            resource_data: Resource change details

        Returns:
            Updated PlannerProfile, or None if no profile exists
        """
        profile = self._profiles.get(project_id)
        if not profile:
            return None

        old_profile_snapshot = profile.model_copy(deep=True)
        new_rules: List[PolicyRule] = []

        available_skills = resource_data.get("available_skills", [])
        if available_skills:
            # If specific skills become available, create opportunistic rules
            for skill in available_skills:
                rule_id = f"rule_resource_{uuid.uuid4().hex[:8]}"
                new_rules.append(PolicyRule(
                    rule_id=rule_id,
                    name=f"Opportunistic: {skill} worker available",
                    description=f"Worker with skill '{skill}' became available",
                    condition_type=PolicyConditionType.CUSTOM,
                    condition_params={"required_skill": skill},
                    action_type=PolicyActionType.ELEVATE_PRIORITY,
                    action_params={"boost": 0.1},
                    confidence=ConfidenceBand(
                        level=ConfidenceLevel.LOW,
                        rationale="Opportunistic — resource availability",
                    ),
                    source_goal_id=None,
                ))

        existing_rule_ids = {r.rule_id for r in profile.policy_rules}
        for rule in new_rules:
            if rule.rule_id not in existing_rule_ids:
                profile.policy_rules.append(rule)

        profile.triggers.append(ProfileTrigger(
            trigger_type=ProfileTriggerType.RESOURCE_CHANGE,
            source_id=resource_data.get("source_id", "system"),
            description=f"Resource change: {list(resource_data.keys())}",
        ))
        profile.version += 1
        profile.updated_at = datetime.now(timezone.utc)

        await self._save_profile_to_redis(profile)
        await self._save_profile_history(profile)

        logger.info(
            f"Updated profile for project {project_id} from resource change"
        )

        # Trigger bucket tree reorganization
        await self._trigger_reorganization(project_id, old_profile_snapshot, profile)

        return profile

    async def update_for_goal_removed(
        self,
        project_id: str,
        removed_goal_id: str,
        remaining_goals: List[Goal],
    ) -> Optional[PlannerProfile]:
        """Rebuild profile when a goal is removed.

        Removes the goal's influence and reconstructs from remaining goals.

        Args:
            project_id: Project to update
            removed_goal_id: Goal being removed
            remaining_goals: Goals still active

        Returns:
            Updated PlannerProfile, or None if no remaining goals
        """
        if not remaining_goals:
            # No goals left, remove profile
            if project_id in self._profiles:
                del self._profiles[project_id]
                await self._delete_profile_from_redis(project_id)
            logger.info(f"Removed profile for project {project_id} (no goals remain)")
            return None

        profile = await self.construct_profile(project_id, remaining_goals)

        # Add removal trigger
        profile.triggers.append(ProfileTrigger(
            trigger_type=ProfileTriggerType.GOAL_REMOVED,
            source_id=removed_goal_id,
            description=f"Goal {removed_goal_id} removed, profile rebuilt",
        ))

        await self._save_profile_to_redis(profile)
        await self._save_profile_history(profile)

        logger.info(
            f"Rebuilt profile for project {project_id} after removing goal {removed_goal_id}"
        )
        return profile

    # =========================================================================
    # Profile Retrieval
    # =========================================================================
    # Bucket Tree Reorganization
    # =========================================================================

    async def _trigger_reorganization(
        self,
        project_id: str,
        old_profile: Optional[PlannerProfile],
        new_profile: PlannerProfile,
    ) -> None:
        """Trigger bucket tree reorganization after a profile change.

        Best-effort: if the bucket tree store or reorganization service
        is not initialized, the call is silently skipped.
        """
        try:
            from services.bucket_tree_store import trigger_bucket_tree_reorganization
            await trigger_bucket_tree_reorganization(project_id, old_profile, new_profile)
        except Exception as e:
            logger.debug(f"Bucket tree reorganization skipped for {project_id}: {e}")

    # =========================================================================

    async def get_profile(self, project_id: str) -> Optional[PlannerProfile]:
        """Get the active profile for a project.

        Args:
            project_id: Project to get profile for

        Returns:
            Active PlannerProfile, or None if no profile exists
        """
        return self._profiles.get(project_id)

    async def get_profile_history(
        self,
        project_id: str,
        limit: int = 10,
    ) -> List[PlannerProfile]:
        """Get profile version history for a project.

        Args:
            project_id: Project to get history for
            limit: Maximum versions to return

        Returns:
            List of historical profile versions (most recent first)
        """
        if not self._redis:
            return []

        try:
            key = self._key(f"history:{project_id}")
            raw_entries = await self._redis._redis.lrange(key, 0, limit - 1)

            profiles = []
            for raw in raw_entries:
                data = raw.decode() if isinstance(raw, bytes) else raw
                profile_dict = json.loads(data)
                profiles.append(PlannerProfile(**profile_dict))

            return profiles
        except Exception as e:
            logger.error(f"Error loading profile history for {project_id}: {e}")
            return []

    # =========================================================================
    # Intent Detection and Translation
    # =========================================================================

    def _detect_intent(self, goal: Goal) -> str:
        """Get the intent for a goal, using persisted classification when available.

        If the goal has a primary_intent from GoalIntentService classification,
        uses that directly. Otherwise falls back to keyword-based detection.

        Args:
            goal: Goal to analyze

        Returns:
            Intent type: "expansion", "consolidation", "targeted_investment",
            or "quality_focused"
        """
        # Use persisted intent classification if available
        if goal.primary_intent is not None:
            # Map GoalIntentType enum to the string keys used by INTENT_KEYWORDS
            return goal.primary_intent.value

        # Fallback to keyword-based detection
        text = f"{goal.title} {goal.description}".lower()

        expansion_score = sum(1 for kw in EXPANSION_KEYWORDS if kw in text)
        consolidation_score = sum(1 for kw in CONSOLIDATION_KEYWORDS if kw in text)
        targeted_score = sum(1 for kw in TARGETED_KEYWORDS if kw in text)

        max_score = max(expansion_score, consolidation_score, targeted_score)

        if max_score == 0:
            return "expansion"  # Default: assume building new things

        if consolidation_score == max_score:
            return "consolidation"
        if targeted_score == max_score:
            return "targeted_investment"
        return "expansion"

    def _get_goal_weight_factor(self, goal: Goal) -> float:
        """Get the weight factor for a goal based on its intent strength.

        Goals with higher intent_strength influence the profile more strongly.

        Args:
            goal: Goal to get factor for

        Returns:
            Weight factor between 0.5 and 1.5
        """
        if goal.intent_strength > 0:
            # Scale from 0.5 (weak intent) to 1.5 (strong intent)
            return 0.5 + goal.intent_strength
        return 1.0  # Default neutral factor

    def _calculate_reconciliation_factor(self, goal: Goal) -> float:
        """Calculate the overall reconciliation factor for a goal.

        Combines three influence sources:
        1. User-set reconciliation_weight (if set, takes priority)
        2. Priority-based weighting (P0 = 1.0, P1 = 0.75, P2 = 0.5, P3 = 0.25)
        3. Recency weighting (newer goals get a boost, decays over 7 days)

        The factor is multiplied into the goal's weight contributions
        during reconciliation, so higher-factor goals have more influence
        on the final profile.

        Args:
            goal: Goal to calculate factor for

        Returns:
            Reconciliation factor (0.25 to 2.0)
        """
        # User override takes priority
        if goal.reconciliation_weight is not None:
            # User weight maps directly to a 0.5-2.0 range
            return 0.5 + (goal.reconciliation_weight * 1.5)

        # Priority factor: P0=1.0, P1=0.75, P2=0.5, P3=0.25
        priority_factor = {
            "P0": 1.0,
            "P1": 0.75,
            "P2": 0.5,
            "P3": 0.25,
        }.get(goal.priority.value, 0.5)

        # Recency factor: goals created within last 24h get 1.5x,
        # decays linearly to 1.0x over 7 days
        now = datetime.now(timezone.utc)
        age_hours = max(0.0, (now - goal.created_at).total_seconds() / 3600)
        if age_hours <= 24:
            recency_factor = 1.5
        elif age_hours <= 168:  # 7 days
            # Linear decay from 1.5 to 1.0 over 6 days
            recency_factor = 1.5 - (0.5 * (age_hours - 24) / 144)
        else:
            recency_factor = 1.0

        return priority_factor * recency_factor

    def _intent_to_weights(
        self,
        intent: str,
        goal: Goal,
    ) -> Dict[str, Dict[str, List[tuple]]]:
        """Translate an intent signal into ontology weight contributions.

        Uses the goal's intent_strength to scale weights proportionally,
        so goals with stronger intent have more influence on the profile.

        Each entry is a 4-tuple: (weight, confidence, goal_id, reconciliation_factor)
        where reconciliation_factor combines priority, recency, and user overrides.

        Args:
            intent: Detected intent type
            goal: Source goal for context

        Returns:
            Dict mapping category -> key -> list of (weight, confidence, goal_id, recon_factor) tuples
        """
        weights: Dict[str, Dict[str, List[tuple]]] = {}
        intent_config = INTENT_KEYWORDS.get(intent, {})
        weight_factor = self._get_goal_weight_factor(goal)
        recon_factor = self._calculate_reconciliation_factor(goal)

        for category, entries in intent_config.items():
            if category not in weights:
                weights[category] = {}
            for key, weight, confidence in entries:
                if key not in weights[category]:
                    weights[category][key] = []
                # Scale weight by goal's intent strength factor
                scaled_weight = min(1.0, weight * weight_factor)
                weights[category][key].append((scaled_weight, confidence, goal.goal_id, recon_factor))

        return weights

    def _generate_policy_rules(
        self,
        intent: str,
        goal: Goal,
    ) -> List[PolicyRule]:
        """Generate policy rules from detected intent.

        Creates conditional rules based on the goal's intent signal.

        Args:
            intent: Detected intent type
            goal: Source goal

        Returns:
            List of PolicyRule objects
        """
        rules: List[PolicyRule] = []
        goal_short = goal.goal_id[-8:]

        if intent == "consolidation":
            # Rule: finish near-complete work
            rules.append(PolicyRule(
                rule_id=f"rule_{goal_short}_finish_wip",
                name="Finish near-complete work",
                description="Tasks >80% complete should be finished regardless of deprioritization",
                condition_type=PolicyConditionType.COMPLETION_ABOVE_THRESHOLD,
                condition_params={"threshold": 0.8},
                action_type=PolicyActionType.PRESERVE_PRIORITY,
                action_params={},
                confidence=ConfidenceBand(
                    level=ConfidenceLevel.HIGH,
                    rationale="Consolidation intent: finish what's started",
                ),
                source_goal_id=goal.goal_id,
            ))
            # Rule: elevate blockers of high-priority testing
            rules.append(PolicyRule(
                rule_id=f"rule_{goal_short}_test_blockers",
                name="Elevate testing blockers",
                description="Tasks blocking high-priority testing inherit elevated priority",
                condition_type=PolicyConditionType.BLOCKS_HIGH_PRIORITY,
                condition_params={"target_work_type": "test", "min_weight": 0.7},
                action_type=PolicyActionType.ELEVATE_PRIORITY,
                action_params={"boost": 0.3},
                confidence=ConfidenceBand(
                    level=ConfidenceLevel.HIGH,
                    rationale="Consolidation intent: unblock testing",
                ),
                source_goal_id=goal.goal_id,
            ))

        elif intent == "expansion":
            # Rule: deprioritize refactoring during expansion
            rules.append(PolicyRule(
                rule_id=f"rule_{goal_short}_defer_refactor",
                name="Defer refactoring during expansion",
                description="Deprioritize refactoring work when expanding functionality",
                condition_type=PolicyConditionType.IN_ONTOLOGY_CATEGORY,
                condition_params={"category": "work_type", "key": "refactor"},
                action_type=PolicyActionType.DEPRIORITIZE,
                action_params={"factor": 0.5},
                confidence=ConfidenceBand(
                    level=ConfidenceLevel.LOW,
                    rationale="Expansion intent: build first, refactor later",
                ),
                source_goal_id=goal.goal_id,
            ))

        elif intent == "targeted_investment":
            # Rule: elevate items with many dependents (high leverage)
            rules.append(PolicyRule(
                rule_id=f"rule_{goal_short}_high_leverage",
                name="Prioritize high-leverage items",
                description="Items blocking many others get elevated priority",
                condition_type=PolicyConditionType.BLOCKING_COUNT_ABOVE,
                condition_params={"threshold": 2},
                action_type=PolicyActionType.ELEVATE_PRIORITY,
                action_params={"boost": 0.2},
                confidence=ConfidenceBand(
                    level=ConfidenceLevel.MEDIUM,
                    rationale="Targeted investment: maximize unblocking",
                ),
                source_goal_id=goal.goal_id,
            ))

        elif intent == "quality_focused":
            # Rule: finish near-complete work (same as consolidation)
            rules.append(PolicyRule(
                rule_id=f"rule_{goal_short}_finish_wip",
                name="Finish near-complete work",
                description="Tasks >80% complete should be finished",
                condition_type=PolicyConditionType.COMPLETION_ABOVE_THRESHOLD,
                condition_params={"threshold": 0.8},
                action_type=PolicyActionType.PRESERVE_PRIORITY,
                action_params={},
                confidence=ConfidenceBand(
                    level=ConfidenceLevel.HIGH,
                    rationale="Quality focus: finish what's started",
                ),
                source_goal_id=goal.goal_id,
            ))
            # Rule: deprioritize new features during quality focus
            rules.append(PolicyRule(
                rule_id=f"rule_{goal_short}_defer_features",
                name="Defer new features during quality focus",
                description="Deprioritize new feature work when focusing on quality",
                condition_type=PolicyConditionType.IN_ONTOLOGY_CATEGORY,
                condition_params={"category": "work_type", "key": "feature"},
                action_type=PolicyActionType.DEPRIORITIZE,
                action_params={"factor": 0.4},
                confidence=ConfidenceBand(
                    level=ConfidenceLevel.MEDIUM,
                    rationale="Quality focus: improve before expanding",
                ),
                source_goal_id=goal.goal_id,
            ))

        return rules

    # =========================================================================
    # Multi-Goal Reconciliation
    # =========================================================================

    def _reconcile_weights(
        self,
        all_weights: Dict[str, Dict[str, List[tuple]]],
    ) -> ProfileWeights:
        """Reconcile weight contributions from multiple goals.

        When multiple goals contribute weights for the same category/key,
        uses a weighted average that factors in:
        1. Confidence level (HIGH=3x, MEDIUM=2x, LOW=1x)
        2. Reconciliation factor (combines priority, recency, and user weight overrides)

        Entries are 3-tuples (weight, confidence, goal_id) for backwards
        compatibility, or 4-tuples (weight, confidence, goal_id, recon_factor)
        when reconciliation factor is available.

        Args:
            all_weights: category -> key -> list of weight entry tuples

        Returns:
            Reconciled ProfileWeights
        """
        confidence_multiplier = {
            ConfidenceLevel.HIGH: 3.0,
            ConfidenceLevel.MEDIUM: 2.0,
            ConfidenceLevel.LOW: 1.0,
        }

        def reconcile_entries(entries: List[tuple]) -> WeightedValue:
            """Compute confidence-and-reconciliation-weighted average."""
            if len(entries) == 1:
                weight = entries[0][0]
                confidence = entries[0][1]
                return WeightedValue(
                    weight=weight,
                    confidence=ConfidenceBand(level=confidence),
                )

            total_weight_sum = 0.0
            total_multiplier = 0.0
            max_confidence = ConfidenceLevel.LOW

            for entry in entries:
                weight = entry[0]
                confidence = entry[1]
                # Support both 3-tuples and 4-tuples
                recon_factor = entry[3] if len(entry) >= 4 else 1.0

                conf_mult = confidence_multiplier[confidence]
                # Combined multiplier: confidence * reconciliation factor
                combined_mult = conf_mult * recon_factor
                total_weight_sum += weight * combined_mult
                total_multiplier += combined_mult
                if confidence_multiplier[confidence] > confidence_multiplier[max_confidence]:
                    max_confidence = confidence

            avg_weight = total_weight_sum / total_multiplier if total_multiplier > 0 else 0.5
            avg_weight = max(0.0, min(1.0, avg_weight))

            return WeightedValue(
                weight=round(avg_weight, 3),
                confidence=ConfidenceBand(
                    level=max_confidence,
                    rationale=f"Reconciled from {len(entries)} goal signals",
                ),
            )

        work_type_weights = {}
        lifecycle_stage_weights = {}
        technical_domain_weights = {}
        cluster_weights = {}

        category_map = {
            "work_type": work_type_weights,
            "lifecycle_stage": lifecycle_stage_weights,
            "technical_domain": technical_domain_weights,
            "cluster": cluster_weights,
        }

        for category, keys in all_weights.items():
            target = category_map.get(category, {})
            for key, entries in keys.items():
                target[key] = reconcile_entries(entries)

        return ProfileWeights(
            work_type_weights=work_type_weights,
            lifecycle_stage_weights=lifecycle_stage_weights,
            technical_domain_weights=technical_domain_weights,
            cluster_weights=cluster_weights,
        )

    # =========================================================================
    # Redis Persistence
    # =========================================================================

    async def _load_profiles_from_redis(self) -> None:
        """Load active profiles from Redis on initialization."""
        if not self._redis:
            return

        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis._redis.scan(
                    cursor,
                    match=self._key("active:*"),
                    count=100,
                )
                for key in keys:
                    try:
                        raw = await self._redis._redis.get(key)
                        if raw:
                            data = raw.decode() if isinstance(raw, bytes) else raw
                            profile = PlannerProfile(**json.loads(data))
                            self._profiles[profile.project_id] = profile
                    except Exception as e:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        logger.error(f"Error loading profile from {key_str}: {e}")

                if cursor == 0:
                    break

            logger.info(f"Loaded {len(self._profiles)} profiles from Redis")
        except Exception as e:
            logger.error(f"Error loading profiles from Redis: {e}")

    async def _save_profile_to_redis(self, profile: PlannerProfile) -> None:
        """Save active profile to Redis."""
        if not self._redis:
            return

        try:
            key = self._key(f"active:{profile.project_id}")
            data = profile.model_dump_json()
            await self._redis._redis.set(key, data)
        except Exception as e:
            logger.error(f"Error saving profile to Redis: {e}")

    async def _save_profile_history(self, profile: PlannerProfile) -> None:
        """Append profile version to history list in Redis."""
        if not self._redis:
            return

        try:
            key = self._key(f"history:{profile.project_id}")
            data = profile.model_dump_json()
            await self._redis._redis.lpush(key, data)
            # Keep last 50 versions
            await self._redis._redis.ltrim(key, 0, 49)
        except Exception as e:
            logger.error(f"Error saving profile history to Redis: {e}")

    # =========================================================================
    # Decision Traceability
    # =========================================================================

    async def _record_profile_shift_trace(
        self,
        project_id: str,
        trigger_type: str,
        trigger_source_id: str,
        trigger_description: str,
        decision_summary: str,
        key_factors: List[str],
        profile_version_before: int,
        profile_version_after: int,
        profile_id: str,
        active_goal_ids: Optional[List[str]] = None,
    ) -> None:
        """Record a decision trace for a profile shift.

        Non-critical — failures are logged but do not interrupt the
        profile update flow.
        """
        try:
            from services.decision_trace_service import get_decision_trace_service
            from models.decision_trace import (
                DecisionContext,
                DecisionImpact,
                DecisionPointType,
                DecisionTrigger,
            )

            service = get_decision_trace_service()
            await service.record(
                project_id=project_id,
                decision_type=DecisionPointType.PROFILE_SHIFT,
                trigger=DecisionTrigger(
                    trigger_type=trigger_type,
                    source_id=trigger_source_id,
                    source_type="goal" if trigger_type == "new_goal" else "feedback_signal",
                    description=trigger_description,
                ),
                decision_summary=decision_summary,
                key_factors=key_factors,
                context=DecisionContext(
                    profile_version=profile_version_before,
                    profile_id=profile_id,
                    active_goal_ids=active_goal_ids or [],
                ),
                impact=DecisionImpact(
                    profile_version_before=profile_version_before,
                    profile_version_after=profile_version_after,
                ),
            )
        except Exception as e:
            logger.debug(f"Could not record profile shift trace: {e}")

    async def _delete_profile_from_redis(self, project_id: str) -> None:
        """Delete active profile from Redis."""
        if not self._redis:
            return

        try:
            await self._redis._redis.delete(self._key(f"active:{project_id}"))
        except Exception as e:
            logger.error(f"Error deleting profile from Redis: {e}")


# =============================================================================
# Global Instance
# =============================================================================


_planner_profile_service: Optional[PlannerProfileService] = None


def get_planner_profile_service() -> PlannerProfileService:
    """Get the global planner profile service instance."""
    if _planner_profile_service is None:
        raise RuntimeError("Planner profile service not initialized")
    return _planner_profile_service


def set_planner_profile_service(service: Optional[PlannerProfileService]) -> None:
    """Set the global planner profile service instance."""
    global _planner_profile_service
    _planner_profile_service = service
