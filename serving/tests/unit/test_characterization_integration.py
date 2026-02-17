"""Tests for characterization integration into decomposition-to-planning flow.

Tests the pipeline: Decomposition -> Characterization -> Issue Creation
as specified in docs/work_management_framework.md Section 5.

Issue: #564
"""

import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

from models.characterization import (
    BatchCharacterizationResponse,
    CharacterizationRequest,
    CharacterizationResult,
    CharacterizationStatus,
)
from models.goal_decomposer import (
    DecomposedIssue,
    EstimatedComplexity,
    GoalDecomposerConfig,
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
    return redis


@pytest.fixture
def sample_decomposition_result():
    """Sample decomposition result."""
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
                acceptance_criteria=["Users table created"],
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
                acceptance_criteria=["GET /users works"],
            ),
        ],
        dependency_graph={"issue-2": ["issue-1"]},
        execution_phases=[["issue-1"], ["issue-2"]],
        confidence=0.85,
        reasoning="Decomposed into 2 issues following data-first pattern.",
    )


@pytest.fixture
def sample_characterization_results():
    """Sample characterization results keyed by temp_id."""
    return {
        "issue-1": CharacterizationResult(
            item_id="issue-1",
            project_id="project-test",
            ontology_tags=None,
            meaning=None,
            status=CharacterizationStatus.COMPLETED,
            confidence=0.9,
            evaluated_in_isolation=True,
            evaluated_in_context=False,
        ),
        "issue-2": CharacterizationResult(
            item_id="issue-2",
            project_id="project-test",
            ontology_tags=None,
            meaning=None,
            status=CharacterizationStatus.COMPLETED,
            confidence=0.85,
            evaluated_in_isolation=True,
            evaluated_in_context=False,
        ),
    }


@pytest.fixture
def sample_batch_characterization_response(sample_characterization_results):
    """Sample batch response from characterization service."""
    return BatchCharacterizationResponse(
        project_id="project-test",
        results=list(sample_characterization_results.values()),
        total=2,
        completed=2,
        failed=0,
    )


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
        timeout=10,
    )
    service._initialized = True
    return service


# ============================================================================
# Tests: decompose_and_characterize
# ============================================================================


class TestDecomposeAndCharacterize:
    """Test the decompose_and_characterize method that implements the spec pipeline."""

    @pytest.mark.asyncio
    async def test_returns_decomposition_and_characterization_map(
        self,
        goal_decomposer_service,
        sample_decomposition_result,
        sample_batch_characterization_response,
    ):
        """Test that decompose_and_characterize returns both results."""
        mock_char_service = MagicMock()
        mock_char_service.characterize_items = AsyncMock(
            return_value=sample_batch_characterization_response
        )

        with patch.object(
            goal_decomposer_service, "decompose_goal", new_callable=AsyncMock
        ) as mock_decompose, patch(
            "services.characterization_service.get_characterization_service",
            return_value=mock_char_service,
        ):
            mock_decompose.return_value = sample_decomposition_result

            decomposition, char_map = await goal_decomposer_service.decompose_and_characterize(
                goal_id="goal-001",
                goal_text="Build a user management system",
                project_id="project-test",
            )

        assert isinstance(decomposition, GoalDecompositionResult)
        assert len(decomposition.issues) == 2
        assert len(char_map) == 2
        assert "issue-1" in char_map
        assert "issue-2" in char_map

    @pytest.mark.asyncio
    async def test_calls_decompose_then_characterize(
        self,
        goal_decomposer_service,
        sample_decomposition_result,
        sample_batch_characterization_response,
    ):
        """Test that decomposition happens first, then characterization."""
        call_order = []

        async def mock_decompose(*args, **kwargs):
            call_order.append("decompose")
            return sample_decomposition_result

        async def mock_characterize(*args, **kwargs):
            call_order.append("characterize")
            return sample_batch_characterization_response

        mock_char_service = MagicMock()
        mock_char_service.characterize_items = AsyncMock(side_effect=mock_characterize)

        with patch.object(
            goal_decomposer_service, "decompose_goal", new_callable=AsyncMock,
            side_effect=mock_decompose,
        ), patch(
            "services.characterization_service.get_characterization_service",
            return_value=mock_char_service,
        ):
            await goal_decomposer_service.decompose_and_characterize(
                goal_id="goal-001",
                goal_text="Build a feature",
                project_id="project-test",
            )

        assert call_order == ["decompose", "characterize"]

    @pytest.mark.asyncio
    async def test_characterization_uses_temp_ids(
        self,
        goal_decomposer_service,
        sample_decomposition_result,
        sample_batch_characterization_response,
    ):
        """Test that characterization requests use temp_ids from decomposition."""
        mock_char_service = MagicMock()
        mock_char_service.characterize_items = AsyncMock(
            return_value=sample_batch_characterization_response
        )

        with patch.object(
            goal_decomposer_service, "decompose_goal", new_callable=AsyncMock,
            return_value=sample_decomposition_result,
        ), patch(
            "services.characterization_service.get_characterization_service",
            return_value=mock_char_service,
        ):
            await goal_decomposer_service.decompose_and_characterize(
                goal_id="goal-001",
                goal_text="Build a feature",
                project_id="project-test",
            )

        # Verify characterize_items was called with correct args
        mock_char_service.characterize_items.assert_awaited_once()
        call_kwargs = mock_char_service.characterize_items.call_args.kwargs
        assert call_kwargs["project_id"] == "project-test"
        assert call_kwargs["source_goal_id"] == "goal-001"

        items = call_kwargs["items"]
        assert len(items) == 2
        assert items[0].item_id == "issue-1"
        assert items[0].title == "Set up database schema"
        assert items[0].issue_type_hint == "feature"
        assert items[0].area_hint == "database"
        assert items[1].item_id == "issue-2"
        assert items[1].title == "Implement user API endpoints"

    @pytest.mark.asyncio
    async def test_returns_empty_map_when_no_compute_available(
        self,
        goal_decomposer_service,
        sample_decomposition_result,
    ):
        """Test graceful fallback when characterization compute is unavailable."""
        mock_char_service = MagicMock()
        mock_char_service.characterize_items = AsyncMock(
            side_effect=RuntimeError("No idle compute instances available")
        )

        with patch.object(
            goal_decomposer_service, "decompose_goal", new_callable=AsyncMock,
            return_value=sample_decomposition_result,
        ), patch(
            "services.characterization_service.get_characterization_service",
            return_value=mock_char_service,
        ):
            decomposition, char_map = await goal_decomposer_service.decompose_and_characterize(
                goal_id="goal-001",
                goal_text="Build a feature",
                project_id="project-test",
            )

        # Decomposition still returned, characterization map is empty
        assert len(decomposition.issues) == 2
        assert char_map == {}

    @pytest.mark.asyncio
    async def test_returns_empty_map_when_characterization_fails(
        self,
        goal_decomposer_service,
        sample_decomposition_result,
    ):
        """Test graceful fallback on characterization error."""
        mock_char_service = MagicMock()
        mock_char_service.characterize_items = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        with patch.object(
            goal_decomposer_service, "decompose_goal", new_callable=AsyncMock,
            return_value=sample_decomposition_result,
        ), patch(
            "services.characterization_service.get_characterization_service",
            return_value=mock_char_service,
        ):
            decomposition, char_map = await goal_decomposer_service.decompose_and_characterize(
                goal_id="goal-001",
                goal_text="Build a feature",
                project_id="project-test",
            )

        assert len(decomposition.issues) == 2
        assert char_map == {}

    @pytest.mark.asyncio
    async def test_returns_empty_map_when_no_issues_decomposed(
        self,
        goal_decomposer_service,
    ):
        """Test that empty decomposition skips characterization entirely."""
        empty_result = GoalDecompositionResult(
            goal_id="goal-001",
            decomposition_id="decomp-empty",
            issues=[],
            confidence=0.5,
            reasoning="No issues needed",
        )

        with patch.object(
            goal_decomposer_service, "decompose_goal", new_callable=AsyncMock,
            return_value=empty_result,
        ):
            decomposition, char_map = await goal_decomposer_service.decompose_and_characterize(
                goal_id="goal-001",
                goal_text="Simple goal",
                project_id="project-test",
            )

        assert len(decomposition.issues) == 0
        assert char_map == {}

    @pytest.mark.asyncio
    async def test_passes_all_args_to_decompose_goal(
        self,
        goal_decomposer_service,
        sample_decomposition_result,
        sample_batch_characterization_response,
    ):
        """Test that all optional args are forwarded to decompose_goal."""
        mock_char_service = MagicMock()
        mock_char_service.characterize_items = AsyncMock(
            return_value=sample_batch_characterization_response
        )

        project_context = {"tech_stack": "Python"}
        constraints = {"max_issues": 10}
        comments = [{"content": "test", "created_by": "user"}]
        existing_decomp = {"issues": []}
        supplemental = {"trigger": "manual", "pass_number": 2}

        with patch.object(
            goal_decomposer_service, "decompose_goal", new_callable=AsyncMock,
            return_value=sample_decomposition_result,
        ) as mock_decompose, patch(
            "services.characterization_service.get_characterization_service",
            return_value=mock_char_service,
        ):
            await goal_decomposer_service.decompose_and_characterize(
                goal_id="goal-001",
                goal_text="Build a feature",
                project_id="project-test",
                project_context=project_context,
                constraints=constraints,
                conversation_comments=comments,
                existing_decomposition=existing_decomp,
                supplemental_context=supplemental,
            )

        mock_decompose.assert_awaited_once_with(
            goal_id="goal-001",
            goal_text="Build a feature",
            project_context=project_context,
            existing_issues=None,
            constraints=constraints,
            conversation_comments=comments,
            existing_decomposition=existing_decomp,
            supplemental_context=supplemental,
        )


# ============================================================================
# Tests: map_to_issue_models with characterization results
# ============================================================================


class TestMapToIssueModelsWithCharacterization:
    """Test that map_to_issue_models includes characterization data when available."""

    def test_without_characterization_results(self, goal_decomposer_service):
        """Test mapping without characterization (backwards compatible)."""
        decomposed = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Test Issue",
                description="Test description",
                issue_type="feature",
                priority="P1",
                area="database",
            ),
        ]

        result = goal_decomposer_service.map_to_issue_models(
            decomposed, goal_id="goal-001"
        )

        assert len(result) == 1
        assert result[0]["temp_id"] == "issue-1"
        assert "ontology_tags" not in result[0]

    def test_with_characterization_results_no_ontology(self, goal_decomposer_service):
        """Test mapping with characterization results that have no ontology tags."""
        decomposed = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Test Issue",
                description="Test description",
            ),
        ]

        char_results = {
            "issue-1": CharacterizationResult(
                item_id="issue-1",
                project_id="project-test",
                ontology_tags=None,
                meaning=None,
                status=CharacterizationStatus.PENDING,
                confidence=0.0,
            ),
        }

        result = goal_decomposer_service.map_to_issue_models(
            decomposed,
            goal_id="goal-001",
            characterization_results=char_results,
        )

        assert len(result) == 1
        # No ontology_tags because they're None
        assert "ontology_tags" not in result[0]

    def test_with_characterization_results_with_ontology(self, goal_decomposer_service):
        """Test mapping includes ontology_tags from completed characterization."""
        from models.ontology import (
            LifecycleStage,
            OntologyTags,
            ProjectSpecificTags,
            TechnicalDomain,
            UniversalTags,
            WorkType,
        )

        decomposed = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Test Issue",
                description="Test description",
                issue_type="feature",
                area="database",
            ),
        ]

        ontology = OntologyTags(
            universal=UniversalTags(
                work_type=WorkType.FEATURE,
                lifecycle_stage=LifecycleStage.BUILD,
                technical_domains=[TechnicalDomain.BACKEND, TechnicalDomain.DATA],
            ),
            project_specific=ProjectSpecificTags(
                cluster_ids=["cluster-db"],
                cluster_labels=["database"],
            ),
        )

        char_results = {
            "issue-1": CharacterizationResult(
                item_id="issue-1",
                project_id="project-test",
                ontology_tags=ontology,
                meaning=None,
                status=CharacterizationStatus.COMPLETED,
                confidence=0.9,
            ),
        }

        result = goal_decomposer_service.map_to_issue_models(
            decomposed,
            goal_id="goal-001",
            characterization_results=char_results,
        )

        assert len(result) == 1
        assert result[0]["ontology_tags"] is ontology
        assert result[0]["ontology_tags"].universal.work_type == WorkType.FEATURE

    def test_partial_characterization_results(self, goal_decomposer_service):
        """Test mapping when only some issues have characterization results."""
        from models.ontology import (
            LifecycleStage,
            OntologyTags,
            ProjectSpecificTags,
            TechnicalDomain,
            UniversalTags,
            WorkType,
        )

        decomposed = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Issue 1",
                description="First issue",
            ),
            DecomposedIssue(
                temp_id="issue-2",
                title="Issue 2",
                description="Second issue",
            ),
        ]

        ontology = OntologyTags(
            universal=UniversalTags(
                work_type=WorkType.FEATURE,
                lifecycle_stage=LifecycleStage.BUILD,
                technical_domains=[TechnicalDomain.BACKEND],
            ),
            project_specific=ProjectSpecificTags(),
        )

        # Only issue-1 has characterization
        char_results = {
            "issue-1": CharacterizationResult(
                item_id="issue-1",
                project_id="project-test",
                ontology_tags=ontology,
                meaning=None,
                status=CharacterizationStatus.COMPLETED,
                confidence=0.9,
            ),
        }

        result = goal_decomposer_service.map_to_issue_models(
            decomposed,
            goal_id="goal-001",
            characterization_results=char_results,
        )

        assert len(result) == 2
        # issue-1 has ontology_tags
        assert result[0]["ontology_tags"] is ontology
        # issue-2 does not
        assert "ontology_tags" not in result[1]

    def test_empty_characterization_results(self, goal_decomposer_service):
        """Test mapping with empty characterization dict (no compute was available)."""
        decomposed = [
            DecomposedIssue(
                temp_id="issue-1",
                title="Test Issue",
                description="Test description",
            ),
        ]

        result = goal_decomposer_service.map_to_issue_models(
            decomposed,
            goal_id="goal-001",
            characterization_results={},
        )

        assert len(result) == 1
        assert "ontology_tags" not in result[0]
