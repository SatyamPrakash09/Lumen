import os
import threading
from functools import lru_cache
from typing import Optional

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from src.config.settings import get_settings

settings = get_settings()

_client_lock = threading.Lock()
_chroma_client: Optional[chromadb.PersistentClient] = None


def _get_chroma_client() -> chromadb.PersistentClient:
    """Return the single shared PersistentClient (thread-safe singleton)."""
    global _chroma_client
    if _chroma_client is None:
        with _client_lock:
            if _chroma_client is None:
                os.makedirs(settings.CHROMA_DB_DIR, exist_ok=True)
                _chroma_client = chromadb.PersistentClient(path=settings.CHROMA_DB_DIR)
    return _chroma_client


@lru_cache(maxsize=4)
def _get_embedding_fn(model_name: str) -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(
        model=model_name,
        google_api_key=settings.GOOGLE_API_KEY
    )


def _collection_name(session_id: str) -> str:
    return f"session_{session_id}"


def get_or_create_collection(session_id: str) -> Chroma:
    return Chroma(
        client=_get_chroma_client(),
        collection_name=_collection_name(session_id),
        embedding_function=_get_embedding_fn(settings.EMBEDDING_MODEL),
    )


def add_chunks_to_store(session_id: str, chunks: list[Document]) -> int:
    if not chunks:
        return 0
    store = get_or_create_collection(session_id)
    store.add_documents(chunks)
    return len(chunks)


def similarity_search(session_id: str, query: str, k: Optional[int] = None) -> list[Document]:
    k = k or settings.RAG_TOP_K
    return get_or_create_collection(session_id).similarity_search(query, k=k)


def delete_collection(session_id: str) -> None:
    try:
        _get_chroma_client().delete_collection(_collection_name(session_id))
    except Exception:
        pass
