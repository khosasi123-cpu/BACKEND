from database.model.document_image import DocumentImage
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()
IMAGE_DIRECTORY = Path(os.getenv("IMAGE_DIRECTORY")).resolve()


def delete_file(
    path: Path,
) -> None:
    file_path = Path(path)
    if file_path.exists():
        file_path.unlink()

def delete_images(
    images: list[DocumentImage],
) -> None:

    for image in images:
        delete_file(
            IMAGE_DIRECTORY / image.filename
        )