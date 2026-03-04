"""Unit tests for ComputeProvisioner interface and ProvisionerRegistry."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.compute_provisioner import (
    ComputeProvisioner,
    ProvisionerRegistry,
    ProvisioningRequest,
    ProvisioningResult,
    ComputeImage,
)


# ── Test provisioner implementations ─────────────────────────────────────────

class FakeProvisioner(ComputeProvisioner):
    """Fake provisioner for testing."""

    def __init__(self, provider_name="fake", can=True, success=True):
        self._name = provider_name
        self._can = can
        self._success = success
        self.provision_calls = []
        self.deprovision_calls = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Fake provisioner ({self._name})"

    async def provision(self, request):
        self.provision_calls.append(request)
        return ProvisioningResult(
            success=self._success,
            instance_id=f"{self._name}-001" if self._success else None,
            provider=self._name,
            estimated_ready_seconds=10,
            error=None if self._success else "provision failed",
        )

    async def deprovision(self, instance_id):
        self.deprovision_calls.append(instance_id)
        return True

    async def can_provision(self, request):
        return self._can

    async def list_available_images(self):
        return [ComputeImage(
            image_id=f"{self._name}-image",
            name=f"{self._name} Image",
            capabilities=["runtime:python:3.12"],
            provider=self._name,
        )]


@pytest.fixture
def request_data():
    return ProvisioningRequest(
        required_tools=["runtime:node:22"],
        required_labels=[],
        required_capabilities=[],
        project_id="proj-001",
        triggered_by_work_id="work-001",
    )


# ── ProvisioningRequest model ────────────────────────────────────────────────

class TestProvisioningRequest:
    def test_create_request(self, request_data):
        assert request_data.required_tools == ["runtime:node:22"]
        assert request_data.project_id == "proj-001"
        assert request_data.triggered_by_work_id == "work-001"


# ── ProvisionerRegistry ──────────────────────────────────────────────────────

class TestProvisionerRegistry:
    def test_register_provider(self):
        registry = ProvisionerRegistry()
        provider = FakeProvisioner("test")
        registry.register(provider, priority=50)

        providers = registry.list_providers()
        assert len(providers) == 1
        assert providers[0].name == "test"
        assert providers[0].priority == 50
        assert providers[0].enabled is True

    def test_priority_ordering(self):
        registry = ProvisionerRegistry()
        registry.register(FakeProvisioner("low"), priority=200)
        registry.register(FakeProvisioner("high"), priority=10)
        registry.register(FakeProvisioner("mid"), priority=100)

        names = [p.name for p in registry.list_providers()]
        assert names == ["high", "mid", "low"]

    @pytest.mark.asyncio
    async def test_provision_uses_first_capable(self, request_data):
        registry = ProvisionerRegistry()
        p1 = FakeProvisioner("first", can=False)
        p2 = FakeProvisioner("second", can=True)
        registry.register(p1, priority=10)
        registry.register(p2, priority=20)

        result = await registry.provision(request_data)
        assert result.success
        assert result.provider == "second"
        assert len(p1.provision_calls) == 0
        assert len(p2.provision_calls) == 1

    @pytest.mark.asyncio
    async def test_provision_returns_failure_when_none_capable(self, request_data):
        registry = ProvisionerRegistry()
        registry.register(FakeProvisioner("nope", can=False))

        result = await registry.provision(request_data)
        assert not result.success
        assert result.provider == "none"

    @pytest.mark.asyncio
    async def test_disabled_providers_skipped(self, request_data):
        registry = ProvisionerRegistry()
        p = FakeProvisioner("disabled_one", can=True)
        registry.register(p, enabled=False)

        result = await registry.provision(request_data)
        assert not result.success
        assert len(p.provision_calls) == 0

    def test_enable_disable(self):
        registry = ProvisionerRegistry()
        registry.register(FakeProvisioner("toggle"), enabled=True)

        assert registry.disable("toggle")
        assert not registry.list_providers()[0].enabled

        assert registry.enable("toggle")
        assert registry.list_providers()[0].enabled

    def test_enable_nonexistent_returns_false(self):
        registry = ProvisionerRegistry()
        assert not registry.enable("ghost")
        assert not registry.disable("ghost")

    @pytest.mark.asyncio
    async def test_deprovision_routes_to_correct_provider(self):
        registry = ProvisionerRegistry()
        p = FakeProvisioner("docker")
        registry.register(p)

        result = await registry.deprovision("inst-001", "docker")
        assert result is True
        assert p.deprovision_calls == ["inst-001"]

    @pytest.mark.asyncio
    async def test_deprovision_unknown_provider(self):
        registry = ProvisionerRegistry()
        result = await registry.deprovision("inst-001", "unknown")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_all_images(self):
        registry = ProvisionerRegistry()
        registry.register(FakeProvisioner("a"))
        registry.register(FakeProvisioner("b"))

        images = await registry.list_all_images()
        assert len(images) == 2
        providers = {img.provider for img in images}
        assert providers == {"a", "b"}

    @pytest.mark.asyncio
    async def test_list_images_skips_disabled(self):
        registry = ProvisionerRegistry()
        registry.register(FakeProvisioner("enabled"), enabled=True)
        registry.register(FakeProvisioner("disabled"), enabled=False)

        images = await registry.list_all_images()
        assert len(images) == 1
        assert images[0].provider == "enabled"
