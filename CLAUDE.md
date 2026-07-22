# CLAUDE.md

Project Intent

This is a conversational assistant for DC-area transit (WMATA Metrorail/Metrobus), built as a 3-week hackathon project for Coding It Forward. The core architecture is hybrid tool-calling + RAG — not pure RAG. This distinction matters and should guide implementation choices:

Tool-calling (live, structured data): schedules, real-time arrivals, service alerts, and weather are all time-sensitive. These are answered by Claude calling a live API function at query time, NOT by retrieving from a pre-embedded vector store (which would go stale immediately). Use Claude's tool-use API for these.
RAG (descriptive, semi-static text): station accessibility notes, historical alert descriptions, and trip-planning FAQ content are better suited to semantic retrieval, since they're unstructured and don't change minute-to-minute. This is what ChromaDB (chroma_db/, gitignored) is for.
Do not default to "put everything in the vector store" — if a task involves current/live information, it should be a tool call, not a retrieval.

Data sources

WMATA static GTFS — schedules, routes, stops (the DC-Metro-GTFS-Files/ currently in the repo; going forward, feeds should be fetched via a script into the gitignored data/ path, not committed directly)
WMATA GTFS-Realtime — live vehicle positions, trip updates, service alerts (requires the free WMATA API key, stored in .env)
National Weather Service API (api.weather.gov) — DC-area weather, no key required
Anthropic API — powers the chatbot's own conversational/tool-calling logic (separate key from Claude Code's own auth, stored in .env as ANTHROPIC_API_KEY)
Planned tools for the agent

get_scheduled_times(route, stop) — static schedule lookup
get_real_time_arrivals(station) — live GTFS-RT predictions
get_service_alerts(line=None) — active disruptions
get_weather(when="now") — current/forecast conditions
search_station_info(query) — RAG retrieval over the ChromaDB index
Team conventions

Two or more contributors on this project — work on feature branches per area (e.g. data-pipeline, agent-tools, ui-eval), merge to main via PR even though it's a small team, so each person's contribution stays reviewable and attributable.
Prefer small, single-purpose commits over large batched ones.
When making a non-obvious design decision (e.g., chunking strategy, tool-routing logic), briefly explain the reasoning before implementing — this project doubles as a learning exercise, and both contributors need to be able to explain how it works, not just that it works.
When making a non-trivial design decision during implementation (e.g., choice of library, data structure, architecture pattern, or a deviation from the original plan), append a short entry to DECISIONS.md — decision plus one-line reasoning — as part of that same change, not as a separate follow-up step.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

This repository is a very early-stage scaffold for a **DC Metro (WMATA) transit assistant**. As of now there is
no application code committed — the repo contains only a `.gitignore` and (locally, untracked) a raw WMATA Rail
GTFS Static data dump in `DC-Metro-GTFS-Files/`. There is no build system, package manifest, README, or test
suite yet. When adding the first real code, set up the language/framework tooling (package manifest, linter,
test runner) as part of that work rather than assuming any convention below already exists.

The `.gitignore` telegraphs the intended architecture even though the code isn't written:
- `chroma_db/` is ignored — the assistant is expected to use ChromaDB as a vector store (likely RAG over transit
  data/schedules).
- `DC-Metro-GTFS-Files/` and `*.zip` are ignored — GTFS data is meant to be fetched/downloaded via a script, not
  committed to git. If you write that fetch script, have it pull WMATA's GTFS static feed and unzip it to this
  path.
- `.env` / `*.env.local` are ignored — expect API keys (e.g. an LLM provider, possibly a WMATA API key) to be
  configured via environment variables.
- Python artifacts (`venv/`, `__pycache__/`, `*.egg-info/`) are ignored, and a `venv/` already exists locally, so
  this project is Python-based.

## GTFS data (`DC-Metro-GTFS-Files/`)

This is WMATA's Rail GTFS Static feed (not committed to git; regenerate/download separately). Any transit-logic
code will need to join across these files. Key shapes, from `feed_info.txt`:

| File | Rows | Purpose |
|---|---|---|
| `agency.txt` | 1 | Single agency: WMATA |
| `routes.txt` | 6 | The 6 Metrorail lines (`route_id` = RED/BLUE/ORANGE/etc., with `route_color`) |
| `stops.txt` | ~2.1k | Stations and platforms; `location_type` distinguishes parent stations from child stops/platforms via `parent_station` |
| `trips.txt` | ~18k | One row per scheduled train run, linked to `route_id`, `service_id` (calendar), and `shape_id` |
| `stop_times.txt` | ~386k | The large one — every stop a trip makes, with `arrival_time`/`departure_time` and `stop_sequence` |
| `shapes.txt` | ~186k | Lat/lon polylines per `shape_id`, for drawing route paths |
| `calendar_dates.txt` | ~338 | Service-date exceptions (this feed uses exception-based calendars, not `calendar.txt`) |
| `pathways.txt` | ~2.9k | In-station walking paths (escalators, stairs, entrances) between stops, with accessibility metadata (`stair_count`, `max_slope`, `wheelchair_boarding`) |
| `levels.txt` | ~277 | Station levels (street/mezzanine/platform) that pathways connect between |
| `feed_info.txt` | 1 | Feed validity window (`feed_start_date`/`feed_end_date`) — check this before trusting schedule data as current |

Notes when writing code against this data:
- IDs are strings even when numeric-looking (e.g. `agency_id: "1"`) — don't coerce them to ints.
- Dates use `YYYYMMDD` integers/strings (`calendar_dates.txt`, `feed_info.txt`); times in `stop_times.txt` are
  `HH:MM:SS` and can exceed `24:00:00` for post-midnight service on the same service day.
- `stop_times.txt` and `shapes.txt` are large enough that naive full loads (e.g. `pandas.read_csv` without
  filtering) will be slow — prefer streaming/chunked reads or loading into a real DB/index for repeated queries.

## Working in this repo

Since there's no established structure yet:
- Check whether a package manifest (`requirements.txt`/`pyproject.toml`) or app entry point exists before assuming
  one — it may have been added after this file was last updated.
- Keep the GTFS fetch/ingest step reproducible and scripted (not manual downloads) so `DC-Metro-GTFS-Files/`
  can stay gitignored.
