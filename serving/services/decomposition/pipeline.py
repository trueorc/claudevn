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
)
from .goal_analyzer import GoalAnalyzer
from .work_unit_builder import WorkUnitBuilder
from .spec_validator import SpecValidator
from .environment_analyzer import EnvironmentAnalyzer

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
        self.success = False
        self.error = ""

    def to_dict(self):
        return {
            "steps": [s.to_dict() for s in self.steps],
            "work_unit_count": len(self.work_units),
            "work_units": [wu.model_dump() for wu in self.work_units],
            "environment": self.environment.model_dump() if self.environment else None,
            "validation_issues": self.validation_issues,
            "success": self.success,
            "error": self.error,
        }


class DecompositionPipeline:
    """v2.0 decomposition pipeline — replaces v1.0 GoalDecomposerService.

    Each step emits events for real-time Plan page observability.
    Steps:
    1. llm_decompose — Claude breaks goal into structured units
    2. codebase_analysis — static analysis of the repo
    3. build_work_units — formal spec construction
    4. validate — independence checking, cycle detection
    5. analyze_environment — detect runtime requirements, generate Dockerfile
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
        try:
            raw_units = await self._llm_decompose(goal_id, goal_text, project_context, existing_issues, conversation_comments)
            step1.complete(f"{len(raw_units)} units from LLM")
            logger.info(f"Pipeline step 1 complete: {len(raw_units)} raw units for {goal_id}")
        except Exception as e:
            step1.fail(str(e))
            result.error = f"LLM decomposition failed: {e}"
            logger.error(f"Pipeline step 1 failed for {goal_id}: {e}")
            await self._emit_update(project_id, goal_id, [], "failed")
            return result

        # Step 2: Codebase analysis
        step2 = PipelineStep("codebase_analysis")
        result.steps.append(step2)
        step2.start()
        try:
            analyzer = GoalAnalyzer(self._repo_path)
            codebase = await analyzer.analyze(max_files=2000)
            step2.complete(f"{codebase.total_files} files, {len(codebase.modules)} modules")
            logger.info(f"Pipeline step 2 complete: {codebase.total_files} files analyzed for {goal_id}")
        except Exception as e:
            step2.fail(str(e))
            # Non-fatal — continue with empty codebase
            codebase = None
            logger.warning(f"Pipeline step 2 failed (non-fatal) for {goal_id}: {e}")

        # Step 3: Build formal work units
        step3 = PipelineStep("build_work_units")
        result.steps.append(step3)
        step3.start()
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
            logger.info(f"Pipeline step 3 complete: {len(work_units)} work units for {goal_id}")

            await self._emit_update(project_id, goal_id, [wu.id for wu in work_units], "created")
        except Exception as e:
            step3.fail(str(e))
            result.error = f"Work unit building failed: {e}"
            logger.error(f"Pipeline step 3 failed for {goal_id}: {e}")
            await self._emit_update(project_id, goal_id, [], "failed")
            return result

        # Step 4: Validate
        step4 = PipelineStep("validate")
        result.steps.append(step4)
        step4.start()
        try:
            validator = SpecValidator(repo_path=self._repo_path)
            validation = validator.validate(work_units)
            result.validation_issues = [
                {"severity": i.severity, "code": i.code, "message": i.message, "work_unit_id": i.work_unit_id}
                for i in validation.issues
            ]
            if validation.valid:
                step4.complete(f"Valid — {len(validation.warnings)} warnings")
            else:
                step4.complete(f"{len(validation.errors)} errors, {len(validation.warnings)} warnings")
            logger.info(f"Pipeline step 4 complete: valid={validation.valid} for {goal_id}")
        except Exception as e:
            step4.fail(str(e))
            logger.warning(f"Pipeline step 4 failed (non-fatal) for {goal_id}: {e}")

        # Step 5: Environment analysis
        step5 = PipelineStep("analyze_environment")
        result.steps.append(step5)
        step5.start()
        try:
            env_analyzer = EnvironmentAnalyzer(self._repo_path)
            environment = env_analyzer.analyze(
                work_units=work_units,
                codebase=codebase,
                project_id=project_id,
                spec_id=f"env-{goal_id}",
            )
            result.environment = environment
            step5.complete(f"Base: {environment.base_image}, {len(environment.requirements)} requirements")
            logger.info(f"Pipeline step 5 complete: {len(environment.requirements)} requirements for {goal_id}")
        except Exception as e:
            step5.fail(str(e))
            logger.warning(f"Pipeline step 5 failed (non-fatal) for {goal_id}: {e}")

        result.success = True
        logger.info(f"Decomposition pipeline complete for {goal_id}: {len(result.work_units)} work units")
        return result

    async def _llm_decompose(
        self,
        goal_id: str,
        goal_text: str,
        project_context: Optional[Dict[str, Any]],
        existing_issues: Optional[list],
        conversation_comments: Optional[list],
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

        prompt = "\n\n".join(context_parts)

        system = """You are decomposing a software goal into independent work units.

For each work unit, provide:
- description: what to build/change
- target_files: specific file paths that will be modified or created
- depends_on: list of other unit descriptions this depends on (empty if independent)

Respond with JSON only:
{
  "units": [
    {
      "description": "Implement calculator math operations module",
      "target_files": ["src/calculator.py", "tests/test_calculator.py"],
      "depends_on": []
    }
  ],
  "confidence": 0.85,
  "reasoning": "Split by module boundaries..."
}

Rules:
- Each unit should touch SEPARATE files (independence)
- Include test files alongside implementation
- Be specific about file paths
- Order dependencies correctly
- Keep units small and focused"""

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

    async def _emit_update(self, project_id: str, goal_id: str, unit_ids: List[str], change_type: str):
        """Emit a decomposition update event."""
        await self._bus.publish(DecompositionUpdated(
            project_id=project_id,
            goal_id=goal_id,
            work_unit_ids=unit_ids,
            change_type=change_type,
        ))
