# Source discovery report — first pass

Probed: 2026-10-23 from a corporate network, using
`research/probe_sources.py` (identifying User-Agent, 1 s delay per host, robots.txt checked).
Raw evidence: `research/output/probe_20261023T183115Z.json`.

**This is a single snapshot.** "Working" means the endpoint returned parseable items with a
recent timestamp on this date. Sitemap freshness has not been verified yet.

## Final selection: primary sources (fresh + full text in feed)

Criteria, checked with `research/check_fulltext.py` on 2026-10-23
(evidence: `research/output/fulltext_20261023T193309Z.json`):
- **Fresh:** newest feed item ≤ 24 h old.
- **Full text:** median feed text ≥ 500 chars and ≥ 80 % of the article body on the
  publisher's page (JSON-LD `articleBody` or `<p>` text), over the 3 newest items.

| Publisher | Lang | Feed URL | Items in feed | Feed text vs. page | Notes |
|---|---|---|---|---|---|
| Prothom Alo | bn | https://www.prothomalo.com/feed | 37–43 | 98 % (median 1,244 chars) | Body is in `content` as HTML; strip tags |
| bdnews24 Bangla | bn | https://bangla.bdnews24.com/stories.rss | 50 | 101 % (median 2,101 chars) | |
| bdnews24.com | en | https://bdnews24.com/stories.rss | 50 | 99 % (median 3,818 chars) | |
| Prothom Alo English | en | https://en.prothomalo.com/feed | **1–2** | 111 % (1 item) | Feed window is tiny: must poll often or articles are missed |

**Only 4 sources (3 robust) meet both criteria.** This is far below the 30-source goal.

### Near misses

| Group | Sources | Why excluded | Possible path |
|---|---|---|---|
| Full text but stale | Daily Star EN (newest 2026-06), Daily Star BN (2026-02), TBS EN (2021), TBS BN (2025) | Feed not updated | News sitemap + feed check later; the feeds may be revived |
| Fresh, excerpt only, article page fetchable (robots.txt allows) | Janakantha, Amar Desh, Ajker Patrika, Barta24, Channel i Online, NTV (newest item 31 h old) | Feed has 0–400 chars | Fetch the article page for the body — needs a policy decision |
| Fresh, excerpt only, article page blocked (403) | Ittefaq, Bangla Tribune, Jago News 24, Dhaka Post, Dhaka Tribune EN/BN, Desh Rupantor | No legitimate way to get the body | Metadata + excerpt only, or ask the publisher |

Correction to the first pass below: Prothom Alo's feed *does* carry full text; the first
probe only read the first `content` value and reported it as empty.

## Summary (first pass, all candidates)

| Status | Count |
|---|---|
| Candidates probed | 44 |
| Working RSS/Atom feed, fresh (items from last ~24 h) | 17 |
| Feed exists but stale (newest item weeks–years old) | 4 (Daily Star EN/BN, TBS EN/BN) |
| No feed, but a Google News sitemap found | 4 (Jugantor, Bonik Barta, Bhorer Kagoj, Dainik Bangla); plus en.bonikbarta.com found as a bonus |
| Blocked by Cloudflare bot challenge (HTTP 403 "Just a moment…") | 14 |
| Other / needs investigation | 5 |

## A. Working, fresh RSS/Atom feeds

| Publisher | Lang | Feed URL | Items | Fields present | Text in feed |
|---|---|---|---|---|---|
| Prothom Alo | bn | https://www.prothomalo.com/feed | 43 | title, link, date, author, categories, image | full text (see Final selection) |
| Prothom Alo English | en | https://en.prothomalo.com/feed | 2 | title, link, date, author, categories, image | full text, but only 1–2 items |
| Ittefaq | bn | https://www.ittefaq.com.bd/feed/ | 100 | title, link, date, author, summary, categories | summary ~450 chars |
| Janakantha | bn | https://www.dailyjanakantha.com/rss/rss.xml | 30 | title, link, date, summary | summary |
| bdnews24.com | en | https://bdnews24.com/stories.rss | 50 | all incl. author, categories, image | ~1,700 chars (best) |
| bdnews24 Bangla | bn | https://bangla.bdnews24.com/stories.rss | 50 | all incl. author, categories, image | ~1,700 chars (best) |
| Bangla Tribune | bn | https://www.banglatribune.com/feed/ | 100 | title, link, date, author, summary, categories | summary |
| Jago News 24 | bn | https://www.jagonews24.com/rss/rss.xml | 100 | title, link, date, summary, categories | short summary (~60 chars) |
| Dhaka Post | bn | https://www.dhakapost.com/rss/rss.xml | 20 | title, link, date, image | none |
| Dhaka Tribune | en | https://www.dhakatribune.com/feed/ | 100 | title, link, date, summary, categories | summary |
| Dhaka Tribune Bangla | bn | https://bangla.dhakatribune.com/feed/ | 100 | title, link, date, summary, categories | summary |
| Desh Rupantor | bn | https://www.deshrupantor.com/feed/ | 100 | title, link, date, author, summary, categories | summary |
| Amar Desh | bn | https://www.dailyamardesh.com/feed | 20 | title, link, date, summary, content, categories, image | ~330 chars |
| Ajker Patrika | bn | https://www.ajkerpatrika.com/feed | 20 | title, link, date, summary, categories, image | summary |
| Barta24 | bn | https://barta24.com/rss/rss.xml | 120 | title, link, date, summary, image | summary |
| Channel i Online | bn | https://www.channelionline.com/rss.xml | 30 | title, link, date, summary, categories | summary |
| NTV | bn | https://www.ntvbd.com/rss.xml | 10 | title, link, date, author, summary | summary (newest item ~1 day old) |

Notes: Ittefaq, Bangla Tribune, Dhaka Tribune (EN/BN) and Desh Rupantor return 403 for
the homepage and robots.txt but serve the feed. Their robots.txt could not be read, so
permission is **unconfirmed**; check their terms before production use.

## B. Stale feeds → use news sitemap instead

| Publisher | Feed newest item | Alternative |
|---|---|---|
| The Daily Star | 2026-06-01 (8 items) | news sitemap advertised in robots.txt |
| The Daily Star Bangla | 2026-02-04 (1 item) | to investigate |
| The Business Standard | 2021-11-12 | news sitemap advertised in robots.txt |
| TBS Bangla | 2025-10-17 | news sitemap advertised in robots.txt |

## C. No feed, Google News sitemap available

Jugantor (`/news_sitemap.xml`), Bonik Barta (`/sitemap.xml`, also en.bonikbarta.com),
Bhorer Kagoj (`bhorerkagoj.net/news_sitemap.xml`), Dainik Bangla (`/news-sitemap.xml`).
News sitemaps usually give URL, title, publication date and language only. Freshness not yet
verified.

## D. Blocked by Cloudflare bot challenge (not pursued)

Bangladesh Pratidin, Kaler Kantho, Samakal (feeds; sitemap.xml did load), Daily Inqilab, Risingbd,
New Age, Kalbela, banglanews24.com, Somoy News, Jamuna TV, Daily Sun, Daily Observer, BSS (BN/EN).

Responses carry `cf-mitigated: challenge`. Solving or evading the challenge would be bypassing
an access control, which the project brief rules out. Legitimate options:
- re-test from a different (non-corporate) network — the block may depend on IP reputation;
- ask publishers for feed access / allow-listing;
- use GDELT for metadata-only coverage (see below).

## E. Needs investigation

- **Naya Diganta**: TLS certificate hostname mismatch on `www.dailynayadiganta.com`; try other hostnames.
- **Manab Zamin**: no feed; `sitemap.php` exists (not a news sitemap).
- **The Financial Express**, **Bangladesh Post**: generic sitemap only.
- **UNB**: no feed or sitemap found at common paths.

## F. GDELT DOC 2.0 API

`https://api.gdeltproject.org/api/v2/doc/doc?query=sourcecountry:bangladesh&mode=artlist&format=json`

- Works, but rate-limited to **1 request / 5 s** (got HTTP 429 when calling faster).
- Last 24 h: **94 articles from 16 domains** (69 Bengali, 25 English). Fields: url, title,
  domain, language, seendate, image, sourcecountry. **No summary, body or author.**
- Coverage is uneven; covers some sites we can't reach directly (Naya Diganta, Manab Zamin)
  but misses big ones (Prothom Alo, Jugantor).
- Role: discovery and cross-check layer, not a primary source.

## Key findings for the design

1. **~24–25 sources look reachable** through feeds + news sitemaps (17 fresh feeds, 3 stale feeds
   with a news sitemap, 4–5 sitemap-only), still short of 30 verified. The 14 Cloudflare-blocked sites are the main gap.
2. **Feeds rarely carry article text.** Only bdnews24 gives substantial text (~1,700 chars).
   Most give a title and short summary. NLP phases will need article pages fetched — a policy
   decision (robots.txt, terms, storage of full text) to make before Phase 2.
3. Connector types needed in Phase 1: `rss` (17 sources), `news_sitemap` (~9), `gdelt` (optional).
4. Windows console needs `PYTHONIOENCODING=utf-8` to print Bengali; storage is unaffected.

## Next steps

- Verify news-sitemap freshness and fields for the sitemap sources.
- Re-run the probe from a non-corporate network to see whether the 403s persist.
- Check terms of use for each source in sections A–C.
- Repeat the probe over several days to measure update frequency and feed window size.
