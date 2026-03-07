"""Conversation API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.users import get_current_user_id, get_optional_user_id
from models.conversation import ConversationResponse, SendMessageRequest
from services.conversation_service import get_conversation_service

router = APIRouter(prefix="/projects/{project_id}/conversation", tags=["conversation"])


@router.get("", response_model=ConversationResponse)
async def get_conversation(
    project_id: str,
    limit: int = Query(default=500, ge=1, le=500),
    before: Optional[str] = Query(default=None),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """Get conversation messages for a project."""
    service = get_conversation_service()
    if not service:
        raise HTTPException(status_code=503, detail="Conversation service not available")

    messages, total, has_more = await service.get_messages(
        project_id=project_id,
        limit=limit,
        before=before,
    )

    return ConversationResponse(messages=messages, total=total, has_more=has_more)


@router.post("", status_code=201)
async def send_message(
    project_id: str,
    body: SendMessageRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Send a message to a project conversation."""
    service = get_conversation_service()
    if not service:
        raise HTTPException(status_code=503, detail="Conversation service not available")

    # Get user display name
    from services.user_service import get_user_service
    user_service = get_user_service()
    display_name = "Unknown"
    if user_service:
        user = await user_service.get_user(user_id)
        if user:
            display_name = user.username

    msg = await service.add_message(
        project_id=project_id,
        user_id=user_id,
        display_name=display_name,
        type=body.type,
        content=body.content,
        metadata=body.metadata,
    )

    return msg.model_dump()


@router.delete("", status_code=204)
async def clear_conversation(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Clear conversation for a project."""
    service = get_conversation_service()
    if not service:
        raise HTTPException(status_code=503, detail="Conversation service not available")

    await service.clear(project_id)
