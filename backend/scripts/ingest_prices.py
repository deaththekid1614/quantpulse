#!/usr/bin/env python3
"""
Populate securities and prices_daily from Yahoo Finance.

Usage:
    python backend/scripts/ingest_prices.py --ticker TCS.NS --years 5
    python backend/scripts/ingest_prices.py --universe nifty50 --years 5

Idempotent: re-running for the same range updates existing rows in place.
Safe to interrupt — no partial state, thanks to per-ticker transactions.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# --- make `app.*` importable when run as a script ---
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pandas as pd  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.dialects.sqlite import insert as sqlite_insert  # noqa: E402

from app.core.log_config import get_logger, setup_logging  # noqa: E402
from app.db.models import IngestLog, PriceDaily, Security  # noqa: E402
from app.db.session import init_db, session_scope  # noqa: E402
from app.providers.yahoo import YahooMarketDataProvider  # noqa: E402

setup_logging("INFO")
log = get_logger("quantpulse.ingest")

UNIVERSE_PATH = REPO_ROOT / "data" / "universe.json"
DEFAULT_YEARS = 5
BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# universe loading
# ---------------------------------------------------------------------------

def load_universe() -> list[dict]:
    if not UNIVERSE_PATH.exists():
        raise SystemExit(f"universe file not found: {UNIVERSE_PATH}")
    data = json.loads(UNIVERSE_PATH.read_text())
    return data["securities"]


# ---------------------------------------------------------------------------
# securities upsert
# ---------------------------------------------------------------------------

def ensure_security(ticker: str, symbol: str, name: str, sector: str) -> int:
    """Insert or update a row in `securities`. Returns its id."""
    with session_scope() as db:
        existing = db.execute(
            select(Security).where(Security.ticker == ticker)
        ).scalar_one_or_none()

        if existing is not None:
            existing.symbol = symbol
            existing.name = name
            existing.sector = sector
            return existing.id

        sec = Security(ticker=ticker, symbol=symbol, name=name, sector=sector)
        db.add(sec)
        db.flush()
        return sec.id


# ---------------------------------------------------------------------------
# prices upsert
# ---------------------------------------------------------------------------

def upsert_prices(security_id: int, df: pd.DataFrame) -> tuple[int, int]:
    """
    Insert-or-update daily bars for a security.
    Returns (rows_added, rows_updated).
    """
    if df.empty:
        return 0, 0

    # How many rows already existed in this range?
    min_d, max_d = df.index.min().date(), df.index.max().date()
    with session_scope() as db:
        existing_count = db.execute(
            select(func.count(PriceDaily.id)).where(
                PriceDaily.security_id == security_id,
                PriceDaily.date >= min_d,
                PriceDaily.date <= max_d,
            )
        ).scalar_one()

    rows = [
        {
            "security_id": security_id,
            "date": ts.date(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]),
        }
        for ts, row in df.iterrows()
    ]

    with session_scope() as db:
        for i in range(0, len(rows), BATCH_SIZE):
            chunk = rows[i : i + BATCH_SIZE]
            stmt = sqlite_insert(PriceDaily).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["security_id", "date"],
                set_={
                    "open":   stmt.excluded.open,
                    "high":   stmt.excluded.high,
                    "low":    stmt.excluded.low,
                    "close":  stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                },
            )
            db.execute(stmt)

    total_after = len(rows)
    rows_added = total_after - existing_count
    rows_updated = total_after - rows_added
    return rows_added, rows_updated


# ---------------------------------------------------------------------------
# ingest log
# ---------------------------------------------------------------------------

def open_ingest_log(ticker: str) -> int:
    with session_scope() as db:
        row = IngestLog(ticker=ticker, status="running", started_at=datetime.now(timezone.utc))
        db.add(row)
        db.flush()
        return row.id


def close_ingest_log(
    log_id: int,
    status: str,
    rows_added: int = 0,
    rows_updated: int = 0,
    error: str | None = None,
) -> None:
    with session_scope() as db:
        row = db.get(IngestLog, log_id)
        if row is None:
            return
        row.status = status
        row.rows_added = rows_added
        row.rows_updated = rows_updated
        row.error = error
        row.finished_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# per-ticker driver
# ---------------------------------------------------------------------------

def ingest_one(
    provider: YahooMarketDataProvider,
    sec: dict,
    start: date,
    end: date,
) -> tuple[int, int]:
    ticker = sec["ticker"]
    log_id = open_ingest_log(ticker)
    try:
        security_id = ensure_security(
            ticker=ticker,
            symbol=sec["symbol"],
            name=sec["name"],
            sector=sec["sector"],
        )

        df = provider.get_daily_ohlcv(ticker, start, end)
        if df.empty:
            log.warning("%-15s no data returned", ticker)
            close_ingest_log(log_id, status="ok", rows_added=0, rows_updated=0)
            return 0, 0

        added, updated = upsert_prices(security_id, df)
        close_ingest_log(log_id, status="ok", rows_added=added, rows_updated=updated)
        log.info(
            "%-15s +%-5d ~%-5d  (%s .. %s)",
            ticker, added, updated,
            df.index.min().date(), df.index.max().date(),
        )
        return added, updated

    except Exception as exc:
        log.exception("%-15s FAILED: %s", ticker, exc)
        close_ingest_log(log_id, status="error", error=str(exc))
        return 0, 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Quantpulse price ingestion")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--ticker", help="single Yahoo ticker, e.g. TCS.NS")
    g.add_argument("--universe", choices=["nifty50"], help="ingest the full universe")
    p.add_argument("--years", type=int, default=DEFAULT_YEARS, help="history length (default 5)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    init_db()

    end   = date.today()
    start = end - timedelta(days=args.years * 365 + 5)

    provider = YahooMarketDataProvider()

    if args.ticker:
        # Minimal security metadata for a one-off ticker ingest.
        symbol = args.ticker.removesuffix(".NS")
        targets = [{
            "symbol": symbol,
            "ticker": args.ticker,
            "name": symbol,
            "sector": "Unknown",
        }]
    else:
        targets = load_universe()

    log.info("Ingesting %d ticker(s), %s .. %s", len(targets), start, end)

    t0 = time.perf_counter()
    total_added = total_updated = total_failed = 0

    for i, sec in enumerate(targets, 1):
        log.info("[%d/%d] %s", i, len(targets), sec["ticker"])
        added, updated = ingest_one(provider, sec, start, end)
        total_added += added
        total_updated += updated
        if added == 0 and updated == 0:
            total_failed += 1

    elapsed = time.perf_counter() - t0
    log.info("=" * 60)
    log.info("Done in %.1fs", elapsed)
    log.info("  tickers       : %d", len(targets))
    log.info("  rows added    : %d", total_added)
    log.info("  rows updated  : %d", total_updated)
    log.info("  tickers w/ 0  : %d", total_failed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

