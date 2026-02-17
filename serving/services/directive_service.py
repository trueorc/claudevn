"""Directive Service for interpreting and applying user topology directives.

Processes natural-language directives like "Accelerate payment flow validation"
or "Focus on testing for the authentication domain" into concrete profile
adjustments. Provides preview/approval workflow and tracks directive history.

Integrates with:
- PlannerProfileService: applies weight and policy adjustments
- DecisionTraceService: records directive application in decision trace
- GoalIntentService: reuses intent detection patterns

Reference: docs/work_management_framework.md - Section 10
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from models.directive import (
    Directive,
    DirectiveInterpretation,
    DirectiveStatus,
    PolicyAdjustment,
    WeightAdjustment,
)
from models.planner_profile import (
    ConfidenceBand,
    ConfidenceLevel,
    PolicyActionType,
    PolicyConditionType,
    PolicyRule,
    ProfileTrigger,
    ProfileTriggerType,
    WeightedValue,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Directive Intent Patterns
# =============================================================================

# Maps directive verbs to intent categories and their effect direction
DIRECTIVE_PATTERNS: Dict[str, Dict] = {
    "accelerate": {
        "intent": "accelerate",
        "weight_direction": 1.0,  # boost weights
        "confidence": ConfidenceLevel.HIGH,
        "keywords": ["accelerate", "speed up", "fast-track", "rush", "expedite", "hurry"],
    },
    "deprioritize": {
        "intent": "deprioritize",
        "weight_direction": -1.0,  # reduce weights
        "confidence": ConfidenceLevel.HIGH,
        "keywords": ["deprioritize", "defer", "delay", "park", "shelve", "pause", "slow down", "back-burner"],
    },
    "focus": {
        "intent": "focus",
        "weight_direction": 1.0,
        "confidence": ConfidenceLevel.HIGH,
        "keywords": ["focus", "concentrate", "prioritize", "emphasize", "invest in", "double down"],
    },
    "unblock": {
        "intent": "unblock",
        "weight_direction": 1.0,
        "confidence": ConfidenceLevel.MEDIUM,
        "keywords": ["unblock", "clear", "resolve", "fix blockers", "remove obstacles"],
    },
    "balance": {
        "intent": "balance",
        "weight_direction": 0.0,  # normalize toward 0.5
        "confidence": ConfidenceLevel.LOW,
        "keywords": ["balance", "normalize", "even out", "distribute evenly", "rebalance"],
    },
}

# Domain/area keyword mapping to ontology categories
AREA_KEYWORDS: Dict[str, Dict[str, str]] = {
    # Work types
    "testing": {"category": "work_type", "key": "test"},
    "test": {"category": "work_type", "key": "test"},
    "tests": {"category": "work_type", "key": "test"},
    "feature": {"category": "work_type", "key": "feature"},
    "features": {"category": "work_type", "key": "feature"},
    "bug": {"category": "work_type", "key": "bug_fix"},
    "bugs": {"category": "work_type", "key": "bug_fix"},
    "bug fix": {"category": "work_type", "key": "bug_fix"},
    "refactor": {"category": "work_type", "key": "refactor"},
    "refactoring": {"category": "work_type", "key": "refactor"},
    "documentation": {"category": "work_type", "key": "documentation"},
    "docs": {"category": "work_type", "key": "documentation"},
    "infrastructure": {"category": "work_type", "key": "infrastructure"},
    "infra": {"category": "work_type", "key": "infrastructure"},
    "integration": {"category": "work_type", "key": "integration"},
    # Lifecycle stages
    "design": {"category": "lifecycle_stage", "key": "design"},
    "build": {"category": "lifecycle_stage", "key": "build"},
    "building": {"category": "lifecycle_stage", "key": "build"},
    "validation": {"category": "lifecycle_stage", "key": "validate"},
    "validate": {"category": "lifecycle_stage", "key": "validate"},
    "deploy": {"category": "lifecycle_stage", "key": "deploy"},
    "deployment": {"category": "lifecycle_stage", "key": "deploy"},
    # Technical domains
    "frontend": {"category": "technical_domain", "key": "frontend"},
    "ui": {"category": "technical_domain", "key": "frontend"},
    "backend": {"category": "technical_domain", "key": "backend"},
    "api": {"category": "technical_domain", "key": "api"},
    "security": {"category": "technical_domain", "key": "security"},
    "devops": {"category": "technical_domain", "key": "devops"},
    "data": {"category": "technical_domain", "key": "data"},
    "database": {"category": "technical_domain", "key": "data"},
}


class DirectiveService:
    """Service for interpreting and applying user topology directives.

    Provides:
    - Natural language directive interpretation
    - Preview of profile changes before applying
    - Application of approved directives to planner profile
    - Directive history tracking via Redis
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._directives: Dict[str, Dict[str, Directive]] = {}  # project_id -> {directive_id -> Directive}

    def _key(self, key: str) -> str:
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}directive:{key}"

    # =========================================================================
    # Interpretation
    # =========================================================================

    async def interpret(
        self,
        project_id: str,
        text: str,
    ) -> Directive:
        """Interpret a natural language directive into profile adjustments.

        Parses the directive text to detect intent (accelerate, deprioritize,
        focus, unblock) and target areas, then generates proposed weight and
        policy adjustments.

        Args:
            project_id: Project this directive targets.
            text: Natural language directive text.

        Returns:
            Directive with interpretation populated (status=PENDING_REVIEW).
        """
        directive_id = f"dir_{uuid.uuid4().hex[:12]}"

        # Detect intent and target areas
        intent, confidence = self._detect_directive_intent(text)
        target_areas = self._detect_target_areas(text)

        # Get current profile for context
        current_profile = await self._get_current_profile(project_id)

        # Generate weight adjustments
        weight_adjustments = self._generate_weight_adjustments(
            intent, confidence, target_areas, current_profile
        )

        # Generate policy adjustments
        policy_adjustments = self._generate_policy_adjustments(
            intent, target_areas, directive_id
        )

        # Build summary
        affected_area_names = [f"{a['category']}/{a['key']}" for a in target_areas]
        summary = self._build_summary(intent, affected_area_names, weight_adjustments)

        interpretation = DirectiveInterpretation(
            weight_adjustments=weight_adjustments,
            policy_adjustments=policy_adjustments,
            summary=summary,
            detected_intent=intent,
            affected_areas=affected_area_names,
        )

        directive = Directive(
            directive_id=directive_id,
            project_id=project_id,
            text=text,
            status=DirectiveStatus.PENDING_REVIEW,
            interpretation=interpretation,
            profile_version_before=(
                current_profile.version if current_profile else None
            ),
        )

        # Store in memory
        if project_id not in self._directives:
            self._directives[project_id] = {}
        self._directives[project_id][directive_id] = directive

        await self._save_directive_to_redis(directive)
        await self._append_directive_to_history(directive)

        logger.info(
            f"Interpreted directive {directive_id}: intent={intent}, "
            f"areas={affected_area_names}"
        )
        return directive

    # =========================================================================
    # Application
    # =========================================================================

    async def apply(
        self,
        project_id: str,
        directive_id: str,
    ) -> Directive:
        """Apply an approved directive to the planner profile.

        Takes the interpretation's weight and policy adjustments and applies
        them to the current profile. Records a decision trace entry.

        Args:
            project_id: Project this directive targets.
            directive_id: Directive to apply.

        Returns:
            Updated Directive with status=APPLIED.

        Raises:
            ValueError: If directive not found or not in PENDING_REVIEW status.
        """
        directive = self._get_directive(project_id, directive_id)
        if not directive:
            raise ValueError(f"Directive {directive_id} not found")
        if directive.status != DirectiveStatus.PENDING_REVIEW:
            raise ValueError(
                f"Directive {directive_id} is {directive.status.value}, "
                f"expected {DirectiveStatus.PENDING_REVIEW.value}"
            )
        if not directive.interpretation:
            raise ValueError(f"Directive {directive_id} has no interpretation")

        # Apply to profile
        profile = await self._apply_to_profile(project_id, directive)

        # Update directive
        directive.status = DirectiveStatus.APPLIED
        directive.applied_at = datetime.now(timezone.utc)
        directive.profile_version_after = profile.version if profile else None

        await self._save_directive_to_redis(directive)

        # Record decision trace
        await self._record_directive_trace(directive)

        logger.info(f"Applied directive {directive_id} to project {project_id}")
        return directive

    async def reject(
        self,
        project_id: str,
        directive_id: str,
    ) -> Directive:
        """Reject a directive (do not apply changes).

        Args:
            project_id: Project this directive targets.
            directive_id: Directive to reject.

        Returns:
            Updated Directive with status=REJECTED.

        Raises:
            ValueError: If directive not found or not in PENDING_REVIEW status.
        """
        directive = self._get_directive(project_id, directive_id)
        if not directive:
            raise ValueError(f"Directive {directive_id} not found")
        if directive.status != DirectiveStatus.PENDING_REVIEW:
            raise ValueError(
                f"Directive {directive_id} is {directive.status.value}, "
                f"expected {DirectiveStatus.PENDING_REVIEW.value}"
            )

        directive.status = DirectiveStatus.REJECTED
        directive.rejected_at = datetime.now(timezone.utc)
        await self._save_directive_to_redis(directive)

        logger.info(f"Rejected directive {directive_id}")
        return directive

    # =========================================================================
    # Queries
    # =========================================================================

    async def get_directive(
        self,
        project_id: str,
        directive_id: str,
    ) -> Optional[Directive]:
        """Get a specific directive by ID."""
        return self._get_directive(project_id, directive_id)

    async def get_history(
        self,
        project_id: str,
        limit: int = 50,
    ) -> List[Directive]:
        """Get directive history for a project (most recent first).

        Args:
            project_id: Project to get history for.
            limit: Maximum directives to return.

        Returns:
            List of Directive objects, most recent first.
        """
        # Try Redis first
        directives = await self._load_history_from_redis(project_id, limit)
        if directives:
            return directives

        # Fallback to in-memory
        project_directives = self._directives.get(project_id, {})
        sorted_directives = sorted(
            project_directives.values(),
            key=lambda d: d.created_at,
            reverse=True,
        )
        return sorted_directives[:limit]

    # =========================================================================
    # Intent Detection
    # =========================================================================

    def _detect_directive_intent(self, text: str) -> Tuple[str, ConfidenceLevel]:
        """Detect the directive intent from text.

        Returns:
            Tuple of (intent_name, confidence_level).
        """
        text_lower = text.lower()

        best_intent = None
        best_match_count = 0
        best_confidence = ConfidenceLevel.LOW

        for pattern_name, pattern in DIRECTIVE_PATTERNS.items():
            match_count = sum(
                1 for kw in pattern["keywords"] if kw in text_lower
            )
            if match_count > best_match_count:
                best_match_count = match_count
                best_intent = pattern["intent"]
                best_confidence = pattern["confidence"]

        if not best_intent:
            # Default: treat as a focus directive
            best_intent = "focus"
            best_confidence = ConfidenceLevel.LOW

        return best_intent, best_confidence

    def _detect_target_areas(self, text: str) -> List[Dict[str, str]]:
        """Detect ontology target areas from directive text.

        Matches against known work types, lifecycle stages, technical
        domains, and cluster names.

        Returns:
            List of dicts with 'category' and 'key' fields.
        """
        text_lower = text.lower()
        found = []
        seen = set()

        # Sort keywords by length descending to match longer phrases first
        sorted_keywords = sorted(AREA_KEYWORDS.keys(), key=len, reverse=True)

        for keyword in sorted_keywords:
            if keyword in text_lower:
                area = AREA_KEYWORDS[keyword]
                area_key = f"{area['category']}/{area['key']}"
                if area_key not in seen:
                    seen.add(area_key)
                    found.append(area)

        return found

    # =========================================================================
    # Adjustment Generation
    # =========================================================================

    def _generate_weight_adjustments(
        self,
        intent: str,
        confidence: ConfidenceLevel,
        target_areas: List[Dict[str, str]],
        current_profile,
    ) -> List[WeightAdjustment]:
        """Generate weight adjustments from intent and target areas."""
        adjustments = []
        pattern = DIRECTIVE_PATTERNS.get(intent, DIRECTIVE_PATTERNS["focus"])
        direction = pattern["weight_direction"]

        for area in target_areas:
            category = area["category"]
            key = area["key"]

            # Get current weight from profile
            current_weight = None
            if current_profile:
                current_weight = current_profile.weights.get_weight(category, key)

            # Calculate proposed weight
            if direction > 0:
                # Boost: move toward 1.0
                base = current_weight if current_weight is not None else 0.5
                proposed = min(1.0, base + 0.3)
            elif direction < 0:
                # Reduce: move toward 0.0
                base = current_weight if current_weight is not None else 0.5
                proposed = max(0.0, base - 0.3)
            else:
                # Balance: move toward 0.5
                proposed = 0.5

            proposed = round(proposed, 2)

            adjustments.append(WeightAdjustment(
                category=category,
                key=key,
                current_weight=current_weight if current_weight != 0.5 else None,
                proposed_weight=proposed,
                confidence=confidence.value,
                rationale=f"{intent.capitalize()} directive targeting {category}/{key}",
            ))

        return adjustments

    def _generate_policy_adjustments(
        self,
        intent: str,
        target_areas: List[Dict[str, str]],
        directive_id: str,
    ) -> List[PolicyAdjustment]:
        """Generate policy rule adjustments from intent."""
        adjustments = []

        if intent == "accelerate":
            for area in target_areas:
                adjustments.append(PolicyAdjustment(
                    action="add",
                    rule_name=f"Accelerate {area['key']}",
                    rule_description=(
                        f"Elevate priority for {area['category']}/{area['key']} "
                        f"items per user directive"
                    ),
                    condition_type=PolicyConditionType.IN_ONTOLOGY_CATEGORY.value,
                    condition_params={
                        "category": area["category"],
                        "key": area["key"],
                    },
                    action_type=PolicyActionType.ELEVATE_PRIORITY.value,
                    action_params={"boost": 0.3},
                ))

        elif intent == "deprioritize":
            for area in target_areas:
                adjustments.append(PolicyAdjustment(
                    action="add",
                    rule_name=f"Deprioritize {area['key']}",
                    rule_description=(
                        f"Deprioritize {area['category']}/{area['key']} "
                        f"items per user directive"
                    ),
                    condition_type=PolicyConditionType.IN_ONTOLOGY_CATEGORY.value,
                    condition_params={
                        "category": area["category"],
                        "key": area["key"],
                    },
                    action_type=PolicyActionType.DEPRIORITIZE.value,
                    action_params={"factor": 0.4},
                ))

        elif intent == "unblock":
            adjustments.append(PolicyAdjustment(
                action="add",
                rule_name="Elevate blocked items",
                rule_description="Elevate items that are blocking others",
                condition_type=PolicyConditionType.BLOCKING_COUNT_ABOVE.value,
                condition_params={"threshold": 1},
                action_type=PolicyActionType.ELEVATE_PRIORITY.value,
                action_params={"boost": 0.25},
            ))

        return adjustments

    def _build_summary(
        self,
        intent: str,
        area_names: List[str],
        weight_adjustments: List[WeightAdjustment],
    ) -> str:
        """Build a human-readable summary of the directive interpretation."""
        if not area_names:
            return f"Directive interpreted as '{intent}' but no specific areas detected."

        areas_str = ", ".join(area_names)
        changes_count = len(weight_adjustments)

        intent_verbs = {
            "accelerate": "Accelerating",
            "deprioritize": "Deprioritizing",
            "focus": "Focusing on",
            "unblock": "Unblocking",
            "balance": "Rebalancing",
        }
        verb = intent_verbs.get(intent, "Adjusting")

        return f"{verb} {areas_str}. {changes_count} weight adjustment(s) proposed."

    # =========================================================================
    # Profile Application
    # =========================================================================

    async def _apply_to_profile(
        self,
        project_id: str,
        directive: Directive,
    ):
        """Apply directive's interpretation to the planner profile."""
        try:
            from services.planner_profile_service import get_planner_profile_service

            service = get_planner_profile_service()
            profile = await service.get_profile(project_id)

            if not profile:
                logger.warning(f"No profile found for project {project_id}")
                return None

            interp = directive.interpretation

            # Apply weight adjustments
            for adj in interp.weight_adjustments:
                conf_level = ConfidenceLevel(adj.confidence)
                weighted_val = WeightedValue(
                    weight=adj.proposed_weight,
                    confidence=ConfidenceBand(
                        level=conf_level,
                        rationale=adj.rationale,
                    ),
                )

                weights_map = {
                    "work_type": profile.weights.work_type_weights,
                    "lifecycle_stage": profile.weights.lifecycle_stage_weights,
                    "technical_domain": profile.weights.technical_domain_weights,
                    "cluster": profile.weights.cluster_weights,
                }
                target = weights_map.get(adj.category)
                if target is not None:
                    target[adj.key] = weighted_val

            # Apply policy adjustments
            for pol_adj in interp.policy_adjustments:
                if pol_adj.action == "add" and pol_adj.condition_type and pol_adj.action_type:
                    rule = PolicyRule(
                        rule_id=f"rule_dir_{directive.directive_id}_{uuid.uuid4().hex[:6]}",
                        name=pol_adj.rule_name,
                        description=pol_adj.rule_description,
                        condition_type=PolicyConditionType(pol_adj.condition_type),
                        condition_params=pol_adj.condition_params,
                        action_type=PolicyActionType(pol_adj.action_type),
                        action_params=pol_adj.action_params,
                        confidence=ConfidenceBand(
                            level=ConfidenceLevel.HIGH,
                            rationale=f"User directive: {directive.text}",
                        ),
                        source_goal_id=None,
                    )
                    profile.policy_rules.append(rule)

            # Update profile metadata
            profile.triggers.append(ProfileTrigger(
                trigger_type=ProfileTriggerType.MANUAL_ADJUSTMENT,
                source_id=directive.directive_id,
                description=f"User directive: {directive.text}",
            ))
            profile.version += 1
            profile.updated_at = datetime.now(timezone.utc)

            # Save updated profile
            await service._save_profile_to_redis(profile)
            await service._save_profile_history(profile)

            return profile

        except Exception as e:
            logger.error(f"Failed to apply directive to profile: {e}")
            return None

    async def _get_current_profile(self, project_id: str):
        """Get current planner profile for context."""
        try:
            from services.planner_profile_service import get_planner_profile_service
            service = get_planner_profile_service()
            return await service.get_profile(project_id)
        except Exception:
            return None

    # =========================================================================
    # Decision Trace
    # =========================================================================

    async def _record_directive_trace(self, directive: Directive) -> None:
        """Record a decision trace for a directive application."""
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
                project_id=directive.project_id,
                decision_type=DecisionPointType.PROFILE_SHIFT,
                trigger=DecisionTrigger(
                    trigger_type="user_directive",
                    source_id=directive.directive_id,
                    source_type="directive",
                    description=f"User directive: {directive.text}",
                ),
                decision_summary=(
                    f"Applied directive '{directive.text}': "
                    f"{directive.interpretation.summary}"
                ),
                key_factors=[
                    f"Intent: {directive.interpretation.detected_intent}",
                    f"Areas: {', '.join(directive.interpretation.affected_areas)}",
                ],
                context=DecisionContext(
                    profile_version=directive.profile_version_before,
                ),
                impact=DecisionImpact(
                    profile_version_before=directive.profile_version_before,
                    profile_version_after=directive.profile_version_after,
                ),
            )
        except Exception as e:
            logger.debug(f"Could not record directive trace: {e}")

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _get_directive(
        self,
        project_id: str,
        directive_id: str,
    ) -> Optional[Directive]:
        """Get a directive from in-memory store."""
        return self._directives.get(project_id, {}).get(directive_id)

    # =========================================================================
    # Redis Persistence
    # =========================================================================

    async def _save_directive_to_redis(self, directive: Directive) -> None:
        """Persist a directive to Redis (individual key only).

        Does NOT append to the history list — call _append_directive_to_history
        once during interpret() for that.
        """
        if not self._redis:
            return

        try:
            key = self._key(f"item:{directive.project_id}:{directive.directive_id}")
            data = directive.model_dump_json()
            await self._redis._redis.set(key, data)
        except Exception as e:
            logger.error(f"Error saving directive to Redis: {e}")

    async def _append_directive_to_history(self, directive: Directive) -> None:
        """Append a directive to the project history list (call once on creation)."""
        if not self._redis:
            return

        try:
            history_key = self._key(f"history:{directive.project_id}")
            data = directive.model_dump_json()
            await self._redis._redis.lpush(history_key, data)
            await self._redis._redis.ltrim(history_key, 0, 99)
        except Exception as e:
            logger.error(f"Error appending directive to history: {e}")

    async def _load_history_from_redis(
        self,
        project_id: str,
        limit: int = 50,
    ) -> List[Directive]:
        """Load directive history from Redis."""
        if not self._redis:
            return []

        try:
            key = self._key(f"history:{project_id}")
            raw_entries = await self._redis._redis.lrange(key, 0, limit - 1)

            directives = []
            for raw in raw_entries:
                data = raw.decode() if isinstance(raw, bytes) else raw
                directives.append(Directive(**json.loads(data)))

            return directives
        except Exception as e:
            logger.error(f"Error loading directive history: {e}")
            return []


# =============================================================================
# Global Instance
# =============================================================================


_directive_service: Optional[DirectiveService] = None


def get_directive_service() -> DirectiveService:
    """Get the global directive service instance."""
    if _directive_service is None:
        raise RuntimeError("Directive service not initialized")
    return _directive_service


def set_directive_service(service: Optional[DirectiveService]) -> None:
    """Set the global directive service instance."""
    global _directive_service
    _directive_service = service
