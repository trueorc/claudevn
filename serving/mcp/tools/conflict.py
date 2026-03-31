"""claudevn_notify_conflict tool.

This tool notifies compute instances when their branch has a merge conflict
with the base branch (usually main). It provides detailed guidance on how
to resolve the conflict using git rebase.
"""

import logging
from typing import Optional

from ..models import NotifyConflictInput, ConflictNotification, MCPError
from mcp.tools import emit_tool_error
from services.work_map_service import get_work_map_service
from models.work_map import WorkStatus

logger = logging.getLogger(__name__)


def _generate_rebase_guidance(
    branch: str,
    base_branch: str,
    conflicting_files: list[str]
) -> str:
    """Generate detailed rebase guidance for the compute instance.

    Args:
        branch: The feature branch with conflicts
        base_branch: The branch to rebase onto (usually main)
        conflicting_files: List of files with conflicts

    Returns:
        Detailed step-by-step guidance string
    """
    files_list = "\n".join(f"  - {f}" for f in conflicting_files)

    return f"""Your branch '{branch}' has merge conflicts with '{base_branch}'.

## Conflicting Files
{files_list}

## Resolution Steps

1. **Fetch latest changes:**
   ```
   git fetch origin
   ```

2. **Start interactive rebase:**
   ```
   git rebase origin/{base_branch}
   ```

3. **For each conflicting file:**
   - Open the file and look for conflict markers (<<<<<<<, =======, >>>>>>>)
   - Resolve the conflict by keeping the appropriate changes
   - Stage the resolved file: `git add <filename>`
   - Continue rebase: `git rebase --continue`

4. **If you need to abort:**
   ```
   git rebase --abort
   ```

5. **After successful rebase, force push:**
   ```
   git push --force-with-lease origin {branch}
   ```

## Important Notes
- Use `--force-with-lease` instead of `--force` for safety
- Test your changes after rebase to ensure nothing broke
- If conflicts are complex, consider using `git mergetool`

After pushing the rebased branch, request a new review."""


async def notify_conflict(
    input: NotifyConflictInput
) -> tuple[Optional[ConflictNotification], Optional[MCPError]]:
    """Notify a compute instance of a merge conflict.

    This tool is called when a PR merge fails due to conflicts.
    It updates the work item status and provides detailed guidance
    on how to resolve the conflict.
    """
    logger.warning(
        f"Conflict notification: task={input.task_id} branch={input.branch} "
        f"files={input.conflicting_files}"
    )

    try:
        service = get_work_map_service()

        # Verify work item exists
        work = await service.get_work(input.task_id)
        if not work:
            return None, MCPError(
                code="TASK_NOT_FOUND",
                message=f"Task {input.task_id} not found"
            )

        # Update work status to indicate conflict
        await service.update_status(
            work_id=input.task_id,
            status=WorkStatus.BLOCKED,
        )

        # Generate rebase guidance
        guidance = _generate_rebase_guidance(
            branch=input.branch,
            base_branch=input.base_branch,
            conflicting_files=input.conflicting_files
        )

        return ConflictNotification(
            acknowledged=True,
            task_id=input.task_id,
            branch=input.branch,
            action_required="rebase_and_push",
            conflicting_files=input.conflicting_files,
            guidance=guidance
        ), None

    except RuntimeError as e:
        logger.error(f"Work map service not available: {e}")
        await emit_tool_error(tool_name="notify_conflict", error_code="SERVICE_UNAVAILABLE", error_msg=str(e))
        return None, MCPError(
            code="SERVICE_UNAVAILABLE",
            message="Work map service not initialized"
        )
    except Exception as e:
        logger.error(f"Error notifying conflict: {e}")
        await emit_tool_error(tool_name="notify_conflict", error_code="INTERNAL_ERROR", error_msg=str(e))
        return None, MCPError(
            code="INTERNAL_ERROR",
            message=str(e)
        )
