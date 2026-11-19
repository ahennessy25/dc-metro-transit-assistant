"""Compiles real WMATA Rail station/entrance data into the flat list of
entries entries.json is built from, for the RAG index.

compile_sources() fetches the Station List and Station Entrances endpoints
live, merges dual-platform stations and attaches each station's entrances
(see transform_stations()/transform_entrances()/merge_entrances_into_stations()),
and returns one entry per physical station. Kept separate from the embedding
step itself (data/rag_index.py) so the content can be reviewed/edited as
plain JSON first.
"""

import json
import re
from pathlib import Path

import requests

from config import WMATA_API_KEY

OUTPUT_PATH = Path(__file__).parent / "entries.json"

STATION_LIST_URL = "https://api.wmata.com/Rail.svc/json/jStations"
STATION_ENTRANCES_URL = "https://api.wmata.com/Rail.svc/json/jStationEntrances"


class WmataStationInfoError(RuntimeError):
    """Raised when WMATA's Rail Station Information API can't be fetched."""


def _get(url: str) -> dict:
    if not WMATA_API_KEY:
        raise WmataStationInfoError(
            "WMATA_API_KEY is not set. Add it to .env (see .env.example)."
        )

    try:
        response = requests.get(url, headers={"api_key": WMATA_API_KEY}, timeout=15)
    except requests.exceptions.RequestException as e:
        raise WmataStationInfoError(f"Failed to reach WMATA API: {e}") from e

    if response.status_code in (401, 403):
        raise WmataStationInfoError(
            f"WMATA API rejected the request (HTTP {response.status_code}) — "
            "check that WMATA_API_KEY is valid and not expired."
        )
    if response.status_code != 200:
        raise WmataStationInfoError(
            f"WMATA API request failed with HTTP {response.status_code}."
        )

    return response.json()


def fetch_station_list() -> list[dict]:
    """Fetches WMATA's Rail Station List (jStations) — one row per station
    code, with name/lat/lon/address/line codes and StationTogether1/2 for
    dual-platform stations. See transform_stations() for the merge step.
    """
    return _get(STATION_LIST_URL)["Stations"]


def fetch_station_entrances() -> list[dict]:
    """Fetches WMATA's Rail Station Entrances (jStationEntrances) — every
    entrance systemwide, each tagged with the station code(s) it serves.

    Deliberately passes no Lat/Lon/Radius query params. WMATA's docs suggest
    Lat=0/Lon=0/Radius=0 means "no filter," but a live check showed that
    combination returns zero entrances — omitting the params entirely is
    what actually returns the full list (confirmed against a real response:
    275 entrances systemwide).
    """
    return _get(STATION_ENTRANCES_URL)["Entrances"]


def _collect_line_codes(raw_station: dict) -> list[str]:
    return [
        raw_station[key]
        for key in ("LineCode1", "LineCode2", "LineCode3", "LineCode4")
        if raw_station.get(key)
    ]


def _flatten_address(address: dict) -> str:
    return f"{address.get('Street', '')}, {address.get('City', '')}, {address.get('State', '')} {address.get('Zip', '')}".strip()


def transform_stations(raw_stations: list[dict]) -> list[dict]:
    """Merges WMATA jStations rows (the "Stations" array) into one entry per
    physical station.

    jStations returns one row per station *code*, and a station with two
    platform levels gets two rows that reference each other via
    StationTogether1/StationTogether2 (empty string when a station has no
    pair). As a sanity-check reference — not hardcoded, since the merge is
    driven purely by StationTogether1/2 — the four paired stations as of
    this writing are Metro Center, Gallery Place, L'Enfant Plaza, and Fort
    Totten.

    Any row whose StationTogether1/2 points at another code present in
    `raw_stations` is merged into a single output entry rather than kept as
    two. The alphabetically/numerically lower of the two codes becomes the
    canonical `code`; both original codes are kept in `codes` so a lookup by
    either still resolves to this entry. Line codes (LineCode1-4) from both
    rows are deduplicated into `lines`, the nested `Address` is flattened
    into a single string, and `name`/`lat`/`lon` are taken from the first
    (lower-code) row.
    """
    by_code = {station["Code"]: station for station in raw_stations}
    merged = []
    seen = set()

    for station in raw_stations:
        code = station["Code"]
        if code in seen:
            continue
        seen.add(code)

        partner_code = None
        for key in ("StationTogether1", "StationTogether2"):
            candidate = station.get(key) or ""
            if candidate and candidate in by_code:
                partner_code = candidate
                break

        if partner_code is not None:
            seen.add(partner_code)
            codes = sorted([code, partner_code])
            lines = _collect_line_codes(station) + _collect_line_codes(by_code[partner_code])
        else:
            codes = [code]
            lines = _collect_line_codes(station)

        canonical_row = by_code[codes[0]]
        merged.append(
            {
                "code": codes[0],
                "codes": codes,
                "name": canonical_row["Name"],
                "lat": canonical_row["Lat"],
                "lon": canonical_row["Lon"],
                "lines": sorted(set(lines)),
                "address": _flatten_address(canonical_row.get("Address") or {}),
            }
        )

    return merged


def _sample_raw_stations_for_demo() -> list[dict]:
    """Small fixture of raw jStations rows (real field shapes, trimmed) for
    manually verifying transform_stations() before wiring it into the full
    pipeline. Includes one paired station (Metro Center) and three unpaired
    ones.
    """
    return [
        {
            "Code": "A01", "Name": "Metro Center",
            "StationTogether1": "C01", "StationTogether2": "",
            "LineCode1": "RD", "LineCode2": None, "LineCode3": None, "LineCode4": None,
            "Lat": 38.898303, "Lon": -77.028099,
            "Address": {"Street": "607 13th St. NW", "City": "Washington", "State": "DC", "Zip": "20005"},
        },
        {
            "Code": "C01", "Name": "Metro Center",
            "StationTogether1": "A01", "StationTogether2": "",
            "LineCode1": "BL", "LineCode2": "OR", "LineCode3": "SV", "LineCode4": None,
            "Lat": 38.898303, "Lon": -77.028099,
            "Address": {"Street": "607 13th St. NW", "City": "Washington", "State": "DC", "Zip": "20005"},
        },
        {
            "Code": "A02", "Name": "Farragut North",
            "StationTogether1": "", "StationTogether2": "",
            "LineCode1": "RD", "LineCode2": None, "LineCode3": None, "LineCode4": None,
            "Lat": 38.903192, "Lon": -77.039766,
            "Address": {"Street": "1001 Connecticut Avenue NW", "City": "Washington", "State": "DC", "Zip": "20036"},
        },
        {
            "Code": "A03", "Name": "Dupont Circle",
            "StationTogether1": "", "StationTogether2": "",
            "LineCode1": "RD", "LineCode2": None, "LineCode3": None, "LineCode4": None,
            "Lat": 38.909499, "Lon": -77.04362,
            "Address": {"Street": "1525 20th St. NW", "City": "Washington", "State": "DC", "Zip": "20036"},
        },
        {
            "Code": "B01", "Name": "Gallery Place-Chinatown",
            "StationTogether1": "F01", "StationTogether2": "",
            "LineCode1": "RD", "LineCode2": None, "LineCode3": None, "LineCode4": None,
            "Lat": 38.898303, "Lon": -77.021975,
            "Address": {"Street": "630 H St. NW", "City": "Washington", "State": "DC", "Zip": "20001"},
        },
        {
            "Code": "F01", "Name": "Gallery Place-Chinatown",
            "StationTogether1": "B01", "StationTogether2": "",
            "LineCode1": "GR", "LineCode2": "YL", "LineCode3": None, "LineCode4": None,
            "Lat": 38.898303, "Lon": -77.021975,
            "Address": {"Street": "630 H St. NW", "City": "Washington", "State": "DC", "Zip": "20001"},
        },
    ]


def transform_entrances(raw_entrances: list[dict]) -> dict[str, list[dict]]:
    """Groups WMATA jStationEntrances rows by the station code(s) each one serves.

    Each raw entrance carries StationCode1 and, optionally, StationCode2 (an
    empty string when the entrance only serves one station). An entrance
    serving two paired station codes (e.g. a shared Metro Center A01/C01
    entrance) is added under both codes here — merge_entrances_into_stations()
    reconciles that once stations are merged, deduplicating anything that got
    added twice.

    An entrance counts as an elevator if "elevator" (case-insensitive)
    appears literally in its `Name` or `Description` — e.g.
    "Q ST NW & CONNECTICUT AVE NW (ELEVATOR)" tags it in the name, but some
    real entrances (confirmed against live data — Union Station's AMTRAK/
    MARC/VRE passageway entrance) only say it in the description, with no
    "(ELEVATOR)" tag in the name. Checking both catches those without
    inferring anything not literally in WMATA's text. `name` is stored with
    any such suffix intact (not stripped); `description` is kept verbatim
    too, both for this check and so later text-generation can quote WMATA's
    own wording rather than paraphrasing it as "accessible."

    This is a keyword match, not a judgment of current elevator status — a
    description that says "elevator" alongside a negation/outage word (no,
    not, closed, out of service, construction) still sets is_elevator=True
    here. See find_ambiguous_elevator_entrances() to surface those for human
    review before they're used to claim an entrance is accessible.
    """
    entrances_by_code: dict[str, list[dict]] = {}

    for entrance in raw_entrances:
        name = entrance["Name"]
        description = entrance.get("Description") or ""
        processed = {
            "name": name,
            "description": description,
            "lat": entrance["Lat"],
            "lon": entrance["Lon"],
            "is_elevator": "elevator" in f"{name} {description}".lower(),
        }

        for key in ("StationCode1", "StationCode2"):
            code = entrance.get(key) or ""
            if code:
                entrances_by_code.setdefault(code, []).append(processed)

    return entrances_by_code


def merge_entrances_into_stations(stations: list[dict], entrances_by_code: dict) -> list[dict]:
    """Attaches a deduplicated `entrances` list to each merged station entry
    from transform_stations(), combining entrances_by_code's lists across
    every code in that station's `codes`.

    An entrance shared between a station's two paired codes (added under
    both by transform_entrances()) would otherwise appear twice; dedupe by
    (name, lat, lon) rather than object identity, since the same entrance
    can arrive as separate dict instances after being looked up under two
    different codes.
    """
    merged = []

    for station in stations:
        seen_keys = set()
        entrances = []
        for code in station["codes"]:
            for entrance in entrances_by_code.get(code, []):
                key = (entrance["name"], entrance["lat"], entrance["lon"])
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                entrances.append(entrance)

        merged.append({**station, "entrances": entrances})

    return merged


_NEGATION_WORDS = ("no", "not", "closed", "out of service", "construction")
_NEGATION_PATTERNS = [re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE) for word in _NEGATION_WORDS]


def find_ambiguous_elevator_entrances(stations: list[dict]) -> list[dict]:
    """Flags entrances already marked is_elevator=True whose Name/Description
    also contain a negation/outage word (no, not, closed, out of service,
    construction) — e.g. "no elevator" or "elevator closed for
    construction" would otherwise read as a plain elevator mention.

    `is_elevator` is a keyword match, not a judgment of current status, so
    these need a human read before entries.json's text quotes WMATA's
    wording as evidence an entrance is accessible — the literal text might
    actually be saying the opposite. Takes the merged station list (post
    merge_entrances_into_stations()) so results can be reported per station.
    """
    flagged = []
    for station in stations:
        for entrance in station["entrances"]:
            if not entrance["is_elevator"]:
                continue
            text = f"{entrance['name']} {entrance['description']}"
            if any(pattern.search(text) for pattern in _NEGATION_PATTERNS):
                flagged.append({"station": station["name"], **entrance})
    return flagged


def _sample_raw_entrances_for_demo() -> list[dict]:
    """Real (trimmed) jStationEntrances rows for Metro Center (A01/C01, 8
    entrances, 1 elevator) and Dupont Circle (A03, 3 entrances, 1 elevator),
    captured from a live call — for manually verifying transform_entrances()
    and merge_entrances_into_stations() before wiring them into the pipeline.
    """
    return [
        {
            "Name": "11TH ST NW & G ST NW", "StationCode1": "A01", "StationCode2": "C01",
            "Description": "Building Entrance from the southeast corner of 11th St NW and G St NW.",
            "Lat": 38.898073, "Lon": -77.026789,
        },
        {
            "Name": "13TH ST NW & G ST NW", "StationCode1": "A01", "StationCode2": "C01",
            "Description": "Building Entrance from the southeast corner of 13th St NW and G St NW.",
            "Lat": 38.898026, "Lon": -77.029379,
        },
        {
            "Name": "ENTRANCE FROM MACY'S", "StationCode1": "A01", "StationCode2": "C01",
            "Description": "Building entrance from west mezzanine to Macy's entrance.",
            "Lat": 38.898433, "Lon": -77.029402,
        },
        {
            "Name": "GRANT HYATT HOTEL", "StationCode1": "A01", "StationCode2": "C01",
            "Description": "Building entrance from east mezzanine to Grand Hyatt Hotel entrance.",
            "Lat": 38.898365, "Lon": -77.026683,
        },
        {
            "Name": "12TH ST NW & G ST NW (ELEVATOR)", "StationCode1": "C01", "StationCode2": "A01",
            "Description": "Street level elevator at 12th St NW segment between G St NW and H St NW.",
            "Lat": 38.89892, "Lon": -77.027914,
        },
        {
            "Name": "12TH ST NW & F ST NW", "StationCode1": "C01", "StationCode2": "A01",
            "Description": "Escalator to station from the building located at the southeast corner of 12th St NW and F St NW.",
            "Lat": 38.897147, "Lon": -77.028567,
        },
        {
            "Name": "12TH ST NW & G ST NW", "StationCode1": "C01", "StationCode2": "A01",
            "Description": "Escalator to station from northeast corner of 12th St NW and G St NW.",
            "Lat": 38.898498, "Lon": -77.027903,
        },
        {
            "Name": "ENTRANCE FROM MACY'S", "StationCode1": "C01", "StationCode2": "A01",
            "Description": "Building entrance from north mezzanine to Macy's entrance.",
            "Lat": 38.898985, "Lon": -77.028228,
        },
        {
            "Name": "Q ST NW & CONNECTICUT AVE NW (ELEVATOR)", "StationCode1": "A03", "StationCode2": "",
            "Description": "Street level elevator at north side of the station is accessible from "
            "Connecticut Ave NW, 20th NW and Q St NW.",
            "Lat": 38.910792, "Lon": -77.044553,
        },
        {
            "Name": "19TH ST NW & CONNECTICUT AVE NW", "StationCode1": "A03", "StationCode2": "",
            "Description": "Canopied entrance from 19th St NW and is also accessible from Connecticut Ave NW.",
            "Lat": 38.908648, "Lon": -77.043322,
        },
        {
            "Name": "Q ST NW & 20TH ST NW", "StationCode1": "A03", "StationCode2": "",
            "Description": "North side station entrance is located at the southeast corner of 20th NW and "
            "Q St NW and accessible from Connecticut Ave NW.",
            "Lat": 38.911001, "Lon": -77.044746,
        },
    ]


def compile_sources() -> list[dict]:
    """Fetches WMATA's live Station List and Station Entrances, merges
    dual-platform stations (transform_stations()), groups entrances by
    station code (transform_entrances()), and attaches each station's
    deduplicated entrance list (merge_entrances_into_stations()).

    Returns the list of merged station entries entries.json is built from —
    replaces the old hand-written PLACEHOLDER entries entirely.
    """
    stations = transform_stations(fetch_station_list())
    entrances_by_code = transform_entrances(fetch_station_entrances())
    return merge_entrances_into_stations(stations, entrances_by_code)


def write_entries(entries: list[dict], output_path: Path = OUTPUT_PATH) -> None:
    output_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


if __name__ == "__main__":
    entries = compile_sources()
    write_entries(entries)

    total_entrances = sum(len(e["entrances"]) for e in entries)
    total_elevators = sum(1 for e in entries for ent in e["entrances"] if ent["is_elevator"])
    stations_with_elevator = sum(1 for e in entries if any(ent["is_elevator"] for ent in e["entrances"]))

    print(f"Wrote {len(entries)} station entries to {OUTPUT_PATH}")
    print(f"  total entrances: {total_entrances}")
    print(f"  elevator entrances: {total_elevators}")
    print(f"  stations with at least one elevator entrance: {stations_with_elevator}")

    ambiguous = find_ambiguous_elevator_entrances(entries)
    print(f"\n  entrances mentioning 'elevator' alongside a negation/outage word ({len(ambiguous)}) — review by hand:")
    for item in ambiguous:
        print(f"    [{item['station']}] {item['name']!r} — {item['description']!r}")

    print("\n--- transform_stations() demo (not yet wired into the pipeline) ---")
    raw_stations = _sample_raw_stations_for_demo()
    merged_stations = transform_stations(raw_stations)
    print(f"Merged {len(raw_stations)} raw station rows into {len(merged_stations)} entries:")
    print(json.dumps(merged_stations, indent=2))

    print("\n--- transform_entrances() / merge_entrances_into_stations() smoke test ---")
    raw_entrances = _sample_raw_entrances_for_demo()
    entrances_by_code = transform_entrances(raw_entrances)
    stations_with_entrances = merge_entrances_into_stations(merged_stations, entrances_by_code)

    by_name = {s["name"]: s for s in stations_with_entrances}
    metro_center = by_name["Metro Center"]
    dupont_circle = by_name["Dupont Circle"]

    metro_center_elevators = sum(1 for e in metro_center["entrances"] if e["is_elevator"])
    dupont_circle_elevators = sum(1 for e in dupont_circle["entrances"] if e["is_elevator"])

    print(f"Metro Center: {len(metro_center['entrances'])} entrances, {metro_center_elevators} elevator(s)")
    print(f"Dupont Circle: {len(dupont_circle['entrances'])} entrances, {dupont_circle_elevators} elevator(s)")

    assert len(metro_center["entrances"]) == 8, "expected 8 deduplicated Metro Center entrances"
    assert metro_center_elevators == 1, "expected 1 Metro Center elevator entrance"
    assert len(dupont_circle["entrances"]) == 3, "expected 3 Dupont Circle entrances"
    assert dupont_circle_elevators == 1, "expected 1 Dupont Circle elevator entrance"
    print("OK: counts match the live data verified by hand.")
