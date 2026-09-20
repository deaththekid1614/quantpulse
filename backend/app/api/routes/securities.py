"""
Securities endpoints.

  GET /api/securities            list all
  GET /api/securities/{ticker}   one security's metadata
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cache import get_cache
from app.api.deps import get_db
from app.api.schemas import SecurityListOut, SecurityOut
from app.db.models import Security

router = APIRouter()

CACHE_KEY_LIST = "securities:list"


@router.get(
    "/securities",
    response_model=SecurityListOut,
    summary="List all tracked securities",
)
def list_securities(db: Session = Depends(get_db)) -> SecurityListOut:
    cache = get_cache()
    cached = cache.get(CACHE_KEY_LIST)
    if cached is not None:
        return cached

    rows = db.execute(
        select(Security).order_by(Security.ticker)
    ).scalars().all()

    out = SecurityListOut(
        count=len(rows),
        securities=[
            SecurityOut(
                ticker=r.ticker, symbol=r.symbol, name=r.name, sector=r.sector,
            )
            for r in rows
        ],
    )
    cache.set(CACHE_KEY_LIST, out)
    return out


@router.get(
    "/securities/{ticker}",
    response_model=SecurityOut,
    summary="Metadata for one security",
)
def get_security(ticker: str, db: Session = Depends(get_db)) -> SecurityOut:
    key = f"security:{ticker}"
    cache = get_cache()
    cached = cache.get(key)
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

    out = SecurityOut(
        ticker=sec.ticker, symbol=sec.symbol, name=sec.name, sector=sec.sector,
    )
    cache.set(key, out)
    return out
