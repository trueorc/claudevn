"""Tests for marketplace Git storage service."""

import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
import subprocess

from git_storage import MarketplaceGitStorage, get_git_storage, set_git_storage


@pytest.fixture
def temp_paths(tmp_path):
    """Create temporary paths for repos and worktree."""
    repos_path = tmp_path / "repos"
    worktree_path = tmp_path / "worktrees"
    repos_path.mkdir()
    worktree_path.mkdir()
    return str(repos_path), str(worktree_path)


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run for tests that don't need real Git."""
    with patch('git_storage.subprocess.run') as mock:
        mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
        yield mock


class TestMarketplaceGitStorageInit:
    """Tests for GitStorage initialization."""

    def test_init_sets_paths(self, temp_paths):
        """Test that initialization sets correct paths."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)

        assert storage._repos_path == Path(repos_path)
        assert storage._worktree_base_path == Path(worktree_path)
        assert storage._initialized is False
        assert storage._worktree_path is None

    def test_repo_path(self, temp_paths):
        """Test that repo_path returns correct path."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)

        assert storage._repo_path() == Path(repos_path) / "marketplace.git"


class TestMarketplaceGitStorageRepoOperations:
    """Tests for Git repository operations."""

    def test_repo_exists_false_when_no_repo(self, temp_paths):
        """Test repo_exists returns False when repo doesn't exist."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)

        assert storage._repo_exists() is False

    def test_repo_exists_false_when_no_head(self, temp_paths):
        """Test repo_exists returns False when HEAD doesn't exist."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)

        # Create directory but no HEAD file
        (Path(repos_path) / "marketplace.git").mkdir()

        assert storage._repo_exists() is False

    def test_create_bare_repo(self, temp_paths, mock_subprocess):
        """Test creating a bare Git repository."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)

        storage._create_bare_repo()

        # Verify git init --bare was called
        calls = mock_subprocess.call_args_list
        assert len(calls) == 2
        assert "init" in calls[0][0][0]
        assert "--bare" in calls[0][0][0]

        # Verify symbolic-ref was called to set default branch
        assert "symbolic-ref" in calls[1][0][0]
        assert "refs/heads/main" in calls[1][0][0]


class TestMarketplaceGitStorageWorktreeOperations:
    """Tests for worktree operations."""

    def test_add_worktree(self, temp_paths, mock_subprocess):
        """Test adding a Git worktree."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        storage._worktree_path = Path(worktree_path) / "test-worktree"

        # Create the repo path
        (Path(repos_path) / "marketplace.git").mkdir()

        storage._add_worktree("main", create_branch=False)

        call_args = mock_subprocess.call_args[0][0]
        assert "worktree" in call_args
        assert "add" in call_args
        assert "main" in call_args

    def test_add_worktree_create_branch(self, temp_paths, mock_subprocess):
        """Test adding a worktree with branch creation."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        storage._worktree_path = Path(worktree_path) / "test-worktree"

        (Path(repos_path) / "marketplace.git").mkdir()

        storage._add_worktree("main", create_branch=True)

        call_args = mock_subprocess.call_args[0][0]
        assert "-b" in call_args
        assert "main" in call_args

    def test_remove_worktree(self, temp_paths, mock_subprocess):
        """Test removing a Git worktree."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        storage._worktree_path = Path(worktree_path) / "test-worktree"

        (Path(repos_path) / "marketplace.git").mkdir()

        storage._remove_worktree(force=True)

        call_args = mock_subprocess.call_args[0][0]
        assert "worktree" in call_args
        assert "remove" in call_args
        assert "--force" in call_args


class TestMarketplaceGitStorageDirectories:
    """Tests for directory management."""

    def test_ensure_directories_creates_structure(self, temp_paths):
        """Test that _ensure_directories creates the expected structure."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        storage._worktree_path = wt_path

        storage._ensure_directories()

        assert (wt_path / "skills" / "user").exists()
        assert (wt_path / "personas" / "user").exists()
        assert (wt_path / "archive" / "skills").exists()
        assert (wt_path / "archive" / "personas").exists()

    def test_ensure_directories_raises_without_worktree(self, temp_paths):
        """Test that _ensure_directories raises when worktree not set."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)

        with pytest.raises(RuntimeError, match="Worktree not initialized"):
            storage._ensure_directories()


class TestMarketplaceGitStorageFileOperations:
    """Tests for file operations."""

    def test_save_yaml(self, temp_paths, mock_subprocess):
        """Test saving YAML content."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        storage._worktree_path = wt_path

        # Mock that there are changes to commit
        mock_subprocess.side_effect = [
            MagicMock(returncode=0),  # git add
            MagicMock(returncode=1),  # git diff (changes exist)
            MagicMock(returncode=0),  # git commit
        ]

        result = storage.save_yaml("skills/user/test.yaml", "content: test", "Test commit")

        assert result is True
        assert (wt_path / "skills" / "user" / "test.yaml").exists()
        assert (wt_path / "skills" / "user" / "test.yaml").read_text() == "content: test"

    def test_save_yaml_no_changes(self, temp_paths, mock_subprocess):
        """Test saving YAML when there are no changes."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        storage._worktree_path = wt_path

        # Mock that there are no changes to commit
        mock_subprocess.side_effect = [
            MagicMock(returncode=0),  # git add
            MagicMock(returncode=0),  # git diff (no changes)
        ]

        result = storage.save_yaml("skills/user/test.yaml", "content: test", "Test commit")

        assert result is False

    def test_load_yaml_existing_file(self, temp_paths):
        """Test loading YAML from existing file."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        (wt_path / "skills" / "user").mkdir(parents=True)
        storage._worktree_path = wt_path

        # Create test file
        test_file = wt_path / "skills" / "user" / "test.yaml"
        test_file.write_text("id: test\nname: Test")

        content = storage.load_yaml("skills/user/test.yaml")

        assert content == "id: test\nname: Test"

    def test_load_yaml_nonexistent_file(self, temp_paths):
        """Test loading YAML from nonexistent file."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        storage._worktree_path = wt_path

        content = storage.load_yaml("skills/user/nonexistent.yaml")

        assert content is None

    def test_load_yaml_without_worktree(self, temp_paths):
        """Test loading YAML when worktree not initialized."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)

        content = storage.load_yaml("skills/user/test.yaml")

        assert content is None

    def test_delete_file(self, temp_paths, mock_subprocess):
        """Test deleting a file."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        (wt_path / "skills" / "user").mkdir(parents=True)
        storage._worktree_path = wt_path

        # Create test file
        test_file = wt_path / "skills" / "user" / "test.yaml"
        test_file.write_text("id: test")

        result = storage.delete_file("skills/user/test.yaml", "Delete test")

        assert result is True
        assert not test_file.exists()

    def test_delete_file_nonexistent(self, temp_paths):
        """Test deleting a nonexistent file."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        storage._worktree_path = wt_path

        result = storage.delete_file("skills/user/nonexistent.yaml", "Delete test")

        assert result is False

    def test_file_exists(self, temp_paths):
        """Test checking if file exists."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        (wt_path / "skills" / "user").mkdir(parents=True)
        storage._worktree_path = wt_path

        # Create test file
        test_file = wt_path / "skills" / "user" / "test.yaml"
        test_file.write_text("id: test")

        assert storage.file_exists("skills/user/test.yaml") is True
        assert storage.file_exists("skills/user/nonexistent.yaml") is False

    def test_list_files(self, temp_paths):
        """Test listing files in a directory."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        (wt_path / "skills" / "user").mkdir(parents=True)
        storage._worktree_path = wt_path

        # Create test files
        (wt_path / "skills" / "user" / "skill1.yaml").write_text("id: skill1")
        (wt_path / "skills" / "user" / "skill2.yaml").write_text("id: skill2")
        (wt_path / "skills" / "user" / "readme.txt").write_text("readme")

        files = storage.list_files("skills/user")

        assert len(files) == 2
        file_names = [f.name for f in files]
        assert "skill1.yaml" in file_names
        assert "skill2.yaml" in file_names
        assert "readme.txt" not in file_names


class TestMarketplaceGitStorageHistory:
    """Tests for Git history operations."""

    def test_get_file_history(self, temp_paths, mock_subprocess):
        """Test getting file history."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        storage._worktree_path = wt_path

        # Mock git log output
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout="abc123|author|1706745600|create: skill-1 v1.0.0"
        )

        history = storage.get_file_history("skills/user/skill-1.yaml")

        assert len(history) == 1
        assert history[0]["commit"] == "abc123"
        assert history[0]["author"] == "author"
        assert history[0]["message"] == "create: skill-1 v1.0.0"

    def test_get_file_at_commit(self, temp_paths, mock_subprocess):
        """Test getting file at specific commit."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        storage._worktree_path = wt_path

        # Mock git show output
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout="id: test\nversion: 1.0.0"
        )

        content = storage.get_file_at_commit("skills/user/test.yaml", "abc123")

        assert content == "id: test\nversion: 1.0.0"

    def test_get_file_at_commit_not_found(self, temp_paths, mock_subprocess):
        """Test getting file at commit when not found."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        storage._worktree_path = wt_path

        # Mock git show failure
        mock_subprocess.return_value = MagicMock(returncode=128, stdout="")

        content = storage.get_file_at_commit("skills/user/test.yaml", "abc123")

        assert content is None


class TestMarketplaceGitStorageGlobalInstance:
    """Tests for global instance management."""

    def test_get_git_storage_not_initialized(self):
        """Test that get_git_storage raises when not initialized."""
        # Reset global state
        import git_storage
        git_storage._git_storage = None

        with pytest.raises(RuntimeError, match="Git storage not initialized"):
            get_git_storage()

    def test_set_and_get_git_storage(self, temp_paths):
        """Test setting and getting global git storage."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)

        set_git_storage(storage)
        retrieved = get_git_storage()

        assert retrieved is storage

        # Clean up
        import git_storage
        git_storage._git_storage = None


class TestMarketplaceGitStorageArchive:
    """Tests for archive operations."""

    def test_archive_file(self, temp_paths, mock_subprocess):
        """Test archiving a file."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        (wt_path / "skills" / "user").mkdir(parents=True)
        (wt_path / "archive" / "skills").mkdir(parents=True)
        storage._worktree_path = wt_path

        # Create test file
        src = wt_path / "skills" / "user" / "test.yaml"
        src.write_text("id: test")

        result = storage.archive_file(
            "skills/user/test.yaml",
            "archive/skills/test.yaml",
            "Archive test skill"
        )

        assert result is True
        assert not src.exists()
        assert (wt_path / "archive" / "skills" / "test.yaml").exists()

    def test_archive_file_nonexistent(self, temp_paths):
        """Test archiving a nonexistent file."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        storage._worktree_path = wt_path

        result = storage.archive_file(
            "skills/user/nonexistent.yaml",
            "archive/skills/nonexistent.yaml",
            "Archive test"
        )

        assert result is False


@pytest.mark.asyncio
class TestMarketplaceGitStorageInitialize:
    """Tests for async initialize method."""

    async def test_initialize_creates_repo_and_worktree(self, temp_paths, mock_subprocess):
        """Test that initialize creates repo and worktree."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)

        # Simulate successful initialization
        # First set of calls for repo creation
        mock_subprocess.side_effect = [
            MagicMock(returncode=0),  # git init --bare
            MagicMock(returncode=0),  # git symbolic-ref
            MagicMock(returncode=0),  # git worktree add
        ]

        await storage.initialize()

        assert storage._initialized is True
        assert storage._worktree_path is not None

    async def test_initialize_idempotent(self, temp_paths, mock_subprocess):
        """Test that initialize only runs once."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        storage._initialized = True

        await storage.initialize()

        # Should not call any subprocess commands
        mock_subprocess.assert_not_called()

    async def test_cleanup(self, temp_paths, mock_subprocess):
        """Test cleanup removes worktree."""
        repos_path, worktree_path = temp_paths
        storage = MarketplaceGitStorage(repos_path, worktree_path)
        wt_path = Path(worktree_path) / "test-worktree"
        wt_path.mkdir()
        storage._worktree_path = wt_path

        await storage.cleanup()

        # Should have called worktree remove
        call_args = mock_subprocess.call_args[0][0]
        assert "worktree" in call_args
        assert "remove" in call_args
