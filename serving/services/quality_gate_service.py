"""Quality gate service for PR validation before auto-merge.

Runs configurable validation checks on PR branches before allowing
auto-approval. Gates include syntax checking, test execution,
startup smoke tests, and config completeness validation.
"""

import asyncio
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import get_config

logger = logging.getLogger(__name__)


class GateStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class GateResult:
    gate: str
    status: GateStatus
    message: str = ""
    details: Optional[List[str]] = None
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.gate,
            "status": self.status.value,
            "message": self.message,
            "details": self.details or [],
            "duration_ms": self.duration_ms,
        }


@dataclass
class ValidationResult:
    passed: bool
    gates: List[GateResult] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "gates": [g.to_dict() for g in self.gates],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class QualityGateService:
    """Runs validation gates on PR branches before auto-merge."""

    def __init__(self):
        self._config = get_config()

    async def validate_branch(
        self,
        project: str,
        branch: str,
    ) -> ValidationResult:
        """Run all enabled quality gates against a branch.

        Clones the repo, merges the branch into the default branch in a temp
        directory, then runs each gate. Returns a ValidationResult.

        Args:
            project: Git project name (e.g. "proj_abc_repo_def")
            branch: Branch to validate

        Returns:
            ValidationResult with per-gate results
        """
        gate_config = self._config.quality_gate
        if not gate_config.enabled:
            return ValidationResult(
                passed=True,
                started_at=datetime.now(timezone.utc).isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
                gates=[GateResult(gate="quality_gates", status=GateStatus.SKIPPED, message="Quality gates disabled")],
            )

        started_at = datetime.now(timezone.utc).isoformat()
        gates: List[GateResult] = []
        repo_path = Path(self._config.git.repos_path) / f"{project}.git"

        # Create temp working directory with merged state
        work_dir = None
        changed_files: List[str] = []
        try:
            work_dir = Path(tempfile.mkdtemp(prefix=f"quality-gate-{project}-"))

            from git.repo_manager import RepoManager
            repo_manager = RepoManager()
            default_branch = repo_manager.get_default_branch(project)

            # Clone and merge
            env = _safe_git_env()
            subprocess.run(
                ["git", "clone", str(repo_path), str(work_dir)],
                capture_output=True, text=True, check=True, env=env
            )
            subprocess.run(
                ["git", "-C", str(work_dir), "checkout", default_branch],
                capture_output=True, text=True, check=True, env=env
            )

            # Get changed files before merging
            diff_result = subprocess.run(
                ["git", "-C", str(work_dir), "diff", "--name-only", f"{default_branch}..origin/{branch}"],
                capture_output=True, text=True, env=env
            )
            changed_files = [f for f in diff_result.stdout.strip().split("\n") if f]

            # Merge branch
            merge_result = subprocess.run(
                ["git", "-C", str(work_dir), "merge", "--no-ff", f"origin/{branch}",
                 "-m", "quality-gate-merge"],
                capture_output=True, text=True, env=env
            )
            if merge_result.returncode != 0:
                gates.append(GateResult(
                    gate="merge",
                    status=GateStatus.FAILED,
                    message="Branch has merge conflicts",
                    details=[merge_result.stderr],
                ))
                return ValidationResult(passed=False, gates=gates, started_at=started_at,
                                        completed_at=datetime.now(timezone.utc).isoformat())

            # Run gates
            if gate_config.syntax_check:
                result = await self._run_syntax_check(work_dir, changed_files)
                gates.append(result)

            if gate_config.test_gate:
                result = await self._run_test_gate(work_dir, gate_config.timeout_seconds)
                gates.append(result)

            if gate_config.startup_smoke_test:
                result = await self._run_startup_smoke_test(work_dir, gate_config.timeout_seconds)
                gates.append(result)

            if gate_config.config_completeness:
                result = await self._run_config_completeness_check(work_dir, changed_files)
                gates.append(result)

        except Exception as e:
            logger.error(f"Quality gate setup failed for {project}/{branch}: {e}")
            gates.append(GateResult(
                gate="setup",
                status=GateStatus.ERROR,
                message=f"Quality gate setup failed: {e}",
            ))
        finally:
            if work_dir and work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)

        passed = all(g.status in (GateStatus.PASSED, GateStatus.SKIPPED) for g in gates)
        completed_at = datetime.now(timezone.utc).isoformat()

        return ValidationResult(
            passed=passed,
            gates=gates,
            started_at=started_at,
            completed_at=completed_at,
        )

    async def _run_syntax_check(
        self, work_dir: Path, changed_files: List[str]
    ) -> GateResult:
        """Run Python syntax/import validation on changed files."""
        import time
        start = time.monotonic()

        py_files = [f for f in changed_files if f.endswith(".py")]
        if not py_files:
            return GateResult(
                gate="syntax_check",
                status=GateStatus.SKIPPED,
                message="No Python files changed",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        errors: List[str] = []
        for py_file in py_files:
            file_path = work_dir / py_file
            if not file_path.exists():
                continue  # File was deleted
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["python", "-m", "py_compile", str(file_path)],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    errors.append(f"{py_file}: {result.stderr.strip()}")
            except Exception as e:
                errors.append(f"{py_file}: {e}")

        elapsed = int((time.monotonic() - start) * 1000)
        if errors:
            return GateResult(
                gate="syntax_check",
                status=GateStatus.FAILED,
                message=f"{len(errors)} file(s) have syntax errors",
                details=errors,
                duration_ms=elapsed,
            )
        return GateResult(
            gate="syntax_check",
            status=GateStatus.PASSED,
            message=f"{len(py_files)} file(s) checked",
            duration_ms=elapsed,
        )

    async def _run_test_gate(self, work_dir: Path, timeout: int) -> GateResult:
        """Run test suite in the working directory."""
        import time
        start = time.monotonic()

        # Look for test runner scripts or pytest
        test_script = work_dir / "scripts" / "run_unit_tests.sh"
        if test_script.exists():
            cmd = ["bash", str(test_script)]
        else:
            cmd = ["python", "-m", "pytest", "--tb=short", "-q"]

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True, text=True,
                cwd=str(work_dir),
                timeout=timeout,
            )
            elapsed = int((time.monotonic() - start) * 1000)

            if result.returncode != 0:
                # Extract last 20 lines of output for context
                output_lines = (result.stdout + result.stderr).strip().split("\n")
                tail = output_lines[-20:] if len(output_lines) > 20 else output_lines
                return GateResult(
                    gate="test_suite",
                    status=GateStatus.FAILED,
                    message="Test suite failed",
                    details=tail,
                    duration_ms=elapsed,
                )
            return GateResult(
                gate="test_suite",
                status=GateStatus.PASSED,
                message="All tests passed",
                duration_ms=elapsed,
            )
        except subprocess.TimeoutExpired:
            elapsed = int((time.monotonic() - start) * 1000)
            return GateResult(
                gate="test_suite",
                status=GateStatus.ERROR,
                message=f"Test suite timed out after {timeout}s",
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return GateResult(
                gate="test_suite",
                status=GateStatus.ERROR,
                message=f"Test execution error: {e}",
                duration_ms=elapsed,
            )

    async def _run_startup_smoke_test(self, work_dir: Path, timeout: int) -> GateResult:
        """Attempt to import the main application module."""
        import time
        start = time.monotonic()

        # Try to import the app module to verify no import errors
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["python", "-c", "import app"],
                capture_output=True, text=True,
                cwd=str(work_dir),
                timeout=min(timeout, 30),
            )
            elapsed = int((time.monotonic() - start) * 1000)

            if result.returncode != 0:
                output_lines = result.stderr.strip().split("\n")
                tail = output_lines[-10:] if len(output_lines) > 10 else output_lines
                return GateResult(
                    gate="startup_smoke_test",
                    status=GateStatus.FAILED,
                    message="Application failed to import",
                    details=tail,
                    duration_ms=elapsed,
                )
            return GateResult(
                gate="startup_smoke_test",
                status=GateStatus.PASSED,
                message="Application imports successfully",
                duration_ms=elapsed,
            )
        except subprocess.TimeoutExpired:
            elapsed = int((time.monotonic() - start) * 1000)
            return GateResult(
                gate="startup_smoke_test",
                status=GateStatus.ERROR,
                message="Startup smoke test timed out",
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return GateResult(
                gate="startup_smoke_test",
                status=GateStatus.ERROR,
                message=f"Smoke test error: {e}",
                duration_ms=elapsed,
            )

    async def _run_config_completeness_check(
        self, work_dir: Path, changed_files: List[str]
    ) -> GateResult:
        """Check that new env var/config references have template entries."""
        import re
        import time
        start = time.monotonic()

        # Scan changed Python files for os.getenv / os.environ references
        new_env_refs: List[str] = []
        env_pattern = re.compile(r'os\.(?:getenv|environ(?:\.get)?)\s*\(\s*["\'](\w+)["\']')

        py_files = [f for f in changed_files if f.endswith(".py")]
        for py_file in py_files:
            file_path = work_dir / py_file
            if not file_path.exists():
                continue
            content = file_path.read_text(errors="replace")
            matches = env_pattern.findall(content)
            new_env_refs.extend(matches)

        if not new_env_refs:
            elapsed = int((time.monotonic() - start) * 1000)
            return GateResult(
                gate="config_completeness",
                status=GateStatus.SKIPPED,
                message="No new environment variable references found",
                duration_ms=elapsed,
            )

        # Check .env.example or similar template files
        template_files = [".env.example", ".env.template", "env.example"]
        template_vars: set = set()
        for tf in template_files:
            tp = work_dir / tf
            if tp.exists():
                for line in tp.read_text().split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        template_vars.add(line.split("=", 1)[0].strip())

        missing = [v for v in set(new_env_refs) if v not in template_vars]
        elapsed = int((time.monotonic() - start) * 1000)

        if missing:
            return GateResult(
                gate="config_completeness",
                status=GateStatus.FAILED,
                message=f"{len(missing)} env var(s) missing from templates",
                details=[f"{v} not found in .env.example" for v in sorted(missing)],
                duration_ms=elapsed,
            )
        return GateResult(
            gate="config_completeness",
            status=GateStatus.PASSED,
            message=f"All {len(new_env_refs)} env var references have template entries",
            duration_ms=elapsed,
        )


def _safe_git_env() -> dict:
    """Get environment with safe git settings."""
    import os
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


# Singleton
_quality_gate_service: Optional[QualityGateService] = None


def get_quality_gate_service() -> QualityGateService:
    global _quality_gate_service
    if _quality_gate_service is None:
        _quality_gate_service = QualityGateService()
    return _quality_gate_service
