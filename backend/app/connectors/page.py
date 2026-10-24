"""Extract article data from a publisher's article page.

Order of preference:
1. schema.org NewsArticle JSON-LD (structured data publishers provide for search engines):
   headline, articleBody, datePublished, author, keywords, description, image.
2. If the JSON-LD body is missing or only a teaser (bdnews24 English puts ~100 chars there),
   the main text is extracted from the HTML with trafilatura.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass, field

import trafilatura

from app.ingest.normalize import html_to_text

ARTICLE_TYPES = {"NewsArticle", "Article", "ReportageNewsArticle", "AnalysisNewsArticle", "OpinionNewsArticle"}
MIN_JSONLD_BODY_CHARS = 300

_JSONLD = re.compile(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)
_OG_TITLE = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', re.I)


@dataclass
class ExtractedArticle:
    title: str | None
    body_html: str | None
    body_method: str | None  # "jsonld" | "trafilatura" | None
    description: str | None = None
    published_raw: str | None = None
    updated_raw: str | None = None
    author: str | None = None
    section: str | None = None
    keywords: list[str] = field(default_factory=list)
    image_url: str | None = None


def _jsonld_objects(page: str) -> list[dict]:
    found = []
    for block in _JSONLD.findall(page):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, dict):
                found.append(x)
                if "@graph" in x:
                    stack.append(x["@graph"])
    return found


def _is_article(obj: dict) -> bool:
    types = obj.get("@type")
    types = types if isinstance(types, list) else [types]
    return any(t in ARTICLE_TYPES for t in types)


def _names(value) -> str | None:
    items = value if isinstance(value, list) else [value]
    names = []
    for it in items:
        name = it.get("name") if isinstance(it, dict) else it
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return ", ".join(dict.fromkeys(names)) or None


def _first_str(value) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("url") or value.get("name")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _keywords(value) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        return []
    return [k.strip() for k in value if isinstance(k, str) and k.strip()]


# Page furniture that trafilatura sometimes keeps at the top of the text (e.g. bdnews24 English).
_DATELINE = re.compile(r"^(published|updated)\s*:", re.I)


def _text_to_html(text: str) -> str:
    lines = [p.strip() for p in text.split("\n") if p.strip()]
    while lines and _DATELINE.match(lines[0]):
        lines.pop(0)
    return "".join(f"<p>{html_lib.escape(p)}</p>" for p in lines)


def _jsonld_body(article: dict) -> str | None:
    body = article.get("articleBody")
    if not isinstance(body, str) or not body.strip():
        return None
    # Some publishers (e.g. Prothom Alo) store the body as entity-escaped HTML ("&lt;p&gt;...").
    if "&lt;" in body and "<" not in body:
        body = html_lib.unescape(body)
    return body


def extract_article(page: str, url: str) -> ExtractedArticle:
    article = next((o for o in _jsonld_objects(page) if _is_article(o)), {})

    body_html = _jsonld_body(article)
    body_method = "jsonld" if body_html else None
    if not body_html or len(html_to_text(body_html) or "") < MIN_JSONLD_BODY_CHARS:
        text = trafilatura.extract(page, url=url, include_comments=False, include_tables=False,
                                   favor_precision=True, deduplicate=True)
        if text and len(text) > len(html_to_text(body_html) or ""):
            body_html, body_method = _text_to_html(text), "trafilatura"

    title = _first_str(article.get("headline"))
    if not title:
        m = _OG_TITLE.search(page)
        title = html_lib.unescape(m.group(1)).strip() if m else None

    return ExtractedArticle(
        title=title,
        body_html=body_html,
        body_method=body_method if body_html else None,
        description=_first_str(article.get("description")),
        published_raw=_first_str(article.get("datePublished")),
        updated_raw=_first_str(article.get("dateModified")),
        author=_names(article.get("author")),
        section=_first_str(article.get("articleSection")),
        keywords=_keywords(article.get("keywords")),
        image_url=_first_str(article.get("image")),
    )
