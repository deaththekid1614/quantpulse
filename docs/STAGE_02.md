# Stage 02 — Feature Engine

**Status:** ✅ complete
**Completed:** 2026-09-20
**Repo:** `~/IDE/quantpulse`
**Depends on:** Stage 1
**Supersedes:** nothing

---

## 1. What this stage delivered

A pure, vectorised feature engine that transforms raw daily OHLCV plus
market index data into 24 numerical features per (security, date), plus
a batch builder that populates `features_daily` for the entire Nifty 50
universe.

Concretely:

- Two new tables in `models.py`: `market_index_daily`, `features_daily`
- `backend/scripts/ingest_indices.py` — populates `^NSEI`, `^NSEBANK`,
  `^INDIAVIX`
- `backend/app/pipeline/features.py` — 8 pure functions + `compute_all`,
  fully vectorised, no side effects
- `backend/scripts/build_features.py` — reads prices + Nifty, computes
  features, writes to `features_daily`
- Populated DB: **50 securities × ~1039 feature rows = 51,939 rows**,
  covering **2022-07-05 → 2026-09-18**

---

## 2. Design rules locked in this stage

1. **`features.py` is pure.** No DB access, no file IO, no globals. Its
   functions take DataFrames and return DataFrames. This makes the
   engine testable in isolation and the DB layer swappable later.
2. **Warm-up rows are dropped, not stored as NaN.** Any row where any
   feature is NaN after computation is removed before insertion. The
   `features_daily` columns are therefore all `NOT NULL`.
3. **Volume baselines use the PRIOR 20 days** (`rolling().shift(1)`),
   not the inclusive window. This matches standard relative-volume
   definitions and avoids diluting the signal with today's own value.
4. **`sector_ret_1d` uses a fill-with-zero policy** for single-member
   sectors (Telecom — Bharti Airtel). Zero means "no sector signal,
   neutral". This preserves the row rather than dropping the entire
   ticker.
5. **Extreme values are not winsorized here.** `beta_60d = 5.48` for
   Adani Enterprises in April 2023 is real. Any winsorization belongs in
   Stage 8 (ML preprocessing), not in feature engineering.

---

## 3. Feature catalogue

24 columns in `features_daily`, in this exact order
(`FEATURE_COLUMNS` in `features.py`):

| Column | Description | Warm-up |
|---|---|---|
| `ret_1d` | 1-day log return | 1 |
| `ret_5d` | 5-day log return | 5 |
| `ret_20d` | 20-day log return | 20 |
| `vol_20d` | rolling std of `ret_1d` (ddof=1) | 21 |
| `atr_14d` | 14-day SMA of True Range | 14 |
| `sma_20` | 20-day simple moving average of close | 20 |
| `sma_50` | 50-day SMA | 50 |
| `sma_200` | 200-day SMA | **200** ← binding constraint |
| `ema_12` | 12-period EMA (adjust=False) | 12 |
| `ema_26` | 26-period EMA | 26 |
| `px_over_sma_20` | close / sma_20 (ratio ≈ 1.0) | 20 |
| `px_over_sma_50` | close / sma_50 | 50 |
| `px_over_sma_200` | close / sma_200 | 200 |
| `rsi_14` | Wilder RSI-14, range 0–100 | 14 |
| `macd` | EMA(12) − EMA(26) | 26 |
| `macd_signal` | EMA(9) of `macd` | 35 |
| `macd_hist` | `macd` − `macd_signal` | 35 |
| `roc_10` | 10-day rate of change, in percent | 10 |
| `rel_volume_20d` | today volume / prior 20d mean volume | 20 |
| `volume_z_20d` | (today − prior mean) / prior std | 20 |
| `mkt_ret_1d` | Nifty 50, 1-day log return | 1 |
| `mkt_ret_5d` | Nifty 50, 5-day log return | 5 |
| `beta_60d` | 60-day rolling beta vs Nifty | 60 (+1 ret) |
| `sector_ret_1d` | mean 1d log return of same-sector peers | 1 |

**Effective warm-up per ticker:** 203–205 rows (binding: `sma_200` and
any one-day gaps). Tickers with 1243 price rows produce ~1038–1039
feature rows.

---

## 4. Locked files

### `backend/app/db/models.py` (append-only)

`MarketIndexDaily` and `FeaturesDaily` added. Existing `Security`,
`PriceDaily`, `IngestLog` **unchanged**. Future stages append new
classes, never edit existing ones.

### `backend/app/pipeline/features.py` (frozen)

Exports:
- `compute_returns(price_df)`
- `compute_volatility(price_df)`
- `compute_moving_averages(price_df)`
- `compute_momentum(price_df)`
- `compute_volume(price_df)`
- `compute_market_context(price_df, index_df)`
- `compute_beta(price_df, index_df, window=60)`
- `compute_sector_context(price_df, peer_closes)`
- `compute_all(price_df, nifty_df, peer_closes)`
- `FEATURE_COLUMNS` (constant tuple of 24 names)

### `backend/scripts/ingest_indices.py` (frozen)

CLI: `--years N` (default 5), optional `--symbol ^NSEI`.
Indices tracked: `^NSEI`, `^NSEBANK`, `^INDIAVIX`.

### `backend/scripts/build_features.py` (frozen)

CLI: `--ticker TCS.NS` or `--universe nifty50`.
Loads all prices into memory once (~62k rows), loads Nifty once, iterates
securities, computes, upserts. Logs each ticker to `ingest_log` with
`status='ok'` and row counts.

---

## 5. Verification results

**Index ingestion:**

```
^NSEI      +1238 rows  (2021-09-16 → 2026-09-18)
^NSEBANK   +1237 rows
^INDIAVIX  +1232 rows
```

**Feature builder (final run):**

```
securities     : 50
rows added     : 51939
rows updated   : 0
Done in        : 30.5s
```

Per-ticker row count: 1038–1039 (varies by 1 row due to single-day gaps
in Yahoo's feed).

**BHARTIARTL.NS verification (post-fix):**

```
BHARTIARTL.NS rows        : 1039
BHARTIARTL.NS sum(sector) : 0.000000  (fill-with-zero policy working)
```

**Beta range check (across all 51,939 rows):**

```
beta_60d: avg=0.962  min=-0.635  max=5.483
```

The max of 5.48 is Adani Enterprises in March–April 2023 (Hindenburg
window). This is real, documented market behaviour, not a bug.

**Cross-check TCS last row (recompute vs stored):**

```
max diff across all features: 0.00e+00
```

Stored rows match fresh computations exactly.

---

## 6. Repository deltas since Stage 1

**Added:**

```
backend/app/pipeline/features.py
backend/scripts/ingest_indices.py
backend/scripts/build_features.py
docs/STAGE_02.md
```

**Modified:**

```
backend/app/db/models.py       (appended MarketIndexDaily, FeaturesDaily)
```

**DB state:**

```
securities         : 50
prices_daily       : 62,138 rows
market_index_daily : 3,707 rows
features_daily     : 51,939 rows
```

---

## 7. Known limitations going into Stage 3

- `beta_60d` can exceed 3 during idiosyncratic events. Winsorization is
  deferred to Stage 8 (ML). Do not modify `features.py` to clamp it.
- `sector_ret_1d = 0.0` for Bharti Airtel on every date. This is the
  fill policy. It is not a "real" zero. Stage 10 (Explanation Engine)
  must not describe it as "flat sector performance" for Airtel — check
  the peer count before narrating.
- Feature warm-up is dominated by `sma_200`. The first ~200 trading
  days per ticker are unusable. Any model in Stage 8 must respect this.
- No train/validation split logic yet — that belongs to Stage 8.
- `macd_hist` mean is ~-0.011 (not exactly zero) because MACD and
  signal have slightly different warm-up start points. This is expected.
- No tests in `backend/tests/` yet — Stage 12 adds the pytest suite.
- The `Unknown` sector no longer exists in the DB. Any future ingestion
  of a ticker not in `universe.json` will write `sector='Unknown'`,
  which is fine for ad-hoc probing but should not persist.

---

## 8. Next stage entry point — Stage 3

**Stage 3 — Backend API Core**

Read-only HTTP endpoints over the three populated data layers. No ML, no
news, no explanations.

Endpoints (all under `/api`):

- `GET /api/securities` — list of all securities with ticker, symbol,
  name, sector
- `GET /api/securities/{ticker}` — full metadata for one security
- `GET /api/securities/{ticker}/prices?range=1y` — OHLCV history with
  range params (`1w`, `1m`, `6m`, `1y`, `3y`, `5y`, `max`)
- `GET /api/securities/{ticker}/features?range=1y` — feature history
  with the same range params
- `GET /api/securities/{ticker}/snapshot` — today's most recent row:
  latest close, change, volume, plus the latest feature row values

Design:
- Pydantic response schemas in `backend/app/api/schemas.py`
- Router per resource in `backend/app/api/routes/`
- Query via `SessionLocal` (sync), FastAPI thread pool handles it
- In-memory TTL cache for hot reads (simple dict + timestamp, no Redis)
- Structured error responses: 404 for unknown ticker, 400 for bad range

Out of scope for Stage 3: ML, NLP, news, forecasts, explanations, any
frontend changes.

Deliverable: a working read-only API with `/docs` Swagger UI showing
every endpoint and example responses captured in `docs/STAGE_03.md`.

---

## 9. Handoff prompt for the next chat

Copy this into a new conversation:

> Context: I'm building **Quantpulse**. Repo at `~/IDE/quantpulse`.
> Read `docs/architecture_handoff.md`, `docs/STAGE_01.md`, and
> `docs/STAGE_02.md` — all in my repo — before starting. Then begin
> **Stage 3 — Backend API Core** exactly as scoped in section 8 of
> `docs/STAGE_02.md`.
>
> Environment: MacBook Air 2015, Intel i5, 8 GB RAM, Zorin OS 16
> (XFCE). Python 3.12.14 in `~/IDE/quantpulse/.venv` managed by `uv`.
> System Python untouched at 3.8.10.
>
> Rules: plan first, full-file replacements only, one test per chunk,
> no debug cycles, hand off as `docs/STAGE_03.md`.

---
