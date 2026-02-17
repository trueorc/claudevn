"""Goal Decomposer models for Slim Claude Code.

Models for goal decomposition - transforming natural language goals
into structured issues with dependencies.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EstimatedComplexity(str, Enum):
    """Estimated complexity/size of an issue."""
    XS = "xs"
    S = "s"
    M = "m"
    L = "l"
    XL = "xl"


class DecomposedIssue(BaseModel):
    """A structured issue extracted from goal decomposition.

    Represents an actionable unit of work with dependencies and requirements.
    """
    temp_id: str = Field(..., description="Temporary ID for dependency refs")
    title: str = Field(..., description="Brief, actionable title")
    description: str = Field(..., description="Detailed description of work")
    issue_type: str = Field(
        default="feature",
        description="Type: feature, bug, refactor, test, docs"
    )
    priority: str = Field(
        default="P2",
        description="Priority: P0 (critical), P1 (high), P2 (medium), P3 (low)"
    )
    area: str = Field(
        default="api",
        description="Area: api, database, frontend, infra"
    )
    required_skills: List[str] = Field(
        default_factory=list,
        description="Skill IDs needed to complete this issue"
    )
    estimated_complexity: EstimatedComplexity = Field(
        default=EstimatedComplexity.M,
        description="Estimated size/complexity"
    )
    blocked_by: List[str] = Field(
        default_factory=list,
        description="temp_ids of issues that must complete first"
    )
    acceptance_criteria: List[str] = Field(
        default_factory=list,
        description="Definition of done criteria"
    )


class GoalDecompositionRequest(BaseModel):
    """Request to decompose a goal into issues."""
    goal_id: str = Field(..., description="Reference to existing Goal")
    constraints: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional constraints (max_issues, focus_areas, etc.)"
    )


class GoalDecompositionResult(BaseModel):
    """Result of goal decomposition.

    Contains the decomposed issues, dependency graph, and execution phases.
    """
    goal_id: str = Field(..., description="Source goal ID")
    decomposition_id: str = Field(..., description="Unique decomposition ID")
    issues: List[DecomposedIssue] = Field(
        default_factory=list,
        description="Decomposed issues"
    )
    dependency_graph: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="issue temp_id -> list of blocked_by temp_ids"
    )
    execution_phases: List[List[str]] = Field(
        default_factory=list,
        description="Parallel execution groups (list of temp_ids per phase)"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score (0-1) for decomposition quality"
    )
    reasoning: str = Field(
        default="",
        description="Explanation of decomposition approach"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class GoalDecomposerConfig(BaseModel):
    """Configuration for Goal Decomposer service."""

    # Claude model settings
    model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model to use"
    )
    max_tokens: int = Field(
        default=4096,
        description="Max tokens for Claude response"
    )
    temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Temperature for decomposition (lower = more consistent)"
    )

    # Decomposition limits
    max_issues_per_goal: int = Field(
        default=50,
        description="Maximum issues per decomposition"
    )
    default_max_issues: int = Field(
        default=20,
        description="Default max issues if not specified in constraints"
    )


# Claude prompt response schema for structured output
DECOMPOSITION_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "temp_id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "issue_type": {
                        "type": "string",
                        "enum": ["feature", "bug", "refactor", "test", "docs"]
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["P0", "P1", "P2", "P3"]
                    },
                    "area": {
                        "type": "string",
                        "enum": ["api", "database", "frontend", "infra"]
                    },
                    "required_skills": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "estimated_complexity": {
                        "type": "string",
                        "enum": ["xs", "s", "m", "l", "xl"]
                    },
                    "blocked_by": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "acceptance_criteria": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["temp_id", "title", "description"]
            }
        },
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"}
    },
    "required": ["issues", "confidence", "reasoning"]
}
