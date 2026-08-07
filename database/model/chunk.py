from sqlalchemy import Column, Integer, String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from database.database import Base


class Chunk(Base):
    __tablename__ = "chunk"

    id = Column(
        String,
        primary_key=True,
        index=True
    )

    document_id = Column(
        String,
        ForeignKey("document.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    chunk_index = Column(
        Integer,
        nullable=False
    )

    text = Column(
        Text,
        nullable=False
    )

    document = relationship(
        "Document",
        back_populates="chunks"
    )
