"""
Yahoo Finance implementation of the provider interfaces.

Uses yfinance for historical OHLCV and company fundamentals.

This is a historical and slow-moving-data provider. It is not a live tick
feed and not an authoritative fundamentals source — Yahoo occasionally
rate-limits, changes endpoints, or returns partial data. When that
happens, only this file changes, not the rest of the codebase.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

from app.providers.base import (
    OHLCV_COLUMNS,
    OHLCV_INDEX_NAME,
    Fundamentals,
    MarketDataProvider,
    ProviderError,
    ProviderUnavailable,
    TickerNotFound,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _empty_ohlcv() -> pd.DataFrame:
    """Return an empty DataFrame with the exact canonical schema."""
    df = pd.DataFrame({c: pd.Series(dtype="float64") for c in OHLCV_COLUMNS})
    df.index = pd.DatetimeIndex([], name=OHLCV_INDEX_NAME)
    df["volume"] = df["volume"].astype("int64")
    return df


def _coerce_float(v) -> float | None:
    """Return v as a finite float, or None if missing / not numeric / non-finite."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _coerce_int(v) -> int | None:
    f = _coerce_float(v)
    if f is None:
        return None
    return int(f)


def _coerce_str(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("none", "null", "n/a", "nan"):
        return None
    return s


# ---------------------------------------------------------------------------
# provider
# ---------------------------------------------------------------------------

class YahooMarketDataProvider(MarketDataProvider):
    """yfinance-backed historical OHLCV and fundamentals provider."""

    def __init__(self, auto_adjust: bool = True) -> None:
        # auto_adjust=True means prices are adjusted for splits/dividends.
        # This is the correct choice for any historical modelling.
        self._auto_adjust = auto_adjust

    # ------------------------------------------------------------------
    # MarketDataProvider
    # ------------------------------------------------------------------

    def get_daily_ohlcv(
        self,
        ticker: str,
        start: date | datetime | str,
        end: date | datetime | str,
    ) -> pd.DataFrame:
        start_s, end_s = self._normalise_range(start, end)
        log.debug("yahoo: fetching %s [%s .. %s]", ticker, start_s, end_s)

        try:
            raw = yf.download(
                tickers=ticker,
                start=start_s,
                end=end_s,
                interval="1d",
                auto_adjust=self._auto_adjust,
                progress=False,
                threads=False,
                group_by="column",
            )
        except Exception as exc:  # yfinance raises a zoo of exceptions
            raise ProviderUnavailable(f"yahoo request failed for {ticker}: {exc}") from exc

        if raw is None or raw.empty:
            log.info("yahoo: no rows for %s [%s .. %s]", ticker, start_s, end_s)
            return _empty_ohlcv()

        df = self._normalise(raw, ticker)

        if df.empty:
            log.info("yahoo: no usable rows for %s", ticker)
            return _empty_ohlcv()

        return df

    # ------------------------------------------------------------------
    # FundamentalsProvider
    # ------------------------------------------------------------------

    def get_fundamentals(self, ticker: str) -> Fundamentals:
        """
        Fetch company fundamentals via yfinance `.info`.

        Never raises on missing fields — returns a Fundamentals with
        None for anything the provider didn't supply. Raises only on
        network / provider failure so the caller can distinguish
        "data genuinely absent" from "the source is down".
        """
        try:
            yt = yf.Ticker(ticker)
            info = yt.info or {}
        except Exception as exc:
            raise ProviderUnavailable(
                f"yahoo .info failed for {ticker}: {exc}"
            ) from exc

        if not isinstance(info, dict) or not info:
            log.warning("yahoo: empty .info for %s", ticker)
            return Fundamentals(ticker=ticker)

        return Fundamentals(
            ticker=ticker,

            current_price=_coerce_float(info.get("currentPrice")),
            previous_close=_coerce_float(info.get("previousClose")),
            market_cap=_coerce_float(info.get("marketCap")),
            enterprise_value=_coerce_float(info.get("enterpriseValue")),
            high_52w=_coerce_float(info.get("fiftyTwoWeekHigh")),
            low_52w=_coerce_float(info.get("fiftyTwoWeekLow")),
            shares_outstanding=_coerce_float(info.get("sharesOutstanding")),

            pe_trailing=_coerce_float(info.get("trailingPE")),
            price_to_book=_coerce_float(info.get("priceToBook")),
            price_to_sales=_coerce_float(info.get("priceToSalesTrailing12Months")),

            eps_trailing=_coerce_float(info.get("trailingEps")),

            total_revenue=_coerce_float(info.get("totalRevenue")),
            gross_profits=_coerce_float(info.get("grossProfits")),
            net_income=_coerce_float(info.get("netIncomeToCommon")),
            profit_margin=_coerce_float(info.get("profitMargins")),
            return_on_equity=_coerce_float(info.get("returnOnEquity")),
            return_on_assets=_coerce_float(info.get("returnOnAssets")),

            total_debt=_coerce_float(info.get("totalDebt")),
            total_cash=_coerce_float(info.get("totalCash")),
            debt_to_equity=_coerce_float(info.get("debtToEquity")),

            dividend_rate=_coerce_float(info.get("dividendRate")),
            dividend_yield=_coerce_float(info.get("dividendYield")),
            payout_ratio=_coerce_float(info.get("payoutRatio")),

            long_name=_coerce_str(info.get("longName")),
            yf_sector=_coerce_str(info.get("sector")),
            industry=_coerce_str(info.get("industry")),
            employees=_coerce_int(info.get("fullTimeEmployees")),
            city=_coerce_str(info.get("city")),
            country=_coerce_str(info.get("country")),
            website=_coerce_str(info.get("website")),
            description=_coerce_str(info.get("longBusinessSummary")),

            beta_yf=_coerce_float(info.get("beta")),
        )

    # ------------------------------------------------------------------
    # OHLCV internals
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_range(
        start: date | datetime | str,
        end: date | datetime | str,
    ) -> tuple[str, str]:
        """Coerce any accepted start/end to ISO date strings for yfinance."""
        def _to_date(v: date | datetime | str) -> date:
            if isinstance(v, datetime):
                return v.date()
            if isinstance(v, date):
                return v
            return datetime.fromisoformat(str(v)).date()

        s, e = _to_date(start), _to_date(end)
        if e < s:
            raise ProviderError(f"end ({e}) is before start ({s})")
        # yfinance treats `end` as exclusive; add one day so both bounds are inclusive.
        return s.isoformat(), (e + timedelta(days=1)).isoformat()

    @staticmethod
    def _normalise(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """
        Coerce whatever yfinance hands back into the canonical schema.
        """
        df = raw.copy()

        # yfinance sometimes returns MultiIndex columns even for a single ticker.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Rename to canonical lowercase names.
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

        required = set(OHLCV_COLUMNS)
        if not required.issubset(df.columns):
            raise ProviderError(
                f"yahoo returned unexpected columns for {ticker}: {list(df.columns)}"
            )

        df = df[list(OHLCV_COLUMNS)].copy()

        # Index: DatetimeIndex, tz-naive, name="date", monotonic ASC.
        df.index = pd.to_datetime(df.index)
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_localize(None)
        df.index.name = OHLCV_INDEX_NAME
        df = df.sort_index()

        # Drop rows with no close (holidays, partial bars).
        df = df.dropna(subset=["close"])

        # Enforce dtypes.
        for c in ("open", "high", "low", "close"):
            df[c] = df[c].astype("float64")
        df["volume"] = df["volume"].fillna(0).astype("int64")

        # Final guard: no duplicate dates.
        df = df[~df.index.duplicated(keep="last")]

        return df


__all__ = ["YahooMarketDataProvider"]