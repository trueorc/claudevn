"""Conflict resolution handler for merge_conflict events.

Handles merge conflict events from Serving by orchestrating
the conflict resolution process in the running Claude Code instance.
"""

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class ConflictResolutionContext:
    """Context for conflict resolution."""
    issue_id: str
    branch: str
    conflicting_files: list[str]
    main_head: str
    message: str
    task_id: Optional[str] = None


@dataclass
class ConflictResolutionResult:
    """Result of conflict resolution attempt."""
    success: bool
    message: str
    resolved_files: list[str]
    remaining_conflicts: list[str]


@dataclass
class InstructionInjectionResult:
    """Result of instruction injection attempt."""
    success: bool
    message: str
    method: str = "none"  # "stdin", "automatic", "failed"


class ConflictResolutionHandler:
    """Handles merge conflict resolution for Compute Infra.

    When Serving sends a merge_conflict event, this handler:
    1. Prepares conflict resolution context
    2. Injects instructions into the running Claude Code instance
    3. Monitors the resolution process
    4. Reports completion back to Serving via MCP

    The handler can operate in two modes:
    - Instruction injection: Sends conflict context to Claude Code
    - Direct resolution: Executes git commands directly (fallback)
    """

    def __init__(
        self,
        workspace_path: str,
        mcp_client: Optional[Any] = None,
        progress_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None
    ):
        """Initialize the conflict resolution handler.

        Args:
            workspace_path: Path to the git workspace
            mcp_client: Optional MCP client for reporting progress
            progress_callback: Optional callback for progress updates
        """
        self.workspace_path = workspace_path
        self.mcp_client = mcp_client
        self.progress_callback = progress_callback
        self._current_context: Optional[ConflictResolutionContext] = None

    async def handle_merge_conflict(
        self,
        event_type: str,
        data: dict[str, Any]
    ) -> InstructionInjectionResult:
        """Handle a merge_conflict event from Serving.

        This is the main entry point called by the SSE event client.
        It attempts to inject conflict resolution instructions into the
        running Claude Code instance, with fallback to automatic resolution.

        Args:
            event_type: Event type (should be "merge_conflict")
            data: Event data containing conflict details

        Returns:
            Result of the instruction injection attempt
        """
        logger.warning(
            f"Received merge_conflict event: branch={data.get('branch')} "
            f"files={data.get('conflicting_files')}"
        )

        context = ConflictResolutionContext(
            issue_id=data.get("issue_id", ""),
            branch=data.get("branch", ""),
            conflicting_files=data.get("conflicting_files", []),
            main_head=data.get("main_head", ""),
            message=data.get("message", ""),
            task_id=data.get("task_id")
        )

        self._current_context = context

        # Generate conflict resolution instructions
        instructions = self._generate_resolution_instructions(context)

        # Notify that we're starting conflict resolution
        if self.progress_callback:
            await self.progress_callback("conflict_resolution_started", {
                "branch": context.branch,
                "conflicting_files": context.conflicting_files
            })

        # Attempt to inject instructions into the running Claude Code instance
        injection_result = await self._inject_instructions(context.task_id, instructions)

        if injection_result.success:
            logger.info(
                f"Successfully injected conflict resolution instructions "
                f"via {injection_result.method}"
            )
        else:
            logger.warning(
                f"Failed to inject instructions: {injection_result.message}. "
                f"Attempting automatic resolution as fallback."
            )
            # Fallback to automatic resolution
            auto_result = await self.attempt_automatic_resolution(context)
            if auto_result.success:
                return InstructionInjectionResult(
                    success=True,
                    message="Automatic resolution succeeded as fallback",
                    method="automatic"
                )
            else:
                logger.error(
                    f"Automatic resolution also failed: {auto_result.message}"
                )
                return InstructionInjectionResult(
                    success=False,
                    message=f"Injection failed ({injection_result.message}), "
                            f"automatic resolution also failed ({auto_result.message})",
                    method="failed"
                )

        return injection_result

    async def _inject_instructions(
        self,
        task_id: Optional[str],
        instructions: str
    ) -> InstructionInjectionResult:
        """Inject conflict resolution instructions into Claude Code.

        Attempts to write instructions to the Claude Code process stdin.
        Requires access to the ClaudeCodeSpawner to get the process handle.

        Args:
            task_id: Task ID to find the associated process
            instructions: Instructions to inject

        Returns:
            Result of the injection attempt
        """
        if not task_id:
            return InstructionInjectionResult(
                success=False,
                message="No task_id provided in conflict event",
                method="none"
            )

        # Import here to avoid circular dependency
        from services.claude_code_spawner import get_claude_code_spawner

        spawner = get_claude_code_spawner()
        if not spawner:
            return InstructionInjectionResult(
                success=False,
                message="No ClaudeCodeSpawner available",
                method="none"
            )

        # Get the process for this task
        process = spawner._processes.get(task_id)
        if not process:
            return InstructionInjectionResult(
                success=False,
                message=f"No process found for task {task_id}",
                method="none"
            )

        if not process.stdin:
            return InstructionInjectionResult(
                success=False,
                message=f"Process for task {task_id} has no stdin",
                method="none"
            )

        try:
            # Format the instructions as a user message
            formatted_instructions = (
                f"\n\n--- URGENT: Merge Conflict Detected ---\n\n"
                f"{instructions}\n"
                f"--- End of Conflict Resolution Instructions ---\n\n"
            )

            process.stdin.write(formatted_instructions.encode())
            await process.stdin.drain()

            logger.info(f"Injected instructions into process for task {task_id}")

            return InstructionInjectionResult(
                success=True,
                message=f"Instructions injected via stdin for task {task_id}",
                method="stdin"
            )

        except Exception as e:
            logger.error(f"Failed to inject instructions: {e}")
            return InstructionInjectionResult(
                success=False,
                message=str(e),
                method="none"
            )

    def _generate_resolution_instructions(
        self,
        context: ConflictResolutionContext
    ) -> str:
        """Generate detailed instructions for resolving conflicts.

        Args:
            context: Conflict resolution context

        Returns:
            Markdown-formatted instructions
        """
        files_list = "\n".join(f"  - {f}" for f in context.conflicting_files)

        return f"""## Merge Conflict Resolution Required

Your branch `{context.branch}` has conflicts with `main` that must be resolved.

### Conflicting Files
{files_list}

### Resolution Steps

1. **Fetch latest main:**
   ```bash
   git fetch origin main
   ```

2. **Rebase onto main:**
   ```bash
   git rebase origin/main
   ```

3. **For each conflicting file:**
   - Open the file and find conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
   - Resolve by keeping the correct changes
   - Remove conflict markers
   - Stage the file: `git add <filename>`
   - Continue: `git rebase --continue`

4. **Force push the rebased branch:**
   ```bash
   git push --force-with-lease origin {context.branch}
   ```

5. **Report completion:**
   Call `claudevn_report_progress` with status="conflicts_resolved"

### Important
- Use `--force-with-lease` for safety
- Test changes after rebase
- If stuck, use `git rebase --abort` to start over

### Message from Serving
{context.message}
"""

    async def attempt_automatic_resolution(
        self,
        context: Optional[ConflictResolutionContext] = None
    ) -> ConflictResolutionResult:
        """Attempt to automatically resolve conflicts using git.

        This is a fallback mechanism that tries to resolve conflicts
        automatically. It's used when Claude Code isn't available
        or for simple conflict cases.

        Args:
            context: Conflict context (uses current if not provided)

        Returns:
            Result of the resolution attempt
        """
        ctx = context or self._current_context
        if not ctx:
            return ConflictResolutionResult(
                success=False,
                message="No conflict context available",
                resolved_files=[],
                remaining_conflicts=[]
            )

        logger.info(f"Attempting automatic conflict resolution for {ctx.branch}")

        try:
            # Fetch latest main
            result = subprocess.run(
                ["git", "-C", self.workspace_path, "fetch", "origin", "main"],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise Exception(f"git fetch failed: {result.stderr}")

            # Try rebase
            result = subprocess.run(
                ["git", "-C", self.workspace_path, "rebase", "origin/main"],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                # Rebase succeeded - push changes
                push_result = subprocess.run(
                    [
                        "git", "-C", self.workspace_path,
                        "push", "--force-with-lease", "origin", ctx.branch
                    ],
                    capture_output=True,
                    text=True
                )

                if push_result.returncode == 0:
                    return ConflictResolutionResult(
                        success=True,
                        message="Conflicts resolved automatically",
                        resolved_files=ctx.conflicting_files,
                        remaining_conflicts=[]
                    )
                else:
                    # Rebase succeeded but push failed
                    return ConflictResolutionResult(
                        success=False,
                        message=f"Push failed: {push_result.stderr}",
                        resolved_files=ctx.conflicting_files,
                        remaining_conflicts=[]
                    )
            else:
                # Rebase failed - abort and report
                subprocess.run(
                    ["git", "-C", self.workspace_path, "rebase", "--abort"],
                    capture_output=True
                )

                # Determine remaining conflicts
                return ConflictResolutionResult(
                    success=False,
                    message="Automatic resolution failed - manual intervention required",
                    resolved_files=[],
                    remaining_conflicts=ctx.conflicting_files
                )

        except Exception as e:
            logger.error(f"Error during automatic resolution: {e}")
            return ConflictResolutionResult(
                success=False,
                message=str(e),
                resolved_files=[],
                remaining_conflicts=ctx.conflicting_files
            )

    async def report_resolution_complete(
        self,
        task_id: str,
        success: bool = True,
        message: str = "Conflicts resolved"
    ) -> bool:
        """Report conflict resolution completion to Serving.

        Args:
            task_id: Task ID to report progress for
            success: Whether resolution was successful
            message: Status message

        Returns:
            True if report was sent successfully
        """
        if self.mcp_client:
            try:
                # Use MCP client to report progress
                status = "in_progress" if success else "blocked"
                await self.mcp_client.report_progress(
                    task_id=task_id,
                    status=status,
                    message=message
                )
                logger.info(f"Reported conflict resolution: {status} - {message}")
                return True
            except Exception as e:
                logger.error(f"Failed to report resolution: {e}")
                return False
        else:
            logger.warning("No MCP client available for reporting")
            return False

    def get_current_context(self) -> Optional[ConflictResolutionContext]:
        """Get the current conflict resolution context."""
        return self._current_context

    def clear_context(self) -> None:
        """Clear the current conflict resolution context."""
        self._current_context = None


# Global instance
_conflict_handler: Optional[ConflictResolutionHandler] = None


def get_conflict_handler() -> Optional[ConflictResolutionHandler]:
    """Get the global conflict resolution handler."""
    return _conflict_handler


def set_conflict_handler(handler: ConflictResolutionHandler) -> None:
    """Set the global conflict resolution handler."""
    global _conflict_handler
    _conflict_handler = handler


def initialize_conflict_handler(
    workspace_path: str,
    mcp_client: Optional[Any] = None,
    progress_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None
) -> ConflictResolutionHandler:
    """Initialize the global conflict resolution handler.

    Args:
        workspace_path: Path to the git workspace
        mcp_client: Optional MCP client for reporting
        progress_callback: Optional progress callback

    Returns:
        The initialized handler
    """
    handler = ConflictResolutionHandler(
        workspace_path=workspace_path,
        mcp_client=mcp_client,
        progress_callback=progress_callback
    )
    set_conflict_handler(handler)
    return handler
