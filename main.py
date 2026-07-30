from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.database import Base, engine
from database.model.document import Document
from database.model.document_image import DocumentImage
from database.model.conversation import Conversation
from database.model.message import Message

from routes.document import router as document_router
from routes.chat import router as chat_router
from routes.conversation import router as conversation_router
from services.ingest import init_vector_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    init_vector_db()
    yield


app = FastAPI(lifespan=lifespan)

app.include_router(document_router)
app.include_router(chat_router)
app.include_router(conversation_router)


@app.get("/health")
def health():
    return {"status": "ok"}



app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)