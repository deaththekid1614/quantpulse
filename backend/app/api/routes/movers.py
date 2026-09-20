"""
Top movers endpoint.

  GET /api/movers?limit=10

Returns the N securities with the largest absolute 1-day percentage
change on the most recent feature date, using `features_daily.ret_1d`
(a log return) converted to percent.
"""
from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.cache import get_cache
from app.api.deps import get_db
from app.api.schemas import MoverOut, MoversOut
from app.db.models import FeaturesDaily, PriceDaily, Security

router = APIRouter()


@router.get(
    "/movers",
    response_model=MoversOut,
    summary="Top movers by absolute 1-day percent change",
)
def get_movers(
    limit: int = Query(10, ge=1, le=50, description="Number of securities to return"),
    db: Session = Depends(get_db),
) -> MoversOut:
    cache = get_cache()
    cache_key = f"movers:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # The most recent feature date in the DB. All active securities share it.
    latest_date = db.execute(select(func.max(FeaturesDaily.date))).scalar_one()

    # Join securities -> features_daily at that date.
    rows = db.execute(
        select(
            Security.id,
            Security.ticker,
            Security.symbol,
            Security.name,
            Security.sector,
            FeaturesDaily.ret_1d,
        )
        .join(FeaturesDaily, FeaturesDaily.security_id == Security.id)
        .where(FeaturesDaily.date == latest_date)
    ).all()

    # Latest price per security at the same date (for close + volume).
    price_by_sec = {
        r.security_id: r
        for r in db.execute(
            select(
                PriceDaily.security_id,
                PriceDaily.close,
                PriceDaily.volume,
            ).where(PriceDaily.date == latest_date)
        ).all()
    }

    items: list[MoverOut] = []
    for r in rows:
        price = price_by_sec.get(r.id)
        if price is None:
            # Should not happen: features are built from prices.
            continue

        # ret_1d is a log return. Convert to percent.
        try:
            pct = (math.exp(float(r.ret_1d)) - 1.0) * 100.0
        except OverflowError:
            continue

        items.append(
            MoverOut(
                ticker=r.ticker,
                symbol=r.symbol,
                name=r.name,
                sector=r.sector,
                close=round(float(price.close), 2),
                change_1d_pct=round(pct, 4),
                volume=int(price.volume),
            )
        )

    items.sort(key=lambda m: abs(m.change_1d_pct), reverse=True)
    items = items[:limit]

    out = MoversOut(as_of=latest_date, count=len(items), movers=items)
    cache.set(cache_key, out)
    return out
