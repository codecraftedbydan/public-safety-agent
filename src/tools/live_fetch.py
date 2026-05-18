"""Tool 2: Live fetch — pulls fresh content from RSS feeds right now."""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from src.config import settings
from src.sources.newsapi import NewsAPIClient
from src.sources.rss_feeds import DEFAULT_FEEDS, RSSFetcher

logger = logging.getLogger(__name__)

# Default feed URLs used when caller does not specify any
DEFAULT_FEED_URLS = [meta["url"] for meta in DEFAULT_FEEDS.values()]


@tool
def live_fetch_tool(
    query_hint: str = "",
    jurisdiction: str = "both",
    max_items: int = 5,
    since_hours: int = 72,
) -> str:
    """Fetch the latest articles from live RSS feeds right now.

    Use this tool when the query asks for recent or latest information —
    e.g. 'latest developments', 'this week', 'recently announced'.
    Unlike rag_retrieval_tool which searches pre-indexed content, this tool
    hits live feeds and returns articles published in the last N hours.

    Args:
        query_hint:   Optional hint to help select relevant feeds (not used for filtering).
        jurisdiction: Restrict feeds to "UK", "US", or "both" (default).
        max_items:    Max articles per feed (default 5).
        since_hours:  Only return items published within this many hours (default 72).

    Returns:
        JSON string with a list of recent articles.
    """
    fetcher = RSSFetcher()
    filtered_feeds = {
        k: v
        for k, v in DEFAULT_FEEDS.items()
        if jurisdiction.lower() == "both" or v["jurisdiction"].lower() == jurisdiction.lower()
    }

    articles: list[dict] = []
    for meta in filtered_feeds.values():
        fetched = fetcher.fetch_feed(
            meta["url"],
            meta,
            max_items=max_items,
            since_hours=since_hours,
        )
        articles.extend(fetched)

    # Augment with NewsAPI if key is configured and a query hint was given
    newsapi_client = NewsAPIClient(api_key=settings.newsapi_key)
    if newsapi_client.available and query_hint:
        newsapi_articles = newsapi_client.fetch_live(
            query=query_hint,
            jurisdiction=jurisdiction,
            max_items=max_items,
        )
        articles.extend(newsapi_articles)

    if not articles:
        return json.dumps({"articles": [], "message": "No recent articles found."})

    # Keep only the fields the agent needs
    slim = [
        {
            "title": a.get("title", ""),
            "summary": (a.get("summary") or "")[:400],
            "url": a.get("url", ""),
            "date": a.get("date", ""),
            "source_name": a.get("source_name", ""),
            "jurisdiction": a.get("jurisdiction", ""),
        }
        for a in articles
    ]

    logger.debug("live_fetch_tool: returned %d articles", len(slim))
    return json.dumps({"articles": slim})
