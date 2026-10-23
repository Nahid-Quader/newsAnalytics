"""Check whether each feed is fresh and carries full article text.

For every feed, the newest few entries are compared with the article page:
  feed_text  = longest of the entry's summary / content values, HTML stripped
  page_text  = schema.org JSON-LD articleBody, or joined <p> text as a fallback
  ratio      = len(feed_text) / len(page_text)

A feed is classed "full text" when the median ratio is >= 0.8 and the median feed text is
>= 500 characters. Pages are fetched only when robots.txt allows it (or cannot be read and
the page is public); blocked pages are recorded, not retried.

Usage:
    $env:PYTHONIOENCODING="utf-8"; .venv\\Scripts\\python.exe research\\check_fulltext.py
"""

from __future__ import annotations

import html
import json
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import httpx

USER_AGENT = "newsAnalytics-research-probe/0.1 (+https://github.com/Nahid-Quader/newsAnalytics)"
SAMPLE = 3
FRESH_HOURS = 24
FULL_RATIO = 0.8
FULL_MIN_CHARS = 500

FEEDS = [
    ("Prothom Alo", "bn", "https://www.prothomalo.com/feed"),
    ("Prothom Alo English", "en", "https://en.prothomalo.com/feed"),
    ("Ittefaq", "bn", "https://www.ittefaq.com.bd/feed/"),
    ("Janakantha", "bn", "https://www.dailyjanakantha.com/rss/rss.xml"),
    ("bdnews24.com", "en", "https://bdnews24.com/stories.rss"),
    ("bdnews24 Bangla", "bn", "https://bangla.bdnews24.com/stories.rss"),
    ("Bangla Tribune", "bn", "https://www.banglatribune.com/feed/"),
    ("Jago News 24", "bn", "https://www.jagonews24.com/rss/rss.xml"),
    ("Dhaka Post", "bn", "https://www.dhakapost.com/rss/rss.xml"),
    ("Dhaka Tribune", "en", "https://www.dhakatribune.com/feed/"),
    ("Dhaka Tribune Bangla", "bn", "https://bangla.dhakatribune.com/feed/"),
    ("Desh Rupantor", "bn", "https://www.deshrupantor.com/feed/"),
    ("Amar Desh", "bn", "https://www.dailyamardesh.com/feed"),
    ("Ajker Patrika", "bn", "https://www.ajkerpatrika.com/feed"),
    ("Barta24", "bn", "https://barta24.com/rss/rss.xml"),
    ("Channel i Online", "bn", "https://www.channelionline.com/rss.xml"),
    ("NTV", "bn", "https://www.ntvbd.com/rss.xml"),
    ("The Daily Star", "en", "https://www.thedailystar.net/rss.xml"),
    ("The Daily Star Bangla", "bn", "https://bangla.thedailystar.net/rss.xml"),
    ("The Business Standard", "en", "https://www.tbsnews.net/rss.xml"),
    ("The Business Standard Bangla", "bn", "https://www.tbsnews.net/bangla/rss.xml"),
]


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def feed_text(entry) -> str:
    parts = [entry.get("summary", "")] + [c.get("value", "") for c in entry.get("content", [])]
    return max((clean(p) for p in parts), key=len, default="")


def page_text(page: str) -> tuple[str, str]:
    for m in re.finditer(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", page, re.S):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack += x
            elif isinstance(x, dict):
                body = x.get("articleBody")
                if isinstance(body, str) and len(body) > 200:
                    return "jsonld", clean(body)
                stack += list(x.values())
    paras = [clean(p) for p in re.findall(r"<p\b[^>]*>(.*?)</p>", page, re.S)]
    return "p-tags", " ".join(p for p in paras if len(p) > 40)


def entry_time(e) -> datetime | None:
    t = e.get("published_parsed") or e.get("updated_parsed")
    return datetime(*t[:6], tzinfo=timezone.utc) if t else None


def main() -> None:
    client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=25, follow_redirects=True)
    now = datetime.now(timezone.utc)
    results = []
    for name, lang, url in FEEDS:
        print(f"Checking {name} ...", flush=True)
        root = "{0.scheme}://{0.netloc}".format(urlparse(url))
        robots = RobotFileParser()
        try:
            rr = client.get(root + "/robots.txt")
            robots_readable = rr.status_code == 200
            if robots_readable:
                robots.parse(rr.text.splitlines())
        except httpx.HTTPError:
            robots_readable = False
        time.sleep(1)

        rec = {"name": name, "language": lang, "feed_url": url, "robots_readable": robots_readable,
               "checked_at": now.isoformat(), "samples": []}
        try:
            fr = client.get(url)
            parsed = feedparser.parse(fr.content)
        except httpx.HTTPError as exc:
            rec["error"] = str(exc)
            results.append(rec)
            continue
        entries = parsed.entries
        times = [t for t in map(entry_time, entries) if t]
        newest = max(times) if times else None
        rec["entries"] = len(entries)
        rec["newest"] = newest.isoformat() if newest else None
        rec["age_hours"] = round((now - newest).total_seconds() / 3600, 1) if newest else None
        rec["fresh"] = bool(newest and rec["age_hours"] <= FRESH_HOURS)

        for e in entries[:SAMPLE]:
            time.sleep(1.5)
            ft = feed_text(e)
            s = {"title": e.get("title", ""), "link": e.get("link", ""), "feed_chars": len(ft)}
            if robots_readable and not robots.can_fetch(USER_AGENT, s["link"]):
                s["page"] = "disallowed by robots.txt"
            else:
                try:
                    pr = client.get(s["link"])
                    s["page_status"] = pr.status_code
                    if pr.status_code == 200:
                        how, pt = page_text(pr.text)
                        s["page_chars"], s["page_method"] = len(pt), how
                        s["ratio"] = round(len(ft) / len(pt), 2) if pt else None
                except httpx.HTTPError as exc:
                    s["page"] = f"error: {exc}"
            rec["samples"].append(s)

        feed_lens = [s["feed_chars"] for s in rec["samples"]]
        ratios = [s["ratio"] for s in rec["samples"] if s.get("ratio") is not None]
        rec["median_feed_chars"] = statistics.median(feed_lens) if feed_lens else 0
        rec["median_ratio"] = statistics.median(ratios) if ratios else None
        rec["page_fetchable"] = any(s.get("page_status") == 200 for s in rec["samples"])
        rec["full_text"] = bool(rec["median_ratio"] is not None and rec["median_ratio"] >= FULL_RATIO
                                and rec["median_feed_chars"] >= FULL_MIN_CHARS)
        print(f"  fresh={rec['fresh']} age_h={rec['age_hours']} feed_chars={rec['median_feed_chars']} "
              f"ratio={rec['median_ratio']} page_ok={rec['page_fetchable']} FULL={rec['full_text']}", flush=True)
        results.append(rec)

    out = Path(__file__).parent / "output" / f"fulltext_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
