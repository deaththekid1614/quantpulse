"""
Yahoo Finance implementation of MarketDataProvider.

Uses yfinance. This is a historical-data provider — not a live tick feed.
Yahoo occasionally rate-limits or changes its endpoints; when that happens,
only this file changes, not the rest of the codebase.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

from app.providers.base import (
    OHLCV_COLUMNS,
    OHLCV_INDEX_NAME,
    MarketDataProvider,
    ProviderError,
    ProviderUnavailable,
    TickerNotFound,
)

log = logging.getLogger(__name__)


def _empty_ohlcv() -> pd.DataFrame:
    """Return an empty DataFrame with the exact canonical schema."""
    df = pd.DataFrame({c: pd.Series(dtype="float64") for c in OHLCV_COLUMNS})
    df.index = pd.DatetimeIndex([], name=OHLCV_INDEX_NAME)
    df["volume"] = df["volume"].astype("int64")
    return df


class YahooMarketDataProvider(MarketDataProvider):
    """yfinance-backed historical OHLCV provider."""

    def __init__(self, auto_adjust: bool = True) -> None:
        # auto_adjust=True means prices are adjusted for splits/dividends.
        # This is the correct choice for any historical modelling.
        self._auto_adjust = auto_adjust

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
    # internals
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
