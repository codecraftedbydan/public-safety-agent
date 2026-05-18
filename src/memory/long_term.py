"""Long-term memory — persists turn summaries to disk and indexes them semantically."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.config import settings
from src.rag.embeddings import get_embeddings

logger = logging.getLogger(__name__)

_HISTORY_FILE = "session_history.json"
_MEMORY_COLLECTION = "agent_memory"

_memory_store: Chroma | None = None


def _history_path() -> Path:
    return Path(settings.memory_dir) / _HISTORY_FILE


def _get_memory_store() -> Chroma:
    """Return (or create) the ChromaDB collection for semantic memory."""
    global _memory_store
    if _memory_store is None:
        settings.ensure_data_dirs()
        _memory_store = Chroma(
            collection_name=_MEMORY_COLLECTION,
            embedding_function=get_embeddings(),
            persist_directory=settings.chroma_persist_dir,
        )
    return _memory_store


# ─────────────────────────────────────────────────────────────────────────────
# Persistence helpers
# ─────────────────────────────────────────────────────────────────────────────

def save_turn_summary(query: str, summary: str) -> None:
    """Persist a turn summary to disk (Tier 2) and embed it (Tier 3)."""
    settings.ensure_data_dirs()
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "query": query,
        "summary": summary,
    }

    # Tier 2 — JSON file (recency-based retrieval)
    path = _history_path()
    history: list[dict] = []
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            history = []

    history.append(entry)
    path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")

    # Tier 3 — ChromaDB (semantic retrieval)
    try:
        store = _get_memory_store()
        doc = Document(
            page_content=f"Query: {query}\nSummary: {summary}",
            metadata={
                "id": entry["id"],
                "timestamp": entry["timestamp"],
                "query": query,
            },
        )
        store.add_documents([doc], ids=[entry["id"]])
    except Exception as exc:
        logger.warning("Failed to embed memory summary: %s", exc)


def load_recent_summaries(n: int = 5) -> str:
    """Load the most recent N turn summaries for injection into the system prompt (Tier 2)."""
    path = _history_path()
    if not path.exists():
        return ""

    try:
        history: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""

    recent = history[-n:]
    lines = []
    for entry in recent:
        ts = entry.get("timestamp", "")[:10]
        query = entry.get("query", "")
        summary = entry.get("summary", "")
        lines.append(f"[{ts}] Q: {query}\n  {summary}")

    return "\n\n".join(lines) if lines else ""


def retrieve_similar_memories(query: str, top_k: int = 3) -> str:
    """Retrieve semantically similar past turn summaries (Tier 3)."""
    try:
        store = _get_memory_store()
        docs = store.similarity_search(query, k=top_k)
        if not docs:
            return ""
        lines = []
        for doc in docs:
            ts = doc.metadata.get("timestamp", "")[:10]
            lines.append(f"[{ts}] {doc.page_content[:300]}")
        return "\n\n".join(lines)
    except Exception as exc:
        logger.warning("Semantic memory retrieval failed: %s", exc)
        return ""


def build_session_context(query: str) -> str:
    """Combine recency-based and relevance-based memory into a single context string.

    Tier 2 (recent) takes priority; Tier 3 (semantic) surfaces older relevant context.
    The two tiers serve different access patterns and are combined here at session start.
    """
    recent = load_recent_summaries(n=4)
    semantic = retrieve_similar_memories(query, top_k=2)

    parts: list[str] = []
    if recent:
        parts.append(f"Recent session history:\n{recent}")
    if semantic:
        # Avoid duplicating content already in 'recent'
        if semantic not in recent:
            parts.append(f"Relevant past findings:\n{semantic}")

    return "\n\n---\n\n".join(parts) if parts else ""
