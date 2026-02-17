"""Unit tests for work profile presets.

Tests preset definitions, the preset registry, and the profile presets API.

Reference: Issue #878
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.work_profile_preset import (
    BUILD_PRESET,
    DEFAULT_PRESET,
    HARDEN_PRESET,
    INVEST_PRESET,
    PRESETS,
    TEST_PRESET,
    PresetName,
    WorkProfilePreset,
    get_preset,
    list_presets,
)
from models.planner_profile import PlannerProfile, ProfileWeights


# =============================================================================
# Preset Definition Tests
# =============================================================================


class TestPresetDefinitions:
    """Test that all preset definitions are valid and complete."""

    def test_all_four_presets_exist(self):
        assert len(PRESETS) == 4
        assert PresetName.BUILD in PRESETS
        assert PresetName.HARDEN in PRESETS
        assert PresetName.TEST in PRESETS
        assert PresetName.INVEST in PRESETS

    def test_default_preset_is_build(self):
        assert DEFAULT_PRESET == PresetName.BUILD

    def test_get_preset_returns_correct_preset(self):
        preset = get_preset(PresetName.BUILD)
        assert preset.name == PresetName.BUILD
        assert preset.label == "Build"

    def test_list_presets_returns_all(self):
        presets = list_presets()
        assert len(presets) == 4
        names = {p.name for p in presets}
        assert names == {PresetName.BUILD, PresetName.HARDEN, PresetName.TEST, PresetName.INVEST}

    def test_build_preset_prioritizes_features(self):
        weights = BUILD_PRESET.weights
        feature_weight = weights.work_type_weights["feature"].weight
        test_weight = weights.work_type_weights["test"].weight
        assert feature_weight > 0.8
        assert test_weight < 0.3
        assert feature_weight > test_weight

    def test_harden_preset_prioritizes_stability(self):
        weights = HARDEN_PRESET.weights
        bug_fix_weight = weights.work_type_weights["bug_fix"].weight
        feature_weight = weights.work_type_weights["feature"].weight
        assert bug_fix_weight > 0.8
        assert feature_weight < 0.3

    def test_test_preset_prioritizes_testing(self):
        weights = TEST_PRESET.weights
        test_weight = weights.work_type_weights["test"].weight
        feature_weight = weights.work_type_weights["feature"].weight
        assert test_weight > 0.8
        assert feature_weight < 0.3

    def test_invest_preset_is_balanced(self):
        weights = INVEST_PRESET.weights
        feature_weight = weights.work_type_weights["feature"].weight
        infra_weight = weights.work_type_weights["infrastructure"].weight
        # Both should be moderately weighted
        assert 0.5 <= feature_weight <= 0.8
        assert 0.5 <= infra_weight <= 0.8

    def test_all_presets_have_required_fields(self):
        for preset in list_presets():
            assert preset.label
            assert preset.description
            assert preset.optimization_target
            assert preset.intent in ("expansion", "consolidation", "targeted_investment", "quality_focused")
            assert preset.color.startswith("#")
            assert preset.icon

    def test_all_presets_have_valid_weights(self):
        for preset in list_presets():
            for key, wv in preset.weights.work_type_weights.items():
                assert 0.0 <= wv.weight <= 1.0, f"{preset.name}: work_type {key} weight out of range"
            for key, wv in preset.weights.lifecycle_stage_weights.items():
                assert 0.0 <= wv.weight <= 1.0, f"{preset.name}: lifecycle {key} weight out of range"

    def test_preset_policy_rule_ids_unique_within_preset(self):
        for preset in list_presets():
            rule_ids = [r.rule_id for r in preset.policy_rules]
            assert len(rule_ids) == len(set(rule_ids)), f"{preset.name}: duplicate rule IDs"

    def test_preset_policy_rule_ids_unique_across_presets(self):
        all_rule_ids = []
        for preset in list_presets():
            all_rule_ids.extend(r.rule_id for r in preset.policy_rules)
        assert len(all_rule_ids) == len(set(all_rule_ids)), "Duplicate rule IDs across presets"


# =============================================================================
# Planner Profile active_preset Field Tests
# =============================================================================


class TestPlannerProfilePresetField:
    """Test the active_preset field on PlannerProfile."""

    def test_active_preset_defaults_to_none(self):
        profile = PlannerProfile(
            profile_id="test",
            project_id="proj1",
        )
        assert profile.active_preset is None

    def test_active_preset_can_be_set(self):
        profile = PlannerProfile(
            profile_id="test",
            project_id="proj1",
            active_preset="build",
        )
        assert profile.active_preset == "build"

    def test_active_preset_serializes(self):
        profile = PlannerProfile(
            profile_id="test",
            project_id="proj1",
            active_preset="harden",
        )
        data = profile.model_dump()
        assert data["active_preset"] == "harden"


# =============================================================================
# Profile Presets API Tests
# =============================================================================


class TestProfilePresetsAPI:
    """Test the profile presets API endpoints."""

    def _make_app(self):
        from api.profile_presets import router
        app = FastAPI()
        app.include_router(router)
        return app

    def test_list_presets_endpoint(self):
        app = self._make_app()
        client = TestClient(app)
        response = client.get("/profiles/presets")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 4
        names = {p["name"] for p in data}
        assert names == {"build", "harden", "test", "invest"}

    def test_list_presets_contains_expected_fields(self):
        app = self._make_app()
        client = TestClient(app)
        response = client.get("/profiles/presets")
        data = response.json()
        for preset in data:
            assert "name" in preset
            assert "label" in preset
            assert "description" in preset
            assert "optimization_target" in preset
            assert "intent" in preset
            assert "color" in preset
            assert "icon" in preset

    @patch("api.profile_presets.get_planner_profile_service")
    def test_activate_preset_creates_new_profile(self, mock_get_service):
        mock_service = MagicMock()
        mock_service.get_profile = AsyncMock(return_value=None)
        mock_service._profiles = {}
        mock_service._save_profile_to_redis = AsyncMock()
        mock_service._save_profile_history = AsyncMock()
        mock_get_service.return_value = mock_service

        app = self._make_app()
        client = TestClient(app)
        response = client.post("/profiles/presets/build/activate?project_id=proj1")
        assert response.status_code == 200
        data = response.json()
        assert data["preset_name"] == "build"
        assert data["preset_label"] == "Build"
        assert data["project_id"] == "proj1"
        assert data["profile_version"] == 1

        # Verify profile was stored
        assert "proj1" in mock_service._profiles
        stored_profile = mock_service._profiles["proj1"]
        assert stored_profile.active_preset == "build"

    @patch("api.profile_presets.get_planner_profile_service")
    def test_activate_preset_updates_existing_profile(self, mock_get_service):
        existing = PlannerProfile(
            profile_id="old",
            project_id="proj1",
            active_preset="build",
            version=3,
        )
        mock_service = MagicMock()
        mock_service.get_profile = AsyncMock(return_value=existing)
        mock_service._save_profile_to_redis = AsyncMock()
        mock_service._save_profile_history = AsyncMock()
        mock_get_service.return_value = mock_service

        app = self._make_app()
        client = TestClient(app)
        response = client.post("/profiles/presets/harden/activate?project_id=proj1")
        assert response.status_code == 200
        data = response.json()
        assert data["preset_name"] == "harden"
        assert data["profile_version"] == 4  # incremented from 3

        # Verify profile was updated
        assert existing.active_preset == "harden"
        assert len(existing.triggers) == 1
        assert "Harden" in existing.triggers[0].description

    def test_activate_invalid_preset_returns_400(self):
        app = self._make_app()
        client = TestClient(app)
        response = client.post("/profiles/presets/invalid/activate?project_id=proj1")
        assert response.status_code == 400
        assert "Invalid preset name" in response.json()["detail"]

    def test_activate_preset_missing_project_id_returns_422(self):
        app = self._make_app()
        client = TestClient(app)
        response = client.post("/profiles/presets/build/activate")
        assert response.status_code == 422

    @patch("api.profile_presets.get_planner_profile_service")
    def test_get_active_preset_with_preset(self, mock_get_service):
        profile = PlannerProfile(
            profile_id="test",
            project_id="proj1",
            active_preset="test",
        )
        mock_service = MagicMock()
        mock_service.get_profile = AsyncMock(return_value=profile)
        mock_get_service.return_value = mock_service

        app = self._make_app()
        client = TestClient(app)
        response = client.get("/profiles/presets/active?project_id=proj1")
        assert response.status_code == 200
        data = response.json()
        assert data["active_preset"] == "test"
        assert data["active_preset_label"] == "Test"

    @patch("api.profile_presets.get_planner_profile_service")
    def test_get_active_preset_without_profile(self, mock_get_service):
        mock_service = MagicMock()
        mock_service.get_profile = AsyncMock(return_value=None)
        mock_get_service.return_value = mock_service

        app = self._make_app()
        client = TestClient(app)
        response = client.get("/profiles/presets/active?project_id=proj1")
        assert response.status_code == 200
        data = response.json()
        assert data["active_preset"] is None


# =============================================================================
# Planner Focus Service Preset Integration Tests
# =============================================================================


class TestFocusServicePresetAwareness:
    """Test that the focus service includes preset info in summaries."""

    @pytest.mark.asyncio
    async def test_focus_summary_includes_preset_info(self):
        from services.planner_focus_service import PlannerFocusService

        service = PlannerFocusService()
        profile = PlannerProfile(
            profile_id="test",
            project_id="proj1",
            active_preset="build",
            weights=BUILD_PRESET.weights.model_copy(deep=True),
        )

        summary = await service.get_focus_summary(
            project_id="proj1",
            profile=profile,
            goals=[],
        )

        assert summary.has_profile is True
        assert summary.active_preset == "build"
        assert summary.active_preset_label == "Build"
        assert summary.active_preset_color == "#3b82f6"

    @pytest.mark.asyncio
    async def test_focus_summary_uses_preset_target_when_no_goals(self):
        from services.planner_focus_service import PlannerFocusService

        service = PlannerFocusService()
        profile = PlannerProfile(
            profile_id="test",
            project_id="proj1",
            active_preset="harden",
            weights=HARDEN_PRESET.weights.model_copy(deep=True),
        )

        summary = await service.get_focus_summary(
            project_id="proj1",
            profile=profile,
            goals=[],
        )

        assert "Stabilizing and hardening" in summary.optimization_target

    @pytest.mark.asyncio
    async def test_focus_summary_no_preset_no_profile(self):
        from services.planner_focus_service import PlannerFocusService

        service = PlannerFocusService()
        summary = await service.get_focus_summary(
            project_id="proj1",
            profile=None,
            goals=[],
        )

        assert summary.has_profile is False
        assert summary.active_preset is None
        assert "Select a work profile" in summary.optimization_target
