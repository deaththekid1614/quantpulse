# Stage 01 — Data Provider Layer + Stock Universe

**Status:** ✅ complete
**Completed:** 2026-09-20
**Repo:** `~/IDE/quantpulse`
**Depends on:** Stage 0
**Supersedes:** nothing

---

## 1. What this stage delivered

A working, idempotent pipeline that pulls 5 years of daily OHLCV for
India's Nifty 50 index constituents from Yahoo Finance into SQLite. This
is the foundation every later stage reads from.

Concretely:

- Python 3.12 environment managed by `uv`, isolated from system Python 3.8
- Rewritten `Makefile` + `backend/requirements.txt` using `uv pip`
- Frozen `data/universe.json` — 50 securities with symbol, Yahoo ticker,
  name, sector
- Provider interface layer (`providers/base.py`) — abstract classes +
  value objects + error hierarchy
- Yahoo Finance implementation (`providers/yahoo.py`) — returns a
  DataFrame with a strict, canonical schema
- SQLAlchemy database layer (`db/session.py`, `db/models.py`) — three
  tables: `securities`, `prices_daily`, `ingest_log`
- Ingestion CLI (`scripts/ingest_prices.py`) — single-ticker and
  full-universe modes, idempotent upserts, per-ticker error isolation
- Populated DB: **50 securities**, **62,138 daily price rows**, covering
  **2021-09-16 → 2026-09-18**

---

## 2. Environment

**Interpreter:** Python 3.12.14 (managed by `uv`, installed to
`~/.local/share/uv/python/`). System Python remains 3.8.10 — untouched.

**Virtualenv:** `~/IDE/quantpulse/.venv` (Python 3.12.14). Gitignored.

**`uv` version:** 0.12.17.

**Install flow used:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
cd ~/IDE/quantpulse && uv venv --python 3.12
make setup-backend   # runs:  uv pip install -r backend/requirements.txt
```

**Why not system Python 3.8 or deadsnakes 3.9/3.10:** 3.8 is EOL,
deadsnakes no longer publishes 3.11+ for focal, and 3.9/3.10 would force
`numpy<2` pins across the whole project. `uv` ships prebuilt 3.12 with no
compile and no shell changes.

---

## 3. Locked files

### `backend/requirements.txt` (final)

```
fastapi>=0.115,<1
uvicorn[standard]>=0.32,<1
python-dotenv>=1.0,<2
pydantic>=2.9,<3
pydantic-settings>=2.6,<3
SQLAlchemy>=2.0,<3
pandas>=2.2,<3
numpy>=1.26,<3
yfinance>=0.2.50,<1
requests>=2.32,<3
```

Installed versions confirmed:
`fastapi 0.141.1`, `sqlalchemy 2.0.54`, `pydantic 2.13.5`,
`pandas 2.3.3`, `numpy 2.5.3`, `yfinance 0.2.66`, `requests 2.34.2`.

### `Makefile` (final)

Targets: `help`, `setup`, `setup-backend`, `setup-frontend`,
`run-backend`, `run-frontend`, `clean`. Uses `.venv/bin/uvicorn` to run
the API; `uv pip install` for dependencies.

### `data/universe.json` (frozen)

50 entries. Sectors used: Automobile, Cement, Consumer Goods, Energy,
Financial Services, Healthcare, Information Technology, Infrastructure,
Metals, Power, Telecom.

Two corrections were made during Stage 1 due to real corporate events:

| Original | Corrected | Reason |
|---|---|---|
| `LTIM` / `LTIM.NS` | `LTM` / `LTM.NS` | NSE renamed LTIMindtree symbol LTIM → LTM on 2026-02-27; Yahoo followed |
| `TATAMOTORS` / `TATAMOTORS.NS` | `TMPV` / `TMPV.NS` | Tata Motors demerged in late 2025; passenger-vehicle entity renamed TMPV, stayed in Nifty 50. CV spinoff (TMCV) is a new listing and not an index constituent. |

Both renamed tickers retain full ~5-year price history under the new
symbols (same legal entity / ISIN).

The file is frozen. It changes only if Nifty 50 itself is reconstituted.

### `backend/app/providers/base.py` (frozen)

Interfaces:

- `MarketDataProvider.get_daily_ohlcv(ticker, start, end) -> DataFrame`
- `NewsProvider.get_news(ticker, since, limit) -> list[NewsArticle]`
- `FundamentalsProvider.get_fundamentals(ticker) -> Fundamentals`

Value objects: `NewsArticle`, `Fundamentals`.

Errors: `ProviderError`, `ProviderUnavailable`, `TickerNotFound`.

Constants: `OHLCV_COLUMNS = ("open","high","low","close","volume")`,
`OHLCV_INDEX_NAME = "date"`.

### `backend/app/providers/yahoo.py` (frozen)

`YahooMarketDataProvider.get_daily_ohlcv` contract:

- Index: `DatetimeIndex(name="date", tz=None, monotonic ASC)`
- Columns: exactly `OHLCV_COLUMNS`, in order
- dtypes: OHLC `float64`, volume `int64`
- Empty input range or delisted ticker → **empty DataFrame with the same
  schema** (never raises on no-data)
- Unrecoverable failure → `ProviderUnavailable` or `ProviderError`
- `auto_adjust=True` (split/dividend adjusted)

### `backend/app/db/session.py` (frozen)

- SQLite at `<repo>/data/quantpulse.db`
- WAL mode, foreign keys on, `synchronous=NORMAL`
- `Base` declarative base, `SessionLocal` factory
- `init_db()` — idempotent `create_all`
- `session_scope()` — context manager with commit/rollback/close
- `db_file_path()` — convenience accessor

### `backend/app/db/models.py` (frozen for Stage 1 tables)

**`securities`** — `id`, `ticker` (unique), `symbol`, `name`, `sector`,
`created_at`

**`prices_daily`** — `id`, `security_id` FK→securities (cascade delete),
`date`, `open`, `high`, `low`, `close`, `volume`. Unique constraint on
`(security_id, date)` plus an index on the same pair.

**`ingest_log`** — `id`, `ticker`, `rows_added`, `rows_updated`,
`status` (`running` | `ok` | `error`), `error`, `started_at`,
`finished_at`

Future stages append new tables. Existing tables are never rewritten.

### `backend/scripts/ingest_prices.py` (frozen)

CLI:

```bash
.venv/bin/python backend/scripts/ingest_prices.py --ticker TCS.NS --years 5
.venv/bin/python backend/scripts/ingest_prices.py --universe nifty50 --years 5
```

Behaviour:

- Upserts `securities` from `universe.json` metadata
- Fetches OHLCV in a single yfinance call per ticker
- Upserts `prices_daily` via `INSERT ... ON CONFLICT (security_id, date) DO UPDATE`
- Writes a row to `ingest_log` for every ticker, success or failure
- One ticker's failure does not abort the batch
- Batches inserts at 500 rows per statement

---

## 4. Verification results

**Schema check (Chunk E):**

```
db path: /home/death-kid/IDE/quantpulse/data/quantpulse.db
tables : ['ingest_log', 'prices_daily', 'securities']
init_db idempotent: ok
```

**Provider check (Chunk F):**

```
shape       : (7, 5)
index name  : date
index tz    : None
monotonic   : True
columns     : ('open','high','low','close','volume')
dtypes      : open/high/low/close float64, volume int64
empty-range OK: (0, 5)
bad-ticker  OK: (0, 5)
```

**Idempotency check (Chunk G1c):**

Second consecutive run for `TCS.NS`:

```
TCS.NS   +0  ~1243
rows after re-run: 1243
```

No duplicates. Upsert works.

**Full-universe ingest (Chunk G2):**

```
tickers       : 50
rows added    : 58409
rows updated  : 1243
tickers w/ 0  : 2   (LTIM.NS, TATAMOTORS.NS — both later fixed)
Done in       : 30.7s
```

**Post-correction state (final):**

```
securities : 50
price rows : 62138

lowest 3 :
  BAJAJ-AUTO.NS   1242
  BAJAJFINSV.NS   1242
  BAJFINANCE.NS   1242
highest 3:
  TMPV.NS         1243
  ULTRACEMCO.NS   1243
  WIPRO.NS        1243
```

Row count per ticker: 1242–1243 (5 years of NSE trading days). TMPV and
LTM both back-fill the full history under their new symbols.

Date range covered: **2021-09-16 → 2026-09-18**.

---

## 5. How to run it (frozen reference)

First time:

```bash
cd ~/IDE/quantpulse
cp .env.example .env          # if not already done
make setup-backend
make setup-frontend
```

Ingest (re-runnable any time):

```bash
# single ticker
.venv/bin/python backend/scripts/ingest_prices.py --ticker RELIANCE.NS --years 5

# full universe
.venv/bin/python backend/scripts/ingest_prices.py --universe nifty50 --years 5
```

API still works from Stage 0:

```bash
make run-backend
curl http://127.0.0.1:8000/api/health
```

---

## 6. Repository deltas since Stage 0

**Added:**

```
backend/app/providers/base.py
backend/app/providers/yahoo.py
backend/app/db/session.py
backend/app/db/models.py
backend/scripts/ingest_prices.py
data/universe.json
data/quantpulse.db            (gitignored)
```

**Modified:**

```
Makefile                      (uv-based; venv now at repo root)
backend/requirements.txt      (rewritten for 3.12)
.gitignore                    (adds data/*.sqlite, .venv variants)
```

**Deleted:**

```
backend/.venv/                (Stage 0's stale Python 3.8 venv)
```

---

## 7. Known limitations going into Stage 2

- `prices_daily` has no NaN rows, but a handful of tickers have 1242
  instead of 1243 days (single-day gaps in Yahoo's feed). This is normal
  and does not affect feature engineering — forward-fill will handle it
  where it matters.
- Only close prices are split/dividend adjusted. OHLC all adjusted
  consistently because `auto_adjust=True`.
- Yahoo's EOD data for a given trading day is typically available by
  ~18:00 IST. The Stage 11 scheduler must not run ingestion before then.
- No `Nifty 50 index` row yet — market-context features in Stage 2 will
  need `^NSEI` and `^NSEBANK` added to the universe, or fetched
  separately by the feature engine. Decision deferred to Stage 2.
- `securities.sector` for `LTM` and `TMPV` was written correctly on the
  final full-universe run.
- No tests yet — Stage 12 adds the pytest suite.
- Git history is a single commit for this stage; granular commits are
  not required by the workflow.

---

## 8. Next stage entry point — Stage 2

**Stage 2 — Feature Engine**

Reads `prices_daily`, writes a new table `features_daily` with:

- Returns: 1d, 5d, 20d (simple and log)
- Volatility: rolling std (20d), ATR (14d)
- Moving averages: SMA 20/50/200, EMA 12/26, and price vs each
- Momentum: RSI(14), MACD(12,26,9), ROC(10)
- Volume features: relative volume (vs 20d avg), volume z-score
- Market context: needs Nifty 50 index history — either add `^NSEI` to
  the universe or fetch it inside the feature engine. Decide at the top
  of Stage 2.
- Sector context: average return of the ticker's sector peers on the
  same day
- Beta: 60-day rolling beta vs Nifty

All features computed vectorised with pandas. Persisted via SQLAlchemy
upsert on `(security_id, date)`. CLI at
`backend/scripts/build_features.py` with `--ticker` and `--universe`
modes.

Out of scope for Stage 2: ML, NLP, news, forecasts, explanations,
frontend changes.

Deliverable: `data/quantpulse.db` gains a populated `features_daily`
table for all 50 tickers, plus `docs/STAGE_02.md` handoff with feature
distributions and sample rows.

---

## 9. Handoff prompt for the next chat

Copy this into a new conversation:

> Context: I'm building **Quantpulse**. Repo at `~/IDE/quantpulse`.
> Read `docs/architecture_handoff.md` (full architecture and stage plan)
> and `docs/STAGE_01.md` (Stage 1 completion state) — both are in my
> repo. Then begin **Stage 2 — Feature Engine** exactly as scoped in
> section 8 of `docs/STAGE_01.md`.
>
> Environment: MacBook Air 2015, Intel i5, 8 GB RAM, Zorin OS 16
> (XFCE). Python 3.12.14 in `~/IDE/quantpulse/.venv` managed by `uv`.
> System Python untouched at 3.8.10. `make setup-backend` installs
> dependencies.
>
> Rule: plan first, one file at a time, test every file, no debug
> cycles. Hand off as `docs/STAGE_02.md`.

---
