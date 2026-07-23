"""Tests for the RAG index/search logic in data/rag_index.py.

Builds a small, temporary Chroma collection from hardcoded sample entries
using a tiny hand-rolled offline embedding function (word-hashing bag of
words) instead of Chroma's default ONNX model or any live embedding API, so
this runs fast and works with no network access. The real ./chroma_db and
data/rag_sources/entries.json are never touched.
"""

import tempfile
import zlib

import pytest
from chromadb import Documents, EmbeddingFunction, Embeddings

from data import rag_index

SAMPLE_ENTRIES = [
    {
        "text": "Dupont Circle's south entrance has no elevator; use the north "
        "entrance for wheelchair access to the platform.",
        "station": "Dupont Circle",
        "type": "accessibility",
        "source": "test fixture",
    },
    {
        "text": "Metro Center has elevator access from street level to the "
        "mezzanine and both platforms.",
        "station": "Metro Center",
        "type": "accessibility",
        "source": "test fixture",
    },
    {
        "text": "Single-tracking between Metro Center and Gallery Place on the "
        "Red Line due to weekend track maintenance.",
        "station": "Metro Center",
        "type": "alert_history",
        "source": "test fixture",
    },
    {
        "text": "SmarTrip fares are calculated by distance traveled and time "
        "of day, with lower off-peak fares.",
        "station": None,
        "type": "faq",
        "source": "test fixture",
    },
]


class HashingEmbeddingFunction(EmbeddingFunction):
    """Tiny deterministic bag-of-words embedding — no model, no network.

    Hashes each word into a bucket and L2-normalizes the result, so
    Chroma's (unnormalized) L2 distance behaves like cosine distance —
    otherwise longer documents pick up more hash collisions and skew
    "closer" than short, truly relevant ones. Good enough to rank
    documents that share vocabulary with the query above ones that don't,
    which is all these tests need.

    Uses zlib.crc32 rather than Python's built-in hash() — str hashing is
    randomized per-process (PYTHONHASHSEED), which would make the word ->
    bucket mapping (and therefore the ranking) flaky across test runs.
    """

    VECTOR_SIZE = 512

    def __init__(self):
        pass

    @staticmethod
    def name() -> str:
        return "hashing_test_embedding_function"

    def get_config(self) -> dict:
        return {}

    def __call__(self, input: Documents) -> Embeddings:
        vectors = []
        for text in input:
            vector = [0.0] * self.VECTOR_SIZE
            for word in text.lower().split():
                vector[zlib.crc32(word.encode()) % self.VECTOR_SIZE] += 1.0
            norm = sum(x * x for x in vector) ** 0.5 or 1.0
            vectors.append([x / norm for x in vector])
        return vectors


@pytest.fixture
def sample_collection(monkeypatch):
    """Builds a temp Chroma collection from SAMPLE_ENTRIES and points
    rag_index at it for the duration of the test.
    """
    tmp_dir = tempfile.mkdtemp(prefix="rag_index_test_")
    embedding_function = HashingEmbeddingFunction()

    monkeypatch.setattr(rag_index, "CHROMA_DB_DIR", tmp_dir)
    monkeypatch.setattr(rag_index, "COLLECTION_NAME", "test_station_info")

    rag_index.build_index(entries=SAMPLE_ENTRIES, embedding_function=embedding_function)

    return embedding_function


def test_search_station_info_returns_relevant_result_first(sample_collection):
    results = rag_index.search_station_info(
        "elevator wheelchair access Dupont Circle",
        n_results=2,
        embedding_function=sample_collection,
    )

    assert len(results) == 2
    assert results[0]["station"] == "Dupont Circle"
    assert results[0]["type"] == "accessibility"
    assert "elevator" in results[0]["text"].lower()
    assert isinstance(results[0]["score"], float)


def test_search_station_info_respects_n_results(sample_collection):
    results = rag_index.search_station_info(
        "Metro Center", n_results=1, embedding_function=sample_collection
    )
    assert len(results) == 1

    results = rag_index.search_station_info(
        "Metro Center", n_results=3, embedding_function=sample_collection
    )
    assert len(results) == 3


def test_search_station_info_none_station_comes_back_as_none(sample_collection):
    results = rag_index.search_station_info(
        "SmarTrip fares off-peak", n_results=1, embedding_function=sample_collection
    )
    assert results[0]["station"] is None
    assert results[0]["type"] == "faq"


def test_search_station_info_missing_collection_returns_message(monkeypatch):
    tmp_dir = tempfile.mkdtemp(prefix="rag_index_test_empty_")
    monkeypatch.setattr(rag_index, "CHROMA_DB_DIR", tmp_dir)
    monkeypatch.setattr(rag_index, "COLLECTION_NAME", "does_not_exist")

    results = rag_index.search_station_info("elevator")

    assert len(results) == 1
    assert results[0]["station"] is None
    assert "hasn't been built" in results[0]["text"]


def test_search_station_info_empty_collection_returns_message(monkeypatch):
    tmp_dir = tempfile.mkdtemp(prefix="rag_index_test_zero_")
    embedding_function = HashingEmbeddingFunction()

    monkeypatch.setattr(rag_index, "CHROMA_DB_DIR", tmp_dir)
    monkeypatch.setattr(rag_index, "COLLECTION_NAME", "test_empty_collection")

    rag_index.build_index(entries=[], embedding_function=embedding_function)

    results = rag_index.search_station_info("elevator", embedding_function=embedding_function)

    assert len(results) == 1
    assert results[0]["station"] is None
    assert "empty" in results[0]["text"]
