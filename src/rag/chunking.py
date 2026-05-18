"""Content-aware text chunking strategies."""
from __future__ import annotations

import logging

import tiktoken

logger = logging.getLogger(__name__)

# cl100k_base covers GPT-4 / text-embedding-3 family
_ENCODER = tiktoken.get_encoding("cl100k_base")


def _encode(text: str) -> list[int]:
    return _ENCODER.encode(text)


def _decode(tokens: list[int]) -> str:
    return _ENCODER.decode(tokens)


def chunk_narrative(
    text: str,
    chunk_size: int = 512,
    overlap: int = 50,
) -> list[str]:
    """Split narrative text (news, policy docs) with token overlap.

    512-token chunks with 50-token overlap preserves paragraph-level
    coherence and avoids cutting mid-sentence at boundaries.
    """
    tokens = _encode(text)
    if not tokens:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_text = _decode(tokens[start:end]).strip()
        if chunk_text:
            chunks.append(chunk_text)
        if end == len(tokens):
            break
        start += chunk_size - overlap

    return chunks


def chunk_statistical(
    text: str,
    chunk_size: int = 256,
) -> list[str]:
    """Split statistical data with no overlap.

    Crime statistics are dense and structured — smaller chunks without
    overlap improve retrieval precision by keeping each statistic atomic.
    """
    tokens = _encode(text)
    if not tokens:
        return []

    chunks: list[str] = []
    for i in range(0, len(tokens), chunk_size):
        chunk_text = _decode(tokens[i : i + chunk_size]).strip()
        if chunk_text:
            chunks.append(chunk_text)

    return chunks


def chunk_document(text: str, source_type: str) -> list[str]:
    """Choose the appropriate chunking strategy based on source type.

    - ``statistics`` / ``data``  → 256-token chunks, no overlap
    - everything else            → 512-token chunks, 50-token overlap
    """
    if not text or not text.strip():
        return []

    if source_type in ("statistics", "data"):
        return chunk_statistical(text)

    return chunk_narrative(text)
