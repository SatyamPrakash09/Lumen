import os
from fastapi import HTTPException
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader,
    CSVLoader,
)


async def load_pdf_document(file_path: str):
    try:
        loader = PyPDFLoader(file_path)
        documents = loader.load()
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading PDF: {str(e)}")


async def load_text_document(file_path: str):
    try:
        loader = TextLoader(file_path, encoding="utf-8")
        documents = loader.load()
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading text file: {str(e)}")


async def load_docx_document(file_path: str):
    try:
        loader = Docx2txtLoader(file_path)
        documents = loader.load()
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading DOCX file: {str(e)}")


async def load_markdown_document(file_path: str):
    try:
        loader = TextLoader(file_path, encoding="utf-8")
        documents = loader.load()
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading Markdown file: {str(e)}")


async def load_csv_document(file_path: str):
    try:
        loader = CSVLoader(file_path)
        documents = loader.load()
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading CSV file: {str(e)}")


async def load_document(file_path: str, ext: str):
    """Unified dispatcher — routes to the correct loader based on file extension."""
    ext = ext.lower().lstrip(".")
    loaders = {
        "pdf": load_pdf_document,
        "txt": load_text_document,
        "docx": load_docx_document,
        "md": load_markdown_document,
        "csv": load_csv_document,
    }
    loader_fn = loaders.get(ext)
    if loader_fn is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension: .{ext}"
        )
    return await loader_fn(file_path)
