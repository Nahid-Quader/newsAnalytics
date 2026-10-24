"""API routes: sources, source health, articles, analytics overview."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ArticleOut,
    ArticleSummaryOut,
    CountBy,
    OverviewOut,
    Page,
    RunSummary,
    SourceCoverage,
    SourceHealthOut,
    SourceOut,
)
from app.db import get_session, utcnow
from app.health import all_source_health
from app.models import Article, FetchRun, Source

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/sources", response_model=list[SourceOut], tags=["sources"])
def list_sources(session: SessionDep):
    return session.scalars(select(Source).order_by(Source.id)).all()


@router.get("/sources/health", response_model=list[SourceHealthOut], tags=["sources"])
def sources_health(session: SessionDep):
    return all_source_health(session)


def _summary(article: Article, source_name: str) -> dict:
    data = {c: getattr(article, c) for c in ArticleSummaryOut.model_fields if hasattr(article, c)}
    data.update(source_name=source_name, has_body=bool(article.body))
    return data


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/articles", response_model=Page[ArticleSummaryOut], tags=["articles"])
def list_articles(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200, description="Search in title, summary and body")] = None,
    source: Annotated[list[str] | None, Query(description="Source id (repeatable)")] = None,
    language: Annotated[str | None, Query(pattern="^(bn|en)$")] = None,
    section: str | None = None,
    date_from: Annotated[date | None, Query(description="Published on or after (UTC date)")] = None,
    date_to: Annotated[date | None, Query(description="Published on or before (UTC date)")] = None,
    include_duplicates: bool = True,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Articles newest first. Articles without a known publication time sort last and are
    excluded when a date filter is given."""
    filters = []
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        filters.append(or_(Article.title.ilike(pattern, escape="\\"),
                           Article.summary.ilike(pattern, escape="\\"),
                           Article.body.ilike(pattern, escape="\\")))
    if source:
        filters.append(Article.source_id.in_(source))
    if language:
        filters.append(Article.language == language)
    if section:
        filters.append(Article.section == section)
    if date_from:
        filters.append(Article.published_at >= datetime.combine(date_from, time.min, timezone.utc))
    if date_to:
        filters.append(Article.published_at < datetime.combine(date_to + timedelta(days=1), time.min, timezone.utc))
    if not include_duplicates:
        filters.append(Article.duplicate_of_id.is_(None))

    total = session.scalar(select(func.count(Article.id)).where(*filters))
    rows = session.execute(
        select(Article, Source.name)
        .join(Source, Source.id == Article.source_id)
        .where(*filters)
        .order_by(case((Article.published_at.is_(None), 1), else_=0), Article.published_at.desc(),
                  Article.first_seen_at.desc(), Article.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {"items": [_summary(a, name) for a, name in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/articles/{article_id}", response_model=ArticleOut, tags=["articles"])
def get_article(article_id: str, session: SessionDep):
    row = session.execute(
        select(Article, Source.name).join(Source, Source.id == Article.source_id).where(Article.id == article_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="article not found")
    article, source_name = row
    data = {c: getattr(article, c) for c in ArticleOut.model_fields if hasattr(article, c)}
    data.update(source_name=source_name, has_body=bool(article.body))
    return data


@router.get("/analytics/overview", response_model=OverviewOut, tags=["analytics"])
def analytics_overview(session: SessionDep):
    now = utcnow()
    health = all_source_health(session)
    sources = session.scalars(select(Source).order_by(Source.id)).all()

    coverage = []
    for src in sources:
        total, with_body, with_pub, with_author, latest = session.execute(
            select(
                func.count(Article.id),
                func.count(Article.body),
                func.count(Article.published_at),
                func.count(Article.author),
                func.max(Article.published_at),
            ).where(Article.source_id == src.id)
        ).one()
        h = next(x for x in health if x.source_id == src.id)
        coverage.append(SourceCoverage(source_id=src.id, name=src.name, language=src.language, articles=total,
                                       with_body=with_body, with_published_at=with_pub, with_author=with_author,
                                       latest_published_at=h.latest_published_at))

    by_language = session.execute(
        select(Article.language, func.count(Article.id)).group_by(Article.language).order_by(Article.language)
    ).all()

    since = datetime.combine((now - timedelta(days=13)).date(), time.min, timezone.utc)
    days = Counter(
        d.date().isoformat()
        for d in session.scalars(select(Article.published_at).where(Article.published_at >= since))
    )
    per_day = [CountBy(key=(since.date() + timedelta(days=i)).isoformat(),
                       count=days.get((since.date() + timedelta(days=i)).isoformat(), 0)) for i in range(14)]

    runs = session.scalars(select(FetchRun).where(FetchRun.started_at >= now - timedelta(hours=24))).all()
    last_24h = RunSummary(
        runs=len(runs),
        succeeded=sum(r.status == "success" for r in runs),
        not_modified=sum(r.status == "not_modified" for r in runs),
        failed=sum(r.status == "failed" for r in runs),
        new_articles=sum(r.new_count for r in runs),
        updated_articles=sum(r.updated_count for r in runs),
    )
    status_counts = Counter(h.status for h in health)
    return OverviewOut(
        generated_at=now,
        articles_total=session.scalar(select(func.count(Article.id))),
        duplicates_linked=session.scalar(select(func.count(Article.id)).where(Article.duplicate_of_id.is_not(None))),
        sources_total=len(sources),
        sources_active=sum(s.active for s in sources),
        sources_by_status=[CountBy(key=k, count=v) for k, v in sorted(status_counts.items())],
        by_language=[CountBy(key=k, count=v) for k, v in by_language],
        per_day=per_day,
        coverage=coverage,
        last_24h=last_24h,
    )
