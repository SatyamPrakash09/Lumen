"""
chat_engine.py — RAG-powered chat using LangChain + Ollama.

Builds a context window from:
  - Retrieved document chunks (ChromaDB similarity search)
  - Conversation history (last N messages)

Then calls Ollama to generate a grounded answer.
"""

import logging
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.documents import Document

from src.rag.llm import get_llm_model
from src.rag.vector_store import similarity_search
from src.config.settings import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are Lumen, a helpful AI assistant that answers questions strictly based on the provided document context.

Instructions:
- Answer only from the context below. Do NOT use outside knowledge.
- If the answer is not in the context, say: "I couldn't find relevant information in the uploaded documents."
- Be concise, accurate, and cite which document the information comes from when possible.
- If multiple documents are relevant, synthesize the information clearly.
"""


def _format_context(docs: list[Document]) -> str:
    """Format retrieved chunks into a readable context block."""
    if not docs:
        return "No relevant context found."

    parts = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "Unknown document")
        page = doc.metadata.get("page", "")
        page_info = f", page {page}" if page != "" else ""
        parts.append(f"[Chunk {i} — {source}{page_info}]\n{doc.page_content}")

    return "\n\n---\n\n".join(parts)


def _build_messages(
    query: str,
    context: str,
    chat_history: list[dict],
) -> list:
    """Assemble the full message list for the LLM."""
    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    # Add recent conversation history (alternating human/AI)
    for msg in chat_history:
        if msg["sender"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    # Append the current question with context
    user_message = (
        f"Context from uploaded documents:\n\n{context}\n\n"
        f"Question: {query}"
    )
    messages.append(HumanMessage(content=user_message))

    return messages


async def get_rag_response(
    session_id: str,
    query: str,
    chat_history: Optional[list[dict]] = None,
    k: Optional[int] = None,
) -> dict:
    """
    Main RAG entry point.

    Args:
        session_id: The chat session ID (used to scope ChromaDB collection).
        query: The user's question.
        chat_history: List of previous messages [{"sender": "user"|"ai", "content": "..."}].
        k: Number of chunks to retrieve (defaults to settings.RAG_TOP_K).

    Returns:
        {
            "answer": str,
            "sources": list[str],   # unique source file names
        }
    """
    chat_history = chat_history or []
    k = k or settings.RAG_TOP_K

    # ── 1. Retrieve relevant chunks ────────────────────────────────────────
    logger.info(f"[RAG] Retrieving top-{k} chunks for session {session_id}")
    retrieved_docs = similarity_search(session_id, query, k=k)

    if not retrieved_docs:
        logger.warning(f"[RAG] No chunks retrieved for session {session_id}")

    # ── 2. Build context + messages ────────────────────────────────────────
    context = _format_context(retrieved_docs)
    messages = _build_messages(query, context, chat_history)

    # ── 3. Call LLM ─────────────────────────────────────────────────────
    llm = get_llm_model(temperature=0.1, max_tokens=1024)

    logger.info("[RAG] Calling LLM for response")
    response = await llm.ainvoke(messages)
    answer = response.content

    # ── 4. Collect unique sources ──────────────────────────────────────────
    sources = list({
        doc.metadata.get("source", "Unknown")
        for doc in retrieved_docs
    })

    return {
        "answer": answer,
        "sources": sources,
    }
