# Stage 03 — Backend API Core

**Status:** ✅ complete
**Completed:** 2026-09-20
**Repo:** `~/IDE/quantpulse`
**Depends on:** Stage 2
**Supersedes:** nothing

---

## 1. What this stage delivered

A read-only HTTP API over the three populated data layers
(`securities`, `prices_daily`, `features_daily`). Five endpoints, all
served from SQLite, all cached, all documented at `/docs`.

No ML, no NLP, no news, no explanations, no frontend. Those come later.

---

## 2. Endpoints (locked)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | Liveness (unchanged from Stage 0) |
| GET | `/api/securities` | All 50 securities with metadata |
| GET | `/api/securities/{ticker}` | One security's metadata |
| GET | `/api/securities/{ticker}/prices` | Daily OHLCV, `?range=1w\|1m\|3m\|6m\|1y\|3y\|5y\|max` |
| GET | `/api/securities/{ticker}/features` | Daily feature vector, same range param |
| GET | `/api/securities/{ticker}/snapshot` | Latest price + change + latest features |

- Default range is `1y`
- Invalid ticker → **404**
- Invalid range → **400**
- All responses are Pydantic v2 models (see `schemas.py`)

---

## 3. Locked files

### `backend/app/api/cache.py` (frozen)

Thread-safe in-memory TTL cache. Default TTL 60 s. Singleton via
`get_cache()`. Provides `get`, `set`, `clear`, `invalidate_prefix`.
Not persistent, cleared on restart.

### `backend/app/api/schemas.py` (frozen)

Pydantic v2 models: `SecurityOut`, `SecurityListOut`, `PriceBar`,
`PriceHistoryOut`, `FeatureRow`, `FeatureHistoryOut`, `LatestPrice`,
`SnapshotOut`, `ErrorOut`.

**Feature responses expose the feature vector as a dict keyed by column
name** — this lets future stages add new features without touching the
API layer.

### `backend/app/api/deps.py` (frozen)

- `get_db()` — request-scoped SQLAlchemy session
- `resolve_range(str) -> date | None` — range token → start date
- `RANGE_TO_DAYS` — the canonical range map
- `DEFAULT_RANGE = '1y'`

### `backend/app/api/routes/securities.py` (frozen)
### `backend/app/api/routes/prices.py` (frozen)
### `backend/app/api/routes/features.py` (frozen)
### `backend/app/api/routes/snapshot.py` (frozen)

Each route file is a small APIRouter with one or two endpoints.
Caching is per-resource-prefix:
- `securities:list`
- `security:{ticker}`
- `prices:{ticker}:{range}`
- `features:{ticker}:{range}`
- `snapshot:{ticker}`

### `backend/app/api/router.py` (frozen)

Aggregates all sub-routers under `/api`. Adding a new resource in a
future stage means one import and one `include_router` call.

---

## 4. Verification results

**End-to-end smoke test:** all five endpoints return expected status
codes and shapes. Error paths verified: 4 × 404 (unknown ticker on each
endpoint), 2 × 400 (bad range on prices/features).

**Coverage:** every one of the 50 securities returns a working
snapshot with a populated 24-field feature vector.

**Cache:** second call to any endpoint returns in **< 5 ms** (measured
1.7–3.0 ms across endpoints).

**Cross-checks:**
- `/snapshot`'s `change_1d` and `change_1d_pct` match a manual
  calculation from the last two bars of `/prices` to floating-point
  exactness.
- `/features` row count matches the DB count for TCS `max` range (1039).
- All feature vectors expose exactly 24 finite values.

**Swagger UI:** `/docs` shows five tag groups — `health`, `securities`,
`prices`, `features`, `snapshot` — with all 6 endpoints listed.

---

## 5. Example responses (frozen reference)

`GET /api/securities/TCS.NS/snapshot`:

```json
{
  "ticker": "TCS.NS",
  "symbol": "TCS",
  "name": "Tata Consultancy Services",
  "sector": "Information Technology",
  "as_of": "2026-09-18",
  "price": {
    "date": "2026-09-18",
    "open": 2177.199951171875,
    "high": 2177.300048828125,
    "low": 2101.199951171875,
    "close": 2105.0,
    "volume": 6875428
  },
  "change_1d": -85.0,
  "change_1d_pct": -3.8813,
  "features": { "... 24 keys ..." }
}
```

`GET /api/securities/TCS.NS/features?range=1y`:

```json
{
  "ticker": "TCS.NS",
  "symbol": "TCS",
  "name": "Tata Consultancy Services",
  "sector": "Information Technology",
  "range": "1y",
  "count": 245,
  "data": [
    { "date": "2025-09-22",
      "features": { "ret_1d": ..., "rsi_14": 44.5542, "beta_60d": 1.1827, ... } },
    ...
  ]
}
```

---

## 6. Repository deltas since Stage 2

**Added:**

```
backend/app/api/cache.py
backend/app/api/schemas.py
backend/app/api/deps.py
backend/app/api/routes/securities.py
backend/app/api/routes/prices.py
backend/app/api/routes/features.py
backend/app/api/routes/snapshot.py
docs/STAGE_03.md
```

**Modified:**

```
backend/app/api/router.py   (import + include all sub-routers)
```

**No changes** to any Stage 0/1/2 file. `deps.py` uses only the
existing `SessionLocal` from `db/session.py`.

---

## 7. Known limitations going into Stage 4

- Cache is process-local. Multiple uvicorn workers would each have
  their own copy. Fine for one worker — which is what `make run-backend`
  uses.
- No pagination on `/securities` or history endpoints. Ranges are
  bounded by the DB (max ~1243 rows per ticker), so responses are small.
  If we ever track 500+ securities or add intraday, add pagination then.
- `snapshot.features` will be empty if `features_daily` has no rows for
  a security. Currently unreachable — all 50 have features — but
  defensively handled in code, not asserted at the schema level.
- No rate limiting. Fine for localhost. Add at Stage 12 deployment.
- No authentication. Fine for a read-only public API. Decide at Stage 12.
- API returns ISO date strings (`"2026-09-18"`) — no timezone because
  the underlying data is daily bars.
- `snapshot.change_1d` is `None` if a security has only one price bar.
  Never happens with current data.

---

## 8. Next stage entry point — Stage 4

**Stage 4 — Frontend Foundation + Home + Search**

First real UI. Wire React to the live API. No stock page yet — just:

1. Layout shell: top bar with Quantpulse wordmark + search input.
2. Home page: three-section page.
   - **Market overview strip** — small card row showing the three
     indices fetched from a new `/api/indices/snapshot` endpoint we'll
     add in this stage (Nifty 50, Bank Nifty, India VIX with day change).
   - **Top movers** — grid of N securities by absolute 1-day %
     change, fetched from a new `/api/movers` endpoint added in this
     stage.
   - **Market summary placeholder** — a static block for now, filled
     by the Explanation Engine in Stage 10.
3. Search: autocomplete against `/api/securities`, keyboard-navigable,
   Enter routes to `/stock/:ticker`.
4. Routing: `/` (home), `/stock/:ticker` (placeholder page for now).
5. React Query for data fetching, with proper loading and error states.
6. Tailwind design tokens as established in Stage 0 (`ink.*`,
   `accent.*`).

**Two new backend endpoints required for Stage 4:**

- `GET /api/indices/snapshot` — latest bar + change for each of
  `^NSEI`, `^NSEBANK`, `^INDIAVIX`
- `GET /api/movers?limit=5` — top N by 1-day % change, using the
  `ret_1d` feature

These go in a new file `backend/app/api/routes/indices.py` and
`backend/app/api/routes/movers.py`, wired into `router.py`. Two new
schemas in `schemas.py` (append only — no edit to existing schemas).

Out of scope for Stage 4: stock page content, charts, fundamentals,
news, forecasts, risk, explanations.

Deliverable: a working home page + search that hits the live API.
Screenshots in `docs/STAGE_04.md`.

---

## 9. Handoff prompt for the next chat

Copy this into a new conversation:

> Context: I'm building **Quantpulse**. Repo at `~/IDE/quantpulse`.
> Read `docs/architecture_handoff.md`, `docs/STAGE_01.md`,
> `docs/STAGE_02.md`, and `docs/STAGE_03.md` — all in my repo — before
> starting. Then begin **Stage 4 — Frontend Foundation + Home + Search**
> exactly as scoped in section 8 of `docs/STAGE_03.md`.
>
> Environment: MacBook Air 2015, Intel i5, 8 GB RAM, Zorin OS 16
> (XFCE). Python 3.12.14 in `~/IDE/quantpulse/.venv` managed by `uv`.
> Node 20 + npm. Backend runs on `127.0.0.1:8000`, Vite proxies
> `/api/*` to it.
>
> Rules: plan first, full-file replacements only, one test per chunk,
> no debug cycles, hand off as `docs/STAGE_04.md`.

---
