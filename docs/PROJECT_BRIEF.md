# Project brief (original requirements)

This is the project owner's original brief, kept verbatim as the source of requirements.
Progress, decisions and next steps are in [PLAN.md](../PLAN.md).

---

# Project: Bangladesh News Intelligence Platform

## Role

Act as a senior software engineer, data engineer, and applied NLP researcher. Build a reliable, maintainable platform for collecting and analyzing publicly accessible news from Bangladesh.

Work incrementally. Prioritize data quality, verifiable results, and a working end-to-end system over architectural complexity or impressive-looking but unreliable AI features.

## 1. Product vision

Build a web platform that collects news from at least 30 Bangladeshi news publishers, primarily Bengali-language newspapers and news websites, with selected English-language sources.

The platform should eventually:

1. Collect and normalize articles from public news APIs, RSS/Atom feeds, and other permitted public sources.
2. Categorize articles automatically.
3. identify multiple articles covering the same event.
4. Discover emerging topics and changes in news coverage.
5. Compare how different publishers report and frame the same event.
6. Identify competing narratives, claims, arguments, and opposing interpretations.
7. Present findings through interactive dashboards with traceable evidence.

The long-term research objective is to understand how narratives form, differ, and evolve across the Bangladeshi news ecosystem.

**Scope for the initial version:** publicly accessible news and data APIs only. Do not collect Facebook comments, social-media posts, private content, or user data.

## 2. Development strategy

Implement the project in phases:

- Phase 1: Source discovery, ingestion, normalization, deduplication, persistence, and source-health reporting.
- Phase 2: Bengali-capable categorization, entity extraction, and article search.
- Phase 3: Event clustering and related-story timelines.
- Phase 4: Category analytics, publisher comparisons, and interactive visualizations.
- Phase 5: Narrative, framing, stance, and argument analysis.
- Phase 6: Evaluation, reliability improvements, and expansion.

**Implement Phase 1 only initially.** Create a concise roadmap for the later phases, but do not build their features until Phase 1 has been tested and accepted.

## 3. Source discovery and collection requirements

Investigate possible data sources, including:

- Official publisher APIs and documented feeds.
- RSS and Atom feeds.
- GDELT and other relevant public news datasets or APIs.
- Publisher-provided structured metadata.
- Other publicly accessible sources, where their terms and access methods permit the intended collection.

Potential publishers to investigate include Prothom Alo, Bangladesh Pratidin, Ittefaq, Kaler Kantho, Jugantor, Samakal, Janakantha, Naya Diganta, Daily Inqilab, Manab Zamin, bdnews24.com, Bangla Tribune, Jago News 24, Dhaka Post, Risingbd, The Daily Star, Dhaka Tribune, New Age, The Business Standard, and The Financial Express.

This list is a starting point, not a claim that every publisher currently offers a working feed or API.

For each source, record:

- Publisher name and homepage.
- Language and available sections.
- Access method and actual endpoint or feed URL.
- Whether the endpoint has been tested successfully.
- Available fields: title, URL, timestamp, author, summary, article body, categories, and images.
- Update frequency, known limitations, and last successful fetch.
- Applicable terms, access restrictions, attribution requirements, and collection notes.

Do not invent endpoints, assume that a publisher has an RSS feed, or report a source as working without testing it.

Prioritize documented APIs and feeds. If a source has no usable supported access method, record it as unavailable or requiring further investigation rather than silently implementing brittle scraping. Do not bypass authentication, CAPTCHAs, rate limits, paywalls, or other access controls.

## 4. Article data model

Design a normalized schema that can support later NLP and analytics.

At minimum, store:

- Stable internal article ID.
- Publisher/source ID.
- Original article URL and canonical URL, when reliably determined.
- Title and available summary.
- Article body only when collection and retention are permitted.
- Original publication timestamp and normalized UTC timestamp when known.
- First-seen and last-updated timestamps.
- Language.
- Publisher section/category.
- Author, when available.
- Content hash and deduplication metadata.
- Collection method and ingestion status.
- Relevant provenance and attribution information.

Keep missing values explicit. Do not fabricate publication dates, article text, categories, or authors.

Preserve Bengali Unicode correctly throughout ingestion, storage, search, and display. Support Bengali and English content in the same database.

Design for syndicated and near-duplicate stories. Do not simply delete all similar articles: preserve publisher-specific records and link duplicates or related versions where appropriate.

## 5. Ingestion pipeline

Implement an idempotent collection pipeline with:

1. Source configuration and validation.
2. Scheduled fetching.
3. Parsing and normalization.
4. Validation of required fields.
5. Deduplication.
6. Persistence and update handling.
7. Structured logs and error handling.
8. Retries with sensible backoff.
9. Per-source health and collection statistics.

One failed publisher must not stop the entire ingestion run.

Track attempted fetches, successful fetches, newly discovered articles, updated articles, duplicate matches, parsing failures, and the latest successful collection time.

Make ingestion safe to rerun. Use database transactions where appropriate and avoid inserting duplicate records on repeated runs.

## 6. Initial application and API

Build a minimal functional interface for Phase 1.

Required capabilities:

- View configured sources and their current status.
- See the latest successful fetch and recent errors per source.
- Browse collected articles.
- Search titles and available article text.
- Filter by publisher, language, date, and source category when available.
- View article metadata, provenance, and the original publisher link.
- View basic collection statistics and source coverage.

Create clean API endpoints, for example:

- `GET /sources`
- `GET /sources/health`
- `GET /articles`
- `GET /articles/{article_id}`
- `GET /analytics/overview`

Use pagination and appropriate filters. Keep endpoints consistent and documented.

The frontend should use React and TypeScript. The backend should use Python and FastAPI.

## 7. Engineering choices

Prefer the following initial stack:

- Python, FastAPI, Pydantic.
- PostgreSQL with a migration tool such as Alembic.
- `feedparser` and `httpx` for appropriate source connectors.
- React and TypeScript.
- Docker Compose for local development.
- pytest for automated tests.
- Structured logging and configuration through environment variables.

Keep source-specific logic behind a common connector interface so new publishers can be added without rewriting the pipeline.

Avoid unnecessary microservices. Do not introduce Kubernetes, Kafka, paid LLM APIs, or complex agent orchestration unless a demonstrated requirement justifies them.

Never commit secrets, API keys, credentials, or private configuration.

## 8. Future NLP architecture

Prepare the schema and module boundaries for future phases without implementing them yet.

Later, the platform should support:

- Hierarchical multi-label classification of Bengali and English articles.
- Named-entity and geographic extraction.
- Semantic embeddings and related-story retrieval.
- Event clustering across publishers and publication times.
- Emerging-topic detection.
- Framing, stance, claim, and argument analysis.
- Evidence-backed, time-aware visualizations.

Candidate models include BanglaBERT, XLM-R, and multilingual sentence-transformer models. Do not assume any model is best without evaluating it on representative Bangladeshi news.

Future classifications and analytical findings must retain links to their supporting articles, model versions, timestamps, and confidence or uncertainty indicators.

Do not treat sentiment as equivalent to stance. Do not infer public opinion from the number of articles, or real-world crime rates from media coverage volume.

## 9. Testing and acceptance criteria for Phase 1

Write automated tests for:

- Feed/API parsing and malformed responses.
- Bengali Unicode preservation.
- Missing or invalid timestamps.
- URL normalization and duplicate detection.
- Idempotent ingestion.
- Database persistence and updates.
- Pagination and filters.
- Connector failures and retry behavior.
- Source-health reporting.

Include sample fixtures so most tests do not require live internet access.

Before claiming Phase 1 is complete:

1. Run the automated tests and report the results.
2. Test at least a few real sources and document the evidence.
3. Demonstrate an end-to-end collection run.
4. Verify that rerunning the same ingestion does not create duplicate records.
5. Report how many sources were tested, how many worked, and which article fields were available.
6. Document known limitations and setup instructions.
7. Provide a reproducible local development environment.

Do not claim support for 30 working sources until at least 30 have actually been verified. If fewer work initially, deliver a functioning pipeline and a transparent source-coverage report.

## 10. Working process

Start by inspecting the existing repository and available development environment. If the repository is empty, propose a sensible initial structure.

Then:

1. Summarize the proposed architecture and major decisions.
2. Create a concise implementation checklist.
3. Implement Phase 1 in small, testable increments.
4. Run tests after each meaningful change.
5. Show the changed files and explain important design decisions.
6. Report errors, limitations, and unresolved questions honestly.
7. Provide exact commands to run the application locally.

Do not stop after producing an architecture document or mockup. Build a working implementation.

Do not generate fake articles or simulated collection statistics and present them as real data. Clearly label any fixtures or demo data.

Do not silently skip failures. Do not implement later phases prematurely.

## Definition of success

The first milestone is a working local application that can collect real, permitted news data from several verified sources, store it consistently, avoid duplicate ingestion, display source health, and let the user browse and search collected articles.

The architecture should make expansion to 30+ sources and later NLP-based news intelligence straightforward without requiring a complete rewrite.
