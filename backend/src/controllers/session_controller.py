import asyncio
import logging
import os
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import get_settings
from src.database.db import async_session_maker
from src.models.models import ChatSession, Documents, User
from src.rag.pipeline import run_embedding_pipeline
from src.rag.vector_store import delete_collection
from src.utils.validate_document import validate_upload

settings = get_settings()
logger = logging.getLogger(__name__)


async def create_session(title: str | None, user: User, db: AsyncSession) -> ChatSession:
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    session = ChatSession(
        session_id=str(uuid.uuid4()),
        user_id=user.id,
        title=title or "New Chat",
        embedding_status="pending",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info(f"[Session] Created {session.session_id} for user {user.id}")
    return session


async def get_user_sessions(user: User, db: AsyncSession) -> list[ChatSession]:
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    stmt = (
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_session(session_id: str, user: User, db: AsyncSession) -> ChatSession:
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    stmt = select(ChatSession).where(
        ChatSession.session_id == session_id,
        ChatSession.user_id == user.id,
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


async def delete_session(session_id: str, user: User, db: AsyncSession) -> dict:
    session = await get_session(session_id, user, db)
    delete_collection(session_id)
    await db.delete(session)
    await db.commit()
    logger.info(f"[Session] Deleted {session_id}")
    return {"message": "Session deleted successfully"}


async def attach_documents_to_session(
    session_id: str,
    files: list[UploadFile],
    user: User,
    db: AsyncSession,
) -> list[Documents]:
    session = await get_session(session_id, user, db)

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Step 1: Pre-validate all files to avoid partial success/failures
    validated_temp_paths = []
    for file in files:
        if not file.filename:
            raise HTTPException(status_code=400, detail="A file has no filename")

        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type .{ext} not allowed. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}",
            )

        try:
            temp_path = await validate_upload(file)
            validated_temp_paths.append((file, temp_path, ext))
        except ValueError as ve:
            # Clean up previously validated temp files in this request
            for _, tp, _ in validated_temp_paths:
                Path(tp).unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as e:
            for _, tp, _ in validated_temp_paths:
                Path(tp).unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"Validation error: {str(e)}")

    # Step 2: Save files to persistent local storage and insert metadata into DB
    created_docs: list[tuple[Documents, str, str]] = []
    try:
        for file, temp_path, ext in validated_temp_paths:
            user_dir = os.path.join(settings.UPLOAD_DIR, str(user.id), session_id)
            os.makedirs(user_dir, exist_ok=True)
            stored_filename = f"{uuid.uuid4().hex}.{ext}"
            filepath = os.path.join(user_dir, stored_filename)
            shutil.move(temp_path, filepath)

            file_size = Path(filepath).stat().st_size

            new_doc = Documents(
                user_id=user.id,
                session_id=session_id,
                file_name=file.filename,
                file_path=filepath,
                file_size=file_size,
                file_type=ext,
                status="pending",
            )
            db.add(new_doc)
            created_docs.append((new_doc, filepath, ext))

        await db.commit()
        for doc, _, _ in created_docs:
            await db.refresh(doc)
    except Exception as e:
        await db.rollback()
        # Clean up files saved in this transaction
        for _, filepath, _ in created_docs:
            Path(filepath).unlink(missing_ok=True)
        # Clean up any remaining temp files
        for _, temp_path, _ in validated_temp_paths:
            Path(temp_path).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to save documents: {str(e)}")

    # Step 3: Spawn background embedding pipelines
    for doc, filepath, ext in created_docs:
        asyncio.create_task(
            run_embedding_pipeline(
                document_id=doc.id,
                file_path=filepath,
                file_ext=ext,
                session_id=session_id,
                db_session_maker=async_session_maker,
            )
        )
        logger.info(f"[Session] Queued embedding for doc {doc.id}")

    session.embedding_status = "processing"
    await db.commit()

    return [doc for doc, _, _ in created_docs]


async def get_session_documents(
    session_id: str, user: User, db: AsyncSession
) -> list[Documents]:
    await get_session(session_id, user, db)
    stmt = select(Documents).where(Documents.session_id == session_id)
    result = await db.execute(stmt)
    return result.scalars().all()
