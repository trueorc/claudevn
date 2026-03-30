"""Quality scoring service for decomposition assessment.

Implements Planning System Specification Section 5:
- Per-unit quality scores (0-100) with 5 weighted factors
- Overall decomposition confidence (0-100) with 6 weighted factors
- Traffic light indicator (Green >= 75, Yellow 50-74, Red < 50)
- Split/merge recommendations
"""

import logging
import re
from typing import Dict, List, Tuple

from models.work_unit import WorkUnit
from models.work_unit.quality_score import (
    ConfidenceLevel,
    DecompositionConfidence,
    RecommendationType,
    ScoringFactor,
    SplitMergeRecommendation,
    UnitQualityScore,
)

logger = logging.getLogger(__name__)

# Vague words that indicate non-testable acceptance criteria
VAGUE_WORDS = re.compile(
    r"\b(works?|correct(?:ly)?|proper(?:ly)?|good|nice|appropriate(?:ly)?|"
    r"should work|functions? correctly|as expected)\b",
    re.IGNORECASE,
)


class QualityScorer:
    """Scores decomposition quality at per-unit and aggregate levels.

    Per-unit scoring (Section 5.1):
      - Independence (25%): 100 if no shared files, -50 per overlap
      - Acceptance criteria quality (25%): 20 per testable criterion, max 100
      - Interface completeness (20%): produces/consumes defined for dependent units
      - Complexity appropriateness (15%): smaller is better
      - Target file specificity (15%): extensions and paths present

    Overall confidence (Section 5.2):
      - Average unit score (30%)
      - Independence rate (20%)
      - Dependency validity (15%)
      - Acceptance criteria coverage (15%)
      - Interface chain completeness (10%)
      - Validation errors (10%)
    """

    def score(
        self,
        units: List[WorkUnit],
        validation_issues: List[dict] = None,
    ) -> DecompositionConfidence:
        """Score a full decomposition.

        Args:
            units: Work units to score.
            validation_issues: Issues from SpecValidator (for error counting).

        Returns:
            DecompositionConfidence with per-unit scores and aggregate confidence.
        """
        if not units:
            return DecompositionConfidence(
                score=0,
                level=ConfidenceLevel.RED,
            )

        validation_issues = validation_issues or []

        # Build shared state for scoring
        file_owners = self._build_file_ownership(units)
        unit_map = {u.id: u for u in units}

        # Score each unit
        unit_scores = []
        for unit in units:
            score = self._score_unit(unit, file_owners, unit_map)
            unit_scores.append(score)

        # Aggregate confidence
        confidence = self._compute_confidence(
            units, unit_scores, file_owners, unit_map, validation_issues,
        )
        confidence.unit_scores = unit_scores

        # Recommendations
        confidence.recommendations = self._generate_recommendations(units, unit_scores)

        return confidence

    def _score_unit(
        self,
        unit: WorkUnit,
        file_owners: Dict[str, List[str]],
        unit_map: Dict[str, WorkUnit],
    ) -> UnitQualityScore:
        """Score a single work unit across 5 factors."""
        factors = []

        # Factor 1: Independence (25%)
        overlap_count = len(unit.independence.shares_files_with)
        independence_score = max(0, 100 - (overlap_count * 50))
        detail = "No file overlaps" if overlap_count == 0 else f"{overlap_count} shared file(s)"
        factors.append(ScoringFactor(
            name="independence", weight=0.25, score=independence_score, detail=detail,
        ))

        # Factor 2: Acceptance criteria quality (25%)
        criteria_score, criteria_detail = self._score_acceptance_criteria(unit)
        factors.append(ScoringFactor(
            name="acceptance_criteria", weight=0.25, score=criteria_score, detail=criteria_detail,
        ))

        # Factor 3: Interface completeness (20%)
        interface_score, interface_detail = self._score_interface_completeness(unit, unit_map)
        factors.append(ScoringFactor(
            name="interface_completeness", weight=0.20, score=interface_score, detail=interface_detail,
        ))

        # Factor 4: Complexity appropriateness (15%)
        complexity_score, complexity_detail = self._score_complexity(unit)
        factors.append(ScoringFactor(
            name="complexity", weight=0.15, score=complexity_score, detail=complexity_detail,
        ))

        # Factor 5: Target file specificity (15%)
        file_score, file_detail = self._score_target_files(unit)
        factors.append(ScoringFactor(
            name="target_files", weight=0.15, score=file_score, detail=file_detail,
        ))

        # Weighted total
        total = int(round(sum(f.weight * f.score for f in factors)))

        return UnitQualityScore(
            unit_id=unit.id,
            score=total,
            factors=factors,
        )

    def _score_acceptance_criteria(self, unit: WorkUnit) -> Tuple[int, str]:
        """Score acceptance criteria: 20 points per testable criterion, max 100."""
        criteria = unit.acceptance_criteria or []
        if not criteria:
            return 0, "No acceptance criteria"

        testable = 0
        vague = 0
        for c in criteria:
            if VAGUE_WORDS.search(c):
                vague += 1
            else:
                testable += 1

        score = min(100, testable * 20)
        parts = [f"{testable} testable"]
        if vague > 0:
            parts.append(f"{vague} vague")
        return score, ", ".join(parts)

    def _score_interface_completeness(
        self, unit: WorkUnit, unit_map: Dict[str, WorkUnit],
    ) -> Tuple[int, str]:
        """Score interface contract completeness.

        100 if both produces and consumes are defined for dependent units.
        Non-dependent units (no deps and no dependents) get 100 by default.
        """
        has_deps = len(unit.independence.depends_on) > 0
        has_dependents = len(unit.independence.depended_by) > 0

        if not has_deps and not has_dependents:
            return 100, "Independent unit"

        score = 100
        issues = []

        # If this unit has dependents, it should produce something
        if has_dependents and not unit.interface_produces:
            score -= 50
            issues.append("no produces for dependents")

        # If this unit has dependencies, it should consume something
        if has_deps and not unit.interface_consumes:
            score -= 50
            issues.append("no consumes for dependencies")

        detail = "Interfaces defined" if not issues else "; ".join(issues)
        return max(0, score), detail

    def _score_complexity(self, unit: WorkUnit) -> Tuple[int, str]:
        """Score complexity appropriateness: smaller units are better."""
        complexity_scores = {
            "xs": 100,
            "s": 100,
            "m": 80,
            "l": 50,
            "xl": 20,
        }
        c = (unit.estimated_complexity or "m").lower()
        score = complexity_scores.get(c, 80)
        detail = f"Complexity: {c.upper()}"
        if score < 80:
            detail += " — consider splitting"
        return score, detail

    def _score_target_files(self, unit: WorkUnit) -> Tuple[int, str]:
        """Score target file specificity: extensions and real paths."""
        files = unit.formal_spec.target_files or []
        if not files:
            return 0, "No target files"

        specific = 0
        for f in files:
            # Has extension and at least one directory separator
            has_ext = "." in f.split("/")[-1]
            has_path = "/" in f
            if has_ext and has_path:
                specific += 1
            elif has_ext:
                specific += 0.5

        ratio = specific / len(files) if files else 0
        score = int(round(ratio * 100))
        return score, f"{int(specific)}/{len(files)} files with full paths"

    def _compute_confidence(
        self,
        units: List[WorkUnit],
        unit_scores: List[UnitQualityScore],
        file_owners: Dict[str, List[str]],
        unit_map: Dict[str, WorkUnit],
        validation_issues: List[dict],
    ) -> DecompositionConfidence:
        """Compute overall decomposition confidence (Section 5.2)."""
        factors = []
        n = len(units)

        # Factor 1: Average unit score (30%)
        avg_score = int(round(sum(s.score for s in unit_scores) / n))
        factors.append(ScoringFactor(
            name="average_unit_score", weight=0.30, score=avg_score,
            detail=f"Mean: {avg_score}/100 across {n} units",
        ))

        # Factor 2: Independence rate (20%)
        independent = sum(1 for u in units if not u.independence.shares_files_with)
        independence_pct = int(round(independent / n * 100))
        factors.append(ScoringFactor(
            name="independence_rate", weight=0.20, score=independence_pct,
            detail=f"{independent}/{n} units with no file overlaps",
        ))

        # Factor 3: Dependency validity (15%)
        all_ids = {u.id for u in units}
        total_deps = 0
        valid_deps = 0
        for u in units:
            for dep in u.independence.depends_on:
                total_deps += 1
                if dep in all_ids:
                    valid_deps += 1
        dep_pct = int(round(valid_deps / total_deps * 100)) if total_deps > 0 else 100
        factors.append(ScoringFactor(
            name="dependency_validity", weight=0.15, score=dep_pct,
            detail=f"{valid_deps}/{total_deps} deps resolved" if total_deps > 0 else "No dependencies",
        ))

        # Factor 4: Acceptance criteria coverage (15%)
        with_criteria = sum(1 for u in units if len(u.acceptance_criteria or []) >= 2)
        criteria_pct = int(round(with_criteria / n * 100))
        factors.append(ScoringFactor(
            name="criteria_coverage", weight=0.15, score=criteria_pct,
            detail=f"{with_criteria}/{n} units with 2+ criteria",
        ))

        # Factor 5: Interface chain completeness (10%)
        chain_score = self._score_interface_chains(units, unit_map)
        factors.append(ScoringFactor(
            name="interface_chains", weight=0.10, score=chain_score,
            detail="Upstream produces match downstream consumes",
        ))

        # Factor 6: Validation errors (10%)
        error_count = sum(1 for i in validation_issues if i.get("severity") == "error")
        error_score = max(0, 100 - (error_count * 20))
        factors.append(ScoringFactor(
            name="validation_errors", weight=0.10, score=error_score,
            detail=f"{error_count} errors" if error_count > 0 else "No errors",
        ))

        total = int(round(sum(f.weight * f.score for f in factors)))

        if total >= 75:
            level = ConfidenceLevel.GREEN
        elif total >= 50:
            level = ConfidenceLevel.YELLOW
        else:
            level = ConfidenceLevel.RED

        return DecompositionConfidence(score=total, level=level, factors=factors)

    def _score_interface_chains(
        self, units: List[WorkUnit], unit_map: Dict[str, WorkUnit],
    ) -> int:
        """Check that upstream units produce what downstream units consume."""
        chain_pairs = 0
        chain_matches = 0

        for unit in units:
            for dep_id in unit.independence.depends_on:
                dep = unit_map.get(dep_id)
                if not dep:
                    continue
                chain_pairs += 1
                # Does the upstream unit produce anything?
                if dep.interface_produces and unit.interface_consumes:
                    chain_matches += 1

        if chain_pairs == 0:
            return 100
        return int(round(chain_matches / chain_pairs * 100))

    def _generate_recommendations(
        self,
        units: List[WorkUnit],
        unit_scores: List[UnitQualityScore],
    ) -> List[SplitMergeRecommendation]:
        """Generate split/merge recommendations (Section 5.3)."""
        recs = []
        score_map = {s.unit_id: s for s in unit_scores}

        for unit in units:
            c = (unit.estimated_complexity or "m").lower()
            files = unit.formal_spec.target_files or []
            criteria = unit.acceptance_criteria or []

            # Split candidates
            reasons = []
            if c in ("l", "xl"):
                reasons.append(f"complexity {c.upper()}")
            if len(files) > 6:
                reasons.append(f"{len(files)} target files")
            if len(criteria) > 4:
                reasons.append(f"{len(criteria)} acceptance criteria")

            if reasons:
                recs.append(SplitMergeRecommendation(
                    type=RecommendationType.SPLIT,
                    unit_ids=[unit.id],
                    reason=f"Consider splitting: {', '.join(reasons)}",
                    detail=unit.description,
                ))

        # Merge candidates: adjacent XS units in the same module with no other dependents
        xs_units = [u for u in units if (u.estimated_complexity or "").lower() == "xs"]
        if len(xs_units) >= 2:
            # Group by directory prefix
            dir_groups: Dict[str, List[WorkUnit]] = {}
            for u in xs_units:
                files = u.formal_spec.target_files or []
                if files:
                    prefix = "/".join(files[0].split("/")[:-1])
                    dir_groups.setdefault(prefix, []).append(u)

            for prefix, group in dir_groups.items():
                if len(group) >= 2:
                    # Only recommend merge if units have no other dependents
                    group_ids = {u.id for u in group}
                    mergeable = all(
                        all(d in group_ids for d in u.independence.depended_by)
                        for u in group
                    )
                    if mergeable:
                        recs.append(SplitMergeRecommendation(
                            type=RecommendationType.MERGE,
                            unit_ids=[u.id for u in group],
                            reason=f"Adjacent XS units in {prefix or 'root'}",
                            detail="; ".join(u.description for u in group),
                        ))

        return recs

    def _build_file_ownership(self, units: List[WorkUnit]) -> Dict[str, List[str]]:
        """Map files to the work units that target them."""
        ownership: Dict[str, List[str]] = {}
        for u in units:
            for f in u.formal_spec.target_files:
                ownership.setdefault(f, []).append(u.id)
        return ownership
