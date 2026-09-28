"""
Rich features — news aggregates + market context + cross-sectional.

Three pure-function groups:

  compute_news_features       (7 columns, per ticker per date)
  compute_market_features     (8 columns, per date; broadcast to all tickers)
  compute_cross_sectional_features
                              (6 columns, per ticker per date)

No DB access, no side effects. The caller assembles input frames from
the DB and hands them here.

Warm-up policy:
  - News features default to 0.0 when the window is empty.
  - Market features are NaN during rolling warm-up; mkt_stress is always
    finite (missing components contribute 0).
  - Cross-sectional pct_from_52w_high, corr_to_nifty_60d, and
    beta_residual_5d are NaN during their rolling warm-up.
  - HistGradientBoostingClassifier handles NaN natively, so these warm-
    up NaNs do not need to be dropped before training.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# canonical schemas
# ---------------------------------------------------------------------------

NEWS_FEATURE_COLUMNS: tuple[str, ...] = (
    "news_sent_7d_mean",
    "news_count_7d",
    "news_sent_30d_mean",
    "news_sent_30d_std",
    "news_count_30d",
    "news_importance_wmean_30d",
    "news_pos_frac_30d",
)

MARKET_FEATURE_COLUMNS: tuple[str, ...] = (
    "vix_level",
    "vix_change_5d",
    "vix_zscore_60d",
    "nifty_ret_20d",
    "nifty_drawdown_60d",
    "nifty_vol_20d",
    "breadth_5d",
    "mkt_stress",
)

CROSS_SECTIONAL_FEATURE_COLUMNS: tuple[str, ...] = (
    "sector_rank_ret_20d",
    "universe_rank_ret_5d",
    "pct_from_52w_high",
    "corr_to_nifty_60d",
    "beta_residual_5d",
    "sector_dispersion_20d",
)


def news_feature_columns() -> list[str]:
    return list(NEWS_FEATURE_COLUMNS)


def market_feature_columns() -> list[str]:
    return list(MARKET_FEATURE_COLUMNS)


def cross_sectional_feature_columns() -> list[str]:
    return list(CROSS_SECTIONAL_FEATURE_COLUMNS)


# ===========================================================================
# internal helpers
# ===========================================================================

def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    """Strip tz, normalize to midnight, dedupe, sort ascending."""
    if df is None or df.empty:
        return df
    out = df.copy()
    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    out.index = out.index.normalize()
    out = out.sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out


def _sector_groups(tickers: list[str], sector_map: dict[str, str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for t in tickers:
        s = sector_map.get(t, "Unknown")
        groups.setdefault(s, []).append(t)
    return groups


# ===========================================================================
# NEWS AGGREGATES
# ===========================================================================

def _empty_news_features(dates: pd.DatetimeIndex) -> pd.DataFrame:
    out = pd.DataFrame(0.0, index=dates, columns=list(NEWS_FEATURE_COLUMNS))
    out["news_count_7d"]  = out["news_count_7d"].astype("int64")
    out["news_count_30d"] = out["news_count_30d"].astype("int64")
    return out


def compute_news_features(
    dates: pd.DatetimeIndex,
    news_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aggregate news articles into a fixed set of features per date.

    See Stage 8B Chunk A for the full contract.
    """
    if not isinstance(dates, pd.DatetimeIndex):
        dates = pd.DatetimeIndex(dates)
    if dates.tz is not None:
        dates = dates.tz_localize(None)
    dates = dates.normalize()
    dates.name = "date"

    if len(dates) == 0:
        return _empty_news_features(dates)
    if news_df is None or news_df.empty:
        return _empty_news_features(dates)

    required = {"published_at", "sentiment_score", "sentiment_label", "importance_score"}
    missing = required - set(news_df.columns)
    if missing:
        raise ValueError(f"news_df is missing columns: {sorted(missing)}")

    n = news_df.copy()
    n["published_at"] = pd.to_datetime(n["published_at"], utc=True).dt.tz_localize(None)
    n["date"] = n["published_at"].dt.normalize()

    n["sentiment_score"]  = pd.to_numeric(n["sentiment_score"],  errors="coerce").fillna(0.0)
    n["importance_score"] = pd.to_numeric(n["importance_score"], errors="coerce").fillna(0.0)

    n["sent_sq"]     = n["sentiment_score"] ** 2
    n["imp_x_sent"]  = n["importance_score"] * n["sentiment_score"]
    n["is_positive"] = (n["sentiment_label"] == "positive").astype("int64")
    n["is_any"]      = 1

    daily = (
        n.groupby("date", sort=True)
        .agg(
            count        = ("is_any",          "sum"),
            sum_sent     = ("sentiment_score", "sum"),
            sum_sent_sq  = ("sent_sq",         "sum"),
            pos_count    = ("is_positive",     "sum"),
            sum_imp      = ("importance_score", "sum"),
            sum_imp_sent = ("imp_x_sent",      "sum"),
        )
        .sort_index()
    )

    start = min(daily.index.min(), dates.min())
    end   = max(daily.index.max(), dates.max())
    full_index = pd.date_range(start, end, freq="D", name="date")
    daily = daily.reindex(full_index, fill_value=0)

    roll7  = daily.rolling(window=7,  min_periods=1).sum()
    roll30 = daily.rolling(window=30, min_periods=1).sum()

    r7  = roll7.reindex(dates).fillna(0.0)
    r30 = roll30.reindex(dates).fillna(0.0)

    out = pd.DataFrame(index=dates)

    count_7 = r7["count"].astype("int64")
    out["news_count_7d"] = count_7
    out["news_sent_7d_mean"] = (
        r7["sum_sent"] / count_7.where(count_7 > 0, 1)
    ).where(count_7 > 0, 0.0)

    count_30 = r30["count"].astype("int64")
    out["news_count_30d"] = count_30

    mean_30 = (
        r30["sum_sent"] / count_30.where(count_30 > 0, 1)
    ).where(count_30 > 0, 0.0)
    out["news_sent_30d_mean"] = mean_30

    mean_sq_30 = (
        r30["sum_sent_sq"] / count_30.where(count_30 > 0, 1)
    ).where(count_30 > 0, 0.0)
    var_30 = (mean_sq_30 - mean_30 ** 2).clip(lower=0.0)
    out["news_sent_30d_std"] = np.sqrt(var_30)

    sum_imp      = r30["sum_imp"]
    sum_imp_sent = r30["sum_imp_sent"]
    out["news_importance_wmean_30d"] = (
        sum_imp_sent / sum_imp.where(sum_imp > 0, 1)
    ).where(sum_imp > 0, 0.0)

    out["news_pos_frac_30d"] = (
        r30["pos_count"] / count_30.where(count_30 > 0, 1)
    ).where(count_30 > 0, 0.0)

    out = out.loc[:, list(NEWS_FEATURE_COLUMNS)]
    out = out.replace([np.inf, -np.inf], 0.0).fillna(0.0)
    return out


# ===========================================================================
# MARKET CONTEXT
# ===========================================================================

def _empty_market_features(dates: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(np.nan, index=dates, columns=list(MARKET_FEATURE_COLUMNS))


def compute_market_features(
    dates: pd.DatetimeIndex,
    indices_df: pd.DataFrame,
    universe_returns: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Compute market-context features for a set of dates.

    See Stage 8B Chunk B for the full contract. `universe_returns`
    contains 1-day LOG returns per security.
    """
    if not isinstance(dates, pd.DatetimeIndex):
        dates = pd.DatetimeIndex(dates)
    if dates.tz is not None:
        dates = dates.tz_localize(None)
    dates = dates.normalize()
    dates.name = "date"

    if len(dates) == 0:
        return _empty_market_features(dates)
    if indices_df is None or indices_df.empty:
        return _empty_market_features(dates)

    required = {"vix_close", "nifty_close"}
    missing = required - set(indices_df.columns)
    if missing:
        raise ValueError(f"indices_df is missing columns: {sorted(missing)}")

    idx = _normalize_index(indices_df)

    vix   = idx["vix_close"].astype("float64")
    nifty = idx["nifty_close"].astype("float64")

    vix_change_5d = np.log(vix / vix.shift(5))
    vix_mean_60   = vix.rolling(window=60, min_periods=60).mean()
    vix_std_60    = vix.rolling(window=60, min_periods=60).std(ddof=1)
    vix_z = (vix - vix_mean_60) / vix_std_60.where(vix_std_60 > 0, np.nan)

    nifty_ret_20d  = np.log(nifty / nifty.shift(20))
    nifty_high_60  = nifty.rolling(window=60, min_periods=60).max()
    nifty_drawdown = (nifty - nifty_high_60) / nifty_high_60.where(nifty_high_60 > 0, np.nan)

    nifty_daily_ret = np.log(nifty / nifty.shift(1))
    nifty_vol_20d   = nifty_daily_ret.rolling(window=20, min_periods=20).std(ddof=1)

    if universe_returns is not None and not universe_returns.empty:
        ur = _normalize_index(universe_returns)
        r5 = ur.rolling(window=5, min_periods=5).sum()
        positive = (r5 > 0).astype("float64")
        breadth_series = positive.mean(axis=1, skipna=True)
    else:
        breadth_series = pd.Series(0.5, index=idx.index)

    z_clip   = (vix_z / 2.0).clip(lower=0.0, upper=1.0).fillna(0.0)
    dd_clip  = (-nifty_drawdown * 10.0).clip(lower=0.0, upper=1.0).fillna(0.0)
    br_clip  = (1.0 - breadth_series).clip(lower=0.0, upper=1.0).fillna(0.0)
    stress = (z_clip + dd_clip + br_clip) / 3.0

    df = pd.DataFrame(index=idx.index)
    df["vix_level"]          = vix
    df["vix_change_5d"]      = vix_change_5d
    df["vix_zscore_60d"]     = vix_z
    df["nifty_ret_20d"]      = nifty_ret_20d
    df["nifty_drawdown_60d"] = nifty_drawdown
    df["nifty_vol_20d"]      = nifty_vol_20d
    df["breadth_5d"]         = breadth_series.reindex(idx.index)
    df["mkt_stress"]         = stress

    out = df.reindex(dates)
    out = out.loc[:, list(MARKET_FEATURE_COLUMNS)]
    out = out.replace([np.inf, -np.inf], np.nan)
    return out


# ===========================================================================
# CROSS-SECTIONAL
# ===========================================================================

def compute_cross_sectional_features(
    close_wide: pd.DataFrame,
    ret5_wide: pd.DataFrame,
    ret20_wide: pd.DataFrame,
    sector_map: dict[str, str],
    nifty_returns: pd.Series | None = None,
) -> pd.DataFrame:
    """
    Compute cross-sectional features in long format.

    Parameters
    ----------
    close_wide : pd.DataFrame
        Index = date, columns = ticker, values = close price.
    ret5_wide, ret20_wide : pd.DataFrame
        Same shape as close_wide, values = 5-day and 20-day log returns.
    sector_map : dict[str, str]
        ticker → sector name.
    nifty_returns : pd.Series | None
        Daily log returns of Nifty 50, index = date. When None,
        corr_to_nifty_60d and beta_residual_5d are NaN.

    Returns
    -------
    pd.DataFrame with MultiIndex (ticker, date) and columns
    CROSS_SECTIONAL_FEATURE_COLUMNS.
    """
    if close_wide is None or close_wide.empty:
        return pd.DataFrame(columns=list(CROSS_SECTIONAL_FEATURE_COLUMNS))

    close_wide = _normalize_index(close_wide)
    ret5_wide  = _normalize_index(ret5_wide)  if ret5_wide  is not None else pd.DataFrame(index=close_wide.index)
    ret20_wide = _normalize_index(ret20_wide) if ret20_wide is not None else pd.DataFrame(index=close_wide.index)

    common = (
        set(close_wide.columns)
        & set(ret5_wide.columns)
        & set(ret20_wide.columns)
    )
    tickers = sorted(common)
    if not tickers:
        return pd.DataFrame(columns=list(CROSS_SECTIONAL_FEATURE_COLUMNS))

    dates = close_wide.index
    close_wide = close_wide.reindex(dates)[tickers]
    ret5_wide  = ret5_wide.reindex(dates)[tickers]
    ret20_wide = ret20_wide.reindex(dates)[tickers]

    groups = _sector_groups(tickers, sector_map)

    # --- 1. sector_rank_ret_20d ---
    sector_rank_20 = pd.DataFrame(np.nan, index=dates, columns=tickers, dtype="float64")
    for _sector, members in groups.items():
        cols = [t for t in members if t in tickers]
        if len(cols) >= 2:
            sector_rank_20[cols] = ret20_wide[cols].rank(axis=1, pct=True)
        elif len(cols) == 1:
            sector_rank_20[cols[0]] = 0.5

    # --- 2. universe_rank_ret_5d ---
    universe_rank_5 = ret5_wide.rank(axis=1, pct=True)

    # --- 3. pct_from_52w_high ---
    high_252 = close_wide.rolling(window=252, min_periods=200).max()
    pct_from_high = (close_wide - high_252) / high_252

    # --- 4. corr_to_nifty_60d ---
    daily_rets = np.log(close_wide / close_wide.shift(1))

    corr_60    = pd.DataFrame(np.nan, index=dates, columns=tickers, dtype="float64")
    beta_resid = pd.DataFrame(np.nan, index=dates, columns=tickers, dtype="float64")

    if nifty_returns is not None and not nifty_returns.empty:
        nr = nifty_returns.copy()
        if nr.index.tz is not None:
            nr.index = nr.index.tz_localize(None)
        nr.index = nr.index.normalize()
        nr = nr.sort_index()
        nr = nr[~nr.index.duplicated(keep="last")]
        nr = nr.reindex(dates).astype("float64")

        for t in tickers:
            corr_60[t] = daily_rets[t].rolling(window=60, min_periods=60).corr(nr)

        nifty_mean_60  = nr.rolling(window=60, min_periods=60).mean()
        stock_mean_60  = daily_rets.rolling(window=60, min_periods=60).mean()
        nifty_centered = nr - nifty_mean_60
        stock_centered = daily_rets.sub(stock_mean_60, axis=0)
        cov_xy = (
            stock_centered
            .mul(nifty_centered, axis=0)
            .rolling(window=60, min_periods=60)
            .mean()
        )
        var_y = (nifty_centered ** 2).rolling(window=60, min_periods=60).mean()
        beta_60 = cov_xy.div(var_y.where(var_y > 0, np.nan), axis=0)

        nifty_5d = nr.rolling(window=5, min_periods=5).sum()
        beta_resid = ret5_wide - beta_60.mul(nifty_5d, axis=0)

    # --- 6. sector_dispersion_20d ---
    sector_disp = pd.DataFrame(np.nan, index=dates, columns=tickers, dtype="float64")
    for _sector, members in groups.items():
        cols = [t for t in members if t in tickers]
        if len(cols) >= 2:
            std_per_date = ret20_wide[cols].std(axis=1, ddof=1)
            for c in cols:
                sector_disp[c] = std_per_date

    # --- build long output ---
    # future_stack=True replaces the deprecated stack(dropna=False).
    # It preserves NaN values in the stacked output, which is what we
    # want (warm-up rows). The full (date, ticker) grid already exists
    # in each wide frame, so no phantom-row behavior applies.
    frames: dict[str, pd.DataFrame] = {
        "sector_rank_ret_20d":   sector_rank_20,
        "universe_rank_ret_5d":  universe_rank_5,
        "pct_from_52w_high":     pct_from_high,
        "corr_to_nifty_60d":     corr_60,
        "beta_residual_5d":      beta_resid,
        "sector_dispersion_20d": sector_disp,
    }

    parts = []
    for name, wide in frames.items():
        long = wide.stack(future_stack=True).rename(name)
        long.index.names = ["date", "ticker"]
        parts.append(long)

    out = pd.concat(parts, axis=1)
    out = out.swaplevel("ticker", "date").sort_index()
    out = out.loc[:, list(CROSS_SECTIONAL_FEATURE_COLUMNS)]
    out = out.replace([np.inf, -np.inf], np.nan)
    return out


__all__ = [
    "NEWS_FEATURE_COLUMNS",
    "MARKET_FEATURE_COLUMNS",
    "CROSS_SECTIONAL_FEATURE_COLUMNS",
    "compute_news_features",
    "compute_market_features",
    "compute_cross_sectional_features",
    "news_feature_columns",
    "market_feature_columns",
    "cross_sectional_feature_columns",
]