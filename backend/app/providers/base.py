"""
Abstract provider interfaces.

Every external data source (Yahoo Finance, news RSS, fundamentals APIs)
implements one of these three interfaces. Downstream code (pipeline, ML,
NLP) depends ONLY on these abstractions, never on concrete implementations.

Frozen after Stage 1. If a provider needs a new capability, add a new
method to the relevant ABC AND to every implementation — but do not
rewrite existing signatures.
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
    Every field except `ticker` is optional — providers may return partial data.
    """
    ticker: str
    as_of: date | None = None
    market_cap: float | None = None       # in INR
    pe_ratio: float | None = None
    eps: float | None = None
    revenue: float | None = None          # trailing 12 months
    profit: float | None = None
    dividend_yield: float | None = None
    debt_to_equity: float | None = None
    roe: float | None = None
    roce: float | None = None
    industry: str | None = None
    employees: int | None = None
    headquarters: str | None = None
    description: str | None = None


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
