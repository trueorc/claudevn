"""Unit tests for claudevn_submit_characterization MCP tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.tools.characterization import (
    SubmitCharacterizationInput,
    SubmitCharacterizationResponse,
    OntologyTagsInput,
    MeaningInput,
    DependencyInput,
    submit_characterization,
)
from mcp.models import MCPError


# =============================================================================
# Helpers
# =============================================================================


def make_ontology_input(**overrides):
    defaults = dict(
        work_type="feature",
        lifecycle_stage="build",
        technical_domains=["backend"],
    )
    defaults.update(overrides)
    return OntologyTagsInput(**defaults)


def make_meaning_input(**overrides):
    defaults = dict(
        business_summary="Adds user value",
        technical_summary="Implements REST endpoint",
    )
    defaults.update(overrides)
    return MeaningInput(**defaults)


def make_submit_input(**overrides):
    defaults = dict(
        characterization_id="char-abc123",
        project_id="proj-1",
        item_id="item-001",
        ontology_tags=make_ontology_input(),
        meaning=make_meaning_input(),
        confidence=0.85,
    )
    defaults.update(overrides)
    return SubmitCharacterizationInput(**defaults)


# =============================================================================
# Input Model Tests
# =============================================================================


class TestOntologyTagsInput:
    def test_creation(self):
        tags = make_ontology_input()
        assert tags.work_type == "feature"
        assert tags.lifecycle_stage == "build"
        assert tags.technical_domains == ["backend"]
        assert tags.cluster_ids == []

    def test_with_cluster_ids(self):
        tags = make_ontology_input(cluster_ids=["c1", "c2"])
        assert tags.cluster_ids == ["c1", "c2"]


class TestMeaningInput:
    def test_minimal(self):
        m = MeaningInput(
            business_summary="Value",
            technical_summary="Impl",
        )
        assert m.business_summary == "Value"
        assert m.business_user_impact == ""
        assert m.contextual_role == "incremental"

    def test_full(self):
        m = MeaningInput(
            business_summary="Value",
            business_user_impact="Better UX",
            business_value="Revenue",
            technical_summary="Impl",
            technical_components=["api", "db"],
            technical_risk="Low",
            contextual_summary="Core work",
            contextual_role="foundational",
            related_work_summary="Related to auth",
        )
        assert m.contextual_role == "foundational"
        assert len(m.technical_components) == 2


class TestDependencyInput:
    def test_creation(self):
        dep = DependencyInput(
            target_item_id="item-002",
            relation="blocks",
        )
        assert dep.target_item_id == "item-002"
        assert dep.dependency_type == "contextual"
        assert dep.confidence == 0.8

    def test_full(self):
        dep = DependencyInput(
            target_item_id="item-003",
            relation="enables",
            dependency_type="structural",
            reasoning="Schema needed first",
            confidence=0.95,
        )
        assert dep.dependency_type == "structural"
        assert dep.confidence == 0.95


class TestSubmitCharacterizationInput:
    def test_minimal(self):
        inp = make_submit_input()
        assert inp.characterization_id == "char-abc123"
        assert inp.evaluated_in_isolation is True
        assert inp.evaluated_in_context is False
        assert inp.dependencies == []

    def test_with_dependencies(self):
        inp = make_submit_input(
            dependencies=[
                DependencyInput(target_item_id="item-002", relation="blocks"),
                DependencyInput(target_item_id="item-003", relation="related_to"),
            ]
        )
        assert len(inp.dependencies) == 2


# =============================================================================
# Tool Execution Tests
# =============================================================================


class TestSubmitCharacterization:
    @pytest.mark.asyncio
    @patch("git.redis_client.get_redis")
    @patch("services.characterization_service.get_characterization_service")
    async def test_success(self, mock_get_service, mock_get_redis):
        mock_service = MagicMock()
        mock_service.store_result = AsyncMock()
        mock_get_service.return_value = mock_service

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        inp = make_submit_input()
        response, error = await submit_characterization(inp)

        assert error is None
        assert response is not None
        assert response.acknowledged is True
        assert response.status == "stored"
        assert response.characterization_id == "char-abc123"
        assert response.item_id == "item-001"

        mock_service.store_result.assert_awaited_once()
        mock_redis.setex.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("git.redis_client.get_redis")
    @patch("services.characterization_service.get_characterization_service")
    async def test_stores_correct_result(self, mock_get_service, mock_get_redis):
        mock_service = MagicMock()
        mock_service.store_result = AsyncMock()
        mock_get_service.return_value = mock_service

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        inp = make_submit_input(confidence=0.92)
        await submit_characterization(inp)

        stored_result = mock_service.store_result.call_args[0][0]
        assert stored_result.item_id == "item-001"
        assert stored_result.project_id == "proj-1"
        assert stored_result.confidence == 0.92
        assert stored_result.status.value == "completed"

    @pytest.mark.asyncio
    @patch("git.redis_client.get_redis")
    @patch("services.characterization_service.get_characterization_service")
    async def test_ontology_conversion(self, mock_get_service, mock_get_redis):
        mock_service = MagicMock()
        mock_service.store_result = AsyncMock()
        mock_get_service.return_value = mock_service
        mock_get_redis.return_value = AsyncMock()

        inp = make_submit_input(
            ontology_tags=OntologyTagsInput(
                work_type="bug_fix",
                lifecycle_stage="test",
                technical_domains=["frontend", "api"],
                cluster_ids=["c1"],
            )
        )
        await submit_characterization(inp)

        stored = mock_service.store_result.call_args[0][0]
        assert stored.ontology_tags.universal.work_type.value == "bug_fix"
        assert stored.ontology_tags.universal.lifecycle_stage.value == "test"
        assert len(stored.ontology_tags.universal.technical_domains) == 2
        assert stored.ontology_tags.project_specific.cluster_ids == ["c1"]

    @pytest.mark.asyncio
    @patch("git.redis_client.get_redis")
    @patch("services.characterization_service.get_characterization_service")
    async def test_invalid_enum_fallback(self, mock_get_service, mock_get_redis):
        """Invalid enum values should fall back to defaults."""
        mock_service = MagicMock()
        mock_service.store_result = AsyncMock()
        mock_get_service.return_value = mock_service
        mock_get_redis.return_value = AsyncMock()

        inp = make_submit_input(
            ontology_tags=OntologyTagsInput(
                work_type="invalid_type",
                lifecycle_stage="invalid_stage",
                technical_domains=["invalid_domain"],
            ),
            meaning=MeaningInput(
                business_summary="Test",
                technical_summary="Test",
                contextual_role="invalid_role",
            ),
        )
        await submit_characterization(inp)

        stored = mock_service.store_result.call_args[0][0]
        # Should fall back to defaults
        assert stored.ontology_tags.universal.work_type.value == "feature"
        assert stored.ontology_tags.universal.lifecycle_stage.value == "build"
        assert stored.ontology_tags.universal.technical_domains[0].value == "backend"
        assert stored.meaning.contextual.role.value == "incremental"

    @pytest.mark.asyncio
    @patch("git.redis_client.get_redis")
    @patch("services.characterization_service.get_characterization_service")
    async def test_dependency_conversion(self, mock_get_service, mock_get_redis):
        mock_service = MagicMock()
        mock_service.store_result = AsyncMock()
        mock_get_service.return_value = mock_service
        mock_get_redis.return_value = AsyncMock()

        inp = make_submit_input(
            dependencies=[
                DependencyInput(
                    target_item_id="item-002",
                    relation="blocks",
                    dependency_type="structural",
                    reasoning="Schema first",
                    confidence=0.95,
                ),
                DependencyInput(
                    target_item_id="item-003",
                    relation="related_to",
                    dependency_type="contextual",
                ),
            ]
        )
        await submit_characterization(inp)

        stored = mock_service.store_result.call_args[0][0]
        assert len(stored.dependencies) == 2
        assert stored.dependencies[0].relation.value == "blocks"
        assert stored.dependencies[0].dependency_type.value == "structural"
        assert stored.dependencies[1].relation.value == "related_to"

    @pytest.mark.asyncio
    @patch("git.redis_client.get_redis")
    @patch("services.characterization_service.get_characterization_service")
    async def test_invalid_dependency_fallback(self, mock_get_service, mock_get_redis):
        mock_service = MagicMock()
        mock_service.store_result = AsyncMock()
        mock_get_service.return_value = mock_service
        mock_get_redis.return_value = AsyncMock()

        inp = make_submit_input(
            dependencies=[
                DependencyInput(
                    target_item_id="item-002",
                    relation="invalid_relation",
                    dependency_type="invalid_type",
                ),
            ]
        )
        await submit_characterization(inp)

        stored = mock_service.store_result.call_args[0][0]
        assert stored.dependencies[0].relation.value == "related_to"
        assert stored.dependencies[0].dependency_type.value == "contextual"

    @pytest.mark.asyncio
    @patch("git.redis_client.get_redis")
    @patch("services.characterization_service.get_characterization_service")
    async def test_redis_completion_signal(self, mock_get_service, mock_get_redis):
        mock_service = MagicMock()
        mock_service.store_result = AsyncMock()
        mock_get_service.return_value = mock_service

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        inp = make_submit_input(characterization_id="char-xyz789")
        await submit_characterization(inp)

        # Should set completion key with 5-minute TTL
        mock_redis.setex.assert_awaited_once_with(
            "claudevn:characterization_complete:char-xyz789",
            300,
            "1",
        )

    @pytest.mark.asyncio
    @patch("git.redis_client.get_redis")
    @patch("services.characterization_service.get_characterization_service")
    async def test_service_error_returns_mcp_error(self, mock_get_service, mock_get_redis):
        mock_service = MagicMock()
        mock_service.store_result = AsyncMock(side_effect=Exception("Redis down"))
        mock_get_service.return_value = mock_service
        mock_get_redis.return_value = AsyncMock()

        inp = make_submit_input()
        response, error = await submit_characterization(inp)

        assert response is None
        assert error is not None
        assert error.code == "INTERNAL_ERROR"
        assert "Redis down" in error.message

    @pytest.mark.asyncio
    @patch("git.redis_client.get_redis")
    @patch("services.characterization_service.get_characterization_service")
    async def test_meaning_conversion(self, mock_get_service, mock_get_redis):
        mock_service = MagicMock()
        mock_service.store_result = AsyncMock()
        mock_get_service.return_value = mock_service
        mock_get_redis.return_value = AsyncMock()

        inp = make_submit_input(
            meaning=MeaningInput(
                business_summary="Revenue growth",
                business_user_impact="Better UX",
                business_value="$100k ARR",
                technical_summary="New microservice",
                technical_components=["api", "db", "cache"],
                technical_risk="Medium",
                contextual_summary="Enables billing",
                contextual_role="enabling",
                related_work_summary="Related to payments",
            ),
        )
        await submit_characterization(inp)

        stored = mock_service.store_result.call_args[0][0]
        assert stored.meaning.business.summary == "Revenue growth"
        assert stored.meaning.business.user_impact == "Better UX"
        assert stored.meaning.technical.components_affected == ["api", "db", "cache"]
        assert stored.meaning.contextual.role.value == "enabling"
