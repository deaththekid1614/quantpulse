"""
Pydantic v2 response models for the Quantpulse read API.

Every route returns one of these. Defined once, reused everywhere. No
route returns a raw ORM object or a raw dict.

Feature values are exposed as a dict keyed by column name rather than
positional fields, so adding a new feature in Stage 8 does not require
touching this file.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# securities
# ---------------------------------------------------------------------------

class SecurityOut(BaseModel):
    """Public metadata for one security."""
    model_config = ConfigDict(from_attributes=True)

    ticker: str = Field(..., description="Yahoo-format ticker, e.g. TCS.NS")
    symbol: str = Field(..., description="NSE symbol, e.g. TCS")
    name:   str
    sector: str


class SecurityListOut(BaseModel):
    count: int
    securities: list[SecurityOut]


# ---------------------------------------------------------------------------
# prices
# ---------------------------------------------------------------------------

class PriceBar(BaseModel):
    """One daily OHLCV bar."""
    date:   date
    open:   float
    high:   float
    low:    float
    close:  float
    volume: int


class PriceHistoryOut(BaseModel):
    ticker: str
    symbol: str
    name:   str
    sector: str
    range:  str
    count:  int
    data:   list[PriceBar]


# ---------------------------------------------------------------------------
# features
# ---------------------------------------------------------------------------

class FeatureRow(BaseModel):
    """One day's feature vector. Keys mirror FEATURE_COLUMNS from features.py."""
    date:     date
    features: dict[str, float]


class FeatureHistoryOut(BaseModel):
    ticker: str
    symbol: str
    name:   str
    sector: str
    range:  str
    count:  int
    data:   list[FeatureRow]


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

class LatestPrice(BaseModel):
    date:   date
    open:   float
    high:   float
    low:    float
    close:  float
    volume: int


class SnapshotOut(BaseModel):
    """
    Everything the frontend needs to render the top of the stock page.

    `change_1d` and `change_1d_pct` are None if the security has fewer
    than two price rows in the DB (not expected, but defensive).
    """
    ticker:          str
    symbol:          str
    name:            str
    sector:          str
    as_of:           date
    price:           LatestPrice
    change_1d:       float | None = Field(None, description="Absolute close change vs previous session")
    change_1d_pct:   float | None = Field(None, description="Percent change vs previous session")
    features:        dict[str, float] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# indices  (Stage 4)
# ---------------------------------------------------------------------------

class IndexQuote(BaseModel):
    """Latest bar and change for one market index."""
    symbol:         str
    name:           str
    as_of:          date
    close:          float
    change_1d:      float | None
    change_1d_pct:  float | None


class IndexSnapshotOut(BaseModel):
    as_of:   date
    indices: list[IndexQuote]


# ---------------------------------------------------------------------------
# movers  (Stage 4)
# ---------------------------------------------------------------------------

class MoverOut(BaseModel):
    """One security in the top-movers list."""
    ticker:        str
    symbol:        str
    name:          str
    sector:        str
    close:         float
    change_1d_pct: float
    volume:        int


class MoversOut(BaseModel):
    as_of:  date
    count:  int
    movers: list[MoverOut]


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------

class ErrorOut(BaseModel):
    detail: str