"""Compute provisioner interface and registry.

Defines the abstract ComputeProvisioner interface and the ProvisionerRegistry
that manages ordered providers for capability-driven compute provisioning.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, List

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Models ────────────────────────────────────────────────────────────────────


class ProvisioningRequest(BaseModel):
    """Request to provision a new compute instance."""
    required_tools: List[str] = Field(default_factory=list, description="Required tools (e.g., runtime:node:22)")
    required_labels: List[str] = Field(default_factory=list, description="Required routing labels")
    required_capabilities: List[str] = Field(default_factory=list, description="Required capabilities")
    project_id: str = Field(..., description="Project the work belongs to")
    triggered_by_work_id: str = Field(..., description="Work item that triggered provisioning")


class ProvisioningResult(BaseModel):
    """Result of a provisioning attempt."""
    success: bool = Field(..., description="Whether provisioning succeeded")
    instance_id: Optional[str] = Field(None, description="Provisioned instance ID (if success)")
    provider: str = Field(..., description="Provider that handled the request")
    estimated_ready_seconds: int = Field(default=0, description="Estimated seconds until compute is online")
    error: Optional[str] = Field(None, description="Error message (if failed)")


class ComputeImage(BaseModel):
    """A compute image available for provisioning."""
    image_id: str = Field(..., description="Unique image identifier")
    name: str = Field(..., description="Human-readable name")
    capabilities: List[str] = Field(default_factory=list, description="Capabilities included (runtimes, tools)")
    provider: str = Field(..., description="Provider that offers this image")


class ProviderInfo(BaseModel):
    """Information about a registered provisioner."""
    name: str = Field(..., description="Provider name")
    enabled: bool = Field(default=True, description="Whether provider is enabled")
    priority: int = Field(default=0, description="Priority (lower = tried first)")
    description: str = Field(default="", description="Human-readable description")


# ── Abstract interface ────────────────────────────────────────────────────────


class ComputeProvisioner(ABC):
    """Abstract interface for compute instance provisioning.

    Implementations handle the actual infrastructure for different environments
    (Docker, ECS, K8s, manual notification, etc.).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider name."""

    @property
    def description(self) -> str:
        """Human-readable description of this provider."""
        return ""

    @abstractmethod
    async def provision(self, request: ProvisioningRequest) -> ProvisioningResult:
        """Provision a new compute instance with the specified capabilities.

        Args:
            request: Provisioning requirements

        Returns:
            Result indicating success/failure and instance details
        """

    @abstractmethod
    async def deprovision(self, instance_id: str) -> bool:
        """Stop and remove a managed compute instance.

        Args:
            instance_id: Instance to deprovision

        Returns:
            True if deprovisioned successfully
        """

    @abstractmethod
    async def can_provision(self, request: ProvisioningRequest) -> bool:
        """Check if this provider can satisfy the given requirements.

        Args:
            request: Provisioning requirements

        Returns:
            True if this provider can handle the request
        """

    @abstractmethod
    async def list_available_images(self) -> List[ComputeImage]:
        """List compute images this provider can deploy.

        Returns:
            Available images with their capabilities
        """


# ── Registry ──────────────────────────────────────────────────────────────────


class ProvisionerRegistry:
    """Manages an ordered list of compute provisioners.

    Providers are tried in priority order (lowest first). The first provider
    that can satisfy a request gets the provision() call.
    """

    def __init__(self):
        self._providers: List[tuple[int, ComputeProvisioner]] = []  # (priority, provider)
        self._enabled: dict[str, bool] = {}

    def register(self, provider: ComputeProvisioner, priority: int = 100, enabled: bool = True) -> None:
        """Register a provisioner with a given priority.

        Args:
            provider: Provisioner to register
            priority: Lower = tried first (default: 100)
            enabled: Whether provider is initially enabled
        """
        self._providers.append((priority, provider))
        self._providers.sort(key=lambda x: x[0])
        self._enabled[provider.name] = enabled
        logger.info(f"Registered provisioner '{provider.name}' (priority={priority}, enabled={enabled})")

    def enable(self, name: str) -> bool:
        """Enable a provisioner by name."""
        if name in self._enabled:
            self._enabled[name] = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a provisioner by name."""
        if name in self._enabled:
            self._enabled[name] = False
            return True
        return False

    def list_providers(self) -> List[ProviderInfo]:
        """List all registered providers with their status."""
        return [
            ProviderInfo(
                name=provider.name,
                enabled=self._enabled.get(provider.name, True),
                priority=priority,
                description=provider.description,
            )
            for priority, provider in self._providers
        ]

    async def provision(self, request: ProvisioningRequest) -> ProvisioningResult:
        """Try each enabled provider in priority order until one succeeds.

        Args:
            request: Provisioning requirements

        Returns:
            Result from the first provider that can handle the request
        """
        for priority, provider in self._providers:
            if not self._enabled.get(provider.name, True):
                continue

            try:
                if await provider.can_provision(request):
                    logger.info(f"Provisioning via '{provider.name}' for work {request.triggered_by_work_id}")
                    result = await provider.provision(request)
                    return result
            except Exception as e:
                logger.error(f"Provider '{provider.name}' failed: {e}")
                continue

        return ProvisioningResult(
            success=False,
            provider="none",
            error="No provider could satisfy the requirements",
        )

    async def deprovision(self, instance_id: str, provider_name: str) -> bool:
        """Deprovision an instance using its provider.

        Args:
            instance_id: Instance to deprovision
            provider_name: Which provider manages this instance

        Returns:
            True if deprovisioned
        """
        for _, provider in self._providers:
            if provider.name == provider_name:
                return await provider.deprovision(instance_id)
        logger.warning(f"Provider '{provider_name}' not found for deprovisioning {instance_id}")
        return False

    async def list_all_images(self) -> List[ComputeImage]:
        """List available images from all enabled providers."""
        images = []
        for _, provider in self._providers:
            if not self._enabled.get(provider.name, True):
                continue
            try:
                provider_images = await provider.list_available_images()
                images.extend(provider_images)
            except Exception as e:
                logger.error(f"Failed to list images from '{provider.name}': {e}")
        return images


# ── Singleton ─────────────────────────────────────────────────────────────────

_registry: Optional[ProvisionerRegistry] = None


def get_provisioner_registry() -> ProvisionerRegistry:
    """Get the global provisioner registry."""
    global _registry
    if _registry is None:
        _registry = ProvisionerRegistry()
    return _registry
