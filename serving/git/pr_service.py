"""Pull Request management service for ClaudeVN.

Coordinates Git operations with Redis-backed PR queue for managing
code review and merge workflows.
"""

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .redis_client import RedisClient, get_redis
from .repo_manager import RepoManager
from config import get_config
from services.sse_connection_manager import (
    SSEConnectionManager,
    get_sse_connection_manager,
)

logger = logging.getLogger(__name__)


def _parse_conflict_files(merge_output: str) -> List[str]:
    """Parse conflicting file names from git merge output.

    Args:
        merge_output: stderr/stdout from failed git merge command

    Returns:
        List of conflicting file paths
    """
    conflicts = []
    for line in merge_output.split('\n'):
        # Look for "CONFLICT (content): Merge conflict in <file>"
        if 'CONFLICT' in line and 'Merge conflict in' in line:
            # Extract filename after "Merge conflict in "
            parts = line.split('Merge conflict in ')
            if len(parts) > 1:
                conflicts.append(parts[1].strip())
        # Also handle "CONFLICT (modify/delete): <file> deleted in ..."
        elif 'CONFLICT' in line and '):' in line:
            # Extract the file path between "): " and " deleted" or end
            try:
                after_paren = line.split('):')[1].strip()
                file_path = after_paren.split()[0] if after_paren else None
                if file_path and file_path not in conflicts:
                    conflicts.append(file_path)
            except (IndexError, AttributeError):
                pass
    return conflicts


class PRStatus(str, Enum):
    """Pull request status values."""
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged"
    CONFLICT = "conflict"
    CLOSED = "closed"


@dataclass
class PullRequest:
    """Pull request data structure."""
    project: str
    branch: str
    status: PRStatus
    compute_id: str
    task_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    head_commit: Optional[str] = None
    base_branch: str = "main"
    queue_position: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    merged_at: Optional[str] = None
    conflicting_files: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "project": self.project,
            "branch": self.branch,
            "status": self.status.value,
            "compute_id": self.compute_id,
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "head_commit": self.head_commit,
            "base_branch": self.base_branch,
            "queue_position": self.queue_position,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "reviewed_by": self.reviewed_by,
            "merged_at": self.merged_at,
            "conflicting_files": self.conflicting_files,
        }


class PRService:
    """Pull request management service.

    Manages the lifecycle of pull requests:
    - Creation: When compute pushes a branch and requests review
    - Review: Queue position, status updates
    - Merge: Conflict detection, merge execution
    - Cleanup: Branch deletion after merge
    """

    def __init__(
        self,
        redis_client: Optional[RedisClient] = None,
        repo_manager: Optional[RepoManager] = None,
        sse_manager: Optional[SSEConnectionManager] = None
    ):
        """Initialize PR service.

        Args:
            redis_client: Redis client (created on demand if None)
            repo_manager: Repository manager (created on demand if None)
            sse_manager: SSE connection manager for compute notifications (uses global if None)
        """
        self._redis = redis_client
        self._repo_manager = repo_manager or RepoManager()
        self._sse_manager = sse_manager
        self._config = get_config()

    async def _get_redis(self) -> RedisClient:
        """Get Redis client, creating if needed."""
        if self._redis is None:
            redis = await get_redis()
            self._redis = RedisClient(redis)
        return self._redis

    def _get_sse_manager(self) -> SSEConnectionManager:
        """Get SSE connection manager, using global if not set."""
        if self._sse_manager is None:
            self._sse_manager = get_sse_connection_manager()
        return self._sse_manager

    def _git_env(self) -> dict:
        """Build env dict with git author/committer identity.

        Sets git author/committer identity so merge commits succeed
        in temp work directories that have no local git config.
        """
        return {
            **os.environ,
            "GIT_AUTHOR_NAME": "ClaudeVN",
            "GIT_AUTHOR_EMAIL": "claudevn@system",
            "GIT_COMMITTER_NAME": "ClaudeVN",
            "GIT_COMMITTER_EMAIL": "claudevn@system",
        }

    def _git_cmd(self, repo_path: Path, *args: str, **kwargs) -> subprocess.CompletedProcess:
        """Run a git command against a repo."""
        cmd = ["git", "-C", str(repo_path), *args]
        env = self._git_env()
        return subprocess.run(cmd, capture_output=True, text=True, env=env, **kwargs)

    # ==========================================================================
    # PR Lifecycle Operations
    # ==========================================================================

    async def create_pr(
        self,
        project: str,
        branch: str,
        compute_id: str,
        task_id: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None
    ) -> PullRequest:
        """Create a new pull request.

        Args:
            project: Project/repo name
            branch: Feature branch name
            compute_id: Compute instance that owns the branch
            task_id: Optional task ID
            title: PR title (defaults to branch name)
            description: PR description

        Returns:
            Created PullRequest

        Raises:
            ValueError: If branch doesn't exist or PR already exists
        """
        redis = await self._get_redis()

        # Verify branch exists in Git
        head = self._repo_manager.get_branch_head(project, branch)
        if not head:
            raise ValueError(f"Branch not found: {project}/{branch}")

        # Check if PR already exists
        existing = await redis.get_branch_status(project, branch)
        if existing and existing.get("status") not in [PRStatus.CLOSED.value, PRStatus.MERGED.value]:
            raise ValueError(f"PR already exists for branch: {branch}")

        now = datetime.now(timezone.utc).isoformat()

        # Set branch status
        await redis.set_branch_status(
            project=project,
            branch=branch,
            status=PRStatus.PENDING.value,
            compute_id=compute_id,
            task_id=task_id,
            title=title or branch,
            description=description or "",
            head_commit=head,
            base_branch="main",
            created_at=now
        )

        # Add to PR queue
        queue_position = await redis.add_to_pr_queue(project, branch)

        # Track compute ownership
        await redis.track_compute_branch(compute_id, f"{project}:{branch}")

        # Publish event
        await redis.publish_git_event(project, "pr_created", {
            "branch": branch,
            "compute_id": compute_id,
            "task_id": task_id,
            "queue_position": queue_position
        })

        logger.info(f"PR created: {project}/{branch} by {compute_id} (position: {queue_position})")

        # Early conflict detection: check for merge conflicts immediately
        initial_status = PRStatus.PENDING
        conflicting_files = []

        dry_run_result = await self.dry_run_merge(project, branch)
        if not dry_run_result.get("can_merge"):
            conflicting_files = dry_run_result.get("conflicting_files", [])
            if conflicting_files and conflicting_files != ["Unable to determine specific files"]:
                # Update status to CONFLICT
                initial_status = PRStatus.CONFLICT
                await redis.set_branch_status(
                    project=project,
                    branch=branch,
                    status=PRStatus.CONFLICT.value,
                    rejection_reason=f"Conflicts with main: {', '.join(conflicting_files)}",
                    conflicting_files=json.dumps(conflicting_files)
                )

                # Publish conflict event (Redis pub/sub)
                await redis.publish_git_event(project, "status", {
                    "branch": branch,
                    "status": "conflict",
                    "message": "Conflicts detected on PR submission",
                    "conflicting_files": conflicting_files
                })

                # Send SSE merge_conflict event to compute instance immediately
                main_head = dry_run_result.get("main_head", "")
                repo_url = self._repo_manager.get_repo_url(project)
                sse_manager = self._get_sse_manager()
                await sse_manager.send_merge_conflict(
                    compute_id=compute_id,
                    issue_id=task_id,
                    branch=branch,
                    conflicting_files=conflicting_files,
                    main_head=main_head,
                    message="Conflicts with main detected on PR submission. Resolve before review.",
                    task_id=task_id,
                    repository=repo_url,
                )

                logger.warning(
                    f"PR created with conflicts: {project}/{branch}: {conflicting_files}"
                )

        return PullRequest(
            project=project,
            branch=branch,
            status=initial_status,
            compute_id=compute_id,
            task_id=task_id,
            title=title or branch,
            description=description,
            head_commit=head,
            queue_position=queue_position,
            created_at=now,
            updated_at=now,
            conflicting_files=conflicting_files if conflicting_files else None
        )

    async def get_pr(self, project: str, branch: str) -> Optional[PullRequest]:
        """Get pull request details.

        Args:
            project: Project/repo name
            branch: Branch name

        Returns:
            PullRequest or None if not found
        """
        redis = await self._get_redis()

        data = await redis.get_branch_status(project, branch)
        if not data:
            return None

        queue_position = await redis.get_pr_queue_position(project, branch)

        # Parse conflicting_files from JSON if present
        conflicting_files = None
        if data.get("conflicting_files"):
            try:
                conflicting_files = json.loads(data["conflicting_files"])
            except (json.JSONDecodeError, TypeError):
                conflicting_files = None

        return PullRequest(
            project=project,
            branch=branch,
            status=PRStatus(data.get("status", "pending")),
            compute_id=data.get("compute_id", "unknown"),
            task_id=data.get("task_id"),
            title=data.get("title"),
            description=data.get("description"),
            head_commit=data.get("head_commit"),
            base_branch=data.get("base_branch", "main"),
            queue_position=queue_position,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            reviewed_by=data.get("reviewed_by"),
            merged_at=data.get("merged_at"),
            conflicting_files=conflicting_files
        )

    async def list_prs(
        self,
        project: str,
        status: Optional[PRStatus] = None,
        compute_id: Optional[str] = None
    ) -> List[PullRequest]:
        """List pull requests with optional filtering.

        Args:
            project: Project/repo name
            status: Optional status filter
            compute_id: Optional compute ID filter

        Returns:
            List of PullRequests
        """
        redis = await self._get_redis()

        status_str = status.value if status else None
        branches = await redis.list_branches(project, status=status_str, compute_id=compute_id)

        prs = []
        for data in branches:
            branch = data.get("branch")
            if not branch:
                continue

            queue_position = await redis.get_pr_queue_position(project, branch)

            # Parse conflicting_files from JSON if present
            conflicting_files = None
            if data.get("conflicting_files"):
                try:
                    conflicting_files = json.loads(data["conflicting_files"])
                except (json.JSONDecodeError, TypeError):
                    conflicting_files = None

            prs.append(PullRequest(
                project=project,
                branch=branch,
                status=PRStatus(data.get("status", "pending")),
                compute_id=data.get("compute_id", "unknown"),
                task_id=data.get("task_id"),
                title=data.get("title"),
                description=data.get("description"),
                head_commit=data.get("head_commit"),
                base_branch=data.get("base_branch", "main"),
                queue_position=queue_position,
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
                reviewed_by=data.get("reviewed_by"),
                merged_at=data.get("merged_at"),
                conflicting_files=conflicting_files
            ))

        return prs

    async def update_status(
        self,
        project: str,
        branch: str,
        status: PRStatus,
        reviewed_by: Optional[str] = None
    ) -> PullRequest:
        """Update PR status.

        Args:
            project: Project/repo name
            branch: Branch name
            status: New status
            reviewed_by: Optional reviewer identifier

        Returns:
            Updated PullRequest

        Raises:
            ValueError: If PR not found
        """
        redis = await self._get_redis()

        existing = await redis.get_branch_status(project, branch)
        if not existing:
            raise ValueError(f"PR not found: {project}/{branch}")

        now = datetime.now(timezone.utc).isoformat()

        update_fields = {"updated_at": now}
        if reviewed_by:
            update_fields["reviewed_by"] = reviewed_by

        await redis.set_branch_status(
            project=project,
            branch=branch,
            status=status.value,
            **update_fields
        )

        # Handle queue transitions
        if status == PRStatus.APPROVED:
            # Add to merge queue
            await redis.add_to_merge_queue(project, branch)
            await redis.publish_git_event(project, "pr_approved", {
                "branch": branch,
                "reviewed_by": reviewed_by
            })

        elif status in [PRStatus.REJECTED, PRStatus.CLOSED]:
            # Remove from PR queue
            await redis.remove_from_pr_queue(project, branch)
            await redis.publish_git_event(project, "pr_closed", {
                "branch": branch,
                "status": status.value
            })

        logger.info(f"PR status updated: {project}/{branch} -> {status.value}")

        return await self.get_pr(project, branch)

    async def approve(self, project: str, branch: str, reviewed_by: str) -> PullRequest:
        """Approve a PR.

        Args:
            project: Project/repo name
            branch: Branch name
            reviewed_by: Reviewer identifier

        Returns:
            Updated PullRequest
        """
        return await self.update_status(project, branch, PRStatus.APPROVED, reviewed_by)

    async def reject(self, project: str, branch: str, reviewed_by: str) -> PullRequest:
        """Reject a PR.

        Args:
            project: Project/repo name
            branch: Branch name
            reviewed_by: Reviewer identifier

        Returns:
            Updated PullRequest
        """
        return await self.update_status(project, branch, PRStatus.REJECTED, reviewed_by)

    # ==========================================================================
    # Merge Operations
    # ==========================================================================

    async def check_mergeable(self, project: str, branch: str) -> Dict[str, Any]:
        """Check if branch can be merged.

        Args:
            project: Project/repo name
            branch: Branch name

        Returns:
            Dict with mergeable status and conflict info
        """
        repo_path = Path(self._config.git.repos_path) / f"{project}.git"

        if not repo_path.exists():
            return {"mergeable": False, "error": "Repository not found"}

        # Check if branch exists
        head = self._repo_manager.get_branch_head(project, branch)
        if not head:
            return {"mergeable": False, "error": "Branch not found"}

        # Check for merge base (common ancestor with main)
        result = self._git_cmd(repo_path, "merge-base", "main", branch)

        if result.returncode != 0:
            return {"mergeable": False, "error": "No common ancestor with main"}

        merge_base = result.stdout.strip()

        # Check if main has diverged
        main_head = self._repo_manager.get_branch_head(project, "main")

        if main_head == merge_base:
            # Fast-forward possible
            return {
                "mergeable": True,
                "merge_type": "fast-forward",
                "merge_base": merge_base,
                "head": head
            }

        # Need to check for conflicts - this is a dry run
        # Create a temporary worktree would be ideal, but for now just report
        return {
            "mergeable": True,
            "merge_type": "merge",
            "merge_base": merge_base,
            "head": head,
            "main_head": main_head,
            "warning": "Main has diverged; merge may have conflicts"
        }

    async def dry_run_merge(self, project: str, branch: str) -> Dict[str, Any]:
        """Perform a dry-run merge to detect conflicts without committing.

        Creates a temporary clone, attempts merge with --no-commit, detects
        conflicts, then aborts and cleans up. This allows conflict detection
        before actually merging.

        Args:
            project: Project/repo name
            branch: Branch name

        Returns:
            Dict with:
            - can_merge: bool (True if no conflicts)
            - conflicting_files: List[str] (empty if can_merge)
            - main_head: str (current main commit)
            - branch_head: str (branch commit)
            - error: str (if error occurred)
        """
        repo_path = Path(self._config.git.repos_path) / f"{project}.git"
        work_dir = Path(f"/tmp/dry-run-merge/{project}-{uuid4()}")

        # Check if branch exists
        branch_head = self._repo_manager.get_branch_head(project, branch)
        if not branch_head:
            return {
                "can_merge": False,
                "conflicting_files": [],
                "error": "Branch not found"
            }

        main_head = self._repo_manager.get_branch_head(project, "main")

        try:
            # 1. Clone bare repo to temp work directory
            work_dir.parent.mkdir(parents=True, exist_ok=True)
            safe_env = self._git_env()
            subprocess.run(
                ["git", "clone", str(repo_path), str(work_dir)],
                capture_output=True,
                text=True,
                check=True,
                env=safe_env
            )

            # 2. Checkout main
            subprocess.run(
                ["git", "-C", str(work_dir), "checkout", "main"],
                capture_output=True,
                text=True,
                check=True,
                env=safe_env
            )

            # 3. Attempt merge with --no-commit to detect conflicts
            merge_result = subprocess.run(
                [
                    "git", "-C", str(work_dir),
                    "merge", "--no-ff", "--no-commit", f"origin/{branch}"
                ],
                capture_output=True,
                text=True,
                env=safe_env
            )

            if merge_result.returncode != 0:
                # Conflict detected - parse conflicting files
                merge_output = merge_result.stdout + merge_result.stderr
                conflicts = _parse_conflict_files(merge_output)

                if not conflicts:
                    # Fallback: try to get unmerged files
                    conflicts = ["Unable to determine specific files"]

                # Abort the merge
                subprocess.run(
                    ["git", "-C", str(work_dir), "merge", "--abort"],
                    capture_output=True,
                    env=safe_env
                )

                logger.info(
                    f"Dry-run merge detected conflicts for {project}/{branch}: {conflicts}"
                )

                return {
                    "can_merge": False,
                    "conflicting_files": conflicts,
                    "main_head": main_head,
                    "branch_head": branch_head
                }

            # 4. No conflicts - abort the uncommitted merge
            subprocess.run(
                ["git", "-C", str(work_dir), "merge", "--abort"],
                capture_output=True,
                env=safe_env
            )

            logger.info(f"Dry-run merge successful for {project}/{branch}")

            return {
                "can_merge": True,
                "conflicting_files": [],
                "main_head": main_head,
                "branch_head": branch_head
            }

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            logger.error(f"Dry-run merge failed for {project}/{branch}: {error_msg}")

            return {
                "can_merge": False,
                "conflicting_files": [],
                "error": f"Git error: {error_msg}"
            }

        except Exception as e:
            logger.error(f"Dry-run merge failed for {project}/{branch}: {e}")

            return {
                "can_merge": False,
                "conflicting_files": [],
                "error": str(e)
            }

        finally:
            # Cleanup temp directory
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)

    async def merge(
        self,
        project: str,
        branch: str,
        delete_branch: bool = True
    ) -> Dict[str, Any]:
        """Merge a PR into main using worktree-based merge with conflict detection.

        Uses a temporary clone to perform actual merge, allowing proper conflict
        detection that's not possible with direct ref updates on bare repos.

        Args:
            project: Project/repo name
            branch: Branch name
            delete_branch: Whether to delete branch after merge

        Returns:
            Dict with merge result including:
            - success: bool
            - merged_commit: str (if success)
            - branch: str
            - deleted: bool (if success)
            - conflicts: List[str] (if conflict)
            - reason: str (if failure)

        Raises:
            ValueError: If PR not found or not approved
        """
        redis = await self._get_redis()
        repo_path = Path(self._config.git.repos_path) / f"{project}.git"
        work_dir = Path(f"/tmp/merge-work/{project}-{uuid4()}")

        # Verify PR is approved
        pr = await self.get_pr(project, branch)
        if not pr:
            raise ValueError(f"PR not found: {project}/{branch}")

        if pr.status != PRStatus.APPROVED:
            raise ValueError(f"PR not approved: {project}/{branch} (status: {pr.status.value})")

        # Check basic mergeability
        check = await self.check_mergeable(project, branch)
        if not check.get("mergeable"):
            raise ValueError(f"Cannot merge: {check.get('error')}")

        try:
            # 1. Clone bare repo to temp work directory
            work_dir.parent.mkdir(parents=True, exist_ok=True)
            safe_env = self._git_env()
            subprocess.run(
                ["git", "clone", str(repo_path), str(work_dir)],
                capture_output=True,
                text=True,
                check=True,
                env=safe_env
            )

            # 2. Checkout main
            subprocess.run(
                ["git", "-C", str(work_dir), "checkout", "main"],
                capture_output=True,
                text=True,
                check=True,
                env=safe_env
            )

            # 3. Attempt merge with --no-ff to ensure merge commit
            merge_result = subprocess.run(
                [
                    "git", "-C", str(work_dir),
                    "merge", "--no-ff", f"origin/{branch}",
                    "-m", f"Merge {branch} into main\n\nPR merged by ClaudeVN"
                ],
                capture_output=True,
                text=True,
                env=safe_env
            )

            if merge_result.returncode != 0:
                # Merge failed - could be conflict, missing identity, or other error
                merge_output = merge_result.stdout + merge_result.stderr
                logger.warning(
                    f"Merge failed for {project}/{branch} "
                    f"(exit {merge_result.returncode}): {merge_output.strip()}"
                )

                subprocess.run(
                    ["git", "-C", str(work_dir), "merge", "--abort"],
                    capture_output=True,
                    env=safe_env
                )

                # Parse conflicting files from merge output
                conflicts = _parse_conflict_files(merge_output)

                if not conflicts:
                    # Fallback: try to get unmerged files
                    conflicts = ["Unable to determine specific files"]

                # Update Redis with conflict info
                await redis.set_branch_status(
                    project=project,
                    branch=branch,
                    status=PRStatus.CONFLICT.value,
                    rejection_reason=f"Merge conflict: {', '.join(conflicts)}",
                    conflicting_files=json.dumps(conflicts)
                )

                # Publish conflict event for compute notification (Redis pub/sub)
                await redis.publish_git_event(project, "status", {
                    "branch": branch,
                    "status": "conflict",
                    "message": "Rebase required",
                    "conflicting_files": conflicts
                })

                # Send SSE merge_conflict event to compute instance
                if pr.compute_id:
                    # Get main HEAD for the event
                    main_head = self._repo_manager.get_branch_head(project, "main") or ""
                    repo_url = self._repo_manager.get_repo_url(project)
                    sse_manager = self._get_sse_manager()
                    await sse_manager.send_merge_conflict(
                        compute_id=pr.compute_id,
                        issue_id=pr.task_id,
                        branch=branch,
                        conflicting_files=conflicts,
                        main_head=main_head,
                        message="Resolve conflicts with main and push again",
                        task_id=pr.task_id,
                        repository=repo_url,
                    )

                logger.warning(
                    f"Merge conflict for {project}/{branch}: {conflicts}"
                )

                return {
                    "success": False,
                    "reason": "conflict",
                    "error": f"Merge failed: {', '.join(conflicts)}",
                    "conflicts": conflicts,
                    "branch": branch
                }

            # 4. Merge successful - push merged main back to bare repo
            # Include CLAUDEVN_ALLOW_MAIN_PUSH=true so the pre-receive hook permits
            # this authorized Serving merge push (only set for this operation).
            merge_push_env = {**safe_env, "CLAUDEVN_ALLOW_MAIN_PUSH": "true"}
            push_result = subprocess.run(
                ["git", "-C", str(work_dir), "push", "origin", "main"],
                capture_output=True,
                text=True,
                env=merge_push_env
            )

            if push_result.returncode != 0:
                logger.error(f"Push failed for {project}/{branch}: {push_result.stderr}")
                raise ValueError(f"Push failed: {push_result.stderr}")

            # 5. Get merge commit
            commit_result = subprocess.run(
                ["git", "-C", str(work_dir), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
                env=safe_env
            )
            merge_commit = commit_result.stdout.strip()

            now = datetime.now(timezone.utc).isoformat()

            # 6. Update Redis with merged status
            await redis.set_branch_status(
                project=project,
                branch=branch,
                status=PRStatus.MERGED.value,
                merge_commit=merge_commit,
                merged_at=now
            )

            # Remove from queues
            await redis.remove_from_pr_queue(project, branch)

            # Delete branch if requested
            if delete_branch:
                self._git_cmd(repo_path, "branch", "-D", branch)
                # Clean up compute tracking
                if pr.compute_id:
                    await redis.untrack_compute_branch(pr.compute_id, f"{project}:{branch}")

            # 7. Publish merge success event (Redis pub/sub)
            await redis.publish_git_event(project, "merged", {
                "branch": branch,
                "merge_commit": merge_commit,
                "compute_id": pr.compute_id,
                "task_id": pr.task_id
            })

            # Send SSE work_completed event to compute instance
            if pr.compute_id:
                sse_manager = self._get_sse_manager()
                await sse_manager.send_work_completed(
                    compute_id=pr.compute_id,
                    issue_id=pr.task_id,
                    branch=branch,
                    merge_commit=merge_commit
                )

            logger.info(f"PR merged: {project}/{branch} -> main ({merge_commit[:8]})")

            return {
                "success": True,
                "merged_commit": merge_commit,
                "branch": branch,
                "deleted": delete_branch
            }

        except subprocess.CalledProcessError as e:
            # Unexpected git error (not merge conflict)
            error_msg = e.stderr if e.stderr else str(e)
            logger.error(f"Git operation failed for {project}/{branch}: {error_msg}")

            await redis.set_branch_status(
                project=project,
                branch=branch,
                status=PRStatus.CONFLICT.value,
                rejection_reason=f"Git error: {error_msg}"
            )

            raise ValueError(f"Merge failed: {error_msg}")

        finally:
            # Cleanup temp directory
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)

    async def process_merge_queue(self, project: str) -> List[Dict[str, Any]]:
        """Process pending merges from the queue.

        Args:
            project: Project/repo name

        Returns:
            List of merge results
        """
        redis = await self._get_redis()
        results = []

        while True:
            branch = await redis.pop_merge_queue(project)
            if not branch:
                break

            try:
                result = await self.merge(project, branch)
                results.append(result)
            except ValueError as e:
                results.append({
                    "success": False,
                    "branch": branch,
                    "error": str(e)
                })
                # Re-add to queue if conflict (needs resolution)
                await redis.add_to_merge_queue(project, branch)
                break  # Stop processing on first failure

        return results

    # ==========================================================================
    # Queue Operations
    # ==========================================================================

    async def get_pr_queue(self, project: str) -> List[PullRequest]:
        """Get PRs in queue order.

        Args:
            project: Project/repo name

        Returns:
            List of PRs in queue order
        """
        redis = await self._get_redis()

        branches = await redis.get_pr_queue(project)
        prs = []

        for i, branch in enumerate(branches, 1):
            pr = await self.get_pr(project, branch)
            if pr:
                pr.queue_position = i
                prs.append(pr)

        return prs

    async def get_merge_queue(self, project: str) -> List[str]:
        """Get branches in merge queue.

        Args:
            project: Project/repo name

        Returns:
            List of branch names
        """
        redis = await self._get_redis()
        return await redis.get_merge_queue(project)

    # ==========================================================================
    # Compute Operations
    # ==========================================================================

    async def get_compute_prs(self, compute_id: str) -> List[PullRequest]:
        """Get all PRs owned by a compute instance.

        Args:
            compute_id: Compute instance ID

        Returns:
            List of PRs
        """
        redis = await self._get_redis()

        branches = await redis.get_compute_branches(compute_id)
        prs = []

        for branch_ref in branches:
            if ":" in branch_ref:
                project, branch = branch_ref.split(":", 1)
                pr = await self.get_pr(project, branch)
                if pr:
                    prs.append(pr)

        return prs

    async def cleanup_compute(self, compute_id: str) -> int:
        """Clean up PRs when a compute instance is deregistered.

        Closes all pending PRs from the compute instance.

        Args:
            compute_id: Compute instance ID

        Returns:
            Number of PRs closed
        """
        prs = await self.get_compute_prs(compute_id)
        closed = 0

        for pr in prs:
            if pr.status in [PRStatus.PENDING, PRStatus.IN_REVIEW]:
                await self.update_status(pr.project, pr.branch, PRStatus.CLOSED)
                closed += 1

        logger.info(f"Cleaned up {closed} PRs for compute: {compute_id}")
        return closed
