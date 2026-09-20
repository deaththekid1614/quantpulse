# Quantpulse

**Post-Market Intelligence & Forecasting Platform.**

Quantpulse is not a live-trading tool and not an AI dashboard. It is a
post-market research system: after each NSE session closes (3:30 PM IST),
it collects the day's price, volume, and news data for a fixed universe
of Indian equities, computes features, runs an ML/NLP pipeline, and
publishes per-ticker pages containing a 5-year interactive chart, a
plain-English performance narrative, a risk assessment, news sentiment,
and probabilistic 7/15/30-day forecasts with explanations.

> One analysis per session. Many users. No fake precision. 🎯

**Status:** Stage 6 complete — the stock page now includes company
fundamentals with rule-based interpretation cards and an About section.
Interactive chart, narrative, and statistics grid are already live.
No ML, no news, no forecasts yet.

---

## 🧭 Design principles

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

## 🧱 Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.12.14 (managed by `uv`) |
| Web framework | FastAPI + Uvicorn |
| Database | SQLite via SQLAlchemy 2.x |
| Data | pandas, numpy, yfinance |
| ML (later) | scikit-learn, PyTorch (Colab training), ONNX Runtime (local inference) |
| NLP (later) | VADER → FinBERT-ONNX |
| Frontend | React 18 + Vite 5 + TailwindCSS 3 + React Router 6 + React Query 5 |
| Charts | lightweight-charts 4 |

---

## 📁 Layout

```
quantpulse/
├── backend/                FastAPI service + pipeline + ML + NLP
│   ├── app/
│   │   ├── api/            HTTP routes + schemas + cache
│   │   ├── core/           config, logging
│   │   ├── db/             SQLAlchemy engine, session, models
│   │   ├── providers/      external data interfaces + implementations
│   │   ├── pipeline/       feature engine
│   │   ├── ml/             (reserved — Stage 8+)
│   │   ├── nlp/            (reserved — Stage 7+)
│   │   ├── explain/        (reserved — Stage 10+)
│   │   └── scheduler/      (reserved — Stage 11+)
│   ├── scripts/            CLI entrypoints (prices, indices,
│   │                       features, fundamentals, probes)
│   ├── tests/              pytest suite (Stage 12)
│   └── requirements.txt
├── frontend/               React + Vite + Tailwind
│   └── src/
│       ├── api/            backend client + React Query hooks
│       ├── components/     Layout, Search, MarketStrip, TopMovers,
│       │                   TimeframeTabs, PerformanceNarrative,
│       │                   StatsGrid, CompanySnapshot, CompanyProfile
│       ├── charts/         PriceChart (candlestick)
│       ├── pages/          Home, Stock
│       └── styles/         Tailwind entry
├── data/
│   ├── universe.json       frozen Nifty 50 list
│   └── quantpulse.db       SQLite (gitignored)
└── docs/                   per-stage handoff documents
```

---

## ⚙️ Requirements

- **Python 3.12** via [`uv`](https://docs.astral.sh/uv/)
- **Node 20+** and npm
- **git**

System Python is not touched. `uv` installs its own Python into
`~/.local/share/uv/`.

---

## 🚀 First-time setup

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

## ▶️ Running the app

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

Open <http://localhost:5173>. You land on the **market overview** —
indices strip, top movers, and a market-summary placeholder. The search
box in the top bar autocompletes over the 50 securities; pressing Enter
navigates to `/stock/:ticker`.

📖 API docs (Swagger UI): <http://127.0.0.1:8000/docs>

---

## 🧮 Data pipeline

Four idempotent scripts populate the database. Run in this order on a
fresh clone.

### 1. Price history (Nifty 50)

```bash
# single ticker
.venv/bin/python backend/scripts/ingest_prices.py --ticker TCS.NS --years 5

# full universe (~30 seconds)
.venv/bin/python backend/scripts/ingest_prices.py --universe nifty50 --years 5
```

### 2. Market indices (Nifty 50, Bank Nifty, India VIX)

```bash
.venv/bin/python backend/scripts/ingest_indices.py --years 5
```

### 3. Feature engine

Computes 24 features per (security, date) from raw prices plus index
context. Warm-up rows are dropped; only fully-populated rows are stored.

```bash
# single ticker
.venv/bin/python backend/scripts/build_features.py --ticker TCS.NS

# full universe (~30 seconds)
.venv/bin/python backend/scripts/build_features.py --universe nifty50
```

### 4. Company fundamentals

Fetches market cap, P/E, EPS, revenue, profit, dividends, balance sheet
items, and company profile from Yahoo Finance. One row per security.

```bash
# single ticker
.venv/bin/python backend/scripts/ingest_fundamentals.py --ticker TCS.NS

# full universe (~20 seconds)
.venv/bin/python backend/scripts/ingest_fundamentals.py --universe nifty50
```

Every run is logged to `ingest_log`. Re-running is safe and never
duplicates rows.

### 📊 Current database state

```
securities         :  50
prices_daily       :  62,138 rows   (2021-09-16 → 2026-09-18)
market_index_daily :   3,707 rows   (^NSEI, ^NSEBANK, ^INDIAVIX)
features_daily     :  51,939 rows   (2022-07-05 → 2026-09-18)
fundamentals       :      50 rows   (one per security)
```

---

## 🌐 API

Nine endpoints under `/api`. All responses are JSON. Full interactive
reference at <http://127.0.0.1:8000/docs>.

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness check |
| GET | `/api/securities` | List all 50 tracked securities |
| GET | `/api/securities/{ticker}` | Metadata for one security |
| GET | `/api/securities/{ticker}/prices?range=1y` | Daily OHLCV history |
| GET | `/api/securities/{ticker}/features?range=1y` | Daily feature vector |
| GET | `/api/securities/{ticker}/snapshot` | Latest price + change + features |
| GET | `/api/securities/{ticker}/stats` | 52w range, returns, volumes, ATH/ATL |
| GET | `/api/securities/{ticker}/fundamentals` | Company fundamentals + profile |
| GET | `/api/indices/snapshot` | Latest bar + change for the three indices |
| GET | `/api/movers?limit=10` | Top movers by absolute 1-day % change |

`range` accepts `1w`, `1m`, `3m`, `6m`, `1y`, `3y`, `5y`, `max`.
Default is `1y`. `limit` accepts 1–50.

Errors: `404` for unknown ticker, `400` for invalid range, `422` for
invalid `limit`.

Responses are cached in-memory for 60 seconds. Second reads of any
endpoint return in < 5 ms.

---

## 🖥️ Frontend

React 18 + Vite 5, styled with Tailwind. Data fetching via React Query
with a 60-second `staleTime` matching the backend cache TTL. Routing via
React Router 6.

**Pages:**

- `/` — **Market overview**: indices strip, top movers, market summary
  placeholder.
- `/stock/:ticker` — **Stock page** (see below).

**Stock page sections, top to bottom:**

1. Header — symbol, name, sector, NSE, last session date
2. Price block — current close + day change
3. **Price history** — interactive candlestick chart with a
   `3M / 6M / 1Y / 3Y / 5Y / MAX` timeframe switcher
4. **How is {symbol} doing?** — plain-English performance narrative
   (rule-based, deterministic)
5. **Statistics** — 9-cell grid: 52-week range, distances from 52w
   high/low, 1d / 20d / YTD / 1y returns, average volume, all-time
   range
6. **Company snapshot** — 4 interpretation cards (Profitability,
   Valuation, Balance Sheet, Dividend) + 9-cell metric grid
7. **About {symbol}** — business description, industry, employees, HQ,
   website
8. **Today's session** — OHLC + volume
9. **Coming next** — placeholder listing Stages 7–10

**Search** in the top bar autocompletes over the full security list
(client-side, since only 50 rows). Keyboard-navigable: ↑ / ↓ to move,
Enter to open, Esc to close.

📈 **Chart** — dark-themed candlestick via `lightweight-charts` 4.2.
Crosshair, pan, and zoom work out of the box. Auto-resizes to its
container.

📝 **Narrative** — reads five features from `/snapshot`
(`px_over_sma_50`, `px_over_sma_200`, `rsi_14`, `ret_20d`, `vol_20d`) and
produces three sentences: trend, momentum + monthly performance,
volatility band. No LLM. Same inputs → same output.

🧾 **Fundamentals** — rule-based interpretation for four metric groups.
Profitability trusts the sign of trailing net income over Yahoo's margin
field (Yahoo can report positive margin for a loss-making company during
a corporate action). Financial-sector companies are flagged separately
for debt/equity because banks are structurally leveraged. Missing values
render as `—`; nothing is invented. No recommendation language
("buy", "undervalued", etc.) anywhere in the UI.

---

## 🧬 Feature catalogue

24 columns per row in `features_daily`, grouped:

| Group | Columns |
|---|---|
| Returns | `ret_1d`, `ret_5d`, `ret_20d` (log) |
| Volatility | `vol_20d`, `atr_14d` |
| Moving averages | `sma_20`, `sma_50`, `sma_200`, `ema_12`, `ema_26` |
| Price vs MA | `px_over_sma_20`, `px_over_sma_50`, `px_over_sma_200` |
| Momentum | `rsi_14`, `macd`, `macd_signal`, `macd_hist`, `roc_10` |
| Volume | `rel_volume_20d`, `volume_z_20d` |
| Market | `mkt_ret_1d`, `mkt_ret_5d`, `beta_60d` |
| Sector | `sector_ret_1d` |

**Warm-up:** ~203 rows per ticker (dominated by `sma_200`). Tickers with
1243 price rows produce 1038–1039 feature rows.

**Extremes are kept, not clamped.** `beta_60d` can exceed 5 during
idiosyncratic events (e.g. Adani Group, March–April 2023). Winsorization
is a Stage 8 modelling concern, not a Stage 2 feature concern.

---

## 💼 Fundamentals catalogue

36 columns per row in `fundamentals`, grouped:

| Group | Columns |
|---|---|
| Market | current_price, previous_close, market_cap, enterprise_value, high_52w, low_52w, shares_outstanding |
| Valuation | pe_trailing, price_to_book, price_to_sales |
| Earnings | eps_trailing |
| Revenue/Profit | total_revenue, gross_profits, net_income, profit_margin, return_on_equity, return_on_assets |
| Balance sheet | total_debt, total_cash, debt_to_equity |
| Dividends | dividend_rate, dividend_yield, payout_ratio |
| Profile | long_name, yf_sector, industry, employees, city, country, website, description |
| Reference | beta_yf |

**Coverage is uneven.** Yahoo publishes ROE/ROA for only ~28% of NSE-listed
non-financials, and `debt_to_equity` is missing for ~14%. Everything else
is at or near 100%. The frontend renders missing values as `—` and picks
alternate signals when the primary one is absent.

---

## 🧰 Common commands

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

## 🗺️ Project stages

The build is split into 13 stages. Each stage produces a handoff document
under `docs/` and freezes its files before the next stage begins.

| Stage | Title | Status |
|---|---|---|
| 00 | Foundations | ✅ complete |
| 01 | Data Provider Layer + Stock Universe | ✅ complete |
| 02 | Feature Engine | ✅ complete |
| 03 | Backend API Core | ✅ complete |
| 04 | Frontend Foundation + Home + Search | ✅ complete |
| 05 | Stock Page Core + 5-Year Chart | ✅ complete |
| 06 | Fundamentals + Company Info | ✅ complete |
| 07 | News Pipeline + NLP | ⏳ next |
| 08 | Forecasting Engine | pending |
| 09 | Risk Engine + Stress Detection | pending |
| 10 | Explanation Engine | pending |
| 11 | Post-Market Batch Pipeline | pending |
| 12 | Testing, Hardening, Deployment | pending |

See `docs/architecture_handoff.md` for the full architecture and
`docs/STAGE_XX.md` for per-stage handoffs.

---

## 📡 Data provider notes

Yahoo Finance is used through `yfinance` for historical OHLCV and
fundamentals. It is a free data source, not a guaranteed production API.
All access goes through `backend/app/providers/base.py` abstractions, so
a source swap touches one file.

Prices are split- and dividend-adjusted (`auto_adjust=True`). This is the
correct choice for any historical modelling.

Fundamentals are a snapshot, refreshed on each ingest run. The `probe_fundamentals.py`
script exists so we can re-audit field coverage if Yahoo changes its
schema.

---

