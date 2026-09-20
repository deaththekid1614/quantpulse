"""
Market index snapshot endpoint.

  GET /api/indices/snapshot

Returns the latest bar and 1-day change for each tracked market index
(Nifty 50, Bank Nifty, India VIX). Indices live in `market_index_daily`,
not `securities` — they are not tradeable and do not belong in
universe.json.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cache import get_cache
from app.api.deps import get_db
from app.api.schemas import IndexQuote, IndexSnapshotOut
from app.db.models import MarketIndexDaily

router = APIRouter()

# Display names, in fixed order for the home page strip.
INDEX_ORDER: tuple[tuple[str, str], ...] = (
    ("^NSEI",    "NIFTY 50"),
    ("^NSEBANK", "BANK NIFTY"),
    ("^INDIAVIX", "INDIA VIX"),
)

CACHE_KEY = "indices:snapshot"


@router.get(
    "/indices/snapshot",
    response_model=IndexSnapshotOut,
    summary="Latest bar and 1-day change for each tracked index",
)
def get_indices_snapshot(db: Session = Depends(get_db)) -> IndexSnapshotOut:
    cache = get_cache()
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    quotes: list[IndexQuote] = []
    for symbol, display_name in INDEX_ORDER:
        latest_two = (
            db.execute(
                select(MarketIndexDaily)
                .where(MarketIndexDaily.symbol == symbol)
                .order_by(MarketIndexDaily.date.desc())
                .limit(2)
            )
            .scalars()
            .all()
        )
        if not latest_two:
            continue

        latest = latest_two[0]
        prev = latest_two[1] if len(latest_two) > 1 else None

        change_1d: float | None = None
        change_pct: float | None = None
        if prev is not None and prev.close != 0:
            change_1d = round(latest.close - prev.close, 4)
            change_pct = round((latest.close / prev.close - 1.0) * 100.0, 4)

        quotes.append(
            IndexQuote(
                symbol=symbol,
                name=display_name,
                as_of=latest.date,
                close=round(latest.close, 2),
                change_1d=change_1d,
                change_1d_pct=change_pct,
            )
        )

    as_of = quotes[0].as_of if quotes else date.today()
    out = IndexSnapshotOut(as_of=as_of, indices=quotes)
    cache.set(CACHE_KEY, out)
    return out
