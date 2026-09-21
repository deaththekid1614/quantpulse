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

**Status:** Stage 7 complete — the stock page now includes a scored news
feed with sentiment chips and impact bars. Chart, narrative, statistics,
fundamentals, and profile sections are already live. No ML, no forecasts
yet.

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
| NLP | VADER + custom financial lexicon overlay |
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
│   │   │                   (yahoo, news)
│   │   ├── pipeline/       feature engine
│   │   ├── ml/             (reserved — Stage 8+)
│   │   ├── nlp/            sentiment, relevance, importance
│   │   ├── explain/        (reserved — Stage 10+)
│   │   └── scheduler/      (reserved — Stage 11+)
│   ├── scripts/            CLI entrypoints (prices, indices,
│   │                       features, fundamentals, news, probes)
│   ├── tests/              pytest suite (Stage 12)
│   └── requirements.txt
├── frontend/               React + Vite + Tailwind
│   └── src/
│       ├── api/            backend client + React Query hooks
│       ├── components/     Layout, Search, MarketStrip, TopMovers,
│       │                   TimeframeTabs, PerformanceNarrative,
│       │                   StatsGrid, CompanySnapshot, CompanyProfile,
│       │                   NewsFeed
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

Five idempotent scripts populate the database. Run in this order on a
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

### 5. News

Fetches RSS articles per ticker (Google News + Yahoo Finance), scores
them for sentiment, relevance, and importance, drops anything below
relevance 0.30, and stores the rest. Deduplicated on
`(security_id, url)` so an article mentioning multiple tickers appears
under each one with its own per-ticker relevance.

```bash
# single ticker
.venv/bin/python backend/scripts/ingest_news.py --ticker TCS.NS --limit 30

# full universe (~2 minutes)
.venv/bin/python backend/scripts/ingest_news.py --universe nifty50 --limit 30
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
news_articles      :     949 rows   (last 30 days, scored)
```

---

## 🌐 API

Eleven endpoints under `/api`. All responses are JSON. Full interactive
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
| GET | `/api/securities/{ticker}/news?limit=20` | Scored news feed |
| GET | `/api/indices/snapshot` | Latest bar + change for the three indices |
| GET | `/api/movers?limit=10` | Top movers by absolute 1-day % change |

`range` accepts `1w`, `1m`, `3m`, `6m`, `1y`, `3y`, `5y`, `max`.
Default is `1y`. `limit` accepts 1–100 on `/news`, 1–50 on `/movers`.
`/news` also accepts `min_importance` (0–1).

Errors: `404` for unknown ticker, `400` for invalid range, `422` for
invalid numeric params.

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
5. **Statistics** — 9-cell grid: 52-week range, distances from 52w
   high/low, 1d / 20d / YTD / 1y returns, average volume, all-time
   range
6. **Recent news** — scored article cards with sentiment chips and
   impact bars
7. **Company snapshot** — 4 interpretation cards + 9-cell metric grid
8. **About {symbol}** — description, industry, employees, HQ, website
9. **Today's session** — OHLC + volume
10. **Coming next** — placeholder listing Stages 8–10

**Search** in the top bar autocompletes over the full security list
(client-side, since only 50 rows). Keyboard-navigable: ↑ / ↓ to move,
Enter to open, Esc to close.

📈 **Chart** — dark-themed candlestick via `lightweight-charts` 4.2.

📝 **Narrative** — rule-based, deterministic, reads five features from
`/snapshot`. No LLM.

🧾 **Fundamentals** — rule-based interpretation cards. Missing values
render as `—`. No recommendation language anywhere.

📰 **News** — cards show cleaned title, publisher, time-ago, a coloured
sentiment chip, and an impact bar. Titles are deduplicated with the
publisher so `MarketWatch` appears once, not twice. Times are rendered
with the correct IST offset from naive UTC stored in SQLite.

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

**Warm-up:** ~203 rows per ticker (dominated by `sma_200`).

**Extremes are kept, not clamped.** `beta_60d` can exceed 5 during
idiosyncratic events (e.g. Adani Group, March–April 2023).

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

**Coverage is uneven.** Yahoo publishes ROE/ROA for only ~28% of NSE
non-financials; `debt_to_equity` is missing for ~14%. Everything else is
at or near 100%. Missing values render as `—`.

---

## 📰 News & NLP

**Sources:** Google News RSS (per company name and per symbol),
Yahoo Finance RSS. Merged and deduped on normalised title. No API keys,
no rate limits, no cost.

**Sentiment:** VADER with a custom financial lexicon overlay. VADER
alone scores `"profit warning"` as positive because it sees `profit` +
`warning` as separate terms. The overlay counts 40+ finance-negative
terms (`plunge`, `downgrade`, `miss`, `cut`, …) at −0.35 each and 30+
finance-positive terms (`rally`, `record`, `dividend`, …) at +0.15 each,
capped at ±0.5. Output is `positive` / `neutral` / `negative` with a
compound score in [−1, 1].

**Relevance (0–1):** exact company name = +0.50, symbol as word = +0.40,
first meaningful name word = +0.20, sector keyword = +0.10, financial
context keyword = +0.05. Articles below **0.30 are dropped at ingest
time** — they never enter the database.

**Importance (0–1):** publisher tier (tier-1 = 0.50, tier-2 = 0.30,
unknown = 0.10), recency (exponential decay, 30-day half-life, up to
0.30), market-impact keywords (up to 5 unique, +0.08 each, max 0.40).

**Storage:** one row per `(security_id, url)`. An IT-sector roundup
mentioning TCS, INFY, and WIPRO gets three rows, one per ticker, each
with its own relevance score. Dedup is therefore on the composite key,
not URL alone.

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
| 07 | News Pipeline + NLP | ✅ complete |
| 08 | Forecasting Engine | ⏳ next |
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

News is fetched from public RSS feeds. RSS URLs from Google News are
redirects (`news.google.com/rss/articles/...`) — one extra hop when a
user clicks through, but no API key, no quota.

Prices are split- and dividend-adjusted (`auto_adjust=True`). This is
the correct choice for any historical modelling.

---