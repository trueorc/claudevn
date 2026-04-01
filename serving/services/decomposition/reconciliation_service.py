"""Reconciliation service — reconciles new directive units against the existing project plan.

Implements the unified project plan model:
- Auto-supersede: draft/ready units with full file overlap are superseded mechanically
- LLM-resolved: overlaps with completed/failed/in-flight units go to Claude for
  intelligent resolution — understanding intent, not just file overlap
- Cross-goal dependency threading: interface contract matching across directives

The LLM sees the full context of both units (description, files, acceptance criteria,
interfaces) and decides whether the new unit builds on completed work, replaces a
failed attempt, or genuinely conflicts with in-flight work. Only true exceptions
require user attention.
"""

import json
import logging
import uuid
from typing import Dict, List, Optional, Set, Tuple

from models.work_unit.reconciliation import (
    ConflictRecord,
    ReconciliationResult,
    SupersessionRecord,
)

logger = logging.getLogger(__name__)

# Statuses that can be mechanically superseded (no LLM needed)
_MUTABLE_STATUSES = {"draft", "ready"}

# All other statuses go through LLM resolution
_TERMINAL_STATUSES = {"completed", "verified", "failed", "failed_verification",
                       "needs_review", "merge_conflict", "superseded", "cancelled"}
_IN_FLIGHT_STATUSES = {"queued", "executing", "submitted", "merging",
                        "verifying", "waiting_compute"}


RECONCILIATION_SYSTEM_PROMPT = """You are a software planning assistant resolving overlaps between work units in a project plan.

A new directive has produced work units that overlap (share target files) with existing units. For each overlap pair, decide the correct resolution based on the INTENT of both units, not just file overlap.

For each overlap, choose ONE resolution:

- "proceed": The new unit intentionally builds on or extends the existing completed work. The existing work is merged to main and the new unit will modify those same files further. No conflict — the new unit depends on the completed work being there. This is the MOST COMMON case when a second directive refines or extends earlier work.

- "supersede_old": The existing unit should be superseded by the new one. Use when:
  - The existing unit failed and the new unit is a fresh attempt at the same work
  - The existing unit is draft/ready and the new unit covers the same scope better

- "supersede_new": The new unit is redundant — the existing unit already covers this scope adequately. The new unit should be dropped. Use sparingly.

- "escalate": Genuine conflict that needs human attention. Use ONLY when:
  - The existing unit is actively executing/in-flight AND the new unit would interfere
  - The units have contradictory goals that can't be automatically resolved

Default to "proceed" when in doubt — most overlaps between a new directive and completed work are intentional refinements.

Respond with JSON only:
{
  "resolutions": [
    {
      "overlap_id": "the overlap ID provided",
      "resolution": "proceed | supersede_old | supersede_new | escalate",
      "reasoning": "Brief explanation of why this resolution was chosen",
      "rewrite_deps": true/false  // If true, new unit should depend on the existing completed unit
    }
  ]
}"""


class ReconciliationService:
    """Reconciles new work units against the existing project plan.

    Two-phase approach:
    1. Mechanical: auto-supersede draft/ready units with full file overlap (fast)
    2. Intelligent: overlaps with completed/failed/in-flight units go to Claude
    """

    async def reconcile(
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
            existing_units: All current units from the project plan.

        Returns:
            ReconciliationResult with supersessions, conflicts, and unit classifications.
        """
        supersessions: List[SupersessionRecord] = []
        conflicts: List[ConflictRecord] = []

        # Filter existing to only active units (not already superseded/cancelled)
        active_existing = [
            u for u in existing_units
            if u.get("status") not in ("superseded", "cancelled")
            and u.get("source_directive_id") != directive_id
        ]

        # Build file → existing unit mapping
        existing_by_file: Dict[str, List[dict]] = {}
        for u in active_existing:
            for f in u.get("formal_spec", {}).get("target_files", []):
                existing_by_file.setdefault(f, []).append(u)

        superseded_ids: Set[str] = set()
        llm_overlaps: List[dict] = []  # Overlaps needing LLM resolution

        # Phase 1: Mechanical resolution for mutable units
        for new_unit in new_units:
            new_files = set(new_unit.get("formal_spec", {}).get("target_files", []))
            if not new_files:
                continue

            overlapping: Dict[str, dict] = {}
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
                    # Full overlap → auto-supersede (no LLM needed)
                    if existing_files <= new_files:
                        supersessions.append(SupersessionRecord(
                            old_unit_id=eid,
                            new_unit_id=new_unit.get("id", ""),
                            reason="file_overlap",
                            overlapping_files=sorted(overlap_files),
                        ))
                        superseded_ids.add(eid)
                        if "supersedes" not in new_unit:
                            new_unit["supersedes"] = []
                        new_unit["supersedes"].append(eid)
                        logger.info(f"Auto-supersede (mutable): {eid} → {new_unit.get('id')}")
                    else:
                        # Partial overlap with mutable — still send to LLM for smarter resolution
                        llm_overlaps.append({
                            "overlap_id": f"overlap-{uuid.uuid4().hex[:8]}",
                            "new_unit": new_unit,
                            "existing_unit": existing,
                            "overlap_files": sorted(overlap_files),
                        })
                else:
                    # Completed, failed, in-flight — needs intelligent resolution
                    llm_overlaps.append({
                        "overlap_id": f"overlap-{uuid.uuid4().hex[:8]}",
                        "new_unit": new_unit,
                        "existing_unit": existing,
                        "overlap_files": sorted(overlap_files),
                    })

        # Phase 2: LLM resolution for non-trivial overlaps
        if llm_overlaps:
            llm_results = await self._resolve_with_llm(llm_overlaps)
            for overlap, resolution in zip(llm_overlaps, llm_results):
                new_unit = overlap["new_unit"]
                existing = overlap["existing_unit"]
                eid = existing.get("id", "")
                action = resolution.get("resolution", "proceed")
                reasoning = resolution.get("reasoning", "")
                rewrite = resolution.get("rewrite_deps", False)

                if action == "proceed":
                    # New unit builds on existing — no conflict
                    # Optionally add dependency on the completed unit
                    if rewrite and eid:
                        deps = new_unit.get("independence", {}).get("depends_on", [])
                        if eid not in deps:
                            deps.append(eid)
                            logger.info(f"LLM: added dep {new_unit.get('id')} → {eid} ({reasoning})")
                    logger.info(f"LLM: proceed — {new_unit.get('id')} builds on {eid} ({reasoning})")

                elif action == "supersede_old":
                    if eid not in superseded_ids:
                        supersessions.append(SupersessionRecord(
                            old_unit_id=eid,
                            new_unit_id=new_unit.get("id", ""),
                            reason="llm_determined",
                            overlapping_files=overlap["overlap_files"],
                        ))
                        superseded_ids.add(eid)
                        if "supersedes" not in new_unit:
                            new_unit["supersedes"] = []
                        new_unit["supersedes"].append(eid)
                        logger.info(f"LLM: supersede {eid} → {new_unit.get('id')} ({reasoning})")

                elif action == "supersede_new":
                    # Mark the new unit as superseded by the existing one
                    new_unit["status"] = "superseded"
                    new_unit["superseded_by"] = eid
                    logger.info(f"LLM: drop new unit {new_unit.get('id')} — {eid} covers it ({reasoning})")

                elif action == "escalate":
                    conflicts.append(ConflictRecord(
                        conflict_id=f"conflict-{uuid.uuid4().hex[:12]}",
                        unit_ids=[eid, new_unit.get("id", "")],
                        description=reasoning,
                        severity="high",
                        resolution_hint=reasoning,
                    ))
                    logger.warning(f"LLM: escalate — {eid} vs {new_unit.get('id')} ({reasoning})")

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
                        f"Dep rewrite: {u.get('id')} {dep_id} → {supersession_map[dep_id]}"
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

    async def _resolve_with_llm(self, overlaps: List[dict]) -> List[dict]:
        """Call Claude to resolve non-trivial overlaps.

        Returns a list of resolution dicts, one per overlap, in the same order.
        Falls back to heuristic resolution if the LLM call fails.
        """
        prompt = self._build_resolution_prompt(overlaps)

        try:
            from services.claude_client import get_claude_client
            client = get_claude_client()
            response = await client.complete(
                prompt=prompt,
                system=RECONCILIATION_SYSTEM_PROMPT,
                model="haiku",  # Fast + cheap — resolutions are straightforward
            )
            return self._parse_resolution_response(response.content, overlaps)
        except Exception as e:
            logger.error(f"LLM reconciliation failed, using heuristics: {e}")
            return self._heuristic_fallback(overlaps)

    def _build_resolution_prompt(self, overlaps: List[dict]) -> str:
        """Build the prompt with full context for each overlap pair."""
        parts = ["Resolve the following overlaps between new and existing work units:\n"]

        for o in overlaps:
            new = o["new_unit"]
            old = o["existing_unit"]
            oid = o["overlap_id"]

            new_desc = new.get("description", "")
            new_files = ", ".join(new.get("formal_spec", {}).get("target_files", [])[:8])
            new_criteria = "; ".join((new.get("acceptance_criteria") or [])[:4])

            old_desc = old.get("description", "")
            old_status = old.get("status", "unknown")
            old_files = ", ".join(old.get("formal_spec", {}).get("target_files", [])[:8])
            old_criteria = "; ".join((old.get("acceptance_criteria") or [])[:4])

            overlap_files = ", ".join(o["overlap_files"][:5])

            parts.append(f"""---
Overlap ID: {oid}

EXISTING UNIT [{old.get('id', '?')}] (status: {old_status}):
  Description: {old_desc}
  Files: {old_files}
  Criteria: {old_criteria or 'none'}

NEW UNIT [{new.get('id', '?')}]:
  Description: {new_desc}
  Files: {new_files}
  Criteria: {new_criteria or 'none'}

Overlapping files: {overlap_files}
""")

        return "\n".join(parts)

    def _parse_resolution_response(self, content: str, overlaps: List[dict]) -> List[dict]:
        """Parse LLM response into resolution dicts."""
        try:
            # Handle markdown code blocks
            text = content.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            data = json.loads(text)
            resolutions = data.get("resolutions", [])

            # Index by overlap_id
            by_id = {r.get("overlap_id"): r for r in resolutions}

            result = []
            for o in overlaps:
                oid = o["overlap_id"]
                if oid in by_id:
                    r = by_id[oid]
                    # Validate resolution value
                    if r.get("resolution") not in ("proceed", "supersede_old", "supersede_new", "escalate"):
                        r["resolution"] = "proceed"
                    result.append(r)
                else:
                    # Missing from response — default to proceed
                    result.append({"resolution": "proceed", "reasoning": "default (not in LLM response)", "rewrite_deps": False})

            return result

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse LLM reconciliation response: {e}")
            return self._heuristic_fallback(overlaps)

    def _heuristic_fallback(self, overlaps: List[dict]) -> List[dict]:
        """Fallback when LLM is unavailable — simple status-based heuristics."""
        results = []
        for o in overlaps:
            status = o["existing_unit"].get("status", "unknown")
            if status in ("completed", "verified"):
                results.append({"resolution": "proceed", "reasoning": "heuristic: existing completed, new builds on top", "rewrite_deps": False})
            elif status in ("failed", "failed_verification", "needs_review", "merge_conflict"):
                results.append({"resolution": "supersede_old", "reasoning": "heuristic: existing failed, new replaces it", "rewrite_deps": False})
            else:
                results.append({"resolution": "escalate", "reasoning": f"heuristic: existing is {status}, needs review", "rewrite_deps": False})
        return results

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
                key = f"{ptype}:{pdef[:50]}"
                produces_index[key] = u.get("id", "")

        # Check new units' consumes against the index
        for new_unit in new_units:
            for c in new_unit.get("interface_consumes", []):
                ctype = c.get("type", "").lower()
                cdef = c.get("definition", "").lower()
                key = f"{ctype}:{cdef[:50]}"

                if key in produces_index:
                    dep_id = produces_index[key]
                    deps = new_unit.get("independence", {}).get("depends_on", [])
                    if dep_id not in deps:
                        deps.append(dep_id)
                        logger.debug(
                            f"Cross-goal dep: {new_unit.get('id')} depends on {dep_id}"
                        )
