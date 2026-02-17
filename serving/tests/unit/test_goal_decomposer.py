"""Tests for GoalDecomposerService - Delegated goal decomposition via compute instances."""

import json
import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

from models.goal_decomposer import (
    DecomposedIssue,
    EstimatedComplexity,
    GoalDecomposerConfig,
    GoalDecompositionRequest,
    GoalDecompositionResult,
)
from models.issue import (
    Issue,
    IssueArea,
    IssuePriority,
    IssueStatus,
    IssueType,
)
from services.goal_decomposer import (
    GoalDecomposerService,
    NoComputeAvailableError,
    DecompositionTimeoutError,
    get_goal_decomposer_service,
    set_goal_decomposer_service,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.exists = AsyncMock(return_value=False)
    return redis


@pytest.fixture
def sample_decomposition_result():
    """Sample decomposition result stored in Redis."""
    return GoalDecompositionResult(
        goal_id="goal-001",
        decomposition_id="decomp-abc123456",
        issues=[
            DecomposedIssue(
                temp_id="issue-1",
                title="Set up database schema",
                description="Create the initial database schema for user management.",
                issue_type="feature",
                priority="P1",
                area="database",
                required_skills=["sql", "postgres"],
                estimated_complexity=EstimatedComplexity.M,
                blocked_by=[],
                acceptance_criteria=[
                    "Users table created with required columns",
                    "Migrations are reversible"
                ]
            ),
            DecomposedIssue(
                temp_id="issue-2",
                title="Implement user API endpoints",
                description="Create REST API endpoints for user CRUD operations.",
                issue_type="feature",
                priority="P1",
                area="api",
                required_skills=["python", "fastapi"],
                estimated_complexity=EstimatedComplexity.L,
                blocked_by=["issue-1"],
                acceptance_criteria=[
                    "GET /users returns list of users",
                    "POST /users creates new user",
                ]
            ),
        ],
        dependency_graph={"issue-2": ["issue-1"]},
        execution_phases=[["issue-1"], ["issue-2"]],
        confidence=0.85,
        reasoning="Decomposed into 2 issues following data-first pattern."
    )


@pytest.fixture
def sample_existing_issues():
    """Sample existing issues for context."""
    return [
        Issue(
            id="issue-100",
            title="Existing feature",
            description="An existing feature in the backlog",
            type=IssueType.FEATURE,
            area=IssueArea.API,
            priority=IssuePriority.P2,
            status=IssueStatus.READY,
        ),
        Issue(
            id="issue-101",
            title="Existing bug",
            description="A bug that needs fixing",
            type=IssueType.BUG,
            area=IssueArea.FRONTEND,
            priority=IssuePriority.P1,
            status=IssueStatus.IN_PROGRESS,
        ),
    ]


@pytest.fixture
def goal_decomposer_service():
    """Create GoalDecomposerService for testing."""
    config = GoalDecomposerConfig(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        temperature=0.3,
    )
    service = GoalDecomposerService(
        config=config,
        timeout=10,  # Short timeout for tests
    )
    service._initialized = True
    return service


# ============================================================================
# Model Tests - DecomposedIssue
# ============================================================================


class TestDecomposedIssueModel:
    """Test DecomposedIssue model."""

    def test_create_decomposed_issue_with_defaults(self):
        """Test creating DecomposedIssue with minimal fields."""
        issue = DecomposedIssue(
            temp_id="issue-1",
            title="Test Issue",
            description="Test description",
        )

        assert issue.temp_id == "issue-1"
        assert issue.title == "Test Issue"
        assert issue.description == "Test description"
        assert issue.issue_type == "feature"
        assert issue.priority == "P2"
        assert issue.area == "api"
        assert issue.required_skills == []
        assert issue.estimated_complexity == EstimatedComplexity.M
        assert issue.blocked_by == []
        assert issue.acceptance_criteria == []

    def test_create_decomposed_issue_with_all_fields(self):
        """Test creating DecomposedIssue with all fields."""
        issue = DecomposedIssue(
            temp_id="issue-1",
            title="Test Issue",
            description="Test description",
            issue_type="bug",
            priority="P0",
            area="frontend",
            required_skills=["react", "typescript"],
            estimated_complexity=EstimatedComplexity.XL,
            blocked_by=["issue-0"],
            acceptance_criteria=["Criterion 1", "Criterion 2"],
        )

        assert issue.issue_type == "bug"
        assert issue.priority == "P0"
        assert issue.area == "frontend"
        assert issue.required_skills == ["react", "typescript"]
        assert issue.estimated_complexity == EstimatedComplexity.XL
        assert issue.blocked_by == ["issue-0"]
        assert issue.acceptance_criteria == ["Criterion 1", "Criterion 2"]

    def test_estimated_complexity_enum_values(self):
        """Test all EstimatedComplexity enum values."""
        assert EstimatedComplexity.XS.value == "xs"
        assert EstimatedComplexity.S.value == "s"
        assert EstimatedComplexity.M.value == "m"
        assert EstimatedComplexity.L.value == "l"
        assert EstimatedComplexity.XL.value == "xl"


# ============================================================================
# Model Tests - GoalDecompositionResult
# ============================================================================


class TestGoalDecompositionResultModel:
    """Test GoalDecompositionResult model."""

    def test_create_result_with_defaults(self):
        """Test creating result with minimal fields."""
        result = GoalDecompositionResult(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
        )

        assert result.goal_id == "goal-001"
        assert result.decomposition_id == "decomp-abc123"
        assert result.issues == []
        assert result.dependency_graph == {}
        assert result.execution_phases == []
        assert result.confidence == 0.0
        assert result.reasoning == ""
        assert result.created_at is not None

    def test_create_result_with_issues(self):
        """Test creating result with issues."""
        issues = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Issue 1",
                description="Desc 1",
            ),
            DecomposedIssue(
                temp_id="issue-2",
                title="Issue 2",
                description="Desc 2",
                blocked_by=["issue-1"],
            ),
        ]

        result = GoalDecompositionResult(
            goal_id="goal-001",
            decomposition_id="decomp-abc123",
            issues=issues,
            dependency_graph={"issue-2": ["issue-1"]},
            execution_phases=[["issue-1"], ["issue-2"]],
            confidence=0.9,
            reasoning="Test reasoning",
        )

        assert len(result.issues) == 2
        assert result.dependency_graph == {"issue-2": ["issue-1"]}
        assert result.execution_phases == [["issue-1"], ["issue-2"]]
        assert result.confidence == 0.9
        assert result.reasoning == "Test reasoning"


# ============================================================================
# Model Tests - GoalDecomposerConfig
# ============================================================================


class TestGoalDecomposerConfigModel:
    """Test GoalDecomposerConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = GoalDecomposerConfig()

        assert config.model == "claude-sonnet-4-20250514"
        assert config.max_tokens == 4096
        assert config.temperature == 0.3
        assert config.max_issues_per_goal == 50
        assert config.default_max_issues == 20

    def test_custom_config(self):
        """Test custom configuration values."""
        config = GoalDecomposerConfig(
            model="claude-3-opus-20240229",
            max_tokens=8192,
            temperature=0.5,
            max_issues_per_goal=100,
            default_max_issues=30,
        )

        assert config.model == "claude-3-opus-20240229"
        assert config.max_tokens == 8192
        assert config.temperature == 0.5
        assert config.max_issues_per_goal == 100
        assert config.default_max_issues == 30


# ============================================================================
# Service Tests - Initialization
# ============================================================================


class TestGoalDecomposerServiceInit:
    """Test GoalDecomposerService initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        service = GoalDecomposerService()

        assert service._config is not None
        assert service._timeout == 300  # Default timeout
        assert service._initialized is False

    def test_init_with_custom_config(self):
        """Test initialization with custom config."""
        config = GoalDecomposerConfig(temperature=0.5)
        service = GoalDecomposerService(
            config=config,
            timeout=120,
        )

        assert service._config.temperature == 0.5
        assert service._timeout == 120
        assert service._initialized is False

    @pytest.mark.asyncio
    async def test_initialize_sets_initialized_flag(self):
        """Test that initialize sets the initialized flag."""
        service = GoalDecomposerService()

        await service.initialize()

        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self):
        """Test that initialize can be called multiple times safely."""
        service = GoalDecomposerService()

        await service.initialize()
        await service.initialize()  # Should not fail

        assert service._initialized is True


# ============================================================================
# Service Tests - Delegated Decomposition
# ============================================================================


class TestGoalDecomposerServiceDecomposition:
    """Test goal decomposition via compute delegation (event-driven, no polling)."""

    @pytest.mark.asyncio
    async def test_decompose_goal_spawns_compute(
        self,
        goal_decomposer_service,
        mock_redis,
        sample_decomposition_result,
    ):
        """Test that decompose_goal calls _spawn_decomposition_compute with goal_id."""
        async def mock_spawn(decomposition_id, task_context, goal_id=""):
            from services.completion_events import create_event, signal as signal_event
            create_event(decomposition_id)
            mock_redis.get = AsyncMock(return_value=sample_decomposition_result.model_dump_json())
            signal_event(decomposition_id)

        with patch.object(
            goal_decomposer_service, "_spawn_decomposition_compute", side_effect=mock_spawn
        ) as mock_spawn_method, \
        patch("git.redis_client.get_redis", AsyncMock(return_value=mock_redis)):
            await goal_decomposer_service.decompose_goal(
                goal_id="goal-001",
                goal_text="Build a user management system",
            )

        mock_spawn_method.assert_awaited_once()
        call_kwargs = mock_spawn_method.call_args.kwargs
        assert call_kwargs["goal_id"] == "goal-001"
        assert call_kwargs["decomposition_id"].startswith("decomp-")

    @pytest.mark.asyncio
    async def test_decompose_goal_returns_result(
        self,
        goal_decomposer_service,
        mock_redis,
        sample_decomposition_result,
    ):
        """Test decompose_goal returns a GoalDecompositionResult via asyncio.Event."""
        async def mock_spawn(decomposition_id, task_context, goal_id=""):
            from services.completion_events import create_event, signal as signal_event
            create_event(decomposition_id)
            mock_redis.get = AsyncMock(return_value=sample_decomposition_result.model_dump_json())
            signal_event(decomposition_id)

        with patch.object(
            goal_decomposer_service, "_spawn_decomposition_compute", side_effect=mock_spawn
        ), \
        patch("git.redis_client.get_redis", AsyncMock(return_value=mock_redis)):
            result = await goal_decomposer_service.decompose_goal(
                goal_id="goal-001",
                goal_text="Build a user management system",
            )

        assert isinstance(result, GoalDecompositionResult)
        assert len(result.issues) == 2
        assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_decompose_goal_handles_spawn_failure(
        self,
        goal_decomposer_service,
    ):
        """Test handling of spawn failure."""
        with patch.object(
            goal_decomposer_service, "_spawn_decomposition_compute", new_callable=AsyncMock
        ) as mock_spawn:
            mock_spawn.side_effect = NoComputeAvailableError("No compute available")

            with pytest.raises(NoComputeAvailableError) as exc_info:
                await goal_decomposer_service.decompose_goal(
                    goal_id="goal-001",
                    goal_text="Build a feature",
                )

        assert "No compute available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_decompose_goal_handles_timeout(self):
        """Test handling of decomposition timeout via asyncio.Event (no polling)."""
        service = GoalDecomposerService(timeout=0.1)
        service._initialized = True

        async def mock_spawn_no_signal(decomposition_id, task_context, goal_id=""):
            from services.completion_events import create_event
            create_event(decomposition_id)
            # Never signals — timeout fires after 0.1s

        with patch.object(
            service, "_spawn_decomposition_compute", side_effect=mock_spawn_no_signal
        ):
            with pytest.raises(DecompositionTimeoutError) as exc_info:
                await service.decompose_goal(
                    goal_id="goal-001",
                    goal_text="Build a feature",
                )

        assert "timed out" in str(exc_info.value)


# ============================================================================
# Service Tests - Task Context Building
# ============================================================================


class TestTaskContextBuilding:
    """Test task context building for compute instances."""

    def test_build_task_context_includes_goal(self, goal_decomposer_service):
        """Test that task context includes goal information."""
        context = goal_decomposer_service._build_task_context(
            goal_id="goal-001",
            goal_text="Build a user management system",
            decomposition_id="decomp-abc123",
        )

        assert "goal-001" in context
        assert "decomp-abc123" in context
        assert "Build a user management system" in context
        assert "claudevn_submit_decomposition" in context

    def test_build_task_context_includes_project_context(self, goal_decomposer_service):
        """Test that task context includes project context."""
        context = goal_decomposer_service._build_task_context(
            goal_id="goal-001",
            goal_text="Build a feature",
            decomposition_id="decomp-abc123",
            project_context={
                "tech_stack": "Python, FastAPI, PostgreSQL",
                "conventions": "Use Pydantic v2 models",
            },
        )

        assert "Python, FastAPI, PostgreSQL" in context
        assert "Pydantic v2" in context

    def test_build_task_context_includes_existing_issues(
        self,
        goal_decomposer_service,
        sample_existing_issues,
    ):
        """Test that task context includes existing issues."""
        context = goal_decomposer_service._build_task_context(
            goal_id="goal-001",
            goal_text="Build a feature",
            decomposition_id="decomp-abc123",
            existing_issues=sample_existing_issues,
        )

        assert "Existing feature" in context
        assert "issue-100" in context

    def test_build_task_context_includes_constraints(self, goal_decomposer_service):
        """Test that task context includes constraints."""
        context = goal_decomposer_service._build_task_context(
            goal_id="goal-001",
            goal_text="Build a feature",
            decomposition_id="decomp-abc123",
            constraints={
                "max_issues": 10,
                "focus_areas": ["api", "database"],
            },
        )

        assert "Maximum issues: 10" in context
        assert "Focus areas: api, database" in context


# ============================================================================
# Service Tests - Issue Model Mapping
# ============================================================================


class TestIssueModelMapping:
    """Test mapping decomposed issues to Issue models."""

    def test_map_to_issue_models(self, goal_decomposer_service):
        """Test mapping decomposed issues to IssueCreateRequest format."""
        decomposed = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Test Issue",
                description="Test description",
                issue_type="feature",
                priority="P1",
                area="database",
                required_skills=["sql"],
                blocked_by=[],
                acceptance_criteria=["Criterion 1"],
            ),
        ]

        result = goal_decomposer_service.map_to_issue_models(
            decomposed,
            goal_id="goal-001",
        )

        assert len(result) == 1
        issue = result[0]
        assert issue["temp_id"] == "issue-1"
        assert issue["title"] == "Test Issue"
        assert issue["type"] == IssueType.FEATURE
        assert issue["priority"] == IssuePriority.P1
        assert issue["area"] == IssueArea.DATABASE
        assert issue["goal_id"] == "goal-001"
        assert issue["required_skills"] == ["sql"]
        assert issue["acceptance_criteria"] == ["Criterion 1"]

    def test_map_all_issue_types(self, goal_decomposer_service):
        """Test mapping all issue types."""
        type_mappings = [
            ("feature", IssueType.FEATURE),
            ("bug", IssueType.BUG),
            ("refactor", IssueType.REFACTOR),
            ("test", IssueType.TEST),
            ("docs", IssueType.DOCS),
        ]

        for type_str, expected_type in type_mappings:
            decomposed = [
                DecomposedIssue(
                    temp_id="issue-1",
                    title="Test",
                    description="Test",
                    issue_type=type_str,
                ),
            ]
            result = goal_decomposer_service.map_to_issue_models(
                decomposed,
                goal_id="goal-001",
            )
            assert result[0]["type"] == expected_type

    def test_map_all_areas(self, goal_decomposer_service):
        """Test mapping all areas."""
        area_mappings = [
            ("api", IssueArea.API),
            ("database", IssueArea.DATABASE),
            ("frontend", IssueArea.FRONTEND),
            ("infra", IssueArea.INFRA),
        ]

        for area_str, expected_area in area_mappings:
            decomposed = [
                DecomposedIssue(
                    temp_id="issue-1",
                    title="Test",
                    description="Test",
                    area=area_str,
                ),
            ]
            result = goal_decomposer_service.map_to_issue_models(
                decomposed,
                goal_id="goal-001",
            )
            assert result[0]["area"] == expected_area

    def test_map_all_priorities(self, goal_decomposer_service):
        """Test mapping all priorities."""
        priority_mappings = [
            ("P0", IssuePriority.P0),
            ("P1", IssuePriority.P1),
            ("P2", IssuePriority.P2),
            ("P3", IssuePriority.P3),
        ]

        for priority_str, expected_priority in priority_mappings:
            decomposed = [
                DecomposedIssue(
                    temp_id="issue-1",
                    title="Test",
                    description="Test",
                    priority=priority_str,
                ),
            ]
            result = goal_decomposer_service.map_to_issue_models(
                decomposed,
                goal_id="goal-001",
            )
            assert result[0]["priority"] == expected_priority


# ============================================================================
# Service Tests - Global Instance
# ============================================================================


class TestGlobalInstance:
    """Test global service instance management."""

    def test_get_service_returns_instance(self):
        """Test get_goal_decomposer_service returns an instance."""
        # Reset global state
        set_goal_decomposer_service(None)

        service = get_goal_decomposer_service()

        assert isinstance(service, GoalDecomposerService)

    def test_set_service_replaces_instance(self):
        """Test set_goal_decomposer_service replaces the global instance."""
        custom_service = GoalDecomposerService(timeout=999)

        set_goal_decomposer_service(custom_service)

        assert get_goal_decomposer_service() is custom_service

    def test_get_service_returns_same_instance(self):
        """Test get_goal_decomposer_service returns the same instance."""
        # Reset global state
        set_goal_decomposer_service(None)

        service1 = get_goal_decomposer_service()
        service2 = get_goal_decomposer_service()

        assert service1 is service2


# ============================================================================
# Tests for MCP Decomposition Tool
# ============================================================================


class TestDecompositionMCPTool:
    """Test the claudevn_submit_decomposition MCP tool."""

    @pytest.mark.asyncio
    async def test_submit_decomposition_stores_result(self, mock_redis):
        """Test that submit_decomposition stores result in Redis."""
        from mcp.tools.decomposition import submit_decomposition, SubmitDecompositionInput

        input_data = SubmitDecompositionInput(
            decomposition_id="decomp-test123",
            goal_id="goal-001",
            issues=[
                {
                    "temp_id": "issue-1",
                    "title": "Test Issue",
                    "description": "Test description",
                    "issue_type": "feature",
                    "priority": "P1",
                    "area": "api",
                    "required_skills": ["python"],
                    "estimated_complexity": "m",
                    "blocked_by": [],
                    "acceptance_criteria": ["Works"],
                }
            ],
            confidence=0.85,
            reasoning="Test decomposition",
        )

        with patch("git.redis_client.get_redis", return_value=mock_redis):
            response, error = await submit_decomposition(input_data)

        assert error is None
        assert response is not None
        assert response.acknowledged is True
        assert response.decomposition_id == "decomp-test123"
        assert response.issues_count == 1
        assert response.status == "stored"

        # Verify Redis was called
        assert mock_redis.setex.call_count == 2  # Result + completion signal

    @pytest.mark.asyncio
    async def test_submit_decomposition_handles_errors(self, mock_redis):
        """Test that submit_decomposition handles errors gracefully."""
        from mcp.tools.decomposition import submit_decomposition, SubmitDecompositionInput

        mock_redis.setex.side_effect = Exception("Redis error")

        input_data = SubmitDecompositionInput(
            decomposition_id="decomp-test123",
            goal_id="goal-001",
            issues=[
                {
                    "temp_id": "issue-1",
                    "title": "Test Issue",
                }
            ],
        )

        with patch("git.redis_client.get_redis", return_value=mock_redis):
            response, error = await submit_decomposition(input_data)

        assert response is None
        assert error is not None
        assert error.code == "INTERNAL_ERROR"

    @pytest.mark.asyncio
    async def test_submit_decomposition_updates_goal_service(self, mock_redis):
        """Test that submit_decomposition updates goal with decomposition_id (#431)."""
        from mcp.tools.decomposition import submit_decomposition, SubmitDecompositionInput

        mock_goal_service = MagicMock()
        mock_goal_service.update_goal_decomposition_id = AsyncMock()

        input_data = SubmitDecompositionInput(
            decomposition_id="decomp-test456",
            goal_id="goal-002",
            issues=[
                {
                    "temp_id": "issue-1",
                    "title": "Test Issue",
                    "description": "Test",
                    "issue_type": "feature",
                    "priority": "P2",
                    "area": "api",
                    "estimated_complexity": "m",
                }
            ],
            confidence=0.9,
            reasoning="Test",
        )

        with patch("git.redis_client.get_redis", return_value=mock_redis), \
             patch("services.goal_service.get_goal_service", return_value=mock_goal_service):
            response, error = await submit_decomposition(input_data)

        assert error is None
        assert response is not None
        assert response.status == "stored"

        # Verify goal service was called with correct args
        mock_goal_service.update_goal_decomposition_id.assert_awaited_once_with(
            "goal-002", "decomp-test456"
        )


# ============================================================================
# Tests for goal_id propagation in SSE context (#430)
# ============================================================================


class TestGoalIdPropagation:
    """Test that goal_id is propagated through the decomposition call chain (#430)."""

    @pytest.mark.asyncio
    async def test_spawn_decomposition_compute_enqueues_with_goal_id(
        self, goal_decomposer_service
    ):
        """_spawn_decomposition_compute must pass goal_id to the WorkDispatcher task."""
        mock_dispatcher = MagicMock()
        mock_dispatcher.enqueue_decomposition = MagicMock()

        mock_marketplace = MagicMock()
        mock_marketplace.get_skill = AsyncMock(return_value={"instructions": "test"})

        with patch(
            "services.work_dispatcher.get_work_dispatcher",
            return_value=mock_dispatcher,
        ), patch(
            "services.marketplace_client.get_marketplace_client",
            return_value=mock_marketplace,
        ):
            await goal_decomposer_service._spawn_decomposition_compute(
                decomposition_id="decomp-abc123",
                task_context="test context",
                goal_id="goal-test-002",
            )

        mock_dispatcher.enqueue_decomposition.assert_called_once()
        task = mock_dispatcher.enqueue_decomposition.call_args[0][0]
        assert task.goal_id == "goal-test-002"
        assert task.decomp_id == "decomp-abc123"


# ============================================================================
# Tests for premature idle reset fix (#861)
# ============================================================================


class TestGoalDecomposerIdleReset:
    """Verify decomposition flow does not directly reset SSE idle state (#861).

    The compute.py event handler (claude_code_completed / claude_code_failed) is
    the single authoritative source for resetting connection.status to "idle".
    GoalDecomposerService must not touch SSE state — that responsibility moved to
    the WorkDispatcher and compute.py when _cleanup_compute was removed.
    """

    @pytest.mark.asyncio
    async def test_spawn_does_not_touch_sse_manager(self, goal_decomposer_service):
        """_spawn_decomposition_compute must not interact with SSE manager (#861)."""
        mock_dispatcher = MagicMock()
        mock_dispatcher.enqueue_decomposition = MagicMock()

        mock_marketplace = MagicMock()
        mock_marketplace.get_skill = AsyncMock(return_value={"instructions": "test"})

        mock_sse_manager = MagicMock()

        with patch(
            "services.work_dispatcher.get_work_dispatcher",
            return_value=mock_dispatcher,
        ), patch(
            "services.marketplace_client.get_marketplace_client",
            return_value=mock_marketplace,
        ), patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse_manager,
        ):
            await goal_decomposer_service._spawn_decomposition_compute(
                decomposition_id="decomp-test",
                task_context="ctx",
                goal_id="goal-test",
            )

        # SSE manager must not be touched — WorkDispatcher owns dispatch
        mock_sse_manager.find_matching_connection.assert_not_called()
        mock_sse_manager.send_work_assigned.assert_not_called()
        mock_sse_manager.get_connection.assert_not_called()
