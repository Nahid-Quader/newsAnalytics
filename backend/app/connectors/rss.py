"""RSS / Atom connector."""

from __future__ import annotations

import feedparser

from app.connectors.base import ConnectorError, ConnectorResult, RawItem
from app.core.http import FetchError, PoliteHttpClient
from app.models import Source


def _longest_content(entry) -> str | None:
    """Pick the longest `content` value. Some publishers (e.g. Prothom Alo) put an empty
    content entry first and the article body in a later one."""
    values = [c.get("value") or "" for c in entry.get("content", [])]
    best = max(values, key=len, default="")
    return best or None


def _image(entry) -> str | None:
    for key in ("media_content", "media_thumbnail"):
        for media in entry.get(key) or []:
            if media.get("url"):
                return media["url"]
    for enc in entry.get("enclosures") or []:
        if (enc.get("type") or "").startswith("image/") and enc.get("href"):
            return enc["href"]
    return None


def _raw_field(entry, key: str) -> str | None:
    """Read a field only if the feed actually has it. feedparser's `entry.get("updated")`
    silently falls back to the published date, which would invent an update time."""
    return dict.get(entry, key) or None


def parse_feed(content: bytes) -> tuple[list[RawItem], list[str]]:
    """Parse feed bytes into raw items. Raises ConnectorError if nothing usable was parsed."""
    parsed = feedparser.parse(content)
    warnings: list[str] = []
    if parsed.bozo:
        problem = f"{type(parsed.bozo_exception).__name__}: {parsed.bozo_exception}"
        # An empty but well-formed channel is fine; a broken document with no entries is not.
        if not parsed.entries and not parsed.feed.get("title"):
            raise ConnectorError(f"feed could not be parsed ({problem})")
        warnings.append(f"feed parsed with errors: {problem}"[:300])

    items = []
    for entry in parsed.entries:
        items.append(
            RawItem(
                url=entry.get("link"),
                title=entry.get("title"),
                external_id=entry.get("id"),
                summary_html=entry.get("summary"),
                body_html=_longest_content(entry),
                published_raw=_raw_field(entry, "published"),
                updated_raw=_raw_field(entry, "updated"),
                author=entry.get("author"),
                categories=[t["term"] for t in entry.get("tags", []) if t.get("term")],
                image_url=_image(entry),
            )
        )
    return items, warnings


class RssConnector:
    name = "rss"

    def __init__(self, http: PoliteHttpClient) -> None:
        self.http = http

    def fetch(self, source: Source) -> ConnectorResult:
        try:
            response = self.http.get(source.endpoint, etag=source.http_etag, last_modified=source.http_last_modified)
        except FetchError as exc:
            raise ConnectorError(str(exc), exc.status_code, exc.attempts) from exc

        if response.not_modified:
            return ConnectorResult(items=[], not_modified=True, http_status=304, attempts=response.attempts,
                                   etag=source.http_etag, last_modified=source.http_last_modified)
        items, warnings = parse_feed(response.content)
        return ConnectorResult(
            items=items,
            http_status=response.status_code,
            attempts=response.attempts,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            warnings=warnings,
        )
