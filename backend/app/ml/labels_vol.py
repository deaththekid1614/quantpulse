"""
Volatility forecast labels — Stage 8B-v2.

Binary labels for forward realized volatility, in the same style as the
binary direction labels in app.ml.labels.

Definition
----------
For a horizon h (in trading days):

    future_realized_vol_h[t] = std( log_returns[t+1 : t+h+1], ddof=1 ) * sqrt(252)

where log_returns[i] = log( close[i] / close[i-1] ).

`future_realized_vol_h[t]` is the annualized realized volatility of the
next h trading days, expressed as a fraction (0.20 = 20%).

The binary label is defined relative to a threshold that the CALLER
supplies:

    label_vol_h[t] = 'high_vol'  if future_realized_vol_h[t] >  threshold_h
                   = 'low_vol'   if future_realized_vol_h[t] <= threshold_h
                   = None        if future_realized_vol_h[t] is NaN

The threshold is NOT computed here. It is the median of
`future_realized_vol_h` in the training split only, computed by the
dataset builder (app.ml.vol_dataset). Computing it here would require
seeing validation or test data and would violate the leakage policy.

Why volatility is predictable
-----------------------------
Realized volatility is strongly autocorrelated: high-volatility days
cluster together, low-volatility days cluster together. This is one of
the most robust facts in finance across decades and asset classes.
Unlike direction, volatility has a stable, learnable structure.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# Annualization factor for daily volatility → annualized. 252 trading
# days per year is the standard convention for NSE and most global
# exchanges.
TRADING_DAYS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------

def compute_future_realized_vol(
    close: pd.Series,
    horizon: int,
) -> pd.Series:
    """
    Annualized realized volatility over the next `horizon` trading days.

    Returns a Series with the same index as `close`. The last `horizon`
    values are NaN because no future data exists for them.

    `horizon` must be >= 2 — sample standard deviation of a single
    value is undefined.
    """
    if horizon < 2:
        raise ValueError(f"horizon must be >= 2, got {horizon}")

    c = close.astype("float64")
    log_ret = np.log(c / c.shift(1))

    # At index t we want std of log_ret[t+1 : t+h+1].
    # rolling(h).std() at index t gives std of log_ret[t-h+1 : t+1].
    # So we compute rolling(h).std() and shift by -h: the value that
    # was at index t+h moves to index t, giving std of log_ret[t+1 :
    # t+h+1]. Exactly what we want.
    rolling_std = log_ret.rolling(window=horizon, min_periods=horizon).std(ddof=1)
    future_vol = rolling_std.shift(-horizon) * np.sqrt(TRADING_DAYS_PER_YEAR)
    return future_vol


def classify_vol_binary(
    future_vol: pd.Series,
    threshold: float,
) -> pd.Series:
    """
    Bin future volatility into 'high_vol' / 'low_vol' / None.

    - 'high_vol'  if future_vol > threshold
    - 'low_vol'   if future_vol <= threshold
    - None        if future_vol is NaN

    Boundary value (future_vol == threshold) is classified as 'low_vol',
    matching the median convention: exactly half the training rows fall
    at or below the training median.
    """
    out = pd.Series(index=future_vol.index, dtype="object")

    fv = future_vol.astype("float64")
    valid = fv.notna()
    high = valid & (fv > threshold)
    low  = valid & (fv <= threshold)

    out[high] = "high_vol"
    out[low]  = "low_vol"
    return out


# ---------------------------------------------------------------------------
# multi-horizon
# ---------------------------------------------------------------------------

def build_future_vol(
    price_df: pd.DataFrame,
    horizons: tuple[int, ...] = (7, 15, 30),
) -> pd.DataFrame:
    """
    Compute raw forward realized volatility for multiple horizons.

    Returns a DataFrame indexed like price_df.index, with one column
    per horizon named `future_vol_{h}d`. Rows where future data does not
    exist (last h rows of the series) are NaN.

    This function returns ONLY the raw volatility values. It does NOT
    compute binary labels. Labels are added by the dataset builder
    after the training-median threshold has been determined.
    """
    if "close" not in price_df.columns:
        raise ValueError("price_df must contain a 'close' column")

    close = price_df["close"].astype("float64").sort_index()

    out = pd.DataFrame(index=close.index)
    for h in horizons:
        out[f"future_vol_{h}d"] = compute_future_realized_vol(close, h)
    return out


def apply_vol_thresholds(
    future_vol_df: pd.DataFrame,
    thresholds: dict[int, float],
    horizons: tuple[int, ...] = (7, 15, 30),
) -> pd.DataFrame:
    """
    Given a DataFrame from `build_future_vol` and a mapping from
    horizon → threshold, produce a DataFrame with the label columns
    added.

    Columns in the output:
      - the original future_vol_{h}d columns (unchanged)
      - a new label_vol_{h}d column for each horizon in `thresholds`
    """
    missing = [h for h in horizons if h not in thresholds]
    if missing:
        raise ValueError(f"thresholds missing horizons: {missing}")

    out = future_vol_df.copy()
    for h in horizons:
        col = f"future_vol_{h}d"
        if col not in out.columns:
            raise ValueError(f"missing column {col} in future_vol_df")
        out[f"label_vol_{h}d"] = classify_vol_binary(out[col], thresholds[h])
    return out


def label_columns_vol(horizons: tuple[int, ...] = (7, 15, 30)) -> list[str]:
    """Names of the volatility label columns for a horizon set."""
    return [f"label_vol_{h}d" for h in horizons]


def raw_columns_vol(horizons: tuple[int, ...] = (7, 15, 30)) -> list[str]:
    """Names of the raw forward-volatility columns for a horizon set."""
    return [f"future_vol_{h}d" for h in horizons]


__all__ = [
    "TRADING_DAYS_PER_YEAR",
    "compute_future_realized_vol",
    "classify_vol_binary",
    "build_future_vol",
    "apply_vol_thresholds",
    "label_columns_vol",
    "raw_columns_vol",
]
