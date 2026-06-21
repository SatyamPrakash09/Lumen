"""
embeddings.py — Embedding model provider (Ollama only).

Returns OllamaEmbeddings for local inference via Ollama.
"""

from functools import lru_cache

from langchain_ollama import OllamaEmbeddings
from langchain_core.embeddings import Embeddings

from src.config.settings import get_settings


@lru_cache(maxsize=4)
def _get_ollama_embeddings(model_name: str) -> OllamaEmbeddings:
    """Cached Ollama embedding model instance."""
    return OllamaEmbeddings(model=model_name)


def get_embedding_model() -> Embeddings:
    """
    Return the Ollama embedding model for local inference.
    """
    settings = get_settings()
    return _get_ollama_embeddings(settings.OLLAMA_EMBEDDING_MODEL)
