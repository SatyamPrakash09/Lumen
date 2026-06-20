"""
embeddings.py — Unified embedding model provider.

Returns OllamaEmbeddings in development and GoogleGenerativeAIEmbeddings
in production, based on settings.is_development.
"""

from functools import lru_cache
from typing import Union

from langchain_ollama import OllamaEmbeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.embeddings import Embeddings

from src.config.settings import get_settings


@lru_cache(maxsize=4)
def _get_ollama_embeddings(model_name: str) -> OllamaEmbeddings:
    """Cached Ollama embedding model instance."""
    return OllamaEmbeddings(model=model_name)


@lru_cache(maxsize=4)
def _get_google_embeddings(model_name: str, api_key: str) -> GoogleGenerativeAIEmbeddings:
    """Cached Google Generative AI embedding model instance."""
    return GoogleGenerativeAIEmbeddings(
        model=model_name,
        google_api_key=api_key,
    )


def get_embedding_model() -> Embeddings:
    """
    Return the appropriate embedding model based on the current environment.

    - Development (is_development=True):  OllamaEmbeddings (local)
    - Production  (is_development=False): GoogleGenerativeAIEmbeddings (API)
    """
    settings = get_settings()

    if settings.is_development:
        return _get_ollama_embeddings(settings.OLLAMA_EMBEDDING_MODEL)
    else:
        return _get_google_embeddings(
            settings.EMBEDDING_MODEL,
            settings.GOOGLE_API_KEY,
        )
