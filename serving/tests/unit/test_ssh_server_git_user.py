"""Unit tests for SSH server git user creation (issue #712)."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from git.ssh_server import SSHServer


@pytest.fixture
def git_config(tmp_path):
    """Create a minimal GitConfig mock."""
    config = MagicMock()
    config.ssh_keys_path = str(tmp_path / "ssh_keys")
    config.repos_path = str(tmp_path / "repos")
    config.git_user = "git"
    return config


@pytest.fixture
def ssh_server(git_config):
    """Create an SSHServer with a mock config."""
    with patch("git.ssh_server.get_config") as mock_get_config:
        mock_get_config.return_value.git = git_config
        server = SSHServer(config=git_config)
    return server


class TestEnsureGitUser:
    """Tests for _ensure_git_user method."""

    def test_user_already_exists(self, ssh_server):
        """Test that no action is taken if the git user already exists."""
        mock_pwnam = MagicMock()

        with patch("pwd.getpwnam", return_value=mock_pwnam) as mock_getpwnam:
            ssh_server._ensure_git_user("/usr/bin/git-shell")

        mock_getpwnam.assert_called_once_with("git")

    def test_user_created_when_missing(self, ssh_server):
        """Test that the git user is created and account unlocked."""
        with patch("pwd.getpwnam", side_effect=KeyError("git")), \
             patch("subprocess.run") as mock_run:
            ssh_server._ensure_git_user("/usr/bin/git-shell")

        assert mock_run.call_count == 2
        mock_run.assert_any_call(
            ["useradd", "-m", "-d", "/home/git", "-s", "/usr/bin/git-shell", "git"],
            check=True,
            capture_output=True,
            text=True
        )
        mock_run.assert_any_call(
            ["usermod", "-p", "*", "git"],
            check=True,
            capture_output=True,
            text=True
        )

    def test_custom_git_user_name(self, git_config):
        """Test that a custom git user name is used and account unlocked."""
        git_config.git_user = "gituser"

        with patch("git.ssh_server.get_config") as mock_get_config:
            mock_get_config.return_value.git = git_config
            server = SSHServer(config=git_config)

        with patch("pwd.getpwnam", side_effect=KeyError("gituser")), \
             patch("subprocess.run") as mock_run:
            server._ensure_git_user("/usr/bin/git-shell")

        assert mock_run.call_count == 2
        mock_run.assert_any_call(
            ["useradd", "-m", "-d", "/home/gituser", "-s", "/usr/bin/git-shell", "gituser"],
            check=True,
            capture_output=True,
            text=True
        )
        mock_run.assert_any_call(
            ["usermod", "-p", "*", "gituser"],
            check=True,
            capture_output=True,
            text=True
        )

    def test_useradd_failure_handled_gracefully(self, ssh_server):
        """Test that useradd failure doesn't crash the server."""
        with patch("pwd.getpwnam", side_effect=KeyError("git")), \
             patch("subprocess.run", side_effect=subprocess.CalledProcessError(
                 1, "useradd", stderr="Permission denied"
             )):
            # Should not raise
            ssh_server._ensure_git_user("/usr/bin/git-shell")

    def test_useradd_not_found_handled(self, ssh_server):
        """Test graceful handling when useradd binary is not found."""
        with patch("pwd.getpwnam", side_effect=KeyError("git")), \
             patch("subprocess.run", side_effect=FileNotFoundError()):
            # Should not raise
            ssh_server._ensure_git_user("/usr/bin/git-shell")


class TestEnsurePrerequisites:
    """Tests for _ensure_prerequisites calling _ensure_git_user."""

    def test_prerequisites_calls_ensure_git_user(self, ssh_server):
        """Test that _ensure_prerequisites calls _ensure_git_user."""
        with patch("shutil.which", side_effect=lambda x: f"/usr/bin/{x}"), \
             patch.object(ssh_server, "_ensure_git_user") as mock_ensure:
            result = ssh_server._ensure_prerequisites()

        assert result is True
        mock_ensure.assert_called_once_with("/usr/bin/git-shell")

    def test_prerequisites_no_sshd(self, ssh_server):
        """Test that missing sshd returns False without calling _ensure_git_user."""
        def which_no_sshd(name):
            if name == "sshd":
                return None
            return f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=which_no_sshd), \
             patch.object(ssh_server, "_ensure_git_user") as mock_ensure:
            result = ssh_server._ensure_prerequisites()

        assert result is False
        mock_ensure.assert_not_called()

    def test_prerequisites_no_git_shell(self, ssh_server):
        """Test that missing git-shell returns False without calling _ensure_git_user."""
        def which_no_git_shell(name):
            if name == "git-shell":
                return None
            return f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=which_no_git_shell), \
             patch.object(ssh_server, "_ensure_git_user") as mock_ensure:
            result = ssh_server._ensure_prerequisites()

        assert result is False
        mock_ensure.assert_not_called()

    def test_prerequisites_creates_authorized_keys(self, ssh_server, tmp_path):
        """Test that prerequisites creates authorized_keys if it doesn't exist."""
        with patch("shutil.which", side_effect=lambda x: f"/usr/bin/{x}"), \
             patch.object(ssh_server, "_ensure_git_user"):
            result = ssh_server._ensure_prerequisites()

        assert result is True
        assert ssh_server._authorized_keys.exists()
