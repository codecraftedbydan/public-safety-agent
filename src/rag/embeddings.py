"""OpenAI embedding client wrapper — singleton to avoid recreating on every call."""
from __future__ import annotations

from langchain_openai import OpenAIEmbeddings

from src.config import settings

_embeddings: OpenAIEmbeddings | None = None


def get_embeddings() -> OpenAIEmbeddings:
    """Return a cached OpenAI embeddings instance."""
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            openai_api_key=settings.openai_api_key,
        )
    return _embeddings
