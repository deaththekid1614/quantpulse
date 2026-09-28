"""
Binary forecasting model wrapper.

One model per horizon. Each model is a histogram gradient boosting
classifier wrapped in isotonic probability calibration. This module
exposes a small, opinionated API:

    fit_forecaster(X_train, y_train, X_val, y_val, horizon)  -> FittedForecaster
    predict_proba(forecaster, X)                             -> np.ndarray (n, 2)
    predict_direction(forecaster, X)                         -> (dirs, confs)
    evaluate(forecaster, X, y)                               -> dict of metrics
    save_forecaster(forecaster, dir)                         -> Path
    load_forecaster(path)                                    -> FittedForecaster

Design decisions (locked, Stage 8A — binary):

  - Class order is always ["down", "up"] — alphabetical.
    We never trust sklearn's implicit ordering.

  - Calibration is isotonic, fitted via 3-fold CV on the training set.
    This is what lets us report "60% up" as a calibrated probability
    rather than an uncalibrated score.

  - No class balancing. Binary up/down is naturally near-balanced
    (~44/56 at worst in our training data). Balancing adds noise
    without benefit and was empirically worse in the 3-class variant.

  - Two calibration metrics we care about:
      * Brier score  — mean squared error of the up-probability.
                       Lower is better. Baseline (always predict 0.5): 0.25.
      * Calibration bins — for a well-calibrated model, the actual
                       up-rate in each probability bin equals the bin's
                       mean predicted probability.

  - Metrics are computed on whatever data you pass to `evaluate`.
    During development we use validation; the test set is only touched
    once, in the final backtest (Chunk H).

  - Artifacts are joblib files: model + metadata in a single dict.
    Loading a saved forecaster validates the feature list and class
    order so a mismatch can't silently corrupt predictions.
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

# Locked class order for every horizon. Alphabetical: 'down' < 'up'.
CLASS_ORDER: tuple[str, ...] = ("down", "up")
N_CLASSES = len(CLASS_ORDER)

# Default model hyperparameters. Deliberately modest — HGB with too
# many leaves will overfit on 4 years × 50 securities.
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
) -> FittedForecaster:
    """
    Fit one calibrated binary forecaster for `horizon`.

    X_train / X_val must have columns exactly matching FEATURE_COLUMNS.
    y_train / y_val must be string arrays with values in {'up', 'down'}.
    """
    import sklearn

    # --- validate inputs ---
    if list(X_train.columns) != list(FEATURE_COLUMNS):
        raise ValueError(
            f"X_train columns mismatch: got {list(X_train.columns)}, "
            f"expected {list(FEATURE_COLUMNS)}"
        )
    if list(X_val.columns) != list(FEATURE_COLUMNS):
        raise ValueError("X_val columns mismatch")
    if len(X_train) != len(y_train):
        raise ValueError(f"X_train/y_train length mismatch: {len(X_train)} vs {len(y_train)}")
    if len(X_val) != len(y_val):
        raise ValueError(f"X_val/y_val length mismatch: {len(X_val)} vs {len(y_val)}")

    y_train = np.asarray(y_train, dtype="<U4")
    y_val   = np.asarray(y_val,   dtype="<U4")

    unknown_train = set(y_train) - set(CLASS_ORDER)
    unknown_val   = set(y_val)   - set(CLASS_ORDER)
    if unknown_train:
        raise ValueError(f"y_train has unknown labels: {unknown_train}")
    if unknown_val:
        raise ValueError(f"y_val has unknown labels: {unknown_val}")

    params = dict(DEFAULT_HGB_PARAMS)
    if hgb_params:
        params.update(hgb_params)

    # Log class distribution for the record
    counts = {c: int((y_train == c).sum()) for c in CLASS_ORDER}
    log.info("fitting h=%dd | %d train rows, %d features | train class counts: %s",
             horizon, len(X_train), X_train.shape[1], counts)

    t0 = time.perf_counter()

    base = HistGradientBoostingClassifier(**params)
    calibrated = CalibratedClassifierCV(
        estimator=base,
        method="isotonic",
        cv=3,
    )
    calibrated.fit(X_train.to_numpy(dtype="float32"), y_train)

    fitted_classes = list(calibrated.classes_)
    if fitted_classes != list(CLASS_ORDER):
        raise RuntimeError(
            f"model class order {fitted_classes} != locked CLASS_ORDER {list(CLASS_ORDER)}"
        )

    fit_seconds = time.perf_counter() - t0

    fc = FittedForecaster(
        horizon=horizon,
        feature_columns=list(FEATURE_COLUMNS),
        class_order=list(CLASS_ORDER),
        model=calibrated,
        trained_at=datetime.now(timezone.utc).isoformat(),
        sklearn_version=sklearn.__version__,
        train_rows=len(X_train),
        val_rows=len(X_val),
        hgb_params=params,
        fit_seconds=fit_seconds,
    )

    fc.val_metrics = evaluate(fc, X_val, y_val)

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
    Return an (n, 2) array of probabilities in CLASS_ORDER
    (down, up). Rows sum to 1.
    """
    if list(X.columns) != forecaster.feature_columns:
        raise ValueError(
            f"X columns mismatch: got {list(X.columns)}, "
            f"expected {forecaster.feature_columns}"
        )
    raw = forecaster.model.predict_proba(X.to_numpy(dtype="float32"))
    assert raw.shape[1] == N_CLASSES
    return raw


def predict_proba_up(forecaster: FittedForecaster, X: pd.DataFrame) -> np.ndarray:
    """Convenience: return the up-probability column only (n,)."""
    return predict_proba(forecaster, X)[:, forecaster.class_order.index("up")]


def predict_direction(
    forecaster: FittedForecaster,
    X: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Return (directions, confidences).
    Direction is 'up' if p_up > 0.5, else 'down'.
    Confidence is max(p_down, p_up).
    """
    probs = predict_proba(forecaster, X)
    idx = probs.argmax(axis=1)
    dirs = np.array([forecaster.class_order[i] for i in idx], dtype="<U4")
    conf = probs.max(axis=1)
    return dirs, conf


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------

def _calibration_bins(
    p_up: np.ndarray,
    y_up: np.ndarray,
    n_bins: int = 10,
) -> list[dict]:
    """
    Return a list of calibration bins. Each entry:
      {bin_low, bin_high, n, mean_predicted, actual_up_rate}
    """
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    out: list[dict] = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        # last bin closed on the right
        if i == n_bins - 1:
            mask = (p_up >= lo) & (p_up <= hi)
        else:
            mask = (p_up >= lo) & (p_up < hi)
        n = int(mask.sum())
        if n == 0:
            out.append({
                "bin_low": round(lo, 2),
                "bin_high": round(hi, 2),
                "n": 0,
                "mean_predicted": None,
                "actual_up_rate": None,
            })
        else:
            out.append({
                "bin_low": round(lo, 2),
                "bin_high": round(hi, 2),
                "n": n,
                "mean_predicted": round(float(p_up[mask].mean()), 4),
                "actual_up_rate": round(float(y_up[mask].mean()), 4),
            })
    return out


def evaluate(
    forecaster: FittedForecaster,
    X: pd.DataFrame,
    y_true: np.ndarray,
) -> dict[str, Any]:
    """
    Compute a full metric bundle for a binary forecaster.

    Metrics:
      accuracy  — fraction of correct argmax predictions
      brier     — mean((p_up - y_up)^2). Baseline 0.25 (always 0.5).
      roc_auc   — ranking quality. 0.5 = random, 1.0 = perfect.
      log_loss  — cross-entropy. Baseline log(2) ≈ 0.693.
      precision/recall/f1 per class
      confusion_matrix
      calibration_bins — 10-bin calibration table
      pred_freq / true_freq — distribution sanity check
    """
    y_true = np.asarray(y_true, dtype="<U4")
    probs = predict_proba(forecaster, X)
    up_idx = forecaster.class_order.index("up")
    down_idx = forecaster.class_order.index("down")

    p_up = probs[:, up_idx]
    y_up = (y_true == "up").astype(int)  # 1 if up, 0 if down

    # Direction = argmax
    y_pred = np.where(p_up > 0.5, "up", "down").astype("<U4")

    acc = float(accuracy_score(y_true, y_pred))
    brier = float(brier_score_loss(y_up, p_up))
    try:
        auc = float(roc_auc_score(y_up, p_up))
    except ValueError:
        # Can happen if a split has only one class
        auc = float("nan")
    ll = float(log_loss(y_up, np.column_stack([1.0 - p_up, p_up]), labels=[0, 1]))

    labels = list(CLASS_ORDER)
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

    bins = _calibration_bins(p_up, y_up, n_bins=10)

    pred_freq = {c: float((y_pred == c).mean()) for c in labels}
    true_freq = {c: float((y_true == c).mean()) for c in labels}

    return {
        "n":              int(len(y_true)),
        "accuracy":       acc,
        "brier":          brier,
        "roc_auc":        auc,
        "log_loss":       ll,
        "per_class":      per_class,
        "confusion_matrix": cm.tolist(),
        "class_order":    list(CLASS_ORDER),
        "calibration_bins": bins,
        "pred_freq":      pred_freq,
        "true_freq":      true_freq,
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

    if payload["feature_columns"] != list(FEATURE_COLUMNS):
        raise RuntimeError(
            f"feature mismatch: saved {payload['feature_columns']}, "
            f"current {list(FEATURE_COLUMNS)}"
        )
    if payload["class_order"] != list(CLASS_ORDER):
        raise RuntimeError(
            f"class order mismatch: saved {payload['class_order']}, "
            f"current {list(CLASS_ORDER)}"
        )

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

    meta = {
        "trained_at":      datetime.now(timezone.utc).isoformat(),
        "horizons":        sorted(forecasters.keys()),
        "class_order":     list(CLASS_ORDER),
        "feature_count":   len(FEATURE_COLUMNS),
        "feature_columns": list(FEATURE_COLUMNS),
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
    "FittedForecaster",
    "fit_forecaster",
    "predict_proba",
    "predict_proba_up",
    "predict_direction",
    "evaluate",
    "save_forecaster",
    "load_forecaster",
    "write_run_metadata",
]