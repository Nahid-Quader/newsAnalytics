"""Probe candidate Bangladeshi news sources for usable, permitted access methods.

For each publisher this script:
  1. Fetches robots.txt (records Sitemap: entries and whether our paths are allowed).
  2. Fetches the homepage and looks for advertised RSS/Atom feeds (<link rel="alternate">).
  3. Tries a small set of common feed paths.
  4. Parses every candidate with feedparser and records which article fields are present.
  5. Checks sitemaps advertised in robots.txt for Google News sitemap markup.

Requests are sequential per host with a delay, and use an identifying User-Agent.
Results are written to research/output/ as JSON (raw evidence) and Markdown (summary).

Usage:
    .venv\\Scripts\\python.exe research\\probe_sources.py [--only domain1,domain2]
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import httpx

USER_AGENT = "newsAnalytics-research-probe/0.1 (+https://github.com/Nahid-Quader/newsAnalytics)"
REQUEST_DELAY_S = 1.0
TIMEOUT_S = 20.0

COMMON_FEED_PATHS = [
    "/rss.xml",
    "/rss",
    "/feed",
    "/feed/",
    "/rss/rss.xml",
    "/stories.rss",
    "/feed.xml",
    "/atom.xml",
]
COMMON_SITEMAP_PATHS = ["/sitemap.xml", "/news-sitemap.xml", "/sitemap-news.xml", "/sitemap_index.xml"]

# Starting list from the project brief, plus additional candidates to reach 30+.
# Homepages are candidates to verify, not claims that they work.
SOURCES = [
    ("Prothom Alo", "https://www.prothomalo.com", "bn"),
    ("Prothom Alo English", "https://en.prothomalo.com", "en"),
    ("Bangladesh Pratidin", "https://www.bd-pratidin.com", "bn"),
    ("Ittefaq", "https://www.ittefaq.com.bd", "bn"),
    ("Kaler Kantho", "https://www.kalerkantho.com", "bn"),
    ("Jugantor", "https://www.jugantor.com", "bn"),
    ("Samakal", "https://samakal.com", "bn"),
    ("Janakantha", "https://www.dailyjanakantha.com", "bn"),
    ("Naya Diganta", "https://www.dailynayadiganta.com", "bn"),
    ("Daily Inqilab", "https://dailyinqilab.com", "bn"),
    ("Manab Zamin", "https://mzamin.com", "bn"),
    ("bdnews24.com", "https://bdnews24.com", "en"),
    ("bdnews24 Bangla", "https://bangla.bdnews24.com", "bn"),
    ("Bangla Tribune", "https://www.banglatribune.com", "bn"),
    ("Jago News 24", "https://www.jagonews24.com", "bn"),
    ("Dhaka Post", "https://www.dhakapost.com", "bn"),
    ("Risingbd", "https://www.risingbd.com", "bn"),
    ("The Daily Star", "https://www.thedailystar.net", "en"),
    ("The Daily Star Bangla", "https://bangla.thedailystar.net", "bn"),
    ("Dhaka Tribune", "https://www.dhakatribune.com", "en"),
    ("Dhaka Tribune Bangla", "https://bangla.dhakatribune.com", "bn"),
    ("New Age", "https://www.newagebd.net", "en"),
    ("The Business Standard", "https://www.tbsnews.net", "en"),
    ("The Business Standard Bangla", "https://www.tbsnews.net/bangla", "bn"),
    ("The Financial Express", "https://thefinancialexpress.com.bd", "en"),
    ("Kalbela", "https://www.kalbela.com", "bn"),
    ("Desh Rupantor", "https://www.deshrupantor.com", "bn"),
    ("Amar Desh", "https://www.dailyamardesh.com", "bn"),
    ("Bonik Barta", "https://bonikbarta.com", "bn"),
    ("Ajker Patrika", "https://www.ajkerpatrika.com", "bn"),
    ("Bhorer Kagoj", "https://www.bhorerkagoj.com", "bn"),
    ("Dainik Bangla", "https://www.dainikbangla.com.bd", "bn"),
    ("banglanews24.com", "https://www.banglanews24.com", "bn"),
    ("Barta24", "https://barta24.com", "bn"),
    ("Somoy News", "https://www.somoynews.tv", "bn"),
    ("Jamuna TV", "https://jamuna.tv", "bn"),
    ("Channel i Online", "https://www.channelionline.com", "bn"),
    ("NTV", "https://www.ntvbd.com", "bn"),
    ("Daily Sun", "https://www.daily-sun.com", "en"),
    ("Daily Observer", "https://www.observerbd.com", "en"),
    ("Bangladesh Post", "https://bangladeshpost.net", "en"),
    ("BSS (Bangla)", "https://www.bssnews.net/bangla", "bn"),
    ("BSS (English)", "https://www.bssnews.net", "en"),
    ("UNB", "https://unb.com.bd", "en"),
]

FEED_LINK_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
ATTR_RE = re.compile(r'(\w[\w-]*)\s*=\s*["\']([^"\']*)["\']')
BENGALI_RE = re.compile(r"[ঀ-৿]")


@dataclass
class FeedResult:
    url: str
    status: int | None = None
    content_type: str | None = None
    ok: bool = False
    robots_allowed: bool | None = None
    entries: int = 0
    feed_title: str | None = None
    bozo: str | None = None
    fields: dict[str, int] = field(default_factory=dict)  # field -> count of entries having it
    newest: str | None = None
    oldest: str | None = None
    bengali_titles: int = 0
    sample_titles: list[str] = field(default_factory=list)
    sample_links: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class SitemapResult:
    url: str
    status: int | None = None
    is_index: bool = False
    is_news: bool = False
    url_count: int = 0
    child_sample: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class SourceResult:
    name: str
    homepage: str
    language: str
    homepage_status: int | None = None
    final_url: str | None = None
    homepage_error: str | None = None
    robots_status: int | None = None
    robots_sitemaps: list[str] = field(default_factory=list)
    advertised_feeds: list[str] = field(default_factory=list)
    feeds: list[FeedResult] = field(default_factory=list)
    sitemaps: list[SitemapResult] = field(default_factory=list)
    probed_at: str = ""

    @property
    def working_feeds(self) -> list[FeedResult]:
        return [f for f in self.feeds if f.ok]


class PoliteClient:
    def __init__(self) -> None:
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            timeout=TIMEOUT_S,
            follow_redirects=True,
        )
        self.last_request: dict[str, float] = {}

    def get(self, url: str) -> httpx.Response:
        host = urlparse(url).netloc
        wait = REQUEST_DELAY_S - (time.monotonic() - self.last_request.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        try:
            return self.client.get(url)
        finally:
            self.last_request[host] = time.monotonic()


def find_advertised_feeds(html: str, base: str) -> list[str]:
    found = []
    for tag in FEED_LINK_RE.findall(html):
        attrs = {k.lower(): v for k, v in ATTR_RE.findall(tag)}
        if "alternate" in attrs.get("rel", "").lower() and (
            "rss" in attrs.get("type", "").lower() or "atom" in attrs.get("type", "").lower()
        ):
            href = attrs.get("href")
            if href:
                found.append(urljoin(base, href))
    return list(dict.fromkeys(found))


def entry_time(e) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = e.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def probe_feed(pc: PoliteClient, url: str, robots: RobotFileParser | None) -> FeedResult:
    res = FeedResult(url=url)
    if robots is not None:
        res.robots_allowed = robots.can_fetch(USER_AGENT, url)
    try:
        r = pc.get(url)
    except httpx.HTTPError as exc:
        res.error = f"{type(exc).__name__}: {exc}"
        return res
    res.status = r.status_code
    res.content_type = r.headers.get("content-type")
    if r.status_code != 200:
        return res
    parsed = feedparser.parse(r.content)
    if parsed.bozo:
        res.bozo = str(parsed.bozo_exception)[:200]
    entries = parsed.entries
    res.entries = len(entries)
    res.feed_title = parsed.feed.get("title")
    if not entries:
        return res
    res.ok = True
    checks = {
        "title": lambda e: bool(e.get("title")),
        "link": lambda e: bool(e.get("link")),
        "published": lambda e: bool(e.get("published") or e.get("updated")),
        "author": lambda e: bool(e.get("author")),
        "summary": lambda e: bool(e.get("summary")),
        "content": lambda e: bool(e.get("content")),
        "categories": lambda e: bool(e.get("tags")),
        "image": lambda e: bool(e.get("media_content") or e.get("media_thumbnail") or e.get("enclosures")),
        "guid": lambda e: bool(e.get("id")),
    }
    res.fields = {k: sum(1 for e in entries if fn(e)) for k, fn in checks.items()}
    times = [t for t in (entry_time(e) for e in entries) if t]
    if times:
        res.newest = max(times).isoformat()
        res.oldest = min(times).isoformat()
    titles = [unicodedata.normalize("NFC", e.get("title", "")) for e in entries]
    res.bengali_titles = sum(1 for t in titles if BENGALI_RE.search(t))
    res.sample_titles = titles[:3]
    res.sample_links = [e.get("link", "") for e in entries[:3]]
    return res


def probe_sitemap(pc: PoliteClient, url: str) -> SitemapResult:
    res = SitemapResult(url=url)
    try:
        r = pc.get(url)
    except httpx.HTTPError as exc:
        res.error = f"{type(exc).__name__}: {exc}"
        return res
    res.status = r.status_code
    if r.status_code != 200:
        return res
    text = r.text[:2_000_000]
    res.is_index = "<sitemapindex" in text
    res.is_news = "sitemap-news" in text or "<news:news" in text
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)
    res.url_count = len(locs)
    res.child_sample = locs[:5]
    return res


def probe_source(pc: PoliteClient, name: str, homepage: str, lang: str) -> SourceResult:
    sr = SourceResult(name=name, homepage=homepage, language=lang,
                      probed_at=datetime.now(timezone.utc).isoformat())
    parsed = urlparse(homepage)
    root = f"{parsed.scheme}://{parsed.netloc}"

    robots = RobotFileParser()
    try:
        r = pc.get(root + "/robots.txt")
        sr.robots_status = r.status_code
        if r.status_code == 200:
            robots.parse(r.text.splitlines())
            sr.robots_sitemaps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", r.text)
        else:
            robots = None
    except httpx.HTTPError:
        robots = None

    html = ""
    try:
        r = pc.get(homepage)
        sr.homepage_status = r.status_code
        sr.final_url = str(r.url)
        if r.status_code == 200:
            html = r.text
    except httpx.HTTPError as exc:
        sr.homepage_error = f"{type(exc).__name__}: {exc}"

    sr.advertised_feeds = find_advertised_feeds(html, sr.final_url or homepage) if html else []
    base = (sr.final_url or homepage).rstrip("/")
    candidates = list(dict.fromkeys(sr.advertised_feeds + [base + p for p in COMMON_FEED_PATHS]))
    for url in candidates:
        fr = probe_feed(pc, url, robots)
        sr.feeds.append(fr)
        # Stop trying guessed paths once two working feeds are found.
        if len(sr.working_feeds) >= 2 and url not in sr.advertised_feeds:
            break

    sitemap_urls = list(dict.fromkeys(sr.robots_sitemaps[:6] or [root + p for p in COMMON_SITEMAP_PATHS]))
    for url in sitemap_urls:
        sr.sitemaps.append(probe_sitemap(pc, url))
    return sr


def write_reports(results: list[SourceResult], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw = [asdict(r) for r in results]
    (out_dir / f"probe_{stamp}.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# Source probe results ({stamp})", "",
             "| Source | Lang | Home | Working feeds | Best feed | Entries | Fields (best feed) | News sitemap |",
             "|---|---|---|---|---|---|---|---|"]
    for r in results:
        best = max(r.working_feeds, key=lambda f: f.entries, default=None)
        fields = ""
        if best:
            fields = ", ".join(f"{k}:{v}" for k, v in best.fields.items() if v)
        news_sm = any(s.is_news for s in r.sitemaps)
        lines.append(
            f"| {r.name} | {r.language} | {r.homepage_status or r.homepage_error or '-'} | "
            f"{len(r.working_feeds)} | {best.url if best else '-'} | {best.entries if best else 0} | "
            f"{fields or '-'} | {'yes' if news_sm else 'no'} |"
        )
    (out_dir / f"probe_{stamp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_dir / f'probe_{stamp}.json'} and .md")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated substrings of homepage to probe")
    args = ap.parse_args()
    sources = SOURCES
    if args.only:
        keys = [k.strip() for k in args.only.split(",")]
        sources = [s for s in SOURCES if any(k in s[1] for k in keys)]

    pc = PoliteClient()
    results = []
    for name, home, lang in sources:
        print(f"Probing {name} ({home}) ...", flush=True)
        sr = probe_source(pc, name, home, lang)
        print(f"  home={sr.homepage_status or sr.homepage_error} feeds={len(sr.working_feeds)} "
              f"sitemaps_news={any(s.is_news for s in sr.sitemaps)}", flush=True)
        results.append(sr)
    write_reports(results, Path(__file__).parent / "output")


if __name__ == "__main__":
    main()
