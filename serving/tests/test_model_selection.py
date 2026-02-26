"""Unit tests for model selection in WorkOrchestrator (#59).

Tests the _resolve_model_for_skills method that resolves Claude model
from skill preferences, and the end-to-end flow through SSE assignment.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.work_orchestrator import WorkOrchestrator


@pytest.fixture
def orchestrator():
    return WorkOrchestrator(poll_interval=60)


class TestResolveModelForSkills:
    """Tests for _resolve_model_for_skills model resolution logic."""

    @pytest.mark.asyncio
    async def test_no_skills_returns_none(self, orchestrator):
        """No skills → None (use default Sonnet)."""
        result = await orchestrator._resolve_model_for_skills([])
        assert result is None

    @pytest.mark.asyncio
    async def test_skills_without_preference_returns_none(self, orchestrator):
        """Skills with no preferred_model → None."""
        orchestrator._set_cached_skill("doc-writer", {
            "id": "doc-writer",
            "name": "Doc Writer",
            "instructions": "Write docs",
        })
        result = await orchestrator._resolve_model_for_skills(["doc-writer"])
        assert result is None

    @pytest.mark.asyncio
    async def test_single_skill_with_opus(self, orchestrator):
        """Skill with preferred_model=opus → Opus model ID."""
        orchestrator._set_cached_skill("code-writer", {
            "id": "code-writer",
            "name": "Code Writer",
            "instructions": "Write code",
            "preferred_model": "opus",
        })
        result = await orchestrator._resolve_model_for_skills(["code-writer"])
        assert result == "claude-opus-4-20250514"

    @pytest.mark.asyncio
    async def test_single_skill_with_sonnet(self, orchestrator):
        """Skill with preferred_model=sonnet → Sonnet model ID."""
        orchestrator._set_cached_skill("test-automator", {
            "id": "test-automator",
            "name": "Test Automator",
            "instructions": "Write tests",
            "preferred_model": "sonnet",
        })
        result = await orchestrator._resolve_model_for_skills(["test-automator"])
        assert result == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_single_skill_with_haiku(self, orchestrator):
        """Skill with preferred_model=haiku → Haiku model ID."""
        orchestrator._set_cached_skill("git-ops", {
            "id": "git-ops",
            "name": "Git Operations",
            "instructions": "Do git stuff",
            "preferred_model": "haiku",
        })
        result = await orchestrator._resolve_model_for_skills(["git-ops"])
        assert result == "claude-3-5-haiku-20241022"

    @pytest.mark.asyncio
    async def test_mixed_skills_picks_highest_priority(self, orchestrator):
        """Multiple skills with different models → highest priority (Opus) wins."""
        orchestrator._set_cached_skill("code-writer", {
            "id": "code-writer",
            "preferred_model": "opus",
        })
        orchestrator._set_cached_skill("doc-writer", {
            "id": "doc-writer",
            "preferred_model": "sonnet",
        })
        result = await orchestrator._resolve_model_for_skills(["code-writer", "doc-writer"])
        assert result == "claude-opus-4-20250514"

    @pytest.mark.asyncio
    async def test_mixed_with_none_preferences(self, orchestrator):
        """Skills with and without preferences → non-None preference wins."""
        orchestrator._set_cached_skill("code-writer", {
            "id": "code-writer",
            "preferred_model": "opus",
        })
        orchestrator._set_cached_skill("doc-writer", {
            "id": "doc-writer",
            # No preferred_model
        })
        result = await orchestrator._resolve_model_for_skills(["code-writer", "doc-writer"])
        assert result == "claude-opus-4-20250514"

    @pytest.mark.asyncio
    async def test_case_insensitive(self, orchestrator):
        """Model names are case-insensitive."""
        orchestrator._set_cached_skill("code-writer", {
            "id": "code-writer",
            "preferred_model": "Opus",
        })
        result = await orchestrator._resolve_model_for_skills(["code-writer"])
        assert result == "claude-opus-4-20250514"

    @pytest.mark.asyncio
    async def test_uncached_skill_fetched_from_marketplace(self, orchestrator):
        """Skills not in cache are fetched from marketplace client."""
        mock_client = AsyncMock()
        mock_client.get_skill.return_value = {
            "id": "code-writer",
            "name": "Code Writer",
            "preferred_model": "opus",
        }

        with patch(
            "services.marketplace_client.get_marketplace_client",
            return_value=mock_client,
        ):
            result = await orchestrator._resolve_model_for_skills(["code-writer"])

        assert result == "claude-opus-4-20250514"
        mock_client.get_skill.assert_called_once_with("code-writer")

    @pytest.mark.asyncio
    async def test_marketplace_fetch_failure_skips_skill(self, orchestrator):
        """If marketplace fetch fails, skill is skipped gracefully."""
        with patch(
            "services.marketplace_client.get_marketplace_client",
            side_effect=Exception("connection refused"),
        ):
            result = await orchestrator._resolve_model_for_skills(["unknown-skill"])

        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_model_name_returns_none(self, orchestrator):
        """Unrecognized model name → None (falls through priority map)."""
        orchestrator._set_cached_skill("custom-skill", {
            "id": "custom-skill",
            "preferred_model": "gpt-4",  # Not a valid Claude model name
        })
        result = await orchestrator._resolve_model_for_skills(["custom-skill"])
        assert result is None
