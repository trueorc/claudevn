"""Work Planner Service for Slim Claude Code.

Analyzes decomposed issues and creates optimized execution plans.

Supports two planning modes:
1. Phase-based (legacy): Linear topological phases (ExecutionPhase)
2. Bucket tree (v1.0): Priority bucket tree driven by planner profile

The bucket tree approach replaces flat phase-based plans with hierarchical
strategic groupings where buckets cut across the ontology. Tasks are placed
into buckets based on characterization output and planner profile weights.
"""

import logging
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from models.characterization import CharacterizationResult, CharacterizationStatus
from models.goal_decomposer import (
    DecomposedIssue,
    EstimatedComplexity,
    GoalDecompositionResult,
)
from models.planner_profile import (
    PlannerProfile,
    PolicyActionType,
    PolicyConditionType,
    ProfileWeights,
)
from models.priority_bucket import (
    BucketCriterion,
    BucketCriterionType,
    BucketDefinition,
    BucketItem,
    BucketTree,
    ItemReadiness,
    PriorityBucket,
)
from models.work_planner import (
    ExecutionPhase,
    PlanConstraints,
    PlanRisk,
    RiskSeverity,
    WorkPlan,
    WorkPlannerConfig,
)

logger = logging.getLogger(__name__)


class CyclicDependencyError(Exception):
    """Raised when a cyclic dependency is detected in the issue graph."""

    def __init__(self, cycle: List[str], message: str = "Cyclic dependency detected"):
        self.cycle = cycle
        self.message = f"{message}: {' -> '.join(cycle)}"
        super().__init__(self.message)


class WorkPlannerService:
    """Service for creating execution plans from decomposed issues.

    Analyzes dependency graphs, identifies parallelization opportunities,
    assesses risks, and creates phased execution plans.
    """

    def __init__(self, config: Optional[WorkPlannerConfig] = None):
        """Initialize the Work Planner service.

        Args:
            config: Service configuration
        """
        self._config = config or WorkPlannerConfig()

    async def create_plan(
        self,
        goal_id: str,
        decomposition_id: str,
        issues: List[DecomposedIssue],
        dependency_graph: Dict[str, List[str]],
        constraints: Optional[PlanConstraints] = None,
    ) -> WorkPlan:
        """Create an execution plan from decomposed issues.

        Args:
            goal_id: Source goal ID
            decomposition_id: Source decomposition ID
            issues: List of decomposed issues
            dependency_graph: Issue dependencies (issue_id -> blocked_by)
            constraints: Optional planning constraints

        Returns:
            WorkPlan with phases, critical path, risks, and recommendations

        Raises:
            CyclicDependencyError: If cyclic dependency is detected
        """
        plan_id = f"plan-{uuid.uuid4().hex[:12]}"

        logger.info(
            f"Creating execution plan {plan_id} for goal {goal_id} "
            f"with {len(issues)} issues"
        )

        # Build lookup maps
        issue_map = {issue.temp_id: issue for issue in issues}

        # Detect cycles first
        cycle = self._detect_cycle(issues, dependency_graph)
        if cycle:
            raise CyclicDependencyError(cycle)

        # Calculate execution phases using topological sort
        phases = self._calculate_phases(
            issues=issues,
            dependency_graph=dependency_graph,
            constraints=constraints,
        )

        # Identify critical path
        critical_path = self._calculate_critical_path(
            issues=issues,
            dependency_graph=dependency_graph,
            issue_map=issue_map,
        )

        # Assess risks
        risks = self._assess_risks(
            issues=issues,
            dependency_graph=dependency_graph,
            issue_map=issue_map,
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            issues=issues,
            phases=phases,
            critical_path=critical_path,
            risks=risks,
            constraints=constraints,
        )

        # Estimate duration
        estimated_duration = self._estimate_duration(
            phases=phases,
            issue_map=issue_map,
            constraints=constraints,
        )

        plan = WorkPlan(
            plan_id=plan_id,
            goal_id=goal_id,
            decomposition_id=decomposition_id,
            phases=phases,
            estimated_duration=estimated_duration,
            critical_path=critical_path,
            risks=risks,
            recommendations=recommendations,
        )

        logger.info(
            f"Created plan {plan_id} with {len(phases)} phases, "
            f"{len(critical_path)} issues on critical path, "
            f"{len(risks)} risks identified"
        )

        return plan

    async def create_plan_from_decomposition(
        self,
        decomposition: GoalDecompositionResult,
        constraints: Optional[PlanConstraints] = None,
    ) -> WorkPlan:
        """Create an execution plan from a GoalDecompositionResult.

        Convenience method that extracts necessary data from decomposition.

        Args:
            decomposition: Goal decomposition result
            constraints: Optional planning constraints

        Returns:
            WorkPlan with phases, critical path, risks, and recommendations
        """
        return await self.create_plan(
            goal_id=decomposition.goal_id,
            decomposition_id=decomposition.decomposition_id,
            issues=decomposition.issues,
            dependency_graph=decomposition.dependency_graph,
            constraints=constraints,
        )

    def _detect_cycle(
        self,
        issues: List[DecomposedIssue],
        dependency_graph: Dict[str, List[str]],
    ) -> Optional[List[str]]:
        """Detect cyclic dependencies in the issue graph.

        Uses DFS with path tracking to find cycles.

        Args:
            issues: List of decomposed issues
            dependency_graph: Issue dependencies

        Returns:
            List of issue IDs in the cycle, or None if no cycle
        """
        # Build adjacency list for dependents (who depends on me)
        dependents: Dict[str, List[str]] = defaultdict(list)
        all_ids = {issue.temp_id for issue in issues}

        for issue in issues:
            for blocked_by in issue.blocked_by:
                if blocked_by in all_ids:
                    dependents[blocked_by].append(issue.temp_id)

        # DFS to detect cycle
        visited: Set[str] = set()
        path: Set[str] = set()
        path_list: List[str] = []

        def dfs(node: str) -> Optional[List[str]]:
            if node in path:
                # Found cycle, extract it
                cycle_start = path_list.index(node)
                return path_list[cycle_start:] + [node]

            if node in visited:
                return None

            visited.add(node)
            path.add(node)
            path_list.append(node)

            for dependent in dependents.get(node, []):
                cycle = dfs(dependent)
                if cycle:
                    return cycle

            path.remove(node)
            path_list.pop()
            return None

        for issue in issues:
            if issue.temp_id not in visited:
                cycle = dfs(issue.temp_id)
                if cycle:
                    return cycle

        return None

    def _calculate_phases(
        self,
        issues: List[DecomposedIssue],
        dependency_graph: Dict[str, List[str]],
        constraints: Optional[PlanConstraints] = None,
    ) -> List[ExecutionPhase]:
        """Calculate execution phases using topological sort.

        Groups issues into phases based on dependencies. Issues with
        no remaining dependencies are grouped together and can run
        in parallel.

        Args:
            issues: List of decomposed issues
            dependency_graph: Issue dependencies
            constraints: Optional planning constraints

        Returns:
            List of ExecutionPhase objects
        """
        if not issues:
            return []

        # Build dependency counts
        all_ids = {issue.temp_id for issue in issues}
        in_degree: Dict[str, int] = {issue.temp_id: 0 for issue in issues}

        for issue in issues:
            for dep in issue.blocked_by:
                if dep in all_ids:
                    in_degree[issue.temp_id] += 1

        # Get priority overrides from constraints
        priority_override = set()
        if constraints and constraints.priority_override:
            priority_override = set(constraints.priority_override)

        phases: List[ExecutionPhase] = []
        phase_number = 1
        remaining = dict(in_degree)

        while remaining:
            # Find all issues with no remaining dependencies
            ready = [tid for tid, count in remaining.items() if count == 0]

            if not ready:
                # Should not happen if no cycles, but handle gracefully
                logger.warning("No ready issues but remaining issues exist")
                ready = list(remaining.keys())

            # Sort ready issues: priority overrides first, then by original order
            ready.sort(
                key=lambda tid: (
                    0 if tid in priority_override else 1,
                    list(all_ids).index(tid) if tid in all_ids else 999,
                )
            )

            # Apply max_parallel constraint
            max_parallel = self._config.default_max_parallel
            if constraints and constraints.max_parallel:
                max_parallel = constraints.max_parallel

            # Split into chunks if exceeds max_parallel
            for i in range(0, len(ready), max_parallel):
                chunk = ready[i : i + max_parallel]

                # Determine if gate is needed
                gate = None
                if len(chunk) >= self._config.phase_gate_threshold:
                    gate = f"Review {len(chunk)} issues before proceeding"

                # Create phase description
                issue_titles = []
                for tid in chunk[:3]:  # Limit to first 3 for brevity
                    for issue in issues:
                        if issue.temp_id == tid:
                            issue_titles.append(issue.title)
                            break

                description = ", ".join(issue_titles)
                if len(chunk) > 3:
                    description += f" (+{len(chunk) - 3} more)"

                phase = ExecutionPhase(
                    phase_number=phase_number,
                    issues=chunk,
                    parallel=len(chunk) > 1,
                    gate=gate,
                    description=description,
                )
                phases.append(phase)
                phase_number += 1

            # Remove processed issues and update dependents
            for tid in ready:
                del remaining[tid]

            for issue in issues:
                if issue.temp_id in remaining:
                    for dep in issue.blocked_by:
                        if dep in ready:
                            remaining[issue.temp_id] -= 1

        return phases

    def _calculate_critical_path(
        self,
        issues: List[DecomposedIssue],
        dependency_graph: Dict[str, List[str]],
        issue_map: Dict[str, DecomposedIssue],
    ) -> List[str]:
        """Calculate the critical path through the dependency graph.

        The critical path is the longest path considering issue complexity
        as the weight. Issues on this path directly impact total duration.

        Args:
            issues: List of decomposed issues
            dependency_graph: Issue dependencies
            issue_map: Map of issue temp_id to DecomposedIssue

        Returns:
            List of issue temp_ids on the critical path
        """
        if not issues:
            return []

        all_ids = {issue.temp_id for issue in issues}

        # Build adjacency list for dependents (who depends on me)
        dependents: Dict[str, List[str]] = defaultdict(list)
        for issue in issues:
            for blocked_by in issue.blocked_by:
                if blocked_by in all_ids:
                    dependents[blocked_by].append(issue.temp_id)

        # Calculate longest path to each node (considering complexity weight)
        longest_path: Dict[str, Tuple[float, List[str]]] = {}

        def get_weight(issue_id: str) -> float:
            """Get complexity weight for an issue."""
            issue = issue_map.get(issue_id)
            if not issue:
                return self._config.complexity_hours.get("m", 4.0)
            return self._config.complexity_hours.get(
                issue.estimated_complexity.value, 4.0
            )

        def calculate_longest(issue_id: str) -> Tuple[float, List[str]]:
            """Calculate longest path ending at this issue."""
            if issue_id in longest_path:
                return longest_path[issue_id]

            issue = issue_map.get(issue_id)
            if not issue:
                return (0, [])

            # Base case: no dependencies
            weight = get_weight(issue_id)
            if not issue.blocked_by:
                result = (weight, [issue_id])
                longest_path[issue_id] = result
                return result

            # Find longest path among dependencies
            max_path_length = 0.0
            max_path: List[str] = []

            for dep in issue.blocked_by:
                if dep in all_ids:
                    dep_length, dep_path = calculate_longest(dep)
                    if dep_length > max_path_length:
                        max_path_length = dep_length
                        max_path = dep_path

            result = (max_path_length + weight, max_path + [issue_id])
            longest_path[issue_id] = result
            return result

        # Calculate longest path for all issues
        for issue in issues:
            calculate_longest(issue.temp_id)

        # Find the overall longest path
        if not longest_path:
            return []

        max_length = 0.0
        critical = []
        for issue_id, (length, path) in longest_path.items():
            if length > max_length:
                max_length = length
                critical = path

        return critical

    def _assess_risks(
        self,
        issues: List[DecomposedIssue],
        dependency_graph: Dict[str, List[str]],
        issue_map: Dict[str, DecomposedIssue],
    ) -> List[PlanRisk]:
        """Assess risks in the execution plan.

        Identifies risks based on:
        - High dependency count (bottleneck risk)
        - High complexity (scope creep risk)
        - Skill requirements (resource risk)

        Args:
            issues: List of decomposed issues
            dependency_graph: Issue dependencies
            issue_map: Map of issue temp_id to DecomposedIssue

        Returns:
            List of PlanRisk objects
        """
        risks: List[PlanRisk] = []
        risk_count = 0
        all_ids = {issue.temp_id for issue in issues}

        # Count how many issues depend on each issue
        dependent_count: Dict[str, int] = defaultdict(int)
        for issue in issues:
            for blocked_by in issue.blocked_by:
                if blocked_by in all_ids:
                    dependent_count[blocked_by] += 1

        # Check each issue for risks
        for issue in issues:
            # High dependency count (many issues blocked by this one)
            if dependent_count[issue.temp_id] >= self._config.high_dependency_threshold:
                risk_count += 1
                risks.append(
                    PlanRisk(
                        risk_id=f"risk-{risk_count:03d}",
                        description=(
                            f"Issue '{issue.title}' blocks "
                            f"{dependent_count[issue.temp_id]} other issues"
                        ),
                        severity=RiskSeverity.HIGH,
                        mitigation=(
                            "Prioritize this issue and consider breaking it "
                            "into smaller pieces"
                        ),
                        affected_issues=[issue.temp_id],
                    )
                )

            # High complexity
            high_complexity = self._config.complex_issue_threshold
            complexity_order = ["xs", "s", "m", "l", "xl"]
            issue_complexity_idx = complexity_order.index(
                issue.estimated_complexity.value
            )
            threshold_idx = complexity_order.index(high_complexity)

            if issue_complexity_idx >= threshold_idx:
                risk_count += 1
                risks.append(
                    PlanRisk(
                        risk_id=f"risk-{risk_count:03d}",
                        description=(
                            f"Issue '{issue.title}' has high complexity "
                            f"({issue.estimated_complexity.value})"
                        ),
                        severity=RiskSeverity.MEDIUM,
                        mitigation=(
                            "Consider breaking into smaller subtasks or "
                            "allowing extra buffer time"
                        ),
                        affected_issues=[issue.temp_id],
                    )
                )

            # Many dependencies (this issue blocked by many others)
            if len(issue.blocked_by) >= self._config.high_dependency_threshold:
                risk_count += 1
                risks.append(
                    PlanRisk(
                        risk_id=f"risk-{risk_count:03d}",
                        description=(
                            f"Issue '{issue.title}' depends on "
                            f"{len(issue.blocked_by)} other issues"
                        ),
                        severity=RiskSeverity.MEDIUM,
                        mitigation=(
                            "Monitor blocking issues closely; delays will cascade"
                        ),
                        affected_issues=[issue.temp_id] + list(issue.blocked_by),
                    )
                )

        # Check for skill concentration risk
        skill_issues: Dict[str, List[str]] = defaultdict(list)
        for issue in issues:
            for skill in issue.required_skills:
                skill_issues[skill].append(issue.temp_id)

        for skill, issue_ids in skill_issues.items():
            if len(issue_ids) > len(issues) * 0.5:  # Skill needed by >50% of issues
                risk_count += 1
                risks.append(
                    PlanRisk(
                        risk_id=f"risk-{risk_count:03d}",
                        description=(
                            f"Skill '{skill}' required by {len(issue_ids)} issues "
                            f"({len(issue_ids)*100//len(issues)}% of total)"
                        ),
                        severity=RiskSeverity.LOW,
                        mitigation=(
                            "Ensure sufficient resources with this skill are available"
                        ),
                        affected_issues=issue_ids,
                    )
                )

        return risks

    def _generate_recommendations(
        self,
        issues: List[DecomposedIssue],
        phases: List[ExecutionPhase],
        critical_path: List[str],
        risks: List[PlanRisk],
        constraints: Optional[PlanConstraints] = None,
    ) -> List[str]:
        """Generate optimization recommendations for the plan.

        Args:
            issues: List of decomposed issues
            phases: Calculated execution phases
            critical_path: Critical path issue IDs
            risks: Identified risks
            constraints: Planning constraints

        Returns:
            List of recommendation strings
        """
        recommendations: List[str] = []

        # Recommendation based on phase count
        if len(phases) > 5:
            recommendations.append(
                f"Plan has {len(phases)} phases. Consider parallelizing more "
                "work to reduce total phases."
            )

        # Recommendation based on critical path
        if len(critical_path) > len(issues) * 0.5:
            recommendations.append(
                "Critical path includes majority of issues. Look for opportunities "
                "to parallelize work to reduce total duration."
            )

        # Recommendation based on high risks
        high_risks = [r for r in risks if r.severity == RiskSeverity.HIGH]
        if high_risks:
            recommendations.append(
                f"Found {len(high_risks)} high-severity risks. Address these "
                "before starting execution."
            )

        # Recommendation for single-issue phases
        single_phases = [p for p in phases if len(p.issues) == 1]
        if len(single_phases) > len(phases) * 0.5:
            recommendations.append(
                "Many phases have only one issue. Review dependencies to see "
                "if more parallelization is possible."
            )

        # Recommendation based on constraints
        if constraints:
            if constraints.deadline:
                recommendations.append(
                    "Plan has a deadline constraint. Monitor progress closely "
                    "and consider contingency plans for delays."
                )
            if constraints.excluded_skills:
                recommendations.append(
                    f"Some skills are excluded: {', '.join(constraints.excluded_skills)}. "
                    "Verify all issues can still be completed."
                )

        # If no recommendations, add a positive note
        if not recommendations:
            recommendations.append(
                "Plan looks well-balanced with good parallelization opportunities."
            )

        return recommendations

    def _estimate_duration(
        self,
        phases: List[ExecutionPhase],
        issue_map: Dict[str, DecomposedIssue],
        constraints: Optional[PlanConstraints] = None,
    ) -> str:
        """Estimate total duration for the plan.

        Calculates based on phase structure and complexity weights.
        Parallel issues within a phase take max(individual durations).

        Args:
            phases: Execution phases
            issue_map: Map of issue temp_id to DecomposedIssue
            constraints: Planning constraints

        Returns:
            Human-readable duration string
        """
        total_hours = 0.0

        for phase in phases:
            if phase.parallel:
                # Parallel: take max duration in phase
                max_duration = 0.0
                for issue_id in phase.issues:
                    issue = issue_map.get(issue_id)
                    if issue:
                        hours = self._config.complexity_hours.get(
                            issue.estimated_complexity.value, 4.0
                        )
                        max_duration = max(max_duration, hours)
                total_hours += max_duration
            else:
                # Sequential: sum all durations
                for issue_id in phase.issues:
                    issue = issue_map.get(issue_id)
                    if issue:
                        total_hours += self._config.complexity_hours.get(
                            issue.estimated_complexity.value, 4.0
                        )

        # Convert to human-readable format
        if total_hours < 8:
            return f"{total_hours:.1f} hours"
        elif total_hours < 40:
            days = total_hours / 8
            return f"{days:.1f} days"
        else:
            weeks = total_hours / 40
            return f"{weeks:.1f} weeks"

    # ========================================================================
    # Bucket Tree Planning (v1.0)
    # ========================================================================

    async def create_bucket_tree(
        self,
        project_id: str,
        profile: PlannerProfile,
        items: List[DecomposedIssue],
        characterizations: Dict[str, CharacterizationResult],
        dependency_graph: Dict[str, List[str]],
    ) -> BucketTree:
        """Create a priority bucket tree from characterized work items.

        Replaces phase-based planning with strategic bucket groupings
        driven by the planner profile and characterization output.

        Args:
            project_id: Project context
            profile: Planner profile defining bucket strategy and weights
            items: Decomposed issues to place
            characterizations: Characterization results keyed by item_id
            dependency_graph: Dependencies (item_id → list of blocked_by)

        Returns:
            BucketTree with items placed and ordered
        """
        tree_id = f"tree-{uuid.uuid4().hex[:12]}"

        logger.info(
            f"Creating bucket tree {tree_id} for project {project_id} "
            f"with {len(items)} items, profile {profile.profile_id}"
        )

        # Detect cycles
        cycle = self._detect_cycle(items, dependency_graph)
        if cycle:
            raise CyclicDependencyError(cycle)

        # Step 1: Define buckets from profile
        buckets = self._define_buckets_from_profile(profile)

        # Step 2: Place items into buckets
        all_ids = {item.temp_id for item in items}
        self._place_items_in_buckets(
            buckets=buckets,
            items=items,
            characterizations=characterizations,
            dependency_graph=dependency_graph,
            profile=profile,
            all_ids=all_ids,
        )

        # Step 3: Sort items within each bucket
        for bucket in buckets:
            bucket.sort_items()

        tree = BucketTree(
            tree_id=tree_id,
            project_id=project_id,
            profile_id=profile.profile_id,
            buckets=buckets,
        )

        logger.info(
            f"Created bucket tree {tree_id}: {len(buckets)} buckets, "
            f"{tree.total_items} items, {tree.total_ready} ready"
        )

        return tree

    def _define_buckets_from_profile(
        self,
        profile: PlannerProfile,
    ) -> List[PriorityBucket]:
        """Define priority buckets from the planner profile.

        Creates strategic buckets based on profile weights. High-weight
        ontology categories get dedicated buckets. Policy rules with
        FORCE_BUCKET create additional buckets. A default catch-all
        bucket collects remaining items.

        Args:
            profile: Active planner profile

        Returns:
            List of PriorityBucket with definitions (empty of items)
        """
        buckets: List[PriorityBucket] = []
        rank = 1

        # Check for FORCE_BUCKET policy rules first — these create explicit buckets
        for rule in profile.get_enabled_rules():
            if rule.action_type == PolicyActionType.FORCE_BUCKET:
                target_bucket = rule.action_params.get("target_bucket", "")
                if not target_bucket:
                    continue

                # Build criteria from the rule's condition
                criteria = self._criteria_from_policy_rule(rule)

                buckets.append(PriorityBucket(
                    bucket_id=f"bucket-policy-{rule.rule_id}",
                    rank=rank,
                    definition=BucketDefinition(
                        name=rule.name,
                        description=rule.description or f"Policy-driven bucket: {rule.name}",
                        criteria=criteria,
                    ),
                ))
                rank += 1

        # Create buckets from high-weight ontology categories
        # Identify work types with weight >= 0.7
        high_weight_work_types = []
        for wt_key, wv in profile.weights.work_type_weights.items():
            if wv.weight >= 0.7:
                high_weight_work_types.append(wt_key)

        if high_weight_work_types:
            buckets.append(PriorityBucket(
                bucket_id=f"bucket-priority-work-types",
                rank=rank,
                definition=BucketDefinition(
                    name="High-priority work types",
                    description=f"Work types with elevated priority: {', '.join(high_weight_work_types)}",
                    criteria=[BucketCriterion(
                        criterion_type=BucketCriterionType.WORK_TYPE_IN,
                        params={"values": high_weight_work_types},
                    )],
                ),
            ))
            rank += 1

        # Identify lifecycle stages with weight >= 0.7
        high_weight_stages = []
        for ls_key, wv in profile.weights.lifecycle_stage_weights.items():
            if wv.weight >= 0.7:
                high_weight_stages.append(ls_key)

        if high_weight_stages:
            buckets.append(PriorityBucket(
                bucket_id=f"bucket-priority-stages",
                rank=rank,
                definition=BucketDefinition(
                    name="High-priority lifecycle stages",
                    description=f"Lifecycle stages with elevated priority: {', '.join(high_weight_stages)}",
                    criteria=[BucketCriterion(
                        criterion_type=BucketCriterionType.LIFECYCLE_STAGE_IN,
                        params={"values": high_weight_stages},
                    )],
                ),
            ))
            rank += 1

        # Default catch-all bucket
        buckets.append(PriorityBucket(
            bucket_id="bucket-default",
            rank=rank,
            definition=BucketDefinition(
                name="General work",
                description="Items not matching any specific bucket criteria",
                is_default=True,
            ),
        ))

        return buckets

    def _criteria_from_policy_rule(self, rule) -> List[BucketCriterion]:
        """Convert a policy rule's condition into bucket criteria."""
        criteria = []
        if rule.condition_type == PolicyConditionType.IN_ONTOLOGY_CATEGORY:
            category = rule.condition_params.get("category", "")
            values = rule.condition_params.get("values", [])
            type_map = {
                "work_type": BucketCriterionType.WORK_TYPE_IN,
                "lifecycle_stage": BucketCriterionType.LIFECYCLE_STAGE_IN,
                "technical_domain": BucketCriterionType.TECHNICAL_DOMAIN_IN,
                "cluster": BucketCriterionType.CLUSTER_IN,
            }
            criterion_type = type_map.get(category)
            if criterion_type and values:
                criteria.append(BucketCriterion(
                    criterion_type=criterion_type,
                    params={"values": values},
                ))
        elif rule.condition_type == PolicyConditionType.IN_CLUSTER:
            cluster_ids = rule.condition_params.get("cluster_ids", [])
            if cluster_ids:
                criteria.append(BucketCriterion(
                    criterion_type=BucketCriterionType.CLUSTER_IN,
                    params={"values": cluster_ids},
                ))
        elif rule.condition_type == PolicyConditionType.BLOCKING_COUNT_ABOVE:
            threshold = rule.condition_params.get("threshold", 0)
            criteria.append(BucketCriterion(
                criterion_type=BucketCriterionType.IS_BLOCKING,
                params={"min_count": threshold},
            ))
        return criteria

    def _place_items_in_buckets(
        self,
        buckets: List[PriorityBucket],
        items: List[DecomposedIssue],
        characterizations: Dict[str, CharacterizationResult],
        dependency_graph: Dict[str, List[str]],
        profile: PlannerProfile,
        all_ids: Set[str],
    ) -> None:
        """Place work items into the appropriate buckets.

        Evaluates each item's characterization against bucket criteria.
        Items matching multiple non-default buckets go into the
        highest-priority (lowest rank) match. Unmatched items go to the
        default bucket.

        Args:
            buckets: Defined buckets (mutated in place)
            items: Decomposed issues
            characterizations: Characterization results by item_id
            dependency_graph: Item dependencies
            profile: Active profile for weight computation
            all_ids: All item IDs for dependency resolution
        """
        default_bucket = None
        criteria_buckets = []
        for bucket in buckets:
            if bucket.definition.is_default:
                default_bucket = bucket
            else:
                criteria_buckets.append(bucket)

        # Sort criteria buckets by rank (lowest = highest priority)
        criteria_buckets.sort(key=lambda b: b.rank)

        for item in items:
            char_result = characterizations.get(item.temp_id)

            # Compute item metadata
            readiness = self._compute_readiness(
                item.temp_id, dependency_graph, all_ids
            )
            blocking_count = self._compute_blocking_count(
                item.temp_id, items, all_ids
            )
            priority_score = self._compute_priority_score(
                char_result, profile
            )

            bucket_item = BucketItem(
                item_id=item.temp_id,
                readiness=readiness,
                priority_score=priority_score,
                blocking_count=blocking_count,
            )

            # Try to place in the first matching criteria bucket
            placed = False
            for bucket in criteria_buckets:
                if self._item_matches_bucket(
                    item, char_result, bucket.definition.criteria, all_ids,
                    items, dependency_graph,
                ):
                    bucket.items.append(bucket_item)
                    placed = True
                    break

            # Fall through to default bucket
            if not placed and default_bucket:
                default_bucket.items.append(bucket_item)

    def _item_matches_bucket(
        self,
        item: DecomposedIssue,
        char_result: Optional[CharacterizationResult],
        criteria: List[BucketCriterion],
        all_ids: Set[str],
        items: List[DecomposedIssue],
        dependency_graph: Dict[str, List[str]],
    ) -> bool:
        """Check if an item matches all criteria for a bucket (AND logic).

        Returns True only if all criteria are satisfied.
        """
        if not criteria:
            return False

        for criterion in criteria:
            if not self._evaluate_criterion(
                criterion, item, char_result, all_ids, items, dependency_graph
            ):
                return False
        return True

    def _evaluate_criterion(
        self,
        criterion: BucketCriterion,
        item: DecomposedIssue,
        char_result: Optional[CharacterizationResult],
        all_ids: Set[str],
        items: List[DecomposedIssue],
        dependency_graph: Dict[str, List[str]],
    ) -> bool:
        """Evaluate a single bucket criterion against an item."""
        ct = criterion.criterion_type
        params = criterion.params

        if ct == BucketCriterionType.WORK_TYPE_IN:
            values = params.get("values", [])
            if char_result and char_result.ontology_tags:
                return char_result.ontology_tags.universal.work_type.value in values
            # Fallback to issue type hint
            return (item.issue_type or "") in values

        elif ct == BucketCriterionType.LIFECYCLE_STAGE_IN:
            values = params.get("values", [])
            if char_result and char_result.ontology_tags:
                return char_result.ontology_tags.universal.lifecycle_stage.value in values
            return False

        elif ct == BucketCriterionType.TECHNICAL_DOMAIN_IN:
            values = set(params.get("values", []))
            if char_result and char_result.ontology_tags:
                item_domains = {
                    d.value for d in char_result.ontology_tags.universal.technical_domains
                }
                return bool(item_domains & values)
            return False

        elif ct == BucketCriterionType.CLUSTER_IN:
            values = set(params.get("values", []))
            if char_result and char_result.ontology_tags:
                item_clusters = set(
                    char_result.ontology_tags.project_specific.cluster_ids
                )
                return bool(item_clusters & values)
            return False

        elif ct == BucketCriterionType.IS_BLOCKING:
            min_count = params.get("min_count", 1)
            blocking_count = self._compute_blocking_count(
                item.temp_id, items, all_ids
            )
            return blocking_count >= min_count

        elif ct == BucketCriterionType.DEPENDENCY_READY:
            readiness = self._compute_readiness(
                item.temp_id, dependency_graph, all_ids
            )
            return readiness == ItemReadiness.READY

        elif ct == BucketCriterionType.MATCH_ANY:
            # OR logic: at least one nested criterion must match
            return any(
                self._evaluate_criterion(
                    nested, item, char_result, all_ids, items, dependency_graph
                )
                for nested in criterion.nested
            )

        return False

    def _compute_readiness(
        self,
        item_id: str,
        dependency_graph: Dict[str, List[str]],
        all_ids: Set[str],
    ) -> ItemReadiness:
        """Compute the dependency readiness state of an item.

        An item is READY if all its dependencies are outside the current
        item set (i.e., already completed or external). BLOCKED if all
        dependencies are still pending. PARTIALLY_BLOCKED if some are resolved.
        """
        deps = dependency_graph.get(item_id, [])
        if not deps:
            return ItemReadiness.READY

        # Filter to deps within the current item set
        internal_deps = [d for d in deps if d in all_ids]
        if not internal_deps:
            return ItemReadiness.READY

        # All deps blocked → BLOCKED, some → PARTIALLY_BLOCKED
        # Since we don't have completion status here, treat all internal deps as blocking
        return ItemReadiness.BLOCKED

    def _compute_blocking_count(
        self,
        item_id: str,
        items: List[DecomposedIssue],
        all_ids: Set[str],
    ) -> int:
        """Count how many items this item blocks."""
        count = 0
        for item in items:
            if item_id in item.blocked_by and item.temp_id in all_ids:
                count += 1
        return count

    def _compute_priority_score(
        self,
        char_result: Optional[CharacterizationResult],
        profile: PlannerProfile,
    ) -> float:
        """Compute a priority score for an item based on profile weights.

        Combines ontology weights from the profile with the item's
        characterization tags to produce a 0.0-1.0 priority score.
        """
        if not char_result or not char_result.ontology_tags:
            return 0.5  # Neutral default for uncharacterized items

        tags = char_result.ontology_tags.universal
        weights = profile.weights

        # Average the relevant weights
        scores = []

        # Work type weight
        wt_weight = weights.get_weight("work_type", tags.work_type.value)
        scores.append(wt_weight)

        # Lifecycle stage weight
        ls_weight = weights.get_weight("lifecycle_stage", tags.lifecycle_stage.value)
        scores.append(ls_weight)

        # Technical domain weights — average across all domains
        if tags.technical_domains:
            domain_weights = [
                weights.get_weight("technical_domain", d.value)
                for d in tags.technical_domains
            ]
            scores.append(sum(domain_weights) / len(domain_weights))

        # Cluster weights — average if any
        cluster_ids = char_result.ontology_tags.project_specific.cluster_ids
        if cluster_ids:
            cluster_weights = [
                weights.get_weight("cluster", cid)
                for cid in cluster_ids
            ]
            scores.append(sum(cluster_weights) / len(cluster_weights))

        return sum(scores) / len(scores) if scores else 0.5


# Global service instance
_work_planner_service: Optional[WorkPlannerService] = None


def get_work_planner_service() -> WorkPlannerService:
    """Get the global Work Planner service instance."""
    global _work_planner_service
    if _work_planner_service is None:
        _work_planner_service = WorkPlannerService()
    return _work_planner_service


def set_work_planner_service(service: Optional[WorkPlannerService]) -> None:
    """Set the global Work Planner service instance."""
    global _work_planner_service
    _work_planner_service = service
