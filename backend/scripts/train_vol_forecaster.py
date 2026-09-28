#!/usr/bin/env python3
"""
Train volatility forecasters (Stage 8B-v2).

Trains three binary low_vol/high_vol forecasters (7d, 15d, 30d) on the
45-feature rich dataset using a training-only median threshold, and
evaluates them on the same chronological split used in Stage 8A/8B.

Writes:
  backend/models_artifacts/forecasters_vol/forecaster_{h}d.joblib
  backend/models_artifacts/forecasters_vol/metadata.json
  backend/models_artifacts/forecasters_vol/thresholds.json

Usage:
    python backend/scripts/train_vol_forecaster.py
    python backend/scripts/train_vol_forecaster.py --horizons 7
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import numpy as np  # noqa: E402

from app.core.log_config import get_logger, setup_logging  # noqa: E402
from app.ml.classical import (  # noqa: E402
    fit_forecaster,
    save_forecaster,
    write_run_metadata,
)
from app.ml.vol_dataset import (  # noqa: E402
    RICH_FEATURE_COLUMNS,
    VOL_CLASS_ORDER,
    build_vol_dataset,
)

setup_logging("INFO")
log = get_logger("quantpulse.train_vol")

DEFAULT_OUT_DIR = REPO_ROOT / "backend" / "models_artifacts" / "forecasters_vol"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train volatility forecasters")
    p.add_argument("--horizons", type=int, nargs="+", default=[7, 15, 30])
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return p.parse_args()


def _verdict(h: int, auc: float) -> str:
    if auc >= 0.70:
        return "STRONG — ship with confidence"
    if auc >= 0.65:
        return "GOOD — real, learnable signal"
    if auc >= 0.60:
        return "MODERATE — weaker than expected but real"
    if auc >= 0.55:
        return "WEAK — usable with caveats"
    return "NULL — no usable signal"


def _write_thresholds(out_dir: Path, thresholds: dict[int, float]) -> Path:
    """Write thresholds.json next to the model files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "thresholds.json"
    payload = {
        "note": "Training-split median of future realized volatility per horizon. "
                "Applied unchanged to validation and test. Read by build_vol_forecasts.py.",
        "thresholds": {str(h): round(v, 8) for h, v in sorted(thresholds.items())},
    }
    path.write_text(json.dumps(payload, indent=2))
    log.info("wrote %s", path.name)
    return path


def main() -> int:
    args = parse_args()
    horizons = tuple(sorted(set(args.horizons)))

    log.info("Building volatility dataset (45 features)...")
    t_ds = time.perf_counter()
    ds = build_vol_dataset(horizons=horizons)
    log.info("  dataset built in %.1fs", time.perf_counter() - t_ds)

    forecasters = {}
    thresholds: dict[int, float] = {}

    for h in horizons:
        d = ds[h]
        thresholds[h] = float(d.threshold)
        log.info("training h=%dd on %d train rows, %d val rows, threshold=%.4f",
                 h, len(d.y_train), len(d.y_val), d.threshold)
        fc = fit_forecaster(
            X_train=d.X_train, y_train=d.y_train,
            X_val=d.X_val,     y_val=d.y_val,
            horizon=h,
            feature_columns=list(RICH_FEATURE_COLUMNS),
            class_order=VOL_CLASS_ORDER,
        )
        forecasters[h] = fc
        save_forecaster(fc, args.out_dir)

    write_run_metadata(args.out_dir, forecasters)
    _write_thresholds(args.out_dir, thresholds)

    # --- Report ---
    print()
    print("=" * 78)
    print("VOLATILITY FORECAST — VALIDATION RESULTS")
    print("=" * 78)
    print()

    print(f"{'horizon':>8}  {'threshold':>10}  {'accuracy':>10}  {'roc_auc':>10}  {'brier':>10}  {'log_loss':>10}")
    print("-" * 78)
    for h in horizons:
        m = forecasters[h].val_metrics
        print(f"  {h:>5}d  {thresholds[h]:>10.4f}  {m['accuracy']:>10.4f}  {m['roc_auc']:>10.4f}  {m['brier']:>10.4f}  {m['log_loss']:>10.4f}")
    print()

    print("=" * 78)
    print("PER-CLASS DETAIL")
    print("=" * 78)
    print()
    for h in horizons:
        m = forecasters[h].val_metrics
        print(f"h = {h}d  (positive class = {m['positive_class']})")
        for cls, s in m["per_class"].items():
            print(f"  {cls:10s}  prec={s['precision']:.3f}  rec={s['recall']:.3f}  f1={s['f1']:.3f}  n={s['support']}")
        cm = np.array(m["confusion_matrix"])
        print(f"  confusion (rows=true, cols={m['class_order']}):")
        for i, row in enumerate(cm):
            print(f"    {m['class_order'][i]:10s}: {row.tolist()}")
        print(f"  pred_freq: {m['pred_freq']}")
        print(f"  true_freq: {m['true_freq']}")
        print()

    if 7 in forecasters:
        print("=" * 78)
        print("CALIBRATION BINS (7d, validation)")
        print("=" * 78)
        print()
        print(f"  {'range':>14}  {'n':>5}  {'pred':>7}  {'actual':>7}  {'gap':>7}")
        for b in forecasters[7].val_metrics["calibration_bins"]:
            if b["n"] == 0:
                continue
            gap = b["actual_positive_rate"] - b["mean_predicted"]
            print(f"  [{b['bin_low']:.1f}, {b['bin_high']:.1f}]  {b['n']:>5d}  {b['mean_predicted']:.4f}  {b['actual_positive_rate']:.4f}  {gap:+.4f}")
        print()

    print("=" * 78)
    print("DECISION")
    print("=" * 78)
    print()
    for h in horizons:
        auc = forecasters[h].val_metrics["roc_auc"]
        verdict = _verdict(h, auc)
        print(f"  h = {h:>2}d   AUC = {auc:.4f}   →   {verdict}")
    print()

    best_h = max(horizons, key=lambda x: forecasters[x].val_metrics["roc_auc"])
    best_auc = forecasters[best_h].val_metrics["roc_auc"]
    print(f"  best horizon: {best_h}d  (AUC {best_auc:.4f})")
    print(f"  overall verdict: {_verdict(best_h, best_auc)}")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())