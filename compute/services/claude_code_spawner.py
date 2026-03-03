"""Claude Code Spawner for Compute Infrastructure (Compute-side).

This is the COMPUTE-SIDE spawner for the DISTRIBUTED deployment model.
It runs within Compute Infrastructure (Docker container) and executes
Claude Code tasks via the Claude Agent SDK in response to SSE
work_assigned events from Serving.

Use this spawner for:
- Production deployments with distributed compute fleet
- Scale-out scenarios with multiple compute containers
- Resource isolation (Claude Code runs in containers)
- SSE-based registration model (v1.0 event-driven architecture)

For the CENTRALIZED deployment model (development, single-host), use the
serving-side spawner at serving/services/compute_spawner.py instead.

See docs/design/adr/005-dual-spawner-architecture.md for architectural details.

Responsibilities:
- Executes Claude Code tasks via claude-agent-sdk in response to SSE work_assigned events
- Sets up Git clone + branch for assigned work
- Injects task context into CLAUDE.md at spawn time
- Reports lifecycle events (started, completed, failed) to Serving via HTTP
- Manages instance tasks and monitors completion
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

import httpx

from services.claude_sdk_executor import ExecutionResult, execute_task, build_mcp_servers

logger = logging.getLogger(__name__)


def _extract_json_from_output(output: str) -> Optional[Dict[str, Any]]:
    """Extract a JSON decomposition result from Claude Code output.

    Tries multiple strategies in order:
    1. Single-line JSON (lines starting with { and ending with })
    2. JSON inside markdown code fences (```json ... ``` or ``` ... ```)
    3. Brace-balanced extraction of JSON containing "issues" key

    Args:
        output: Raw stdout from Claude Code

    Returns:
        Parsed JSON dict if found, None otherwise
    """
    return _extract_json_with_key(output, "issues")


def _extract_json_with_key(output: str, required_key: str) -> Optional[Dict[str, Any]]:
    """Extract a JSON dict from Claude Code output that contains a required key.

    Tries multiple strategies in order:
    1. Single-line JSON (lines starting with { and ending with })
    2. JSON inside markdown code fences (```json ... ``` or ``` ... ```)
    3. Brace-balanced extraction of JSON containing the required key

    Args:
        output: Raw stdout from Claude Code
        required_key: Key that must be present in the extracted JSON dict

    Returns:
        Parsed JSON dict if found, None otherwise
    """
    if not output:
        return None

    quoted_key = f'"{required_key}"'

    # Strategy 1: Single-line JSON (scan from end, most likely location)
    for line in reversed(output.split('\n')):
        line = line.strip()
        if line.startswith('{') and line.endswith('}'):
            try:
                result = json.loads(line)
                if isinstance(result, dict) and required_key in result:
                    return result
            except json.JSONDecodeError:
                continue

    # Strategy 2: JSON inside markdown code fences
    fence_pattern = r'```(?:json)?\s*\n(.*?)\n\s*```'
    for match in reversed(list(re.finditer(fence_pattern, output, re.DOTALL))):
        candidate = match.group(1).strip()
        try:
            result = json.loads(candidate)
            if isinstance(result, dict) and required_key in result:
                return result
        except json.JSONDecodeError:
            continue

    # Strategy 3: Brace-balanced extraction for multi-line JSON with required_key
    for match in re.finditer(r'\{', output):
        start = match.start()
        remaining = output[start:start + 50000]  # cap search length
        if quoted_key not in remaining[:500]:
            continue
        # Try to find matching closing brace
        depth = 0
        end = None
        for i, ch in enumerate(remaining):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end:
            candidate = remaining[:end]
            try:
                result = json.loads(candidate)
                if isinstance(result, dict) and required_key in result:
                    return result
            except json.JSONDecodeError:
                continue

    return None


def _extract_characterization_json_from_output(output: str) -> Optional[Dict[str, Any]]:
    """Extract characterization result JSON from Claude Code output.

    Looks for JSON containing a 'characterizations' key (list of per-item results)
    or an 'ontology_tags' key (single-item result).

    Args:
        output: Raw stdout from Claude Code

    Returns:
        Parsed JSON dict if found, None otherwise
    """
    # Try multi-item format first (characterizations list)
    result = _extract_json_with_key(output, "characterizations")
    if result:
        return result

    # Try single-item format (ontology_tags)
    result = _extract_json_with_key(output, "ontology_tags")
    if result:
        return result

    return None


class ClaudeCodeSpawner:
    """Spawns and manages Claude Code tasks via the Claude Agent SDK."""

    # Standard path where the serving repo is cloned for AI inspection
    SERVING_REPO_PATH = Path.home() / ".claudevn" / "repos" / "serving"

    def __init__(
        self,
        workspace_path: str,
        serving_url: str = "http://localhost:8002",
        compute_id: str = "compute-001",
        api_key: str = "",
        git_token: Optional[str] = None,
        event_max_retries: int = 5,
        event_base_delay: float = 1.0,
        max_instances: int = 1,
        serving_repo_url: Optional[str] = None,
        tls_verify: bool = True,
        # Deprecated: kept for backwards compatibility, no longer used
        claude_cli_path: Optional[str] = None,
        ssh_key_path: Optional[str] = None,
    ):
        """Initialize the Claude Code spawner.

        Args:
            workspace_path: Base workspace directory for Claude instances
            serving_url: URL of the serving component
            compute_id: This compute infrastructure's ID
            api_key: API key for authentication with Serving
            git_token: Token for Git HTTP authentication (optional)
            event_max_retries: Maximum retries for failed event deliveries (default: 5)
            event_base_delay: Base delay in seconds for exponential backoff (default: 1.0)
            max_instances: Maximum concurrent Claude Code instances (default: 1)
            serving_repo_url: Git URL of the serving repo — cloned once to
                SERVING_REPO_PATH and pulled on every task start so compute
                workers can inspect serving code during reasoning.
            claude_cli_path: Deprecated, ignored. SDK manages CLI binary.
            ssh_key_path: Deprecated, ignored. Use git_token for HTTP auth.
        """
        if claude_cli_path is not None:
            logger.warning(
                "claude_cli_path is deprecated and ignored. "
                "The Claude Agent SDK manages the CLI binary internally."
            )
        if ssh_key_path is not None:
            logger.warning(
                "ssh_key_path is deprecated and ignored. "
                "Git transport now uses HTTP with token auth."
            )

        self.workspace_path = Path(workspace_path)
        self.serving_url = serving_url.rstrip('/')
        self.compute_id = compute_id
        self.api_key = api_key
        self.git_token = git_token
        self.event_max_retries = event_max_retries
        self.event_base_delay = event_base_delay
        self.max_instances = max_instances
        self.serving_repo_url = serving_repo_url
        self.tls_verify = tls_verify

        # Track running instances and their async execution tasks
        self._instances: Dict[str, Dict[str, Any]] = {}
        self._execution_tasks: Dict[str, asyncio.Task] = {}

        # Metrics for failed events
        self._failed_events_count: int = 0

        # Ensure workspace exists
        self.workspace_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"ClaudeCodeSpawner initialized: workspace={workspace_path}")

    def _run_git_command(
        self,
        args: list,
        cwd: Optional[Path] = None,
        git_token: Optional[str] = None
    ) -> subprocess.CompletedProcess:
        """Run a git command with optional HTTP token authentication.

        Args:
            args: Git command arguments (without 'git' prefix)
            cwd: Working directory for the command
            git_token: Git HTTP token for authentication

        Returns:
            CompletedProcess result

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        env = os.environ.copy()

        # Configure Git credential helper for HTTP token auth.
        # Uses the GIT_ASKPASS approach: a script that echoes the token
        # when git asks for a password.
        token = git_token or self.git_token
        if token:
            # Create a temporary askpass script that returns the token
            askpass_path = self.workspace_path / ".git-askpass.sh"
            askpass_path.write_text(f"#!/bin/sh\necho '{token}'\n")
            askpass_path.chmod(0o700)
            env["GIT_ASKPASS"] = str(askpass_path)
            # Suppress interactive prompts
            env["GIT_TERMINAL_PROMPT"] = "0"

        cmd = ["git"] + args
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            check=True,
            capture_output=True,
            text=True,
            env=env
        )

    def _setup_branch(
        self,
        instance_workspace: Path,
        repo_url: str,
        base_branch: str,
        feature_branch: str,
        git_token: Optional[str] = None
    ) -> Path:
        """Set up Git clone + feature branch for a compute instance.

        Simple workflow per v1.0 architecture (each compute handles one task):
        1. Clone the repository
        2. Create and checkout a feature branch from the base branch

        Args:
            instance_workspace: Base workspace directory for this instance
            repo_url: Repository URL to clone
            base_branch: Base branch name (typically "main")
            feature_branch: Feature branch name for work
            git_token: Git HTTP token for authentication

        Returns:
            Path to the repository working directory

        Raises:
            subprocess.CalledProcessError: If git operations fail
        """
        repo_path = instance_workspace / "repo"

        # Step 1: Clone the repository
        logger.info(f"Cloning repository from {repo_url} to {repo_path}")
        clone_args = ["clone"]
        if base_branch:
            clone_args.extend(["--branch", base_branch])
        clone_args.extend([repo_url, str(repo_path)])

        self._run_git_command(clone_args, git_token=git_token)
        logger.debug(f"Repository cloned to {repo_path}")

        # Step 2: Create and checkout the feature branch
        logger.info(f"Creating feature branch {feature_branch} in {repo_path}")
        self._run_git_command(
            ["checkout", "-b", feature_branch],
            cwd=repo_path
        )
        logger.debug(f"Feature branch {feature_branch} created and checked out")

        self._install_pre_push_hook(repo_path, feature_branch)
        self._exclude_claude_directory(repo_path)

        logger.info(f"Git setup complete: repo={repo_path}, branch={feature_branch}")
        return repo_path

    def _setup_existing_branch(
        self,
        instance_workspace: Path,
        repo_url: str,
        branch: str,
        git_token: Optional[str] = None
    ) -> Path:
        """Set up Git clone and checkout an existing remote branch.

        Used for conflict resolution where we need to work on an existing
        branch rather than creating a new one.

        Args:
            instance_workspace: Base workspace directory for this instance
            repo_url: Repository URL to clone
            branch: Existing remote branch to checkout
            git_token: Git HTTP token for authentication

        Returns:
            Path to the repository working directory

        Raises:
            subprocess.CalledProcessError: If git operations fail
        """
        repo_path = instance_workspace / "repo"

        # Clone the repository (fetches all branches)
        logger.info(f"Cloning repository from {repo_url} to {repo_path}")
        self._run_git_command(
            ["clone", repo_url, str(repo_path)],
            git_token=git_token
        )

        # Checkout the existing remote branch
        logger.info(f"Checking out existing branch {branch} in {repo_path}")
        self._run_git_command(
            ["checkout", branch],
            cwd=repo_path
        )

        self._install_pre_push_hook(repo_path, branch)
        self._exclude_claude_directory(repo_path)

        logger.info(f"Git setup complete: repo={repo_path}, branch={branch}")
        return repo_path

    def _install_pre_push_hook(self, repo_path: Path, expected_branch: str) -> None:
        """Install a pre-push hook that validates the branch name (#57).

        Prevents Claude Code from pushing to any branch other than the assigned one.
        The hook checks the current branch against the expected branch and rejects
        pushes from the wrong branch.

        Args:
            repo_path: Path to the git repository
            expected_branch: The branch name that is allowed to be pushed
        """
        hooks_dir = repo_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        pre_push_hook = hooks_dir / "pre-push"

        hook_content = f"""#!/bin/bash
# ClaudeVN pre-push hook — validates branch before push (#57)
EXPECTED_BRANCH="{expected_branch}"
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

if [ "$CURRENT_BRANCH" != "$EXPECTED_BRANCH" ]; then
    echo "ERROR: Push rejected. Current branch '$CURRENT_BRANCH' does not match" >&2
    echo "       assigned branch '$EXPECTED_BRANCH'." >&2
    echo "       Switch to '$EXPECTED_BRANCH' before pushing." >&2
    exit 1
fi
"""
        pre_push_hook.write_text(hook_content)
        pre_push_hook.chmod(0o755)
        logger.debug(f"Installed pre-push hook for branch {expected_branch} in {repo_path}")

    def _exclude_claude_directory(self, repo_path: Path) -> None:
        """Add .claude/ to .git/info/exclude so Claude Code's internal files
        (session state, todos, settings) are never tracked as uncommitted changes.

        Uses .git/info/exclude instead of .gitignore to keep this local-only
        and avoid modifying the shared repository gitignore. Idempotent.
        """
        exclude_file = repo_path / ".git" / "info" / "exclude"
        exclude_file.parent.mkdir(parents=True, exist_ok=True)
        existing = exclude_file.read_text() if exclude_file.exists() else ""
        if ".claude/" not in existing:
            with open(exclude_file, "a") as f:
                f.write("\n# Claude Code internal files (auto-added by spawner)\n.claude/\n")
            logger.debug(f"Added .claude/ to .git/info/exclude for {repo_path}")
        else:
            logger.debug(f".claude/ already in .git/info/exclude for {repo_path}")

    def _ensure_serving_repo(self) -> None:
        """Ensure the serving repo is cloned and up-to-date at the standard path.

        On first call: performs a shallow clone (--depth 1) of serving_repo_url
        into SERVING_REPO_PATH (~/.claudevn/repos/serving/).

        On subsequent calls: runs git pull --ff-only to fetch latest main.

        Failures are non-blocking — logged as warnings and ignored so they
        never cause a task to fail.
        """
        if not self.serving_repo_url:
            return

        repo_path = self.SERVING_REPO_PATH
        try:
            if not repo_path.exists():
                logger.info(f"Cloning serving repo (shallow) to {repo_path}")
                repo_path.parent.mkdir(parents=True, exist_ok=True)
                self._run_git_command(
                    ["clone", "--depth", "1", self.serving_repo_url, str(repo_path)],
                    git_token=self.git_token,
                )
                logger.info(f"Serving repo cloned to {repo_path}")
            else:
                logger.debug(f"Pulling latest main in serving repo at {repo_path}")
                self._run_git_command(
                    ["pull", "--ff-only", "origin", "main"],
                    cwd=repo_path,
                    git_token=self.git_token,
                )
                logger.debug(f"Serving repo updated at {repo_path}")
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.strip() if e.stderr else str(e)
            logger.warning(f"Serving repo sync failed (non-fatal): {stderr}")
        except Exception as e:
            logger.warning(f"Serving repo sync failed (non-fatal): {e}")

    def _cleanup_workspace(self, instance_workspace: Path) -> None:
        """Clean up workspace directory.

        Args:
            instance_workspace: Instance workspace directory to clean up
        """
        if instance_workspace.exists():
            try:
                shutil.rmtree(instance_workspace)
                logger.debug(f"Cleaned up workspace: {instance_workspace}")
            except Exception as e:
                logger.warning(f"Failed to remove workspace {instance_workspace}: {e}")

    def delete_local_branch(self, branch_name: str) -> bool:
        """Delete a local git branch from the tracked instance's repo.

        Called when Serving confirms a branch has been successfully merged.
        Finds the instance workspace associated with the branch and deletes
        the local branch via ``git branch -d``.

        If the branch does not exist locally (already cleaned up or never
        checked out), the method returns False without raising an error.

        Args:
            branch_name: Full branch name to delete (e.g. "feat/issue-123-foo")

        Returns:
            True if the branch was deleted, False if not found or already gone
        """
        # Find the repo path from tracked instances
        repo_path: Optional[Path] = None
        for instance in self._instances.values():
            if instance.get("branch_name") == branch_name:
                raw = instance.get("repo_path")
                if raw:
                    repo_path = Path(raw)
                break

        if repo_path is None or not repo_path.exists():
            logger.info(
                f"Branch {branch_name!r} not found in tracked instances "
                "(already cleaned up or never checked out) — skipping local delete"
            )
            return False

        try:
            result = subprocess.run(
                ["git", "branch", "-d", branch_name],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.info(f"Deleted local branch {branch_name!r} from {repo_path}")
                return True
            else:
                # Branch may not exist locally — treat as non-fatal
                stderr = result.stderr.strip()
                logger.info(
                    f"Could not delete local branch {branch_name!r} "
                    f"(returncode={result.returncode}): {stderr}"
                )
                return False
        except Exception as e:
            logger.warning(f"Error deleting local branch {branch_name!r}: {e}")
            return False

    async def spawn(self, work_assigned_event: Dict[str, Any]) -> bool:
        """Spawn a Claude Code instance for assigned work.

        Args:
            work_assigned_event: work_assigned event data from Serving

        Returns:
            True if spawned successfully
        """
        task_id = work_assigned_event.get("task_id")
        if not task_id:
            logger.error("No task_id in work_assigned event")
            return False

        # Check capacity limit
        if len(self._instances) >= self.max_instances:
            reason = f"At capacity ({self.max_instances} instance(s))"
            logger.warning(f"{reason}, rejecting task {task_id}")
            await self.send_claude_code_rejected(task_id, reason)
            return False

        # Check if we already have an instance for this task
        if task_id in self._instances:
            logger.warning(f"Claude Code instance already running for task {task_id}")
            return False

        logger.info(f"Spawning Claude Code for task: {task_id}")

        # Generate instance ID
        instance_id = f"cc-{uuid.uuid4().hex[:8]}"

        # Create workspace for this instance
        instance_workspace = self.workspace_path / instance_id
        instance_workspace.mkdir(parents=True, exist_ok=True)

        # Extract context for Git setup
        context = work_assigned_event.get("context", {})
        repo_url = context.get("repository")
        base_branch = context.get("base_branch", "main")
        branch_name = work_assigned_event.get("branch_name")
        git_token = context.get("git_token") or self.git_token

        # Detect conflict resolution tasks — they need an existing branch, not a new one
        is_conflict_resolution = context.get("is_conflict_resolution", False)

        # Set up Git clone + branch if repository info is provided
        repo_path: Optional[Path] = None
        if repo_url:
            # Generate feature branch name if not provided
            if not branch_name:
                branch_name = f"work/{self.compute_id}/{task_id}"

            try:
                if is_conflict_resolution:
                    # Check out the existing conflicting branch rather than creating a new one
                    logger.info(
                        f"Conflict resolution task {task_id}: checking out existing branch {branch_name}"
                    )
                    repo_path = self._setup_existing_branch(
                        instance_workspace=instance_workspace,
                        repo_url=repo_url,
                        branch=branch_name,
                        git_token=git_token,
                    )
                else:
                    repo_path = self._setup_branch(
                        instance_workspace=instance_workspace,
                        repo_url=repo_url,
                        base_branch=base_branch,
                        feature_branch=branch_name,
                        git_token=git_token,
                    )
                logger.info(f"Git branch set up for task {task_id}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to set up Git branch for task {task_id}: {e.stderr}")
                self._cleanup_workspace(instance_workspace)
                await self.send_claude_code_failed(task_id, instance_id, f"Git setup failed: {e.stderr}", exit_code=-1)
                return False
            except Exception as e:
                logger.error(f"Failed to set up Git branch for task {task_id}: {e}")
                self._cleanup_workspace(instance_workspace)
                await self.send_claude_code_failed(task_id, instance_id, f"Git setup failed: {e}", exit_code=-1)
                return False
        else:
            logger.warning(f"No repository URL provided for task {task_id}, skipping Git setup")

        # Determine working directory: repo clone if available, else instance workspace
        working_dir = repo_path if repo_path else instance_workspace

        # Ensure serving repo is present and current for AI reasoning
        self._ensure_serving_repo()

        # Create CLAUDE.md in the working directory
        claude_md_content = self._create_claude_md(work_assigned_event)
        claude_md_path = working_dir / "CLAUDE.md"
        claude_md_path.write_text(claude_md_content)
        logger.debug(f"Created CLAUDE.md at {claude_md_path}")

        # Set up MCP tools — copies script to workspace and returns SDK config
        mcp_servers = self._setup_mcp_tools(working_dir, work_assigned_event)
        logger.debug(f"Set up MCP tools in {working_dir}")

        # Record instance metadata
        self._instances[task_id] = {
            "instance_id": instance_id,
            "task_id": task_id,
            "workspace": str(instance_workspace),
            "working_dir": str(working_dir),
            "repo_path": str(repo_path) if repo_path else None,
            "branch_name": branch_name if repo_url else None,
            "started_at": datetime.now(timezone.utc),
            "event": work_assigned_event
        }

        # Execute the task via SDK
        try:
            await self._start_task(
                task_id, instance_id, working_dir,
                work_assigned_event, mcp_servers
            )

            # Send claude_code_started event to Serving
            await self.send_claude_code_started(task_id, instance_id)

            return True
        except Exception as e:
            logger.error(f"Failed to start Claude Code for task {task_id}: {e}")

            # Clean up
            del self._instances[task_id]
            if repo_url:
                self._cleanup_workspace(instance_workspace)
            await self.send_claude_code_failed(task_id, instance_id, str(e), exit_code=-1)

            return False

    async def spawn_conflict_resolution(self, conflict_data: Dict[str, Any]) -> bool:
        """Spawn a Claude Code instance specifically for conflict resolution.

        Checks out the existing conflicting branch (not creating a new one),
        writes conflict-resolution CLAUDE.md, and spawns Claude Code to
        rebase, resolve, and force-push.

        Args:
            conflict_data: merge_conflict event data containing issue_id,
                branch, conflicting_files, main_head, message

        Returns:
            True if spawned successfully
        """
        branch = conflict_data.get("branch", "")
        issue_id = conflict_data.get("issue_id", "unknown")
        conflicting_files = conflict_data.get("conflicting_files", [])
        main_head = conflict_data.get("main_head", "")
        message = conflict_data.get("message", "")

        if not branch:
            logger.error("No branch in conflict_data, cannot spawn resolver")
            return False

        # Check capacity limit
        if len(self._instances) >= self.max_instances:
            logger.warning(
                f"At capacity ({self.max_instances} instance(s)), "
                f"rejecting conflict resolution for {branch}"
            )
            return False

        # Find repo URL from an existing instance's context
        repo_url = None
        git_token = self.git_token
        for inst in self._instances.values():
            event = inst.get("event", {})
            ctx = event.get("context", {})
            if ctx.get("repository"):
                repo_url = ctx["repository"]
                git_token = ctx.get("git_token") or git_token
                break

        if not repo_url:
            logger.error(
                f"No repository URL available to spawn conflict resolver "
                f"for branch {branch}"
            )
            return False

        # Build a synthetic task_id for this conflict resolution
        task_id = f"conflict-{issue_id}-{uuid.uuid4().hex[:8]}"

        if task_id in self._instances:
            logger.warning(f"Conflict resolver already running for {task_id}")
            return False

        logger.info(
            f"Spawning conflict resolver: task_id={task_id}, "
            f"branch={branch}, files={conflicting_files}"
        )

        # Create workspace
        instance_id = f"cc-{uuid.uuid4().hex[:8]}"
        instance_workspace = self.workspace_path / instance_id
        instance_workspace.mkdir(parents=True, exist_ok=True)

        # Clone and checkout the existing branch (not creating a new one)
        try:
            repo_path = self._setup_existing_branch(
                instance_workspace=instance_workspace,
                repo_url=repo_url,
                branch=branch,
                git_token=git_token
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set up branch for conflict resolver: {e.stderr}")
            self._cleanup_workspace(instance_workspace)
            return False

        # Build conflict resolution CLAUDE.md
        files_list = "\n".join(f"  - `{f}`" for f in conflicting_files)
        work_event = {
            "task_id": task_id,
            "title": f"Resolve merge conflicts on {branch}",
            "description": (
                f"## Conflict Resolution Task\n\n"
                f"Your branch `{branch}` has merge conflicts with main.\n\n"
                f"### Conflicting Files\n{files_list}\n\n"
                f"### Steps\n"
                f"1. `git fetch origin main`\n"
                f"2. `git rebase origin/main`\n"
                f"3. Resolve conflicts in the listed files\n"
                f"4. `git add -A && git rebase --continue`\n"
                f"5. `git push --force-with-lease origin {branch}`\n\n"
                f"### Message from Serving\n{message}"
            ),
            "branch_name": branch,
            "skills": {
                "merged_instructions": (
                    "You are a conflict resolution specialist. "
                    "Your only job is to rebase the current branch onto main, "
                    "resolve all merge conflicts, and push the result. "
                    "Do NOT create new features or modify behavior."
                )
            },
            "context": {
                "repository": repo_url,
                "base_branch": "main",
                "git_token": git_token,
            },
            "mcp_config": {}
        }

        # Create CLAUDE.md
        claude_md_content = self._create_claude_md(work_event)
        claude_md_path = repo_path / "CLAUDE.md"
        claude_md_path.write_text(claude_md_content)

        # Set up MCP tools
        mcp_servers = self._setup_mcp_tools(repo_path, work_event)

        # Record instance metadata
        self._instances[task_id] = {
            "instance_id": instance_id,
            "task_id": task_id,
            "workspace": str(instance_workspace),
            "working_dir": str(repo_path),
            "repo_path": str(repo_path),
            "branch_name": branch,
            "started_at": datetime.now(timezone.utc),
            "event": work_event
        }

        # Start the task via SDK
        try:
            await self._start_task(
                task_id, instance_id, repo_path,
                work_event, mcp_servers
            )
            await self.send_claude_code_started(task_id, instance_id)
            return True
        except Exception as e:
            logger.error(f"Failed to start conflict resolver for {task_id}: {e}")
            del self._instances[task_id]
            self._cleanup_workspace(instance_workspace)
            await self.send_claude_code_failed(
                task_id, instance_id, str(e), exit_code=-1
            )
            return False

    @staticmethod
    def _classify_task_complexity(work_type: str, title: str, description: str) -> str:
        """Classify task complexity based on work type and content.

        Returns one of: 'simple', 'standard', 'complex'.

        Simple tasks (docs, scaffolding, small fixes) get lower effort/turns.
        Standard tasks (implementation, bug fixes) get moderate limits.
        Complex tasks (architecture, research, decomposition) get higher limits.

        Args:
            work_type: Work type from the work_assigned event (task, bug, feature, docs, etc.)
            title: Task title
            description: Task description

        Returns:
            Complexity level: 'simple', 'standard', or 'complex'
        """
        title_lower = title.lower()
        desc_lower = description.lower()
        combined = f"{title_lower} {desc_lower}"

        # Simple: docs, scaffolding, config, formatting
        simple_types = {"docs", "documentation"}
        simple_keywords = [
            "scaffold", "stub", "placeholder", "readme", "documentation",
            "formatting", "lint", "config", "rename", "typo",
        ]
        if work_type in simple_types:
            return "simple"
        if any(kw in combined for kw in simple_keywords):
            return "simple"

        # Complex: architecture, research, decomposition, multi-component
        complex_keywords = [
            "architect", "design", "research", "decompos", "refactor",
            "migration", "multi-component", "system-wide", "cross-cutting",
        ]
        if any(kw in combined for kw in complex_keywords):
            return "complex"

        # Standard: everything else (bug, feature, task, review, test, etc.)
        return "standard"

    @staticmethod
    def _get_effort_for_complexity(complexity: str) -> str:
        """Map complexity to SDK effort level.

        Args:
            complexity: One of 'simple', 'standard', 'complex'

        Returns:
            SDK effort value: 'low', 'medium', or 'high'
        """
        return {"simple": "low", "standard": "medium", "complex": "high"}.get(
            complexity, "medium"
        )

    @staticmethod
    def _get_max_turns_for_complexity(complexity: str) -> int:
        """Map complexity to max_turns safety net.

        Args:
            complexity: One of 'simple', 'standard', 'complex'

        Returns:
            Maximum conversation turns
        """
        return {"simple": 30, "standard": 50, "complex": 100}.get(complexity, 50)

    def _build_stable_system_instructions(self) -> str:
        """Build stable instructions for the system_prompt append field (#58).

        These instructions are identical across all tasks on this compute instance
        and benefit from prompt caching. Dynamic per-task content goes in CLAUDE.md.

        Returns:
            Stable instruction text for system_prompt append
        """
        sections = [
            "## ClaudeVN Compute Instance",
            "",
            f"You are running as compute instance `{self.compute_id}`.",
            "",
            "## Git Conventions",
            "",
            "When working on a Git branch:",
            "- Stage all changes: `git add -A`",
            '- Commit with a descriptive message: `git commit -m "<description>"`',
            "- Push your assigned branch explicitly (do not use `git push origin HEAD`)",
            "- CRITICAL: Do NOT create or switch branches. Do NOT run: "
            "`git checkout -b`, `git switch -c`, `git branch`",
            "- You MUST commit and push your changes before finishing",
            "- The system relies on your branch having commits to create PRs and merge",
            "",
            "## Output Format",
            "",
            "IMPORTANT: Output your result as valid JSON at the end of your response.",
            "Your JSON output should be on a single line starting with `{` and ending with `}`.",
            "The system will parse this JSON to get your result.",
            "",
            "For decomposition tasks, output JSON like:",
            "```",
            '{"issues": [...], "confidence": 0.85, "reasoning": "..."}',
            "```",
            "",
        ]

        # Serving repo availability is stable per-instance
        if self.serving_repo_url and self.SERVING_REPO_PATH.exists():
            sections.extend([
                "## Serving Repository",
                "",
                f"The ClaudeVN serving codebase is available at `{self.SERVING_REPO_PATH}` (shallow clone of main).",
                "Inspect it to understand existing patterns, module structure, and conventions before making decisions.",
                "This repo is updated with `git pull` at the start of every task.",
                "",
            ])

        return "\n".join(sections)

    def _build_system_prompt(self) -> Dict[str, Any]:
        """Build the system_prompt configuration for the Agent SDK (#58).

        Uses the ``claude_code`` preset for full Claude Code behavior and
        appends stable ClaudeVN-specific instructions. The SDK automatically
        applies cache_control markers to system prompt blocks.

        Returns:
            Dict suitable for ClaudeAgentOptions.system_prompt
        """
        return {
            "type": "preset",
            "preset": "claude_code",
            "append": self._build_stable_system_instructions(),
        }

    def _create_claude_md(self, work_assigned_event: Dict[str, Any]) -> str:
        """Create CLAUDE.md content with per-task dynamic content (#58).

        Stable instructions (git conventions, output format, serving repo) are
        now in the system_prompt append field for prompt caching. This method
        only generates task-specific content.

        Args:
            work_assigned_event: work_assigned event data

        Returns:
            CLAUDE.md content as string
        """
        task_id = work_assigned_event.get("task_id", "unknown")
        title = work_assigned_event.get("title", "Untitled task")
        description = work_assigned_event.get("description", "")
        skills = work_assigned_event.get("skills", {})
        context = work_assigned_event.get("context", {})

        # Get merged instructions from skills
        merged_instructions = skills.get("merged_instructions", "")

        # Build CLAUDE.md — per-task dynamic content only
        sections = [
            f"# Task: {title}",
            "",
            f"**Task ID:** {task_id}",
            "",
            "## Description",
            "",
            description,
            "",
            "## Skills",
            "",
            merged_instructions if merged_instructions else "No specific skills provided.",
            "",
            "## Context",
            "",
        ]

        # Add context details
        if context.get("repository"):
            sections.append(f"**Repository:** {context['repository']}")
        if context.get("base_branch"):
            sections.append(f"**Base Branch:** {context['base_branch']}")
        if context.get("relevant_files"):
            sections.append("\n**Relevant Files:**")
            for f in context["relevant_files"]:
                sections.append(f"  - {f}")
        if context.get("requirements"):
            sections.append(f"\n**Requirements:**\n{context['requirements']}")

        # Branch assignment — task-specific details (branch name, base)
        if context.get("repository"):
            branch_name = work_assigned_event.get("branch_name", "")
            sections.extend([
                "",
                "## Branch Assignment",
                "",
                f"- **Branch:** `{branch_name}`",
                f"- **Base:** `{context.get('base_branch', 'main')}`",
                f"- Push command: `git push origin {branch_name}`",
                "",
            ])

        # Scope constraints to prevent over-scoping (#60)
        sections.extend([
            "## Scope",
            "",
            "Focus ONLY on what the task description asks for. Do not:",
            "- Add functionality beyond what is requested",
            "- Write comprehensive test suites — only write Tier 1 tests "
            "(mockable unit tests covering new functionality)",
            "- Create detailed documentation unless documentation is the task",
            "- Refactor or improve unrelated code",
            "",
        ])

        return "\n".join(sections)

    def _setup_mcp_tools(
        self, working_dir: Path, work_assigned_event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Set up MCP tools for the SDK executor.

        Copies the MCP stdio server script to the workspace and returns
        the MCP server configuration dict for ClaudeAgentOptions.mcp_servers.

        Args:
            working_dir: The working directory for the Claude instance
            work_assigned_event: work_assigned event data

        Returns:
            MCP server configuration dict for SDK
        """
        # Find bundled MCP script locations
        mcp_script_candidates = [
            Path("/app/mcp/stdio_server.py"),  # Bundled in compute container
            Path(__file__).parent.parent / "mcp" / "stdio_server.py",  # Local dev
            Path(__file__).parent.parent.parent / "serving" / "mcp" / "stdio_server.py",  # Sibling dir
        ]

        mcp_script_src = None
        for candidate in mcp_script_candidates:
            if candidate.exists():
                mcp_script_src = candidate
                break

        # Copy MCP script to workspace if found
        mcp_script_dest = working_dir / "mcp_stdio_server.py"
        if mcp_script_src:
            shutil.copy(mcp_script_src, mcp_script_dest)
            logger.debug(f"Copied MCP script from {mcp_script_src} to {mcp_script_dest}")
        else:
            logger.warning("MCP server script not found in any candidate location")
            # Create a stub that logs an error
            mcp_script_dest.write_text('''#!/usr/bin/env python
"""MCP stub - actual script not found at build time."""
import sys
print("ERROR: MCP stdio_server.py not bundled in compute container", file=sys.stderr)
sys.exit(1)
''')

        # Build MCP server config for the SDK
        mcp_config_data = work_assigned_event.get("mcp_config", {})
        server_url = mcp_config_data.get("server_url", self.serving_url)
        task_api_key = mcp_config_data.get("api_key", self.api_key)

        return build_mcp_servers(
            mcp_script_path=mcp_script_dest.resolve(),
            server_url=server_url,
            compute_id=self.compute_id,
            api_key=task_api_key,
        )

    async def _start_task(
        self,
        task_id: str,
        instance_id: str,
        workspace: Path,
        work_assigned_event: Dict[str, Any],
        mcp_servers: Dict[str, Any],
    ) -> None:
        """Start a Claude Code task via the SDK executor.

        Launches the SDK query() call in a background async task that
        handles the full lifecycle: execution, result processing, event
        reporting, and cleanup.

        Args:
            task_id: Task ID
            instance_id: Claude Code instance ID
            workspace: Instance workspace directory
            work_assigned_event: work_assigned event data
            mcp_servers: MCP server configuration for SDK
        """
        # Extract model from work assignment (set by serving's model resolution)
        model = work_assigned_event.get("model")
        if model:
            logger.info(f"Task {task_id}: using model {model}")
        else:
            logger.info(f"Task {task_id}: using default model (no model specified)")
        # Build environment variables for the SDK subprocess
        env_vars: Dict[str, str] = {}
        env_vars["CLAUDEVN_COMPUTE_ID"] = self.compute_id
        env_vars["CLAUDEVN_TASK_ID"] = task_id
        env_vars["CLAUDEVN_INSTANCE_ID"] = instance_id
        env_vars["CLAUDEVN_SERVING_URL"] = self.serving_url

        # Add context from work assignment
        context = work_assigned_event.get("context", {})
        if context.get("repository"):
            env_vars["CLAUDEVN_REPOSITORY"] = context["repository"]
        if context.get("base_branch"):
            env_vars["CLAUDEVN_BASE_BRANCH"] = context["base_branch"]

        # Set GIT_ASKPASS so Claude Code can push/pull via HTTP token auth
        git_token = context.get("git_token") or self.git_token
        if git_token:
            askpass_script = self.workspace_path / instance_id / ".git-askpass"
            askpass_script.write_text(f"#!/bin/sh\necho '{git_token}'\n")
            askpass_script.chmod(0o700)
            env_vars["GIT_ASKPASS"] = str(askpass_script.resolve())
            env_vars["GIT_TERMINAL_PROMPT"] = "0"

        # Classify task complexity for effort/max_turns (#60)
        title = work_assigned_event.get("title", "")
        description = work_assigned_event.get("description", "")
        work_type = work_assigned_event.get("work_type", "task")
        complexity = self._classify_task_complexity(work_type, title, description)
        effort = self._get_effort_for_complexity(complexity)
        max_turns = self._get_max_turns_for_complexity(complexity)
        logger.info(
            f"Task {task_id}: complexity={complexity}, effort={effort}, max_turns={max_turns}"
        )

        # Direct prompt with task context instead of generic "read CLAUDE.md" (#60)
        initial_prompt = (
            f"Complete this task: {title}\n\n"
            f"{description}\n\n"
            "Read CLAUDE.md for additional context and scope constraints. "
            "Evaluate what you can accomplish but keep your focus strictly on "
            "what the task description asks for. Do not over-deliver.\n\n"
            "Output your final result as a JSON object on a single line."
        )

        # Build system prompt with claude_code preset for caching (#58)
        system_prompt = self._build_system_prompt()

        logger.info(f"Starting SDK task execution in {workspace}")

        # Launch the execution in a background async task
        self._execution_tasks[task_id] = asyncio.create_task(
            self._run_and_handle_result(
                task_id=task_id,
                instance_id=instance_id,
                prompt=initial_prompt,
                cwd=workspace,
                mcp_servers=mcp_servers,
                env_vars=env_vars,
                system_prompt=system_prompt,
                model=model,
                effort=effort,
                max_turns=max_turns,
            )
        )

    async def _run_and_handle_result(
        self,
        task_id: str,
        instance_id: str,
        prompt: str,
        cwd: Path,
        mcp_servers: Dict[str, Any],
        env_vars: Dict[str, str],
        system_prompt: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        max_turns: Optional[int] = None,
    ) -> None:
        """Execute a task via SDK and handle the result.

        This runs as a background async task. It calls the SDK executor,
        processes the result (commit/push safety net, JSON extraction),
        and reports the appropriate event to Serving.

        Args:
            task_id: Task ID
            instance_id: Claude Code instance ID
            prompt: Task prompt
            cwd: Working directory
            mcp_servers: MCP server configuration
            env_vars: Environment variables
            system_prompt: System prompt configuration for caching (#58)
            model: Claude model identifier (None = use default)
            effort: SDK effort level (None = use default)
            max_turns: Maximum conversation turns (None = unlimited)
        """
        instance = self._instances.get(task_id)
        started_at = instance["started_at"] if instance else datetime.now(timezone.utc)

        try:
            # Execute via SDK
            result: ExecutionResult = await execute_task(
                prompt=prompt,
                cwd=cwd,
                mcp_servers=mcp_servers,
                env_vars=env_vars,
                system_prompt=system_prompt,
                model=model,
                effort=effort,
                max_turns=max_turns,
            )

            stopped_at = datetime.now(timezone.utc)
            duration = (stopped_at - started_at).total_seconds()
            # Prefer SDK-reported duration if available
            if result.duration_ms > 0:
                duration = result.duration_ms / 1000.0

            logger.info(
                f"SDK execution finished: instance={instance_id}, "
                f"success={result.success}, duration={duration:.1f}s, "
                f"tools_used={len(result.tool_calls)}"
            )

            if result.success:
                if result.output:
                    logger.info(f"Claude Code output for {instance_id}: {result.output[:500]}...")

                # Safety net: commit and push any uncommitted changes
                push_ok = True
                if instance and instance.get("repo_path"):
                    push_ok = await self._commit_and_push_changes(
                        task_id, instance_id, instance
                    )

                if not push_ok:
                    await self.send_claude_code_failed(
                        task_id=task_id,
                        instance_id=instance_id,
                        error="Git push failed after retries — work completed but code not pushed",
                        exit_code=2,
                    )
                else:
                    # Try to extract and submit JSON result
                    await self._submit_result(task_id, instance_id, result.output, instance)

                    branch_name = instance.get("branch_name") if instance else None

                    await self.send_claude_code_completed(
                        task_id=task_id,
                        instance_id=instance_id,
                        exit_code=result.exit_code,
                        duration_seconds=int(duration),
                        branch_name=branch_name,
                        duration_ms=result.duration_ms,
                        session_id=result.session_id,
                        cost_usd=result.cost_usd,
                        duration_api_ms=result.duration_api_ms if result.duration_api_ms > 0 else None,
                        num_turns=result.num_turns if result.num_turns > 0 else None,
                        input_tokens=result.input_tokens if result.input_tokens > 0 else None,
                        output_tokens=result.output_tokens if result.output_tokens > 0 else None,
                        cache_read_tokens=result.cache_read_tokens if result.cache_read_tokens > 0 else None,
                        cache_creation_tokens=result.cache_creation_tokens if result.cache_creation_tokens > 0 else None,
                        tool_timings=result.tool_timings if result.tool_timings else None,
                    )
            else:
                error_msg = result.error or f"SDK execution failed with exit code {result.exit_code}"
                await self.send_claude_code_failed(
                    task_id=task_id,
                    instance_id=instance_id,
                    error=error_msg,
                    exit_code=result.exit_code,
                )

        except asyncio.CancelledError:
            logger.info(f"Task execution cancelled for {task_id}")
            await self.send_claude_code_failed(
                task_id=task_id,
                instance_id=instance_id,
                error="Task execution cancelled",
                exit_code=-1,
            )
        except Exception as e:
            logger.error(f"Error in task execution for {task_id}: {e}")
            await self.send_claude_code_failed(
                task_id=task_id,
                instance_id=instance_id,
                error=str(e),
                exit_code=-1,
            )
        finally:
            self._cleanup_instance(task_id)

    def _cleanup_instance(self, task_id: str, cleanup_workspace: bool = False) -> None:
        """Clean up instance resources.

        Args:
            task_id: Task ID to clean up
            cleanup_workspace: Whether to remove the workspace directory
        """
        # Remove from tracking
        if task_id in self._instances:
            instance = self._instances.pop(task_id)
            logger.debug(f"Cleaned up instance for task {task_id}")

            # Clean up workspace if requested
            if cleanup_workspace:
                workspace = Path(instance["workspace"])
                self._cleanup_workspace(workspace)

        if task_id in self._execution_tasks:
            del self._execution_tasks[task_id]

    async def _submit_result(
        self,
        task_id: str,
        instance_id: str,
        output: str,
        instance: Optional[Dict[str, Any]]
    ) -> None:
        """Parse and submit the result from Claude's output.

        Handles both decomposition (decomp-*) and characterization (char-*) tasks.
        Extracts JSON from stdout and POSTs to the appropriate serving endpoint.

        Args:
            task_id: Task ID
            instance_id: Claude instance ID
            output: Claude's stdout output
            instance: Instance metadata
        """
        if not output:
            logger.warning(f"No output to parse for {instance_id}")
            return

        if task_id.startswith("decomp-"):
            await self._submit_decomposition_result(task_id, instance_id, output, instance)
        elif task_id.startswith("char-"):
            await self._submit_characterization_result(task_id, instance_id, output, instance)
        else:
            logger.debug(f"Task {task_id} is not a decomposition or characterization task, skipping result submission")

    async def _submit_decomposition_result(
        self,
        task_id: str,
        instance_id: str,
        output: str,
        instance: Optional[Dict[str, Any]]
    ) -> None:
        """Extract and submit decomposition result to serving.

        Args:
            task_id: Decomposition task ID (format: decomp-{uuid})
            instance_id: Claude instance ID
            output: Claude's stdout output
            instance: Instance metadata
        """
        decomposition_id = task_id

        json_result = _extract_json_from_output(output)

        if json_result:
            logger.info(f"Found decomposition JSON in output for {instance_id}")
        else:
            # Not a warning: decompositions are typically submitted via MCP during
            # execution, so output parsing is just a fallback. Missing JSON in stdout
            # is expected when MCP succeeded.
            logger.debug(f"No decomposition JSON in output for {instance_id} (likely submitted via MCP)")
            return

        # Get goal_id from instance event
        goal_id = None
        if instance and instance.get("event"):
            event = instance["event"]
            context = event.get("context", {})
            goal_id = context.get("goal_id")

        if not goal_id:
            logger.warning(f"No goal_id found for decomposition {decomposition_id}")

        submit_data = {
            "decomposition_id": decomposition_id,
            "goal_id": goal_id or "unknown",
            "issues": json_result.get("issues", []),
            "confidence": json_result.get("confidence", 0.5),
            "reasoning": json_result.get("reasoning", "")
        }

        try:
            url = f"{self.serving_url}/api/v1/compute/decomposition/{decomposition_id}/result"
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            async with httpx.AsyncClient(verify=self.tls_verify) as client:
                response = await client.post(url, json=submit_data, headers=headers, timeout=30.0)
                if response.status_code == 200:
                    resp_data = response.json()
                    if resp_data.get("status") == "already_stored":
                        logger.info(
                            f"Decomposition {decomposition_id} already submitted via MCP, "
                            "skipping duplicate REST submission"
                        )
                    else:
                        logger.info(f"Submitted decomposition result for {decomposition_id}")
                else:
                    logger.warning(
                        f"Failed to submit decomposition result: HTTP {response.status_code} - {response.text}"
                    )
        except Exception as e:
            logger.error(f"Error submitting decomposition result: {e}")

    async def _submit_characterization_result(
        self,
        task_id: str,
        instance_id: str,
        output: str,
        instance: Optional[Dict[str, Any]]
    ) -> None:
        """Extract and submit characterization result to serving.

        Args:
            task_id: Characterization task ID (format: char-{uuid})
            instance_id: Claude instance ID
            output: Claude's stdout output
            instance: Instance metadata
        """
        characterization_id = task_id

        json_result = _extract_characterization_json_from_output(output)

        if json_result:
            logger.info(f"Found characterization JSON in output for {instance_id}")
        else:
            # Not a warning: characterizations are typically submitted via MCP during
            # execution, so output parsing is just a fallback. Missing JSON in stdout
            # is expected when MCP succeeded.
            logger.debug(f"No characterization JSON in output for {instance_id} (likely submitted via MCP)")
            return

        # Get project_id from instance event context
        project_id = None
        if instance and instance.get("event"):
            event = instance["event"]
            context = event.get("context", {})
            project_id = context.get("project_id")

        if not project_id:
            logger.warning(f"No project_id found for characterization {characterization_id}")

        submit_data = {
            "characterization_id": characterization_id,
            "project_id": project_id or "unknown",
            "characterizations": json_result.get("characterizations", []),
        }

        # If the output is a single-item result (ontology_tags at top level),
        # wrap it into the characterizations list format
        if "ontology_tags" in json_result and "characterizations" not in json_result:
            submit_data["characterizations"] = [json_result]

        try:
            url = f"{self.serving_url}/api/v1/compute/characterization/{characterization_id}/result"
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            async with httpx.AsyncClient(verify=self.tls_verify) as client:
                response = await client.post(url, json=submit_data, headers=headers, timeout=30.0)
                if response.status_code == 200:
                    logger.info(f"Submitted characterization result for {characterization_id}")
                else:
                    logger.warning(
                        f"Failed to submit characterization result: HTTP {response.status_code} - {response.text}"
                    )
        except Exception as e:
            logger.error(f"Error submitting characterization result: {e}")

    def _verify_and_fix_branch(
        self,
        repo_dir: Path,
        expected_branch: str,
        instance_id: str,
    ) -> bool:
        """Verify HEAD is on the expected branch and recover if not (#57).

        If Claude Code switched to a different branch, this method:
        1. Logs a WARNING with both branch names
        2. Checks out the expected branch
        3. Cherry-picks all commits from the wrong branch that aren't in expected

        Args:
            repo_dir: Path to the git repository
            expected_branch: The branch name the instance should be on
            instance_id: Instance ID for logging

        Returns:
            True if branch is correct (or was recovered), False if recovery failed
        """
        try:
            current_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(repo_dir), capture_output=True, text=True, check=True
            )
            current_branch = current_result.stdout.strip()

            if current_branch == expected_branch:
                return True

            logger.warning(
                f"Branch mismatch for {instance_id}: "
                f"expected '{expected_branch}', found '{current_branch}'"
            )

            # Get commits on the wrong branch that aren't in expected branch
            wrong_branch_tip = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(repo_dir), capture_output=True, text=True, check=True
            ).stdout.strip()

            # Find commits unique to the wrong branch (not in expected)
            log_result = subprocess.run(
                ["git", "log", f"{expected_branch}..{current_branch}",
                 "--reverse", "--format=%H"],
                cwd=str(repo_dir), capture_output=True, text=True, check=True
            )
            commits_to_recover = [
                c for c in log_result.stdout.strip().splitlines() if c
            ]

            # Switch to expected branch
            subprocess.run(
                ["git", "checkout", expected_branch],
                cwd=str(repo_dir), capture_output=True, text=True, check=True
            )

            if commits_to_recover:
                logger.info(
                    f"Recovering {len(commits_to_recover)} commit(s) from "
                    f"'{current_branch}' to '{expected_branch}' for {instance_id}"
                )
                for commit_hash in commits_to_recover:
                    try:
                        subprocess.run(
                            ["git", "cherry-pick", commit_hash],
                            cwd=str(repo_dir), capture_output=True, text=True,
                            check=True
                        )
                    except subprocess.CalledProcessError as cp_err:
                        logger.error(
                            f"Cherry-pick of {commit_hash[:8]} failed for "
                            f"{instance_id}: {cp_err.stderr or cp_err.stdout}. "
                            f"Aborting cherry-pick."
                        )
                        subprocess.run(
                            ["git", "cherry-pick", "--abort"],
                            cwd=str(repo_dir), capture_output=True, text=True
                        )
                        return False

                logger.info(
                    f"Successfully recovered work from '{current_branch}' "
                    f"to '{expected_branch}' for {instance_id}"
                )
            else:
                # No unique commits — maybe work is uncommitted (handled elsewhere)
                logger.info(
                    f"No commits to recover from '{current_branch}' for "
                    f"{instance_id}, switched to '{expected_branch}'"
                )

            return True

        except subprocess.CalledProcessError as e:
            logger.error(
                f"Branch verification failed for {instance_id}: "
                f"{e.stderr or e.stdout}"
            )
            return False

    async def _commit_and_push_changes(
        self,
        task_id: str,
        instance_id: str,
        instance: Dict[str, Any],
        max_retries: int = 3,
        base_delay: float = 2.0,
    ) -> bool:
        """Safety net: commit and push any uncommitted changes after Claude exits.

        If Claude didn't commit/push its work, this ensures changes are not lost.
        Verifies branch before pushing and recovers work if branch changed (#57).
        Retries push on transient failures with exponential backoff (#831).

        Args:
            task_id: Task ID
            instance_id: Claude Code instance ID
            instance: Instance metadata dict
            max_retries: Maximum push attempts
            base_delay: Base delay in seconds between retries

        Returns:
            True if push succeeded (or no push needed), False if push failed
        """
        repo_path = instance.get("repo_path")
        if not repo_path:
            return True  # Nothing to push

        repo_dir = Path(repo_path)
        if not repo_dir.exists():
            return True  # Nothing to push

        # Build HTTP token auth environment for git push.
        # Since the service runs as 'compute' user (same as Claude CLI),
        # there are no ownership mismatches — git operations work directly.
        event = instance.get("event", {})
        context = event.get("context", {})
        git_token = context.get("git_token") or self.git_token

        try:
            # Verify branch before committing/pushing (#57)
            expected_branch = instance.get("branch_name")
            if expected_branch:
                if not self._verify_and_fix_branch(
                    repo_dir, expected_branch, instance_id
                ):
                    logger.error(
                        f"Branch recovery failed for {instance_id}. "
                        f"Attempting push from current branch as fallback."
                    )

            # Check for uncommitted changes
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(repo_dir),
                capture_output=True, text=True
            )
            status_output = status_result.stdout.strip()
            if not status_output:
                logger.debug(f"No uncommitted changes for {instance_id}")
                # Still try to push in case there are unpushed commits
            else:
                # Check if all changes are in .claude/ (shouldn't happen after exclude fix,
                # but handle gracefully if it does)
                non_claude_changes = [
                    line for line in status_output.splitlines()
                    if '.claude/' not in line
                ]
                if non_claude_changes:
                    logger.info(f"Found uncommitted changes for {instance_id}, committing...")
                else:
                    logger.debug(
                        f"Found only .claude/ changes for {instance_id} "
                        f"(unexpected after exclude fix), committing..."
                    )
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=str(repo_dir), check=True,
                    capture_output=True, text=True
                )
                subprocess.run(
                    ["git", "commit", "-m",
                     f"Auto-commit: work completed for task {task_id}"],
                    cwd=str(repo_dir), check=True,
                    capture_output=True, text=True
                )

            # Push to expected branch explicitly (#57) with retry (#831)
            # using HTTP token auth (#14)
            push_env = os.environ.copy()
            if git_token:
                askpass_script = repo_dir / ".git-askpass"
                askpass_script.write_text(f"#!/bin/sh\necho '{git_token}'\n")
                askpass_script.chmod(0o700)
                push_env["GIT_ASKPASS"] = str(askpass_script.resolve())
                push_env["GIT_TERMINAL_PROMPT"] = "0"

            # Use explicit branch name in push to avoid pushing wrong branch
            push_refspec = f"HEAD:{expected_branch}" if expected_branch else "HEAD"

            last_error = None
            for attempt in range(1, max_retries + 1):
                try:
                    subprocess.run(
                        ["git", "push", "origin", push_refspec],
                        cwd=str(repo_dir), check=True,
                        capture_output=True, text=True, env=push_env
                    )
                    logger.info(f"Pushed changes for {instance_id} (task {task_id})")
                    return True
                except subprocess.CalledProcessError as push_err:
                    last_error = push_err
                    if attempt < max_retries:
                        delay = base_delay * (2 ** (attempt - 1))
                        logger.warning(
                            f"Push attempt {attempt}/{max_retries} failed for {instance_id}: "
                            f"{push_err.stderr or push_err.stdout}. Retrying in {delay}s..."
                        )
                        await asyncio.sleep(delay)

            # All retries exhausted
            logger.error(
                f"Git push failed after {max_retries} attempts for {instance_id}: "
                f"{last_error.stderr or last_error.stdout if last_error else 'unknown'}"
            )
            return False

        except subprocess.CalledProcessError as e:
            logger.error(
                f"Git commit failed for {instance_id}: {e.stderr or e.stdout}"
            )
            return False
        except Exception as e:
            logger.error(f"Error in commit/push safety net for {instance_id}: {e}")
            return False

    async def stop(self, task_id: str, force: bool = False, timeout: int = 30) -> bool:
        """Stop a Claude Code instance.

        Args:
            task_id: Task ID of instance to stop
            force: Force cancel if graceful stop fails
            timeout: Timeout for graceful stop (unused with SDK, kept for API compat)

        Returns:
            True if stopped successfully
        """
        if task_id not in self._instances:
            logger.warning(f"No instance found for task {task_id}")
            return False

        instance = self._instances[task_id]
        instance_id = instance["instance_id"]
        execution_task = self._execution_tasks.get(task_id)

        if not execution_task:
            logger.warning(f"No execution task found for task {task_id}")
            self._cleanup_instance(task_id)
            return True

        logger.info(f"Stopping Claude Code: instance={instance_id}, task={task_id}")

        try:
            # Cancel the async execution task
            execution_task.cancel()

            try:
                await asyncio.wait_for(execution_task, timeout=timeout)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

            logger.info(f"Claude Code stopped: {instance_id}")
            self._cleanup_instance(task_id)
            return True

        except Exception as e:
            logger.error(f"Error stopping Claude Code {instance_id}: {e}")
            return False

    async def send_claude_code_rejected(self, task_id: str, reason: str) -> None:
        """Send claude_code_rejected event to Serving when task is rejected.

        Args:
            task_id: Task ID
            reason: Reason for rejection (e.g., "At capacity")
        """
        event = {
            "event": "claude_code_rejected",
            "compute_id": self.compute_id,
            "task_id": task_id,
            "error": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        await self._send_event(event)

    async def send_claude_code_started(self, task_id: str, instance_id: str) -> None:
        """Send claude_code_started event to Serving.

        Args:
            task_id: Task ID
            instance_id: Claude Code instance ID
        """
        event = {
            "event": "claude_code_started",
            "compute_id": self.compute_id,
            "task_id": task_id,
            "instance_id": instance_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        await self._send_event(event)

    async def send_claude_code_completed(
        self,
        task_id: str,
        instance_id: str,
        exit_code: int,
        duration_seconds: int,
        branch_name: Optional[str] = None,
        duration_ms: Optional[int] = None,
        session_id: Optional[str] = None,
        cost_usd: Optional[float] = None,
        duration_api_ms: Optional[int] = None,
        num_turns: Optional[int] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        cache_read_tokens: Optional[int] = None,
        cache_creation_tokens: Optional[int] = None,
        tool_timings: Optional[list] = None,
    ) -> None:
        """Send claude_code_completed event to Serving.

        Args:
            task_id: Task ID
            instance_id: Claude Code instance ID
            exit_code: Process exit code
            duration_seconds: Duration in seconds
            branch_name: Git branch name with the work's commits
            duration_ms: Total SDK execution time in milliseconds
            session_id: SDK session ID
            cost_usd: Total cost in USD
            duration_api_ms: LLM API inference time in milliseconds
            num_turns: Number of conversation turns
            input_tokens: Total input tokens
            output_tokens: Total output tokens
            cache_read_tokens: Cache read tokens
            cache_creation_tokens: Cache creation tokens
            tool_timings: Per-tool execution timing from SDK hooks
        """
        event = {
            "event": "claude_code_completed",
            "compute_id": self.compute_id,
            "task_id": task_id,
            "instance_id": instance_id,
            "exit_code": exit_code,
            "duration_seconds": duration_seconds,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        if branch_name is not None:
            event["branch_name"] = branch_name
        if duration_ms is not None:
            event["duration_ms"] = duration_ms
        if session_id is not None:
            event["session_id"] = session_id
        if cost_usd is not None:
            event["cost_usd"] = cost_usd
        if duration_api_ms is not None:
            event["duration_api_ms"] = duration_api_ms
        if num_turns is not None:
            event["num_turns"] = num_turns
        if input_tokens is not None:
            event["input_tokens"] = input_tokens
        if output_tokens is not None:
            event["output_tokens"] = output_tokens
        if cache_read_tokens is not None:
            event["cache_read_tokens"] = cache_read_tokens
        if cache_creation_tokens is not None:
            event["cache_creation_tokens"] = cache_creation_tokens
        if tool_timings:
            event["tool_timings"] = tool_timings

        await self._send_event(event)

    async def send_claude_code_failed(
        self,
        task_id: str,
        instance_id: str,
        error: str,
        exit_code: int
    ) -> None:
        """Send claude_code_failed event to Serving.

        Args:
            task_id: Task ID
            instance_id: Claude Code instance ID
            error: Error message
            exit_code: Process exit code
        """
        event = {
            "event": "claude_code_failed",
            "compute_id": self.compute_id,
            "task_id": task_id,
            "instance_id": instance_id,
            "error": error,
            "exit_code": exit_code,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        await self._send_event(event)

    async def _send_event(self, event: Dict[str, Any]) -> bool:
        """Send event to Serving via HTTP POST with retry and exponential backoff.

        Args:
            event: Event data to send

        Returns:
            True if event was sent successfully, False if all retries exhausted
        """
        url = f"{self.serving_url}/api/v1/compute/events"
        headers = {
            "Content-Type": "application/json"
        }
        # Only add Authorization header if api_key is non-empty
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        event_type = event.get("event", "unknown")

        for attempt in range(self.event_max_retries):
            try:
                async with httpx.AsyncClient(verify=self.tls_verify) as client:
                    response = await client.post(url, json=event, headers=headers, timeout=10.0)

                    if response.status_code == 200:
                        logger.debug(f"Sent event {event_type} to Serving")
                        return True

                    # Non-success status code - log and retry
                    logger.warning(
                        f"Failed to send event {event_type}: HTTP {response.status_code}, "
                        f"retry {attempt + 1}/{self.event_max_retries}"
                    )

            except Exception as e:
                logger.warning(
                    f"Error sending event {event_type}: {e}, "
                    f"retry {attempt + 1}/{self.event_max_retries}"
                )

            # Calculate delay with exponential backoff (1s, 2s, 4s, 8s, 16s for default values)
            if attempt < self.event_max_retries - 1:
                delay = self.event_base_delay * (2 ** attempt)
                logger.debug(f"Waiting {delay}s before retry")
                await asyncio.sleep(delay)

        # All retries exhausted
        self._failed_events_count += 1
        logger.error(
            f"Event {event_type} lost after {self.event_max_retries} retries "
            f"(total failed events: {self._failed_events_count})"
        )
        return False

    async def shutdown(self) -> None:
        """Shutdown all Claude Code instances."""
        logger.info("Shutting down all Claude Code instances...")

        for task_id in list(self._instances.keys()):
            try:
                await self.stop(task_id, force=True, timeout=10)
            except Exception as e:
                logger.error(f"Error stopping task {task_id}: {e}")

        logger.info("All Claude Code instances stopped")

    def get_status(self) -> Dict[str, Any]:
        """Get spawner status.

        Returns:
            Status information
        """
        return {
            "running_instances": len(self._instances),
            "max_instances": self.max_instances,
            "available_capacity": max(0, self.max_instances - len(self._instances)),
            "failed_events_count": self._failed_events_count,
            "instances": [
                {
                    "task_id": task_id,
                    "instance_id": inst["instance_id"],
                    "started_at": inst["started_at"].isoformat(),
                    "working_dir": inst.get("working_dir"),
                    "branch_name": inst.get("branch_name")
                }
                for task_id, inst in self._instances.items()
            ]
        }


# Global instance
_spawner: Optional[ClaudeCodeSpawner] = None


def get_claude_code_spawner() -> Optional[ClaudeCodeSpawner]:
    """Get the global Claude Code spawner."""
    return _spawner


def set_claude_code_spawner(spawner: ClaudeCodeSpawner) -> None:
    """Set the global Claude Code spawner."""
    global _spawner
    _spawner = spawner


def initialize_claude_code_spawner(
    workspace_path: str,
    serving_url: str = "http://localhost:8002",
    compute_id: str = "compute-001",
    api_key: str = "",
    git_token: Optional[str] = None,
    event_max_retries: int = 5,
    event_base_delay: float = 1.0,
    max_instances: int = 1,
    serving_repo_url: Optional[str] = None,
    tls_verify: bool = True,
) -> ClaudeCodeSpawner:
    """Initialize the global Claude Code spawner.

    Args:
        workspace_path: Base workspace directory
        serving_url: Serving component URL
        compute_id: Compute infrastructure ID
        api_key: API key for authentication
        git_token: Git HTTP token for authentication
        event_max_retries: Maximum retries for failed event deliveries (default: 5)
        event_base_delay: Base delay in seconds for exponential backoff (default: 1.0)
        max_instances: Maximum concurrent Claude Code instances (default: 1)
        serving_repo_url: Git URL of the serving repo — cloned once to
            ~/.claudevn/repos/serving/ and pulled on every task start.
        tls_verify: Whether to verify TLS certificates (default: True)

    Returns:
        The initialized spawner
    """
    spawner = ClaudeCodeSpawner(
        workspace_path=workspace_path,
        serving_url=serving_url,
        compute_id=compute_id,
        api_key=api_key,
        git_token=git_token,
        event_max_retries=event_max_retries,
        event_base_delay=event_base_delay,
        max_instances=max_instances,
        serving_repo_url=serving_repo_url,
        tls_verify=tls_verify,
    )
    set_claude_code_spawner(spawner)
    return spawner
