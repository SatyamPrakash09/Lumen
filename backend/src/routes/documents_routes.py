from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, File, Request, Response, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from src.controllers.auth_controller import current_user
from src.database.db import get_async_session
from src.models.models import Documents
from sqlalchemy import select
from src.controllers.document_controller import get_all_uploaded_documents, get_uploaded_document, upload_document


router = APIRouter()

@router.get("/")
async def get_documents(
    db: AsyncSession = Depends(get_async_session),
    user = Depends(current_user)
):
    return await get_all_uploaded_documents(db, user)


@router.post("/")
async def upload_document_to_db(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_session), 
    user = Depends(current_user)
):
    return await upload_document(file, db, user)



@router.get("/{document_id}")
async def get_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_async_session), user = Depends(current_user)):
    return await get_uploaded_document(document_id, db, user)