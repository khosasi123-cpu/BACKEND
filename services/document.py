from fastapi import HTTPException
from pathlib import Path
from sqlalchemy.orm import Session
from langchain_core.documents import Document
from dotenv import load_dotenv
import os

from tools.docx_parser.docx_parser import parse_docx
from tools.docx_parser.delete_images import delete_images, delete_file
from services.ingest import ingest_new_document, delete_document_vector
from database.crud.document import create_document, create_document_images, get_document_by_id, get_document_by_name, delete_document_db


load_dotenv()


DOCUMENT_DIR = Path(os.getenv("DOCUMENT_DIRECTORY")).resolve()

def get_document_path(db: Session, document_id: str) -> Path:
    document = get_document_by_id(db, document_id=document_id)
    document_path = DOCUMENT_DIR / document.document_name

    if not document_path.exists():
        raise FileNotFoundError(
            f"Document not found: {document.document_name}"
        )

    return document_path

def add_document(db : Session, document_name: str):
    if get_document_by_name(db, document_name=document_name) is not None:
        raise HTTPException(
            status_code=409,
            detail="Document already exists"
        )
    doc = parse_docx(str(DOCUMENT_DIR / document_name))
    document_db = create_document(
        db,
        document_name= document_name
    )
    create_document_images(
        db,
        document_db.id,
        doc.images
    )
    document = [Document(
        page_content =doc.text,
        metadata = {
                    "document_name" : document_name,
                    "document_id" : document_db.id}
    )]
    ingest_new_document(db=db, document=document)
    # TODO:
    # Implement compensating transaction to clean up
    # database, vector store, images, and files when
    # ingestion fails.
    return {
        "id" : document_db.id,
        "document_name" : document_db.document_name
    }

def delete_document(db: Session,
                    document_id: str
                    ):
    document = get_document_by_id(db, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    delete_document_vector(
        document.id
    )
    delete_images(
        document.images
    )
    delete_file(
        get_document_path(db=db, document_id=document.id)
    )
    delete_document_db(db,
           document)

if __name__=="__main__":
    print(get_document_path("HUMS_installation.md"))