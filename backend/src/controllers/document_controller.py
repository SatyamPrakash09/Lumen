


import os
import shutil
import tempfile
import uuid
from fastapi import APIRouter, Depends, File, Request, Response, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from pathlib import Path
from sqlalchemy import select
from src.models.models import Documents, User
from src.config.settings import get_settings
from src.utils.validate_document import validate_upload
settings = get_settings()

async def get_all_uploaded_documents(db: AsyncSession, user: User):
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        stmt = select(Documents).where(Documents.user_id == user.id)
        result = await db.execute(stmt)
        documents = result.scalars().all()
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

async def upload_document(file: UploadFile, db: AsyncSession, user: User):
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, 
                            detail=f"File type .{ext} not allowed. Allowed types: {', '.join(settings.ALLOWED_EXTENSIONS)}")

    try:
        temp_path = await validate_upload(file)

        user_dir = os.path.join(settings.UPLOAD_DIR, str(user.id))
        os.makedirs(user_dir, exist_ok=True)

        stored_filename = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(user_dir, stored_filename)

        # Move temp file to final destination
        shutil.move(temp_path, filepath)

        file_size = Path(filepath).stat().st_size
        new_doc = Documents(
            user_id=user.id,
            file_name=file.filename,
            file_path=filepath,
            file_size=file_size,
            file_type=ext,
            status="pending"
        )
        db.add(new_doc)
        await db.commit()
        await db.refresh(new_doc)
        return new_doc
    except Exception as e:
        await db.rollback()
        Path(filepath).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e))

    
    
async def get_uploaded_document(document_id: uuid.UUID, db: AsyncSession, user: User):
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        stmt = select(Documents).where(Documents.id == document_id, Documents.user_id == user.id)
        result = await db.execute(stmt)
        document = result.scalar_one_or_none()
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return document
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))