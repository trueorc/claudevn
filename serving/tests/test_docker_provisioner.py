"""Tests for DockerProvisioner — Docker socket-based compute provisioning."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from config import DockerProvisionerConfig, DockerImageMapping
from services.providers.docker_provisioner import DockerProvisioner
from services.compute_provisioner import ProvisioningRequest, ProvisioningResult, ComputeImage


@pytest.fixture
def config():
    return DockerProvisionerConfig(
        enabled=True,
        socket="/var/run/docker.sock",
        network="claudevn-network",
        serving_url="http://serving:8002",
        container_prefix="claudevn-managed-",
        default_image="trueorc/compute-base:latest",
        image_mappings=[
            DockerImageMapping(
                image="trueorc/compute-node:22",
                capabilities=["runtime:node:22", "runtime:node"],
            ),
            DockerImageMapping(
                image="trueorc/compute-python:3.12",
                capabilities=["runtime:python:3.12", "runtime:python"],
            ),
        ],
    )


@pytest.fixture
def provisioner(config):
    return DockerProvisioner(config)


@pytest.fixture
def sample_request():
    return ProvisioningRequest(
        triggered_by_work_id="work-abc",
        project_id="proj-1",
        required_tools=["runtime:node:22"],
        required_capabilities=["runtime:node"],
    )


@pytest.fixture
def minimal_request():
    return ProvisioningRequest(
        triggered_by_work_id="work-xyz",
        project_id="proj-2",
    )


@pytest.fixture
def mock_docker_client():
    client = MagicMock()
    client.ping.return_value = True
    return client


class TestDockerProvisionerProperties:
    def test_name(self, provisioner):
        assert provisioner.name == "docker"

    def test_description(self, provisioner):
        assert "docker" in provisioner.description.lower()


class TestCanProvision:
    @pytest.mark.asyncio
    async def test_returns_false_when_socket_unavailable(self, provisioner, sample_request):
        provisioner._client = None
        with patch.object(provisioner, "_get_client", return_value=None):
            result = await provisioner.can_provision(sample_request)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_image_exists(self, provisioner, sample_request, mock_docker_client):
        provisioner._client = mock_docker_client
        mock_docker_client.images.get.return_value = MagicMock()
        result = await provisioner.can_provision(sample_request)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_after_pulling_image(self, provisioner, sample_request, mock_docker_client):
        provisioner._client = mock_docker_client
        mock_docker_client.images.get.side_effect = Exception("not found")
        mock_docker_client.images.pull.return_value = MagicMock()
        result = await provisioner.can_provision(sample_request)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_image_unavailable(self, provisioner, sample_request, mock_docker_client):
        provisioner._client = mock_docker_client
        mock_docker_client.images.get.side_effect = Exception("not found")
        mock_docker_client.images.pull.side_effect = Exception("pull failed")
        result = await provisioner.can_provision(sample_request)
        assert result is False


class TestImageSelection:
    def test_selects_matching_image(self, provisioner, sample_request):
        image = provisioner._find_image_for_request(sample_request)
        assert image == "trueorc/compute-node:22"

    def test_falls_back_to_default_for_no_match(self, provisioner):
        request = ProvisioningRequest(
            triggered_by_work_id="work-1",
            project_id="proj-1",
            required_tools=["runtime:go:1.22"],
        )
        image = provisioner._find_image_for_request(request)
        assert image == "trueorc/compute-base:latest"

    def test_falls_back_to_default_for_empty_requirements(self, provisioner, minimal_request):
        image = provisioner._find_image_for_request(minimal_request)
        assert image == "trueorc/compute-base:latest"


class TestProvision:
    @pytest.mark.asyncio
    async def test_returns_failure_when_no_client(self, provisioner, sample_request):
        provisioner._client = None
        with patch.object(provisioner, "_get_client", return_value=None):
            result = await provisioner.provision(sample_request)
        assert result.success is False
        assert "not available" in result.error

    @pytest.mark.asyncio
    async def test_starts_container_successfully(self, provisioner, sample_request, mock_docker_client):
        provisioner._client = mock_docker_client
        mock_container = MagicMock()
        mock_docker_client.containers.run.return_value = mock_container

        result = await provisioner.provision(sample_request)

        assert result.success is True
        assert result.provider == "docker"
        assert result.instance_id is not None
        assert result.estimated_ready_seconds == 20
        mock_docker_client.containers.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_container_has_correct_env(self, provisioner, sample_request, mock_docker_client):
        provisioner._client = mock_docker_client
        mock_docker_client.containers.run.return_value = MagicMock()

        await provisioner.provision(sample_request)

        call_kwargs = mock_docker_client.containers.run.call_args
        env = call_kwargs[1]["environment"]
        assert env["SERVING_URL"] == "http://serving:8002"
        assert env["COMPUTE_LIFECYCLE_MODE"] == "managed"
        assert env["COMPUTE_REGISTER_ON_STARTUP"] == "true"
        assert env["COMPUTE_AUTH_MODE"] == "serving"

    @pytest.mark.asyncio
    async def test_container_has_correct_labels(self, provisioner, sample_request, mock_docker_client):
        provisioner._client = mock_docker_client
        mock_docker_client.containers.run.return_value = MagicMock()

        await provisioner.provision(sample_request)

        call_kwargs = mock_docker_client.containers.run.call_args
        labels = call_kwargs[1]["labels"]
        assert labels["claudevn.managed"] == "true"
        assert labels["claudevn.work_id"] == "work-abc"

    @pytest.mark.asyncio
    async def test_container_joins_correct_network(self, provisioner, sample_request, mock_docker_client):
        provisioner._client = mock_docker_client
        mock_docker_client.containers.run.return_value = MagicMock()

        await provisioner.provision(sample_request)

        call_kwargs = mock_docker_client.containers.run.call_args
        assert call_kwargs[1]["network"] == "claudevn-network"

    @pytest.mark.asyncio
    async def test_returns_failure_on_docker_error(self, provisioner, sample_request, mock_docker_client):
        provisioner._client = mock_docker_client
        mock_docker_client.containers.run.side_effect = RuntimeError("container creation failed")

        result = await provisioner.provision(sample_request)

        assert result.success is False
        assert "container creation failed" in result.error


class TestDeprovision:
    @pytest.mark.asyncio
    async def test_stops_and_removes_container(self, provisioner, mock_docker_client):
        provisioner._client = mock_docker_client
        mock_container = MagicMock()
        mock_docker_client.containers.get.return_value = mock_container

        result = await provisioner.deprovision("managed-abc12345")

        assert result is True
        mock_container.stop.assert_called_once_with(timeout=10)
        mock_container.remove.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_container_not_found(self, provisioner, mock_docker_client):
        provisioner._client = mock_docker_client
        mock_docker_client.containers.get.side_effect = Exception("not found")

        result = await provisioner.deprovision("managed-abc12345")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_client(self, provisioner):
        provisioner._client = None
        with patch.object(provisioner, "_get_client", return_value=None):
            result = await provisioner.deprovision("managed-abc12345")
        assert result is False


class TestListAvailableImages:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_client(self, provisioner):
        provisioner._client = None
        with patch.object(provisioner, "_get_client", return_value=None):
            images = await provisioner.list_available_images()
        assert images == []

    @pytest.mark.asyncio
    async def test_lists_compute_images(self, provisioner, mock_docker_client):
        provisioner._client = mock_docker_client
        mock_img1 = MagicMock()
        mock_img1.tags = ["trueorc/compute-node:22"]
        mock_img1.short_id = "sha256:abc123"
        mock_img2 = MagicMock()
        mock_img2.tags = ["nginx:latest"]
        mock_img2.short_id = "sha256:def456"
        mock_docker_client.images.list.return_value = [mock_img1, mock_img2]

        images = await provisioner.list_available_images()

        assert len(images) == 1
        assert images[0].name == "trueorc/compute-node:22"
        assert "runtime:node:22" in images[0].capabilities
