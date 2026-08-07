from sqlalchemy.orm import Session, joinedload


from database.model.chunk import Chunk

def create_chunks(
    db: Session,
    chunks: list[Chunk]
) -> list[Chunk]:
    """
    Create new chunks.
    """
    db.add_all(chunks)
    db.commit()
    
    return chunks

def get_chunk_by_id(
    db: Session,
    chunk_id: str
) -> Chunk | None:
    """
    Get chunk by its ID.
    """

    return (
        db.query(Chunk)
        .options(joinedload(Chunk.document))
        .filter(Chunk.id == chunk_id)
        .first()
    )

def get_chunks_by_ids(
    db: Session,
    chunk_ids: list[str]
) -> list[Chunk]:

    chunks = (
        db.query(Chunk)
        .options(joinedload(Chunk.document))
        .filter(Chunk.id.in_(chunk_ids))
        .all()
    )

    chunk_map = {
        chunk.id: chunk
        for chunk in chunks
    }

    return [
        chunk_map[chunk_id]
        for chunk_id in chunk_ids
        if chunk_id in chunk_map
    ]


