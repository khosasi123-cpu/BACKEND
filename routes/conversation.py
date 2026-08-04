from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from database.database import get_db

from schemas.conversation import (
    ConversationUpdateRequest,
    ConversationResponse,
    ConversationSummaryResponse
)

from services import conversation as conversation_service

router = APIRouter(
    prefix="/conversation",
    tags=["Conversation"]
)


@router.get(
    "/",
    response_model=list[ConversationSummaryResponse]
)
def list_conversations(
    db: Session = Depends(get_db)
):
    """
    Get all conversations.
    """

    return conversation_service.list_conversations(
        db=db
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse
)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a conversation by ID.
    """

    return conversation_service.get_conversation(
        db=db,
        conversation_id=conversation_id
    )


@router.patch(
    "/{conversation_id}",
    response_model=ConversationResponse
)
def update_conversation(
    conversation_id: int,
    payload: ConversationUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Update conversation title.
    """

    return conversation_service.update_conversation_title(
        db=db,
        conversation_id=conversation_id,
        title=payload.title
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a conversation.
    """

    conversation_service.delete_conversation(
        db=db,
        conversation_id=conversation_id
    )
