from pydantic import BaseModel, Field, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(
        ...,
        description="Unique identifier of the document",
        examples=["43e6367f-f153-433a-ab3c-018b6461e3ad"],
    )

    document_name: str = Field(
        ...,
        description="The name of the document",
        examples=["NAVFIT98A Troubleshooting Guide.docx"],
    )


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse] = Field(
        ...,
        description="List of documents for the current page",
    )

    total: int = Field(
        ...,
        description="Total number of documents",
        examples=[125],
    )

    page: int = Field(
        ...,
        description="Current page number",
        examples=[1],
    )

    page_size: int = Field(
        ...,
        description="Number of documents per page",
        examples=[10],
    )

class UploadDocumentResponse(BaseModel):
    message: str = Field(
        ...,
        description="Upload result"
    )

    document: DocumentResponse

class MessageResponse(BaseModel):
    message: str = Field(
        ...,
        description="Operation result message"
    )