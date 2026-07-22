"""Downloads and loads WMATA's static Metrorail GTFS feed.

Fetches the feed via the WMATA API (not a manual download), per CLAUDE.md's
convention of keeping DC-Metro-GTFS-Files/ / data/ gitignored and reproducible.
"""

import io
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import requests

from config import WMATA_API_KEY

GTFS_RAIL_STATIC_URL = "https://api.wmata.com/gtfs/rail-gtfs-static.zip"

GTFS_FILES = ("stops.txt", "routes.txt", "trips.txt", "stop_times.txt")


class WmataGtfsDownloadError(RuntimeError):
    """Raised when the WMATA GTFS static feed can't be downloaded or unzipped."""


def fetch_gtfs_static() -> dict[str, pd.DataFrame]:
    """Downloads WMATA's static Metrorail GTFS feed and loads key files into DataFrames.

    Returns a dict with keys "stops", "routes", "trips", "stop_times", each
    mapping to a pandas DataFrame loaded from the corresponding GTFS file.

    Raises:
        WmataGtfsDownloadError: if WMATA_API_KEY is missing, the download fails
            (network error, bad/expired key, non-200 response), or the
            downloaded file isn't a valid GTFS zip.
    """
    if not WMATA_API_KEY:
        raise WmataGtfsDownloadError(
            "WMATA_API_KEY is not set. Add it to .env (see .env.example)."
        )

    try:
        response = requests.get(
            GTFS_RAIL_STATIC_URL,
            headers={"api_key": WMATA_API_KEY},
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        raise WmataGtfsDownloadError(f"Failed to reach WMATA API: {e}") from e

    if response.status_code == 401 or response.status_code == 403:
        raise WmataGtfsDownloadError(
            f"WMATA API rejected the request (HTTP {response.status_code}) — "
            "check that WMATA_API_KEY is valid."
        )
    if response.status_code != 200:
        raise WmataGtfsDownloadError(
            f"WMATA API request failed with HTTP {response.status_code}."
        )

    with tempfile.TemporaryDirectory(prefix="wmata_gtfs_") as tmp_dir:
        zip_path = Path(tmp_dir) / "rail-gtfs-static.zip"
        zip_path.write_bytes(response.content)

        try:
            with zipfile.ZipFile(zip_path) as zf:
                extract_dir = Path(tmp_dir) / "extracted"
                zf.extractall(extract_dir)
        except zipfile.BadZipFile as e:
            raise WmataGtfsDownloadError(
                "Downloaded file is not a valid GTFS zip — the WMATA API key "
                "may be invalid or the response was an error page."
            ) from e

        dataframes = {}
        for filename in GTFS_FILES:
            file_path = extract_dir / filename
            if not file_path.exists():
                raise WmataGtfsDownloadError(
                    f"Expected GTFS file missing from feed: {filename}"
                )
            key = filename.removesuffix(".txt")
            dataframes[key] = pd.read_csv(file_path, dtype=str)

    return dataframes


if __name__ == "__main__":
    dataframes = fetch_gtfs_static()
    print("WMATA static GTFS feed loaded:")
    for name, df in dataframes.items():
        print(f"  {name}.txt: {len(df):,} rows, {len(df.columns)} columns")
