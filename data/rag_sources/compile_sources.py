"""Compiles descriptive Metrorail text (accessibility notes, historical alert
descriptions, trip-planning FAQ content) into a flat list of entries for the
RAG index.

This is the source-of-truth structure that data/rag.py will eventually embed
into ChromaDB — kept separate from the embedding step itself so the content
can be reviewed/edited as plain JSON first.

All entries below are placeholders (marked PLACEHOLDER in the text) for 5
stations, meant to demonstrate the shape — swap in real content from WMATA's
station guides, MetroAlerts archive, and trip-planning FAQ before this feeds
the actual index.
"""

import json
from pathlib import Path

OUTPUT_PATH = Path(__file__).parent / "entries.json"

ENTRIES = [
    # --- accessibility notes (one per station) ---
    {
        "text": "PLACEHOLDER: Metro Center has elevator access from street level to the "
        "mezzanine and from the mezzanine to both the Red Line and Blue/Orange/Silver "
        "Line platforms. All entrances are accessible.",
        "station": "Metro Center",
        "type": "accessibility",
        "source": "WMATA station accessibility guide (placeholder)",
    },
    {
        "text": "PLACEHOLDER: Union Station has a street-level elevator at the main "
        "entrance and platform elevators serving the Red Line. Escalator outages are "
        "common during peak commuter rail transfer times.",
        "station": "Union Station",
        "type": "accessibility",
        "source": "WMATA station accessibility guide (placeholder)",
    },
    {
        "text": "PLACEHOLDER: Dupont Circle's south entrance (19th St) has no elevator; "
        "wheelchair users should use the north entrance (Q St), which has full "
        "elevator access to the platform.",
        "station": "Dupont Circle",
        "type": "accessibility",
        "source": "WMATA station accessibility guide (placeholder)",
    },
    {
        "text": "PLACEHOLDER: Gallery Place-Chinatown has elevator access at all "
        "entrances and between both the Red Line and Green/Yellow Line platforms, "
        "though transfers require exiting fare gates at street level during certain "
        "elevator outages.",
        "station": "Gallery Place-Chinatown",
        "type": "accessibility",
        "source": "WMATA station accessibility guide (placeholder)",
    },
    {
        "text": "PLACEHOLDER: Rosslyn has a single long escalator bank and one elevator "
        "connecting the mezzanine to the platform; the elevator is the only accessible "
        "path when escalators are under maintenance.",
        "station": "Rosslyn",
        "type": "accessibility",
        "source": "WMATA station accessibility guide (placeholder)",
    },
    # --- historical service alert descriptions ---
    {
        "text": "PLACEHOLDER: Single-tracking between Metro Center and Gallery "
        "Place-Chinatown on the Red Line due to weekend track maintenance, resulting "
        "in delays of up to 15 minutes.",
        "station": "Metro Center",
        "type": "alert_history",
        "source": "WMATA MetroAlerts archive (placeholder)",
    },
    {
        "text": "PLACEHOLDER: Elevator at the Q St entrance to Dupont Circle was out of "
        "service for approximately two weeks for a scheduled motor replacement.",
        "station": "Dupont Circle",
        "type": "alert_history",
        "source": "WMATA MetroAlerts archive (placeholder)",
    },
    {
        "text": "PLACEHOLDER: Systemwide reduced service on a federal holiday, with "
        "trains running on a weekend schedule across all six lines.",
        "station": None,
        "type": "alert_history",
        "source": "WMATA MetroAlerts archive (placeholder)",
    },
    # --- trip-planning FAQ content ---
    {
        "text": "PLACEHOLDER: SmarTrip fares are calculated by distance traveled and "
        "time of day; peak fares apply on weekdays roughly 5-9:30am and 3-7pm, with "
        "off-peak (lower) fares at all other times.",
        "station": None,
        "type": "faq",
        "source": "WMATA trip-planning FAQ (placeholder)",
    },
    {
        "text": "PLACEHOLDER: Bikes are permitted on Metrorail at all times except "
        "during designated peak-hour restrictions on certain lines; folding bikes are "
        "always allowed.",
        "station": None,
        "type": "faq",
        "source": "WMATA trip-planning FAQ (placeholder)",
    },
    {
        "text": "PLACEHOLDER: Free transfers between Metrorail and Metrobus are "
        "available within a set time window when paying with the same SmarTrip card.",
        "station": None,
        "type": "faq",
        "source": "WMATA trip-planning FAQ (placeholder)",
    },
]


def compile_sources() -> list[dict]:
    """Returns the flat list of RAG source entries (text/station/type/source)."""
    return ENTRIES


def write_entries(entries: list[dict], output_path: Path = OUTPUT_PATH) -> None:
    output_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


if __name__ == "__main__":
    entries = compile_sources()
    write_entries(entries)

    counts_by_type = {}
    for entry in entries:
        counts_by_type[entry["type"]] = counts_by_type.get(entry["type"], 0) + 1

    print(f"Wrote {len(entries)} entries to {OUTPUT_PATH}")
    for entry_type, count in counts_by_type.items():
        print(f"  {entry_type}: {count}")
