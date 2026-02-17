"""Git-backed storage for Marketplace user data.

Provides durable, version-controlled storage for user-created skills and personas.
Follows the same pattern as serving's IssueService for consistency.
"""

import logging
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, TypeVar, Generic
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


class MarketplaceGitStorage:
    """Git-backed storage manager for marketplace user data.

    Storage architecture:
    - Git: Persistent YAML files with full version history (source of truth)
    - Worktree: Active working directory for read/write operations

    Git structure:
        marketplace-repo/
        ├── skills/
        │   └── user/
        │       ├── custom-skill-1.yaml
        │       └── custom-skill-2.yaml
        ├── personas/
        │   └── user/
        │       ├── custom-persona-1.yaml
        │       └── custom-persona-2.yaml
        └── archive/
            ├── skills/
            └── personas/
    """

    def __init__(self, repos_path: str, worktree_path: str):
        """Initialize Git storage manager.

        Args:
            repos_path: Directory for bare Git repositories
            worktree_path: Directory for worktree (working directory)
        """
        self._repos_path = Path(repos_path)
        self._repo_name = "marketplace"
        self._worktree_base_path = Path(worktree_path)
        self._worktree_path: Optional[Path] = None
        self._lock = threading.RLock()  # For atomic Git operations
        self._initialized = False

    @property
    def worktree_path(self) -> Optional[Path]:
        """Get the current worktree path."""
        return self._worktree_path

    async def initialize(self) -> None:
        """Initialize marketplace repo and worktree if not exists."""
        if self._initialized:
            return

        self._repos_path.mkdir(parents=True, exist_ok=True)
        repo_path = self._repo_path()

        # Create bare repo if doesn't exist
        if not self._repo_exists():
            logger.info("Creating marketplace Git repository")
            self._create_bare_repo()

        # Create worktree for read/write operations
        self._worktree_path = self._worktree_base_path / f"marketplace-{id(self)}"

        # Clean up any existing worktree at this path
        if self._worktree_path.exists():
            try:
                self._remove_worktree(force=True)
            except Exception:
                pass

        # Create worktree on main branch
        try:
            self._add_worktree(branch="main", create_branch=False)
        except subprocess.CalledProcessError:
            # Main branch doesn't exist yet, create it
            self._add_worktree(branch="main", create_branch=True)

        # Ensure directory structure exists
        self._ensure_directories()

        self._initialized = True
        logger.info(f"Marketplace Git storage initialized with worktree at {self._worktree_path}")

    def _repo_path(self) -> Path:
        """Get path to the bare repository."""
        return self._repos_path / f"{self._repo_name}.git"

    def _repo_exists(self) -> bool:
        """Check if repository exists."""
        repo_path = self._repo_path()
        return repo_path.exists() and (repo_path / "HEAD").exists()

    def _create_bare_repo(self) -> None:
        """Create a new bare repository."""
        repo_path = self._repo_path()

        # Initialize bare repository
        subprocess.run(
            ["git", "init", "--bare", str(repo_path)],
            check=True,
            capture_output=True
        )

        # Set default branch to main
        subprocess.run(
            ["git", "-C", str(repo_path), "symbolic-ref", "HEAD", "refs/heads/main"],
            check=True,
            capture_output=True
        )

        logger.info(f"Created bare repository at {repo_path}")

    def _add_worktree(self, branch: str, create_branch: bool = False) -> None:
        """Add a Git worktree to the repository.

        Args:
            branch: Branch name to checkout
            create_branch: If True, create a new branch
        """
        repo_path = self._repo_path()
        self._worktree_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = ["git", "-C", str(repo_path), "worktree", "add"]

        if create_branch:
            cmd.extend(["-b", branch])
            cmd.append(str(self._worktree_path))
        else:
            cmd.extend([str(self._worktree_path), branch])

        subprocess.run(cmd, check=True, capture_output=True)

    def _remove_worktree(self, force: bool = False) -> None:
        """Remove the current worktree."""
        repo_path = self._repo_path()

        cmd = ["git", "-C", str(repo_path), "worktree", "remove"]
        if force:
            cmd.append("--force")
        cmd.append(str(self._worktree_path))

        subprocess.run(cmd, check=True, capture_output=True)

    def _ensure_directories(self) -> None:
        """Ensure directory structure exists in worktree."""
        if not self._worktree_path:
            raise RuntimeError("Worktree not initialized")

        (self._worktree_path / "skills" / "user").mkdir(parents=True, exist_ok=True)
        (self._worktree_path / "personas" / "user").mkdir(parents=True, exist_ok=True)
        (self._worktree_path / "archive" / "skills").mkdir(parents=True, exist_ok=True)
        (self._worktree_path / "archive" / "personas").mkdir(parents=True, exist_ok=True)

    def _git_commit(self, message: str) -> bool:
        """Create a Git commit in the worktree.

        Args:
            message: Commit message

        Returns:
            True if a commit was made, False if no changes to commit
        """
        if not self._worktree_path:
            raise RuntimeError("Worktree not initialized")

        with self._lock:
            # Add all changes
            subprocess.run(
                ["git", "add", "."],
                cwd=self._worktree_path,
                check=True,
                capture_output=True
            )

            # Check if there are changes to commit
            result = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=self._worktree_path,
                capture_output=True
            )

            if result.returncode == 0:
                # No changes to commit
                return False

            # Commit
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self._worktree_path,
                check=True,
                capture_output=True
            )

            logger.debug(f"Git commit: {message}")
            return True

    def save_yaml(self, relative_path: str, content: str, commit_message: str) -> bool:
        """Save YAML content to a file and commit.

        Args:
            relative_path: Path relative to worktree root (e.g., "skills/user/my-skill.yaml")
            content: YAML content to write
            commit_message: Git commit message

        Returns:
            True if saved and committed successfully
        """
        if not self._worktree_path:
            raise RuntimeError("Worktree not initialized")

        file_path = self._worktree_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

        return self._git_commit(commit_message)

    def load_yaml(self, relative_path: str) -> Optional[str]:
        """Load YAML content from a file.

        Args:
            relative_path: Path relative to worktree root

        Returns:
            YAML content if file exists, None otherwise
        """
        if not self._worktree_path:
            return None

        file_path = self._worktree_path / relative_path
        if not file_path.exists():
            return None

        return file_path.read_text()

    def delete_file(self, relative_path: str, commit_message: str) -> bool:
        """Delete a file and commit.

        Args:
            relative_path: Path relative to worktree root
            commit_message: Git commit message

        Returns:
            True if deleted and committed, False if file didn't exist
        """
        if not self._worktree_path:
            raise RuntimeError("Worktree not initialized")

        file_path = self._worktree_path / relative_path
        if not file_path.exists():
            return False

        file_path.unlink()
        self._git_commit(commit_message)
        return True

    def archive_file(self, from_path: str, archive_path: str, commit_message: str) -> bool:
        """Move a file to archive and commit.

        Args:
            from_path: Source path relative to worktree
            archive_path: Destination path in archive
            commit_message: Git commit message

        Returns:
            True if archived and committed
        """
        if not self._worktree_path:
            raise RuntimeError("Worktree not initialized")

        src = self._worktree_path / from_path
        dst = self._worktree_path / archive_path

        if not src.exists():
            return False

        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        self._git_commit(commit_message)
        return True

    def list_files(self, directory: str, pattern: str = "*.yaml") -> List[Path]:
        """List files in a directory.

        Args:
            directory: Directory relative to worktree
            pattern: Glob pattern (default: "*.yaml")

        Returns:
            List of file paths
        """
        if not self._worktree_path:
            return []

        dir_path = self._worktree_path / directory
        if not dir_path.exists():
            return []

        return list(dir_path.glob(pattern))

    def get_file_history(self, relative_path: str, max_entries: int = 50) -> List[Dict]:
        """Get Git commit history for a file.

        Args:
            relative_path: Path relative to worktree root
            max_entries: Maximum number of history entries

        Returns:
            List of commit history entries
        """
        if not self._worktree_path:
            return []

        result = subprocess.run(
            [
                "git", "log",
                f"--max-count={max_entries}",
                "--pretty=format:%H|%an|%at|%s",
                "--", relative_path
            ],
            cwd=self._worktree_path,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return []

        history = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("|", 3)
            if len(parts) == 4:
                commit_hash, author, timestamp, message = parts
                history.append({
                    "commit": commit_hash,
                    "author": author,
                    "timestamp": datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat(),
                    "message": message
                })

        return history

    def get_file_at_commit(self, relative_path: str, commit_hash: str) -> Optional[str]:
        """Get file content at a specific commit.

        Args:
            relative_path: Path relative to worktree root
            commit_hash: Git commit hash

        Returns:
            File content at that commit, or None if not found
        """
        if not self._worktree_path:
            return None

        result = subprocess.run(
            ["git", "show", f"{commit_hash}:{relative_path}"],
            cwd=self._worktree_path,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return None

        return result.stdout

    def file_exists(self, relative_path: str) -> bool:
        """Check if a file exists in the worktree.

        Args:
            relative_path: Path relative to worktree root

        Returns:
            True if file exists
        """
        if not self._worktree_path:
            return False

        return (self._worktree_path / relative_path).exists()

    async def cleanup(self) -> None:
        """Clean up worktree on shutdown."""
        if self._worktree_path and self._worktree_path.exists():
            try:
                self._remove_worktree(force=True)
                logger.info(f"Cleaned up worktree at {self._worktree_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup worktree: {e}")


# Global instance
_git_storage: Optional[MarketplaceGitStorage] = None


def get_git_storage() -> MarketplaceGitStorage:
    """Get the global Git storage instance."""
    if _git_storage is None:
        raise RuntimeError("Git storage not initialized")
    return _git_storage


def set_git_storage(storage: MarketplaceGitStorage) -> None:
    """Set the global Git storage instance."""
    global _git_storage
    _git_storage = storage
