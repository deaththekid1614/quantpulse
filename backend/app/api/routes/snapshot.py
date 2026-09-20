"""
Snapshot endpoint — the stock page header in one request.

  GET /api/securities/{ticker}/snapshot

Combines the latest OHLCV bar, the change vs the previous session, and
the latest feature vector into a single response. Cached for 60 seconds
like every other endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cache import get_cache
from app.api.deps import get_db
from app.api.schemas import LatestPrice, SnapshotOut
from app.db.models import FeaturesDaily, PriceDaily, Security
from app.pipeline.features import FEATURE_COLUMNS

router = APIRouter()


@router.get(
    "/securities/{ticker}/snapshot",
    response_model=SnapshotOut,
    summary="Latest price + change + latest features for one security",
)
def get_snapshot(ticker: str, db: Session = Depends(get_db)) -> SnapshotOut:
    cache = get_cache()
    cache_key = f"snapshot:{ticker}"
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

    # Latest two price bars (for change calculation).
    latest_two = db.execute(
        select(PriceDaily)
        .where(PriceDaily.security_id == sec.id)
        .order_by(PriceDaily.date.desc())
        .limit(2)
    ).scalars().all()

    if not latest_two:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No price data for '{ticker}'. Run ingest_prices.py first.",
        )

    latest = latest_two[0]
    prev = latest_two[1] if len(latest_two) > 1 else None

    change_1d = None
    change_1d_pct = None
    if prev is not None and prev.close != 0:
        change_1d = round(latest.close - prev.close, 4)
        change_1d_pct = round((latest.close / prev.close - 1.0) * 100.0, 4)

    # Latest feature row at or before the latest price date.
    feat = db.execute(
        select(FeaturesDaily)
        .where(
            FeaturesDaily.security_id == sec.id,
            FeaturesDaily.date <= latest.date,
        )
        .order_by(FeaturesDaily.date.desc())
        .limit(1)
    ).scalar_one_or_none()

    features: dict[str, float] = {}
    if feat is not None:
        features = {col: float(getattr(feat, col)) for col in FEATURE_COLUMNS}

    out = SnapshotOut(
        ticker=sec.ticker,
        symbol=sec.symbol,
        name=sec.name,
        sector=sec.sector,
        as_of=latest.date,
        price=LatestPrice(
            date=latest.date,
            open=latest.open,
            high=latest.high,
            low=latest.low,
            close=latest.close,
            volume=latest.volume,
        ),
        change_1d=change_1d,
        change_1d_pct=change_1d_pct,
        features=features,
    )
    cache.set(cache_key, out)
    return out
