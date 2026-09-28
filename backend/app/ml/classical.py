"""
Binary forecasting model wrapper.

One model per horizon. Each model is a histogram gradient boosting
classifier wrapped in isotonic probability calibration.

Class order
-----------
`CLASS_ORDER` is the default for direction forecasting: ("down", "up").
`fit_forecaster` accepts an optional `class_order` parameter so the same
wrapper can be reused for other binary tasks — e.g. volatility, where
the classes are ("low_vol", "high_vol").

Implementation detail
---------------------
sklearn's classifiers sort their classes alphabetically. That happens
to match our direction order ('down' < 'up') but NOT our volatility
order ('high_vol' < 'low_vol'). To guarantee that `predict_proba`
returns columns in OUR class order, `fit_forecaster` relabels y values
to integers using our class_order as the mapping BEFORE fitting. The
model then sees classes [0, 1] and returns columns in our intended
order. `FittedForecaster.class_order` stores the string labels for
callers to interpret predictions.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    precision_recall_fscore_support,
    roc_auc_score,
)

from app.pipeline.features import FEATURE_COLUMNS

log = logging.getLogger(__name__)

CLASS_ORDER: tuple[str, ...] = ("down", "up")
N_CLASSES = len(CLASS_ORDER)

# Fixed-width unicode dtype wide enough for the longest label used by
# any task. 'high_vol' is 8 chars.
LABEL_DTYPE = "<U8"

DEFAULT_HGB_PARAMS: dict[str, Any] = {
    "max_iter":           400,
    "learning_rate":      0.05,
    "max_depth":          5,
    "min_samples_leaf":   40,
    "l2_regularization":  1.0,
    "early_stopping":     True,
    "validation_fraction": 0.1,
    "n_iter_no_change":   20,
    "random_state":       42,
}


# ---------------------------------------------------------------------------
# container
# ---------------------------------------------------------------------------

@dataclass
class FittedForecaster:
    """A calibrated binary classifier for one horizon."""
    horizon:          int
    feature_columns:  list[str]
    class_order:      list[str]
    model:            CalibratedClassifierCV
    trained_at:       str
    sklearn_version:  str
    train_rows:       int
    val_rows:         int
    hgb_params:       dict[str, Any] = field(default_factory=dict)
    val_metrics:      dict[str, Any] = field(default_factory=dict)
    fit_seconds:      float = 0.0


# ---------------------------------------------------------------------------
# fit
# ---------------------------------------------------------------------------

def fit_forecaster(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_val: pd.DataFrame,
    y_val: np.ndarray,
    horizon: int,
    *,
    hgb_params: dict[str, Any] | None = None,
    feature_columns: list[str] | None = None,
    class_order: tuple[str, ...] | None = None,
) -> FittedForecaster:
    """
    Fit one calibrated binary forecaster for `horizon`.

    Parameters
    ----------
    feature_columns : list[str] | None
        Expected feature names. None → FEATURE_COLUMNS.
    class_order : tuple[str, ...] | None
        Expected label values in the exact order they should appear in
        the probability output. None → CLASS_ORDER.
    """
    import sklearn

    expected_columns: list[str] = (
        list(feature_columns) if feature_columns is not None
        else list(FEATURE_COLUMNS)
    )
    expected_class_order: tuple[str, ...] = (
        tuple(class_order) if class_order is not None
        else CLASS_ORDER
    )

    if len(expected_class_order) != N_CLASSES:
        raise ValueError(
            f"class_order must have exactly {N_CLASSES} elements, "
            f"got {len(expected_class_order)}: {expected_class_order}"
        )

    if list(X_train.columns) != expected_columns:
        raise ValueError(
            f"X_train columns mismatch: got {list(X_train.columns)}, "
            f"expected {expected_columns}"
        )
    if list(X_val.columns) != expected_columns:
        raise ValueError(
            f"X_val columns mismatch: got {list(X_val.columns)}, "
            f"expected {expected_columns}"
        )
    if len(X_train) != len(y_train):
        raise ValueError(f"X_train/y_train length mismatch: {len(X_train)} vs {len(y_train)}")
    if len(X_val) != len(y_val):
        raise ValueError(f"X_val/y_val length mismatch: {len(X_val)} vs {len(y_val)}")

    y_train_str = np.asarray(y_train, dtype=LABEL_DTYPE)
    y_val_str   = np.asarray(y_val,   dtype=LABEL_DTYPE)

    unknown_train = set(y_train_str) - set(expected_class_order)
    unknown_val   = set(y_val_str)   - set(expected_class_order)
    if unknown_train:
        raise ValueError(f"y_train has unknown labels: {unknown_train} (expected {expected_class_order})")
    if unknown_val:
        raise ValueError(f"y_val has unknown labels: {unknown_val} (expected {expected_class_order})")

    # --- relabel to integers using OUR order ---
    # This is the critical fix: sklearn will then see classes [0, 1] and
    # `predict_proba` returns column i = probability of class_order[i].
    label_to_int = {c: i for i, c in enumerate(expected_class_order)}
    y_train_int = np.array([label_to_int[c] for c in y_train_str], dtype=np.int64)
    y_val_int   = np.array([label_to_int[c] for c in y_val_str],   dtype=np.int64)

    params = dict(DEFAULT_HGB_PARAMS)
    if hgb_params:
        params.update(hgb_params)

    counts = {c: int((y_train_str == c).sum()) for c in expected_class_order}
    log.info("fitting h=%dd | %d train rows, %d features | class counts: %s",
             horizon, len(X_train), X_train.shape[1], counts)

    t0 = time.perf_counter()

    base = HistGradientBoostingClassifier(**params)
    calibrated = CalibratedClassifierCV(
        estimator=base,
        method="isotonic",
        cv=3,
    )
    calibrated.fit(X_train.to_numpy(dtype="float32"), y_train_int)

    fitted_classes = list(calibrated.classes_)
    expected_int_classes = list(range(N_CLASSES))
    if fitted_classes != expected_int_classes:
        raise RuntimeError(
            f"model classes {fitted_classes} != expected {expected_int_classes}"
        )

    fit_seconds = time.perf_counter() - t0

    fc = FittedForecaster(
        horizon=horizon,
        feature_columns=expected_columns,
        class_order=list(expected_class_order),
        model=calibrated,
        trained_at=datetime.now(timezone.utc).isoformat(),
        sklearn_version=sklearn.__version__,
        train_rows=len(X_train),
        val_rows=len(X_val),
        hgb_params=params,
        fit_seconds=fit_seconds,
    )

    # Pass strings to evaluate — it does its own interpretation using
    # forecaster.class_order.
    fc.val_metrics = evaluate(fc, X_val, y_val_str)

    log.info(
        "  h=%dd fitted in %.1fs | val acc=%.4f  brier=%.4f  auc=%.4f",
        horizon, fit_seconds,
        fc.val_metrics["accuracy"],
        fc.val_metrics["brier"],
        fc.val_metrics["roc_auc"],
    )

    return fc


# ---------------------------------------------------------------------------
# predict
# ---------------------------------------------------------------------------

def predict_proba(forecaster: FittedForecaster, X: pd.DataFrame) -> np.ndarray:
    """
    Return an (n, 2) array of probabilities. Column i is the probability
    of forecaster.class_order[i]. Rows sum to 1.
    """
    if list(X.columns) != forecaster.feature_columns:
        raise ValueError(
            f"X columns mismatch: got {list(X.columns)}, "
            f"expected {forecaster.feature_columns}"
        )
    raw = forecaster.model.predict_proba(X.to_numpy(dtype="float32"))
    assert raw.shape[1] == N_CLASSES
    return raw


def predict_proba_positive(forecaster: FittedForecaster, X: pd.DataFrame) -> np.ndarray:
    """
    Probability of the second class in forecaster.class_order:
    'up' for direction, 'high_vol' for volatility.
    """
    return predict_proba(forecaster, X)[:, 1]


# Backwards-compatible alias (Stage 8A/8B used `predict_proba_up`).
predict_proba_up = predict_proba_positive


def predict_direction(
    forecaster: FittedForecaster,
    X: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    probs = predict_proba(forecaster, X)
    idx = probs.argmax(axis=1)
    dirs = np.array([forecaster.class_order[i] for i in idx], dtype=LABEL_DTYPE)
    conf = probs.max(axis=1)
    return dirs, conf


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------

def _calibration_bins(
    p_pos: np.ndarray,
    y_pos: np.ndarray,
    n_bins: int = 10,
) -> list[dict]:
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    out: list[dict] = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        if i == n_bins - 1:
            mask = (p_pos >= lo) & (p_pos <= hi)
        else:
            mask = (p_pos >= lo) & (p_pos < hi)
        n = int(mask.sum())
        if n == 0:
            out.append({
                "bin_low": round(lo, 2),
                "bin_high": round(hi, 2),
                "n": 0,
                "mean_predicted": None,
                "actual_positive_rate": None,
            })
        else:
            out.append({
                "bin_low": round(lo, 2),
                "bin_high": round(hi, 2),
                "n": n,
                "mean_predicted": round(float(p_pos[mask].mean()), 4),
                "actual_positive_rate": round(float(y_pos[mask].mean()), 4),
            })
    return out


def evaluate(
    forecaster: FittedForecaster,
    X: pd.DataFrame,
    y_true: np.ndarray,
) -> dict[str, Any]:
    """
    The positive class is the second element of forecaster.class_order:
    'up' for direction, 'high_vol' for volatility.
    """
    y_true = np.asarray(y_true, dtype=LABEL_DTYPE)
    probs = predict_proba(forecaster, X)

    labels = list(forecaster.class_order)
    pos_class = labels[1]
    neg_class = labels[0]

    p_pos = probs[:, 1]
    y_pos = (y_true == pos_class).astype(int)

    y_pred_idx = probs.argmax(axis=1)
    y_pred = np.array([labels[i] for i in y_pred_idx], dtype=LABEL_DTYPE)

    acc = float(accuracy_score(y_true, y_pred))
    brier = float(brier_score_loss(y_pos, p_pos))
    try:
        auc = float(roc_auc_score(y_pos, p_pos))
    except ValueError:
        auc = float("nan")
    ll = float(log_loss(y_pos, np.column_stack([1.0 - p_pos, p_pos]), labels=[0, 1]))

    prec, rec, f1, supp = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0,
    )

    per_class = {}
    for i, cls in enumerate(labels):
        per_class[cls] = {
            "precision": float(prec[i]),
            "recall":    float(rec[i]),
            "f1":        float(f1[i]),
            "support":   int(supp[i]),
        }

    label_to_idx = {c: i for i, c in enumerate(labels)}
    cm = np.zeros((N_CLASSES, N_CLASSES), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[label_to_idx[t], label_to_idx[p]] += 1

    bins = _calibration_bins(p_pos, y_pos, n_bins=10)

    pred_freq = {c: float((y_pred == c).mean()) for c in labels}
    true_freq = {c: float((y_true == c).mean()) for c in labels}

    return {
        "n":                 int(len(y_true)),
        "positive_class":    pos_class,
        "negative_class":    neg_class,
        "accuracy":          acc,
        "brier":             brier,
        "roc_auc":           auc,
        "log_loss":          ll,
        "per_class":         per_class,
        "confusion_matrix":  cm.tolist(),
        "class_order":       list(labels),
        "calibration_bins":  bins,
        "pred_freq":         pred_freq,
        "true_freq":         true_freq,
    }


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------

def save_forecaster(forecaster: FittedForecaster, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"forecaster_{forecaster.horizon}d.joblib"

    payload = {
        "horizon":         forecaster.horizon,
        "feature_columns": forecaster.feature_columns,
        "class_order":     forecaster.class_order,
        "trained_at":      forecaster.trained_at,
        "sklearn_version": forecaster.sklearn_version,
        "train_rows":      forecaster.train_rows,
        "val_rows":        forecaster.val_rows,
        "hgb_params":      forecaster.hgb_params,
        "val_metrics":     forecaster.val_metrics,
        "fit_seconds":     forecaster.fit_seconds,
        "model":           forecaster.model,
    }
    joblib.dump(payload, path)
    log.info("saved %s (%.1f KB)", path.name, path.stat().st_size / 1024)
    return path


def load_forecaster(path: Path) -> FittedForecaster:
    payload = joblib.load(path)
    return FittedForecaster(
        horizon=payload["horizon"],
        feature_columns=payload["feature_columns"],
        class_order=payload["class_order"],
        model=payload["model"],
        trained_at=payload["trained_at"],
        sklearn_version=payload["sklearn_version"],
        train_rows=payload["train_rows"],
        val_rows=payload["val_rows"],
        hgb_params=payload["hgb_params"],
        val_metrics=payload["val_metrics"],
        fit_seconds=payload["fit_seconds"],
    )


def write_run_metadata(out_dir: Path, forecasters: dict[int, FittedForecaster]) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "metadata.json"

    if forecasters:
        sample = next(iter(forecasters.values()))
        feature_count = len(sample.feature_columns)
        class_order   = list(sample.class_order)
    else:
        feature_count = 0
        class_order   = []

    meta = {
        "trained_at":    datetime.now(timezone.utc).isoformat(),
        "horizons":      sorted(forecasters.keys()),
        "class_order":   class_order,
        "feature_count": feature_count,
        "models": {
            str(h): {
                "trained_at":      fc.trained_at,
                "train_rows":      fc.train_rows,
                "val_rows":        fc.val_rows,
                "fit_seconds":     round(fc.fit_seconds, 2),
                "sklearn_version": fc.sklearn_version,
                "val_accuracy":    round(fc.val_metrics["accuracy"], 4),
                "val_brier":       round(fc.val_metrics["brier"], 4),
                "val_roc_auc":     round(fc.val_metrics["roc_auc"], 4),
                "val_log_loss":    round(fc.val_metrics["log_loss"], 4),
            }
            for h, fc in forecasters.items()
        },
    }
    path.write_text(json.dumps(meta, indent=2))
    log.info("wrote %s", path.name)
    return path


__all__ = [
    "CLASS_ORDER",
    "N_CLASSES",
    "LABEL_DTYPE",
    "FittedForecaster",
    "fit_forecaster",
    "predict_proba",
    "predict_proba_positive",
    "predict_proba_up",
    "predict_direction",
    "evaluate",
    "save_forecaster",
    "load_forecaster",
    "write_run_metadata",
]