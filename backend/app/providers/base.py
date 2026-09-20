"""
Abstract provider interfaces.

Every external data source (Yahoo Finance, news RSS, fundamentals APIs)
implements one of these three interfaces. Downstream code (pipeline, ML,
NLP) depends ONLY on these abstractions, never on concrete implementations.

Frozen after Stage 1, except for additive changes to value objects.
Stage 6 (Fundamentals) expanded the Fundamentals dataclass with more
optional fields. No method signature changed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd


# ---------------------------------------------------------------------------
# Canonical schema for OHLCV DataFrames
# ---------------------------------------------------------------------------

OHLCV_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")
OHLCV_INDEX_NAME: str = "date"


# ---------------------------------------------------------------------------
# Value objects returned by providers
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class NewsArticle:
    """One news item about a company or the broader market."""
    ticker: str
    title: str
    url: str
    source: str
    published_at: datetime      # timezone-aware, UTC
    body: str = ""
    summary: str = ""


@dataclass(frozen=True, slots=True)
class Fundamentals:
    """
    Snapshot of a company's fundamental metrics.

    Every field except `ticker` is optional — providers may return partial
    data, and NSE-listed equities genuinely vary in what they report.
    Consumers must tolerate None for any field.

    Units (locked):
      profit_margin, return_on_equity, return_on_assets, payout_ratio
        are fractions (0.18 = 18%).
      dividend_yield is a percent (3.09 = 3.09%).
      debt_to_equity is yfinance's raw value; for NSE it typically comes
        as a percentage (10.211 = 10.211%). Interpretation is a UI concern.
      All market_cap / revenue / debt / cash values are in INR.

    beta_yf is Yahoo's own beta estimate. It is deliberately distinct from
    our computed `beta_60d` feature, which uses local price history.
    """
    ticker: str                                       # required

    # --- identity / as-of ---
    as_of: date | None = None

    # --- market data ---
    current_price:       float | None = None
    previous_close:      float | None = None
    market_cap:          float | None = None
    enterprise_value:    float | None = None
    high_52w:            float | None = None
    low_52w:             float | None = None
    shares_outstanding:  float | None = None

    # --- valuation ---
    pe_trailing:         float | None = None
    price_to_book:       float | None = None
    price_to_sales:      float | None = None

    # --- earnings ---
    eps_trailing:        float | None = None

    # --- revenue / profit ---
    total_revenue:       float | None = None
    gross_profits:       float | None = None
    net_income:          float | None = None
    profit_margin:       float | None = None       # fraction
    return_on_equity:    float | None = None       # fraction
    return_on_assets:    float | None = None       # fraction

    # --- balance sheet ---
    total_debt:          float | None = None
    total_cash:          float | None = None
    debt_to_equity:      float | None = None       # yfinance raw (usually percent)

    # --- dividends ---
    dividend_rate:       float | None = None       # per share, INR
    dividend_yield:      float | None = None       # percent
    payout_ratio:        float | None = None       # fraction

    # --- profile ---
    long_name:           str   | None = None
    yf_sector:           str   | None = None       # Yahoo's coarse sector, kept for reference
    industry:            str   | None = None
    employees:           int   | None = None
    city:                str   | None = None
    country:             str   | None = None
    website:             str   | None = None
    description:         str   | None = None

    # --- reference ---
    beta_yf:             float | None = None       # Yahoo beta (distinct from beta_60d)


# ---------------------------------------------------------------------------
# Provider interfaces
# ---------------------------------------------------------------------------

class MarketDataProvider(ABC):
    """Source of historical daily OHLCV data."""

    @abstractmethod
    def get_daily_ohlcv(
        self,
        ticker: str,
        start: date | datetime | str,
        end: date | datetime | str,
    ) -> pd.DataFrame:
        """
        Return daily OHLCV bars for `ticker` between `start` and `end` inclusive.

        Contract:
          - Index  : pandas.DatetimeIndex, name="date", tz-naive, monotonic ASC
          - Columns: exactly OHLCV_COLUMNS, in that order
          - dtypes : open/high/low/close -> float64, volume -> int64
          - Empty  : return an EMPTY DataFrame with the same schema (no exception)
          - Raises : ProviderError subclasses on unrecoverable failure
        """
        raise NotImplementedError


class NewsProvider(ABC):
    """Source of company / market news articles."""

    @abstractmethod
    def get_news(
        self,
        ticker: str,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[NewsArticle]:
        """
        Return up to `limit` recent news items for `ticker`, newest first.
        `since=None` means "whatever the provider can supply".
        """
        raise NotImplementedError


class FundamentalsProvider(ABC):
    """Source of company fundamentals and profile."""

    @abstractmethod
    def get_fundamentals(self, ticker: str) -> Fundamentals:
        """Return a Fundamentals snapshot. Missing fields stay None."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    """Base class for any provider-level failure."""


class ProviderUnavailable(ProviderError):
    """The underlying source is temporarily unreachable or rate-limited."""


class TickerNotFound(ProviderError):
    """The provider does not recognize the requested ticker."""