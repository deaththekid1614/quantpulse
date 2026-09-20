"""
Price history endpoint.

  GET /api/securities/{ticker}/prices?range=1y

Returns every daily OHLCV bar in the requested range, ascending by date.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cache import get_cache
from app.api.deps import DEFAULT_RANGE, RANGE_TO_DAYS, get_db, resolve_range
from app.api.schemas import PriceBar, PriceHistoryOut
from app.db.models import PriceDaily, Security

router = APIRouter()


@router.get(
    "/securities/{ticker}/prices",
    response_model=PriceHistoryOut,
    summary="Daily OHLCV history for one security",
)
def get_prices(
    ticker: str,
    range: str = Query(  # noqa: A002  — shadowing builtin is FastAPI convention
        DEFAULT_RANGE,
        description=f"History window. Allowed: {', '.join(RANGE_TO_DAYS.keys())}",
    ),
    db: Session = Depends(get_db),
) -> PriceHistoryOut:
    cache = get_cache()
    cache_key = f"prices:{ticker}:{range}"
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

    start: date | None = resolve_range(range)

    stmt = (
        select(PriceDaily)
        .where(PriceDaily.security_id == sec.id)
        .order_by(PriceDaily.date)
    )
    if start is not None:
        stmt = stmt.where(PriceDaily.date >= start)

    rows = db.execute(stmt).scalars().all()

    out = PriceHistoryOut(
        ticker=sec.ticker,
        symbol=sec.symbol,
        name=sec.name,
        sector=sec.sector,
        range=range,
        count=len(rows),
        data=[
            PriceBar(
                date=r.date,
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
            )
            for r in rows
        ],
    )
    cache.set(cache_key, out)
    return out
