"""ChromaDB-backed corpus retriever with MMR reranking."""
from __future__ import annotations

import logging

from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.config import settings
from src.rag.embeddings import get_embeddings

logger = logging.getLogger(__name__)

_corpus: Chroma | None = None


def get_corpus() -> Chroma:
    """Return a cached Chroma collection for the main RAG corpus."""
    global _corpus
    if _corpus is None:
        settings.ensure_data_dirs()
        _corpus = Chroma(
            collection_name="public_safety_corpus",
            embedding_function=get_embeddings(),
            persist_directory=settings.chroma_persist_dir,
        )
    return _corpus


def retrieve(
    query: str,
    top_k: int = 5,
    jurisdiction: str = "both",
    source_type: str = "any",
) -> list[Document]:
    """Retrieve relevant documents using MMR to reduce redundancy.

    MMR (Maximum Marginal Relevance) balances relevance against diversity,
    preventing the retriever from returning five near-identical chunks.

    Args:
        query:        The search string.
        top_k:        Number of results to return.
        jurisdiction: Filter to "UK", "US", or "both" (no filter).
        source_type:  Filter to "news", "research", "statistics", or "any".

    Returns:
        List of LangChain Documents with page_content and metadata.
    """
    corpus = get_corpus()

    # Build optional metadata filter
    where: dict = {}
    if jurisdiction and jurisdiction.lower() != "both":
        where["jurisdiction"] = jurisdiction.upper()
    if source_type and source_type.lower() != "any":
        where["source_type"] = source_type

    search_kwargs: dict = {
        "k": top_k,
        "fetch_k": top_k * 4,  # fetch more candidates for MMR to select from
    }
    if where:
        search_kwargs["filter"] = where

    try:
        retriever = corpus.as_retriever(
            search_type="mmr",
            search_kwargs=search_kwargs,
        )
        docs = retriever.invoke(query)
        logger.debug("Retrieved %d docs for query '%s'", len(docs), query[:60])
        return docs
    except Exception as exc:
        logger.warning("Retrieval failed for query '%s': %s", query[:60], exc)
        return []


def add_documents(documents: list[Document]) -> int:
    """Add documents to the corpus. Returns the count of documents added."""
    if not documents:
        return 0
    corpus = get_corpus()
    corpus.add_documents(documents)
    logger.debug("Added %d documents to corpus", len(documents))
    return len(documents)


def corpus_size() -> int:
    """Return the total number of chunks in the corpus."""
    try:
        corpus = get_corpus()
        return corpus._collection.count()
    except Exception:
        return 0
