# Quantpulse

**Post-Market Intelligence & Forecasting Platform.**

Quantpulse is not a live-trading tool and not an AI dashboard. It is a
post-market research system: after each NSE session closes (3:30 PM IST),
it collects the day's price, volume, and news data for a fixed universe
of Indian equities, computes features, runs an ML/NLP pipeline, and
publishes per-ticker pages containing a 5-year interactive chart, a
plain-English performance narrative, a risk assessment, news sentiment,
and probabilistic 7/15/30-day forecasts with explanations.

One analysis per session. Many users. No fake precision.

**Status:** Stage 1 complete — data pipeline and stock universe populated.
No ML, no news, no real UI yet.

---

## Design principles

1. **Batch, not streaming.** The heavy pipeline runs once per day after
   market close. The API reads precomputed rows from SQLite. No user
   click ever triggers a model.
2. **Probabilistic output, never point predictions.** Forecasts are
   direction probabilities and expected ranges, calibrated on a backtest.
3. **Every number has an explanation.** Raw indicators are never shown
   alone — a natural-language layer wraps every metric.
4. **Provider abstraction.** Data sources sit behind interfaces, so a
   source swap touches one file, not the codebase.
5. **Train remotely, infer locally.** LSTM/GRU training runs on free
   Colab GPU; only ONNX weights are committed. The laptop does inference.
6. **Honest UI.** No glowing circles, no "AI magic", no fake precision.
   Bloomberg-style information density with modern consumer polish.
7. **No Docker, no cloud bill.** SQLite + venv + Vite. Runs entirely on
   a MacBook Air 2015 (Intel i5, 8 GB RAM, Zorin OS).

---

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.12.14 (managed by `uv`) |
| Web framework | FastAPI + Uvicorn |
| Database | SQLite via SQLAlchemy 2.x |
| Data | pandas, numpy, yfinance |
| ML (later) | scikit-learn, PyTorch (Colab training), ONNX Runtime (local inference) |
| NLP (later) | VADER → FinBERT-ONNX |
| Frontend | React 18 + Vite 5 + TailwindCSS 3 |
| Charts (later) | lightweight-charts |

---

## Layout

```
quantpulse/
├── backend/                FastAPI service + pipeline + ML + NLP
│   ├── app/
│   │   ├── api/            HTTP routes
│   │   ├── core/           config, logging
│   │   ├── db/             SQLAlchemy engine, session, models
│   │   ├── providers/      external data interfaces + implementations
│   │   ├── pipeline/       (reserved — Stage 2+)
│   │   ├── ml/             (reserved — Stage 8+)
│   │   ├── nlp/            (reserved — Stage 7+)
│   │   ├── explain/        (reserved — Stage 10+)
│   │   └── scheduler/      (reserved — Stage 11+)
│   ├── scripts/            CLI entrypoints (ingestion, feature builds)
│   ├── tests/              pytest suite (Stage 12)
│   └── requirements.txt
├── frontend/               React + Vite + Tailwind
│   └── src/
│       ├── api/            backend client
│       ├── pages/
│       ├── components/
│       ├── charts/
│       └── styles/
├── data/
│   ├── universe.json       frozen Nifty 50 list
│   └── quantpulse.db       SQLite (gitignored)
└── docs/                   per-stage handoff documents
```

---

## Requirements

- **Python 3.12** via [`uv`](https://docs.astral.sh/uv/)
- **Node 20+** and npm
- **git**

System Python is not touched. `uv` installs its own Python into
`~/.local/share/uv/`.

---

## First-time setup

```bash
# 1. install uv (one-time, no sudo)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. install Python 3.12 (one-time, ~3 seconds, prebuilt)
uv python install 3.12

# 3. clone and enter the repo
git clone https://github.com/deaththekid1614/quantpulse.git
cd quantpulse

# 4. create the virtual environment
uv venv --python 3.12

# 5. create local config
cp .env.example .env

# 6. install backend + frontend dependencies
make setup
```

---

## Running the app

Two terminals.

**Terminal A — backend:**

```bash
make run-backend
# → http://127.0.0.1:8000
```

**Terminal B — frontend:**

```bash
make run-frontend
# → http://localhost:5173
```

Open <http://localhost:5173>. You should see the Quantpulse shell with a
green `backend: ok` indicator.

API docs (Swagger UI): <http://127.0.0.1:8000/docs>

---

## Data pipeline

Populate the database with 5 years of daily OHLCV for the Nifty 50:

```bash
# single ticker
.venv/bin/python backend/scripts/ingest_prices.py --ticker TCS.NS --years 5

# full universe (~30 seconds)
.venv/bin/python backend/scripts/ingest_prices.py --universe nifty50 --years 5
```

Idempotent. Re-running for the same range updates rows in place and
never duplicates. Every run is logged to `ingest_log`.

Current database state: **50 securities, 62,138 daily price rows,
2021-09-16 → 2026-09-18**.

---

## Common commands

```bash
make help             list all targets
make setup            install backend + frontend deps
make setup-backend    install Python deps into .venv
make setup-frontend   install Node deps into frontend/node_modules
make run-backend      run FastAPI on 127.0.0.1:8000
make run-frontend     run Vite on localhost:5173
make clean            remove .venv, node_modules, caches
```

---

## Project stages

The build is split into 13 stages. Each stage produces a handoff document
under `docs/` and freezes its files before the next stage begins.

| Stage | Title | Status |
|---|---|---|
| 00 | Foundations | ✅ complete |
| 01 | Data Provider Layer + Stock Universe | ✅ complete |
| 02 | Feature Engine | ⏳ next |
| 03 | Backend API Core | pending |
| 04 | Frontend Foundation + Home + Search | pending |
| 05 | Stock Page Core + 5-Year Chart | pending |
| 06 | Fundamentals + Company Info | pending |
| 07 | News Pipeline + NLP | pending |
| 08 | Forecasting Engine | pending |
| 09 | Risk Engine + Stress Detection | pending |
| 10 | Explanation Engine | pending |
| 11 | Post-Market Batch Pipeline | pending |
| 12 | Testing, Hardening, Deployment | pending |

See `docs/architecture_handoff.md` for the full architecture and
`docs/STAGE_XX.md` for per-stage handoffs.

---

## Data provider notes

Yahoo Finance is used through `yfinance` for historical OHLCV. It is a
free historical-data source, not a guaranteed production API. All access
goes through `backend/app/providers/base.py` abstractions, so a source
swap touches one file.

Prices are split- and dividend-adjusted (`auto_adjust=True`). This is the
correct choice for any historical modelling.

---

## License

Personal project. Not licensed for redistribution yet.