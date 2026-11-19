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


SAMPLE_STATIONS = [
    {
        "code": "A03",
        "codes": ["A03"],
        "name": "Dupont Circle",
        "lat": 38.909499,
        "lon": -77.04362,
        "lines": ["RD"],
        "address": "1525 20th St. NW, Washington, DC 20036",
        "entrances": [
            {
                "name": "Q ST NW & CONNECTICUT AVE NW (ELEVATOR)",
                "description": "Street level elevator at north side of the station.",
                "lat": 38.910792,
                "lon": -77.044553,
                "is_elevator": True,
            },
            {
                "name": "19TH ST NW & CONNECTICUT AVE NW",
                "description": "Canopied entrance from 19th St NW.",
                "lat": 38.908648,
                "lon": -77.043322,
                "is_elevator": False,
            },
        ],
    },
    {
        "code": "B06",
        "codes": ["B06", "E06"],
        "name": "Fort Totten",
        "lat": 38.951779,
        "lon": -77.002174,
        "lines": ["RD", "GR", "YL"],
        "address": "550 Galloway St NE, Washington, DC 20011",
        "entrances": [
            {
                "name": "GALLOWAY ST NE & 1ST PL NE",
                "description": "Facility entrance from the Galloway St NE segment.",
                "lat": 38.952078,
                "lon": -77.002275,
                "is_elevator": False,
            },
        ],
    },
]


@pytest.fixture
def station_collection(monkeypatch):
    """Builds a temp Chroma collection from SAMPLE_STATIONS — the new
    compile_sources.py station-entry shape (code/codes/name/lines/address/
    entrances) — via build_index()'s _generate_chunks() expansion, so the
    station_info/accessibility chunk generation is exercised end-to-end
    rather than just unit-tested in isolation. Separate fixture from
    sample_collection/SAMPLE_ENTRIES, which exercise the older ready-made
    {text, station, type, source} chunk shape.
    """
    tmp_dir = tempfile.mkdtemp(prefix="rag_index_test_stations_")
    embedding_function = HashingEmbeddingFunction()

    monkeypatch.setattr(rag_index, "CHROMA_DB_DIR", tmp_dir)
    monkeypatch.setattr(rag_index, "COLLECTION_NAME", "test_station_entries")

    rag_index.build_index(entries=SAMPLE_STATIONS, embedding_function=embedding_function)

    return embedding_function


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


def test_search_station_info_finds_elevator_present_accessibility_chunk(station_collection):
    """An elevator-present station (Dupont Circle) should have a retrievable
    accessibility chunk that says so, generated by _accessibility_chunk()
    from its one elevator entrance.
    """
    results = rag_index.search_station_info(
        "Dupont Circle elevator access", n_results=2, embedding_function=station_collection
    )

    accessibility_results = [r for r in results if r["type"] == "accessibility" and r["station"] == "A03"]
    assert accessibility_results
    assert "1 elevator entrance" in accessibility_results[0]["text"]
    assert "Q ST NW" in accessibility_results[0]["text"]


def test_search_station_info_finds_elevator_absent_accessibility_chunk(station_collection):
    """An elevator-absent station (Fort Totten) should have a retrievable
    accessibility chunk that explicitly says it has no elevators, rather
    than being silently missing from the index — a "no" answer needs to be
    as testable as a "yes" one.
    """
    results = rag_index.search_station_info(
        "Fort Totten elevator access", n_results=2, embedding_function=station_collection
    )

    accessibility_results = [r for r in results if r["type"] == "accessibility" and r["station"] == "B06"]
    assert accessibility_results
    assert "no elevator entrances" in accessibility_results[0]["text"].lower()


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
