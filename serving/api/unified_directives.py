"""API router for unified directives.

Provides a single entry point for all user intents — new work requests,
priority shifts, combined directives, and conversation follow-ups.

Endpoints:
    POST   /unified-directives              - Submit a new directive
    POST   /unified-directives/{id}/comments - Add a comment to a directive
    GET    /unified-directives              - List all directives
    GET    /unified-directives/{id}         - Get a specific directive
    DELETE /unified-directives              - Delete all directives for a project

Reference: Issue #613 - Unified Directives Backend
"""

from fastapi import APIRouter, HTTPException, Query

from models.unified_directive import (
    DirectiveCommentCreateRequest,
    UnifiedDirective,
    UnifiedDirectiveCreateRequest,
    UnifiedDirectiveListResponse,
)
from services.unified_directive_service import get_unified_directive_service

router = APIRouter(prefix="/unified-directives", tags=["unified-directives"])


# =============================================================================
# Endpoints
# =============================================================================


@router.post("", response_model=UnifiedDirective)
async def submit_directive(request: UnifiedDirectiveCreateRequest):
    """Submit a new unified directive.

    Accepts any natural language input, classifies intent (new_work,
    priority_shift, combined, clarification), and routes to the
    appropriate handler.

    Examples:
    - "Build a user authentication system" -> new_work
    - "Accelerate testing for the frontend" -> priority_shift
    - "Create payment integration and focus on security" -> combined
    """
    service = get_unified_directive_service()
    directive = await service.submit(
        project_id=request.project_id,
        text=request.text,
        parent_directive_id=request.parent_directive_id,
    )
    return directive


@router.post("/{directive_id}/comments", response_model=UnifiedDirective)
async def add_comment(
    directive_id: str,
    request: DirectiveCommentCreateRequest,
    project_id: str = Query(...),
):
    """Add a comment to an existing directive.

    Used for conversation follow-ups, clarifications, and feedback
    on processing results.
    """
    service = get_unified_directive_service()
    try:
        directive = await service.add_comment(
            project_id=project_id,
            directive_id=directive_id,
            content=request.content,
        )
        return directive
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("", response_model=UnifiedDirectiveListResponse)
async def list_directives(
    project_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List unified directives for a project.

    Returns directives ordered by most recent first.
    """
    service = get_unified_directive_service()
    directives = await service.list_directives(
        project_id=project_id,
        limit=limit,
    )
    return UnifiedDirectiveListResponse(
        items=directives,
        total=len(directives),
    )


@router.delete("")
async def delete_directives(
    project_id: str = Query(...),
):
    """Delete all unified directives for a project.

    Removes both individual item keys and the history list from Redis.
    Used for data cleanup and system resets.
    """
    service = get_unified_directive_service()
    deleted = await service.delete_project_directives(project_id)
    return {"deleted": deleted, "project_id": project_id}


@router.get("/{directive_id}", response_model=UnifiedDirective)
async def get_directive(
    directive_id: str,
    project_id: str = Query(...),
):
    """Get a specific unified directive by ID."""
    service = get_unified_directive_service()
    directive = await service.get_directive(
        project_id=project_id,
        directive_id=directive_id,
    )
    if not directive:
        raise HTTPException(
            status_code=404,
            detail=f"Directive {directive_id} not found",
        )
    return directive
