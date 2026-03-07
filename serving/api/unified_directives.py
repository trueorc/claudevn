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

import logging

from fastapi import APIRouter, HTTPException, Query

from models.unified_directive import (
    DirectiveCommentCreateRequest,
    UnifiedDirective,
    UnifiedDirectiveCreateRequest,
    UnifiedDirectiveListResponse,
)
from services.unified_directive_service import get_unified_directive_service
from services.conflict_detector import get_conflict_detector
from services.conversation_service import get_conversation_service
from middleware.user_context import get_current_user, get_current_user_id as get_context_user_id

logger = logging.getLogger(__name__)

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

    # Populate user attribution
    user_id = get_context_user_id()
    display_name = None
    if user_id:
        directive.created_by = user_id
        user = get_current_user()
        if user:
            display_name = user.get("username") or user.get("email")
            directive.created_by_name = display_name
        await service._save_directive_to_redis(directive)

    # Conflict detection: check before recording so we don't compare against self
    detector = get_conflict_detector()
    conflict = detector.check_conflicts(
        user_id=user_id or "anonymous",
        text=request.text,
        project_id=request.project_id,
    )
    detector.record_directive(
        user_id=user_id or "anonymous",
        display_name=display_name or user_id or "anonymous",
        text=request.text,
        project_id=request.project_id,
    )

    if conflict:
        conv_service = get_conversation_service()
        if conv_service:
            try:
                await conv_service.add_message(
                    project_id=request.project_id,
                    user_id="system",
                    display_name="System",
                    type="attention",
                    content=(
                        f"Potential conflict: {conflict['other_user']} recently directed "
                        f"\"{conflict['other_text'][:100]}\" which may contradict this directive."
                    ),
                    metadata={
                        'conflict_type': conflict['type'],
                        'other_user': conflict['other_user'],
                        'other_text': conflict['other_text'],
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to persist conflict attention message: {e}")

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
        user_id = get_context_user_id()
        user = get_current_user() if user_id else None
        created_by = user_id or "user"
        created_by_name = (user.get("username") or user.get("email")) if user else None

        directive = await service.add_comment(
            project_id=project_id,
            directive_id=directive_id,
            content=request.content,
            created_by=created_by,
            created_by_name=created_by_name,
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
