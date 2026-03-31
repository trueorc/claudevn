"""Reconciliation service — reconciles new directive units against the existing project plan.

Implements the unified project plan model:
- Auto-supersede: draft/ready units with full file overlap are superseded
- Conflict detection: partial overlap or immutable units are flagged
- Cross-goal dependency threading: interface contract matching across directives
"""

import logging
import uuid
from typing import Dict, List, Optional, Set, Tuple

from models.work_unit.reconciliation import (
    ConflictRecord,
    ReconciliationResult,
    SupersessionRecord,
)

logger = logging.getLogger(__name__)

# Statuses that can be superseded (mutable)
_MUTABLE_STATUSES = {"draft", "ready"}

# Statuses that are immutable (cannot be superseded)
_IMMUTABLE_STATUSES = {
    "queued", "executing", "submitted", "verifying",
    "verified", "completed", "failed_verification",
    "retrying", "needs_human_review",
}


class ReconciliationService:
    """Reconciles new work units against the existing project plan.

    Called after the pipeline produces new work units for a directive,
    before they are stored. Detects overlaps, auto-supersedes draft units,
    and flags conflicts for user review.
    """

    def reconcile(
        self,
        project_id: str,
        directive_id: str,
        new_units: List[dict],
        existing_units: List[dict],
    ) -> ReconciliationResult:
        """Reconcile new units against existing project plan.

        Args:
            project_id: Project being reconciled.
            directive_id: The new directive (goal_id) that produced the new units.
            new_units: Work units just produced by the pipeline.
            existing_units: All current units from the project plan (from get_project_units).

        Returns:
            ReconciliationResult with supersessions, conflicts, and unit classifications.
        """
        supersessions: List[SupersessionRecord] = []
        conflicts: List[ConflictRecord] = []
        retained_ids: List[str] = []

        # Filter existing to only active units (not already superseded/cancelled)
        active_existing = [
            u for u in existing_units
            if u.get("status") not in ("superseded", "cancelled")
            and u.get("source_directive_id") != directive_id  # Don't compare against own units
        ]

        # Build file → existing unit mapping
        existing_by_file: Dict[str, List[dict]] = {}
        for u in active_existing:
            for f in u.get("formal_spec", {}).get("target_files", []):
                existing_by_file.setdefault(f, []).append(u)

        # Track which existing units have been processed
        superseded_ids: Set[str] = set()

        for new_unit in new_units:
            new_files = set(new_unit.get("formal_spec", {}).get("target_files", []))
            if not new_files:
                continue

            # Find overlapping existing units
            overlapping: Dict[str, dict] = {}  # unit_id → unit
            for f in new_files:
                for existing in existing_by_file.get(f, []):
                    eid = existing.get("id", "")
                    if eid and eid not in superseded_ids:
                        overlapping[eid] = existing

            for eid, existing in overlapping.items():
                existing_files = set(existing.get("formal_spec", {}).get("target_files", []))
                existing_status = existing.get("status", "draft")
                overlap_files = new_files & existing_files

                if existing_status in _MUTABLE_STATUSES:
                    # Full overlap or superset → auto-supersede
                    if existing_files <= new_files:
                        supersessions.append(SupersessionRecord(
                            old_unit_id=eid,
                            new_unit_id=new_unit.get("id", ""),
                            reason="file_overlap",
                            overlapping_files=sorted(overlap_files),
                        ))
                        superseded_ids.add(eid)
                        # Track on the new unit
                        if "supersedes" not in new_unit:
                            new_unit["supersedes"] = []
                        new_unit["supersedes"].append(eid)
                        logger.info(
                            f"Auto-supersede: {eid} → {new_unit.get('id')} "
                            f"({len(overlap_files)} overlapping files)"
                        )
                    else:
                        # Partial overlap with mutable unit → conflict
                        conflicts.append(ConflictRecord(
                            conflict_id=f"conflict-{uuid.uuid4().hex[:12]}",
                            unit_ids=[eid, new_unit.get("id", "")],
                            description=(
                                f"Partial file overlap: {len(overlap_files)} shared files "
                                f"between existing unit '{eid}' and new unit '{new_unit.get('id')}'"
                            ),
                            severity="medium",
                            resolution_hint=(
                                f"Files: {', '.join(sorted(overlap_files)[:3])}. "
                                f"Consider superseding the old unit or splitting scope."
                            ),
                        ))
                elif existing_status in _IMMUTABLE_STATUSES:
                    # Overlap with immutable unit → always a conflict
                    conflicts.append(ConflictRecord(
                        conflict_id=f"conflict-{uuid.uuid4().hex[:12]}",
                        unit_ids=[eid, new_unit.get("id", "")],
                        description=(
                            f"New unit overlaps with {existing_status} unit '{eid}' "
                            f"({len(overlap_files)} shared files)"
                        ),
                        severity="high",
                        resolution_hint=(
                            f"Unit '{eid}' is {existing_status} and cannot be superseded. "
                            f"Review whether the new unit should wait or target different files."
                        ),
                    ))

        # Existing units not superseded are retained
        retained_ids = [
            u.get("id", "") for u in active_existing
            if u.get("id", "") not in superseded_ids
        ]

        # Rewrite dependencies: any unit depending on a superseded unit
        # should now depend on its replacement instead
        supersession_map = {s.old_unit_id: s.new_unit_id for s in supersessions}
        all_project_units = list(active_existing) + list(new_units)
        for u in all_project_units:
            deps = u.get("independence", {}).get("depends_on", [])
            rewritten = False
            new_deps = []
            for dep_id in deps:
                if dep_id in supersession_map:
                    new_deps.append(supersession_map[dep_id])
                    rewritten = True
                    logger.info(
                        f"Rewriting dependency: {u.get('id')} depends on "
                        f"{dep_id} → {supersession_map[dep_id]} (superseded)"
                    )
                else:
                    new_deps.append(dep_id)
            if rewritten:
                u.get("independence", {})["depends_on"] = new_deps

        # Cross-goal dependency threading
        self._thread_cross_goal_deps(new_units, active_existing, superseded_ids)

        result = ReconciliationResult(
            project_id=project_id,
            directive_id=directive_id,
            supersessions=supersessions,
            conflicts=conflicts,
            new_unit_ids=[u.get("id", "") for u in new_units],
            retained_unit_ids=retained_ids,
        )

        logger.info(
            f"Reconciliation for {directive_id}: "
            f"{len(supersessions)} superseded, {len(conflicts)} conflicts, "
            f"{len(new_units)} new, {len(retained_ids)} retained"
        )

        return result

    def _thread_cross_goal_deps(
        self,
        new_units: List[dict],
        existing_units: List[dict],
        superseded_ids: Set[str],
    ) -> None:
        """Thread cross-goal dependencies via interface contract matching.

        If a new unit consumes an interface that an existing unit produces
        (from a different directive), add a cross-goal dependency.
        """
        # Build produces index from existing active units
        produces_index: Dict[str, str] = {}  # "type:keyword" → unit_id
        for u in existing_units:
            if u.get("id", "") in superseded_ids:
                continue
            for p in u.get("interface_produces", []):
                ptype = p.get("type", "").lower()
                pdef = p.get("definition", "").lower()
                # Index by type + first significant word
                key = f"{ptype}:{pdef[:50]}"
                produces_index[key] = u.get("id", "")

        # Check new units' consumes against the index
        for new_unit in new_units:
            for c in new_unit.get("interface_consumes", []):
                ctype = c.get("type", "").lower()
                cdef = c.get("definition", "").lower()
                key = f"{ctype}:{cdef[:50]}"

                # Exact match
                if key in produces_index:
                    dep_id = produces_index[key]
                    deps = new_unit.get("independence", {}).get("depends_on", [])
                    if dep_id not in deps:
                        deps.append(dep_id)
                        logger.debug(
                            f"Cross-goal dep: {new_unit.get('id')} depends on {dep_id}"
                        )
