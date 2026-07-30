from pydantic import BaseModel

class ChatRequest(BaseModel):
    conversation_id: int | None = None
    question: str

class ReferenceResponse(BaseModel):
    document_name: str
    images: list[str] = []

class LLMResponse(BaseModel):
    answer: str
    references: list[ReferenceResponse]

class ChatResponse(LLMResponse):
    conversation_id: int
    

