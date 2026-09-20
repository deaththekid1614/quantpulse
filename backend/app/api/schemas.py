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
# indices
# ---------------------------------------------------------------------------

class IndexQuote(BaseModel):
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
# movers
# ---------------------------------------------------------------------------

class MoverOut(BaseModel):
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
# stats
# ---------------------------------------------------------------------------

class StatsOut(BaseModel):
    ticker: str
    symbol: str
    name:   str
    sector: str
    as_of:  date

    high_52w:           float
    low_52w:            float
    pct_from_52w_high:  float
    pct_from_52w_low:   float

    ret_1d_pct:  float | None
    ret_5d_pct:  float | None
    ret_20d_pct: float | None
    ret_ytd_pct: float | None
    ret_1y_pct:  float | None

    avg_volume_20d: int
    avg_volume_60d: int

    all_time_high: float
    all_time_low:  float


# ---------------------------------------------------------------------------
# fundamentals  (Stage 6)
# ---------------------------------------------------------------------------

class FundamentalsOut(BaseModel):
    """
    Company fundamentals. Every metric is nullable — NSE-listed equities
    genuinely vary in what Yahoo reports. Consumers must render missing
    values as an em-dash or similar, never as a fabricated zero.

    Units:
      profit_margin, return_on_equity, return_on_assets, payout_ratio
        are fractions (0.18 = 18%).
      dividend_yield is a percent (3.09 = 3.09%).
      debt_to_equity is Yahoo's raw value, typically a percent for NSE.
      All currency fields are INR.
    """
    ticker: str
    symbol: str
    name:   str
    sector: str                              # our sector (from universe.json)
    as_of:  date | None = Field(None, description="Date the metrics were captured")

    # --- market data ---
    current_price:      float | None = None
    previous_close:     float | None = None
    market_cap:         float | None = None
    enterprise_value:   float | None = None
    high_52w:           float | None = None
    low_52w:            float | None = None
    shares_outstanding: float | None = None

    # --- valuation ---
    pe_trailing:    float | None = None
    price_to_book:  float | None = None
    price_to_sales: float | None = None

    # --- earnings ---
    eps_trailing: float | None = None

    # --- revenue / profit ---
    total_revenue:    float | None = None
    gross_profits:    float | None = None
    net_income:       float | None = None
    profit_margin:    float | None = None
    return_on_equity: float | None = None
    return_on_assets: float | None = None

    # --- balance sheet ---
    total_debt:     float | None = None
    total_cash:     float | None = None
    debt_to_equity: float | None = None

    # --- dividends ---
    dividend_rate:  float | None = None
    dividend_yield: float | None = None
    payout_ratio:   float | None = None

    # --- profile ---
    yf_sector:   str | None = None       # Yahoo's coarse sector, distinct from ours
    industry:    str | None = None
    employees:   int | None = None
    city:        str | None = None
    country:     str | None = None
    website:     str | None = None
    description: str | None = None

    # --- reference ---
    beta_yf: float | None = None


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------

class ErrorOut(BaseModel):
    detail: str