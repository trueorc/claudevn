"""Planner Focus and Goal Alignment Service.

Generates human-readable planner focus summaries and computes
goal-to-execution alignment metrics. Reads from planner profile,
goal, and issue services — purely read-only aggregation.

Reference: Issue #528
"""

import logging
from collections import Counter
from typing import Dict, List, Optional

from models.planner_focus import (
    AlignedWorkItem,
    GoalAlignmentEntry,
    GoalAlignmentSummary,
    PlannerFocusSummary,
    PolicyRuleSummary,
    WeightCategory,
    WeightEntry,
)
from models.planner_profile import PlannerProfile, PolicyActionType
from models.work_map import Goal, GoalStatus

logger = logging.getLogger(__name__)

# Human-readable labels for ontology keys
WORK_TYPE_LABELS = {
    "feature": "Features",
    "bug_fix": "Bug Fixes",
    "refactor": "Refactoring",
    "test": "Testing",
    "documentation": "Documentation",
    "infrastructure": "Infrastructure",
    "integration": "Integration",
}

LIFECYCLE_LABELS = {
    "design": "Design",
    "build": "Build",
    "test": "Test",
    "validate": "Validate",
    "deploy": "Deploy",
}

DOMAIN_LABELS = {
    "frontend": "Frontend",
    "backend": "Backend",
    "data": "Data",
    "api": "API",
    "security": "Security",
    "devops": "DevOps",
    "testing": "Testing",
    "documentation": "Documentation",
}

INTENT_DESCRIPTIONS = {
    "expansion": "Building new features and capabilities",
    "consolidation": "Stabilizing and hardening existing systems",
    "targeted_investment": "Focused investment in specific capability areas",
    "quality_focused": "Deep quality improvement and testing focus",
}

ACTION_LABELS = {
    PolicyActionType.ELEVATE_PRIORITY: "Elevate priority",
    PolicyActionType.PRESERVE_PRIORITY: "Preserve priority",
    PolicyActionType.DEPRIORITIZE: "Deprioritize",
    PolicyActionType.FORCE_BUCKET: "Force to bucket",
    PolicyActionType.SKIP: "Skip",
}


class PlannerFocusService:
    """Aggregation service for planner focus and goal alignment views.

    This service is stateless — it reads from existing services
    to compute summaries on demand.
    """

    async def get_focus_summary(
        self,
        project_id: str,
        profile: Optional[PlannerProfile],
        goals: List[Goal],
    ) -> PlannerFocusSummary:
        """Generate a planner focus summary for a project.

        Args:
            project_id: Project to summarize
            profile: Active planner profile (may be None)
            goals: Active goals for the project

        Returns:
            PlannerFocusSummary with weights and policy rules
        """
        if not profile:
            return PlannerFocusSummary(
                project_id=project_id,
                has_profile=False,
                optimization_target="No active planner profile. Select a work profile or create goals to activate the planner.",
                active_goal_count=len(goals),
            )

        # Build goal lookup for rule source labels
        goal_lookup: Dict[str, Goal] = {g.goal_id: g for g in goals}

        # Determine dominant intent
        primary_intent = self._determine_dominant_intent(goals)

        # Build optimization target description
        optimization_target = self._build_optimization_description(
            profile, goals, primary_intent
        )

        # Build weight categories
        weight_categories = self._build_weight_categories(profile)

        # Build policy rule summaries
        active_rules = self._build_rule_summaries(profile, goal_lookup)

        # Last trigger description
        last_trigger = None
        if profile.triggers:
            last = profile.triggers[-1]
            last_trigger = last.description

        # Preset info
        preset_name = None
        preset_label = None
        preset_color = None
        if profile.active_preset:
            preset_name = profile.active_preset
            preset_info = self._get_preset_info(profile.active_preset)
            if preset_info:
                preset_label = preset_info.get("label")
                preset_color = preset_info.get("color")

        # If profile has a preset but no goals, use the preset's optimization target
        if profile.active_preset and not goals:
            preset_info = self._get_preset_info(profile.active_preset)
            if preset_info:
                optimization_target = preset_info.get("optimization_target", optimization_target)

        return PlannerFocusSummary(
            project_id=project_id,
            has_profile=True,
            optimization_target=optimization_target,
            primary_intent=primary_intent,
            active_preset=preset_name,
            active_preset_label=preset_label,
            active_preset_color=preset_color,
            weight_categories=weight_categories,
            active_rules=active_rules,
            active_goal_count=len(profile.active_goal_ids),
            profile_version=profile.version,
            last_updated=profile.updated_at,
            last_trigger=last_trigger,
        )

    async def get_goal_alignment(
        self,
        project_id: str,
        goals: List[Goal],
        issues: List[dict],
        conflicts: Optional[List[dict]] = None,
    ) -> GoalAlignmentSummary:
        """Compute goal-to-execution alignment metrics.

        Args:
            project_id: Project to analyze
            goals: Active goals
            issues: All issues (as dicts with issue_id, title, status, goal_id)
            conflicts: Optional conflict data (goal_id_a, goal_id_b pairs)

        Returns:
            GoalAlignmentSummary with per-goal alignment data
        """
        # Build conflict map
        conflict_map: Dict[str, List[str]] = {}
        if conflicts:
            for c in conflicts:
                a = c.get("goal_id_a", "")
                b = c.get("goal_id_b", "")
                if a:
                    conflict_map.setdefault(a, []).append(b)
                if b:
                    conflict_map.setdefault(b, []).append(a)

        # Group issues by goal
        issues_by_goal: Dict[str, List[dict]] = {}
        unaligned_count = 0
        for issue in issues:
            goal_id = issue.get("goal_id")
            if goal_id:
                issues_by_goal.setdefault(goal_id, []).append(issue)
            else:
                unaligned_count += 1

        # Find multi-goal work items (items whose goal_id appears under multiple goals
        # or items that are depended on by items from other goals)
        # For simplicity: items tagged to one goal but blocking items in another
        goal_for_issue = {
            issue.get("issue_id"): issue.get("goal_id")
            for issue in issues if issue.get("goal_id")
        }

        total_issues = len(issues)
        total_active = sum(
            1 for i in issues
            if i.get("status") in ("ready", "in_progress", "assigned")
        )

        entries = []
        for goal in goals:
            goal_issues = issues_by_goal.get(goal.goal_id, [])
            completed = sum(1 for i in goal_issues if i.get("status") == "done")
            active = sum(
                1 for i in goal_issues
                if i.get("status") in ("ready", "in_progress", "assigned")
            )

            # Alignment = proportion of total active execution aligned to this goal
            alignment_pct = (active / total_active * 100) if total_active > 0 else 0.0

            # Gap detection: goal has issues but none are active
            has_gaps = len(goal_issues) > 0 and active == 0 and completed < len(goal_issues)
            gap_description = None
            if has_gaps:
                blocked = sum(1 for i in goal_issues if i.get("status") == "blocked")
                pending = sum(1 for i in goal_issues if i.get("status") == "backlog")
                parts = []
                if blocked > 0:
                    parts.append(f"{blocked} blocked")
                if pending > 0:
                    parts.append(f"{pending} in backlog")
                gap_description = f"No active work — {', '.join(parts)}" if parts else "No active work"

            # No issues at all is also a gap
            if len(goal_issues) == 0:
                has_gaps = True
                gap_description = "No issues created for this goal yet"

            # Conflict indicators
            competing = conflict_map.get(goal.goal_id, [])

            entries.append(GoalAlignmentEntry(
                goal_id=goal.goal_id,
                goal_title=goal.title,
                goal_status=goal.status.value if isinstance(goal.status, GoalStatus) else str(goal.status),
                goal_priority=goal.priority.value if hasattr(goal.priority, "value") else str(goal.priority),
                primary_intent=goal.primary_intent.value if goal.primary_intent else None,
                total_issues=len(goal_issues),
                active_issues=active,
                completed_issues=completed,
                alignment_percentage=round(alignment_pct, 1),
                has_gaps=has_gaps,
                gap_description=gap_description,
                competing_goal_ids=competing,
                has_conflicts=len(competing) > 0,
            ))

        # Overall alignment: percentage of issues that are linked to a goal
        overall = ((total_issues - unaligned_count) / total_issues * 100) if total_issues > 0 else 0.0

        return GoalAlignmentSummary(
            project_id=project_id,
            total_goals=len(goals),
            total_issues=total_issues,
            overall_alignment=round(overall, 1),
            unaligned_issue_count=unaligned_count,
            goals=entries,
        )

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _get_preset_info(self, preset_name: str) -> Optional[Dict]:
        """Get preset display info by name. Returns None if not found."""
        try:
            from models.work_profile_preset import PresetName, get_preset
            preset = get_preset(PresetName(preset_name))
            return {
                "label": preset.label,
                "color": preset.color,
                "optimization_target": preset.optimization_target,
            }
        except (ValueError, KeyError):
            return None

    def _determine_dominant_intent(self, goals: List[Goal]) -> Optional[str]:
        """Determine the dominant intent across active goals."""
        intents = [
            g.primary_intent.value for g in goals
            if g.primary_intent is not None
        ]
        if not intents:
            return None
        counts = Counter(intents)
        return counts.most_common(1)[0][0]

    def _build_optimization_description(
        self,
        profile: PlannerProfile,
        goals: List[Goal],
        primary_intent: Optional[str],
    ) -> str:
        """Build a human-readable optimization target description."""
        if not goals:
            return "No active goals influencing the planner."

        intent_desc = INTENT_DESCRIPTIONS.get(primary_intent, "")
        goal_count = len(profile.active_goal_ids)
        rule_count = len(profile.get_enabled_rules())

        parts = []
        if intent_desc:
            parts.append(f"Primary focus: {intent_desc}.")
        parts.append(f"Driven by {goal_count} active goal{'s' if goal_count != 1 else ''}.")
        if rule_count > 0:
            parts.append(f"{rule_count} policy rule{'s' if rule_count != 1 else ''} active.")

        # Top-priority work types
        top_weights = sorted(
            profile.weights.work_type_weights.items(),
            key=lambda x: x[1].weight,
            reverse=True,
        )[:3]
        if top_weights:
            top_labels = [
                WORK_TYPE_LABELS.get(k, k) for k, v in top_weights if v.weight >= 0.6
            ]
            if top_labels:
                parts.append(f"Prioritizing: {', '.join(top_labels)}.")

        return " ".join(parts)

    def _build_weight_categories(
        self,
        profile: PlannerProfile,
    ) -> List[WeightCategory]:
        """Build weight categories from profile for visualization."""
        categories = []

        # Work type weights
        if profile.weights.work_type_weights:
            entries = []
            for key, wv in sorted(
                profile.weights.work_type_weights.items(),
                key=lambda x: x[1].weight,
                reverse=True,
            ):
                entries.append(WeightEntry(
                    key=key,
                    weight=wv.weight,
                    confidence=wv.confidence.level.value,
                    label=WORK_TYPE_LABELS.get(key, key),
                ))
            categories.append(WeightCategory(
                category="work_type",
                label="Work Type",
                weights=entries,
            ))

        # Lifecycle stage weights
        if profile.weights.lifecycle_stage_weights:
            entries = []
            for key, wv in sorted(
                profile.weights.lifecycle_stage_weights.items(),
                key=lambda x: x[1].weight,
                reverse=True,
            ):
                entries.append(WeightEntry(
                    key=key,
                    weight=wv.weight,
                    confidence=wv.confidence.level.value,
                    label=LIFECYCLE_LABELS.get(key, key),
                ))
            categories.append(WeightCategory(
                category="lifecycle_stage",
                label="Lifecycle Stage",
                weights=entries,
            ))

        # Technical domain weights
        if profile.weights.technical_domain_weights:
            entries = []
            for key, wv in sorted(
                profile.weights.technical_domain_weights.items(),
                key=lambda x: x[1].weight,
                reverse=True,
            ):
                entries.append(WeightEntry(
                    key=key,
                    weight=wv.weight,
                    confidence=wv.confidence.level.value,
                    label=DOMAIN_LABELS.get(key, key),
                ))
            categories.append(WeightCategory(
                category="technical_domain",
                label="Technical Domain",
                weights=entries,
            ))

        # Cluster weights
        if profile.weights.cluster_weights:
            entries = []
            for key, wv in sorted(
                profile.weights.cluster_weights.items(),
                key=lambda x: x[1].weight,
                reverse=True,
            ):
                entries.append(WeightEntry(
                    key=key,
                    weight=wv.weight,
                    confidence=wv.confidence.level.value,
                    label=key,  # Cluster names are already readable
                ))
            categories.append(WeightCategory(
                category="cluster",
                label="Domain Clusters",
                weights=entries,
            ))

        return categories

    def _build_rule_summaries(
        self,
        profile: PlannerProfile,
        goal_lookup: Dict[str, Goal],
    ) -> List[PolicyRuleSummary]:
        """Build simplified rule summaries for display."""
        summaries = []
        for rule in profile.get_enabled_rules():
            source_title = None
            if rule.source_goal_id and rule.source_goal_id in goal_lookup:
                source_title = goal_lookup[rule.source_goal_id].title

            action_label = ACTION_LABELS.get(rule.action_type, rule.action_type.value)

            summaries.append(PolicyRuleSummary(
                name=rule.name,
                description=rule.description,
                action=action_label,
                confidence=rule.confidence.level.value,
                enabled=rule.enabled,
                source_goal_title=source_title,
            ))
        return summaries


# =============================================================================
# Global Instance
# =============================================================================

_planner_focus_service: Optional[PlannerFocusService] = None


def get_planner_focus_service() -> PlannerFocusService:
    """Get the global planner focus service instance."""
    if _planner_focus_service is None:
        raise RuntimeError("Planner focus service not initialized")
    return _planner_focus_service


def set_planner_focus_service(service: Optional[PlannerFocusService]) -> None:
    """Set the global planner focus service instance."""
    global _planner_focus_service
    _planner_focus_service = service
