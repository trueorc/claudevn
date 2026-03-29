"""Compute environment provisioner — writes approved environments to disk.

On approval, writes the Dockerfile and metadata to the mounted
compute-envs volume so the host start.sh script can build and run them.
"""

import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

COMPUTE_ENVS_PATH = os.getenv("COMPUTE_ENVS_PATH", "/app/compute-envs")


def _safe_name(name: str) -> str:
    """Convert a project name to a safe directory name."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name).lower().strip('_')[:50]


async def write_environment(
    project_name: str,
    project_id: str,
    goal_id: str,
    dockerfile_content: str,
    requirements: list,
    description: str = "default",
) -> str:
    """Write an approved compute environment to the mounted volume.

    Creates compute-envs/<project_name>/Dockerfile and metadata.json
    for the host start.sh script to build and run.

    Args:
        project_name: Human-readable project name.
        project_id: Project ID for registration.
        goal_id: Goal that produced this environment.
        dockerfile_content: The generated Dockerfile.
        requirements: List of runtime requirement dicts.
        description: Short description for container naming.

    Returns:
        Path to the environment directory.
    """
    safe_name = _safe_name(project_name)
    env_dir = os.path.join(COMPUTE_ENVS_PATH, safe_name)
    os.makedirs(env_dir, exist_ok=True)

    # Write Dockerfile
    dockerfile_path = os.path.join(env_dir, "Dockerfile")
    with open(dockerfile_path, "w") as f:
        f.write(dockerfile_content)

    # Write metadata
    safe_desc = _safe_name(description)
    metadata = {
        "project_name": project_name,
        "project_id": project_id,
        "goal_id": goal_id,
        "description": safe_desc or "default",
        "compute_id": f"{safe_name}-compute_{safe_desc or 'default'}",
        "requirements": requirements,
        "container_name": f"{safe_name}-compute_{safe_desc or 'default'}",
    }

    metadata_path = os.path.join(env_dir, "metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(
        f"Wrote compute environment to {env_dir}: "
        f"Dockerfile ({len(dockerfile_content)} bytes), "
        f"container={metadata['container_name']}"
    )

    return env_dir
