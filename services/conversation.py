from fastapi import HTTPException
from sqlalchemy.orm import Session

from database.model.conversation import Conversation


from database.crud import conversation as conversation_crud
from database.crud import messages as message_crud

VALID_ROLES = {
    "user",
    "assistant"
}


def _require_conversation(
    db: Session,
    conversation_id: int
) -> Conversation:
    """
    Get a conversation or raise 404 if it does not exist.
    """

    conversation = conversation_crud.get_conversation_by_id(
        db,
        conversation_id
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    return conversation


def create_conversation(
    db: Session,
    title: str = "New Conversation"
) -> Conversation:
    """
    Create a new conversation.
    """

    title = title.strip()

    if not title:
        title = "New Conversation"

    return conversation_crud.create_conversation(
        db=db,
        title=title
    )


def get_conversation(
    db: Session,
    conversation_id: int
) -> Conversation:
    """
    Get a conversation by its ID.
    """

    return _require_conversation(
        db,
        conversation_id
    )


def list_conversations(
    db: Session
) -> list[Conversation]:
    """
    Get all conversations.
    """

    return conversation_crud.get_all_conversations(
        db
    )


def update_conversation_title(
    db: Session,
    conversation_id: int,
    title: str
) -> Conversation:
    """
    Update conversation title.
    """

    conversation = _require_conversation(
        db,
        conversation_id
    )

    title = title.strip()

    if not title:
        raise HTTPException(
            status_code=400,
            detail="Title cannot be empty"
        )

    return conversation_crud.update_conversation_title(
        db=db,
        conversation=conversation,
        new_title=title
    )


def delete_conversation(
    db: Session,
    conversation_id: int
) -> None:
    """
    Delete a conversation.
    """

    conversation = _require_conversation(
        db,
        conversation_id
    )

    conversation_crud.delete_conversation(
        db=db,
        conversation=conversation
    )
