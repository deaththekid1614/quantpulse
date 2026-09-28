"""
Binary forecast labels.

Pure functions that turn historical prices into binary supervised
learning labels. No DB access, no training, no side effects.

Label definition (locked, Stage 8A — binary):

  For a horizon h (in trading days):
    future_return_h = log( close[t+h] / close[t] )
    label_h         = 'up'   if future_return_h > 0
                    = 'down' if future_return_h < 0
                    = None   if future_return_h is exactly 0
                             (vanishingly rare; dropped by the caller)
                             or if future data does not exist (last h rows)

Why binary and not 3-class (up/flat/down)?
  The 3-class formulation with a volatility-scaled flat band was tested
  and produced a degenerate classifier: on 4 years of Nifty 50 data
  across 50 securities, accuracy was 0.40 with the model collapsing to
  near-50% predictions of the majority class. The flat class absorbs
  ~38% of rows and dominates the learning signal. Every serious
  forecasting product uses binary up/down. We join them.

Why log returns?
  Additive across time: log(P2/P0) = log(P1/P0) + log(P2/P1). Consistent
  with ret_1d / ret_5d / ret_20d from Stage 2.

Leakage guarantee:
  Future returns use close prices strictly AFTER t. No feature at time t
  uses information from t+1 onwards. There is no shared information
  between features and labels at time t other than close[t] itself,
  which is knowable at t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------

def compute_future_return(close: pd.Series, horizon: int) -> pd.Series:
    """
    Log return from close[t] to close[t+horizon].

    The last `horizon` rows have no future data and are NaN.
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    c = close.astype("float64")
    return np.log(c.shift(-horizon) / c)


def classify_binary(future_return: pd.Series) -> pd.Series:
    """
    Classify each future return as 'up', 'down', or None.

    - 'up'   if future_return > 0
    - 'down' if future_return < 0
    - None   if future_return is NaN or exactly 0

    Returns a Series of dtype 'object'.
    """
    fr = future_return.astype("float64")

    out = pd.Series(index=fr.index, dtype="object")

    valid = fr.notna()
    up    = valid & (fr > 0)
    down  = valid & (fr < 0)
    # exactly-zero rows are neither up nor down → left as None

    out[up]   = "up"
    out[down] = "down"

    return out


# ---------------------------------------------------------------------------
# multi-horizon
# ---------------------------------------------------------------------------

def build_binary_labels(
    price_df: pd.DataFrame,
    horizons: tuple[int, ...] = (7, 15, 30),
) -> pd.DataFrame:
    """
    Build a wide binary label DataFrame for all horizons.

    Input:
      price_df — DataFrame indexed by date, must contain 'close'
      horizons — tuple of positive ints, e.g. (7, 15, 30)

    Output: DataFrame indexed on price_df.index, with these columns per
    horizon h:

      future_return_{h}d   float64, NaN for last h rows
      label_{h}d           object  ('up' | 'down' | None)

    Rows are sorted ascending by date. No data is dropped — the caller
    decides how to handle NaN labels.
    """
    if "close" not in price_df.columns:
        raise ValueError("price_df must contain a 'close' column")

    close = price_df["close"].astype("float64").sort_index()

    out = pd.DataFrame(index=close.index)

    for h in horizons:
        fr = compute_future_return(close, h)
        out[f"future_return_{h}d"] = fr
        out[f"label_{h}d"]         = classify_binary(fr)

    return out


def label_columns(horizons: tuple[int, ...] = (7, 15, 30)) -> list[str]:
    """Convenience: the names of the label columns for a horizon set."""
    return [f"label_{h}d" for h in horizons]


__all__ = [
    "compute_future_return",
    "classify_binary",
    "build_binary_labels",
    "label_columns",
]