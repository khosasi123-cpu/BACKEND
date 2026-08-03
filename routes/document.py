
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from fastapi.responses import FileResponse
import shutil
from sqlalchemy.orm import Session
from pathlib import Path
import os
from dotenv import load_dotenv

from services.document import get_document_path, DOCUMENT_DIR, add_document, delete_document as del_doc
from database.crud.document import get_all_documents, search_documents
from schemas import document
from database.database import get_db


load_dotenv(override=True)

IMAGE_DIRECTORY = Path(os.getenv("IMAGE_DIRECTORY"))

router = APIRouter(
    prefix="/document",
    tags=["document"]
)


@router.get("/search", response_model=document.DocumentListResponse, status_code=200)
def retrieve_document(  keyword : str,
                        page: int = Query(1, ge=1, description="Page number"),
                        page_size: int = Query(10, ge=1, description="Number of documents per page"),
                        db: Session = Depends(get_db),
                      ):
    """
    fungsi untuk cari dokumen berdasarkan nama similarity
    """
    result = search_documents(page=page, page_size=page_size, db=db, keyword=keyword)
    return {
        **result,
        "page": page,
        "page_size": page_size,
    }



@router.get("/download/{document_id}", status_code=200)
def download_document(document_id: str,
                      db: Session = Depends(get_db)
                      ): 
    """
    fungsi untuk download document
    """
    try:
        path = get_document_path(db, document_id=document_id)

        return FileResponse(
            path=path,
            filename=path.name
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    
@router.post("/upload", response_model=document.UploadDocumentResponse, status_code=201)
def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    DOCUMENT_DIR.mkdir(
        parents=True,
        exist_ok=True
)
    destination = DOCUMENT_DIR / file.filename

    with destination.open("wb") as buffer:
        shutil.copyfileobj(
            file.file,
            buffer
        )

    document = add_document(
        db=db,
        document_name=file.filename
    )
    return {
        "message": f"Document uploaded successfully.",
        "document": document
    }
    

@router.get("/", response_model=document.DocumentListResponse, status_code=200)
def get_documents(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, description="Number of documents per page"),
    db: Session = Depends(get_db),
):
    result = get_all_documents(
        db=db,
        page=page,
        page_size=page_size,
    )

    return {
        **result,
        "page": page,
        "page_size": page_size,
    }

@router.delete("/{document_id}", response_model=document.MessageResponse, status_code=200)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
                    ):
    del_doc(
        db=db,
        document_id=document_id
    )
    return {
        "message": "Document deleted successfully."
    }

@router.get("/images/{image_name}", status_code=200)
def get_image(image_name: str):

    image_path = IMAGE_DIRECTORY / image_name

    if not image_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Image not found"
        )

    return FileResponse(image_path)
