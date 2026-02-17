"""Tests for UnifiedDirectiveService.

Tests cover:
- Directive submission and storage
- Deterministic intent classification
- Routing to new_work handler (GoalService)
- Routing to priority_shift handler (DirectiveService)
- Routing to combined handler
- Clarification handling
- Conversation follow-ups
- Comment threading
- History listing
- Auto-process triggering after goal creation (#694)
- Global instance management
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.unified_directive import (
    DirectiveComment,
    DirectiveIntent,
    DirectiveLifecycleStatus,
    DirectiveOutcome,
    UnifiedDirective,
)
from services.unified_directive_service import (
    UnifiedDirectiveService,
    _generate_goal_title,
    get_unified_directive_service,
    set_unified_directive_service,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def suppress_auto_process():
    """Suppress background auto-process in all tests to prevent side effects.

    The _schedule_auto_process method fires asyncio.create_task which would
    try to import API-layer functions and start real decomposition. Patching
    it at the class level keeps every test isolated.
    """
    with patch.object(UnifiedDirectiveService, "_schedule_auto_process"):
        yield


@pytest.fixture
def service():
    """UnifiedDirectiveService with no Redis."""
    return UnifiedDirectiveService(redis_client=None)


@pytest.fixture
def mock_goal_service():
    """Mock GoalService for new_work routing."""
    mock = MagicMock()
    goal = MagicMock()
    goal.goal_id = "goal_test_001"
    mock.create_goal = AsyncMock(return_value=goal)
    # Default: no existing goals (dedup check finds nothing)
    mock.list_goals = AsyncMock(return_value=MagicMock(items=[]))
    mock._save_goal_to_redis = AsyncMock()
    return mock


@pytest.fixture
def mock_directive_service():
    """Mock DirectiveService for priority_shift routing."""
    mock = MagicMock()

    interpreted = MagicMock()
    interpreted.directive_id = "dir_old_001"
    interpreted.interpretation = MagicMock()
    mock.interpret = AsyncMock(return_value=interpreted)

    applied = MagicMock()
    applied.profile_version_before = 3
    applied.profile_version_after = 4
    mock.apply = AsyncMock(return_value=applied)

    return mock


# ============================================================================
# Deterministic Classification
# ============================================================================


class TestDeterministicClassification:
    """Tests for keyword-based intent classification."""

    def test_new_work_keywords(self, service):
        assert service._classify_deterministic(
            "Create a user authentication system"
        ) == DirectiveIntent.NEW_WORK

    def test_priority_shift_keywords(self, service):
        assert service._classify_deterministic(
            "Accelerate testing for the frontend"
        ) == DirectiveIntent.PRIORITY_SHIFT

    def test_combined_keywords(self, service):
        assert service._classify_deterministic(
            "Build payment integration and focus on security"
        ) == DirectiveIntent.COMBINED

    def test_focus_is_priority_shift(self, service):
        assert service._classify_deterministic(
            "Focus on testing"
        ) == DirectiveIntent.PRIORITY_SHIFT

    def test_deprioritize_is_priority_shift(self, service):
        assert service._classify_deterministic(
            "Deprioritize new features"
        ) == DirectiveIntent.PRIORITY_SHIFT

    def test_ambiguous_defaults_to_new_work(self, service):
        assert service._classify_deterministic(
            "Something about the system"
        ) == DirectiveIntent.NEW_WORK

    def test_implement_is_new_work(self, service):
        assert service._classify_deterministic(
            "Implement dark mode for the UI"
        ) == DirectiveIntent.NEW_WORK


# ============================================================================
# Submit — New Work
# ============================================================================


class TestSubmitNewWork:
    """Tests for submitting new_work directives."""

    @pytest.mark.asyncio
    async def test_submit_new_work(self, service, mock_goal_service):
        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            directive = await service.submit(
                project_id="project-001",
                text="Create a login page",
            )

        assert directive.intent == DirectiveIntent.NEW_WORK
        assert directive.lifecycle_status == DirectiveLifecycleStatus.COMPLETE
        assert directive.outcome is not None
        assert directive.outcome.goal_id_created == "goal_test_001"
        mock_goal_service.create_goal.assert_called_once()

    @pytest.mark.asyncio
    async def test_long_directive_gets_concise_title(self, service, mock_goal_service):
        """Long directive text should produce a concise goal title (#713)."""
        long_text = (
            "Build a simple REST API for a todo list application using Python "
            "and FastAPI. It should support CRUD operations for todo items with "
            "title, description, and done status. Include input validation and "
            "basic error handling."
        )
        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            await service.submit(project_id="project-001", text=long_text)

        call_args = mock_goal_service.create_goal.call_args
        request = call_args[0][0]
        assert len(request.title) <= 80
        assert request.description == long_text

    @pytest.mark.asyncio
    async def test_submit_stores_in_memory(self, service, mock_goal_service):
        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            directive = await service.submit(
                project_id="project-001",
                text="Build a dashboard",
            )

        stored = service._get("project-001", directive.directive_id)
        assert stored is not None
        assert stored.directive_id == directive.directive_id


# ============================================================================
# Goal Deduplication
# ============================================================================


class TestGoalDeduplication:
    """Tests that duplicate goals are not created from identical directives."""

    @pytest.mark.asyncio
    async def test_reuses_existing_goal_with_same_description(self, service, mock_goal_service):
        """If a goal with identical text exists, reuse it instead of creating."""
        existing_goal = MagicMock()
        existing_goal.goal_id = "goal_existing_001"
        existing_goal.description = "Create a login page"
        mock_goal_service.list_goals = AsyncMock(
            return_value=MagicMock(items=[existing_goal])
        )

        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            directive = await service.submit(
                project_id="project-001",
                text="Create a login page",
            )

        # Should reuse existing goal, not create a new one
        assert directive.outcome.goal_id_created == "goal_existing_001"
        mock_goal_service.create_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_goal_when_no_match(self, service, mock_goal_service):
        """If no matching goal exists, create a new one."""
        different_goal = MagicMock()
        different_goal.goal_id = "goal_different"
        different_goal.description = "Build a dashboard"
        mock_goal_service.list_goals = AsyncMock(
            return_value=MagicMock(items=[different_goal])
        )

        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            directive = await service.submit(
                project_id="project-001",
                text="Create a login page",
            )

        # Should create a new goal since descriptions don't match
        assert directive.outcome.goal_id_created == "goal_test_001"
        mock_goal_service.create_goal.assert_called_once()


# ============================================================================
# Intent Mapping on Goal Creation
# ============================================================================


class TestIntentMapping:
    """Tests that directive intent is mapped to goal intent fields."""

    @pytest.mark.asyncio
    async def test_new_work_sets_goal_primary_intent(self, service, mock_goal_service):
        """Goals from new_work directives get primary_intent=EXPANSION."""
        from models.work_map import GoalIntentType

        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            directive = await service.submit(
                project_id="project-001",
                text="Create a login page",
            )

        goal = mock_goal_service.create_goal.return_value
        assert goal.primary_intent == GoalIntentType.EXPANSION
        assert goal.intent_strength == 0.8
        assert len(goal.intent_signals) == 1
        assert goal.intent_signals[0].intent_type == GoalIntentType.EXPANSION
        assert goal.intent_signals[0].detected_from == "directive"
        assert goal.intent_signals[0].source_id == directive.directive_id
        mock_goal_service._save_goal_to_redis.assert_awaited_once()

    def test_map_directive_to_goal_intent(self, service):
        """Test the static mapping from directive intent to goal intent."""
        from models.work_map import GoalIntentType

        assert service._map_directive_to_goal_intent(DirectiveIntent.NEW_WORK) == GoalIntentType.EXPANSION
        assert service._map_directive_to_goal_intent(DirectiveIntent.PRIORITY_SHIFT) == GoalIntentType.TARGETED_INVESTMENT
        assert service._map_directive_to_goal_intent(DirectiveIntent.COMBINED) == GoalIntentType.EXPANSION
        assert service._map_directive_to_goal_intent(DirectiveIntent.CLARIFICATION) is None
        assert service._map_directive_to_goal_intent(DirectiveIntent.CONVERSATION) is None


# ============================================================================
# Submit — Priority Shift
# ============================================================================


class TestSubmitPriorityShift:
    """Tests for submitting priority_shift directives."""

    @pytest.mark.asyncio
    async def test_submit_priority_shift(self, service, mock_directive_service):
        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.directive_service.get_directive_service",
            return_value=mock_directive_service,
        ):
            directive = await service.submit(
                project_id="project-001",
                text="Accelerate testing efforts",
            )

        assert directive.intent == DirectiveIntent.PRIORITY_SHIFT
        assert directive.lifecycle_status == DirectiveLifecycleStatus.COMPLETE
        assert directive.outcome is not None
        assert directive.outcome.profile_changes_applied is True
        assert directive.outcome.profile_version_before == 3
        assert directive.outcome.profile_version_after == 4
        mock_directive_service.interpret.assert_called_once()
        mock_directive_service.apply.assert_called_once()


# ============================================================================
# Submit — Combined
# ============================================================================


class TestSubmitCombined:
    """Tests for submitting combined directives."""

    @pytest.mark.asyncio
    async def test_submit_combined(
        self, service, mock_goal_service, mock_directive_service
    ):
        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ), patch(
            "services.directive_service.get_directive_service",
            return_value=mock_directive_service,
        ):
            directive = await service.submit(
                project_id="project-001",
                text="Build payment flow and accelerate security testing",
            )

        assert directive.intent == DirectiveIntent.COMBINED
        assert directive.lifecycle_status == DirectiveLifecycleStatus.COMPLETE
        assert directive.outcome is not None
        assert directive.outcome.goal_id_created == "goal_test_001"
        assert directive.outcome.profile_changes_applied is True


# ============================================================================
# Submit — Failed Processing
# ============================================================================


class TestSubmitFailure:
    """Tests for directive submission when handlers fail."""

    @pytest.mark.asyncio
    async def test_new_work_failure_sets_failed(self, service):
        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            side_effect=RuntimeError("Goal service not initialized"),
        ):
            directive = await service.submit(
                project_id="project-001",
                text="Create something new",
            )

        assert directive.lifecycle_status == DirectiveLifecycleStatus.FAILED


# ============================================================================
# Conversation Follow-ups
# ============================================================================


class TestConversation:
    """Tests for conversation follow-ups."""

    @pytest.mark.asyncio
    async def test_conversation_creates_child(self, service, mock_goal_service):
        # Create parent directive first
        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            parent = await service.submit(
                project_id="project-001",
                text="Create a login page",
            )

        # Submit follow-up
        child = await service.submit(
            project_id="project-001",
            text="Also add OAuth support",
            parent_directive_id=parent.directive_id,
        )

        assert child.intent == DirectiveIntent.CONVERSATION
        assert child.parent_directive_id == parent.directive_id
        assert child.lifecycle_status == DirectiveLifecycleStatus.COMPLETE

    @pytest.mark.asyncio
    async def test_conversation_adds_comment_to_parent(
        self, service, mock_goal_service
    ):
        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            parent = await service.submit(
                project_id="project-001",
                text="Build a dashboard",
            )

        await service.submit(
            project_id="project-001",
            text="Include analytics charts",
            parent_directive_id=parent.directive_id,
        )

        updated_parent = service._get("project-001", parent.directive_id)
        assert len(updated_parent.comments) == 1
        assert "analytics charts" in updated_parent.comments[0].content


# ============================================================================
# Comments
# ============================================================================


class TestComments:
    """Tests for comment threading."""

    @pytest.mark.asyncio
    async def test_add_comment(self, service, mock_goal_service):
        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            directive = await service.submit(
                project_id="project-001",
                text="Create a login page",
            )

        result = await service.add_comment(
            project_id="project-001",
            directive_id=directive.directive_id,
            content="What about SSO?",
        )

        assert len(result.comments) == 1
        assert result.comments[0].content == "What about SSO?"
        assert result.comments[0].created_by == "user"

    @pytest.mark.asyncio
    async def test_add_comment_nonexistent_raises(self, service):
        with pytest.raises(ValueError, match="not found"):
            await service.add_comment(
                project_id="project-001",
                directive_id="nonexistent",
                content="test",
            )


# ============================================================================
# Queries
# ============================================================================


class TestQueries:
    """Tests for get/list queries."""

    @pytest.mark.asyncio
    async def test_get_directive(self, service, mock_goal_service):
        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            directive = await service.submit(
                project_id="project-001",
                text="Create a login page",
            )

        result = await service.get_directive("project-001", directive.directive_id)
        assert result is not None
        assert result.directive_id == directive.directive_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, service):
        result = await service.get_directive("project-001", "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_directives(self, service, mock_goal_service):
        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            await service.submit("project-001", "Create login")
            await service.submit("project-001", "Create dashboard")

        results = await service.list_directives("project-001")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_most_recent_first(self, service, mock_goal_service):
        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            d1 = await service.submit("project-001", "Create login")
            d2 = await service.submit("project-001", "Create dashboard")

        results = await service.list_directives("project-001")
        assert results[0].directive_id == d2.directive_id

    @pytest.mark.asyncio
    async def test_list_empty_project(self, service):
        results = await service.list_directives("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_list_respects_limit(self, service, mock_goal_service):
        with patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            for i in range(5):
                await service.submit("project-001", f"Create item {i}")

        results = await service.list_directives("project-001", limit=3)
        assert len(results) == 3


# ============================================================================
# Redis History (ID-based, not snapshot)
# ============================================================================


class TestRedisHistory:
    """Tests for the ID-based Redis history list (fix for #676).

    The history list stores only directive IDs, and list_directives
    fetches current state from individual item keys — ensuring list
    results always match get_directive results.
    """

    @pytest.mark.asyncio
    async def test_append_stores_only_directive_id(self):
        """_append_to_history pushes only the directive_id, not a JSON snapshot."""
        mock_redis_inner = AsyncMock()
        mock_redis_inner.lpush = AsyncMock()
        mock_redis_inner.ltrim = AsyncMock()

        mock_redis = MagicMock()
        mock_redis._redis = mock_redis_inner
        mock_redis._prefix = "claudevn:"

        svc = UnifiedDirectiveService(redis_client=mock_redis)

        directive = UnifiedDirective(
            directive_id="udir_test001",
            project_id="project-001",
            text="Build something",
        )
        await svc._append_to_history(directive)

        # Should push the directive_id string, not JSON
        mock_redis_inner.lpush.assert_called_once()
        pushed_value = mock_redis_inner.lpush.call_args[0][1]
        assert pushed_value == "udir_test001"

    @pytest.mark.asyncio
    async def test_load_history_fetches_from_item_keys(self):
        """_load_history_from_redis reads IDs from list, then fetches item keys."""
        directive = UnifiedDirective(
            directive_id="udir_abc",
            project_id="project-001",
            text="Build a thing",
            intent=DirectiveIntent.NEW_WORK,
            lifecycle_status=DirectiveLifecycleStatus.COMPLETE,
        )

        mock_redis_inner = AsyncMock()
        # History list returns directive IDs
        mock_redis_inner.lrange = AsyncMock(return_value=[b"udir_abc"])
        # Item key returns current state
        mock_redis_inner.get = AsyncMock(return_value=directive.model_dump_json().encode())

        mock_redis = MagicMock()
        mock_redis._redis = mock_redis_inner
        mock_redis._prefix = "claudevn:"

        svc = UnifiedDirectiveService(redis_client=mock_redis)
        results = await svc._load_history_from_redis("project-001")

        assert len(results) == 1
        assert results[0].directive_id == "udir_abc"
        assert results[0].intent == DirectiveIntent.NEW_WORK
        assert results[0].lifecycle_status == DirectiveLifecycleStatus.COMPLETE

        # Verify it fetched from the item key
        mock_redis_inner.get.assert_called_once_with(
            "claudevn:unified_directive:item:project-001:udir_abc"
        )

    @pytest.mark.asyncio
    async def test_load_history_skips_missing_item_keys(self):
        """If an item key is missing (deleted), the directive is skipped."""
        mock_redis_inner = AsyncMock()
        mock_redis_inner.lrange = AsyncMock(return_value=[b"udir_a", b"udir_b"])
        # First ID has data, second is missing
        mock_redis_inner.get = AsyncMock(side_effect=[
            UnifiedDirective(
                directive_id="udir_a",
                project_id="project-001",
                text="First",
            ).model_dump_json().encode(),
            None,
        ])

        mock_redis = MagicMock()
        mock_redis._redis = mock_redis_inner
        mock_redis._prefix = "claudevn:"

        svc = UnifiedDirectiveService(redis_client=mock_redis)
        results = await svc._load_history_from_redis("project-001")

        assert len(results) == 1
        assert results[0].directive_id == "udir_a"

    @pytest.mark.asyncio
    async def test_list_returns_current_state_not_snapshot(self):
        """list_directives returns up-to-date state, not stale creation snapshot.

        This is the core regression test for issue #676.
        """
        directive = UnifiedDirective(
            directive_id="udir_fresh",
            project_id="project-001",
            text="Create a login page",
            intent=DirectiveIntent.NEW_WORK,
            lifecycle_status=DirectiveLifecycleStatus.COMPLETE,
            outcome=DirectiveOutcome(goal_id_created="goal_123"),
        )

        mock_redis_inner = AsyncMock()
        mock_redis_inner.lrange = AsyncMock(return_value=[b"udir_fresh"])
        mock_redis_inner.get = AsyncMock(return_value=directive.model_dump_json().encode())

        mock_redis = MagicMock()
        mock_redis._redis = mock_redis_inner
        mock_redis._prefix = "claudevn:"

        svc = UnifiedDirectiveService(redis_client=mock_redis)
        results = await svc.list_directives("project-001")

        assert len(results) == 1
        # Should reflect CURRENT state (complete, with intent and outcome)
        assert results[0].lifecycle_status == DirectiveLifecycleStatus.COMPLETE
        assert results[0].intent == DirectiveIntent.NEW_WORK
        assert results[0].outcome is not None
        assert results[0].outcome.goal_id_created == "goal_123"

    @pytest.mark.asyncio
    async def test_load_history_handles_string_ids(self):
        """History list entries may be strings (not bytes) depending on Redis client."""
        directive = UnifiedDirective(
            directive_id="udir_str",
            project_id="project-001",
            text="Something",
        )

        mock_redis_inner = AsyncMock()
        mock_redis_inner.lrange = AsyncMock(return_value=["udir_str"])  # string, not bytes
        mock_redis_inner.get = AsyncMock(return_value=directive.model_dump_json())

        mock_redis = MagicMock()
        mock_redis._redis = mock_redis_inner
        mock_redis._prefix = "claudevn:"

        svc = UnifiedDirectiveService(redis_client=mock_redis)
        results = await svc._load_history_from_redis("project-001")

        assert len(results) == 1
        assert results[0].directive_id == "udir_str"


# ============================================================================
# Global Instance
# ============================================================================


# ============================================================================
# Classify via Compute
# ============================================================================


class TestClassifyViaCompute:
    """Tests for SSE-based intent classification via compute."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_sse_manager(self, service):
        """When SSE manager is not initialized, returns None."""
        with patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=None,
        ):
            directive = UnifiedDirective(
                directive_id="test-001",
                project_id="project-001",
                text="Create a login page",
            )
            result = await service._classify_via_compute(directive)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_idle_connections(self, service):
        """When no idle compute connections, returns None."""
        mock_sse = MagicMock()
        mock_sse.get_idle_connections.return_value = []

        with patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ):
            directive = UnifiedDirective(
                directive_id="test-001",
                project_id="project-001",
                text="Create a login page",
            )
            result = await service._classify_via_compute(directive)

        assert result is None

    @pytest.mark.asyncio
    async def test_sends_sse_event_and_returns_intent(self, service):
        """Dispatches classification task via SSE and polls Redis for result."""
        mock_sse = MagicMock()
        mock_sse.get_idle_connections.return_value = ["compute-abc"]
        mock_sse.send_event = AsyncMock()

        with patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ), patch.object(
            service,
            "_poll_for_result",
            new_callable=AsyncMock,
            return_value="new_work",
        ):
            directive = UnifiedDirective(
                directive_id="test-001",
                project_id="project-001",
                text="Build a payment system",
            )
            result = await service._classify_via_compute(directive)

        assert result == DirectiveIntent.NEW_WORK
        mock_sse.send_event.assert_called_once()
        call_kwargs = mock_sse.send_event.call_args
        assert call_kwargs[1]["compute_id"] == "compute-abc"
        assert call_kwargs[1]["event_type"] == "task"
        assert call_kwargs[1]["data"]["type"] == "intent_classification"

    @pytest.mark.asyncio
    async def test_returns_priority_shift_from_compute(self, service):
        """Compute returns priority_shift intent."""
        mock_sse = MagicMock()
        mock_sse.get_idle_connections.return_value = ["compute-abc"]
        mock_sse.send_event = AsyncMock()

        with patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ), patch.object(
            service,
            "_poll_for_result",
            new_callable=AsyncMock,
            return_value="priority_shift",
        ):
            directive = UnifiedDirective(
                directive_id="test-001",
                project_id="project-001",
                text="Focus on security",
            )
            result = await service._classify_via_compute(directive)

        assert result == DirectiveIntent.PRIORITY_SHIFT

    @pytest.mark.asyncio
    async def test_returns_none_when_poll_times_out(self, service):
        """When polling returns None (timeout), returns None."""
        mock_sse = MagicMock()
        mock_sse.get_idle_connections.return_value = ["compute-abc"]
        mock_sse.send_event = AsyncMock()

        with patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ), patch.object(
            service,
            "_poll_for_result",
            new_callable=AsyncMock,
            return_value=None,
        ):
            directive = UnifiedDirective(
                directive_id="test-001",
                project_id="project-001",
                text="Something",
            )
            result = await service._classify_via_compute(directive)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_compute_response(self, service):
        """When compute returns unrecognized intent string, returns None."""
        mock_sse = MagicMock()
        mock_sse.get_idle_connections.return_value = ["compute-abc"]
        mock_sse.send_event = AsyncMock()

        with patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ), patch.object(
            service,
            "_poll_for_result",
            new_callable=AsyncMock,
            return_value="unknown_intent_type",
        ):
            directive = UnifiedDirective(
                directive_id="test-001",
                project_id="project-001",
                text="Something",
            )
            result = await service._classify_via_compute(directive)

        assert result is None

    @pytest.mark.asyncio
    async def test_strips_whitespace_and_quotes(self, service):
        """Compute result with extra whitespace/quotes is cleaned."""
        mock_sse = MagicMock()
        mock_sse.get_idle_connections.return_value = ["compute-abc"]
        mock_sse.send_event = AsyncMock()

        with patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ), patch.object(
            service,
            "_poll_for_result",
            new_callable=AsyncMock,
            return_value='  "combined"  ',
        ):
            directive = UnifiedDirective(
                directive_id="test-001",
                project_id="project-001",
                text="Something",
            )
            result = await service._classify_via_compute(directive)

        assert result == DirectiveIntent.COMBINED

    @pytest.mark.asyncio
    async def test_returns_none_on_sse_send_error(self, service):
        """When SSE send_event raises, returns None gracefully."""
        mock_sse = MagicMock()
        mock_sse.get_idle_connections.return_value = ["compute-abc"]
        mock_sse.send_event = AsyncMock(side_effect=ConnectionError("SSE broken"))

        with patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ):
            directive = UnifiedDirective(
                directive_id="test-001",
                project_id="project-001",
                text="Something",
            )
            result = await service._classify_via_compute(directive)

        assert result is None


# ============================================================================
# Poll for Result
# ============================================================================


class TestPollForResult:
    """Tests for Redis-based result polling."""

    @pytest.mark.asyncio
    async def test_returns_none_without_redis(self, service):
        """Without Redis client, returns None immediately."""
        result = await service._poll_for_result("some_key", timeout=5)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_result_on_first_poll(self):
        """When result is available immediately, returns it."""
        mock_redis_inner = AsyncMock()
        mock_redis_inner.get = AsyncMock(return_value=b"new_work")
        mock_redis_inner.delete = AsyncMock()

        mock_redis = MagicMock()
        mock_redis._redis = mock_redis_inner

        svc = UnifiedDirectiveService(redis_client=mock_redis)
        result = await svc._poll_for_result("test_key", timeout=5)

        assert result == "new_work"
        mock_redis_inner.delete.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_returns_string_result(self):
        """When Redis returns a string (not bytes), handles it."""
        mock_redis_inner = AsyncMock()
        mock_redis_inner.get = AsyncMock(return_value="priority_shift")
        mock_redis_inner.delete = AsyncMock()

        mock_redis = MagicMock()
        mock_redis._redis = mock_redis_inner

        svc = UnifiedDirectiveService(redis_client=mock_redis)
        result = await svc._poll_for_result("test_key", timeout=5)

        assert result == "priority_shift"

    @pytest.mark.asyncio
    async def test_polls_until_result_appears(self):
        """Polls multiple times until a result is found."""
        mock_redis_inner = AsyncMock()
        # First two polls: no result. Third poll: result.
        mock_redis_inner.get = AsyncMock(
            side_effect=[None, None, b"combined"]
        )
        mock_redis_inner.delete = AsyncMock()

        mock_redis = MagicMock()
        mock_redis._redis = mock_redis_inner

        svc = UnifiedDirectiveService(redis_client=mock_redis)

        with patch("services.unified_directive_service.asyncio.sleep", new_callable=AsyncMock):
            result = await svc._poll_for_result("test_key", timeout=10)

        assert result == "combined"
        assert mock_redis_inner.get.call_count == 3

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        """Returns None when polling exceeds timeout."""
        mock_redis_inner = AsyncMock()
        mock_redis_inner.get = AsyncMock(return_value=None)

        mock_redis = MagicMock()
        mock_redis._redis = mock_redis_inner

        svc = UnifiedDirectiveService(redis_client=mock_redis)

        with patch(
            "services.unified_directive_service.asyncio.sleep",
            new_callable=AsyncMock,
        ), patch(
            "services.unified_directive_service.CLASSIFICATION_POLL_INTERVAL",
            2,
        ):
            result = await svc._poll_for_result("test_key", timeout=3)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_redis_get_error_gracefully(self):
        """Swallows Redis errors during polling and keeps trying."""
        mock_redis_inner = AsyncMock()
        mock_redis_inner.get = AsyncMock(
            side_effect=[ConnectionError("transient"), b"new_work"]
        )
        mock_redis_inner.delete = AsyncMock()

        mock_redis = MagicMock()
        mock_redis._redis = mock_redis_inner

        svc = UnifiedDirectiveService(redis_client=mock_redis)

        with patch("services.unified_directive_service.asyncio.sleep", new_callable=AsyncMock):
            result = await svc._poll_for_result("test_key", timeout=10)

        assert result == "new_work"


# ============================================================================
# Clarification Intent Path
# ============================================================================


class TestClarificationIntent:
    """Tests for clarification intent routing."""

    @pytest.mark.asyncio
    async def test_clarification_sets_needs_clarification(self, service):
        """When compute classifies as clarification, asks for clarification."""
        mock_sse = MagicMock()
        mock_sse.get_idle_connections.return_value = ["compute-abc"]
        mock_sse.send_event = AsyncMock()

        with patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ), patch.object(
            service,
            "_poll_for_result",
            new_callable=AsyncMock,
            return_value="clarification",
        ):
            directive = await service.submit(
                project_id="project-001",
                text="hmm something",
            )

        assert directive.intent == DirectiveIntent.CLARIFICATION
        assert directive.lifecycle_status == DirectiveLifecycleStatus.NEEDS_CLARIFICATION
        assert directive.outcome is not None
        assert directive.outcome.clarification_question is not None
        assert "clarify" in directive.outcome.clarification_question.lower()


# ============================================================================
# Classify Intent Fallback
# ============================================================================


class TestClassifyIntentFallback:
    """Tests for the full _classify_intent flow including fallback."""

    @pytest.mark.asyncio
    async def test_uses_compute_when_available(self, service):
        """When compute classification succeeds, uses its result."""
        with patch.object(
            service,
            "_classify_via_compute",
            new_callable=AsyncMock,
            return_value=DirectiveIntent.PRIORITY_SHIFT,
        ):
            directive = UnifiedDirective(
                directive_id="test-001",
                project_id="project-001",
                text="Create a login page",  # Deterministic would say NEW_WORK
            )
            result = await service._classify_intent(directive)

        # Compute overrides deterministic
        assert result == DirectiveIntent.PRIORITY_SHIFT

    @pytest.mark.asyncio
    async def test_falls_back_to_deterministic_on_none(self, service):
        """When compute returns None, falls back to keyword matching."""
        with patch.object(
            service,
            "_classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ):
            directive = UnifiedDirective(
                directive_id="test-001",
                project_id="project-001",
                text="Accelerate testing",
            )
            result = await service._classify_intent(directive)

        assert result == DirectiveIntent.PRIORITY_SHIFT

    @pytest.mark.asyncio
    async def test_falls_back_to_deterministic_on_error(self, service):
        """When compute raises, falls back to keyword matching."""
        with patch.object(
            service,
            "_classify_via_compute",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Compute exploded"),
        ):
            directive = UnifiedDirective(
                directive_id="test-001",
                project_id="project-001",
                text="Create a payment system",
            )
            result = await service._classify_intent(directive)

        assert result == DirectiveIntent.NEW_WORK


# ============================================================================
# Global Instance
# ============================================================================


# ============================================================================
# Delete Project Directives
# ============================================================================


class TestDeleteProjectDirectives:
    """Tests for delete_project_directives."""

    @pytest.mark.asyncio
    async def test_delete_clears_in_memory_directives(self, service):
        """Test that in-memory directives for the project are cleared."""
        # Seed directives in two projects
        service._directives["proj-1:d1"] = MagicMock()
        service._directives["proj-1:d2"] = MagicMock()
        service._directives["proj-2:d3"] = MagicMock()

        deleted = await service.delete_project_directives("proj-1")

        assert deleted == 2
        assert "proj-1:d1" not in service._directives
        assert "proj-1:d2" not in service._directives
        # Other project untouched
        assert "proj-2:d3" in service._directives

    @pytest.mark.asyncio
    async def test_delete_no_redis_only_clears_memory(self, service):
        """Test delete works when there is no Redis client."""
        service._directives["proj-1:d1"] = MagicMock()

        deleted = await service.delete_project_directives("proj-1")

        assert deleted == 1

    @pytest.mark.asyncio
    async def test_delete_scans_and_deletes_redis_keys(self):
        """Test that Redis item keys and history key are deleted."""
        mock_redis = MagicMock()
        mock_redis._prefix = "claudevn:"
        mock_redis._redis = MagicMock()

        # Simulate SCAN returning keys then ending
        mock_redis._redis.scan = AsyncMock(
            side_effect=[
                (0, [b"claudevn:unified_directive:item:proj-1:d1",
                     b"claudevn:unified_directive:item:proj-1:d2"]),
            ]
        )
        mock_redis._redis.delete = AsyncMock()

        svc = UnifiedDirectiveService(redis_client=mock_redis)
        deleted = await svc.delete_project_directives("proj-1")

        # Should have called delete for item keys
        assert mock_redis._redis.delete.call_count == 2  # items + history
        # Verify history key was deleted
        history_key = "claudevn:unified_directive:history:proj-1"
        delete_calls = [str(c) for c in mock_redis._redis.delete.call_args_list]
        assert any(history_key in c for c in delete_calls)

    @pytest.mark.asyncio
    async def test_delete_returns_zero_for_empty_project(self, service):
        """Test that deleting an empty project returns 0."""
        deleted = await service.delete_project_directives("nonexistent")
        assert deleted == 0


# ============================================================================
# Auto-Process Triggering (#694)
# ============================================================================


class TestAutoProcessTrigger:
    """Tests that auto-process is triggered after goal creation from directives.

    Verifies fix for #694: backend should automatically trigger decomposition
    when a directive creates a new goal, instead of relying on the frontend.
    """

    @pytest.mark.asyncio
    async def test_new_work_triggers_auto_process(self, service, mock_goal_service):
        """Creating a goal from new_work directive triggers auto-process."""
        with patch.object(
            service, "_schedule_auto_process"
        ) as mock_schedule, patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            await service.submit(
                project_id="project-001",
                text="Create a login page",
            )

        mock_schedule.assert_called_once()
        args, kwargs = mock_schedule.call_args
        assert args[0] == "goal_test_001"
        assert kwargs["project_id"] == "project-001"
        assert kwargs["directive_id"]  # non-empty string

    @pytest.mark.asyncio
    async def test_dedup_does_not_trigger_auto_process(self, service, mock_goal_service):
        """Reusing an existing goal does NOT trigger auto-process."""
        existing_goal = MagicMock()
        existing_goal.goal_id = "goal_existing_001"
        existing_goal.description = "Create a login page"
        mock_goal_service.list_goals = AsyncMock(
            return_value=MagicMock(items=[existing_goal])
        )

        with patch.object(
            service, "_schedule_auto_process"
        ) as mock_schedule, patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            await service.submit(
                project_id="project-001",
                text="Create a login page",
            )

        mock_schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_combined_triggers_auto_process_for_new_goal(
        self, service, mock_goal_service, mock_directive_service
    ):
        """Combined directive triggers auto-process when creating a new goal."""
        with patch.object(
            service, "_schedule_auto_process"
        ) as mock_schedule, patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ), patch(
            "services.directive_service.get_directive_service",
            return_value=mock_directive_service,
        ):
            await service.submit(
                project_id="project-001",
                text="Build payment flow and accelerate security testing",
            )

        mock_schedule.assert_called_once()
        args, kwargs = mock_schedule.call_args
        assert args[0] == "goal_test_001"
        assert kwargs["project_id"] == "project-001"
        assert kwargs["directive_id"]  # non-empty string

    @pytest.mark.asyncio
    async def test_combined_dedup_does_not_trigger_auto_process(
        self, service, mock_goal_service, mock_directive_service
    ):
        """Combined directive with existing goal does NOT trigger auto-process."""
        existing_goal = MagicMock()
        existing_goal.goal_id = "goal_existing_001"
        existing_goal.description = "Build payment flow and accelerate security testing"
        mock_goal_service.list_goals = AsyncMock(
            return_value=MagicMock(items=[existing_goal])
        )

        with patch.object(
            service, "_schedule_auto_process"
        ) as mock_schedule, patch(
            "services.unified_directive_service.UnifiedDirectiveService._classify_via_compute",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ), patch(
            "services.directive_service.get_directive_service",
            return_value=mock_directive_service,
        ):
            await service.submit(
                project_id="project-001",
                text="Build payment flow and accelerate security testing",
            )

        mock_schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_auto_process_calls_background_function(self, service):
        """_run_auto_process calls the API-layer auto-process function."""
        mock_set_status = AsyncMock()
        mock_background = AsyncMock()

        with patch(
            "api.slim_claude_code._set_processing_status", mock_set_status
        ), patch(
            "api.slim_claude_code._auto_process_background", mock_background
        ), patch(
            "api.slim_claude_code.ProcessingStage"
        ) as mock_stage:
            await service._run_auto_process("goal_abc")

        mock_set_status.assert_called_once_with("goal_abc", mock_stage.QUEUED)
        mock_background.assert_called_once_with("goal_abc", constraints=None)

    @pytest.mark.asyncio
    async def test_run_auto_process_backfills_directive(self, service):
        """_run_auto_process backfills directive outcome with issue IDs (#714)."""
        mock_set_status = AsyncMock()
        mock_background = AsyncMock()

        with patch(
            "api.slim_claude_code._set_processing_status", mock_set_status
        ), patch(
            "api.slim_claude_code._auto_process_background", mock_background
        ), patch(
            "api.slim_claude_code.ProcessingStage"
        ), patch.object(
            service, "_backfill_directive_issue_ids", new_callable=AsyncMock
        ) as mock_backfill:
            await service._run_auto_process(
                "goal_abc", directive_id="dir_001", project_id="proj_001"
            )

        mock_backfill.assert_called_once_with("dir_001", "proj_001", "goal_abc")

    @pytest.mark.asyncio
    async def test_run_auto_process_skips_backfill_without_directive(self, service):
        """_run_auto_process skips backfill when no directive info provided."""
        mock_set_status = AsyncMock()
        mock_background = AsyncMock()

        with patch(
            "api.slim_claude_code._set_processing_status", mock_set_status
        ), patch(
            "api.slim_claude_code._auto_process_background", mock_background
        ), patch(
            "api.slim_claude_code.ProcessingStage"
        ), patch.object(
            service, "_backfill_directive_issue_ids", new_callable=AsyncMock
        ) as mock_backfill:
            await service._run_auto_process("goal_abc")

        mock_backfill.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_auto_process_handles_errors(self, service):
        """_run_auto_process logs errors but does not raise."""
        with patch(
            "api.slim_claude_code._set_processing_status",
            AsyncMock(side_effect=RuntimeError("Redis down")),
        ):
            # Should not raise
            await service._run_auto_process("goal_abc")


class TestBackfillDirectiveIssueIds:
    """Tests for _backfill_directive_issue_ids — updating directive outcome
    with issue IDs created during goal decomposition (#714).
    """

    @pytest.mark.asyncio
    async def test_backfill_updates_outcome(self, service):
        """Issue IDs from goal decomposition are written to directive outcome."""
        # Set up a directive with an outcome that has no issue IDs
        directive = UnifiedDirective(
            directive_id="dir_001",
            project_id="proj_001",
            text="Build something",
            intent=DirectiveIntent.NEW_WORK,
            lifecycle_status=DirectiveLifecycleStatus.COMPLETE,
            outcome=DirectiveOutcome(goal_id_created="goal_001"),
        )
        service._store(directive)

        # Mock goal service returning a goal with issue IDs
        mock_goal = MagicMock()
        mock_goal.issue_ids = ["issue-1", "issue-2", "issue-3"]
        mock_goal_svc = MagicMock()
        mock_goal_svc.get_goal = AsyncMock(return_value=mock_goal)

        with patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_svc,
        ):
            await service._backfill_directive_issue_ids(
                "dir_001", "proj_001", "goal_001"
            )

        assert directive.outcome.issue_ids_created == ["issue-1", "issue-2", "issue-3"]

    @pytest.mark.asyncio
    async def test_backfill_skips_when_goal_has_no_issues(self, service):
        """Backfill is a no-op when goal has no issue IDs yet."""
        directive = UnifiedDirective(
            directive_id="dir_002",
            project_id="proj_001",
            text="Build something",
            intent=DirectiveIntent.NEW_WORK,
            lifecycle_status=DirectiveLifecycleStatus.COMPLETE,
            outcome=DirectiveOutcome(goal_id_created="goal_002"),
        )
        service._store(directive)

        mock_goal = MagicMock()
        mock_goal.issue_ids = []
        mock_goal_svc = MagicMock()
        mock_goal_svc.get_goal = AsyncMock(return_value=mock_goal)

        with patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_svc,
        ):
            await service._backfill_directive_issue_ids(
                "dir_002", "proj_001", "goal_002"
            )

        assert directive.outcome.issue_ids_created == []

    @pytest.mark.asyncio
    async def test_backfill_skips_when_goal_not_found(self, service):
        """Backfill is a no-op when goal cannot be found."""
        directive = UnifiedDirective(
            directive_id="dir_003",
            project_id="proj_001",
            text="Build something",
            intent=DirectiveIntent.NEW_WORK,
            lifecycle_status=DirectiveLifecycleStatus.COMPLETE,
            outcome=DirectiveOutcome(goal_id_created="goal_missing"),
        )
        service._store(directive)

        mock_goal_svc = MagicMock()
        mock_goal_svc.get_goal = AsyncMock(return_value=None)

        with patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_svc,
        ):
            await service._backfill_directive_issue_ids(
                "dir_003", "proj_001", "goal_missing"
            )

        assert directive.outcome.issue_ids_created == []

    @pytest.mark.asyncio
    async def test_backfill_skips_when_directive_not_found(self, service):
        """Backfill is a no-op when directive cannot be found in memory."""
        mock_goal = MagicMock()
        mock_goal.issue_ids = ["issue-1"]
        mock_goal_svc = MagicMock()
        mock_goal_svc.get_goal = AsyncMock(return_value=mock_goal)

        with patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_svc,
        ):
            # Should not raise even though directive doesn't exist
            await service._backfill_directive_issue_ids(
                "dir_nonexistent", "proj_001", "goal_001"
            )

    @pytest.mark.asyncio
    async def test_backfill_handles_exceptions_gracefully(self, service):
        """Backfill logs errors but does not raise."""
        with patch(
            "services.goal_service.get_goal_service",
            side_effect=RuntimeError("Service unavailable"),
        ):
            # Should not raise
            await service._backfill_directive_issue_ids(
                "dir_001", "proj_001", "goal_001"
            )


class TestGlobalInstance:
    """Tests for global service singleton."""

    def test_get_before_set_raises(self):
        set_unified_directive_service(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_unified_directive_service()

    def test_set_and_get(self):
        svc = UnifiedDirectiveService()
        set_unified_directive_service(svc)
        assert get_unified_directive_service() is svc
        set_unified_directive_service(None)


# ============================================================================
# Goal Title Generation (#713)
# ============================================================================


class TestGenerateGoalTitle:
    """Tests for _generate_goal_title — concise titles from directive text."""

    def test_short_text_unchanged(self):
        assert _generate_goal_title("Create a login page") == "Create a login page"

    def test_first_sentence_extracted(self):
        text = (
            "Build a REST API for todo items. It should support CRUD operations "
            "with title, description, and done status."
        )
        assert _generate_goal_title(text) == "Build a REST API for todo items."

    def test_long_single_sentence_truncated_at_word_boundary(self):
        text = (
            "Build a simple REST API for a todo list application using Python "
            "and FastAPI with support for CRUD operations for todo items with "
            "title description and done status including input validation"
        )
        result = _generate_goal_title(text)
        assert len(result) <= 80
        assert not result.endswith(" ")
        # Should not cut in the middle of a word
        assert result == text[:result.__len__()]  # prefix of original

    def test_strips_whitespace(self):
        assert _generate_goal_title("  Hello world  ") == "Hello world"

    def test_first_sentence_too_long_falls_through(self):
        """If the first sentence exceeds max length, fall back to word truncation."""
        text = (
            "Build a comprehensive user authentication system with OAuth2 support "
            "and multi-factor authentication and password reset functionality. "
            "Then deploy it."
        )
        result = _generate_goal_title(text)
        assert len(result) <= 80
        # Should not include the period from the first sentence
        assert "." not in result

    def test_exact_boundary(self):
        text = "x" * 80
        assert _generate_goal_title(text) == text

    def test_one_over_boundary_no_spaces(self):
        text = "x" * 81
        # No spaces to break on, so just truncate at max length
        assert _generate_goal_title(text) == "x" * 80
