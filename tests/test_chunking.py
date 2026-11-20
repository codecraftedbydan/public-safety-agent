"""Tests for the token-based chunking strategies (no API keys or network calls needed)."""
from src.rag.chunking import _encode, chunk_document, chunk_narrative, chunk_statistical


def _long_text(n_sentences: int = 400) -> str:
    return " ".join(f"Sentence number {i} about public safety." for i in range(n_sentences))


def test_empty_input_returns_no_chunks():
    assert chunk_document("", "news") == []
    assert chunk_document("   \n ", "statistics") == []
    assert chunk_narrative("") == []
    assert chunk_statistical("") == []


def test_short_text_is_a_single_chunk():
    text = "Burglary fell slightly in the last quarter."
    assert chunk_document(text, "news") == [text]


def test_narrative_chunks_respect_size_limit():
    chunks = chunk_narrative(_long_text(), chunk_size=128, overlap=16)
    assert len(chunks) > 1
    # Decoding then re-encoding can shift token boundaries slightly, so allow a small margin.
    assert all(len(_encode(c)) <= 130 for c in chunks)


def test_narrative_chunks_overlap():
    chunks = chunk_narrative(_long_text(), chunk_size=64, overlap=16)
    tail = chunks[0].split()[-3:]
    assert " ".join(tail) in chunks[1]


def test_statistical_chunks_do_not_overlap():
    text = _long_text()
    chunks = chunk_statistical(text, chunk_size=64)
    total = sum(len(_encode(c)) for c in chunks)
    # Without overlap, the chunks together hold roughly the original token count.
    assert abs(total - len(_encode(text))) <= len(chunks) * 2


def test_strategy_selected_by_source_type():
    text = _long_text()
    assert chunk_document(text, "statistics") == chunk_statistical(text)
    assert chunk_document(text, "data") == chunk_statistical(text)
    assert chunk_document(text, "news") == chunk_narrative(text)
