"""Tool 1: RAG retrieval — semantic search over the pre-ingested corpus."""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from src.rag.retriever import retrieve

logger = logging.getLogger(__name__)


@tool
def rag_retrieval_tool(
    query: str,
    top_k: int = 5,
    jurisdiction: str = "both",
    source_type: str = "any",
) -> str:
    """Search the pre-ingested public safety corpus using semantic similarity.

    Use this tool when you need background knowledge, historical context,
    or statistical baselines on a topic. It searches across RSS articles,
    Police UK statistics, arXiv abstracts, and policy documents that were
    ingested at startup.

    Args:
        query:        Natural language search query.
        top_k:        Number of results to return (default 5).
        jurisdiction: Restrict to "UK", "US", or "both" (default).
        source_type:  Restrict to "news", "research", "statistics", or "any" (default).

    Returns:
        JSON string with a list of matching chunks and their metadata.
    """
    docs = retrieve(query, top_k=top_k, jurisdiction=jurisdiction, source_type=source_type)

    if not docs:
        return json.dumps({"results": [], "message": "No matching documents found in corpus."})

    results = []
    for doc in docs:
        results.append(
            {
                "content": doc.page_content,
                "source_url": doc.metadata.get("source_url", ""),
                "source_name": doc.metadata.get("source_name", ""),
                "date": doc.metadata.get("publication_date", ""),
                "jurisdiction": doc.metadata.get("jurisdiction", ""),
                "source_type": doc.metadata.get("source_type", ""),
            }
        )

    logger.debug("rag_retrieval_tool: returned %d results", len(results))
    return json.dumps({"results": results})
