"""Database models.

Missing values stay NULL: nothing here is filled in with guesses. Tables for later phases
(entities, embeddings, event clusters, classifications) are deliberately not created yet;
each will reference `articles.id` and carry model_version, created_at and confidence.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime, utcnow


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # stable slug, e.g. "prothomalo-bn"
    name: Mapped[str] = mapped_column(String(200))
    homepage: Mapped[str] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(8))
    connector: Mapped[str] = mapped_column(String(32))
    endpoint: Mapped[str] = mapped_column(String(1000))
    poll_minutes: Mapped[int] = mapped_column(Integer, default=30)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    full_text_in_feed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    terms_notes: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # connector-specific options

    # Conditional GET state from the last successful fetch.
    http_etag: Mapped[str | None] = mapped_column(String(500))
    http_last_modified: Mapped[str | None] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    runs: Mapped[list[FetchRun]] = relationship(back_populates="source")


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("source_id", "url_hash", name="uq_articles_source_url"),
        Index("ix_articles_source_external", "source_id", "external_id"),
        Index("ix_articles_published_at", "published_at"),
        Index("ix_articles_first_seen_at", "first_seen_at"),
        Index("ix_articles_content_hash", "content_hash"),
        Index("ix_articles_language", "language"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str | None] = mapped_column(String(500))  # feed guid

    url: Mapped[str] = mapped_column(String(2000))  # as given by the publisher
    url_normalized: Mapped[str] = mapped_column(String(2000))
    url_hash: Mapped[str] = mapped_column(String(64))
    canonical_url: Mapped[str | None] = mapped_column(String(2000))  # only when reliably determined

    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)  # plain text, paragraphs separated by blank lines
    body_source: Mapped[str | None] = mapped_column(String(16))  # "feed" | "page" | NULL

    language: Mapped[str] = mapped_column(String(8))
    section: Mapped[str | None] = mapped_column(String(200))
    section_source: Mapped[str | None] = mapped_column(String(32))  # how section was determined
    categories: Mapped[list] = mapped_column(JSON, default=list)  # publisher tags, as given
    author: Mapped[str | None] = mapped_column(String(500))
    image_url: Mapped[str | None] = mapped_column(String(2000))

    published_at_raw: Mapped[str | None] = mapped_column(String(100))
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # NULL if no reliable timezone
    published_at_note: Mapped[str | None] = mapped_column(String(200))
    updated_at_raw: Mapped[str | None] = mapped_column(String(100))

    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)  # bumped when content changes

    content_hash: Mapped[str] = mapped_column(String(64))
    duplicate_of_id: Mapped[str | None] = mapped_column(ForeignKey("articles.id"))
    duplicate_method: Mapped[str | None] = mapped_column(String(32))

    collection_method: Mapped[str] = mapped_column(String(32))
    ingestion_status: Mapped[str] = mapped_column(String(16))  # "complete" | "partial"
    first_fetch_run_id: Mapped[int | None] = mapped_column(ForeignKey("fetch_runs.id"))
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)

    source: Mapped[Source] = relationship()


class FetchRun(Base):
    __tablename__ = "fetch_runs"
    __table_args__ = (Index("ix_fetch_runs_source_started", "source_id", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    kind: Mapped[str] = mapped_column(String(16), default="feed", server_default="feed")  # feed | backfill
    target_date: Mapped[str | None] = mapped_column(String(10))  # backfill: publication day (YYYY-MM-DD)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|success|not_modified|failed
    http_status: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    items_seen: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    parse_failures: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    source: Mapped[Source] = relationship(back_populates="runs")
