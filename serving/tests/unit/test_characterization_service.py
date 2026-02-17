"""Unit tests for CharacterizationService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from models.characterization import (
    BatchCharacterizationRequest,
    BusinessMeaning,
    CharacterizationRequest,
    CharacterizationResult,
    CharacterizationStatus,
    ContextualDependency,
    ContextualMeaning,
    ContextualRole,
    DependencyRelation,
    DependencyType,
    MeaningAssessment,
    TechnicalMeaning,
)
from models.ontology import (
    LifecycleStage,
    OntologyTags,
    ProjectSpecificTags,
    TechnicalDomain,
    UniversalTags,
    WorkType,
)
from services.characterization_service import CharacterizationService


# =============================================================================
# Helpers
# =============================================================================


def make_ontology_tags():
    return OntologyTags(
        universal=UniversalTags(
            work_type=WorkType.FEATURE,
            lifecycle_stage=LifecycleStage.BUILD,
            technical_domains=[TechnicalDomain.BACKEND],
        ),
        project_specific=ProjectSpecificTags(cluster_ids=["cluster-abc"]),
    )


def make_meaning():
    return MeaningAssessment(
        business=BusinessMeaning(summary="Adds value"),
        technical=TechnicalMeaning(summary="Implements feature"),
        contextual=ContextualMeaning(
            summary="Core work",
            role=ContextualRole.FOUNDATIONAL,
        ),
    )


def make_completed_result(item_id="item-001", project_id="proj-1", **overrides):
    defaults = dict(
        item_id=item_id,
        project_id=project_id,
        ontology_tags=make_ontology_tags(),
        meaning=make_meaning(),
        status=CharacterizationStatus.COMPLETED,
        confidence=0.85,
        evaluated_in_isolation=True,
        evaluated_in_context=True,
    )
    defaults.update(overrides)
    return CharacterizationResult(**defaults)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service():
    """CharacterizationService with no Redis."""
    svc = CharacterizationService(redis_client=None)
    svc._initialized = True
    svc._save_result_to_redis = AsyncMock()
    return svc


@pytest.fixture
def service_with_data(service):
    """Service pre-loaded with characterization results."""
    service._results["proj-1"] = {
        "item-001": make_completed_result("item-001"),
        "item-002": make_completed_result("item-002"),
        "item-003": make_completed_result(
            "item-003",
            status=CharacterizationStatus.FAILED,
            error="LLM timeout",
        ),
    }
    return service


# =============================================================================
# Initialization Tests
# =============================================================================


class TestServiceInit:
    def test_init_no_redis(self):
        svc = CharacterizationService(redis_client=None)
        assert svc._results == {}
        assert not svc._initialized

    @pytest.mark.asyncio
    async def test_initialize_sets_flag(self):
        svc = CharacterizationService(redis_client=None)
        await svc.initialize()
        assert svc._initialized

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self):
        svc = CharacterizationService(redis_client=None)
        await svc.initialize()
        await svc.initialize()
        assert svc._initialized


# =============================================================================
# Store and Retrieve Tests
# =============================================================================


class TestStoreResult:
    @pytest.mark.asyncio
    async def test_store_new_result(self, service):
        result = make_completed_result()
        await service.store_result(result)

        stored = await service.get_result("proj-1", "item-001")
        assert stored is not None
        assert stored.item_id == "item-001"
        assert stored.confidence == 0.85
        service._save_result_to_redis.assert_awaited()

    @pytest.mark.asyncio
    async def test_store_overwrites_existing(self, service):
        result1 = make_completed_result(confidence=0.5)
        await service.store_result(result1)

        result2 = make_completed_result(confidence=0.9)
        await service.store_result(result2)

        stored = await service.get_result("proj-1", "item-001")
        assert stored.confidence == 0.9

    @pytest.mark.asyncio
    async def test_store_creates_project_entry(self, service):
        result = make_completed_result(project_id="new-proj")
        await service.store_result(result)
        assert "new-proj" in service._results


class TestGetResult:
    @pytest.mark.asyncio
    async def test_get_existing(self, service_with_data):
        result = await service_with_data.get_result("proj-1", "item-001")
        assert result is not None
        assert result.status == CharacterizationStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_get_nonexistent_item(self, service_with_data):
        result = await service_with_data.get_result("proj-1", "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_nonexistent_project(self, service_with_data):
        result = await service_with_data.get_result("nonexistent", "item-001")
        assert result is None


class TestGetResultsForProject:
    @pytest.mark.asyncio
    async def test_returns_all(self, service_with_data):
        results = await service_with_data.get_results_for_project("proj-1")
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_empty_project(self, service_with_data):
        results = await service_with_data.get_results_for_project("nonexistent")
        assert results == []


class TestGetCompletedResults:
    @pytest.mark.asyncio
    async def test_filters_completed(self, service_with_data):
        completed = await service_with_data.get_completed_results("proj-1")
        assert len(completed) == 2
        assert all(r.status == CharacterizationStatus.COMPLETED for r in completed)


# =============================================================================
# Batch Operations Tests
# =============================================================================


class TestCreatePendingBatch:
    @pytest.mark.asyncio
    async def test_creates_pending_entries(self, service):
        request = BatchCharacterizationRequest(
            project_id="proj-1",
            items=[
                CharacterizationRequest(
                    item_id="new-1",
                    project_id="proj-1",
                    title="Task A",
                    description="Do A",
                ),
                CharacterizationRequest(
                    item_id="new-2",
                    project_id="proj-1",
                    title="Task B",
                    description="Do B",
                ),
            ],
        )
        response = await service.create_pending_batch(request)

        assert response.total == 2
        assert response.completed == 0
        assert response.failed == 0

        # Both should be stored as pending
        r1 = await service.get_result("proj-1", "new-1")
        assert r1 is not None
        assert r1.status == CharacterizationStatus.PENDING

        r2 = await service.get_result("proj-1", "new-2")
        assert r2 is not None
        assert r2.status == CharacterizationStatus.PENDING


class TestMarkInProgress:
    @pytest.mark.asyncio
    async def test_marks_pending_as_in_progress(self, service):
        # Create a pending result first
        result = make_completed_result(status=CharacterizationStatus.PENDING)
        await service.store_result(result)

        updated = await service.mark_in_progress("proj-1", "item-001")
        assert updated.status == CharacterizationStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_does_not_mark_completed(self, service_with_data):
        """Already completed items should not be re-marked."""
        updated = await service_with_data.mark_in_progress("proj-1", "item-001")
        # Already COMPLETED, so status should stay COMPLETED
        assert updated.status == CharacterizationStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_nonexistent_returns_none(self, service):
        result = await service.mark_in_progress("proj-1", "nonexistent")
        assert result is None


class TestMarkFailed:
    @pytest.mark.asyncio
    async def test_marks_as_failed(self, service_with_data):
        updated = await service_with_data.mark_failed("proj-1", "item-001", "Timeout")
        assert updated.status == CharacterizationStatus.FAILED
        assert updated.error == "Timeout"

    @pytest.mark.asyncio
    async def test_nonexistent_returns_none(self, service):
        result = await service.mark_failed("proj-1", "nonexistent", "Error")
        assert result is None


# =============================================================================
# Work Topology Tests
# =============================================================================


class TestGetWorkTopology:
    @pytest.mark.asyncio
    async def test_topology_from_completed(self, service_with_data):
        topology = await service_with_data.get_work_topology("proj-1")
        assert topology.project_id == "proj-1"
        # Only 2 completed out of 3
        assert topology.item_count == 2

    @pytest.mark.asyncio
    async def test_empty_topology(self, service):
        topology = await service.get_work_topology("proj-1")
        assert topology.item_count == 0


# =============================================================================
# Statistics Tests
# =============================================================================


class TestGetStats:
    @pytest.mark.asyncio
    async def test_stats(self, service_with_data):
        stats = await service_with_data.get_stats("proj-1")
        assert stats["total"] == 3
        assert stats["completed"] == 2
        assert stats["failed"] == 1
        assert stats["pending"] == 0

    @pytest.mark.asyncio
    async def test_stats_empty_project(self, service):
        stats = await service.get_stats("nonexistent")
        assert stats["total"] == 0


# =============================================================================
# Compute Delegation Tests
# =============================================================================


class TestCharacterizeItems:
    @pytest.mark.asyncio
    async def test_success_spawns_and_waits(self, service):
        """Full happy path: enqueue task → completion event → return."""
        items = [
            CharacterizationRequest(
                item_id="item-001",
                project_id="proj-1",
                title="Task A",
                description="Do A",
            ),
        ]

        # Simulate the dispatcher immediately signaling completion
        def mock_enqueue(characterization_id, item_id, task_context, project_id):
            from services.completion_events import create_event, signal as signal_event
            # Must register event before signaling (mirrors real _enqueue_characterization_task)
            create_event(characterization_id)
            # Simulate MCP tool: store completed result and signal event
            completed = make_completed_result("item-001")
            service._results["proj-1"]["item-001"] = completed
            signal_event(characterization_id)

        with patch.object(service, "_enqueue_characterization_task", side_effect=mock_enqueue):
            response = await service.characterize_items("proj-1", items)

        assert response.project_id == "proj-1"
        assert response.total == 1
        assert response.completed == 1

    @pytest.mark.asyncio
    async def test_no_compute_marks_failed(self, service):
        """When dispatcher raises (no compute), items marked as failed."""
        items = [
            CharacterizationRequest(
                item_id="item-001",
                project_id="proj-1",
                title="Task A",
                description="Do A",
            ),
        ]

        with patch.object(
            service,
            "_enqueue_characterization_task",
            side_effect=RuntimeError("WorkDispatcher not initialized"),
        ):
            response = await service.characterize_items("proj-1", items)

        assert response.failed == 1
        assert response.completed == 0

        # Item should be stored as failed
        result = await service.get_result("proj-1", "item-001")
        assert result.status == CharacterizationStatus.FAILED

    @pytest.mark.asyncio
    async def test_creates_pending_batch_first(self, service):
        """Should create pending entries before enqueuing to dispatcher."""
        items = [
            CharacterizationRequest(
                item_id="new-1",
                project_id="proj-1",
                title="Task",
                description="Desc",
            ),
        ]

        # Raise on enqueue to simulate dispatcher not available
        with patch.object(
            service,
            "_enqueue_characterization_task",
            side_effect=RuntimeError("dispatcher unavailable"),
        ):
            await service.characterize_items("proj-1", items)

        # Pending batch should have been created (even though enqueue failed)
        result = await service.get_result("proj-1", "new-1")
        assert result is not None


class TestBuildCharacterizationTaskContext:
    def test_includes_items(self, service):
        items = [
            CharacterizationRequest(
                item_id="item-001",
                project_id="proj-1",
                title="Add auth",
                description="Implement OAuth2",
                issue_type_hint="feature",
                area_hint="auth",
            ),
        ]
        from models.characterization import WorkTopology
        topology = WorkTopology(project_id="proj-1")

        context = service._build_characterization_task_context(
            characterization_id="char-123",
            project_id="proj-1",
            items=items,
            topology=topology,
        )

        assert "char-123" in context
        assert "proj-1" in context
        assert "item-001" in context
        assert "Add auth" in context
        assert "OAuth2" in context
        assert "type=feature" in context

    def test_includes_topology(self, service_with_data):
        items = [
            CharacterizationRequest(
                item_id="new-1",
                project_id="proj-1",
                title="New task",
                description="Desc",
            ),
        ]
        from models.characterization import WorkTopology, TopologyItem
        topology = WorkTopology(
            project_id="proj-1",
            items=[
                TopologyItem(
                    item_id="existing-1",
                    title="Existing task",
                    ontology_tags=make_ontology_tags(),
                    contextual_role=ContextualRole.FOUNDATIONAL,
                ),
            ],
        )

        context = service_with_data._build_characterization_task_context(
            characterization_id="char-456",
            project_id="proj-1",
            items=items,
            topology=topology,
        )

        assert "Existing Work Topology" in context
        assert "existing-1" in context
        assert "foundational" in context

    def test_includes_enum_values(self, service):
        items = [
            CharacterizationRequest(
                item_id="item-001",
                project_id="proj-1",
                title="Task",
                description="Desc",
            ),
        ]
        from models.characterization import WorkTopology
        topology = WorkTopology(project_id="proj-1")

        context = service._build_characterization_task_context(
            characterization_id="char-789",
            project_id="proj-1",
            items=items,
            topology=topology,
        )

        assert "feature" in context
        assert "bug_fix" in context
        assert "lifecycle_stage" in context
        assert "claudevn_submit_characterization" in context


class TestEnqueueCharacterizationTask:
    """Tests for the event-driven characterization task enqueuing."""

    def setup_method(self):
        """Reset module-level state."""
        from services import completion_events, work_dispatcher
        completion_events._events.clear()
        work_dispatcher._work_dispatcher = None

    def test_enqueue_registers_event_and_queues_task(self, service):
        """Enqueue should register a completion event and add task to dispatcher queue."""
        from services.work_dispatcher import WorkDispatcher, set_work_dispatcher

        dispatcher = WorkDispatcher()
        set_work_dispatcher(dispatcher)

        service._enqueue_characterization_task(
            characterization_id="char-123",
            item_id="item-001",
            task_context="Test context",
            project_id="proj-1",
        )

        from services.completion_events import get_event
        assert get_event("char-123") is not None
        assert len(dispatcher._char_queue) == 1
        assert dispatcher._char_queue[0].char_id == "char-123"

    def test_enqueue_raises_when_dispatcher_not_initialized(self, service):
        """Should raise RuntimeError if WorkDispatcher is not set."""
        with pytest.raises(RuntimeError):
            service._enqueue_characterization_task(
                characterization_id="char-123",
                item_id="item-001",
                task_context="Test",
                project_id="proj-1",
            )


class TestWaitForCharacterizationResult:
    """Tests for event-based wait (no polling)."""

    def setup_method(self):
        from services import completion_events
        completion_events._events.clear()

    @pytest.mark.asyncio
    async def test_immediate_completion_via_event(self, service):
        """If event is pre-set, wait completes immediately."""
        from services.completion_events import create_event, signal as signal_event

        create_event("char-123")
        signal_event("char-123")  # Pre-signal

        # Should complete instantly
        await service._wait_for_characterization_result(
            characterization_id="char-123",
            project_id="proj-1",
            item_ids=["item-001"],
        )

    @pytest.mark.asyncio
    async def test_timeout_marks_failed(self, service):
        """Items not completed by timeout should be marked as failed."""
        from services.completion_events import create_event

        # Store a pending item
        pending = make_completed_result(
            "item-001", status=CharacterizationStatus.IN_PROGRESS
        )
        service._results["proj-1"] = {"item-001": pending}

        # Register event but never signal it → timeout
        create_event("char-timeout")

        # Use very short timeout for test
        original_timeout = service.CHARACTERIZATION_TIMEOUT
        service.CHARACTERIZATION_TIMEOUT = 0.05
        try:
            await service._wait_for_characterization_result(
                characterization_id="char-timeout",
                project_id="proj-1",
                item_ids=["item-001"],
            )
        finally:
            service.CHARACTERIZATION_TIMEOUT = original_timeout

        result = await service.get_result("proj-1", "item-001")
        assert result.status == CharacterizationStatus.FAILED
        assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_no_event_registered_returns_gracefully(self, service):
        """If no event was registered (unusual), should not raise."""
        # char-no-event has no registered event
        await service._wait_for_characterization_result(
            characterization_id="char-no-event",
            project_id="proj-1",
            item_ids=["item-001"],
        )


class TestGetCharacterizerSkillInstructions:
    def test_dispatcher_returns_instructions(self):
        """_get_characterizer_skill_instructions moved to work_dispatcher module."""
        from services.work_dispatcher import _get_characterizer_skill_instructions
        instructions = _get_characterizer_skill_instructions()
        assert "Work Item Characterizer" in instructions
        assert "claudevn_submit_characterization" in instructions
        assert "Frame 1" in instructions
        assert "Frame 2" in instructions
