"""Built-in work profile presets for the planner.

Defines preset configurations that provide a default planner stance
without requiring goal creation. Each preset maps to a GoalIntentType
and provides pre-configured ontology weights and policy rules.

Reference: Issue #878
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from models.planner_profile import (
    ConfidenceBand,
    ConfidenceLevel,
    PolicyActionType,
    PolicyConditionType,
    PolicyRule,
    ProfileWeights,
    WeightedValue,
)


class PresetName(str, Enum):
    """Available built-in work profile presets."""
    BUILD = "build"
    HARDEN = "harden"
    TEST = "test"
    INVEST = "invest"


class WorkProfilePreset(BaseModel):
    """A built-in work profile preset definition.

    Presets provide pre-configured PlannerProfile weights and policy rules
    that can be activated without creating goals. They serve as a base layer
    that goals and directives can layer on top of.
    """
    name: PresetName = Field(..., description="Preset identifier")
    label: str = Field(..., description="Human-readable display name")
    description: str = Field(..., description="Short description of this profile's focus")
    optimization_target: str = Field(
        ...,
        description="Human-readable optimization target shown in Plan tab"
    )
    intent: str = Field(
        ...,
        description="Mapped GoalIntentType value (expansion, consolidation, etc.)"
    )
    color: str = Field(..., description="CSS color for UI display")
    icon: str = Field(..., description="Lucide icon name for UI display")
    weights: ProfileWeights = Field(
        ...,
        description="Pre-configured ontology weights"
    )
    policy_rules: List[PolicyRule] = Field(
        default_factory=list,
        description="Pre-configured policy rules"
    )


def _wv(weight: float, confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM, rationale: str = "") -> WeightedValue:
    """Shorthand to create a WeightedValue."""
    return WeightedValue(
        weight=weight,
        confidence=ConfidenceBand(level=confidence, rationale=rationale),
    )


# =============================================================================
# Preset Definitions
# =============================================================================

BUILD_PRESET = WorkProfilePreset(
    name=PresetName.BUILD,
    label="Build",
    description="Feature development focus — reach functional state fast",
    optimization_target="Primary focus: Building new features and capabilities. Prioritizing: Features, Integration.",
    intent="expansion",
    color="#3b82f6",
    icon="Hammer",
    weights=ProfileWeights(
        work_type_weights={
            "feature": _wv(0.9, ConfidenceLevel.HIGH, "Build preset: features prioritized"),
            "integration": _wv(0.7, ConfidenceLevel.MEDIUM, "Build preset: integration work"),
            "bug_fix": _wv(0.4, ConfidenceLevel.LOW, "Build preset: fix only blocking bugs"),
            "test": _wv(0.25, ConfidenceLevel.LOW, "Build preset: minimal testing"),
            "refactor": _wv(0.15, ConfidenceLevel.LOW, "Build preset: defer refactoring"),
        },
        lifecycle_stage_weights={
            "build": _wv(0.9, ConfidenceLevel.HIGH, "Build preset: build phase"),
            "design": _wv(0.7, ConfidenceLevel.MEDIUM, "Build preset: design as needed"),
            "test": _wv(0.3, ConfidenceLevel.LOW, "Build preset: minimal testing"),
            "validate": _wv(0.2, ConfidenceLevel.LOW, "Build preset: validate later"),
        },
    ),
    policy_rules=[
        PolicyRule(
            rule_id="preset_build_defer_refactor",
            name="Defer refactoring during build",
            description="Deprioritize refactoring work when building features",
            condition_type=PolicyConditionType.IN_ONTOLOGY_CATEGORY,
            condition_params={"category": "work_type", "key": "refactor"},
            action_type=PolicyActionType.DEPRIORITIZE,
            action_params={"factor": 0.5},
            confidence=ConfidenceBand(
                level=ConfidenceLevel.LOW,
                rationale="Build preset: build first, refactor later",
            ),
        ),
    ],
)

HARDEN_PRESET = WorkProfilePreset(
    name=PresetName.HARDEN,
    label="Harden",
    description="Stability focus — bug fixes, refactoring, and hardening",
    optimization_target="Primary focus: Stabilizing and hardening existing systems. Prioritizing: Bug Fixes, Refactoring, Testing.",
    intent="consolidation",
    color="#f59e0b",
    icon="Shield",
    weights=ProfileWeights(
        work_type_weights={
            "bug_fix": _wv(0.9, ConfidenceLevel.HIGH, "Harden preset: fix bugs first"),
            "refactor": _wv(0.8, ConfidenceLevel.HIGH, "Harden preset: clean up code"),
            "test": _wv(0.75, ConfidenceLevel.MEDIUM, "Harden preset: testing important"),
            "feature": _wv(0.15, ConfidenceLevel.MEDIUM, "Harden preset: pause new features"),
            "infrastructure": _wv(0.6, ConfidenceLevel.MEDIUM, "Harden preset: infra stability"),
        },
        lifecycle_stage_weights={
            "test": _wv(0.9, ConfidenceLevel.HIGH, "Harden preset: testing phase"),
            "validate": _wv(0.85, ConfidenceLevel.HIGH, "Harden preset: validation"),
            "build": _wv(0.3, ConfidenceLevel.LOW, "Harden preset: minimize new build"),
        },
    ),
    policy_rules=[
        PolicyRule(
            rule_id="preset_harden_finish_wip",
            name="Finish near-complete work",
            description="Tasks >80% complete should be finished regardless",
            condition_type=PolicyConditionType.COMPLETION_ABOVE_THRESHOLD,
            condition_params={"threshold": 0.8},
            action_type=PolicyActionType.PRESERVE_PRIORITY,
            action_params={},
            confidence=ConfidenceBand(
                level=ConfidenceLevel.HIGH,
                rationale="Harden preset: finish what's started",
            ),
        ),
        PolicyRule(
            rule_id="preset_harden_elevate_blockers",
            name="Elevate blocking issues",
            description="Items blocking many others get elevated priority",
            condition_type=PolicyConditionType.BLOCKING_COUNT_ABOVE,
            condition_params={"threshold": 1},
            action_type=PolicyActionType.ELEVATE_PRIORITY,
            action_params={"boost": 0.3},
            confidence=ConfidenceBand(
                level=ConfidenceLevel.HIGH,
                rationale="Harden preset: unblock dependent work",
            ),
        ),
    ],
)

TEST_PRESET = WorkProfilePreset(
    name=PresetName.TEST,
    label="Test",
    description="Testing focus — coverage, validation, and quality assurance",
    optimization_target="Primary focus: Deep quality improvement and testing focus. Prioritizing: Testing, Validation.",
    intent="quality_focused",
    color="#10b981",
    icon="FlaskConical",
    weights=ProfileWeights(
        work_type_weights={
            "test": _wv(0.9, ConfidenceLevel.HIGH, "Test preset: testing is top priority"),
            "bug_fix": _wv(0.7, ConfidenceLevel.MEDIUM, "Test preset: fix found bugs"),
            "refactor": _wv(0.6, ConfidenceLevel.MEDIUM, "Test preset: refactor for testability"),
            "feature": _wv(0.2, ConfidenceLevel.LOW, "Test preset: pause new features"),
        },
        lifecycle_stage_weights={
            "test": _wv(0.9, ConfidenceLevel.HIGH, "Test preset: test phase"),
            "validate": _wv(0.9, ConfidenceLevel.HIGH, "Test preset: validation phase"),
            "build": _wv(0.2, ConfidenceLevel.LOW, "Test preset: minimize new build"),
        },
    ),
    policy_rules=[
        PolicyRule(
            rule_id="preset_test_defer_features",
            name="Defer new features during testing",
            description="Deprioritize new feature work when focusing on testing",
            condition_type=PolicyConditionType.IN_ONTOLOGY_CATEGORY,
            condition_params={"category": "work_type", "key": "feature"},
            action_type=PolicyActionType.DEPRIORITIZE,
            action_params={"factor": 0.4},
            confidence=ConfidenceBand(
                level=ConfidenceLevel.MEDIUM,
                rationale="Test preset: test before expanding",
            ),
        ),
        PolicyRule(
            rule_id="preset_test_elevate_blockers",
            name="Elevate test blockers",
            description="Tasks blocking high-priority testing get elevated",
            condition_type=PolicyConditionType.BLOCKS_HIGH_PRIORITY,
            condition_params={"target_work_type": "test", "min_weight": 0.7},
            action_type=PolicyActionType.ELEVATE_PRIORITY,
            action_params={"boost": 0.3},
            confidence=ConfidenceBand(
                level=ConfidenceLevel.HIGH,
                rationale="Test preset: unblock testing",
            ),
        ),
    ],
)

INVEST_PRESET = WorkProfilePreset(
    name=PresetName.INVEST,
    label="Invest",
    description="Targeted investment — focused capability in a specific area",
    optimization_target="Primary focus: Focused investment in specific capability areas. Balanced priorities with high confidence.",
    intent="targeted_investment",
    color="#8b5cf6",
    icon="TrendingUp",
    weights=ProfileWeights(
        work_type_weights={
            "feature": _wv(0.7, ConfidenceLevel.MEDIUM, "Invest preset: balanced features"),
            "infrastructure": _wv(0.7, ConfidenceLevel.MEDIUM, "Invest preset: infrastructure investment"),
            "integration": _wv(0.6, ConfidenceLevel.MEDIUM, "Invest preset: integration work"),
            "test": _wv(0.5, ConfidenceLevel.MEDIUM, "Invest preset: balanced testing"),
            "bug_fix": _wv(0.5, ConfidenceLevel.MEDIUM, "Invest preset: balanced fixes"),
        },
        lifecycle_stage_weights={
            "build": _wv(0.8, ConfidenceLevel.MEDIUM, "Invest preset: build phase"),
            "design": _wv(0.7, ConfidenceLevel.MEDIUM, "Invest preset: design phase"),
            "test": _wv(0.5, ConfidenceLevel.MEDIUM, "Invest preset: balanced testing"),
        },
    ),
    policy_rules=[
        PolicyRule(
            rule_id="preset_invest_high_leverage",
            name="Prioritize high-leverage items",
            description="Items blocking many others get elevated priority",
            condition_type=PolicyConditionType.BLOCKING_COUNT_ABOVE,
            condition_params={"threshold": 2},
            action_type=PolicyActionType.ELEVATE_PRIORITY,
            action_params={"boost": 0.2},
            confidence=ConfidenceBand(
                level=ConfidenceLevel.MEDIUM,
                rationale="Invest preset: maximize unblocking",
            ),
        ),
    ],
)

# Registry of all presets keyed by name
PRESETS: Dict[PresetName, WorkProfilePreset] = {
    PresetName.BUILD: BUILD_PRESET,
    PresetName.HARDEN: HARDEN_PRESET,
    PresetName.TEST: TEST_PRESET,
    PresetName.INVEST: INVEST_PRESET,
}

# Default preset applied when no profile exists
DEFAULT_PRESET = PresetName.BUILD


def get_preset(name: PresetName) -> WorkProfilePreset:
    """Get a preset by name."""
    return PRESETS[name]


def list_presets() -> List[WorkProfilePreset]:
    """List all available presets."""
    return list(PRESETS.values())
