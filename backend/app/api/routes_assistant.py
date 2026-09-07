"""SOC assistant chat endpoint (Part 6)."""

from typing import Any

from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user
from app.schemas.assistant import AssistantMessage, AssistantResponse
from app.services import assistant_service

router = APIRouter(prefix="/assistant", tags=["SOC Assistant"])


@router.post("/chat", response_model=AssistantResponse)
async def chat_with_assistant(
    payload: AssistantMessage, user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Answer an analyst question grounded in recent alert context."""
    return await assistant_service.chat_with_assistant(
        payload.message, user_id=user.id, user_name=user.email or user.id
    )
