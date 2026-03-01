"""Unit tests for initial bucket tree creation after decomposition.

Verifies that create_initial_bucket_tree correctly creates a bucket tree
when issues are first created from goal decomposition, fixing the
chicken-and-egg problem where the tree never existed to be reorganized.

Reference: Issue #605
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from models.goal_decomposer import DecomposedIssue, EstimatedComplexity
from models.planner_profile import (
    ConfidenceBand,
    ConfidenceLevel,
    PlannerProfile,
    ProfileWeights,
    WeightedValue,
)
from models.priority_bucket import (
    BucketDefinition,
    BucketItem,
    BucketTree,
    ItemReadiness,
    PriorityBucket,
)
from services.bucket_tree_store import (
    BucketTreeStore,
    create_initial_bucket_tree,
    set_bucket_tree_store,
)


# =============================================================================
# Helpers
# =============================================================================


def make_issue(temp_id, title="Task", blocked_by=None, **kw):
    return DecomposedIssue(
        temp_id=temp_id,
        title=title,
        description=kw.get("description", f"Description for {temp_id}"),
        issue_type=kw.get("issue_type", "feature"),
        priority=kw.get("priority", "P2"),
        area=kw.get("area", "backend"),
        required_skills=[],
        estimated_complexity=EstimatedComplexity.M,
        blocked_by=blocked_by or [],
        acceptance_criteria=[],
    )


def make_profile(project_id="project-001"):
    return PlannerProfile(
        profile_id="profile-test-001",
        project_id=project_id,
        weights=ProfileWeights(
            work_type_weights={
                "feature": WeightedValue(
                    weight=0.8,
                    confidence=ConfidenceBand(level=ConfidenceLevel.HIGH),
                ),
            },
        ),
        active_goal_ids=["goal-001"],
    )


def make_tree(project_id="project-001"):
    return BucketTree(
        tree_id="tree-existing",
        project_id=project_id,
        buckets=[
            PriorityBucket(
                bucket_id="bucket-1",
                rank=1,
                definition=BucketDefinition(name="Test Bucket"),
                items=[
                    BucketItem(
                        item_id="item-1",
                        readiness=ItemReadiness.READY,
                    )
                ],
            ),
        ],
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def store():
    """BucketTreeStore with no Redis."""
    s = BucketTreeStore(redis_client=None)
    s.load = AsyncMock(return_value=None)
    s.save = AsyncMock()
    return s


@pytest.fixture(autouse=True)
def setup_store(store):
    """Set the global store for each test, reset after."""
    set_bucket_tree_store(store)
    yield
    set_bucket_tree_store(None)


@pytest.fixture
def issues():
    return [
        make_issue("issue-1", "Set up database schema"),
        make_issue("issue-2", "Build API endpoints", blocked_by=["issue-1"]),
        make_issue("issue-3", "Create frontend views", blocked_by=["issue-2"]),
    ]


@pytest.fixture
def dependency_graph():
    return {
        "issue-2": ["issue-1"],
        "issue-3": ["issue-2"],
    }


def _patch_profile_service(profile):
    """Create patches for planner profile service with a given profile."""
    profile_service = MagicMock()
    profile_service.get_profile = AsyncMock(return_value=profile)
    profile_service.construct_profile = AsyncMock(return_value=profile)
    return patch(
        "services.planner_profile_service.get_planner_profile_service",
        return_value=profile_service,
    ), profile_service


def _patch_planner(tree):
    """Create patches for work planner service with a given tree."""
    planner = MagicMock()
    planner.create_bucket_tree = AsyncMock(return_value=tree)
    return patch(
        "services.work_planner.get_work_planner_service",
        return_value=planner,
    ), planner


# =============================================================================
# Tests: create_initial_bucket_tree
# =============================================================================


class TestCreateInitialBucketTree:
    """Tests for the create_initial_bucket_tree function."""

    @pytest.mark.asyncio
    async def test_creates_tree_on_first_call(self, store, issues, dependency_graph):
        """Tree is created and saved when no tree exists for the project."""
        profile = make_profile()
        mock_tree = make_tree()

        profile_patch, profile_svc = _patch_profile_service(profile)
        planner_patch, planner = _patch_planner(mock_tree)

        with profile_patch, planner_patch:
            result = await create_initial_bucket_tree(
                project_id="project-001",
                decomposed_issues=issues,
                dependency_graph=dependency_graph,
            )

        assert result is True
        store.save.assert_awaited_once_with(mock_tree)
        planner.create_bucket_tree.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_tree_exists(self, store, issues, dependency_graph):
        """Tree creation is skipped if a tree already exists."""
        store.load = AsyncMock(return_value=make_tree())

        result = await create_initial_bucket_tree(
            project_id="project-001",
            decomposed_issues=issues,
            dependency_graph=dependency_graph,
        )

        assert result is False
        store.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_replaces_existing_when_flag_set(
        self, store, issues, dependency_graph
    ):
        """Tree is rebuilt when replace_existing=True, even if one exists."""
        store.load = AsyncMock(return_value=make_tree())
        profile = make_profile()
        mock_tree = make_tree()

        profile_patch, _ = _patch_profile_service(profile)
        planner_patch, planner = _patch_planner(mock_tree)

        with profile_patch, planner_patch:
            result = await create_initial_bucket_tree(
                project_id="project-001",
                decomposed_issues=issues,
                dependency_graph=dependency_graph,
                replace_existing=True,
            )

        assert result is True
        store.save.assert_awaited_once_with(mock_tree)

    @pytest.mark.asyncio
    async def test_skips_with_no_issues(self, store):
        """Returns False when no issues are provided."""
        result = await create_initial_bucket_tree(
            project_id="project-001",
            decomposed_issues=[],
            dependency_graph={},
        )

        assert result is False
        store.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_store_not_initialized(self, issues, dependency_graph):
        """Returns False when the bucket tree store is not initialized."""
        set_bucket_tree_store(None)

        result = await create_initial_bucket_tree(
            project_id="project-001",
            decomposed_issues=issues,
            dependency_graph=dependency_graph,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_skips_when_profile_service_not_initialized(
        self, store, issues, dependency_graph
    ):
        """Returns False when the planner profile service is not initialized."""
        with patch(
            "services.planner_profile_service.get_planner_profile_service",
            side_effect=RuntimeError("not initialized"),
        ):
            result = await create_initial_bucket_tree(
                project_id="project-001",
                decomposed_issues=issues,
                dependency_graph=dependency_graph,
            )

        assert result is False
        store.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_constructs_profile_when_none_exists(
        self, store, issues, dependency_graph
    ):
        """Constructs a profile from active goals when no profile exists."""
        from models.work_map import Goal, GoalStatus, IssuePriority

        mock_goal = Goal(
            goal_id="goal-001",
            title="Build a new feature",
            description="Create something new",
            project_id="project-001",
            priority=IssuePriority.P1,
            status=GoalStatus.IN_PROGRESS,
        )
        new_profile = make_profile()
        mock_tree = make_tree()

        profile_service = MagicMock()
        profile_service.get_profile = AsyncMock(return_value=None)
        profile_service.construct_profile = AsyncMock(return_value=new_profile)

        goal_service = MagicMock()
        goal_service.list_active_goals = AsyncMock(return_value=[mock_goal])

        planner = MagicMock()
        planner.create_bucket_tree = AsyncMock(return_value=mock_tree)

        with (
            patch(
                "services.planner_profile_service.get_planner_profile_service",
                return_value=profile_service,
            ),
            patch(
                "services.goal_service.get_goal_service",
                return_value=goal_service,
            ),
            patch(
                "services.work_planner.get_work_planner_service",
                return_value=planner,
            ),
        ):
            result = await create_initial_bucket_tree(
                project_id="project-001",
                decomposed_issues=issues,
                dependency_graph=dependency_graph,
            )

        assert result is True
        profile_service.construct_profile.assert_awaited_once_with(
            "project-001", [mock_goal]
        )
        store.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_no_active_goals_and_no_profile(
        self, store, issues, dependency_graph
    ):
        """Returns False when there's no profile and no active goals."""
        profile_service = MagicMock()
        profile_service.get_profile = AsyncMock(return_value=None)

        goal_service = MagicMock()
        goal_service.list_active_goals = AsyncMock(return_value=[])

        with (
            patch(
                "services.planner_profile_service.get_planner_profile_service",
                return_value=profile_service,
            ),
            patch(
                "services.goal_service.get_goal_service",
                return_value=goal_service,
            ),
        ):
            result = await create_initial_bucket_tree(
                project_id="project-001",
                decomposed_issues=issues,
                dependency_graph=dependency_graph,
            )

        assert result is False
        store.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handles_planner_exception_gracefully(
        self, store, issues, dependency_graph
    ):
        """Returns False and doesn't crash when planner raises an exception."""
        profile = make_profile()

        profile_service = MagicMock()
        profile_service.get_profile = AsyncMock(return_value=profile)

        planner = MagicMock()
        planner.create_bucket_tree = AsyncMock(
            side_effect=ValueError("cyclic dep")
        )

        with (
            patch(
                "services.planner_profile_service.get_planner_profile_service",
                return_value=profile_service,
            ),
            patch(
                "services.work_planner.get_work_planner_service",
                return_value=planner,
            ),
        ):
            result = await create_initial_bucket_tree(
                project_id="project-001",
                decomposed_issues=issues,
                dependency_graph=dependency_graph,
            )

        assert result is False
        store.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_passes_characterization_map(
        self, store, issues, dependency_graph
    ):
        """Characterization map is forwarded to the work planner."""
        profile = make_profile()
        mock_tree = make_tree()
        char_map = {"issue-1": MagicMock()}

        profile_patch, _ = _patch_profile_service(profile)
        planner_patch, planner = _patch_planner(mock_tree)

        with profile_patch, planner_patch:
            await create_initial_bucket_tree(
                project_id="project-001",
                decomposed_issues=issues,
                dependency_graph=dependency_graph,
                characterization_map=char_map,
            )

        call_kwargs = planner.create_bucket_tree.call_args[1]
        assert call_kwargs["characterizations"] == char_map

    @pytest.mark.asyncio
    async def test_records_decision_trace_on_creation(
        self, store, issues, dependency_graph
    ):
        """A BUCKET_REORGANIZATION decision trace is recorded on initial creation."""
        profile = make_profile()
        mock_tree = make_tree()

        mock_trace_service = MagicMock()
        mock_trace_service.record_trace = AsyncMock()

        profile_patch, _ = _patch_profile_service(profile)
        planner_patch, _ = _patch_planner(mock_tree)

        with profile_patch, planner_patch, patch(
            "services.decision_trace_service.get_decision_trace_service",
            return_value=mock_trace_service,
        ):
            result = await create_initial_bucket_tree(
                project_id="project-001",
                decomposed_issues=issues,
                dependency_graph=dependency_graph,
            )

        assert result is True
        mock_trace_service.record_trace.assert_awaited_once()
        trace = mock_trace_service.record_trace.call_args[0][0]
        assert trace.decision_type.value == "bucket_reorganization"
        assert trace.project_id == "project-001"
        assert "initial_creation" in trace.trigger.trigger_type
        assert len(trace.key_factors) >= 1

    @pytest.mark.asyncio
    async def test_trace_records_all_items_in_impact(
        self, store, issues, dependency_graph
    ):
        """Decision trace impact includes all item IDs from the created tree."""
        profile = make_profile()
        mock_tree = make_tree()

        mock_trace_service = MagicMock()
        mock_trace_service.record_trace = AsyncMock()

        profile_patch, _ = _patch_profile_service(profile)
        planner_patch, _ = _patch_planner(mock_tree)

        with profile_patch, planner_patch, patch(
            "services.decision_trace_service.get_decision_trace_service",
            return_value=mock_trace_service,
        ):
            await create_initial_bucket_tree(
                project_id="project-001",
                decomposed_issues=issues,
                dependency_graph=dependency_graph,
            )

        trace = mock_trace_service.record_trace.call_args[0][0]
        # mock_tree has items from make_tree helper
        assert trace.impact is not None
        assert len(trace.impact.affected_bucket_ids) > 0

    @pytest.mark.asyncio
    async def test_creation_succeeds_even_if_trace_service_unavailable(
        self, store, issues, dependency_graph
    ):
        """Tree creation still succeeds if decision trace service is not initialized."""
        profile = make_profile()
        mock_tree = make_tree()

        profile_patch, _ = _patch_profile_service(profile)
        planner_patch, _ = _patch_planner(mock_tree)

        with profile_patch, planner_patch, patch(
            "services.decision_trace_service.get_decision_trace_service",
            side_effect=RuntimeError("not initialized"),
        ):
            result = await create_initial_bucket_tree(
                project_id="project-001",
                decomposed_issues=issues,
                dependency_graph=dependency_graph,
            )

        assert result is True
        store.save.assert_awaited_once()
