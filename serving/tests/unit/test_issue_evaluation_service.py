"""Tests for IssueEvaluationService."""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from services.issue_evaluation_service import (
    IssueEvaluationService,
    get_issue_evaluation_service,
    set_issue_evaluation_service,
    MAX_EVALUATION_RETRIES,
)
from models.work_map import (
    Issue,
    IssueStatus,
    IssueType,
    IssueArea,
    IssuePriority,
    IssueResult,
    IssueCreateRequest,
    EvaluationStatus,
    IssueEvaluationResult,
    IssueEvaluationOutcome,
    RootCauseCategory,
)


@pytest.fixture
def mock_issue_ops_service():
    """Create mock issue ops service."""
    service = MagicMock()
    service.get_issue = AsyncMock()
    service.create_issue = AsyncMock()
    service._save_issue_to_redis = AsyncMock()
    return service


@pytest.fixture
def sample_issue():
    """Create a sample completed issue."""
    return Issue(
        issue_id="issue_abc123",
        title="Implement user authentication",
        description="Add JWT-based auth to the API",
        issue_type=IssueType.FEATURE,
        area=IssueArea.API,
        priority=IssuePriority.P1,
        status=IssueStatus.DONE,
        goal_id="goal_test123",
        project_id="proj_test",
        required_skills=["python", "security"],
        required_labels=["backend"],
        required_tools=["pytest"],
        result=IssueResult(
            branch="feature/auth",
            summary="Implemented JWT auth with login/logout endpoints",
            commits=["abc123", "def456"],
        ),
        evaluation_status=EvaluationStatus.NOT_EVALUATED,
    )


@pytest.fixture
def sample_issue_no_result():
    """Create a sample completed issue with no result."""
    return Issue(
        issue_id="issue_no_result",
        title="Fix broken tests",
        description="Fix the failing test suite",
        status=IssueStatus.DONE,
        goal_id="goal_test123",
        project_id="proj_test",
        evaluation_status=EvaluationStatus.NOT_EVALUATED,
    )


@pytest.fixture
def sample_issue_partial():
    """Create a sample issue with partial result (summary but no commits)."""
    return Issue(
        issue_id="issue_partial",
        title="Refactor database layer",
        description="Improve database abstraction",
        status=IssueStatus.DONE,
        goal_id="goal_test123",
        project_id="proj_test",
        result=IssueResult(
            branch="refactor/db",
            summary="Started refactoring the database layer",
            commits=[],
        ),
        evaluation_status=EvaluationStatus.NOT_EVALUATED,
    )


@pytest.fixture
def sample_evaluation_result():
    """Create a sample evaluation result."""
    return IssueEvaluationResult(
        outcome=IssueEvaluationOutcome.SUCCESS,
        confidence=0.9,
        summary="Issue successfully completed all objectives",
        accomplishments=["Implemented JWT auth", "Added tests"],
        gaps=[],
        requires_followup=False,
        evaluator_version="1.0-test",
    )


@pytest.fixture
def evaluation_service(mock_issue_ops_service):
    """Create evaluation service with mocked dependencies."""
    return IssueEvaluationService(
        issue_ops_service=mock_issue_ops_service,
        max_retries=3,
        retry_delay=0.1,
    )


class TestIssueEvaluationServiceInit:
    """Test IssueEvaluationService initialization."""

    def test_init_defaults(self, mock_issue_ops_service):
        """Test initialization with default values."""
        service = IssueEvaluationService(
            issue_ops_service=mock_issue_ops_service
        )
        assert service._issue_ops_service is mock_issue_ops_service
        assert service._max_retries == MAX_EVALUATION_RETRIES
        assert service._running is False
        assert service._evaluator is None
        assert service._initialized is False

    def test_init_custom_params(self, mock_issue_ops_service):
        """Test initialization with custom parameters."""
        service = IssueEvaluationService(
            issue_ops_service=mock_issue_ops_service,
            max_retries=5,
            retry_delay=1.0,
        )
        assert service._max_retries == 5
        assert service._retry_delay == 1.0

    @pytest.mark.asyncio
    async def test_start_stop(self, evaluation_service):
        """Test starting and stopping the service."""
        await evaluation_service.start()
        assert evaluation_service.is_running() is True
        assert evaluation_service._processing_task is not None
        assert evaluation_service._initialized is True

        await evaluation_service.stop()
        assert evaluation_service.is_running() is False
        assert evaluation_service._processing_task is None

    @pytest.mark.asyncio
    async def test_start_idempotent(self, evaluation_service):
        """Test that starting twice is idempotent."""
        await evaluation_service.start()
        task1 = evaluation_service._processing_task

        await evaluation_service.start()
        task2 = evaluation_service._processing_task

        assert task1 is task2
        await evaluation_service.stop()


class TestQueueForEvaluation:
    """Test queuing issues for evaluation."""

    @pytest.mark.asyncio
    async def test_queue_valid_issue(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test queuing a valid completed issue."""
        mock_issue_ops_service.get_issue.return_value = sample_issue

        result = await evaluation_service.queue_for_evaluation("issue_abc123")

        assert result is True
        assert evaluation_service.get_queue_size() == 1

    @pytest.mark.asyncio
    async def test_queue_nonexistent_issue(
        self, evaluation_service, mock_issue_ops_service
    ):
        """Test queuing a nonexistent issue."""
        mock_issue_ops_service.get_issue.return_value = None

        result = await evaluation_service.queue_for_evaluation("nonexistent")

        assert result is False
        assert evaluation_service.get_queue_size() == 0

    @pytest.mark.asyncio
    async def test_queue_already_evaluated_issue(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test queuing an issue that's already evaluated."""
        sample_issue.evaluation_status = EvaluationStatus.EVALUATED
        mock_issue_ops_service.get_issue.return_value = sample_issue

        result = await evaluation_service.queue_for_evaluation("issue_abc123")

        assert result is False
        assert evaluation_service.get_queue_size() == 0

    @pytest.mark.asyncio
    async def test_queue_evaluating_issue(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test queuing an issue currently being evaluated."""
        sample_issue.evaluation_status = EvaluationStatus.EVALUATING
        mock_issue_ops_service.get_issue.return_value = sample_issue

        result = await evaluation_service.queue_for_evaluation("issue_abc123")

        assert result is False


class TestEvaluateIssue:
    """Test full evaluation lifecycle."""

    @pytest.mark.asyncio
    async def test_evaluate_success(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test successful issue evaluation."""
        mock_issue_ops_service.get_issue.return_value = sample_issue

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            result = await evaluation_service.evaluate_issue("issue_abc123")

        assert result is not None
        assert result.outcome == IssueEvaluationOutcome.SUCCESS
        assert result.confidence > 0
        assert len(result.accomplishments) > 0

    @pytest.mark.asyncio
    async def test_evaluate_nonexistent_issue(
        self, evaluation_service, mock_issue_ops_service
    ):
        """Test evaluating a nonexistent issue."""
        mock_issue_ops_service.get_issue.return_value = None

        result = await evaluation_service.evaluate_issue("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_sets_evaluating_status(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test that evaluation sets EVALUATING status first."""
        mock_issue_ops_service.get_issue.return_value = sample_issue
        status_changes = []

        def track_status(issue_id, status, result):
            status_changes.append(status)

        evaluation_service.on_status_change(track_status)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            await evaluation_service.evaluate_issue("issue_abc123")

        assert EvaluationStatus.EVALUATING in status_changes
        assert EvaluationStatus.EVALUATED in status_changes
        # EVALUATING should come before EVALUATED
        eval_ing_idx = status_changes.index(EvaluationStatus.EVALUATING)
        eval_ed_idx = status_changes.index(EvaluationStatus.EVALUATED)
        assert eval_ing_idx < eval_ed_idx

    @pytest.mark.asyncio
    async def test_evaluate_with_custom_evaluator(
        self, evaluation_service, mock_issue_ops_service,
        sample_issue, sample_evaluation_result
    ):
        """Test evaluation with a custom evaluator."""
        mock_issue_ops_service.get_issue.return_value = sample_issue

        async def custom_evaluator(issue):
            return sample_evaluation_result

        evaluation_service.set_evaluator(custom_evaluator)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            result = await evaluation_service.evaluate_issue("issue_abc123")

        assert result is sample_evaluation_result
        assert result.outcome == IssueEvaluationOutcome.SUCCESS


class TestDefaultEvaluation:
    """Test the default evaluation heuristics."""

    def test_evaluate_success_with_result(self, evaluation_service, sample_issue):
        """Test evaluation of issue with full result (summary + commits)."""
        result = evaluation_service._default_evaluation(sample_issue)

        assert result.outcome == IssueEvaluationOutcome.SUCCESS
        assert result.confidence >= 0.7
        assert not result.requires_followup
        assert len(result.accomplishments) >= 2  # summary + commits
        assert len(result.gaps) == 0
        assert result.root_cause_category is None

    def test_evaluate_failure_no_result(
        self, evaluation_service, sample_issue_no_result
    ):
        """Test evaluation of issue with no result."""
        result = evaluation_service._default_evaluation(sample_issue_no_result)

        assert result.outcome == IssueEvaluationOutcome.FAILURE
        assert result.requires_followup is True
        assert len(result.gaps) > 0
        assert result.root_cause_category == RootCauseCategory.OTHER

    def test_evaluate_partial_no_commits(
        self, evaluation_service, sample_issue_partial
    ):
        """Test evaluation of issue with summary but no commits."""
        result = evaluation_service._default_evaluation(sample_issue_partial)

        assert result.outcome == IssueEvaluationOutcome.PARTIAL
        assert result.requires_followup is True
        assert any("commit" in g.lower() for g in result.gaps)
        assert result.root_cause_category == RootCauseCategory.OTHER
        assert result.root_cause_analysis is not None

    def test_evaluate_partial_no_summary(self, evaluation_service):
        """Test evaluation of issue with commits but no summary."""
        issue = Issue(
            issue_id="issue_no_summary",
            title="Quick fix",
            description="A quick fix",
            status=IssueStatus.DONE,
            result=IssueResult(
                branch="fix/quick",
                summary="",
                commits=["abc123"],
            ),
            evaluation_status=EvaluationStatus.NOT_EVALUATED,
        )

        result = evaluation_service._default_evaluation(issue)

        assert result.outcome == IssueEvaluationOutcome.PARTIAL
        assert result.requires_followup is True

    def test_evaluator_version(self, evaluation_service, sample_issue):
        """Test that default evaluator sets version."""
        result = evaluation_service._default_evaluation(sample_issue)
        assert result.evaluator_version == "1.0-heuristic"


class TestRetryLogic:
    """Test evaluation retry logic."""

    @pytest.mark.asyncio
    async def test_retry_on_failure(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test that failed evaluations trigger retry."""
        sample_issue.evaluation_retry_count = 0
        mock_issue_ops_service.get_issue.return_value = sample_issue

        async def failing_evaluator(issue):
            raise ValueError("Evaluation failed")

        evaluation_service.set_evaluator(failing_evaluator)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            result = await evaluation_service.evaluate_issue("issue_abc123")

        assert result is None
        # Should have incremented retry count
        assert sample_issue.evaluation_retry_count == 1
        assert sample_issue.evaluation_status == EvaluationStatus.NOT_EVALUATED

    @pytest.mark.asyncio
    async def test_mark_failed_after_max_retries(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test that evaluation is marked as FAILED after max retries."""
        sample_issue.evaluation_retry_count = 3  # Already at max
        mock_issue_ops_service.get_issue.return_value = sample_issue

        async def failing_evaluator(issue):
            raise ValueError("Evaluation failed")

        evaluation_service.set_evaluator(failing_evaluator)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            result = await evaluation_service.evaluate_issue("issue_abc123")

        assert result is None
        # Should have been marked FAILED via _update_status
        assert sample_issue.evaluation_status == EvaluationStatus.FAILED

    @pytest.mark.asyncio
    async def test_retry_count_increments(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test retry count increments correctly."""
        sample_issue.evaluation_retry_count = 1
        mock_issue_ops_service.get_issue.return_value = sample_issue

        async def failing_evaluator(issue):
            raise ValueError("Evaluation failed")

        evaluation_service.set_evaluator(failing_evaluator)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            await evaluation_service.evaluate_issue("issue_abc123")

        assert sample_issue.evaluation_retry_count == 2


class TestFollowupIssueCreation:
    """Test follow-up issue creation."""

    @pytest.mark.asyncio
    async def test_followup_created_for_failure(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test follow-up issue is created for FAILURE outcome."""
        mock_issue_ops_service.get_issue.return_value = sample_issue

        followup_issue = Issue(
            issue_id="issue_followup123",
            title="[Follow-up] Implement user authentication",
            description="Follow-up",
            status=IssueStatus.READY,
        )
        mock_issue_ops_service.create_issue.return_value = followup_issue

        async def failure_evaluator(issue):
            return IssueEvaluationResult(
                outcome=IssueEvaluationOutcome.FAILURE,
                confidence=0.8,
                summary="Issue failed",
                gaps=["No commits", "No tests"],
                requires_followup=True,
                root_cause_category=RootCauseCategory.TECHNICAL_LIMITATION,
                root_cause_analysis="Technical limitations prevented completion",
            )

        evaluation_service.set_evaluator(failure_evaluator)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            result = await evaluation_service.evaluate_issue("issue_abc123")

        assert result is not None
        assert result.followup_issue_id == "issue_followup123"
        mock_issue_ops_service.create_issue.assert_called_once()

        # Verify the create request
        create_call = mock_issue_ops_service.create_issue.call_args[0][0]
        assert isinstance(create_call, IssueCreateRequest)
        assert create_call.title == "[Follow-up] Implement user authentication"
        assert create_call.goal_id == "goal_test123"
        assert create_call.parent_issue_id == "issue_abc123"
        assert create_call.project_id == "proj_test"
        assert create_call.required_skills == ["python", "security"]
        assert create_call.required_labels == ["backend"]
        assert create_call.required_tools == ["pytest"]

    @pytest.mark.asyncio
    async def test_followup_created_for_partial(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test follow-up issue is created for PARTIAL outcome."""
        mock_issue_ops_service.get_issue.return_value = sample_issue

        followup_issue = Issue(
            issue_id="issue_followup456",
            title="[Follow-up] Implement user authentication",
            description="Follow-up",
            status=IssueStatus.READY,
        )
        mock_issue_ops_service.create_issue.return_value = followup_issue

        async def partial_evaluator(issue):
            return IssueEvaluationResult(
                outcome=IssueEvaluationOutcome.PARTIAL,
                confidence=0.6,
                summary="Issue partially completed",
                accomplishments=["Started implementation"],
                gaps=["Missing tests"],
                requires_followup=True,
                root_cause_category=RootCauseCategory.SCOPE_CREEP,
            )

        evaluation_service.set_evaluator(partial_evaluator)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            result = await evaluation_service.evaluate_issue("issue_abc123")

        assert result is not None
        assert result.followup_issue_id == "issue_followup456"

    @pytest.mark.asyncio
    async def test_no_followup_for_success(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test no follow-up issue is created for SUCCESS outcome."""
        mock_issue_ops_service.get_issue.return_value = sample_issue

        async def success_evaluator(issue):
            return IssueEvaluationResult(
                outcome=IssueEvaluationOutcome.SUCCESS,
                confidence=0.9,
                summary="Issue completed successfully",
                requires_followup=False,
            )

        evaluation_service.set_evaluator(success_evaluator)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            result = await evaluation_service.evaluate_issue("issue_abc123")

        assert result is not None
        assert result.followup_issue_id is None
        mock_issue_ops_service.create_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_followup_creation_failure_doesnt_break_evaluation(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test that follow-up creation failure doesn't fail the evaluation."""
        mock_issue_ops_service.get_issue.return_value = sample_issue
        mock_issue_ops_service.create_issue.side_effect = Exception("Creation failed")

        async def failure_evaluator(issue):
            return IssueEvaluationResult(
                outcome=IssueEvaluationOutcome.FAILURE,
                confidence=0.8,
                summary="Issue failed",
                gaps=["Incomplete"],
                requires_followup=True,
            )

        evaluation_service.set_evaluator(failure_evaluator)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            result = await evaluation_service.evaluate_issue("issue_abc123")

        # Evaluation should still succeed even though follow-up creation failed
        assert result is not None
        assert result.outcome == IssueEvaluationOutcome.FAILURE
        assert result.followup_issue_id is None

    @pytest.mark.asyncio
    async def test_followup_not_created_when_requires_followup_false(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test no follow-up when requires_followup is False even for FAILURE."""
        mock_issue_ops_service.get_issue.return_value = sample_issue

        async def failure_no_followup_evaluator(issue):
            return IssueEvaluationResult(
                outcome=IssueEvaluationOutcome.FAILURE,
                confidence=0.8,
                summary="Issue failed but no followup needed",
                requires_followup=False,
            )

        evaluation_service.set_evaluator(failure_no_followup_evaluator)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            result = await evaluation_service.evaluate_issue("issue_abc123")

        assert result is not None
        mock_issue_ops_service.create_issue.assert_not_called()


class TestStatusChangeCallbacks:
    """Test status change callback functionality."""

    @pytest.mark.asyncio
    async def test_callback_on_evaluation(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test that callbacks are triggered on status change."""
        mock_issue_ops_service.get_issue.return_value = sample_issue

        callback_calls = []

        def callback(issue_id, status, result):
            callback_calls.append((issue_id, status, result))

        evaluation_service.on_status_change(callback)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            await evaluation_service.evaluate_issue("issue_abc123")

        # Should have been called at least twice: EVALUATING, then EVALUATED
        assert len(callback_calls) >= 2
        assert callback_calls[0][1] == EvaluationStatus.EVALUATING
        assert callback_calls[1][1] == EvaluationStatus.EVALUATED

    @pytest.mark.asyncio
    async def test_callback_error_doesnt_break_service(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test that a failing callback doesn't break the service."""
        mock_issue_ops_service.get_issue.return_value = sample_issue

        def bad_callback(issue_id, status, result):
            raise RuntimeError("Callback error")

        evaluation_service.on_status_change(bad_callback)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            # Should not raise
            result = await evaluation_service.evaluate_issue("issue_abc123")

        assert result is not None


class TestWebSocketBroadcast:
    """Test WebSocket event broadcasting."""

    @pytest.mark.asyncio
    async def test_broadcast_on_evaluation(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test that WebSocket events are broadcast on evaluation."""
        mock_issue_ops_service.get_issue.return_value = sample_issue

        broadcast_calls = []

        async def track_broadcast(**kwargs):
            broadcast_calls.append(kwargs)

        with patch.object(
            evaluation_service, '_broadcast_status_event',
            side_effect=track_broadcast
        ):
            await evaluation_service.evaluate_issue("issue_abc123")

        # Should have at least 2 broadcasts: EVALUATING and EVALUATED
        assert len(broadcast_calls) >= 2
        assert broadcast_calls[0]['new_status'] == EvaluationStatus.EVALUATING
        assert broadcast_calls[1]['new_status'] == EvaluationStatus.EVALUATED

    @pytest.mark.asyncio
    async def test_broadcast_includes_issue_and_goal_ids(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test that broadcasts include correct issue and goal IDs."""
        mock_issue_ops_service.get_issue.return_value = sample_issue

        broadcast_calls = []

        async def track_broadcast(**kwargs):
            broadcast_calls.append(kwargs)

        with patch.object(
            evaluation_service, '_broadcast_status_event',
            side_effect=track_broadcast
        ):
            await evaluation_service.evaluate_issue("issue_abc123")

        for call in broadcast_calls:
            assert call['issue_id'] == "issue_abc123"
            assert call['goal_id'] == "goal_test123"

    @pytest.mark.asyncio
    async def test_broadcast_failure_doesnt_break_evaluation(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test that broadcast failure doesn't break evaluation."""
        mock_issue_ops_service.get_issue.return_value = sample_issue

        # Make _broadcast_status_event raise an exception
        async def failing_broadcast(**kwargs):
            raise RuntimeError("Broadcast failed")

        with patch.object(
            evaluation_service, '_broadcast_status_event',
            side_effect=failing_broadcast
        ):
            # Should not raise - broadcast failures are caught in _update_status
            # But since we're patching the method itself, the exception will propagate
            # from _update_status. Instead, let's test that the internal broadcast
            # method handles errors gracefully.
            pass

        # Test the actual broadcast method with a failing event bus
        with patch(
            'services.observability_event_bus.get_event_bus',
            side_effect=RuntimeError("No event bus"),
        ):
            # _broadcast_status_event should swallow the exception
            await evaluation_service._broadcast_status_event(
                issue_id="issue_abc123",
                goal_id="goal_test123",
                old_status=EvaluationStatus.NOT_EVALUATED,
                new_status=EvaluationStatus.EVALUATING,
            )
            # If we get here, the exception was swallowed successfully


class TestCustomEvaluator:
    """Test set_evaluator() injection."""

    def test_set_evaluator(self, evaluation_service):
        """Test setting a custom evaluator."""
        async def my_evaluator(issue):
            return IssueEvaluationResult(
                outcome=IssueEvaluationOutcome.SUCCESS,
                confidence=1.0,
                summary="Custom evaluation",
            )

        evaluation_service.set_evaluator(my_evaluator)
        assert evaluation_service._evaluator is my_evaluator

    @pytest.mark.asyncio
    async def test_custom_evaluator_used(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test that custom evaluator is used when set."""
        mock_issue_ops_service.get_issue.return_value = sample_issue

        custom_result = IssueEvaluationResult(
            outcome=IssueEvaluationOutcome.PARTIAL,
            confidence=0.42,
            summary="Custom evaluation result",
            requires_followup=False,
        )

        async def custom_evaluator(issue):
            return custom_result

        evaluation_service.set_evaluator(custom_evaluator)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            result = await evaluation_service.evaluate_issue("issue_abc123")

        assert result.confidence == 0.42
        assert result.summary == "Custom evaluation result"


class TestGlobalInstance:
    """Test global instance management."""

    def test_set_get_service(self, evaluation_service):
        """Test setting and getting global service."""
        set_issue_evaluation_service(evaluation_service)

        retrieved = get_issue_evaluation_service()
        assert retrieved is evaluation_service

        # Clean up
        set_issue_evaluation_service(None)

    def test_get_service_not_initialized(self):
        """Test getting service when not initialized raises error."""
        set_issue_evaluation_service(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_issue_evaluation_service()


class TestIssueEvaluationResultModel:
    """Test IssueEvaluationResult model."""

    def test_result_creation(self):
        """Test creating an evaluation result."""
        result = IssueEvaluationResult(
            outcome=IssueEvaluationOutcome.SUCCESS,
            confidence=0.9,
            summary="All objectives met",
            accomplishments=["Feature A", "Feature B"],
            gaps=[],
        )

        assert result.outcome == IssueEvaluationOutcome.SUCCESS
        assert result.confidence == 0.9
        assert len(result.accomplishments) == 2
        assert result.requires_followup is False
        assert result.evaluator_version == "1.0"

    def test_result_with_root_cause(self):
        """Test result with root cause analysis."""
        result = IssueEvaluationResult(
            outcome=IssueEvaluationOutcome.FAILURE,
            confidence=0.8,
            summary="Failed due to technical limitations",
            gaps=["Missing feature X"],
            root_cause_category=RootCauseCategory.TECHNICAL_LIMITATION,
            root_cause_analysis="The underlying API doesn't support this",
            requires_followup=True,
        )

        assert result.root_cause_category == RootCauseCategory.TECHNICAL_LIMITATION
        assert result.requires_followup is True

    def test_confidence_bounds(self):
        """Test confidence is bounded between 0 and 1."""
        result = IssueEvaluationResult(
            outcome=IssueEvaluationOutcome.SUCCESS,
            confidence=0.0,
            summary="Low confidence",
        )
        assert result.confidence == 0.0

        result = IssueEvaluationResult(
            outcome=IssueEvaluationOutcome.SUCCESS,
            confidence=1.0,
            summary="High confidence",
        )
        assert result.confidence == 1.0

        with pytest.raises(ValueError):
            IssueEvaluationResult(
                outcome=IssueEvaluationOutcome.SUCCESS,
                confidence=1.5,
                summary="Invalid",
            )

    def test_outcome_enum_values(self):
        """Test all outcome enum values."""
        assert IssueEvaluationOutcome.SUCCESS.value == "success"
        assert IssueEvaluationOutcome.PARTIAL.value == "partial"
        assert IssueEvaluationOutcome.FAILURE.value == "failure"

    def test_root_cause_enum_values(self):
        """Test all root cause category enum values."""
        assert RootCauseCategory.INCOMPLETE_REQUIREMENTS.value == "incomplete_requirements"
        assert RootCauseCategory.TECHNICAL_LIMITATION.value == "technical_limitation"
        assert RootCauseCategory.SCOPE_CREEP.value == "scope_creep"
        assert RootCauseCategory.DEPENDENCY_ISSUE.value == "dependency_issue"
        assert RootCauseCategory.OTHER.value == "other"


class TestProcessQueue:
    """Test background queue processing."""

    @pytest.mark.asyncio
    async def test_queue_processes_items(
        self, evaluation_service, mock_issue_ops_service, sample_issue
    ):
        """Test that the background queue processes queued items."""
        mock_issue_ops_service.get_issue.return_value = sample_issue

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            await evaluation_service.start()

            # Queue an item
            await evaluation_service.queue_for_evaluation("issue_abc123")

            # Wait for processing
            await asyncio.sleep(0.5)

            await evaluation_service.stop()

        # Issue should have been evaluated (status updated)
        assert sample_issue.evaluation_status == EvaluationStatus.EVALUATED
