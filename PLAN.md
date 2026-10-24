# Project plan: Bangladesh News Intelligence Platform

Living plan for this repository. Requirements are in
[docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md); source research is in
[research/SOURCES.md](research/SOURCES.md). **Update the Status section and checkboxes whenever
you finish a piece of work.**

## Status

Last updated: 2026-10-23

| Item | State |
|---|---|
| Source research (first pass) | Done: 44 candidates probed |
| Phase 1 primary sources | 4 verified: [config/sources.yaml](config/sources.yaml) |
| Phase 1 code | Backbone done (steps 1.1–1.9); 73 tests passing; live run verified |
| Data so far | 135 real articles from 3 sources (Prothom Alo EN feed was empty), local SQLite |
| Current task | Owner review of Phase 1 (step 1.10 acceptance), then Phase 1b on the personal machine |

## Goal

Collect news from Bangladeshi publishers (mainly Bengali, some English) and analyse how
narratives form, differ and evolve across outlets: categories, event clusters, emerging topics,
publisher comparisons and framing, with every finding traceable to the source articles.

## Non-negotiable rules (from the brief)

- Public news sources only. No social media, comments, private content or user data.
- Never invent endpoints, articles, dates, authors or statistics. Label fixtures as fixtures.
- Never bypass authentication, CAPTCHAs, Cloudflare challenges, rate limits or paywalls.
  A 403 means stop and record it.
- Respect robots.txt. Use the identifying User-Agent
  `newsAnalytics/<version> (+https://github.com/Nahid-Quader/newsAnalytics)`.
- Keep missing values explicit (NULL). Don't fill them in with guesses.
- Preserve Bengali Unicode end to end (normalise to NFC).
- Don't build a phase until the previous one is tested and accepted by the owner.
- Never commit secrets. Configuration comes from environment variables or `.env` (gitignored).
- Don't add Kubernetes, Kafka, paid LLM APIs or agent orchestration without a demonstrated need.

## Decisions made

| # | Decision | Reason |
|---|---|---|
| D1 | Phase 1 primary sources are those that are **fresh (≤ 24 h) and carry full article text in the feed** | Avoids page fetching for v1; NLP phases need body text |
| D2 | Primary sources: Prothom Alo BN, Prothom Alo EN, bdnews24 BN, bdnews24 EN | Only ones meeting D1 (see SOURCES.md) |
| D3 | **Page fetching is deferred.** It will be added later from the owner's personal machine, not the work laptop | Requests from the company network/IP aren't appropriate for a personal project |
| D4 | GDELT is a discovery/cross-check layer, not a primary source | Metadata only, uneven coverage, 1 request / 5 s limit |
| D5 | Cloudflare-blocked sources aren't pursued. Re-test from a non-corporate network later | Bypassing challenges is ruled out |
| D6 | Full text is stored privately. The UI and any export show headline, short excerpt and link to the original | Republishing full text is the main copyright risk |
| D7 | SQLite on the work laptop, PostgreSQL via Docker on the personal machine; same code and migrations | No Postgres server or Docker on the laptop |
| D8 | `section` comes from the article URL's first path segment (`section_source = url_path`) | Feeds carry keyword tags, not sections; URL paths are the publisher's own structure |
| D9 | Search is `ILIKE` substring (+ `pg_trgm` index on PostgreSQL) | No Bengali stemmer in PostgreSQL; better search is Phase 2 |

## Environment notes

- Current machine: Windows 11 work laptop, Python 3.12.1 in `.venv`, **no Docker**.
- The owner will move to a personal machine later. Docker and page fetching are expected there.
- Set `PYTHONIOENCODING=utf-8` when printing Bengali in the Windows console.
- Git identity is repo-local (`git config user.*`). Never change global git config.
- Until Docker is available, develop against a local PostgreSQL install. Use SQLite only for
  unit tests that don't depend on Postgres-specific features (full-text search, `pg_trgm`).

## Architecture (Phase 1)

Single Python package plus a React app; no microservices. **Implemented as described below.**
Run instructions and design notes are in [README.md](README.md).

Extension points for later work:
- New connector type: add `backend/app/connectors/<name>.py` implementing `fetch(source) -> ConnectorResult`,
  register it in `connectors/__init__.py`, and allow the value in `SourceConfig.connector` (`app/sources.py`).
- Page fetching (Phase 1b): set `body_source='page'`; the pipeline and schema already support it.
- Later-phase tables reference `articles.id`; add them via a new Alembic migration.

```
newsAnalytics/
  backend/
    app/
      api/           FastAPI routers: sources, articles, analytics
      connectors/    base.py (Connector interface), rss.py; later: news_sitemap.py, page_fetch.py, gdelt.py
      ingest/        pipeline.py (fetch -> parse -> normalise -> validate -> dedup -> persist), scheduler.py
      models/        SQLAlchemy models
      schemas/       Pydantic API schemas
      core/          config (env vars), logging (structured JSON), http client (retry, rate limit)
    migrations/      Alembic
    tests/           pytest; fixtures/ holds saved real feed samples (labelled as fixtures)
  frontend/          React + TypeScript (Vite)
  config/sources.yaml
  research/          probe scripts and findings (not production code)
  docs/
  docker-compose.yml (when Docker is available)
```

**Connector interface:** `fetch(source) -> list[RawItem]`; the pipeline handles everything else.
New publishers are added via `config/sources.yaml`, not code, unless a new connector type is needed.

**Data model (core tables):**
- `sources`: id, name, homepage, language, connector type, endpoint, config, terms notes, active flag.
- `articles`: id (UUID), source_id, url, canonical_url, url_hash, title, summary, body,
  body_source (`feed` | `page` | NULL), language, section, author, published_at_raw,
  published_at_utc, first_seen_at, last_updated_at, content_hash, duplicate_of (nullable FK),
  collection_method, provenance (JSON).
- `fetch_runs`: per-source run log with attempted, succeeded, new, updated, duplicates,
  parse_failures, error, duration, started_at.
- Constraint: unique (source_id, url_hash). Updates bump `last_updated_at` when `content_hash` changes.
- Reserved for later phases (don't create yet): `article_entities`, `article_embeddings`,
  `event_clusters`, `classifications` (each with model_version, created_at, confidence).

**Search:** PostgreSQL full-text search with the `simple` config (no Bengali stemmer exists) plus
`pg_trgm` for substring and fuzzy matching.

**Timestamps:** store the raw string. Convert to UTC only when a timezone is present. If it's
missing, keep `published_at_utc` NULL and record why in provenance. Don't assume UTC+6 silently.

## Phases

### Phase 1: Ingestion, storage, source health, basic UI (current)

Steps, each one small and tested:

- [x] **1.1 Skeleton:** backend package, `pyproject.toml`/requirements, config from env,
      structured logging, pytest set up, `.env.example`.
- [x] **1.2 Data model:** SQLAlchemy models + first Alembic migration; DB connection via `DATABASE_URL`.
- [x] **1.3 HTTP client:** shared httpx client with User-Agent, timeouts, retry with exponential
      backoff (on 429/5xx/timeouts only), per-host rate limit, conditional GET (ETag/Last-Modified).
- [x] **1.4 RSS connector:** parse with feedparser. Take body from the longest of `content[*]`
      and `summary` and strip HTML (Prothom Alo puts the body in a later `content` entry). NFC normalise.
- [x] **1.5 Normalisation and validation:** URL normalisation (scheme, host case, tracking params,
      trailing slash), required fields (title + url), timestamp parsing rules above.
- [x] **1.6 Dedup and persistence:** upsert on (source_id, url_hash) inside a transaction; content-hash
      change means update; cross-source exact-text duplicates linked via `duplicate_of`, never deleted.
- [x] **1.7 Pipeline and scheduler:** run all active sources, isolate failures per source, write
      `fetch_runs`; CLI `python -m app.ingest run [--source ID]`; scheduler (APScheduler) with
      per-source interval (Prothom Alo EN needs a short one, ~10 min, since its feed holds 1–2 items).
- [x] **1.8 API:** `GET /sources`, `/sources/health`, `/articles` (pagination, filters: source,
      language, date range, section, q), `/articles/{id}`, `/analytics/overview`. OpenAPI docs.
- [x] **1.9 Frontend:** sources and health page, article list with search and filters, article detail
      with provenance and original link, overview stats.
- [ ] **1.10 Acceptance:** real collection run on the 4 sources, rerun to show no duplicates,
      test report, source-coverage report, README with exact setup commands, known limitations.
      Done 2026-10-23 except owner sign-off: run 1 gave 135 new articles (bdnews24 BN 50, EN 50,
      Prothom Alo BN 35, Prothom Alo EN 0 because the feed was empty); run 2 gave 0 new, 135 total, 3 sources
      answered HTTP 304. Field coverage: body 133/135 (2 bdnews24 video items), date 135/135,
      author 135/135. Still open: owner review of the UI; docker-compose untested; a multi-day
      scheduled run to measure feed turnover (especially Prothom Alo EN).

Tests required (see brief §9): parsing and malformed feeds, Bengali Unicode, bad or missing timestamps,
URL normalisation and dedup, idempotent reruns, persistence and updates, pagination and filters,
connector failure and retry, health reporting. Use saved fixtures; live tests marked `@pytest.mark.live`.

### Phase 1b: Source expansion (on the owner's personal machine)

Do this **after** Phase 1 works, and **only on the personal machine** (decision D3).

- [ ] **Page-fetch connector** (`page_fetch.py`): for each new feed item, fetch the article page
      (only links from the publisher's own feed, no crawling) and extract the body via JSON-LD
      `articleBody`, falling back to `trafilatura`. Rules:
      robots.txt must allow it; ≥ 5 s between requests per host; stop on 403/429 and back off;
      record `body_source='page'`; keep full text private (D6).
- [ ] Add and verify these 6 sources (fresh feed, excerpt only, article pages fetchable on 2026-10-23):

  | Source | Lang | Feed |
  |---|---|---|
  | Janakantha | bn | https://www.dailyjanakantha.com/rss/rss.xml |
  | Amar Desh | bn | https://www.dailyamardesh.com/feed |
  | Ajker Patrika | bn | https://www.ajkerpatrika.com/feed |
  | Barta24 | bn | https://barta24.com/rss/rss.xml |
  | Channel i Online | bn | https://www.channelionline.com/rss.xml |
  | NTV | bn | https://www.ntvbd.com/rss.xml (newest item was 31 h old; check freshness) |

  For each: check terms of use, confirm extraction on ≥ 5 real articles (body length vs. page),
  record results in SOURCES.md, then mark it `verified` in `config/sources.yaml`.
- [ ] **Excerpt-only sources** (title + summary, no body; page blocked): Ittefaq, Bangla Tribune,
      Jago News 24, Dhaka Post, Dhaka Tribune EN/BN, Desh Rupantor. These are useful for event
      clustering, not framing analysis. Their robots.txt returned 403, so confirm terms first.
- [ ] **News-sitemap connector** for Daily Star EN, TBS EN/BN, Jugantor, Bonik Barta, Bhorer Kagoj,
      Dainik Bangla (verify freshness first).
- [ ] Re-run `research/probe_sources.py` from the personal network; re-check the 14
      Cloudflare-blocked sources and Naya Diganta (TLS hostname mismatch).
- [ ] Optional GDELT connector for discovery and cross-checks.

Target after 1b: ~10 publishers with full text, ~17+ with at least headline + excerpt.

### Phase 2: Enrichment (categorisation, entities, search)

- Category classification (multi-label, BN + EN). Start with publisher section labels as weak
  labels; map them to a shared taxonomy; train or fine-tune and evaluate (BanglaBERT, XLM-R candidates).
- Named entities and places (people, organisations, Bangladeshi districts/upazilas), with a
  gazetteer for geography.
- Better search (entity filters, cross-language search via embeddings).
- Every output stores model_version, created_at, confidence.
- Start a small hand-labelled evaluation set now: ~300 articles with category + entities.

### Phase 3: Event clustering and timelines

- **Embeddings:** multilingual sentence model so BN and EN articles about the same event align.
  Compare multilingual-E5, LaBSE, paraphrase-multilingual-mpnet on labelled pairs before choosing.
- **Event clustering (incremental):** a new article is compared with active clusters (last ~72 h)
  by centroid similarity plus entity overlap; it joins the best match above a threshold, otherwise
  starts a new cluster. Clusters go dormant when inactive. Periodic merge/split passes. Stable cluster IDs.
- **Topic discovery** (separate from events): BERTopic with a Bengali stopword list, for emerging themes.
- **Evaluation:** a few hundred hand-labelled "same event / different event" pairs; report
  precision/recall and tune the threshold.

### Phase 4: Analytics and visualisation

Priority views:
1. **Event detail:** articles side by side by publisher (headline, time, excerpt, link). The core evidence view.
2. **Event timeline:** one row per event, dots per article coloured by publisher.
3. **Publisher × topic heatmap:** share of each outlet's coverage per topic.
4. **Topic volume over time:** stacked area chart, for emerging topics.
5. 2D UMAP map of clusters: internal exploration only (distances are misleading).

Caveat to show in the UI: coverage volume isn't public opinion or real-world incidence.

### Phase 5: Narrative, framing, stance, argument analysis

Research-grade; treat it as experiments with evaluation, not features with deadlines.
- Within an event cluster: claim extraction, who is quoted, framing categories, stance towards
  named actors (stance isn't sentiment).
- Annotation guidelines + inter-annotator agreement before trusting any model.
- Every finding links to supporting article passages, model version and confidence.

### Phase 6: Evaluation, reliability, expansion

- Monitoring of source health over time; alert on silent feed death (like the stale Daily Star/TBS feeds).
- Historical backfill via news sitemaps where permitted.
- Grow to 30+ verified sources; publisher outreach for access where blocked.

## Open questions for the owner

1. Is Postgres installable on the work laptop, or should Phase 1 wait for the personal machine/Docker?
2. Publishing plans: will any dashboard or dataset be public? (Affects decision D6.)
3. Which taxonomy for categories in Phase 2? (Proposal: derive from publisher sections.)

## How to work on this project (for agents)

1. Read this file, then [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) and
   [research/SOURCES.md](research/SOURCES.md).
2. Pick the first unchecked step of the current phase. Keep changes small; write tests with the code.
3. Run `pytest` before committing. Report failures honestly.
4. Tick the checkbox, update **Status**, and add any new decision to **Decisions made**.
5. Commit with a clear message; don't push or commit without the owner's go-ahead in your session.
