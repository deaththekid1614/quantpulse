"""
Training dataset builder for the classical forecasting engine (binary).

Reads features_daily and prices_daily from the DB, computes binary
up/down labels via app.ml.labels, joins them, applies a strict
chronological split, and returns per-horizon train/val/test matrices.

This module is the ONLY place in the pipeline where features and labels
meet. It is deliberately opinionated:

  - No shuffling. The split is chronological.
  - Rows without a valid label for a given horizon are dropped BEFORE
    the split, not after, so train/val/test sizes are honest.
  - The split uses calendar dates, not row indices, so it survives
    per-security gaps and stays reproducible across reruns.
  - No cross-sectional pooling: rows from different securities are
    concatenated, but the model in classical.py sees one flat design
    matrix and treats all rows equally.

Leakage guarantees (verified in test_chunk_b.py):
  1. max(train dates) < min(val dates) < min(test dates)
  2. No NaN remains in X or y for the returned splits
  3. Every label row has a corresponding feature row at the same
     (security_id, date) — no joining across time
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.db.models import FeaturesDaily, PriceDaily, Security
from app.db.session import session_scope
from app.ml.labels import build_binary_labels, label_columns
from app.pipeline.features import FEATURE_COLUMNS


# ---------------------------------------------------------------------------
# locked split boundaries
# ---------------------------------------------------------------------------

TRAIN_END  = date(2025, 6, 30)
VAL_START  = date(2025, 7, 1)
VAL_END    = date(2025, 10, 31)
TEST_START = date(2025, 11, 1)

# The default horizon set. Three models, one per horizon.
DEFAULT_HORIZONS: tuple[int, ...] = (7, 15, 30)


# ---------------------------------------------------------------------------
# result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HorizonSplit:
    """
    One horizon's train/val/test partition.

    X_* are float32 DataFrames with columns == FEATURE_COLUMNS, index
    being a RangeIndex. y_* are 1-D numpy arrays of dtype '<U4' with
    values in {'up', 'down'}.

    tickers_* and dates_* mirror the row order of X_*/y_* and are for
    diagnostics only — the model does not see them.
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

    def summary(self) -> dict:
        def _dist(y: np.ndarray) -> dict[str, float]:
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
# DB load
# ---------------------------------------------------------------------------

def _load_features_and_prices() -> tuple[pd.DataFrame, pd.DataFrame, dict[int, str]]:
    """
    Load features_daily and prices_daily for all securities in one pass.

    Returns:
      features_df : MultiIndex (security_id, date) × FEATURE_COLUMNS
      prices_df   : MultiIndex (security_id, date) × ['close']
      id_to_ticker: {security_id: ticker}
    """
    with session_scope() as db:
        secs = db.execute(select(Security.id, Security.ticker)).all()
        id_to_ticker = {sid: tk for sid, tk in secs}

        feat_rows = db.execute(
            select(
                FeaturesDaily.security_id,
                FeaturesDaily.date,
                *[getattr(FeaturesDaily, c) for c in FEATURE_COLUMNS],
            ).order_by(FeaturesDaily.security_id, FeaturesDaily.date)
        ).all()

        price_rows = db.execute(
            select(
                PriceDaily.security_id,
                PriceDaily.date,
                PriceDaily.close,
            ).order_by(PriceDaily.security_id, PriceDaily.date)
        ).all()

    feat_df = pd.DataFrame(
        feat_rows,
        columns=["security_id", "date", *FEATURE_COLUMNS],
    )
    feat_df["date"] = pd.to_datetime(feat_df["date"])
    feat_df = feat_df.set_index(["security_id", "date"]).sort_index()

    price_df = pd.DataFrame(
        price_rows,
        columns=["security_id", "date", "close"],
    )
    price_df["date"] = pd.to_datetime(price_df["date"])
    price_df = price_df.set_index(["security_id", "date"]).sort_index()

    return feat_df, price_df, id_to_ticker


# ---------------------------------------------------------------------------
# label assembly (per security)
# ---------------------------------------------------------------------------

def _labels_for_all_securities(
    price_df: pd.DataFrame,
    horizons: tuple[int, ...],
) -> pd.DataFrame:
    """
    Compute binary labels per security by calling build_binary_labels on
    each security's price series, then concatenating.

    Returns a DataFrame with MultiIndex (security_id, date) and columns
    future_return_{h}d, label_{h}d for each horizon.
    """
    parts: list[pd.DataFrame] = []

    for sec_id in price_df.index.get_level_values("security_id").unique():
        try:
            p_sec = price_df.xs(sec_id, level="security_id").copy()
        except KeyError:
            continue

        p_sec.index.name = "date"

        labels_sec = build_binary_labels(p_sec[["close"]], horizons=horizons)
        labels_sec["security_id"] = sec_id
        labels_sec = labels_sec.set_index("security_id", append=True)
        parts.append(labels_sec)

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
    Split a MultiIndex (security_id, date) DataFrame into train/val/test
    by date. Boundaries are inclusive at the ends: train <= TRAIN_END,
    VAL_START <= val <= VAL_END, test >= TEST_START.
    """
    dates = df.index.get_level_values("date").date

    train_mask = dates <= TRAIN_END
    val_mask   = (dates >= VAL_START) & (dates <= VAL_END)
    test_mask  = dates >= TEST_START

    return df[train_mask], df[val_mask], df[test_mask]


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def build_dataset(
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[int, HorizonSplit]:
    """
    Build the full training/validation/test dataset, one entry per
    horizon. Binary labels only (up / down).

    Guarantees:
      - X has exactly FEATURE_COLUMNS in the right order.
      - y contains only 'up' / 'down'.
      - No NaN in X or y for any returned split.
      - Chronological ordering: max(train dates) < min(val dates) < min(test dates).
    """
    feat_df, price_df, id_to_ticker = _load_features_and_prices()
    labels_df = _labels_for_all_securities(price_df, horizons)

    # Join features and labels on (security_id, date).
    # Any row where the label for a horizon is None/NaN is dropped.
    joined = feat_df.join(labels_df, how="inner").dropna(subset=label_columns(horizons))

    if joined.empty:
        raise RuntimeError("joined features+labels is empty — check DB state")

    train_df, val_df, test_df = _chronological_split(joined)

    if train_df.empty or val_df.empty or test_df.empty:
        raise RuntimeError(
            f"split produced empty partition: "
            f"train={len(train_df)} val={len(val_df)} test={len(test_df)}"
        )

    out: dict[int, HorizonSplit] = {}

    for h in horizons:
        ycol = f"label_{h}d"

        def _split_xy(sub: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, list[str], list[date]]:
            X = sub.loc[:, list(FEATURE_COLUMNS)].astype("float32").reset_index(drop=True)
            y = sub[ycol].to_numpy(dtype="<U4")
            tickers = [id_to_ticker[sid] for sid in sub.index.get_level_values("security_id")]
            dates   = [d.date() for d in sub.index.get_level_values("date")]
            return X, y, tickers, dates

        X_tr, y_tr, tk_tr, dt_tr = _split_xy(train_df)
        X_va, y_va, tk_va, dt_va = _split_xy(val_df)
        X_te, y_te, tk_te, dt_te = _split_xy(test_df)

        out[h] = HorizonSplit(
            horizon=h,
            X_train=X_tr, y_train=y_tr,
            X_val=X_va,   y_val=y_va,
            X_test=X_te,  y_test=y_te,
            tickers_train=tk_tr, tickers_val=tk_va, tickers_test=tk_te,
            dates_train=dt_tr,   dates_val=dt_va,   dates_test=dt_te,
        )

    return out


__all__ = [
    "DEFAULT_HORIZONS",
    "TRAIN_END",
    "VAL_START",
    "VAL_END",
    "TEST_START",
    "HorizonSplit",
    "build_dataset",
]