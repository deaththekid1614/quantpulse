#!/usr/bin/env python3
"""
One-off probe: which RSS sources actually return per-ticker news for
NSE-listed equities?

Reads nothing from the DB. Writes nothing. Prints a coverage report for
one ticker across several candidate sources so we can pick the provider
strategy for Stage 7.

Usage:
    .venv/bin/python backend/scripts/probe_news_sources.py
"""
from __future__ import annotations

import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import feedparser  # noqa: E402

UA = "Mozilla/5.0 (X11; Linux x86_64) Quantpulse/0.1 (+https://example.local)"


def fetch(url: str, timeout: float = 10.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def gnews_url(query: str, days: int = 30) -> str:
    """Google News RSS search URL for the given query, scoped to India."""
    q = f"{query} when:{days}d"
    params = {
        "q": q,
        "hl": "en-IN",
        "gl": "IN",
        "ceid": "IN:en",
    }
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def yahoo_url(ticker: str) -> str:
    """Yahoo Finance per-ticker RSS."""
    return f"https://finance.yahoo.com/rss/headline?s={urllib.parse.quote(ticker)}"


def probe(label: str, url: str) -> dict:
    print(f"--- {label} ---")
    print(f"URL: {url}")
    t0 = time.perf_counter()
    try:
        raw = fetch(url)
    except Exception as exc:
        dt = time.perf_counter() - t0
        print(f"  FETCH ERROR ({dt:.2f}s): {type(exc).__name__}: {exc}")
        print()
        return {"label": label, "ok": False, "count": 0}

    dt = time.perf_counter() - t0
    parsed = feedparser.parse(raw)

    entries = parsed.entries or []
    print(f"  fetched {len(raw):,} bytes in {dt:.2f}s")
    print(f"  feed title : {parsed.feed.get('title', '(none)')}")
    print(f"  entries    : {len(entries)}")

    if entries:
        print()
        print("  first 5 entries:")
        for i, e in enumerate(entries[:5], 1):
            title = (e.get("title") or "")[:90]
            pub = e.get("published", "(no date)")[:25]
            src = ""
            if e.get("source") and isinstance(e["source"], dict):
                src = e["source"].get("title", "")
            print(f"    {i}. [{pub}] {src}")
            print(f"       {title}")
    print()
    return {"label": label, "ok": True, "count": len(entries), "entries": entries}


def main() -> int:
    ticker = "TCS.NS"
    symbol = "TCS"
    company = "Tata Consultancy Services"

    print("=" * 74)
    print(f"Probing news sources for {ticker} ({company})")
    print("=" * 74)
    print()

    results = []

    # 1. Google News RSS — quote the full company name for precision
    results.append(probe(
        "Google News RSS — full company name",
        gnews_url(f'"{company}"', days=30),
    ))

    # 2. Google News RSS — symbol + India
    results.append(probe(
        "Google News RSS — symbol + India",
        gnews_url(f"{symbol} India stock", days=30),
    ))

    # 3. Yahoo Finance per-ticker RSS
    results.append(probe(
        "Yahoo Finance RSS",
        yahoo_url(ticker),
    ))

    print("=" * 74)
    print("Summary")
    print("=" * 74)
    for r in results:
        status = "OK " if r["ok"] else "ERR"
        print(f"  [{status}] {r['label']:45s}  {r['count']:3d} entries")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
