"""Tests for GoalCommentService."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from services.goal_comment_service import (
    GoalCommentService,
    get_goal_comment_service,
    set_goal_comment_service
)
from models.work_map import (
    GoalComment,
    GoalCommentCreateRequest,
    GoalCommentUpdateRequest,
    EvaluationStatus,
    EvaluationResult,
    CommentType,
    ConversationStatus,
    Goal,
    GoalStatus,
    IssuePriority,
    IssueArea
)


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = MagicMock()
    redis._redis = MagicMock()
    redis._redis.hset = AsyncMock()
    redis._redis.hgetall = AsyncMock(return_value={})
    redis._redis.delete = AsyncMock()
    redis._redis.sadd = AsyncMock()
    redis._redis.srem = AsyncMock()
    redis._redis.scan = AsyncMock(return_value=(0, []))
    redis._prefix = "claudevn:"
    return redis


@pytest.fixture
def service():
    """Create service without Redis for in-memory testing."""
    return GoalCommentService(redis_client=None)


@pytest.fixture
def service_with_redis(mock_redis):
    """Create service with mocked Redis."""
    return GoalCommentService(redis_client=mock_redis)


@pytest.fixture
def sample_goal():
    """Create a sample goal for testing."""
    return Goal(
        goal_id="goal_test123",
        title="Test Goal",
        description="Test goal description",
        priority=IssuePriority.P1,
        status=GoalStatus.PLANNING
    )


@pytest.fixture
def sample_comment_request():
    """Create a sample comment creation request."""
    return GoalCommentCreateRequest(
        content="This is a test comment",
        priority=IssuePriority.P1,
        area=IssueArea.API,
        created_by="test_user"
    )


class TestGoalCommentServiceInit:
    """Test GoalCommentService initialization."""

    def test_init_without_redis(self):
        """Test initialization without Redis client."""
        service = GoalCommentService()
        assert service._redis is None
        assert service._comments == {}
        assert service._goal_comments_index == {}
        assert service._initialized is False

    def test_init_with_redis(self, mock_redis):
        """Test initialization with Redis client."""
        service = GoalCommentService(redis_client=mock_redis)
        assert service._redis is mock_redis
        assert service._comments == {}

    @pytest.mark.asyncio
    async def test_initialize(self, service):
        """Test service initialization."""
        await service.initialize()
        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_with_redis(self, service_with_redis, mock_redis):
        """Test service initialization loads from Redis."""
        await service_with_redis.initialize()
        assert service_with_redis._initialized is True
        mock_redis._redis.scan.assert_called()


class TestGoalCommentCRUD:
    """Test GoalComment CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_comment(self, service, sample_goal, sample_comment_request):
        """Test creating a comment."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        comment = await service.create_comment(sample_goal.goal_id, sample_comment_request)

        assert comment.comment_id.startswith("comment_")
        assert comment.goal_id == sample_goal.goal_id
        assert comment.content == "This is a test comment"
        assert comment.priority == IssuePriority.P1
        assert comment.area == IssueArea.API
        assert comment.evaluation_status == EvaluationStatus.NOT_EVALUATED
        assert comment.evaluation_result is None
        assert comment.created_by == "test_user"

    @pytest.mark.asyncio
    async def test_create_comment_minimal(self, service, sample_goal):
        """Test creating a comment with minimal fields."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        request = GoalCommentCreateRequest(content="Simple comment")
        comment = await service.create_comment(sample_goal.goal_id, request)

        assert comment.content == "Simple comment"
        assert comment.priority is None
        assert comment.area is None
        assert comment.created_by == "user"  # default

    @pytest.mark.asyncio
    async def test_get_comment(self, service, sample_goal, sample_comment_request):
        """Test getting a comment by ID."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        created = await service.create_comment(sample_goal.goal_id, sample_comment_request)
        comment = await service.get_comment(created.comment_id)

        assert comment is not None
        assert comment.comment_id == created.comment_id
        assert comment.content == "This is a test comment"

    @pytest.mark.asyncio
    async def test_get_nonexistent_comment(self, service):
        """Test getting nonexistent comment returns None."""
        comment = await service.get_comment("nonexistent-comment-id")
        assert comment is None

    @pytest.mark.asyncio
    async def test_list_comments(self, service, sample_goal):
        """Test listing comments for a goal."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        for i in range(3):
            await service.create_comment(
                sample_goal.goal_id,
                GoalCommentCreateRequest(content=f"Comment {i}")
            )

        result = await service.list_comments(sample_goal.goal_id)

        assert result.total == 3
        assert len(result.items) == 3
        assert result.goal_id == sample_goal.goal_id

    @pytest.mark.asyncio
    async def test_list_comments_empty(self, service, sample_goal):
        """Test listing comments for goal with no comments."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        result = await service.list_comments(sample_goal.goal_id)

        assert result.total == 0
        assert len(result.items) == 0
        assert result.conversation_status == ConversationStatus.NO_COMMENTS

    @pytest.mark.asyncio
    async def test_list_comments_sorted_by_created_at(self, service, sample_goal):
        """Test that comments are sorted by created_at."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        # Create comments
        await service.create_comment(
            sample_goal.goal_id,
            GoalCommentCreateRequest(content="First")
        )
        await service.create_comment(
            sample_goal.goal_id,
            GoalCommentCreateRequest(content="Second")
        )

        result = await service.list_comments(sample_goal.goal_id)

        # First created should be first in list
        assert result.items[0].content == "First"
        assert result.items[1].content == "Second"

    @pytest.mark.asyncio
    async def test_update_comment_content(self, service, sample_goal, sample_comment_request):
        """Test updating comment content."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        comment = await service.create_comment(sample_goal.goal_id, sample_comment_request)

        update_request = GoalCommentUpdateRequest(content="Updated content")
        updated = await service.update_comment(comment.comment_id, update_request)

        assert updated is not None
        assert updated.content == "Updated content"

    @pytest.mark.asyncio
    async def test_update_comment_evaluation_status(self, service, sample_goal, sample_comment_request):
        """Test updating comment evaluation status."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        comment = await service.create_comment(sample_goal.goal_id, sample_comment_request)

        update_request = GoalCommentUpdateRequest(
            evaluation_status=EvaluationStatus.EVALUATING
        )
        updated = await service.update_comment(comment.comment_id, update_request)

        assert updated.evaluation_status == EvaluationStatus.EVALUATING

    @pytest.mark.asyncio
    async def test_update_comment_evaluation_result(self, service, sample_goal, sample_comment_request):
        """Test updating comment with evaluation result."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        comment = await service.create_comment(sample_goal.goal_id, sample_comment_request)

        eval_result = EvaluationResult(
            comment_type=CommentType.SUGGESTION,
            entities=["feature", "api"],
            suggested_actions=[],
            confidence=0.95,
            summary="Feature suggestion for API"
        )
        update_request = GoalCommentUpdateRequest(
            evaluation_status=EvaluationStatus.EVALUATED,
            evaluation_result=eval_result
        )
        updated = await service.update_comment(comment.comment_id, update_request)

        assert updated.evaluation_status == EvaluationStatus.EVALUATED
        assert updated.evaluation_result.comment_type == CommentType.SUGGESTION
        assert updated.evaluation_result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_update_nonexistent_comment(self, service):
        """Test updating nonexistent comment returns None."""
        update_request = GoalCommentUpdateRequest(content="New content")
        result = await service.update_comment("nonexistent", update_request)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_comment(self, service, sample_goal, sample_comment_request):
        """Test deleting a comment."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        comment = await service.create_comment(sample_goal.goal_id, sample_comment_request)

        result = await service.delete_comment(comment.comment_id)

        assert result is True
        assert await service.get_comment(comment.comment_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_comment(self, service):
        """Test deleting nonexistent comment returns False."""
        result = await service.delete_comment("nonexistent")
        assert result is False


class TestConversationStatus:
    """Test conversation status aggregation."""

    @pytest.mark.asyncio
    async def test_no_comments_status(self, service, sample_goal):
        """Test NO_COMMENTS status when no comments exist."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        result = await service.list_comments(sample_goal.goal_id)
        assert result.conversation_status == ConversationStatus.NO_COMMENTS

    @pytest.mark.asyncio
    async def test_pending_status(self, service, sample_goal):
        """Test PENDING status when comments are not evaluated."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        await service.create_comment(
            sample_goal.goal_id,
            GoalCommentCreateRequest(content="Comment 1")
        )

        result = await service.list_comments(sample_goal.goal_id)
        assert result.conversation_status == ConversationStatus.PENDING

    @pytest.mark.asyncio
    async def test_evaluating_status(self, service, sample_goal):
        """Test EVALUATING status when at least one comment is being evaluated."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        comment = await service.create_comment(
            sample_goal.goal_id,
            GoalCommentCreateRequest(content="Comment 1")
        )

        await service.update_comment(
            comment.comment_id,
            GoalCommentUpdateRequest(evaluation_status=EvaluationStatus.EVALUATING)
        )

        result = await service.list_comments(sample_goal.goal_id)
        assert result.conversation_status == ConversationStatus.EVALUATING

    @pytest.mark.asyncio
    async def test_complete_status(self, service, sample_goal):
        """Test COMPLETE status when all comments are evaluated."""
        sample_goal.goal_text_evaluated = True
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        comment1 = await service.create_comment(
            sample_goal.goal_id,
            GoalCommentCreateRequest(content="Comment 1")
        )
        comment2 = await service.create_comment(
            sample_goal.goal_id,
            GoalCommentCreateRequest(content="Comment 2")
        )

        await service.update_comment(
            comment1.comment_id,
            GoalCommentUpdateRequest(evaluation_status=EvaluationStatus.EVALUATED)
        )
        await service.update_comment(
            comment2.comment_id,
            GoalCommentUpdateRequest(evaluation_status=EvaluationStatus.EVALUATED)
        )

        result = await service.list_comments(sample_goal.goal_id)
        assert result.conversation_status == ConversationStatus.COMPLETE

    @pytest.mark.asyncio
    async def test_mixed_status_with_evaluating(self, service, sample_goal):
        """Test EVALUATING takes precedence over PENDING."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        # Create two comments - one not evaluated, one evaluating
        await service.create_comment(
            sample_goal.goal_id,
            GoalCommentCreateRequest(content="Comment 1")
        )
        comment2 = await service.create_comment(
            sample_goal.goal_id,
            GoalCommentCreateRequest(content="Comment 2")
        )

        await service.update_comment(
            comment2.comment_id,
            GoalCommentUpdateRequest(evaluation_status=EvaluationStatus.EVALUATING)
        )

        result = await service.list_comments(sample_goal.goal_id)
        assert result.conversation_status == ConversationStatus.EVALUATING

    @pytest.mark.asyncio
    async def test_goal_conversation_status_updates(self, service, sample_goal):
        """Test that goal conversation status is updated when comments change."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        # Initially no comments
        assert sample_goal.conversation_status == ConversationStatus.NO_COMMENTS

        # Add a comment - should become PENDING
        comment = await service.create_comment(
            sample_goal.goal_id,
            GoalCommentCreateRequest(content="New comment")
        )
        assert sample_goal.conversation_status == ConversationStatus.PENDING

        # Update to evaluating
        await service.update_comment(
            comment.comment_id,
            GoalCommentUpdateRequest(evaluation_status=EvaluationStatus.EVALUATING)
        )
        assert sample_goal.conversation_status == ConversationStatus.EVALUATING

        # Update to evaluated - also need goal_text_evaluated for COMPLETE
        sample_goal.goal_text_evaluated = True
        await service.update_comment(
            comment.comment_id,
            GoalCommentUpdateRequest(evaluation_status=EvaluationStatus.EVALUATED)
        )
        assert sample_goal.conversation_status == ConversationStatus.COMPLETE


class TestGetCommentsByStatus:
    """Test getting comments by evaluation status."""

    @pytest.mark.asyncio
    async def test_get_comments_by_status(self, service, sample_goal):
        """Test getting comments filtered by evaluation status."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})

        # Create comments with different statuses
        comment1 = await service.create_comment(
            sample_goal.goal_id,
            GoalCommentCreateRequest(content="Comment 1")
        )
        comment2 = await service.create_comment(
            sample_goal.goal_id,
            GoalCommentCreateRequest(content="Comment 2")
        )

        await service.update_comment(
            comment2.comment_id,
            GoalCommentUpdateRequest(evaluation_status=EvaluationStatus.EVALUATED)
        )

        # Get not evaluated
        not_evaluated = await service.get_comments_by_status(EvaluationStatus.NOT_EVALUATED)
        assert len(not_evaluated) == 1
        assert not_evaluated[0].comment_id == comment1.comment_id

        # Get evaluated
        evaluated = await service.get_comments_by_status(EvaluationStatus.EVALUATED)
        assert len(evaluated) == 1
        assert evaluated[0].comment_id == comment2.comment_id


class TestGoalCommentServiceGlobals:
    """Test global instance management."""

    def test_set_get_service(self):
        """Test setting and getting global service."""
        service = GoalCommentService()
        set_goal_comment_service(service)

        retrieved = get_goal_comment_service()
        assert retrieved is service

    def test_get_service_not_initialized(self):
        """Test getting service when not initialized raises error."""
        set_goal_comment_service(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_goal_comment_service()


class TestGoalCommentModels:
    """Test GoalComment model validation."""

    def test_goal_comment_model(self):
        """Test GoalComment model creation."""
        comment = GoalComment(
            comment_id="comment_test123",
            goal_id="goal_test123",
            content="Test content",
            priority=IssuePriority.P1,
            area=IssueArea.API,
            evaluation_status=EvaluationStatus.NOT_EVALUATED,
            created_by="user"
        )

        assert comment.comment_id == "comment_test123"
        assert comment.goal_id == "goal_test123"
        assert comment.content == "Test content"
        assert comment.priority == IssuePriority.P1
        assert comment.area == IssueArea.API
        assert comment.evaluation_status == EvaluationStatus.NOT_EVALUATED
        assert comment.evaluation_result is None

    def test_goal_comment_model_nullable_fields(self):
        """Test GoalComment model with nullable fields."""
        comment = GoalComment(
            comment_id="comment_test123",
            goal_id="goal_test123",
            content="Test content",
            priority=None,
            area=None,
            evaluation_status=EvaluationStatus.NOT_EVALUATED,
            created_by="user"
        )

        assert comment.priority is None
        assert comment.area is None

    def test_evaluation_status_enum(self):
        """Test EvaluationStatus enum values."""
        assert EvaluationStatus.NOT_EVALUATED.value == "not_evaluated"
        assert EvaluationStatus.EVALUATING.value == "evaluating"
        assert EvaluationStatus.EVALUATED.value == "evaluated"

    def test_conversation_status_enum(self):
        """Test ConversationStatus enum values."""
        assert ConversationStatus.NO_COMMENTS.value == "no_comments"
        assert ConversationStatus.PENDING.value == "pending"
        assert ConversationStatus.EVALUATING.value == "evaluating"
        assert ConversationStatus.COMPLETE.value == "complete"
