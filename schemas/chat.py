from pydantic import BaseModel

# request models

class ChatFile(BaseModel):
    file_id: str
    filename: str
    content_type: str

class ChatRequest(BaseModel):
    conversation_id: int | None = None
    question: str
    file_ids: list[str] = []





# response models
class ReferenceResponse(BaseModel):
    document_name: str
    images: list[str] = []

class LLMResponse(BaseModel):
    answer: str
    references: list[ReferenceResponse] = []

class ChatResponse(LLMResponse):
    conversation_id: int
    

