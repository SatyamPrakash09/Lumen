"""
llm.py — Unified LLM provider.

Returns ChatOllama in development and ChatGoogleGenerativeAI
in production, based on settings.is_development.
"""

import logging
from functools import lru_cache

from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models.chat_models import BaseChatModel

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def _get_ollama_llm(
    model: str,
    temperature: float,
    max_tokens: int,
) -> ChatOllama:
    """Cached Ollama LLM instance."""
    return ChatOllama(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


@lru_cache(maxsize=4)
def _get_google_llm(
    model: str,
    api_key: str,
    temperature: float,
    max_tokens: int,
) -> ChatGoogleGenerativeAI:
    """Cached Google Generative AI LLM instance."""
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )


def get_llm_model(
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> BaseChatModel:
    """
    Return the appropriate LLM based on the current environment.

    - Development (is_development=True):  ChatOllama (local)
    - Production  (is_development=False): ChatGoogleGenerativeAI (API)
    """
    settings = get_settings()

    if settings.is_development:
        logger.info(f"[LLM] Using Ollama model: {settings.OLLAMA_MODEL}")
        return _get_ollama_llm(
            model=settings.OLLAMA_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    else:
        logger.info(f"[LLM] Using Google GenAI model: {settings.GOOGLE_GENAI_MODEL}")
        return _get_google_llm(
            model=settings.GOOGLE_GENAI_MODEL,
            api_key=settings.GOOGLE_API_KEY,
            temperature=temperature,
            max_tokens=max_tokens,
        )
