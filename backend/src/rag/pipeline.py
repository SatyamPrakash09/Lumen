import asyncio
import logging
import time
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import Documents, ChatSession
from src.rag.loader import load_document
from src.rag.splitter import split_document
from src.rag.vector_store import add_chunks_to_store
from src.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_embedding_pipeline(
    document_id: UUID,
    file_path: str,
    file_ext: str,
    session_id: str,
    db_session_maker,
) -> None:
    """Load, split, and embed a document in the background. Call via asyncio.create_task()."""
    async with db_session_maker() as db:
        try:
            await _set_document_status(db, document_id, "processing")

            logger.info(f"[Pipeline] Loading {document_id} ({file_ext})")
            documents = await load_document(file_path, file_ext)
            if not documents:
                raise ValueError("Document loaded but produced no content.")

            # Overwrite source metadata with the original human-readable filename
            stmt = select(Documents).where(Documents.id == document_id)
            res = await db.execute(stmt)
            doc_record = res.scalar_one_or_none()
            original_filename = doc_record.file_name if doc_record else None

            if original_filename:
                for doc in documents:
                    doc.metadata["source"] = original_filename

            chunks = split_document(documents)
            total_chunks = len(chunks)
            logger.info(f"[Pipeline] {total_chunks} chunks for {document_id}")

            # ── Batched embedding ──────────────────────────────────────────
            # Process chunks in small batches with async yields between them.
            # This lets the event loop serve chat requests while Ollama is
            # momentarily idle between batches.
            batch_size = settings.EMBEDDING_BATCH_SIZE
            embedded = 0
            start_time = time.perf_counter()

            for i in range(0, total_chunks, batch_size):
                batch = chunks[i : i + batch_size]

                # Run the blocking Ollama embedding call in a thread
                await asyncio.to_thread(add_chunks_to_store, session_id, batch)

                embedded += len(batch)
                elapsed = time.perf_counter() - start_time
                rate = embedded / elapsed if elapsed > 0 else 0
                logger.info(
                    f"[Pipeline] {document_id}: {embedded}/{total_chunks} chunks "
                    f"({embedded * 100 // total_chunks}%) — {rate:.0f} chunks/s"
                )

                # Yield control to the event loop so chat requests can get through
                await asyncio.sleep(0.1)

            elapsed = time.perf_counter() - start_time
            logger.info(
                f"[Pipeline] Finished {document_id}: {total_chunks} chunks in {elapsed:.1f}s"
            )

            await _set_document_status(db, document_id, "ready", total_chunks=total_chunks)
            await _update_session_status(db, session_id)

        except Exception as e:
            logger.error(f"[Pipeline] Failed for {document_id}: {e}", exc_info=True)
            
            # 1. Clean up file from local storage
            import os
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"[Pipeline] Cleaned up file {file_path} on failure")
                except Exception as cleanup_err:
                    logger.error(f"[Pipeline] Failed to delete file {file_path}: {cleanup_err}")
            
            # 2. Clean up document record from DB
            try:
                stmt = select(Documents).where(Documents.id == document_id)
                res = await db.execute(stmt)
                doc_record = res.scalar_one_or_none()
                if doc_record:
                    await db.delete(doc_record)
                    await db.commit()
                    logger.info(f"[Pipeline] Deleted doc record {document_id} from DB on failure")
            except Exception as db_err:
                logger.error(f"[Pipeline] Failed to delete doc record {document_id} from DB: {db_err}")
                await db.rollback()

            # 3. Update session status
            await _update_session_status(db, session_id)


async def _set_document_status(
    db: AsyncSession,
    document_id: UUID,
    status: str,
    total_chunks: int = 0,
) -> None:
    values = {"status": status}
    if total_chunks:
        values["total_chunks"] = total_chunks
    await db.execute(update(Documents).where(Documents.id == document_id).values(**values))
    await db.commit()


async def _update_session_status(db: AsyncSession, session_id: str) -> None:
    """Recompute session embedding_status from all its documents."""
    result = await db.execute(select(Documents).where(Documents.session_id == session_id))
    docs = result.scalars().all()
    if not docs:
        return

    statuses = {doc.status for doc in docs}
    if statuses == {"ready"}:
        new_status = "ready"
    elif "processing" in statuses:
        new_status = "processing"
    elif "failed" in statuses:
        new_status = "failed"
    else:
        new_status = "pending"

    await db.execute(
        update(ChatSession)
        .where(ChatSession.session_id == session_id)
        .values(embedding_status=new_status)
    )
    await db.commit()
