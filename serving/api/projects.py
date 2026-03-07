"""API endpoints for Project management."""

import logging
from enum import Enum
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from models.project import (
    Project, ProjectStatus, RepoConfig,
    ProjectCreateRequest, ProjectUpdateRequest,
    RepoAddRequest, RepoCreateInternalRequest,
    ProjectListResponse, ProjectStats,
    RepoStatusResponse, RepoSyncResponse,
    ProjectActivityResponse
)
from models.work_map import ProjectDeleteResponse
from services.project_service import get_project_service
from services.repo_sync_service import get_repo_sync_service
from services.work_map_service import get_work_map_service
from middleware.user_context import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


# ============ Stats Endpoint (must be before /{project_id}) ============

@router.get("/stats", response_model=ProjectStats)
async def get_stats():
    """Get project statistics.

    Returns:
        Project statistics including counts by status
    """
    service = get_project_service()
    return await service.get_stats()


# ============ Project CRUD Endpoints ============

class SortOrder(str, Enum):
    """Sort order options for project listing."""
    NAME_ASC = "name_asc"
    NAME_DESC = "name_desc"
    CREATED_ASC = "created_asc"
    CREATED_DESC = "created_desc"
    UPDATED_ASC = "updated_asc"
    UPDATED_DESC = "updated_desc"


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by name or description"),
    sort: Optional[SortOrder] = Query(None, description="Sort order"),
    include_activity: bool = Query(True, description="Include activity summary in response")
):
    """List all projects.

    Args:
        status_filter: Filter by project status (active, archived, suspended)
        search: Search query for name or description
        sort: Sort order (name_asc, name_desc, created_asc, created_desc, updated_asc, updated_desc)
        include_activity: Include activity_summary in response (default: true)

    Returns:
        List of projects with optional activity summaries
    """
    service = get_project_service()

    project_status = None
    if status_filter:
        try:
            project_status = ProjectStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}"
            )

    return await service.list_projects_with_activity(
        status=project_status,
        search=search,
        sort=sort.value if sort else None,
        include_activity=include_activity
    )


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(request: ProjectCreateRequest):
    """Create a new project.

    Args:
        request: Project creation request

    Returns:
        Created project
    """
    service = get_project_service()
    project = await service.create_project(request)

    # Populate user attribution
    user = get_current_user()
    if user:
        project.created_by = user.get('sub')
        project.created_by_name = user.get('username') or user.get('email')
        await service._save_project(project)

    return project


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str):
    """Get a project by ID.

    Args:
        project_id: Project identifier

    Returns:
        Project details
    """
    service = get_project_service()
    project = await service.get_project(project_id)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}"
        )

    return project


@router.patch("/{project_id}", response_model=Project)
async def update_project(project_id: str, request: ProjectUpdateRequest):
    """Update a project.

    Args:
        project_id: Project identifier
        request: Update request

    Returns:
        Updated project
    """
    service = get_project_service()
    project = await service.update_project(project_id, request)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}"
        )

    # Populate user attribution
    user = get_current_user()
    if user:
        project.modified_by = user.get('sub')
        project.modified_by_name = user.get('username') or user.get('email')
        await service._save_project(project)

    return project


@router.delete("/{project_id}", response_model=ProjectDeleteResponse)
async def delete_project(
    project_id: str,
    cascade: bool = Query(False, description="Delete all child goals, issues, and work items")
):
    """Delete a project.

    Use cascade=true to also delete all associated goals, issues, and work items.
    Without cascade, only the project record is removed (children become orphaned).
    """
    service = get_project_service()

    if project_id not in service._projects:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}"
        )

    goal_count = 0
    issue_count = 0
    work_item_count = 0
    comment_count = 0

    if cascade:
        work_map_service = get_work_map_service()
        counts = await work_map_service.cascade_delete_project(project_id)
        goal_count = counts["goal_count"]
        issue_count = counts["issue_count"]
        work_item_count = counts["work_item_count"]
        comment_count = counts["comment_count"]

    result = await service.delete_project(project_id)

    return ProjectDeleteResponse(
        project_id=project_id,
        deleted=True,
        goal_count=goal_count,
        issue_count=issue_count,
        work_item_count=work_item_count,
        comment_count=comment_count,
        repo_count=result.get("repo_count", 0),
    )


# ============ Activity Endpoints ============

@router.get("/{project_id}/activity", response_model=ProjectActivityResponse)
async def get_project_activity(
    project_id: str,
    limit: int = Query(10, ge=1, le=50, description="Number of recent events to return")
):
    """Get activity data for a project.

    Returns activity summary and recent events for the project.

    Args:
        project_id: Project identifier
        limit: Number of recent events to return (default: 10, max: 50)

    Returns:
        Project activity summary and recent events
    """
    service = get_project_service()
    activity = await service.get_project_activity(project_id, limit=limit)

    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}"
        )

    return activity


# ============ Repository Endpoints ============

@router.get("/{project_id}/repos", response_model=List[RepoConfig])
async def get_project_repos(project_id: str):
    """Get all repositories for a project.

    Args:
        project_id: Project identifier

    Returns:
        List of repositories
    """
    service = get_project_service()
    project = await service.get_project(project_id)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}"
        )

    return await service.get_repos(project_id)


@router.post("/{project_id}/repos", response_model=RepoConfig, status_code=status.HTTP_201_CREATED)
async def add_repo(project_id: str, request: RepoAddRequest):
    """Add a repository to a project.

    Args:
        project_id: Project identifier
        request: Repository configuration

    Returns:
        Added repository
    """
    service = get_project_service()
    repo = await service.add_repo(project_id, request)

    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}"
        )

    return repo


@router.post(
    "/{project_id}/repos/internal",
    response_model=RepoConfig,
    status_code=status.HTTP_201_CREATED
)
async def create_internal_repo(project_id: str, request: RepoCreateInternalRequest):
    """Create an internal Git repository hosted by ClaudeVN.

    Creates a bare Git repo on ClaudeVN's built-in Git server and registers
    it in the project. No external URL needed.

    Args:
        project_id: Project identifier
        request: Internal repo creation request (name and optional default branch)

    Returns:
        Created repository configuration
    """
    service = get_project_service()
    repo = await service.create_internal_repo(project_id, request)

    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}"
        )

    return repo


@router.delete("/{project_id}/repos/{repo_id}")
async def remove_repo(project_id: str, repo_id: str):
    """Remove a repository from a project.

    Args:
        project_id: Project identifier
        repo_id: Repository identifier

    Returns:
        Deletion confirmation
    """
    service = get_project_service()
    removed = await service.remove_repo(project_id, repo_id)

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project or repo not found"
        )

    return {"message": f"Repo {repo_id} removed from project {project_id}"}


# ============ Repository Sync Endpoints ============

@router.post("/{project_id}/repos/{repo_id}/clone", response_model=RepoSyncResponse)
async def clone_repo(project_id: str, repo_id: str):
    """Clone a repository from its configured URL.

    Clones the repository into Serving's Git infrastructure and sets up
    the origin remote for pushing work back.

    Args:
        project_id: Project identifier
        repo_id: Repository identifier

    Returns:
        Clone operation result
    """
    sync_service = get_repo_sync_service()
    result = await sync_service.clone_repo(project_id, repo_id)

    if not result.success and "not found" in result.message.lower():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.message
        )

    return result


@router.post("/{project_id}/repos/{repo_id}/pull", response_model=RepoSyncResponse)
async def pull_repo(project_id: str, repo_id: str):
    """Pull latest changes from origin.

    Fetches all branches and tags from the upstream origin.

    Args:
        project_id: Project identifier
        repo_id: Repository identifier

    Returns:
        Pull operation result
    """
    sync_service = get_repo_sync_service()
    result = await sync_service.pull_repo(project_id, repo_id)

    if not result.success and "not found" in result.message.lower():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.message
        )

    return result


@router.post("/{project_id}/repos/{repo_id}/push", response_model=RepoSyncResponse)
async def push_repo(
    project_id: str,
    repo_id: str,
    branch: str = Query(..., description="Branch name to push"),
    force: bool = Query(False, description="Force push (use with caution)")
):
    """Push a branch to origin.

    Pushes the specified branch to the upstream origin repository.

    Args:
        project_id: Project identifier
        repo_id: Repository identifier
        branch: Branch name to push
        force: Force push flag

    Returns:
        Push operation result
    """
    sync_service = get_repo_sync_service()
    result = await sync_service.push_to_origin(project_id, repo_id, branch, force)

    if not result.success and "not found" in result.message.lower():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.message
        )

    return result


@router.get("/{project_id}/repos/{repo_id}/status", response_model=RepoStatusResponse)
async def get_repo_status(project_id: str, repo_id: str):
    """Get status of a repository.

    Returns clone status, branches, sync times, and other repository info.

    Args:
        project_id: Project identifier
        repo_id: Repository identifier

    Returns:
        Repository status
    """
    sync_service = get_repo_sync_service()
    result = await sync_service.get_repo_status(project_id, repo_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project or repo not found"
        )

    return result


@router.post("/{project_id}/repos/{repo_id}/sync", response_model=RepoSyncResponse)
async def sync_repo(project_id: str, repo_id: str):
    """Sync repository with origin (pull latest).

    Convenience endpoint that pulls latest changes from origin.
    Equivalent to calling the pull endpoint.

    Args:
        project_id: Project identifier
        repo_id: Repository identifier

    Returns:
        Sync operation result
    """
    sync_service = get_repo_sync_service()

    # Check if repo is cloned first
    status_result = await sync_service.get_repo_status(project_id, repo_id)
    if not status_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project or repo not found"
        )

    if status_result.clone_status.value == "not_cloned":
        # Clone first, then pull
        clone_result = await sync_service.clone_repo(project_id, repo_id)
        return clone_result

    # Already cloned, just pull
    result = await sync_service.pull_repo(project_id, repo_id)
    return result
