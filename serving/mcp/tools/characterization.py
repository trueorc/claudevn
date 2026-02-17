"""claudevn_submit_characterization tool - Return characterization results.

This tool allows a compute instance to submit the results of work item
characterization back to the serving component. Characterization is
performed by compute instances using Claude Code, following the v1.0
architecture where serving orchestrates but does not execute LLM work.
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..models import MCPError

logger = logging.getLogger(__name__)


# ============================================================================
# Input Models
# ============================================================================


class MeaningInput(BaseModel):
    """Meaning assessment from compute characterization."""
    business_summary: str = Field(..., description="Business value summary")
    business_user_impact: str = Field(default="", description="How this affects end users")
    business_value: str = Field(default="", description="Revenue, retention, compliance value")
    technical_summary: str = Field(..., description="Technical accomplishment summary")
    technical_components: List[str] = Field(default_factory=list, description="Components affected")
    technical_risk: str = Field(default="", description="Complexity and unknowns assessment")
    contextual_summary: str = Field(default="", description="Role in the broader project")
    contextual_role: str = Field(
        default="incremental",
        description="Role: foundational, incremental, enabling, blocking"
    )
    related_work_summary: str = Field(default="", description="Relationship to other work")


class DependencyInput(BaseModel):
    """A discovered contextual dependency from characterization."""
    target_item_id: str = Field(..., description="ID of the related work item")
    relation: str = Field(
        ..., description="Relation: blocks, enables, related_to, extends, conflicts_with"
    )
    dependency_type: str = Field(
        default="contextual", description="Type: structural or contextual"
    )
    reasoning: str = Field(default="", description="Why this relationship was identified")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence 0-1")


class OntologyTagsInput(BaseModel):
    """Ontology tags assigned during characterization."""
    work_type: str = Field(..., description="Work type: feature, bug_fix, refactor, test, etc.")
    lifecycle_stage: str = Field(..., description="Lifecycle: design, build, test, validate, deploy")
    technical_domains: List[str] = Field(
        ..., description="Domains: frontend, backend, data, api, security, devops, testing, documentation"
    )
    cluster_ids: List[str] = Field(default_factory=list, description="Project-specific cluster IDs")


class SubmitCharacterizationInput(BaseModel):
    """Input for claudevn_submit_characterization tool."""
    characterization_id: str = Field(..., description="Characterization ID assigned by serving")
    project_id: str = Field(..., description="Project this item belongs to")
    item_id: str = Field(..., description="Work item being characterized")
    ontology_tags: OntologyTagsInput = Field(..., description="Assigned ontology tags")
    meaning: MeaningInput = Field(..., description="Meaning assessments")
    dependencies: List[DependencyInput] = Field(
        default_factory=list, description="Discovered contextual dependencies"
    )
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Overall confidence 0-1")
    evaluated_in_isolation: bool = Field(default=True, description="Was Frame 1 evaluation done")
    evaluated_in_context: bool = Field(default=False, description="Was Frame 2 evaluation done")
    topology_item_count: int = Field(default=0, description="Items in topology during evaluation")


class SubmitCharacterizationResponse(BaseModel):
    """Response for claudevn_submit_characterization tool."""
    acknowledged: bool
    characterization_id: str
    project_id: str
    item_id: str
    status: str = Field(description="Status: stored, error")


# ============================================================================
# Tool Implementation
# ============================================================================


async def submit_characterization(
    input: SubmitCharacterizationInput,
) -> tuple[Optional[SubmitCharacterizationResponse], Optional[MCPError]]:
    """Submit characterization results from a compute instance.

    This tool is called by compute instances that have been assigned a
    characterization task. The compute uses Claude Code to evaluate the
    work item in isolation (Frame 1) and in project context (Frame 2),
    then submits the structured results back to serving.
    """
    logger.info(
        f"Received characterization {input.characterization_id} for item {input.item_id} "
        f"in project {input.project_id}"
    )

    try:
        from models.ontology import (
            OntologyTags,
            UniversalTags,
            ProjectSpecificTags,
            WorkType,
            LifecycleStage,
            TechnicalDomain,
        )
        from models.characterization import (
            CharacterizationResult,
            CharacterizationStatus,
            MeaningAssessment,
            BusinessMeaning,
            TechnicalMeaning,
            ContextualMeaning,
            ContextualRole,
            ContextualDependency,
            DependencyRelation,
            DependencyType,
        )
        from services.characterization_service import get_characterization_service

        # Convert ontology tags input to model
        try:
            work_type = WorkType(input.ontology_tags.work_type)
        except ValueError:
            work_type = WorkType.FEATURE

        try:
            lifecycle_stage = LifecycleStage(input.ontology_tags.lifecycle_stage)
        except ValueError:
            lifecycle_stage = LifecycleStage.BUILD

        technical_domains = []
        for domain_str in input.ontology_tags.technical_domains:
            try:
                technical_domains.append(TechnicalDomain(domain_str))
            except ValueError:
                pass
        if not technical_domains:
            technical_domains = [TechnicalDomain.BACKEND]

        ontology_tags = OntologyTags(
            universal=UniversalTags(
                work_type=work_type,
                lifecycle_stage=lifecycle_stage,
                technical_domains=technical_domains,
            ),
            project_specific=ProjectSpecificTags(
                cluster_ids=input.ontology_tags.cluster_ids,
            ),
        )

        # Convert meaning input to model
        try:
            contextual_role = ContextualRole(input.meaning.contextual_role)
        except ValueError:
            contextual_role = ContextualRole.INCREMENTAL

        meaning = MeaningAssessment(
            business=BusinessMeaning(
                summary=input.meaning.business_summary,
                user_impact=input.meaning.business_user_impact,
                business_value=input.meaning.business_value,
            ),
            technical=TechnicalMeaning(
                summary=input.meaning.technical_summary,
                components_affected=input.meaning.technical_components,
                technical_risk=input.meaning.technical_risk,
            ),
            contextual=ContextualMeaning(
                summary=input.meaning.contextual_summary,
                role=contextual_role,
                related_work_summary=input.meaning.related_work_summary,
            ),
        )

        # Convert dependencies
        dependencies = []
        for dep_input in input.dependencies:
            try:
                relation = DependencyRelation(dep_input.relation)
            except ValueError:
                relation = DependencyRelation.RELATED_TO

            try:
                dep_type = DependencyType(dep_input.dependency_type)
            except ValueError:
                dep_type = DependencyType.CONTEXTUAL

            dependencies.append(ContextualDependency(
                target_item_id=dep_input.target_item_id,
                relation=relation,
                dependency_type=dep_type,
                reasoning=dep_input.reasoning,
                confidence=dep_input.confidence,
            ))

        # Build the full characterization result
        result = CharacterizationResult(
            item_id=input.item_id,
            project_id=input.project_id,
            ontology_tags=ontology_tags,
            meaning=meaning,
            dependencies=dependencies,
            status=CharacterizationStatus.COMPLETED,
            confidence=input.confidence,
            evaluated_in_isolation=input.evaluated_in_isolation,
            evaluated_in_context=input.evaluated_in_context,
            topology_item_count=input.topology_item_count,
        )

        # Store via CharacterizationService
        service = get_characterization_service()
        await service.store_result(result)

        # Signal completion via Redis key (legacy fallback) and in-process asyncio.Event
        from git.redis_client import get_redis
        redis = await get_redis()
        completion_key = f"claudevn:characterization_complete:{input.characterization_id}"
        await redis.setex(completion_key, 300, "1")  # 5 minute TTL

        # In-process event: instant unblock for _wait_for_characterization_result() (no polling)
        try:
            from services.completion_events import signal as signal_completion
            signal_completion(input.characterization_id)
        except Exception:
            pass  # Graceful degradation — legacy Redis polling still works

        logger.info(
            f"Stored characterization for item {input.item_id}: "
            f"confidence={input.confidence:.2f}, "
            f"isolation={input.evaluated_in_isolation}, "
            f"context={input.evaluated_in_context}"
        )

        return SubmitCharacterizationResponse(
            acknowledged=True,
            characterization_id=input.characterization_id,
            project_id=input.project_id,
            item_id=input.item_id,
            status="stored",
        ), None

    except Exception as e:
        logger.error(f"Error storing characterization: {e}", exc_info=True)
        return None, MCPError(
            code="INTERNAL_ERROR",
            message=f"Failed to store characterization: {str(e)}",
        )
