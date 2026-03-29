"""Per-unit verification — automated checks for a single work unit.

Runs the verification criteria from a work unit's spec as CI-style
checks. No LLM judgment — these are computational checks: build,
test, lint, type check, spec compliance, scope containment.
"""

import asyncio
import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models.work_unit import (
    WorkUnit,
    AutomatedCheck,
    AutomatedCheckType,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger(__name__)

# Timeout for individual checks
CHECK_TIMEOUT_SECONDS = 120


class UnitVerifier:
    """Runs automated verification checks on a single work unit.

    Each check maps to a subprocess command. Results are purely
    computational — pass/fail based on exit codes and output parsing.
    """

    def __init__(self, repo_path: str):
        self._repo_path = repo_path

    async def verify(
        self,
        unit: WorkUnit,
        branch: Optional[str] = None,
    ) -> List[VerificationResult]:
        """Run all automated checks for a work unit.

        Args:
            unit: The work unit to verify.
            branch: Git branch to check out before running (if provided).

        Returns:
            List of VerificationResult, one per check.
        """
        results = []

        for check in unit.verification_criteria.automated:
            result = await self._run_check(check, unit)
            results.append(result)

        # Scope containment check — did the unit touch only its target files?
        scope_result = await self._check_scope_containment(unit, branch)
        if scope_result:
            results.append(scope_result)

        return results

    async def _run_check(
        self,
        check: AutomatedCheck,
        unit: WorkUnit,
    ) -> VerificationResult:
        """Run a single automated check.

        Maps check types to commands and returns structured results.
        """
        try:
            if check.type == AutomatedCheckType.BUILD_SUCCESS:
                return await self._check_build(check)
            elif check.type == AutomatedCheckType.TEST_PASS:
                return await self._check_tests(check)
            elif check.type == AutomatedCheckType.LINT_CLEAN:
                return await self._check_lint(check)
            elif check.type == AutomatedCheckType.TYPE_CHECK:
                return await self._check_types(check)
            else:
                return VerificationResult(
                    check_type=check.type.value,
                    status=VerificationStatus.FAILED,
                    details=f"Unknown check type: {check.type}",
                )
        except asyncio.TimeoutError:
            return VerificationResult(
                check_type=check.type.value,
                status=VerificationStatus.FAILED,
                details=f"Check timed out after {CHECK_TIMEOUT_SECONDS}s",
            )
        except Exception as e:
            return VerificationResult(
                check_type=check.type.value,
                status=VerificationStatus.FAILED,
                details=f"Check error: {str(e)}",
            )

    async def _check_build(self, check: AutomatedCheck) -> VerificationResult:
        """Check that the project builds successfully."""
        # Detect build system and run appropriate command
        build_commands = self._detect_build_command()
        if not build_commands:
            return VerificationResult(
                check_type="build_success",
                status=VerificationStatus.PASSED,
                details="No build system detected, skipping",
            )

        for cmd in build_commands:
            exit_code, output = await self._run_command(cmd)
            if exit_code != 0:
                return VerificationResult(
                    check_type="build_success",
                    status=VerificationStatus.FAILED,
                    details=f"Build failed: {cmd}",
                    output=output[-2000:] if output else None,
                )

        return VerificationResult(
            check_type="build_success",
            status=VerificationStatus.PASSED,
            details="Build succeeded",
        )

    async def _check_tests(self, check: AutomatedCheck) -> VerificationResult:
        """Run specified tests."""
        target = check.target
        cmd = self._detect_test_command(target)
        if not cmd:
            return VerificationResult(
                check_type="test_pass",
                status=VerificationStatus.PASSED,
                details=f"No test runner detected for {target}",
            )

        exit_code, output = await self._run_command(cmd)
        status = VerificationStatus.PASSED if exit_code == 0 else VerificationStatus.FAILED
        return VerificationResult(
            check_type="test_pass",
            status=status,
            details=f"Tests {'passed' if exit_code == 0 else 'failed'}: {target}",
            output=output[-2000:] if output else None,
        )

    async def _check_lint(self, check: AutomatedCheck) -> VerificationResult:
        """Run linter on target."""
        cmd = self._detect_lint_command()
        if not cmd:
            return VerificationResult(
                check_type="lint_clean",
                status=VerificationStatus.PASSED,
                details="No linter detected, skipping",
            )

        exit_code, output = await self._run_command(cmd)
        status = VerificationStatus.PASSED if exit_code == 0 else VerificationStatus.FAILED
        return VerificationResult(
            check_type="lint_clean",
            status=status,
            details=f"Lint {'clean' if exit_code == 0 else 'issues found'}",
            output=output[-2000:] if output else None,
        )

    async def _check_types(self, check: AutomatedCheck) -> VerificationResult:
        """Run type checker."""
        cmd = self._detect_type_check_command()
        if not cmd:
            return VerificationResult(
                check_type="type_check",
                status=VerificationStatus.PASSED,
                details="No type checker detected, skipping",
            )

        exit_code, output = await self._run_command(cmd)
        status = VerificationStatus.PASSED if exit_code == 0 else VerificationStatus.FAILED
        return VerificationResult(
            check_type="type_check",
            status=status,
            details=f"Type check {'passed' if exit_code == 0 else 'failed'}",
            output=output[-2000:] if output else None,
        )

    async def _check_scope_containment(
        self,
        unit: WorkUnit,
        branch: Optional[str],
    ) -> Optional[VerificationResult]:
        """Check if the work unit only modified its target files.

        Compares the branch diff against the formal spec's target_files.
        Files outside scope are flagged — may indicate decomposition was wrong.
        """
        if not branch:
            return None

        exit_code, output = await self._run_command(
            f"git diff --name-only {unit.formal_spec.input_state}...{branch}"
        )
        if exit_code != 0:
            return None

        if not output:
            return None

        changed_files = set(output.strip().split("\n"))
        target_files = set(unit.formal_spec.target_files)

        # Also allow new files from expected_outputs
        for eo in unit.formal_spec.expected_outputs:
            target_files.add(eo.path)

        out_of_scope = changed_files - target_files
        if out_of_scope:
            return VerificationResult(
                check_type="scope_containment",
                status=VerificationStatus.NEEDS_HUMAN_REVIEW,
                details=(
                    f"Modified {len(out_of_scope)} file(s) outside scope: "
                    f"{', '.join(sorted(out_of_scope)[:10])}"
                ),
            )

        return VerificationResult(
            check_type="scope_containment",
            status=VerificationStatus.PASSED,
            details="All changes within target scope",
        )

    def _detect_build_command(self) -> List[str]:
        """Detect the project's build command."""
        if os.path.exists(os.path.join(self._repo_path, "package.json")):
            return ["npm run build"]
        if os.path.exists(os.path.join(self._repo_path, "Makefile")):
            return ["make"]
        if os.path.exists(os.path.join(self._repo_path, "go.mod")):
            return ["go build ./..."]
        if os.path.exists(os.path.join(self._repo_path, "Cargo.toml")):
            return ["cargo build"]
        return []

    def _detect_test_command(self, target: str) -> Optional[str]:
        """Detect test command for a target."""
        if target.endswith(".py"):
            return f"python -m pytest {target} -x -q"
        if target.endswith((".test.js", ".test.ts", ".test.tsx", ".spec.js", ".spec.ts")):
            return f"npx jest {target}"
        if target.endswith("_test.go"):
            return f"go test ./{os.path.dirname(target)}/..."
        if target == ".":
            if os.path.exists(os.path.join(self._repo_path, "pytest.ini")) or \
               os.path.exists(os.path.join(self._repo_path, "pyproject.toml")):
                return "python -m pytest -x -q"
        return None

    def _detect_lint_command(self) -> Optional[str]:
        """Detect linter command."""
        if os.path.exists(os.path.join(self._repo_path, ".eslintrc.json")) or \
           os.path.exists(os.path.join(self._repo_path, ".eslintrc.js")):
            return "npx eslint ."
        if os.path.exists(os.path.join(self._repo_path, "pyproject.toml")):
            return "python -m ruff check ."
        return None

    def _detect_type_check_command(self) -> Optional[str]:
        """Detect type checker command."""
        if os.path.exists(os.path.join(self._repo_path, "tsconfig.json")):
            return "npx tsc --noEmit"
        if os.path.exists(os.path.join(self._repo_path, "mypy.ini")) or \
           os.path.exists(os.path.join(self._repo_path, "pyproject.toml")):
            return "python -m mypy ."
        return None

    async def _run_command(self, cmd: str) -> tuple[int, str]:
        """Run a shell command and return (exit_code, output)."""
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=self._repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=CHECK_TIMEOUT_SECONDS
            )
            return proc.returncode or 0, stdout.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            proc.kill()
            raise
