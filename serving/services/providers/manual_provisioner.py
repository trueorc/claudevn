"""Manual provisioner — notification-based fallback provider.

Always available. Does not start anything; instead, it emits a notification
to the frontend so the user can manually provision the needed compute.
"""

import logging
from typing import List

from models.notification import NotificationLevel, NotificationCategory
from services.compute_provisioner import (
    ComputeProvisioner,
    ProvisioningRequest,
    ProvisioningResult,
    ComputeImage,
)

logger = logging.getLogger(__name__)


class ManualProvisioner(ComputeProvisioner):
    """Fallback provisioner that notifies the user to provision manually.

    Always returns can_provision=True so it acts as a catch-all.
    """

    @property
    def name(self) -> str:
        return "manual"

    @property
    def description(self) -> str:
        return "Notifies the user to manually start a compute instance with the required capabilities"

    async def provision(self, request: ProvisioningRequest) -> ProvisioningResult:
        """Emit a notification with the required capabilities.

        Does NOT start any compute — the user handles provisioning.
        """
        # Build human-readable requirements summary
        requirements = []
        if request.required_tools:
            requirements.append(f"tools: {', '.join(request.required_tools)}")
        if request.required_labels:
            requirements.append(f"labels: {', '.join(request.required_labels)}")
        if request.required_capabilities:
            requirements.append(f"capabilities: {', '.join(request.required_capabilities)}")

        req_summary = "; ".join(requirements) if requirements else "general compute"

        message = (
            f"Work item {request.triggered_by_work_id} requires compute with {req_summary}. "
            f"Start a compute instance with the needed capabilities and register it."
        )

        # Emit frontend notification
        try:
            from services.notification_service import get_notification_service
            svc = get_notification_service()
            svc.emit(
                title="Compute needed",
                message=message,
                level=NotificationLevel.WARNING,
                category=NotificationCategory.COMPUTE,
                project_id=request.project_id,
                entity_id=request.triggered_by_work_id,
            )
        except Exception as e:
            logger.debug(f"Could not emit notification: {e}")

        # Emit SSE event to all connected frontends
        try:
            from services.sse_connection_manager import get_sse_connection_manager
            sse = get_sse_connection_manager()
            await sse.broadcast_event("compute_needed", {
                "work_id": request.triggered_by_work_id,
                "project_id": request.project_id,
                "required_tools": request.required_tools,
                "required_labels": request.required_labels,
                "required_capabilities": request.required_capabilities,
                "message": message,
            })
        except Exception as e:
            logger.debug(f"Could not broadcast SSE event: {e}")

        logger.info(f"Manual provisioner: notified user for work {request.triggered_by_work_id}")

        return ProvisioningResult(
            success=True,
            instance_id=None,
            provider=self.name,
            estimated_ready_seconds=-1,  # Unknown — user-driven
        )

    async def deprovision(self, instance_id: str) -> bool:
        """Manual provisioner does not manage lifecycle — no-op."""
        logger.info(f"Manual provisioner: deprovision requested for {instance_id} (no-op)")
        return False

    async def can_provision(self, request: ProvisioningRequest) -> bool:
        """Always returns True — this is the fallback provider."""
        return True

    async def list_available_images(self) -> List[ComputeImage]:
        """Manual provisioner has no pre-built images."""
        return []
