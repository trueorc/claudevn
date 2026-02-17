"""Tests for GoalEvaluationService."""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from services.goal_evaluation_service import (
    GoalEvaluationService,
    get_goal_evaluation_service,
    set_goal_evaluation_service,
    MAX_EVALUATION_RETRIES,
)
from services.goal_comment_service import GoalCommentService
from models.work_map import (
    GoalComment,
    GoalCommentCreateRequest,
    GoalCommentUpdateRequest,
    EvaluationStatus,
    EvaluationResult,
    CommentType,
    SuggestedAction,
    ConversationStatus,
    Goal,
    GoalStatus,
    IssuePriority,
    IssueArea,
)


@pytest.fixture
def mock_comment_service():
    """Create mock comment service."""
    service = MagicMock(spec=GoalCommentService)
    service.get_comment = AsyncMock()
    service.update_comment = AsyncMock()
    service.get_comments_by_status = AsyncMock(return_value=[])
    service.list_comments = AsyncMock()
    return service


@pytest.fixture
def sample_comment():
    """Create a sample comment for testing."""
    return GoalComment(
        comment_id="comment_abc123",
        goal_id="goal_test123",
        content="This is a test comment with a bug report",
        priority=IssuePriority.P1,
        area=IssueArea.API,
        evaluation_status=EvaluationStatus.NOT_EVALUATED,
        created_by="test_user",
    )


@pytest.fixture
def sample_comment_suggestion():
    """Create a sample comment with suggestion keywords."""
    return GoalComment(
        comment_id="comment_suggest456",
        goal_id="goal_test123",
        content="I suggest adding a new feature for better usability",
        priority=None,
        area=None,
        evaluation_status=EvaluationStatus.NOT_EVALUATED,
        created_by="test_user",
    )


@pytest.fixture
def sample_evaluation_result():
    """Create a sample evaluation result."""
    return EvaluationResult(
        comment_type=CommentType.BUG,
        entities=["API", "Authentication"],
        suggested_actions=[
            SuggestedAction(
                action_type="create_issue",
                description="Create bug fix issue",
                metadata={"issue_type": "bug"}
            )
        ],
        confidence=0.8,
        summary="Bug report related to API authentication",
        evaluator_version="1.0-test"
    )


@pytest.fixture
def evaluation_service(mock_comment_service):
    """Create evaluation service with mocked dependencies."""
    return GoalEvaluationService(
        comment_service=mock_comment_service,
        max_retries=3,
        retry_delay=0.1,
    )


class TestGoalEvaluationServiceInit:
    """Test GoalEvaluationService initialization."""

    def test_init_defaults(self, mock_comment_service):
        """Test initialization with default values."""
        service = GoalEvaluationService(comment_service=mock_comment_service)
        assert service._comment_service is mock_comment_service
        assert service._max_retries == MAX_EVALUATION_RETRIES
        assert service._running is False
        assert service._evaluator is None

    def test_init_custom_params(self, mock_comment_service):
        """Test initialization with custom parameters."""
        service = GoalEvaluationService(
            comment_service=mock_comment_service,
            max_retries=5,
            retry_delay=1.0,
        )
        assert service._max_retries == 5
        assert service._retry_delay == 1.0


class TestGoalEvaluationServiceLifecycle:
    """Test service start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_stop(self, evaluation_service):
        """Test starting and stopping the service."""
        await evaluation_service.start()
        assert evaluation_service.is_running() is True
        assert evaluation_service._processing_task is not None

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

        # Should be the same task
        assert task1 is task2

        await evaluation_service.stop()


class TestQueueForEvaluation:
    """Test queuing comments for evaluation."""

    @pytest.mark.asyncio
    async def test_queue_valid_comment(
        self, evaluation_service, mock_comment_service, sample_comment
    ):
        """Test queuing a valid comment."""
        mock_comment_service.get_comment.return_value = sample_comment

        result = await evaluation_service.queue_for_evaluation("comment_abc123")

        assert result is True
        assert evaluation_service.get_queue_size() == 1

    @pytest.mark.asyncio
    async def test_queue_nonexistent_comment(
        self, evaluation_service, mock_comment_service
    ):
        """Test queuing a nonexistent comment."""
        mock_comment_service.get_comment.return_value = None

        result = await evaluation_service.queue_for_evaluation("nonexistent")

        assert result is False
        assert evaluation_service.get_queue_size() == 0

    @pytest.mark.asyncio
    async def test_queue_already_evaluated_comment(
        self, evaluation_service, mock_comment_service, sample_comment
    ):
        """Test queuing a comment that's already evaluated."""
        sample_comment.evaluation_status = EvaluationStatus.EVALUATED
        mock_comment_service.get_comment.return_value = sample_comment

        result = await evaluation_service.queue_for_evaluation("comment_abc123")

        assert result is False
        assert evaluation_service.get_queue_size() == 0


class TestDefaultEvaluation:
    """Test the default evaluation heuristics."""

    def test_evaluate_bug_content(self, evaluation_service, sample_comment):
        """Test evaluation of bug-related content."""
        result = evaluation_service._default_evaluation(sample_comment)

        assert result.comment_type == CommentType.BUG
        assert result.confidence >= 0.6
        assert len(result.suggested_actions) > 0
        assert result.suggested_actions[0].action_type == "create_issue"

    def test_evaluate_suggestion_content(
        self, evaluation_service, sample_comment_suggestion
    ):
        """Test evaluation of suggestion content."""
        result = evaluation_service._default_evaluation(sample_comment_suggestion)

        assert result.comment_type == CommentType.SUGGESTION

    def test_evaluate_priority_content(self, evaluation_service):
        """Test evaluation of priority-related content."""
        comment = GoalComment(
            comment_id="comment_priority",
            goal_id="goal_test",
            content="This is urgent and needs immediate attention ASAP",
            evaluation_status=EvaluationStatus.NOT_EVALUATED,
        )

        result = evaluation_service._default_evaluation(comment)

        assert result.comment_type == CommentType.PRIORITY_INFLUENCE

    def test_evaluate_info_content(self, evaluation_service):
        """Test evaluation of general info content."""
        comment = GoalComment(
            comment_id="comment_info",
            goal_id="goal_test",
            content="Here is some information about the current state",
            evaluation_status=EvaluationStatus.NOT_EVALUATED,
        )

        result = evaluation_service._default_evaluation(comment)

        assert result.comment_type == CommentType.INFO

    def test_confidence_with_priority_and_area(self, evaluation_service, sample_comment):
        """Test that confidence increases with priority and area."""
        result = evaluation_service._default_evaluation(sample_comment)

        # Base confidence 0.6 + 0.1 (priority) + 0.1 (area) = 0.8
        # Use approximate comparison to handle floating point
        assert result.confidence >= 0.79  # Floating point safe


class TestEvaluateComment:
    """Test synchronous comment evaluation."""

    @pytest.mark.asyncio
    async def test_evaluate_success(
        self, evaluation_service, mock_comment_service, sample_comment
    ):
        """Test successful comment evaluation."""
        mock_comment_service.get_comment.return_value = sample_comment

        # Patch the broadcast to avoid needing event bus
        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            result = await evaluation_service.evaluate_comment("comment_abc123")

        assert result is not None
        assert result.comment_type == CommentType.BUG

        # Verify status updates were called
        assert mock_comment_service.update_comment.call_count >= 2  # evaluating, evaluated

    @pytest.mark.asyncio
    async def test_evaluate_nonexistent_comment(
        self, evaluation_service, mock_comment_service
    ):
        """Test evaluating a nonexistent comment."""
        mock_comment_service.get_comment.return_value = None

        result = await evaluation_service.evaluate_comment("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_with_custom_evaluator(
        self, evaluation_service, mock_comment_service, sample_comment, sample_evaluation_result
    ):
        """Test evaluation with a custom evaluator."""
        mock_comment_service.get_comment.return_value = sample_comment

        # Set custom evaluator
        async def custom_evaluator(comment):
            return sample_evaluation_result

        evaluation_service.set_evaluator(custom_evaluator)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            result = await evaluation_service.evaluate_comment("comment_abc123")

        assert result is sample_evaluation_result


class TestEvaluationRetry:
    """Test evaluation retry logic."""

    @pytest.mark.asyncio
    async def test_retry_on_failure(
        self, evaluation_service, mock_comment_service, sample_comment
    ):
        """Test that failed evaluations trigger retry."""
        sample_comment.evaluation_retry_count = 0
        mock_comment_service.get_comment.return_value = sample_comment

        # Set failing evaluator
        async def failing_evaluator(comment):
            raise ValueError("Evaluation failed")

        evaluation_service.set_evaluator(failing_evaluator)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            result = await evaluation_service.evaluate_comment("comment_abc123")

        assert result is None

        # Should have updated with incremented retry count
        update_calls = mock_comment_service.update_comment.call_args_list
        final_call = update_calls[-1]
        update_request = final_call[0][1]  # Second arg is the request

        assert update_request.evaluation_retry_count == 1
        assert update_request.evaluation_status == EvaluationStatus.NOT_EVALUATED

    @pytest.mark.asyncio
    async def test_mark_failed_after_max_retries(
        self, evaluation_service, mock_comment_service, sample_comment
    ):
        """Test that evaluation is marked as FAILED after max retries."""
        sample_comment.evaluation_retry_count = 3  # Already at max
        mock_comment_service.get_comment.return_value = sample_comment

        async def failing_evaluator(comment):
            raise ValueError("Evaluation failed")

        evaluation_service.set_evaluator(failing_evaluator)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            result = await evaluation_service.evaluate_comment("comment_abc123")

        assert result is None

        # Should have been marked as FAILED
        update_calls = mock_comment_service.update_comment.call_args_list
        final_call = update_calls[-1]
        update_request = final_call[0][1]

        assert update_request.evaluation_status == EvaluationStatus.FAILED


class TestBatchEvaluation:
    """Test batch/rollup evaluation."""

    @pytest.mark.asyncio
    async def test_evaluate_batch(
        self, evaluation_service, mock_comment_service, sample_comment
    ):
        """Test batch evaluation of goal comments."""
        comment2 = GoalComment(
            comment_id="comment_def456",
            goal_id="goal_test123",
            content="Another comment to evaluate",
            evaluation_status=EvaluationStatus.NOT_EVALUATED,
        )

        # First call returns the list, subsequent calls return individual comments
        mock_comment_service.list_comments.return_value = MagicMock(
            items=[sample_comment, comment2]
        )

        # get_comment is called multiple times per evaluate_comment call
        # Provide enough return values for all calls
        def get_comment_mock(comment_id):
            if comment_id == "comment_abc123":
                return sample_comment
            return comment2

        mock_comment_service.get_comment = AsyncMock(side_effect=get_comment_mock)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            results = await evaluation_service.evaluate_batch("goal_test123")

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_evaluate_batch_skips_evaluated(
        self, evaluation_service, mock_comment_service, sample_comment
    ):
        """Test that batch evaluation skips already-evaluated comments."""
        evaluated_comment = GoalComment(
            comment_id="comment_evaluated",
            goal_id="goal_test123",
            content="Already evaluated",
            evaluation_status=EvaluationStatus.EVALUATED,
        )

        mock_comment_service.list_comments.return_value = MagicMock(
            items=[sample_comment, evaluated_comment]
        )
        mock_comment_service.get_comment.return_value = sample_comment

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            results = await evaluation_service.evaluate_batch("goal_test123")

        # Only one should be evaluated
        assert len(results) == 1


class TestStatusChangeCallbacks:
    """Test status change callback functionality."""

    @pytest.mark.asyncio
    async def test_callback_on_evaluation(
        self, evaluation_service, mock_comment_service, sample_comment
    ):
        """Test that callbacks are triggered on status change."""
        mock_comment_service.get_comment.return_value = sample_comment

        callback_calls = []

        def callback(comment_id, status, result):
            callback_calls.append((comment_id, status, result))

        evaluation_service.on_status_change(callback)

        with patch.object(
            evaluation_service, '_broadcast_status_event', new_callable=AsyncMock
        ):
            await evaluation_service.evaluate_comment("comment_abc123")

        # Should have been called twice: evaluating, then evaluated
        assert len(callback_calls) == 2
        assert callback_calls[0][1] == EvaluationStatus.EVALUATING
        assert callback_calls[1][1] == EvaluationStatus.EVALUATED


class TestGlobalInstance:
    """Test global instance management."""

    def test_set_get_service(self, evaluation_service):
        """Test setting and getting global service."""
        set_goal_evaluation_service(evaluation_service)

        retrieved = get_goal_evaluation_service()
        assert retrieved is evaluation_service

    def test_get_service_not_initialized(self):
        """Test getting service when not initialized raises error."""
        set_goal_evaluation_service(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_goal_evaluation_service()


class TestEvaluationResultModel:
    """Test EvaluationResult model."""

    def test_evaluation_result_creation(self):
        """Test creating an evaluation result."""
        result = EvaluationResult(
            comment_type=CommentType.BUG,
            entities=["Feature", "Component"],
            suggested_actions=[
                SuggestedAction(
                    action_type="create_issue",
                    description="Create bug issue"
                )
            ],
            confidence=0.85,
            summary="Bug report identified"
        )

        assert result.comment_type == CommentType.BUG
        assert len(result.entities) == 2
        assert result.confidence == 0.85
        assert result.evaluator_version == "1.0"  # Default

    def test_evaluation_result_confidence_bounds(self):
        """Test that confidence is bounded between 0 and 1."""
        # Should accept valid values
        result = EvaluationResult(
            comment_type=CommentType.INFO,
            confidence=0.0,
            summary="Low confidence result"
        )
        assert result.confidence == 0.0

        result = EvaluationResult(
            comment_type=CommentType.INFO,
            confidence=1.0,
            summary="High confidence result"
        )
        assert result.confidence == 1.0

        # Should reject invalid values
        with pytest.raises(ValueError):
            EvaluationResult(
                comment_type=CommentType.INFO,
                confidence=1.5,
                summary="Invalid confidence"
            )


class TestSuggestedAction:
    """Test SuggestedAction model."""

    def test_suggested_action_creation(self):
        """Test creating a suggested action."""
        action = SuggestedAction(
            action_type="create_issue",
            description="Create a new issue",
            target="goal_123",
            metadata={"priority": "high"}
        )

        assert action.action_type == "create_issue"
        assert action.target == "goal_123"
        assert action.metadata["priority"] == "high"

    def test_suggested_action_optional_fields(self):
        """Test suggested action with optional fields."""
        action = SuggestedAction(
            action_type="update_priority",
            description="Increase priority"
        )

        assert action.target is None
        assert action.metadata == {}
