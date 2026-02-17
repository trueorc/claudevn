"""Tests for PlanExecutorService - Slim Claude Code plan execution."""

import pytest
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock

from models.goal_decomposer import (
    DecomposedIssue,
    EstimatedComplexity,
    GoalDecompositionResult,
)
from models.issue import Issue, IssueArea, IssuePriority, IssueStatus, IssueType
from models.plan_executor import (
    ApprovalRecord,
    ExecutePlanRequest,
    ExecutionError,
    ExecutionStatus,
    IssueBatchCreateResponse,
    IssueMapping,
    PlanExecutorConfig,
)
from models.work_planner import ExecutionPhase, WorkPlan
from services.plan_executor import (
    DecompositionNotFoundError,
    InMemoryStorage,
    PlanExecutionError,
    PlanExecutorService,
    PlanNotFoundError,
    get_plan_executor_service,
    set_plan_executor_service,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_issue_service():
    """Create a mock issue service."""
    service = MagicMock()
    service.create_issue = AsyncMock()
    service.delete_issue = AsyncMock(return_value=True)
    return service


@pytest.fixture
def sample_decomposed_issues():
    """Sample decomposed issues for testing."""
    return [
        DecomposedIssue(
            temp_id="issue-1",
            title="Set up database schema",
            description="Create the initial database schema.",
            issue_type="feature",
            priority="P1",
            area="database",
            required_skills=["sql"],
            estimated_complexity=EstimatedComplexity.M,
            blocked_by=[],
        ),
        DecomposedIssue(
            temp_id="issue-2",
            title="Implement API endpoints",
            description="Create REST API endpoints.",
            issue_type="feature",
            priority="P1",
            area="api",
            required_skills=["python"],
            estimated_complexity=EstimatedComplexity.L,
            blocked_by=["issue-1"],
        ),
        DecomposedIssue(
            temp_id="issue-3",
            title="Add authentication",
            description="Implement JWT authentication.",
            issue_type="feature",
            priority="P0",
            area="api",
            required_skills=["security"],
            estimated_complexity=EstimatedComplexity.L,
            blocked_by=["issue-2"],
        ),
    ]


@pytest.fixture
def sample_decomposition(sample_decomposed_issues):
    """Sample decomposition result."""
    return GoalDecompositionResult(
        goal_id="goal-001",
        decomposition_id="decomp-abc123",
        issues=sample_decomposed_issues,
        dependency_graph={
            "issue-2": ["issue-1"],
            "issue-3": ["issue-2"],
        },
        execution_phases=[["issue-1"], ["issue-2"], ["issue-3"]],
        confidence=0.85,
        reasoning="Test decomposition",
    )


@pytest.fixture
def sample_plan():
    """Sample work plan."""
    return WorkPlan(
        plan_id="plan-xyz789",
        goal_id="goal-001",
        decomposition_id="decomp-abc123",
        phases=[
            ExecutionPhase(
                phase_number=1,
                issues=["issue-1"],
                parallel=False,
                description="Database setup",
            ),
            ExecutionPhase(
                phase_number=2,
                issues=["issue-2"],
                parallel=False,
                description="API implementation",
            ),
            ExecutionPhase(
                phase_number=3,
                issues=["issue-3"],
                parallel=False,
                description="Authentication",
            ),
        ],
        estimated_duration="1.5 days",
        critical_path=["issue-1", "issue-2", "issue-3"],
    )


@pytest.fixture
def plan_executor_service(mock_issue_service):
    """Create PlanExecutorService with mock issue service."""
    service = PlanExecutorService(issue_service=mock_issue_service)
    return service


def create_mock_issue(issue_id: str, title: str) -> Issue:
    """Helper to create a mock Issue."""
    return Issue(
        id=issue_id,
        title=title,
        description="Test description",
        type=IssueType.FEATURE,
        area=IssueArea.API,
        priority=IssuePriority.P2,
        status=IssueStatus.READY,
    )


# ============================================================================
# Model Tests - ApprovalRecord
# ============================================================================


class TestApprovalRecordModel:
    """Test ApprovalRecord model."""

    def test_create_approval_record(self):
        """Test creating an approval record."""
        record = ApprovalRecord(
            approved_by="user-001",
            plan_id="plan-xyz",
            goal_id="goal-001",
            notes="Approved for execution",
        )

        assert record.approved_by == "user-001"
        assert record.plan_id == "plan-xyz"
        assert record.goal_id == "goal-001"
        assert record.notes == "Approved for execution"
        assert record.approved_at is not None


# ============================================================================
# Model Tests - IssueMapping
# ============================================================================


class TestIssueMappingModel:
    """Test IssueMapping model."""

    def test_create_issue_mapping(self):
        """Test creating an issue mapping."""
        mapping = IssueMapping(
            temp_id="issue-1",
            issue_id="real-001",
            title="Test Issue",
            phase_number=1,
        )

        assert mapping.temp_id == "issue-1"
        assert mapping.issue_id == "real-001"
        assert mapping.title == "Test Issue"
        assert mapping.phase_number == 1


# ============================================================================
# Model Tests - IssueBatchCreateResponse
# ============================================================================


class TestIssueBatchCreateResponseModel:
    """Test IssueBatchCreateResponse model."""

    def test_create_success_response(self):
        """Test creating a successful response."""
        approval = ApprovalRecord(
            approved_by="user-001",
            plan_id="plan-xyz",
            goal_id="goal-001",
        )

        response = IssueBatchCreateResponse(
            success=True,
            goal_id="goal-001",
            plan_id="plan-xyz",
            decomposition_id="decomp-abc",
            status=ExecutionStatus.COMPLETED,
            created_issues=[
                IssueMapping(
                    temp_id="issue-1",
                    issue_id="real-001",
                    title="Test",
                    phase_number=1,
                )
            ],
            approval=approval,
        )

        assert response.success is True
        assert response.status == ExecutionStatus.COMPLETED
        assert len(response.created_issues) == 1
        assert response.errors == []
        assert response.rolled_back_issues == []

    def test_create_failure_response(self):
        """Test creating a failure response."""
        approval = ApprovalRecord(
            approved_by="user-001",
            plan_id="plan-xyz",
            goal_id="goal-001",
        )

        response = IssueBatchCreateResponse(
            success=False,
            goal_id="goal-001",
            plan_id="plan-xyz",
            decomposition_id="decomp-abc",
            status=ExecutionStatus.FAILED,
            created_issues=[],
            approval=approval,
            errors=[
                ExecutionError(
                    temp_id="issue-1",
                    error_message="Failed to create",
                    phase_number=1,
                )
            ],
        )

        assert response.success is False
        assert response.status == ExecutionStatus.FAILED
        assert len(response.errors) == 1


# ============================================================================
# Model Tests - PlanExecutorConfig
# ============================================================================


class TestPlanExecutorConfigModel:
    """Test PlanExecutorConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = PlanExecutorConfig()

        assert config.rollback_on_failure is True
        assert config.continue_on_error is False
        assert config.decomposition_ttl_hours == 24
        assert config.plan_ttl_hours == 24

    def test_custom_config(self):
        """Test custom configuration values."""
        config = PlanExecutorConfig(
            rollback_on_failure=False,
            continue_on_error=True,
        )

        assert config.rollback_on_failure is False
        assert config.continue_on_error is True


# ============================================================================
# Service Tests - Initialization
# ============================================================================


class TestPlanExecutorServiceInit:
    """Test PlanExecutorService initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        service = PlanExecutorService()

        assert service._issue_service is None
        assert service._storage is not None
        assert service._config is not None

    def test_init_with_custom_config(self, mock_issue_service):
        """Test initialization with custom config."""
        config = PlanExecutorConfig(rollback_on_failure=False)
        service = PlanExecutorService(
            issue_service=mock_issue_service,
            config=config,
        )

        assert service._issue_service is mock_issue_service
        assert service._config.rollback_on_failure is False


# ============================================================================
# Service Tests - Execute Plan
# ============================================================================


class TestPlanExecutorServiceExecutePlan:
    """Test plan execution functionality."""

    @pytest.mark.asyncio
    async def test_execute_plan_success(
        self,
        plan_executor_service,
        mock_issue_service,
        sample_decomposition,
        sample_plan,
    ):
        """Test successful plan execution."""
        # Setup mock to return different issues
        mock_issue_service.create_issue.side_effect = [
            create_mock_issue("real-001", "Set up database schema"),
            create_mock_issue("real-002", "Implement API endpoints"),
            create_mock_issue("real-003", "Add authentication"),
        ]

        response = await plan_executor_service.execute_plan(
            goal_id="goal-001",
            plan_id="plan-xyz789",
            approved_by="user-001",
            decomposition=sample_decomposition,
            plan=sample_plan,
        )

        assert response.success is True
        assert response.status == ExecutionStatus.COMPLETED
        assert len(response.created_issues) == 3
        assert response.errors == []

        # Verify issue mappings
        assert response.created_issues[0].temp_id == "issue-1"
        assert response.created_issues[0].issue_id == "real-001"
        assert response.created_issues[1].temp_id == "issue-2"
        assert response.created_issues[1].issue_id == "real-002"
        assert response.created_issues[2].temp_id == "issue-3"
        assert response.created_issues[2].issue_id == "real-003"

    @pytest.mark.asyncio
    async def test_execute_plan_creates_issues_in_order(
        self,
        plan_executor_service,
        mock_issue_service,
        sample_decomposition,
        sample_plan,
    ):
        """Test that issues are created in phase order."""
        created_order = []

        async def track_creation(**kwargs):
            created_order.append(kwargs["title"])
            return create_mock_issue(f"real-{len(created_order)}", kwargs["title"])

        mock_issue_service.create_issue.side_effect = track_creation

        await plan_executor_service.execute_plan(
            goal_id="goal-001",
            plan_id="plan-xyz789",
            approved_by="user-001",
            decomposition=sample_decomposition,
            plan=sample_plan,
        )

        # Verify order matches phases
        assert created_order == [
            "Set up database schema",
            "Implement API endpoints",
            "Add authentication",
        ]

    @pytest.mark.asyncio
    async def test_execute_plan_resolves_dependencies(
        self,
        plan_executor_service,
        mock_issue_service,
        sample_decomposition,
        sample_plan,
    ):
        """Test that dependencies are resolved to real IDs."""
        call_args = []

        async def capture_args(**kwargs):
            call_args.append(kwargs)
            return create_mock_issue(f"real-{len(call_args):03d}", kwargs["title"])

        mock_issue_service.create_issue.side_effect = capture_args

        await plan_executor_service.execute_plan(
            goal_id="goal-001",
            plan_id="plan-xyz789",
            approved_by="user-001",
            decomposition=sample_decomposition,
            plan=sample_plan,
        )

        # First issue has no dependencies
        assert call_args[0]["blocked_by"] == []

        # Second issue depends on first (issue-1 -> real-001)
        assert call_args[1]["blocked_by"] == ["real-001"]

        # Third issue depends on second (issue-2 -> real-002)
        assert call_args[2]["blocked_by"] == ["real-002"]

    @pytest.mark.asyncio
    async def test_execute_plan_records_approval(
        self,
        plan_executor_service,
        mock_issue_service,
        sample_decomposition,
        sample_plan,
    ):
        """Test that approval is recorded."""
        mock_issue_service.create_issue.return_value = create_mock_issue(
            "real-001", "Test"
        )

        response = await plan_executor_service.execute_plan(
            goal_id="goal-001",
            plan_id="plan-xyz789",
            approved_by="user-001",
            approval_notes="Approved after review",
            decomposition=sample_decomposition,
            plan=sample_plan,
        )

        assert response.approval.approved_by == "user-001"
        assert response.approval.plan_id == "plan-xyz789"
        assert response.approval.goal_id == "goal-001"
        assert response.approval.notes == "Approved after review"
        assert response.approval.approved_at is not None

    @pytest.mark.asyncio
    async def test_execute_plan_without_issue_service(
        self,
        sample_decomposition,
        sample_plan,
    ):
        """Test execution fails without issue service."""
        service = PlanExecutorService()

        with pytest.raises(ValueError) as exc_info:
            await service.execute_plan(
                goal_id="goal-001",
                plan_id="plan-xyz789",
                approved_by="user-001",
                decomposition=sample_decomposition,
                plan=sample_plan,
            )

        assert "Issue service not configured" in str(exc_info.value)


# ============================================================================
# Service Tests - Error Handling
# ============================================================================


class TestPlanExecutorErrorHandling:
    """Test error handling during plan execution."""

    @pytest.mark.asyncio
    async def test_execute_plan_failure_with_rollback(
        self,
        mock_issue_service,
        sample_decomposition,
        sample_plan,
    ):
        """Test rollback on failure."""
        # First issue succeeds, second fails
        mock_issue_service.create_issue.side_effect = [
            create_mock_issue("real-001", "First"),
            Exception("Database error"),
        ]

        config = PlanExecutorConfig(rollback_on_failure=True)
        service = PlanExecutorService(
            issue_service=mock_issue_service,
            config=config,
        )

        response = await service.execute_plan(
            goal_id="goal-001",
            plan_id="plan-xyz789",
            approved_by="user-001",
            decomposition=sample_decomposition,
            plan=sample_plan,
        )

        assert response.success is False
        assert response.status == ExecutionStatus.ROLLED_BACK
        assert len(response.errors) == 1
        assert "real-001" in response.rolled_back_issues

        # Verify delete was called for rollback
        mock_issue_service.delete_issue.assert_called_once_with("real-001")

    @pytest.mark.asyncio
    async def test_execute_plan_failure_without_rollback(
        self,
        mock_issue_service,
        sample_decomposition,
        sample_plan,
    ):
        """Test failure without rollback."""
        mock_issue_service.create_issue.side_effect = [
            create_mock_issue("real-001", "First"),
            Exception("Database error"),
        ]

        config = PlanExecutorConfig(rollback_on_failure=False)
        service = PlanExecutorService(
            issue_service=mock_issue_service,
            config=config,
        )

        response = await service.execute_plan(
            goal_id="goal-001",
            plan_id="plan-xyz789",
            approved_by="user-001",
            decomposition=sample_decomposition,
            plan=sample_plan,
        )

        assert response.success is False
        assert response.status == ExecutionStatus.FAILED
        assert len(response.created_issues) == 1
        assert response.rolled_back_issues == []

        # Verify delete was NOT called
        mock_issue_service.delete_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_plan_continue_on_error(
        self,
        mock_issue_service,
        sample_decomposition,
        sample_plan,
    ):
        """Test continue on error."""
        # Second issue fails, but continue
        mock_issue_service.create_issue.side_effect = [
            create_mock_issue("real-001", "First"),
            Exception("Temporary error"),
            create_mock_issue("real-003", "Third"),
        ]

        config = PlanExecutorConfig(continue_on_error=True)
        service = PlanExecutorService(
            issue_service=mock_issue_service,
            config=config,
        )

        response = await service.execute_plan(
            goal_id="goal-001",
            plan_id="plan-xyz789",
            approved_by="user-001",
            decomposition=sample_decomposition,
            plan=sample_plan,
        )

        # Should have partial success
        assert response.success is False
        assert response.status == ExecutionStatus.FAILED
        assert len(response.created_issues) == 2  # First and third
        assert len(response.errors) == 1  # Second failed

    @pytest.mark.asyncio
    async def test_execute_plan_missing_issue_in_decomposition(
        self,
        mock_issue_service,
        sample_decomposition,
    ):
        """Test handling of missing issue in decomposition."""
        # Plan references non-existent issue
        plan = WorkPlan(
            plan_id="plan-xyz789",
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            phases=[
                ExecutionPhase(
                    phase_number=1,
                    issues=["non-existent"],
                    parallel=False,
                    description="Missing issue",
                ),
            ],
        )

        service = PlanExecutorService(issue_service=mock_issue_service)

        response = await service.execute_plan(
            goal_id="goal-001",
            plan_id="plan-xyz789",
            approved_by="user-001",
            decomposition=sample_decomposition,
            plan=plan,
        )

        assert response.success is False
        assert len(response.errors) == 1
        assert "not found" in response.errors[0].error_message


# ============================================================================
# Service Tests - Storage
# ============================================================================


class TestPlanExecutorStorage:
    """Test storage functionality."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_decomposition(
        self,
        plan_executor_service,
        sample_decomposition,
    ):
        """Test storing and retrieving decomposition."""
        await plan_executor_service.store_decomposition(sample_decomposition)

        retrieved = await plan_executor_service.get_decomposition(
            sample_decomposition.decomposition_id
        )

        assert retrieved is not None
        assert retrieved.decomposition_id == sample_decomposition.decomposition_id
        assert len(retrieved.issues) == len(sample_decomposition.issues)

    @pytest.mark.asyncio
    async def test_store_and_retrieve_plan(
        self,
        plan_executor_service,
        sample_plan,
    ):
        """Test storing and retrieving plan."""
        await plan_executor_service.store_plan(sample_plan)

        retrieved = await plan_executor_service.get_plan(sample_plan.plan_id)

        assert retrieved is not None
        assert retrieved.plan_id == sample_plan.plan_id
        assert len(retrieved.phases) == len(sample_plan.phases)

    @pytest.mark.asyncio
    async def test_execute_plan_from_storage(
        self,
        mock_issue_service,
        sample_decomposition,
        sample_plan,
    ):
        """Test executing plan retrieved from storage."""
        service = PlanExecutorService(issue_service=mock_issue_service)

        # Store decomposition and plan
        await service.store_decomposition(sample_decomposition)
        await service.store_plan(sample_plan)

        mock_issue_service.create_issue.return_value = create_mock_issue(
            "real-001", "Test"
        )

        # Execute using stored data
        response = await service.execute_plan(
            goal_id="goal-001",
            plan_id=sample_plan.plan_id,
            approved_by="user-001",
        )

        assert response.success is True

    @pytest.mark.asyncio
    async def test_execute_plan_not_found(
        self,
        mock_issue_service,
    ):
        """Test execution with non-existent plan."""
        service = PlanExecutorService(issue_service=mock_issue_service)

        with pytest.raises(PlanNotFoundError):
            await service.execute_plan(
                goal_id="goal-001",
                plan_id="non-existent",
                approved_by="user-001",
            )

    @pytest.mark.asyncio
    async def test_execute_plan_decomposition_not_found(
        self,
        mock_issue_service,
        sample_plan,
    ):
        """Test execution with non-existent decomposition."""
        service = PlanExecutorService(issue_service=mock_issue_service)

        # Store plan but not decomposition
        await service.store_plan(sample_plan)

        with pytest.raises(DecompositionNotFoundError):
            await service.execute_plan(
                goal_id="goal-001",
                plan_id=sample_plan.plan_id,
                approved_by="user-001",
            )


# ============================================================================
# Service Tests - InMemoryStorage
# ============================================================================


class TestInMemoryStorage:
    """Test InMemoryStorage."""

    @pytest.mark.asyncio
    async def test_store_and_get_decomposition(self, sample_decomposition):
        """Test decomposition storage."""
        storage = InMemoryStorage()

        await storage.store_decomposition(sample_decomposition)
        retrieved = await storage.get_decomposition(
            sample_decomposition.decomposition_id
        )

        assert retrieved == sample_decomposition

    @pytest.mark.asyncio
    async def test_get_nonexistent_decomposition(self):
        """Test retrieving non-existent decomposition."""
        storage = InMemoryStorage()

        result = await storage.get_decomposition("non-existent")

        assert result is None

    @pytest.mark.asyncio
    async def test_store_and_get_plan(self, sample_plan):
        """Test plan storage."""
        storage = InMemoryStorage()

        await storage.store_plan(sample_plan)
        retrieved = await storage.get_plan(sample_plan.plan_id)

        assert retrieved == sample_plan


# ============================================================================
# Service Tests - Global Instance
# ============================================================================


class TestGlobalInstance:
    """Test global service instance management."""

    def test_get_service_returns_instance(self):
        """Test get_plan_executor_service returns an instance."""
        set_plan_executor_service(None)

        service = get_plan_executor_service()

        assert isinstance(service, PlanExecutorService)

    def test_set_service_replaces_instance(self, mock_issue_service):
        """Test set_plan_executor_service replaces the global instance."""
        custom_service = PlanExecutorService(issue_service=mock_issue_service)

        set_plan_executor_service(custom_service)

        assert get_plan_executor_service() is custom_service

    def test_get_service_returns_same_instance(self):
        """Test get_plan_executor_service returns the same instance."""
        set_plan_executor_service(None)

        service1 = get_plan_executor_service()
        service2 = get_plan_executor_service()

        assert service1 is service2


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for complete workflow."""

    @pytest.mark.asyncio
    async def test_full_execution_workflow(
        self,
        mock_issue_service,
        sample_decomposed_issues,
    ):
        """Test full workflow from decomposition to execution."""
        # Create decomposition
        decomposition = GoalDecompositionResult(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=sample_decomposed_issues,
            dependency_graph={
                "issue-2": ["issue-1"],
                "issue-3": ["issue-2"],
            },
            confidence=0.85,
            reasoning="Test",
        )

        # Create plan
        plan = WorkPlan(
            plan_id="plan-xyz789",
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            phases=[
                ExecutionPhase(phase_number=1, issues=["issue-1"]),
                ExecutionPhase(phase_number=2, issues=["issue-2"]),
                ExecutionPhase(phase_number=3, issues=["issue-3"]),
            ],
        )

        # Setup mock
        issue_counter = 0

        async def create_issue_mock(**kwargs):
            nonlocal issue_counter
            issue_counter += 1
            return create_mock_issue(f"real-{issue_counter:03d}", kwargs["title"])

        mock_issue_service.create_issue.side_effect = create_issue_mock

        # Create service and store data
        service = PlanExecutorService(issue_service=mock_issue_service)
        await service.store_decomposition(decomposition)
        await service.store_plan(plan)

        # Execute
        response = await service.execute_plan(
            goal_id="goal-001",
            plan_id="plan-xyz789",
            approved_by="admin-001",
            approval_notes="Approved for testing",
        )

        # Verify
        assert response.success is True
        assert response.status == ExecutionStatus.COMPLETED
        assert len(response.created_issues) == 3
        assert response.approval.approved_by == "admin-001"
        assert response.execution_duration_ms is not None
        assert response.execution_duration_ms >= 0  # May be 0 for fast execution

        # Verify ID mapping
        id_map = {m.temp_id: m.issue_id for m in response.created_issues}
        assert "issue-1" in id_map
        assert "issue-2" in id_map
        assert "issue-3" in id_map
