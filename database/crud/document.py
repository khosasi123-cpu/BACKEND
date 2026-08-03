from sqlalchemy.orm import Session, joinedload

from database.model.document import Document
from database.model.document_image import DocumentImage
from tools.docx_parser import ExtractedImage


def create_document(
    db: Session,
    document_name: str
) -> Document:
    """
    Create new document metadata.
    """

    document = Document(
        document_name=document_name
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document

def create_document_images(
        db: Session,
        document_id: str,
        images: list[ExtractedImage] 
) -> None:
    """
    Create new document picture metada
    """
    document_images = [
        DocumentImage(
            document_id = document_id,
            filename = image.filename
        )
        for image in images
    ]
    db.add_all(document_images)
    db.commit()

    
def get_document_by_id(
    db: Session,
    document_id: str
) -> Document | None:
    """
    Get document by id.
    """

    return (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
    )


def get_document_by_name(
    db: Session,
    document_name: str
) -> Document | None:
    """
    Get document by filename.
    """

    return (
        db.query(Document)
        .options(joinedload(Document.images))
        .filter(Document.document_name == document_name)
        .first()
    )


def get_all_documents(
    db: Session,
    page: int = 1,
    page_size: int = 10
) -> dict:
    """
    Get all documents.
    """
    offset = (page - 1) * page_size
    total = db.query(Document).count()
    items =(
        db.query(Document)
        .order_by(Document.document_name)
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "items": items
    }


def delete_document_db(
    db: Session,
    document: Document
) -> None:
    """
    Delete document metadata.
    """

    db.delete(document)
    db.commit()

def search_documents(
    page: int,
    page_size: int,
    db: Session,
    keyword: str
) -> dict:

    offset = (page - 1) * page_size

    items = (
        db.query(Document)
        .filter(
            Document.document_name.ilike(f"%{keyword}%")
        )
        .order_by(Document.document_name)
        .offset(offset)
        .limit(page_size)
        .all()
    )
    total = (
        db.query(Document)
        .filter(
            Document.document_name.ilike(f"%{keyword}%")
        )
        .count()
    )
    return {
        "total": total,
        "items": items
    }