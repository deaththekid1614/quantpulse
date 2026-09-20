"""
Company fundamentals endpoint.

  GET /api/securities/{ticker}/fundamentals

Returns the latest fundamentals row for one security. If the security
exists but no fundamentals have been ingested yet, returns 200 with every
metric null — the frontend renders missing values as em-dashes rather
than treating the response as an error.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cache import get_cache
from app.api.deps import get_db
from app.api.schemas import FundamentalsOut
from app.db.models import FundamentalsRow, Security

router = APIRouter()


@router.get(
    "/securities/{ticker}/fundamentals",
    response_model=FundamentalsOut,
    summary="Company fundamentals for one security",
)
def get_fundamentals(ticker: str, db: Session = Depends(get_db)) -> FundamentalsOut:
    cache = get_cache()
    cache_key = f"fundamentals:{ticker}"
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

    row = db.execute(
        select(FundamentalsRow).where(FundamentalsRow.security_id == sec.id)
    ).scalar_one_or_none()

    # Build the response. When `row` is None, every metric defaults to
    # None and the frontend renders em-dashes.
    out = FundamentalsOut(
        ticker=sec.ticker,
        symbol=sec.symbol,
        name=sec.name,
        sector=sec.sector,

        as_of=row.as_of if row else None,

        current_price=row.current_price if row else None,
        previous_close=row.previous_close if row else None,
        market_cap=row.market_cap if row else None,
        enterprise_value=row.enterprise_value if row else None,
        high_52w=row.high_52w if row else None,
        low_52w=row.low_52w if row else None,
        shares_outstanding=row.shares_outstanding if row else None,

        pe_trailing=row.pe_trailing if row else None,
        price_to_book=row.price_to_book if row else None,
        price_to_sales=row.price_to_sales if row else None,

        eps_trailing=row.eps_trailing if row else None,

        total_revenue=row.total_revenue if row else None,
        gross_profits=row.gross_profits if row else None,
        net_income=row.net_income if row else None,
        profit_margin=row.profit_margin if row else None,
        return_on_equity=row.return_on_equity if row else None,
        return_on_assets=row.return_on_assets if row else None,

        total_debt=row.total_debt if row else None,
        total_cash=row.total_cash if row else None,
        debt_to_equity=row.debt_to_equity if row else None,

        dividend_rate=row.dividend_rate if row else None,
        dividend_yield=row.dividend_yield if row else None,
        payout_ratio=row.payout_ratio if row else None,

        yf_sector=row.yf_sector if row else None,
        industry=row.industry if row else None,
        employees=row.employees if row else None,
        city=row.city if row else None,
        country=row.country if row else None,
        website=row.website if row else None,
        description=row.description if row else None,

        beta_yf=row.beta_yf if row else None,
    )
    cache.set(cache_key, out)
    return out
