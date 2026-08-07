from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database.database import Base
from uuid import uuid4

class Document(Base):
    __tablename__ = "document"
    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid4()),
        index=True
    )
    document_name = Column(
        String,
        nullable=False,
    )
    images = relationship(
        "DocumentImage",
        back_populates="document",
        cascade="all, delete-orphan"
    )
    chunks = relationship(
        "Chunk",
        back_populates="document",
        cascade="all, delete-orphan"
    )
