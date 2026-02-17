"""Issue Service - Git-backed issue and goal storage for WorkMap.

Manages persistent issues and goals using Git for storage and Redis for indexing.
Each issue/goal is stored as a YAML file in a Git repository with full history.
"""

import asyncio
import logging
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from git.redis_client import RedisClient
from git.repo_manager import RepoManager
from models.issue import (
    Goal,
    GoalCreateRequest,
    GoalListResponse,
    GoalStatus,
    GoalUpdateRequest,
    Issue,
    IssueArea,
    IssueCreateRequest,
    IssueListResponse,
    IssuePriority,
    IssueResult,
    IssueStatus,
    IssueType,
    IssueUpdateRequest,
)

logger = logging.getLogger(__name__)


class IssueService:
    """Service for managing issues and goals with Git+Redis storage.

    Storage architecture:
    - Git: Persistent YAML files with full history (source of truth)
    - Redis: Fast indexes for queries (status, priority, dependencies, skills)

    Git structure:
        workmap-repo/
        ├── goals/
        │   └── goal-001.yaml
        ├── issues/
        │   └── issue-100.yaml
        └── archive/
            └── done/
                └── issue-050.yaml
    """

    def __init__(self, redis_client: RedisClient, repo_manager: RepoManager):
        """Initialize issue service.

        Args:
            redis_client: Redis client for indexes
            repo_manager: Repository manager for Git operations
        """
        self._redis = redis_client
        self._repo_manager = repo_manager
        self._repo_name = "workmap"
        self._worktree_path: Optional[Path] = None
        self._lock = threading.RLock()  # For atomic Git operations
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize workmap repo and worktree if not exists."""
        if self._initialized:
            return

        # Create bare repo if doesn't exist
        if not self._repo_manager.repo_exists(self._repo_name):
            logger.info(f"Creating workmap repository")
            self._repo_manager.create_repo(self._repo_name, install_hooks=False)

            # Initialize with directory structure
            await self._initialize_repo_structure()

        # Create worktree for read/write operations
        repo_path = self._repo_manager._repo_path(self._repo_name)
        self._worktree_path = Path(f"/tmp/workmap-worktree-{id(self)}")

        # Clean up any existing worktree at this path
        if self._worktree_path.exists():
            try:
                self._repo_manager.remove_worktree(repo_path, self._worktree_path, force=True)
            except:
                pass

        # Create worktree on main branch
        try:
            self._repo_manager.add_worktree(
                repo_path=repo_path,
                worktree_path=self._worktree_path,
                branch="main",
                create_branch=False
            )
        except subprocess.CalledProcessError:
            # Main branch doesn't exist yet, create it
            self._repo_manager.add_worktree(
                repo_path=repo_path,
                worktree_path=self._worktree_path,
                branch="main",
                create_branch=True
            )

        # Initialize counters if not exist
        if not await self._redis._redis.exists(self._redis._key("workmap:issue_counter")):
            await self._redis._redis.set(self._redis._key("workmap:issue_counter"), 0)
        if not await self._redis._redis.exists(self._redis._key("workmap:goal_counter")):
            await self._redis._redis.set(self._redis._key("workmap:goal_counter"), 0)

        self._initialized = True
        logger.info(f"Issue service initialized with worktree at {self._worktree_path}")

    async def _initialize_repo_structure(self) -> None:
        """Initialize repository with directory structure and initial commit."""
        # This will be called on a fresh repo
        # We'll create the structure in the first commit via worktree
        pass

    def _ensure_directories(self) -> None:
        """Ensure directory structure exists in worktree."""
        if not self._worktree_path:
            raise RuntimeError("Worktree not initialized")

        (self._worktree_path / "goals").mkdir(parents=True, exist_ok=True)
        (self._worktree_path / "issues").mkdir(parents=True, exist_ok=True)
        (self._worktree_path / "archive" / "done").mkdir(parents=True, exist_ok=True)

    async def _next_issue_id(self) -> str:
        """Generate next issue ID.

        Returns:
            Issue ID like 'issue-100'
        """
        counter = await self._redis._redis.incr(self._redis._key("workmap:issue_counter"))
        return f"issue-{counter}"

    async def _next_goal_id(self) -> str:
        """Generate next goal ID.

        Returns:
            Goal ID like 'goal-001'
        """
        counter = await self._redis._redis.incr(self._redis._key("workmap:goal_counter"))
        return f"goal-{counter:03d}"

    def _git_commit(self, message: str) -> None:
        """Create a Git commit in the worktree.

        Args:
            message: Commit message
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
                return

            # Commit
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self._worktree_path,
                check=True,
                capture_output=True
            )

            logger.debug(f"Git commit: {message}")

    async def _save_issue(self, issue: Issue, commit_message: str) -> None:
        """Save issue to Git and update Redis indexes.

        Args:
            issue: Issue to save
            commit_message: Git commit message
        """
        self._ensure_directories()

        # Write YAML file
        issue_path = self._worktree_path / "issues" / f"{issue.id}.yaml"
        issue_path.write_text(issue.to_yaml())

        # Git commit
        self._git_commit(commit_message)

        # Update Redis indexes
        await self._update_issue_indexes(issue)

    async def _update_issue_indexes(self, issue: Issue) -> None:
        """Update Redis indexes for an issue.

        Args:
            issue: Issue to index
        """
        # Status index
        await self._redis._redis.sadd(
            self._redis._key(f"workmap:issues:status:{issue.status.value}"),
            issue.id
        )

        # Priority queue (for ready issues)
        if issue.status == IssueStatus.READY:
            # Score = priority * 1000 + age in hours
            priority_score = {
                IssuePriority.P0: 0,
                IssuePriority.P1: 1,
                IssuePriority.P2: 2,
                IssuePriority.P3: 3,
            }[issue.priority] * 1000

            age_hours = (datetime.now(timezone.utc) - issue.created_at).total_seconds() / 3600
            score = priority_score + age_hours

            await self._redis._redis.zadd(
                self._redis._key("workmap:issues:ready:queue"),
                {issue.id: score}
            )

        # Dependency indexes
        for dep_id in issue.depends_on:
            await self._redis._redis.sadd(
                self._redis._key(f"workmap:issues:depends_on:{issue.id}"),
                dep_id
            )
            await self._redis._redis.sadd(
                self._redis._key(f"workmap:issues:blocks:{dep_id}"),
                issue.id
            )

        # Skill index
        for skill in issue.required_skills:
            await self._redis._redis.sadd(
                self._redis._key(f"workmap:issues:skill:{skill}"),
                issue.id
            )

    async def _remove_issue_indexes(self, issue: Issue) -> None:
        """Remove issue from all Redis indexes.

        Args:
            issue: Issue to remove from indexes
        """
        # Status index
        for status in IssueStatus:
            await self._redis._redis.srem(
                self._redis._key(f"workmap:issues:status:{status.value}"),
                issue.id
            )

        # Priority queue
        await self._redis._redis.zrem(
            self._redis._key("workmap:issues:ready:queue"),
            issue.id
        )

        # Dependency indexes
        for dep_id in issue.depends_on:
            await self._redis._redis.srem(
                self._redis._key(f"workmap:issues:depends_on:{issue.id}"),
                dep_id
            )
            await self._redis._redis.srem(
                self._redis._key(f"workmap:issues:blocks:{dep_id}"),
                issue.id
            )

        # Skill index
        for skill in issue.required_skills:
            await self._redis._redis.srem(
                self._redis._key(f"workmap:issues:skill:{skill}"),
                issue.id
            )

    # ========================================================================
    # Issue CRUD Operations
    # ========================================================================

    async def create_issue(self, request: IssueCreateRequest) -> Issue:
        """Create a new issue.

        Args:
            request: Issue creation request

        Returns:
            Created issue
        """
        issue_id = await self._next_issue_id()

        # Determine initial status based on dependencies
        status = IssueStatus.BACKLOG
        if not request.depends_on:
            status = IssueStatus.READY
        else:
            # Check if all dependencies are done
            all_done = True
            for dep_id in request.depends_on:
                dep = await self.get_issue(dep_id)
                if not dep or dep.status != IssueStatus.DONE:
                    all_done = False
                    break
            if all_done:
                status = IssueStatus.READY

        issue = Issue(
            id=issue_id,
            title=request.title,
            description=request.description,
            type=request.type,
            area=request.area,
            priority=request.priority,
            status=status,
            required_skills=request.required_skills,
            depends_on=request.depends_on,
            goal_id=request.goal_id,
            parent_issue_id=request.parent_issue_id,
        )

        # Save to Git
        await self._save_issue(
            issue,
            f"create: {issue.type.value} {issue.id} - {issue.title}"
        )

        # Update blocks index for dependencies
        for dep_id in request.depends_on:
            dep = await self.get_issue(dep_id)
            if dep:
                dep.blocks.append(issue_id)
                await self._save_issue(
                    dep,
                    f"update: {dep.id} - add blocker {issue_id}"
                )

        logger.info(f"Created issue {issue_id}: {issue.title}")
        return issue

    async def get_issue(self, issue_id: str) -> Optional[Issue]:
        """Get an issue by ID.

        Args:
            issue_id: Issue ID

        Returns:
            Issue if found, None otherwise
        """
        if not self._worktree_path:
            return None

        issue_path = self._worktree_path / "issues" / f"{issue_id}.yaml"
        if not issue_path.exists():
            # Check archive
            issue_path = self._worktree_path / "archive" / "done" / f"{issue_id}.yaml"
            if not issue_path.exists():
                return None

        yaml_content = issue_path.read_text()
        return Issue.from_yaml(yaml_content)

    async def update_issue(self, issue_id: str, request: IssueUpdateRequest) -> Optional[Issue]:
        """Update an issue.

        Args:
            issue_id: Issue ID
            request: Update request

        Returns:
            Updated issue if found
        """
        issue = await self.get_issue(issue_id)
        if not issue:
            return None

        # Update fields
        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(issue, field, value)

        # Save to Git
        await self._save_issue(
            issue,
            f"update: {issue.id} - {', '.join(update_data.keys())}"
        )

        logger.info(f"Updated issue {issue_id}")
        return issue

    async def delete_issue(self, issue_id: str) -> bool:
        """Delete an issue.

        Args:
            issue_id: Issue ID

        Returns:
            True if deleted
        """
        issue = await self.get_issue(issue_id)
        if not issue:
            return False

        # Remove from Redis indexes
        await self._remove_issue_indexes(issue)

        # Remove from dependency graph
        for dep_id in issue.depends_on:
            dep = await self.get_issue(dep_id)
            if dep and issue_id in dep.blocks:
                dep.blocks.remove(issue_id)
                await self._save_issue(
                    dep,
                    f"update: {dep.id} - remove blocker {issue_id}"
                )

        # Remove file
        issue_path = self._worktree_path / "issues" / f"{issue_id}.yaml"
        if issue_path.exists():
            issue_path.unlink()

        # Git commit
        self._git_commit(f"delete: {issue.type.value} {issue.id} - {issue.title}")

        logger.info(f"Deleted issue {issue_id}")
        return True

    async def list_issues(
        self,
        status: Optional[IssueStatus] = None,
        priority: Optional[IssuePriority] = None,
        goal_id: Optional[str] = None
    ) -> IssueListResponse:
        """List issues with optional filters.

        Args:
            status: Filter by status
            priority: Filter by priority
            goal_id: Filter by goal

        Returns:
            Issue list response
        """
        issues = []

        # Load all issues from Git
        if self._worktree_path:
            issues_dir = self._worktree_path / "issues"
            if issues_dir.exists():
                for issue_file in issues_dir.glob("*.yaml"):
                    yaml_content = issue_file.read_text()
                    issue = Issue.from_yaml(yaml_content)

                    # Apply filters
                    if status and issue.status != status:
                        continue
                    if priority and issue.priority != priority:
                        continue
                    if goal_id and issue.goal_id != goal_id:
                        continue

                    issues.append(issue)

        # Calculate stats
        by_status: Dict[str, int] = {}
        by_priority: Dict[str, int] = {}

        for issue in issues:
            by_status[issue.status.value] = by_status.get(issue.status.value, 0) + 1
            by_priority[issue.priority.value] = by_priority.get(issue.priority.value, 0) + 1

        return IssueListResponse(
            items=issues,
            total=len(issues),
            by_status=by_status,
            by_priority=by_priority
        )

    # ========================================================================
    # Status Transitions
    # ========================================================================

    async def complete_issue(self, issue_id: str, result: IssueResult) -> Optional[Issue]:
        """Mark an issue as complete with result.

        Args:
            issue_id: Issue ID
            result: Completion result

        Returns:
            Updated issue
        """
        issue = await self.get_issue(issue_id)
        if not issue:
            return None

        # Update issue
        old_status = issue.status
        issue.status = IssueStatus.DONE
        issue.completed_at = datetime.now(timezone.utc)
        issue.result = result

        # Remove from old status index
        await self._redis._redis.srem(
            self._redis._key(f"workmap:issues:status:{old_status.value}"),
            issue_id
        )

        # Save to Git
        await self._save_issue(
            issue,
            f"complete: {issue.id} - {result.summary}"
        )

        # Resolve dependencies
        newly_ready = await self._resolve_dependencies(issue_id)
        if newly_ready:
            logger.info(f"Issue {issue_id} completion unlocked: {newly_ready}")

        logger.info(f"Completed issue {issue_id}")
        return issue

    async def fail_issue(self, issue_id: str, error: str) -> Optional[Issue]:
        """Mark an issue as failed.

        Args:
            issue_id: Issue ID
            error: Error description

        Returns:
            Updated issue
        """
        issue = await self.get_issue(issue_id)
        if not issue:
            return None

        # Update issue
        old_status = issue.status
        issue.status = IssueStatus.FAILED
        issue.completed_at = datetime.now(timezone.utc)

        # Remove from old status index
        await self._redis._redis.srem(
            self._redis._key(f"workmap:issues:status:{old_status.value}"),
            issue_id
        )

        # Save to Git
        await self._save_issue(
            issue,
            f"fail: {issue.id} - {error}"
        )

        logger.warning(f"Failed issue {issue_id}: {error}")
        return issue

    async def _resolve_dependencies(self, completed_issue_id: str) -> List[str]:
        """Resolve dependencies and unlock blocked issues.

        When an issue completes, check all issues that depend on it.
        If all their dependencies are now done, move them to READY.

        Args:
            completed_issue_id: ID of the completed issue

        Returns:
            List of issue IDs that became ready
        """
        newly_ready = []

        # Get issues that were blocked by this one
        blocked_ids = await self._redis._redis.smembers(
            self._redis._key(f"workmap:issues:blocks:{completed_issue_id}")
        )

        for blocked_id in blocked_ids:
            issue = await self.get_issue(blocked_id)
            if not issue or issue.status != IssueStatus.BACKLOG:
                continue

            # Check if ALL dependencies are now done
            all_deps_done = True
            for dep_id in issue.depends_on:
                dep = await self.get_issue(dep_id)
                if not dep or dep.status != IssueStatus.DONE:
                    all_deps_done = False
                    break

            if all_deps_done:
                # Move to ready
                old_status = issue.status
                issue.status = IssueStatus.READY

                # Remove from backlog index
                await self._redis._redis.srem(
                    self._redis._key(f"workmap:issues:status:{old_status.value}"),
                    issue.id
                )

                # Save
                await self._save_issue(
                    issue,
                    f"status transition: {issue.id} - ready (dependencies met)"
                )

                newly_ready.append(issue.id)

        return newly_ready

    # ========================================================================
    # History
    # ========================================================================

    async def get_issue_history(self, issue_id: str) -> List[Dict]:
        """Get Git commit history for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            List of commit history entries
        """
        if not self._worktree_path:
            return []

        issue_path = f"issues/{issue_id}.yaml"

        result = subprocess.run(
            ["git", "log", "--pretty=format:%H|%an|%at|%s", "--", issue_path],
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

    # ========================================================================
    # Archive
    # ========================================================================

    async def archive_issue(self, issue_id: str) -> bool:
        """Move a completed issue to archive.

        Args:
            issue_id: Issue ID

        Returns:
            True if archived
        """
        issue = await self.get_issue(issue_id)
        if not issue or issue.status != IssueStatus.DONE:
            return False

        # Move file
        issue_path = self._worktree_path / "issues" / f"{issue_id}.yaml"
        archive_path = self._worktree_path / "archive" / "done" / f"{issue_id}.yaml"

        if issue_path.exists():
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            issue_path.rename(archive_path)

            # Git commit
            self._git_commit(f"archive: {issue.id}")

            logger.info(f"Archived issue {issue_id}")
            return True

        return False

    # ========================================================================
    # Goal CRUD Operations
    # ========================================================================

    async def create_goal(self, request: GoalCreateRequest) -> Goal:
        """Create a new goal.

        Args:
            request: Goal creation request

        Returns:
            Created goal
        """
        goal_id = await self._next_goal_id()

        goal = Goal(
            id=goal_id,
            title=request.title,
            description=request.description,
            priority=request.priority,
            created_by=request.created_by,
        )

        # Save to Git
        self._ensure_directories()
        goal_path = self._worktree_path / "goals" / f"{goal_id}.yaml"
        goal_path.write_text(goal.to_yaml())

        self._git_commit(f"create: goal {goal.id} - {goal.title}")

        logger.info(f"Created goal {goal_id}: {goal.title}")
        return goal

    async def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get a goal by ID.

        Args:
            goal_id: Goal ID

        Returns:
            Goal if found
        """
        if not self._worktree_path:
            return None

        goal_path = self._worktree_path / "goals" / f"{goal_id}.yaml"
        if not goal_path.exists():
            return None

        yaml_content = goal_path.read_text()
        return Goal.from_yaml(yaml_content)

    async def update_goal(self, goal_id: str, request: GoalUpdateRequest) -> Optional[Goal]:
        """Update a goal.

        Args:
            goal_id: Goal ID
            request: Update request

        Returns:
            Updated goal if found
        """
        goal = await self.get_goal(goal_id)
        if not goal:
            return None

        # Update fields
        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(goal, field, value)

        # Save to Git
        goal_path = self._worktree_path / "goals" / f"{goal_id}.yaml"
        goal_path.write_text(goal.to_yaml())

        self._git_commit(f"update: goal {goal.id} - {', '.join(update_data.keys())}")

        logger.info(f"Updated goal {goal_id}")
        return goal

    async def delete_goal(self, goal_id: str) -> bool:
        """Delete a goal.

        Args:
            goal_id: Goal ID

        Returns:
            True if deleted
        """
        goal = await self.get_goal(goal_id)
        if not goal:
            return False

        # Remove file
        goal_path = self._worktree_path / "goals" / f"{goal_id}.yaml"
        if goal_path.exists():
            goal_path.unlink()

        # Git commit
        self._git_commit(f"delete: goal {goal.id} - {goal.title}")

        logger.info(f"Deleted goal {goal_id}")
        return True

    async def list_goals(self, status: Optional[GoalStatus] = None) -> GoalListResponse:
        """List goals with optional filter.

        Args:
            status: Filter by status

        Returns:
            Goal list response
        """
        goals = []

        # Load all goals from Git
        if self._worktree_path:
            goals_dir = self._worktree_path / "goals"
            if goals_dir.exists():
                for goal_file in goals_dir.glob("*.yaml"):
                    yaml_content = goal_file.read_text()
                    goal = Goal.from_yaml(yaml_content)

                    # Apply filter
                    if status and goal.status != status:
                        continue

                    goals.append(goal)

        # Calculate stats
        by_status: Dict[str, int] = {}
        for goal in goals:
            by_status[goal.status.value] = by_status.get(goal.status.value, 0) + 1

        return GoalListResponse(
            items=goals,
            total=len(goals),
            by_status=by_status
        )


# ============================================================================
# Global Service Instance
# ============================================================================

_issue_service: Optional[IssueService] = None


def get_issue_service() -> IssueService:
    """Get the global issue service instance."""
    if _issue_service is None:
        raise RuntimeError("Issue service not initialized")
    return _issue_service


def set_issue_service(service: IssueService) -> None:
    """Set the global issue service instance."""
    global _issue_service
    _issue_service = service
