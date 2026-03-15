"""Unit tests for WorkContextEnrichmentService.

Tests context enrichment with goal, dependency, sibling, and project info.
All external services are mocked.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.work_context_enrichment_service import WorkContextEnrichmentService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def service():
    return WorkContextEnrichmentService()


@pytest.fixture
def base_context():
    return {
        "task_type": "execution",
        "goal_id": "goal-123",
        "issue_id": "issue-456",
        "repo_url": "http://serving:8002/repos/myproject",
    }


def _mock_goal(title="Build auth", description="Implement authentication", intent_type=None):
    goal = MagicMock()
    goal.title = title
    goal.description = description
    goal.intent_type = intent_type
    return goal


def _mock_work(work_id, title="Some work", status_val="pending", depends_on=None, blocks=None):
    work = MagicMock()
    work.work_id = work_id
    work.title = title
    work.status.value = status_val
    work.depends_on = depends_on or []
    work.blocks = blocks or []
    return work


def _mock_issue(issue_id, title="Some issue", status_val="ready", area_val="api"):
    issue = MagicMock()
    issue.issue_id = issue_id
    issue.title = title
    issue.status.value = status_val
    issue.area.value = area_val
    return issue


def _patch_service_module(service_name, mock_getter):
    """Create a mock module that provides the getter function.

    The enrichment service does `from services.X import get_X` inside methods.
    We need to ensure the module exists in sys.modules with the getter.
    """
    module_name = f"services.{service_name}"
    mock_module = MagicMock()
    setattr(mock_module, f"get_{service_name}", mock_getter)
    return patch.dict(sys.modules, {module_name: mock_module})


# ---------------------------------------------------------------------------
# Goal context
# ---------------------------------------------------------------------------

class TestGoalContext:
    @pytest.mark.asyncio
    async def test_goal_context_included(self, service, base_context):
        mock_goal_svc = MagicMock()
        mock_goal_svc.get_goal = AsyncMock(return_value=_mock_goal())

        mock_mod = MagicMock()
        mock_mod.get_goal_service = MagicMock(return_value=mock_goal_svc)

        with patch.dict(sys.modules, {"services.goal_service": mock_mod}):
            result = await service._get_goal_context(base_context)

        assert result is not None
        assert result["goal_title"] == "Build auth"
        assert "Implement authentication" in result["goal_description"]

    @pytest.mark.asyncio
    async def test_no_goal_id(self, service):
        result = await service._get_goal_context({})
        assert result is None

    @pytest.mark.asyncio
    async def test_goal_not_found(self, service, base_context):
        mock_goal_svc = MagicMock()
        mock_goal_svc.get_goal = AsyncMock(return_value=None)
        mock_mod = MagicMock()
        mock_mod.get_goal_service = MagicMock(return_value=mock_goal_svc)

        with patch.dict(sys.modules, {"services.goal_service": mock_mod}):
            result = await service._get_goal_context(base_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_goal_service_error(self, service, base_context):
        mock_mod = MagicMock()
        mock_mod.get_goal_service = MagicMock(side_effect=Exception("DB error"))

        with patch.dict(sys.modules, {"services.goal_service": mock_mod}):
            result = await service._get_goal_context(base_context)
        assert result is None


# ---------------------------------------------------------------------------
# Dependency context
# ---------------------------------------------------------------------------

class TestDependencyContext:
    @pytest.mark.asyncio
    async def test_depends_on_included(self, service):
        main_work = _mock_work("w-1", depends_on=["w-0"], blocks=[])
        dep_work = _mock_work("w-0", title="Setup DB")

        mock_wm_svc = MagicMock()
        mock_wm_svc.get_work = AsyncMock(side_effect=lambda wid: {
            "w-1": main_work, "w-0": dep_work
        }.get(wid))
        mock_mod = MagicMock()
        mock_mod.get_work_map_service = MagicMock(return_value=mock_wm_svc)

        with patch.dict(sys.modules, {"services.work_map_service": mock_mod}):
            result = await service._get_dependency_context("w-1")

        assert result is not None
        assert len(result["depends_on"]) == 1
        assert result["depends_on"][0]["title"] == "Setup DB"

    @pytest.mark.asyncio
    async def test_blocks_included(self, service):
        main_work = _mock_work("w-1", depends_on=[], blocks=["w-2"])
        blocked_work = _mock_work("w-2", title="Frontend")

        mock_wm_svc = MagicMock()
        mock_wm_svc.get_work = AsyncMock(side_effect=lambda wid: {
            "w-1": main_work, "w-2": blocked_work
        }.get(wid))
        mock_mod = MagicMock()
        mock_mod.get_work_map_service = MagicMock(return_value=mock_wm_svc)

        with patch.dict(sys.modules, {"services.work_map_service": mock_mod}):
            result = await service._get_dependency_context("w-1")

        assert result is not None
        assert result["blocks"][0]["title"] == "Frontend"

    @pytest.mark.asyncio
    async def test_no_dependencies(self, service):
        work = _mock_work("w-1")
        mock_wm_svc = MagicMock()
        mock_wm_svc.get_work = AsyncMock(return_value=work)
        mock_mod = MagicMock()
        mock_mod.get_work_map_service = MagicMock(return_value=mock_wm_svc)

        with patch.dict(sys.modules, {"services.work_map_service": mock_mod}):
            result = await service._get_dependency_context("w-1")
        assert result is None


# ---------------------------------------------------------------------------
# Sibling context
# ---------------------------------------------------------------------------

class TestSiblingContext:
    @pytest.mark.asyncio
    async def test_siblings_included(self, service, base_context):
        issues = [
            _mock_issue("issue-456", title="Current issue"),
            _mock_issue("issue-789", title="Sibling issue"),
        ]
        mock_is_svc = MagicMock()
        mock_is_svc.list_issues = AsyncMock(return_value=issues)
        mock_mod = MagicMock()
        mock_mod.get_issue_service = MagicMock(return_value=mock_is_svc)

        with patch.dict(sys.modules, {"services.issue_service": mock_mod}):
            result = await service._get_sibling_context(base_context)

        assert result is not None
        assert len(result) == 1
        assert result[0]["title"] == "Sibling issue"

    @pytest.mark.asyncio
    async def test_no_goal_id(self, service):
        result = await service._get_sibling_context({})
        assert result is None

    @pytest.mark.asyncio
    async def test_only_self(self, service, base_context):
        issues = [_mock_issue("issue-456", title="Only me")]
        mock_is_svc = MagicMock()
        mock_is_svc.list_issues = AsyncMock(return_value=issues)
        mock_mod = MagicMock()
        mock_mod.get_issue_service = MagicMock(return_value=mock_is_svc)

        with patch.dict(sys.modules, {"services.issue_service": mock_mod}):
            result = await service._get_sibling_context(base_context)
        assert result is None


# ---------------------------------------------------------------------------
# Full enrichment
# ---------------------------------------------------------------------------

class TestFullEnrichment:
    @pytest.mark.asyncio
    async def test_enrichment_adds_all_sections(self, service, base_context):
        mock_goal_svc = MagicMock()
        mock_goal_svc.get_goal = AsyncMock(return_value=_mock_goal())

        main_work = _mock_work("w-1", depends_on=["w-0"])
        dep_work = _mock_work("w-0", title="Setup DB")
        mock_wm_svc = MagicMock()
        mock_wm_svc.get_work = AsyncMock(side_effect=lambda wid: {
            "w-1": main_work, "w-0": dep_work
        }.get(wid))

        issues = [_mock_issue("issue-456"), _mock_issue("issue-789", title="Sibling")]
        mock_is_svc = MagicMock()
        mock_is_svc.list_issues = AsyncMock(return_value=issues)

        mock_project = MagicMock()
        mock_project.tech_stack = "Python, FastAPI"
        mock_project.conventions = "PEP 8"
        mock_project.description = "AI orchestration platform"
        mock_ps_svc = MagicMock()
        mock_ps_svc.get_project = AsyncMock(return_value=mock_project)

        mock_mods = {
            "services.goal_service": MagicMock(get_goal_service=MagicMock(return_value=mock_goal_svc)),
            "services.work_map_service": MagicMock(get_work_map_service=MagicMock(return_value=mock_wm_svc)),
            "services.issue_service": MagicMock(get_issue_service=MagicMock(return_value=mock_is_svc)),
            "services.project_service": MagicMock(get_project_service=MagicMock(return_value=mock_ps_svc)),
        }

        with patch.dict(sys.modules, mock_mods):
            result = await service.enrich(base_context, "w-1", "proj-1")

        assert result["task_type"] == "execution"
        assert "goal_context" in result
        assert "dependency_context" in result
        assert "sibling_issues" in result
        assert "project_context" in result

    @pytest.mark.asyncio
    async def test_enrichment_graceful_on_failures(self, service, base_context):
        """If all service imports fail, enrichment returns original context."""
        mock_mods = {
            "services.goal_service": MagicMock(get_goal_service=MagicMock(side_effect=Exception("fail"))),
            "services.work_map_service": MagicMock(get_work_map_service=MagicMock(side_effect=Exception("fail"))),
            "services.issue_service": MagicMock(get_issue_service=MagicMock(side_effect=Exception("fail"))),
            "services.project_service": MagicMock(get_project_service=MagicMock(side_effect=Exception("fail"))),
        }

        with patch.dict(sys.modules, mock_mods):
            result = await service.enrich(base_context, "w-1", "proj-1")

        assert result["task_type"] == "execution"
        assert "goal_context" not in result

    @pytest.mark.asyncio
    async def test_original_context_not_mutated(self, service, base_context):
        original = dict(base_context)

        mock_goal_svc = MagicMock()
        mock_goal_svc.get_goal = AsyncMock(return_value=_mock_goal())
        mock_mods = {
            "services.goal_service": MagicMock(get_goal_service=MagicMock(return_value=mock_goal_svc)),
            "services.work_map_service": MagicMock(get_work_map_service=MagicMock(side_effect=Exception)),
            "services.issue_service": MagicMock(get_issue_service=MagicMock(side_effect=Exception)),
            "services.project_service": MagicMock(get_project_service=MagicMock(side_effect=Exception)),
        }

        with patch.dict(sys.modules, mock_mods):
            result = await service.enrich(base_context, "w-1", "proj-1")

        assert base_context == original
        assert "goal_context" in result
        assert "goal_context" not in base_context
