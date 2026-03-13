"""Unit tests for LeadComputeService.

Tests PR review dispatch, timeout handling, and graceful degradation.
All external services (SSE, Redis, MCP) are mocked.
"""

import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.lead_compute_service import (
    LeadComputeService,
    LeadReviewResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def service():
    return LeadComputeService(timeout=5)


@pytest.fixture
def disabled_service():
    svc = LeadComputeService(timeout=5)
    svc.enabled = False
    return svc


# ---------------------------------------------------------------------------
# LeadReviewResult
# ---------------------------------------------------------------------------

class TestLeadReviewResult:
    def test_to_dict(self):
        result = LeadReviewResult(
            approved=False,
            reviewer_id="compute-1",
            summary="Found issues",
            issues=[{"severity": "error", "file": "main.py", "message": "Bad import"}],
        )
        d = result.to_dict()
        assert d["approved"] is False
        assert d["reviewer_id"] == "compute-1"
        assert len(d["issues"]) == 1

    def test_defaults(self):
        result = LeadReviewResult(approved=True, reviewer_id="test")
        assert result.summary == ""
        assert result.issues == []


# ---------------------------------------------------------------------------
# Disabled service
# ---------------------------------------------------------------------------

class TestDisabledService:
    @pytest.mark.asyncio
    async def test_returns_approved_when_disabled(self, disabled_service):
        result = await disabled_service.review_pr(
            project="myproject",
            branch="f/issue-1/compute-1",
            compute_id="compute-1",
        )
        assert result.approved is True
        assert result.reviewer_id == "lead-review-disabled"


# ---------------------------------------------------------------------------
# Review context building
# ---------------------------------------------------------------------------

class TestBuildReviewContext:
    def test_context_contains_project_and_branch(self, service):
        ctx = service._build_review_context(
            review_id="rev-123",
            project="myproject",
            branch="f/issue-1/compute-1",
            work_title="Add auth",
            work_description="Implement JWT auth",
        )
        assert "myproject" in ctx
        assert "f/issue-1/compute-1" in ctx
        assert "Add auth" in ctx
        assert "Implement JWT auth" in ctx
        assert "rev-123" in ctx

    def test_context_no_description(self, service):
        ctx = service._build_review_context(
            review_id="rev-123",
            project="proj",
            branch="b",
        )
        assert "No description provided" in ctx


# ---------------------------------------------------------------------------
# No compute available
# ---------------------------------------------------------------------------

class TestNoComputeAvailable:
    @pytest.mark.asyncio
    async def test_auto_approves_when_no_compute(self, service):
        mock_sse = MagicMock()
        mock_sse.find_matching_connection = MagicMock(return_value=None)

        mock_completion = MagicMock()
        mock_completion.create_event = MagicMock()
        mock_completion.get_event = MagicMock()
        mock_completion.cleanup = MagicMock()

        mock_mods = {
            "services.completion_events": mock_completion,
            "services.sse_connection_manager": MagicMock(
                get_sse_connection_manager=MagicMock(return_value=mock_sse)
            ),
        }

        with patch.dict(sys.modules, mock_mods):
            result = await service.review_pr(
                project="proj",
                branch="b",
                compute_id="c1",
            )

        assert result.approved is True
        assert "no-reviewer-available" in result.reviewer_id.lower() or "no" in result.reviewer_id


# ---------------------------------------------------------------------------
# Dispatch failure
# ---------------------------------------------------------------------------

class TestDispatchFailure:
    @pytest.mark.asyncio
    async def test_auto_approves_on_dispatch_error(self, service):
        """If dispatching review fails entirely, auto-approve."""
        mock_completion = MagicMock()
        mock_completion.create_event = MagicMock(side_effect=Exception("event system down"))
        mock_completion.cleanup = MagicMock()

        mock_mods = {
            "services.completion_events": mock_completion,
        }

        with patch.dict(sys.modules, mock_mods):
            result = await service.review_pr(
                project="proj",
                branch="b",
                compute_id="c1",
            )

        assert result.approved is True


# ---------------------------------------------------------------------------
# Successful review
# ---------------------------------------------------------------------------

class TestSuccessfulReview:
    @pytest.mark.asyncio
    async def test_approved_review(self, service):
        """Test a full successful review flow."""
        mock_event = asyncio.Event()
        mock_event.set()  # Pre-set so wait() returns immediately

        mock_connection = MagicMock()
        mock_connection.compute_id = "reviewer-1"

        mock_sse = MagicMock()
        mock_sse.find_matching_connection = MagicMock(return_value=mock_connection)
        mock_sse.send_work_assigned = AsyncMock(return_value=True)

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps({
            "approved": True,
            "summary": "LGTM",
            "issues": [],
        }))

        mock_mods = {
            "services.completion_events": MagicMock(
                create_event=MagicMock(),
                get_event=MagicMock(return_value=mock_event),
                cleanup=MagicMock(),
            ),
            "services.sse_connection_manager": MagicMock(
                get_sse_connection_manager=MagicMock(return_value=mock_sse),
            ),
            "services.marketplace_client": MagicMock(
                get_marketplace_client=MagicMock(side_effect=Exception("skip")),
            ),
            "mcp.auth": MagicMock(
                generate_api_key=MagicMock(return_value="key-123"),
                register_compute_key=AsyncMock(),
            ),
            "git.redis_client": MagicMock(
                get_redis=AsyncMock(return_value=mock_redis),
            ),
        }

        with patch.dict(sys.modules, mock_mods):
            result = await service.review_pr(
                project="proj",
                branch="b",
                compute_id="author-1",
            )

        assert result.approved is True
        assert result.reviewer_id == "reviewer-1"
        assert result.summary == "LGTM"

    @pytest.mark.asyncio
    async def test_rejected_review(self, service):
        """Test a review that rejects the PR."""
        mock_event = asyncio.Event()
        mock_event.set()

        mock_connection = MagicMock()
        mock_connection.compute_id = "reviewer-1"

        mock_sse = MagicMock()
        mock_sse.find_matching_connection = MagicMock(return_value=mock_connection)
        mock_sse.send_work_assigned = AsyncMock(return_value=True)

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps({
            "approved": False,
            "summary": "Missing DB migration",
            "issues": [{"severity": "error", "file": "models.py", "message": "No migration"}],
        }))

        mock_mods = {
            "services.completion_events": MagicMock(
                create_event=MagicMock(),
                get_event=MagicMock(return_value=mock_event),
                cleanup=MagicMock(),
            ),
            "services.sse_connection_manager": MagicMock(
                get_sse_connection_manager=MagicMock(return_value=mock_sse),
            ),
            "services.marketplace_client": MagicMock(
                get_marketplace_client=MagicMock(side_effect=Exception("skip")),
            ),
            "mcp.auth": MagicMock(
                generate_api_key=MagicMock(return_value="key-123"),
                register_compute_key=AsyncMock(),
            ),
            "git.redis_client": MagicMock(
                get_redis=AsyncMock(return_value=mock_redis),
            ),
        }

        with patch.dict(sys.modules, mock_mods):
            result = await service.review_pr(
                project="proj",
                branch="b",
                compute_id="author-1",
            )

        assert result.approved is False
        assert result.reviewer_id == "reviewer-1"
        assert len(result.issues) == 1
