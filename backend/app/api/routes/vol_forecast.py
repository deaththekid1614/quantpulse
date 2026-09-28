"""
Volatility forecast endpoint.

  GET /api/securities/{ticker}/vol_forecast

Returns the latest volatility forecast for one security, one entry per
horizon (7d, 15d, 30d). 404 if the ticker exists but has no forecast
yet (i.e. build_vol_forecasts.py has not been run).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.cache import get_cache
from app.api.deps import get_db
from app.api.schemas import VolForecastHorizonOut, VolForecastOut
from app.db.models import Security, VolForecastRow

router = APIRouter()


@router.get(
    "/securities/{ticker}/vol_forecast",
    response_model=VolForecastOut,
    summary="Volatility forecast for one security (7d, 15d, 30d)",
)
def get_vol_forecast(ticker: str, db: Session = Depends(get_db)) -> VolForecastOut:
    cache = get_cache()
    cache_key = f"vol_forecast:{ticker}"
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

    # latest as-of date available for this security
    as_of = db.execute(
        select(func.max(VolForecastRow.date)).where(VolForecastRow.security_id == sec.id)
    ).scalar_one()

    if as_of is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No volatility forecast for '{ticker}'. Run build_vol_forecasts.py.",
        )

    rows = db.execute(
        select(VolForecastRow)
        .where(
            VolForecastRow.security_id == sec.id,
            VolForecastRow.date == as_of,
        )
        .order_by(VolForecastRow.horizon_days)
    ).scalars().all()

    out = VolForecastOut(
        ticker=sec.ticker,
        symbol=sec.symbol,
        name=sec.name,
        sector=sec.sector,
        as_of=as_of,
        horizons=[
            VolForecastHorizonOut(
                horizon_days=r.horizon_days,
                prob_high_vol=r.prob_high_vol,
                prob_low_vol=r.prob_low_vol,
                threshold=r.threshold,
                current_vol_20d=r.current_vol_20d,
                model_auc=r.model_auc,
            )
            for r in rows
        ],
    )
    cache.set(cache_key, out)
    return out
