"""Git infrastructure API endpoints.

Provides REST API for Git repository management, SSH keys, and PR operations.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from git.pr_service import PRService, PRStatus, PullRequest
from git.repo_manager import RepoManager
from git.ssh_key_manager import SSHKeyManager
from git.ssh_server import get_ssh_server

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/git", tags=["git"])

# Service instances (created lazily)
_pr_service: Optional[PRService] = None
_repo_manager: Optional[RepoManager] = None
_ssh_manager: Optional[SSHKeyManager] = None


def get_pr_service() -> PRService:
    """Get PR service singleton."""
    global _pr_service
    if _pr_service is None:
        _pr_service = PRService()
    return _pr_service


def get_repo_manager() -> RepoManager:
    """Get repo manager singleton."""
    global _repo_manager
    if _repo_manager is None:
        _repo_manager = RepoManager()
    return _repo_manager


def get_ssh_manager() -> SSHKeyManager:
    """Get SSH key manager singleton."""
    global _ssh_manager
    if _ssh_manager is None:
        _ssh_manager = SSHKeyManager()
    return _ssh_manager


# ==========================================================================
# Request/Response Models
# ==========================================================================

class CreateRepoRequest(BaseModel):
    """Request to create a new repository."""
    project: str = Field(..., description="Project name")
    install_hooks: bool = Field(default=True, description="Install Git hooks")


class RepoResponse(BaseModel):
    """Repository information response."""
    project: str
    ssh_url: str
    exists: bool


class HookStatus(BaseModel):
    """Status of a single Git hook."""
    exists: bool
    executable: bool
    path: Optional[str] = None


class HookStatusResponse(BaseModel):
    """Response with hook installation status."""
    project: str
    hooks_installed: bool
    pre_receive: HookStatus
    post_receive: HookStatus


class RepoStatusResponse(BaseModel):
    """Extended repository status response with hook info."""
    project: str
    path: str
    ssh_url: str
    origin_url: Optional[str] = None
    default_branch: Optional[str] = None
    branches: List[str] = []
    branch_count: int = 0
    is_mirror: bool = False
    exists: bool
    hooks_installed: bool = False
    hooks: Optional[HookStatusResponse] = None


class InstallHooksResponse(BaseModel):
    """Response from hook installation."""
    project: str
    success: bool
    message: str


class MigrateHooksResponse(BaseModel):
    """Response from hook migration across all repos."""
    total: int
    success: int
    failed: int
    results: dict


class RegisterKeyRequest(BaseModel):
    """Request to register SSH key."""
    compute_id: str = Field(..., description="Compute instance ID")
    public_key: str = Field(..., description="SSH public key")


class GenerateKeyResponse(BaseModel):
    """Response with generated key pair."""
    compute_id: str
    public_key: str
    private_key: str


class CreatePRRequest(BaseModel):
    """Request to create a pull request."""
    project: str = Field(..., description="Project name")
    branch: str = Field(..., description="Branch name")
    compute_id: str = Field(..., description="Compute instance ID")
    task_id: Optional[str] = Field(None, description="Associated task ID")
    title: Optional[str] = Field(None, description="PR title")
    description: Optional[str] = Field(None, description="PR description")


class UpdatePRRequest(BaseModel):
    """Request to update PR status."""
    status: str = Field(..., description="New status")
    reviewed_by: Optional[str] = Field(None, description="Reviewer identifier")


class PRResponse(BaseModel):
    """Pull request response."""
    project: str
    branch: str
    status: str
    compute_id: str
    task_id: Optional[str]
    title: Optional[str]
    description: Optional[str]
    head_commit: Optional[str]
    base_branch: str
    queue_position: Optional[int]
    created_at: Optional[str]
    updated_at: Optional[str]
    reviewed_by: Optional[str]
    merged_at: Optional[str]


class MergeRequest(BaseModel):
    """Request to merge a PR."""
    delete_branch: bool = Field(default=True, description="Delete branch after merge")


class MergeResponse(BaseModel):
    """Merge result response."""
    success: bool
    merged_commit: Optional[str]
    branch: str
    deleted: bool
    error: Optional[str] = None


class DeleteBranchResponse(BaseModel):
    """Response from branch deletion."""
    project: str
    branch: str
    deleted: bool


def pr_to_response(pr: PullRequest) -> PRResponse:
    """Convert PullRequest to response model."""
    return PRResponse(
        project=pr.project,
        branch=pr.branch,
        status=pr.status.value,
        compute_id=pr.compute_id,
        task_id=pr.task_id,
        title=pr.title,
        description=pr.description,
        head_commit=pr.head_commit,
        base_branch=pr.base_branch,
        queue_position=pr.queue_position,
        created_at=pr.created_at,
        updated_at=pr.updated_at,
        reviewed_by=pr.reviewed_by,
        merged_at=pr.merged_at
    )


# ==========================================================================
# Repository Endpoints
# ==========================================================================

@router.post("/repos", response_model=RepoResponse, status_code=status.HTTP_201_CREATED)
async def create_repository(request: CreateRepoRequest):
    """Create a new Git repository.

    Args:
        request: Create repo request

    Returns:
        Repository information

    Raises:
        HTTPException: If repository already exists
    """
    repo_manager = get_repo_manager()

    if repo_manager.repo_exists(request.project):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository already exists: {request.project}"
        )

    try:
        repo_manager.create_repo(request.project, install_hooks=request.install_hooks)
        ssh_url = repo_manager.get_repo_url(request.project)

        logger.info(f"Created repository: {request.project}")

        return RepoResponse(
            project=request.project,
            ssh_url=ssh_url,
            exists=True
        )
    except Exception as e:
        logger.error(f"Failed to create repository: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/repos", response_model=List[str])
async def list_repositories():
    """List all repositories.

    Returns:
        List of project names
    """
    repo_manager = get_repo_manager()
    return repo_manager.list_repos()


@router.get("/repos/{project}", response_model=RepoResponse)
async def get_repository(project: str):
    """Get repository information.

    Args:
        project: Project name

    Returns:
        Repository information

    Raises:
        HTTPException: If repository not found
    """
    repo_manager = get_repo_manager()

    if not repo_manager.repo_exists(project):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {project}"
        )

    return RepoResponse(
        project=project,
        ssh_url=repo_manager.get_repo_url(project),
        exists=True
    )


@router.delete("/repos/{project}", status_code=status.HTTP_200_OK)
async def delete_repository(project: str):
    """Delete a repository.

    Args:
        project: Project name

    Returns:
        Success message

    Raises:
        HTTPException: If repository not found
    """
    repo_manager = get_repo_manager()

    if not repo_manager.delete_repo(project):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {project}"
        )

    logger.warning(f"Deleted repository: {project}")

    return {"status": "deleted", "project": project}


@router.get("/repos/{project}/branches", response_model=List[str])
async def list_branches(project: str):
    """List branches in a repository.

    Args:
        project: Project name

    Returns:
        List of branch names
    """
    repo_manager = get_repo_manager()

    if not repo_manager.repo_exists(project):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {project}"
        )

    return repo_manager.get_branches(project)


@router.delete("/repos/{project}/branches/{branch:path}", response_model=DeleteBranchResponse)
async def delete_branch(project: str, branch: str):
    """Delete a branch from the repository.

    Protected branches (main, master) cannot be deleted.

    Args:
        project: Project name
        branch: Branch name to delete

    Returns:
        Deletion result

    Raises:
        HTTPException: If repository not found, branch not found, or branch is protected
    """
    repo_manager = get_repo_manager()

    if not repo_manager.repo_exists(project):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {project}"
        )

    try:
        deleted = repo_manager.delete_branch(project, branch)
    except ValueError as e:
        # Protected branch
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Branch not found: {branch}"
        )

    logger.info(f"Deleted branch {branch} from {project}")

    return DeleteBranchResponse(
        project=project,
        branch=branch,
        deleted=True
    )


@router.get("/repos/{project}/status", response_model=RepoStatusResponse)
async def get_repository_status(project: str):
    """Get detailed repository status including hook status.

    Args:
        project: Project name

    Returns:
        Extended repository status with hook information

    Raises:
        HTTPException: If repository not found
    """
    repo_manager = get_repo_manager()

    if not repo_manager.repo_exists(project):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {project}"
        )

    # Get basic repo status
    repo_status = repo_manager.get_repo_status(project)
    if not repo_status:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get repository status: {project}"
        )

    # Get hook status
    hook_status = repo_manager.verify_hooks(project)

    return RepoStatusResponse(
        project=project,
        path=repo_status["path"],
        ssh_url=repo_manager.get_repo_url(project),
        origin_url=repo_status.get("origin_url"),
        default_branch=repo_status.get("default_branch"),
        branches=repo_status.get("branches", []),
        branch_count=repo_status.get("branch_count", 0),
        is_mirror=repo_status.get("is_mirror", False),
        exists=True,
        hooks_installed=hook_status["hooks_installed"],
        hooks=HookStatusResponse(
            project=project,
            hooks_installed=hook_status["hooks_installed"],
            pre_receive=HookStatus(**hook_status["pre_receive"]),
            post_receive=HookStatus(**hook_status["post_receive"])
        )
    )


@router.get("/repos/{project}/hooks", response_model=HookStatusResponse)
async def get_hook_status(project: str):
    """Get Git hook installation status for a repository.

    Args:
        project: Project name

    Returns:
        Hook installation status

    Raises:
        HTTPException: If repository not found
    """
    repo_manager = get_repo_manager()

    if not repo_manager.repo_exists(project):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {project}"
        )

    try:
        hook_status = repo_manager.verify_hooks(project)
        return HookStatusResponse(
            project=project,
            hooks_installed=hook_status["hooks_installed"],
            pre_receive=HookStatus(**hook_status["pre_receive"]),
            post_receive=HookStatus(**hook_status["post_receive"])
        )
    except Exception as e:
        logger.error(f"Failed to get hook status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/repos/{project}/hooks", response_model=InstallHooksResponse)
async def install_hooks(project: str):
    """Install or reinstall Git hooks for a repository.

    This endpoint can be used to:
    - Install hooks on a repository that doesn't have them
    - Update hooks to the latest version
    - Fix broken hook installations

    Args:
        project: Project name

    Returns:
        Installation result

    Raises:
        HTTPException: If repository not found or installation fails
    """
    repo_manager = get_repo_manager()

    if not repo_manager.repo_exists(project):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {project}"
        )

    try:
        repo_manager.install_hooks(project)
        logger.info(f"Hooks installed for repository: {project}")
        return InstallHooksResponse(
            project=project,
            success=True,
            message=f"Hooks successfully installed for {project}"
        )
    except Exception as e:
        logger.error(f"Failed to install hooks for {project}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/repos/hooks/migrate", response_model=MigrateHooksResponse)
async def migrate_hooks():
    """Install hooks on all existing repositories.

    This endpoint is used for migrating existing repositories to include
    the latest Git hooks. Safe to run multiple times (idempotent).

    Returns:
        Migration results for all repositories
    """
    repo_manager = get_repo_manager()

    try:
        results = repo_manager.install_hooks_all()
        logger.info(
            f"Hook migration complete: {results['success']}/{results['total']} succeeded"
        )
        return MigrateHooksResponse(**results)
    except Exception as e:
        logger.error(f"Hook migration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==========================================================================
# SSH Key Endpoints
# ==========================================================================

@router.post("/ssh/keys", status_code=status.HTTP_201_CREATED)
async def register_ssh_key(request: RegisterKeyRequest):
    """Register an SSH public key for a compute instance.

    Args:
        request: Register key request

    Returns:
        Registration status

    Raises:
        HTTPException: If key format is invalid
    """
    ssh_manager = get_ssh_manager()

    try:
        registered = ssh_manager.register_key(request.compute_id, request.public_key)

        return {
            "status": "registered" if registered else "unchanged",
            "compute_id": request.compute_id,
            "message": "SSH key registered" if registered else "Key already registered"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/ssh/keys/{compute_id}", status_code=status.HTTP_200_OK)
async def revoke_ssh_key(compute_id: str):
    """Revoke SSH key for a compute instance.

    Args:
        compute_id: Compute instance ID

    Returns:
        Revocation status

    Raises:
        HTTPException: If key not found
    """
    ssh_manager = get_ssh_manager()

    if not ssh_manager.revoke_key(compute_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No SSH key found for: {compute_id}"
        )

    return {"status": "revoked", "compute_id": compute_id}


@router.get("/ssh/keys", response_model=List[str])
async def list_ssh_keys():
    """List compute instances with registered SSH keys.

    Returns:
        List of compute IDs
    """
    ssh_manager = get_ssh_manager()
    return ssh_manager.list_registered()


@router.post("/ssh/keys/{compute_id}/generate", response_model=GenerateKeyResponse)
async def generate_ssh_key(compute_id: str):
    """Generate a new SSH key pair for a compute instance.

    This creates a new key pair and automatically registers the public key.

    Args:
        compute_id: Compute instance ID

    Returns:
        Generated key pair (private key should be sent to compute securely)
    """
    ssh_manager = get_ssh_manager()

    try:
        private_key, public_key = ssh_manager.generate_key_pair(compute_id)
        ssh_manager.register_key(compute_id, public_key)

        logger.info(f"Generated SSH key pair for: {compute_id}")

        return GenerateKeyResponse(
            compute_id=compute_id,
            public_key=public_key,
            private_key=private_key
        )
    except Exception as e:
        logger.error(f"Failed to generate key pair: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==========================================================================
# Pull Request Endpoints
# ==========================================================================

@router.post("/prs", response_model=PRResponse, status_code=status.HTTP_201_CREATED)
async def create_pull_request(request: CreatePRRequest):
    """Create a new pull request.

    Args:
        request: Create PR request

    Returns:
        Created pull request

    Raises:
        HTTPException: If branch doesn't exist or PR already exists
    """
    pr_service = get_pr_service()

    try:
        pr = await pr_service.create_pr(
            project=request.project,
            branch=request.branch,
            compute_id=request.compute_id,
            task_id=request.task_id,
            title=request.title,
            description=request.description
        )

        logger.info(f"Created PR: {request.project}/{request.branch}")

        return pr_to_response(pr)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/prs/{project}", response_model=List[PRResponse])
async def list_pull_requests(
    project: str,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    compute_id: Optional[str] = Query(None, description="Filter by compute ID")
):
    """List pull requests for a project.

    Args:
        project: Project name
        status_filter: Optional status filter
        compute_id: Optional compute ID filter

    Returns:
        List of pull requests
    """
    pr_service = get_pr_service()

    status_enum = None
    if status_filter:
        try:
            status_enum = PRStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}"
            )

    prs = await pr_service.list_prs(project, status=status_enum, compute_id=compute_id)
    return [pr_to_response(pr) for pr in prs]


@router.get("/prs/{project}/{branch}", response_model=PRResponse)
async def get_pull_request(project: str, branch: str):
    """Get pull request details.

    Args:
        project: Project name
        branch: Branch name

    Returns:
        Pull request details

    Raises:
        HTTPException: If PR not found
    """
    pr_service = get_pr_service()

    pr = await pr_service.get_pr(project, branch)
    if not pr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PR not found: {project}/{branch}"
        )

    return pr_to_response(pr)


@router.patch("/prs/{project}/{branch}", response_model=PRResponse)
async def update_pull_request(project: str, branch: str, request: UpdatePRRequest):
    """Update pull request status.

    Args:
        project: Project name
        branch: Branch name
        request: Update request

    Returns:
        Updated pull request

    Raises:
        HTTPException: If PR not found or invalid status
    """
    pr_service = get_pr_service()

    try:
        status_enum = PRStatus(request.status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {request.status}"
        )

    try:
        pr = await pr_service.update_status(
            project, branch, status_enum, reviewed_by=request.reviewed_by
        )
        return pr_to_response(pr)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/prs/{project}/{branch}/approve", response_model=PRResponse)
async def approve_pull_request(
    project: str,
    branch: str,
    reviewed_by: str = Query(..., description="Reviewer identifier")
):
    """Approve a pull request.

    Args:
        project: Project name
        branch: Branch name
        reviewed_by: Reviewer identifier

    Returns:
        Updated pull request
    """
    pr_service = get_pr_service()

    try:
        pr = await pr_service.approve(project, branch, reviewed_by)
        return pr_to_response(pr)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/prs/{project}/{branch}/reject", response_model=PRResponse)
async def reject_pull_request(
    project: str,
    branch: str,
    reviewed_by: str = Query(..., description="Reviewer identifier")
):
    """Reject a pull request.

    Args:
        project: Project name
        branch: Branch name
        reviewed_by: Reviewer identifier

    Returns:
        Updated pull request
    """
    pr_service = get_pr_service()

    try:
        pr = await pr_service.reject(project, branch, reviewed_by)
        return pr_to_response(pr)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/prs/{project}/{branch}/merge", response_model=MergeResponse)
async def merge_pull_request(project: str, branch: str, request: Optional[MergeRequest] = None):
    """Merge a pull request.

    Args:
        project: Project name
        branch: Branch name
        request: Optional merge options

    Returns:
        Merge result
    """
    pr_service = get_pr_service()
    delete_branch = request.delete_branch if request else True

    try:
        result = await pr_service.merge(project, branch, delete_branch=delete_branch)
        return MergeResponse(**result)
    except ValueError as e:
        return MergeResponse(
            success=False,
            merged_commit=None,
            branch=branch,
            deleted=False,
            error=str(e)
        )


@router.get("/prs/{project}/{branch}/mergeable")
async def check_mergeable(project: str, branch: str):
    """Check if a PR can be merged.

    Args:
        project: Project name
        branch: Branch name

    Returns:
        Mergeability status
    """
    pr_service = get_pr_service()
    return await pr_service.check_mergeable(project, branch)


# ==========================================================================
# Queue Endpoints
# ==========================================================================

@router.get("/queues/{project}/prs", response_model=List[PRResponse])
async def get_pr_queue(project: str):
    """Get PRs in queue order.

    Args:
        project: Project name

    Returns:
        List of PRs in queue order
    """
    pr_service = get_pr_service()
    prs = await pr_service.get_pr_queue(project)
    return [pr_to_response(pr) for pr in prs]


@router.get("/queues/{project}/merges", response_model=List[str])
async def get_merge_queue(project: str):
    """Get branches in merge queue.

    Args:
        project: Project name

    Returns:
        List of branch names
    """
    pr_service = get_pr_service()
    return await pr_service.get_merge_queue(project)


@router.post("/queues/{project}/process-merges")
async def process_merge_queue(project: str):
    """Process pending merges from the queue.

    Args:
        project: Project name

    Returns:
        List of merge results
    """
    pr_service = get_pr_service()
    return await pr_service.process_merge_queue(project)


# ==========================================================================
# Compute Integration Endpoints
# ==========================================================================

@router.get("/compute/{compute_id}/prs", response_model=List[PRResponse])
async def get_compute_prs(compute_id: str):
    """Get all PRs owned by a compute instance.

    Args:
        compute_id: Compute instance ID

    Returns:
        List of PRs
    """
    pr_service = get_pr_service()
    prs = await pr_service.get_compute_prs(compute_id)
    return [pr_to_response(pr) for pr in prs]


@router.post("/compute/{compute_id}/cleanup")
async def cleanup_compute(compute_id: str):
    """Clean up when a compute instance is deregistered.

    Closes all pending PRs from the compute instance.

    Args:
        compute_id: Compute instance ID

    Returns:
        Cleanup result
    """
    pr_service = get_pr_service()
    closed = await pr_service.cleanup_compute(compute_id)

    return {
        "compute_id": compute_id,
        "prs_closed": closed
    }


# ==========================================================================
# SSH Server Endpoints
# ==========================================================================

@router.get("/ssh/server/status")
async def get_ssh_server_status():
    """Get SSH Git server status.

    Returns:
        SSH server status including running state, port, and configuration
    """
    ssh_server = get_ssh_server()
    if ssh_server:
        return ssh_server.get_status()
    return {
        "running": False,
        "port": None,
        "message": "SSH server not initialized"
    }


@router.get("/ssh/server/clone-url/{project}")
async def get_clone_url(project: str):
    """Get SSH clone URL for a project.

    Args:
        project: Project name

    Returns:
        SSH clone URL
    """
    ssh_server = get_ssh_server()
    if not ssh_server or not ssh_server.is_running():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSH server is not running"
        )

    repo_manager = get_repo_manager()
    if not repo_manager.repo_exists(project):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {project}"
        )

    return {
        "project": project,
        "clone_url": ssh_server.get_clone_url(project)
    }
