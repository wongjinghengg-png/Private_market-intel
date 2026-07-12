"""
Scraper module — pulls news from Google News RSS and optionally NewsAPI.
Accepts a from_date to scrape from, enabling catch-up after gaps.
Returns raw articles (title, url, source, published_date, snippet).
"""

import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

import feedparser
import requests

from config import (
    MAX_ARTICLES_PER_COMPANY,
    NEWS_API_KEY,
    REQUEST_DELAY_SECONDS,
)


def scrape_company(company: dict, from_date: str, use_newsapi: bool = True) -> list[dict]:
    """Scrape news for a single company from from_date to today, deduplicated.

    Set use_newsapi=False to use only the free Google News RSS source — used by the
    broad movers scrape so its many queries don't burn the limited NewsAPI quota.
    """
    all_articles = []
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # Source 1: Google News RSS (free, no key needed)
    all_articles.extend(_google_news_rss(company, from_date, today))

    # Source 2: NewsAPI (optional, richer results — max 30 days back; quota-limited)
    if use_newsapi and NEWS_API_KEY:
        all_articles.extend(_newsapi_search(company, from_date, today))

    # Deduplicate by URL
    seen_urls = set()
    unique = []
    for a in all_articles:
        url_key = a["url"].split("?")[0].rstrip("/").lower()
        if url_key not in seen_urls:
            seen_urls.add(url_key)
            unique.append(a)

    # Sort by date descending, cap results
    unique.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    return unique[:MAX_ARTICLES_PER_COMPANY]


# ── Google News RSS ──────────────────────────────────────────────────

def _google_news_rss(company: dict, from_date: str, to_date: str) -> list[dict]:
    """Pull from Google News RSS. Chunks into 30-day windows for large ranges."""
    articles = []
    queries = [company["name"]] + company.get("aliases", [])

    # Build date windows (Google News works best in <=30-day chunks)
    windows = _build_date_windows(from_date, to_date, max_days=30)

    for query in queries[:2]:  # Limit to name + first alias
        for window_start, window_end in windows:
            # Encode only the company name, not the date operators
            encoded_name = urllib.parse.quote(query)
            url = (
                f"https://news.google.com/rss/search?"
                f"q={encoded_name}+after:{window_start}+before:{window_end}"
                f"&hl=en&gl=US&ceid=US:en"
            )
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    pub_date = _parse_date(entry.get("published", ""))
                    articles.append({
                        "title": _clean_title(entry.get("title", "")),
                        "url": entry.get("link", ""),
                        "source": _extract_source(entry.get("title", "")),
                        "published_date": pub_date,
                        "snippet": entry.get("summary", "")[:300],
                        "company": company["name"],
                        "raw_source": "google_news",
                    })
            except Exception as e:
                print(f"  [WARN] Google News error for '{query}' ({window_start}→{window_end}): {e}")

            time.sleep(REQUEST_DELAY_SECONDS)

    return articles


# ── NewsAPI ──────────────────────────────────────────────────────────

def _newsapi_search(company: dict, from_date: str, to_date: str) -> list[dict]:
    """Pull from NewsAPI.org (requires free API key). Free tier: 30 days back max."""
    articles = []

    # NewsAPI free tier only goes back ~30 days
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    effective_from = max(from_date, thirty_days_ago)

    query = f'"{company["name"]}"'
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": effective_from,
        "to": to_date,
        "sortBy": "publishedAt",
        "pageSize": 10,
        "language": "en",
        "apiKey": NEWS_API_KEY,
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("articles", []):
            articles.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source": item.get("source", {}).get("name", "Unknown"),
                "published_date": _parse_date(item.get("publishedAt", "")),
                "snippet": (item.get("description") or "")[:300],
                "company": company["name"],
                "raw_source": "newsapi",
            })
    except Exception as e:
        print(f"  [WARN] NewsAPI error for '{company['name']}': {e}")

    time.sleep(REQUEST_DELAY_SECONDS)
    return articles


# ── Helpers ──────────────────────────────────────────────────────────

def _build_date_windows(from_date: str, to_date: str, max_days: int = 30) -> list[tuple[str, str]]:
    """Split a date range into chunks of max_days for API-friendly requests."""
    start = datetime.strptime(from_date, "%Y-%m-%d")
    end = datetime.strptime(to_date, "%Y-%m-%d")

    windows = []
    current = start
    while current < end:
        window_end = min(current + timedelta(days=max_days), end)
        windows.append((current.strftime("%Y-%m-%d"), window_end.strftime("%Y-%m-%d")))
        current = window_end

    return windows


def _clean_title(title: str) -> str:
    """Strip source suffix from Google News titles (e.g. ' - Reuters')."""
    if " - " in title:
        return title.rsplit(" - ", 1)[0].strip()
    return title.strip()


def _extract_source(title: str) -> str:
    """Extract source name from Google News title suffix."""
    if " - " in title:
        return title.rsplit(" - ", 1)[1].strip()
    return "Unknown"


def _parse_date(date_str: str) -> Optional[str]:
    """Try to parse various date formats into YYYY-MM-DD."""
    if not date_str:
        return datetime.utcnow().strftime("%Y-%m-%d")

    for fmt in [
        "%a, %d %b %Y %H:%M:%S %Z",     # RSS format
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%SZ",             # ISO
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ]:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return datetime.utcnow().strftime("%Y-%m-%d")
