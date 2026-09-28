"""
Rich-feature dataset builder — Stage 8B.

Loads features_daily (24 base features) and rich_features_daily (21
additional features), joins them on (security_id, date), computes
binary labels from prices_daily, applies the SAME chronological split
as Stage 8A, and returns per-horizon train/val/test matrices with all
45 features.

This module does not modify app.ml.dataset. It imports the split
constants and the HorizonSplit container from it.

Feature columns
---------------
The 45 columns are, in order:

  24 base features   (from features_daily)         — FEATURE_COLUMNS
   7 news features   (from rich_features_daily)    — NEWS_FEATURE_COLUMNS
   8 market features (from rich_features_daily)    — MARKET_FEATURE_COLUMNS
   6 cross-sectional (from rich_features_daily)    — CROSS_SECTIONAL_FEATURE_COLUMNS

Missing values
--------------
Rows that exist in features_daily but not rich_features_daily are
preserved; the rich columns are NaN for those rows. No imputation is
performed. HistGradientBoosting handles NaN natively.

Leakage guarantees
------------------
Identical to Stage 8A: max(train dates) < min(val dates) < min(test
dates); no NaN in X or y for base features; label columns are strictly
{up, down}.
"""
from __future__ import annotations

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
from app.ml.dataset import (
    DEFAULT_HORIZONS,
    HorizonSplit,
    TEST_START,
    TRAIN_END,
    VAL_END,
    VAL_START,
)
from app.ml.labels import build_binary_labels, label_columns
from app.pipeline.features import FEATURE_COLUMNS
from app.pipeline.rich_features import (
    CROSS_SECTIONAL_FEATURE_COLUMNS,
    MARKET_FEATURE_COLUMNS,
    NEWS_FEATURE_COLUMNS,
)


# ---------------------------------------------------------------------------
# feature column list
# ---------------------------------------------------------------------------

RICH_FEATURE_COLUMNS: tuple[str, ...] = (
    tuple(FEATURE_COLUMNS)
    + tuple(NEWS_FEATURE_COLUMNS)
    + tuple(MARKET_FEATURE_COLUMNS)
    + tuple(CROSS_SECTIONAL_FEATURE_COLUMNS)
)

N_BASE = len(FEATURE_COLUMNS)
N_RICH = len(RICH_FEATURE_COLUMNS) - N_BASE


# ---------------------------------------------------------------------------
# DB loaders
# ---------------------------------------------------------------------------

def _load_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[int, str]]:
    """
    Return (base_features_df, rich_features_df, prices_df, id_to_ticker).

    Each DataFrame is indexed by MultiIndex (security_id, date).
    """
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

    base_df = pd.DataFrame(
        base_rows,
        columns=["security_id", "date", *FEATURE_COLUMNS],
    )
    base_df["date"] = pd.to_datetime(base_df["date"])
    base_df = base_df.set_index(["security_id", "date"]).sort_index()

    rich_df = pd.DataFrame(
        rich_rows,
        columns=["security_id", "date", *rich_cols],
    )
    rich_df["date"] = pd.to_datetime(rich_df["date"])
    rich_df = rich_df.set_index(["security_id", "date"]).sort_index()

    price_df = pd.DataFrame(
        price_rows,
        columns=["security_id", "date", "close"],
    )
    price_df["date"] = pd.to_datetime(price_df["date"])
    price_df = price_df.set_index(["security_id", "date"]).sort_index()

    return base_df, rich_df, price_df, id_to_ticker


# ---------------------------------------------------------------------------
# label helper (inline; dataset.py has a private version we do not import)
# ---------------------------------------------------------------------------

def _labels_for_all_securities(
    price_df: pd.DataFrame,
    horizons: tuple[int, ...],
) -> pd.DataFrame:
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
# split (inline; dataset.py has a private version we do not import)
# ---------------------------------------------------------------------------

def _chronological_split(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = df.index.get_level_values("date").date
    train_mask = dates <= TRAIN_END
    val_mask   = (dates >= VAL_START) & (dates <= VAL_END)
    test_mask  = dates >= TEST_START
    return df[train_mask], df[val_mask], df[test_mask]


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def build_rich_dataset(
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[int, HorizonSplit]:
    """
    Build the full training/validation/test dataset with all 45
    features (24 base + 21 rich), one entry per horizon.
    """
    base_df, rich_df, price_df, id_to_ticker = _load_all()

    # LEFT join: keep every base row; rich columns NaN where missing.
    joined = base_df.join(rich_df, how="left")

    # Labels
    labels_df = _labels_for_all_securities(price_df, horizons)

    # Inner join with labels, drop rows where any horizon's label is NaN
    joined = joined.join(labels_df, how="inner").dropna(subset=label_columns(horizons))

    if joined.empty:
        raise RuntimeError("joined rich dataset is empty — check DB state")

    train_df, val_df, test_df = _chronological_split(joined)

    if train_df.empty or val_df.empty or test_df.empty:
        raise RuntimeError(
            f"split produced empty partition: "
            f"train={len(train_df)} val={len(val_df)} test={len(test_df)}"
        )

    out: dict[int, HorizonSplit] = {}

    for h in horizons:
        ycol = f"label_{h}d"

        def _split_xy(sub: pd.DataFrame):
            X = sub.loc[:, list(RICH_FEATURE_COLUMNS)].astype("float32").reset_index(drop=True)
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
    "RICH_FEATURE_COLUMNS",
    "N_BASE",
    "N_RICH",
    "build_rich_dataset",
]