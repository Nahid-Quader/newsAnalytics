from datetime import datetime, timezone

import pytest

from app.ingest.normalize import (
    clean_text,
    content_hash,
    html_to_text,
    normalize_url,
    parse_timestamp,
    section_from_url,
)


class TestUrlNormalisation:
    @pytest.mark.parametrize("raw, expected", [
        ("HTTPS://WWW.ProthomAlo.com/bangladesh/abc/", "https://www.prothomalo.com/bangladesh/abc"),
        ("https://bdnews24.com/world/x?utm_source=fb&utm_medium=s", "https://bdnews24.com/world/x"),
        ("https://bdnews24.com/world/x?b=2&a=1&fbclid=zz", "https://bdnews24.com/world/x?a=1&b=2"),
        ("https://bdnews24.com/world/x#comments", "https://bdnews24.com/world/x"),
        ("https://bdnews24.com:443/world/x", "https://bdnews24.com/world/x"),
        ("https://bdnews24.com:8443/world/x", "https://bdnews24.com:8443/world/x"),
        ("https://bdnews24.com", "https://bdnews24.com/"),
        ("  https://bdnews24.com/a  ", "https://bdnews24.com/a"),
    ])
    def test_normalise(self, raw, expected):
        assert normalize_url(raw) == expected

    def test_variants_collapse_to_same_key(self):
        a = normalize_url("https://www.prothomalo.com/bangladesh/capital/gf28tulsur")
        b = normalize_url("https://WWW.prothomalo.com/bangladesh/capital/gf28tulsur/?utm_campaign=x#top")
        assert a == b

    def test_section_from_url(self):
        assert section_from_url("https://bdnews24.com/sport/hk5fhsutsg") == "sport"
        assert section_from_url("https://www.prothomalo.com/bangladesh/capital/gf28tulsur") == "bangladesh"
        assert section_from_url("https://bdnews24.com/hk5fhsutsg") is None


class TestBengaliText:
    def test_nfc_composition(self):
        decomposed = "কো"  # ক + ে + া  -> কো
        assert clean_text(decomposed) == "কো"

    def test_zwj_and_zwnj_are_preserved(self):
        rab = "র‍্যাব"  # র‍্যাব (RAB) needs the zero width joiner
        assert clean_text(rab) == rab
        assert "‌" in clean_text("ক‌ষ")

    def test_zero_width_space_and_bom_removed(self):
        assert clean_text("﻿ঢাকা​শহর") == "ঢাকাশহর"

    def test_html_to_text_keeps_paragraphs_and_bengali(self):
        html = "<p>প্রথম অনুচ্ছেদ।</p><p>দ্বিতীয় &amp; শেষ</p><script>x()</script>"
        assert html_to_text(html) == "প্রথম অনুচ্ছেদ।\n\nদ্বিতীয় & শেষ"

    def test_empty_html_is_none(self):
        assert html_to_text("") is None
        assert html_to_text("<p> </p>") is None

    def test_content_hash_ignores_whitespace_and_normalisation_form(self):
        assert content_hash("শিরোনাম", "কো  বিষয়") == content_hash("শিরোনাম", "কো বিষয়")
        assert content_hash("a", "b") != content_hash("a", "c")


class TestTimestamps:
    NOW = datetime(2026, 10, 23, 20, 0, tzinfo=timezone.utc)

    def test_rfc822_with_offset(self):
        ts, note = parse_timestamp("Fri, 23 Oct 2026 19:19:03 +0000", self.NOW)
        assert ts == datetime(2026, 10, 23, 19, 19, 3, tzinfo=timezone.utc) and note is None

    def test_bangladesh_offset_converted_to_utc(self):
        ts, _ = parse_timestamp("Sat, 24 Oct 2026 01:00:00 +0600", self.NOW)
        assert ts == datetime(2026, 10, 23, 19, 0, tzinfo=timezone.utc)

    def test_iso_with_z(self):
        ts, note = parse_timestamp("2026-10-23T19:19:03.041Z", self.NOW)
        assert ts.tzinfo is not None and note is None

    def test_missing_timezone_is_not_guessed(self):
        assert parse_timestamp("2026-10-23 19:19:03", self.NOW) == (None, "no timezone in source timestamp")

    @pytest.mark.parametrize("raw, note", [(None, "missing"), ("", "missing"), ("yesterday", "unparseable")])
    def test_missing_or_invalid(self, raw, note):
        assert parse_timestamp(raw, self.NOW) == (None, note)

    def test_future_timestamp_flagged(self):
        ts, note = parse_timestamp("2027-01-01T00:00:00+00:00", self.NOW)
        assert ts is not None and note == "timestamp is in the future"
