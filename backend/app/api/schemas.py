"""
Pydantic v2 response models for the Quantpulse read API.

Every route returns one of these. Defined once, reused everywhere. No
route returns a raw ORM object or a raw dict.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# securities
# ---------------------------------------------------------------------------

class SecurityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ticker: str
    symbol: str
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
    change_1d:       float | None = None
    change_1d_pct:   float | None = None
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
# fundamentals
# ---------------------------------------------------------------------------

class FundamentalsOut(BaseModel):
    ticker: str
    symbol: str
    name:   str
    sector: str
    as_of:  date | None = None

    current_price:      float | None = None
    previous_close:     float | None = None
    market_cap:         float | None = None
    enterprise_value:   float | None = None
    high_52w:           float | None = None
    low_52w:            float | None = None
    shares_outstanding: float | None = None

    pe_trailing:    float | None = None
    price_to_book:  float | None = None
    price_to_sales: float | None = None

    eps_trailing: float | None = None

    total_revenue:    float | None = None
    gross_profits:    float | None = None
    net_income:       float | None = None
    profit_margin:    float | None = None
    return_on_equity: float | None = None
    return_on_assets: float | None = None

    total_debt:     float | None = None
    total_cash:     float | None = None
    debt_to_equity: float | None = None

    dividend_rate:  float | None = None
    dividend_yield: float | None = None
    payout_ratio:   float | None = None

    yf_sector:   str | None = None
    industry:    str | None = None
    employees:   int | None = None
    city:        str | None = None
    country:     str | None = None
    website:     str | None = None
    description: str | None = None

    beta_yf: float | None = None


# ---------------------------------------------------------------------------
# news  (Stage 7)
# ---------------------------------------------------------------------------

class NewsArticleOut(BaseModel):
    """
    One news article, as stored and scored.

    - sentiment_label: 'positive' | 'neutral' | 'negative'
    - sentiment_score: VADER+overlay compound in [-1, 1]
    - relevance_score: 0–1, how confident we are this article is about the
      security. Articles below 0.30 are never stored.
    - importance_score: 0–1, how likely this article is to matter. Combines
      publisher reputation, recency, and market-impact keywords.
    """
    title:            str
    url:              str
    source:           str | None = None
    published_at:     datetime
    sentiment_label:  str | None = None
    sentiment_score:  float | None = None
    relevance_score:  float | None = None
    importance_score: float | None = None


class NewsFeedOut(BaseModel):
    ticker: str
    symbol: str
    name:   str
    sector: str
    count:  int
    articles: list[NewsArticleOut]


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------

class ErrorOut(BaseModel):
    detail: str