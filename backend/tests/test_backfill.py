from datetime import date

import httpx
from sqlalchemy import select

from app.connectors.page import extract_article
from app.connectors.sitemap import SitemapBackfillConnector, bd_date_of, parse_sitemap
from app.core.http import PoliteHttpClient
from app.health import all_source_health
from app.ingest.backfill import backfill_days, run_backfill
from app.ingest.normalize import html_to_text, normalize_url, sha256
from app.models import Article, FetchRun, Source
from tests.conftest import fixture_bytes

PA = "prothomalo-bn"
DAY = date(2026, 10, 22)
PA_DAILY = "https://www.prothomalo.com/sitemap/sitemap-daily-2026-10-22.xml"
PA_NEWS = "https://www.prothomalo.com/news_sitemap.xml"
PAGE = fixture_bytes("page-prothomalo-bn.html")


def sitemap(*urls: str, news_date: str | None = None) -> bytes:
    """SYNTHETIC sitemap listing the given URLs."""
    news = (f"<news:news><news:publication_date>{news_date}</news:publication_date></news:news>"
            if news_date else "")
    body = "".join(f"<url><loc>{u}</loc>{news}</url>" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            f'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">{body}</urlset>').encode()


def http(settings, web, sleeps):
    return PoliteHttpClient(settings, transport=httpx.MockTransport(web.handler), sleep=sleeps.append)


# --- page extraction (real fixtures) -------------------------------------------------------------

def test_extract_prothomalo_from_jsonld():
    art = extract_article(PAGE.decode("utf-8"), "https://www.prothomalo.com/bangladesh/district/34hl2tc2c5")
    text = html_to_text(art.body_html)
    assert art.body_method == "jsonld" and len(text) > 1500 and "<p>" not in text
    assert art.title.startswith("গৃহবধূর মরদেহ")
    assert art.published_raw == "2026-07-24T16:01:34+06:00"
    assert art.author and art.keywords


def test_extract_bdnews24_en_falls_back_to_trafilatura():
    # bdnews24 English's JSON-LD articleBody is only a ~100 character teaser.
    art = extract_article(fixture_bytes("page-bdnews24-en.html").decode("utf-8"),
                          "https://bdnews24.com/bangladesh/2tc5qa433p")
    text = html_to_text(art.body_html)
    assert art.body_method == "trafilatura" and len(text) > 3000
    assert text.startswith("The plans were taking shape")  # "Published : ..." dateline removed
    assert art.published_raw == "2026-10-22T19:04:38+00:00"


def test_extract_page_without_article_data():
    art = extract_article("<html><head><title>x</title></head><body><p>hi</p></body></html>", "https://e.org/a")
    assert art.title is None and art.published_raw is None


# --- sitemaps ----------------------------------------------------------------------------------

def test_parse_real_news_sitemap():
    entries = parse_sitemap(fixture_bytes("news-sitemap-bdnews24-bn.xml"))
    assert len(entries) > 50
    assert all(u.startswith("https://") for u, _ in entries)
    assert all(d for _, d in entries)


def test_bd_date_conversion():
    assert bd_date_of("2026-10-21T19:30:00Z") == date(2026, 10, 22)  # 01:30 next day in Dhaka
    assert bd_date_of("2026-10-22T10:00:00+06:00") == date(2026, 10, 22)
    assert bd_date_of("2026-10-22T10:00:00") is None and bd_date_of(None) is None


def test_backfill_days_newest_first():
    assert backfill_days(3, today=date(2026, 10, 24)) == [date(2026, 10, 24), date(2026, 10, 23), date(2026, 10, 22)]


# --- connector -------------------------------------------------------------------------------

def _source(session_factory) -> Source:
    with session_factory() as s:
        return s.get(Source, PA)


def test_connector_filters_hosts_known_and_news_sitemap_by_day(session_factory, settings, web, sleeps):
    known_url = "https://www.prothomalo.com/bangladesh/known1"
    web.add(PA_DAILY, httpx.Response(200, content=sitemap(
        "https://www.prothomalo.com/bangladesh/new1", known_url, "https://www.kishoralo.com/abc")))
    web.add(PA_NEWS, httpx.Response(200, content=sitemap(
        "https://www.prothomalo.com/bangladesh/new2", news_date="2026-10-22T05:00:00+06:00")
        .replace(b"</urlset>", b"<url><loc>https://www.prothomalo.com/x/other-day</loc><news:news>"
                 b"<news:publication_date>2026-10-20T05:00:00Z</news:publication_date></news:news></url></urlset>")))
    for u in ("https://www.prothomalo.com/bangladesh/new1", "https://www.prothomalo.com/bangladesh/new2"):
        web.add(u, httpx.Response(200, content=PAGE))
    conn = SitemapBackfillConnector(http(settings, web, sleeps), DAY, {sha256(normalize_url(known_url))})
    result = conn.fetch(_source(session_factory))
    assert [i.url for i in result.items] == ["https://www.prothomalo.com/bangladesh/new1",
                                             "https://www.prothomalo.com/bangladesh/new2"]
    assert all(i.body_source == "page" and i.provenance["body_extraction"] == "jsonld" for i in result.items)
    assert result.collection_method == "sitemap_page" and result.update_http_state is False
    assert any("other hosts" in w for w in result.warnings)


def test_connector_stops_on_403(session_factory, settings, web, sleeps):
    urls = [f"https://www.prothomalo.com/a/{i}" for i in range(3)]
    web.add(PA_DAILY, httpx.Response(200, content=sitemap(*urls)))
    web.add(PA_NEWS, httpx.Response(200, content=sitemap()))
    web.add(urls[0], httpx.Response(200, content=PAGE))
    web.add(urls[1], httpx.Response(403))
    web.add(urls[2], httpx.Response(200, content=PAGE))
    conn = SitemapBackfillConnector(http(settings, web, sleeps), DAY, set())
    result = conn.fetch(_source(session_factory))
    assert len(result.items) == 1 and conn.blocked == f"HTTP 403 on {urls[1]}"
    assert urls[2] not in {str(r.url) for r in web.requests}


def test_connector_skips_pages_that_fail_with_other_errors(session_factory, settings, web, sleeps):
    urls = ["https://www.prothomalo.com/a/gone", "https://www.prothomalo.com/a/ok"]
    web.add(PA_DAILY, httpx.Response(200, content=sitemap(*urls)))
    web.add(PA_NEWS, httpx.Response(200, content=sitemap()))
    web.add(urls[1], httpx.Response(200, content=PAGE))  # urls[0] -> 404
    conn = SitemapBackfillConnector(http(settings, web, sleeps), DAY, set())
    result = conn.fetch(_source(session_factory))
    assert [i.url for i in result.items] == [urls[1]] and conn.blocked is None
    assert any("could not be fetched" in w for w in result.warnings)


# --- end to end --------------------------------------------------------------------------------

def _serve_one_day(web):
    urls = ["https://www.prothomalo.com/bangladesh/p1", "https://www.prothomalo.com/bangladesh/p2"]
    web.add(PA_DAILY, httpx.Response(200, content=sitemap(*urls)))
    web.add(PA_NEWS, httpx.Response(200, content=sitemap()))
    for u in urls:
        web.add(u, httpx.Response(200, content=PAGE))
    return urls


def test_run_backfill_persists_and_rerun_fetches_nothing(session_factory, settings, web, sleeps):
    urls = _serve_one_day(web)
    client = http(settings, web, sleeps)
    first = run_backfill(session_factory, client, days=1, source_ids=[PA], today=DAY)
    assert first[0]["status"] == "success" and first[0]["new"] == 2
    # The fixture page is the same article, so the second copy is linked as an exact duplicate.
    assert first[0]["duplicates"] == 1

    requests_before = len(web.requests)
    second = run_backfill(session_factory, client, days=1, source_ids=[PA], today=DAY)
    assert second[0]["new"] == 0
    page_requests = [r for r in web.requests[requests_before:] if str(r.url) in urls]
    assert page_requests == []  # known articles are skipped before fetching

    with session_factory() as s:
        arts = s.scalars(select(Article).where(Article.source_id == PA)).all()
        runs = s.scalars(select(FetchRun)).all()
    assert len(arts) == 2
    assert all(a.collection_method == "sitemap_page" and a.body_source == "page" for a in arts)
    assert all(a.published_at is not None and a.provenance["backfill_day"] == "2026-10-22" for a in arts)
    assert {(r.kind, r.target_date) for r in runs} == {("backfill", "2026-10-22")}


def test_backfill_does_not_affect_feed_health_or_etag(session_factory, settings, web, sleeps):
    _serve_one_day(web)
    run_backfill(session_factory, http(settings, web, sleeps), days=1, source_ids=[PA], today=DAY)
    with session_factory() as s:
        health = {h.source_id: h for h in all_source_health(s)}
        assert s.get(Source, PA).http_etag is None
    assert health[PA].status == "never_run" and health[PA].articles_total == 2


def test_dry_run_reads_only_sitemaps(session_factory, settings, web, sleeps):
    urls = _serve_one_day(web)
    result = run_backfill(session_factory, http(settings, web, sleeps), days=1, source_ids=[PA],
                          today=DAY, dry_run=True)
    assert result == [{"source_id": PA, "day": "2026-10-22", "to_fetch": 2, "warnings": []}]
    assert not {str(r.url) for r in web.requests} & set(urls)
    with session_factory() as s:
        assert s.scalar(select(Article.id)) is None


def test_missing_sitemap_fails_the_run(session_factory, settings, web, sleeps):
    web.add(PA_DAILY, httpx.Response(404))
    result = run_backfill(session_factory, http(settings, web, sleeps), days=1, source_ids=[PA], today=DAY)
    assert result[0]["status"] == "failed" and "HTTP 404" in result[0]["error"]
