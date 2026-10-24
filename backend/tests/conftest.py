from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from app.connectors import build_connectors
from app.core.config import REPO_ROOT, Settings
from app.core.http import PoliteHttpClient
from app.db import Base, make_engine, make_session_factory
from app.sources import load_sources, sync_sources

FIXTURES = Path(__file__).parent / "fixtures"

FEED_URLS = {
    "prothomalo-bn": "https://www.prothomalo.com/feed",
    "bdnews24-bn": "https://bangla.bdnews24.com/stories.rss",
    "bdnews24-en": "https://bdnews24.com/stories.rss",
    "prothomalo-en": "https://en.prothomalo.com/feed",
}
FIXTURE_FILES = {
    "prothomalo-bn": "prothomalo-bn.xml",
    "bdnews24-bn": "bdnews24-bn.xml",
    "bdnews24-en": "bdnews24-en.xml",
    "prothomalo-en": "prothomalo-en-empty.xml",
}


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def rss(items_xml: str, title: str = "Synthetic test feed") -> bytes:
    """Build a SYNTHETIC RSS document for edge-case tests (not real publisher data)."""
    return (f'<?xml version="1.0" encoding="utf-8"?><rss version="2.0" '
            f'xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>{title}</title>'
            f"<link>https://example.org</link>{items_xml}</channel></rss>").encode("utf-8")


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        per_host_delay_s=0,
        http_backoff_base_s=0,
        http_max_retries=2,
        log_json=False,
    )


@pytest.fixture
def session_factory(settings):
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        sync_sources(session, load_sources(REPO_ROOT / "config" / "sources.yaml"))
    yield factory
    engine.dispose()


class FakeWeb:
    """httpx MockTransport serving queued responses per URL and recording requests."""

    def __init__(self) -> None:
        self.routes: dict[str, list] = {}
        self.requests: list[httpx.Request] = []

    def add(self, url: str, *responses) -> None:
        self.routes.setdefault(url, []).extend(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        queue = self.routes.get(str(request.url))
        if not queue:
            return httpx.Response(404)
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(request)
        return item


@pytest.fixture
def web() -> FakeWeb:
    return FakeWeb()


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def make_connectors(settings, web, sleeps) -> Callable:
    def _make():
        http = PoliteHttpClient(settings, transport=httpx.MockTransport(web.handler), sleep=sleeps.append)
        return build_connectors(http)
    return _make


@pytest.fixture
def serve_real_fixtures(web):
    for sid, url in FEED_URLS.items():
        web.add(url, httpx.Response(200, content=fixture_bytes(FIXTURE_FILES[sid]),
                                    headers={"content-type": "application/rss+xml"}))
    return web
