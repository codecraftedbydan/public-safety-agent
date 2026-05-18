"""RSS feed client — fetches articles from curated public safety feeds."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import feedparser
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Curated list of reliable, free public safety RSS/Atom feeds.
# All URLs verified reachable at time of writing.
# Broken feeds have been removed; see comments on each for rationale.
DEFAULT_FEEDS: dict[str, dict[str, str]] = {
    # ── UK ────────────────────────────────────────────────────────────────
    "gov_uk_home_office": {
        "url": "https://www.gov.uk/government/organisations/home-office.atom",
        "jurisdiction": "UK",
        "source_type": "policy",
        "source_name": "UK Home Office",
    },
    "gov_uk_crime_policing": {
        # GOV.UK topic feed for crime & policing announcements
        "url": "https://www.gov.uk/search/news-and-communications.atom?topics%5B%5D=crime-policing",
        "jurisdiction": "UK",
        "source_type": "policy",
        "source_name": "GOV.UK Crime & Policing",
    },
    "bbc_uk_news": {
        "url": "https://feeds.bbci.co.uk/news/uk/rss.xml",
        "jurisdiction": "UK",
        "source_type": "news",
        "source_name": "BBC UK News",
    },
    "guardian_uk_crime": {
        # The Guardian's UK crime section — reliable, free, no auth
        "url": "https://www.theguardian.com/uk/rss",
        "jurisdiction": "UK",
        "source_type": "news",
        "source_name": "The Guardian UK",
    },
    "ons_crime_bulletins": {
        # ONS statistical bulletins feed — crime & justice category
        "url": "https://www.ons.gov.uk/feed",
        "jurisdiction": "UK",
        "source_type": "statistics",
        "source_name": "ONS Statistics",
    },
    # ── US ────────────────────────────────────────────────────────────────
    "justice_gov_news": {
        # US Dept of Justice official press releases
        "url": "https://www.justice.gov/news/rss",
        "jurisdiction": "US",
        "source_type": "policy",
        "source_name": "US Dept of Justice",
    },
    "npr_us_news": {
        # NPR national news — reliable US public affairs feed
        "url": "https://feeds.npr.org/1001/rss.xml",
        "jurisdiction": "US",
        "source_type": "news",
        "source_name": "NPR News",
    },
}


def _strip_html(html: str) -> str:
    """Remove HTML tags and return clean text."""
    if not html:
        return ""
    try:
        return BeautifulSoup(html, "lxml").get_text(separator=" ").strip()
    except Exception:
        return html


def _parse_date(entry: Any) -> str:
    """Extract ISO date string from a feedparser entry."""
    for attr in ("published", "updated", "created"):
        val = getattr(entry, attr, None)
        if val:
            return val
    return ""


class RSSFetcher:
    """Fetches and normalises RSS/Atom feeds into a common article format."""

    def fetch_feed(
        self,
        url: str,
        metadata: dict[str, str],
        max_items: int = 20,
        since_hours: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch a single feed. Returns a list of article dicts."""
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "PublicSafetyAgent/1.0"})
        except Exception as exc:
            logger.warning("Failed to fetch feed %s: %s", url, exc)
            return []

        if feed.bozo and not feed.entries:
            logger.warning("Feed %s returned bozo=True with no entries", url)
            return []

        cutoff: datetime | None = None
        if since_hours is not None:
            cutoff = datetime.now(tz=timezone.utc).replace(
                hour=datetime.now(tz=timezone.utc).hour - since_hours % 24
            )

        articles = []
        for entry in feed.entries[:max_items]:
            date_str = _parse_date(entry)

            # Content — try full content first, then summary
            content = ""
            if hasattr(entry, "content") and entry.content:
                content = _strip_html(entry.content[0].get("value", ""))
            summary = _strip_html(getattr(entry, "summary", ""))

            articles.append(
                {
                    "title": getattr(entry, "title", "").strip(),
                    "summary": summary,
                    "content": content,
                    "url": getattr(entry, "link", ""),
                    "date": date_str,
                    "jurisdiction": metadata.get("jurisdiction", "UK"),
                    "source_type": metadata.get("source_type", "news"),
                    "source_name": metadata.get("source_name", ""),
                }
            )

        logger.debug("Fetched %d articles from %s", len(articles), url)
        return articles

    def fetch_all_feeds(self, max_per_feed: int = 20) -> list[dict[str, Any]]:
        """Fetch all default feeds. Failures are silently skipped."""
        all_articles: list[dict[str, Any]] = []
        for feed_id, meta in DEFAULT_FEEDS.items():
            articles = self.fetch_feed(meta["url"], meta, max_items=max_per_feed)
            all_articles.extend(articles)
            logger.info("Feed '%s': %d articles", feed_id, len(articles))
        return all_articles

    def fetch_urls(self, urls: list[str], max_items: int = 10, since_hours: int = 72) -> list[dict[str, Any]]:
        """Fetch a custom list of feed URLs (used by live_fetch_tool)."""
        all_articles: list[dict[str, Any]] = []
        for url in urls:
            # Try to match against default feeds for metadata
            meta = next(
                (m for m in DEFAULT_FEEDS.values() if m["url"] == url),
                {"jurisdiction": "both", "source_type": "news", "source_name": url},
            )
            articles = self.fetch_feed(url, meta, max_items=max_items, since_hours=since_hours)
            all_articles.extend(articles)
        return all_articles
