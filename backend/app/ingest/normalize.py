"""Text, URL and timestamp normalisation.

Bengali notes:
- Text is normalised to Unicode NFC so visually identical strings compare equal
  (e.g. "ে" + "া" composes to "ো").
- ZERO WIDTH JOINER / NON-JOINER (U+200D / U+200C) are kept: Bengali uses them to control
  conjunct rendering (e.g. "র‍্যাব"). Only U+200B (zero width space) and U+FEFF (BOM) are removed.
"""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_INVISIBLE = dict.fromkeys(map(ord, "​﻿"))
_SPACES = re.compile(r"[ \t\r\f\v ]+")
_TRACKING_PARAMS = re.compile(r"^(utm_[a-z]+|fbclid|gclid|mc_cid|mc_eid|ref|ref_src)$", re.I)
_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
               "blockquote", "figure", "figcaption", "table", "tr", "section", "article"}
_SKIP_TAGS = {"script", "style", "noscript", "iframe"}


def clean_text(value: str | None) -> str | None:
    """NFC-normalise, drop invisible characters, collapse spaces. Empty results become None."""
    if value is None:
        return None
    value = unicodedata.normalize("NFC", html.unescape(value)).translate(_INVISIBLE)
    lines = [_SPACES.sub(" ", line).strip() for line in value.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data.replace("\n", " "))


def html_to_text(value: str | None) -> str | None:
    """Convert an HTML fragment to plain text, keeping paragraph breaks as blank lines."""
    if not value:
        return None
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    text = clean_text("".join(parser.parts))
    if text is None:
        return None
    return re.sub(r"\n\s*\n", "\n\n", text)


def single_line(value: str | None) -> str | None:
    text = html_to_text(value)
    return re.sub(r"\s+", " ", text).strip() if text else None


def normalize_url(url: str) -> str:
    """Normalise a URL for duplicate detection (not for display)."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING_PARAMS.match(k)]
    return urlunsplit((scheme, host, path, urlencode(sorted(query)), ""))


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def content_hash(title: str, text: str | None) -> str:
    """Hash of the article's normalised title + text; used to detect changes and exact copies."""
    combined = f"{title}\n{text or ''}"
    normalised = re.sub(r"\s+", " ", unicodedata.normalize("NFC", combined)).strip().casefold()
    return sha256(normalised)


def section_from_url(url: str) -> str | None:
    """First path segment, when the URL has at least two segments (/sport/abc123 -> "sport")."""
    segments = [s for s in urlsplit(url).path.split("/") if s]
    return segments[0].lower() if len(segments) >= 2 else None


FUTURE_TOLERANCE = timedelta(days=1)


def parse_timestamp(raw: str | None, now: datetime | None = None) -> tuple[datetime | None, str | None]:
    """Parse a feed timestamp. Returns (utc_datetime_or_None, note_or_None).

    A timestamp without an explicit timezone is NOT converted (it could be UTC or Bangladesh
    time, UTC+6); the raw value is kept and the parsed value is None.
    """
    if raw is None or not raw.strip():
        return None, "missing"
    raw = raw.strip()
    parsed: datetime | None = None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00") if raw.endswith("Z") else raw)
        except ValueError:
            return None, "unparseable"
    if parsed.tzinfo is None:
        return None, "no timezone in source timestamp"
    utc = parsed.astimezone(timezone.utc)
    now = now or datetime.now(timezone.utc)
    if utc > now + FUTURE_TOLERANCE:
        return utc, "timestamp is in the future"
    return utc, None
