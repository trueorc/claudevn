"""Tests for WorkPlannerService - Slim Claude Code work planning."""

import pytest
from datetime import datetime, timezone
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

from models.goal_decomposer import (
    DecomposedIssue,
    EstimatedComplexity,
    GoalDecompositionResult,
)
from models.work_planner import (
    ExecutionPhase,
    PlanConstraints,
    PlanRisk,
    RiskSeverity,
    WorkPlan,
    WorkPlannerConfig,
)
from services.work_planner import (
    CyclicDependencyError,
    WorkPlannerService,
    get_work_planner_service,
    set_work_planner_service,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def work_planner_service():
    """Create WorkPlannerService with default config."""
    config = WorkPlannerConfig(
        default_max_parallel=5,
        phase_gate_threshold=5,
    )
    return WorkPlannerService(config=config)


@pytest.fixture
def sample_issues():
    """Sample decomposed issues for testing."""
    return [
        DecomposedIssue(
            temp_id="issue-1",
            title="Set up database schema",
            description="Create the initial database schema.",
            issue_type="feature",
            priority="P1",
            area="database",
            required_skills=["sql", "postgres"],
            estimated_complexity=EstimatedComplexity.M,
            blocked_by=[],
            acceptance_criteria=["Schema created"],
        ),
        DecomposedIssue(
            temp_id="issue-2",
            title="Implement API endpoints",
            description="Create REST API endpoints.",
            issue_type="feature",
            priority="P1",
            area="api",
            required_skills=["python", "fastapi"],
            estimated_complexity=EstimatedComplexity.L,
            blocked_by=["issue-1"],
            acceptance_criteria=["API working"],
        ),
        DecomposedIssue(
            temp_id="issue-3",
            title="Add authentication",
            description="Implement JWT authentication.",
            issue_type="feature",
            priority="P0",
            area="api",
            required_skills=["python", "security"],
            estimated_complexity=EstimatedComplexity.L,
            blocked_by=["issue-2"],
            acceptance_criteria=["Auth working"],
        ),
        DecomposedIssue(
            temp_id="issue-4",
            title="Create frontend UI",
            description="Build React components.",
            issue_type="feature",
            priority="P2",
            area="frontend",
            required_skills=["react", "typescript"],
            estimated_complexity=EstimatedComplexity.L,
            blocked_by=["issue-2"],
            acceptance_criteria=["UI working"],
        ),
    ]


@pytest.fixture
def sample_dependency_graph():
    """Sample dependency graph matching sample_issues."""
    return {
        "issue-2": ["issue-1"],
        "issue-3": ["issue-2"],
        "issue-4": ["issue-2"],
    }


@pytest.fixture
def sample_decomposition(sample_issues, sample_dependency_graph):
    """Sample GoalDecompositionResult for testing."""
    return GoalDecompositionResult(
        goal_id="goal-001",
        decomposition_id="decomp-abc123",
        issues=sample_issues,
        dependency_graph=sample_dependency_graph,
        execution_phases=[["issue-1"], ["issue-2"], ["issue-3", "issue-4"]],
        confidence=0.85,
        reasoning="Test decomposition",
    )


# ============================================================================
# Model Tests - PlanConstraints
# ============================================================================


class TestPlanConstraintsModel:
    """Test PlanConstraints model."""

    def test_create_with_defaults(self):
        """Test creating PlanConstraints with defaults."""
        constraints = PlanConstraints()

        assert constraints.max_parallel is None
        assert constraints.priority_override is None
        assert constraints.deadline is None
        assert constraints.excluded_skills is None

    def test_create_with_all_fields(self):
        """Test creating PlanConstraints with all fields."""
        deadline = datetime.now(timezone.utc)
        constraints = PlanConstraints(
            max_parallel=3,
            priority_override=["issue-1", "issue-2"],
            deadline=deadline,
            excluded_skills=["react"],
        )

        assert constraints.max_parallel == 3
        assert constraints.priority_override == ["issue-1", "issue-2"]
        assert constraints.deadline == deadline
        assert constraints.excluded_skills == ["react"]


# ============================================================================
# Model Tests - ExecutionPhase
# ============================================================================


class TestExecutionPhaseModel:
    """Test ExecutionPhase model."""

    def test_create_phase(self):
        """Test creating ExecutionPhase."""
        phase = ExecutionPhase(
            phase_number=1,
            issues=["issue-1", "issue-2"],
            parallel=True,
            gate="Review before proceeding",
            description="Initial setup phase",
        )

        assert phase.phase_number == 1
        assert phase.issues == ["issue-1", "issue-2"]
        assert phase.parallel is True
        assert phase.gate == "Review before proceeding"
        assert phase.description == "Initial setup phase"

    def test_create_phase_with_defaults(self):
        """Test ExecutionPhase defaults."""
        phase = ExecutionPhase(phase_number=1)

        assert phase.issues == []
        assert phase.parallel is True
        assert phase.gate is None
        assert phase.description == ""


# ============================================================================
# Model Tests - PlanRisk
# ============================================================================


class TestPlanRiskModel:
    """Test PlanRisk model."""

    def test_create_risk(self):
        """Test creating PlanRisk."""
        risk = PlanRisk(
            risk_id="risk-001",
            description="High dependency bottleneck",
            severity=RiskSeverity.HIGH,
            mitigation="Prioritize this issue",
            affected_issues=["issue-1", "issue-2"],
        )

        assert risk.risk_id == "risk-001"
        assert risk.description == "High dependency bottleneck"
        assert risk.severity == RiskSeverity.HIGH
        assert risk.mitigation == "Prioritize this issue"
        assert risk.affected_issues == ["issue-1", "issue-2"]

    def test_risk_severity_enum(self):
        """Test RiskSeverity enum values."""
        assert RiskSeverity.LOW.value == "low"
        assert RiskSeverity.MEDIUM.value == "medium"
        assert RiskSeverity.HIGH.value == "high"


# ============================================================================
# Model Tests - WorkPlan
# ============================================================================


class TestWorkPlanModel:
    """Test WorkPlan model."""

    def test_create_work_plan(self):
        """Test creating WorkPlan."""
        phase = ExecutionPhase(
            phase_number=1,
            issues=["issue-1"],
            description="Phase 1",
        )
        risk = PlanRisk(
            risk_id="risk-001",
            description="Test risk",
        )

        plan = WorkPlan(
            plan_id="plan-abc123",
            goal_id="goal-001",
            decomposition_id="decomp-xyz",
            phases=[phase],
            estimated_duration="2 days",
            critical_path=["issue-1"],
            risks=[risk],
            recommendations=["Test recommendation"],
        )

        assert plan.plan_id == "plan-abc123"
        assert plan.goal_id == "goal-001"
        assert plan.decomposition_id == "decomp-xyz"
        assert len(plan.phases) == 1
        assert plan.estimated_duration == "2 days"
        assert plan.critical_path == ["issue-1"]
        assert len(plan.risks) == 1
        assert plan.recommendations == ["Test recommendation"]
        assert plan.created_at is not None

    def test_work_plan_defaults(self):
        """Test WorkPlan default values."""
        plan = WorkPlan(
            plan_id="plan-abc",
            goal_id="goal-001",
            decomposition_id="decomp-xyz",
        )

        assert plan.phases == []
        assert plan.estimated_duration == ""
        assert plan.critical_path == []
        assert plan.risks == []
        assert plan.recommendations == []


# ============================================================================
# Model Tests - WorkPlannerConfig
# ============================================================================


class TestWorkPlannerConfigModel:
    """Test WorkPlannerConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = WorkPlannerConfig()

        assert config.default_max_parallel == 5
        assert config.phase_gate_threshold == 5
        assert config.complexity_hours["m"] == 4.0
        assert config.high_dependency_threshold == 3
        assert config.complex_issue_threshold == "l"

    def test_custom_config(self):
        """Test custom configuration values."""
        config = WorkPlannerConfig(
            default_max_parallel=10,
            phase_gate_threshold=3,
            complexity_hours={"xs": 0.5, "s": 1.0, "m": 2.0, "l": 4.0, "xl": 8.0},
        )

        assert config.default_max_parallel == 10
        assert config.phase_gate_threshold == 3
        assert config.complexity_hours["m"] == 2.0


# ============================================================================
# Service Tests - Initialization
# ============================================================================


class TestWorkPlannerServiceInit:
    """Test WorkPlannerService initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default config."""
        service = WorkPlannerService()

        assert service._config is not None
        assert service._config.default_max_parallel == 5

    def test_init_with_custom_config(self):
        """Test initialization with custom config."""
        config = WorkPlannerConfig(default_max_parallel=10)
        service = WorkPlannerService(config=config)

        assert service._config.default_max_parallel == 10


# ============================================================================
# Service Tests - Plan Creation
# ============================================================================


class TestWorkPlannerServiceCreatePlan:
    """Test plan creation functionality."""

    @pytest.mark.asyncio
    async def test_create_plan_returns_work_plan(
        self,
        work_planner_service,
        sample_issues,
        sample_dependency_graph,
    ):
        """Test create_plan returns a WorkPlan."""
        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=sample_issues,
            dependency_graph=sample_dependency_graph,
        )

        assert isinstance(plan, WorkPlan)
        assert plan.goal_id == "goal-001"
        assert plan.decomposition_id == "decomp-abc123"
        assert plan.plan_id.startswith("plan-")

    @pytest.mark.asyncio
    async def test_create_plan_generates_phases(
        self,
        work_planner_service,
        sample_issues,
        sample_dependency_graph,
    ):
        """Test that phases are generated correctly."""
        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=sample_issues,
            dependency_graph=sample_dependency_graph,
        )

        # Should have 3 phases: db -> api -> (auth, ui)
        assert len(plan.phases) == 3

        # Phase 1: database
        assert "issue-1" in plan.phases[0].issues

        # Phase 2: api
        assert "issue-2" in plan.phases[1].issues

        # Phase 3: auth and ui in parallel
        assert set(plan.phases[2].issues) == {"issue-3", "issue-4"}
        assert plan.phases[2].parallel is True

    @pytest.mark.asyncio
    async def test_create_plan_from_decomposition(
        self,
        work_planner_service,
        sample_decomposition,
    ):
        """Test create_plan_from_decomposition convenience method."""
        plan = await work_planner_service.create_plan_from_decomposition(
            decomposition=sample_decomposition,
        )

        assert plan.goal_id == "goal-001"
        assert plan.decomposition_id == "decomp-abc123"
        assert len(plan.phases) == 3

    @pytest.mark.asyncio
    async def test_create_plan_empty_issues(self, work_planner_service):
        """Test create_plan with empty issues list."""
        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=[],
            dependency_graph={},
        )

        assert plan.phases == []
        assert plan.critical_path == []
        assert plan.risks == []

    @pytest.mark.asyncio
    async def test_create_plan_respects_max_parallel(
        self,
        sample_issues,
        sample_dependency_graph,
    ):
        """Test that max_parallel constraint is respected."""
        config = WorkPlannerConfig(default_max_parallel=1)
        service = WorkPlannerService(config=config)

        plan = await service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=sample_issues,
            dependency_graph=sample_dependency_graph,
        )

        # With max_parallel=1, issue-3 and issue-4 should be in separate phases
        for phase in plan.phases:
            assert len(phase.issues) <= 1

    @pytest.mark.asyncio
    async def test_create_plan_with_constraints(
        self,
        work_planner_service,
        sample_issues,
        sample_dependency_graph,
    ):
        """Test create_plan with constraints."""
        constraints = PlanConstraints(
            max_parallel=2,
            priority_override=["issue-1"],
        )

        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=sample_issues,
            dependency_graph=sample_dependency_graph,
            constraints=constraints,
        )

        # Max 2 issues per phase
        for phase in plan.phases:
            assert len(phase.issues) <= 2


# ============================================================================
# Service Tests - Cycle Detection
# ============================================================================


class TestCycleDetection:
    """Test cyclic dependency detection."""

    @pytest.mark.asyncio
    async def test_detects_simple_cycle(self, work_planner_service):
        """Test detection of simple A -> B -> A cycle."""
        issues = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Issue 1",
                description="Desc",
                blocked_by=["issue-2"],
            ),
            DecomposedIssue(
                temp_id="issue-2",
                title="Issue 2",
                description="Desc",
                blocked_by=["issue-1"],
            ),
        ]

        with pytest.raises(CyclicDependencyError) as exc_info:
            await work_planner_service.create_plan(
                goal_id="goal-001",
                decomposition_id="decomp-abc123",
                issues=issues,
                dependency_graph={
                    "issue-1": ["issue-2"],
                    "issue-2": ["issue-1"],
                },
            )

        assert "issue-1" in exc_info.value.cycle or "issue-2" in exc_info.value.cycle

    @pytest.mark.asyncio
    async def test_detects_longer_cycle(self, work_planner_service):
        """Test detection of A -> B -> C -> A cycle."""
        issues = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Issue 1",
                description="Desc",
                blocked_by=["issue-3"],
            ),
            DecomposedIssue(
                temp_id="issue-2",
                title="Issue 2",
                description="Desc",
                blocked_by=["issue-1"],
            ),
            DecomposedIssue(
                temp_id="issue-3",
                title="Issue 3",
                description="Desc",
                blocked_by=["issue-2"],
            ),
        ]

        with pytest.raises(CyclicDependencyError):
            await work_planner_service.create_plan(
                goal_id="goal-001",
                decomposition_id="decomp-abc123",
                issues=issues,
                dependency_graph={
                    "issue-1": ["issue-3"],
                    "issue-2": ["issue-1"],
                    "issue-3": ["issue-2"],
                },
            )

    @pytest.mark.asyncio
    async def test_no_false_positive_cycle(
        self,
        work_planner_service,
        sample_issues,
        sample_dependency_graph,
    ):
        """Test that valid graphs don't trigger cycle detection."""
        # Should not raise
        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=sample_issues,
            dependency_graph=sample_dependency_graph,
        )

        assert plan is not None


# ============================================================================
# Service Tests - Critical Path
# ============================================================================


class TestCriticalPathCalculation:
    """Test critical path calculation."""

    @pytest.mark.asyncio
    async def test_critical_path_linear_chain(self, work_planner_service):
        """Test critical path for linear dependency chain."""
        issues = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Issue 1",
                description="Desc",
                estimated_complexity=EstimatedComplexity.M,
            ),
            DecomposedIssue(
                temp_id="issue-2",
                title="Issue 2",
                description="Desc",
                blocked_by=["issue-1"],
                estimated_complexity=EstimatedComplexity.M,
            ),
            DecomposedIssue(
                temp_id="issue-3",
                title="Issue 3",
                description="Desc",
                blocked_by=["issue-2"],
                estimated_complexity=EstimatedComplexity.M,
            ),
        ]

        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=issues,
            dependency_graph={
                "issue-2": ["issue-1"],
                "issue-3": ["issue-2"],
            },
        )

        # All issues should be on critical path
        assert plan.critical_path == ["issue-1", "issue-2", "issue-3"]

    @pytest.mark.asyncio
    async def test_critical_path_parallel_branches(self, work_planner_service):
        """Test critical path chooses longest branch."""
        issues = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Root",
                description="Desc",
                estimated_complexity=EstimatedComplexity.S,  # 2 hours
            ),
            DecomposedIssue(
                temp_id="issue-2",
                title="Short branch",
                description="Desc",
                blocked_by=["issue-1"],
                estimated_complexity=EstimatedComplexity.S,  # 2 hours
            ),
            DecomposedIssue(
                temp_id="issue-3",
                title="Long branch",
                description="Desc",
                blocked_by=["issue-1"],
                estimated_complexity=EstimatedComplexity.XL,  # 16 hours
            ),
        ]

        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=issues,
            dependency_graph={
                "issue-2": ["issue-1"],
                "issue-3": ["issue-1"],
            },
        )

        # Critical path should go through longer branch
        assert "issue-1" in plan.critical_path
        assert "issue-3" in plan.critical_path
        assert "issue-2" not in plan.critical_path


# ============================================================================
# Service Tests - Risk Assessment
# ============================================================================


class TestRiskAssessment:
    """Test risk assessment functionality."""

    @pytest.mark.asyncio
    async def test_identifies_bottleneck_risk(self, work_planner_service):
        """Test identification of high-dependency bottleneck."""
        issues = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Core infrastructure",
                description="Base issue",
            ),
            DecomposedIssue(
                temp_id="issue-2",
                title="Dependent 1",
                description="Depends on core",
                blocked_by=["issue-1"],
            ),
            DecomposedIssue(
                temp_id="issue-3",
                title="Dependent 2",
                description="Depends on core",
                blocked_by=["issue-1"],
            ),
            DecomposedIssue(
                temp_id="issue-4",
                title="Dependent 3",
                description="Depends on core",
                blocked_by=["issue-1"],
            ),
        ]

        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=issues,
            dependency_graph={
                "issue-2": ["issue-1"],
                "issue-3": ["issue-1"],
                "issue-4": ["issue-1"],
            },
        )

        # Should have a high-severity risk for issue-1
        high_risks = [r for r in plan.risks if r.severity == RiskSeverity.HIGH]
        assert len(high_risks) >= 1
        assert any("issue-1" in r.affected_issues for r in high_risks)

    @pytest.mark.asyncio
    async def test_identifies_complexity_risk(self, work_planner_service):
        """Test identification of high-complexity risk."""
        issues = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Complex issue",
                description="Very complex",
                estimated_complexity=EstimatedComplexity.XL,
            ),
        ]

        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=issues,
            dependency_graph={},
        )

        # Should have a medium-severity risk for complexity
        medium_risks = [r for r in plan.risks if r.severity == RiskSeverity.MEDIUM]
        assert len(medium_risks) >= 1
        assert any("complexity" in r.description.lower() for r in medium_risks)


# ============================================================================
# Service Tests - Duration Estimation
# ============================================================================


class TestDurationEstimation:
    """Test duration estimation functionality."""

    @pytest.mark.asyncio
    async def test_estimates_hours_for_short_plans(self, work_planner_service):
        """Test that short plans show hours."""
        issues = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Quick issue",
                description="Desc",
                estimated_complexity=EstimatedComplexity.XS,  # 1 hour
            ),
        ]

        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=issues,
            dependency_graph={},
        )

        assert "hour" in plan.estimated_duration.lower()

    @pytest.mark.asyncio
    async def test_estimates_days_for_medium_plans(self, work_planner_service):
        """Test that medium plans show days."""
        issues = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Issue 1",
                description="Desc",
                estimated_complexity=EstimatedComplexity.L,  # 8 hours
            ),
            DecomposedIssue(
                temp_id="issue-2",
                title="Issue 2",
                description="Desc",
                blocked_by=["issue-1"],
                estimated_complexity=EstimatedComplexity.L,  # 8 hours
            ),
        ]

        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=issues,
            dependency_graph={"issue-2": ["issue-1"]},
        )

        assert "day" in plan.estimated_duration.lower()

    @pytest.mark.asyncio
    async def test_parallel_reduces_duration(self, work_planner_service):
        """Test that parallel execution reduces duration."""
        # Two parallel XL issues
        parallel_issues = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Issue 1",
                description="Desc",
                estimated_complexity=EstimatedComplexity.XL,
            ),
            DecomposedIssue(
                temp_id="issue-2",
                title="Issue 2",
                description="Desc",
                estimated_complexity=EstimatedComplexity.XL,
            ),
        ]

        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=parallel_issues,
            dependency_graph={},
        )

        # Parallel execution: max(16, 16) = 16 hours = 2 days
        assert "2.0 days" in plan.estimated_duration or "16" in plan.estimated_duration


# ============================================================================
# Service Tests - Phase Calculation Details
# ============================================================================


class TestPhaseCalculation:
    """Test detailed phase calculation scenarios."""

    @pytest.mark.asyncio
    async def test_no_dependencies_single_phase(self, work_planner_service):
        """Test that issues with no dependencies are in single phase."""
        issues = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Issue 1",
                description="Desc",
            ),
            DecomposedIssue(
                temp_id="issue-2",
                title="Issue 2",
                description="Desc",
            ),
            DecomposedIssue(
                temp_id="issue-3",
                title="Issue 3",
                description="Desc",
            ),
        ]

        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=issues,
            dependency_graph={},
        )

        # All issues should be in a single phase
        assert len(plan.phases) == 1
        assert set(plan.phases[0].issues) == {"issue-1", "issue-2", "issue-3"}

    @pytest.mark.asyncio
    async def test_phase_gate_threshold(self):
        """Test that gate is added when threshold exceeded."""
        config = WorkPlannerConfig(phase_gate_threshold=2)
        service = WorkPlannerService(config=config)

        issues = [
            DecomposedIssue(
                temp_id=f"issue-{i}",
                title=f"Issue {i}",
                description="Desc",
            )
            for i in range(1, 4)  # 3 issues, threshold is 2
        ]

        plan = await service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=issues,
            dependency_graph={},
        )

        # Phase should have a gate since 3 >= 2
        assert plan.phases[0].gate is not None

    @pytest.mark.asyncio
    async def test_phase_description_includes_titles(
        self,
        work_planner_service,
        sample_issues,
        sample_dependency_graph,
    ):
        """Test that phase descriptions include issue titles."""
        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=sample_issues,
            dependency_graph=sample_dependency_graph,
        )

        # First phase should mention database
        assert "database" in plan.phases[0].description.lower()


# ============================================================================
# Service Tests - Recommendations
# ============================================================================


class TestRecommendations:
    """Test recommendation generation."""

    @pytest.mark.asyncio
    async def test_generates_recommendations(
        self,
        work_planner_service,
        sample_issues,
        sample_dependency_graph,
    ):
        """Test that recommendations are generated."""
        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=sample_issues,
            dependency_graph=sample_dependency_graph,
        )

        assert len(plan.recommendations) >= 1

    @pytest.mark.asyncio
    async def test_deadline_constraint_recommendation(self, work_planner_service):
        """Test recommendation when deadline is set."""
        issues = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Issue 1",
                description="Desc",
            ),
        ]

        constraints = PlanConstraints(
            deadline=datetime.now(timezone.utc),
        )

        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=issues,
            dependency_graph={},
            constraints=constraints,
        )

        assert any("deadline" in r.lower() for r in plan.recommendations)


# ============================================================================
# Service Tests - Global Instance
# ============================================================================


class TestGlobalInstance:
    """Test global service instance management."""

    def test_get_service_returns_instance(self):
        """Test get_work_planner_service returns an instance."""
        set_work_planner_service(None)

        service = get_work_planner_service()

        assert isinstance(service, WorkPlannerService)

    def test_set_service_replaces_instance(self):
        """Test set_work_planner_service replaces the global instance."""
        custom_config = WorkPlannerConfig(default_max_parallel=10)
        custom_service = WorkPlannerService(config=custom_config)

        set_work_planner_service(custom_service)

        assert get_work_planner_service() is custom_service

    def test_get_service_returns_same_instance(self):
        """Test get_work_planner_service returns the same instance."""
        set_work_planner_service(None)

        service1 = get_work_planner_service()
        service2 = get_work_planner_service()

        assert service1 is service2


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for complete workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow(
        self,
        work_planner_service,
        sample_decomposition,
    ):
        """Test full workflow from decomposition to plan."""
        plan = await work_planner_service.create_plan_from_decomposition(
            decomposition=sample_decomposition,
        )

        # Verify complete plan structure
        assert plan.plan_id.startswith("plan-")
        assert plan.goal_id == "goal-001"
        assert plan.decomposition_id == "decomp-abc123"
        assert len(plan.phases) > 0
        assert plan.estimated_duration != ""
        assert len(plan.critical_path) > 0

    @pytest.mark.asyncio
    async def test_complex_dependency_graph(self, work_planner_service):
        """Test with a more complex dependency graph."""
        # Diamond dependency: A -> (B, C) -> D
        issues = [
            DecomposedIssue(
                temp_id="A",
                title="Foundation",
                description="Base",
                estimated_complexity=EstimatedComplexity.M,
            ),
            DecomposedIssue(
                temp_id="B",
                title="Branch B",
                description="Left branch",
                blocked_by=["A"],
                estimated_complexity=EstimatedComplexity.S,
            ),
            DecomposedIssue(
                temp_id="C",
                title="Branch C",
                description="Right branch",
                blocked_by=["A"],
                estimated_complexity=EstimatedComplexity.L,
            ),
            DecomposedIssue(
                temp_id="D",
                title="Merge point",
                description="Depends on both branches",
                blocked_by=["B", "C"],
                estimated_complexity=EstimatedComplexity.M,
            ),
        ]

        plan = await work_planner_service.create_plan(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=issues,
            dependency_graph={
                "B": ["A"],
                "C": ["A"],
                "D": ["B", "C"],
            },
        )

        # Should have 3 phases: A -> (B, C) -> D
        assert len(plan.phases) == 3
        assert plan.phases[0].issues == ["A"]
        assert set(plan.phases[1].issues) == {"B", "C"}
        assert plan.phases[2].issues == ["D"]

        # Critical path should go through longer C branch
        assert "A" in plan.critical_path
        assert "C" in plan.critical_path
        assert "D" in plan.critical_path
