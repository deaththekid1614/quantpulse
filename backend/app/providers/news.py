"""
RSS-based news provider.

Implements the `NewsProvider` interface from `providers/base.py`. Fetches
per-ticker news from two free sources:

  1. Google News RSS search  — quoted company name + symbol queries
  2. Yahoo Finance RSS       — per-ticker feed

Merges, normalises, and dedupes by cleaned title. No API keys, no rate
limits. Reads only; never writes.

Every network call is wrapped so one source failing does not lose the
others. If all sources fail, returns an empty list.
"""
from __future__ import annotations

import logging
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser

from app.providers.base import NewsArticle, NewsProvider

log = logging.getLogger(__name__)

UA = "Mozilla/5.0 (X11; Linux x86_64) Quantpulse/0.1"
DEFAULT_TIMEOUT = 10.0
DEFAULT_WINDOW_DAYS = 30

# Titles from Google News come formatted as "<headline> - <Publisher>".
# Strip the trailing " - Publisher" so the same story from two sources
# dedupes cleanly.
_PUBLISHER_SUFFIX_RE = re.compile(r"\s+[-–—]\s+[^-–—]{2,60}$")

# Non-alphanumeric characters collapse to a space during dedup hashing.
_NORMALISE_RE = re.compile(r"[^a-z0-9 ]+")


@dataclass(frozen=True, slots=True)
class _Raw:
    """Internal record produced by one source fetch, before dedup."""
    title: str
    url: str
    source: str
    published_at: datetime
    summary: str = ""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _normalise_title(title: str) -> str:
    """Lowercase, strip publisher suffix, collapse punctuation."""
    t = title.strip()
    t = _PUBLISHER_SUFFIX_RE.sub("", t)
    t = t.lower()
    t = _NORMALISE_RE.sub(" ", t)
    t = " ".join(t.split())
    return t[:120]


def _parse_published(entry) -> datetime | None:
    """Feedparser gives either published_parsed (UTC struct) or nothing."""
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed is None:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _extract_source(entry) -> str:
    """Publisher name from feedparser's <source> tag, else URL domain."""
    src = getattr(entry, "source", None)
    if isinstance(src, dict):
        title = (src.get("title") or "").strip()
        if title:
            return title
    # Fallback: derive from the URL's hostname.
    link = getattr(entry, "link", "") or ""
    try:
        host = urllib.parse.urlparse(link).hostname or ""
    except ValueError:
        host = ""
    return host.replace("www.", "") or "Unknown"


def _fetch_bytes(url: str, timeout: float) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as exc:
        log.warning("news fetch failed %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# provider
# ---------------------------------------------------------------------------

class RSSNewsProvider(NewsProvider):
    """
    Stateless RSS news provider.

    `name_map` maps a Yahoo ticker ("TCS.NS") to the company's full name
    ("Tata Consultancy Services"). It is used to build higher-precision
    Google News queries. When a ticker is missing from the map, only the
    symbol-based query is used.

    The provider performs no persistence and holds no cross-call state.
    """

    def __init__(
        self,
        name_map: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._name_map = name_map or {}
        self._timeout = timeout

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def get_news(
        self,
        ticker: str,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[NewsArticle]:
        raw: list[_Raw] = []

        for query in self._google_queries(ticker):
            raw.extend(self._fetch_google_news(query))

        raw.extend(self._fetch_yahoo(ticker))

        seen: set[str] = set()
        deduped: list[_Raw] = []
        for item in raw:
            key = _normalise_title(item.title)
            if not key or key in seen:
                continue
            if since is not None and item.published_at < since:
                continue
            seen.add(key)
            deduped.append(item)

        deduped.sort(key=lambda r: r.published_at, reverse=True)
        deduped = deduped[:limit]

        return [
            NewsArticle(
                ticker=ticker,
                title=r.title,
                url=r.url,
                source=r.source,
                published_at=r.published_at,
                body="",
                summary=r.summary,
            )
            for r in deduped
        ]

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def _google_queries(self, ticker: str) -> list[str]:
        symbol = ticker.removesuffix(".NS").removesuffix(".BO")
        queries: list[str] = []

        name = self._name_map.get(ticker)
        if name:
            queries.append(f'"{name}"')
        queries.append(f'"{symbol}" stock India')

        return queries

    @staticmethod
    def _gnews_url(query: str, days: int = DEFAULT_WINDOW_DAYS) -> str:
        params = {
            "q": f"{query} when:{days}d",
            "hl": "en-IN",
            "gl": "IN",
            "ceid": "IN:en",
        }
        return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)

    @staticmethod
    def _yahoo_url(ticker: str) -> str:
        return f"https://finance.yahoo.com/rss/headline?s={urllib.parse.quote(ticker)}"

    # ------------------------------------------------------------------
    # fetchers
    # ------------------------------------------------------------------

    def _fetch_google_news(self, query: str) -> list[_Raw]:
        url = self._gnews_url(query)
        body = _fetch_bytes(url, self._timeout)
        if body is None:
            return []

        parsed = feedparser.parse(body)
        out: list[_Raw] = []
        for e in parsed.entries or []:
            title = (getattr(e, "title", "") or "").strip()
            link  = (getattr(e, "link", "") or "").strip()
            if not title or not link:
                continue
            published = _parse_published(e)
            if published is None:
                continue
            summary = (getattr(e, "summary", "") or "").strip()
            out.append(_Raw(
                title=title,
                url=link,
                source=_extract_source(e),
                published_at=published,
                summary=summary,
            ))
        return out

    def _fetch_yahoo(self, ticker: str) -> list[_Raw]:
        url = self._yahoo_url(ticker)
        body = _fetch_bytes(url, self._timeout)
        if body is None:
            return []

        parsed = feedparser.parse(body)
        out: list[_Raw] = []
        for e in parsed.entries or []:
            title = (getattr(e, "title", "") or "").strip()
            link  = (getattr(e, "link", "") or "").strip()
            if not title or not link:
                continue
            published = _parse_published(e)
            if published is None:
                continue
            summary = (getattr(e, "summary", "") or "").strip()
            out.append(_Raw(
                title=title,
                url=link,
                source=_extract_source(e) or "Yahoo Finance",
                published_at=published,
                summary=summary,
            ))
        return out


__all__ = ["RSSNewsProvider"]
