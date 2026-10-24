# newsAnalytics: Bangladesh News Intelligence Platform

Collects news from Bangladeshi publishers and (in later phases) analyses how coverage and narratives
differ across outlets. **Current state: Phase 1 backbone; project paused (see PLAN.md).** Ingestion, storage, deduplication, source
health, API and a browsing UI, running on 4 verified sources.

- Plan, status and decisions: [PLAN.md](PLAN.md)
- Original requirements: [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md)
- Source research and evidence: [research/SOURCES.md](research/SOURCES.md)

## Sources

| Source | Language | Access | Full text |
|---|---|---|---|
| Prothom Alo | Bengali | RSS | in feed |
| bdnews24 Bangla | Bengali | RSS | in feed |
| bdnews24.com | English | RSS | in feed |
| Prothom Alo English | English | RSS | in feed, but the feed holds only 0–2 items |

Configured in [config/sources.yaml](config/sources.yaml). Adding another RSS source needs only a new
entry there, after verifying it (see `research/`).

## Layout

```
backend/            Python package `app` (FastAPI, SQLAlchemy, Alembic, pytest)
  app/connectors/   connector interface + RSS connector
  app/ingest/       normalisation, pipeline, scheduler, CLI
  app/api/          REST API
  migrations/       Alembic migrations
  tests/            88 tests; fixtures/ holds real feed snapshots for offline tests
frontend/           React + TypeScript (Vite)
config/sources.yaml source configuration
research/           source discovery scripts and findings
docker-compose.yml  PostgreSQL + API + scheduled worker (for a machine with Docker)
```

## Run it locally (Windows, no Docker, SQLite)

Requires Python 3.11+ and Node 20+. Commands are for PowerShell from the repo root.

```powershell
# 1. Backend setup (once)
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
$env:PYTHONIOENCODING = "utf-8"
cd backend
..\.venv\Scripts\alembic.exe upgrade head          # creates data/news.db
..\.venv\Scripts\python.exe -m app.ingest sync-sources

# 2. Collect articles
..\.venv\Scripts\python.exe -m app.ingest run       # one run over all sources
..\.venv\Scripts\python.exe -m app.ingest schedule  # or: keep collecting on each source's interval
..\.venv\Scripts\python.exe -m app.ingest health    # per-source health as JSON
..\.venv\Scripts\python.exe -m app.ingest backfill --days 3 --dry-run  # past days: list what would be fetched
..\.venv\Scripts\python.exe -m app.ingest backfill --days 3            # fetch them (sitemaps + article pages)

# 3. API (http://localhost:8000/docs)
..\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --port 8000

# 4. Frontend (second terminal; http://localhost:5173)
cd frontend
npm install
npm run dev
```

The scheduler, API and frontend run as separate processes. Set `LOG_JSON=false` for readable logs.

## Run with PostgreSQL (Docker)

```bash
docker compose up --build      # db + api (:8000) + worker (scheduled collection)
cd frontend && npm install && npm run dev
```

The compose file has not been tested yet: this was developed on a machine without Docker.

## Tests

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest           # offline, uses saved fixtures
```

They cover feed parsing and malformed feeds, Bengali Unicode (NFC, ZWJ/ZWNJ kept), missing, naive and
future timestamps, URL normalisation, rerunning without duplicates, content updates, cross-source
duplicate linking, retries and backoff (403 never retried), conditional GET, failure isolation, source
health states, API pagination, filters and search, migrations and the scheduler.

## API

| Endpoint | Purpose |
|---|---|
| `GET /sources` | configured sources |
| `GET /sources/health` | status (`ok`, `warning`, `stale`, `failing`, `never_run`, `inactive`), last success, recent errors |
| `GET /articles` | `q`, `source` (repeatable), `language`, `section`, `date_from`, `date_to`, `include_duplicates`, `page`, `page_size` (≤100) |
| `GET /articles/{id}` | full record with provenance |
| `GET /analytics/overview` | totals, coverage per source, per-day counts, last-24 h run stats |

## Design notes

- **Idempotent:** articles are unique on (source, normalised-URL hash), with the feed GUID as a
  fallback. A changed title or body updates the row (`version` + 1), and rows are never duplicated.
- **Duplicates across publishers** with identical text are linked via `duplicate_of_id`, never deleted.
- **Timestamps:** the raw value is always stored. A UTC value is stored only if the source gave a
  timezone; otherwise it's NULL with a note. Times are shown in Bangladesh time (BDT, UTC+6) in the UI.
- **Politeness:** identifying User-Agent, delay between requests per host, retries only on
  timeouts, 429 and 5xx, conditional GET (most reruns get HTTP 304).
- **Search:** case-insensitive substring match (`ILIKE`), with trigram indexes on PostgreSQL.
  PostgreSQL has no Bengali stemmer, so morphological variants aren't matched yet (Phase 2).
- **Full text** is stored for private analysis. Link to the publisher when sharing anything.

## Known limitations

- Only 4 sources (3 that deliver steadily). Prothom Alo English often has an empty feed, and it shows as
  `warning` in source health.
- Feeds only expose recent items. Past days come from the `backfill` command (daily sitemaps +
  article pages); it's built and tested but hasn't been run live yet. bdnews24 Bangla's daily
  sitemaps are capped at 100 links, so some of its articles may be missed.
- A few items are videos with only a summary (`ingestion_status = partial`).
- Section comes from the URL path (e.g. `/sport/…`). It's the publisher's own structure, not a classification.
- SQLite allows one writer: run one scheduler process at a time. Use PostgreSQL for anything bigger.
- The frontend has no automated tests yet (type-checked by `npm run build`).
