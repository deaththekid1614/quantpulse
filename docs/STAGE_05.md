# Stage 05 — Stock Page Core + 5-Year Chart

**Status:** ✅ complete
**Completed:** 2026-09-20
**Repo:** `~/IDE/quantpulse`
**Depends on:** Stage 4
**Supersedes:** nothing

---

## 1. What this stage delivered

The stock page became the real product surface. An interactive
candlestick chart with six timeframes, a rule-based performance
narrative, a 9-cell statistics grid, and the existing snapshot-driven
header and OHLC row.

Concretely:

- One new backend endpoint: `GET /api/securities/{ticker}/stats`
- One new Pydantic schema: `StatsOut`
- `lightweight-charts@4.2.3` integrated for candlestick rendering
- New `PriceChart.jsx` — dark-themed candlestick with crosshair,
  auto-resize, range switching
- New `TimeframeTabs.jsx` — 3M / 6M / 1Y / 3Y / 5Y / MAX
- New `narrative.js` — pure rule function, deterministic, no LLM
- New `PerformanceNarrative.jsx` — wraps the rule function with
  loading / error / empty states
- New `StatsGrid.jsx` — 3×3 responsive grid, sign-coloured returns
- `Stock.jsx` rewritten to compose all sections

No ML, no news, no forecasts, no risk engine. Those come in Stages 6–10.

---

## 2. Backend addition (frozen)

### `backend/app/api/routes/stats.py` (new)

`GET /api/securities/{ticker}/stats` — rolling statistics computed on
the fly from `prices_daily`. No new table; 60-second cache.

Fields:

| Field | Description |
|---|---|
| `high_52w`, `low_52w` | Calendar 52-week range |
| `pct_from_52w_high` | ≤ 0 |
| `pct_from_52w_low` | ≥ 0 |
| `ret_1d_pct`, `ret_5d_pct`, `ret_20d_pct` | Positional returns (N bars back) |
| `ret_1y_pct` | Close at latest date − 365 calendar days |
| `ret_ytd_pct` | Close at last trading day of previous year |
| `avg_volume_20d`, `avg_volume_60d` | Simple means |
| `all_time_high`, `all_time_low` | Since 2021-09-16 (start of history) |

Verified values for TCS on 2026-09-18:

```
52w range    : 1966.02 → 3287.16
from high    : -35.96%
from low     : +7.07%
1d return    : -3.88%   (matches /snapshot)
20d return   : -8.56%
YTD return   : -31.87%
1y return    : -30.99%
avg vol 20/60: 2,793,214 / 3,732,588
all-time     : 1966.02 → 4266.48
```

### `backend/app/api/schemas.py` (append-only)

Added `StatsOut`. All prior schemas byte-identical.

### `backend/app/api/router.py` (frozen)

Now includes 8 sub-routers (added `stats`).

---

## 3. Frontend additions (frozen)

### `frontend/package.json` (frozen)

Added `lightweight-charts` ^4.2.0 (installed 4.2.3).

### `frontend/src/charts/PriceChart.jsx` (frozen)

- Uses `createChart` from lightweight-charts v4
- Dark theme matching Tailwind `ink.*` tokens
- Candlestick series (green up, red down)
- Crosshair with dashed border
- Right price scale with 10% margins top/bottom
- `ResizeObserver` auto-fits width to container
- Reads `usePrices(ticker, range)`, maps bars to `{time, open, high, low, close}`
- Loading overlay while query in flight
- Chart instance created once per mount; data pushed via `setData`
- Clean teardown on unmount (`chart.remove()` + observer disconnect)
- Fixed height 380 px

### `frontend/src/components/TimeframeTabs.jsx` (frozen)

Six pills: `3M 6M 1Y 3Y 5Y MAX`. Active pill in `bg-ink-600 text-white`.
Emits `onChange(range)` with one of the backend range tokens.

Rationale for omitting `1W`: only ~5 candles, visually noisy. `1D`
requires intraday data we don't have. Both deferred.

### `frontend/src/components/narrative.js` (frozen)

Pure rule function. `buildNarrative(symbol, features) → string | null`.

Inputs (all required, all from `/snapshot.features`):
`px_over_sma_50`, `px_over_sma_200`, `rsi_14`, `ret_20d`, `vol_20d`.

Three sentences:

1. **Trend** — classified by price vs 50-day and 200-day SMAs:
   above-both / below-both / above-200-only / below-200-only / neutral.
2. **Momentum + 20-day performance** — RSI bucketed into very weak
   (<30) / weak (30–45) / neutral (45–55) / positive (55–70) / strong
   (≥70). Return converted from log to simple percent; <1% shown as
   "roughly flat."
3. **Volatility** — daily log-return std × √252 → annual band: low
   (<18%) / moderate (<30%) / elevated (<45%) / high (≥45%). Displayed
   as the daily percent for reader intuition.

Deterministic. Same inputs → same text. Returns `null` if any input is
missing or non-finite.

### `frontend/src/components/PerformanceNarrative.jsx` (frozen)

Wraps `buildNarrative` in the `useSnapshot` query. Three states:
loading (skeleton lines), error (red box), or paragraph. Falls back to
"insufficient feature history" if `buildNarrative` returns null.

### `frontend/src/components/StatsGrid.jsx` (frozen)

3×3 responsive grid (1 col mobile, 2 col tablet, 3 col desktop).
Uses `useQuery` directly with key `["stats", ticker]` — a dedicated
`useStats` hook wasn't warranted for one consumer. Values formatted
with Indian notation for volume (`L`/`Cr`), sign-coloured returns,
em-dash for null returns.

### `frontend/src/pages/Stock.jsx` (frozen)

Full-page composition:

1. Back link
2. Header (symbol · name · sector · NSE · date)
3. Price + change
4. Price history section with TimeframeTabs on the right, chart below
5. "How is {symbol} doing?" section — narrative
6. Statistics section — StatsGrid
7. Today's session — OHLC row
8. "Coming next" placeholder card listing Stages 6–10

`range` is local state, defaults to `1y`, not persisted across
navigations. On ticker change, tabs reset to `1Y` (component remounts
via React Router's route key).

### `frontend/src/api/client.js` (frozen)

Added `getStats(ticker)`. All existing exports unchanged.

---

## 4. Verification results

**Backend smoke test (Chunk A):**

```
shape + invariants: ok
  52w high     : 3287.16
  52w low      : 1966.02
  from high    : -35.96%
  from low     : +7.07%
  1d return    : -3.88%
  20d return   : -8.56%
  YTD return   : -31.87%
  1y return    : -30.99%
  vol 20d/60d  : 2,793,214 / 3,732,588
  all-time     : 1966.02 → 4266.48
ALL OK

stats 1d = -3.8813%, snapshot 1d = -3.8813%  → match
unknown ticker → 404
cache second call < 5 ms
```

**Chart library (Chunk B):**

```
lightweight-charts 4.2.3
createChart     ok
ColorType       ok
CrosshairMode   ok
LineStyle       ok
```

**Rule engine (Chunk E):**

Eight test cases covering all trend × momentum × volatility bands.
Invalid inputs return `null`. Determinism confirmed: identical inputs
produce identical output.

**Full build (Chunk G):**

```
✓ 95 modules transformed
dist/assets/index-*.css   12.68 kB │ gzip:  3.24 kB
dist/assets/index-*.js   379.17 kB │ gzip: 121.10 kB
✓ built in ~4 s
```

Bundle grew from ~68 kB gzip (Stage 4) to ~121 kB gzip — the
lightweight-charts library accounts for the majority. Acceptable.

---

## 5. Repository deltas since Stage 4

**Backend — added:**

```
backend/app/api/routes/stats.py
```

**Backend — modified:**

```
backend/app/api/schemas.py   (appended StatsOut)
backend/app/api/router.py    (added stats include)
```

**Frontend — added:**

```
frontend/src/charts/PriceChart.jsx
frontend/src/components/TimeframeTabs.jsx
frontend/src/components/PerformanceNarrative.jsx
frontend/src/components/narrative.js
frontend/src/components/StatsGrid.jsx
```

**Frontend — modified:**

```
frontend/package.json          (added lightweight-charts)
frontend/package-lock.json     (regenerated)
frontend/src/api/client.js     (added getStats)
frontend/src/pages/Stock.jsx   (full rewrite)
```

**Docs — added:**

```
docs/STAGE_05.md
```

**No changes** to `features.py`, `providers/`, `db/models.py`, any
ingest script, `api/hooks.js`, `Layout.jsx`, `Search.jsx`,
`MarketStrip.jsx`, `TopMovers.jsx`, `Home.jsx`, or any earlier schema
beyond the appended `StatsOut`.

---

## 6. Known limitations going into Stage 6

- Chart does not show a volume pane. Deferred until it's clearly
  needed.
- Chart has no moving-average overlays. The narrative describes
  trend from SMAs, but the chart shows only candles. Adding overlays
  is a small future improvement; not stage-critical.
- Chart has no data markers for events (earnings, splits). Out of
  scope for Stage 5.
- `1W` and `1D` ranges omitted. `1D` needs intraday data — not
  available from the current ingestion pipeline. `1W` is trivial to
  add but was deprioritised; revisit in Stage 12.
- Narrative only reads five features. It intentionally doesn't mention
  MACD, ATR, beta, or sector return. Those are available for Stage 10's
  fuller explanation engine.
- Narrative text is hardcoded English, no i18n.
- Bundle is now ~121 kB gzip. Comfortable on the target machine, but
  worth watching if later stages push past ~250 kB gzip.
- No tests in `backend/tests/` for `/stats`. Stage 12 collects all
  pytest tests.
- `stats` values are computed on the fly rather than stored. For 50
  securities this is fine (<5 ms per request). If the universe grows
  past ~500, precompute into a table during the batch pipeline in
  Stage 11.

---

## 7. Next stage entry point — Stage 6

**Stage 6 — Fundamentals + Company Info**

Company data and profile, shown on the stock page below the statistics
section.

**New backend endpoint:**

- `GET /api/securities/{ticker}/fundamentals` — one row per security,
  cached.

Fields to source from yfinance:

- Market cap, P/E, EPS (TTM)
- Revenue (TTM), Profit (TTM)
- Dividend yield
- Debt/equity
- ROE, ROCE
- Industry, employees, HQ
- Business description

Not every field will be available for every ticker — the response must
tolerate nulls and the UI must show "—" for missing values.

**Approach:**

1. New provider method `get_fundamentals(ticker)` in
   `providers/yahoo.py` (implementation), matching the existing
   `FundamentalsProvider` interface from `providers/base.py`.
2. New table `fundamentals` in `db/models.py` (append-only) with
   nullable columns for each metric.
3. New script `backend/scripts/ingest_fundamentals.py` — pulls for all
   50 tickers, upserts. Run after `ingest_prices`.
4. New route `api/routes/fundamentals.py`.
5. New schema `FundamentalsOut` (append-only to schemas.py).
6. New frontend component `CompanySnapshot.jsx` — a two-column card
   list: metric name on the left, value on the right.
7. New frontend component `CompanyProfile.jsx` — description paragraph,
   industry, employees, HQ.

**Design rules:**

- Human-language interpretation of a small subset of metrics:
  - "Profitability: Strong / Moderate / Weak" based on ROE/ROCE bands
  - "Valuation: Expensive / Fair / Cheap" based on P/E vs sector peers
  - "Balance sheet: Conservative / Moderate / Leveraged" based on D/E
- Raw numbers shown below the interpretation.
- "—" for missing metrics. No zeroes invented.
- No recommendation language ("buy", "sell", "undervalued").

**New sections on the stock page (below Statistics):**

- COMPANY SNAPSHOT — grid of metrics with interpretation
- ABOUT — description + industry + employees + HQ

**Out of scope for Stage 6:** news, forecasts, risk, explanations.

Deliverable: fundamentals populated for the full universe, a working
`/fundamentals` endpoint, and two new stock-page sections.

---

## 8. Handoff prompt for the next chat

Copy this into a new conversation:

> Context: I'm building **Quantpulse**. Repo at `~/IDE/quantpulse`.
> Read `docs/architecture_handoff.md` and `docs/STAGE_01.md` through
> `docs/STAGE_05.md` — all in my repo — before starting. Then begin
> **Stage 6 — Fundamentals + Company Info** exactly as scoped in
> section 7 of `docs/STAGE_05.md`.
>
> Environment: MacBook Air 2015, Intel i5, 8 GB RAM, Zorin OS 16
> (XFCE). Python 3.12.14 in `~/IDE/quantpulse/.venv` managed by `uv`.
> Node 20 + npm. Backend on `127.0.0.1:8000`, Vite on `localhost:5173`
> proxying `/api/*` to the backend.
>
> Rules: plan first, full-file replacements only, one test per chunk,
> no debug cycles, hand off as `docs/STAGE_06.md`.

---
