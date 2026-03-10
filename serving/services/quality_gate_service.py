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
        """Run Python syntax and import validation on changed files.

        Two-phase check:
        1. Syntax: ``python -m py_compile`` on each changed .py file.
        2. Imports: For each changed top-level module/package, attempt
           ``python -c "import <module>"`` to catch missing dependencies
           and broken internal imports.

        Error details include file path and line number where available.
        """
        import re
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

        # Phase 1: Syntax check with py_compile
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
                    error_detail = _parse_compile_error(
                        result.stderr.strip(), py_file, str(work_dir)
                    )
                    errors.append(error_detail)
            except Exception as e:
                errors.append(f"{py_file}: {e}")

        # Phase 2: Import validation for top-level modules
        # Deduplicate to unique top-level packages from changed files
        top_level_modules = _extract_top_level_modules(py_files)
        for module_name in top_level_modules:
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["python", "-c", f"import {module_name}"],
                    capture_output=True, text=True,
                    cwd=str(work_dir),
                    timeout=30,
                )
                if result.returncode != 0:
                    import_error = _parse_import_error(
                        result.stderr.strip(), module_name
                    )
                    errors.append(import_error)
            except subprocess.TimeoutExpired:
                errors.append(f"import {module_name}: timed out after 30s")
            except Exception as e:
                errors.append(f"import {module_name}: {e}")

        elapsed = int((time.monotonic() - start) * 1000)
        checked_count = len(py_files)
        import_count = len(top_level_modules)

        if errors:
            return GateResult(
                gate="syntax_check",
                status=GateStatus.FAILED,
                message=f"{len(errors)} error(s) in {checked_count} file(s), {import_count} module(s)",
                details=errors,
                duration_ms=elapsed,
            )
        return GateResult(
            gate="syntax_check",
            status=GateStatus.PASSED,
            message=f"{checked_count} file(s) compiled, {import_count} module(s) imported",
            duration_ms=elapsed,
        )

    async def _run_test_gate(self, work_dir: Path, timeout: int) -> GateResult:
        """Run test suite in the working directory.

        Detects the appropriate test runner:
        1. ``scripts/run_unit_tests.sh`` (project-specific runner)
        2. ``package.json`` with ``test`` script → ``npm test``
        3. Fallback to ``python -m pytest``

        Parses pytest-style summary lines to extract pass/fail counts.
        """
        import time
        start = time.monotonic()

        cmd = _detect_test_command(work_dir)

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True, text=True,
                cwd=str(work_dir),
                timeout=timeout,
            )
            elapsed = int((time.monotonic() - start) * 1000)
            combined_output = (result.stdout + result.stderr).strip()
            summary = _parse_test_summary(combined_output)

            if result.returncode != 0:
                output_lines = combined_output.split("\n")
                tail = output_lines[-20:] if len(output_lines) > 20 else output_lines
                message = f"Test suite failed: {summary}" if summary else "Test suite failed"
                return GateResult(
                    gate="test_suite",
                    status=GateStatus.FAILED,
                    message=message,
                    details=tail,
                    duration_ms=elapsed,
                )
            message = f"Tests passed: {summary}" if summary else "All tests passed"
            return GateResult(
                gate="test_suite",
                status=GateStatus.PASSED,
                message=message,
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


def _parse_compile_error(stderr: str, py_file: str, work_dir: str) -> str:
    """Extract file:line from py_compile error output.

    py_compile output looks like:
        File "/tmp/work/serving/foo.py", line 10
            x = (
            ^
        SyntaxError: unexpected EOF while parsing

    Returns a string like: ``serving/foo.py:10: SyntaxError: unexpected EOF``
    """
    import re
    # Match: File "<path>", line <N>
    match = re.search(r'File "([^"]+)", line (\d+)', stderr)
    if match:
        full_path, line_num = match.group(1), match.group(2)
        # Strip work_dir prefix to show relative path
        rel_path = full_path.replace(work_dir + "/", "").replace(work_dir, "")
        # Extract the error type/message from the last line
        lines = stderr.strip().split("\n")
        error_msg = lines[-1].strip() if lines else "unknown error"
        return f"{rel_path}:{line_num}: {error_msg}"
    # Fallback: return raw stderr with file prefix
    return f"{py_file}: {stderr}"


def _parse_import_error(stderr: str, module_name: str) -> str:
    """Extract structured error from import failure.

    Returns a string like:
        ``import serving: ModuleNotFoundError: No module named 'missing_dep'``
    """
    lines = stderr.strip().split("\n")
    # The last line usually has the actual error
    error_line = lines[-1].strip() if lines else "unknown import error"
    return f"import {module_name}: {error_line}"


def _extract_top_level_modules(py_files: List[str]) -> List[str]:
    """Derive unique top-level module names from a list of changed .py paths.

    Examples:
        ``serving/api/compute.py`` → ``serving``
        ``app.py`` → (skip standalone scripts)
        ``tests/test_foo.py`` → (skip test files)
    """
    modules: set = set()
    for f in py_files:
        parts = Path(f).parts
        if len(parts) < 2:
            continue  # Top-level script, not a package
        top = parts[0]
        # Skip test directories — they import project modules, not standalone
        if top in ("tests", "test"):
            continue
        modules.add(top)
    return sorted(modules)


def _detect_test_command(work_dir: Path) -> List[str]:
    """Detect the appropriate test command for a project directory.

    Checks in order:
    1. scripts/run_unit_tests.sh (project runner)
    2. package.json with "test" script (JS/TS project)
    3. Fallback: python -m pytest
    """
    test_script = work_dir / "scripts" / "run_unit_tests.sh"
    if test_script.exists():
        return ["bash", str(test_script)]

    package_json = work_dir / "package.json"
    if package_json.exists():
        import json
        try:
            pkg = json.loads(package_json.read_text())
            if "test" in pkg.get("scripts", {}):
                return ["npm", "test", "--", "--ci"]
        except (json.JSONDecodeError, OSError):
            pass

    return ["python", "-m", "pytest", "--tb=short", "-q"]


def _parse_test_summary(output: str) -> str:
    """Extract pass/fail counts from pytest or jest output.

    Pytest summary looks like: ``5 passed, 2 failed, 1 error in 1.23s``
    Jest summary looks like: ``Tests: 2 failed, 5 passed, 7 total``

    Returns a short summary string, or empty string if not parseable.
    """
    import re

    # jest: "Tests: X failed, Y passed, Z total"
    jest_match = re.search(r"Tests:\s+(.+total)", output)
    if jest_match:
        return jest_match.group(1)

    # pytest summary line: capture the full "X failed, Y passed" or "X passed" etc.
    # The summary line looks like: "2 failed, 8 passed, 1 warning in 1.23s"
    # Match the whole summary (comma-separated counts before " in ")
    pytest_summary = re.search(
        r"((?:\d+\s+(?:passed|failed|error|errors|warning|warnings|skipped)"
        r"(?:,\s*)?)+)",
        output,
    )
    if pytest_summary:
        return pytest_summary.group(1).strip().rstrip(",")

    return ""


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
