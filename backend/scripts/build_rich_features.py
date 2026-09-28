#!/usr/bin/env python3
"""
Populate the `rich_features_daily` table.

Computes 21 features per (security, date) across three groups:
  - news aggregates      (7 cols, from news_articles)
  - market context       (8 cols, from market_index_daily + breadth)
  - cross-sectional      (6 cols, computed across all securities per date)

The base 24 features live in `features_daily` and are joined at
training time, not duplicated here.

Usage:
    python backend/scripts/build_rich_features.py --ticker TCS.NS
    python backend/scripts/build_rich_features.py --universe nifty50

Idempotent. Re-running updates rows in place.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import numpy as np
import pandas as pd
from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.sqlite import insert as sqlite_insert  # noqa: E402

from app.core.log_config import get_logger, setup_logging  # noqa: E402
from app.db.models import (  # noqa: E402
    FeaturesDaily,
    IngestLog,
    MarketIndexDaily,
    NewsArticleRow,
    PriceDaily,
    RichFeaturesDaily,
    Security,
)
from app.db.session import init_db, session_scope  # noqa: E402
from app.pipeline.rich_features import (  # noqa: E402
    CROSS_SECTIONAL_FEATURE_COLUMNS,
    MARKET_FEATURE_COLUMNS,
    NEWS_FEATURE_COLUMNS,
    compute_cross_sectional_features,
    compute_market_features,
    compute_news_features,
)

setup_logging("INFO")
log = get_logger("quantpulse.build_rich_features")

ALL_RICH_COLUMNS: tuple[str, ...] = (
    NEWS_FEATURE_COLUMNS + MARKET_FEATURE_COLUMNS + CROSS_SECTIONAL_FEATURE_COLUMNS
)
BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# DB loaders
# ---------------------------------------------------------------------------

def load_securities(ticker_filter: str | None) -> list[dict]:
    with session_scope() as db:
        stmt = select(
            Security.id, Security.ticker, Security.symbol,
            Security.name, Security.sector,
        )
        if ticker_filter:
            stmt = stmt.where(Security.ticker == ticker_filter)
        stmt = stmt.order_by(Security.id)
        rows = db.execute(stmt).all()
    return [
        {"id": r.id, "ticker": r.ticker, "symbol": r.symbol,
         "name": r.name, "sector": r.sector}
        for r in rows
    ]


def load_feature_date_ranges() -> dict[int, tuple[date, date]]:
    """{security_id: (min_date, max_date)} from features_daily."""
    with session_scope() as db:
        rows = db.execute(
            select(
                FeaturesDaily.security_id,
                FeaturesDaily.date,
            ).order_by(FeaturesDaily.security_id, FeaturesDaily.date)
        ).all()
    out: dict[int, tuple[date, date]] = {}
    for sec_id, dt in rows:
        if sec_id not in out:
            out[sec_id] = (dt, dt)
        else:
            prev_min, _ = out[sec_id]
            out[sec_id] = (prev_min, dt)
    return out


def load_price_matrix() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load price data as wide frames (dates x tickers).

    Returns:
      close_wide       — close prices
      ret5_wide        — 5-day log returns
      ret20_wide       — 20-day log returns
      daily_rets_wide  — 1-day log returns
    """
    with session_scope() as db:
        rows = db.execute(
            select(
                PriceDaily.security_id,
                PriceDaily.date,
                PriceDaily.close,
            ).order_by(PriceDaily.security_id, PriceDaily.date)
        ).all()
        secs = db.execute(select(Security.id, Security.ticker)).all()

    id_to_ticker = {sid: tk for sid, tk in secs}
    df = pd.DataFrame(rows, columns=["security_id", "date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = df["security_id"].map(id_to_ticker)

    close_wide = df.pivot(index="date", columns="ticker", values="close").sort_index()
    close_wide = close_wide.astype("float64")

    log_rets = np.log(close_wide / close_wide.shift(1))
    ret5 = log_rets.rolling(window=5, min_periods=5).sum()
    ret20 = log_rets.rolling(window=20, min_periods=20).sum()

    return close_wide, ret5, ret20, log_rets


def load_indices() -> pd.DataFrame:
    """Return a wide frame with columns vix_close and nifty_close."""
    with session_scope() as db:
        rows = db.execute(
            select(
                MarketIndexDaily.symbol,
                MarketIndexDaily.date,
                MarketIndexDaily.close,
            ).order_by(MarketIndexDaily.symbol, MarketIndexDaily.date)
        ).all()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["symbol", "date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    wide = df.pivot(index="date", columns="symbol", values="close").sort_index()

    out = pd.DataFrame(index=wide.index)
    if "^INDIAVIX" in wide.columns:
        out["vix_close"] = wide["^INDIAVIX"].astype("float64")
    if "^NSEI" in wide.columns:
        out["nifty_close"] = wide["^NSEI"].astype("float64")
    return out.dropna(how="any")

def load_nifty_returns() -> pd.Series | None:
    """
    Daily log returns of ^NSEI, indexed by normalised date.
    Returns None if ^NSEI is not in market_index_daily.
    """
    with session_scope() as db:
        rows = db.execute(
            select(MarketIndexDaily.date, MarketIndexDaily.close)
            .where(MarketIndexDaily.symbol == "^NSEI")
            .order_by(MarketIndexDaily.date)
        ).all()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    close = df["close"].astype("float64")
    return np.log(close / close.shift(1))

def load_news_by_security() -> dict[int, pd.DataFrame]:
    """Return {security_id: news DataFrame}."""
    with session_scope() as db:
        rows = db.execute(
            select(
                NewsArticleRow.security_id,
                NewsArticleRow.published_at,
                NewsArticleRow.sentiment_score,
                NewsArticleRow.sentiment_label,
                NewsArticleRow.importance_score,
            )
        ).all()
    if not rows:
        return {}

    df = pd.DataFrame(
        rows,
        columns=["security_id", "published_at", "sentiment_score",
                 "sentiment_label", "importance_score"],
    )
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True)
    return {int(sid): g.reset_index(drop=True) for sid, g in df.groupby("security_id")}


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------

def _to_optional_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return f


def _to_optional_int(v) -> int | None:
    f = _to_optional_float(v)
    if f is None:
        return None
    return int(f)


def upsert_rich(security_id: int, df: pd.DataFrame) -> tuple[int, int]:
    if df.empty:
        return 0, 0

    min_d, max_d = df.index.min().date(), df.index.max().date()

    with session_scope() as db:
        existing = db.execute(
            select(RichFeaturesDaily.date)
            .where(RichFeaturesDaily.security_id == security_id)
            .where(RichFeaturesDaily.date >= min_d)
            .where(RichFeaturesDaily.date <= max_d)
        ).all()
    existing_dates = {d for (d,) in existing}

    rows = []
    for ts, row in df.iterrows():
        rec = {
            "security_id": security_id,
            "date": ts.date(),
            "created_at": datetime.now(timezone.utc),
        }
        for col in NEWS_FEATURE_COLUMNS:
            if col in ("news_count_7d", "news_count_30d"):
                rec[col] = _to_optional_int(row[col])
            else:
                rec[col] = _to_optional_float(row[col])
        for col in MARKET_FEATURE_COLUMNS + CROSS_SECTIONAL_FEATURE_COLUMNS:
            rec[col] = _to_optional_float(row[col])
        rows.append(rec)

    with session_scope() as db:
        for i in range(0, len(rows), BATCH_SIZE):
            chunk = rows[i : i + BATCH_SIZE]
            stmt = sqlite_insert(RichFeaturesDaily).values(chunk)
            update_cols = {c: getattr(stmt.excluded, c) for c in ALL_RICH_COLUMNS}
            update_cols["created_at"] = stmt.excluded.created_at
            stmt = stmt.on_conflict_do_update(
                index_elements=["security_id", "date"],
                set_=update_cols,
            )
            db.execute(stmt)

    added = len(rows) - len(existing_dates)
    updated = len(existing_dates)
    return added, updated


# ---------------------------------------------------------------------------
# log helpers
# ---------------------------------------------------------------------------

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
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Quantpulse rich feature builder")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--ticker",   help="single Yahoo ticker, e.g. TCS.NS")
    g.add_argument("--universe", choices=["nifty50"], help="build for every security")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    init_db()

    securities = load_securities(args.ticker)
    if not securities:
        raise SystemExit(f"No security found for ticker={args.ticker!r}")

    log.info("Loading shared inputs...")
    close_wide, ret5_wide, ret20_wide, daily_rets_wide = load_price_matrix()
    indices_df = load_indices()
    if indices_df.empty:
        raise SystemExit("market_index_daily is empty — run ingest_indices.py first")
    log.info("  prices wide: %s", close_wide.shape)

    nifty_returns = load_nifty_returns()
    if nifty_returns is None:
        log.warning("^NSEI not found in market_index_daily — corr_to_nifty_60d and beta_residual_5d will be NULL")

    sector_map = {sec["ticker"]: sec["sector"] for sec in securities}

    log.info("Computing market context (once)...")
    market = compute_market_features(
        dates=close_wide.index,
        indices_df=indices_df,
        universe_returns=daily_rets_wide,
    )
    log.info("  market: %s", market.shape)

    log.info("Computing cross-sectional features (once)...")
    cross = compute_cross_sectional_features(
        close_wide=close_wide,
        ret5_wide=ret5_wide,
        ret20_wide=ret20_wide,
        sector_map=sector_map,
        nifty_returns=nifty_returns,
    )
    log.info("  cross-sectional: %s", cross.shape)

    log.info("Loading news...")
    news_by_sec = load_news_by_security()
    log.info("  %d securities with news", len(news_by_sec))

    log.info("Loading feature date ranges...")
    ranges = load_feature_date_ranges()

    log.info("Building rich features for %d security/ies", len(securities))
    t0 = time.perf_counter()
    total_added = total_updated = 0

    for i, sec in enumerate(securities, 1):
        ticker = sec["ticker"]
        sec_id = sec["id"]
        log.info("[%d/%d] %s", i, len(securities), ticker)

        log_id = _open_log(ticker)
        try:
            if sec_id not in ranges:
                _close_log(log_id, status="error", error="no features_daily rows")
                log.warning("  %-15s no features_daily rows — skipping", ticker)
                continue

            start_date, end_date = ranges[sec_id]
            ticker_dates = close_wide.index[
                (close_wide.index.date >= start_date) & (close_wide.index.date <= end_date)
            ]
            if len(ticker_dates) == 0:
                _close_log(log_id, status="error", error="no price rows in range")
                log.warning("  %-15s no price rows in feature range", ticker)
                continue

            # --- news ---
            news_df = news_by_sec.get(sec_id, pd.DataFrame())
            news_feat = compute_news_features(
                pd.DatetimeIndex(ticker_dates), news_df,
            )

            # --- market (already computed) ---
            market_slice = market.reindex(ticker_dates)

            # --- cross-sectional for this ticker ---
            if ticker in cross.index.get_level_values("ticker").unique():
                cross_ticker = cross.xs(ticker, level="ticker")
                cross_slice = cross_ticker.reindex(ticker_dates)
            else:
                cross_slice = pd.DataFrame(
                    np.nan, index=ticker_dates,
                    columns=list(CROSS_SECTIONAL_FEATURE_COLUMNS),
                )

            # --- assemble ---
            df = pd.concat([
                news_feat.reindex(ticker_dates),
                market_slice,
                cross_slice,
            ], axis=1)
            df = df.loc[:, list(ALL_RICH_COLUMNS)]

            added, updated = upsert_rich(sec_id, df)
            total_added   += added
            total_updated += updated

            non_null = df.notna().any(axis=0).sum()
            _close_log(log_id, status="ok", added=added, updated=updated)
            log.info(
                "  %-15s +%-5d ~%-5d  (%d/%d cols have data)",
                ticker, added, updated, non_null, len(ALL_RICH_COLUMNS),
            )

        except Exception as exc:
            log.exception("  %-15s FAILED: %s", ticker, exc)
            _close_log(log_id, status="error", error=str(exc))

    elapsed = time.perf_counter() - t0
    log.info("=" * 60)
    log.info("Done in %.1fs", elapsed)
    log.info("  securities     : %d", len(securities))
    log.info("  rows added     : %d", total_added)
    log.info("  rows updated   : %d", total_updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
