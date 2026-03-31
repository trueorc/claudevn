"""Work Unit State Machine Engine.

The single mechanism that drives all work unit lifecycle transitions.
Every phase — dispatch, execution, merge, conflict resolution, verification
— is a state. Every action is a transition. Every failure is handled
as error metadata on the current state.

One evaluate() function. One pattern. One way things move forward.

See docs/design/specifications/state-machine-engine.md for the full spec.
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
    """Retry configuration for a transition."""
    max_attempts: int = 3
    backoff_seconds: float = 5.0


@dataclass
class TransitionError:
    """Error metadata tracked on a work unit."""
    message: str = ""
    code: str = ""  # "transient", "permanent", "timeout"
    transition: str = ""  # "queued→executing", etc.
    attempt: int = 0
    max_attempts: int = 3
    first_at: Optional[datetime] = None
    last_at: Optional[datetime] = None
    backoff_until: Optional[datetime] = None

    def should_retry(self) -> bool:
        """Can this error be retried?"""
        if self.code == "permanent":
            return False
        if self.attempt >= self.max_attempts:
            return False
        if self.backoff_until and datetime.now(timezone.utc) < self.backoff_until:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "message": self.message,
            "code": self.code,
            "transition": self.transition,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
        }


@dataclass
class EvaluationContext:
    """Snapshot of system state for condition checking."""
    idle_computes: List[str] = field(default_factory=list)
    busy_computes: Set[str] = field(default_factory=set)
    merging_project_ids: Set[str] = field(default_factory=set)
    completed_unit_ids: Set[str] = field(default_factory=set)
    paused: bool = False


@dataclass
class Transition:
    """A single valid state transition."""
    from_state: WorkUnitStatus
    to_state: WorkUnitStatus
    condition: Callable[['WorkUnit', EvaluationContext], bool]
    action: Callable[['WorkUnit', EvaluationContext, 'WorkUnitEngine'], Awaitable[None]]
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    description: str = ""


class WorkUnitEngine:
    """Unified state machine engine for work unit lifecycle.

    evaluate() is the ONLY function that advances state.
    External events call on_event() which identifies affected
    units and triggers evaluation.
    """

    def __init__(self):
        self._units: Dict[str, WorkUnit] = {}  # unit_id → WorkUnit
        self._errors: Dict[str, TransitionError] = {}  # unit_id → error
        self._transitions: List[Transition] = []
        self._evaluating = False
        self._pending_eval: Set[str] = set()
        self._paused = False

        # Merge coordination: one merge at a time per project
        self._merging_project_ids: Set[str] = set()

        # Compute tracking
        self._busy_computes: Set[str] = set()
        self._unit_compute: Dict[str, str] = {}  # unit_id → compute_id

        # Completed tracking for dependency resolution
        self._completed_ids: Set[str] = set()

        self._bus = get_event_bus()

    def register_transitions(self, transitions: List[Transition]) -> None:
        """Set the transition table. Called once at startup."""
        self._transitions = transitions
        logger.info(f"Engine registered {len(transitions)} transitions")

    def track_unit(self, unit: WorkUnit) -> None:
        """Add a unit to the engine's tracking."""
        self._units[unit.id] = unit
        if unit.status in TERMINAL_STATES:
            self._completed_ids.add(unit.id)

    def track_units(self, units: List[WorkUnit]) -> None:
        """Add multiple units to tracking."""
        for u in units:
            self.track_unit(u)

    def mark_completed(self, unit_id: str) -> None:
        """Mark a unit as completed for dependency tracking."""
        self._completed_ids.add(unit_id)

    def pause(self) -> None:
        self._paused = True
        logger.info("Engine paused")

    def resume(self) -> None:
        self._paused = False
        logger.info("Engine resumed")
        asyncio.create_task(self.evaluate(set(self._units.keys())))

    @property
    def is_paused(self) -> bool:
        return self._paused

    async def on_event(self, event_type: str, **kwargs) -> None:
        """Handle an external event. Identifies affected units and evaluates.

        This is the single entry point for all external state changes.
        """
        affected = self._get_affected_units(event_type, **kwargs)
        if affected:
            await self.evaluate(affected)

    async def evaluate(self, unit_ids: Optional[Set[str]] = None) -> None:
        """Evaluate units for possible state transitions.

        The core of the engine. For each affected unit, checks all
        transitions from its current state. If conditions are met,
        executes the transition action and advances state.

        One transition per unit per evaluate pass. Re-evaluates
        if any transition fired (cascading).
        """
        if self._evaluating:
            # Queue for re-evaluation after current pass
            if unit_ids:
                self._pending_eval.update(unit_ids)
            return

        self._evaluating = True
        try:
            ids_to_check = unit_ids or set(self._units.keys())
            max_passes = 20  # Safety limit

            for _ in range(max_passes):
                transitioned_any = False

                # Build context snapshot once per pass
                ctx = self._build_context()

                for unit_id in list(ids_to_check):
                    unit = self._units.get(unit_id)
                    if not unit or unit.status in TERMINAL_STATES:
                        continue

                    # Find applicable transitions for this unit's state
                    for t in self._transitions:
                        if t.from_state != unit.status:
                            continue

                        # Check error/retry state
                        error = self._errors.get(unit_id)
                        if error and not error.should_retry():
                            # Retries exhausted — fail
                            await self._transition_to(unit, WorkUnitStatus.FAILED,
                                                      reason=f"Retries exhausted: {error.message}")
                            transitioned_any = True
                            break

                        # Check condition
                        if not t.condition(unit, ctx):
                            continue

                        # Execute transition
                        old_state = unit.status
                        try:
                            await t.action(unit, ctx, self)
                            unit.status = t.to_state
                            self._errors.pop(unit_id, None)

                            await self._emit_transition(unit, old_state, t.to_state, t.description)

                            if t.to_state in TERMINAL_STATES:
                                self._completed_ids.add(unit_id)

                            transitioned_any = True
                            logger.info(f"Engine: {unit_id} {old_state.value} → {t.to_state.value}")

                        except StateRedirectError as e:
                            # Action redirects to a different state than the transition target
                            # Example: merge action detects conflict → redirect to MERGE_CONFLICT
                            unit.status = e.target_state
                            self._errors.pop(unit_id, None)
                            await self._emit_transition(unit, old_state, e.target_state, str(e))
                            transitioned_any = True
                            logger.info(
                                f"Engine: {unit_id} {old_state.value} → {e.target_state.value} "
                                f"(redirect: {e})"
                            )

                        except Exception as e:
                            self._record_error(unit_id, t, e)
                            logger.warning(
                                f"Engine: {unit_id} transition {old_state.value}→{t.to_state.value} "
                                f"failed: {e}"
                            )

                        break  # One transition attempt per unit per pass

                if not transitioned_any:
                    break  # No more progress possible

                # Widen check to include dependents of transitioned units
                ids_to_check = set(self._units.keys())

            # Process any evaluations queued during this pass
            if self._pending_eval:
                pending = self._pending_eval.copy()
                self._pending_eval.clear()
                self._evaluating = False
                await self.evaluate(pending)
                return

        finally:
            self._evaluating = False

    def _build_context(self) -> EvaluationContext:
        """Build a snapshot of current system state for condition checking."""
        idle = []
        try:
            from services.sse_connection_manager import get_sse_connection_manager
            sse = get_sse_connection_manager()
            if sse:
                idle = [c.compute_id for c in sse.get_idle_connections()
                        if c.compute_id not in self._busy_computes]
        except Exception:
            pass

        return EvaluationContext(
            idle_computes=idle,
            busy_computes=set(self._busy_computes),
            merging_project_ids=set(self._merging_project_ids),
            completed_unit_ids=set(self._completed_ids),
            paused=self._paused,
        )

    def _get_affected_units(self, event_type: str, **kwargs) -> Set[str]:
        """Map an external event to the set of unit IDs that need re-evaluation."""
        affected = set()

        if event_type == "code_complete":
            unit_id = kwargs.get("unit_id", "")
            if unit_id:
                affected.add(unit_id)
                # Also evaluate dependents
                for uid, u in self._units.items():
                    if unit_id in (u.independence.depends_on or []):
                        affected.add(uid)

        elif event_type == "code_failed":
            unit_id = kwargs.get("unit_id", "")
            if unit_id:
                affected.add(unit_id)

        elif event_type == "merge_complete":
            unit_id = kwargs.get("unit_id", "")
            if unit_id:
                affected.add(unit_id)
                # Dependents may now be unblocked
                for uid, u in self._units.items():
                    if unit_id in (u.independence.depends_on or []):
                        affected.add(uid)

        elif event_type == "merge_conflict":
            unit_id = kwargs.get("unit_id", "")
            if unit_id:
                affected.add(unit_id)

        elif event_type == "conflict_resolved":
            unit_id = kwargs.get("unit_id", "")
            if unit_id:
                affected.add(unit_id)

        elif event_type == "compute_available":
            # Any unit waiting for compute
            for uid, u in self._units.items():
                if u.status in (WorkUnitStatus.QUEUED, WorkUnitStatus.WAITING_COMPUTE):
                    affected.add(uid)

        elif event_type == "approved":
            # All units in the approved goal
            goal_id = kwargs.get("goal_id", "")
            for uid, u in self._units.items():
                if u.goal_ref == goal_id:
                    affected.add(uid)

        elif event_type == "rejected":
            unit_id = kwargs.get("unit_id", "")
            if unit_id:
                affected.add(unit_id)

        else:
            # Unknown event — evaluate everything
            affected = set(self._units.keys())

        return affected

    def _record_error(self, unit_id: str, transition: Transition, error: Exception) -> None:
        """Record an error on a unit for retry tracking."""
        now = datetime.now(timezone.utc)
        existing = self._errors.get(unit_id)
        is_transient = not isinstance(error, PermanentError)

        if existing and existing.transition == f"{transition.from_state.value}→{transition.to_state.value}":
            existing.attempt += 1
            existing.last_at = now
            existing.message = str(error)
            if is_transient:
                from datetime import timedelta
                existing.backoff_until = now + timedelta(seconds=transition.retry_policy.backoff_seconds)
        else:
            self._errors[unit_id] = TransitionError(
                message=str(error),
                code="transient" if is_transient else "permanent",
                transition=f"{transition.from_state.value}→{transition.to_state.value}",
                attempt=1,
                max_attempts=transition.retry_policy.max_attempts,
                first_at=now,
                last_at=now,
            )

    async def _transition_to(self, unit: WorkUnit, new_state: WorkUnitStatus, reason: str = "") -> None:
        """Direct state transition (for terminal states like failed)."""
        old_state = unit.status
        unit.status = new_state
        await self._emit_transition(unit, old_state, new_state, reason)
        if new_state in TERMINAL_STATES:
            self._completed_ids.add(unit.id)

    async def _emit_transition(self, unit: WorkUnit, old_state, new_state, reason: str = "") -> None:
        """Emit the canonical state transition event."""
        error_dict = None
        err = self._errors.get(unit.id)
        if err:
            error_dict = err.to_dict()

        try:
            await self._bus.publish(WorkUnitStateTransition(
                project_id=unit.project_id,
                unit_id=unit.id,
                old_state=old_state.value if hasattr(old_state, 'value') else str(old_state),
                new_state=new_state.value if hasattr(new_state, 'value') else str(new_state),
                reason=reason,
                error=error_dict,
                compute_id=self._unit_compute.get(unit.id),
            ))
        except Exception as e:
            logger.debug(f"Failed to emit state transition event: {e}")

    # -- Helpers for transition actions --

    def assign_compute(self, unit_id: str, compute_id: str) -> None:
        """Track a compute assignment."""
        self._busy_computes.add(compute_id)
        self._unit_compute[unit_id] = compute_id

    def release_compute(self, unit_id: str) -> None:
        """Release a compute assignment."""
        compute_id = self._unit_compute.pop(unit_id, None)
        if compute_id:
            self._busy_computes.discard(compute_id)

    def start_merge(self, project_id: str) -> None:
        """Mark a project as having a merge in progress."""
        self._merging_project_ids.add(project_id)

    def end_merge(self, project_id: str) -> None:
        """Mark a project's merge as complete."""
        self._merging_project_ids.discard(project_id)


class PermanentError(Exception):
    """An error that should not be retried."""
    pass


class TransientError(Exception):
    """An error that can be retried."""
    pass


class StateRedirectError(Exception):
    """Raised by an action to redirect to a different state than the transition target.

    Example: merge action detects conflict → raises StateRedirectError(MERGE_CONFLICT)
    instead of completing the SUBMITTED→MERGING transition normally.
    """
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
