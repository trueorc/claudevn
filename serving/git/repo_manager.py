"""Git repository manager for ClaudeVN.

Manages bare Git repositories including creation, hook installation,
and basic Git operations.
"""

import logging
import os
import pwd
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from config import get_config, GitConfig

logger = logging.getLogger(__name__)

# Hook templates directory (relative to this file)
HOOKS_DIR = Path(__file__).parent / "hooks"


class RepoManager:
    """Manages bare Git repositories for ClaudeVN projects."""

    def __init__(self, config: Optional[GitConfig] = None):
        """Initialize repository manager.

        Args:
            config: Git configuration (defaults to global config)
        """
        self._config = config or get_config().git
        self._repos_path = Path(self._config.repos_path)

    def _ensure_repos_dir(self) -> None:
        """Ensure repositories directory exists."""
        self._repos_path.mkdir(parents=True, exist_ok=True)

    def _git_cmd(self, repo_path: Path, *args: str, **kwargs) -> subprocess.CompletedProcess:
        """Run a git command against a repo, bypassing safe.directory checks.

        Serving runs as root but repos are owned by the git user.  Without
        this, git refuses to operate on the repo (CVE-2022-24765).
        """
        cmd = ["git", "-C", str(repo_path), *args]
        env = {**os.environ, "GIT_CONFIG_COUNT": "1",
               "GIT_CONFIG_KEY_0": "safe.directory",
               "GIT_CONFIG_VALUE_0": "*"}
        return subprocess.run(cmd, capture_output=True, text=True, env=env, **kwargs)

    def _chown_to_git_user(self, path: Path) -> None:
        """Change ownership of a path to the git user.

        When sshd authenticates compute instances as the git user,
        git-upload-pack/git-receive-pack runs as that user. Git's
        safe.directory check (CVE-2022-24765) rejects repositories
        owned by a different user. Since serving runs as root but
        SSH access runs as the git user, we must chown repos after
        creation.

        Args:
            path: Path to chown (typically a bare repo directory)
        """
        git_user = self._config.git_user
        try:
            pw = pwd.getpwnam(git_user)
            uid, gid = pw.pw_uid, pw.pw_gid
            # Recursively chown the entire repo directory
            for dirpath, dirnames, filenames in os.walk(path):
                os.chown(dirpath, uid, gid)
                for filename in filenames:
                    os.chown(os.path.join(dirpath, filename), uid, gid)
            logger.debug(f"Changed ownership of {path} to {git_user} ({uid}:{gid})")
        except KeyError:
            logger.warning(
                f"Git user '{git_user}' not found, skipping chown. "
                "SSH Git access may fail with 'dubious ownership' errors."
            )
        except OSError as e:
            logger.warning(f"Failed to chown {path} to {git_user}: {e}")

    def _seed_initial_commit(self, repo_path: Path) -> None:
        """Create an initial empty commit in a bare repository.

        Uses a temporary clone to create the commit, then cleans up.
        This ensures refs/heads/main exists so that
        `git clone --branch main` succeeds.

        Args:
            repo_path: Path to the bare repository
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Clone the bare repo into a temp working directory
            subprocess.run(
                ["git", "clone", str(repo_path), tmp_dir],
                check=True,
                capture_output=True
            )

            # Configure minimal git identity for the commit
            subprocess.run(
                ["git", "-C", tmp_dir, "config", "user.email", "claudevn@system"],
                check=True,
                capture_output=True
            )
            subprocess.run(
                ["git", "-C", tmp_dir, "config", "user.name", "ClaudeVN"],
                check=True,
                capture_output=True
            )

            # Create an empty initial commit
            subprocess.run(
                ["git", "-C", tmp_dir, "commit", "--allow-empty", "-m", "Initial commit"],
                check=True,
                capture_output=True
            )

            # Push back to the bare repo
            subprocess.run(
                ["git", "-C", tmp_dir, "push", "origin", "main"],
                check=True,
                capture_output=True
            )

        logger.debug(f"Seeded initial commit in {repo_path}")

    def _repo_path(self, project: str) -> Path:
        """Get path to project repository.

        Args:
            project: Project name

        Returns:
            Path to bare repository
        """
        return self._repos_path / f"{project}.git"

    def repo_exists(self, project: str) -> bool:
        """Check if project repository exists.

        Args:
            project: Project name

        Returns:
            True if repository exists
        """
        repo_path = self._repo_path(project)
        return repo_path.exists() and (repo_path / "HEAD").exists()

    def create_repo(self, project: str, install_hooks: bool = True) -> Path:
        """Create a new bare repository.

        Args:
            project: Project name
            install_hooks: Whether to install Git hooks

        Returns:
            Path to created repository

        Raises:
            FileExistsError: If repository already exists
            subprocess.CalledProcessError: If git init fails
        """
        self._ensure_repos_dir()
        repo_path = self._repo_path(project)

        if repo_path.exists():
            raise FileExistsError(f"Repository already exists: {project}")

        logger.info(f"Creating bare repository: {repo_path}")

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

        # Seed initial commit so refs/heads/main actually exists
        # Without this, `git clone --branch main` fails because the
        # symbolic ref points to a nonexistent ref
        self._seed_initial_commit(repo_path)

        # Install hooks if requested
        if install_hooks:
            self.install_hooks(project)

        # Chown repo to git user so SSH-based access works
        # (prevents "dubious ownership" errors when git-upload-pack
        # runs as the git user but the repo was created by root)
        self._chown_to_git_user(repo_path)

        logger.info(f"Repository created: {project}")
        return repo_path

    def delete_repo(self, project: str) -> bool:
        """Delete a repository.

        Args:
            project: Project name

        Returns:
            True if deleted, False if not found
        """
        repo_path = self._repo_path(project)

        if not repo_path.exists():
            return False

        logger.warning(f"Deleting repository: {project}")
        shutil.rmtree(repo_path)
        return True

    def list_repos(self) -> List[str]:
        """List all repositories.

        Returns:
            List of project names
        """
        self._ensure_repos_dir()
        repos = []

        for item in self._repos_path.iterdir():
            if item.is_dir() and item.name.endswith(".git"):
                # Verify it's a valid repo
                if (item / "HEAD").exists():
                    repos.append(item.name[:-4])  # Remove .git suffix

        return sorted(repos)

    def install_hooks(self, project: str) -> None:
        """Install Git hooks for a repository.

        Args:
            project: Project name

        Raises:
            FileNotFoundError: If repository doesn't exist
        """
        repo_path = self._repo_path(project)

        if not repo_path.exists():
            raise FileNotFoundError(f"Repository not found: {project}")

        hooks_dest = repo_path / "hooks"
        hooks_dest.mkdir(exist_ok=True)

        # Install pre-receive hook
        self._install_hook(project, "pre-receive")

        # Install post-receive hook
        self._install_hook(project, "post-receive")

        logger.info(f"Hooks installed for: {project}")

    def verify_hooks(self, project: str) -> dict:
        """Verify Git hooks are properly installed for a repository.

        Args:
            project: Project name

        Returns:
            Dict with hook status:
            - hooks_installed: bool - True if all hooks are present
            - pre_receive: dict with exists and executable status
            - post_receive: dict with exists and executable status

        Raises:
            FileNotFoundError: If repository doesn't exist
        """
        repo_path = self._repo_path(project)

        if not repo_path.exists():
            raise FileNotFoundError(f"Repository not found: {project}")

        hooks_dir = repo_path / "hooks"

        def check_hook(hook_name: str) -> dict:
            hook_path = hooks_dir / hook_name
            exists = hook_path.exists()
            executable = exists and os.access(hook_path, os.X_OK)
            return {
                "exists": exists,
                "executable": executable,
                "path": str(hook_path) if exists else None
            }

        pre_receive = check_hook("pre-receive")
        post_receive = check_hook("post-receive")

        hooks_installed = (
            pre_receive["exists"] and pre_receive["executable"] and
            post_receive["exists"] and post_receive["executable"]
        )

        return {
            "hooks_installed": hooks_installed,
            "pre_receive": pre_receive,
            "post_receive": post_receive
        }

    def install_hooks_all(self) -> dict:
        """Install hooks on all existing repositories.

        Returns:
            Dict with results for each repository
        """
        results = {}
        repos = self.list_repos()

        for project in repos:
            try:
                self.install_hooks(project)
                results[project] = {"success": True}
            except Exception as e:
                logger.error(f"Failed to install hooks for {project}: {e}")
                results[project] = {"success": False, "error": str(e)}

        return {
            "total": len(repos),
            "success": sum(1 for r in results.values() if r["success"]),
            "failed": sum(1 for r in results.values() if not r["success"]),
            "results": results
        }

    def _install_hook(self, project: str, hook_name: str) -> None:
        """Install a specific hook.

        Args:
            project: Project name
            hook_name: Hook name (e.g., 'pre-receive')
        """
        repo_path = self._repo_path(project)
        hook_template = HOOKS_DIR / hook_name
        hook_dest = repo_path / "hooks" / hook_name

        if hook_template.exists():
            # Copy template
            shutil.copy(hook_template, hook_dest)
        else:
            # Generate default hook
            hook_content = self._generate_hook(hook_name, project)
            hook_dest.write_text(hook_content)

        # Make executable
        hook_dest.chmod(0o755)

    def _generate_hook(self, hook_name: str, project: str) -> str:
        """Generate hook script content.

        Args:
            hook_name: Hook name
            project: Project name

        Returns:
            Hook script content
        """
        config = get_config()

        if hook_name == "pre-receive":
            return self._generate_pre_receive_hook(project)
        elif hook_name == "post-receive":
            return self._generate_post_receive_hook(project, config)
        else:
            return "#!/bin/bash\nexit 0\n"

    def _generate_pre_receive_hook(self, project: str) -> str:
        """Generate pre-receive hook that validates pushes."""
        return f'''#!/bin/bash
# ClaudeVN pre-receive hook for {project}
# Validates branch naming and blocks direct pushes to main
# Types: f (feature), b (bugfix), r (refactor), d (docs), t (test)

while read oldrev newrev refname; do
    branch=$(echo "$refname" | sed 's|refs/heads/||')

    # STRICTLY block direct pushes to main/master
    # Compute instances can NEVER push to main - only Serving (via merge process)
    if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
        echo "ERROR: Direct push to $branch is FORBIDDEN."
        echo "       Only Serving can merge to main."
        exit 1
    fi

    # Skip validation for special branches
    if [ "$branch" = "develop" ]; then
        continue
    fi

    # Validate branch naming convention: {{type}}/{{identifier}}/{{compute-id}}
    if ! [[ "$branch" =~ ^[fbrdt]/(issue|work)_[a-z0-9]+/compute-[a-z0-9-]+$ ]]; then
        echo "ERROR: Invalid branch name: $branch"
        echo "       Format: {{type}}/{{issue_id}}/{{compute-id}}"
        echo "       Types: f (feature), b (bugfix), r (refactor), d (docs), t (test)"
        echo "       Example: f/issue_ae655ba830a9/compute-001"
        exit 1
    fi

    # Extract compute ID and verify ownership
    compute_id=$(echo "$branch" | grep -oP 'compute-[a-z0-9-]+$')
    if [ -n "$GIT_PUSH_COMPUTE_ID" ] && [ "$compute_id" != "$GIT_PUSH_COMPUTE_ID" ]; then
        echo "ERROR: $GIT_PUSH_COMPUTE_ID cannot push to $compute_id's branch"
        exit 1
    fi
done

exit 0
'''

    def _generate_post_receive_hook(self, project: str, config) -> str:
        """Generate post-receive hook that notifies Redis."""
        redis_config = config.redis
        return f'''#!/bin/bash
# ClaudeVN post-receive hook for {project}
# Publishes push events to Redis

REDIS_HOST="${{REDIS_HOST:-{redis_config.host}}}"
REDIS_PORT="${{REDIS_PORT:-{redis_config.port}}}"
REDIS_PREFIX="${{REDIS_PREFIX:-{redis_config.key_prefix}}}"
PROJECT="{project}"

while read oldrev newrev refname; do
    branch=$(echo "$refname" | sed 's|refs/heads/||')
    timestamp=$(date -Iseconds)

    # Skip main branch events (shouldn't happen due to pre-receive)
    if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
        continue
    fi

    # Extract compute ID from branch name (format: compute-NNN)
    compute_id=$(echo "$branch" | grep -oP 'compute-[0-9]+$' || echo "unknown")

    # Publish to Redis
    if command -v redis-cli &> /dev/null; then
        # Publish push event
        redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" PUBLISH "${{REDIS_PREFIX}}git:${{PROJECT}}:push" \\
            "{{\\"branch\\":\\"$branch\\",\\"commit\\":\\"$newrev\\",\\"compute_id\\":\\"$compute_id\\",\\"timestamp\\":\\"$timestamp\\"}}"

        # Update branch metadata
        redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HSETNX "${{REDIS_PREFIX}}branch:${{PROJECT}}:${{branch}}" status "pending"
        redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HSET "${{REDIS_PREFIX}}branch:${{PROJECT}}:${{branch}}" \\
            last_commit "$newrev" \\
            compute_id "$compute_id" \\
            updated_at "$timestamp"
    fi

    echo "Branch $branch updated to ${{newrev:0:8}}"
done

exit 0
'''

    def get_branches(self, project: str) -> List[str]:
        """Get list of branches in repository.

        Args:
            project: Project name

        Returns:
            List of branch names
        """
        repo_path = self._repo_path(project)

        if not repo_path.exists():
            return []

        result = self._git_cmd(repo_path, "branch", "--list", "--format=%(refname:short)")

        if result.returncode != 0:
            return []

        return [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]

    def get_branch_head(self, project: str, branch: str) -> Optional[str]:
        """Get HEAD commit of a branch.

        Args:
            project: Project name
            branch: Branch name

        Returns:
            Commit SHA or None if not found
        """
        repo_path = self._repo_path(project)

        if not repo_path.exists():
            return None

        result = self._git_cmd(repo_path, "rev-parse", f"refs/heads/{branch}")

        if result.returncode != 0:
            return None

        return result.stdout.strip()

    def delete_branch(self, project: str, branch: str) -> bool:
        """Delete a branch from the repository.

        Args:
            project: Project name
            branch: Branch name to delete

        Returns:
            True if branch was deleted, False if branch not found

        Raises:
            ValueError: If attempting to delete protected branch (main/master)
        """
        # Protect main/master branches
        protected_branches = {"main", "master"}
        if branch in protected_branches:
            raise ValueError(f"Cannot delete protected branch: {branch}")

        repo_path = self._repo_path(project)

        if not repo_path.exists():
            return False

        # Check if branch exists
        if self.get_branch_head(project, branch) is None:
            return False

        # Delete the branch
        result = subprocess.run(
            ["git", "-C", str(repo_path), "branch", "-D", branch],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            logger.error(f"Failed to delete branch {branch} from {project}: {result.stderr}")
            return False

        logger.info(f"Deleted branch {branch} from {project}")
        return True

    def get_repo_url(self, project: str) -> str:
        """Get SSH URL for repository.

        Args:
            project: Project name

        Returns:
            SSH URL for cloning
        """
        git_user = self._config.git_user
        repo_path = self._repo_path(project)
        return f"{git_user}@localhost:{repo_path}"

    def clone_from_url(
        self,
        project: str,
        url: str,
        ssh_key_path: Optional[str] = None,
        default_branch: str = "main"
    ) -> Path:
        """Clone a repository from a URL into Serving's Git infrastructure.

        Creates a bare mirror clone that can receive pushes and push back to origin.

        Args:
            project: Project name for the local repo
            url: Git URL to clone from (SSH or HTTPS)
            ssh_key_path: Path to SSH key for authentication (optional)
            default_branch: Default branch name

        Returns:
            Path to cloned repository

        Raises:
            FileExistsError: If repository already exists
            subprocess.CalledProcessError: If git clone fails
        """
        self._ensure_repos_dir()
        repo_path = self._repo_path(project)

        if repo_path.exists():
            raise FileExistsError(f"Repository already exists: {project}")

        logger.info(f"Cloning repository from {url} to {repo_path}")

        # Build git clone command
        env = os.environ.copy()
        if ssh_key_path:
            env["GIT_SSH_COMMAND"] = f'ssh -i {ssh_key_path} -o StrictHostKeyChecking=no'

        # Clone as a bare mirror
        subprocess.run(
            ["git", "clone", "--bare", "--mirror", url, str(repo_path)],
            check=True,
            capture_output=True,
            env=env
        )

        # Configure origin for push
        subprocess.run(
            ["git", "-C", str(repo_path), "remote", "set-url", "--push", "origin", url],
            check=True,
            capture_output=True,
            env=env
        )

        # Set default branch
        subprocess.run(
            ["git", "-C", str(repo_path), "symbolic-ref", "HEAD", f"refs/heads/{default_branch}"],
            check=True,
            capture_output=True
        )

        # Install hooks
        self.install_hooks(project)

        # Chown repo to git user for SSH access
        self._chown_to_git_user(repo_path)

        logger.info(f"Repository cloned: {project} from {url}")
        return repo_path

    def pull_from_origin(
        self,
        project: str,
        ssh_key_path: Optional[str] = None
    ) -> dict:
        """Pull latest changes from origin into the bare repository.

        Args:
            project: Project name
            ssh_key_path: Path to SSH key for authentication (optional)

        Returns:
            Dict with pull results (branches updated, etc.)

        Raises:
            FileNotFoundError: If repository doesn't exist
            subprocess.CalledProcessError: If git fetch fails
        """
        repo_path = self._repo_path(project)

        if not repo_path.exists():
            raise FileNotFoundError(f"Repository not found: {project}")

        logger.info(f"Pulling from origin for: {project}")

        env = os.environ.copy()
        if ssh_key_path:
            env["GIT_SSH_COMMAND"] = f'ssh -i {ssh_key_path} -o StrictHostKeyChecking=no'

        # Fetch all branches and tags from origin
        result = subprocess.run(
            ["git", "-C", str(repo_path), "fetch", "--all", "--prune", "--tags"],
            capture_output=True,
            text=True,
            env=env
        )

        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                result.args,
                result.stdout,
                result.stderr
            )

        # Re-chown so SSH pushes (as git user) still work after fetch
        self._chown_to_git_user(repo_path)

        return {
            "success": True,
            "project": project,
            "output": result.stdout + result.stderr
        }

    def push_to_origin(
        self,
        project: str,
        branch: str,
        ssh_key_path: Optional[str] = None,
        force: bool = False
    ) -> dict:
        """Push a branch to origin.

        Args:
            project: Project name
            branch: Branch name to push
            ssh_key_path: Path to SSH key for authentication (optional)
            force: Force push (use with caution)

        Returns:
            Dict with push results

        Raises:
            FileNotFoundError: If repository doesn't exist
            subprocess.CalledProcessError: If git push fails
        """
        repo_path = self._repo_path(project)

        if not repo_path.exists():
            raise FileNotFoundError(f"Repository not found: {project}")

        logger.info(f"Pushing {branch} to origin for: {project}")

        env = os.environ.copy()
        if ssh_key_path:
            env["GIT_SSH_COMMAND"] = f'ssh -i {ssh_key_path} -o StrictHostKeyChecking=no'

        cmd = ["git", "-C", str(repo_path), "push", "origin", branch]
        if force:
            cmd.insert(-1, "--force")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env
        )

        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                result.args,
                result.stdout,
                result.stderr
            )

        return {
            "success": True,
            "project": project,
            "branch": branch,
            "output": result.stdout + result.stderr
        }

    def get_origin_url(self, project: str) -> Optional[str]:
        """Get the origin remote URL for a repository.

        Args:
            project: Project name

        Returns:
            Origin URL or None if not configured
        """
        repo_path = self._repo_path(project)

        if not repo_path.exists():
            return None

        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return None

        return result.stdout.strip()

    def get_repo_status(self, project: str) -> Optional[dict]:
        """Get status information for a repository.

        Args:
            project: Project name

        Returns:
            Dict with repository status or None if not found
        """
        repo_path = self._repo_path(project)

        if not repo_path.exists():
            return None

        # Get origin URL
        origin_url = self.get_origin_url(project)

        # Get branches
        branches = self.get_branches(project)

        # Get HEAD ref
        head_result = subprocess.run(
            ["git", "-C", str(repo_path), "symbolic-ref", "HEAD"],
            capture_output=True,
            text=True
        )
        default_branch = None
        if head_result.returncode == 0:
            default_branch = head_result.stdout.strip().replace("refs/heads/", "")

        # Check if it's a mirror clone
        is_mirror = False
        config_result = subprocess.run(
            ["git", "-C", str(repo_path), "config", "--get", "remote.origin.mirror"],
            capture_output=True,
            text=True
        )
        if config_result.returncode == 0 and config_result.stdout.strip() == "true":
            is_mirror = True

        return {
            "project": project,
            "path": str(repo_path),
            "origin_url": origin_url,
            "default_branch": default_branch,
            "branches": branches,
            "branch_count": len(branches),
            "is_mirror": is_mirror,
            "exists": True
        }

    # =========================================================================
    # Worktree Operations (for compute instances)
    # =========================================================================

    def clone_regular(
        self,
        url: str,
        dest_path: Path,
        ssh_key_path: Optional[str] = None,
        branch: Optional[str] = None
    ) -> Path:
        """Clone a repository as a regular (non-bare) clone.

        Used for compute workspaces where worktrees will be added.

        Args:
            url: Git URL to clone from (SSH or HTTPS)
            dest_path: Destination directory for the clone
            ssh_key_path: Path to SSH key for authentication (optional)
            branch: Specific branch to clone (optional, uses default if not specified)

        Returns:
            Path to cloned repository

        Raises:
            FileExistsError: If destination already exists
            subprocess.CalledProcessError: If git clone fails
        """
        if dest_path.exists():
            raise FileExistsError(f"Destination already exists: {dest_path}")

        logger.info(f"Cloning repository from {url} to {dest_path}")

        env = os.environ.copy()
        if ssh_key_path:
            env["GIT_SSH_COMMAND"] = f'ssh -i {ssh_key_path} -o StrictHostKeyChecking=no'

        cmd = ["git", "clone"]
        if branch:
            cmd.extend(["--branch", branch])
        cmd.extend([url, str(dest_path)])

        subprocess.run(cmd, check=True, capture_output=True, env=env)

        logger.info(f"Repository cloned to {dest_path}")
        return dest_path

    def add_worktree(
        self,
        repo_path: Path,
        worktree_path: Path,
        branch: str,
        create_branch: bool = False,
        track_remote: Optional[str] = None
    ) -> Path:
        """Add a Git worktree to a repository.

        Args:
            repo_path: Path to the main repository
            worktree_path: Path where worktree should be created
            branch: Branch name to checkout in the worktree
            create_branch: If True, create a new branch (-b flag)
            track_remote: Remote branch to track (e.g., "origin/main")

        Returns:
            Path to the created worktree

        Raises:
            FileNotFoundError: If repository doesn't exist
            FileExistsError: If worktree path already exists
            subprocess.CalledProcessError: If git worktree add fails
        """
        if not repo_path.exists():
            raise FileNotFoundError(f"Repository not found: {repo_path}")

        if worktree_path.exists():
            raise FileExistsError(f"Worktree path already exists: {worktree_path}")

        logger.info(f"Adding worktree at {worktree_path} for branch {branch}")

        cmd = ["git", "-C", str(repo_path), "worktree", "add"]

        if create_branch:
            cmd.extend(["-b", branch])
            cmd.append(str(worktree_path))
            if track_remote:
                cmd.append(track_remote)
        else:
            cmd.extend([str(worktree_path), branch])

        subprocess.run(cmd, check=True, capture_output=True)

        logger.info(f"Worktree created at {worktree_path}")
        return worktree_path

    def list_worktrees(self, repo_path: Path) -> List[dict]:
        """List all worktrees for a repository.

        Args:
            repo_path: Path to the repository (main or any worktree)

        Returns:
            List of worktree info dicts with keys: path, head, branch
        """
        if not repo_path.exists():
            return []

        result = subprocess.run(
            ["git", "-C", str(repo_path), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return []

        worktrees = []
        current = {}

        for line in result.stdout.strip().split("\n"):
            if not line:
                if current:
                    worktrees.append(current)
                    current = {}
            elif line.startswith("worktree "):
                current["path"] = line[9:]
            elif line.startswith("HEAD "):
                current["head"] = line[5:]
            elif line.startswith("branch "):
                current["branch"] = line[7:].replace("refs/heads/", "")
            elif line == "bare":
                current["bare"] = True
            elif line == "detached":
                current["detached"] = True

        if current:
            worktrees.append(current)

        return worktrees

    def remove_worktree(
        self,
        repo_path: Path,
        worktree_path: Path,
        force: bool = False
    ) -> bool:
        """Remove a Git worktree.

        Args:
            repo_path: Path to the main repository
            worktree_path: Path to the worktree to remove
            force: Force removal even if worktree has uncommitted changes

        Returns:
            True if removed successfully

        Raises:
            FileNotFoundError: If repository doesn't exist
            subprocess.CalledProcessError: If git worktree remove fails
        """
        if not repo_path.exists():
            raise FileNotFoundError(f"Repository not found: {repo_path}")

        logger.info(f"Removing worktree at {worktree_path}")

        cmd = ["git", "-C", str(repo_path), "worktree", "remove"]
        if force:
            cmd.append("--force")
        cmd.append(str(worktree_path))

        subprocess.run(cmd, check=True, capture_output=True)

        logger.info(f"Worktree removed: {worktree_path}")
        return True

    def prune_worktrees(self, repo_path: Path) -> bool:
        """Prune stale worktree references.

        Args:
            repo_path: Path to the repository

        Returns:
            True if pruned successfully
        """
        if not repo_path.exists():
            return False

        subprocess.run(
            ["git", "-C", str(repo_path), "worktree", "prune"],
            check=True,
            capture_output=True
        )

        return True
