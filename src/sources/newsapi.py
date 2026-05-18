"""NewsAPI.org client — aggregated news search across UK and US sources.

Free tier: 100 requests/day. Requires a free API key from https://newsapi.org.
The client degrades gracefully when no key is configured, returning an empty
list so the rest of the pipeline continues unaffected.

Returns articles in the same normalised dict format used by RSSFetcher so
they flow directly into the existing chunking/ingestion pipeline and
live_fetch_tool without any adapter layer.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://newsapi.org/v2/everything"
TIMEOUT = 15.0

# Pre-defined queries that cover both jurisdictions and major topics.
# Used during batch ingestion.
INGESTION_QUERIES: list[dict[str, Any]] = [
    {
        "q": "UK crime policing law enforcement",
        "language": "en",
        "jurisdiction": "UK",
        "source_type": "news",
    },
    {
        "q": "UK home office public safety policy",
        "language": "en",
        "jurisdiction": "UK",
        "source_type": "policy",
    },
    {
        "q": "US crime law enforcement FBI police",
        "language": "en",
        "jurisdiction": "US",
        "source_type": "news",
    },
    {
        "q": "US public safety criminal justice reform",
        "language": "en",
        "jurisdiction": "US",
        "source_type": "policy",
    },
]


class NewsAPIClient:
    """Wrapper around the NewsAPI.org /v2/everything endpoint."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------ #
    #  Core API                                                            #
    # ------------------------------------------------------------------ #

    def search(
        self,
        query: str,
        language: str = "en",
        page_size: int = 20,
        sort_by: str = "publishedAt",
        jurisdiction: str = "both",
        source_type: str = "news",
    ) -> list[dict[str, Any]]:
        """Search NewsAPI for articles matching *query*.

        Returns a list of normalised article dicts compatible with the RSS
        article format used throughout this codebase.
        """
        if not self.available:
            logger.debug("NewsAPI key not configured — skipping search for '%s'", query)
            return []

        params = {
            "q": query,
            "language": language,
            "pageSize": min(page_size, 100),
            "sortBy": sort_by,
            "apiKey": self.api_key,
        }

        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.get(BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                logger.warning("NewsAPI: invalid API key (401)")
            elif exc.response.status_code == 429:
                logger.warning("NewsAPI: rate limit reached (429) — free tier is 100 req/day")
            else:
                logger.warning("NewsAPI HTTP error for '%s': %s", query, exc)
            return []
        except Exception as exc:
            logger.warning("NewsAPI request failed for '%s': %s", query, exc)
            return []

        articles = []
        for item in data.get("articles", []):
            # Skip removed articles (NewsAPI returns placeholders)
            if item.get("title") == "[Removed]":
                continue

            source_name = (item.get("source") or {}).get("name", "NewsAPI")
            articles.append(
                {
                    "title": item.get("title", "").strip(),
                    "summary": (item.get("description") or "").strip(),
                    "content": (item.get("content") or "").strip(),
                    "url": item.get("url", ""),
                    "date": item.get("publishedAt", ""),
                    "jurisdiction": jurisdiction,
                    "source_type": source_type,
                    "source_name": source_name,
                }
            )

        logger.debug("NewsAPI '%s': %d articles", query, len(articles))
        return articles

    # ------------------------------------------------------------------ #
    #  High-level helpers                                                  #
    # ------------------------------------------------------------------ #

    def fetch_for_ingestion(self, page_size: int = 20) -> list[dict[str, Any]]:
        """Run all pre-defined ingestion queries and return combined articles."""
        all_articles: list[dict[str, Any]] = []
        for spec in INGESTION_QUERIES:
            articles = self.search(
                query=spec["q"],
                language=spec.get("language", "en"),
                page_size=page_size,
                jurisdiction=spec.get("jurisdiction", "both"),
                source_type=spec.get("source_type", "news"),
            )
            all_articles.extend(articles)
        return all_articles

    def fetch_live(
        self,
        query: str,
        jurisdiction: str = "both",
        max_items: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch recent articles for a live query (used by live_fetch_tool)."""
        return self.search(
            query=query,
            page_size=max_items,
            sort_by="publishedAt",
            jurisdiction=jurisdiction,
            source_type="news",
        )
