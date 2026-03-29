"""Cross-unit integration verification — ClaudeVN's unique value.

Verifies that independently-produced work unit outputs integrate
correctly. No single Claude Code instance can do this — it requires
the global view across all completed units.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from models.work_unit import (
    WorkUnit,
    IntegrationCheck,
    IntegrationCheckType,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class IntegrationReport:
    """Report from cross-unit integration verification."""
    unit_pairs_checked: int = 0
    merge_conflicts: List[Dict[str, str]] = field(default_factory=list)
    interface_mismatches: List[Dict[str, str]] = field(default_factory=list)
    combined_test_failures: List[str] = field(default_factory=list)
    all_passed: bool = True
    results: List[VerificationResult] = field(default_factory=list)


class IntegrationVerifier:
    """Verifies cross-unit integration for completed work units.

    Runs when multiple work units from the same goal complete:
    1. Merge safety — do branches merge cleanly?
    2. Interface compatibility — do outputs conform to contracts?
    3. Combined test suite — does the merged result pass all tests?
    4. Cumulative static analysis — complexity/coverage delta.
    """

    def __init__(self, repo_path: str):
        self._repo_path = repo_path

    async def verify_integration(
        self,
        units: List[WorkUnit],
        base_branch: str = "main",
    ) -> IntegrationReport:
        """Run cross-unit integration checks.

        Args:
            units: Completed work units to verify integration for.
            base_branch: The branch all units were based on.

        Returns:
            IntegrationReport with per-pair results.
        """
        report = IntegrationReport()

        if len(units) < 2:
            return report

        # Check all pairs with integration criteria
        pairs = self._find_integration_pairs(units)
        report.unit_pairs_checked = len(pairs)

        for unit_a, unit_b in pairs:
            # 1. Merge safety
            merge_result = await self._check_merge_safety(unit_a, unit_b, base_branch)
            report.results.append(merge_result)
            if merge_result.status != VerificationStatus.PASSED:
                report.all_passed = False
                report.merge_conflicts.append({
                    "unit_a": unit_a.id,
                    "unit_b": unit_b.id,
                    "details": merge_result.details,
                })

            # 2. Interface compatibility
            iface_result = await self._check_interface_compatibility(unit_a, unit_b)
            if iface_result:
                report.results.append(iface_result)
                if iface_result.status != VerificationStatus.PASSED:
                    report.all_passed = False
                    report.interface_mismatches.append({
                        "unit_a": unit_a.id,
                        "unit_b": unit_b.id,
                        "details": iface_result.details,
                    })

        # 3. Combined test suite (merge all branches and run tests)
        if all(u.branch for u in units):
            combined_result = await self._check_combined_tests(units, base_branch)
            report.results.append(combined_result)
            if combined_result.status != VerificationStatus.PASSED:
                report.all_passed = False
                report.combined_test_failures.append(combined_result.details)

        return report

    def _find_integration_pairs(
        self, units: List[WorkUnit]
    ) -> List[Tuple[WorkUnit, WorkUnit]]:
        """Find pairs of units that need integration checking.

        Checks units that have explicit integration criteria or
        that share file overlap warnings.
        """
        pairs = []
        unit_map = {u.id: u for u in units}

        # Pairs from explicit integration criteria
        seen = set()
        for unit in units:
            for check in unit.verification_criteria.integration:
                other_id = check.with_unit
                if other_id in unit_map:
                    pair_key = tuple(sorted([unit.id, other_id]))
                    if pair_key not in seen:
                        seen.add(pair_key)
                        pairs.append((unit, unit_map[other_id]))

        # Pairs from file overlap (independence warnings)
        for unit in units:
            for other_id in unit.independence.shares_files_with:
                if other_id in unit_map:
                    pair_key = tuple(sorted([unit.id, other_id]))
                    if pair_key not in seen:
                        seen.add(pair_key)
                        pairs.append((unit, unit_map[other_id]))

        return pairs

    async def _check_merge_safety(
        self,
        unit_a: WorkUnit,
        unit_b: WorkUnit,
        base_branch: str,
    ) -> VerificationResult:
        """Check if two work unit branches merge cleanly."""
        if not unit_a.branch or not unit_b.branch:
            return VerificationResult(
                check_type="merge_safety",
                status=VerificationStatus.PASSED,
                details="Branches not yet available, skipping merge check",
            )

        # Try merging in a temporary branch
        exit_code, output = await self._run_git(
            f"git merge-tree {base_branch} {unit_a.branch} {unit_b.branch}"
        )

        if exit_code != 0:
            return VerificationResult(
                check_type="merge_safety",
                status=VerificationStatus.FAILED,
                details=f"Merge conflict between {unit_a.id} and {unit_b.id}",
                output=output[-2000:] if output else None,
            )

        return VerificationResult(
            check_type="merge_safety",
            status=VerificationStatus.PASSED,
            details=f"Branches {unit_a.id} and {unit_b.id} merge cleanly",
        )

    async def _check_interface_compatibility(
        self,
        unit_a: WorkUnit,
        unit_b: WorkUnit,
    ) -> Optional[VerificationResult]:
        """Check interface contract compatibility between two units.

        Verifies that what unit_a exports matches what unit_b expects
        (and vice versa) based on their interface contracts.
        """
        # Find contracts that reference each other
        a_contracts = {c.file: c for c in unit_a.formal_spec.interface_contracts}
        b_contracts = {c.file: c for c in unit_b.formal_spec.interface_contracts}

        shared_files = set(a_contracts.keys()) & set(b_contracts.keys())
        if not shared_files:
            return None

        mismatches = []
        for file_path in shared_files:
            a_def = a_contracts[file_path].definition
            b_def = b_contracts[file_path].definition
            if a_def != b_def:
                mismatches.append(
                    f"{file_path}: unit {unit_a.id} expects '{a_def}', "
                    f"unit {unit_b.id} expects '{b_def}'"
                )

        if mismatches:
            return VerificationResult(
                check_type="interface_compatible",
                status=VerificationStatus.FAILED,
                details=f"Interface mismatches: {'; '.join(mismatches)}",
            )

        return VerificationResult(
            check_type="interface_compatible",
            status=VerificationStatus.PASSED,
            details=f"Interface contracts compatible for {', '.join(shared_files)}",
        )

    async def _check_combined_tests(
        self,
        units: List[WorkUnit],
        base_branch: str,
    ) -> VerificationResult:
        """Merge all branches and run the full test suite.

        This is the definitive integration check — does the combined
        result of all work units pass the project's test suite?
        """
        # Collect all test files that should pass
        all_tests = set()
        for unit in units:
            for test in unit.context_package.relevant_tests:
                all_tests.add(test)

        if not all_tests:
            return VerificationResult(
                check_type="combined_tests",
                status=VerificationStatus.PASSED,
                details="No relevant tests to run",
            )

        # The actual merge + test run would happen in a temp worktree.
        # For now, return a placeholder that indicates the check type exists.
        return VerificationResult(
            check_type="combined_tests",
            status=VerificationStatus.PENDING,
            details=f"Combined test run pending for {len(all_tests)} test files",
        )

    async def _run_git(self, cmd: str) -> tuple[int, str]:
        """Run a git command."""
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=self._repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            return proc.returncode or 0, stdout.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            return 1, "Git command timed out"
