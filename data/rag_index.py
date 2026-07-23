"""Builds the ChromaDB index over descriptive Metrorail text (accessibility
notes, alert history, trip-planning FAQ) from data/rag_sources/entries.json.

Each entry is already a short, discrete fact, so it's indexed as one chunk
with no further splitting. Uses Chroma's default embedding function.
"""

import json
from pathlib import Path

import chromadb
from chromadb.errors import NotFoundError

from config import CHROMA_DB_DIR

ENTRIES_PATH = Path(__file__).parent / "rag_sources" / "entries.json"
COLLECTION_NAME = "wmata_station_info"


def _load_entries() -> list[dict]:
    return json.loads(ENTRIES_PATH.read_text(encoding="utf-8"))


def build_index(entries: list[dict] | None = None, embedding_function=None):
    """Rebuilds the Chroma collection and returns it.

    Safe to re-run whenever entries.json changes — drops and recreates the
    collection each time rather than upserting, so stale/removed entries
    don't linger.

    `entries` and `embedding_function` default to entries.json and Chroma's
    default embedding function respectively; they're overridable so tests
    can build a small, fast, offline collection instead.
    """
    if entries is None:
        entries = _load_entries()

    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    existing_collections = {c.name for c in client.list_collections()}
    if COLLECTION_NAME in existing_collections:
        client.delete_collection(COLLECTION_NAME)
    create_kwargs = {}
    if embedding_function is not None:
        create_kwargs["embedding_function"] = embedding_function
    collection = client.create_collection(COLLECTION_NAME, **create_kwargs)

    if entries:
        collection.add(
            documents=[entry["text"] for entry in entries],
            metadatas=[
                {
                    "station": entry.get("station") or "",
                    "type": entry["type"],
                    "source": entry["source"],
                }
                for entry in entries
            ],
            ids=[f"entry-{i}" for i in range(len(entries))],
        )

    return collection


def search_station_info(query: str, n_results: int = 3, embedding_function=None) -> list[dict]:
    """Searches the RAG index for chunks relevant to `query`.

    Returns a list of dicts with `text`, `station`, `type`, and `score`
    (Chroma's distance — lower means more similar). If the index hasn't been
    built yet or has no entries, returns a single-item list with a `text`
    explaining that, rather than raising, since this is called directly by
    Claude's tool-calling loop and needs a result it can relay to the user.

    `embedding_function` must match whatever build_index() used to create
    the collection — only needed when overriding the default (e.g. in tests).
    """
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)

    get_kwargs = {}
    if embedding_function is not None:
        get_kwargs["embedding_function"] = embedding_function

    try:
        collection = client.get_collection(COLLECTION_NAME, **get_kwargs)
    except NotFoundError:
        return [
            {
                "text": "The station info index hasn't been built yet — run build_index() first.",
                "station": None,
                "type": None,
                "score": None,
            }
        ]

    if collection.count() == 0:
        return [
            {
                "text": "The station info index is empty — no entries have been indexed yet.",
                "station": None,
                "type": None,
                "score": None,
            }
        ]

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    return [
        {
            "text": document,
            "station": metadata.get("station") or None,
            "type": metadata.get("type"),
            "score": distance,
        }
        for document, metadata, distance in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        )
    ]


if __name__ == "__main__":
    collection = build_index()
    print(f"Indexed {collection.count()} documents into '{COLLECTION_NAME}' at {CHROMA_DB_DIR}/")
