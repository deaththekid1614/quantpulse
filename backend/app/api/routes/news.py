"""
News feed endpoint.

  GET /api/securities/{ticker}/news?limit=20&min_importance=0.0

Returns the freshest articles for a security, newest first, optionally
filtered by a minimum importance score. Articles below the ingest-time
relevance floor (0.30) are never in the DB to begin with.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cache import get_cache
from app.api.deps import get_db
from app.api.schemas import NewsArticleOut, NewsFeedOut
from app.db.models import NewsArticleRow, Security

router = APIRouter()


@router.get(
    "/securities/{ticker}/news",
    response_model=NewsFeedOut,
    summary="News feed for one security",
)
def get_news(
    ticker: str,
    limit: int = Query(20, ge=1, le=100, description="Max articles to return"),
    min_importance: float = Query(
        0.0, ge=0.0, le=1.0,
        description="Only return articles with importance_score >= this value",
    ),
    db: Session = Depends(get_db),
) -> NewsFeedOut:
    cache = get_cache()
    cache_key = f"news:{ticker}:{limit}:{min_importance}"
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

    stmt = (
        select(NewsArticleRow)
        .where(NewsArticleRow.security_id == sec.id)
        .order_by(NewsArticleRow.published_at.desc())
        .limit(limit)
    )
    if min_importance > 0.0:
        stmt = stmt.where(NewsArticleRow.importance_score >= min_importance)

    rows = db.execute(stmt).scalars().all()

    out = NewsFeedOut(
        ticker=sec.ticker,
        symbol=sec.symbol,
        name=sec.name,
        sector=sec.sector,
        count=len(rows),
        articles=[
            NewsArticleOut(
                title=r.title,
                url=r.url,
                source=r.source,
                published_at=r.published_at,
                sentiment_label=r.sentiment_label,
                sentiment_score=r.sentiment_score,
                relevance_score=r.relevance_score,
                importance_score=r.importance_score,
            )
            for r in rows
        ],
    )
    cache.set(cache_key, out)
    return out
