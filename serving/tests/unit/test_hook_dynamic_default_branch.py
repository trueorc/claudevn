"""Tests for dynamic default branch support in git hooks.

Unit tests for:
- Pre-receive hook: protects whatever branch HEAD points to
- Post-receive hook: skips events for whatever branch HEAD points to
- Generated hooks in repo_manager.py use the same dynamic approach
- delete_branch protects the actual default branch
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from git.repo_manager import RepoManager

# Paths to hook template files
PRE_RECEIVE_HOOK = Path(__file__).parent.parent.parent / "git" / "hooks" / "pre-receive"
POST_RECEIVE_HOOK = Path(__file__).parent.parent.parent / "git" / "hooks" / "post-receive"


# =============================================================================
# Hook template content tests
# =============================================================================

class TestPreReceiveHookDynamicBranch:
    """Test pre-receive hook uses dynamic default branch detection."""

    def test_hook_uses_symbolic_ref(self):
        """Pre-receive hook should read default branch from git symbolic-ref HEAD."""
        content = PRE_RECEIVE_HOOK.read_text()
        assert "git symbolic-ref HEAD" in content

    def test_hook_has_default_fallback(self):
        """Pre-receive hook should fall back to 'main' if symbolic-ref fails."""
        content = PRE_RECEIVE_HOOK.read_text()
        assert '${DEFAULT_BRANCH:-main}' in content

    def test_hook_does_not_hardcode_main_in_protection(self):
        """Pre-receive hook should not hardcode main/master in branch protection."""
        content = PRE_RECEIVE_HOOK.read_text()
        # The protection block should compare against $DEFAULT_BRANCH, not literals
        assert '"$branch" = "$DEFAULT_BRANCH"' in content
        # Should NOT have the old hardcoded pattern
        assert '"$branch" = "main" ] || [ "$branch" = "master"' not in content

    def test_hook_skip_validation_uses_default_branch(self):
        """Pre-receive hook should skip naming validation for $DEFAULT_BRANCH."""
        content = PRE_RECEIVE_HOOK.read_text()
        # The skip block should use $DEFAULT_BRANCH, not hardcoded main/master
        assert '"$branch" = "$DEFAULT_BRANCH" ] || [ "$branch" = "develop"' in content

    def test_dynamic_protection_blocks_custom_default(self):
        """Simulates hook logic: blocks push to 'develop' when HEAD points to develop."""
        result = subprocess.run(
            ["bash", "-c", '''
                DEFAULT_BRANCH="develop"
                branch="develop"
                CLAUDEVN_ALLOW_MAIN_PUSH="false"
                if [ "$branch" = "$DEFAULT_BRANCH" ]; then
                    if [ "$CLAUDEVN_ALLOW_MAIN_PUSH" != "true" ]; then
                        exit 1
                    fi
                fi
                exit 0
            '''],
            capture_output=True
        )
        assert result.returncode == 1, "Push to custom default branch should be blocked"

    def test_dynamic_protection_allows_non_default(self):
        """Simulates hook logic: allows push to 'main' when HEAD points to 'develop'."""
        result = subprocess.run(
            ["bash", "-c", '''
                DEFAULT_BRANCH="develop"
                branch="main"
                CLAUDEVN_ALLOW_MAIN_PUSH="false"
                if [ "$branch" = "$DEFAULT_BRANCH" ]; then
                    if [ "$CLAUDEVN_ALLOW_MAIN_PUSH" != "true" ]; then
                        exit 1
                    fi
                fi
                exit 0
            '''],
            capture_output=True
        )
        assert result.returncode == 0, "Push to non-default branch should be allowed"

    def test_dynamic_protection_env_override_custom_default(self):
        """CLAUDEVN_ALLOW_MAIN_PUSH=true should allow push to any default branch."""
        result = subprocess.run(
            ["bash", "-c", '''
                DEFAULT_BRANCH="develop"
                branch="develop"
                CLAUDEVN_ALLOW_MAIN_PUSH="true"
                if [ "$branch" = "$DEFAULT_BRANCH" ]; then
                    if [ "$CLAUDEVN_ALLOW_MAIN_PUSH" != "true" ]; then
                        exit 1
                    fi
                fi
                exit 0
            '''],
            capture_output=True
        )
        assert result.returncode == 0, "Env override should allow push to custom default"

    def test_naming_validation_skips_custom_default(self):
        """Naming validation should skip whatever the default branch is."""
        result = subprocess.run(
            ["bash", "-c", '''
                DEFAULT_BRANCH="release"
                branch="release"
                if [ "$branch" = "$DEFAULT_BRANCH" ] || [ "$branch" = "develop" ]; then
                    exit 0  # skipped
                fi
                exit 1  # would fail naming validation
            '''],
            capture_output=True
        )
        assert result.returncode == 0, "Custom default branch should skip naming validation"


class TestPostReceiveHookDynamicBranch:
    """Test post-receive hook uses dynamic default branch detection."""

    def test_hook_uses_symbolic_ref(self):
        """Post-receive hook should read default branch from git symbolic-ref HEAD."""
        content = POST_RECEIVE_HOOK.read_text()
        assert "git symbolic-ref HEAD" in content

    def test_hook_has_default_fallback(self):
        """Post-receive hook should fall back to 'main' if symbolic-ref fails."""
        content = POST_RECEIVE_HOOK.read_text()
        assert '${DEFAULT_BRANCH:-main}' in content

    def test_hook_does_not_hardcode_main_in_skip(self):
        """Post-receive hook should not hardcode main/master in skip logic."""
        content = POST_RECEIVE_HOOK.read_text()
        assert '"$branch" = "$DEFAULT_BRANCH"' in content
        assert '"$branch" = "main" ] || [ "$branch" = "master"' not in content

    def test_dynamic_skip_for_custom_default(self):
        """Simulates hook logic: skips events for 'develop' when HEAD points to develop."""
        result = subprocess.run(
            ["bash", "-c", '''
                DEFAULT_BRANCH="develop"
                branch="develop"
                if [ "$branch" = "$DEFAULT_BRANCH" ]; then
                    exit 0  # skipped (continue in actual hook)
                fi
                exit 1  # would process the event
            '''],
            capture_output=True
        )
        assert result.returncode == 0, "Default branch events should be skipped"

    def test_dynamic_skip_processes_non_default(self):
        """Simulates hook logic: processes events for non-default branches."""
        result = subprocess.run(
            ["bash", "-c", '''
                DEFAULT_BRANCH="develop"
                branch="f/issue_abc123/compute-001"
                if [ "$branch" = "$DEFAULT_BRANCH" ]; then
                    exit 0  # skipped
                fi
                exit 1  # would process the event
            '''],
            capture_output=True
        )
        assert result.returncode == 1, "Non-default branch events should be processed"


# =============================================================================
# Generated hooks tests (repo_manager.py)
# =============================================================================

@pytest.fixture
def repo_manager():
    """Create a RepoManager instance with mocked config."""
    with patch("git.repo_manager.get_config") as mock_config:
        mock_config.return_value.git.repos_path = "/tmp/repos"
        mock_config.return_value.redis.host = "localhost"
        mock_config.return_value.redis.port = 6379
        mock_config.return_value.redis.key_prefix = "claudevn:"
        manager = RepoManager()
    return manager


class TestGeneratedPreReceiveHook:
    """Test _generate_pre_receive_hook uses dynamic default branch."""

    def test_contains_symbolic_ref(self, repo_manager):
        """Generated pre-receive hook should detect default branch dynamically."""
        hook = repo_manager._generate_pre_receive_hook("test-project")
        assert "git symbolic-ref HEAD" in hook

    def test_contains_default_branch_fallback(self, repo_manager):
        """Generated pre-receive hook should fall back to main."""
        hook = repo_manager._generate_pre_receive_hook("test-project")
        assert "${DEFAULT_BRANCH:-main}" in hook

    def test_does_not_hardcode_main_master(self, repo_manager):
        """Generated pre-receive hook should not hardcode main/master protection."""
        hook = repo_manager._generate_pre_receive_hook("test-project")
        assert '"$branch" = "$DEFAULT_BRANCH"' in hook
        assert '"$branch" = "main" ] || [ "$branch" = "master"' not in hook


class TestGeneratedPostReceiveHook:
    """Test _generate_post_receive_hook uses dynamic default branch."""

    def test_contains_symbolic_ref(self, repo_manager):
        """Generated post-receive hook should detect default branch dynamically."""
        config = MagicMock()
        config.redis.host = "localhost"
        config.redis.port = 6379
        config.redis.key_prefix = "claudevn:"

        with patch("git.repo_manager.get_config", return_value=config):
            hook = repo_manager._generate_post_receive_hook("test-project", config)

        assert "git symbolic-ref HEAD" in hook

    def test_does_not_hardcode_main_master(self, repo_manager):
        """Generated post-receive hook should not hardcode main/master skip."""
        config = MagicMock()
        config.redis.host = "localhost"
        config.redis.port = 6379
        config.redis.key_prefix = "claudevn:"

        with patch("git.repo_manager.get_config", return_value=config):
            hook = repo_manager._generate_post_receive_hook("test-project", config)

        assert '"$branch" = "$DEFAULT_BRANCH"' in hook
        assert '"$branch" = "main" ] || [ "$branch" = "master"' not in hook


# =============================================================================
# delete_branch dynamic protection tests
# =============================================================================

class TestDeleteBranchDynamicProtection:
    """Test delete_branch protects the actual default branch."""

    @patch("git.repo_manager.subprocess.run")
    def test_blocks_deletion_of_custom_default(self, mock_run, repo_manager):
        """delete_branch should block deletion of whatever branch is default."""
        # get_default_branch returns "develop"
        mock_run.return_value = MagicMock(returncode=0, stdout="refs/heads/develop\n")

        with patch.object(repo_manager, "_repo_path") as mock_path:
            mock_path.return_value = Path("/tmp/repos/test.git")
            with patch("pathlib.Path.exists", return_value=True):
                with pytest.raises(ValueError, match="Cannot delete protected branch: develop"):
                    repo_manager.delete_branch("test", "develop")

    @patch("git.repo_manager.subprocess.run")
    def test_allows_deletion_of_main_when_not_default(self, mock_run, repo_manager):
        """delete_branch should allow deleting 'main' if default is 'develop'."""
        # First call: get_default_branch → symbolic-ref returns "develop"
        # Second call: get_branch_head → rev-parse returns a commit
        # Third call: git branch -D succeeds
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="refs/heads/develop\n"),  # symbolic-ref
            MagicMock(returncode=0, stdout="abc123\n"),  # rev-parse (branch exists)
            MagicMock(returncode=0, stdout="Deleted branch main\n"),  # branch -D
        ]

        with patch.object(repo_manager, "_repo_path") as mock_path:
            mock_path.return_value = Path("/tmp/repos/test.git")
            with patch("pathlib.Path.exists", return_value=True):
                result = repo_manager.delete_branch("test", "main")

        assert result is True
