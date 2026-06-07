"""
chat_controller.py — Agent-based chat handler for Lumen.

The agent always:
  1. Searches uploaded documents (RAG)
  2. Verifies / enriches with web search
  3. Returns a synthesised, grounded answer
"""

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from src.models.models import ChatSession, Messages, User
from src.controllers.session_controller import get_session

logger = logging.getLogger(__name__)

# Number of recent messages to pass as context
HISTORY_WINDOW = 10


async def agent_chat(
    session_id: str,
    query: str,
    user: User,
    db: AsyncSession,
) -> dict:
    """
    Run the LangGraph ReAct agent for a session query.

    Flow:
        1. Verify session ownership
        2. Load recent conversation history
        3. Run agent (RAG search → web verify → synthesise)
        4. Persist user + AI messages
        5. Return AgentResponseSchema-compatible dict
    """
    from src.rag.agent import run_agent

    # ── 1. Verify session ownership ────────────────────────────────────────
    session: ChatSession = await get_session(session_id, user, db)

    # ── 2. Load recent conversation history ────────────────────────────────
    history_stmt = (
        select(Messages)
        .where(Messages.session_id == session_id)
        .order_by(Messages.timestamp.desc())
        .limit(HISTORY_WINDOW)
    )
    history_result = await db.execute(history_stmt)
    recent_messages = list(reversed(history_result.scalars().all()))

    chat_history = [
        {"sender": msg.sender, "content": msg.content}
        for msg in recent_messages
    ]

    # ── 3. Run the agent ───────────────────────────────────────────────────
    logger.info(f"[AgentChat] Running agent for session {session_id}: '{query[:80]}'")
    try:
        result = await run_agent(
            session_id=session_id,
            query=query,
            chat_history=chat_history,
        )
    except Exception as e:
        logger.error(f"[AgentChat] Error for session {session_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=f"Agent error: {str(e)}",
        )

    # ── 4. Persist messages ────────────────────────────────────────────────
    user_msg = Messages(session_id=session_id, sender="user", content=query)
    ai_msg = Messages(session_id=session_id, sender="ai", content=result["answer"])
    db.add(user_msg)
    db.add(ai_msg)
    await db.commit()

    # ── 5. Return response ─────────────────────────────────────────────────
    return {
        "answer": result["answer"],
        "citations": result.get("citations", []),
        "sources": result.get("sources", []),
        "tools_used": result.get("tools_used", []),
        "session_id": session_id,
    }


async def agent_chat_stream(
    session_id: str,
    query: str,
    user: User,
):
    """
    Stream the LangGraph ReAct agent response.

    Yields:
        JSON lines with event type: 'token' | 'tool_start' | 'tool_end' | 'complete' | 'error'
    """
    from src.database.db import async_session_maker
    from src.rag.agent import run_agent_stream
    from src.models.models import Messages
    import json

    # 1. Verify session ownership and save user message first
    async with async_session_maker() as db:
        await get_session(session_id, user, db)

        history_stmt = (
            select(Messages)
            .where(Messages.session_id == session_id)
            .order_by(Messages.timestamp.desc())
            .limit(HISTORY_WINDOW)
        )
        history_result = await db.execute(history_stmt)
        recent_messages = list(reversed(history_result.scalars().all()))

        chat_history = [
            {"sender": msg.sender, "content": msg.content}
            for msg in recent_messages
        ]

        user_msg = Messages(session_id=session_id, sender="user", content=query)
        db.add(user_msg)
        await db.commit()

    # 2. Stream agent execution
    answer = ""
    try:
        async for event in run_agent_stream(
            session_id=session_id,
            query=query,
            chat_history=chat_history,
        ):
            if event["type"] == "token":
                answer += event["content"]
            yield json.dumps(event) + "\n"
    except Exception as e:
        logger.error(f"[AgentChatStream] Error streaming response: {e}", exc_info=True)
        yield json.dumps({
            "type": "error",
            "detail": f"Streaming agent error: {str(e)}"
        }) + "\n"
        return

    # 3. Persist AI message after stream completes successfully
    async with async_session_maker() as db:
        ai_msg = Messages(
            session_id=session_id,
            sender="ai",
            content=answer or "I was unable to generate a response."
        )
        db.add(ai_msg)
        await db.commit()


async def get_chat_history(
    session_id: str,
    user: User,
    db: AsyncSession,
    limit: int = 50,
) -> list[Messages]:
    """Retrieve paginated message history for a session (oldest first)."""
    await get_session(session_id, user, db)  # ownership check

    stmt = (
        select(Messages)
        .where(Messages.session_id == session_id)
        .order_by(Messages.timestamp.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()
