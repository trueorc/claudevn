"""Service for repository synchronization operations.

Coordinates between project metadata and Git operations to clone,
pull, and push repositories.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import subprocess

from config import get_config
from git.repo_manager import RepoManager
from models.project import (
    RepoConfig, RepoCloneStatus, RepoStatusResponse, RepoSyncResponse
)
from services.project_service import get_project_service

logger = logging.getLogger(__name__)


class RepoSyncService:
    """Service for synchronizing repositories with their origins."""

    def __init__(self, repo_manager: Optional[RepoManager] = None):
        """Initialize repo sync service.

        Args:
            repo_manager: Repository manager instance
        """
        self._repo_manager = repo_manager or RepoManager()
        self._config = get_config()
        self._ssh_keys_path = Path(self._config.git.ssh_keys_path)

    def _get_ssh_key_path(self, ssh_key_id: Optional[str]) -> Optional[str]:
        """Get path to SSH key file.

        Args:
            ssh_key_id: SSH key identifier

        Returns:
            Path to SSH key file or None
        """
        if not ssh_key_id:
            return None

        key_path = self._ssh_keys_path / f"{ssh_key_id}_key"
        if key_path.exists():
            return str(key_path)

        return None

    def _get_repo_local_name(self, project_id: str, repo_id: str) -> str:
        """Generate local repository name.

        Args:
            project_id: Project identifier
            repo_id: Repository identifier

        Returns:
            Local repository name
        """
        # Use a combination to ensure uniqueness
        return f"{project_id}_{repo_id}"

    async def clone_repo(
        self,
        project_id: str,
        repo_id: str
    ) -> RepoSyncResponse:
        """Clone a repository from its configured URL.

        Args:
            project_id: Project identifier
            repo_id: Repository identifier

        Returns:
            Sync response with operation results
        """
        project_service = get_project_service()
        project = await project_service.get_project(project_id)

        if not project:
            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="clone",
                success=False,
                message=f"Project not found: {project_id}"
            )

        # Find the repo config
        repo_config = next(
            (r for r in project.repos if r.repo_id == repo_id),
            None
        )

        if not repo_config:
            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="clone",
                success=False,
                message=f"Repository not found: {repo_id}"
            )

        # Generate local repo name
        local_name = self._get_repo_local_name(project_id, repo_id)

        # Check if already cloned
        if self._repo_manager.repo_exists(local_name):
            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="clone",
                success=False,
                message=f"Repository already cloned: {local_name}"
            )

        # Get SSH key path if configured
        ssh_key_path = self._get_ssh_key_path(repo_config.ssh_key_id)

        try:
            # Clone the repository
            repo_path = self._repo_manager.clone_from_url(
                project=local_name,
                url=repo_config.url,
                ssh_key_path=ssh_key_path,
                default_branch=repo_config.default_branch
            )

            # Update repo config with local path
            repo_config.path = str(repo_path)
            repo_config.metadata["clone_status"] = RepoCloneStatus.CLONED.value
            repo_config.metadata["last_sync"] = datetime.now(timezone.utc).isoformat()

            # Save updated project
            project.updated_at = datetime.now(timezone.utc)
            await project_service._save_project(project)

            logger.info(f"Cloned repo {repo_id} to {repo_path}")

            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="clone",
                success=True,
                message=f"Repository cloned successfully to {repo_path}"
            )

        except FileExistsError as e:
            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="clone",
                success=False,
                message=str(e)
            )
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            logger.error(f"Failed to clone repo {repo_id}: {error_msg}")

            # Update metadata with error
            repo_config.metadata["clone_status"] = RepoCloneStatus.ERROR.value
            repo_config.metadata["clone_error"] = error_msg
            await project_service._save_project(project)

            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="clone",
                success=False,
                message=f"Clone failed: {error_msg}",
                output=error_msg
            )

    async def pull_repo(
        self,
        project_id: str,
        repo_id: str
    ) -> RepoSyncResponse:
        """Pull latest changes from origin.

        Args:
            project_id: Project identifier
            repo_id: Repository identifier

        Returns:
            Sync response with operation results
        """
        project_service = get_project_service()
        project = await project_service.get_project(project_id)

        if not project:
            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="pull",
                success=False,
                message=f"Project not found: {project_id}"
            )

        repo_config = next(
            (r for r in project.repos if r.repo_id == repo_id),
            None
        )

        if not repo_config:
            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="pull",
                success=False,
                message=f"Repository not found: {repo_id}"
            )

        local_name = self._get_repo_local_name(project_id, repo_id)

        if not self._repo_manager.repo_exists(local_name):
            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="pull",
                success=False,
                message="Repository not cloned. Clone it first."
            )

        ssh_key_path = self._get_ssh_key_path(repo_config.ssh_key_id)

        try:
            result = self._repo_manager.pull_from_origin(
                project=local_name,
                ssh_key_path=ssh_key_path
            )

            # Update last sync time
            repo_config.metadata["last_sync"] = datetime.now(timezone.utc).isoformat()
            project.updated_at = datetime.now(timezone.utc)
            await project_service._save_project(project)

            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="pull",
                success=True,
                message="Pull completed successfully",
                output=result.get("output")
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="pull",
                success=False,
                message=f"Pull failed: {error_msg}",
                output=error_msg
            )

    async def push_to_origin(
        self,
        project_id: str,
        repo_id: str,
        branch: str,
        force: bool = False
    ) -> RepoSyncResponse:
        """Push a branch to origin.

        Args:
            project_id: Project identifier
            repo_id: Repository identifier
            branch: Branch name to push
            force: Force push (use with caution)

        Returns:
            Sync response with operation results
        """
        project_service = get_project_service()
        project = await project_service.get_project(project_id)

        if not project:
            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="push",
                success=False,
                message=f"Project not found: {project_id}"
            )

        repo_config = next(
            (r for r in project.repos if r.repo_id == repo_id),
            None
        )

        if not repo_config:
            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="push",
                success=False,
                message=f"Repository not found: {repo_id}"
            )

        local_name = self._get_repo_local_name(project_id, repo_id)

        if not self._repo_manager.repo_exists(local_name):
            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="push",
                success=False,
                message="Repository not cloned. Clone it first."
            )

        ssh_key_path = self._get_ssh_key_path(repo_config.ssh_key_id)

        try:
            result = self._repo_manager.push_to_origin(
                project=local_name,
                branch=branch,
                ssh_key_path=ssh_key_path,
                force=force
            )

            # Update last sync time
            repo_config.metadata["last_push"] = datetime.now(timezone.utc).isoformat()
            repo_config.metadata["last_pushed_branch"] = branch
            project.updated_at = datetime.now(timezone.utc)
            await project_service._save_project(project)

            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="push",
                success=True,
                message=f"Pushed {branch} to origin successfully",
                output=result.get("output")
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            return RepoSyncResponse(
                repo_id=repo_id,
                project_id=project_id,
                operation="push",
                success=False,
                message=f"Push failed: {error_msg}",
                output=error_msg
            )

    async def get_repo_status(
        self,
        project_id: str,
        repo_id: str
    ) -> Optional[RepoStatusResponse]:
        """Get status of a repository.

        Args:
            project_id: Project identifier
            repo_id: Repository identifier

        Returns:
            Repository status or None if not found
        """
        project_service = get_project_service()
        project = await project_service.get_project(project_id)

        if not project:
            return None

        repo_config = next(
            (r for r in project.repos if r.repo_id == repo_id),
            None
        )

        if not repo_config:
            return None

        local_name = self._get_repo_local_name(project_id, repo_id)

        # Check if cloned
        if not self._repo_manager.repo_exists(local_name):
            return RepoStatusResponse(
                repo_id=repo_id,
                name=repo_config.name,
                url=repo_config.url,
                clone_status=RepoCloneStatus.NOT_CLONED
            )

        # Get detailed status from repo manager
        status = self._repo_manager.get_repo_status(local_name)

        if not status:
            return RepoStatusResponse(
                repo_id=repo_id,
                name=repo_config.name,
                url=repo_config.url,
                clone_status=RepoCloneStatus.ERROR,
                error_message="Failed to get repository status"
            )

        # Parse last sync from metadata
        last_sync = None
        if "last_sync" in repo_config.metadata:
            try:
                last_sync = datetime.fromisoformat(repo_config.metadata["last_sync"])
            except (ValueError, TypeError):
                pass

        return RepoStatusResponse(
            repo_id=repo_id,
            name=repo_config.name,
            url=repo_config.url,
            clone_status=RepoCloneStatus.CLONED,
            local_path=status.get("path"),
            origin_url=status.get("origin_url"),
            default_branch=status.get("default_branch"),
            branches=status.get("branches", []),
            branch_count=status.get("branch_count", 0),
            is_mirror=status.get("is_mirror", False),
            last_sync=last_sync
        )


# Singleton instance
_repo_sync_service: Optional[RepoSyncService] = None


def get_repo_sync_service() -> RepoSyncService:
    """Get the global repo sync service instance."""
    global _repo_sync_service
    if _repo_sync_service is None:
        _repo_sync_service = RepoSyncService()
    return _repo_sync_service
