"""Loads configuration and API keys from environment variables (.env)."""

import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
WMATA_API_KEY = os.environ.get("WMATA_API_KEY")

# api.weather.gov requires no key.
NWS_USER_AGENT = os.environ.get(
    "NWS_USER_AGENT",
    "DC-Transit-Assistant (https://github.com/ahennessy25/dc-metro-transit-assistant)",
)

GTFS_STATIC_DIR = os.environ.get("GTFS_STATIC_DIR", "data/gtfs_static")
CHROMA_DB_DIR = os.environ.get("CHROMA_DB_DIR", "chroma_db")
