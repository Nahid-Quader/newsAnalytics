"""Per-source health and collection statistics, derived from `fetch_runs` and `articles`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Article, FetchRun, Source

STALE_AFTER_POLLS = 3  # a source is stale if no successful fetch for this many poll intervals
RECENT_ERRORS = 5


@dataclass
class SourceHealth:
    source_id: str
    name: str
    active: bool
    status: str  # ok | warning | stale | failing | never_run | inactive
    warnings: list[str] = field(default_factory=list)
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    last_success_at: datetime | None = None
    consecutive_failures: int = 0
    recent_errors: list[dict] = field(default_factory=list)
    runs_total: int = 0
    runs_failed: int = 0
    articles_total: int = 0
    latest_published_at: datetime | None = None
    last_new_article_at: datetime | None = None
    last_run_items_seen: int | None = None


def source_health(session: Session, source: Source, now: datetime | None = None) -> SourceHealth:
    now = now or utcnow()
    runs = list(session.scalars(
        select(FetchRun).where(FetchRun.source_id == source.id, FetchRun.status != "running")
        .order_by(FetchRun.started_at.desc(), FetchRun.id.desc())
    ))
    h = SourceHealth(source_id=source.id, name=source.name, active=source.active, status="never_run")
    h.runs_total = len(runs)
    h.runs_failed = sum(1 for r in runs if r.status == "failed")
    h.articles_total, h.latest_published_at, h.last_new_article_at = session.execute(
        select(func.count(Article.id), func.max(Article.published_at), func.max(Article.first_seen_at))
        .where(Article.source_id == source.id)
    ).one()
    # max() on SQLite returns strings/naive values; reload through the model type for consistency.
    h.latest_published_at = _as_utc(h.latest_published_at)
    h.last_new_article_at = _as_utc(h.last_new_article_at)

    h.recent_errors = [
        {"at": r.started_at, "error": r.error, "http_status": r.http_status}
        for r in runs if r.status == "failed"
    ][:RECENT_ERRORS]
    for r in runs:
        if r.status == "failed":
            h.consecutive_failures += 1
        else:
            break
    success = next((r for r in runs if r.status in ("success", "not_modified")), None)
    h.last_success_at = success.started_at if success else None

    if not source.active:
        h.status = "inactive"
        return h
    if not runs:
        return h
    last = runs[0]
    h.last_run_at, h.last_run_status = last.started_at, last.status
    last_items = next((r.items_seen for r in runs if r.status == "success"), None)
    h.last_run_items_seen = last_items

    if last.status == "failed":
        h.status = "failing"
    elif h.last_success_at and now - h.last_success_at > timedelta(minutes=source.poll_minutes * STALE_AFTER_POLLS):
        h.status = "stale"
        h.warnings.append(f"no successful fetch in over {source.poll_minutes * STALE_AFTER_POLLS} minutes")
    else:
        h.status = "ok"
    if last_items == 0:
        h.warnings.append("last successful fetch returned no items")
    if any(r.parse_failures for r in runs[:1]):
        h.warnings.append(f"{runs[0].parse_failures} item(s) rejected in the last run")
    if h.status == "ok" and h.warnings:
        h.status = "warning"
    return h


def _as_utc(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def all_source_health(session: Session) -> list[SourceHealth]:
    sources = session.scalars(select(Source).order_by(Source.id))
    return [source_health(session, s) for s in sources]
