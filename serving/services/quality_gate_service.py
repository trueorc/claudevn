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
                result = await self._run_startup_smoke_test(work_dir, gate_config)
                gates.append(result)

            if gate_config.config_completeness:
                result = await self._run_config_completeness_check(work_dir, changed_files)
                gates.append(result)

            if gate_config.test_presence:
                result = await self._run_test_presence_check(work_dir, changed_files)
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

        Skips if no test runner is available or no test files exist.
        Parses pytest-style summary lines to extract pass/fail counts.
        """
        import time
        start = time.monotonic()

        cmd = _detect_test_command(work_dir)
        if cmd is None:
            elapsed = int((time.monotonic() - start) * 1000)
            return GateResult(
                gate="test_suite",
                status=GateStatus.SKIPPED,
                message="No test runner available (pytest not installed, no package.json test script)",
                duration_ms=elapsed,
            )

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

    async def _run_startup_smoke_test(self, work_dir: Path, gate_config) -> GateResult:
        """Start the application and verify it boots without errors.

        Two strategies:
        1. If a health URL is configured, start the app as a background
           process and poll the URL until it responds 200 or times out.
        2. Otherwise, run the startup command (or auto-detected command)
           and check that it exits cleanly within the timeout.

        The process is always terminated after the check.
        """
        import signal
        import time
        import urllib.request
        import urllib.error
        start = time.monotonic()
        timeout = gate_config.startup_timeout_seconds

        cmd = _detect_startup_command(work_dir, gate_config.startup_command)
        health_url = gate_config.startup_health_url
        process = None

        try:
            if health_url:
                # Strategy 1: Start process, poll health endpoint
                process = await asyncio.to_thread(
                    lambda: subprocess.Popen(
                        cmd, cwd=str(work_dir),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        env=_safe_git_env(),
                    )
                )
                healthy = await _poll_health(health_url, timeout)
                elapsed = int((time.monotonic() - start) * 1000)

                if healthy:
                    return GateResult(
                        gate="startup_smoke_test",
                        status=GateStatus.PASSED,
                        message=f"App started and health check passed ({health_url})",
                        duration_ms=elapsed,
                    )

                # Timed out waiting for health — capture stderr
                stderr_output = ""
                if process.stderr:
                    try:
                        stderr_output = process.stderr.read().decode(errors="replace")
                    except Exception:
                        pass
                tail = stderr_output.strip().split("\n")[-10:] if stderr_output else []
                return GateResult(
                    gate="startup_smoke_test",
                    status=GateStatus.FAILED,
                    message=f"App failed health check within {timeout}s",
                    details=tail,
                    duration_ms=elapsed,
                )
            else:
                # Strategy 2: Run command and check it doesn't crash immediately
                result = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    capture_output=True, text=True,
                    cwd=str(work_dir),
                    timeout=timeout,
                    env=_safe_git_env(),
                )
                elapsed = int((time.monotonic() - start) * 1000)

                if result.returncode != 0:
                    output_lines = (result.stderr or "").strip().split("\n")
                    tail = output_lines[-10:] if len(output_lines) > 10 else output_lines
                    return GateResult(
                        gate="startup_smoke_test",
                        status=GateStatus.FAILED,
                        message=f"Application exited with code {result.returncode}",
                        details=tail,
                        duration_ms=elapsed,
                    )
                return GateResult(
                    gate="startup_smoke_test",
                    status=GateStatus.PASSED,
                    message="Application started and exited cleanly",
                    duration_ms=elapsed,
                )
        except subprocess.TimeoutExpired:
            # For strategy 2: timeout means the app stayed alive (good!)
            elapsed = int((time.monotonic() - start) * 1000)
            return GateResult(
                gate="startup_smoke_test",
                status=GateStatus.PASSED,
                message=f"Application stayed alive for {timeout}s (no crash)",
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
        finally:
            if process and process.poll() is None:
                try:
                    process.terminate()
                    await asyncio.to_thread(process.wait, timeout=5)
                except Exception:
                    process.kill()

    async def _run_config_completeness_check(
        self, work_dir: Path, changed_files: List[str]
    ) -> GateResult:
        """Check that new env var and config references have template entries.

        Scans Python and JS/TS files for:
        - ``os.getenv("VAR")``, ``os.environ["VAR"]``, ``os.environ.get("VAR")``
        - ``process.env.VAR``

        Cross-references against:
        - ``.env.example``, ``.env.template``
        - Pydantic ``Field(default=...)`` entries in ``config.py``

        Reports each missing reference with file location and suggested action.
        """
        import re
        import time
        start = time.monotonic()

        refs = _scan_env_references(work_dir, changed_files)

        if not refs:
            elapsed = int((time.monotonic() - start) * 1000)
            return GateResult(
                gate="config_completeness",
                status=GateStatus.SKIPPED,
                message="No environment variable references found in changed files",
                duration_ms=elapsed,
            )

        known_vars = _collect_known_config_vars(work_dir)
        missing = [(var, source) for var, source in refs if var not in known_vars]
        elapsed = int((time.monotonic() - start) * 1000)

        if missing:
            details = [
                f"{var} referenced in {source} — add to .env.example or config"
                for var, source in sorted(set(missing))
            ]
            return GateResult(
                gate="config_completeness",
                status=GateStatus.FAILED,
                message=f"{len(set(v for v, _ in missing))} env var(s) missing from config templates",
                details=details,
                duration_ms=elapsed,
            )
        unique_vars = len(set(v for v, _ in refs))
        return GateResult(
            gate="config_completeness",
            status=GateStatus.PASSED,
            message=f"All {unique_vars} env var reference(s) have config entries",
            duration_ms=elapsed,
        )


    async def _run_test_presence_check(
        self, work_dir: Path, changed_files: List[str]
    ) -> GateResult:
        """Check that new source files have corresponding test files.

        For each new/changed source file (non-test), looks for a
        corresponding test file. Reports files that lack tests.
        """
        import time
        start = time.monotonic()

        source_files, test_files = _classify_source_and_test_files(changed_files)

        if not source_files:
            elapsed = int((time.monotonic() - start) * 1000)
            return GateResult(
                gate="test_presence",
                status=GateStatus.SKIPPED,
                message="No source files changed (only tests/config/docs)",
                duration_ms=elapsed,
            )

        # Check which source files have corresponding test files in the diff
        # OR already existing test files in the work directory
        missing: List[str] = []
        for src in source_files:
            expected_tests = _expected_test_paths(src)
            has_test = any(t in test_files for t in expected_tests)
            if not has_test:
                # Check if test file already exists in the repo
                has_test = any((work_dir / t).exists() for t in expected_tests)
            if not has_test:
                missing.append(src)

        elapsed = int((time.monotonic() - start) * 1000)

        if missing:
            details = [
                f"{f} — no corresponding test file found"
                for f in sorted(missing)
            ]
            # Soft gate: warn but don't block merge. Test quality is enforced
            # by test_suite gate when tests exist. test_presence is advisory
            # because compute workers may not be tasked with writing tests.
            return GateResult(
                gate="test_presence",
                status=GateStatus.SKIPPED,
                message=f"{len(missing)} source file(s) lack unit tests (advisory)",
                details=details,
                duration_ms=elapsed,
            )
        return GateResult(
            gate="test_presence",
            status=GateStatus.PASSED,
            message=f"All {len(source_files)} source file(s) have test coverage",
            duration_ms=elapsed,
        )


def _classify_source_and_test_files(
    changed_files: List[str],
) -> tuple:
    """Split changed files into source files and test files.

    Skips non-code files (configs, docs, etc.) and init files.
    Returns (source_files, test_files) as lists of paths.
    """
    code_extensions = {".py", ".js", ".jsx", ".ts", ".tsx"}
    # Patterns that indicate a test file
    test_indicators = ("test_", "_test.", ".test.", ".spec.", "tests/", "test/")
    # Files to skip (not expected to have tests)
    skip_patterns = (
        "__init__", "conftest", "setup.py", "config.py", "migrations/",
        # System files bundled by serving
        "mcp_stdio_server.py",
        # Config/boilerplate files
        "vite.config", "eslint.config", "tsconfig", "tailwind.config",
        "postcss.config", "jest.config", "babel.config", "webpack.config",
        "vitest.config",
        "setup-tests", "setupTests",
        # Application entry points (not expected to have direct tests)
        "main.tsx", "main.ts", "main.jsx", "main.py",
        "index.ts", "index.js",
        "app.py", "App.jsx", "App.tsx",
    )

    source_files = []
    test_files = []

    for f in changed_files:
        ext = Path(f).suffix
        if ext not in code_extensions:
            continue
        if any(s in f for s in skip_patterns):
            continue

        basename = Path(f).name
        is_test = any(indicator in f.lower() for indicator in test_indicators)

        if is_test:
            test_files.append(f)
        else:
            source_files.append(f)

    return source_files, test_files


def _expected_test_paths(source_path: str) -> List[str]:
    """Generate expected test file paths for a source file.

    Examples:
        ``serving/services/quality_gate_service.py``
        → ``serving/tests/test_quality_gate_service.py``

        ``src/components/App.jsx``
        → ``src/components/App.test.jsx``, ``src/components/__tests__/App.jsx``
    """
    p = Path(source_path)
    stem = p.stem
    ext = p.suffix
    parent = p.parent

    paths = []

    if ext == ".py":
        # Python: tests/test_{name}.py or test_{name}.py alongside
        # Look for tests/ directory at each parent level
        parts = list(parent.parts)
        for i in range(len(parts), 0, -1):
            test_dir = Path(*parts[:i]) / "tests"
            paths.append(str(test_dir / f"test_{stem}.py"))
        paths.append(str(parent / f"test_{stem}.py"))
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        # JS/TS: Name.test.ext or __tests__/Name.ext
        paths.append(str(parent / f"{stem}.test{ext}"))
        paths.append(str(parent / f"{stem}.spec{ext}"))
        paths.append(str(parent / "__tests__" / f"{stem}{ext}"))

    return paths


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


def _scan_env_references(
    work_dir: Path, changed_files: List[str]
) -> List[tuple]:
    """Scan changed files for environment variable references.

    Returns list of (var_name, source_file) tuples.
    """
    import re

    # Python patterns
    py_patterns = [
        re.compile(r'os\.getenv\s*\(\s*["\'](\w+)["\']'),
        re.compile(r'os\.environ\s*\[\s*["\'](\w+)["\']'),
        re.compile(r'os\.environ\.get\s*\(\s*["\'](\w+)["\']'),
    ]
    # JS/TS pattern
    js_pattern = re.compile(r'process\.env\.(\w+)')

    refs: List[tuple] = []
    for f in changed_files:
        file_path = work_dir / f
        if not file_path.exists():
            continue
        content = file_path.read_text(errors="replace")

        if f.endswith(".py"):
            for pattern in py_patterns:
                for match in pattern.findall(content):
                    refs.append((match, f))
        elif f.endswith((".js", ".jsx", ".ts", ".tsx")):
            for match in js_pattern.findall(content):
                # Skip common built-ins
                if match not in ("NODE_ENV", "HOME", "PATH", "PWD"):
                    refs.append((match, f))

    return refs


def _collect_known_config_vars(work_dir: Path) -> set:
    """Collect all known config variable names from templates and config files.

    Sources:
    - ``.env.example``, ``.env.template``, ``env.example``
    - ``config.py`` Field defaults (Pydantic models)
    """
    import re

    known: set = set()

    # .env template files
    for tf in [".env.example", ".env.template", "env.example"]:
        tp = work_dir / tf
        if tp.exists():
            for line in tp.read_text(errors="replace").split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    known.add(line.split("=", 1)[0].strip())

    # config.py — extract Field descriptions or env var names from Pydantic models
    config_file = work_dir / "config.py"
    if config_file.exists():
        content = config_file.read_text(errors="replace")
        # Match Pydantic field definitions: "    field_name: type = Field("
        # The field name is indented and followed by a colon+type+Field
        field_pattern = re.compile(r'^\s+(\w+)\s*:', re.MULTILINE)
        for match in field_pattern.findall(content):
            # Skip type annotations and class names
            if match[0].isupper() or match in ("class", "def", "return"):
                continue
            known.add(match.upper())
            known.add(match)

    # Also check for os.environ.setdefault or os.environ references in config.py
    # that define defaults
    if config_file.exists():
        content = config_file.read_text(errors="replace")
        env_pattern = re.compile(r'os\.(?:getenv|environ\.get)\s*\(\s*["\'](\w+)["\']')
        for match in env_pattern.findall(content):
            known.add(match)

    return known


def _detect_startup_command(work_dir: Path, custom_command: Optional[str] = None) -> List[str]:
    """Detect the startup command for a project.

    Priority:
    1. Custom command from config
    2. ``app.py`` (Python FastAPI/Flask)
    3. ``package.json`` start script
    4. Fallback: ``python -c "import app"``
    """
    if custom_command:
        return custom_command.split()

    app_py = work_dir / "app.py"
    if app_py.exists():
        return ["python", "app.py"]

    package_json = work_dir / "package.json"
    if package_json.exists():
        import json
        try:
            pkg = json.loads(package_json.read_text())
            if "start" in pkg.get("scripts", {}):
                return ["npm", "start"]
        except (json.JSONDecodeError, OSError):
            pass

    return ["python", "-c", "import app"]


async def _poll_health(url: str, timeout: int) -> bool:
    """Poll a health endpoint until it returns 200 or timeout expires."""
    import time
    import urllib.request
    import urllib.error

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = await asyncio.to_thread(
                urllib.request.urlopen, url, timeout=2
            )
            if resp.status == 200:
                return True
        except (urllib.error.URLError, OSError, Exception):
            pass
        await asyncio.sleep(0.5)
    return False


def _detect_test_command(work_dir: Path) -> Optional[List[str]]:
    """Detect the appropriate test command for a project directory.

    Checks in order:
    1. scripts/run_unit_tests.sh (project runner)
    2. package.json with "test" script (JS/TS project)
    3. python -m pytest (only if pytest is installed)

    Returns None if no test runner is available.
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

    # Only use pytest if it's actually installed
    if shutil.which("pytest") or _check_pytest_available():
        return ["python", "-m", "pytest", "--tb=short", "-q"]

    return None


def _check_pytest_available() -> bool:
    """Check if pytest is importable in the current Python environment."""
    try:
        result = subprocess.run(
            ["python", "-c", "import pytest"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


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
    """Get environment with safe git settings and committer identity."""
    import os
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_AUTHOR_NAME"] = "ClaudeVN"
    env["GIT_AUTHOR_EMAIL"] = "claudevn@system"
    env["GIT_COMMITTER_NAME"] = "ClaudeVN"
    env["GIT_COMMITTER_EMAIL"] = "claudevn@system"
    return env


# Singleton
_quality_gate_service: Optional[QualityGateService] = None


def get_quality_gate_service() -> QualityGateService:
    global _quality_gate_service
    if _quality_gate_service is None:
        _quality_gate_service = QualityGateService()
    return _quality_gate_service
