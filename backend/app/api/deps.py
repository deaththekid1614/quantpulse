"""
Shared FastAPI dependencies.

Provides a scoped DB session per request and helpers for parsing the
`range` query parameter used by the history endpoints.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal

# Range param → days of history. `None` means "all rows".
RANGE_TO_DAYS: dict[str, int | None] = {
    "1w":   7,
    "1m":   30,
    "3m":   90,
    "6m":   180,
    "1y":   365,
    "3y":   1095,
    "5y":   1825,
    "max":  None,
}

DEFAULT_RANGE = "1y"


def get_db() -> Iterator[Session]:
    """Yield a SQLAlchemy session, closing it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def resolve_range(range_str: str) -> date | None:
    """
    Convert a range token (e.g. '1y') into a start date.

    Returns None for `max` — callers should treat that as "no lower bound".
    Raises 400 for unknown tokens.
    """
    if range_str not in RANGE_TO_DAYS:
        allowed = ", ".join(RANGE_TO_DAYS.keys())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid range '{range_str}'. Allowed: {allowed}",
        )
    days = RANGE_TO_DAYS[range_str]
    if days is None:
        return None
    return date.today() - timedelta(days=days)
