#!/usr/bin/env python3
"""
Populate the `vol_forecasts` table.

For each security, loads the trained volatility forecasters (7d, 15d,
30d), predicts the probability of above-median forward realized
volatility for the latest date in `rich_features_daily`, and stores the
result.

Forecasts are generated ONLY for the latest date per security. The UI
shows "as of YYYY-MM-DD". Historical backtest performance is documented
in the Stage 8B-v2 handoff.

Model version
-------------
`MODEL_VERSION` is a stable string, not a timestamp. Retraining the
models produces a new set of .joblib files with a new training
timestamp, but the model_version stored here remains "vol-v1" so
forecasts UPDATE in place rather than accumulating rows across retrains.
Bump to "vol-v2" when the model architecture or feature set changes.

Usage:
    python backend/scripts/build_vol_forecasts.py --ticker TCS.NS
    python backend/scripts/build_vol_forecasts.py --universe nifty50

Idempotent. Re-running updates rows in place.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import numpy as np
import pandas as pd
from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.sqlite import insert as sqlite_insert  # noqa: E402

from app.core.log_config import get_logger, setup_logging  # noqa: E402
from app.db.models import (  # noqa: E402
    FeaturesDaily,
    IngestLog,
    RichFeaturesDaily,
    Security,
    VolForecastRow,
)
from app.db.session import init_db, session_scope  # noqa: E402
from app.ml.classical import (  # noqa: E402
    FittedForecaster,
    load_forecaster,
    predict_proba,
)
from app.ml.vol_dataset import (  # noqa: E402
    RICH_FEATURE_COLUMNS,
    VOL_CLASS_ORDER,
)
from app.pipeline.features import FEATURE_COLUMNS  # noqa: E402
from app.pipeline.rich_features import (  # noqa: E402
    CROSS_SECTIONAL_FEATURE_COLUMNS,
    MARKET_FEATURE_COLUMNS,
    NEWS_FEATURE_COLUMNS,
)

setup_logging("INFO")
log = get_logger("quantpulse.build_vol_forecasts")

DEFAULT_HORIZONS: tuple[int, ...] = (7, 15, 30)
MODELS_DIR = REPO_ROOT / "backend" / "models_artifacts" / "forecasters_vol"

# Stable model identifier. Bump when the model architecture or feature
# set changes in a breaking way.
MODEL_VERSION = "vol-v1"


# ---------------------------------------------------------------------------
# model loading
# ---------------------------------------------------------------------------

def load_all_forecasters(horizons: tuple[int, ...]) -> dict[int, FittedForecaster]:
    out: dict[int, FittedForecaster] = {}
    for h in horizons:
        path = MODELS_DIR / f"forecaster_{h}d.joblib"
        if not path.exists():
            raise SystemExit(
                f"model not found: {path}\n"
                f"run: python backend/scripts/train_vol_forecaster.py"
            )
        fc = load_forecaster(path)
        if fc.class_order != list(VOL_CLASS_ORDER):
            raise SystemExit(
                f"model {path.name} has unexpected class_order {fc.class_order}, "
                f"expected {list(VOL_CLASS_ORDER)}"
            )
        if fc.feature_columns != list(RICH_FEATURE_COLUMNS):
            raise SystemExit(
                f"model {path.name} has unexpected feature_columns "
                f"(len={len(fc.feature_columns)}, expected {len(RICH_FEATURE_COLUMNS)})"
            )
        out[h] = fc
    return out


def load_thresholds() -> dict[int, float]:
    """
    Read thresholds.json written by train_vol_forecaster.py.
    Falls back to {} if missing — callers handle absent thresholds.
    """
    path = MODELS_DIR / "thresholds.json"
    if not path.exists():
        log.warning("thresholds.json not found at %s — threshold will be 0.0", path)
        return {}
    payload = json.loads(path.read_text())
    raw = payload.get("thresholds", {})
    return {int(k): float(v) for k, v in raw.items()}


# ---------------------------------------------------------------------------
# latest features per security
# ---------------------------------------------------------------------------

def load_latest_features(ticker_filter: str | None) -> dict[int, dict]:
    """
    Return {security_id: {ticker, date, values: dict[str, float]}}
    for the latest date per security, joining features_daily and
    rich_features_daily.
    """
    with session_scope() as db:
        secs = db.execute(select(Security.id, Security.ticker)).all()
        id_to_ticker = {sid: tk for sid, tk in secs}

        stmt_base = select(
            FeaturesDaily.security_id,
            FeaturesDaily.date,
            *[getattr(FeaturesDaily, c) for c in FEATURE_COLUMNS],
        ).order_by(FeaturesDaily.security_id, FeaturesDaily.date)
        stmt_rich = select(
            RichFeaturesDaily.security_id,
            RichFeaturesDaily.date,
            *[getattr(RichFeaturesDaily, c) for c in
              NEWS_FEATURE_COLUMNS + MARKET_FEATURE_COLUMNS + CROSS_SECTIONAL_FEATURE_COLUMNS],
        ).order_by(RichFeaturesDaily.security_id, RichFeaturesDaily.date)

        if ticker_filter:
            sec_id = next((sid for sid, tk in id_to_ticker.items() if tk == ticker_filter), None)
            if sec_id is None:
                raise SystemExit(f"ticker {ticker_filter!r} not in securities table")
            stmt_base = stmt_base.where(FeaturesDaily.security_id == sec_id)
            stmt_rich = stmt_rich.where(RichFeaturesDaily.security_id == sec_id)

        base_rows = db.execute(stmt_base).all()
        rich_rows = db.execute(stmt_rich).all()

    base_df = pd.DataFrame(
        base_rows,
        columns=["security_id", "date", *FEATURE_COLUMNS],
    )
    rich_df = pd.DataFrame(
        rich_rows,
        columns=[
            "security_id", "date",
            *NEWS_FEATURE_COLUMNS, *MARKET_FEATURE_COLUMNS, *CROSS_SECTIONAL_FEATURE_COLUMNS,
        ],
    )

    base_latest = base_df.sort_values(["security_id", "date"]).groupby("security_id").tail(1)
    rich_latest = rich_df.sort_values(["security_id", "date"]).groupby("security_id").tail(1)

    merged = base_latest.merge(
        rich_latest,
        on=["security_id", "date"],
        how="left",
    )

    out: dict[int, dict] = {}
    for _, row in merged.iterrows():
        sid = int(row["security_id"])
        out[sid] = {
            "ticker":  id_to_ticker.get(sid, "?"),
            "date":    pd.Timestamp(row["date"]).date(),
            "values":  row.to_dict(),
        }
    return out


# ---------------------------------------------------------------------------
# prediction
# ---------------------------------------------------------------------------

def predict_for_security(
    security_id: int,
    ticker: str,
    forecast_date: date,
    row: dict,
    forecasters: dict[int, FittedForecaster],
    thresholds: dict[int, float],
) -> list[dict]:
    """Return one row-dict per horizon, ready for upsert."""
    x_values: dict[str, float] = {}
    for col in RICH_FEATURE_COLUMNS:
        v = row.get(col, np.nan)
        try:
            x_values[col] = float(v) if v is not None else np.nan
        except (TypeError, ValueError):
            x_values[col] = np.nan

    X = pd.DataFrame([x_values], columns=list(RICH_FEATURE_COLUMNS)).astype("float32")

    current_vol = None
    v20 = row.get("vol_20d")
    if v20 is not None and pd.notna(v20):
        current_vol = float(v20)

    out: list[dict] = []
    for h, fc in forecasters.items():
        probs = predict_proba(fc, X)[0]
        p_low  = float(probs[fc.class_order.index("low_vol")])
        p_high = float(probs[fc.class_order.index("high_vol")])

        auc = None
        if fc.val_metrics and "roc_auc" in fc.val_metrics:
            a = float(fc.val_metrics["roc_auc"])
            auc = round(a, 4) if np.isfinite(a) else None

        out.append({
            "security_id":     security_id,
            "date":            forecast_date,
            "horizon_days":    h,
            "prob_high_vol":   round(p_high, 6),
            "prob_low_vol":    round(p_low, 6),
            "threshold":       float(thresholds.get(h, 0.0)),
            "current_vol_20d": current_vol,
            "model_auc":       auc,
            "model_version":   MODEL_VERSION,
        })
    return out


def upsert_rows(rows: list[dict]) -> tuple[int, int]:
    if not rows:
        return 0, 0

    keys = [(r["security_id"], r["date"], r["horizon_days"], r["model_version"]) for r in rows]

    with session_scope() as db:
        existing = set()
        for sid, dt, h, ver in keys:
            row = db.execute(
                select(VolForecastRow.id).where(
                    VolForecastRow.security_id == sid,
                    VolForecastRow.date == dt,
                    VolForecastRow.horizon_days == h,
                    VolForecastRow.model_version == ver,
                )
            ).first()
            if row is not None:
                existing.add((sid, dt, h, ver))

    with session_scope() as db:
        stmt = sqlite_insert(VolForecastRow).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["security_id", "date", "horizon_days", "model_version"],
            set_={
                "prob_high_vol":   stmt.excluded.prob_high_vol,
                "prob_low_vol":    stmt.excluded.prob_low_vol,
                "threshold":       stmt.excluded.threshold,
                "current_vol_20d": stmt.excluded.current_vol_20d,
                "model_auc":       stmt.excluded.model_auc,
                "created_at":      stmt.excluded.created_at,
            },
        )
        db.execute(stmt)

    added = len(rows) - len(existing)
    updated = len(existing)
    return added, updated


# ---------------------------------------------------------------------------
# log helpers
# ---------------------------------------------------------------------------

def _open_log(ticker: str) -> int:
    with session_scope() as db:
        row = IngestLog(ticker=ticker, status="running", started_at=datetime.now(timezone.utc))
        db.add(row)
        db.flush()
        return row.id


def _close_log(log_id: int, status: str, added: int = 0, updated: int = 0,
               error: str | None = None) -> None:
    with session_scope() as db:
        row = db.get(IngestLog, log_id)
        if row is None:
            return
        row.status = status
        row.rows_added = added
        row.rows_updated = updated
        row.error = error
        row.finished_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Quantpulse volatility forecast builder")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--ticker",   help="single Yahoo ticker, e.g. TCS.NS")
    g.add_argument("--universe", choices=["nifty50"], help="build for every security")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    init_db()

    log.info("Loading volatility forecasters from %s", MODELS_DIR)
    forecasters = load_all_forecasters(DEFAULT_HORIZONS)
    log.info("  loaded %d models (horizons: %s)", len(forecasters), sorted(forecasters.keys()))

    thresholds = load_thresholds()
    if thresholds:
        log.info("  thresholds: %s", {h: round(v, 4) for h, v in sorted(thresholds.items())})
    else:
        log.warning("  no thresholds loaded — threshold will be 0.0 in the DB")

    log.info("Loading latest features per security...")
    latest = load_latest_features(args.ticker)
    log.info("  %d securities with features", len(latest))

    t0 = time.perf_counter()
    total_added = total_updated = 0

    for i, (security_id, info) in enumerate(sorted(latest.items()), 1):
        ticker = info["ticker"]
        fd = info["date"]
        log.info("[%d/%d] %s (as of %s)", i, len(latest), ticker, fd)

        log_id = _open_log(ticker)
        try:
            rows = predict_for_security(
                security_id=security_id,
                ticker=ticker,
                forecast_date=fd,
                row=info["values"],
                forecasters=forecasters,
                thresholds=thresholds,
            )

            added, updated = upsert_rows(rows)
            total_added   += added
            total_updated += updated

            _close_log(log_id, status="ok", added=added, updated=updated)

            summary = " | ".join(
                f"h{r['horizon_days']}={r['prob_high_vol']:.2f}" for r in rows
            )
            log.info("  %-15s +%-2d ~%-2d   %s", ticker, added, updated, summary)

        except Exception as exc:
            log.exception("  %-15s FAILED: %s", ticker, exc)
            _close_log(log_id, status="error", error=str(exc))

    elapsed = time.perf_counter() - t0
    log.info("=" * 60)
    log.info("Done in %.1fs", elapsed)
    log.info("  securities     : %d", len(latest))
    log.info("  rows added     : %d", total_added)
    log.info("  rows updated   : %d", total_updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())