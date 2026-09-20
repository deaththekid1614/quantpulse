"""
Rolling statistics endpoint.

  GET /api/securities/{ticker}/stats

Computes 52-week range, multi-horizon returns, average volumes, and
all-time high/low on the fly from `prices_daily`. No new table; results
are cached for 60 seconds like every other read endpoint.

All returns are expressed in percent, not fractions.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cache import get_cache
from app.api.deps import get_db
from app.api.schemas import StatsOut
from app.db.models import PriceDaily, Security

router = APIRouter()


def _pct_return(latest: float, ref: float | None) -> float | None:
    if ref is None or ref == 0:
        return None
    return round((latest / ref - 1.0) * 100.0, 4)


@router.get(
    "/securities/{ticker}/stats",
    response_model=StatsOut,
    summary="Rolling statistics for one security",
)
def get_stats(ticker: str, db: Session = Depends(get_db)) -> StatsOut:
    cache = get_cache()
    cache_key = f"stats:{ticker}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sec = db.execute(
        select(Security).where(Security.ticker == ticker)
    ).scalar_one_or_none()
    if sec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticker '{ticker}' not found",
        )

    rows = db.execute(
        select(
            PriceDaily.date,
            PriceDaily.open,
            PriceDaily.high,
            PriceDaily.low,
            PriceDaily.close,
            PriceDaily.volume,
        )
        .where(PriceDaily.security_id == sec.id)
        .order_by(PriceDaily.date)
    ).all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No price data for '{ticker}'",
        )

    df = pd.DataFrame(
        rows, columns=["date", "open", "high", "low", "close", "volume"]
    )
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    latest_date: date = df.index[-1].date()
    latest_close = float(df["close"].iloc[-1])

    # --- 52-week range (calendar window) ---
    start_52w = pd.Timestamp(latest_date - timedelta(days=365))
    df_52w = df.loc[start_52w:]
    if df_52w.empty:
        df_52w = df  # defensive fallback; won't fire with 5y of data
    high_52w = float(df_52w["high"].max())
    low_52w  = float(df_52w["low"].min())

    pct_from_high = ((latest_close - high_52w) / high_52w * 100.0) if high_52w else 0.0
    pct_from_low  = ((latest_close - low_52w)  / low_52w  * 100.0) if low_52w  else 0.0

    # --- returns (positional for short horizons, calendar for long) ---
    def ret_positional(n: int) -> float | None:
        if len(df) <= n:
            return None
        return _pct_return(latest_close, float(df["close"].iloc[-(n + 1)]))

    def close_at_or_before(target: date) -> float | None:
        sub = df.loc[: pd.Timestamp(target)]
        if sub.empty:
            return None
        return float(sub["close"].iloc[-1])

    ret_1d  = ret_positional(1)
    ret_5d  = ret_positional(5)
    ret_20d = ret_positional(20)
    ret_1y  = _pct_return(latest_close, close_at_or_before(latest_date - timedelta(days=365)))
    ret_ytd = _pct_return(latest_close, close_at_or_before(date(latest_date.year - 1, 12, 31)))

    # --- volumes ---
    avg_vol_20d = int(df["volume"].tail(20).mean())
    avg_vol_60d = int(df["volume"].tail(60).mean())

    # --- all-time within available history ---
    ath = float(df["high"].max())
    atl = float(df["low"].min())

    out = StatsOut(
        ticker=sec.ticker,
        symbol=sec.symbol,
        name=sec.name,
        sector=sec.sector,
        as_of=latest_date,
        high_52w=round(high_52w, 2),
        low_52w=round(low_52w, 2),
        pct_from_52w_high=round(pct_from_high, 4),
        pct_from_52w_low=round(pct_from_low, 4),
        ret_1d_pct=ret_1d,
        ret_5d_pct=ret_5d,
        ret_20d_pct=ret_20d,
        ret_ytd_pct=ret_ytd,
        ret_1y_pct=ret_1y,
        avg_volume_20d=avg_vol_20d,
        avg_volume_60d=avg_vol_60d,
        all_time_high=round(ath, 2),
        all_time_low=round(atl, 2),
    )
    cache.set(cache_key, out)
    return out
