# Quantpulse — Architecture & Handoff

**Project:** Quantpulse — Post-Market Intelligence & Forecasting Platform
**Repo:** `~/IDE/quantpulse`
**Machine:** MacBook Air 2015, Intel i5 (dual-core), 8 GB RAM, Zorin OS (XFCE)
**Status:** Stage 0 ✅ complete — foundation skeleton verified working
**Last updated:** 2026-09-19

---

## 1. Product in one paragraph

Quantpulse is not an AI dashboard and not a live-trading tool. It is a
**post-market research system**: after each NSE session closes (3:30 PM IST),
it collects the day's price + volume + news data for a fixed universe of
Indian equities, computes features, runs an ML/NLP pipeline, and publishes
per-ticker pages containing — a 5-year interactive chart, plain-English
performance narrative, risk assessment, news + sentiment, and probabilistic
7/15/30-day forecasts with explanations. One analysis is generated once per
session and served to many users. The system never claims to know the
future — it produces probability distributions and expected ranges, and
always shows its evidence.

---

## 2. Non-negotiable design principles

1. **Batch, not streaming.** The heavy pipeline runs once per day after
   market close. The API reads precomputed rows from SQLite. No user click
   ever triggers an LSTM.
2. **Probabilistic output, never point predictions.** Forecasts are direction
   probabilities + expected ranges, calibrated on a backtest.
3. **Every number has an explanation.** Raw indicators are never shown
   alone — a natural-language layer wraps every metric.
4. **Provider abstraction.** Data sources (Yahoo, news, fundamentals) sit
   behind interfaces so a source swap touches one file, not the codebase.
5. **Train remotely, infer locally.** LSTM/GRU training runs on free Colab
   GPU; only ONNX weights are committed. Your laptop only does inference.
6. **Honest UI.** No glowing circles, no "AI magic", no fake precision.
   Bloomberg-style information density with modern consumer polish.
7. **No Docker, no cloud bill.** SQLite + venv + Vite. Runs entirely on the
   laptop.

---

## 3. High-level architecture

```
                    ┌───────────────────────────────┐
                    │        EXTERNAL SOURCES       │
                    │  Yahoo Finance · News RSS ·   │
                    │  Fundamentals · NSE cal       │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                ┌──────────────────────────────────────┐
                │        DATA PROVIDER LAYER           │
                │  base.py · yahoo.py · news.py ·      │
                │  fundamentals.py                     │
                └───────────────┬──────────────────────┘
                                │
                                ▼
                ┌──────────────────────────────────────┐
                │   INGESTION & VALIDATION PIPELINE    │
                │  scrape → clean → dedupe → store     │
                └───────────────┬──────────────────────┘
                                │
                                ▼
                ┌──────────────────────────────────────┐
                │           SQLite (quantpulse.db)     │
                │  securities · prices_daily ·         │
                │  features_daily · news_articles ·    │
                │  forecasts · risk_scores ·           │
                │  explanations · analysis_runs        │
                └───────────────┬──────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│ FEATURE ENGINE│      │  NLP ENGINE   │      │  RISK ENGINE  │
│ returns, vol, │      │ VADER + FinBERT│     │ volatility,   │
│ MA, momentum, │      │ relevance,     │     │ drawdown,     │
│ market ctx    │      │ importance     │     │ beta, stress  │
└───────┬───────┘      └───────┬───────┘      └───────┬───────┘
        │                      │                      │
        ▼                      ▼                      │
┌───────────────┐      ┌───────────────┐              │
│ FORECAST ENGINE│◄────│  NEWS SIGNAL  │              │
│ ARIMA + LGBM  │      └───────────────┘              │
│ + LSTM (ONNX) │                                     │
│ → distributions│                                    │
└───────┬───────┘                                     │
        │                                             │
        └──────────────────┬──────────────────────────┘
                           ▼
                ┌──────────────────────────┐
                │   EXPLANATION ENGINE     │
                │  template NLG + attrib.  │
                └─────────────┬────────────┘
                              │
                              ▼
                ┌──────────────────────────┐
                │   FastAPI  (read-only)   │
                │  /api/securities/...     │
                └─────────────┬────────────┘
                              │
                              ▼
                ┌──────────────────────────┐
                │  React + Vite frontend   │
                │  Home · Stock Page       │
                └──────────────────────────┘

         All of the above triggered by APScheduler
         after NSE close (15:45 → 17:00 IST).
```

---

## 4. Daily lifecycle (target end state)

| Time (IST) | Job | Output |
|---|---|---|
| 15:45 | Ingest EOD prices | `prices_daily` rows |
| 15:50 | Compute features | `features_daily` rows |
| 16:00 | Fetch news | `news_articles` rows |
| 16:15 | Run NLP | sentiment/relevance/importance columns populated |
| 16:30 | Forecast + risk | `forecasts`, `risk_scores` rows |
| 16:45 | Generate explanations | `explanations` rows |
| 17:00 | Mark analysis ready | `analysis_runs.status = 'ready'` |

Frontend reads only from the API. The API reads only from SQLite.

---

## 5. Repository structure (as built)

```
quantpulse/
├── .env                       (gitignored, local only)
├── .env.example               ✅ committed
├── .gitignore                 ✅ committed
├── Makefile                   ✅ setup/run/clean targets
├── README.md                  ✅ committed
├── data/
│   ├── .gitkeep               ✅
│   └── quantpulse.db          (created at Stage 1)
├── docs/
│   ├── architecture_handoff.md  ← this file
│   └── STAGE_00.md … STAGE_12.md (per-stage handoffs)
├── backend/
│   ├── requirements.txt       ✅ minimal (FastAPI + uvicorn + dotenv)
│   ├── .venv/                 (gitignored)
│   ├── app/
│   │   ├── __init__.py        ✅
│   │   ├── main.py            ✅ FastAPI factory + CORS + /api mount
│   │   ├── core/
│   │   │   ├── __init__.py    ✅
│   │   │   ├── config.py      ✅ Settings + get_settings() (cached)
│   │   │   └── log_config.py  ✅ setup_logging() + get_logger()
│   │   ├── api/
│   │   │   ├── __init__.py    ✅
│   │   │   ├── router.py      ✅ aggregates sub-routers under /api
│   │   │   └── routes/
│   │   │       ├── __init__.py  ✅
│   │   │       └── health.py    ✅ GET /api/health
│   │   ├── db/                (empty — Stage 1)
│   │   ├── providers/         (empty — Stage 1)
│   │   ├── pipeline/          (empty — Stage 2)
│   │   ├── ml/                (empty — Stage 8)
│   │   ├── nlp/               (empty — Stage 7)
│   │   ├── explain/           (empty — Stage 10)
│   │   └── scheduler/         (empty — Stage 11)
│   ├── models_artifacts/
│   │   └── .gitkeep           ✅ (ONNX weights land here, gitignored)
│   ├── scripts/
│   │   └── .gitkeep           ✅ (CLI entrypoints, e.g. ingest_prices.py)
│   └── tests/
│       └── __init__.py        ✅
└── frontend/
    ├── package.json           ✅ React 18 + Vite 5 + Tailwind 3
    ├── vite.config.js         ✅ proxies /api → :8000
    ├── tailwind.config.js     ✅ ink.* + accent.* design tokens
    ├── postcss.config.js      ✅
    ├── index.html             ✅
    └── src/
        ├── main.jsx           ✅
        ├── App.jsx            ✅ fetches /api/health, shows status
        ├── styles/index.css   ✅ Tailwind + dark base
        ├── api/               (empty)
        ├── pages/             (empty)
        ├── components/        (empty)
        └── charts/            (empty)
```

---

## 6. Locked tech stack

**Backend**
- Python 3.11 (target — upgrade via `pyenv` in Stage 1; system 3.8 stays
  for other projects)
- FastAPI + Uvicorn
- SQLite via SQLAlchemy
- pandas, numpy, pandas-ta (Stage 2)
- yfinance, feedparser (Stage 1 / 7)
- APScheduler (Stage 11)
- pytest (Stage 12)

**ML / NLP**
- scikit-learn (baselines)
- PyTorch for LSTM/GRU — **training on Colab GPU only**
- ONNX Runtime for local CPU inference
- VADER (baseline sentiment) → FinBERT-ONNX (upgrade) — Stage 7
- SHAP-lite feature attribution — Stage 10

**Frontend**
- React 18 + Vite 5
- TailwindCSS 3 (dark, information-dense)
- lightweight-charts (TradingView OSS) — Stage 5
- Recharts for secondary viz — Stage 5
- React Query — Stage 4

**Dev / Ops**
- Git + GitHub
- `pyenv` for Python version management (Stage 1)
- `venv` per project
- `Makefile` for common commands
- `.env` for config (never committed)

**Explicitly NOT used:** Docker, Kubernetes, Postgres, Redis, cloud VMs,
any paid API.

---

## 7. Stage plan (13 stages, one chat each)

| Stage | Title | Status | Depends on |
|---|---|---|---|
| 00 | Foundations | ✅ done | — |
| 01 | Data Provider Layer + Stock Universe | ⏳ next | 00 |
| 02 | Feature Engine | pending | 01 |
| 03 | Backend API Core | pending | 02 |
| 04 | Frontend Foundation + Home + Search | pending | 03 |
| 05 | Stock Page Core + 5-Year Chart | pending | 04 |
| 06 | Fundamentals + Company Info | pending | 05 |
| 07 | News Pipeline + NLP | pending | 06 |
| 08 | Forecasting Engine (ARIMA + LGBM + LSTM/ONNX) | pending | 07 |
| 09 | Risk Engine + Stress Detection | pending | 08 |
| 10 | Explanation Engine (NLG) | pending | 09 |
| 11 | Post-Market Batch Pipeline (APScheduler) | pending | 10 |
| 12 | Testing, Hardening, Deployment | pending | 11 |

Rule: **no stage starts before the previous stage's handoff is verified.**

---

## 8. Stage 0 — what was actually built

### Deliverables
- Full directory skeleton under `~/IDE/quantpulse`
- FastAPI backend with:
  - `create_app()` factory pattern
  - CORS restricted to `FRONTEND_ORIGIN` (default `http://localhost:5173`)
  - Routers mounted under `/api`
  - `GET /` → identity JSON
  - `GET /api/health` → `{status, service, timestamp}`
  - Auto docs at `/docs`
- Config layer: `Settings` frozen dataclass + `get_settings()` (LRU-cached),
  reads `.env` from repo root via `python-dotenv`
- Logging layer: `setup_logging()` (idempotent) + `get_logger()`
- Frontend: React 18 + Vite + Tailwind with a custom dark palette
  (`ink.900–200`, `accent.{DEFAULT,up,down}`), tabular numerals enabled
  globally
- Vite dev server proxies `/api/*` → `http://127.0.0.1:8000`
- App.jsx fetches `/api/health` on mount and renders `backend: ok` in
  green
- Root tooling: `.gitignore`, `.env.example`, `README.md`, `Makefile`
- Git initialised; Stage 0 committed

### Verification (all passed on 2026-09-19)
- `curl http://127.0.0.1:8000/api/health` → `{"status":"ok",...}`
- `http://127.0.0.1:8000/docs` → Swagger UI renders
- `http://localhost:5173` → "Quantpulse" + green `backend: ok`
- `git status` → clean; `.env` not tracked

### Files created in Stage 0
```
.gitignore
.env.example
README.md
Makefile
docs/architecture_handoff.md   (this file)
backend/requirements.txt
backend/app/__init__.py
backend/app/main.py
backend/app/core/__init__.py
backend/app/core/config.py
backend/app/core/log_config.py
backend/app/api/__init__.py
backend/app/api/router.py
backend/app/api/routes/__init__.py
backend/app/api/routes/health.py
backend/db/__init__.py … (all package markers)
backend/scripts/.gitkeep
backend/models_artifacts/.gitkeep
backend/tests/__init__.py
frontend/package.json
frontend/vite.config.js
frontend/tailwind.config.js
frontend/postcss.config.js
frontend/index.html
frontend/src/main.jsx
frontend/src/App.jsx
frontend/src/styles/index.css
data/.gitkeep
```

### Known limitations going into Stage 1
- Python is still system 3.8.10 — will be upgraded via `pyenv` in Stage 1
  without touching system Python
- `requirements.txt` intentionally minimal — expands at Stage 1
- No database file yet (`data/quantpulse.db` appears in Stage 1)
- No routing on the frontend yet (single `App.jsx`) — Router arrives Stage 4
- `backend/app/db/`, `providers/`, `pipeline/`, `ml/`, `nlp/`, `explain/`,
  `scheduler/` are empty placeholders awaiting their stages

---

## 9. Run commands (memorise these)

From `~/IDE/quantpulse`:

```bash
# First time only
cp .env.example .env
make setup-backend
make setup-frontend

# Every dev session — two terminals
make run-backend    # → http://127.0.0.1:8000
make run-frontend   # → http://localhost:5173
```

Health check: `curl http://127.0.0.1:8000/api/health`

---

## 10. Next stage entry point

**Stage 1 — Data Provider Layer + Stock Universe**

Scope:
1. Install `pyenv`, install Python 3.11.9, write `.python-version` at repo
   root pinning 3.11.9. Rebuild `backend/.venv` on 3.11. Confirm system
   Python 3.8 remains the default for other projects (`python3 --version`
   outside the repo still says 3.8.x).
2. Rewrite `backend/requirements.txt` for 3.11: `fastapi`, `uvicorn[standard]`,
   `python-dotenv`, `sqlalchemy`, `pandas`, `numpy`, `yfinance`, `requests`,
   `pydantic`, `pydantic-settings`.
3. `backend/app/providers/base.py` — abstract `MarketDataProvider`,
   `NewsProvider`, `FundamentalsProvider` (Protocol or ABC).
4. `backend/app/providers/yahoo.py` — `YahooMarketDataProvider` implementing
   `MarketDataProvider` via `yfinance`.
5. `data/universe.json` — Nifty 50 tickers with Yahoo symbols (`.NS` suffix)
   plus name + sector.
6. `backend/app/db/session.py` — SQLAlchemy engine + `SessionLocal` +
   `Base`.
7. `backend/app/db/models.py` — `Security`, `PriceDaily`, `IngestLog`
   ORM models with indexes on `(security_id, date)`.
8. `backend/scripts/ingest_prices.py` — idempotent CLI:
   `python -m backend.scripts.ingest_prices --ticker TCS.NS --years 5`
   and `--universe nifty50`. Uses `INSERT ... ON CONFLICT DO UPDATE`.
9. Create SQLite schema on first run (via `Base.metadata.create_all`).
10. Populate `data/quantpulse.db` with ~5 years of daily OHLCV for `TCS.NS`,
    then the full Nifty 50.
11. Produce `docs/STAGE_01.md` handoff.

Out of scope for Stage 1: features, ML, NLP, news, API endpoints beyond
health, any frontend changes.

Deliverable: `data/quantpulse.db` with a populated `prices_daily` table
for all Nifty 50 tickers, plus row counts and a sample query output in the
handoff.

---

## 11. How to use this file in a new chat

Start every new stage chat with:

> Context: I'm building **Quantpulse**. The full architecture, structure,
> and stage plan are in `docs/architecture_handoff.md` at my repo root —
> read that first. Then begin **Stage N**.

The assistant reads this file, sees the exact current state, and continues
without needing the previous chat's history.

---
