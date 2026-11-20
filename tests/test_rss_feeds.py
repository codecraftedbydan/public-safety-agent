"""Tests for RSS normalisation using inline feed XML (no network calls)."""
from types import SimpleNamespace

from src.sources.rss_feeds import DEFAULT_FEEDS, RSSFetcher, _parse_date, _strip_html

SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test feed</title>
<item>
  <title>  Knife crime figures published  </title>
  <link>https://example.org/a</link>
  <description>&lt;p&gt;New &lt;b&gt;figures&lt;/b&gt; released.&lt;/p&gt;</description>
  <pubDate>Mon, 02 Nov 2026 09:00:00 GMT</pubDate>
</item>
<item>
  <title>Second item</title>
  <link>https://example.org/b</link>
  <description>Plain summary</description>
</item>
</channel></rss>"""


def test_strip_html_removes_tags():
    assert _strip_html("<p>Hello <b>world</b></p>").split() == ["Hello", "world"]
    assert _strip_html("") == ""


def test_parse_date_prefers_published_then_updated():
    assert _parse_date(SimpleNamespace(published="P", updated="U")) == "P"
    assert _parse_date(SimpleNamespace(published="", updated="U")) == "U"
    assert _parse_date(SimpleNamespace()) == ""


def test_fetch_feed_normalises_articles():
    meta = {"jurisdiction": "UK", "source_type": "news", "source_name": "Test"}
    articles = RSSFetcher().fetch_feed(SAMPLE_RSS, meta)
    assert len(articles) == 2
    first = articles[0]
    assert first["title"] == "Knife crime figures published"
    assert first["url"] == "https://example.org/a"
    assert "figures" in first["summary"] and "<b>" not in first["summary"]
    assert first["date"].startswith("Mon, 02 Nov 2026")
    assert first["source_name"] == "Test"
    assert articles[1]["date"] == ""


def test_fetch_feed_respects_max_items():
    articles = RSSFetcher().fetch_feed(SAMPLE_RSS, {}, max_items=1)
    assert len(articles) == 1
    assert articles[0]["jurisdiction"] == "UK"  # default when metadata is missing


def test_default_feeds_are_well_formed():
    required = {"url", "jurisdiction", "source_type", "source_name"}
    for feed_id, meta in DEFAULT_FEEDS.items():
        assert required <= meta.keys(), feed_id
        assert meta["url"].startswith("https://"), feed_id
        assert meta["jurisdiction"] in {"UK", "US"}, feed_id
