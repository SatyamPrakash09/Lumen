"""
llm.py — LLM provider (Ollama only).

Returns ChatOllama for local inference via Ollama.
"""

import logging
from functools import lru_cache

from langchain_ollama import ChatOllama
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


def get_llm_model(
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> BaseChatModel:
    """
    Return the Ollama LLM for local inference.
    """
    settings = get_settings()
    logger.info(f"[LLM] Using Ollama model: {settings.OLLAMA_MODEL}")
    return _get_ollama_llm(
        model=settings.OLLAMA_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
    )
