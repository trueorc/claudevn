"""Git infrastructure API endpoints.

Provides REST API for Git repository management, token auth, and PR operations.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from git.pr_service import PRService, PRStatus, PullRequest
from git.repo_manager import RepoManager
from git.ssh_key_service import SSHKeyService, get_ssh_key_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/git", tags=["git"])

# Service instances (created lazily)
_pr_service: Optional[PRService] = None
_repo_manager: Optional[RepoManager] = None


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
    clone_url: str
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
    clone_url: str
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


class CreatePATRequest(BaseModel):
    """Request to create a personal access token."""
    owner: str = Field(..., description="Token owner")
    description: str = Field(default="", description="Token description")


class CreatePATResponse(BaseModel):
    """Response with created PAT (token shown only once)."""
    token: str
    owner: str
    description: str


class TokenListItem(BaseModel):
    """Token metadata (without the actual token value)."""
    type: str
    token_hash_prefix: str
    created_at: Optional[str] = None
    compute_id: Optional[str] = None
    owner: Optional[str] = None
    description: Optional[str] = None


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


class GenerateSSHKeyRequest(BaseModel):
    """Request to generate a new SSH key pair."""
    description: str = Field(default="", description="Label for the key")


class SSHKeyResponse(BaseModel):
    """SSH key response with public key."""
    key_id: str
    public_key: str
    fingerprint: str
    description: str = ""


class SSHKeyListItem(BaseModel):
    """SSH key metadata (no private key material)."""
    key_id: str
    description: str = ""
    fingerprint: str = ""
    created_at: str = ""


class SSHKeyDeleteResponse(BaseModel):
    """Response from SSH key deletion."""
    key_id: str
    deleted: bool
    referencing_repos: List[str] = Field(
        default_factory=list,
        description="Repos that reference this key_id (if any)",
    )


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
    """Create a new Git repository."""
    repo_manager = get_repo_manager()

    if repo_manager.repo_exists(request.project):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository already exists: {request.project}"
        )

    try:
        repo_manager.create_repo(request.project, install_hooks=request.install_hooks)
        clone_url = repo_manager.get_repo_url(request.project)

        logger.info(f"Created repository: {request.project}")

        return RepoResponse(
            project=request.project,
            clone_url=clone_url,
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
    """List all repositories."""
    repo_manager = get_repo_manager()
    return repo_manager.list_repos()


@router.get("/repos/{project}", response_model=RepoResponse)
async def get_repository(project: str):
    """Get repository information."""
    repo_manager = get_repo_manager()

    if not repo_manager.repo_exists(project):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {project}"
        )

    return RepoResponse(
        project=project,
        clone_url=repo_manager.get_repo_url(project),
        exists=True
    )


@router.delete("/repos/{project}", status_code=status.HTTP_200_OK)
async def delete_repository(project: str):
    """Delete a repository."""
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
    """List branches in a repository."""
    repo_manager = get_repo_manager()

    if not repo_manager.repo_exists(project):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {project}"
        )

    return repo_manager.get_branches(project)


@router.delete("/repos/{project}/branches/{branch:path}", response_model=DeleteBranchResponse)
async def delete_branch(project: str, branch: str):
    """Delete a branch from the repository."""
    repo_manager = get_repo_manager()

    if not repo_manager.repo_exists(project):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {project}"
        )

    try:
        deleted = repo_manager.delete_branch(project, branch)
    except ValueError as e:
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
    return DeleteBranchResponse(project=project, branch=branch, deleted=True)


@router.get("/repos/{project}/status", response_model=RepoStatusResponse)
async def get_repository_status(project: str):
    """Get detailed repository status including hook status."""
    repo_manager = get_repo_manager()

    if not repo_manager.repo_exists(project):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {project}"
        )

    repo_status = repo_manager.get_repo_status(project)
    if not repo_status:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get repository status: {project}"
        )

    hook_status = repo_manager.verify_hooks(project)

    return RepoStatusResponse(
        project=project,
        path=repo_status["path"],
        clone_url=repo_manager.get_repo_url(project),
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
    """Get Git hook installation status for a repository."""
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
    """Install or reinstall Git hooks for a repository."""
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
    """Install hooks on all existing repositories."""
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
# Clone URL Endpoint
# ==========================================================================

@router.get("/clone-url/{project}")
async def get_clone_url(project: str):
    """Get HTTP clone URL for a project."""
    repo_manager = get_repo_manager()
    if not repo_manager.repo_exists(project):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {project}"
        )

    return {
        "project": project,
        "clone_url": repo_manager.get_repo_url(project)
    }


# ==========================================================================
# Token Management Endpoints (PAT)
# ==========================================================================

@router.post("/tokens", response_model=CreatePATResponse, status_code=status.HTTP_201_CREATED)
async def create_personal_access_token(request: CreatePATRequest):
    """Create a personal access token for external Git access."""
    from git.git_token_service import get_git_token_service

    token_service = get_git_token_service()
    if not token_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token service not available"
        )

    token = await token_service.create_personal_access_token(
        owner=request.owner,
        description=request.description
    )

    return CreatePATResponse(
        token=token,
        owner=request.owner,
        description=request.description
    )


@router.get("/tokens", response_model=List[TokenListItem])
async def list_tokens(token_type: Optional[str] = Query(None, alias="type")):
    """List all Git access tokens (metadata only)."""
    from git.git_token_service import get_git_token_service

    token_service = get_git_token_service()
    if not token_service:
        return []

    tokens = await token_service.list_tokens(token_type=token_type)
    return [TokenListItem(**t) for t in tokens]


@router.delete("/tokens/{token_hash_prefix}")
async def revoke_token(token_hash_prefix: str):
    """Revoke a personal access token."""
    from git.git_token_service import get_git_token_service

    token_service = get_git_token_service()
    if not token_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token service not available"
        )

    # Find the full hash matching the prefix
    tokens = await token_service.list_tokens(token_type="pat")
    for t in tokens:
        full_hash = t.get("token_hash", "")
        if full_hash.startswith(token_hash_prefix) or t.get("token_hash_prefix", "").startswith(token_hash_prefix):
            if await token_service.revoke_pat(full_hash):
                return {"status": "revoked"}

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Token not found"
    )


# ==========================================================================
# Pull Request Endpoints
# ==========================================================================

@router.post("/prs", response_model=PRResponse, status_code=status.HTTP_201_CREATED)
async def create_pull_request(request: CreatePRRequest):
    """Create a new pull request."""
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
    """List pull requests for a project."""
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
    """Get pull request details."""
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
    """Update pull request status."""
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
    """Approve a pull request."""
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
    """Reject a pull request."""
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
    """Merge a pull request."""
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
    """Check if a PR can be merged."""
    pr_service = get_pr_service()
    return await pr_service.check_mergeable(project, branch)


# ==========================================================================
# Queue Endpoints
# ==========================================================================

@router.get("/queues/{project}/prs", response_model=List[PRResponse])
async def get_pr_queue(project: str):
    """Get PRs in queue order."""
    pr_service = get_pr_service()
    prs = await pr_service.get_pr_queue(project)
    return [pr_to_response(pr) for pr in prs]


@router.get("/queues/{project}/merges", response_model=List[str])
async def get_merge_queue(project: str):
    """Get branches in merge queue."""
    pr_service = get_pr_service()
    return await pr_service.get_merge_queue(project)


@router.post("/queues/{project}/process-merges")
async def process_merge_queue(project: str):
    """Process pending merges from the queue."""
    pr_service = get_pr_service()
    return await pr_service.process_merge_queue(project)


# ==========================================================================
# Compute Integration Endpoints
# ==========================================================================

@router.get("/compute/{compute_id}/prs", response_model=List[PRResponse])
async def get_compute_prs(compute_id: str):
    """Get all PRs owned by a compute instance."""
    pr_service = get_pr_service()
    prs = await pr_service.get_compute_prs(compute_id)
    return [pr_to_response(pr) for pr in prs]


@router.post("/compute/{compute_id}/cleanup")
async def cleanup_compute(compute_id: str):
    """Clean up when a compute instance is deregistered."""
    pr_service = get_pr_service()
    closed = await pr_service.cleanup_compute(compute_id)

    return {
        "compute_id": compute_id,
        "prs_closed": closed
    }


# ==========================================================================
# SSH Key Management Endpoints
# ==========================================================================

@router.post("/ssh-keys", response_model=SSHKeyResponse, status_code=status.HTTP_201_CREATED)
async def generate_ssh_key(request: GenerateSSHKeyRequest):
    """Generate a new SSH key pair for external repo authentication."""
    service = get_ssh_key_service()

    try:
        result = service.generate_key(description=request.description)
        return SSHKeyResponse(
            key_id=result["key_id"],
            public_key=result["public_key"],
            fingerprint=result["fingerprint"],
            description=result.get("description", ""),
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ssh-keygen not found on this system",
        )
    except Exception as e:
        logger.error(f"Failed to generate SSH key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/ssh-keys", response_model=List[SSHKeyListItem])
async def list_ssh_keys():
    """List all SSH keys (metadata only, no private key material)."""
    service = get_ssh_key_service()
    keys = service.list_keys()
    return [SSHKeyListItem(**k) for k in keys]


@router.get("/ssh-keys/{key_id}", response_model=SSHKeyResponse)
async def get_ssh_key(key_id: str):
    """Get a specific SSH key's public key (for adding as deploy key)."""
    service = get_ssh_key_service()
    result = service.get_key(key_id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SSH key not found: {key_id}",
        )

    return SSHKeyResponse(
        key_id=result["key_id"],
        public_key=result["public_key"],
        fingerprint=result["fingerprint"],
        description=result.get("description", ""),
    )


@router.delete("/ssh-keys/{key_id}", response_model=SSHKeyDeleteResponse)
async def delete_ssh_key(key_id: str):
    """Delete an SSH key pair.

    Returns a warning list of repos that reference this key_id.
    """
    service = get_ssh_key_service()

    if not service.key_exists(key_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SSH key not found: {key_id}",
        )

    # Check for repos referencing this key (best-effort)
    referencing: List[str] = []
    try:
        from services.project_service import get_project_service
        project_service = get_project_service()
        if project_service:
            projects = await project_service.list_projects()
            for project in projects:
                for repo in project.repos:
                    if repo.ssh_key_id == key_id:
                        referencing.append(f"{project.name}/{repo.name}")
    except Exception:
        pass  # Best-effort warning

    deleted = service.delete_key(key_id)
    return SSHKeyDeleteResponse(
        key_id=key_id,
        deleted=deleted,
        referencing_repos=referencing,
    )
