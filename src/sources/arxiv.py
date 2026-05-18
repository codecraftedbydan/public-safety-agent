"""arXiv API client — searches academic papers on public safety topics."""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import feedparser

logger = logging.getLogger(__name__)

_ARXIV_API = "http://export.arxiv.org/api/query"


class ArxivClient:
    """Thin wrapper around the arXiv Atom/OpenSearch API. No auth required."""

    def search(
        self,
        query: str,
        max_results: int = 5,
        sort_by: str = "relevance",
    ) -> list[dict[str, Any]]:
        """Search arXiv and return a list of paper metadata dicts.

        Each dict contains: title, abstract, authors, url, date, arxiv_id.
        """
        sort_map = {
            "relevance": "relevance",
            "date": "submittedDate",
        }
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": sort_map.get(sort_by, "relevance"),
            "sortOrder": "descending",
        }
        url = f"{_ARXIV_API}?{urllib.parse.urlencode(params)}"

        try:
            feed = feedparser.parse(url)
        except Exception as exc:
            logger.warning("arXiv fetch failed for query '%s': %s", query, exc)
            return []

        results: list[dict[str, Any]] = []
        for entry in feed.entries:
            arxiv_id = ""
            if hasattr(entry, "id"):
                arxiv_id = entry.id.split("/abs/")[-1] if "/abs/" in entry.id else entry.id

            authors = []
            for author in getattr(entry, "authors", []):
                name = getattr(author, "name", None)
                if name:
                    authors.append(name)

            results.append(
                {
                    "title": getattr(entry, "title", "").replace("\n", " ").strip(),
                    "abstract": getattr(entry, "summary", "").replace("\n", " ").strip(),
                    "authors": authors,
                    "url": getattr(entry, "link", f"https://arxiv.org/abs/{arxiv_id}"),
                    "date": getattr(entry, "published", ""),
                    "arxiv_id": arxiv_id,
                    "source_name": "arXiv",
                    "jurisdiction": "both",
                    "source_type": "research",
                }
            )

        logger.debug("arXiv returned %d results for '%s'", len(results), query)
        return results
