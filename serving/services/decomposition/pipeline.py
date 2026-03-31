"""v2.0 Decomposition Pipeline — orchestrates the full Layer 1 flow.

Chains: LLM decomposition → GoalAnalyzer → WorkUnitBuilder →
SpecValidator → EnvironmentAnalyzer, emitting events at each step
for real-time observability on the Plan page.

Replaces the v1.0 GoalDecomposerService flow entirely.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.work_unit import (
    WorkUnit,
    WorkUnitStatus,
    ComputeEnvironmentSpec,
    CoherenceAnalysis,
)
from models.goal_decomposer import (
    DecomposedIssue,
    GoalDecompositionResult,
    DECOMPOSITION_SCHEMA,
)
from services.events.event_bus import get_event_bus
from services.events.event_types import (
    DecompositionStarted,
    DecompositionUpdated,
    DecompositionCompleted,
    DecompositionStepStarted,
    DecompositionStepCompleted,
    DecompositionStepFailed,
    PlanReconciled,
    WorkUnitSuperseded,
)
from .goal_analyzer import GoalAnalyzer
from .work_unit_builder import WorkUnitBuilder
from .spec_validator import SpecValidator
from .environment_analyzer import EnvironmentAnalyzer
from .quality_scorer import QualityScorer
from .chain_analyzer import ChainAnalyzer
from .reconciliation_service import ReconciliationService

logger = logging.getLogger(__name__)


class PipelineStep:
    """Result of a single pipeline step for observability."""
    def __init__(self, name: str):
        self.name = name
        self.status = "pending"  # pending, running, completed, failed
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.detail = ""
        self.error = ""

    def start(self):
        self.status = "running"
        self.started_at = datetime.now(timezone.utc)

    def complete(self, detail: str = ""):
        self.status = "completed"
        self.completed_at = datetime.now(timezone.utc)
        self.detail = detail

    def fail(self, error: str):
        self.status = "failed"
        self.completed_at = datetime.now(timezone.utc)
        self.error = error

    def to_dict(self):
        return {
            "name": self.name,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "detail": self.detail,
            "error": self.error,
            "duration_ms": int((self.completed_at - self.started_at).total_seconds() * 1000) if self.started_at and self.completed_at else None,
        }


class PipelineResult:
    """Complete result of the decomposition pipeline."""
    def __init__(self):
        self.steps: List[PipelineStep] = []
        self.work_units: List[WorkUnit] = []
        self.environment: Optional[ComputeEnvironmentSpec] = None
        self.validation_issues: List[dict] = []
        self.quality_scores: Optional[dict] = None
        self.chain_analysis: Optional[dict] = None
        self.reconciliation: Optional[dict] = None
        self.success = False
        self.error = ""

    def to_dict(self):
        # Use model_dump_json → json.loads to handle datetime serialization
        return {
            "steps": [s.to_dict() for s in self.steps],
            "work_unit_count": len(self.work_units),
            "work_units": [
                json.loads(wu.model_dump_json()) for wu in self.work_units
            ],
            "environment": json.loads(self.environment.model_dump_json()) if self.environment else None,
            "validation_issues": self.validation_issues,
            "quality_scores": self.quality_scores,
            "chain_analysis": self.chain_analysis,
            "reconciliation": self.reconciliation,
            "success": self.success,
            "error": self.error,
        }


class DecompositionPipeline:
    """v2.0 decomposition pipeline — replaces v1.0 GoalDecomposerService.

    Each step emits events for real-time Plan page observability.
    Steps:
    1. llm_decompose — Claude breaks goal into structured units (with project context)
    2. codebase_analysis — static analysis of the repo
    3. build_work_units — formal spec construction
    4. resolve_dependencies — map description-based deps to unit IDs
    5. reconcile_plan — reconcile against existing project plan (supersede/conflict)
    6. validate — independence checking, cycle detection
    7. score_quality — per-unit scores + overall confidence
    8. analyze_environment — detect runtime requirements, generate Dockerfile
    """

    def __init__(self, repo_path: str = "."):
        self._repo_path = repo_path
        self._bus = get_event_bus()

    async def run(
        self,
        goal_id: str,
        project_id: str,
        goal_text: str,
        project_context: Optional[Dict[str, Any]] = None,
        existing_issues: Optional[list] = None,
        conversation_comments: Optional[list] = None,
        existing_project_units: Optional[List[Dict[str, Any]]] = None,
    ) -> PipelineResult:
        """Run the full decomposition pipeline.

        Args:
            goal_id: Goal being decomposed.
            project_id: Project context.
            goal_text: Natural language goal description.
            project_context: Tech stack, conventions, etc.
            existing_issues: Current backlog for awareness.
            conversation_comments: Goal comments for context.

        Returns:
            PipelineResult with work units, environment spec, and step status.
        """
        result = PipelineResult()

        # Emit start event
        await self._bus.publish(DecompositionStarted(
            project_id=project_id,
            goal_id=goal_id,
            goal_description=goal_text[:200],
        ))

        # Step 1: LLM decomposition
        step1 = PipelineStep("llm_decompose")
        result.steps.append(step1)
        step1.start()
        await self._emit_step_started(project_id, goal_id, step1)
        try:
            raw_units = await self._llm_decompose(goal_id, goal_text, project_context, existing_issues, conversation_comments, existing_project_units)
            step1.complete(f"{len(raw_units)} units from LLM")
            await self._emit_step_completed(project_id, goal_id, step1)
        except Exception as e:
            step1.fail(str(e))
            await self._emit_step_failed(project_id, goal_id, step1)
            result.error = f"LLM decomposition failed: {e}"
            logger.error(f"Pipeline step 1 failed for {goal_id}: {e}")
            await self._emit_update(project_id, goal_id, [], "failed")
            return result

        # Step 2: Codebase analysis
        step2 = PipelineStep("codebase_analysis")
        result.steps.append(step2)
        step2.start()
        await self._emit_step_started(project_id, goal_id, step2)
        try:
            analyzer = GoalAnalyzer(self._repo_path)
            codebase = await analyzer.analyze(max_files=2000)
            step2.complete(f"{codebase.total_files} files, {len(codebase.modules)} modules")
            await self._emit_step_completed(project_id, goal_id, step2)
        except Exception as e:
            step2.fail(str(e))
            await self._emit_step_failed(project_id, goal_id, step2)
            codebase = None
            logger.warning(f"Pipeline step 2 failed (non-fatal) for {goal_id}: {e}")

        # Step 3: Build formal work units
        step3 = PipelineStep("build_work_units")
        result.steps.append(step3)
        step3.start()
        await self._emit_step_started(project_id, goal_id, step3)
        try:
            from .goal_analyzer import CodebaseAnalysis
            builder = WorkUnitBuilder(codebase or CodebaseAnalysis())
            work_units = builder.build_batch(
                project_id=project_id,
                goal_id=goal_id,
                units_data=raw_units,
            )
            result.work_units = work_units
            step3.complete(f"{len(work_units)} work units built")
            await self._emit_step_completed(project_id, goal_id, step3)
            await self._emit_update(project_id, goal_id, [wu.id for wu in work_units], "created")
        except Exception as e:
            step3.fail(str(e))
            await self._emit_step_failed(project_id, goal_id, step3)
            result.error = f"Work unit building failed: {e}"
            logger.error(f"Pipeline step 3 failed for {goal_id}: {e}")
            await self._emit_update(project_id, goal_id, [], "failed")
            return result

        # Step 4: Resolve dependencies
        step4 = PipelineStep("resolve_dependencies")
        result.steps.append(step4)
        step4.start()
        await self._emit_step_started(project_id, goal_id, step4)
        try:
            self._resolve_dependencies(work_units, raw_units)
            total_deps = sum(len(wu.independence.depends_on) for wu in work_units)
            step4.complete(f"{total_deps} dependencies resolved")
            await self._emit_step_completed(project_id, goal_id, step4)
        except Exception as e:
            step4.fail(str(e))
            await self._emit_step_failed(project_id, goal_id, step4)
            logger.warning(f"Pipeline step 4 failed (non-fatal) for {goal_id}: {e}")

        # Step 5: Reconcile against existing project plan
        step5 = PipelineStep("reconcile_plan")
        result.steps.append(step5)
        step5.start()
        await self._emit_step_started(project_id, goal_id, step5)
        try:
            from .storage import (
                get_project_units,
                update_work_unit_status,
                store_reconciliation_result,
                rebuild_project_units_index,
            )

            plan_units = existing_project_units or await get_project_units(project_id)
            reconciler = ReconciliationService()

            # Convert WorkUnit objects to dicts for reconciliation
            new_unit_dicts = [json.loads(wu.model_dump_json()) for wu in work_units]
            recon = reconciler.reconcile(project_id, goal_id, new_unit_dicts, plan_units)
            result.reconciliation = json.loads(recon.model_dump_json())

            # Apply supersessions to Redis
            for sup in recon.supersessions:
                old_goal = next(
                    (u.get("source_directive_id") or u.get("goal_ref", "")
                     for u in plan_units if u.get("id") == sup.old_unit_id),
                    "",
                )
                if old_goal:
                    await update_work_unit_status(project_id, old_goal, sup.old_unit_id, {
                        "status": "superseded",
                        "superseded_by": sup.new_unit_id,
                    })
                # Emit per-unit event
                await self._bus.publish(WorkUnitSuperseded(
                    project_id=project_id,
                    old_unit_id=sup.old_unit_id,
                    new_unit_id=sup.new_unit_id,
                    reason=sup.reason,
                ))

            # Update supersedes field on new work units
            for wu in work_units:
                for new_dict in new_unit_dicts:
                    if new_dict.get("id") == wu.id and new_dict.get("supersedes"):
                        wu.supersedes = new_dict["supersedes"]

            # Store reconciliation result
            await store_reconciliation_result(project_id, goal_id, result.reconciliation)

            # Emit plan reconciled event
            await self._bus.publish(PlanReconciled(
                project_id=project_id,
                directive_id=goal_id,
                superseded_count=recon.superseded_count,
                conflict_count=recon.conflict_count,
                new_unit_count=len(work_units),
            ))

            detail_parts = []
            if recon.superseded_count > 0:
                detail_parts.append(f"{recon.superseded_count} superseded")
            if recon.conflict_count > 0:
                detail_parts.append(f"{recon.conflict_count} conflicts")
            detail_parts.append(f"{len(work_units)} new")
            step5.complete(" | ".join(detail_parts))
            await self._emit_step_completed(project_id, goal_id, step5)
        except Exception as e:
            step5.fail(str(e))
            await self._emit_step_failed(project_id, goal_id, step5)
            logger.warning(f"Pipeline step 5 failed (non-fatal) for {goal_id}: {e}")

        # Step 6: Validate
        step6 = PipelineStep("validate")
        result.steps.append(step6)
        step6.start()
        await self._emit_step_started(project_id, goal_id, step6)
        try:
            validator = SpecValidator(repo_path=self._repo_path)
            validation = validator.validate(work_units)
            result.validation_issues = [
                {"severity": i.severity, "code": i.code, "message": i.message, "work_unit_id": i.work_unit_id}
                for i in validation.issues
            ]
            if validation.valid:
                step6.complete(f"Valid — {len(validation.warnings)} warnings")
            else:
                step6.complete(f"{len(validation.errors)} errors, {len(validation.warnings)} warnings")
            await self._emit_step_completed(project_id, goal_id, step6)
        except Exception as e:
            step6.fail(str(e))
            await self._emit_step_failed(project_id, goal_id, step6)
            logger.warning(f"Pipeline step 6 failed (non-fatal) for {goal_id}: {e}")

        # Step 7: Quality scoring + chain analysis
        step7 = PipelineStep("score_quality")
        result.steps.append(step7)
        step7.start()
        await self._emit_step_started(project_id, goal_id, step7)
        try:
            scorer = QualityScorer()
            confidence = scorer.score(work_units, result.validation_issues)
            result.quality_scores = json.loads(confidence.model_dump_json())

            # Chain analysis (fast — runs inline with scoring)
            chain_analyzer = ChainAnalyzer()
            unit_map = {u.id: u for u in work_units}
            chains = chain_analyzer.analyze(work_units)
            result.chain_analysis = chains.to_dict(unit_map)

            step7.complete(
                f"Confidence: {confidence.score}/100 ({confidence.level.value}), "
                f"{chains.to_dict()['total_chains']} chains"
            )
            await self._emit_step_completed(project_id, goal_id, step7)
        except Exception as e:
            step7.fail(str(e))
            await self._emit_step_failed(project_id, goal_id, step7)
            logger.warning(f"Pipeline step 7 failed (non-fatal) for {goal_id}: {e}")

        # Step 8: Environment analysis
        step8 = PipelineStep("analyze_environment")
        result.steps.append(step8)
        step8.start()
        await self._emit_step_started(project_id, goal_id, step8)
        try:
            env_analyzer = EnvironmentAnalyzer(self._repo_path)
            environment = env_analyzer.analyze(
                work_units=work_units,
                codebase=codebase,
                project_id=project_id,
                spec_id=f"env-{goal_id}",
            )
            result.environment = environment
            step8.complete(f"Base: {environment.base_image}, {len(environment.requirements)} requirements")
            await self._emit_step_completed(project_id, goal_id, step8)
        except Exception as e:
            step8.fail(str(e))
            await self._emit_step_failed(project_id, goal_id, step8)
            logger.warning(f"Pipeline step 8 failed (non-fatal) for {goal_id}: {e}")

        result.success = True
        await self._emit_completed(project_id, goal_id, result)
        logger.info(f"Decomposition pipeline complete for {goal_id}: {len(result.work_units)} work units")
        return result

    async def _llm_decompose(
        self,
        goal_id: str,
        goal_text: str,
        project_context: Optional[Dict[str, Any]],
        existing_issues: Optional[list],
        conversation_comments: Optional[list],
        existing_project_units: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Call Claude to decompose the goal into structured units.

        Returns a list of dicts with: description, target_files,
        interface_contracts, expected_outputs, depends_on.
        """
        from services.claude_client import get_claude_client

        client = get_claude_client()

        # Build prompt
        context_parts = [f"# Goal\n{goal_text}"]
        if project_context:
            tech = project_context.get("tech_stack", "")
            if tech:
                context_parts.append(f"# Tech Stack\n{tech}")
        if existing_issues:
            summaries = [f"- {i.title} ({i.status.value})" for i in existing_issues[:15]]
            context_parts.append(f"# Existing Backlog\n" + "\n".join(summaries))
        if conversation_comments:
            comments = [f"- {c.get('content', '')[:200]}" for c in conversation_comments[:10]]
            context_parts.append(f"# Context from Conversation\n" + "\n".join(comments))

        # Inject existing project plan context
        if existing_project_units:
            active_units = [
                u for u in existing_project_units
                if u.get("status") not in ("superseded", "cancelled")
            ]
            if active_units:
                summaries = []
                for u in active_units[:20]:
                    status = u.get("status", "?")
                    desc = u.get("description", "")[:100]
                    files = ", ".join(u.get("formal_spec", {}).get("target_files", [])[:3])
                    summaries.append(f"- [{status.upper()}] {desc} (files: {files})")
                context_parts.append(
                    "# Existing Project Plan (active work units)\n"
                    "These units already exist in the project. Do NOT re-create them "
                    "unless this directive supersedes or modifies them.\n"
                    "Only create units for genuinely NEW scope from this directive.\n"
                    + "\n".join(summaries)
                )

        prompt = "\n\n".join(context_parts)

        system = """You are decomposing a software goal into independent, executable work units.

For each work unit, provide ALL of the following:

- description: concise statement of what to build/change
- target_files: specific file paths that will be modified or created
- depends_on: list of other unit descriptions this depends on (empty if independent)
- interface_contracts: what this unit PRODUCES that other units consume, and what it CONSUMES from other units
  - produces: list of {type, definition} — e.g., {type: "exports", definition: "function add(a: number, b: number): number"}
  - consumes: list of {type, definition} — what this unit expects from dependencies
- acceptance_criteria: specific, testable conditions that prove this unit is DONE
  - Each criterion should be verifiable (a test, a check, an observable behavior)
- estimated_complexity: "xs" | "s" | "m" | "l" | "xl" based on scope

Respond with JSON only:
{
  "units": [
    {
      "description": "Implement calculator math operations module",
      "target_files": ["server/src/calculator.js", "server/src/calculator.test.js"],
      "depends_on": [],
      "interface_contracts": {
        "produces": [
          {"type": "exports", "definition": "functions: add, subtract, multiply, divide — each takes (a, b) returns number"}
        ],
        "consumes": []
      },
      "acceptance_criteria": [
        "All four operations return correct results for valid inputs",
        "Division by zero throws descriptive error",
        "Unit tests pass for all operations including edge cases"
      ],
      "estimated_complexity": "s"
    },
    {
      "description": "REST API endpoint for calculator operations",
      "target_files": ["server/src/routes/calculate.js", "server/src/routes/calculate.test.js"],
      "depends_on": ["Implement calculator math operations module"],
      "interface_contracts": {
        "produces": [
          {"type": "api", "definition": "POST /calculate — accepts {operation, operands} returns {result} or {error}"}
        ],
        "consumes": [
          {"type": "imports", "definition": "calculator module — add, subtract, multiply, divide functions"}
        ]
      },
      "acceptance_criteria": [
        "POST /calculate returns correct result for valid operations",
        "Returns 400 with error message for invalid operation or operands",
        "API tests cover success and error paths"
      ],
      "estimated_complexity": "s"
    }
  ],
  "confidence": 0.85,
  "reasoning": "Split by module boundaries — calculator logic, API layer, frontend shell, frontend UI, integration..."
}

Rules:
- Each unit should touch SEPARATE files (true independence — no shared mutable state)
- Include test files alongside implementation in the same unit
- Be specific about file paths — use realistic project structure
- Interface contracts are CRITICAL — they define how units connect
- Acceptance criteria must be TESTABLE — not vague ("works correctly" is bad, "returns 400 for invalid input" is good)
- Keep units small and focused (prefer more small units over fewer large ones)
- estimated_complexity: xs=trivial config, s=single module, m=multiple files with logic, l=cross-cutting, xl=architectural
- Order dependencies correctly — a unit cannot depend on something that depends on it
- IMPORTANT: If existing project work units are listed in the context, do NOT duplicate them.
  Only create units for genuinely new scope. If this directive modifies existing functionality,
  create replacement units that cover the updated requirements."""

        response = await client.complete(prompt=prompt, system=system)

        # Parse response
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', response.content)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"Unparseable LLM response: {response.content[:300]}")

        units = data.get("units", [])
        if not units:
            raise ValueError("LLM returned no work units")

        # Convert depends_on from descriptions to indices for builder
        # (builder uses IDs, but LLM returns description references)
        return units

    def _resolve_dependencies(self, work_units: List[WorkUnit], raw_units: List[Dict[str, Any]]) -> None:
        """Resolve description-based depends_on to actual work unit IDs.

        The LLM returns depends_on as description strings (e.g., "Backend calculator logic").
        This maps them to the unit IDs by matching descriptions.
        """
        # Build description → unit ID mapping
        desc_to_id: Dict[str, str] = {}
        for i, wu in enumerate(work_units):
            desc_to_id[wu.description] = wu.id
            # Also index by the raw unit description (may differ slightly)
            if i < len(raw_units):
                raw_desc = raw_units[i].get("description", "")
                if raw_desc:
                    desc_to_id[raw_desc] = wu.id

        # Resolve dependencies
        for i, wu in enumerate(work_units):
            raw_deps = raw_units[i].get("depends_on", []) if i < len(raw_units) else []
            resolved = []
            for dep in raw_deps:
                if dep in desc_to_id:
                    resolved.append(desc_to_id[dep])
                else:
                    # Fuzzy match — find the closest description
                    best_match = None
                    best_score = 0
                    dep_lower = dep.lower()
                    for desc, uid in desc_to_id.items():
                        # Simple substring match
                        desc_lower = desc.lower()
                        if dep_lower in desc_lower or desc_lower in dep_lower:
                            score = len(set(dep_lower.split()) & set(desc_lower.split()))
                            if score > best_score:
                                best_score = score
                                best_match = uid
                    if best_match and best_score >= 2:
                        resolved.append(best_match)
                    else:
                        logger.warning(f"Could not resolve dependency '{dep[:60]}...' for {wu.id}")

            wu.independence.depends_on = resolved

        # Recompute reverse dependencies
        for wu in work_units:
            wu.independence.depended_by = []
        unit_map = {u.id: u for u in work_units}
        for wu in work_units:
            for dep_id in wu.independence.depends_on:
                if dep_id in unit_map:
                    dep_unit = unit_map[dep_id]
                    if wu.id not in dep_unit.independence.depended_by:
                        dep_unit.independence.depended_by.append(wu.id)

    async def _emit_step_started(self, project_id: str, goal_id: str, step: PipelineStep):
        """Emit a step_started event."""
        await self._bus.publish(DecompositionStepStarted(
            project_id=project_id,
            goal_id=goal_id,
            step_name=step.name,
        ))

    async def _emit_step_completed(self, project_id: str, goal_id: str, step: PipelineStep):
        """Emit a step_completed event."""
        duration = step.to_dict().get("duration_ms") or 0
        await self._bus.publish(DecompositionStepCompleted(
            project_id=project_id,
            goal_id=goal_id,
            step_name=step.name,
            duration_ms=duration,
            detail=step.detail,
        ))

    async def _emit_step_failed(self, project_id: str, goal_id: str, step: PipelineStep):
        """Emit a step_failed event."""
        await self._bus.publish(DecompositionStepFailed(
            project_id=project_id,
            goal_id=goal_id,
            step_name=step.name,
            error=step.error,
        ))

    async def _emit_completed(self, project_id: str, goal_id: str, result: 'PipelineResult'):
        """Emit a decomposition.completed event."""
        scores = result.quality_scores or {}
        await self._bus.publish(DecompositionCompleted(
            project_id=project_id,
            goal_id=goal_id,
            work_unit_count=len(result.work_units),
            confidence_score=scores.get("score"),
            confidence_level=scores.get("level"),
            success=result.success,
        ))

    async def _emit_update(self, project_id: str, goal_id: str, unit_ids: List[str], change_type: str):
        """Emit a decomposition update event."""
        await self._bus.publish(DecompositionUpdated(
            project_id=project_id,
            goal_id=goal_id,
            work_unit_ids=unit_ids,
            change_type=change_type,
        ))
