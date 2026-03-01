"""Health monitoring service for compute instances and marketplaces."""

import asyncio
import logging
from typing import Optional
from datetime import datetime

from models.compute import InstanceStatus
from services.registry_service import ComputeRegistry
from services.marketplace_registry import MarketplaceRegistry

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Background service for monitoring compute and marketplace health.
    
    Periodically checks the last heartbeat of all registered components
    and updates their status accordingly.
    """
    
    def __init__(
        self,
        compute_registry: ComputeRegistry,
        marketplace_registry: Optional[MarketplaceRegistry] = None,
        check_interval: int = 30,
        degraded_threshold: int = 60,
        offline_threshold: int = 90,
        max_failed_checks: int = 3,
        auto_deregister: bool = False
    ):
        """Initialize health monitor.
        
        Args:
            compute_registry: Compute registry to monitor
            marketplace_registry: Marketplace registry to monitor (optional)
            check_interval: Seconds between health checks
            degraded_threshold: Seconds before marking degraded
            offline_threshold: Seconds before marking offline
            max_failed_checks: Failed checks before auto-deregister
            auto_deregister: Whether to auto-deregister failed instances
        """
        self.compute_registry = compute_registry
        self.marketplace_registry = marketplace_registry
        self.check_interval = check_interval
        self.degraded_threshold = degraded_threshold
        self.offline_threshold = offline_threshold
        self.max_failed_checks = max_failed_checks
        self.auto_deregister = auto_deregister
        
        self._task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(
            f"Initialized HealthMonitor "
            f"(check_interval={check_interval}s, "
            f"degraded={degraded_threshold}s, "
            f"offline={offline_threshold}s, "
            f"auto_deregister={auto_deregister})"
        )
    
    async def start(self):
        """Start the health monitoring loop."""
        if self._running:
            logger.warning("Health monitor already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info("Health monitor started")
    
    async def stop(self):
        """Stop the health monitoring loop."""
        if not self._running:
            return
        
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Health monitor stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop."""
        logger.info("Health monitoring loop started")
        
        while self._running:
            try:
                await self._check_health()
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                logger.info("Health monitoring loop cancelled")
                break
                
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}", exc_info=True)
                # Continue running despite errors
                await asyncio.sleep(self.check_interval)
    
    async def _check_drain_completion(self):
        """Check draining instances and transition them when in-flight work is done."""
        try:
            from services.work_map_service import get_work_map_service
            from models.work_map import WorkStatus
            work_map = get_work_map_service()
            work_response = await work_map.list_work()
        except RuntimeError:
            # Work map service not available; skip drain completion checks
            return
        except Exception as e:
            logger.error(f"Error fetching work map for drain completion check: {e}", exc_info=True)
            return

        draining_instances = [
            instance for instance in self.compute_registry._instances.values()
            if instance.status == InstanceStatus.DRAINING
        ]

        for instance in draining_instances:
            instance_id = instance.instance_id
            in_flight = [
                w for w in work_response.items
                if w.assigned_to == instance_id
                and w.status in [WorkStatus.ASSIGNED, WorkStatus.IN_PROGRESS, WorkStatus.BLOCKED]
            ]

            if in_flight:
                continue

            auto_deregister = instance.metadata.get("auto_deregister_on_drain", False)

            if auto_deregister:
                logger.info(
                    f"Drain complete for {instance_id} (health monitor), auto-deregistering"
                )
                await self.compute_registry.remove_instance(instance_id)
            else:
                logger.info(
                    f"Drain complete for {instance_id} (health monitor), transitioning to OFFLINE"
                )
                instance.status = InstanceStatus.OFFLINE
                instance.drain_started_at = None
                instance.metadata.pop("auto_deregister_on_drain", None)
                await self.compute_registry._save_to_storage(instance)

    async def _check_health(self):
        """Check health of all components."""
        try:
            # Check draining instances for completion
            await self._check_drain_completion()

            # Check compute instances
            compute_changes = await self.compute_registry.check_health(
                max_heartbeat_age=self.offline_threshold,
                degraded_threshold=self.degraded_threshold
            )
            
            # Log compute status changes
            if compute_changes.get("status_changes"):
                logger.info(
                    f"Compute health check: {len(compute_changes['status_changes'])} status changes"
                )
                
                for change in compute_changes["status_changes"]:
                    logger.info(
                        f"  Compute {change['instance_id']}: "
                        f"{change['old_status']} -> {change['new_status']} "
                        f"(heartbeat age: {change['heartbeat_age']:.0f}s)"
                    )
            
            # Check auth token expiry
            expired_ids = await self.compute_registry.check_auth_expiry()
            if expired_ids:
                logger.warning(f"Auth expired for {len(expired_ids)} instance(s): {expired_ids}")

            # Check marketplaces if registry exists
            if self.marketplace_registry:
                marketplace_changes = await self.marketplace_registry.check_health(
                    degraded_threshold=self.degraded_threshold,
                    offline_threshold=self.offline_threshold,
                    max_failed_checks=self.max_failed_checks
                )
                
                # Log marketplace status changes
                if marketplace_changes:
                    total_changes = (
                        marketplace_changes.get("degraded", 0) + 
                        marketplace_changes.get("offline", 0) +
                        marketplace_changes.get("deregistered", 0)
                    )
                    
                    if total_changes > 0:
                        logger.info(
                            f"Marketplace health check: {total_changes} changes "
                            f"(degraded={marketplace_changes.get('degraded', 0)}, "
                            f"offline={marketplace_changes.get('offline', 0)}, "
                            f"deregistered={marketplace_changes.get('deregistered', 0)})"
                        )
            
        except Exception as e:
            logger.error(f"Error checking health: {e}", exc_info=True)
    
    async def _auto_deregister_failed(self):
        """Automatically deregister instances with too many failed checks."""
        # Note: Auto-deregistration is now handled by the registries themselves
        # during check_health() calls. This method is kept for backward compatibility
        # but is no longer used.
        pass
    
    def is_running(self) -> bool:
        """Check if monitor is running.
        
        Returns:
            True if running
        """
        return self._running
    
    async def force_check(self):
        """Force an immediate health check.
        
        Returns:
            Health check results
        """
        logger.info("Forcing immediate health check")
        await self._check_health()
        return {"status": "check_completed"}


# Global health monitor instance
_health_monitor: Optional[HealthMonitor] = None


def get_health_monitor() -> Optional[HealthMonitor]:
    """Get the global health monitor instance.
    
    Returns:
        HealthMonitor instance or None if not initialized
    """
    return _health_monitor


def set_health_monitor(monitor: HealthMonitor):
    """Set the global health monitor instance.
    
    Args:
        monitor: HealthMonitor instance
    """
    global _health_monitor
    _health_monitor = monitor


async def start_health_monitoring(
    compute_registry: ComputeRegistry,
    marketplace_registry: Optional[MarketplaceRegistry] = None,
    check_interval: int = 30,
    degraded_threshold: int = 60,
    offline_threshold: int = 90,
    max_failed_checks: int = 3,
    auto_deregister: bool = False
):
    """Start the global health monitor.
    
    Args:
        compute_registry: Compute registry to monitor
        marketplace_registry: Marketplace registry to monitor (optional)
        check_interval: Seconds between health checks
        degraded_threshold: Seconds before marking degraded
        offline_threshold: Seconds before marking offline
        max_failed_checks: Failed checks before auto-deregister
        auto_deregister: Whether to auto-deregister failed instances
    """
    global _health_monitor
    
    if _health_monitor and _health_monitor.is_running():
        logger.warning("Health monitor already running")
        return
    
    _health_monitor = HealthMonitor(
        compute_registry=compute_registry,
        marketplace_registry=marketplace_registry,
        check_interval=check_interval,
        degraded_threshold=degraded_threshold,
        offline_threshold=offline_threshold,
        max_failed_checks=max_failed_checks,
        auto_deregister=auto_deregister
    )
    
    await _health_monitor.start()


async def stop_health_monitoring():
    """Stop the global health monitor."""
    global _health_monitor
    
    if _health_monitor:
        await _health_monitor.stop()

