"""API response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    homepage: str
    language: str
    connector: str
    endpoint: str
    poll_minutes: int
    active: bool
    full_text_in_feed: bool
    notes: str | None
    terms_notes: str | None


class RecentError(BaseModel):
    at: datetime
    error: str | None
    http_status: int | None


class SourceHealthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: str
    name: str
    active: bool
    status: str
    warnings: list[str]
    last_run_at: datetime | None
    last_run_status: str | None
    last_success_at: datetime | None
    consecutive_failures: int
    recent_errors: list[RecentError]
    runs_total: int
    runs_failed: int
    articles_total: int
    latest_published_at: datetime | None
    last_new_article_at: datetime | None
    last_run_items_seen: int | None


class ArticleSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    source_name: str
    url: str
    title: str
    summary: str | None
    language: str
    section: str | None
    author: str | None
    published_at: datetime | None
    first_seen_at: datetime
    has_body: bool
    duplicate_of_id: str | None


class ArticleOut(ArticleSummaryOut):
    external_id: str | None
    url_normalized: str
    canonical_url: str | None
    body: str | None
    body_source: str | None
    section_source: str | None
    categories: list[str]
    image_url: str | None
    published_at_raw: str | None
    published_at_note: str | None
    updated_at_raw: str | None
    last_seen_at: datetime
    last_updated_at: datetime
    version: int
    content_hash: str
    duplicate_method: str | None
    collection_method: str
    ingestion_status: str
    provenance: dict


class CountBy(BaseModel):
    key: str
    count: int


class SourceCoverage(BaseModel):
    source_id: str
    name: str
    language: str
    articles: int
    with_body: int
    with_published_at: int
    with_author: int
    latest_published_at: datetime | None


class RunSummary(BaseModel):
    runs: int
    succeeded: int
    not_modified: int
    failed: int
    new_articles: int
    updated_articles: int


class OverviewOut(BaseModel):
    generated_at: datetime
    articles_total: int
    duplicates_linked: int
    sources_total: int
    sources_active: int
    sources_by_status: list[CountBy]
    by_language: list[CountBy]
    per_day: list[CountBy]  # by publication date (UTC), last 14 days
    coverage: list[SourceCoverage]
    last_24h: RunSummary
