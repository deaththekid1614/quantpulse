# Stage 08A — Classical Forecasting Engine (Null Result)

**Status:** ✅ complete — pipeline ships, model does not
**Completed:** 2026-09-28
**Repo:** `~/IDE/quantpulse`
**Depends on:** Stage 7
**Supersedes:** nothing

---

## 1. Summary

Stage 8A built the full forecasting infrastructure: label generation,
dataset assembly, a calibrated binary classifier, save/load artifacts,
and a rigorous evaluation harness with leakage guards.

The pipeline works. **The model does not.** On the validation set
(2025-07-01 → 2025-10-31, 4,242 rows across 50 securities), the 7-day
binary up/down classifier achieved:

| Metric | Value | Baseline | Verdict |
|---|---|---|---|
| Accuracy | 0.5198 | 0.5000 | +2 pp — within noise |
| ROC AUC | 0.5050 | 0.5000 | ~zero ranking power |
| Brier | 0.2556 | 0.2500 | worse than baseline |
| Log loss | 0.7142 | 0.6931 | worse than baseline |

A systematic regime-filter sweep across 17 subsets found **no pocket
of signal with AUC > 0.53.** The best subset was `Nifty 5-day return > 0`
(AUC 0.5259, n=2,297), which is consistent with noise at this sample
size.

**Decision: Stage 8A does not ship forecasts to the UI.** The
infrastructure ships, the null result ships, the model does not. Stage
8B will add orthogonal features (news sentiment, market context,
cross-sectional rank) and re-evaluate.

---

## 2. What was built (frozen)

### `backend/app/ml/labels.py` (frozen)

Binary up/down labels from log future returns.

- `compute_future_return(close, horizon)` — log return from t to t+h
- `classify_binary(future_return)` — `up` if > 0, `down` if < 0, `None`
  if exactly 0 or NaN
- `build_binary_labels(price_df, horizons)` — wide DataFrame with
  `future_return_{h}d` and `label_{h}d` columns
- `label_columns(horizons)` — helper

A 3-class (up/flat/down) formulation with a volatility-scaled flat band
was **tested first and rejected.** It produced a degenerate classifier
that essentially never predicted `down`, with 0.40 accuracy overall.
The binary reformulation is the correct simplification.

### `backend/app/ml/dataset.py` (frozen)

Training data assembly with strict chronological split and three
leakage guards.

Split boundaries (locked):

| Split | Date range |
|---|---|
| train | 2022-07-05 → 2025-06-30 |
| val | 2025-07-01 → 2025-10-31 |
| test | 2025-11-03 → 2026-08-07 |

Per-horizon row counts:

| Horizon | train | val | test |
|---|---|---|---|
| 7d | 36,808 | 4,242 | 9,367 |
| 15d | 36,808 | 4,242 | 9,367 |
| 30d | 36,808 | 4,242 | 9,367 |

Class balance (train / val / test):

| Horizon | down (train/val/test) | up (train/val/test) |
|---|---|---|
| 7d | 43.3 / 47.5 / 48.6 | 56.7 / 52.5 / 51.4 |
| 15d | 41.5 / 45.7 / 48.3 | 58.5 / 54.3 / 51.7 |
| 30d | 39.5 / 39.0 / 50.7 | 60.5 / 61.0 / 49.3 |

Leakage guarantees (all verified in test):

1. `max(train dates) < min(val dates) < min(test dates)`
2. No NaN in any X or y for any split
3. Every label row has a corresponding feature row at the same
   `(security_id, date)` — no joins across time
4. Per-row date boundaries enforced (every train row ≤ TRAIN_END, etc.)

### `backend/app/ml/classical.py` (frozen)

Calibrated binary classifier.

- `HistGradientBoostingClassifier` with modest params
  (`max_iter=400, lr=0.05, max_depth=5, min_samples_leaf=40`)
- `CalibratedClassifierCV(method="isotonic", cv=3)`
- Class order locked to `["down", "up"]` (alphabetical)
- No class balancing — binary is naturally balanced enough
- Metrics reported: accuracy, Brier, ROC AUC, log loss,
  per-class precision/recall/F1, confusion matrix, 10-bin calibration
  table, predicted-vs-true class frequencies
- Save/load via joblib; loader validates feature columns and class
  order

Artifacts (gitignored): `backend/models_artifacts/forecasters/`
- `forecaster_7d.joblib` (~3.2 MB)
- `metadata.json` (~900 bytes)

---

## 3. Validation results

7-day horizon, validation set (2025-07-01 → 2025-10-31, 4,242 rows):

```
accuracy : 0.5198
brier    : 0.2556   (baseline 0.2500)
roc_auc  : 0.5050   (baseline 0.5000)
log_loss : 0.7142   (baseline 0.6931)
```

Per-class:

```
down   prec=0.484  rec=0.175  f1=0.257  n=2014
up     prec=0.527  rec=0.832  f1=0.645  n=2228
```

Confusion matrix (rows=true, cols=pred):

```
             pred_down  pred_up
true_down  [     352      1662 ]
true_up    [     375      1853 ]
```

Calibration bins:

```
range       n     pred    actual    gap
[0.0, 0.1]     2  0.0476  1.0000  +0.9524
[0.1, 0.2]    16  0.1254  1.0000  +0.8746
[0.2, 0.3]    14  0.2472  0.7857  +0.5385
[0.3, 0.4]    19  0.3755  0.2632  -0.1123
[0.4, 0.5]   676  0.4704  0.5044  +0.0340
[0.5, 0.6]  2528  0.5486  0.5261  -0.0225
[0.6, 0.7]   962  0.6290  0.5301  -0.0989
[0.7, 0.8]    25  0.7123  0.5200  -0.1923
```

Interpretation:
- 85% of rows fall in the `[0.4, 0.6]` band — the model has no
  conviction anywhere
- In the high-confidence `[0.6, 0.7]` bin, predicted 0.629 vs actual
  0.530 — model overstates confidence by ~10 pp
- In the extreme `[0.7, 0.8]` bin (only 25 rows), predicted 0.712 vs
  actual 0.520 — worse than a coin
- Predicted `down` frequency 17.1% vs true 47.5% — heavy prior bias
  toward `up`

---

## 4. Regime-filter sweep (validation set)

The model was tested on 17 subsets defined by market state, trend
state, volatility, model confidence, liquidity, RSI, and recent
returns. Complete results:

```
BASELINE (all val rows):
  all                                    n=4242  acc=0.5198  auc=0.5050

REGIME FILTERS (7d horizon, validation set):
  mkt_ret_5d > 0 (Nifty up)              n=2297  acc=0.5233  auc=0.5259
  mkt_ret_5d <= 0 (Nifty down)           n=1945  acc=0.5157  auc=0.4791
  above 200SMA                           n=3005  acc=0.5128  auc=0.5052
  below 200SMA                           n=1237  acc=0.5368  auc=0.4932
  low vol (<=median)                     n=2121  acc=0.5120  auc=0.4912
  high vol (>median)                     n=2121  acc=0.5276  auc=0.5194
  model has opinion (|p-0.5|>0.10)       n=1038  acc=0.5202  auc=0.4747
  model is unsure (|p-0.5|<=0.10)        n=3204  acc=0.5197  auc=0.5108
  normal volume (0.7<=relvol<=1.5)       n=2345  acc=0.5215  auc=0.5047
  unusual volume                         n=1897  acc=0.5177  auc=0.5052
  RSI neutral (40-60)                    n=2540  acc=0.5067  auc=0.4999
  RSI extreme (<30 or >70)               n= 380  acc=0.4579  auc=0.4790
  ret_5d > 0 (recent gainer)             n=2267  acc=0.4963  auc=0.5025
  ret_5d <= 0 (recent loser)             n=1975  acc=0.5468  auc=0.4923
  Nifty up AND stock above 200SMA        n=1708  acc=0.5181  auc=0.5202
  Nifty down AND stock below 200SMA      n= 648  acc=0.5355  auc=0.4543
  low vol AND above 200SMA               n=1568  acc=0.5108  auc=0.5002
  low vol AND RSI neutral                n=1346  acc=0.4993  auc=0.4670
```

**Key findings:**

1. **No subset has AUC > 0.53.** The single best result
   (`mkt_ret_5d > 0`, AUC 0.5259) is consistent with noise at n=2,297.
2. **Model confidence is anti-predictive.** When `|p_up - 0.5| > 0.10`,
   AUC drops to 0.4747 — worse than random. The model's strong opinions
   are wrong more often than right.
3. **Several filters show high accuracy but low AUC** (e.g.
   `ret_5d <= 0`: 0.5468 acc / 0.4923 AUC; `below 200SMA`: 0.5368 acc /
   0.4932 AUC). These are class-imbalance artifacts — the model is
   riding the prior, not making predictions.
4. **Combining filters does not help.** The two-filter combos score
   0.45–0.52, worse than the single best.

**Conclusion: the 24 price-derived features contain no exploitable
7-day directional signal.**

---

## 5. Why this is a real finding, not a bug

Every component was verified against hand-computed test cases:

- Labels: verified against synthetic log-growth series, constant
  series, and random walks (`tests A`, 9 assertions)
- Dataset: three leakage guards, all passing
- Model: class order locked, save/load byte-exact, `predict_proba`
  rows sum to 1

The pipeline is correct. The features are insufficient. This matches
decades of published research on liquid equity directional prediction:
price-derived technical indicators yield AUC 0.50–0.52 at short
horizons.

---

## 6. What ships

**Shipped:**

- `app/ml/labels.py`, `app/ml/dataset.py`, `app/ml/classical.py`
- `backend/models_artifacts/forecasters/forecaster_7d.joblib` (7-day
  model only; 15-day and 30-day not trained, since testing more
  horizons on features we know are noise is not a good use of time)
- `docs/STAGE_08A.md` (this file)

**Not shipped:**

- Forecast UI panel (`ForecastPanel.jsx`) — deferred to Stage 8B
- `/api/securities/{ticker}/forecast` endpoint — deferred to Stage 8B
- `forecasts` DB table — deferred to Stage 8B
- The 15-day and 30-day models — deferred to Stage 8B; they will be
  retrained with richer features

The pipeline remains available for Stage 8B to reuse.

---

## 7. Known limitations going into Stage 8B

- **No news sentiment used.** Stage 7 produces `sentiment_score`,
  `relevance_score`, `importance_score` per article. Aggregated (7d/30d
  rolling), these are known to add signal in published research.
- **No market context used.** VIX level, VIX change, Nifty 5d/20d
  returns, breadth (advancers / decliners) are all computable from data
  we have. Not currently in the feature set.
- **No fundamentals used.** Stage 6 produces P/E, ROE, margin, dividend
  yield per security. Relative to sector, these may carry signal.
- **No cross-sectional features.** Rank within sector, distance from
  52w high as a percentile, correlation to Nifty, dispersion — none
  currently used.
- **No sequence model.** LSTM on 60-day sequences could capture regime
  persistence that the tree model cannot see.
- **Sample size is modest.** 4 years of daily data × 50 securities =
  36,808 training rows. More history would reduce variance.

---

## 8. Next stage entry point — Stage 8B

**Stage 8B — Rich-feature forecasting**

Add orthogonal signal sources. Retrain. Re-evaluate with the same
strict methodology. Ship if AUC > 0.55; do not ship if it's still
near 0.50.

**New features to add (in `app/pipeline/rich_features.py`):**

*News aggregates (per security, per date):*
- `news_sent_7d_mean` — 7-day rolling mean of `sentiment_score`
- `news_sent_30d_mean` — 30-day rolling mean
- `news_sent_7d_std` — rolling std, capturing sentiment volatility
- `news_count_7d` — number of articles in the last 7 days
- `news_importance_wmean_30d` — importance-weighted sentiment
- `news_pos_frac_30d` — fraction of positive articles

*Market context (per date, shared across securities):*
- `vix_level` — India VIX close
- `vix_change_5d` — 5-day log change
- `vix_zscore_60d` — standardised vs 60-day history
- `nifty_ret_5d`, `nifty_ret_20d`
- `nifty_drawdown_60d` — current level vs 60-day high
- `breadth_5d` — fraction of Nifty 50 with positive 5-day return

*Fundamentals (per security, snapshot-joined):*
- `pe_vs_sector_median` — ratio
- `dividend_yield_pct`
- `profit_margin`, `roe`
- `market_cap_log`

*Cross-sectional (per security, per date, computed across peers):*
- `sector_rank_ret_20d` — percentile rank of 20d return within sector
- `pct_from_52w_high` — (close − high_52w) / high_52w
- `beta_60d_rank` — rank within universe
- `corr_to_nifty_60d` — rolling 60d correlation

**New table:** `features_daily_v2` with the full superset
(24 base + ~24 new = ~48 columns). Rebuild via a new script
`scripts/build_rich_features.py`. Keep the original `features_daily`
frozen so we can compare.

**Model:** same HGB + isotonic calibration. Same chronological split.
Same evaluation harness. Everything is directly comparable.

**Acceptance criteria:**

- ROC AUC ≥ 0.55 on validation: **ship to UI**
- ROC AUC 0.52–0.55: **ship with heavy caveats**, document the edges
- ROC AUC < 0.52: **report null result for 8B too**, and shift focus
  to volatility prediction (Stage 8C) instead

**Then Stage 8C** — LSTM on 60-day sequences, Colab-trained, ONNX-
exported. Only attempted if 8B shows improvement.

---

## 9. Handoff prompt for the next chat

Copy this into a new conversation:

> Context: I'm building **Quantpulse**. Repo at `~/IDE/quantpulse`.
> Read `docs/architecture_handoff.md` and `docs/STAGE_01.md` through
> `docs/STAGE_08A.md` — all in my repo — before starting.
>
> Stage 8A is complete. The forecasting pipeline works end-to-end
> (labels, dataset, calibrated classifier, save/load, evaluation) but
> the model has **no usable signal** on 24 price-derived features
> (ROC AUC 0.505 on validation, and a 17-filter regime sweep found no
> pocket with AUC > 0.53).
>
> Begin **Stage 8B — Rich-feature forecasting** exactly as scoped in
> section 8 of `docs/STAGE_08A.md`. The pipeline to reuse is in
> `backend/app/ml/`. Do not modify `labels.py`, `dataset.py`, or
> `classical.py` — they are frozen and correct.
>
> Environment: MacBook Air 2015, Intel i5, 8 GB RAM, Zorin OS 16
> (XFCE). Python 3.12.14 in `~/IDE/quantpulse/.venv` managed by `uv`.
> Node 20 + npm. Backend on `127.0.0.1:8000`, Vite on `localhost:5173`
> proxying `/api/*`.
>
> Rules: plan first, full-file replacements only, one test per chunk,
> no debug cycles, hand off as `docs/STAGE_08B.md`.

---
