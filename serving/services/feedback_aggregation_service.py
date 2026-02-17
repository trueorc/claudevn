"""Feedback Aggregation Service for worker-to-planner profile loop.

Collects, classifies, and aggregates worker feedback signals. Detects
patterns across signals and triggers planner profile updates through
the PlannerProfileService.

Individual signals cause minor policy adjustments. Detected patterns
(multiple workers reporting similar issues) trigger weight shifts.

Reference: docs/work_management_framework.md — Sections 8.2, 9, 11
"""

import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from models.feedback import (
    DecisionTraceEntry,
    FeedbackPattern,
    FeedbackSeverity,
    FeedbackSignal,
    FeedbackType,
)
from models.planner_profile import ConfidenceBand, ConfidenceLevel
from services.planner_profile_service import get_planner_profile_service

logger = logging.getLogger(__name__)

# Threshold: number of signals of the same type before treating as a pattern
PATTERN_THRESHOLD = 3

# Weight shift amount for detected patterns (systemic signals)
PATTERN_WEIGHT_SHIFT = 0.15

# Policy boost for individual signals
INDIVIDUAL_BOOST = 0.2

# Severity multipliers for weight adjustments
SEVERITY_MULTIPLIER = {
    FeedbackSeverity.LOW: 0.5,
    FeedbackSeverity.MEDIUM: 1.0,
    FeedbackSeverity.HIGH: 1.5,
    FeedbackSeverity.CRITICAL: 2.0,
}


class FeedbackAggregationService:
    """Service for aggregating worker feedback and updating planner profiles.

    Collects feedback signals from MCP tools (blockers, challenges,
    requirements), detects patterns across signals, and triggers
    appropriate profile updates:
    - Individual signals -> policy adjustments (via PlannerProfileService)
    - Detected patterns -> weight shifts (systemic changes)
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._signals: Dict[str, List[FeedbackSignal]] = defaultdict(list)  # project_id -> signals
        self._patterns: Dict[str, List[FeedbackPattern]] = defaultdict(list)  # project_id -> patterns
        self._decision_trace: Dict[str, List[DecisionTraceEntry]] = defaultdict(list)  # project_id -> trace
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the service, loading state from Redis if available."""
        if self._initialized:
            return

        await self._load_from_redis()
        self._initialized = True
        logger.info("Feedback aggregation service initialized")

    def _key(self, key: str) -> str:
        """Get prefixed Redis key."""
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}feedback:{key}"

    # =========================================================================
    # Signal Processing
    # =========================================================================

    async def process_signal(
        self,
        signal: FeedbackSignal,
    ) -> Tuple[Optional[DecisionTraceEntry], Optional[FeedbackPattern]]:
        """Process a worker feedback signal.

        1. Records the signal
        2. Checks for pattern detection
        3. Triggers appropriate profile update
        4. Returns decision trace entry and detected pattern (if any)

        Args:
            signal: The feedback signal to process

        Returns:
            Tuple of (decision_trace_entry, detected_pattern)
            Either or both may be None if no action was taken.
        """
        project_id = signal.project_id

        # Record the signal
        self._signals[project_id].append(signal)
        await self._save_signal_to_redis(signal)

        logger.info(
            f"Feedback signal: project={project_id} type={signal.feedback_type} "
            f"worker={signal.worker_id} task={signal.task_id} "
            f"severity={signal.severity}"
        )

        # Check for pattern detection
        pattern = self._detect_pattern(project_id, signal.feedback_type)
        trace_entry = None

        if pattern:
            # Pattern detected — trigger weight shift
            trace_entry = await self._apply_pattern_update(project_id, pattern, signal)
        else:
            # Individual signal — trigger policy adjustment
            trace_entry = await self._apply_individual_update(project_id, signal)

        if trace_entry:
            self._decision_trace[project_id].append(trace_entry)
            await self._save_trace_to_redis(trace_entry)

        return trace_entry, pattern

    # =========================================================================
    # Pattern Detection
    # =========================================================================

    def _detect_pattern(
        self,
        project_id: str,
        feedback_type: FeedbackType,
    ) -> Optional[FeedbackPattern]:
        """Detect if signals of the same type form a pattern.

        A pattern is detected when PATTERN_THRESHOLD or more signals
        of the same type exist for a project.

        Args:
            project_id: Project to check
            feedback_type: Type to check for pattern

        Returns:
            FeedbackPattern if threshold met, None otherwise
        """
        signals = self._signals.get(project_id, [])
        matching = [s for s in signals if s.feedback_type == feedback_type]

        if len(matching) < PATTERN_THRESHOLD:
            return None

        # Check if we already have an active pattern for this type
        existing_patterns = self._patterns.get(project_id, [])
        for p in existing_patterns:
            if p.feedback_type == feedback_type:
                # Update existing pattern
                new_signal_ids = [s.signal_id for s in matching]
                p.signal_ids = new_signal_ids
                p.signal_count = len(matching)
                p.last_seen = datetime.now(timezone.utc)
                return p

        # Create new pattern
        affected_clusters = set()
        affected_work_types = set()
        for s in matching:
            if "cluster_id" in s.data:
                affected_clusters.add(s.data["cluster_id"])
            if "work_type" in s.data:
                affected_work_types.add(s.data["work_type"])

        pattern = FeedbackPattern(
            pattern_id=f"pattern_{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            feedback_type=feedback_type,
            signal_ids=[s.signal_id for s in matching],
            signal_count=len(matching),
            description=f"Pattern detected: {len(matching)} {feedback_type.value} signals",
            affected_clusters=list(affected_clusters),
            affected_work_types=list(affected_work_types),
            first_seen=matching[0].timestamp,
            last_seen=matching[-1].timestamp,
        )

        self._patterns[project_id].append(pattern)
        return pattern

    # =========================================================================
    # Profile Updates
    # =========================================================================

    async def _apply_individual_update(
        self,
        project_id: str,
        signal: FeedbackSignal,
    ) -> Optional[DecisionTraceEntry]:
        """Apply a minor policy adjustment for an individual signal.

        Routes to PlannerProfileService.update_for_worker_feedback()
        with appropriate feedback_type and data.

        Args:
            project_id: Project to update
            signal: Individual signal

        Returns:
            DecisionTraceEntry if profile was updated, None otherwise
        """
        try:
            profile_service = get_planner_profile_service()
        except RuntimeError:
            logger.warning("Planner profile service not available, skipping profile update")
            return None

        profile = await profile_service.get_profile(project_id)
        if not profile:
            return None

        previous_version = profile.version

        # Map feedback type to profile service feedback_type
        feedback_type_map = {
            FeedbackType.BLOCKER: "blocker",
            FeedbackType.CHALLENGE: "challenge",
            FeedbackType.REQUIREMENT: "new_requirement",
            FeedbackType.PROGRESS_PATTERN: "progress_pattern",
        }

        feedback_data = {
            "worker_id": signal.worker_id,
            "task_id": signal.task_id,
            "severity": signal.severity.value,
            **signal.data,
        }

        # For blocker type, extract blocking_item_id from data
        if signal.feedback_type == FeedbackType.BLOCKER:
            feedback_data["blocking_item_id"] = signal.data.get("blocking_work_id", signal.task_id)

        updated_profile = await profile_service.update_for_worker_feedback(
            project_id=project_id,
            feedback_type=feedback_type_map.get(signal.feedback_type, signal.feedback_type.value),
            feedback_data=feedback_data,
        )

        if not updated_profile:
            return None

        trace = DecisionTraceEntry(
            trace_id=f"trace_{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            trigger_type="individual_signal",
            source_signal_ids=[signal.signal_id],
            previous_profile_version=previous_version,
            new_profile_version=updated_profile.version,
            rule_changes=[],
            rationale=(
                f"Individual {signal.feedback_type.value} signal from worker "
                f"{signal.worker_id} on task {signal.task_id}: {signal.description}"
            ),
        )

        logger.info(
            f"Applied individual feedback to profile: project={project_id} "
            f"type={signal.feedback_type.value} version={previous_version}->{updated_profile.version}"
        )
        return trace

    async def _apply_pattern_update(
        self,
        project_id: str,
        pattern: FeedbackPattern,
        trigger_signal: FeedbackSignal,
    ) -> Optional[DecisionTraceEntry]:
        """Apply weight shifts for a detected pattern.

        When a pattern is detected, this applies stronger changes than
        individual signals — shifting ontology weights rather than just
        adding policy rules.

        Args:
            project_id: Project to update
            pattern: Detected pattern
            trigger_signal: Signal that triggered pattern detection

        Returns:
            DecisionTraceEntry if profile was updated, None otherwise
        """
        try:
            profile_service = get_planner_profile_service()
        except RuntimeError:
            logger.warning("Planner profile service not available, skipping pattern update")
            return None

        profile = await profile_service.get_profile(project_id)
        if not profile:
            return None

        previous_version = profile.version
        weight_changes: Dict[str, Dict[str, float]] = {}

        # Apply weight shifts based on pattern type and affected areas
        severity_mult = SEVERITY_MULTIPLIER.get(trigger_signal.severity, 1.0)
        shift = PATTERN_WEIGHT_SHIFT * severity_mult

        if pattern.feedback_type == FeedbackType.BLOCKER:
            # Systemic blockers: increase weight for bug_fix and infrastructure work types
            for wt in ["bug_fix", "infrastructure"]:
                current = profile.weights.get_weight("work_type", wt)
                new_weight = min(1.0, current + shift)
                from models.planner_profile import WeightedValue
                profile.weights.work_type_weights[wt] = WeightedValue(
                    weight=new_weight,
                    confidence=ConfidenceBand(
                        level=ConfidenceLevel.MEDIUM,
                        rationale=f"Increased due to systemic blocker pattern ({pattern.signal_count} signals)",
                    ),
                )
                weight_changes.setdefault("work_type", {})[wt] = new_weight

        elif pattern.feedback_type == FeedbackType.CHALLENGE:
            # Systemic challenges: may indicate domain needs more attention
            for cluster_id in pattern.affected_clusters:
                if cluster_id in profile.weights.cluster_weights:
                    current = profile.weights.cluster_weights[cluster_id].weight
                    new_weight = min(1.0, current + shift)
                else:
                    new_weight = 0.5 + shift
                from models.planner_profile import WeightedValue
                profile.weights.cluster_weights[cluster_id] = WeightedValue(
                    weight=min(1.0, new_weight),
                    confidence=ConfidenceBand(
                        level=ConfidenceLevel.MEDIUM,
                        rationale=f"Increased due to systemic challenge pattern ({pattern.signal_count} signals)",
                    ),
                )
                weight_changes.setdefault("cluster", {})[cluster_id] = min(1.0, new_weight)

        elif pattern.feedback_type == FeedbackType.REQUIREMENT:
            # Systemic new requirements: shift toward expansion
            current = profile.weights.get_weight("work_type", "feature")
            new_weight = min(1.0, current + shift * 0.5)
            from models.planner_profile import WeightedValue
            profile.weights.work_type_weights["feature"] = WeightedValue(
                weight=new_weight,
                confidence=ConfidenceBand(
                    level=ConfidenceLevel.LOW,
                    rationale=f"Increased due to systemic new requirements ({pattern.signal_count} signals)",
                ),
            )
            weight_changes.setdefault("work_type", {})["feature"] = new_weight

        # Update profile metadata
        from models.planner_profile import ProfileTrigger, ProfileTriggerType
        profile.triggers.append(ProfileTrigger(
            trigger_type=ProfileTriggerType.WORKER_FEEDBACK,
            source_id=f"pattern:{pattern.pattern_id}",
            description=(
                f"Pattern detected: {pattern.signal_count} {pattern.feedback_type.value} "
                f"signals from workers"
            ),
        ))
        profile.version += 1
        profile.updated_at = datetime.now(timezone.utc)

        await profile_service._save_profile_to_redis(profile)
        await profile_service._save_profile_history(profile)

        trace = DecisionTraceEntry(
            trace_id=f"trace_{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            trigger_type="pattern_detected",
            source_signal_ids=pattern.signal_ids,
            pattern_id=pattern.pattern_id,
            previous_profile_version=previous_version,
            new_profile_version=profile.version,
            weight_changes=weight_changes,
            rationale=(
                f"Pattern detected: {pattern.signal_count} {pattern.feedback_type.value} "
                f"signals. Applied weight shifts to affected areas."
            ),
        )

        logger.info(
            f"Applied pattern update to profile: project={project_id} "
            f"pattern={pattern.pattern_id} type={pattern.feedback_type.value} "
            f"signals={pattern.signal_count} version={previous_version}->{profile.version}"
        )
        return trace

    # =========================================================================
    # Query Methods
    # =========================================================================

    async def get_signals(
        self,
        project_id: str,
        feedback_type: Optional[FeedbackType] = None,
        limit: int = 50,
    ) -> List[FeedbackSignal]:
        """Get feedback signals for a project.

        Args:
            project_id: Project to query
            feedback_type: Optional filter by type
            limit: Maximum signals to return

        Returns:
            List of FeedbackSignal, most recent first
        """
        signals = self._signals.get(project_id, [])
        if feedback_type:
            signals = [s for s in signals if s.feedback_type == feedback_type]
        return sorted(signals, key=lambda s: s.timestamp, reverse=True)[:limit]

    async def get_patterns(
        self,
        project_id: str,
    ) -> List[FeedbackPattern]:
        """Get detected patterns for a project.

        Args:
            project_id: Project to query

        Returns:
            List of FeedbackPattern
        """
        return self._patterns.get(project_id, [])

    async def get_decision_trace(
        self,
        project_id: str,
        limit: int = 20,
    ) -> List[DecisionTraceEntry]:
        """Get decision trace entries for a project.

        Args:
            project_id: Project to query
            limit: Maximum entries to return

        Returns:
            List of DecisionTraceEntry, most recent first
        """
        entries = self._decision_trace.get(project_id, [])
        return sorted(entries, key=lambda e: e.timestamp, reverse=True)[:limit]

    # =========================================================================
    # Redis Persistence
    # =========================================================================

    async def _load_from_redis(self) -> None:
        """Load signals and patterns from Redis on initialization."""
        if not self._redis:
            return

        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis._redis.scan(
                    cursor,
                    match=self._key("signals:*"),
                    count=100,
                )
                for key in keys:
                    try:
                        raw = await self._redis._redis.get(key)
                        if raw:
                            data = raw.decode() if isinstance(raw, bytes) else raw
                            signal_list = json.loads(data)
                            key_str = key.decode() if isinstance(key, bytes) else key
                            project_id = key_str.rsplit(":", 1)[-1]
                            self._signals[project_id] = [
                                FeedbackSignal(**s) for s in signal_list
                            ]
                    except Exception as e:
                        logger.error(f"Error loading feedback signals: {e}")
                if cursor == 0:
                    break

            logger.info(
                f"Loaded feedback signals for {len(self._signals)} projects from Redis"
            )
        except Exception as e:
            logger.error(f"Error loading feedback data from Redis: {e}")

    async def _save_signal_to_redis(self, signal: FeedbackSignal) -> None:
        """Save signal to Redis."""
        if not self._redis:
            return

        try:
            key = self._key(f"signals:{signal.project_id}")
            signals = self._signals.get(signal.project_id, [])
            # Keep last 200 signals per project
            recent = signals[-200:]
            data = json.dumps([s.model_dump(mode="json") for s in recent])
            await self._redis._redis.set(key, data)
        except Exception as e:
            logger.error(f"Error saving feedback signal to Redis: {e}")

    async def _save_trace_to_redis(self, trace: DecisionTraceEntry) -> None:
        """Save decision trace entry to Redis."""
        if not self._redis:
            return

        try:
            key = self._key(f"trace:{trace.project_id}")
            data = trace.model_dump_json()
            await self._redis._redis.lpush(key, data)
            await self._redis._redis.ltrim(key, 0, 99)  # Keep last 100 entries
        except Exception as e:
            logger.error(f"Error saving decision trace to Redis: {e}")


# =============================================================================
# Global Instance
# =============================================================================


_feedback_aggregation_service: Optional[FeedbackAggregationService] = None


def get_feedback_aggregation_service() -> FeedbackAggregationService:
    """Get the global feedback aggregation service instance."""
    if _feedback_aggregation_service is None:
        raise RuntimeError("Feedback aggregation service not initialized")
    return _feedback_aggregation_service


def set_feedback_aggregation_service(
    service: Optional[FeedbackAggregationService],
) -> None:
    """Set the global feedback aggregation service instance."""
    global _feedback_aggregation_service
    _feedback_aggregation_service = service
