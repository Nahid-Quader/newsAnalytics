import unicodedata

import feedparser
import httpx
from sqlalchemy import func, select

from app.ingest.pipeline import run_all, run_source
from app.models import Article, FetchRun, Source
from tests.conftest import FEED_URLS, fixture_bytes, rss

PA = "prothomalo-bn"


def count(session_factory, **where) -> int:
    with session_factory() as s:
        q = select(func.count(Article.id))
        for k, v in where.items():
            q = q.where(getattr(Article, k) == v)
        return s.scalar(q)


def test_end_to_end_run_on_real_fixtures(session_factory, serve_real_fixtures, make_connectors):
    results = {r.source_id: r for r in run_all(session_factory, make_connectors())}
    assert set(results) == set(FEED_URLS)
    for sid in ("prothomalo-bn", "bdnews24-bn", "bdnews24-en"):
        expected = len(feedparser.parse(fixture_bytes(f"{sid}.xml")).entries)
        assert results[sid].status == "success"
        assert results[sid].new == expected == count(session_factory, source_id=sid)
    assert results["prothomalo-en"].status == "success" and results["prothomalo-en"].new == 0
    assert "feed returned no items" in results["prothomalo-en"].warnings


def test_rerun_creates_no_duplicates(session_factory, serve_real_fixtures, make_connectors):
    connectors = make_connectors()
    first = run_all(session_factory, connectors)
    total = count(session_factory)
    second = run_all(session_factory, connectors)
    assert count(session_factory) == total
    assert sum(r.new for r in second) == 0
    assert sum(r.unchanged for r in second) == sum(r.new for r in first)


def test_articles_have_full_text_and_utc_dates(session_factory, serve_real_fixtures, make_connectors):
    run_all(session_factory, make_connectors(), [PA])
    with session_factory() as s:
        arts = s.scalars(select(Article).where(Article.source_id == PA)).all()
    assert all(a.published_at is not None and a.published_at.tzinfo is not None for a in arts)
    assert sum(1 for a in arts if a.body and len(a.body) > 500) > len(arts) / 2
    assert all(a.body_source == "feed" for a in arts if a.body)
    # Most URLs carry a section; one real item links to sister site kishoralo.com/<id> with none.
    assert sum(1 for a in arts if a.section) > len(arts) * 0.9
    assert all((a.section is None) == (a.section_source is None) for a in arts)


def test_bengali_text_round_trips_unchanged(session_factory, serve_real_fixtures, make_connectors):
    run_all(session_factory, make_connectors(), ["bdnews24-bn"])
    entry = feedparser.parse(fixture_bytes("bdnews24-bn.xml")).entries[0]
    with session_factory() as s:
        art = s.scalar(select(Article).where(Article.url == entry.link))
    assert art.title == unicodedata.normalize("NFC", entry.title).strip()
    assert any("ঀ" <= ch <= "৿" for ch in art.body)


def _feed(body: str, date: str = "Fri, 23 Oct 2026 10:00:00 +0000") -> bytes:
    # SYNTHETIC feed with one article whose body can be changed between runs.
    return rss(f"<item><title>শিরোনাম</title><link>https://www.prothomalo.com/bangladesh/x1</link>"
               f"<guid>g-1</guid><pubDate>{date}</pubDate><content:encoded><![CDATA[<p>{body}</p>]]>"
               f"</content:encoded></item>")


def test_changed_content_updates_existing_article(session_factory, web, make_connectors):
    web.add(FEED_URLS[PA], httpx.Response(200, content=_feed("প্রথম সংস্করণ")),
            httpx.Response(200, content=_feed("সংশোধিত সংস্করণ")))
    connectors = make_connectors()
    run_source(session_factory, PA, connectors["rss"])
    stats = run_source(session_factory, PA, connectors["rss"])
    assert (stats.new, stats.updated) == (0, 1)
    with session_factory() as s:
        art = s.scalar(select(Article).where(Article.source_id == PA))
    assert art.body == "সংশোধিত সংস্করণ" and art.version == 2
    assert art.last_updated_at > art.first_seen_at
    assert len(art.provenance["updates"]) == 1


def test_items_without_link_or_title_are_rejected_not_fatal(session_factory, web, make_connectors):
    web.add(FEED_URLS[PA], httpx.Response(200, content=rss(
        "<item><title>No link</title></item>"
        "<item><link>https://www.prothomalo.com/a/no-title</link></item>"
        "<item><title>Good</title><link>https://www.prothomalo.com/a/good</link></item>")))
    stats = run_source(session_factory, PA, make_connectors()["rss"])
    assert stats.status == "success" and stats.new == 1 and stats.parse_failures == 2
    assert any("missing title" in w for w in stats.warnings)


def test_missing_and_naive_dates_stay_null(session_factory, web, make_connectors):
    web.add(FEED_URLS[PA], httpx.Response(200, content=rss(
        "<item><title>A</title><link>https://www.prothomalo.com/a/1</link></item>"
        "<item><title>B</title><link>https://www.prothomalo.com/a/2</link><pubDate>2026-10-23 10:00:00</pubDate></item>")))
    run_source(session_factory, PA, make_connectors()["rss"])
    with session_factory() as s:
        arts = {a.url[-1]: a for a in s.scalars(select(Article))}
    assert arts["1"].published_at is None and arts["1"].published_at_note == "missing"
    assert arts["2"].published_at is None and arts["2"].published_at_raw == "2026-10-23 10:00:00"
    assert arts["1"].ingestion_status == "partial"


def test_same_text_in_two_sources_is_linked_not_deleted(session_factory, web, make_connectors):
    item = ("<item><title>Same wire story</title><link>{}</link>"
            "<content:encoded><![CDATA[<p>Identical body text.</p>]]></content:encoded></item>")
    web.add(FEED_URLS["bdnews24-en"], httpx.Response(200, content=rss(item.format("https://bdnews24.com/world/a"))))
    web.add(FEED_URLS["prothomalo-en"], httpx.Response(200, content=rss(item.format("https://en.prothomalo.com/world/b"))))
    connectors = make_connectors()
    run_source(session_factory, "bdnews24-en", connectors["rss"])
    stats = run_source(session_factory, "prothomalo-en", connectors["rss"])
    assert stats.duplicates == 1
    with session_factory() as s:
        original = s.scalar(select(Article).where(Article.source_id == "bdnews24-en"))
        copy = s.scalar(select(Article).where(Article.source_id == "prothomalo-en"))
    assert copy.duplicate_of_id == original.id and original.duplicate_of_id is None


def test_one_failing_source_does_not_stop_others(session_factory, serve_real_fixtures, make_connectors):
    serve_real_fixtures.routes[FEED_URLS["bdnews24-bn"]] = [httpx.Response(403)]
    results = {r.source_id: r for r in run_all(session_factory, make_connectors())}
    assert results["bdnews24-bn"].status == "failed" and results["bdnews24-bn"].error == "HTTP 403"
    assert results["prothomalo-bn"].status == "success" and results["prothomalo-bn"].new > 0
    with session_factory() as s:
        run = s.scalar(select(FetchRun).where(FetchRun.source_id == "bdnews24-bn"))
    assert run.status == "failed" and run.http_status == 403 and run.finished_at is not None


def test_connector_crash_is_recorded(session_factory, make_connectors):
    class Broken:
        name = "rss"

        def fetch(self, source):
            raise RuntimeError("boom")

    stats = run_source(session_factory, PA, Broken())
    assert stats.status == "failed" and "RuntimeError: boom" in stats.error


def test_not_modified_keeps_conditional_state(session_factory, web, make_connectors):
    web.add(FEED_URLS[PA],
            httpx.Response(200, content=_feed("x"), headers={"etag": '"v1"'}),
            httpx.Response(304))
    connectors = make_connectors()
    run_source(session_factory, PA, connectors["rss"])
    stats = run_source(session_factory, PA, connectors["rss"])
    assert stats.status == "not_modified"
    assert web.requests[1].headers["if-none-match"] == '"v1"'
    with session_factory() as s:
        assert s.get(Source, PA).http_etag == '"v1"'


def test_fetch_run_statistics_recorded(session_factory, serve_real_fixtures, make_connectors):
    run_all(session_factory, make_connectors(), [PA])
    with session_factory() as s:
        run = s.scalar(select(FetchRun).where(FetchRun.source_id == PA))
    assert run.status == "success" and run.items_seen == run.new_count > 0
    assert run.attempts == 1 and run.duration_ms is not None
