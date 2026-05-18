"""RAG ingestion pipeline — pulls from all sources, chunks, embeds, stores."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from langchain_core.documents import Document

from src.config import settings
from src.rag.chunking import chunk_document
from src.rag.retriever import add_documents, corpus_size
from src.sources.arxiv import ArxivClient
from src.sources.newsapi import NewsAPIClient
from src.sources.ons import ONSClient
from src.sources.police_uk import PoliceUKClient
from src.sources.rss_feeds import RSSFetcher

logger = logging.getLogger(__name__)

ARXIV_QUERIES = [
    "AI policing machine learning law enforcement",
    "predictive policing algorithmic crime",
    "emergency dispatch artificial intelligence 911",
    "public safety surveillance technology ethics",
    "officer wellness mental health police",
]


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _document_hash(doc: Document) -> str:
    source_url = doc.metadata.get("source_url", "")
    normalized_content = _normalize_text(doc.page_content)

    payload = f"{source_url}|{normalized_content}"

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _deduplicate_documents(documents: list[Document]) -> list[Document]:
    seen: set[str] = set()
    unique_docs: list[Document] = []

    duplicates = 0

    for doc in documents:
        try:
            doc_hash = _document_hash(doc)

            if doc_hash in seen:
                duplicates += 1
                continue

            seen.add(doc_hash)

            doc.metadata["document_hash"] = doc_hash

            unique_docs.append(doc)

        except Exception as exc:
            logger.warning("Failed to hash document: %s", exc)

    logger.info(
        "Deduplication complete: %d unique chunks, %d duplicates removed",
        len(unique_docs),
        duplicates,
    )

    return unique_docs


def _article_to_document(article: dict[str, Any]) -> list[Document]:
    body = article.get("content") or article.get("summary") or ""

    text = f"{article.get('title', '')}\n\n{body}".strip()

    if not text:
        return []

    source_type = article.get("source_type", "news")

    chunks = chunk_document(text, source_type)

    docs = []

    for i, chunk in enumerate(chunks):
        docs.append(
            Document(
                page_content=chunk,
                metadata={
                    "source_url": article.get("url", ""),
                    "source_name": article.get("source_name", ""),
                    "publication_date": article.get("date", ""),
                    "jurisdiction": article.get("jurisdiction", "UK"),
                    "source_type": source_type,
                    "chunk_index": i,
                },
            )
        )

    return docs


def _stats_to_document(
    prose: str,
    metadata: dict[str, Any],
) -> list[Document]:
    chunks = chunk_document(prose, "statistics")

    docs = []

    for i, chunk in enumerate(chunks):
        docs.append(
            Document(
                page_content=chunk,
                metadata={
                    **metadata,
                    "chunk_index": i,
                    "source_type": "statistics",
                },
            )
        )

    return docs


def _arxiv_to_document(paper: dict[str, Any]) -> list[Document]:
    text = f"{paper.get('title', '')}\n\n{paper.get('abstract', '')}".strip()

    if not text:
        return []

    return [
        Document(
            page_content=text,
            metadata={
                "source_url": paper.get("url", ""),
                "source_name": "arXiv",
                "publication_date": paper.get("date", ""),
                "jurisdiction": "both",
                "source_type": "research",
                "arxiv_id": paper.get("arxiv_id", ""),
                "chunk_index": 0,
            },
        )
    ]


def run_ingestion(verbose: bool = True) -> dict[str, int]:
    counts: dict[str, int] = {
        "rss_articles": 0,
        "police_uk": 0,
        "ons": 0,
        "newsapi": 0,
        "arxiv_papers": 0,
        "duplicates_removed": 0,
        "total_chunks": 0,
    }

    all_docs: list[Document] = []

    # ── RSS feeds ──────────────────────────────────────────────────────

    if verbose:
        logger.info("Fetching RSS feeds...")

    fetcher = RSSFetcher()

    articles = fetcher.fetch_all_feeds(max_per_feed=25)

    for article in articles:
        docs = _article_to_document(article)
        all_docs.extend(docs)

    counts["rss_articles"] = len(articles)

    if verbose:
        logger.info(
            "  RSS: %d articles → %d chunks",
            len(articles),
            len(all_docs),
        )

    # ── Police UK ──────────────────────────────────────────────────────

    if verbose:
        logger.info("Fetching Police UK crime statistics...")

    uk_client = PoliceUKClient()

    uk_categories = [
        "violent-crime",
        "burglary",
        "drugs",
        "anti-social-behaviour",
    ]

    uk_docs_before = len(all_docs)

    for category in uk_categories:
        try:
            summary = uk_client.get_crime_summary(category=category)

            prose = summary.get("prose", "")

            if prose:
                docs = _stats_to_document(
                    prose,
                    {
                        "source_url": "https://data.police.uk/api",
                        "source_name": "Police UK API",
                        "publication_date": "",
                        "jurisdiction": "UK",
                    },
                )

                all_docs.extend(docs)

        except Exception as exc:
            logger.warning(
                "Police UK ingestion failed for '%s': %s",
                category,
                exc,
            )

    counts["police_uk"] = len(all_docs) - uk_docs_before

    if verbose:
        logger.info(
            "  Police UK: %d chunks",
            counts["police_uk"],
        )

    # ── ONS ────────────────────────────────────────────────────────────

    if verbose:
        logger.info("Fetching ONS crime statistics...")

    ons_client = ONSClient()

    ons_docs_before = len(all_docs)

    try:
        prose = ons_client.get_crime_summary()

        if prose:
            docs = _stats_to_document(
                prose,
                {
                    "source_url": (
                        "https://www.ons.gov.uk/"
                        "peoplepopulationandcommunity/"
                        "crimeandjustice"
                    ),
                    "source_name": "ONS Crime Survey (CSEW)",
                    "publication_date": "",
                    "jurisdiction": "UK",
                },
            )

            all_docs.extend(docs)

    except Exception as exc:
        logger.warning("ONS ingestion failed: %s", exc)

    counts["ons"] = len(all_docs) - ons_docs_before

    if verbose:
        logger.info(
            "  ONS: %d chunks",
            counts["ons"],
        )

    # ── NewsAPI ────────────────────────────────────────────────────────

    newsapi_client = NewsAPIClient(api_key=settings.newsapi_key)

    if newsapi_client.available:
        if verbose:
            logger.info("Fetching NewsAPI articles...")

        newsapi_docs_before = len(all_docs)

        try:
            articles = newsapi_client.fetch_for_ingestion(page_size=20)

            for article in articles:
                docs = _article_to_document(article)
                all_docs.extend(docs)

            counts["newsapi"] = len(articles)

        except Exception as exc:
            logger.warning("NewsAPI ingestion failed: %s", exc)

        if verbose:
            logger.info(
                "  NewsAPI: %d articles → %d new chunks",
                counts["newsapi"],
                len(all_docs) - newsapi_docs_before,
            )

    else:
        if verbose:
            logger.info(
                "  NewsAPI: key not configured, skipping "
                "(set NEWSAPI_KEY in .env)"
            )

    # ── arXiv ──────────────────────────────────────────────────────────

    if verbose:
        logger.info("Fetching arXiv papers...")

    arxiv_client = ArxivClient()

    arxiv_count = 0

    for query in ARXIV_QUERIES:
        papers = arxiv_client.search(
            query,
            max_results=5,
            sort_by="relevance",
        )

        for paper in papers:
            docs = _arxiv_to_document(paper)

            all_docs.extend(docs)

            arxiv_count += 1

    counts["arxiv_papers"] = arxiv_count

    if verbose:
        logger.info(
            "  arXiv: %d papers",
            arxiv_count,
        )

    # ── Deduplication ──────────────────────────────────────────────────

    before_dedup = len(all_docs)

    all_docs = _deduplicate_documents(all_docs)

    counts["duplicates_removed"] = before_dedup - len(all_docs)

    # ── Embed and store ────────────────────────────────────────────────

    if verbose:
        logger.info(
            "Embedding and storing %d chunks...",
            len(all_docs),
        )

    added = add_documents(all_docs)

    counts["total_chunks"] = added

    if verbose:
        logger.info(
            "Ingestion complete. Corpus size: %d chunks total.",
            corpus_size(),
        )

    return counts