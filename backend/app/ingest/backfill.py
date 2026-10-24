"""Backfill: collect articles published on past days, one run per (source, day).

Each day is committed separately, so an interrupted backfill keeps what it collected and a
rerun skips articles that are already stored.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.base import ConnectorError
from app.connectors.sitemap import BD_TZ, SitemapBackfillConnector
from app.core.http import PoliteHttpClient
from app.ingest.pipeline import run_source
from app.models import Article, Source


def backfill_days(days: int, today: date | None = None) -> list[date]:
    """The last `days` Bangladesh calendar days, newest first, including today."""
    today = today or datetime.now(BD_TZ).date()
    return [today - timedelta(days=i) for i in range(days)]


def run_backfill(session_factory: sessionmaker[Session], http: PoliteHttpClient, days: int,
                 source_ids: list[str] | None = None, today: date | None = None,
                 max_pages: int | None = None, dry_run: bool = False) -> list[dict]:
    with session_factory() as session:
        sources = [s for s in session.scalars(select(Source).where(Source.active.is_(True)).order_by(Source.id))
                   if (s.config or {}).get("backfill")]
    if source_ids:
        unknown = set(source_ids) - {s.id for s in sources}
        if unknown:
            raise KeyError(f"unknown, inactive or not backfill-capable source(s): {sorted(unknown)}")
        sources = [s for s in sources if s.id in source_ids]

    results = []
    for src in sources:
        news_cache: dict = {}
        for day in backfill_days(days, today):
            with session_factory() as session:
                known = set(session.scalars(select(Article.url_hash).where(Article.source_id == src.id)))
                source = session.get(Source, src.id)
            connector = SitemapBackfillConnector(http, day, known, news_cache, max_pages)
            if dry_run:
                try:
                    candidates, warnings = connector.list_candidates(source)
                    results.append({"source_id": src.id, "day": day.isoformat(), "to_fetch": len(candidates),
                                    "warnings": warnings})
                except ConnectorError as exc:
                    results.append({"source_id": src.id, "day": day.isoformat(), "error": str(exc)})
                continue
            stats = run_source(session_factory, src.id, connector, kind="backfill", target_date=day.isoformat())
            results.append({"day": day.isoformat(), **asdict(stats)})
            if connector.blocked:
                break  # stop this source entirely; continue with the next one
    return results
