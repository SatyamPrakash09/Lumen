
import shutil
import tempfile

from fastapi import UploadFile
from pathlib import Path

from src.config.settings import get_settings
settings = get_settings()
async def validate_upload(file: UploadFile):
    if not file.filename:
        raise ValueError("No filename provided")
    ext = Path(file.filename).suffix.lower()
    if ext.lstrip(".") not in settings.ALLOWED_EXTENSIONS:
        raise ValueError(f"File type {ext} not allowed. Allowed types: {', '.join(settings.ALLOWED_EXTENSIONS)}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        shutil.copyfileobj(file.file, tmp)
        temp_path = tmp.name
    try:
        size = Path(temp_path).stat().st_size
        if size == 0:
            raise ValueError("Uploaded file is empty")
        if size > settings.UPLOAD_MAX_SIZE:
            Path(temp_path).unlink(missing_ok=True)
            raise ValueError(f"File size exceeds the maximum allowed size of {settings.UPLOAD_MAX_SIZE} bytes")
        mime_type = file.content_type
        if mime_type not in settings.ALLOWED_MIME_TYPES.get(ext, []):
            Path(temp_path).unlink(missing_ok=True)
            raise ValueError(f"File content type {mime_type} does not match allowed types")
        
        # Deep content validation 
        try:
            if ext == ".pdf":
                from PyPDF2 import PdfReader
                with open(temp_path, "rb") as f:
                    PdfReader(f)
            elif ext in [".docx"]:
                from docx import Document
                Document(temp_path)
            elif ext in [".txt", ".md", ".csv"]:
                with open(temp_path, "r", encoding="utf-8") as f:
                    f.read(1024)  # Read a small portion to check for encoding issues
        except Exception as e:
            Path(temp_path).unlink(missing_ok=True)
            raise ValueError(f"Error occurred while validating file content: {str(e)}")
        return temp_path
    finally:
        pass
