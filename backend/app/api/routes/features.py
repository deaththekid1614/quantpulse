"""
Feature history endpoint.

  GET /api/securities/{ticker}/features?range=1y

Returns every feature row in the requested range, ascending by date.
Each row exposes its 24 features as a dict keyed by column name — this
lets Stage 8 add new features without touching this file.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cache import get_cache
from app.api.deps import DEFAULT_RANGE, RANGE_TO_DAYS, get_db, resolve_range
from app.api.schemas import FeatureHistoryOut, FeatureRow
from app.db.models import FeaturesDaily, Security
from app.pipeline.features import FEATURE_COLUMNS

router = APIRouter()


@router.get(
    "/securities/{ticker}/features",
    response_model=FeatureHistoryOut,
    summary="Daily feature history for one security",
)
def get_features(
    ticker: str,
    range: str = Query(  # noqa: A002
        DEFAULT_RANGE,
        description=f"History window. Allowed: {', '.join(RANGE_TO_DAYS.keys())}",
    ),
    db: Session = Depends(get_db),
) -> FeatureHistoryOut:
    cache = get_cache()
    cache_key = f"features:{ticker}:{range}"
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
        select(FeaturesDaily)
        .where(FeaturesDaily.security_id == sec.id)
        .order_by(FeaturesDaily.date)
    )
    if start is not None:
        stmt = stmt.where(FeaturesDaily.date >= start)

    rows = db.execute(stmt).scalars().all()

    out = FeatureHistoryOut(
        ticker=sec.ticker,
        symbol=sec.symbol,
        name=sec.name,
        sector=sec.sector,
        range=range,
        count=len(rows),
        data=[
            FeatureRow(
                date=r.date,
                features={col: float(getattr(r, col)) for col in FEATURE_COLUMNS},
            )
            for r in rows
        ],
    )
    cache.set(cache_key, out)
    return out
