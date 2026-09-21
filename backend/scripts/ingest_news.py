#!/usr/bin/env python3
"""
Populate the `news_articles` table from RSS sources.

For each security:
  1. Fetch articles via RSSNewsProvider (Google News + Yahoo Finance)
  2. Compute sentiment, relevance, importance via app.nlp.sentiment
  3. Drop any article with relevance < MIN_RELEVANCE (default 0.30)
  4. Upsert into news_articles — deduplicated on URL, scores refreshed
     on every run

Usage:
    python backend/scripts/ingest_news.py --ticker TCS.NS --limit 50
    python backend/scripts/ingest_news.py --universe nifty50 --limit 30

Re-running is safe. Articles already in the DB have their scores and
summary refreshed in place; new articles are inserted.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert  # noqa: E402

from app.core.log_config import get_logger, setup_logging  # noqa: E402
from app.db.models import IngestLog, NewsArticleRow, Security  # noqa: E402
from app.db.session import init_db, session_scope  # noqa: E402
from app.nlp.sentiment import (  # noqa: E402
    analyze_sentiment,
    compute_importance,
    compute_relevance,
)
from app.providers.news import RSSNewsProvider  # noqa: E402

setup_logging("INFO")
log = get_logger("quantpulse.ingest.news")

DEFAULT_WINDOW_DAYS = 30
DEFAULT_LIMIT = 50
MIN_RELEVANCE = 0.30
BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def load_securities(ticker_filter: str | None) -> list[dict]:
    """Return a list of dicts with id, ticker, symbol, name, sector."""
    with session_scope() as db:
        stmt = select(Security.id, Security.ticker, Security.symbol, Security.name, Security.sector)
        if ticker_filter:
            stmt = stmt.where(Security.ticker == ticker_filter)
        stmt = stmt.order_by(Security.id)
        rows = db.execute(stmt).all()
    return [
        {"id": r.id, "ticker": r.ticker, "symbol": r.symbol,
         "name": r.name, "sector": r.sector}
        for r in rows
    ]


def _open_log(ticker: str) -> int:
    with session_scope() as db:
        row = IngestLog(ticker=ticker, status="running", started_at=datetime.now(timezone.utc))
        db.add(row)
        db.flush()
        return row.id


def _close_log(log_id: int, status: str, added: int = 0, updated: int = 0,
               error: str | None = None) -> None:
    with session_scope() as db:
        row = db.get(IngestLog, log_id)
        if row is None:
            return
        row.status = status
        row.rows_added = added
        row.rows_updated = updated
        row.error = error
        row.finished_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------

def upsert_articles(security_id: int, articles: list[dict]) -> tuple[int, int]:
    """
    Insert-or-update news articles for ONE security. Deduplication is on
    the composite key (security_id, url) — the same underlying article can
    exist under multiple tickers if it legitimately mentions them.

    Returns (rows_added, rows_updated).
    """
    if not articles:
        return 0, 0

    urls = [a["url"] for a in articles]

    # How many of these URLs already exist for THIS security?
    with session_scope() as db:
        existing_count = db.execute(
            select(func.count(NewsArticleRow.id)).where(
                NewsArticleRow.security_id == security_id,
                NewsArticleRow.url.in_(urls),
            )
        ).scalar_one()

    rows = [
        {
            "security_id": security_id,
            "title": a["title"],
            "url": a["url"],
            "source": a["source"],
            "published_at": a["published_at"],
            "summary": a.get("summary") or None,
            "body": None,
            "sentiment_score": a["sentiment_score"],
            "sentiment_label": a["sentiment_label"],
            "relevance_score": a["relevance_score"],
            "importance_score": a["importance_score"],
            "fetched_at": datetime.now(timezone.utc),
        }
        for a in articles
    ]

    with session_scope() as db:
        for i in range(0, len(rows), BATCH_SIZE):
            chunk = rows[i : i + BATCH_SIZE]
            stmt = sqlite_insert(NewsArticleRow).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["security_id", "url"],
                set_={
                    "title":            stmt.excluded.title,
                    "source":           stmt.excluded.source,
                    "published_at":     stmt.excluded.published_at,
                    "summary":          stmt.excluded.summary,
                    "sentiment_score":  stmt.excluded.sentiment_score,
                    "sentiment_label":  stmt.excluded.sentiment_label,
                    "relevance_score":  stmt.excluded.relevance_score,
                    "importance_score": stmt.excluded.importance_score,
                    "fetched_at":       stmt.excluded.fetched_at,
                },
            )
            db.execute(stmt)

    added = len(rows) - existing_count
    updated = existing_count
    return added, updated

# ---------------------------------------------------------------------------
# per-security driver
# ---------------------------------------------------------------------------

def ingest_one(
    provider: RSSNewsProvider,
    sec: dict,
    window_days: int,
    limit: int,
) -> tuple[int, int, int]:
    """
    Returns (rows_added, rows_updated, articles_dropped_by_relevance).
    """
    log_id = _open_log(sec["ticker"])
    try:
        since = datetime.now(timezone.utc) - timedelta(days=window_days)
        raw = provider.get_news(sec["ticker"], since=since, limit=limit)

        scored: list[dict] = []
        dropped = 0
        for a in raw:
            relevance = compute_relevance(
                title=a.title,
                summary=a.summary,
                ticker=sec["ticker"],
                company_name=sec["name"],
                sector=sec["sector"],
            )
            if relevance < MIN_RELEVANCE:
                dropped += 1
                continue

            sentiment_score, sentiment_label = analyze_sentiment(a.title, a.summary)
            importance = compute_importance(
                title=a.title,
                summary=a.summary,
                source=a.source,
                published_at=a.published_at,
            )

            scored.append({
                "title": a.title,
                "url": a.url,
                "source": a.source,
                "published_at": a.published_at,
                "summary": a.summary,
                "sentiment_score": sentiment_score,
                "sentiment_label": sentiment_label,
                "relevance_score": relevance,
                "importance_score": importance,
            })

        added, updated = upsert_articles(sec["id"], scored)
        _close_log(log_id, status="ok", added=added, updated=updated)
        log.info(
            "%-15s  fetched=%-3d  kept=%-3d  dropped=%-3d  +%-3d ~%-3d",
            sec["ticker"], len(raw), len(scored), dropped, added, updated,
        )
        return added, updated, dropped

    except Exception as exc:
        log.exception("%-15s FAILED: %s", sec["ticker"], exc)
        _close_log(log_id, status="error", error=str(exc))
        return 0, 0, 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Quantpulse news ingestion")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--ticker",   help="single Yahoo ticker, e.g. TCS.NS")
    g.add_argument("--universe", choices=["nifty50"], help="ingest news for every security")
    p.add_argument("--days",  type=int, default=DEFAULT_WINDOW_DAYS,
                   help=f"lookback window in days (default {DEFAULT_WINDOW_DAYS})")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                   help=f"max articles fetched per ticker (default {DEFAULT_LIMIT})")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    init_db()

    securities = load_securities(args.ticker)
    if not securities:
        raise SystemExit(f"No security found for ticker={args.ticker!r}")

    name_map = {s["ticker"]: s["name"] for s in securities}
    provider = RSSNewsProvider(name_map=name_map)

    log.info(
        "Ingesting news for %d ticker(s), window=%dd, limit=%d",
        len(securities), args.days, args.limit,
    )

    t0 = time.perf_counter()
    total_added = total_updated = total_dropped = 0

    for i, sec in enumerate(securities, 1):
        log.info("[%d/%d] %s", i, len(securities), sec["ticker"])
        added, updated, dropped = ingest_one(provider, sec, args.days, args.limit)
        total_added   += added
        total_updated += updated
        total_dropped += dropped

    elapsed = time.perf_counter() - t0
    log.info("=" * 60)
    log.info("Done in %.1fs", elapsed)
    log.info("  tickers       : %d", len(securities))
    log.info("  rows added    : %d", total_added)
    log.info("  rows updated  : %d", total_updated)
    log.info("  dropped (rel) : %d", total_dropped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())