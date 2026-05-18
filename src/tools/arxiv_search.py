"""Tool 4: Research search — finds academic papers on public safety topics via arXiv."""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from src.sources.arxiv import ArxivClient

logger = logging.getLogger(__name__)

_client = ArxivClient()


@tool
def research_search_tool(
    query: str,
    max_results: int = 5,
    sort_by: str = "relevance",
) -> str:
    """Search arXiv for academic research papers on a topic.

    Use this tool when the query asks about technology trends, AI applications,
    academic findings, or research on policing and public safety. Returns paper
    titles, abstracts, authors, and direct links.

    This tool is different from rag_retrieval_tool — it hits the live arXiv API
    for the most current research rather than searching pre-indexed content.

    Args:
        query:       Natural language query (e.g. "AI emergency dispatch systems").
        max_results: Number of papers to return (default 5, max 10).
        sort_by:     "relevance" (default) or "date" for most recent first.

    Returns:
        JSON string with a list of papers and their metadata.
    """
    max_results = min(max_results, 10)
    papers = _client.search(query, max_results=max_results, sort_by=sort_by)

    if not papers:
        return json.dumps({"papers": [], "message": "No papers found for this query."})

    slim = [
        {
            "title": p.get("title", ""),
            "abstract": (p.get("abstract") or "")[:500],
            "authors": p.get("authors", [])[:3],  # first 3 authors
            "url": p.get("url", ""),
            "date": p.get("date", ""),
            "arxiv_id": p.get("arxiv_id", ""),
        }
        for p in papers
    ]

    logger.debug("research_search_tool: returned %d papers", len(slim))
    return json.dumps({"papers": slim})
