import shutil

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from database.database import get_db
from services.chat import chat as chat_with_AI
from schemas.chat import ChatRequest, ChatResponse
from pathlib import Path


TEMP_DIR = Path("./data/temp")

router = APIRouter(
    prefix="/chat",
    tags=["chat"]
)

@router.post("/", response_model=ChatResponse)
def create_chat(
    question: str = Form(...),
    conversation_id: int = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    file_ids: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
): 
    if len(files) != len(file_ids):
        raise HTTPException(
            status_code=400,
            detail="The number of files and file_ids must match"
        )
    
    user_request = ChatRequest(
        question=question,
        conversation_id=conversation_id,
        file_ids=file_ids,
    )
    for file, file_id  in zip(files, file_ids):
        file_path = TEMP_DIR / file_id
        file_path.mkdir(parents=True, exist_ok=True)
        input_file_path = file_path / "input.pdf"
        with open(input_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    return chat_with_AI(user_request, db)