"""
Feature engine — pure functions.

Every function here takes one or more pandas DataFrames and returns a
DataFrame of computed features. No database access, no file IO, no global
state. This makes the engine testable in isolation and safe to reason
about.

Input contract
--------------
`price_df`:  DataFrame with the canonical OHLCV schema
             (index: DatetimeIndex name="date", tz-naive, ascending;
              columns: open, high, low, close, volume)
`index_df`:  same schema, for a market index (e.g. Nifty 50)

Output
------
All `compute_*` helpers return a DataFrame indexed identically to the
input, with feature columns only. Warm-up rows contain NaN — the caller
is responsible for dropping them before persistence.

Build order (Stage 2)
---------------------
  Chunk C  — returns
  Chunk D  — volatility, moving averages, momentum
  Chunk E  — volume, market context, beta, sector context
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# returns
# ---------------------------------------------------------------------------

def compute_returns(price_df: pd.DataFrame) -> pd.DataFrame:
    """
    Log returns over 1, 5, and 20 trading days.

    All three are computed from the `close` column. Log returns are used
    because they add linearly across time and behave better in any model
    that assumes additive effects.
    """
    close = price_df["close"].astype("float64")

    out = pd.DataFrame(index=price_df.index)
    out["ret_1d"]  = np.log(close / close.shift(1))
    out["ret_5d"]  = np.log(close / close.shift(5))
    out["ret_20d"] = np.log(close / close.shift(20))
    return out


# ---------------------------------------------------------------------------
# volatility
# ---------------------------------------------------------------------------

def compute_volatility(price_df: pd.DataFrame) -> pd.DataFrame:
    """
    Rolling realised volatility and average true range.

    vol_20d : rolling 20-day standard deviation of 1-day log returns
    atr_14d : 14-day simple moving average of True Range
              True Range = max(high - low, |high - prev_close|, |low - prev_close|)
    """
    close = price_df["close"].astype("float64")
    high  = price_df["high"].astype("float64")
    low   = price_df["low"].astype("float64")

    ret_1d = np.log(close / close.shift(1))

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    out = pd.DataFrame(index=price_df.index)
    out["vol_20d"] = ret_1d.rolling(window=20, min_periods=20).std(ddof=1)
    out["atr_14d"] = tr.rolling(window=14, min_periods=14).mean()
    return out


# ---------------------------------------------------------------------------
# moving averages
# ---------------------------------------------------------------------------

def compute_moving_averages(price_df: pd.DataFrame) -> pd.DataFrame:
    """
    Simple and exponential moving averages of close, plus ratios of the
    current close to each simple MA.

    SMA : arithmetic rolling mean, window 20 / 50 / 200
    EMA : exponential, span 12 / 26, adjust=False (standard convention)
    ratios: close / sma, expressed as a ratio near 1.0 (not a percentage)
    """
    close = price_df["close"].astype("float64")

    sma_20  = close.rolling(window=20,  min_periods=20).mean()
    sma_50  = close.rolling(window=50,  min_periods=50).mean()
    sma_200 = close.rolling(window=200, min_periods=200).mean()

    ema_12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema_26 = close.ewm(span=26, adjust=False, min_periods=26).mean()

    out = pd.DataFrame(index=price_df.index)
    out["sma_20"]  = sma_20
    out["sma_50"]  = sma_50
    out["sma_200"] = sma_200
    out["ema_12"]  = ema_12
    out["ema_26"]  = ema_26

    out["px_over_sma_20"]  = close / sma_20
    out["px_over_sma_50"]  = close / sma_50
    out["px_over_sma_200"] = close / sma_200
    return out


# ---------------------------------------------------------------------------
# momentum
# ---------------------------------------------------------------------------

def compute_momentum(price_df: pd.DataFrame) -> pd.DataFrame:
    """
    RSI, MACD (line / signal / histogram), and 10-day rate of change.

    RSI-14   : Wilder's smoothing — equivalent to an EMA with alpha = 1/14.
               Ranges 0..100. Undefined (NaN) when both gains and losses
               are zero.
    MACD     : EMA(12) - EMA(26).
    Signal   : EMA(9) of the MACD line.
    Histogram: MACD - Signal.
    ROC-10   : (close / close.shift(10) - 1) * 100, expressed as a percent.
    """
    close = price_df["close"].astype("float64")

    # --- RSI (Wilder) ---
    delta = close.diff()
    gain  = delta.clip(lower=0.0)
    loss  = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs  = avg_gain / avg_loss
    rsi = 100.0 - 100.0 / (1.0 + rs)

    # --- MACD ---
    ema_12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema_26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    macd   = ema_12 - ema_26
    macd_signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    macd_hist   = macd - macd_signal

    # --- ROC ---
    roc_10 = (close / close.shift(10) - 1.0) * 100.0

    out = pd.DataFrame(index=price_df.index)
    out["rsi_14"]      = rsi
    out["macd"]        = macd
    out["macd_signal"] = macd_signal
    out["macd_hist"]   = macd_hist
    out["roc_10"]      = roc_10
    return out


# ---------------------------------------------------------------------------
# volume
# ---------------------------------------------------------------------------

def compute_volume(price_df: pd.DataFrame) -> pd.DataFrame:
    """
    Relative volume and volume z-score, both against the PRIOR 20-day
    baseline (today excluded).

    rel_volume_20d : today's volume / mean of previous 20 days' volume.
                     1.0 = normal, >2.0 = unusually heavy, <0.5 = light.
    volume_z_20d   : (today - prior mean) / prior std. Undefined when the
                     prior 20-day std is zero.

    The rolling window is shifted by 1 so the baseline at time t uses
    rows t-20..t-1. This avoids diluting the signal with today's own
    value and matches the standard definition of relative volume.
    """
    vol = price_df["volume"].astype("float64")

    prior_mean = vol.rolling(window=20, min_periods=20).mean().shift(1)
    prior_std  = vol.rolling(window=20, min_periods=20).std(ddof=1).shift(1)

    rel = vol / prior_mean

    # Guard against zero std → avoid infinities.
    safe_std = prior_std.where(prior_std > 0, np.nan)
    z = (vol - prior_mean) / safe_std

    out = pd.DataFrame(index=price_df.index)
    out["rel_volume_20d"] = rel
    out["volume_z_20d"]   = z
    return out


# ---------------------------------------------------------------------------
# market context
# ---------------------------------------------------------------------------

def compute_market_context(
    price_df: pd.DataFrame,
    index_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Broad-market context from a market index (typically Nifty 50).

    mkt_ret_1d : 1-day log return of the index, aligned to price_df's index.
    mkt_ret_5d : 5-day log return of the index, aligned to price_df's index.

    The output index is exactly price_df.index. Index dates that don't
    overlap with price_df dates are dropped, and price_df dates with no
    matching index date get NaN (later dropped by the caller).
    """
    mkt_close = index_df["close"].astype("float64")

    mkt_ret_1d = np.log(mkt_close / mkt_close.shift(1))
    mkt_ret_5d = np.log(mkt_close / mkt_close.shift(5))

    out = pd.DataFrame(index=price_df.index)
    out["mkt_ret_1d"] = mkt_ret_1d.reindex(price_df.index)
    out["mkt_ret_5d"] = mkt_ret_5d.reindex(price_df.index)
    return out


# ---------------------------------------------------------------------------
# beta
# ---------------------------------------------------------------------------

def compute_beta(
    price_df: pd.DataFrame,
    index_df: pd.DataFrame,
    window: int = 60,
) -> pd.DataFrame:
    """
    Rolling beta of the stock vs a market index.

    beta = cov(stock_ret, market_ret) / var(market_ret), estimated over a
    rolling `window`-day window using 1-day log returns.

    Rows without a full window of overlapping data are NaN.

    Note: extreme values (> 3 or < 0) are real and expected during
    idiosyncratic events (e.g. Adani Group stocks in March–April 2023,
    demergers, index-inclusion flows). Winsorizing — if desired — is a
    modelling concern, not a feature-engineering one.
    """
    stock_ret = np.log(
        price_df["close"].astype("float64")
        / price_df["close"].astype("float64").shift(1)
    )
    mkt_ret = np.log(
        index_df["close"].astype("float64")
        / index_df["close"].astype("float64").shift(1)
    )

    # Align on the intersection of dates.
    joined = pd.concat(
        [stock_ret.rename("s"), mkt_ret.rename("m")],
        axis=1,
        join="inner",
    )

    cov = joined["s"].rolling(window=window, min_periods=window).cov(joined["m"])
    var = joined["m"].rolling(window=window, min_periods=window).var(ddof=1)

    # Guard against zero market variance.
    safe_var = var.where(var > 0, np.nan)
    beta_aligned = cov / safe_var

    out = pd.DataFrame(index=price_df.index)
    out["beta_60d"] = beta_aligned.reindex(price_df.index)
    return out


# ---------------------------------------------------------------------------
# sector context
# ---------------------------------------------------------------------------

def compute_sector_context(
    price_df: pd.DataFrame,
    peer_closes: pd.DataFrame,
) -> pd.DataFrame:
    """
    Average same-day 1-day log return of the target's sector peers.

    `peer_closes` is a DataFrame with one column per peer ticker and the
    same date index as price_df. The target itself MUST be excluded by the
    caller — this function does not know which column is the target.

    sector_ret_1d : mean of peers' 1-day log returns on the same date.

    Returns NaN when there are no peers at all (a single-member sector)
    or when every peer is missing a return on a given date. The
    fill-with-zero policy for "no sector signal" is applied in
    `compute_all`, not here, so this function stays a pure average.
    """
    if peer_closes.empty:
        out = pd.DataFrame(index=price_df.index)
        out["sector_ret_1d"] = np.nan
        return out

    peer_rets = np.log(peer_closes.astype("float64") / peer_closes.astype("float64").shift(1))
    sector_ret = peer_rets.mean(axis=1, skipna=True)

    out = pd.DataFrame(index=price_df.index)
    out["sector_ret_1d"] = sector_ret.reindex(price_df.index)
    return out


# ---------------------------------------------------------------------------
# combined helper — used by build_features.py
# ---------------------------------------------------------------------------

FEATURE_COLUMNS: tuple[str, ...] = (
    "ret_1d", "ret_5d", "ret_20d",
    "vol_20d", "atr_14d",
    "sma_20", "sma_50", "sma_200", "ema_12", "ema_26",
    "px_over_sma_20", "px_over_sma_50", "px_over_sma_200",
    "rsi_14", "macd", "macd_signal", "macd_hist", "roc_10",
    "rel_volume_20d", "volume_z_20d",
    "mkt_ret_1d", "mkt_ret_5d", "beta_60d",
    "sector_ret_1d",
)


def compute_all(
    price_df: pd.DataFrame,
    nifty_df: pd.DataFrame,
    peer_closes: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute every Stage 2 feature for one security and return them in a
    single DataFrame with columns in FEATURE_COLUMNS order.

    NaN policy:
      - Most features are NaN only during warm-up and are dropped by the
        caller.
      - `sector_ret_1d` is filled with 0.0 when it is NaN after
        computation. This is the "no sector signal, neutral" policy. It
        matters for single-member sectors (Telecom — Bharti Airtel) and
        for dates where every peer is missing a return. Without it, the
        caller's dropna would remove entire tickers.

    Any remaining inf values are converted to NaN so the caller's dropna
    handles them uniformly.
    """
    parts = [
        compute_returns(price_df),
        compute_volatility(price_df),
        compute_moving_averages(price_df),
        compute_momentum(price_df),
        compute_volume(price_df),
        compute_market_context(price_df, nifty_df),
        compute_beta(price_df, nifty_df),
        compute_sector_context(price_df, peer_closes),
    ]
    combined = pd.concat(parts, axis=1).loc[:, list(FEATURE_COLUMNS)]

    # Fill sector signal with neutral 0.0 when unknown.
    combined["sector_ret_1d"] = combined["sector_ret_1d"].fillna(0.0)

    # Any inf (from division guards that slipped through) becomes NaN.
    combined = combined.replace([np.inf, -np.inf], np.nan)

    return combined