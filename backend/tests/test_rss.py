import feedparser
import pytest

from app.connectors.base import ConnectorError
from app.connectors.rss import parse_feed
from app.ingest.normalize import html_to_text
from tests.conftest import fixture_bytes, rss


@pytest.mark.parametrize("name", ["prothomalo-bn.xml", "bdnews24-bn.xml", "bdnews24-en.xml"])
def test_real_fixture_feeds_parse_with_full_text(name):
    items, warnings = parse_feed(fixture_bytes(name))
    expected = len(feedparser.parse(fixture_bytes(name)).entries)
    assert len(items) == expected > 20
    assert all(i.url and i.title and i.published_raw for i in items)
    bodies = sorted(len(html_to_text(i.body_html) or "") for i in items)
    assert bodies[len(bodies) // 2] > 500, "median body should be full article text"


def test_prothomalo_body_taken_from_longest_content_entry():
    # Prothom Alo puts an empty <content> first and the article in a second one.
    items, _ = parse_feed(fixture_bytes("prothomalo-bn.xml"))
    assert all(i.body_html for i in items[:5])


def test_bengali_fixture_contains_bengali_script():
    items, _ = parse_feed(fixture_bytes("bdnews24-bn.xml"))
    assert any("ঀ" <= ch <= "৿" for ch in items[0].title)


def test_real_empty_feed_returns_no_items_without_error():
    items, warnings = parse_feed(fixture_bytes("prothomalo-en-empty.xml"))
    assert items == [] and warnings == []


def test_malformed_xml_raises():
    with pytest.raises(ConnectorError, match="could not be parsed"):
        parse_feed(b"<html><body>Just a moment...</body>")


def test_truncated_feed_keeps_parsed_items_with_warning():
    # SYNTHETIC: a feed cut off mid-document.
    doc = rss("<item><title>One</title><link>https://example.org/a/1</link></item>").decode()[:-20]
    items, warnings = parse_feed(doc.encode())
    assert len(items) == 1
    assert warnings and "parsed with errors" in warnings[0]


def test_missing_optional_fields_are_none():
    # SYNTHETIC
    items, _ = parse_feed(rss("<item><title>Only title</title><link>https://example.org/x/1</link></item>"))
    item = items[0]
    assert item.author is None and item.published_raw is None and item.body_html is None
    assert item.categories == []


def test_update_time_not_invented_from_publish_time():
    # SYNTHETIC: only pubDate present; feedparser would otherwise report it as "updated" too.
    items, _ = parse_feed(rss("<item><title>T</title><link>https://example.org/x/1</link>"
                              "<pubDate>Fri, 23 Oct 2026 10:00:00 +0000</pubDate></item>"))
    assert items[0].published_raw and items[0].updated_raw is None
