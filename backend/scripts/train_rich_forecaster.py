#!/usr/bin/env python3
"""
Train rich-feature forecasters (Stage 8B).

Trains three binary up/down forecasters (7d, 15d, 30d) on the 45-feature
rich dataset and evaluates them on the same validation split used in
Stage 8A. Prints a head-to-head comparison against the 8A baseline.

The 8A baseline AUCs are hardcoded from docs/STAGE_08A.md. They are
historical facts about a specific run, not a moving target.
"""
from __future__ import annotations

import argparse
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
from app.ml.rich_dataset import RICH_FEATURE_COLUMNS, build_rich_dataset  # noqa: E402

setup_logging("INFO")
log = get_logger("quantpulse.train_rich")

BASELINE_8A = {
    7:  {"accuracy": 0.5198, "brier": 0.2556, "roc_auc": 0.5050, "log_loss": 0.7142},
}

DEFAULT_OUT_DIR = REPO_ROOT / "backend" / "models_artifacts" / "forecasters_rich"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train rich-feature forecasters")
    p.add_argument("--horizons", type=int, nargs="+", default=[7, 15, 30])
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return p.parse_args()


def _verdict(h: int, auc: float) -> str:
    if auc >= 0.55:
        return "SHIP — real edge"
    if auc >= 0.52:
        return "SHIP-WITH-CAVEATS — weak but real signal"
    return "NULL — no usable signal"


def main() -> int:
    args = parse_args()
    horizons = tuple(sorted(set(args.horizons)))

    log.info("Building rich dataset (45 features)...")
    t_ds = time.perf_counter()
    ds = build_rich_dataset(horizons=horizons)
    log.info("  dataset built in %.1fs", time.perf_counter() - t_ds)
    log.info("  feature count: %d", len(RICH_FEATURE_COLUMNS))

    forecasters = {}
    for h in horizons:
        d = ds[h]
        log.info("training h=%dd on %d train rows, %d val rows",
                 h, len(d.y_train), len(d.y_val))
        fc = fit_forecaster(
            X_train=d.X_train, y_train=d.y_train,
            X_val=d.X_val,     y_val=d.y_val,
            horizon=h,
            feature_columns=list(RICH_FEATURE_COLUMNS),
        )
        forecasters[h] = fc
        save_forecaster(fc, args.out_dir)

    write_run_metadata(args.out_dir, forecasters)

    print()
    print("=" * 78)
    print("VALIDATION RESULTS — 8B (rich features) vs 8A (base features)")
    print("=" * 78)
    print()

    print(f"{'horizon':>8}  {'metric':>10}  {'8A (base, 24)':>16}  {'8B (rich, 45)':>16}  {'delta':>10}")
    print("-" * 78)

    for h in horizons:
        m = forecasters[h].val_metrics
        base = BASELINE_8A.get(h)
        for metric_key, label in [
            ("accuracy", "accuracy"),
            ("brier",    "brier"),
            ("roc_auc",  "roc_auc"),
            ("log_loss", "log_loss"),
        ]:
            v_8b = m[metric_key]
            if base is None:
                print(f"  {h:>5}d  {label:>10}  {'—':>16}  {v_8b:>16.4f}  {'—':>10}")
            else:
                v_8a = base[metric_key]
                delta = v_8b - v_8a
                sign = "+" if delta >= 0 else ""
                print(f"  {h:>5}d  {label:>10}  {v_8a:>16.4f}  {v_8b:>16.4f}  {sign}{delta:>9.4f}")
        print()

    print("=" * 78)
    print("PER-CLASS DETAIL (rich, validation)")
    print("=" * 78)
    print()
    for h in horizons:
        m = forecasters[h].val_metrics
        print(f"h = {h}d")
        for cls, s in m["per_class"].items():
            print(f"  {cls:5s}  prec={s['precision']:.3f}  rec={s['recall']:.3f}  f1={s['f1']:.3f}  n={s['support']}")
        cm = np.array(m["confusion_matrix"])
        print(f"  confusion (rows=true, cols={m['class_order']}):")
        for i, row in enumerate(cm):
            print(f"    {m['class_order'][i]:5s}: {row.tolist()}")
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
            gap = b["actual_up_rate"] - b["mean_predicted"]
            print(f"  [{b['bin_low']:.1f}, {b['bin_high']:.1f}]  {b['n']:>5d}  {b['mean_predicted']:.4f}  {b['actual_up_rate']:.4f}  {gap:+.4f}")
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
