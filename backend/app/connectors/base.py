"""Common connector interface.

A connector only fetches and parses a source into `RawItem`s. Normalisation, validation,
deduplication and persistence are done by the pipeline, the same way for every source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.models import Source


@dataclass
class RawItem:
    url: str | None
    title: str | None
    external_id: str | None = None
    summary_html: str | None = None
    body_html: str | None = None
    published_raw: str | None = None
    updated_raw: str | None = None
    author: str | None = None
    categories: list[str] = field(default_factory=list)
    image_url: str | None = None
    body_source: str = "feed"  # where body_html came from: "feed" | "page"
    provenance: dict = field(default_factory=dict)  # extra per-item provenance (e.g. extraction method)


@dataclass
class ConnectorResult:
    items: list[RawItem]
    not_modified: bool = False
    http_status: int | None = None
    attempts: int = 1
    etag: str | None = None
    last_modified: str | None = None
    warnings: list[str] = field(default_factory=list)
    collection_method: str | None = None  # defaults to the source's connector name
    # False for secondary collectors (e.g. backfill) so they don't overwrite the feed's ETag state.
    update_http_state: bool = True


class ConnectorError(Exception):
    def __init__(self, message: str, http_status: int | None = None, attempts: int = 1) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.attempts = attempts


class Connector(Protocol):
    name: str

    def fetch(self, source: Source) -> ConnectorResult: ...
