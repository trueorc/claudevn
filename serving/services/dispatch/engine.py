"""Work Unit State Machine Engine.

The single mechanism that drives all work unit lifecycle transitions.
Every phase — dispatch, execution, merge, conflict resolution, verification
— is a state. Every action is a transition. Every failure is a state.

One evaluate() function. One pattern. One way things move forward.

**Critical design:**
- Engine owns BOTH work unit state AND compute state
- evaluate() takes an immutable snapshot — no external queries during evaluation
- State changes are atomic — both sides update together
- No polling, no querying SSE connections, no _busy_computes tracking

See docs/design/specifications/state-machine-engine.md
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from models.work_unit import WorkUnit, WorkUnitStatus
from services.events.event_bus import get_event_bus
from services.events.event_types import WorkUnitStateTransition

logger = logging.getLogger(__name__)

# Terminal states — evaluate() skips these
TERMINAL_STATES = {
    WorkUnitStatus.COMPLETED,
    WorkUnitStatus.FAILED,
    WorkUnitStatus.NEEDS_REVIEW,
    WorkUnitStatus.CANCELLED,
    WorkUnitStatus.SUPERSEDED,
}


@dataclass
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 0.0


@dataclass
class ComputeState:
    """Engine's view of a compute instance."""
    compute_id: str
    status: str = "offline"  # offline, idle, assigned, busy, merging
    assigned_unit_id: Optional[str] = None
    project_ids: List[str] = field(default_factory=list)


@dataclass
class Snapshot:
    """Immutable snapshot of system state for evaluation.

    Built once at the start of evaluate(). No external queries
    during evaluation — everything comes from this snapshot.
    """
    idle_compute_ids: List[str]
    completed_unit_ids: Set[str]
    paused: bool


@dataclass
class Transition:
    from_state: WorkUnitStatus
    to_state: WorkUnitStatus
    condition: Callable[['WorkUnit', Snapshot], bool]
    action: Callable[['WorkUnit', Snapshot, 'WorkUnitEngine'], Awaitable[None]]
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    description: str = ""


class WorkUnitEngine:
    """Unified state machine engine.

    Owns work unit state AND compute state. evaluate() uses an
    immutable snapshot so concurrent events can't cause inconsistency.
    """

    def __init__(self):
        self._units: Dict[str, WorkUnit] = {}
        self._computes: Dict[str, ComputeState] = {}
        self._transitions: List[Transition] = []
        self._evaluating = False
        self._eval_requested = False
        self._paused = False
        self._completed_ids: Set[str] = set()
        self._bus = get_event_bus()

    # -- Setup --

    def register_transitions(self, transitions: List[Transition]) -> None:
        self._transitions = transitions
        logger.info(f"Engine registered {len(transitions)} transitions")

    def track_unit(self, unit: WorkUnit) -> None:
        self._units[unit.id] = unit
        if unit.status in TERMINAL_STATES:
            self._completed_ids.add(unit.id)

    def track_units(self, units: List[WorkUnit]) -> None:
        for u in units:
            self.track_unit(u)

    def mark_completed(self, unit_id: str) -> None:
        self._completed_ids.add(unit_id)

    def pause(self) -> None:
        self._paused = True
        logger.info("Engine paused")

    def resume(self) -> None:
        self._paused = False
        logger.info("Engine resumed")
        asyncio.create_task(self.evaluate())

    @property
    def is_paused(self) -> bool:
        return self._paused

    # -- Compute state management --

    def set_compute_state(self, compute_id: str, status: str,
                          assigned_unit_id: str = None,
                          project_ids: List[str] = None) -> None:
        """Update engine's view of a compute. This is THE source of truth."""
        if compute_id not in self._computes:
            self._computes[compute_id] = ComputeState(compute_id=compute_id)

        cs = self._computes[compute_id]
        old_status = cs.status
        cs.status = status
        if assigned_unit_id is not None:
            cs.assigned_unit_id = assigned_unit_id
        if project_ids is not None:
            cs.project_ids = project_ids

        if old_status != status:
            logger.info(f"Compute {compute_id}: {old_status} → {status}")

    def get_compute_state(self, compute_id: str) -> Optional[ComputeState]:
        return self._computes.get(compute_id)

    def get_idle_compute_ids(self) -> List[str]:
        """Get compute IDs that are idle. Used only for snapshot building."""
        return [cs.compute_id for cs in self._computes.values()
                if cs.status == "idle"]

    # -- Events --

    async def on_event(self, event_type: str, **kwargs) -> None:
        """Handle an external event. Updates state, then evaluates."""
        self._handle_event_state(event_type, **kwargs)
        await self.evaluate()

    def _handle_event_state(self, event_type: str, **kwargs) -> None:
        """Update internal state based on an event. No async, no side effects."""
        if event_type == "compute_available":
            compute_id = kwargs.get("compute_id", "")
            if compute_id:
                self.set_compute_state(compute_id, "idle")

        elif event_type == "compute_offline":
            compute_id = kwargs.get("compute_id", "")
            if compute_id:
                self.set_compute_state(compute_id, "offline")

        elif event_type == "code_complete":
            unit_id = kwargs.get("unit_id", "")
            compute_id = kwargs.get("compute_id")
            # Unit state already set by caller. Release compute to idle.
            if compute_id:
                self.set_compute_state(compute_id, "idle", assigned_unit_id=None)

        elif event_type == "code_failed":
            unit_id = kwargs.get("unit_id", "")
            compute_id = kwargs.get("compute_id")
            if compute_id:
                self.set_compute_state(compute_id, "idle", assigned_unit_id=None)

        elif event_type == "rejected":
            compute_id = kwargs.get("compute_id")
            if compute_id:
                # Compute rejected because it's busy — keep it busy
                self.set_compute_state(compute_id, "busy")

    # -- Core evaluate --

    async def evaluate(self) -> None:
        """Evaluate all non-terminal units for state transitions.

        Takes an immutable snapshot at the start. No external queries.
        No concurrent modification. Atomic.
        """
        if self._evaluating:
            self._eval_requested = True
            return

        self._evaluating = True
        try:
            max_passes = 20

            for _ in range(max_passes):
                # Immutable snapshot — this is what we evaluate against
                snap = Snapshot(
                    idle_compute_ids=list(self.get_idle_compute_ids()),
                    completed_unit_ids=set(self._completed_ids),
                    paused=self._paused,
                )

                transitioned = False

                for unit_id, unit in list(self._units.items()):
                    if unit.status in TERMINAL_STATES:
                        continue

                    for t in self._transitions:
                        if t.from_state != unit.status:
                            continue
                        if not t.condition(unit, snap):
                            continue

                        # Execute transition
                        old_state = unit.status
                        try:
                            await t.action(unit, snap, self)
                            unit.status = t.to_state
                            await self._persist_and_emit(unit, old_state, t.to_state, t.description)

                            if t.to_state in TERMINAL_STATES:
                                self._completed_ids.add(unit_id)

                            transitioned = True

                        except StateRedirectError as e:
                            unit.status = e.target_state
                            await self._persist_and_emit(unit, old_state, e.target_state, str(e))
                            if e.target_state in TERMINAL_STATES:
                                self._completed_ids.add(unit_id)
                            transitioned = True

                        except Exception as e:
                            # Transition failed — mark unit as failed
                            unit.status = WorkUnitStatus.FAILED
                            await self._persist_and_emit(
                                unit, old_state, WorkUnitStatus.FAILED,
                                f"transition failed: {e}"
                            )
                            transitioned = True
                            logger.error(f"Engine: {unit_id} transition {old_state.value}→{t.to_state.value} failed: {e}")

                        break  # One transition per unit per pass

                    # Rebuild snapshot after each transition (state changed)
                    if transitioned:
                        break  # Restart the unit loop with fresh snapshot

                if not transitioned:
                    break

            # Process queued re-evaluation
            if self._eval_requested:
                self._eval_requested = False
                self._evaluating = False
                await self.evaluate()
                return

        finally:
            self._evaluating = False

    # -- Persistence + Events --

    async def _persist_and_emit(self, unit: WorkUnit, old_state, new_state, reason: str = "") -> None:
        """Single method: persist to Redis + emit event + log to activity + log to console.

        Every state change goes through here. No exceptions.
        """
        new_state_str = new_state.value if hasattr(new_state, 'value') else str(new_state)
        old_state_str = old_state.value if hasattr(old_state, 'value') else str(old_state)

        # Find assigned compute
        compute_id = None
        for cs in self._computes.values():
            if cs.assigned_unit_id == unit.id:
                compute_id = cs.compute_id
                break

        # 1. Persist to Redis
        try:
            await self._persist_unit_status(unit, new_state_str)
        except Exception as e:
            logger.error(f"CRITICAL: persist failed {unit.id} → {new_state_str}: {e}")

        # 2. Emit SSE event
        try:
            await self._bus.publish(WorkUnitStateTransition(
                project_id=unit.project_id,
                unit_id=unit.id,
                old_state=old_state_str,
                new_state=new_state_str,
                reason=reason,
                compute_id=compute_id,
            ))
        except Exception as e:
            logger.warning(f"Event emit failed for {unit.id}: {e}")

        # 3. Persist to activity log
        try:
            import json as _json
            from services.decomposition.storage import _get_redis
            redis = await _get_redis()
            event_record = _json.dumps({
                "event": "work_unit.state_transition",
                "project_id": unit.project_id,
                "unit_id": unit.id,
                "old_state": old_state_str,
                "new_state": new_state_str,
                "reason": reason,
                "compute_id": compute_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            log_key = f"claudevn:v2:activity_log:{unit.project_id}"
            await redis.lpush(log_key, event_record)
            await redis.ltrim(log_key, 0, 199)
        except Exception:
            pass

        # 4. Console log
        logger.info(f"State: {unit.id} {old_state_str} → {new_state_str} ({reason})")

    async def _persist_unit_status(self, unit: WorkUnit, new_status: str) -> None:
        """Write unit status to Redis."""
        try:
            import json
            from services.decomposition.storage import _get_redis
            redis = await _get_redis()
            project_id = unit.project_id
            goal_id = unit.goal_ref

            # Update per-goal key
            wu_key = f"claudevn:v2:work_units:{project_id}:{goal_id}"
            data = await redis.get(wu_key)
            if data:
                units = json.loads(data)
                for u in units:
                    if u.get("id") == unit.id:
                        u["status"] = new_status
                        if unit.assigned_instance:
                            u["assigned_instance"] = unit.assigned_instance
                        if unit.branch:
                            u["branch"] = unit.branch
                        break
                await redis.set(wu_key, json.dumps(units))

            # Update project index
            proj_key = f"claudevn:v2:project_units:{project_id}"
            data = await redis.get(proj_key)
            if data:
                units = json.loads(data)
                for u in units:
                    if u.get("id") == unit.id:
                        u["status"] = new_status
                        if unit.assigned_instance:
                            u["assigned_instance"] = unit.assigned_instance
                        if unit.branch:
                            u["branch"] = unit.branch
                        break
                await redis.set(proj_key, json.dumps(units))
        except Exception as e:
            logger.error(f"Redis persist failed for {unit.id}: {e}")

    # -- Helper for transition_to (used by external event handlers) --

    async def _transition_to(self, unit: WorkUnit, new_state: WorkUnitStatus, reason: str = "") -> None:
        """Direct state transition. Used by external event handlers (compute.py)."""
        old_state = unit.status
        unit.status = new_state
        await self._persist_and_emit(unit, old_state, new_state, reason)
        if new_state in TERMINAL_STATES:
            self._completed_ids.add(unit.id)


class PermanentError(Exception):
    pass


class TransientError(Exception):
    pass


class StateRedirectError(Exception):
    def __init__(self, message: str, target_state: WorkUnitStatus):
        super().__init__(message)
        self.target_state = target_state


# -- Singleton --

_engine: Optional[WorkUnitEngine] = None


def get_engine() -> Optional[WorkUnitEngine]:
    return _engine


def set_engine(engine: WorkUnitEngine) -> None:
    global _engine
    _engine = engine
