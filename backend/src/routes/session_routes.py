from typing import List
from fastapi import APIRouter, Body, Depends, File, Query, UploadFile, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.utils.limiter import limiter
from src.controllers.auth_controller import current_user
from src.controllers.session_controller import (
    attach_documents_to_session,
    create_session,
    delete_session,
    get_session,
    get_session_documents,
    get_user_sessions,
)
from src.controllers.chat_controller import agent_chat, agent_chat_stream, get_chat_history
from src.database.db import get_async_session
from src.schemas.schema import (
    AgentResponseSchema,
    ChatRequestSchema,
    ChatSessionResponseSchema,
    CreateSessionSchema,
    DocumentResponseSchema,
    MessageResponseSchema,
)

router = APIRouter()


# ──────────────────────────────────────────────
# Session CRUD
# ──────────────────────────────────────────────

@router.post("/", response_model=ChatSessionResponseSchema, status_code=201)
@limiter.limit("10/minute")
async def create_chat_session(
    request: Request,
    body: CreateSessionSchema = Body(default=CreateSessionSchema()),
    db: AsyncSession = Depends(get_async_session),
    user=Depends(current_user),
):
    """Create a new chat session. Body is optional — title defaults to 'New Chat'."""
    return await create_session(title=body.title, user=user, db=db)


@router.get("/", response_model=list[ChatSessionResponseSchema])
async def list_sessions(
    db: AsyncSession = Depends(get_async_session),
    user=Depends(current_user),
):
    """List all sessions for the authenticated user."""
    return await get_user_sessions(user=user, db=db)


@router.get("/{session_id}", response_model=ChatSessionResponseSchema)
async def get_chat_session(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
    user=Depends(current_user),
):
    """Get a single chat session by its session_id."""
    return await get_session(session_id=session_id, user=user, db=db)


@router.delete("/{session_id}", status_code=200)
async def delete_chat_session(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
    user=Depends(current_user),
):
    """Delete a session, all its messages, documents, and ChromaDB collection."""
    return await delete_session(session_id=session_id, user=user, db=db)


# ──────────────────────────────────────────────
# Document management
# ──────────────────────────────────────────────

@router.post(
    "/{session_id}/documents",
    response_model=list[DocumentResponseSchema],
    status_code=202,
)
async def upload_documents(
    session_id: str,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_async_session),
    user=Depends(current_user),
):
    """
    Upload one or more documents to a session.

    Returns **202 Accepted** immediately — embedding runs in the background.
    Poll `GET /sessions/{session_id}/documents` until all docs show `status=ready`.
    """
    return await attach_documents_to_session(
        session_id=session_id,
        files=files,
        user=user,
        db=db,
    )


@router.get(
    "/{session_id}/documents",
    response_model=list[DocumentResponseSchema],
)
async def list_session_documents(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
    user=Depends(current_user),
):
    """List all documents in a session with their individual embedding status."""
    return await get_session_documents(session_id=session_id, user=user, db=db)


# ──────────────────────────────────────────────
# Agent (LangGraph ReAct — RAG + Web verify)
# ──────────────────────────────────────────────

@router.post(
    "/{session_id}/agent",
    response_model=AgentResponseSchema,
)
@limiter.limit("10/minute")
async def agent_chat_endpoint(
    request: Request,
    session_id: str,
    body: ChatRequestSchema,
    db: AsyncSession = Depends(get_async_session),
    user=Depends(current_user),
):
    """
    Send a query to the **LangGraph ReAct agent**.

    The agent always follows a two-step process:

    1. **RAG search** — retrieves relevant chunks from your uploaded documents via ChromaDB.
    2. **Web verification** — cross-checks and enriches the document findings with a live web search.

    The response is structured as:
    - 📄 What your documents say (with source citations)
    - 🌐 What the web confirms / adds / contradicts
    - ✅ Final synthesised answer

    Additional tools available when relevant:
    - `summarize_documents` — broad overview of all uploaded files
    - `wikipedia_search` — encyclopedic background and definitions
    - `calculator` — mathematical computations
    - `get_current_datetime` — current date and time

    The response includes `tools_used` so the client knows exactly which
    tools the agent invoked.
    """
    return await agent_chat(
        session_id=session_id,
        query=body.query,
        user=user,
        db=db,
    )


@router.post(
    "/{session_id}/agent/stream",
)
async def agent_chat_stream_endpoint(
    request: Request,
    session_id: str,
    body: ChatRequestSchema,
    user=Depends(current_user),
):
    """
    Send a query to the **LangGraph ReAct agent** and stream the response.

    The response is returned as newline-delimited JSON objects (NDJSON) of type application/x-ndjson.
    Each line is a JSON string followed by a newline:

    - `{"type": "token", "content": "..."}`: A chunk of the final response text.
    - `{"type": "tool_start", "tool": "...", "input": "..."}`: The agent starting a tool.
    - `{"type": "tool_end", "tool": "...", "output": "..."}`: The tool completed (with snippet).
    - `{"type": "complete", "answer": "...", "citations": [...], "sources": [...], "tools_used": [...]}`: Final complete result with citations.
    - `{"type": "error", "detail": "..."}`: If an error occurred.
    """
    generator = agent_chat_stream(
        session_id=session_id,
        query=body.query,
        user=user,
    )
    return StreamingResponse(generator, media_type="application/x-ndjson")



# ──────────────────────────────────────────────
# Message history
# ──────────────────────────────────────────────

@router.get(
    "/{session_id}/messages",
    response_model=list[MessageResponseSchema],
)
async def get_messages(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_session),
    user=Depends(current_user),
):
    """Retrieve paginated chat history for a session (oldest first)."""
    return await get_chat_history(
        session_id=session_id,
        user=user,
        db=db,
        limit=limit,
    )
