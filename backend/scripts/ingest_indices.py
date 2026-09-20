#!/usr/bin/env python3
"""
Populate market_index_daily from Yahoo Finance.

Fetches a fixed set of indices used by the feature engine and the risk
engine. Unlike ingest_prices.py, this does not read universe.json — indices
are not tradeable securities.

Usage:
    python backend/scripts/ingest_indices.py --years 5
    python backend/scripts/ingest_indices.py --symbol ^NSEI --years 5

Idempotent. Safe to interrupt.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pandas as pd  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.dialects.sqlite import insert as sqlite_insert  # noqa: E402

from app.core.log_config import get_logger, setup_logging  # noqa: E402
from app.db.models import IngestLog, MarketIndexDaily  # noqa: E402
from app.db.session import init_db, session_scope  # noqa: E402
from app.providers.yahoo import YahooMarketDataProvider  # noqa: E402

setup_logging("INFO")
log = get_logger("quantpulse.ingest.indices")

DEFAULT_YEARS = 5
BATCH_SIZE = 500

# Fixed index list. Adding a new index later is a one-line edit here.
INDICES: tuple[str, ...] = (
    "^NSEI",      # Nifty 50
    "^NSEBANK",   # Bank Nifty
    "^INDIAVIX",  # India VIX
)


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------

def upsert_index(symbol: str, df: pd.DataFrame) -> tuple[int, int]:
    """Insert-or-update daily bars for an index. Returns (added, updated)."""
    if df.empty:
        return 0, 0

    min_d, max_d = df.index.min().date(), df.index.max().date()

    with session_scope() as db:
        existing = db.execute(
            select(func.count(MarketIndexDaily.id)).where(
                MarketIndexDaily.symbol == symbol,
                MarketIndexDaily.date >= min_d,
                MarketIndexDaily.date <= max_d,
            )
        ).scalar_one()

    rows = [
        {
            "symbol": symbol,
            "date":   ts.date(),
            "open":   float(row["open"]),
            "high":   float(row["high"]),
            "low":    float(row["low"]),
            "close":  float(row["close"]),
            "volume": int(row["volume"]),
        }
        for ts, row in df.iterrows()
    ]

    with session_scope() as db:
        for i in range(0, len(rows), BATCH_SIZE):
            chunk = rows[i : i + BATCH_SIZE]
            stmt = sqlite_insert(MarketIndexDaily).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "date"],
                set_={
                    "open":   stmt.excluded.open,
                    "high":   stmt.excluded.high,
                    "low":    stmt.excluded.low,
                    "close":  stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                },
            )
            db.execute(stmt)

    added = len(rows) - existing
    updated = len(rows) - added
    return added, updated


# ---------------------------------------------------------------------------
# per-index driver
# ---------------------------------------------------------------------------

def ingest_one(
    provider: YahooMarketDataProvider,
    symbol: str,
    start: date,
    end: date,
) -> tuple[int, int]:
    log_id = _open_log(symbol)
    try:
        df = provider.get_daily_ohlcv(symbol, start, end)
        if df.empty:
            log.warning("%-10s no data returned", symbol)
            _close_log(log_id, status="ok", added=0, updated=0)
            return 0, 0

        added, updated = upsert_index(symbol, df)
        _close_log(log_id, status="ok", added=added, updated=updated)
        log.info(
            "%-10s +%-5d ~%-5d  (%s .. %s)",
            symbol, added, updated,
            df.index.min().date(), df.index.max().date(),
        )
        return added, updated

    except Exception as exc:
        log.exception("%-10s FAILED: %s", symbol, exc)
        _close_log(log_id, status="error", error=str(exc))
        return 0, 0


# ---------------------------------------------------------------------------
# ingest_log helpers (kept identical in shape to ingest_prices.py)
# ---------------------------------------------------------------------------

def _open_log(symbol: str) -> int:
    with session_scope() as db:
        row = IngestLog(ticker=symbol, status="running", started_at=datetime.now(timezone.utc))
        db.add(row)
        db.flush()
        return row.id


def _close_log(
    log_id: int,
    status: str,
    added: int = 0,
    updated: int = 0,
    error: str | None = None,
) -> None:
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
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Quantpulse index ingestion")
    p.add_argument("--symbol", help="single index symbol, e.g. ^NSEI (default: all)")
    p.add_argument("--years", type=int, default=DEFAULT_YEARS)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    init_db()

    end   = date.today()
    start = end - timedelta(days=args.years * 365 + 5)

    targets = (args.symbol,) if args.symbol else INDICES

    log.info("Ingesting %d index/indices, %s .. %s", len(targets), start, end)

    provider = YahooMarketDataProvider()
    t0 = time.perf_counter()
    total_added = total_updated = 0

    for sym in targets:
        added, updated = ingest_one(provider, sym, start, end)
        total_added   += added
        total_updated += updated

    elapsed = time.perf_counter() - t0
    log.info("=" * 60)
    log.info("Done in %.1fs", elapsed)
    log.info("  indices       : %d", len(targets))
    log.info("  rows added    : %d", total_added)
    log.info("  rows updated  : %d", total_updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
