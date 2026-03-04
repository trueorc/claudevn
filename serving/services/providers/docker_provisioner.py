"""Docker provisioner — starts compute containers via Docker socket.

Primary automated provider for local development and self-hosted deployments.
Requires Docker socket access (sibling containers, not Docker-in-Docker).
"""

import logging
import os
import uuid
from typing import List, Optional

from config import DockerProvisionerConfig
from services.compute_provisioner import (
    ComputeProvisioner,
    ProvisioningRequest,
    ProvisioningResult,
    ComputeImage,
)

logger = logging.getLogger(__name__)


class DockerProvisioner(ComputeProvisioner):
    """Provisions compute containers via the Docker API.

    Uses the Docker SDK to start containers on the same network as serving.
    Containers auto-register via SSE with lifecycle_mode=managed.
    """

    def __init__(self, config: DockerProvisionerConfig):
        self._config = config
        self._client = None  # Lazy — created on first use

    @property
    def name(self) -> str:
        return "docker"

    @property
    def description(self) -> str:
        return "Provisions compute containers via the local Docker socket"

    def _get_client(self):
        """Lazy-init Docker client from socket."""
        if self._client is not None:
            return self._client
        try:
            import docker
            self._client = docker.DockerClient(base_url=f"unix://{self._config.socket}")
            self._client.ping()
            return self._client
        except Exception as e:
            logger.debug(f"Docker client unavailable: {e}")
            self._client = None
            return None

    def _find_image_for_request(self, request: ProvisioningRequest) -> Optional[str]:
        """Find the best matching image for a provisioning request.

        Checks image mappings for capability overlap. Falls back to default image.
        """
        required = set(request.required_tools + request.required_capabilities)
        if not required:
            return self._config.default_image

        best_image = None
        best_overlap = 0
        for mapping in self._config.image_mappings:
            overlap = len(required & set(mapping.capabilities))
            if overlap > best_overlap:
                best_overlap = overlap
                best_image = mapping.image

        return best_image or self._config.default_image

    async def can_provision(self, request: ProvisioningRequest) -> bool:
        """Returns True if Docker socket is accessible and an image is available."""
        client = self._get_client()
        if client is None:
            return False

        image_name = self._find_image_for_request(request)
        try:
            client.images.get(image_name)
            return True
        except Exception:
            # Try pulling the image
            try:
                client.images.pull(image_name)
                return True
            except Exception as e:
                logger.debug(f"Image {image_name} not available: {e}")
                return False

    async def provision(self, request: ProvisioningRequest) -> ProvisioningResult:
        """Start a compute container on the Docker network.

        The container auto-registers with serving via SSE and sets
        lifecycle_mode=managed so serving can control its lifecycle.
        """
        client = self._get_client()
        if client is None:
            return ProvisioningResult(
                success=False,
                provider=self.name,
                error="Docker socket not available",
            )

        image_name = self._find_image_for_request(request)
        instance_id = f"managed-{uuid.uuid4().hex[:8]}"
        container_name = f"{self._config.container_prefix}{instance_id}"

        # Build capability labels string from the matched image mapping
        matched_capabilities = []
        for mapping in self._config.image_mappings:
            if mapping.image == image_name:
                matched_capabilities = mapping.capabilities
                break

        env = {
            "COMPUTE_INSTANCE_ID": instance_id,
            "COMPUTE_INSTANCE_NAME": container_name,
            "SERVING_URL": self._config.serving_url,
            "COMPUTE_REGISTER_ON_STARTUP": "true",
            "COMPUTE_AUTH_MODE": "serving",
            "CLAUDEVN_SERVING_URL": self._config.serving_url,
            "CLAUDEVN_SERVING_AUTH_URL": f"{self._config.serving_url}/api/v1/auth",
            "COMPUTE_LIFECYCLE_MODE": "managed",
            "COMPUTE_CAPABILITIES": ",".join(matched_capabilities),
            "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
            "MCP_ENABLED": "true",
        }

        try:
            container = client.containers.run(
                image=image_name,
                name=container_name,
                environment=env,
                network=self._config.network,
                detach=True,
                restart_policy={"Name": "unless-stopped"},
                labels={
                    "claudevn.managed": "true",
                    "claudevn.instance_id": instance_id,
                    "claudevn.work_id": request.triggered_by_work_id,
                    "claudevn.project_id": request.project_id,
                },
            )
            logger.info(
                f"Docker provisioner: started container {container_name} "
                f"(image={image_name}) for work {request.triggered_by_work_id}"
            )

            return ProvisioningResult(
                success=True,
                instance_id=instance_id,
                provider=self.name,
                estimated_ready_seconds=20,
            )
        except Exception as e:
            logger.error(f"Docker provisioner: failed to start container: {e}")
            return ProvisioningResult(
                success=False,
                provider=self.name,
                error=str(e),
            )

    async def deprovision(self, instance_id: str) -> bool:
        """Stop and remove a managed container."""
        client = self._get_client()
        if client is None:
            return False

        container_name = f"{self._config.container_prefix}{instance_id}"
        try:
            container = client.containers.get(container_name)
            container.stop(timeout=10)
            container.remove()
            logger.info(f"Docker provisioner: removed container {container_name}")
            return True
        except Exception as e:
            logger.error(f"Docker provisioner: failed to remove {container_name}: {e}")
            return False

    async def list_available_images(self) -> List[ComputeImage]:
        """List local Docker images matching trueorc/compute-* pattern."""
        client = self._get_client()
        if client is None:
            return []

        images = []
        try:
            for img in client.images.list():
                for tag in (img.tags or []):
                    if "compute" in tag.lower():
                        # Find matching capability mapping
                        capabilities = []
                        for mapping in self._config.image_mappings:
                            if mapping.image == tag:
                                capabilities = mapping.capabilities
                                break
                        images.append(ComputeImage(
                            image_id=img.short_id,
                            name=tag,
                            capabilities=capabilities,
                            provider=self.name,
                        ))
        except Exception as e:
            logger.error(f"Failed to list Docker images: {e}")

        return images
