from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse
import shutil
from sqlalchemy.orm import Session
from pathlib import Path
from services.retrieval import retrieval
from services.document import get_document_path, DOCUMENT_DIR, add_document, delete_document as del_doc
from database.crud.document import get_all_documents, search_documents
from schemas import document
from database.database import get_db
import os
from dotenv import load_dotenv

load_dotenv(override=True)

IMAGE_DIRECTORY = Path(os.getenv("IMAGE_DIRECTORY"))

router = APIRouter(
    prefix="/document",
    tags=["document"]
)


@router.get("/search", response_model=list[document.DocumentResult])
def retrieve_document(keyword : str,
                      db: Session = Depends(get_db)
                      ):
    """
    fungsi untuk cari dokumen berdasarkan nama similarity
    """
    return search_documents(db, keyword=keyword)
    



@router.get("/{document_name}")
def download_document(document_name: str): 
    """
    fungsi untuk download document
    """
    try:
        path = get_document_path(document_name)

        return FileResponse(
            path=path,
            filename=path.name
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    
@router.post("/upload")
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

    return add_document(
        db=db,
        document_name=file.filename
    )

@router.get(
    "/",
)
def get_documents(
    db: Session = Depends(get_db)
):

    documents = get_all_documents(db)

    return {
        "documents": documents
    }

@router.delete("/{document_name}")
def delete_document(
    document_name : str,
    db: Session = Depends(get_db),
                    ):
    del_doc(
        db=db,
        document_name=document_name
    )
    return {
        "message": "Document deleted successfully."
    }

@router.get("/images/{image_name}")
def get_image(image_name: str):

    image_path = IMAGE_DIRECTORY / image_name

    if not image_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Image not found"
        )

    return FileResponse(image_path)

@router.get("/images/{image_name}")
def get_image(image_name: str):

    image_path = IMAGE_DIRECTORY / image_name

    if not image_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Image not found"
        )

    return FileResponse(image_path)