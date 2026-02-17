"""Unit tests for WorkDispatcher, WorkScheduler, and completion_events."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ===========================================================================
# completion_events tests
# ===========================================================================

class TestCompletionEvents:
    """Tests for the completion event registry."""

    def setup_method(self):
        """Clear event registry before each test."""
        from services import completion_events
        completion_events._events.clear()

    def test_create_event_registers_event(self):
        from services.completion_events import create_event, get_event
        event = create_event("task-1")
        assert event is not None
        assert get_event("task-1") is event

    def test_signal_sets_event(self):
        from services.completion_events import create_event, signal, get_event
        create_event("task-2")
        signal("task-2")
        event = get_event("task-2")
        assert event.is_set()

    def test_signal_unknown_task_is_noop(self):
        from services.completion_events import signal
        # Should not raise
        signal("nonexistent-task")

    def test_cleanup_removes_event(self):
        from services.completion_events import create_event, cleanup, get_event
        create_event("task-3")
        cleanup("task-3")
        assert get_event("task-3") is None

    def test_cleanup_nonexistent_is_noop(self):
        from services.completion_events import cleanup
        cleanup("nonexistent-task")  # Should not raise

    def test_active_count(self):
        from services.completion_events import create_event, cleanup, active_count
        assert active_count() == 0
        create_event("a")
        create_event("b")
        assert active_count() == 2
        cleanup("a")
        assert active_count() == 1

    @pytest.mark.asyncio
    async def test_wait_for_event_unblocks_on_signal(self):
        from services.completion_events import create_event, signal

        event = create_event("task-async")

        async def signal_after_delay():
            await asyncio.sleep(0.05)
            signal("task-async")

        asyncio.create_task(signal_after_delay())
        # Should complete without timeout
        await asyncio.wait_for(event.wait(), timeout=1.0)
        assert event.is_set()

    @pytest.mark.asyncio
    async def test_wait_for_event_times_out(self):
        from services.completion_events import create_event

        create_event("task-timeout")
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                asyncio.Event().wait(),  # Never signaled
                timeout=0.05
            )


# ===========================================================================
# WorkScheduler tests
# ===========================================================================

class TestWorkScheduler:
    """Tests for the multi-bucket priority scheduler."""

    def _make_decomp_task(self, decomp_id: str = "decomp-1"):
        from services.work_dispatcher import DecompositionTask
        return DecompositionTask(
            decomp_id=decomp_id,
            goal_id="goal-1",
            task_context="context",
            skill_instructions="instructions",
        )

    def _make_char_task(self, char_id: str = "char-1", item_id: str = "item-1"):
        from services.work_dispatcher import CharacterizationTask
        return CharacterizationTask(
            char_id=char_id,
            item_id=item_id,
            project_id="proj-1",
            task_context="context",
        )

    def test_empty_queues_returns_empty(self):
        from services.work_scheduler import WorkScheduler
        scheduler = WorkScheduler()
        result = scheduler.select_next([], [], idle_count=3)
        assert result.items == []

    def test_zero_idle_returns_empty(self):
        from services.work_scheduler import WorkScheduler
        scheduler = WorkScheduler()
        decomp = [self._make_decomp_task()]
        result = scheduler.select_next(decomp, [], idle_count=0)
        assert result.items == []

    def test_decomp_has_priority_over_char(self):
        from services.work_scheduler import WorkScheduler, BucketCategory
        scheduler = WorkScheduler()
        decomp = [self._make_decomp_task("d1")]
        char = [self._make_char_task("c1")]
        result = scheduler.select_next(decomp, char, idle_count=1)
        assert len(result.items) == 1
        assert result.items[0].decomp_id == "d1"
        assert result.bucket == BucketCategory.DECOMPOSITION

    def test_char_selected_when_no_decomp(self):
        from services.work_scheduler import WorkScheduler, BucketCategory
        scheduler = WorkScheduler()
        char = [self._make_char_task("c1")]
        result = scheduler.select_next([], char, idle_count=2)
        assert len(result.items) == 1
        assert result.items[0].char_id == "c1"
        assert result.bucket == BucketCategory.CHARACTERIZATION

    def test_fills_up_to_idle_count(self):
        from services.work_scheduler import WorkScheduler
        scheduler = WorkScheduler()
        char = [self._make_char_task(f"c{i}", f"item-{i}") for i in range(5)]
        result = scheduler.select_next([], char, idle_count=3)
        assert len(result.items) == 3

    def test_mixed_decomp_and_char_fills_slots(self):
        from services.work_scheduler import WorkScheduler
        scheduler = WorkScheduler()
        decomp = [self._make_decomp_task("d1")]
        char = [self._make_char_task("c1"), self._make_char_task("c2", "item-2")]
        # 2 idle computes: first takes decomp, second takes char
        result = scheduler.select_next(decomp, char, idle_count=2)
        assert len(result.items) == 2

    def test_skipped_buckets_listed(self):
        from services.work_scheduler import WorkScheduler, BucketCategory
        scheduler = WorkScheduler()
        # Only char tasks available → decomp bucket is skipped
        char = [self._make_char_task("c1")]
        result = scheduler.select_next([], char, idle_count=2)
        assert BucketCategory.DECOMPOSITION in result.skipped_buckets

    def test_describe_bucket_state(self):
        from services.work_scheduler import WorkScheduler
        scheduler = WorkScheduler()
        decomp = [self._make_decomp_task()]
        char = [self._make_char_task()]
        state = scheduler.describe_bucket_state(decomp, char, idle_count=2)
        assert state["idle_computes"] == 2
        assert state["decomp_pending"] == 1
        assert state["char_pending"] == 1


# ===========================================================================
# WorkDispatcher tests
# ===========================================================================

class TestWorkDispatcher:
    """Tests for the event-driven work dispatcher."""

    def setup_method(self):
        """Reset module-level state before each test."""
        from services import completion_events
        completion_events._events.clear()

        from services import work_dispatcher
        work_dispatcher._work_dispatcher = None

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        from services.work_dispatcher import WorkDispatcher
        dispatcher = WorkDispatcher()
        await dispatcher.start()
        assert dispatcher.is_running()
        await dispatcher.stop()
        assert not dispatcher.is_running()

    @pytest.mark.asyncio
    async def test_trigger_wakes_dispatch_loop(self):
        from services.work_dispatcher import WorkDispatcher

        cycles_run = []

        dispatcher = WorkDispatcher()

        original_cycle = dispatcher._run_dispatch_cycle

        async def mock_cycle():
            cycles_run.append(1)

        dispatcher._run_dispatch_cycle = mock_cycle
        await dispatcher.start()

        dispatcher.trigger(reason="test")
        await asyncio.sleep(0.1)  # Let loop process

        assert len(cycles_run) >= 1
        await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_enqueue_characterization_triggers_dispatch(self):
        from services.work_dispatcher import WorkDispatcher, CharacterizationTask

        dispatcher = WorkDispatcher()
        dispatch_called = []

        async def mock_cycle():
            dispatch_called.append(1)

        dispatcher._run_dispatch_cycle = mock_cycle
        await dispatcher.start()

        task = CharacterizationTask(
            char_id="char-test",
            item_id="item-test",
            project_id="proj-test",
            task_context="ctx",
        )
        dispatcher.enqueue_characterization(task)
        await asyncio.sleep(0.1)

        assert len(dispatch_called) >= 1
        await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_enqueue_decomposition_triggers_dispatch(self):
        from services.work_dispatcher import WorkDispatcher, DecompositionTask

        dispatcher = WorkDispatcher()
        dispatch_called = []

        async def mock_cycle():
            dispatch_called.append(1)

        dispatcher._run_dispatch_cycle = mock_cycle
        await dispatcher.start()

        task = DecompositionTask(
            decomp_id="decomp-test",
            goal_id="goal-test",
            task_context="ctx",
            skill_instructions="skills",
        )
        dispatcher.enqueue_decomposition(task)
        await asyncio.sleep(0.1)

        assert len(dispatch_called) >= 1
        await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_char_task_assigned_to_idle_compute(self):
        """End-to-end: enqueue char task → dispatcher assigns to idle compute."""
        from services.work_dispatcher import WorkDispatcher, CharacterizationTask
        from services.completion_events import create_event, signal

        # Mock SSE manager with one idle connection
        mock_connection = MagicMock()
        mock_connection.compute_id = "compute-1"

        mock_sse = MagicMock()
        mock_sse.find_matching_connection.return_value = mock_connection
        mock_sse.send_work_assigned = AsyncMock(return_value=True)

        assigned_tasks = []

        dispatcher = WorkDispatcher()

        async def mock_send_char(connection, task):
            assigned_tasks.append(task.char_id)

        dispatcher._send_char_work = mock_send_char

        with patch("services.work_dispatcher.get_work_dispatcher", return_value=dispatcher):
            with patch(
                "services.work_dispatcher.WorkDispatcher._trigger_execution_dispatch",
                new_callable=AsyncMock,
            ):
                with patch(
                    "services.sse_connection_manager.get_sse_connection_manager",
                    return_value=mock_sse,
                ):
                    await dispatcher.start()

                    char_id = "char-123"
                    create_event(char_id)
                    task = CharacterizationTask(
                        char_id=char_id,
                        item_id="item-1",
                        project_id="proj-1",
                        task_context="ctx",
                    )
                    dispatcher.enqueue_characterization(task)
                    await asyncio.sleep(0.15)

                    await dispatcher.stop()

        assert char_id in assigned_tasks

    def test_get_queue_depths(self):
        from services.work_dispatcher import WorkDispatcher, CharacterizationTask, DecompositionTask

        dispatcher = WorkDispatcher()

        t1 = CharacterizationTask(
            char_id="c1", item_id="i1", project_id="p1", task_context="ctx"
        )
        t2 = DecompositionTask(
            decomp_id="d1", goal_id="g1", task_context="ctx", skill_instructions=""
        )
        dispatcher._char_queue.append(t1)
        dispatcher._decomp_queue.append(t2)

        depths = dispatcher.get_queue_depths()
        assert depths["char_queue"] == 1
        assert depths["decomp_queue"] == 1

    def test_get_stats(self):
        from services.work_dispatcher import WorkDispatcher
        dispatcher = WorkDispatcher()
        stats = dispatcher.get_stats()
        assert "decomp_assigned" in stats
        assert "char_assigned" in stats
        assert "dispatch_cycles" in stats
        assert "running" in stats
        assert stats["running"] is False

    @pytest.mark.asyncio
    async def test_no_idle_compute_does_not_consume_queue(self):
        """If no idle compute is available, char tasks remain in queue."""
        from services.work_dispatcher import WorkDispatcher, CharacterizationTask
        from services.completion_events import create_event

        mock_sse = MagicMock()
        mock_sse.find_matching_connection.return_value = None  # No idle compute

        dispatcher = WorkDispatcher()

        with patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ):
            with patch(
                "services.work_dispatcher.WorkDispatcher._trigger_execution_dispatch",
                new_callable=AsyncMock,
            ):
                await dispatcher.start()

                char_id = "char-no-compute"
                create_event(char_id)
                task = CharacterizationTask(
                    char_id=char_id,
                    item_id="item-1",
                    project_id="proj-1",
                    task_context="ctx",
                )
                dispatcher.enqueue_characterization(task)
                await asyncio.sleep(0.1)

                # Task should remain in queue since no compute was available
                assert len(dispatcher._char_queue) == 1

                await dispatcher.stop()


# ===========================================================================
# ReconciliationManager tests
# ===========================================================================

class TestReconciliationManager:
    """Tests for the reconciliation manager."""

    def setup_method(self):
        from services import reconciliation_manager
        reconciliation_manager._reconciliation_manager = None

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        from services.reconciliation_manager import ReconciliationManager
        manager = ReconciliationManager(check_interval=60)
        await manager.start()
        assert manager.is_running()
        await manager.stop()
        assert not manager.is_running()

    @pytest.mark.asyncio
    async def test_get_stats_initial(self):
        from services.reconciliation_manager import ReconciliationManager
        manager = ReconciliationManager(check_interval=60)
        stats = manager.get_stats()
        assert stats["cycles"] == 0
        assert stats["stale_items_requeued"] == 0
        assert stats["orphaned_items_requeued"] == 0
        assert stats["running"] is False

    @pytest.mark.asyncio
    async def test_fire_dispatch_calls_dispatcher(self):
        from services.reconciliation_manager import ReconciliationManager

        mock_dispatcher = MagicMock()
        mock_dispatcher.trigger = MagicMock()

        manager = ReconciliationManager(check_interval=60)

        # Patch the import inside _fire_dispatch (inline import)
        with patch(
            "services.work_dispatcher.get_work_dispatcher",
            return_value=mock_dispatcher,
        ):
            manager._fire_dispatch()

        mock_dispatcher.trigger.assert_called_once_with(reason="reconciliation")

    @pytest.mark.asyncio
    async def test_fire_dispatch_handles_missing_dispatcher(self):
        from services.reconciliation_manager import ReconciliationManager

        manager = ReconciliationManager(check_interval=60)

        with patch(
            "services.work_dispatcher.get_work_dispatcher",
            side_effect=RuntimeError("not initialized"),
        ):
            # Should not raise
            manager._fire_dispatch()

    @pytest.mark.asyncio
    async def test_consistency_check_triggers_on_pending_work_and_idle_compute(self):
        """If PENDING work and idle computes exist, consistency check returns False."""
        from services.reconciliation_manager import ReconciliationManager

        manager = ReconciliationManager(check_interval=60)

        # Mock: 1 idle compute
        mock_connection = MagicMock()
        mock_connection.status = "idle"
        mock_sse = MagicMock()
        mock_sse.list_connections.return_value = [mock_connection]

        # Mock: 1 pending work item
        mock_work_item = MagicMock()
        mock_result = MagicMock()
        mock_result.items = [mock_work_item]
        mock_work_map = MagicMock()
        mock_work_map.list_work = AsyncMock(return_value=mock_result)

        with patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ):
            with patch(
                "services.work_map_service.get_work_map_service",
                return_value=mock_work_map,
            ):
                consistent = await manager._consistency_check()

        assert consistent is False  # Inconsistency detected

    @pytest.mark.asyncio
    async def test_consistency_check_ok_when_no_idle_computes(self):
        """No idle computes → nothing to do, returns True (consistent)."""
        from services.reconciliation_manager import ReconciliationManager

        manager = ReconciliationManager(check_interval=60)

        mock_sse = MagicMock()
        mock_sse.list_connections.return_value = []  # No idle computes

        with patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ):
            consistent = await manager._consistency_check()

        assert consistent is True

    @pytest.mark.asyncio
    async def test_check_idle_computes_detects_idle(self):
        """_check_idle_computes returns True when there are idle connections."""
        from services.reconciliation_manager import ReconciliationManager

        manager = ReconciliationManager(check_interval=60)

        mock_connection = MagicMock()
        mock_connection.status = "idle"
        mock_sse = MagicMock()
        mock_sse.list_connections.return_value = [mock_connection]

        with patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ):
            result = await manager._check_idle_computes()

        assert result is True

    @pytest.mark.asyncio
    async def test_check_idle_computes_no_idle(self):
        """_check_idle_computes returns False when no idle connections."""
        from services.reconciliation_manager import ReconciliationManager

        manager = ReconciliationManager(check_interval=60)

        mock_connection = MagicMock()
        mock_connection.status = "busy"
        mock_sse = MagicMock()
        mock_sse.list_connections.return_value = [mock_connection]

        with patch(
            "services.sse_connection_manager.get_sse_connection_manager",
            return_value=mock_sse,
        ):
            result = await manager._check_idle_computes()

        assert result is False
