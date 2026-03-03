"""Auto-drain lifecycle management for managed compute instances.

Periodically scans managed compute instances, and drains + deprovisions
those that have been idle (no active/matching work) past the grace period.
Unmanaged (BYOC) instances are never touched.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from config import AutoDrainConfig
from models.compute import InstanceStatus, LifecycleMode
from models.work_map import WorkStatus, BlockerType

logger = logging.getLogger(__name__)


class ComputeLifecycleService:
    """Manages auto-drain for idle managed compute instances."""

    def __init__(self, config: AutoDrainConfig):
        self._config = config
        self._running = False
        self._task: Optional[asyncio.Task] = None
        # Track when each managed instance first became idle (no matching work)
        self._idle_since: Dict[str, datetime] = {}

    async def start(self) -> None:
        """Start the auto-drain monitoring loop."""
        if not self._config.enabled:
            logger.info("Auto-drain disabled via config")
            return
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(
            f"Auto-drain started (interval={self._config.check_interval_seconds}s, "
            f"grace={self._config.idle_grace_period_minutes}min)"
        )

    async def stop(self) -> None:
        """Stop the monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Auto-drain stopped")

    async def _monitor_loop(self) -> None:
        """Periodic loop that checks for idle managed instances."""
        while self._running:
            try:
                await asyncio.sleep(self._config.check_interval_seconds)
                await self._check_idle_instances()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Auto-drain check failed: {e}")

    async def _check_idle_instances(self) -> None:
        """Scan managed instances and drain those idle past grace period."""
        from services.registry_service import get_compute_registry
        from services.work_map_service import get_work_map_service

        registry = get_compute_registry()
        work_service = get_work_map_service()

        instances = await registry.list_instances()
        now = datetime.now(timezone.utc)
        grace_seconds = self._config.idle_grace_period_minutes * 60

        # Get all active and pending work
        all_work = await work_service.list_work()
        active_statuses = {WorkStatus.PENDING, WorkStatus.ASSIGNED, WorkStatus.IN_PROGRESS, WorkStatus.BLOCKED}

        for instance in instances:
            # Only manage lifecycle of managed instances
            if instance.lifecycle_mode != LifecycleMode.MANAGED:
                continue

            # Skip instances already draining or offline
            if instance.status in (InstanceStatus.DRAINING, InstanceStatus.OFFLINE):
                continue

            # Check if instance has active work assigned to it
            has_active_work = any(
                w.status in {WorkStatus.ASSIGNED, WorkStatus.IN_PROGRESS}
                and w.assigned_to == instance.instance_id
                for w in all_work
            )

            if has_active_work:
                # Instance is busy — reset idle tracking
                self._idle_since.pop(instance.instance_id, None)
                continue

            # Check if any pending/blocked work matches this instance's capabilities
            has_matching_pending = self._has_matching_work(instance, all_work, active_statuses)

            if has_matching_pending:
                # There's work this instance could pick up — reset idle tracking
                self._idle_since.pop(instance.instance_id, None)
                continue

            # Instance is idle with no matching work
            if instance.instance_id not in self._idle_since:
                self._idle_since[instance.instance_id] = now
                logger.debug(f"Managed instance {instance.instance_id} became idle")
                continue

            idle_duration = (now - self._idle_since[instance.instance_id]).total_seconds()
            if idle_duration >= grace_seconds:
                logger.info(
                    f"Auto-draining managed instance {instance.instance_id} "
                    f"(idle for {idle_duration:.0f}s, grace={grace_seconds}s)"
                )
                await self._drain_and_deprovision(instance.instance_id)
                self._idle_since.pop(instance.instance_id, None)

        # Clean up tracking for instances that no longer exist
        known_ids = {i.instance_id for i in instances}
        stale = [iid for iid in self._idle_since if iid not in known_ids]
        for iid in stale:
            self._idle_since.pop(iid)

    def _has_matching_work(self, instance, all_work, active_statuses) -> bool:
        """Check if any pending/blocked work matches instance capabilities."""
        caps = instance.capabilities if instance.capabilities else None
        instance_tools = set(caps.tools_available if caps else [])
        instance_labels = set(caps.labels if caps else [])

        for w in all_work:
            if w.status not in active_statuses:
                continue
            # Skip work already assigned to someone else
            if w.assigned_to and w.assigned_to != instance.instance_id:
                continue

            # Check capability_missing blocked work specifically
            if w.status == WorkStatus.BLOCKED:
                has_cap_blocker = any(
                    b.blocker_type == BlockerType.CAPABILITY_MISSING
                    for b in (w.blockers or [])
                    if not b.resolved
                )
                if not has_cap_blocker:
                    continue

            # Check if requirements match
            required_tools = set(w.required_tools or [])
            required_labels = set(w.required_labels or [])

            tools_match = not required_tools or required_tools.issubset(instance_tools)
            labels_match = not required_labels or required_labels.issubset(instance_labels)

            if tools_match and labels_match:
                return True

        return False

    async def _drain_and_deprovision(self, instance_id: str) -> None:
        """Initiate drain, then deprovision once complete."""
        from services.registry_service import get_compute_registry
        from services.compute_provisioner import get_provisioner_registry

        registry = get_compute_registry()

        try:
            await registry.drain_instance(instance_id, auto_deregister=True)
        except Exception as e:
            logger.error(f"Failed to drain {instance_id}: {e}")
            return

        # Deprovision via the provisioner registry
        try:
            prov_registry = get_provisioner_registry()
            # Use the "docker" provider for managed instances
            await prov_registry.deprovision(instance_id, provider_name="docker")
        except Exception as e:
            logger.error(f"Failed to deprovision {instance_id}: {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────

_service: Optional[ComputeLifecycleService] = None


def get_lifecycle_service() -> ComputeLifecycleService:
    """Get the global lifecycle service."""
    global _service
    if _service is None:
        from config import get_config
        _service = ComputeLifecycleService(get_config().auto_drain)
    return _service
