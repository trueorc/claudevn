"""Unit tests for _push_upstream branch status updates in PRService.

Validates that set_branch_status() calls include the required 'status' argument.
Regression tests for issue #52.
"""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from git.pr_service import PRService, PRStatus, PullRequest


@pytest.fixture
def mock_repo_manager():
    manager = MagicMock()
    manager.get_default_branch.return_value = "main"
    return manager


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.set_branch_status = AsyncMock()
    redis.publish_git_event = AsyncMock()
    return redis


@pytest.fixture
def mock_ssh_key_service():
    service = MagicMock()
    return service


@pytest.fixture
def pr_service(mock_repo_manager, mock_redis, mock_ssh_key_service):
    with patch("git.pr_service.get_config") as mock_config:
        mock_config.return_value.git.repos_path = "/repos"
        mock_config.return_value.redis.host = "localhost"
        mock_config.return_value.redis.port = 6379
        mock_config.return_value.redis.key_prefix = "cvn:"
        service = PRService(
            redis_client=mock_redis,
            repo_manager=mock_repo_manager,
            ssh_key_service=mock_ssh_key_service,
        )
    return service


@pytest.fixture
def sample_pr():
    return PullRequest(
        project="test-project",
        branch="feature-branch",
        status=PRStatus.APPROVED,
        compute_id="compute-001",
        task_id="task-001",
    )


class TestPushUpstreamBranchStatus:
    """Regression tests for #52: set_branch_status missing 'status' arg."""

    @pytest.mark.asyncio
    async def test_push_failure_sets_merged_status(self, pr_service, mock_redis, sample_pr):
        """Push failure path must pass status=merged to set_branch_status."""
        failed_run = MagicMock(returncode=1, stderr="push rejected", stdout="")

        with patch.object(pr_service, "_read_git_config", return_value="true"):
            with patch.object(pr_service, "_resolve_ssh_key_path", return_value=None):
                with patch("git.pr_service.subprocess.run", return_value=failed_run):
                    with patch.object(pr_service, "_get_sse_manager") as mock_sse:
                        mock_sse.return_value.send_event = AsyncMock()
                        result = await pr_service._push_upstream(
                            project="test-project",
                            repo_path=Path("/repos/test-project.git"),
                            default_branch="main",
                            pr=sample_pr,
                            merge_commit="abc123def456",
                        )

        assert result["success"] is False

        mock_redis.set_branch_status.assert_called_once()
        call_kwargs = mock_redis.set_branch_status.call_args.kwargs
        assert call_kwargs["status"] == PRStatus.MERGED.value
        assert call_kwargs["upstream_sync_status"] == "failed"
        assert call_kwargs["upstream_push_error"] == "push rejected"

    @pytest.mark.asyncio
    async def test_push_success_sets_merged_status(self, pr_service, mock_redis, sample_pr):
        """Push success path must pass status=merged to set_branch_status."""
        success_run = MagicMock(returncode=0, stderr="", stdout="")

        with patch.object(pr_service, "_read_git_config", return_value="true"):
            with patch.object(pr_service, "_resolve_ssh_key_path", return_value=None):
                with patch("git.pr_service.subprocess.run", return_value=success_run):
                    result = await pr_service._push_upstream(
                        project="test-project",
                        repo_path=Path("/repos/test-project.git"),
                        default_branch="main",
                        pr=sample_pr,
                        merge_commit="abc123def456",
                    )

        assert result["success"] is True

        mock_redis.set_branch_status.assert_called_once()
        call_kwargs = mock_redis.set_branch_status.call_args.kwargs
        assert call_kwargs["status"] == PRStatus.MERGED.value
        assert call_kwargs["upstream_sync_status"] == "synced"
