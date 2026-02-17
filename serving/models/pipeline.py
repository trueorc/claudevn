"""Execution pipeline models."""

from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field


class StepStatus(str, Enum):
    """Status of a pipeline step."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineStatus(str, Enum):
    """Status of execution pipeline."""
    BUILDING = "building"
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineStep(BaseModel):
    """A single step in an execution pipeline."""
    
    step_id: str = Field(..., description="Unique step identifier")
    order: int = Field(..., description="Execution order (0-indexed)")
    agent_id: str = Field(..., description="Agent to execute")
    agent_name: str = Field(..., description="Human-readable agent name")
    description: str = Field(..., description="What this step does")
    
    # Execution details
    prompt: str = Field(..., description="Prompt for the agent")
    context: Dict[str, Any] = Field(default_factory=dict, description="Execution context")
    output_key: str = Field(..., description="Key to store output in session")
    
    # Dependencies and routing
    dependencies: List[str] = Field(
        default_factory=list,
        description="Step IDs that must complete before this step"
    )
    target_compute: Optional[str] = Field(
        None,
        description="Specific compute instance ID, or None for auto-selection"
    )
    
    # Execution state
    status: StepStatus = Field(default=StepStatus.PENDING, description="Current status")
    result: Optional[Dict[str, Any]] = Field(None, description="Step result")
    error: Optional[str] = Field(None, description="Error message if failed")
    
    # Timestamps
    started_at: Optional[datetime] = Field(None, description="When step started")
    completed_at: Optional[datetime] = Field(None, description="When step completed")
    
    # Additional metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional step metadata"
    )

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class ExecutionPipeline(BaseModel):
    """Complete execution pipeline for a business request."""
    
    pipeline_id: str = Field(..., description="Unique pipeline identifier")
    session_id: str = Field(..., description="Parent session ID")
    
    # Pipeline definition
    goal: str = Field(..., description="Business goal this pipeline achieves")
    steps: List[PipelineStep] = Field(default_factory=list, description="Pipeline steps")
    
    # Execution state
    status: PipelineStatus = Field(
        default=PipelineStatus.BUILDING,
        description="Current pipeline status"
    )
    current_step: Optional[int] = Field(
        None,
        description="Index of currently executing step"
    )
    
    # Creation info
    created_by: str = Field(..., description="Agent or user that created pipeline")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When pipeline was created"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update time"
    )
    
    # Results
    final_output: Optional[Dict[str, Any]] = Field(
        None,
        description="Final aggregated output"
    )
    
    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional pipeline metadata"
    )

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })

    def get_step(self, step_id: str) -> Optional[PipelineStep]:
        """Get a step by ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None
    
    def get_pending_steps(self) -> List[PipelineStep]:
        """Get all pending steps whose dependencies are satisfied."""
        pending = []
        for step in self.steps:
            if step.status != StepStatus.PENDING:
                continue
            
            # Check if all dependencies are completed
            deps_satisfied = all(
                self.get_step(dep_id) and self.get_step(dep_id).status == StepStatus.COMPLETED
                for dep_id in step.dependencies
            )
            
            if deps_satisfied:
                pending.append(step)
        
        return pending
    
    def mark_step_running(self, step_id: str):
        """Mark a step as running."""
        step = self.get_step(step_id)
        if step:
            step.status = StepStatus.RUNNING
            step.started_at = datetime.now(timezone.utc)
            self.updated_at = datetime.now(timezone.utc)
    
    def mark_step_completed(self, step_id: str, result: Dict[str, Any]):
        """Mark a step as completed with result."""
        step = self.get_step(step_id)
        if step:
            step.status = StepStatus.COMPLETED
            step.result = result
            step.completed_at = datetime.now(timezone.utc)
            self.updated_at = datetime.now(timezone.utc)
    
    def mark_step_failed(self, step_id: str, error: str):
        """Mark a step as failed with error."""
        step = self.get_step(step_id)
        if step:
            step.status = StepStatus.FAILED
            step.error = error
            step.completed_at = datetime.now(timezone.utc)
            self.updated_at = datetime.now(timezone.utc)
    
    def is_complete(self) -> bool:
        """Check if all steps are completed."""
        return all(step.status == StepStatus.COMPLETED for step in self.steps)
    
    def has_failures(self) -> bool:
        """Check if any steps failed."""
        return any(step.status == StepStatus.FAILED for step in self.steps)
    
    def get_progress(self) -> Dict[str, Any]:
        """Get execution progress statistics."""
        total = len(self.steps)
        completed = sum(1 for step in self.steps if step.status == StepStatus.COMPLETED)
        failed = sum(1 for step in self.steps if step.status == StepStatus.FAILED)
        running = sum(1 for step in self.steps if step.status == StepStatus.RUNNING)
        pending = sum(1 for step in self.steps if step.status == StepStatus.PENDING)
        
        return {
            "total_steps": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": pending,
            "progress_percent": (completed / total * 100) if total > 0 else 0
        }


class PipelineRequest(BaseModel):
    """Request to create an execution pipeline."""
    goal: str = Field(..., description="Business goal to achieve")
    context: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional context for planning"
    )


class PipelineResponse(BaseModel):
    """Response after pipeline creation."""
    pipeline_id: str
    session_id: str
    status: PipelineStatus
    steps_count: int
    message: str

