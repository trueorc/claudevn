"""API endpoints for the Skill Marketplace."""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, status

from models import (
    Skill, Agent, ToolDefinition,
    SkillCreateRequest, SkillUpdateRequest, SkillListResponse,
    SkillVersion, SkillVersionListResponse,
    ComposeRequest, ComposePreviewResponse, ConflictCheckRequest, ConflictCheckResponse,
    AddSkillRequest, AddSkillResult,
    ConflictResolution, ResolveConflictRequest, ResolveConflictResult,
    Persona, PersonaCreateRequest, PersonaUpdateRequest, PersonaListResponse,
    PersonaVersion, PersonaVersionListResponse,
    ExpandedPersona,
    CatalogSkillEntry, CatalogPersonaEntry, CatalogResponse,
    ToolAuthorizationRequest, ToolAuthorizationResponse, ToolListResponse,
    AuthorizationFailure,
    AuthorizationAuditQueryResponse, AuthorizationAuditStats,
    SkillAnalyticsResponse,
    AgentListResponse, AgentCacheStats
)
from skill_registry import get_skill_registry, ToolTier
from composition_service import get_composition_service
from persona_registry import get_persona_registry
from services.authorization_audit_service import get_authorization_audit_service
from services.skill_usage_service import get_skill_usage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["skills"])
persona_router = APIRouter(prefix="/personas", tags=["personas"])
tools_router = APIRouter(prefix="/tools", tags=["tools"])
agents_router = APIRouter(prefix="/agents", tags=["agents"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])


# ============ Stats Endpoint (must be before /{skill_id}) ============

@router.get("/stats")
async def get_stats():
    """Get marketplace statistics.

    Returns:
        Marketplace statistics including skill and tool counts
    """
    registry = get_skill_registry()

    try:
        return registry.get_stats()
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving statistics"
        )


# ============ Analytics Endpoint (must be before /{skill_id}) ============

@router.get("/analytics", response_model=SkillAnalyticsResponse)
async def get_skill_analytics():
    """Get skill usage analytics.

    Returns usage statistics including most-used skills,
    never-used skills, and total composition count.

    Returns:
        Skill usage analytics with most_used, never_used, and totals
    """
    usage_service = get_skill_usage_service()

    try:
        analytics = usage_service.get_analytics()
        return SkillAnalyticsResponse(**analytics)
    except Exception as e:
        logger.error(f"Error getting skill analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving analytics"
        )


# ============ Search Endpoint (must be before /{skill_id}) ============

@router.get("/search/capabilities")
async def search_by_capabilities(
    capabilities: str = Query(..., description="Comma-separated capabilities to search for")
):
    """Search skills by required capabilities.

    Args:
        capabilities: Comma-separated capabilities to search for

    Returns:
        Matching skills with search metadata
    """
    registry = get_skill_registry()

    cap_list = [c.strip() for c in capabilities.split(",")]
    skills = registry.search_by_capabilities(cap_list)

    return {
        "skills": skills,
        "total": len(skills),
        "searched_capabilities": cap_list
    }


# ============ Catalog Endpoint (must be before /{skill_id}) ============

@router.get("/catalog", response_model=CatalogResponse)
async def get_catalog(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return")
):
    """Get complete skill and persona catalog for discovery.

    Returns a lightweight view of all available skills and personas,
    suitable for Planner to discover capabilities and assign work.

    Args:
        skip: Number of records to skip
        limit: Max records to return (default 100, max 1000)

    Returns:
        Catalog with skills (id, name, description, tags, grants_tools)
        and personas (id, name, description, skills, grants_tools)
    """
    skill_registry = get_skill_registry()
    persona_registry = get_persona_registry()

    skills = skill_registry.list_skills()
    catalog_skills = [
        CatalogSkillEntry(
            id=s.id,
            name=s.name,
            description=s.description,
            tags=s.tags,
            grants_tools=s.specialized_tools,
            dependencies=s.dependencies
        )
        for s in skills
    ]

    personas = persona_registry.list_personas()
    catalog_personas = []
    for p in personas:
        aggregated_tools = set()
        for skill_id in p.references_skills:
            skill = skill_registry.get_skill(skill_id)
            if skill:
                aggregated_tools.update(skill.specialized_tools)

        catalog_personas.append(
            CatalogPersonaEntry(
                id=p.id,
                name=p.name,
                description=p.description,
                skills=p.references_skills,
                grants_tools=sorted(list(aggregated_tools))
            )
        )

    total_skills = len(catalog_skills)
    total_personas = len(catalog_personas)
    paginated_skills = catalog_skills[skip:skip + limit]
    paginated_personas = catalog_personas[skip:skip + limit]

    return CatalogResponse(
        skills=paginated_skills,
        personas=paginated_personas,
        total_skills=total_skills,
        total_personas=total_personas,
        skip=skip,
        limit=limit,
        has_more=skip + limit < total_skills or skip + limit < total_personas
    )


# ============ Tool Endpoints (must be before /{skill_id}) ============

@router.get("/tools/{tool_id}", response_model=ToolDefinition)
async def get_tool(tool_id: str):
    """Get a specific tool by ID.

    Args:
        tool_id: Tool identifier

    Returns:
        Tool details

    Raises:
        HTTPException: If tool not found
    """
    registry = get_skill_registry()
    tool = registry.get_tool(tool_id)

    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_id}' not found"
        )

    return tool


# ============ Composition Endpoints (must be before /{skill_id}) ============

@router.post("/compose", response_model=Agent)
async def compose_agent(request: ComposeRequest):
    """Compose an agent bundle from skills for a task.

    Args:
        request: Composition request with task and optional skill IDs

    Returns:
        Composed agent bundle ready for deployment

    Raises:
        HTTPException: If composition fails or no suitable skills found
    """
    service = get_composition_service()

    try:
        agent = await service.compose(request)
        logger.info(f"Composed agent {agent.id} for task {request.task.task_id}")
        return agent
    except ValueError as e:
        logger.error(f"Failed to compose agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error composing agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during agent composition"
        )


@router.post("/compose/preview", response_model=ComposePreviewResponse)
async def preview_composition(request: ComposeRequest):
    """Preview agent composition without persisting.

    Returns the composition result (merged instructions, tools, conflicts)
    without creating an agent or storing anything in the cache. Use this
    to validate skill combinations before committing to composition.

    Args:
        request: Composition request with task and optional skill IDs

    Returns:
        Preview of composition result including:
        - merged_instructions: What the final CLAUDE.md would look like
        - tools: All tools that would be granted
        - skills: Skills that would be included (with dependencies resolved)
        - conflict_warnings: Any conflicts or warnings detected

    Raises:
        HTTPException: If preview fails or no suitable skills found
    """
    service = get_composition_service()

    try:
        preview = await service.compose_preview(request)
        logger.info(f"Generated composition preview for task {request.task.task_id}")
        return preview
    except ValueError as e:
        logger.error(f"Failed to generate preview: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during composition preview"
        )


@router.post("/conflicts/check", response_model=ConflictCheckResponse)
async def check_conflicts(request: ConflictCheckRequest):
    """Check for conflicts between a set of skills.

    Args:
        request: Conflict check request with skill IDs

    Returns:
        Conflict check results with conflicts and warnings
    """
    service = get_composition_service()

    try:
        result = service.check_conflicts(request.skill_ids)
        return result
    except Exception as e:
        logger.error(f"Error checking conflicts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during conflict check"
        )


@router.post("/composition/add-skill", response_model=AddSkillResult)
async def add_skill_to_composition(
    existing_skill_ids: List[str] = Query(..., description="Existing skill IDs in the composition"),
    request: AddSkillRequest = ...
):
    """Add a skill to a composition with conflict detection.

    Conflicts are advisory - the caller can decide to:
    1. Keep both skills (intentional, e.g., writer + reviewer for thorough work)
    2. Remove the conflicting skill first
    3. Cancel the addition

    Args:
        existing_skill_ids: List of skill IDs already in the composition
        request: Add skill request with skill_id and optional force flag

    Returns:
        AddSkillResult with:
        - added: Whether the skill was added
        - has_conflicts: Whether conflicts were detected
        - conflicts: List of conflict details (skill ID and reason)
        - warnings: Advisory warnings (e.g., overlapping tools)
        - can_proceed: Always True (decision point, not rejection)
        - message: Human-readable status

    Example:
        # First attempt - conflicts detected
        POST /skills/composition/add-skill?existing_skill_ids=code-writer
        {"skill_id": "code-reviewer", "force": false}
        -> {"added": false, "has_conflicts": true, "conflicts": [...], "can_proceed": true}

        # Second attempt - force add despite conflicts
        POST /skills/composition/add-skill?existing_skill_ids=code-writer
        {"skill_id": "code-reviewer", "force": true}
        -> {"added": true, "has_conflicts": true, "message": "added with conflicts (forced)"}
    """
    service = get_composition_service()

    try:
        result = service.add_skill(
            existing_skill_ids=existing_skill_ids,
            new_skill_id=request.skill_id,
            force=request.force
        )
        if result.added:
            logger.info(f"Added skill {request.skill_id} to composition")
        elif result.has_conflicts:
            logger.info(f"Skill {request.skill_id} has conflicts - awaiting decision")
        return result
    except Exception as e:
        logger.error(f"Error adding skill to composition: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during skill addition"
        )


@router.post("/composition/resolve-conflict", response_model=ResolveConflictResult)
async def resolve_conflict(request: ResolveConflictRequest):
    """Apply conflict resolution decision.

    After add_skill() detects conflicts, this endpoint applies the user's
    resolution decision. This provides a formal workflow for handling conflicts
    rather than just using the force flag.

    Resolution options:
    - KEEP_BOTH: Accept the conflict, add new skill alongside existing ones
    - REMOVE_EXISTING: Remove conflicting skill(s), then add the new skill
    - CANCEL: Cancel the addition, keep existing composition unchanged

    All resolution decisions are audit-logged for traceability.

    Args:
        request: Resolution request with skill IDs and chosen resolution

    Returns:
        ResolveConflictResult with:
        - resolution: The applied resolution
        - resulting_skill_ids: Final composition after resolution
        - removed_skill_ids: Any skills that were removed
        - success: Whether resolution was applied
        - message: Human-readable status
        - timestamp: When resolution was applied
        - reason: User-provided reason (for audit)

    Example:
        # Conflict detected when adding code-reviewer to [code-writer, rapid-prototyper]
        POST /skills/composition/resolve-conflict
        {
            "new_skill_id": "code-reviewer",
            "existing_skill_ids": ["code-writer", "rapid-prototyper"],
            "conflicting_skill_ids": ["rapid-prototyper"],
            "resolution": "keep_both",
            "reason": "Intentional - want thorough code review"
        }
        -> {
            "resolution": "keep_both",
            "new_skill_id": "code-reviewer",
            "resulting_skill_ids": ["code-writer", "rapid-prototyper", "code-reviewer"],
            "removed_skill_ids": [],
            "success": true,
            "message": "Kept both skills despite conflict (reason: Intentional - want thorough code review)"
        }
    """
    service = get_composition_service()

    try:
        result = service.resolve_conflict(
            new_skill_id=request.new_skill_id,
            existing_skill_ids=request.existing_skill_ids,
            conflicting_skill_ids=request.conflicting_skill_ids,
            resolution=request.resolution,
            reason=request.reason
        )

        # Audit logging
        if result.success:
            logger.info(
                f"Conflict resolution applied: {request.resolution.value} for skill "
                f"'{request.new_skill_id}' (reason: {request.reason or 'not provided'})"
            )
        else:
            logger.warning(
                f"Conflict resolution failed: {request.resolution.value} for skill "
                f"'{request.new_skill_id}' - {result.message}"
            )

        return result
    except Exception as e:
        logger.error(f"Error resolving conflict: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during conflict resolution"
        )


# ============ Skill CRUD Endpoints ============

@router.get("", response_model=SkillListResponse)
async def list_skills(
    tags: Optional[str] = Query(None, description="Comma-separated tags to filter by"),
    author: Optional[str] = Query(None, description="Filter by author type (system/user)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return")
):
    """List all skills with optional filtering.

    Args:
        tags: Comma-separated tags to filter by
        author: Filter by author type (system/user)
        skip: Number of records to skip
        limit: Max records to return (default 100, max 1000)

    Returns:
        List of skills with pagination metadata and summary statistics
    """
    registry = get_skill_registry()

    tag_list = tags.split(",") if tags else None
    all_skills = registry.list_skills(tags=tag_list, author=author)

    by_author = {}
    for skill in all_skills:
        author_type = "system" if skill.author == "system" else "user"
        by_author[author_type] = by_author.get(author_type, 0) + 1

    total = len(all_skills)
    paginated = all_skills[skip:skip + limit]

    return SkillListResponse(
        skills=paginated,
        total=total,
        skip=skip,
        limit=limit,
        has_more=skip + limit < total,
        by_author=by_author
    )


@router.post("", response_model=Skill, status_code=status.HTTP_201_CREATED)
async def create_skill(request: SkillCreateRequest):
    """Create a new user skill.

    Args:
        request: Skill creation request

    Returns:
        Created skill

    Raises:
        HTTPException: If skill ID already exists or validation fails
    """
    registry = get_skill_registry()

    try:
        skill = await registry.create_skill(request, author="user")
        logger.info(f"Created skill {skill.id}")
        return skill
    except ValueError as e:
        logger.error(f"Failed to create skill: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating skill: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during skill creation"
        )


@router.get("/{skill_id}/versions", response_model=SkillVersionListResponse)
async def list_skill_versions(skill_id: str):
    """List all versions of a skill.

    Returns version history in descending order (newest first).
    Git backend provides implicit versioning via commit history.

    Args:
        skill_id: Skill identifier

    Returns:
        Version history with changelog entries

    Raises:
        HTTPException: If skill not found
    """
    registry = get_skill_registry()

    # Verify skill exists
    skill = registry.get_skill(skill_id)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_id}' not found"
        )

    versions = registry.list_skill_versions(skill_id)

    return SkillVersionListResponse(
        skill_id=skill_id,
        versions=versions,
        total=len(versions),
        current_version=skill.version
    )


@router.get("/{skill_id}", response_model=Skill)
async def get_skill(
    skill_id: str,
    version: Optional[str] = Query(None, description="Specific version to retrieve (e.g., 1.0.0)")
):
    """Get a specific skill by ID.

    Optionally retrieve a specific version of the skill.

    Args:
        skill_id: Skill identifier
        version: Optional version string (e.g., "1.0.0") to retrieve a specific version

    Returns:
        Skill details (current version or specified historical version)

    Raises:
        HTTPException: If skill not found or version not found
    """
    registry = get_skill_registry()

    if version:
        # Get specific version
        skill = registry.get_skill_version(skill_id, version)
        if not skill:
            # Check if skill exists at all
            current_skill = registry.get_skill(skill_id)
            if not current_skill:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Skill '{skill_id}' not found"
                )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version '{version}' not found for skill '{skill_id}'"
            )
    else:
        # Get current version
        skill = registry.get_skill(skill_id)
        if not skill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{skill_id}' not found"
            )

    return skill


@router.put("/{skill_id}", response_model=Skill)
async def update_skill(skill_id: str, request: SkillUpdateRequest):
    """Update an existing skill.

    Args:
        skill_id: Skill identifier
        request: Skill update request

    Returns:
        Updated skill

    Raises:
        HTTPException: If skill not found or is a system skill
    """
    registry = get_skill_registry()

    skill = registry.get_skill(skill_id)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_id}' not found"
        )

    # Don't allow updating system skills
    if skill.author == "system":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify system skills"
        )

    try:
        updated = await registry.update_skill(skill_id, request)
        logger.info(f"Updated skill {skill_id}")
        return updated
    except Exception as e:
        logger.error(f"Error updating skill {skill_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during skill update"
        )


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(skill_id: str):
    """Delete a user skill.

    Args:
        skill_id: Skill identifier

    Raises:
        HTTPException: If skill not found or is a system skill
    """
    registry = get_skill_registry()

    try:
        deleted = await registry.delete_skill(skill_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{skill_id}' not found"
            )
        logger.info(f"Deleted skill {skill_id}")
    except ValueError as e:
        logger.error(f"Failed to delete skill {skill_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error deleting skill {skill_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during skill deletion"
        )


# ============================================================================
# PERSONA ENDPOINTS
# ============================================================================


# ============ Stats Endpoint (must be before /{persona_id}) ============

@persona_router.get("/stats")
async def get_persona_stats():
    """Get persona registry statistics.

    Returns:
        Persona registry statistics including persona counts
    """
    registry = get_persona_registry()

    try:
        return registry.get_stats()
    except Exception as e:
        logger.error(f"Error getting persona stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving statistics"
        )


# ============ Expand Endpoint (must be before /{persona_id}) ============

@persona_router.get("/expand/{persona_id}", response_model=ExpandedPersona)
async def expand_persona(persona_id: str):
    """Expand a persona to include its constituent skill objects.

    Args:
        persona_id: Persona identifier

    Returns:
        Expanded persona with skill objects and missing skill IDs

    Raises:
        HTTPException: If persona not found
    """
    registry = get_persona_registry()

    expanded = registry.expand_persona(persona_id)
    if not expanded:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona '{persona_id}' not found"
        )

    return expanded


@persona_router.post("/regenerate/{persona_id}", response_model=Persona)
async def regenerate_merged_instructions(persona_id: str):
    """Regenerate merged instructions for a persona from its referenced skills.

    Useful when referenced skills have been updated and the persona's
    merged_instructions need to be refreshed.

    Args:
        persona_id: Persona identifier

    Returns:
        Updated persona with regenerated merged_instructions

    Raises:
        HTTPException: If persona not found
    """
    registry = get_persona_registry()

    try:
        persona = await registry.regenerate_merged_instructions(persona_id)
        if not persona:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Persona '{persona_id}' not found"
            )
        logger.info(f"Regenerated merged instructions for persona {persona_id}")
        return persona
    except Exception as e:
        logger.error(f"Error regenerating persona {persona_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during regeneration"
        )


# ============ Persona Version Endpoints (must be before /{persona_id}) ============

@persona_router.get("/{persona_id}/versions", response_model=PersonaVersionListResponse)
async def list_persona_versions(persona_id: str):
    """List all versions of a persona.

    Returns version history in descending order (newest first).

    Args:
        persona_id: Persona identifier

    Returns:
        Version history with changelog entries

    Raises:
        HTTPException: If persona not found
    """
    registry = get_persona_registry()

    # Verify persona exists
    persona = registry.get_persona(persona_id)
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona '{persona_id}' not found"
        )

    versions = registry.list_persona_versions(persona_id)

    return PersonaVersionListResponse(
        persona_id=persona_id,
        versions=versions,
        total=len(versions),
        current_version=persona.version
    )


# ============ Persona CRUD Endpoints ============

@persona_router.get("", response_model=PersonaListResponse)
async def list_personas(
    tags: Optional[str] = Query(None, description="Comma-separated tags to filter by"),
    author: Optional[str] = Query(None, description="Filter by author type (system/user)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return")
):
    """List all personas with optional filtering.

    Args:
        tags: Comma-separated tags to filter by
        author: Filter by author type (system/user)
        skip: Number of records to skip
        limit: Max records to return (default 100, max 1000)

    Returns:
        List of personas with pagination metadata and summary statistics
    """
    registry = get_persona_registry()

    tag_list = tags.split(",") if tags else None
    all_personas = registry.list_personas(tags=tag_list, author=author)

    by_author = {}
    for persona in all_personas:
        author_type = "system" if persona.author == "system" else "user"
        by_author[author_type] = by_author.get(author_type, 0) + 1

    total = len(all_personas)
    paginated = all_personas[skip:skip + limit]

    return PersonaListResponse(
        personas=paginated,
        total=total,
        skip=skip,
        limit=limit,
        has_more=skip + limit < total,
        by_author=by_author
    )


@persona_router.post("", response_model=Persona, status_code=status.HTTP_201_CREATED)
async def create_persona(request: PersonaCreateRequest):
    """Create a new user persona.

    Args:
        request: Persona creation request

    Returns:
        Created persona

    Raises:
        HTTPException: If persona ID already exists or validation fails
    """
    registry = get_persona_registry()

    try:
        persona = await registry.create_persona(request, author="user")
        logger.info(f"Created persona {persona.id}")
        return persona
    except ValueError as e:
        logger.error(f"Failed to create persona: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating persona: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during persona creation"
        )


@persona_router.get("/{persona_id}", response_model=Persona)
async def get_persona(
    persona_id: str,
    version: Optional[str] = Query(None, description="Specific version to retrieve (e.g., 1.0.0)")
):
    """Get a specific persona by ID.

    Optionally retrieve a specific version of the persona.

    Args:
        persona_id: Persona identifier
        version: Optional version string (e.g., "1.0.0") to retrieve a specific version

    Returns:
        Persona details (current version or specified historical version)

    Raises:
        HTTPException: If persona not found or version not found
    """
    registry = get_persona_registry()

    if version:
        # Get specific version
        persona = registry.get_persona_version(persona_id, version)
        if not persona:
            # Check if persona exists at all
            current_persona = registry.get_persona(persona_id)
            if not current_persona:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Persona '{persona_id}' not found"
                )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version '{version}' not found for persona '{persona_id}'"
            )
    else:
        # Get current version
        persona = registry.get_persona(persona_id)
        if not persona:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Persona '{persona_id}' not found"
            )

    return persona


@persona_router.put("/{persona_id}", response_model=Persona)
async def update_persona(persona_id: str, request: PersonaUpdateRequest):
    """Update an existing persona.

    Args:
        persona_id: Persona identifier
        request: Persona update request

    Returns:
        Updated persona

    Raises:
        HTTPException: If persona not found or is a system persona
    """
    registry = get_persona_registry()

    persona = registry.get_persona(persona_id)
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona '{persona_id}' not found"
        )

    # Don't allow updating system personas
    if persona.author == "system":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify system personas"
        )

    try:
        updated = await registry.update_persona(persona_id, request)
        logger.info(f"Updated persona {persona_id}")
        return updated
    except Exception as e:
        logger.error(f"Error updating persona {persona_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during persona update"
        )


@persona_router.delete("/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_persona(persona_id: str):
    """Delete a user persona.

    Args:
        persona_id: Persona identifier

    Raises:
        HTTPException: If persona not found or is a system persona
    """
    registry = get_persona_registry()

    try:
        deleted = await registry.delete_persona(persona_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Persona '{persona_id}' not found"
            )
        logger.info(f"Deleted persona {persona_id}")
    except ValueError as e:
        logger.error(f"Failed to delete persona {persona_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error deleting persona {persona_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during persona deletion"
        )


# ============================================================================
# TOOL REGISTRY API ENDPOINTS
# ============================================================================
# These endpoints provide direct access to the Tool Authorization Registry
# as specified in skill-marketplace.md §Tools


@tools_router.get("", response_model=ToolListResponse)
async def list_tools(
    tier: Optional[str] = Query(None, description="Filter by tier (global/specialized)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return")
):
    """List all tool definitions.

    Args:
        tier: Optional tier filter (global/specialized)
        skip: Number of records to skip
        limit: Max records to return (default 100, max 1000)

    Returns:
        List of tools with pagination metadata and summary statistics

    Raises:
        HTTPException: If tier is invalid
    """
    registry = get_skill_registry()

    tool_tier = None
    if tier:
        try:
            tool_tier = ToolTier(tier)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid tier: {tier}. Must be one of: {[t.value for t in ToolTier]}"
            )

    all_tools = registry.list_tools(tier=tool_tier)
    total = len(all_tools)
    paginated = all_tools[skip:skip + limit]

    return ToolListResponse(
        tools=paginated,
        total=total,
        skip=skip,
        limit=limit,
        has_more=skip + limit < total,
        by_tier={
            "global": len([t for t in all_tools if t.tier == ToolTier.GLOBAL]),
            "specialized": len([t for t in all_tools if t.tier == ToolTier.SPECIALIZED])
        }
    )


@tools_router.post("/check-authorization", response_model=ToolAuthorizationResponse)
async def check_tool_authorization(request: ToolAuthorizationRequest):
    """Check if an agent is authorized to use a tool.

    Two-part authorization check:
    1. Skill grants permission: Agent must have a skill that grants the tool
    2. Compute has capability: Compute must have the tool and required labels

    For global tools, only compute check is performed (if compute info provided).
    For specialized tools, both checks must pass.

    All authorization checks are audit-logged for security compliance.

    Args:
        request: Authorization request with agent_id, tool_id, and optional compute

    Returns:
        Authorization result with detailed failure information

    Raises:
        HTTPException: If tool not found
    """
    registry = get_skill_registry()
    service = get_composition_service()
    audit = get_authorization_audit_service()

    compute_id = request.compute.instance_id if request.compute else None

    # Get the tool
    tool = registry.get_tool(request.tool_id)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{request.tool_id}' not found"
        )

    # Global tools are always authorized at skill level
    if tool.tier == ToolTier.GLOBAL:
        # If compute info provided, verify compute has the tool
        if request.compute:
            if request.tool_id not in request.compute.tools_available:
                response = ToolAuthorizationResponse(
                    authorized=False,
                    granted_by=[],
                    tool=tool,
                    reason=f"Compute '{request.compute.instance_id}' does not have "
                           f"tool '{request.tool_id}' available",
                    failure_type=AuthorizationFailure.COMPUTE_MISSING_TOOL,
                    skill_check_passed=True,
                    compute_check_passed=False
                )
                audit.log_authorization(
                    agent_id=request.agent_id, tool_id=request.tool_id,
                    authorized=False, reason=response.reason,
                    compute_id=compute_id,
                    failure_type=AuthorizationFailure.COMPUTE_MISSING_TOOL,
                )
                return response
        response = ToolAuthorizationResponse(
            authorized=True,
            granted_by=[],
            tool=tool,
            reason="Global tools are always authorized",
            skill_check_passed=True,
            compute_check_passed=True if request.compute else None
        )
        audit.log_authorization(
            agent_id=request.agent_id, tool_id=request.tool_id,
            authorized=True, reason=response.reason,
            compute_id=compute_id,
        )
        return response

    # Part 1: Skill grants permission
    agent = service.get_agent(request.agent_id)
    if not agent:
        response = ToolAuthorizationResponse(
            authorized=False,
            granted_by=tool.granted_by,
            tool=tool,
            reason=f"Agent '{request.agent_id}' not found. "
                   "Cannot verify skill-based authorization.",
            failure_type=AuthorizationFailure.AGENT_NOT_FOUND,
            skill_check_passed=False,
            compute_check_passed=None
        )
        audit.log_authorization(
            agent_id=request.agent_id, tool_id=request.tool_id,
            authorized=False, reason=response.reason,
            compute_id=compute_id,
            failure_type=AuthorizationFailure.AGENT_NOT_FOUND,
        )
        return response

    agent_skill_ids = {skill.id for skill in agent.skills}
    granting_skills = set(tool.granted_by)
    matching_skills = agent_skill_ids & granting_skills

    if not matching_skills:
        response = ToolAuthorizationResponse(
            authorized=False,
            granted_by=tool.granted_by,
            tool=tool,
            reason=f"Agent lacks required skills. Tool requires one of: {tool.granted_by}",
            failure_type=AuthorizationFailure.SKILL_NOT_GRANTED,
            skill_check_passed=False,
            compute_check_passed=None
        )
        audit.log_authorization(
            agent_id=request.agent_id, tool_id=request.tool_id,
            authorized=False, reason=response.reason,
            compute_id=compute_id,
            failure_type=AuthorizationFailure.SKILL_NOT_GRANTED,
        )
        return response

    # Part 2: Compute has capability (if compute info provided)
    if request.compute:
        # Check compute has the tool
        if request.tool_id not in request.compute.tools_available:
            response = ToolAuthorizationResponse(
                authorized=False,
                granted_by=sorted(list(matching_skills)),
                tool=tool,
                reason=f"Compute '{request.compute.instance_id}' does not have "
                       f"tool '{request.tool_id}' available. "
                       "Skill authorization passed, but compute lacks the tool.",
                failure_type=AuthorizationFailure.COMPUTE_MISSING_TOOL,
                skill_check_passed=True,
                compute_check_passed=False
            )
            audit.log_authorization(
                agent_id=request.agent_id, tool_id=request.tool_id,
                authorized=False, reason=response.reason,
                compute_id=compute_id,
                failure_type=AuthorizationFailure.COMPUTE_MISSING_TOOL,
                granted_by=sorted(list(matching_skills)),
            )
            return response

        # Check compute has required labels
        if tool.required_labels:
            compute_labels = set(request.compute.labels)
            required_labels = set(tool.required_labels)
            missing_labels = required_labels - compute_labels

            if missing_labels:
                response = ToolAuthorizationResponse(
                    authorized=False,
                    granted_by=sorted(list(matching_skills)),
                    tool=tool,
                    reason=f"Compute '{request.compute.instance_id}' missing required "
                           f"labels: {sorted(list(missing_labels))}. "
                           "Skill authorization passed, but compute lacks required labels.",
                    failure_type=AuthorizationFailure.COMPUTE_MISSING_LABELS,
                    skill_check_passed=True,
                    compute_check_passed=False,
                    missing_labels=sorted(list(missing_labels))
                )
                audit.log_authorization(
                    agent_id=request.agent_id, tool_id=request.tool_id,
                    authorized=False, reason=response.reason,
                    compute_id=compute_id,
                    failure_type=AuthorizationFailure.COMPUTE_MISSING_LABELS,
                    granted_by=sorted(list(matching_skills)),
                )
                return response

    # Both checks passed
    reason = f"Agent has skill(s) {sorted(list(matching_skills))} which grant {tool.id}"
    if request.compute:
        reason += f" and compute '{request.compute.instance_id}' has required capabilities"

    response = ToolAuthorizationResponse(
        authorized=True,
        granted_by=sorted(list(matching_skills)),
        tool=tool,
        reason=reason,
        skill_check_passed=True,
        compute_check_passed=True if request.compute else None
    )
    audit.log_authorization(
        agent_id=request.agent_id, tool_id=request.tool_id,
        authorized=True, reason=reason,
        compute_id=compute_id,
        granted_by=sorted(list(matching_skills)),
    )
    return response


@tools_router.get("/{tool_id}", response_model=ToolDefinition)
async def get_tool(tool_id: str):
    """Get a specific tool by ID.

    Args:
        tool_id: Tool identifier

    Returns:
        Tool details

    Raises:
        HTTPException: If tool not found
    """
    registry = get_skill_registry()
    tool = registry.get_tool(tool_id)

    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_id}' not found"
        )

    return tool


# ============================================================================
# AGENT ENDPOINTS
# ============================================================================
# These endpoints provide access to composed agents for verification and auditing


@agents_router.get("", response_model=AgentListResponse)
async def list_agents(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by agent status (e.g., 'deployed')"
    )
):
    """List all composed agents.

    Returns all agents that have been composed through the /skills/compose endpoint.
    These agents are cached in memory for authorization lookups.

    Args:
        status_filter: Optional status filter (reserved for future use)

    Returns:
        List of composed agents with total count
    """
    service = get_composition_service()

    try:
        agents = service.list_agents()
        # Status filtering reserved for future implementation
        # when agents have lifecycle states
        return AgentListResponse(
            agents=agents,
            total=len(agents)
        )
    except Exception as e:
        logger.error(f"Error listing agents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while listing agents"
        )


@agents_router.get("/cache/stats", response_model=AgentCacheStats)
async def get_agent_cache_stats():
    """Get agent cache statistics.

    Returns statistics about the agent cache including:
    - Current size and max capacity
    - TTL configuration
    - Hit/miss counts and hit rate
    - Eviction count

    Returns:
        AgentCacheStats with current cache metrics
    """
    service = get_composition_service()

    try:
        return service.get_cache_stats()
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving cache statistics"
        )


@agents_router.delete("/cache", status_code=status.HTTP_200_OK)
async def clear_agent_cache():
    """Clear all agents from the cache.

    This is an administrative operation that removes all cached agents.
    Use with caution as it will invalidate all agent authorization lookups.

    Returns:
        Number of agents cleared from cache
    """
    service = get_composition_service()

    try:
        count = service.clear_cache()
        return {"cleared": count, "message": f"Cleared {count} agents from cache"}
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while clearing cache"
        )


@agents_router.get("/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str):
    """Get a composed agent by ID.

    Retrieves a previously composed agent for verification or auditing.
    Agents are created via the /skills/compose endpoint.

    Args:
        agent_id: Agent instance identifier

    Returns:
        Agent details including skills, merged instructions, and tools

    Raises:
        HTTPException: If agent not found
    """
    service = get_composition_service()
    agent = service.get_agent(agent_id)

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found"
        )

    return agent


# ============================================================================
# AUTHORIZATION AUDIT ENDPOINTS
# ============================================================================
# These endpoints provide access to the authorization audit log for
# security compliance, debugging, and threat detection.


@audit_router.get("/authorizations", response_model=AuthorizationAuditQueryResponse)
async def query_authorization_audit(
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    tool_id: Optional[str] = Query(None, description="Filter by tool ID"),
    authorized: Optional[bool] = Query(None, description="Filter by authorization result"),
    compute_id: Optional[str] = Query(None, description="Filter by compute instance ID"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
):
    """Query authorization audit log entries.

    Returns audit entries in reverse chronological order (newest first).
    Supports filtering by agent, tool, compute, and authorization result.

    Args:
        agent_id: Filter by agent ID
        tool_id: Filter by tool ID
        authorized: Filter by True (granted) or False (denied)
        compute_id: Filter by compute instance ID
        skip: Number of records to skip
        limit: Max records to return (default 100, max 1000)

    Returns:
        Matching audit entries with pagination metadata
    """
    audit = get_authorization_audit_service()

    entries, total = audit.query(
        agent_id=agent_id,
        tool_id=tool_id,
        authorized=authorized,
        compute_id=compute_id,
        skip=skip,
        limit=limit,
    )

    failed_count = sum(1 for e in entries if not e.authorized)

    return AuthorizationAuditQueryResponse(
        entries=entries,
        total=total,
        skip=skip,
        limit=limit,
        has_more=skip + limit < total,
        failed_count=failed_count,
    )


@audit_router.get("/authorizations/stats", response_model=AuthorizationAuditStats)
async def get_authorization_audit_stats():
    """Get summary statistics for authorization audit logs.

    Returns aggregate metrics including total checks, denial rates,
    and top denied tools/agents for security monitoring.

    Returns:
        Authorization audit statistics
    """
    audit = get_authorization_audit_service()
    stats = audit.get_stats()

    return AuthorizationAuditStats(**stats)
