#!/usr/bin/env python3
"""
Populate features_daily from prices_daily + market_index_daily.

Reads the raw price data, computes every Stage 2 feature via
app.pipeline.features.compute_all, drops warm-up rows (any NaN in the
output), and upserts into features_daily.

Usage:
    python backend/scripts/build_features.py --ticker TCS.NS
    python backend/scripts/build_features.py --universe nifty50

Idempotent. Re-running updates existing rows in place.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pandas as pd  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.dialects.sqlite import insert as sqlite_insert  # noqa: E402

from app.core.log_config import get_logger, setup_logging  # noqa: E402
from app.db.models import (  # noqa: E402
    FeaturesDaily,
    IngestLog,
    MarketIndexDaily,
    PriceDaily,
    Security,
)
from app.db.session import init_db, session_scope  # noqa: E402
from app.pipeline.features import FEATURE_COLUMNS, compute_all  # noqa: E402

setup_logging("INFO")
log = get_logger("quantpulse.build_features")

NIFTY_SYMBOL = "^NSEI"
BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_prices_wide() -> dict[str, pd.DataFrame]:
    """
    Return {ticker: price_df} for every security in the DB.

    Each price_df has the canonical OHLCV schema, indexed by date.
    """
    with session_scope() as db:
        q = (
            select(
                Security.ticker,
                PriceDaily.date,
                PriceDaily.open,
                PriceDaily.high,
                PriceDaily.low,
                PriceDaily.close,
                PriceDaily.volume,
            )
            .join(PriceDaily, PriceDaily.security_id == Security.id)
            .order_by(Security.ticker, PriceDaily.date)
        )
        rows = db.execute(q).all()

    if not rows:
        return {}

    df = pd.DataFrame(
        rows,
        columns=["ticker", "date", "open", "high", "low", "close", "volume"],
    )
    df["date"] = pd.to_datetime(df["date"])

    out: dict[str, pd.DataFrame] = {}
    for ticker, group in df.groupby("ticker", sort=False):
        g = group.set_index("date").drop(columns=["ticker"]).sort_index()
        g.index.name = "date"
        g["volume"] = g["volume"].astype("int64")
        out[ticker] = g
    return out


def load_nifty() -> pd.DataFrame:
    """Return the Nifty 50 index as a canonical OHLCV DataFrame."""
    with session_scope() as db:
        q = (
            select(
                MarketIndexDaily.date,
                MarketIndexDaily.open,
                MarketIndexDaily.high,
                MarketIndexDaily.low,
                MarketIndexDaily.close,
                MarketIndexDaily.volume,
            )
            .where(MarketIndexDaily.symbol == NIFTY_SYMBOL)
            .order_by(MarketIndexDaily.date)
        )
        rows = db.execute(q).all()

    if not rows:
        raise SystemExit(f"{NIFTY_SYMBOL} not in market_index_daily — run ingest_indices.py first")

    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df.index.name = "date"
    df["volume"] = df["volume"].astype("int64")
    return df


def load_securities() -> pd.DataFrame:
    """Return a DataFrame of securities with id, ticker, sector."""
    with session_scope() as db:
        rows = db.execute(
            select(Security.id, Security.ticker, Security.sector).order_by(Security.id)
        ).all()
    return pd.DataFrame(rows, columns=["id", "ticker", "sector"])


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------

def upsert_features(security_id: int, df: pd.DataFrame) -> tuple[int, int]:
    """Insert-or-update feature rows. Returns (added, updated)."""
    if df.empty:
        return 0, 0

    min_d, max_d = df.index.min().date(), df.index.max().date()

    with session_scope() as db:
        existing = db.execute(
            select(func.count(FeaturesDaily.id)).where(
                FeaturesDaily.security_id == security_id,
                FeaturesDaily.date >= min_d,
                FeaturesDaily.date <= max_d,
            )
        ).scalar_one()

    rows = [
        {
            "security_id": security_id,
            "date": ts.date(),
            **{col: float(row[col]) for col in FEATURE_COLUMNS},
        }
        for ts, row in df.iterrows()
    ]

    with session_scope() as db:
        for i in range(0, len(rows), BATCH_SIZE):
            chunk = rows[i : i + BATCH_SIZE]
            stmt = sqlite_insert(FeaturesDaily).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["security_id", "date"],
                set_={col: getattr(stmt.excluded, col) for col in FEATURE_COLUMNS},
            )
            db.execute(stmt)

    added = len(rows) - existing
    updated = len(rows) - added
    return added, updated


# ---------------------------------------------------------------------------
# log helpers (same shape as ingest scripts)
# ---------------------------------------------------------------------------

def _open_log(ticker: str) -> int:
    with session_scope() as db:
        row = IngestLog(ticker=ticker, status="running", started_at=datetime.now(timezone.utc))
        db.add(row)
        db.flush()
        return row.id


def _close_log(log_id: int, status: str, added: int = 0, updated: int = 0, error: str | None = None) -> None:
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
# per-security driver
# ---------------------------------------------------------------------------

def build_one(
    security_id: int,
    ticker: str,
    sector: str,
    price_df: pd.DataFrame,
    nifty_df: pd.DataFrame,
    all_prices: dict[str, pd.DataFrame],
    securities: pd.DataFrame,
) -> tuple[int, int]:
    log_id = _open_log(ticker)
    try:
        # Sector peers: same sector, different ticker, present in all_prices.
        peer_tickers = securities.loc[
            (securities["sector"] == sector) & (securities["ticker"] != ticker),
            "ticker",
        ].tolist()
        peer_closes = pd.DataFrame(
            {t: all_prices[t]["close"] for t in peer_tickers if t in all_prices}
        )

        feats = compute_all(price_df, nifty_df, peer_closes)

        # Drop warm-up rows (any NaN anywhere).
        before = len(feats)
        feats = feats.dropna(how="any")
        dropped = before - len(feats)

        if feats.empty:
            log.warning("%-15s no rows after warm-up drop", ticker)
            _close_log(log_id, status="ok", added=0, updated=0)
            return 0, 0

        added, updated = upsert_features(security_id, feats)
        _close_log(log_id, status="ok", added=added, updated=updated)
        log.info(
            "%-15s +%-5d ~%-5d  (dropped %d warm-up)",
            ticker, added, updated, dropped,
        )
        return added, updated

    except Exception as exc:
        log.exception("%-15s FAILED: %s", ticker, exc)
        _close_log(log_id, status="error", error=str(exc))
        return 0, 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Quantpulse feature builder")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--ticker", help="single Yahoo ticker, e.g. TCS.NS")
    g.add_argument("--universe", choices=["nifty50"], help="build for every security")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    init_db()

    log.info("Loading prices, Nifty index, and securities...")
    all_prices = load_prices_wide()
    nifty_df   = load_nifty()
    securities = load_securities()
    log.info("  %d securities, %d price series, %d Nifty rows",
             len(securities), len(all_prices), len(nifty_df))

    if args.ticker:
        targets = securities.loc[securities["ticker"] == args.ticker]
        if targets.empty:
            raise SystemExit(f"{args.ticker} not in securities table — run ingest_prices first")
    else:
        targets = securities

    log.info("Building features for %d security/ies", len(targets))

    t0 = time.perf_counter()
    total_added = total_updated = 0

    for i, (_, row) in enumerate(targets.iterrows(), 1):
        log.info("[%d/%d] %s", i, len(targets), row["ticker"])
        added, updated = build_one(
            security_id=int(row["id"]),
            ticker=row["ticker"],
            sector=row["sector"],
            price_df=all_prices.get(row["ticker"]),
            nifty_df=nifty_df,
            all_prices=all_prices,
            securities=securities,
        )
        total_added   += added
        total_updated += updated

    elapsed = time.perf_counter() - t0
    log.info("=" * 60)
    log.info("Done in %.1fs", elapsed)
    log.info("  securities     : %d", len(targets))
    log.info("  rows added     : %d", total_added)
    log.info("  rows updated   : %d", total_updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
