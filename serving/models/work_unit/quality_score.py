"""Quality scoring models for decomposition assessment.

Per-unit quality scores and overall decomposition confidence,
as defined in the Planning System Specification Section 5.
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ConfidenceLevel(str, Enum):
    """Traffic light for decomposition confidence."""
    GREEN = "green"    # >= 75: Ready for approval
    YELLOW = "yellow"  # 50-74: Needs review
    RED = "red"        # < 50: Not ready


class ScoringFactor(BaseModel):
    """A single factor contributing to a quality score."""
    name: str
    weight: float
    score: int = Field(ge=0, le=100)
    detail: str = ""


class UnitQualityScore(BaseModel):
    """Per-unit quality score (0-100) based on 5 weighted factors."""
    unit_id: str
    score: int = Field(ge=0, le=100)
    factors: List[ScoringFactor] = Field(default_factory=list)

    @property
    def level(self) -> str:
        if self.score >= 80:
            return "ready"
        elif self.score >= 60:
            return "acceptable"
        elif self.score >= 40:
            return "needs_attention"
        else:
            return "not_ready"


class RecommendationType(str, Enum):
    """Type of split/merge recommendation."""
    SPLIT = "split"
    MERGE = "merge"


class SplitMergeRecommendation(BaseModel):
    """A recommendation to split or merge work units."""
    type: RecommendationType
    unit_ids: List[str]
    reason: str
    detail: str = ""


class DecompositionConfidence(BaseModel):
    """Overall decomposition confidence with traffic light."""
    score: int = Field(ge=0, le=100)
    level: ConfidenceLevel
    factors: List[ScoringFactor] = Field(default_factory=list)
    unit_scores: List[UnitQualityScore] = Field(default_factory=list)
    recommendations: List[SplitMergeRecommendation] = Field(default_factory=list)
