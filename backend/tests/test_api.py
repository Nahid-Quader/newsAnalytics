from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import create_app
from app.db import get_session, utcnow
from app.ingest.pipeline import run_all
from app.models import Article, FetchRun
from tests.conftest import FEED_URLS


@pytest.fixture
def client(session_factory):
    app = create_app()

    def _session():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    return TestClient(app)


@pytest.fixture
def ingested(session_factory, serve_real_fixtures, make_connectors):
    serve_real_fixtures.routes[FEED_URLS["bdnews24-en"]] = [httpx.Response(503)]
    run_all(session_factory, make_connectors())
    return session_factory


def test_sources_listed(client):
    data = client.get("/sources").json()
    assert {s["id"] for s in data} == set(FEED_URLS)


def test_health_before_any_run(client):
    assert {h["status"] for h in client.get("/sources/health").json()} == {"never_run"}


def test_health_after_run(client, ingested):
    health = {h["source_id"]: h for h in client.get("/sources/health").json()}
    assert health["prothomalo-bn"]["status"] == "ok"
    assert health["prothomalo-bn"]["articles_total"] > 0
    assert health["bdnews24-en"]["status"] == "failing"
    assert health["bdnews24-en"]["consecutive_failures"] == 1
    assert health["bdnews24-en"]["recent_errors"][0]["http_status"] == 503
    assert health["prothomalo-en"]["status"] == "warning"
    assert "no items" in health["prothomalo-en"]["warnings"][0]


def test_stale_source(client, ingested):
    with ingested() as s:
        for run in s.scalars(select(FetchRun).where(FetchRun.source_id == "prothomalo-bn")):
            run.started_at = utcnow() - timedelta(hours=5)
        s.commit()
    health = {h["source_id"]: h for h in client.get("/sources/health").json()}
    assert health["prothomalo-bn"]["status"] == "stale"


def test_articles_pagination(client, ingested):
    first = client.get("/articles", params={"page_size": 10}).json()
    second = client.get("/articles", params={"page_size": 10, "page": 2}).json()
    assert first["total"] == second["total"] > 20
    assert len(first["items"]) == 10
    assert not {a["id"] for a in first["items"]} & {a["id"] for a in second["items"]}
    dates = [a["published_at"] for a in first["items"]]
    assert dates == sorted(dates, reverse=True)


def test_page_size_limit(client):
    assert client.get("/articles", params={"page_size": 500}).status_code == 422


def test_filter_by_source_and_language(client, ingested):
    by_source = client.get("/articles", params={"source": "bdnews24-bn", "page_size": 100}).json()
    assert by_source["total"] > 0 and {a["source_id"] for a in by_source["items"]} == {"bdnews24-bn"}
    en = client.get("/articles", params={"language": "en"}).json()
    assert en["total"] == 0  # the only English source with items failed in this fixture
    assert client.get("/articles", params={"language": "xx"}).status_code == 422


def test_bengali_search(client, ingested):
    with ingested() as s:
        art = s.scalar(select(Article).where(Article.source_id == "bdnews24-bn"))
    word = next(w for w in art.title.split() if len(w) > 3)
    data = client.get("/articles", params={"q": word, "page_size": 100}).json()
    assert art.id in {a["id"] for a in data["items"]}
    assert client.get("/articles", params={"q": "অস্তিত্বহীনশব্দ"}).json()["total"] == 0


def test_search_escapes_wildcards(client, ingested):
    assert client.get("/articles", params={"q": "%_%"}).json()["total"] == 0


def test_date_filter(client, ingested):
    with ingested() as s:
        art = s.scalar(select(Article).where(Article.published_at.is_not(None)).limit(1))
    day = art.published_at.date().isoformat()
    data = client.get("/articles", params={"date_from": day, "date_to": day, "page_size": 100}).json()
    assert data["total"] > 0
    assert all(a["published_at"].startswith(day) for a in data["items"])


def test_filter_by_section(client, ingested):
    data = client.get("/articles", params={"source": "bdnews24-bn", "page_size": 100}).json()
    section = data["items"][0]["section"]
    filtered = client.get("/articles", params={"section": section, "page_size": 100}).json()
    assert filtered["total"] > 0 and all(a["section"] == section for a in filtered["items"])


def test_article_detail_and_404(client, ingested):
    first = client.get("/articles").json()["items"][0]
    detail = client.get(f"/articles/{first['id']}").json()
    assert detail["url"] == first["url"] and detail["provenance"]["collected_via"] == "rss"
    assert detail["body"] and detail["content_hash"]
    assert client.get("/articles/does-not-exist").status_code == 404


def test_overview(client, ingested):
    data = client.get("/analytics/overview").json()
    assert data["articles_total"] == sum(c["articles"] for c in data["coverage"])
    assert data["sources_total"] == 4 and len(data["per_day"]) == 14
    assert data["last_24h"]["runs"] == 4 and data["last_24h"]["failed"] == 1
    assert {s["key"] for s in data["sources_by_status"]} >= {"ok", "failing"}
