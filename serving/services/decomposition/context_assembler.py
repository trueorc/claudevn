"""Context assembler — builds context packages for Claude Code instances.

Prepares everything a Claude Code instance needs to execute a work unit
in one shot: file contents, interface definitions, test files, upstream
outputs, and the formal specification. The goal is zero exploration turns.
"""

import logging
import os
from typing import Dict, List, Optional

from models.work_unit import WorkUnit, ContextPackage

logger = logging.getLogger(__name__)


class ContextAssembler:
    """Assembles context packages for work unit execution.

    Takes a WorkUnit's context_package (file paths) and resolves
    them to actual content. Produces a composed prompt/CLAUDE.md
    that gives the instance everything it needs.
    """

    def __init__(self, repo_path: str):
        self._repo_path = repo_path

    async def assemble(
        self,
        unit: WorkUnit,
        upstream_diffs: Optional[Dict[str, str]] = None,
        max_file_size: int = 50_000,
    ) -> str:
        """Assemble the full context for a work unit execution.

        Args:
            unit: The work unit to prepare context for.
            upstream_diffs: Diffs from completed upstream work units
                (keyed by work unit ID).
            max_file_size: Max bytes per file to include (truncate larger).

        Returns:
            Composed context string ready for CLAUDE.md injection.
        """
        sections = []

        # 1. Work unit specification
        sections.append(self._format_spec(unit))

        # 2. Target file contents
        for filepath in unit.context_package.files:
            content = self._read_file(filepath, max_file_size)
            if content is not None:
                sections.append(f"## File: {filepath}\n```\n{content}\n```")

        # 3. Interface contracts
        if unit.formal_spec.interface_contracts:
            contracts_section = "## Interface Contracts\n"
            for contract in unit.formal_spec.interface_contracts:
                contracts_section += (
                    f"- **{contract.file}** ({contract.type.value}): "
                    f"{contract.definition}\n"
                )
            sections.append(contracts_section)

        # 4. Relevant test files
        for test_path in unit.context_package.relevant_tests:
            content = self._read_file(test_path, max_file_size)
            if content is not None:
                sections.append(f"## Test: {test_path}\n```\n{content}\n```")

        # 5. Upstream diffs (for dependent units)
        if upstream_diffs:
            for dep_id in unit.independence.depends_on:
                if dep_id in upstream_diffs:
                    sections.append(
                        f"## Upstream diff from {dep_id}\n"
                        f"```diff\n{upstream_diffs[dep_id]}\n```"
                    )

        # 6. Verification criteria (so the instance knows what will be checked)
        if unit.verification_criteria.automated:
            checks = "## Verification Criteria\nYour output will be verified by:\n"
            for check in unit.verification_criteria.automated:
                checks += f"- {check.type.value}: {check.target}\n"
            sections.append(checks)

        return "\n\n".join(sections)

    def _format_spec(self, unit: WorkUnit) -> str:
        """Format the work unit spec as a task prompt."""
        lines = [
            f"# Work Unit: {unit.id}",
            f"## Goal: {unit.goal_ref}",
            "",
            f"## Description",
            unit.description,
            "",
            f"## Target Files",
        ]
        for f in unit.formal_spec.target_files:
            lines.append(f"- {f}")

        if unit.formal_spec.expected_outputs:
            lines.append("")
            lines.append("## Expected Outputs")
            for output in unit.formal_spec.expected_outputs:
                constraints = (
                    f" ({', '.join(output.constraints)})" if output.constraints else ""
                )
                lines.append(f"- {output.type.value}: {output.path}{constraints}")

        return "\n".join(lines)

    def _read_file(self, filepath: str, max_size: int) -> Optional[str]:
        """Read a file from the repository.

        Returns None if the file doesn't exist or can't be read.
        Truncates files larger than max_size.
        """
        full_path = os.path.join(self._repo_path, filepath)
        try:
            size = os.path.getsize(full_path)
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                if size > max_size:
                    content = f.read(max_size)
                    content += f"\n... (truncated, {size} bytes total)"
                    return content
                return f.read()
        except (OSError, IOError):
            logger.debug(f"Could not read context file: {filepath}")
            return None
