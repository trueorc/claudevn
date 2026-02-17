"""Tests for re-invocable (supplemental) goal decomposition.

Tests cover:
- DecompositionPass and DecompositionTrigger models
- GoalService.record_decomposition_pass
- GoalDecomposerService supplemental context in task prompts
- Supplemental decompose API endpoint
- Decomposition passes API endpoint
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.slim_claude_code import router as slim_router
from api.work_map import goals_router
from models.goal_decomposer import (
    DecomposedIssue,
    EstimatedComplexity,
    GoalDecompositionResult,
)
from models.work_map import (
    DecompositionPass,
    DecompositionTrigger,
    Goal,
    GoalStatus,
    Issue,
    IssueStatus,
    SupplementalDecomposeRequest,
)
from services.goal_decomposer import GoalDecomposerService
from services.goal_service import GoalService


# =============================================================================
# Fixtures
# =============================================================================


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
def goal_service():
    """Create GoalService without Redis."""
    return GoalService(redis_client=None)


@pytest.fixture
def goal_service_with_redis(mock_redis):
    """Create GoalService with mocked Redis."""
    return GoalService(redis_client=mock_redis)


@pytest.fixture
def sample_goal():
    """Create a sample goal with existing decomposition."""
    return Goal(
        goal_id="goal-test-001",
        title="Build user management",
        description="Build a complete user management system",
        project_id="project-test",
        priority="P1",
        status=GoalStatus.IN_PROGRESS,
        decomposition_id="decomp-initial",
        issue_ids=["issue-1", "issue-2"],
        decomposition_passes=[
            DecompositionPass(
                decomposition_id="decomp-initial",
                pass_number=1,
                trigger=DecompositionTrigger.INITIAL,
                issue_ids_created=["issue-1", "issue-2"],
            )
        ],
    )


@pytest.fixture
def sample_issues():
    """Create sample existing issues for a goal."""
    return [
        Issue(
            issue_id="issue-1",
            title="Set up database schema",
            description="Create the initial database schema",
            goal_id="goal-test-001",
            status=IssueStatus.DONE,
            project_id="project-test",
        ),
        Issue(
            issue_id="issue-2",
            title="Implement API endpoints",
            description="Create REST API endpoints",
            goal_id="goal-test-001",
            status=IssueStatus.IN_PROGRESS,
            project_id="project-test",
        ),
    ]


@pytest.fixture
def sample_decomposition_result():
    """Create a sample supplemental decomposition result."""
    return GoalDecompositionResult(
        goal_id="goal-test-001",
        decomposition_id="decomp-supplemental-001",
        issues=[
            DecomposedIssue(
                temp_id="new-issue-1",
                title="Add input validation",
                description="Add validation for all user inputs",
                issue_type="feature",
                priority="P2",
                area="api",
                required_skills=["python"],
                estimated_complexity=EstimatedComplexity.S,
                blocked_by=[],
                acceptance_criteria=["All inputs validated"],
            ),
        ],
        dependency_graph={},
        execution_phases=[["new-issue-1"]],
        confidence=0.8,
        reasoning="Identified missing input validation from worker feedback.",
    )


@pytest.fixture
def decomposer_service():
    """Create GoalDecomposerService for testing."""
    return GoalDecomposerService()


# =============================================================================
# Model Tests
# =============================================================================


class TestDecompositionPassModel:
    """Test DecompositionPass model."""

    def test_create_initial_pass(self):
        """Test creating an initial decomposition pass."""
        dp = DecompositionPass(
            decomposition_id="decomp-001",
            pass_number=1,
            trigger=DecompositionTrigger.INITIAL,
            issue_ids_created=["issue-1", "issue-2"],
        )
        assert dp.decomposition_id == "decomp-001"
        assert dp.pass_number == 1
        assert dp.trigger == DecompositionTrigger.INITIAL
        assert dp.issue_ids_created == ["issue-1", "issue-2"]
        assert dp.triggered_by is None
        assert dp.trigger_context is None

    def test_create_supplemental_pass(self):
        """Test creating a supplemental decomposition pass."""
        dp = DecompositionPass(
            decomposition_id="decomp-002",
            pass_number=2,
            trigger=DecompositionTrigger.WORKER_FEEDBACK,
            triggered_by="compute-worker-42",
            trigger_context="Missing error handling for edge cases",
            issue_ids_created=["issue-3"],
        )
        assert dp.pass_number == 2
        assert dp.trigger == DecompositionTrigger.WORKER_FEEDBACK
        assert dp.triggered_by == "compute-worker-42"
        assert dp.trigger_context == "Missing error handling for edge cases"

    def test_create_planner_gap_pass(self):
        """Test creating a planner-triggered decomposition pass."""
        dp = DecompositionPass(
            decomposition_id="decomp-003",
            pass_number=3,
            trigger=DecompositionTrigger.PLANNER_GAP,
            trigger_context="No test coverage issues found",
            issue_ids_created=["issue-4", "issue-5"],
        )
        assert dp.trigger == DecompositionTrigger.PLANNER_GAP

    def test_serialization_roundtrip(self):
        """Test JSON serialization and deserialization."""
        dp = DecompositionPass(
            decomposition_id="decomp-001",
            pass_number=1,
            trigger=DecompositionTrigger.MANUAL,
            triggered_by="user-123",
            trigger_context="Need more work on auth",
            issue_ids_created=["issue-1"],
        )
        data = dp.model_dump(mode="json")
        restored = DecompositionPass(**data)
        assert restored.decomposition_id == dp.decomposition_id
        assert restored.trigger == dp.trigger
        assert restored.triggered_by == dp.triggered_by


class TestDecompositionTriggerEnum:
    """Test DecompositionTrigger enum values."""

    def test_all_triggers(self):
        """Test all trigger types exist."""
        assert DecompositionTrigger.INITIAL == "initial"
        assert DecompositionTrigger.PLANNER_GAP == "planner_gap"
        assert DecompositionTrigger.WORKER_FEEDBACK == "worker_feedback"
        assert DecompositionTrigger.MANUAL == "manual"


class TestSupplementalDecomposeRequest:
    """Test SupplementalDecomposeRequest model."""

    def test_default_values(self):
        """Test default request values."""
        req = SupplementalDecomposeRequest()
        assert req.trigger == DecompositionTrigger.MANUAL
        assert req.triggered_by is None
        assert req.gap_description is None
        assert req.context is None
        assert req.constraints is None

    def test_full_request(self):
        """Test request with all fields populated."""
        req = SupplementalDecomposeRequest(
            trigger=DecompositionTrigger.WORKER_FEEDBACK,
            triggered_by="compute-42",
            gap_description="No error handling for network failures",
            context="Worker encountered unhandled exceptions during API calls",
            constraints={"max_issues": 5, "focus_areas": ["error-handling"]},
        )
        assert req.trigger == DecompositionTrigger.WORKER_FEEDBACK
        assert req.triggered_by == "compute-42"
        assert req.gap_description == "No error handling for network failures"
        assert req.constraints["max_issues"] == 5


class TestGoalWithDecompositionPasses:
    """Test Goal model with decomposition_passes field."""

    def test_goal_default_empty_passes(self):
        """Test goal starts with empty decomposition passes."""
        goal = Goal(
            goal_id="goal-001",
            title="Test",
            description="Test goal",
        )
        assert goal.decomposition_passes == []

    def test_goal_with_passes(self, sample_goal):
        """Test goal with existing decomposition passes."""
        assert len(sample_goal.decomposition_passes) == 1
        assert sample_goal.decomposition_passes[0].pass_number == 1
        assert sample_goal.decomposition_passes[0].trigger == DecompositionTrigger.INITIAL


# =============================================================================
# GoalService Tests
# =============================================================================


class TestGoalServiceRecordDecompositionPass:
    """Test GoalService.record_decomposition_pass."""

    @pytest.mark.asyncio
    async def test_record_initial_pass(self, goal_service):
        """Test recording the first decomposition pass."""
        # Create a goal first
        from models.work_map import GoalCreateRequest
        goal = await goal_service.create_goal(GoalCreateRequest(
            title="Test Goal",
            description="Test description",
            project_id="project-test",
        ))

        result = await goal_service.record_decomposition_pass(
            goal_id=goal.goal_id,
            decomposition_id="decomp-001",
            trigger=DecompositionTrigger.INITIAL,
            issue_ids_created=["issue-1", "issue-2"],
        )

        assert result is not None
        assert len(result.decomposition_passes) == 1
        assert result.decomposition_passes[0].pass_number == 1
        assert result.decomposition_passes[0].trigger == DecompositionTrigger.INITIAL
        assert result.decomposition_passes[0].issue_ids_created == ["issue-1", "issue-2"]
        assert result.decomposition_id == "decomp-001"
        assert "issue-1" in result.issue_ids
        assert "issue-2" in result.issue_ids

    @pytest.mark.asyncio
    async def test_record_supplemental_pass(self, goal_service):
        """Test recording a supplemental decomposition pass."""
        from models.work_map import GoalCreateRequest
        goal = await goal_service.create_goal(GoalCreateRequest(
            title="Test Goal",
            description="Test description",
            project_id="project-test",
        ))

        # Record initial pass
        await goal_service.record_decomposition_pass(
            goal_id=goal.goal_id,
            decomposition_id="decomp-001",
            trigger=DecompositionTrigger.INITIAL,
            issue_ids_created=["issue-1"],
        )

        # Record supplemental pass
        result = await goal_service.record_decomposition_pass(
            goal_id=goal.goal_id,
            decomposition_id="decomp-002",
            trigger=DecompositionTrigger.WORKER_FEEDBACK,
            issue_ids_created=["issue-2", "issue-3"],
            triggered_by="compute-42",
            trigger_context="Missing validation logic",
        )

        assert result is not None
        assert len(result.decomposition_passes) == 2
        assert result.decomposition_passes[1].pass_number == 2
        assert result.decomposition_passes[1].trigger == DecompositionTrigger.WORKER_FEEDBACK
        assert result.decomposition_passes[1].triggered_by == "compute-42"
        assert result.decomposition_passes[1].trigger_context == "Missing validation logic"
        assert result.decomposition_id == "decomp-002"
        # issue_ids should include both passes
        assert "issue-1" in result.issue_ids
        assert "issue-2" in result.issue_ids
        assert "issue-3" in result.issue_ids

    @pytest.mark.asyncio
    async def test_record_pass_no_duplicate_issue_ids(self, goal_service):
        """Test that pre-existing issue_ids are not duplicated (#652).

        When update_goal_issues sets goal.issue_ids to the same list object
        that is later passed as issue_ids_created, the extend should not
        double-count the IDs.
        """
        from models.work_map import GoalCreateRequest
        goal = await goal_service.create_goal(GoalCreateRequest(
            title="Test Goal",
            description="Test description",
            project_id="project-test",
        ))

        # Simulate what slim_claude_code does: set goal.issue_ids first
        issue_ids = ["issue-1", "issue-2", "issue-3"]
        await goal_service.update_goal_issues(goal.goal_id, issue_ids)

        # Then record_decomposition_pass with the SAME list object
        result = await goal_service.record_decomposition_pass(
            goal_id=goal.goal_id,
            decomposition_id="decomp-001",
            trigger=DecompositionTrigger.INITIAL,
            issue_ids_created=issue_ids,
        )

        assert result is not None
        # Should be exactly 3, not 6 (the old aliasing bug doubled them)
        assert len(result.issue_ids) == 3
        assert result.issue_ids == ["issue-1", "issue-2", "issue-3"]

    @pytest.mark.asyncio
    async def test_record_pass_nonexistent_goal(self, goal_service):
        """Test recording a pass for a nonexistent goal."""
        result = await goal_service.record_decomposition_pass(
            goal_id="nonexistent",
            decomposition_id="decomp-001",
            trigger=DecompositionTrigger.INITIAL,
            issue_ids_created=["issue-1"],
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_record_pass_saves_to_redis(self, goal_service_with_redis, mock_redis):
        """Test that recording a pass persists to Redis."""
        from models.work_map import GoalCreateRequest
        goal = await goal_service_with_redis.create_goal(GoalCreateRequest(
            title="Test Goal",
            description="Test",
            project_id="project-test",
        ))

        await goal_service_with_redis.record_decomposition_pass(
            goal_id=goal.goal_id,
            decomposition_id="decomp-001",
            trigger=DecompositionTrigger.INITIAL,
            issue_ids_created=["issue-1"],
        )

        # Verify hset was called (for saving goal)
        assert mock_redis._redis.hset.call_count >= 2  # create + record_pass


# =============================================================================
# GoalDecomposerService Tests - Supplemental Context
# =============================================================================


class TestDecomposerSupplementalContext:
    """Test GoalDecomposerService supplemental context in task prompts."""

    def test_build_task_context_without_supplemental(self, decomposer_service):
        """Test that task context works without supplemental context."""
        context = decomposer_service._build_task_context(
            goal_id="goal-001",
            goal_text="Build user management",
            decomposition_id="decomp-001",
        )
        assert "Goal Decomposition Task" in context
        assert "Supplemental" not in context
        assert "goal-001" in context

    def test_build_task_context_with_supplemental(self, decomposer_service):
        """Test that supplemental context is included in task prompt."""
        supplemental = {
            "trigger": "worker_feedback",
            "triggered_by": "compute-42",
            "gap_description": "Missing input validation",
            "context": "Worker encountered unhandled edge cases",
            "pass_number": 2,
        }

        context = decomposer_service._build_task_context(
            goal_id="goal-001",
            goal_text="Build user management",
            decomposition_id="decomp-002",
            supplemental_context=supplemental,
        )

        assert "Supplemental Goal Decomposition Task" in context
        assert "Pass #2" in context
        assert "worker_feedback" in context
        assert "compute-42" in context
        assert "Missing input validation" in context
        assert "Worker encountered unhandled edge cases" in context
        assert "Only identify NEW issues" in context

    def test_build_task_context_supplemental_with_existing_issues(self, decomposer_service):
        """Test supplemental context includes existing issues."""
        existing_issues = [
            MagicMock(id="issue-1", title="Schema setup", status=MagicMock(value="done")),
            MagicMock(id="issue-2", title="API endpoints", status=MagicMock(value="in_progress")),
        ]
        supplemental = {
            "trigger": "planner_gap",
            "pass_number": 2,
        }

        context = decomposer_service._build_task_context(
            goal_id="goal-001",
            goal_text="Build user management",
            decomposition_id="decomp-002",
            existing_issues=existing_issues,
            supplemental_context=supplemental,
        )

        assert "Existing Backlog" in context
        assert "Schema setup" in context
        assert "API endpoints" in context
        assert "Supplemental" in context

    def test_build_task_context_supplemental_with_prev_decomposition(self, decomposer_service):
        """Test supplemental context includes previous decomposition."""
        existing_decomp = {
            "issues": [
                {"title": "Issue A"},
                {"title": "Issue B"},
            ],
            "reasoning": "Initial decomposition into 2 issues",
        }
        supplemental = {
            "trigger": "manual",
            "gap_description": "Need more coverage",
            "pass_number": 3,
        }

        context = decomposer_service._build_task_context(
            goal_id="goal-001",
            goal_text="Build user management",
            decomposition_id="decomp-003",
            existing_decomposition=existing_decomp,
            supplemental_context=supplemental,
        )

        assert "Previous Decomposition" in context
        assert "Issue A" in context
        assert "Issue B" in context
        assert "Pass #3" in context

    def test_build_task_context_supplemental_minimal(self, decomposer_service):
        """Test supplemental with minimal fields."""
        supplemental = {
            "trigger": "manual",
            "pass_number": 2,
        }

        context = decomposer_service._build_task_context(
            goal_id="goal-001",
            goal_text="Build user management",
            decomposition_id="decomp-002",
            supplemental_context=supplemental,
        )

        assert "Supplemental Goal Decomposition Task" in context
        assert "Pass #2" in context
        assert "Gap Description" not in context
        assert "Additional Context" not in context


# =============================================================================
# API Tests - Supplemental Decompose Endpoint
# =============================================================================


@pytest.fixture
def app():
    """Create a FastAPI app with the routes."""
    app = FastAPI()
    app.include_router(slim_router)
    app.include_router(goals_router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestSupplementalDecomposeEndpoint:
    """Test POST /goals/{goal_id}/supplemental-decompose endpoint."""

    @patch("api.slim_claude_code.get_work_map_service")
    def test_goal_not_found(self, mock_wms, client):
        """Test 404 when goal doesn't exist."""
        mock_service = MagicMock()
        mock_service.get_goal = AsyncMock(return_value=None)
        mock_wms.return_value = mock_service

        response = client.post("/goals/nonexistent/supplemental-decompose")
        assert response.status_code == 404

    @patch("api.slim_claude_code.get_work_map_service")
    def test_goal_no_project_id(self, mock_wms, client):
        """Test 400 when goal has no project_id."""
        goal = Goal(
            goal_id="goal-001",
            title="Test",
            description="Test",
            project_id=None,
            status=GoalStatus.IN_PROGRESS,
        )
        mock_service = MagicMock()
        mock_service.get_goal = AsyncMock(return_value=goal)
        mock_wms.return_value = mock_service

        response = client.post("/goals/goal-001/supplemental-decompose")
        assert response.status_code == 400
        assert "project_id" in response.json()["detail"]

    @patch("api.slim_claude_code.get_work_map_service")
    def test_goal_no_initial_decomposition(self, mock_wms, client):
        """Test 400 when goal has no initial decomposition."""
        goal = Goal(
            goal_id="goal-001",
            title="Test",
            description="Test",
            project_id="project-test",
            status=GoalStatus.PLANNING,
            decomposition_id=None,
        )
        mock_service = MagicMock()
        mock_service.get_goal = AsyncMock(return_value=goal)
        mock_service.get_goal_issues = AsyncMock(return_value=[])
        mock_wms.return_value = mock_service

        response = client.post("/goals/goal-001/supplemental-decompose")
        assert response.status_code == 400
        assert "initial decomposition" in response.json()["detail"]

    @patch("api.slim_claude_code._supplemental_decompose_background")
    @patch("api.slim_claude_code._set_processing_status")
    @patch("api.slim_claude_code.get_work_map_service")
    def test_accepted_with_existing_issues(
        self, mock_wms, mock_status, mock_bg, client, sample_goal, sample_issues
    ):
        """Test 202 when goal has existing issues."""
        mock_service = MagicMock()
        mock_service.get_goal = AsyncMock(return_value=sample_goal)
        mock_service.get_goal_issues = AsyncMock(return_value=sample_issues)
        mock_wms.return_value = mock_service
        mock_status.return_value = None

        response = client.post(
            "/goals/goal-test-001/supplemental-decompose",
            json={
                "trigger": "worker_feedback",
                "triggered_by": "compute-42",
                "gap_description": "Missing validation",
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert data["goal_id"] == "goal-test-001"
        assert data["status"] == "accepted"
        assert data["pass_number"] == 2
        assert data["trigger"] == "worker_feedback"

    @patch("api.slim_claude_code._supplemental_decompose_background")
    @patch("api.slim_claude_code._set_processing_status")
    @patch("api.slim_claude_code.get_work_map_service")
    def test_accepted_with_decomposition_id_but_no_issues(
        self, mock_wms, mock_status, mock_bg, client
    ):
        """Test 202 when goal has decomposition_id but no issues yet."""
        goal = Goal(
            goal_id="goal-001",
            title="Test",
            description="Test",
            project_id="project-test",
            status=GoalStatus.IN_PROGRESS,
            decomposition_id="decomp-initial",
        )
        mock_service = MagicMock()
        mock_service.get_goal = AsyncMock(return_value=goal)
        mock_service.get_goal_issues = AsyncMock(return_value=[])
        mock_wms.return_value = mock_service
        mock_status.return_value = None

        response = client.post("/goals/goal-001/supplemental-decompose")
        assert response.status_code == 202

    @patch("api.slim_claude_code._supplemental_decompose_background")
    @patch("api.slim_claude_code._set_processing_status")
    @patch("api.slim_claude_code.get_work_map_service")
    def test_default_trigger_is_manual(
        self, mock_wms, mock_status, mock_bg, client, sample_goal, sample_issues
    ):
        """Test that default trigger is 'manual' when no body provided."""
        mock_service = MagicMock()
        mock_service.get_goal = AsyncMock(return_value=sample_goal)
        mock_service.get_goal_issues = AsyncMock(return_value=sample_issues)
        mock_wms.return_value = mock_service
        mock_status.return_value = None

        response = client.post("/goals/goal-test-001/supplemental-decompose")
        assert response.status_code == 202
        data = response.json()
        assert data["trigger"] == "manual"


# =============================================================================
# API Tests - Decomposition Passes Endpoint
# =============================================================================


class TestDecompositionPassesEndpoint:
    """Test GET /goals/{goal_id}/decomposition-passes endpoint."""

    @patch("api.work_map.get_work_map_service")
    def test_get_passes_empty(self, mock_wms, client):
        """Test getting passes for goal with no passes."""
        goal = Goal(
            goal_id="goal-001",
            title="Test",
            description="Test",
        )
        mock_service = MagicMock()
        mock_service.get_goal = AsyncMock(return_value=goal)
        mock_wms.return_value = mock_service

        response = client.get("/goals/goal-001/decomposition-passes")
        assert response.status_code == 200
        assert response.json() == []

    @patch("api.work_map.get_work_map_service")
    def test_get_passes_with_history(self, mock_wms, client, sample_goal):
        """Test getting passes with decomposition history."""
        mock_service = MagicMock()
        mock_service.get_goal = AsyncMock(return_value=sample_goal)
        mock_wms.return_value = mock_service

        response = client.get("/goals/goal-test-001/decomposition-passes")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["pass_number"] == 1
        assert data[0]["trigger"] == "initial"
        assert data[0]["issue_ids_created"] == ["issue-1", "issue-2"]

    @patch("api.work_map.get_work_map_service")
    def test_get_passes_goal_not_found(self, mock_wms, client):
        """Test 404 when goal doesn't exist."""
        mock_service = MagicMock()
        mock_service.get_goal = AsyncMock(return_value=None)
        mock_wms.return_value = mock_service

        response = client.get("/goals/nonexistent/decomposition-passes")
        assert response.status_code == 404


# =============================================================================
# Redis Serialization Tests
# =============================================================================


class TestDecompositionPassesRedis:
    """Test Redis serialization of decomposition_passes field."""

    @pytest.mark.asyncio
    async def test_save_and_load_passes(self, goal_service_with_redis, mock_redis):
        """Test that decomposition_passes serializes correctly."""
        from models.work_map import GoalCreateRequest
        goal = await goal_service_with_redis.create_goal(GoalCreateRequest(
            title="Test Goal",
            description="Test",
            project_id="project-test",
        ))

        await goal_service_with_redis.record_decomposition_pass(
            goal_id=goal.goal_id,
            decomposition_id="decomp-001",
            trigger=DecompositionTrigger.INITIAL,
            issue_ids_created=["issue-1"],
        )

        # Verify the hset call includes decomposition_passes
        calls = mock_redis._redis.hset.call_args_list
        last_call = calls[-1]
        mapping = last_call.kwargs.get("mapping", last_call[1].get("mapping", {}))
        passes_json = mapping.get("decomposition_passes", "[]")
        passes_data = json.loads(passes_json)
        assert len(passes_data) == 1
        assert passes_data[0]["decomposition_id"] == "decomp-001"
        assert passes_data[0]["trigger"] == "initial"
        assert passes_data[0]["pass_number"] == 1
