# Decisions

Key design decisions made during implementation, newest first. Each entry is a decision plus a one-line reason why.

- **NWS User-Agent header**: Set to the GitHub repo URL rather than a personal email, since NWS requires an identifying header and the repo URL is more appropriate for a project that may be shared/demoed publicly.
- **Project scope**: Scoped to WMATA Metrorail only, not Metrobus. WMATA publishes these as separate GTFS feeds; only the rail feed has been integrated.
- **GTFS-Realtime parsing**: Using the `gtfs-realtime-bindings` library to parse WMATA's protobuf feeds, and converting results to plain Python dicts immediately in `data/wmata_realtime.py` rather than passing protobuf objects further into the app — keeps the rest of the codebase free of protobuf-specific handling.
- **Static GTFS storage**: Using pandas DataFrames (in `data/wmata_static.py`) rather than a local SQLite DB as originally planned, since DataFrames were sufficient for Week 1 development speed. Revisit SQLite once data volume or query patterns make repeated in-memory loading impractical.
