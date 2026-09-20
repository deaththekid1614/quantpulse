# Stage 04 — Frontend Foundation + Home + Search

**Status:** ✅ complete
**Completed:** 2026-09-20
**Repo:** `~/IDE/quantpulse`
**Depends on:** Stage 3
**Supersedes:** nothing

---

## 1. What this stage delivered

The first real UI, wired to the live API. React Router + React Query
setup, a layout shell, a home page with three live sections, an
autocomplete search box in the top bar, and a minimal stock page driven
by `/snapshot`.

Concretely:

- Two new backend endpoints: `GET /api/indices/snapshot` and
  `GET /api/movers?limit=N`
- Four new Pydantic schemas: `IndexQuote`, `IndexSnapshotOut`,
  `MoverOut`, `MoversOut`
- React Router 6 with `/` (home) and `/stock/:ticker` routes
- React Query client with a 60-second `staleTime` matching the backend
  cache TTL
- API client (`api/client.js`) with error propagation as `err.status`
- React Query hooks (`api/hooks.js`) — one per endpoint, stable query
  keys, `enabled` guards
- Layout shell: top bar with wordmark + search, main outlet, footer
- Home page: market strip (3 indices), top movers (10 securities),
  market summary placeholder
- Search: live autocomplete over `/api/securities`, keyboard-navigable
  (↑/↓/Enter/Esc), click-outside-to-close, click-to-navigate
- Stock page: `/snapshot`-driven header, OHLC row, loading + 404 + error
  states

No ML, no NLP, no news, no charts, no fundamentals. Those come later.

---

## 2. Backend additions (frozen)

### `backend/app/api/routes/indices.py` (new)

`GET /api/indices/snapshot` — latest bar + 1-day change for each tracked
index, in fixed display order:

| Symbol | Display name |
|---|---|
| `^NSEI` | NIFTY 50 |
| `^NSEBANK` | BANK NIFTY |
| `^INDIAVIX` | INDIA VIX |

Reads from `market_index_daily`. Cached for 60 s under key
`indices:snapshot`.

### `backend/app/api/routes/movers.py` (new)

`GET /api/movers?limit=N` (1 ≤ N ≤ 50, default 10)

Returns the N securities with the largest **absolute** 1-day percent
change on the most recent feature date. Uses `features_daily.ret_1d`
(log return) converted via `exp(r) - 1` to percent. Sorted descending by
`|change_1d_pct|`. Cached under key `movers:{limit}`.

### `backend/app/api/schemas.py` (append-only)

Four new models — no edits to existing schemas:

```
IndexQuote          symbol, name, as_of, close, change_1d, change_1d_pct
IndexSnapshotOut    as_of, indices[]
MoverOut            ticker, symbol, name, sector, close, change_1d_pct, volume
MoversOut           as_of, count, movers[]
```

### `backend/app/api/router.py` (frozen)

Now includes 7 sub-routers: `health`, `securities`, `prices`,
`features`, `snapshot`, `indices`, `movers`.

---

## 3. Frontend additions (frozen)

### `frontend/package.json` (frozen)

Added:
- `@tanstack/react-query` ^5.59
- `react-router-dom` ^6.27

Confirmed installed: react 18.3.1, react-dom 18.3.1,
react-router-dom 6.30.6, @tanstack/react-query 5.103.1, vite 5.4.21.

### `frontend/src/api/client.js` (frozen)

Pure fetch wrapper. In the browser, calls are relative (`/api/...`) and
Vite proxies to `127.0.0.1:8000`. In Node (used by tests), the base
defaults to `http://127.0.0.1:8000` unless `QUANTPULSE_API` env var
overrides. Non-OK responses throw `Error` with `.status` set to the HTTP
code, so hooks and pages can branch on 404 vs 400 vs 500.

Every backend endpoint has one exported function:
`getHealth`, `listSecurities`, `getSecurity`, `getPrices`, `getFeatures`,
`getSnapshot`, `getIndicesSnapshot`, `getMovers`.

### `frontend/src/api/hooks.js` (frozen)

One hook per endpoint, all built on `useQuery`. `staleTime` = 60 s.
`enabled` guards prevent firing before a ticker is known. Stable
`queryKeys` object for future invalidation.

### `frontend/src/main.jsx` (frozen)

`QueryClientProvider` + `BrowserRouter` with both v7 future flags
enabled (`v7_startTransition`, `v7_relativeSplatPath`) — this silences
the deprecation warnings React Router prints by default.

### `frontend/src/App.jsx` (frozen)

Two routes wrapped in `<Layout>`:
- `/` → `Home`
- `/stock/:ticker` → `Stock`
- `*` → redirect to `/`

### `frontend/src/components/Layout.jsx` (frozen)

Top bar (sticky, backdrop-blur), main outlet at max-width 6xl, footer.
Search component mounts in the top bar.

### `frontend/src/components/Search.jsx` (frozen)

- Focus/type opens the dropdown
- Filters the 50 securities client-side (symbol, ticker, name, sector)
- Max 8 matches shown
- Keyboard: ↑ / ↓ move highlight, Enter selects, Esc closes
- Click-outside closes
- Empty state: "No matches for X"
- Selecting navigates to `/stock/<ticker>` and clears the input

### `frontend/src/components/MarketStrip.jsx` (frozen)

Three cards via `useIndicesSnapshot()`. Renders loading skeleton,
error message, or the real close + change with green/red tone and
arrow glyphs.

### `frontend/src/components/TopMovers.jsx` (frozen)

Two-column grid of `limit` movers via `useMovers(limit)`. Each card
is a `<Link>` to `/stock/<ticker>`. Loading skeleton, error message.

### `frontend/src/pages/Home.jsx` (frozen)

Composes the three sections: heading, MarketStrip, TopMovers,
market-summary placeholder.

### `frontend/src/pages/Stock.jsx` (frozen)

Snapshot-driven header. Handles:
- Loading — three skeleton blocks
- 404 — distinct red box with hint about ticker format
- Other errors — generic red box
- Success — symbol/name/sector line, big price + change, OHLC card

Volume formatting uses Indian notation: `L` (lakh), `Cr` (crore).

---

## 4. Verification results

**Backend smoke test (Chunk A):**

```
NIFTY 50     close=23346.40  chg=+0.33%
BANK NIFTY   close=56358.70  chg=+0.54%
INDIA VIX    close=   11.39  chg=-7.32%
ALL OK

sorted by |% change| desc: ok
  ADANIPORTS   +4.93%  close=1824.00
  DRREDDY      +3.95%  close=1185.00
  TCS          -3.88%  close=2105.00
  TMPV         -3.40%  close= 303.80
  BAJFINANCE   +3.39%  close=1040.30
ALL OK

limit=0  -> 422
limit=99 -> 422

movers first : 0.035212s
movers second: 0.002189s
```

**Frontend client integration test (Chunk C):**

All 9 client functions return valid data. `getSecurity('NOPE.NS')`
throws an error with `.status === 404`; `getPrices('TCS.NS', '42y')`
throws with `.status === 400`.

**Build (Chunk E, F, G):**

```
✓ 87 modules transformed
dist/index.html                   0.40 kB
dist/assets/index-*.css          ~11 kB
dist/assets/index-*.js          ~211 kB
✓ built in ~2.2s
```

No warnings, no errors.

**UI walkthrough:** home page renders all three sections with live data;
search autocompletes, keyboard-navigates, and routes; stock page renders
TCS and Reliance snapshots correctly with Indian-notation volume.

---

## 5. Example responses (frozen reference)

`GET /api/indices/snapshot`:

```json
{
  "as_of": "2026-09-18",
  "indices": [
    { "symbol": "^NSEI",    "name": "NIFTY 50",   "as_of": "2026-09-18",
      "close": 23346.4,  "change_1d": 75.8008,  "change_1d_pct": 0.3257 },
    { "symbol": "^NSEBANK", "name": "BANK NIFTY", "as_of": "2026-09-18",
      "close": 56358.7,  "change_1d": 302.9492, "change_1d_pct": 0.5404 },
    { "symbol": "^INDIAVIX","name": "INDIA VIX",  "as_of": "2026-09-18",
      "close": 11.39,    "change_1d": -0.9,     "change_1d_pct": -7.323 }
  ]
}
```

`GET /api/movers?limit=5`:

```json
{
  "as_of": "2026-09-18",
  "count": 5,
  "movers": [
    { "ticker": "ADANIPORTS.NS", "symbol": "ADANIPORTS",
      "name": "Adani Ports & SEZ", "sector": "Infrastructure",
      "close": 1824.0, "change_1d_pct": 4.9301, "volume": 4148803 },
    ...
  ]
}
```

---

## 6. Repository deltas since Stage 3

**Backend — added:**

```
backend/app/api/routes/indices.py
backend/app/api/routes/movers.py
```

**Backend — modified:**

```
backend/app/api/schemas.py   (appended 4 models)
backend/app/api/router.py    (added 2 includes)
```

**Frontend — added:**

```
frontend/src/api/client.js
frontend/src/api/hooks.js
frontend/src/components/Layout.jsx
frontend/src/components/Search.jsx
frontend/src/components/MarketStrip.jsx
frontend/src/components/TopMovers.jsx
```

**Frontend — modified:**

```
frontend/package.json         (added react-router-dom, react-query)
frontend/src/main.jsx         (providers + router future flags)
frontend/src/App.jsx          (real routes)
frontend/src/pages/Home.jsx   (full implementation)
frontend/src/pages/Stock.jsx  (snapshot-driven)
```

**Docs — added:**

```
docs/STAGE_04.md
```

**No changes** to any Stage 0/1/2/3 file outside the two router
includes and the four schema appends. `pipeline/features.py`,
`providers/`, `db/models.py`, all ingest scripts, and all previously
shipped schemas are byte-identical.

---

## 7. Known limitations going into Stage 5

- Search filters client-side over the full 50-security list already
  loaded by the top bar. If the universe grows past ~500 securities,
  switch to a backend search endpoint.
- No debouncing on search — with 50 rows, immediate filtering is faster
  than debounce overhead.
- `/api/movers` only looks at the most recent date where
  `features_daily` has rows for every security. If a future refresh
  leaves one ticker missing, it silently excludes that ticker for the
  day. Fine for now; monitor during Stage 11 scheduler work.
- Stock page shows only the snapshot. No chart, no fundamentals, no
  news, no forecast panels. All placeholders point to their stages.
- No error boundary at the app level. If a component throws, React
  unmounts the tree. Stage 12 adds one.
- No dark/light theme toggle. Single dark theme.
- Bundle size ~211 kB gzipped ~67 kB. Acceptable. Stage 5 adds
  lightweight-charts (~45 kB gzip). Monitor after that.
- Mobile responsiveness is basic (single-column stacking under `sm`
  breakpoint). Real mobile polish is Stage 12.
- No favicon yet.
- No `<title>` updates per route. Both pages say "Quantpulse".

---

## 8. Next stage entry point — Stage 5

**Stage 5 — Stock Page Core + 5-Year Chart**

The stock page becomes the real product surface.

Components to add:

1. **`PriceChart.jsx`** using `lightweight-charts` (TradingView's OSS
   library, ~45 kB gzip). Candlestick or area chart with volume pane.
2. **Timeframe switcher**: `1D | 1W | 1M | 6M | 1Y | 3Y | 5Y | MAX`.
   Note: "1D" means "one day, intraday" — we don't have intraday data,
   so we'll ship `1M | 3M | 6M | 1Y | 3Y | 5Y | MAX` and add `1D` in a
   later stage if intraday becomes available.
3. **Performance narrative** — "How is this stock doing?" section, v1
   rule-based. Reads a small set of latest features (RSI, px_over_sma_50,
   px_over_sma_200, vol_20d) and generates a paragraph. No LLM.
4. **Stats row** — extended: adds 20-day return, 52-week high/low,
   distance from 52w high, average volume.
5. **Layout polish** — the stock page becomes a real research page:
   header, chart, narrative, stats grid, placeholders for risk/news/
   forecast.

**New backend endpoint(s):**

- `GET /api/securities/{ticker}/stats` — computed on the fly from
  `prices_daily`: 52w high/low, 52w range position, avg volume (20d,
  60d), YTD return, all-time high/low since 2021-09-16.

No model, no news, no forecast. Just richer read access.

Out of scope for Stage 5: fundamentals (Stage 6), news (Stage 7),
forecast (Stage 8), risk (Stage 9), explanations (Stage 10).

Deliverable: a real stock page with an interactive 5-year chart, a
timeframe switcher, and a rule-based performance paragraph.

---

## 9. Handoff prompt for the next chat

Copy this into a new conversation:

> Context: I'm building **Quantpulse**. Repo at `~/IDE/quantpulse`.
> Read `docs/architecture_handoff.md` and `docs/STAGE_01.md` through
> `docs/STAGE_04.md` — all in my repo — before starting. Then begin
> **Stage 5 — Stock Page Core + 5-Year Chart** exactly as scoped in
> section 8 of `docs/STAGE_04.md`.
>
> Environment: MacBook Air 2015, Intel i5, 8 GB RAM, Zorin OS 16
> (XFCE). Python 3.12.14 in `~/IDE/quantpulse/.venv` managed by `uv`.
> Node 20 + npm. Backend on `127.0.0.1:8000`, Vite on `localhost:5173`
> proxying `/api/*` to the backend.
>
> Rules: plan first, full-file replacements only, one test per chunk,
> no debug cycles, hand off as `docs/STAGE_05.md`.

---
