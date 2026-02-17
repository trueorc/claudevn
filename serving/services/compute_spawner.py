"""Compute Spawner Service (Serving-side).

This is the SERVING-SIDE spawner for the CENTRALIZED deployment model.
It runs within the Serving component and spawns Claude Code directly.

Use this spawner for:
- Development and testing (single-host setup)
- Simple deployments without container infrastructure
- Direct API-driven spawning via POST /api/v1/spawner/spawn

For the DISTRIBUTED deployment model (production, scale-out), use the
compute-side spawner at compute/services/claude_code_spawner.py instead.

See docs/design/adr/005-dual-spawner-architecture.md for architectural details.

Responsibilities:
- Spawns Claude Code CLI processes with MCP configuration
- Composes skills from marketplace into CLAUDE.md files
- Issues and manages API keys for instances
- Tracks instance state and metrics
- Handles graceful shutdown
"""

import asyncio
import json
import logging
import os
import shutil
import signal
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.compute_spawner import (
    SpawnRequest, SpawnResponse, SpawnedCompute, ComputeState,
    ComputeListResponse, StopRequest, ComputeMetrics
)
from git.repo_manager import RepoManager

logger = logging.getLogger(__name__)


class ComputeSpawner:
    """Service for spawning and managing Claude Code compute instances."""

    def __init__(
        self,
        serving_url: str = "http://localhost:8002",
        workspaces_path: str = "./data/workspaces",
        claude_path: Optional[str] = None
    ):
        """Initialize the compute spawner.

        Args:
            serving_url: URL of the serving component
            workspaces_path: Directory for compute workspaces
            claude_path: Path to claude CLI (auto-detected if not provided)
        """
        self.serving_url = serving_url
        self.workspaces_path = Path(workspaces_path)
        self.claude_path = claude_path or self._find_claude_cli()
        self._repo_manager = RepoManager()

        self._instances: Dict[str, SpawnedCompute] = {}
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        self._monitor_tasks: Dict[str, asyncio.Task] = {}

        # Ensure workspaces directory exists
        self.workspaces_path.mkdir(parents=True, exist_ok=True)

        self._initialized = False

    def _get_mcp_server_script(self) -> str:
        """Get the path to the MCP server script.

        The MCP server is a Python script that implements JSON-RPC 2.0 over stdio
        and bridges to the serving HTTP API. Claude Code uses this for proper
        MCP protocol compliance.

        Returns:
            Absolute path to the MCP server script
        """
        # The script is in the serving/mcp directory relative to this file
        this_file = Path(__file__).resolve()
        serving_dir = this_file.parent.parent
        mcp_server = serving_dir / "mcp" / "stdio_server.py"

        if not mcp_server.exists():
            raise RuntimeError(f"MCP server script not found at {mcp_server}")

        return str(mcp_server)

    def _find_claude_cli(self) -> str:
        """Find the claude CLI executable."""
        # Check common locations
        locations = [
            "/usr/local/bin/claude",
            "/usr/bin/claude",
            os.path.expanduser("~/.local/bin/claude"),
            shutil.which("claude")
        ]

        for loc in locations:
            if loc and os.path.isfile(loc):
                return loc

        # Default to PATH lookup
        return "claude"

    async def _setup_worktrees(
        self,
        workspace: Path,
        repo_url: str,
        base_branch: str,
        compute_id: str,
        ssh_key_path: Optional[str] = None
    ) -> str:
        """Set up Git worktrees for a compute instance.

        Creates the standard worktree structure:
        - /workspace/repo/   - Main clone
        - /workspace/main/   - Worktree tracking origin/{base_branch} (read-only reference)
        - /workspace/active/ - Worktree for feature branch work

        Args:
            workspace: Compute workspace directory
            repo_url: Repository URL to clone
            base_branch: Base branch name (typically "main")
            compute_id: Compute instance ID for branch naming
            ssh_key_path: Optional path to SSH key for authentication

        Returns:
            Path to the active worktree as string

        Raises:
            subprocess.CalledProcessError: If git operations fail
        """
        repo_path = workspace / "repo"
        main_worktree = workspace / "main"
        active_worktree = workspace / "active"

        # Step 1: Clone the repository as a regular (non-bare) clone
        logger.info(f"Cloning repository to {repo_path}")
        self._repo_manager.clone_regular(
            url=repo_url,
            dest_path=repo_path,
            ssh_key_path=ssh_key_path,
            branch=base_branch
        )

        # Step 2: Create main worktree tracking origin/{base_branch}
        # This serves as a read-only reference to the main branch
        logger.info(f"Creating main worktree at {main_worktree}")
        self._repo_manager.add_worktree(
            repo_path=repo_path,
            worktree_path=main_worktree,
            branch=base_branch
        )

        # Step 3: Create active worktree with a placeholder branch
        # Compute can later switch to feature branches in this worktree
        placeholder_branch = f"work/{compute_id}/placeholder"
        logger.info(f"Creating active worktree at {active_worktree}")
        self._repo_manager.add_worktree(
            repo_path=repo_path,
            worktree_path=active_worktree,
            branch=placeholder_branch,
            create_branch=True,
            track_remote=f"origin/{base_branch}"
        )

        logger.info(f"Worktree setup complete for {compute_id}")
        return str(active_worktree)

    async def initialize(self) -> None:
        """Initialize the spawner service."""
        logger.info(f"Claude CLI: {self.claude_path}")
        logger.info(f"Workspaces: {self.workspaces_path}")
        self._initialized = True
        logger.info("Compute spawner initialized")

    async def spawn(self, request: SpawnRequest) -> SpawnResponse:
        """Spawn a new compute instance.

        Args:
            request: Spawn configuration

        Returns:
            Spawn response with instance details
        """
        # Generate compute ID
        compute_id = request.compute_id or f"compute_{uuid.uuid4().hex[:8]}"
        name = request.name or f"Compute {compute_id}"

        logger.info(f"Spawning compute instance: {compute_id}")

        # Generate API key for this instance
        from mcp.auth import generate_api_key, register_compute_key
        api_key = generate_api_key()
        await register_compute_key(compute_id, api_key)

        # Create workspace directory
        workspace = self.workspaces_path / compute_id
        workspace.mkdir(parents=True, exist_ok=True)

        # Create CLAUDE.md from composed skills
        claude_md = await self._compose_skills(request.skills, compute_id)
        claude_md_path = workspace / "CLAUDE.md"
        claude_md_path.write_text(claude_md)

        # Create MCP configuration
        mcp_config = self._create_mcp_config(compute_id, api_key)
        mcp_config_path = workspace / "mcp.json"
        mcp_config_path.write_text(json.dumps(mcp_config, indent=2))

        # Set up Git worktrees if repo_url is provided
        worktree_active = None
        if request.repo_url:
            try:
                worktree_active = await self._setup_worktrees(
                    workspace=workspace,
                    repo_url=request.repo_url,
                    base_branch=request.base_branch,
                    compute_id=compute_id
                )
                logger.info(f"Git worktrees set up for {compute_id}")
            except Exception as e:
                logger.error(f"Failed to set up worktrees for {compute_id}: {e}")
                raise

        # Create instance record with labels and tools for work matching
        instance = SpawnedCompute(
            compute_id=compute_id,
            name=name,
            state=ComputeState.PENDING,
            skills=request.skills,
            capabilities=request.capabilities,
            labels=request.labels,
            tools_available=request.tools_available,
            project_id=request.project_id,
            serving_url=self.serving_url,
            api_key=api_key,
            workspace_path=str(workspace),
            worktree_active=worktree_active
        )

        self._instances[compute_id] = instance

        # Start the Claude CLI process
        try:
            await self._start_process(instance, request)
        except Exception as e:
            instance.state = ComputeState.FAILED
            logger.error(f"Failed to start compute {compute_id}: {e}")
            raise

        # Get initial work if requested
        initial_work = None
        if request.work_id:
            initial_work = await self._assign_initial_work(compute_id, request.work_id)
        elif request.project_id:
            initial_work = await self._get_next_work(compute_id, request.capabilities)

        return SpawnResponse(
            compute_id=compute_id,
            state=instance.state,
            api_key=api_key,
            serving_url=self.serving_url,
            workspace_path=str(workspace),
            worktree_active=worktree_active,
            initial_work=initial_work
        )

    async def _compose_skills(self, skill_ids: List[str], compute_id: str) -> str:
        """Compose multiple skills into a single CLAUDE.md.

        Args:
            skill_ids: List of skill IDs to compose
            compute_id: Compute instance ID

        Returns:
            Composed CLAUDE.md content
        """
        from services.marketplace_client import get_marketplace_client

        if not skill_ids:
            return self._default_claude_md(compute_id)

        try:
            client = get_marketplace_client()

            skills = []
            for skill_id in skill_ids:
                skill = await client.get_skill(skill_id)
                if skill:
                    skills.append(skill)

            if not skills:
                return self._default_claude_md(compute_id)

            # Build composed CLAUDE.md
            sections = [
                f"# ClaudeVN Compute Instance: {compute_id}",
                "",
                "This instance has the following composed skills:",
                "",
            ]

            # List skills
            for skill in skills:
                sections.append(f"- **{skill['name']}**: {skill.get('description', '')}")

            sections.append("")
            sections.append("---")
            sections.append("")

            # Add each skill's instructions
            for skill in skills:
                sections.append(f"## {skill['name']}")
                sections.append("")
                instructions = skill.get('instructions', '')
                if instructions:
                    sections.append(instructions)
                sections.append("")

            # Add MCP tools section
            sections.extend([
                "---",
                "",
                "## MCP Tools Available",
                "",
                "Use these tools to communicate with ClaudeVN Serving:",
                "",
                "- `claudevn_report_progress` - Report progress on current work",
                "- `claudevn_signal_blocker` - Signal when blocked",
                "- `claudevn_get_context` - Get context for your assigned work",
                "- `claudevn_request_review` - Submit work for review",
                "- `claudevn_complete_task` - Mark work as complete",
                "- `claudevn_get_persona` - Get additional skill definitions",
                "",
                "Note: Your task assignment was provided when you started. You do not need to request it.",
                "",
            ])

            return "\n".join(sections)

        except Exception as e:
            logger.error(f"Error composing skills: {e}")
            return self._default_claude_md(compute_id)

    def _default_claude_md(self, compute_id: str) -> str:
        """Generate default CLAUDE.md content."""
        return f"""# ClaudeVN Compute Instance: {compute_id}

You are a ClaudeVN compute instance. Your role is to:

1. Execute assigned tasks
2. Report progress regularly
3. Submit completed work for review

## Getting Started

Your task assignment was provided when you started. To begin:

1. Review the task details provided above
2. Use `claudevn_get_context` if you need more context
3. Execute the work
4. Use `claudevn_report_progress` to update status
5. Use `claudevn_complete_task` when done

## MCP Tools

- `claudevn_report_progress` - Report progress
- `claudevn_signal_blocker` - Signal blockers
- `claudevn_get_context` - Get task context
- `claudevn_request_review` - Request review
- `claudevn_complete_task` - Complete task
- `claudevn_get_persona` - Get skill definitions

Note: Your task assignment was provided when you started. You do not need to request it.
"""

    def _create_mcp_config(self, compute_id: str, api_key: str) -> Dict[str, Any]:
        """Create MCP configuration for Claude CLI.

        This configures the MCP server that Claude Code will use to communicate
        with ClaudeVN. The server implements JSON-RPC 2.0 over stdio and bridges
        to the serving component's HTTP API.

        Args:
            compute_id: Compute instance ID
            api_key: API key for authentication

        Returns:
            MCP configuration dict with proper MCP server
        """
        # Get the full path to the MCP server script
        mcp_server_script = self._get_mcp_server_script()

        # The MCP server reads JSON-RPC from stdin, writes to stdout
        # and bridges to the serving HTTP API
        return {
            "mcpServers": {
                "claudevn": {
                    "command": "python",
                    "args": [
                        mcp_server_script,
                        "--serving-url", self.serving_url
                    ],
                    "env": {
                        "CLAUDEVN_COMPUTE_ID": compute_id,
                        "CLAUDEVN_API_KEY": api_key
                    }
                }
            }
        }

    async def _start_process(self, instance: SpawnedCompute, request: SpawnRequest) -> None:
        """Start the Claude CLI process.

        Args:
            instance: Compute instance record
            request: Original spawn request
        """
        instance.state = ComputeState.STARTING

        workspace = Path(instance.workspace_path)

        # Prepare environment
        env = os.environ.copy()
        env["CLAUDEVN_COMPUTE_ID"] = instance.compute_id
        env["CLAUDEVN_SERVING_URL"] = self.serving_url
        env["CLAUDEVN_API_KEY"] = instance.api_key

        # Pass work context if available
        if request.work_id:
            env["CLAUDEVN_WORK_ID"] = request.work_id
        if request.project_id:
            env["CLAUDEVN_PROJECT_ID"] = request.project_id

        # Build command
        cmd = [
            self.claude_path,
            "--dangerously-skip-permissions",  # Pre-approved for automation
            "-p", str(workspace / "CLAUDE.md"),  # Use our CLAUDE.md
        ]

        # Add initial prompt to start work
        initial_prompt = "Begin work on your assigned task. Your assignment details are in CLAUDE.md."

        logger.info(f"Starting Claude CLI: {' '.join(cmd)}")

        try:
            # Start process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace),
                env=env
            )

            self._processes[instance.compute_id] = process
            instance.pid = process.pid
            instance.started_at = datetime.now(timezone.utc)
            instance.state = ComputeState.RUNNING

            # Send initial prompt
            if process.stdin:
                process.stdin.write(f"{initial_prompt}\n".encode())
                await process.stdin.drain()

            # Start monitoring task
            self._monitor_tasks[instance.compute_id] = asyncio.create_task(
                self._monitor_process(instance)
            )

            logger.info(f"Compute {instance.compute_id} started (PID: {process.pid})")

        except Exception as e:
            instance.state = ComputeState.FAILED
            logger.error(f"Failed to start process: {e}")
            raise

    async def _monitor_process(self, instance: SpawnedCompute) -> None:
        """Monitor a compute process for completion.

        Args:
            instance: Compute instance to monitor
        """
        compute_id = instance.compute_id
        process = self._processes.get(compute_id)

        if not process:
            return

        try:
            # Wait for process to complete
            returncode = await process.wait()

            instance.stopped_at = datetime.now(timezone.utc)

            if returncode == 0:
                instance.state = ComputeState.STOPPED
                logger.info(f"Compute {compute_id} exited normally")
            else:
                instance.state = ComputeState.FAILED
                logger.warning(f"Compute {compute_id} exited with code {returncode}")

        except asyncio.CancelledError:
            logger.info(f"Monitor for {compute_id} cancelled")
        except Exception as e:
            logger.error(f"Error monitoring {compute_id}: {e}")
            instance.state = ComputeState.FAILED

    async def _assign_initial_work(
        self,
        compute_id: str,
        work_id: str
    ) -> Optional[Dict[str, Any]]:
        """Assign specific work to a compute instance.

        Args:
            compute_id: Compute instance ID
            work_id: Work ID to assign

        Returns:
            Work assignment dict
        """
        from services.work_map_service import get_work_map_service

        try:
            service = get_work_map_service()
            instance = self._instances.get(compute_id)

            if not instance:
                return None

            assignment = await service.assign_work(
                work_id=work_id,
                compute_id=compute_id,
                skills=instance.skills
            )

            if assignment:
                instance.current_work.append(work_id)
                return assignment.model_dump()

        except Exception as e:
            logger.error(f"Error assigning work: {e}")

        return None

    async def _get_next_work(
        self,
        compute_id: str,
        capabilities: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Get next available work for a compute instance.

        Args:
            compute_id: Compute instance ID
            capabilities: Capability tags

        Returns:
            Work assignment dict
        """
        from services.work_map_service import get_work_map_service

        try:
            service = get_work_map_service()
            assignment = await service.get_next_assignment(compute_id, capabilities)

            if assignment:
                instance = self._instances.get(compute_id)
                if instance:
                    instance.current_work.append(assignment.work_id)
                return assignment.model_dump()

        except Exception as e:
            logger.error(f"Error getting next work: {e}")

        return None

    def _cleanup_workspace(self, instance: SpawnedCompute) -> None:
        """Clean up worktrees and workspace directory for a compute instance.

        Args:
            instance: The compute instance to clean up
        """
        if not instance.workspace_path:
            return

        workspace = Path(instance.workspace_path)
        repo_path = workspace / "repo"

        # Remove worktrees first (so git metadata is cleaned up properly)
        if repo_path.exists():
            # Remove active worktree
            active_worktree = workspace / "active"
            if active_worktree.exists():
                try:
                    self._repo_manager.remove_worktree(repo_path, active_worktree, force=True)
                    logger.debug(f"Removed active worktree: {active_worktree}")
                except Exception as e:
                    logger.warning(f"Failed to remove active worktree {active_worktree}: {e}")

            # Remove main worktree
            main_worktree = workspace / "main"
            if main_worktree.exists():
                try:
                    self._repo_manager.remove_worktree(repo_path, main_worktree, force=True)
                    logger.debug(f"Removed main worktree: {main_worktree}")
                except Exception as e:
                    logger.warning(f"Failed to remove main worktree {main_worktree}: {e}")

            # Prune any stale worktree references
            try:
                self._repo_manager.prune_worktrees(repo_path)
            except Exception as e:
                logger.warning(f"Failed to prune worktrees: {e}")

        # Remove entire workspace directory
        if workspace.exists():
            try:
                shutil.rmtree(workspace)
                logger.info(f"Cleaned up workspace: {workspace}")
            except Exception as e:
                logger.warning(f"Failed to remove workspace {workspace}: {e}")

    async def stop(self, request: StopRequest) -> bool:
        """Stop a compute instance.

        Args:
            request: Stop request

        Returns:
            True if stopped successfully
        """
        compute_id = request.compute_id
        instance = self._instances.get(compute_id)

        if not instance:
            return False

        if instance.state in [ComputeState.STOPPED, ComputeState.FAILED]:
            return True

        instance.state = ComputeState.STOPPING

        process = self._processes.get(compute_id)
        if not process:
            # Clean up workspace even if process wasn't tracked
            self._cleanup_workspace(instance)
            instance.state = ComputeState.STOPPED
            return True

        try:
            # Try graceful stop first
            process.send_signal(signal.SIGTERM)

            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=request.timeout
                )
            except asyncio.TimeoutError:
                if request.force:
                    logger.warning(f"Force killing compute {compute_id}")
                    process.kill()
                    await process.wait()
                else:
                    logger.warning(f"Timeout stopping compute {compute_id}")
                    return False

            instance.stopped_at = datetime.now(timezone.utc)
            instance.state = ComputeState.STOPPED

            # Cancel monitor task
            if compute_id in self._monitor_tasks:
                self._monitor_tasks[compute_id].cancel()

            # Revoke API key
            from mcp.auth import revoke_compute_key
            await revoke_compute_key(compute_id)

            # Clean up worktrees and workspace
            self._cleanup_workspace(instance)

            logger.info(f"Compute {compute_id} stopped")
            return True

        except Exception as e:
            logger.error(f"Error stopping compute {compute_id}: {e}")
            instance.state = ComputeState.FAILED
            return False

    async def get_instance(self, compute_id: str) -> Optional[SpawnedCompute]:
        """Get a compute instance by ID.

        Args:
            compute_id: Compute instance ID

        Returns:
            Instance if found
        """
        return self._instances.get(compute_id)

    async def list_instances(
        self,
        state: Optional[ComputeState] = None
    ) -> ComputeListResponse:
        """List compute instances.

        Args:
            state: Optional state filter

        Returns:
            List of instances with stats
        """
        instances = list(self._instances.values())

        if state:
            instances = [i for i in instances if i.state == state]

        by_state = {}
        for i in self._instances.values():
            by_state[i.state.value] = by_state.get(i.state.value, 0) + 1

        return ComputeListResponse(
            instances=instances,
            total=len(self._instances),
            by_state=by_state
        )

    async def get_metrics(self, compute_id: str) -> Optional[ComputeMetrics]:
        """Get metrics for a compute instance.

        Args:
            compute_id: Compute instance ID

        Returns:
            Metrics if found
        """
        instance = self._instances.get(compute_id)
        if not instance:
            return None

        uptime = 0.0
        if instance.started_at:
            end = instance.stopped_at or datetime.now(timezone.utc)
            uptime = (end - instance.started_at).total_seconds()

        return ComputeMetrics(
            compute_id=compute_id,
            uptime_seconds=uptime,
            work_completed=instance.completed_work,
            work_failed=instance.failed_work,
            current_work_count=len(instance.current_work),
            last_heartbeat=instance.last_heartbeat
        )

    async def shutdown(self) -> None:
        """Shutdown all compute instances."""
        logger.info("Shutting down all compute instances...")

        for compute_id in list(self._instances.keys()):
            try:
                await self.stop(StopRequest(compute_id=compute_id, force=True, timeout=10))
            except Exception as e:
                logger.error(f"Error stopping {compute_id}: {e}")

        logger.info("All compute instances stopped")


# Global instance
_spawner: Optional[ComputeSpawner] = None


def get_compute_spawner() -> ComputeSpawner:
    """Get the global compute spawner instance."""
    if _spawner is None:
        raise RuntimeError("Compute spawner not initialized")
    return _spawner


def set_compute_spawner(spawner: ComputeSpawner) -> None:
    """Set the global compute spawner instance."""
    global _spawner
    _spawner = spawner
