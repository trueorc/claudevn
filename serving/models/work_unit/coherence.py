"""Coherence analysis models for goal consistency checking.

Detects inconsistencies, implicit requirements, scope drift, and
gaps across the goal corpus. Runs when goals or steering input
are added, comparing new input against existing goals and specs.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class InsightType(str, Enum):
    """Types of coherence insights."""
    CONTRADICTION = "contradiction"
    IMPLICIT_REQUIREMENT = "implicit_requirement"
    SCOPE_DRIFT = "scope_drift"
    GAP = "gap"
    UNSTATED_DEPENDENCY = "unstated_dependency"


class InsightSeverity(str, Enum):
    """How urgent the insight is."""
    HIGH = "high"      # Direct contradiction or critical gap
    MEDIUM = "medium"  # Implicit requirement or scope drift
    LOW = "low"        # Minor gap or suggestion


class InsightSource(BaseModel):
    """Where an insight was derived from."""
    goal_id: str = Field(..., description="The goal that contributed to this insight")
    goal_title: str = Field(default="", description="Title of the goal for display")
    excerpt: str = Field(default="", description="Relevant excerpt from the goal")


class CoherenceInsight(BaseModel):
    """A single coherence finding across the goal corpus.

    Produced by analyzing new input against all existing goals,
    their decompositions, and any steering comments.
    """
    id: str = Field(..., description="Unique insight identifier")
    type: InsightType = Field(..., description="Category of inconsistency")
    severity: InsightSeverity = Field(default=InsightSeverity.MEDIUM)
    title: str = Field(..., description="Brief summary of the issue")
    description: str = Field(
        ...,
        description="Detailed explanation of what was detected and why it matters"
    )
    sources: List[InsightSource] = Field(
        default_factory=list,
        description="Goals/inputs that contributed to this insight"
    )
    suggestion: str = Field(
        default="",
        description="Suggested resolution or action"
    )
    affected_units: List[str] = Field(
        default_factory=list,
        description="Work unit IDs affected by this insight"
    )


class CoherenceAnalysis(BaseModel):
    """Result of running coherence analysis across the goal corpus."""
    project_id: str
    insights: List[CoherenceInsight] = Field(default_factory=list)
    goals_analyzed: int = Field(default=0, description="Number of goals compared")
