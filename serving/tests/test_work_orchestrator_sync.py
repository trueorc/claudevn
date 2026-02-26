"""Unit tests for pre-clone upstream sync in WorkOrchestrator.

Tests the _sync_project_repo helper that ensures compute instances
clone from the latest upstream state of linked repos.
"""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.work_orchestrator import WorkOrchestrator


@pytest.fixture
def orchestrator():
    return WorkOrchestrator(poll_interval=60)


def _subprocess_result(returncode=0, stdout="", stderr=""):
    """Create a mock subprocess.CompletedProcess."""
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestSyncProjectRepo:
    """Tests for _sync_project_repo pre-clone sync."""

    @patch("config.get_config")
    def test_skips_nonexistent_repo(self, mock_config, orchestrator, tmp_path):
        """No-op if the bare repo directory doesn't exist."""
        mock_config.return_value.git.repos_path = str(tmp_path / "repos")

        with patch("subprocess.run") as mock_run:
            orchestrator._sync_project_repo("nonexistent")
            mock_run.assert_not_called()

    @patch("config.get_config")
    def test_skips_internal_repos(self, mock_config, orchestrator, tmp_path):
        """Internal repos (not linked) should skip sync."""
        repos_dir = tmp_path / "repos"
        repo_path = repos_dir / "test-project.git"
        repo_path.mkdir(parents=True)
        mock_config.return_value.git.repos_path = str(repos_dir)

        with patch("subprocess.run", return_value=_subprocess_result(returncode=1)):
            with patch("git.repo_manager.RepoManager") as MockRM:
                orchestrator._sync_project_repo("test-project")
                MockRM.assert_not_called()

    @patch("config.get_config")
    def test_syncs_linked_repo_with_ssh_key(self, mock_config, orchestrator, tmp_path):
        """Linked repos with SSH key should pull with auth."""
        repos_dir = tmp_path / "repos"
        repo_path = repos_dir / "test-project.git"
        repo_path.mkdir(parents=True)
        mock_config.return_value.git.repos_path = str(repos_dir)

        # Subprocess calls: isLinked -> true, sshKeyId -> key
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _subprocess_result(returncode=0, stdout="true\n"),
                _subprocess_result(returncode=0, stdout="sshk_abc123\n"),
            ]

            mock_rm = MagicMock()
            with patch("git.repo_manager.RepoManager", return_value=mock_rm):
                with patch("git.ssh_key_service.get_ssh_key_service") as mock_sks:
                    mock_service = MagicMock()
                    key_path = MagicMock()
                    key_path.exists.return_value = True
                    key_path.__str__ = lambda s: "/keys/sshk_abc123"
                    mock_service._private_key_path.return_value = key_path
                    mock_sks.return_value = mock_service

                    orchestrator._sync_project_repo("test-project")

            mock_rm.pull_from_origin.assert_called_once_with(
                "test-project", ssh_key_path="/keys/sshk_abc123"
            )

    @patch("config.get_config")
    def test_syncs_linked_repo_without_ssh_key(self, mock_config, orchestrator, tmp_path):
        """Linked repos without SSH key should still sync."""
        repos_dir = tmp_path / "repos"
        repo_path = repos_dir / "test-project.git"
        repo_path.mkdir(parents=True)
        mock_config.return_value.git.repos_path = str(repos_dir)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _subprocess_result(returncode=0, stdout="true\n"),
                _subprocess_result(returncode=1, stdout=""),  # no SSH key
            ]

            mock_rm = MagicMock()
            with patch("git.repo_manager.RepoManager", return_value=mock_rm):
                orchestrator._sync_project_repo("test-project")

            mock_rm.pull_from_origin.assert_called_once_with(
                "test-project", ssh_key_path=None
            )

    @patch("config.get_config")
    def test_sync_failure_is_non_fatal(self, mock_config, orchestrator, tmp_path):
        """Sync failure should log warning but not raise."""
        repos_dir = tmp_path / "repos"
        repo_path = repos_dir / "test-project.git"
        repo_path.mkdir(parents=True)
        mock_config.return_value.git.repos_path = str(repos_dir)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _subprocess_result(returncode=0, stdout="true\n"),
                _subprocess_result(returncode=1, stdout=""),
            ]

            mock_rm = MagicMock()
            mock_rm.pull_from_origin.side_effect = subprocess.CalledProcessError(
                128, ["git", "fetch"], "", "connection refused"
            )
            with patch("git.repo_manager.RepoManager", return_value=mock_rm):
                # Should NOT raise
                orchestrator._sync_project_repo("test-project")


class TestSpawnForWorkSync:
    """Tests that _spawn_for_work calls _sync_project_repo."""

    @pytest.mark.asyncio
    async def test_spawn_syncs_before_assignment(self, orchestrator):
        """_spawn_for_work should sync the project repo before spawning."""
        work = MagicMock()
        work.work_id = "work-001"
        work.title = "Test work"
        work.project_id = "test-project"

        with patch.object(orchestrator, "_sync_project_repo") as mock_sync:
            with patch.object(orchestrator, "_select_skills_for_work", return_value=[]):
                with patch.object(orchestrator, "_try_assign_via_sse", return_value=True):
                    with patch(
                        "services.sse_connection_manager.get_sse_connection_manager"
                    ) as mock_sse:
                        mock_sse.return_value.list_connections.return_value = ["c1"]
                        await orchestrator._spawn_for_work(work)

        mock_sync.assert_called_once_with("test-project")

    @pytest.mark.asyncio
    async def test_spawn_skips_sync_when_no_project_id(self, orchestrator):
        """_spawn_for_work should skip sync if work has no project_id."""
        work = MagicMock()
        work.work_id = "work-002"
        work.title = "Test work"
        work.project_id = None

        with patch.object(orchestrator, "_sync_project_repo") as mock_sync:
            with patch.object(orchestrator, "_select_skills_for_work", return_value=[]):
                with patch.object(orchestrator, "_try_assign_via_sse", return_value=True):
                    with patch(
                        "services.sse_connection_manager.get_sse_connection_manager"
                    ) as mock_sse:
                        mock_sse.return_value.list_connections.return_value = ["c1"]
                        await orchestrator._spawn_for_work(work)

        mock_sync.assert_not_called()
