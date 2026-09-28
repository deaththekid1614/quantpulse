"""
Volatility-forecast dataset builder — Stage 8B-v2.

Loads features_daily (24 base) + rich_features_daily (21 rich), joins
them on (security_id, date), computes future realized volatility for
each horizon, and applies the SAME chronological split as Stage 8A.

The threshold for the binary label (high_vol vs low_vol) is computed
as the median of `future_vol_{h}d` on the TRAIN split only, then
applied unchanged to validation and test. This is a strict leakage
guard: validation and test never influence the threshold.

Feature columns
---------------
Same 45 columns as app.ml.rich_dataset:
  24 base + 7 news + 8 market + 6 cross-sectional.

Labels
------
`y_train`, `y_val`, `y_test` are string arrays with values in
{"low_vol", "high_vol"}. Rows where future volatility is NaN (last h
trading days of each security's series) are dropped.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.db.models import (
    FeaturesDaily,
    PriceDaily,
    RichFeaturesDaily,
    Security,
)
from app.db.session import session_scope
from app.ml.labels_vol import (
    build_future_vol,
    classify_vol_binary,
    label_columns_vol,
    raw_columns_vol,
)
from app.ml.dataset import (
    DEFAULT_HORIZONS,
    TEST_START,
    TRAIN_END,
    VAL_END,
    VAL_START,
)
from app.pipeline.features import FEATURE_COLUMNS
from app.pipeline.rich_features import (
    CROSS_SECTIONAL_FEATURE_COLUMNS,
    MARKET_FEATURE_COLUMNS,
    NEWS_FEATURE_COLUMNS,
)


RICH_FEATURE_COLUMNS: tuple[str, ...] = (
    tuple(FEATURE_COLUMNS)
    + tuple(NEWS_FEATURE_COLUMNS)
    + tuple(MARKET_FEATURE_COLUMNS)
    + tuple(CROSS_SECTIONAL_FEATURE_COLUMNS)
)

VOL_CLASS_ORDER: tuple[str, ...] = ("low_vol", "high_vol")

# Must match LABEL_DTYPE in app.ml.classical and be wide enough for
# 'high_vol' (8 chars).
LABEL_DTYPE = "<U8"


# ---------------------------------------------------------------------------
# container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VolHorizonSplit:
    """
    One horizon's train/val/test partition for volatility.

    Same shape as dataset.HorizonSplit, plus the train-median threshold
    used to binarize the labels at this horizon.
    """
    horizon:     int
    X_train:     pd.DataFrame
    y_train:     np.ndarray
    X_val:       pd.DataFrame
    y_val:       np.ndarray
    X_test:      pd.DataFrame
    y_test:      np.ndarray
    tickers_train: list[str]
    tickers_val:   list[str]
    tickers_test:  list[str]
    dates_train:   list[date]
    dates_val:     list[date]
    dates_test:    list[date]
    threshold:     float

    def summary(self) -> dict:
        def _dist(y: np.ndarray) -> dict:
            if len(y) == 0:
                return {}
            u, c = np.unique(y, return_counts=True)
            return {str(k): round(100.0 * v / len(y), 1) for k, v in zip(u, c)}

        return {
            "horizon":        self.horizon,
            "n_train":        len(self.y_train),
            "n_val":          len(self.y_val),
            "n_test":         len(self.y_test),
            "n_features":     self.X_train.shape[1],
            "threshold":      round(self.threshold, 6),
            "train_date_min": min(self.dates_train).isoformat() if self.dates_train else None,
            "train_date_max": max(self.dates_train).isoformat() if self.dates_train else None,
            "val_date_min":   min(self.dates_val).isoformat()   if self.dates_val   else None,
            "val_date_max":   max(self.dates_val).isoformat()   if self.dates_val   else None,
            "test_date_min":  min(self.dates_test).isoformat()  if self.dates_test  else None,
            "test_date_max":  max(self.dates_test).isoformat()  if self.dates_test  else None,
            "train_dist":     _dist(self.y_train),
            "val_dist":       _dist(self.y_val),
            "test_dist":      _dist(self.y_test),
        }


# ---------------------------------------------------------------------------
# DB loaders
# ---------------------------------------------------------------------------

def _load_base_and_rich() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[int, str]]:
    """Return (base_df, rich_df, price_df, id_to_ticker), each MultiIndexed."""
    rich_cols = (
        NEWS_FEATURE_COLUMNS
        + MARKET_FEATURE_COLUMNS
        + CROSS_SECTIONAL_FEATURE_COLUMNS
    )

    with session_scope() as db:
        secs = db.execute(select(Security.id, Security.ticker)).all()
        id_to_ticker = {sid: tk for sid, tk in secs}

        base_rows = db.execute(
            select(
                FeaturesDaily.security_id,
                FeaturesDaily.date,
                *[getattr(FeaturesDaily, c) for c in FEATURE_COLUMNS],
            ).order_by(FeaturesDaily.security_id, FeaturesDaily.date)
        ).all()

        rich_rows = db.execute(
            select(
                RichFeaturesDaily.security_id,
                RichFeaturesDaily.date,
                *[getattr(RichFeaturesDaily, c) for c in rich_cols],
            ).order_by(RichFeaturesDaily.security_id, RichFeaturesDaily.date)
        ).all()

        price_rows = db.execute(
            select(
                PriceDaily.security_id,
                PriceDaily.date,
                PriceDaily.close,
            ).order_by(PriceDaily.security_id, PriceDaily.date)
        ).all()

    base_df = pd.DataFrame(base_rows, columns=["security_id", "date", *FEATURE_COLUMNS])
    base_df["date"] = pd.to_datetime(base_df["date"])
    base_df = base_df.set_index(["security_id", "date"]).sort_index()

    rich_df = pd.DataFrame(rich_rows, columns=["security_id", "date", *rich_cols])
    rich_df["date"] = pd.to_datetime(rich_df["date"])
    rich_df = rich_df.set_index(["security_id", "date"]).sort_index()

    price_df = pd.DataFrame(price_rows, columns=["security_id", "date", "close"])
    price_df["date"] = pd.to_datetime(price_df["date"])
    price_df = price_df.set_index(["security_id", "date"]).sort_index()

    return base_df, rich_df, price_df, id_to_ticker


# ---------------------------------------------------------------------------
# future-vol assembly (per security)
# ---------------------------------------------------------------------------

def _future_vol_for_all_securities(
    price_df: pd.DataFrame,
    horizons: tuple[int, ...],
) -> pd.DataFrame:
    """
    Returns a DataFrame with MultiIndex (security_id, date) and columns
    future_vol_{h}d for each horizon. Last h rows per security are NaN.
    """
    parts: list[pd.DataFrame] = []
    for sec_id in price_df.index.get_level_values("security_id").unique():
        try:
            p_sec = price_df.xs(sec_id, level="security_id").copy()
        except KeyError:
            continue
        p_sec.index.name = "date"

        fv = build_future_vol(p_sec[["close"]], horizons=horizons)
        fv["security_id"] = sec_id
        fv = fv.set_index("security_id", append=True)
        parts.append(fv)

    if not parts:
        raise RuntimeError("no securities in prices_daily")

    out = pd.concat(parts).sort_index()
    out.index.names = ["date", "security_id"]
    return out.swaplevel("security_id", "date").sort_index()


# ---------------------------------------------------------------------------
# split
# ---------------------------------------------------------------------------

def _chronological_split(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Return three independent COPIES. Copying matters: we write new label
    columns into each split, and writing into a view of a parent frame
    triggers SettingWithCopyWarning and may not persist.
    """
    dates = df.index.get_level_values("date").date
    train_mask = dates <= TRAIN_END
    val_mask   = (dates >= VAL_START) & (dates <= VAL_END)
    test_mask  = dates >= TEST_START
    return (
        df[train_mask].copy(),
        df[val_mask].copy(),
        df[test_mask].copy(),
    )


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def build_vol_dataset(
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[int, VolHorizonSplit]:
    """
    Build the volatility dataset, one entry per horizon.

    Thresholds are computed as the median of future_vol_{h}d on the
    TRAIN split only. Same threshold applied to val/test.
    """
    base_df, rich_df, price_df, id_to_ticker = _load_base_and_rich()

    joined = base_df.join(rich_df, how="left")

    fv_df = _future_vol_for_all_securities(price_df, horizons)
    joined = joined.join(fv_df, how="left")

    raw_cols = raw_columns_vol(horizons)
    joined = joined.dropna(subset=raw_cols)

    if joined.empty:
        raise RuntimeError("joined vol dataset is empty — check DB state")

    train_df, val_df, test_df = _chronological_split(joined)
    if train_df.empty or val_df.empty or test_df.empty:
        raise RuntimeError(
            f"split produced empty partition: "
            f"train={len(train_df)} val={len(val_df)} test={len(test_df)}"
        )

    out: dict[int, VolHorizonSplit] = {}

    for h in horizons:
        raw_col = f"future_vol_{h}d"
        label_col = f"label_vol_{h}d"

        threshold = float(train_df[raw_col].median())
        if not np.isfinite(threshold):
            raise RuntimeError(f"h={h}: train median of {raw_col} is not finite")

        train_df[label_col] = classify_vol_binary(train_df[raw_col], threshold)
        val_df[label_col]   = classify_vol_binary(val_df[raw_col],   threshold)
        test_df[label_col]  = classify_vol_binary(test_df[raw_col],  threshold)

        def _split_xy(sub: pd.DataFrame):
            X = sub.loc[:, list(RICH_FEATURE_COLUMNS)].astype("float32").reset_index(drop=True)
            y = sub[label_col].to_numpy(dtype=LABEL_DTYPE)
            tickers = [id_to_ticker[sid] for sid in sub.index.get_level_values("security_id")]
            dates   = [d.date() for d in sub.index.get_level_values("date")]
            return X, y, tickers, dates

        X_tr, y_tr, tk_tr, dt_tr = _split_xy(train_df)
        X_va, y_va, tk_va, dt_va = _split_xy(val_df)
        X_te, y_te, tk_te, dt_te = _split_xy(test_df)

        out[h] = VolHorizonSplit(
            horizon=h,
            X_train=X_tr, y_train=y_tr,
            X_val=X_va,   y_val=y_va,
            X_test=X_te,  y_test=y_te,
            tickers_train=tk_tr, tickers_val=tk_va, tickers_test=tk_te,
            dates_train=dt_tr,   dates_val=dt_va,   dates_test=dt_te,
            threshold=threshold,
        )

    return out


__all__ = [
    "RICH_FEATURE_COLUMNS",
    "VOL_CLASS_ORDER",
    "LABEL_DTYPE",
    "VolHorizonSplit",
    "build_vol_dataset",
]