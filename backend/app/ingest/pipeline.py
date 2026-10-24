"""Ingestion pipeline: fetch -> parse -> normalise -> validate -> deduplicate -> persist.

Guarantees:
- Idempotent: articles are keyed on (source_id, normalised URL hash), with the feed guid as a
  fallback key, so rerunning a fetch never inserts the same article twice.
- Atomic per source run: all article writes and the run's statistics commit together.
- Isolated: one failing source is recorded as a failed run and the others still run.
- Duplicates across sources are linked (duplicate_of_id), never deleted.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors import Connector, ConnectorError, RawItem
from app.core.logging import log_event
from app.db import utcnow
from app.ingest.normalize import (
    content_hash,
    html_to_text,
    normalize_url,
    parse_timestamp,
    section_from_url,
    sha256,
    single_line,
)
from app.models import Article, FetchRun, Source

logger = logging.getLogger(__name__)

MAX_WARNINGS = 20


class ItemRejected(ValueError):
    pass


@dataclass
class RunStats:
    source_id: str
    run_id: int | None = None
    status: str = "running"
    http_status: int | None = None
    attempts: int = 0
    items_seen: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicates: int = 0
    parse_failures: int = 0
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    duration_ms: int = 0

    def add_warning(self, message: str) -> None:
        if len(self.warnings) < MAX_WARNINGS:
            self.warnings.append(message[:300])


def normalise_item(item: RawItem, source: Source, now: datetime) -> dict:
    """Turn a raw feed item into article field values. Raises ItemRejected if unusable."""
    url = (item.url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ItemRejected(f"missing or invalid url: {url[:100]!r}")
    title = single_line(item.title)
    if not title:
        raise ItemRejected(f"missing title: {url}")

    summary = single_line(item.summary_html)
    body = html_to_text(item.body_html)
    published_at, published_note = parse_timestamp(item.published_raw, now)
    url_norm = normalize_url(url)

    section = section_source = None
    if (source.config or {}).get("section_from_url"):
        section = section_from_url(url)
        section_source = "url_path" if section else None

    return {
        "url": url,
        "url_normalized": url_norm,
        "url_hash": sha256(url_norm),
        "external_id": (item.external_id or "").strip()[:500] or None,
        "title": title,
        "summary": summary,
        "body": body,
        "body_source": "feed" if body else None,
        "language": source.language,
        "section": section,
        "section_source": section_source,
        "categories": [c for c in (single_line(t) for t in item.categories) if c],
        "author": single_line(item.author),
        "image_url": item.image_url,
        "published_at_raw": item.published_raw,
        "published_at": published_at,
        "published_at_note": published_note,
        "updated_at_raw": item.updated_raw,
        "content_hash": content_hash(title, body or summary),
        "ingestion_status": "complete" if body and published_at else "partial",
    }


# Fields refreshed when an existing article's content changes.
_UPDATABLE = ("title", "summary", "body", "body_source", "section", "section_source", "categories",
              "author", "image_url", "published_at_raw", "published_at", "published_at_note",
              "updated_at_raw", "content_hash", "ingestion_status")


def _find_existing(session: Session, source_id: str, values: dict) -> Article | None:
    found = session.scalar(
        select(Article).where(Article.source_id == source_id, Article.url_hash == values["url_hash"])
    )
    if found is None and values["external_id"]:
        found = session.scalar(
            select(Article).where(Article.source_id == source_id, Article.external_id == values["external_id"])
        )
    return found


def _persist(session: Session, source: Source, run: FetchRun, prepared: list[dict], stats: RunStats,
             now: datetime) -> None:
    for values in prepared:
        existing = _find_existing(session, source.id, values)
        if existing is not None:
            existing.last_seen_at = now
            if existing.content_hash == values["content_hash"]:
                stats.unchanged += 1
                continue
            for key in _UPDATABLE:
                setattr(existing, key, values[key])
            existing.version += 1
            existing.last_updated_at = now
            prov = dict(existing.provenance or {})
            prov["updates"] = [*prov.get("updates", []), {"fetch_run_id": run.id, "at": now.isoformat()}][-20:]
            if values["url"] != existing.url:
                prov["alternate_urls"] = sorted({*prov.get("alternate_urls", []), values["url"]})
            existing.provenance = prov
            stats.updated += 1
            continue

        duplicate = session.scalar(
            select(Article).where(Article.content_hash == values["content_hash"]).order_by(Article.first_seen_at).limit(1)
        )
        article = Article(
            source_id=source.id,
            collection_method=source.connector,
            first_seen_at=now,
            last_seen_at=now,
            last_updated_at=now,
            first_fetch_run_id=run.id,
            provenance={
                "collected_via": source.connector,
                "endpoint": source.endpoint,
                "fetch_run_id": run.id,
                "fetched_at": now.isoformat(),
                "attribution": f"{source.name} ({source.homepage})",
            },
            **values,
        )
        if duplicate is not None:
            article.duplicate_of_id = duplicate.duplicate_of_id or duplicate.id
            article.duplicate_method = "exact_content_hash"
            stats.duplicates += 1
        session.add(article)
        session.flush()
        stats.new += 1


def _finish_run(run: FetchRun, stats: RunStats, started: float) -> None:
    stats.duration_ms = int((time.monotonic() - started) * 1000)
    run.finished_at = utcnow()
    run.status = stats.status
    run.http_status = stats.http_status
    run.attempts = stats.attempts
    run.items_seen = stats.items_seen
    run.new_count = stats.new
    run.updated_count = stats.updated
    run.unchanged_count = stats.unchanged
    run.duplicate_count = stats.duplicates
    run.parse_failures = stats.parse_failures
    run.error = stats.error
    run.warnings = stats.warnings
    run.duration_ms = stats.duration_ms


def run_source(session_factory: sessionmaker[Session], source_id: str, connector: Connector) -> RunStats:
    started = time.monotonic()
    stats = RunStats(source_id=source_id)
    with session_factory() as session:
        source = session.get(Source, source_id)
        if source is None:
            raise KeyError(f"unknown source: {source_id}")
        run = FetchRun(source_id=source_id, started_at=utcnow())
        session.add(run)
        session.commit()
        stats.run_id = run.id

        try:
            result = connector.fetch(source)
        except ConnectorError as exc:
            stats.status, stats.error = "failed", str(exc)
            stats.http_status, stats.attempts = exc.http_status, exc.attempts
        except Exception as exc:  # a bug in one connector must not stop the other sources
            stats.status, stats.error = "failed", f"unexpected {type(exc).__name__}: {exc}"
            logger.exception("connector_crashed", extra={"fields": {"source_id": source_id}})
        else:
            stats.http_status, stats.attempts = result.http_status, result.attempts
            for w in result.warnings:
                stats.add_warning(w)
            if result.not_modified:
                stats.status = "not_modified"
            else:
                now = utcnow()
                stats.items_seen = len(result.items)
                prepared: dict[str, dict] = {}
                for item in result.items:
                    try:
                        values = normalise_item(item, source, now)
                    except ItemRejected as exc:
                        stats.parse_failures += 1
                        stats.add_warning(f"item rejected: {exc}")
                        continue
                    if values["url_hash"] in prepared:
                        stats.add_warning(f"same URL twice in feed: {values['url']}")
                        continue
                    prepared[values["url_hash"]] = values
                if not result.items:
                    stats.add_warning("feed returned no items")
                try:
                    _persist(session, source, run, list(prepared.values()), stats, now)
                    source.http_etag = result.etag
                    source.http_last_modified = result.last_modified
                    stats.status = "success"
                except Exception as exc:
                    session.rollback()
                    run = session.get(FetchRun, stats.run_id)
                    stats.new = stats.updated = stats.unchanged = stats.duplicates = 0
                    stats.status, stats.error = "failed", f"persistence error {type(exc).__name__}: {exc}"
                    logger.exception("persist_failed", extra={"fields": {"source_id": source_id}})

        _finish_run(run, stats, started)
        session.commit()

    level = logging.WARNING if stats.status == "failed" else logging.INFO
    log_event(logger, "source_run_finished", level, **{k: v for k, v in asdict(stats).items() if k != "warnings"},
              warning_count=len(stats.warnings))
    return stats


def run_all(session_factory: sessionmaker[Session], connectors: dict[str, Connector],
            source_ids: list[str] | None = None) -> list[RunStats]:
    with session_factory() as session:
        query = select(Source).where(Source.active.is_(True)).order_by(Source.id)
        sources = list(session.scalars(query))
    if source_ids:
        wanted = set(source_ids)
        unknown = wanted - {s.id for s in sources}
        if unknown:
            raise KeyError(f"unknown or inactive source(s): {sorted(unknown)}")
        sources = [s for s in sources if s.id in wanted]

    results = []
    for source in sources:
        connector = connectors.get(source.connector)
        if connector is None:
            log_event(logger, "no_connector", logging.ERROR, source_id=source.id, connector=source.connector)
            continue
        results.append(run_source(session_factory, source.id, connector))
    return results
