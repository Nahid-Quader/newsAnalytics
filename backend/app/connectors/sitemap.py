"""Backfill connector: collect past articles for one publication day.

1. Read the publisher's daily sitemap for that day (plus, optionally, its Google News sitemap,
   filtered to the same day; bdnews24's daily sitemaps are capped at 100 links).
2. Keep only links on the source's own host; skip articles already in the database.
3. Fetch each article page and extract it (app.connectors.page).

Politeness: the shared client spaces requests per host. A 403 or 429 on any page stops the
run for this source immediately (`blocked` is set) instead of continuing to hit the site.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

from app.connectors.base import ConnectorError, ConnectorResult, RawItem
from app.connectors.page import extract_article
from app.core.http import FetchError, PoliteHttpClient
from app.core.logging import log_event
from app.ingest.normalize import normalize_url, sha256
from app.models import Source

logger = logging.getLogger(__name__)

BD_TZ = timezone(timedelta(hours=6))  # Bangladesh Standard Time; no daylight saving
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9", "news": "http://www.google.com/schemas/sitemap-news/0.9"}
STOP_STATUSES = {403, 429}
PROGRESS_EVERY = 50


def parse_sitemap(content: bytes) -> list[tuple[str, str | None]]:
    """Return (url, news publication_date or None) for every <url> in a sitemap."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ConnectorError(f"sitemap could not be parsed: {exc}") from exc
    out = []
    for node in root.findall("sm:url", NS):
        loc = (node.findtext("sm:loc", default="", namespaces=NS) or "").strip()
        if loc:
            out.append((loc, node.findtext("news:news/news:publication_date", default=None, namespaces=NS)))
    return out


def bd_date_of(timestamp: str | None) -> date | None:
    if not timestamp:
        return None
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(BD_TZ).date() if dt.tzinfo else None


class SitemapBackfillConnector:
    name = "sitemap_page"

    def __init__(self, http: PoliteHttpClient, day: date, known_url_hashes: set[str],
                 news_sitemap_cache: dict[str, list[tuple[str, str | None]]] | None = None,
                 max_pages: int | None = None) -> None:
        self.http = http
        self.day = day
        self.known = known_url_hashes
        self.news_cache = news_sitemap_cache if news_sitemap_cache is not None else {}
        self.max_pages = max_pages
        self.blocked: str | None = None
        self.candidates: list[str] = []  # filled by list_candidates(); useful for dry runs

    def _get(self, url: str):
        try:
            return self.http.get(url)
        except FetchError as exc:
            raise ConnectorError(f"{exc} for {url}", exc.status_code, exc.attempts) from exc

    def list_candidates(self, source: Source) -> tuple[list[str], list[str]]:
        cfg = (source.config or {}).get("backfill")
        if not cfg:
            raise ConnectorError(f"source {source.id} has no backfill configuration")
        host = urlsplit(source.homepage).hostname
        warnings: list[str] = []

        daily_url = cfg["daily_sitemap"].replace("{date}", self.day.isoformat())
        entries = parse_sitemap(self._get(daily_url).content)
        if cfg.get("news_sitemap"):
            news_url = cfg["news_sitemap"]
            if news_url not in self.news_cache:
                self.news_cache[news_url] = parse_sitemap(self._get(news_url).content)
            entries += [(u, d) for u, d in self.news_cache[news_url] if bd_date_of(d) == self.day]

        seen, candidates, foreign = set(), [], 0
        for url, _ in entries:
            if urlsplit(url).hostname != host:
                foreign += 1  # e.g. sister sites like kishoralo.com listed in Prothom Alo's sitemap
                continue
            key = sha256(normalize_url(url))
            if key in seen or key in self.known:
                seen.add(key)
                continue
            seen.add(key)
            candidates.append(url)
        if foreign:
            warnings.append(f"skipped {foreign} link(s) on other hosts")
        if self.max_pages is not None and len(candidates) > self.max_pages:
            warnings.append(f"limited to {self.max_pages} of {len(candidates)} pages")
            candidates = candidates[: self.max_pages]
        self.candidates = candidates
        log_event(logger, "backfill_candidates", source_id=source.id, day=self.day.isoformat(),
                  sitemap_links=len(entries), already_known=len(seen) - len(candidates), to_fetch=len(candidates))
        return candidates, warnings

    def fetch(self, source: Source) -> ConnectorResult:
        candidates, warnings = self.list_candidates(source)
        items: list[RawItem] = []
        failed = 0
        for i, url in enumerate(candidates, 1):
            try:
                response = self.http.get(url)
            except FetchError as exc:
                if exc.status_code in STOP_STATUSES:
                    self.blocked = f"HTTP {exc.status_code} on {url}"
                    warnings.append(f"stopped early: {self.blocked}")
                    log_event(logger, "backfill_stopped", logging.WARNING, source_id=source.id, reason=self.blocked)
                    break
                failed += 1
                warnings.append(f"page fetch failed ({exc}): {url}")
                continue
            art = extract_article(response.content.decode("utf-8", errors="replace"), url)
            items.append(RawItem(
                url=url,
                title=art.title,
                external_id=None,
                summary_html=art.description,
                body_html=art.body_html,
                published_raw=art.published_raw,
                updated_raw=art.updated_raw,
                author=art.author,
                categories=art.keywords,
                image_url=art.image_url,
                body_source="page",
                provenance={"body_extraction": art.body_method, "page_section": art.section,
                            "backfill_day": self.day.isoformat()},
            ))
            if i % PROGRESS_EVERY == 0:
                log_event(logger, "backfill_progress", source_id=source.id, day=self.day.isoformat(),
                          fetched=i, of=len(candidates))
        if failed:
            warnings.append(f"{failed} page(s) could not be fetched")
        return ConnectorResult(items=items, http_status=200, attempts=1, warnings=warnings,
                               collection_method=self.name, update_http_state=False)
