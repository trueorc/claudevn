"""Conflict Detection Service for planner-level conflict identification.

Detects and classifies conflicts across four categories:
1. Goal-to-goal: Competing goals via intent conflict detection
2. Goal-to-reality: Goal intent undermined by worker feedback patterns
3. Dependency: Circular or unresolvable dependency chains
4. Resource: Capability/compute demands exceeding availability

Integrates with:
- GoalIntentService for goal-to-goal intent conflicts
- FeedbackAggregationService for goal-to-reality detection
- PlannerProfileService for profile context
- DecisionTraceEntry for traceability

Reference: docs/work_management_framework.md — Sections 10.1, 11, 12
"""

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from models.conflict import (
    AuthorityRule,
    ConflictReport,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    DEFAULT_AUTHORITY_RULES,
    PlannerHandling,
    ResolutionAuthority,
    SuggestedResolution,
    TensionElement,
    UserResponse,
    UserResponseType,
)
from models.feedback import (
    DecisionTraceEntry,
    FeedbackPattern,
    FeedbackType,
)
from models.work_map import Goal, GoalConflict, GoalIntentType

logger = logging.getLogger(__name__)

# =============================================================================
# Intent-to-feedback contradiction mapping
# =============================================================================

# Maps goal intent types to the feedback patterns that contradict them.
# When a goal's primary intent is X, but worker feedback is dominated by
# patterns of type Y, there's a goal-to-reality conflict.
INTENT_FEEDBACK_CONTRADICTIONS: Dict[GoalIntentType, List[FeedbackType]] = {
    # "Focus on testing" but workers report systemic blockers
    GoalIntentType.QUALITY_FOCUSED: [FeedbackType.BLOCKER],
    # "Build new features" but workers report challenges and blockers
    GoalIntentType.EXPANSION: [FeedbackType.BLOCKER, FeedbackType.CHALLENGE],
    # "Harden/stabilize" but workers discover new requirements
    GoalIntentType.CONSOLIDATION: [FeedbackType.REQUIREMENT],
    # "Invest in specific area" but workers report challenges in that area
    GoalIntentType.TARGETED_INVESTMENT: [FeedbackType.CHALLENGE],
}

# Severity score thresholds for classification
SEVERITY_THRESHOLDS = {
    ConflictSeverity.LOW: 0.0,
    ConflictSeverity.MEDIUM: 0.3,
    ConflictSeverity.HIGH: 0.6,
    ConflictSeverity.CRITICAL: 0.85,
}


def _score_to_severity(score: float) -> ConflictSeverity:
    """Convert a numeric severity score to a ConflictSeverity level."""
    if score >= SEVERITY_THRESHOLDS[ConflictSeverity.CRITICAL]:
        return ConflictSeverity.CRITICAL
    elif score >= SEVERITY_THRESHOLDS[ConflictSeverity.HIGH]:
        return ConflictSeverity.HIGH
    elif score >= SEVERITY_THRESHOLDS[ConflictSeverity.MEDIUM]:
        return ConflictSeverity.MEDIUM
    return ConflictSeverity.LOW


def _determine_authority(
    conflict_type: ConflictType,
    severity: ConflictSeverity,
    authority_rules: Optional[List[AuthorityRule]] = None,
) -> ResolutionAuthority:
    """Determine resolution authority based on type and severity.

    Uses authority rules to determine whether a conflict should be
    resolved autonomously or surfaced to the user.
    """
    rules = authority_rules or DEFAULT_AUTHORITY_RULES
    for rule in rules:
        if rule.conflict_type != conflict_type:
            continue
        severity_order = [
            ConflictSeverity.LOW,
            ConflictSeverity.MEDIUM,
            ConflictSeverity.HIGH,
            ConflictSeverity.CRITICAL,
        ]
        threshold_idx = severity_order.index(rule.severity_threshold)
        severity_idx = severity_order.index(severity)
        if severity_idx >= threshold_idx:
            return ResolutionAuthority.USER_REQUIRED
        return rule.authority

    # Default: surface HIGH and CRITICAL to user
    if severity in (ConflictSeverity.HIGH, ConflictSeverity.CRITICAL):
        return ResolutionAuthority.USER_REQUIRED
    return ResolutionAuthority.AUTONOMOUS


class ConflictDetectionService:
    """Service for detecting and managing planner-level conflicts.

    Provides detection methods for each conflict type and maintains
    a registry of active conflicts per project.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        # project_id -> list of conflict reports
        self._conflicts: Dict[str, List[ConflictReport]] = defaultdict(list)
        self._authority_rules: List[AuthorityRule] = list(DEFAULT_AUTHORITY_RULES)

    def _key(self, key: str) -> str:
        """Get prefixed Redis key."""
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}conflicts:{key}"

    # =========================================================================
    # Goal-to-Goal Conflict Detection
    # =========================================================================

    def detect_goal_to_goal_conflicts(
        self,
        project_id: str,
        goal_conflicts: List[GoalConflict],
        goals: List[Goal],
    ) -> List[ConflictReport]:
        """Detect goal-to-goal conflicts from GoalConflict objects.

        Wraps existing GoalConflict objects (from GoalIntentService) into
        full ConflictReport objects with surfacing protocol fields.

        Args:
            project_id: Project to detect conflicts for
            goal_conflicts: GoalConflict objects from intent service
            goals: Active goals for context

        Returns:
            List of ConflictReport objects
        """
        reports = []
        goals_by_id = {g.goal_id: g for g in goals}

        for gc in goal_conflicts:
            goal_a = goals_by_id.get(gc.goal_id_a)
            goal_b = goals_by_id.get(gc.goal_id_b)

            severity = _score_to_severity(gc.severity)
            authority = _determine_authority(
                ConflictType.GOAL_TO_GOAL, severity, self._authority_rules
            )

            # Build tension elements
            tension_elements = []
            if goal_a:
                tension_elements.append(TensionElement(
                    element_type="goal",
                    element_id=gc.goal_id_a,
                    label=goal_a.title,
                    detail=f"Primary intent: {goal_a.primary_intent.value if goal_a.primary_intent else 'unknown'}",
                ))
            if goal_b:
                tension_elements.append(TensionElement(
                    element_type="goal",
                    element_id=gc.goal_id_b,
                    label=goal_b.title,
                    detail=f"Primary intent: {goal_b.primary_intent.value if goal_b.primary_intent else 'unknown'}",
                ))

            # Determine planner handling
            handling = self._goal_conflict_handling(goal_a, goal_b, gc)

            # Build suggested resolutions
            resolutions = self._goal_conflict_resolutions(goal_a, goal_b, gc)

            report = ConflictReport(
                conflict_id=gc.conflict_id,
                project_id=project_id,
                conflict_type=ConflictType.GOAL_TO_GOAL,
                severity=severity,
                severity_score=gc.severity,
                title=f"Goal conflict: {goal_a.title if goal_a else gc.goal_id_a} vs {goal_b.title if goal_b else gc.goal_id_b}",
                description=gc.description,
                tension_elements=tension_elements,
                planner_handling=handling,
                suggested_resolutions=resolutions,
                resolution_authority=authority,
                detected_at=gc.detected_at,
            )
            reports.append(report)

        return reports

    def _goal_conflict_handling(
        self,
        goal_a: Optional[Goal],
        goal_b: Optional[Goal],
        gc: GoalConflict,
    ) -> PlannerHandling:
        """Determine how the planner is handling a goal-to-goal conflict."""
        if not goal_a or not goal_b:
            return PlannerHandling(
                approach="Unable to determine handling — goal data missing",
                reasoning="One or both goals could not be found",
            )

        # Determine which goal the profile favors
        favored = None
        reasoning_parts = []

        # Check reconciliation weights
        if goal_a.reconciliation_weight is not None and goal_b.reconciliation_weight is not None:
            if goal_a.reconciliation_weight > goal_b.reconciliation_weight:
                favored = goal_a.title
                reasoning_parts.append(
                    f"User-set reconciliation weight favors '{goal_a.title}' "
                    f"({goal_a.reconciliation_weight} vs {goal_b.reconciliation_weight})"
                )
            elif goal_b.reconciliation_weight > goal_a.reconciliation_weight:
                favored = goal_b.title
                reasoning_parts.append(
                    f"User-set reconciliation weight favors '{goal_b.title}' "
                    f"({goal_b.reconciliation_weight} vs {goal_a.reconciliation_weight})"
                )
        elif goal_a.reconciliation_weight is not None:
            favored = goal_a.title
            reasoning_parts.append(f"Only '{goal_a.title}' has a user-set weight")
        elif goal_b.reconciliation_weight is not None:
            favored = goal_b.title
            reasoning_parts.append(f"Only '{goal_b.title}' has a user-set weight")

        # Fall back to intent strength
        if not favored:
            if goal_a.intent_strength > goal_b.intent_strength:
                favored = goal_a.title
                reasoning_parts.append(
                    f"Stronger intent signal for '{goal_a.title}' "
                    f"({goal_a.intent_strength} vs {goal_b.intent_strength})"
                )
            elif goal_b.intent_strength > goal_a.intent_strength:
                favored = goal_b.title
                reasoning_parts.append(
                    f"Stronger intent signal for '{goal_b.title}' "
                    f"({goal_b.intent_strength} vs {goal_a.intent_strength})"
                )
            else:
                reasoning_parts.append("Both goals have equal intent strength")

        approach = (
            f"Reconciling by favoring '{favored}' in profile weights"
            if favored
            else "Balancing both goals equally in profile weights"
        )

        if gc.is_irreconcilable:
            approach = f"Conflict is irreconcilable (severity {gc.severity}). " + approach

        return PlannerHandling(
            approach=approach,
            favored_side=favored,
            reasoning="; ".join(reasoning_parts) if reasoning_parts else "No clear signal to favor either goal",
        )

    def _goal_conflict_resolutions(
        self,
        goal_a: Optional[Goal],
        goal_b: Optional[Goal],
        gc: GoalConflict,
    ) -> List[SuggestedResolution]:
        """Generate suggested resolutions for a goal-to-goal conflict."""
        resolutions = []

        if gc.resolution_hint:
            resolutions.append(SuggestedResolution(
                response_type=UserResponseType.SET_PRIORITY,
                description=gc.resolution_hint,
                expected_impact="Planner will weight goals according to your specified priority",
            ))

        resolutions.append(SuggestedResolution(
            response_type=UserResponseType.ADJUST_GOAL,
            description="Modify one goal's language to reduce the tension between intents",
            expected_impact="Intent re-classification may eliminate the conflict",
        ))
        resolutions.append(SuggestedResolution(
            response_type=UserResponseType.ACCEPT_TRADEOFF,
            description="Accept the planner's current reconciliation approach",
            expected_impact="Conflict will be marked as resolved with current handling",
        ))

        return resolutions

    # =========================================================================
    # Goal-to-Reality Conflict Detection
    # =========================================================================

    def detect_goal_to_reality_conflicts(
        self,
        project_id: str,
        goals: List[Goal],
        feedback_patterns: List[FeedbackPattern],
    ) -> List[ConflictReport]:
        """Detect when goal intent is undermined by worker feedback patterns.

        Checks if active feedback patterns contradict the dominant goal
        intent. For example, a quality_focused goal intent contradicted
        by systemic blocker patterns from workers.

        Args:
            project_id: Project to detect conflicts for
            goals: Active goals with classified intents
            feedback_patterns: Detected feedback patterns

        Returns:
            List of ConflictReport objects
        """
        reports = []

        for goal in goals:
            if not goal.primary_intent:
                continue

            contradicting_types = INTENT_FEEDBACK_CONTRADICTIONS.get(
                goal.primary_intent, []
            )
            if not contradicting_types:
                continue

            for pattern in feedback_patterns:
                if pattern.feedback_type not in contradicting_types:
                    continue

                # Severity based on pattern signal count and goal intent strength
                base_severity = min(1.0, (pattern.signal_count / 5) * 0.5)
                severity_score = round(
                    min(1.0, base_severity + goal.intent_strength * 0.3), 3
                )
                severity = _score_to_severity(severity_score)
                authority = _determine_authority(
                    ConflictType.GOAL_TO_REALITY, severity, self._authority_rules
                )

                report = ConflictReport(
                    conflict_id=f"conflict_{uuid.uuid4().hex[:12]}",
                    project_id=project_id,
                    conflict_type=ConflictType.GOAL_TO_REALITY,
                    severity=severity,
                    severity_score=severity_score,
                    title=(
                        f"Goal '{goal.title}' intent contradicted by "
                        f"worker {pattern.feedback_type.value} pattern"
                    ),
                    description=(
                        f"Goal '{goal.title}' has {goal.primary_intent.value} intent, "
                        f"but {pattern.signal_count} worker signals indicate "
                        f"{pattern.feedback_type.value} conditions that undermine this intent."
                    ),
                    tension_elements=[
                        TensionElement(
                            element_type="goal",
                            element_id=goal.goal_id,
                            label=goal.title,
                            detail=f"Intent: {goal.primary_intent.value} (strength: {goal.intent_strength})",
                        ),
                        TensionElement(
                            element_type="feedback_pattern",
                            element_id=pattern.pattern_id,
                            label=f"{pattern.feedback_type.value} pattern ({pattern.signal_count} signals)",
                            detail=pattern.description,
                        ),
                    ],
                    planner_handling=PlannerHandling(
                        approach=(
                            f"Profile is weighted toward {goal.primary_intent.value} "
                            f"per goal intent, but worker feedback is pulling in a "
                            f"different direction"
                        ),
                        reasoning=(
                            f"Worker feedback pattern ({pattern.signal_count} "
                            f"{pattern.feedback_type.value} signals) contradicts "
                            f"the {goal.primary_intent.value} goal intent"
                        ),
                    ),
                    suggested_resolutions=[
                        SuggestedResolution(
                            response_type=UserResponseType.ADJUST_GOAL,
                            description=(
                                f"Adjust '{goal.title}' to account for the "
                                f"{pattern.feedback_type.value} conditions workers are reporting"
                            ),
                            expected_impact="Goal intent will be reclassified, reducing the tension",
                        ),
                        SuggestedResolution(
                            response_type=UserResponseType.CLARIFY_INTENT,
                            description=(
                                f"Clarify that {goal.primary_intent.value} intent should "
                                f"be maintained despite worker feedback"
                            ),
                            expected_impact="Planner will increase confidence on current profile weights",
                        ),
                        SuggestedResolution(
                            response_type=UserResponseType.ACCEPT_TRADEOFF,
                            description="Accept that progress toward this goal will be slower due to ground conditions",
                            expected_impact="Conflict marked as acknowledged, planner continues balancing",
                        ),
                    ],
                    resolution_authority=authority,
                )
                reports.append(report)

        return reports

    # =========================================================================
    # Dependency Conflict Detection
    # =========================================================================

    def detect_dependency_conflicts(
        self,
        project_id: str,
        dependencies: Dict[str, List[str]],
        item_labels: Optional[Dict[str, str]] = None,
    ) -> List[ConflictReport]:
        """Detect circular or unresolvable dependency chains.

        Args:
            project_id: Project to detect conflicts for
            dependencies: Map of item_id -> list of dependency item_ids
            item_labels: Optional map of item_id -> human-readable label

        Returns:
            List of ConflictReport objects for circular dependencies
        """
        reports = []
        labels = item_labels or {}

        # Detect circular dependencies using DFS
        cycles = self._find_cycles(dependencies)

        for cycle in cycles:
            severity_score = min(1.0, 0.6 + len(cycle) * 0.05)
            severity = _score_to_severity(severity_score)
            authority = _determine_authority(
                ConflictType.DEPENDENCY, severity, self._authority_rules
            )
            # Circular dependencies always require user intervention
            if len(cycle) > 0:
                authority = ResolutionAuthority.USER_REQUIRED

            cycle_labels = [labels.get(item_id, item_id) for item_id in cycle]
            cycle_str = " -> ".join(cycle_labels + [cycle_labels[0]])

            report = ConflictReport(
                conflict_id=f"conflict_{uuid.uuid4().hex[:12]}",
                project_id=project_id,
                conflict_type=ConflictType.DEPENDENCY,
                severity=severity,
                severity_score=severity_score,
                title=f"Circular dependency: {len(cycle)} items",
                description=f"Circular dependency chain detected: {cycle_str}",
                tension_elements=[
                    TensionElement(
                        element_type="dependency",
                        element_id=item_id,
                        label=labels.get(item_id, item_id),
                        detail=f"Part of circular chain with {len(cycle)} items",
                    )
                    for item_id in cycle
                ],
                planner_handling=PlannerHandling(
                    approach="Items in the cycle cannot be sequenced — all are blocked",
                    reasoning="Each item in the cycle depends on another item that hasn't completed",
                ),
                suggested_resolutions=[
                    SuggestedResolution(
                        response_type=UserResponseType.ADJUST_GOAL,
                        description="Remove or redefine one dependency in the cycle to break it",
                        expected_impact="Unblocks all items in the cycle for sequencing",
                    ),
                    SuggestedResolution(
                        response_type=UserResponseType.CLARIFY_INTENT,
                        description="Clarify which item should be completed first",
                        expected_impact="Planner can remove the inferred dependency and sequence correctly",
                    ),
                ],
                resolution_authority=authority,
            )
            reports.append(report)

        return reports

    def _find_cycles(self, dependencies: Dict[str, List[str]]) -> List[List[str]]:
        """Find all cycles in a dependency graph using DFS.

        Returns:
            List of cycles, where each cycle is a list of item IDs
        """
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycles: List[List[str]] = []
        path: List[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for dep in dependencies.get(node, []):
                if dep not in visited:
                    dfs(dep)
                elif dep in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(dep)
                    cycle = path[cycle_start:]
                    # Normalize to avoid duplicates (start with smallest ID)
                    min_idx = cycle.index(min(cycle))
                    normalized = cycle[min_idx:] + cycle[:min_idx]
                    if normalized not in cycles:
                        cycles.append(normalized)

            path.pop()
            rec_stack.discard(node)

        for node in dependencies:
            if node not in visited:
                dfs(node)

        return cycles

    # =========================================================================
    # Resource Conflict Detection
    # =========================================================================

    def detect_resource_conflicts(
        self,
        project_id: str,
        resource_demands: List[Dict],
        available_resources: List[Dict],
    ) -> List[ConflictReport]:
        """Detect when plan demands exceed available resources.

        Args:
            project_id: Project to detect conflicts for
            resource_demands: List of dicts with 'task_id', 'capability', 'priority'
            available_resources: List of dicts with 'worker_id', 'capabilities'

        Returns:
            List of ConflictReport objects
        """
        reports = []

        # Build capability -> available workers mapping
        capability_workers: Dict[str, List[str]] = defaultdict(list)
        for resource in available_resources:
            for cap in resource.get("capabilities", []):
                capability_workers[cap].append(resource.get("worker_id", "unknown"))

        # Group demands by capability
        capability_demands: Dict[str, List[Dict]] = defaultdict(list)
        for demand in resource_demands:
            cap = demand.get("capability", "")
            if cap:
                capability_demands[cap].append(demand)

        # Check for contention: multiple high-priority demands on limited workers
        for cap, demands in capability_demands.items():
            workers = capability_workers.get(cap, [])

            if not workers:
                # Capability gap: no workers can provide this
                severity_score = 0.8
                severity = _score_to_severity(severity_score)
                authority = _determine_authority(
                    ConflictType.RESOURCE, severity, self._authority_rules
                )
                report = ConflictReport(
                    conflict_id=f"conflict_{uuid.uuid4().hex[:12]}",
                    project_id=project_id,
                    conflict_type=ConflictType.RESOURCE,
                    severity=severity,
                    severity_score=severity_score,
                    title=f"No workers available for capability: {cap}",
                    description=(
                        f"{len(demands)} task(s) require '{cap}' capability, "
                        f"but no available workers provide it."
                    ),
                    tension_elements=[
                        TensionElement(
                            element_type="task",
                            element_id=d.get("task_id", "unknown"),
                            label=d.get("task_id", "unknown"),
                            detail=f"Requires capability: {cap}",
                        )
                        for d in demands
                    ],
                    planner_handling=PlannerHandling(
                        approach="Tasks requiring this capability are blocked",
                        reasoning=f"No registered worker provides '{cap}'",
                    ),
                    suggested_resolutions=[
                        SuggestedResolution(
                            response_type=UserResponseType.ADJUST_GOAL,
                            description="Redefine tasks to use available capabilities",
                            expected_impact="Tasks can be assigned to existing workers",
                        ),
                    ],
                    resolution_authority=authority,
                )
                reports.append(report)

            elif len(demands) > len(workers):
                # Worker contention: more demands than workers
                severity_score = min(1.0, 0.4 + (len(demands) - len(workers)) * 0.15)
                severity = _score_to_severity(severity_score)
                authority = _determine_authority(
                    ConflictType.RESOURCE, severity, self._authority_rules
                )
                report = ConflictReport(
                    conflict_id=f"conflict_{uuid.uuid4().hex[:12]}",
                    project_id=project_id,
                    conflict_type=ConflictType.RESOURCE,
                    severity=severity,
                    severity_score=severity_score,
                    title=f"Worker contention for capability: {cap}",
                    description=(
                        f"{len(demands)} tasks need '{cap}' but only "
                        f"{len(workers)} worker(s) available."
                    ),
                    tension_elements=[
                        TensionElement(
                            element_type="task",
                            element_id=d.get("task_id", "unknown"),
                            label=d.get("task_id", "unknown"),
                            detail=f"Priority: {d.get('priority', 'unknown')}",
                        )
                        for d in demands
                    ],
                    planner_handling=PlannerHandling(
                        approach="Sequencing tasks by priority to share limited workers",
                        favored_side="Higher priority tasks assigned first",
                        reasoning=f"{len(demands)} demands for {len(workers)} workers",
                    ),
                    suggested_resolutions=[
                        SuggestedResolution(
                            response_type=UserResponseType.SET_PRIORITY,
                            description="Set explicit priorities on competing tasks",
                            expected_impact="Planner will sequence based on your priority preferences",
                        ),
                        SuggestedResolution(
                            response_type=UserResponseType.ACCEPT_TRADEOFF,
                            description="Accept sequential execution of competing tasks",
                            expected_impact="Tasks will be executed in priority order, not in parallel",
                        ),
                    ],
                    resolution_authority=authority,
                )
                reports.append(report)

        return reports

    # =========================================================================
    # Incremental Resource Conflict Storage
    # =========================================================================

    async def store_resource_conflicts(
        self,
        project_id: str,
        resource_reports: List[ConflictReport],
    ) -> None:
        """Store resource conflicts, replacing previous resource conflicts only.

        Merges new resource conflict reports into the project's conflict list
        without affecting other conflict types (goal-to-goal, dependency, etc.).

        Args:
            project_id: Project to store conflicts for
            resource_reports: New resource conflict reports to store
        """
        existing = self._conflicts.get(project_id, [])

        # Keep all non-resource conflicts, replace resource conflicts
        non_resource = [
            c for c in existing if c.conflict_type != ConflictType.RESOURCE
        ]
        self._conflicts[project_id] = non_resource + resource_reports

        await self._save_conflicts_to_redis(project_id)

        # Record decision traces for new resource conflicts
        for conflict in resource_reports:
            await self._record_conflict_identified_trace(project_id, conflict)

        if resource_reports:
            logger.info(
                f"Stored {len(resource_reports)} resource conflicts for "
                f"project {project_id} (kept {len(non_resource)} other conflicts)"
            )

    # =========================================================================
    # Full Detection Sweep
    # =========================================================================

    async def detect_all_conflicts(
        self,
        project_id: str,
        goals: Optional[List[Goal]] = None,
        goal_conflicts: Optional[List[GoalConflict]] = None,
        feedback_patterns: Optional[List[FeedbackPattern]] = None,
        dependencies: Optional[Dict[str, List[str]]] = None,
        item_labels: Optional[Dict[str, str]] = None,
        resource_demands: Optional[List[Dict]] = None,
        available_resources: Optional[List[Dict]] = None,
    ) -> List[ConflictReport]:
        """Run all conflict detection checks and return unified results.

        Runs whichever detection checks have the required data provided.

        Args:
            project_id: Project to detect conflicts for
            goals: Active goals (needed for goal-to-goal and goal-to-reality)
            goal_conflicts: Pre-detected GoalConflict objects from intent service
            feedback_patterns: Detected feedback patterns (for goal-to-reality)
            dependencies: Dependency graph (for dependency conflicts)
            item_labels: Human-readable labels for dependency items
            resource_demands: Resource demands (for resource conflicts)
            available_resources: Available resources (for resource conflicts)

        Returns:
            List of all detected ConflictReport objects
        """
        all_conflicts: List[ConflictReport] = []

        # Goal-to-goal
        if goal_conflicts and goals:
            g2g = self.detect_goal_to_goal_conflicts(
                project_id, goal_conflicts, goals
            )
            all_conflicts.extend(g2g)
            logger.info(f"Detected {len(g2g)} goal-to-goal conflicts for project {project_id}")

        # Goal-to-reality
        if goals and feedback_patterns:
            g2r = self.detect_goal_to_reality_conflicts(
                project_id, goals, feedback_patterns
            )
            all_conflicts.extend(g2r)
            logger.info(f"Detected {len(g2r)} goal-to-reality conflicts for project {project_id}")

        # Dependency
        if dependencies:
            dep = self.detect_dependency_conflicts(
                project_id, dependencies, item_labels
            )
            all_conflicts.extend(dep)
            logger.info(f"Detected {len(dep)} dependency conflicts for project {project_id}")

        # Resource
        if resource_demands is not None and available_resources is not None:
            res = self.detect_resource_conflicts(
                project_id, resource_demands, available_resources
            )
            all_conflicts.extend(res)
            logger.info(f"Detected {len(res)} resource conflicts for project {project_id}")

        # Store results
        self._conflicts[project_id] = all_conflicts
        await self._save_conflicts_to_redis(project_id)

        # Record decision traces for identified conflicts
        for conflict in all_conflicts:
            await self._record_conflict_identified_trace(project_id, conflict)

        return all_conflicts

    # =========================================================================
    # Conflict Management
    # =========================================================================

    async def get_conflicts(
        self,
        project_id: str,
        conflict_type: Optional[ConflictType] = None,
        status: Optional[ConflictStatus] = None,
        surfaceable_only: bool = False,
    ) -> List[ConflictReport]:
        """Get conflicts for a project with optional filters.

        Args:
            project_id: Project to query
            conflict_type: Optional filter by type
            status: Optional filter by status
            surfaceable_only: Only return conflicts that should be surfaced

        Returns:
            List of ConflictReport objects
        """
        conflicts = self._conflicts.get(project_id, [])

        if conflict_type:
            conflicts = [c for c in conflicts if c.conflict_type == conflict_type]
        if status:
            conflicts = [c for c in conflicts if c.status == status]
        if surfaceable_only:
            conflicts = [c for c in conflicts if c.should_surface()]

        return conflicts

    async def resolve_conflict(
        self,
        project_id: str,
        conflict_id: str,
        response: UserResponse,
    ) -> Optional[ConflictReport]:
        """Record a user's response to a surfaced conflict.

        Args:
            project_id: Project the conflict belongs to
            conflict_id: ID of the conflict to resolve
            response: User's response

        Returns:
            Updated ConflictReport, or None if not found
        """
        conflicts = self._conflicts.get(project_id, [])
        for conflict in conflicts:
            if conflict.conflict_id == conflict_id:
                conflict.resolve_by_user(response)
                await self._save_conflicts_to_redis(project_id)

                # Record decision trace for conflict resolution
                await self._record_conflict_resolved_trace(
                    project_id, conflict, response
                )

                logger.info(
                    f"Conflict {conflict_id} resolved by user: "
                    f"{response.response_type.value}"
                )
                return conflict

        return None

    # =========================================================================
    # Decision Traceability
    # =========================================================================

    async def _record_conflict_identified_trace(
        self,
        project_id: str,
        conflict: ConflictReport,
    ) -> None:
        """Record a decision trace for conflict identification."""
        try:
            from services.decision_trace_service import get_decision_trace_service
            from models.decision_trace import (
                DecisionImpact,
                DecisionPointType,
                DecisionTrigger,
            )

            service = get_decision_trace_service()
            element_ids = [e.element_id for e in conflict.tension_elements]
            trace = await service.record(
                project_id=project_id,
                decision_type=DecisionPointType.CONFLICT_IDENTIFIED,
                trigger=DecisionTrigger(
                    trigger_type="conflict_detection",
                    source_id=conflict.conflict_id,
                    source_type="conflict",
                    description=f"Detected {conflict.conflict_type.value} conflict",
                ),
                decision_summary=conflict.title,
                key_factors=[
                    f"Conflict type: {conflict.conflict_type.value}",
                    f"Severity: {conflict.severity.value} ({conflict.severity_score})",
                    f"Authority: {conflict.resolution_authority.value}",
                ],
                impact=DecisionImpact(
                    affected_item_ids=element_ids,
                ),
            )

            # Link the trace back to the conflict report
            conflict.decision_trace_ids.append(trace.trace_id)
        except Exception as e:
            logger.debug(f"Could not record conflict identification trace: {e}")

    async def _record_conflict_resolved_trace(
        self,
        project_id: str,
        conflict: ConflictReport,
        response: UserResponse,
    ) -> None:
        """Record a decision trace for conflict resolution."""
        try:
            from services.decision_trace_service import get_decision_trace_service
            from models.decision_trace import (
                DecisionImpact,
                DecisionPointType,
                DecisionTrigger,
            )

            service = get_decision_trace_service()
            await service.record(
                project_id=project_id,
                decision_type=DecisionPointType.CONFLICT_RESOLVED,
                trigger=DecisionTrigger(
                    trigger_type="user_response",
                    source_id=conflict.conflict_id,
                    source_type="conflict",
                    description=f"User resolved {conflict.conflict_type.value} conflict",
                ),
                decision_summary=(
                    f"Conflict '{conflict.title}' resolved via "
                    f"{response.response_type.value}: {response.description}"
                ),
                key_factors=[
                    f"Response type: {response.response_type.value}",
                    f"Affected goals: {', '.join(response.affected_goal_ids) or 'none'}",
                ],
                impact=DecisionImpact(
                    affected_item_ids=[e.element_id for e in conflict.tension_elements],
                ),
                related_trace_ids=conflict.decision_trace_ids,
            )
        except Exception as e:
            logger.debug(f"Could not record conflict resolution trace: {e}")

    # =========================================================================
    # Redis Persistence
    # =========================================================================

    async def _save_conflicts_to_redis(self, project_id: str) -> None:
        """Save conflicts to Redis."""
        if not self._redis:
            return

        try:
            import json
            key = self._key(project_id)
            conflicts = self._conflicts.get(project_id, [])
            data = json.dumps([c.model_dump(mode="json") for c in conflicts])
            await self._redis._redis.set(key, data)
        except Exception as e:
            logger.error(f"Error saving conflicts to Redis: {e}")

    async def _load_conflicts_from_redis(self, project_id: str) -> None:
        """Load conflicts from Redis."""
        if not self._redis:
            return

        try:
            import json
            key = self._key(project_id)
            raw = await self._redis._redis.get(key)
            if raw:
                data = raw.decode() if isinstance(raw, bytes) else raw
                conflict_list = json.loads(data)
                self._conflicts[project_id] = [
                    ConflictReport(**c) for c in conflict_list
                ]
        except Exception as e:
            logger.error(f"Error loading conflicts from Redis: {e}")


# =============================================================================
# Global Instance
# =============================================================================


_conflict_detection_service: Optional[ConflictDetectionService] = None


def get_conflict_detection_service() -> ConflictDetectionService:
    """Get the global conflict detection service instance."""
    if _conflict_detection_service is None:
        raise RuntimeError("Conflict detection service not initialized")
    return _conflict_detection_service


def set_conflict_detection_service(
    service: Optional[ConflictDetectionService],
) -> None:
    """Set the global conflict detection service instance."""
    global _conflict_detection_service
    _conflict_detection_service = service
