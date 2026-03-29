"""Work unit builder — produces formal work unit specs from decomposition.

This is the core of v2.0 decomposition. Takes a goal + codebase analysis
and produces WorkUnit objects with formal specs, verification criteria,
context packages, and independence assertions.

The LLM assists with scope identification and description; the builder
structures the output into the formal WorkUnit schema.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.work_unit import (
    WorkUnit,
    WorkUnitStatus,
    FormalSpec,
    InterfaceContract,
    ExpectedOutput,
    OutputType,
    VerificationCriteria,
    AutomatedCheck,
    AutomatedCheckType,
    ContextPackage,
    IndependenceAssertion,
)
from .goal_analyzer import CodebaseAnalysis

logger = logging.getLogger(__name__)


def generate_work_unit_id() -> str:
    """Generate a unique work unit ID."""
    return f"wu-{uuid.uuid4().hex[:12]}"


class WorkUnitBuilder:
    """Builds formal WorkUnit specs from decomposition input.

    Takes structured decomposition data (from LLM-assisted analysis)
    and produces fully specified WorkUnit objects. Handles:
    - Formal spec construction (target files, interfaces, expected outputs)
    - Verification criteria generation
    - Context package assembly
    - Independence assertion computation
    """

    def __init__(self, codebase: CodebaseAnalysis):
        self._codebase = codebase
        self._test_file_index = set(codebase.test_files)

    def build(
        self,
        project_id: str,
        goal_id: str,
        description: str,
        target_files: List[str],
        input_state: str = "main",
        interface_contracts: Optional[List[Dict[str, str]]] = None,
        expected_outputs: Optional[List[Dict[str, Any]]] = None,
        depends_on: Optional[List[str]] = None,
        acceptance_criteria: Optional[List[str]] = None,
        estimated_complexity: Optional[str] = None,
    ) -> WorkUnit:
        """Build a single WorkUnit from decomposition data.

        Args:
            project_id: Project this work unit belongs to.
            goal_id: Parent goal reference.
            description: Natural language description.
            target_files: Files this unit will modify.
            input_state: Git ref to start from.
            interface_contracts: Interface boundaries to respect.
            expected_outputs: Expected file-level changes.
            depends_on: Work unit IDs this depends on.

        Returns:
            A fully specified WorkUnit in DRAFT status.
        """
        unit_id = generate_work_unit_id()

        # Build formal spec
        formal_spec = self._build_formal_spec(
            target_files=target_files,
            input_state=input_state,
            interface_contracts=interface_contracts or [],
            expected_outputs=expected_outputs or [],
        )

        # Generate verification criteria from target files
        verification = self._generate_verification_criteria(
            target_files=target_files,
            unit_id=unit_id,
        )

        # Assemble context package
        context = self._assemble_context_package(
            target_files=target_files,
        )

        # Build independence assertion
        independence = IndependenceAssertion(
            depends_on=depends_on or [],
        )

        # Parse interface contracts from LLM format
        produces = []
        consumes = []
        if interface_contracts:
            # LLM returns {produces: [...], consumes: [...]} or flat list
            if isinstance(interface_contracts, dict):
                produces = interface_contracts.get("produces", [])
                consumes = interface_contracts.get("consumes", [])
            elif isinstance(interface_contracts, list):
                # Legacy flat list format
                pass

        return WorkUnit(
            id=unit_id,
            project_id=project_id,
            goal_ref=goal_id,
            description=description,
            formal_spec=formal_spec,
            verification_criteria=verification,
            context_package=context,
            independence=independence,
            acceptance_criteria=acceptance_criteria or [],
            estimated_complexity=estimated_complexity or "m",
            interface_produces=produces,
            interface_consumes=consumes,
            status=WorkUnitStatus.DRAFT,
        )

    def build_batch(
        self,
        project_id: str,
        goal_id: str,
        units_data: List[Dict[str, Any]],
        input_state: str = "main",
    ) -> List[WorkUnit]:
        """Build multiple WorkUnits and compute cross-unit independence.

        Args:
            project_id: Project these work units belong to.
            goal_id: Parent goal reference.
            units_data: List of dicts with keys: description, target_files,
                interface_contracts, expected_outputs, depends_on.
            input_state: Git ref to start from.

        Returns:
            List of WorkUnits with independence assertions computed.
        """
        units = []
        for data in units_data:
            unit = self.build(
                project_id=project_id,
                goal_id=goal_id,
                description=data["description"],
                target_files=data.get("target_files", []),
                input_state=input_state,
                interface_contracts=data.get("interface_contracts"),
                expected_outputs=data.get("expected_outputs"),
                depends_on=data.get("depends_on"),
                acceptance_criteria=data.get("acceptance_criteria"),
                estimated_complexity=data.get("estimated_complexity"),
            )
            units.append(unit)

        # Compute cross-unit file sharing
        self._compute_file_sharing(units)

        # Compute depended_by from depends_on
        self._compute_reverse_dependencies(units)

        return units

    def _build_formal_spec(
        self,
        target_files: List[str],
        input_state: str,
        interface_contracts: List[Dict[str, str]],
        expected_outputs: List[Dict[str, Any]],
    ) -> FormalSpec:
        """Construct a FormalSpec from decomposition data."""
        contracts = []
        # interface_contracts may be a dict (v2.0 LLM format: {produces, consumes})
        # or a list (legacy format: [{file, type, definition}])
        if isinstance(interface_contracts, list):
            for c in interface_contracts:
                if isinstance(c, dict) and "file" in c:
                    contracts.append(InterfaceContract(
                        file=c["file"],
                        type=c.get("type", "exports"),
                        definition=c.get("definition", ""),
                    ))
        # Dict format is handled by build() → interface_produces/consumes

        outputs = []
        for o in expected_outputs:
            outputs.append(ExpectedOutput(
                type=o.get("type", OutputType.FILE_MODIFIED),
                path=o["path"],
                constraints=o.get("constraints", []),
            ))

        # Default: infer output type from whether file exists in the codebase
        if not outputs:
            known_files = {fi.path for fi in self._codebase.file_tree} if self._codebase.file_tree else set()
            for f in target_files:
                output_type = OutputType.FILE_MODIFIED if f in known_files else OutputType.FILE_CREATED
                outputs.append(ExpectedOutput(type=output_type, path=f))

        return FormalSpec(
            target_files=target_files,
            input_state=input_state,
            interface_contracts=contracts,
            expected_outputs=outputs,
        )

    def _generate_verification_criteria(
        self,
        target_files: List[str],
        unit_id: str,
    ) -> VerificationCriteria:
        """Generate verification criteria based on target files.

        Automatically includes:
        - Build success check
        - Existing test files related to target files
        - Type check for typed languages
        """
        checks = []

        # Always check build success
        checks.append(AutomatedCheck(
            type=AutomatedCheckType.BUILD_SUCCESS,
            target=".",
        ))

        # Find related test files
        for target in target_files:
            related_tests = self._find_related_tests(target)
            for test_file in related_tests:
                checks.append(AutomatedCheck(
                    type=AutomatedCheckType.TEST_PASS,
                    target=test_file,
                ))

        # Add lint check
        checks.append(AutomatedCheck(
            type=AutomatedCheckType.LINT_CLEAN,
            target=".",
        ))

        return VerificationCriteria(automated=checks)

    def _assemble_context_package(
        self,
        target_files: List[str],
    ) -> ContextPackage:
        """Assemble the context package for a work unit.

        Includes the target files themselves plus related test files.
        The context assembler in Layer 2 will expand this with file
        contents at dispatch time.
        """
        relevant_tests = []
        for target in target_files:
            relevant_tests.extend(self._find_related_tests(target))

        return ContextPackage(
            files=list(target_files),
            relevant_tests=list(set(relevant_tests)),
        )

    def _find_related_tests(self, file_path: str) -> List[str]:
        """Find test files related to a source file.

        Uses naming conventions: foo.py -> test_foo.py, foo_test.py,
        tests/test_foo.py, etc.
        """
        import os
        base = os.path.splitext(os.path.basename(file_path))[0]
        dirname = os.path.dirname(file_path)

        candidates = [
            f"test_{base}.py",
            f"{base}_test.py",
            f"tests/test_{base}.py",
            f"{dirname}/test_{base}.py",
            f"{dirname}/tests/test_{base}.py",
            f"{base}.test.js",
            f"{base}.test.ts",
            f"{base}.test.tsx",
            f"{base}.spec.js",
            f"{base}.spec.ts",
        ]

        return [c for c in candidates if c in self._test_file_index]

    def _compute_file_sharing(self, units: List[WorkUnit]) -> None:
        """Compute which units share files (should be empty for good decomposition)."""
        # Build file -> unit mapping
        file_to_units: Dict[str, List[str]] = {}
        for unit in units:
            for f in unit.formal_spec.target_files:
                file_to_units.setdefault(f, []).append(unit.id)

        # Flag overlaps
        for unit in units:
            sharing_with: set = set()
            for f in unit.formal_spec.target_files:
                owners = file_to_units.get(f, [])
                for owner_id in owners:
                    if owner_id != unit.id:
                        sharing_with.add(owner_id)
            unit.independence.shares_files_with = sorted(sharing_with)

    def _compute_reverse_dependencies(self, units: List[WorkUnit]) -> None:
        """Compute depended_by from depends_on relationships."""
        unit_map = {u.id: u for u in units}
        for unit in units:
            for dep_id in unit.independence.depends_on:
                if dep_id in unit_map:
                    dep_unit = unit_map[dep_id]
                    if unit.id not in dep_unit.independence.depended_by:
                        dep_unit.independence.depended_by.append(unit.id)
