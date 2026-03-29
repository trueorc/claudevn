"""Compute environment models — derived from planning, not pre-configured.

Layer 1 planning analyzes work units and produces a compute environment
specification (Dockerfile content + metadata). Human approves before
any provisioning happens.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class EnvironmentStatus(str, Enum):
    """Lifecycle of a compute environment spec."""
    PROPOSED = "proposed"      # Planning produced this, awaiting review
    APPROVED = "approved"      # Human approved, ready to build
    BUILDING = "building"      # Docker image being built
    READY = "ready"            # Image built, available for dispatch
    ACTIVE = "active"          # Container running, executing work
    FAILED = "failed"          # Build or runtime failure
    RETIRED = "retired"        # No longer needed


class RuntimeRequirement(BaseModel):
    """A single runtime requirement detected from work units."""
    name: str = Field(..., description="Tool/SDK/runtime name (e.g., python, node, pytest, eslint)")
    version: Optional[str] = Field(default=None, description="Required version (e.g., '3.12', '20.x')")
    reason: str = Field(default="", description="Why this is needed (which work units require it)")
    install_cmd: Optional[str] = Field(
        default=None,
        description="Install command if known (e.g., 'pip install pytest', 'npm install -g eslint')"
    )


class ComputeEnvironmentSpec(BaseModel):
    """A compute environment specification produced by Layer 1 planning.

    This is a reviewable artifact — the human sees exactly what will
    be built and approves before any Docker build happens.
    """
    id: str = Field(..., description="Unique environment spec ID")
    project_id: str = Field(..., description="Project this environment serves")
    goal_refs: List[str] = Field(
        default_factory=list,
        description="Goals that contributed to this spec"
    )

    # What was detected
    requirements: List[RuntimeRequirement] = Field(
        default_factory=list,
        description="Detected runtime requirements"
    )
    base_image: str = Field(
        default="ubuntu:22.04",
        description="Docker base image"
    )

    # The artifact
    dockerfile_content: str = Field(
        default="",
        description="Generated Dockerfile content for review"
    )
    work_unit_ids: List[str] = Field(
        default_factory=list,
        description="Work units this environment supports"
    )

    # Lifecycle
    status: EnvironmentStatus = Field(default=EnvironmentStatus.PROPOSED)
    approved_by: Optional[str] = Field(default=None, description="User who approved")
    approved_at: Optional[datetime] = Field(default=None)

    # Build info (populated after approval + build)
    image_tag: Optional[str] = Field(default=None, description="Docker image tag once built")
    container_id: Optional[str] = Field(default=None, description="Running container ID")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
