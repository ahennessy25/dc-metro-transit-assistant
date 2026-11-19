"""Builds the ChromaDB index over descriptive Metrorail text (accessibility
notes, alert history, trip-planning FAQ) from data/rag_sources/entries.json.

entries.json can hold rows in two shapes:
  - a ready-made chunk: {text, station, type, source} — indexed as-is.
  - a merged station entry from compile_sources.py's live WMATA pipeline:
    {code, codes, name, lines, address, lat, lon, entrances} — expanded by
    _generate_chunks() into a station_info chunk and an accessibility chunk,
    both in the same {text, station, type, source} shape.
Either way, each resulting chunk is indexed as one unit with no further
splitting. Uses Chroma's default embedding function.
"""

import json
import re
from pathlib import Path

import chromadb
from chromadb.errors import NotFoundError

from config import CHROMA_DB_DIR

ENTRIES_PATH = Path(__file__).parent / "rag_sources" / "entries.json"
COLLECTION_NAME = "wmata_station_info"

LINE_NAMES = {
    "RD": "Red",
    "BL": "Blue",
    "OR": "Orange",
    "SV": "Silver",
    "GR": "Green",
    "YL": "Yellow",
}

_ELEVATOR_SUFFIX_RE = re.compile(r"\s*\(elevator\)\s*$", re.IGNORECASE)


def _load_entries() -> list[dict]:
    return json.loads(ENTRIES_PATH.read_text(encoding="utf-8"))


def _join_with_and(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _strip_elevator_suffix(name: str) -> str:
    """Drops a trailing "(ELEVATOR)" tag from an entrance name — redundant
    once the surrounding sentence already says "elevator entrance".
    """
    return _ELEVATOR_SUFFIX_RE.sub("", name).strip()


def _station_info_chunk(station: dict) -> dict:
    """General station_info chunk: name, lines served, and address."""
    line_names = [LINE_NAMES.get(code, code) for code in station["lines"]]
    line_word = "line" if len(line_names) == 1 else "lines"
    text = (
        f"{station['name']} station serves the {_join_with_and(line_names)} {line_word}. "
        f"Located at {station['address']}."
    )
    return {
        "text": text,
        "station": station["code"],
        "type": "station_info",
        "source": "wmata_jstations",
    }


def _accessibility_chunk(station: dict) -> dict:
    """Elevator-accessibility chunk — explicit even when a station has zero
    elevator entrances, so search_station_info() can give a real "no
    elevator access" answer instead of silence.
    """
    entrances = station["entrances"]
    elevators = [e for e in entrances if e["is_elevator"]]
    non_elevators = [e for e in entrances if not e["is_elevator"]]

    if not entrances:
        text = f"{station['name']} has no entrance data available."
    elif not elevators:
        entrance_word = "entrance" if len(entrances) == 1 else "entrances"
        verb = "has" if len(entrances) == 1 else "have"
        text = (
            f"{station['name']} has no elevator entrances. "
            f"None of its {len(entrances)} {entrance_word} {verb} an elevator."
        )
    else:
        elevator_word = "entrance" if len(elevators) == 1 else "entrances"
        elevator_names = _join_with_and([_strip_elevator_suffix(e["name"]) for e in elevators])
        text = f"{station['name']} has {len(elevators)} elevator {elevator_word}: {elevator_names}."
        if non_elevators:
            other_names = _join_with_and([e["name"] for e in non_elevators])
            text += f" Other entrances ({other_names}) do not have elevators."
        else:
            text += " All entrances have elevators."

    return {
        "text": text,
        "station": station["code"],
        "type": "accessibility",
        "source": "wmata_jstationentrances",
    }


def _generate_chunks(raw_entry: dict) -> list[dict]:
    """Expands one raw entries.json row into one or more RAG-indexable
    chunks of the {text, station, type, source} shape.

    A row that's already in that shape (has "text") is a ready-made chunk
    and passes through unchanged — this is how non-station content types
    (FAQ, alert history, etc., if/when reintroduced) stay indexed without
    any change here. A merged station entry from compile_sources.py (has
    "entrances") expands into a station_info chunk and an accessibility
    chunk.
    """
    if "text" in raw_entry:
        return [raw_entry]
    if "entrances" in raw_entry:
        return [_station_info_chunk(raw_entry), _accessibility_chunk(raw_entry)]
    raise ValueError(f"Unrecognized entries.json row shape: {sorted(raw_entry)}")


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

    chunks = [chunk for entry in entries for chunk in _generate_chunks(entry)]

    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    existing_collections = {c.name for c in client.list_collections()}
    if COLLECTION_NAME in existing_collections:
        client.delete_collection(COLLECTION_NAME)
    create_kwargs = {}
    if embedding_function is not None:
        create_kwargs["embedding_function"] = embedding_function
    collection = client.create_collection(COLLECTION_NAME, **create_kwargs)

    if chunks:
        collection.add(
            documents=[chunk["text"] for chunk in chunks],
            metadatas=[
                {
                    "station": chunk.get("station") or "",
                    "type": chunk["type"],
                    "source": chunk["source"],
                }
                for chunk in chunks
            ],
            ids=[f"entry-{i}" for i in range(len(chunks))],
        )

    return collection


def _get_existing_collection(client, **kwargs):
    """Returns the named collection if it exists (populated or not), else None.

    Single source of truth for "does this collection exist" so
    search_station_info() and ensure_index_built() can't drift apart on how
    they detect a missing collection.
    """
    try:
        return client.get_collection(COLLECTION_NAME, **kwargs)
    except NotFoundError:
        return None


def ensure_index_built() -> None:
    """Builds the Chroma index if it isn't already present and populated.

    `chroma_db/` is gitignored, so a fresh clone (e.g. a new Space deploy)
    has no index on disk — without this, search_station_info() would silently
    return "index hasn't been built yet" until someone ran build_index() by
    hand. Skips the rebuild when a populated collection already exists so a
    normal restart doesn't re-embed entries.json (and re-download the
    embedding model) every time.
    """
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    collection = _get_existing_collection(client)
    if collection is not None and collection.count() > 0:
        return

    build_index()


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

    collection = _get_existing_collection(client, **get_kwargs)
    if collection is None:
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
