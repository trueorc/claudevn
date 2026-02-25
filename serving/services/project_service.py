"""Service for managing projects."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from models.project import (
    Project, ProjectStatus, RepoConfig,
    ProjectCreateRequest, ProjectUpdateRequest,
    RepoAddRequest, RepoCreateInternalRequest,
    ProjectListResponse, ProjectStats,
    ActivitySummary, ActivityIndicator, ActivityEvent,
    ActivityEventType, ProjectActivityResponse
)

logger = logging.getLogger(__name__)


class ProjectService:
    """Service for project management."""

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._projects: Dict[str, Project] = {}
        self._activity_events: Dict[str, List[ActivityEvent]] = {}
        self._work_items_ref: Optional[Callable[[], Dict[str, Any]]] = None
        self._initialized = False

    def set_work_items_reference(
        self,
        work_items_getter: Callable[[], Dict[str, Any]]
    ) -> None:
        """Set reference to work items for activity calculation."""
        self._work_items_ref = work_items_getter

    async def initialize(self):
        """Initialize the project service."""
        if self._initialized:
            return

        # Load from Redis if available
        if self._redis:
            try:
                project_ids = await self._redis.smembers("projects:all")
                for pid in project_ids:
                    data = await self._redis.hgetall(f"project:{pid}")
                    if data:
                        self._projects[pid] = Project.model_validate_json(data.get("data", "{}"))
                logger.info(f"Loaded {len(self._projects)} projects from Redis")
            except Exception as e:
                logger.warning(f"Failed to load projects from Redis: {e}")

        # Create default project if none exist
        if not self._projects:
            await self._create_default_project()

        self._initialized = True

    async def _create_default_project(self):
        """Create a default project for new installations."""
        from models.project import ProjectCreateRequest

        default_request = ProjectCreateRequest(
            name="Default Project",
            description="Default project for work items. Create additional projects as needed.",
            metadata={"is_default": True}
        )

        project = await self.create_project(default_request)
        logger.info(f"Created default project: {project.project_id}")

    async def _save_project(self, project: Project):
        """Save project to Redis."""
        if self._redis:
            try:
                await self._redis.sadd("projects:all", project.project_id)
                await self._redis.hset(
                    f"project:{project.project_id}",
                    "data",
                    project.model_dump_json()
                )
            except Exception as e:
                logger.warning(f"Failed to save project to Redis: {e}")

    async def _delete_project_storage(self, project_id: str):
        """Delete project and related data from Redis."""
        if self._redis:
            try:
                await self._redis.srem("projects:all", project_id)
                await self._redis.delete(f"project:{project_id}")
                # Clean up activity events list
                await self._redis.delete(f"project:{project_id}:events")
            except Exception as e:
                logger.warning(f"Failed to delete project from Redis: {e}")

    async def list_projects(
        self,
        status: Optional[ProjectStatus] = None,
        search: Optional[str] = None,
        sort: Optional[str] = None
    ) -> ProjectListResponse:
        """List all projects with optional filtering and sorting."""
        items = list(self._projects.values())

        # Apply status filter
        if status:
            items = [p for p in items if p.status == status]

        # Apply search filter (name or description)
        if search:
            search_lower = search.lower()
            items = [
                p for p in items
                if search_lower in p.name.lower()
                or search_lower in p.description.lower()
            ]

        # Apply sorting
        if sort:
            if sort == "name_asc":
                items.sort(key=lambda p: p.name.lower())
            elif sort == "name_desc":
                items.sort(key=lambda p: p.name.lower(), reverse=True)
            elif sort == "created_asc":
                items.sort(key=lambda p: p.created_at)
            elif sort == "created_desc":
                items.sort(key=lambda p: p.created_at, reverse=True)
            elif sort == "updated_asc":
                items.sort(key=lambda p: p.updated_at)
            elif sort == "updated_desc":
                items.sort(key=lambda p: p.updated_at, reverse=True)

        return ProjectListResponse(
            items=items,
            total=len(items)
        )

    async def get_project(self, project_id: str) -> Optional[Project]:
        """Get a project by ID."""
        return self._projects.get(project_id)

    async def create_project(self, request: ProjectCreateRequest) -> Project:
        """Create a new project."""
        project_id = f"proj_{uuid.uuid4().hex[:12]}"

        project = Project(
            project_id=project_id,
            name=request.name,
            description=request.description or "",
            icon=request.icon,
            icon_color=request.icon_color,
            labels=request.labels,
            metadata=request.metadata,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        self._projects[project_id] = project
        await self._save_project(project)

        logger.info(f"Created project {project_id}: {project.name}")
        return project

    async def update_project(
        self,
        project_id: str,
        request: ProjectUpdateRequest
    ) -> Optional[Project]:
        """Update a project."""
        project = self._projects.get(project_id)
        if not project:
            return None

        update_data = request.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(project, field, value)

        project.updated_at = datetime.now(timezone.utc)
        await self._save_project(project)

        logger.info(f"Updated project {project_id}")
        return project

    async def delete_project(self, project_id: str) -> dict:
        """Delete a project and clean up all associated resources.

        Returns:
            Dict with deletion counts, or empty dict if project not found.
        """
        project = self._projects.get(project_id)
        if not project:
            return {}

        repo_count = 0

        # Clean up internal Git repositories
        for repo in project.repos:
            if repo.is_internal:
                git_project_name = repo.metadata.get("git_project_name")
                if git_project_name:
                    try:
                        from api.git import get_repo_manager
                        repo_manager = get_repo_manager()
                        if repo_manager.delete_repo(git_project_name):
                            repo_count += 1
                            logger.info(
                                f"Deleted internal Git repo {git_project_name}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to delete internal Git repo "
                            f"{git_project_name}: {e}"
                        )

        # Clean up activity events (in-memory)
        self._activity_events.pop(project_id, None)

        # Clean up compute project registrations
        try:
            from services.registry_service import get_compute_registry
            registry = get_compute_registry()
            if project_id in registry._project_index:
                instance_ids = list(registry._project_index[project_id])
                del registry._project_index[project_id]
                # Remove project_id from each instance's project_ids
                for iid in instance_ids:
                    instance = registry._instances.get(iid)
                    if instance and project_id in instance.project_ids:
                        instance.project_ids.remove(project_id)
                logger.info(
                    f"Cleared {len(instance_ids)} compute registrations "
                    f"for project {project_id}"
                )
        except Exception as e:
            logger.debug(f"Compute registry cleanup skipped: {e}")

        del self._projects[project_id]
        await self._delete_project_storage(project_id)

        logger.info(f"Deleted project {project_id} (repos={repo_count})")
        return {"repo_count": repo_count}

    async def add_repo(
        self,
        project_id: str,
        request: RepoAddRequest
    ) -> Optional[RepoConfig]:
        """Add a repository to a project.

        For linked (external) repos, automatically clones into the internal
        git server so compute instances can access via internal URLs.
        """
        project = self._projects.get(project_id)
        if not project:
            return None

        repo_id = f"repo_{uuid.uuid4().hex[:8]}"
        git_project_name = f"{project_id}_{repo_id}"

        # Merge git_project_name and origin_url into metadata
        metadata = dict(request.metadata) if request.metadata else {}
        metadata["git_project_name"] = git_project_name
        metadata["origin_url"] = request.url

        repo = RepoConfig(
            repo_id=repo_id,
            name=request.name,
            url=request.url,
            default_branch=request.default_branch,
            ssh_key_id=request.ssh_key_id,
            metadata=metadata,
            added_at=datetime.now(timezone.utc)
        )

        project.repos.append(repo)

        # Set as primary if it's the first repo
        if len(project.repos) == 1:
            project.primary_repo_id = repo_id

        project.updated_at = datetime.now(timezone.utc)
        await self._save_project(project)

        # Auto-clone linked repo into internal git server
        try:
            from services.repo_sync_service import get_repo_sync_service
            sync_service = get_repo_sync_service()
            result = await sync_service.clone_repo(project_id, repo_id)

            if result.success:
                # Update URL to internal clone URL for compute access
                from api.git import get_repo_manager
                repo_manager = get_repo_manager()
                repo.url = repo_manager.get_repo_url(git_project_name)
                await self._save_project(project)
                logger.info(
                    f"Auto-cloned linked repo {repo_id} as {git_project_name}"
                )
            else:
                logger.warning(
                    f"Auto-clone failed for repo {repo_id}: {result.message}"
                )
        except Exception as e:
            logger.warning(f"Auto-clone failed for repo {repo_id}: {e}")

        logger.info(f"Added repo {repo_id} to project {project_id}")
        return repo

    async def create_internal_repo(
        self,
        project_id: str,
        request: RepoCreateInternalRequest
    ) -> Optional[RepoConfig]:
        """Create an internal Git repository hosted by ClaudeVN.

        Creates a bare Git repo via RepoManager and registers it in the project.

        Args:
            project_id: Project to add the repo to
            request: Internal repo creation request

        Returns:
            Created RepoConfig or None if project not found
        """
        project = self._projects.get(project_id)
        if not project:
            return None

        from api.git import get_repo_manager

        repo_id = f"repo_{uuid.uuid4().hex[:8]}"
        git_project_name = f"{project_id}_{repo_id}"

        # Create bare Git repository
        repo_manager = get_repo_manager()
        repo_manager.create_repo(git_project_name)

        # Get HTTP clone URL
        repo_url = repo_manager.get_repo_url(git_project_name)

        repo = RepoConfig(
            repo_id=repo_id,
            name=request.name,
            url=repo_url,
            default_branch=request.default_branch,
            is_internal=True,
            added_at=datetime.now(timezone.utc),
            metadata={"git_project_name": git_project_name}
        )

        project.repos.append(repo)

        # Set as primary if it's the first repo
        if len(project.repos) == 1:
            project.primary_repo_id = repo_id

        project.updated_at = datetime.now(timezone.utc)
        await self._save_project(project)

        logger.info(
            f"Created internal repo {repo_id} ({git_project_name}) "
            f"for project {project_id}"
        )
        return repo

    async def remove_repo(self, project_id: str, repo_id: str) -> bool:
        """Remove a repository from a project."""
        project = self._projects.get(project_id)
        if not project:
            return False

        # Find the repo before removing (for cleanup)
        repo = next((r for r in project.repos if r.repo_id == repo_id), None)

        project.repos = [r for r in project.repos if r.repo_id != repo_id]

        # Update primary if needed
        if project.primary_repo_id == repo_id:
            project.primary_repo_id = project.repos[0].repo_id if project.repos else None

        project.updated_at = datetime.now(timezone.utc)
        await self._save_project(project)

        # Clean up internal Git repo if applicable
        if repo and repo.is_internal:
            git_project_name = repo.metadata.get("git_project_name")
            if git_project_name:
                try:
                    from api.git import get_repo_manager
                    repo_manager = get_repo_manager()
                    repo_manager.delete_repo(git_project_name)
                    logger.info(
                        f"Deleted internal Git repo {git_project_name}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to delete internal Git repo "
                        f"{git_project_name}: {e}"
                    )

        logger.info(f"Removed repo {repo_id} from project {project_id}")
        return True

    async def get_repos(self, project_id: str) -> List[RepoConfig]:
        """Get all repositories for a project."""
        project = self._projects.get(project_id)
        if not project:
            return []
        return project.repos

    async def get_stats(self) -> ProjectStats:
        """Get project statistics."""
        by_status = {}
        total_repos = 0

        for project in self._projects.values():
            status = project.status.value
            by_status[status] = by_status.get(status, 0) + 1
            total_repos += len(project.repos)

        return ProjectStats(
            total=len(self._projects),
            by_status=by_status,
            total_repos=total_repos
        )

    # ============ Activity Tracking Methods ============

    def _calculate_activity_indicator(
        self,
        last_activity_at: Optional[datetime]
    ) -> ActivityIndicator:
        """Calculate activity indicator based on last activity timestamp."""
        if not last_activity_at:
            return ActivityIndicator.GRAY

        now = datetime.now(timezone.utc)
        delta = now - last_activity_at

        if delta <= timedelta(hours=24):
            return ActivityIndicator.GREEN
        elif delta <= timedelta(days=7):
            return ActivityIndicator.YELLOW
        else:
            return ActivityIndicator.RED

    async def calculate_activity_summary(
        self,
        project_id: str
    ) -> Optional[ActivitySummary]:
        """Calculate activity summary for a project from work items."""
        project = self._projects.get(project_id)
        if not project:
            return None

        now = datetime.now(timezone.utc)
        one_day_ago = now - timedelta(hours=24)
        seven_days_ago = now - timedelta(days=7)

        active_count = 0
        completed_today = 0
        completed_week = 0
        last_activity: Optional[datetime] = None

        # Calculate from work items if available
        if self._work_items_ref:
            work_items = self._work_items_ref()
            for work in work_items.values():
                if work.project_id != project_id:
                    continue

                # Track active work items (in_progress status)
                if work.status.value == "in_progress":
                    active_count += 1

                # Track completed work (must be actually completed, not failed)
                if work.completed_at and work.status.value == "completed":
                    if work.completed_at >= one_day_ago:
                        completed_today += 1
                    if work.completed_at >= seven_days_ago:
                        completed_week += 1

                # Track last activity
                activity_time = work.updated_at or work.created_at
                if activity_time and (
                    last_activity is None or activity_time > last_activity
                ):
                    last_activity = activity_time

        # Also check activity events
        events = self._activity_events.get(project_id, [])
        for event in events:
            if last_activity is None or event.timestamp > last_activity:
                last_activity = event.timestamp

        # Use project's stored last_activity_at if no work items found
        if last_activity is None:
            last_activity = project.last_activity_at

        return ActivitySummary(
            last_activity_at=last_activity,
            indicator=self._calculate_activity_indicator(last_activity),
            active_work_items=active_count,
            completed_today=completed_today,
            completed_week=completed_week
        )

    async def get_project_activity(
        self,
        project_id: str,
        limit: int = 10
    ) -> Optional[ProjectActivityResponse]:
        """Get activity data for a project."""
        project = self._projects.get(project_id)
        if not project:
            return None

        activity_summary = await self.calculate_activity_summary(project_id)
        if not activity_summary:
            activity_summary = ActivitySummary()

        events = self._activity_events.get(project_id, [])
        # Sort by timestamp descending and limit
        sorted_events = sorted(
            events, key=lambda e: e.timestamp, reverse=True
        )[:limit]

        return ProjectActivityResponse(
            project_id=project_id,
            activity_summary=activity_summary,
            recent_events=sorted_events
        )

    async def record_activity_event(
        self,
        project_id: str,
        event_type: ActivityEventType,
        description: str,
        work_id: Optional[str] = None,
        compute_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[ActivityEvent]:
        """Record an activity event for a project."""
        project = self._projects.get(project_id)
        if not project:
            return None

        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        event = ActivityEvent(
            event_id=event_id,
            event_type=event_type,
            project_id=project_id,
            description=description,
            timestamp=now,
            work_id=work_id,
            compute_id=compute_id,
            metadata=metadata or {}
        )

        # Add to events list
        if project_id not in self._activity_events:
            self._activity_events[project_id] = []
        self._activity_events[project_id].append(event)

        # Keep only last 100 events per project in memory
        if len(self._activity_events[project_id]) > 100:
            self._activity_events[project_id] = self._activity_events[
                project_id
            ][-100:]

        # Update project's last_activity_at
        project.last_activity_at = now
        project.updated_at = now
        await self._save_project(project)

        # Save event to Redis if available
        if self._redis:
            try:
                key = f"project:{project_id}:events"
                await self._redis._redis.lpush(key, event.model_dump_json())
                await self._redis._redis.ltrim(key, 0, 99)  # Keep last 100
            except Exception as e:
                logger.warning(f"Failed to save activity event to Redis: {e}")

        logger.debug(
            f"Recorded activity event {event_id} for project {project_id}"
        )
        return event

    async def update_project_activity(
        self,
        project_id: str
    ) -> Optional[Project]:
        """Update a project's activity summary."""
        project = self._projects.get(project_id)
        if not project:
            return None

        activity_summary = await self.calculate_activity_summary(project_id)
        if activity_summary:
            project.activity_summary = activity_summary
            project.updated_at = datetime.now(timezone.utc)
            await self._save_project(project)

        return project

    async def list_projects_with_activity(
        self,
        status: Optional[ProjectStatus] = None,
        search: Optional[str] = None,
        sort: Optional[str] = None,
        include_activity: bool = True
    ) -> ProjectListResponse:
        """List all projects with optional filtering, sorting, and activity summaries."""
        items = list(self._projects.values())

        # Apply status filter
        if status:
            items = [p for p in items if p.status == status]

        # Apply search filter (name or description)
        if search:
            search_lower = search.lower()
            items = [
                p for p in items
                if search_lower in p.name.lower()
                or search_lower in p.description.lower()
            ]

        # Apply sorting
        if sort:
            if sort == "name_asc":
                items.sort(key=lambda p: p.name.lower())
            elif sort == "name_desc":
                items.sort(key=lambda p: p.name.lower(), reverse=True)
            elif sort == "created_asc":
                items.sort(key=lambda p: p.created_at)
            elif sort == "created_desc":
                items.sort(key=lambda p: p.created_at, reverse=True)
            elif sort == "updated_asc":
                items.sort(key=lambda p: p.updated_at)
            elif sort == "updated_desc":
                items.sort(key=lambda p: p.updated_at, reverse=True)

        if include_activity:
            for project in items:
                activity = await self.calculate_activity_summary(
                    project.project_id
                )
                if activity:
                    project.activity_summary = activity

        return ProjectListResponse(
            items=items,
            total=len(items)
        )


    async def resolve_repo_details(
        self,
        project_id: str,
        repo_id: Optional[str] = None
    ) -> Optional[Dict[str, str]]:
        """Resolve git_project_name, clone_url, and default_branch for a project's repo.

        For linked repos, the bare repo name is '{project_id}_{repo_id}', making
        the clone URL 'http://serving:8002/git/{project_id}_{repo_id}.git'.

        Args:
            project_id: Project ID to look up
            repo_id: Specific repo ID (uses primary repo if not specified)

        Returns:
            Dict with git_project_name, clone_url, default_branch; or None if not found
        """
        project = self._projects.get(project_id)
        if not project:
            return None

        # Find the target repo
        repo: Optional[RepoConfig] = None
        if repo_id:
            repo = next((r for r in project.repos if r.repo_id == repo_id), None)
        else:
            repo = project.primary_repo

        if not repo:
            return None

        # Resolve git_project_name
        git_project_name = repo.metadata.get("git_project_name")
        if not git_project_name:
            # For internal repos without metadata, try filesystem resolution
            if repo.is_internal:
                from api.compute import _resolve_git_project_name
                git_project_name = _resolve_git_project_name(project_id)
            else:
                # External repos use project_id as-is
                git_project_name = project_id

        # Resolve clone_url
        clone_url = repo.url
        if repo.is_internal and not clone_url:
            from git.repo_manager import RepoManager
            clone_url = RepoManager().get_repo_url(git_project_name)

        return {
            "git_project_name": git_project_name,
            "clone_url": clone_url,
            "default_branch": repo.default_branch,
        }


# Singleton instance
_project_service: Optional[ProjectService] = None


def get_project_service() -> ProjectService:
    """Get the global project service instance."""
    global _project_service
    if _project_service is None:
        _project_service = ProjectService()
    return _project_service


def set_project_service(service: ProjectService):
    """Set the global project service instance."""
    global _project_service
    _project_service = service
