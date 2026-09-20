# Stage 06 — Fundamentals + Company Info

**Status:** ✅ complete
**Completed:** 2026-09-20
**Repo:** `~/IDE/quantpulse`
**Depends on:** Stage 5
**Supersedes:** nothing

---

## 1. What this stage delivered

Company fundamentals and profile, sourced from Yahoo Finance, stored in
SQLite, exposed via a new API endpoint, and rendered as two new sections
on the stock page — a 9-metric snapshot with rule-based interpretation
cards, and an About section with description and profile metadata.

Concretely:

- One new provider method: `YahooMarketDataProvider.get_fundamentals`
- An expanded `Fundamentals` dataclass (32 optional fields, all nullable)
- One new ORM table: `fundamentals` (36 columns)
- A new ingestion script: `backend/scripts/ingest_fundamentals.py`
- One new API endpoint: `GET /api/securities/{ticker}/fundamentals`
- One new Pydantic schema: `FundamentalsOut`
- Two new frontend components: `CompanySnapshot`, `CompanyProfile`
- A rule engine for interpreting four metric groups in plain English
- Wiring into `Stock.jsx` between Statistics and Today's Session

No ML, no news, no forecasts. Those come later.

---

## 2. Backend additions (frozen)

### `backend/app/providers/base.py` (append-only)

The `Fundamentals` dataclass grew from 11 fields to 32. Every new field
is `float | None`, `int | None`, or `str | None`. Method signatures,
`NewsArticle`, `OHLCV_COLUMNS`, and all error classes are byte-identical
to Stage 1.

Fields:
- Market: `current_price`, `previous_close`, `market_cap`,
  `enterprise_value`, `high_52w`, `low_52w`, `shares_outstanding`
- Valuation: `pe_trailing`, `price_to_book`, `price_to_sales`
- Earnings: `eps_trailing`
- Revenue/profit: `total_revenue`, `gross_profits`, `net_income`,
  `profit_margin`, `return_on_equity`, `return_on_assets`
- Balance sheet: `total_debt`, `total_cash`, `debt_to_equity`
- Dividends: `dividend_rate`, `dividend_yield`, `payout_ratio`
- Profile: `long_name`, `yf_sector`, `industry`, `employees`, `city`,
  `country`, `website`, `description`
- Reference: `beta_yf` (Yahoo's own estimate, distinct from our
  computed `beta_60d`)

### `backend/app/providers/yahoo.py` (frozen)

Added `get_fundamentals(ticker) -> Fundamentals`.

- Fetches via `yf.Ticker(ticker).info`
- Coerces numerics through `_coerce_float` — non-finite values become
  `None`
- Coerces strings through `_coerce_str` — empty strings, "N/A", "None",
  "nan" become `None`
- On network failure: raises `ProviderUnavailable`
- On empty `.info` for a valid ticker (rare): returns an all-None
  `Fundamentals`
- On invalid ticker (Yahoo 404): returns an all-None `Fundamentals` —
  it does **not** raise, because the provider can't distinguish "bad
  ticker" from "no data" reliably. The route layer handles missing
  tickers via the `securities` table.

### `backend/scripts/probe_fundamentals.py` (frozen)

One-off probe used to decide which columns are worth persisting. Not
part of any pipeline. Kept in the repo for reproducibility if we ever
change providers.

### `backend/app/db/models.py` (append-only)

New `FundamentalsRow` class. 36 columns. All value columns nullable.
Unique constraint on `security_id` (one row per security). `updated_at`
set on every upsert.

### `backend/scripts/ingest_fundamentals.py` (frozen)

CLI: `--ticker TCS.NS` or `--universe nifty50`.

- One row per security
- Upsert semantics (add if missing, update if present)
- Per-ticker logging to `ingest_log`
- Coverage count printed per ticker (`X/32 fields`)

### `backend/app/api/routes/fundamentals.py` (frozen)

`GET /api/securities/{ticker}/fundamentals`

- 404 if ticker not in `securities`
- 200 with all-None metrics if security exists but no fundamentals row
- Cached 60 s under key `fundamentals:{ticker}`

### `backend/app/api/schemas.py` (append-only)

Added `FundamentalsOut`. All prior schemas byte-identical.

### `backend/app/api/router.py` (frozen)

Now includes 9 sub-routers (added `fundamentals`).

---

## 3. Frontend additions (frozen)

### `frontend/src/api/client.js` (append-only)

Added `getFundamentals(ticker)`. All existing exports unchanged.

### `frontend/src/api/hooks.js` (append-only)

Added `useFundamentals(ticker)`. Added `stats` and `fundamentals` to
the `queryKeys` map.

### `frontend/src/components/CompanySnapshot.jsx` (frozen)

Four interpretation cards (Profitability, Valuation, Balance Sheet,
Dividend) plus a 3×3 metric grid plus a footnote.

**Rule engine — locked:**

`profitability(data)`:
- If `net_income < 0` → **Loss-making**. Yahoo's `profit_margin` field
  is unreliable during corporate actions (TMPV demerger was the trigger
  case); we trust `net_income`'s sign as ground truth.
- Else if `profit_margin` missing but `net_income > 0` → **Profitable**
  (margin not reported)
- Else if `profit_margin == null` → **—**
- Else bands: ≥20% **Strong**, ≥10% **Moderate**, ≥3% **Modest**,
  ≥0% **Thin**, <0% **Negative**
- ROE appended to the note when present

`valuation(data)`:
- `pe_trailing == null` → **—** "Not reported."
- <15 **Low**, <25 **Moderate**, <40 **Elevated**, ≥40 **High**

`balanceSheet(sector, data)`:
- `debt_to_equity == null` → **—** "Not reported."
- If sector is `Financial Services` → **Typical for financials**
  (banks are structurally leveraged; the usual bands don't apply)
- Else bands by raw yfinance value (typically a percent for NSE):
  ≤30 **Conservative**, ≤80 **Moderate**, ≤200 **Elevated**, >200 **Leveraged**

`dividend(data)`:
- `dividend_yield == null` → **—** "Not reported."
- `== 0` → **None**
- <1% **Modest**, <3% **Moderate**, ≥3% **High**

**Forbidden vocabulary in any card:** buy, sell, undervalued, overvalued,
bargain, opportunity. Only descriptive statements.

Missing values render as `—`. No zeroes invented.

### `frontend/src/components/CompanyProfile.jsx` (frozen)

- Description paragraph, truncated at 600 chars with a `READ MORE`
  toggle
- Metadata row: Industry · Employees · HQ · Website
- Website link opens in new tab; protocol stripped for display
- Indian number formatting for employee count

### `frontend/src/pages/Stock.jsx` (rewritten)

Full-page composition:

1. Back link
2. Header
3. Price block
4. Price history — TimeframeTabs + chart
5. How is {symbol} doing? — narrative
6. Statistics — StatsGrid
7. **Company snapshot — CompanySnapshot (new)**
8. **About {symbol} — CompanyProfile (new)**
9. Today's session — OHLC row
10. Coming next — Stages 7–10 placeholder

---

## 4. Verification results

**Probe (Chunk A):** 4 tickers, all returned 160+ keys. Field coverage
audit identified which fields are worth persisting. Notable findings:
- ROE/ROA are only published for banks/NBFCs among NSE-listed
  non-financials (28% / 26% coverage across the universe)
- TMPV has no trailing P/E (post-demerger)

**Provider (Chunk B):** TCS returned 32/32 populated fields (`as_of` is
set at ingestion, not by the provider). Bad ticker returns all-None
Fundamentals without raising. RELIANCE ROE and TMPV PE correctly `None`.

**DB (Chunk C):**
```
tables            : 6
fundamentals cols : 36
TCS ingest        : +1  ~0   (32/32 fields)
TCS idempotent    : +0  ~1, row count = 1
Full universe     : 49 added + 1 updated = 50 rows in 17.4s
```

**Coverage across 50 securities:**

| Field | Coverage |
|---|---|
| current_price, market_cap, price_to_book, eps_trailing | 100% |
| total_revenue, net_income, profit_margin | 100% |
| total_debt, total_cash | 100% |
| dividend_rate, dividend_yield, payout_ratio | 100% |
| long_name, industry, city, country, website, description, beta_yf | 100% |
| pe_trailing | 98% |
| employees | 98% |
| debt_to_equity | 86% |
| return_on_equity | 28% |
| return_on_assets | 26% |

The low ROE/ROA coverage is Yahoo's behaviour, not a bug. Our rule
engine uses `profit_margin` (100%) as the primary profitability signal.

**API (Chunk D):** TCS returns all 35 fields with real values. RELIANCE
preserves null ROE/ROA. TMPV preserves null P/E. 404 for unknown
tickers. Cache second call < 5 ms.

**UI (Chunk E):**
- TCS: PROFITABILITY `Moderate` (18% margin, 47.7% ROE); VALUATION
  `Moderate`; BALANCE SHEET `Conservative`; DIVIDEND `High`
- HDFCBANK: PROFITABILITY `Strong` (26.8% margin); VALUATION
  `Moderate`; BALANCE SHEET `—` (null); DIVIDEND `Moderate`
- TMPV: PROFITABILITY `Loss-making` (net income −₹3,375 Cr, despite
  Yahoo reporting positive margin — our rule trusts the sign)
- BHARTIARTL: description expands on `READ MORE`, website link works,
  HQ shows `Gurugram, India`

**Build:**
```
✓ 100 modules transformed
dist/assets/index-*.css   13.76 kB │ gzip:   3.37 kB
dist/assets/index-*.js   391.34 kB │ gzip: 124.19 kB
✓ built in ~3.5s
```

---

## 5. Repository deltas since Stage 5

**Backend — added:**
```
backend/scripts/probe_fundamentals.py
backend/scripts/ingest_fundamentals.py
backend/app/api/routes/fundamentals.py
```

**Backend — modified:**
```
backend/app/providers/base.py    (Fundamentals dataclass expanded, additive)
backend/app/providers/yahoo.py   (added get_fundamentals)
backend/app/db/models.py         (appended FundamentalsRow)
backend/app/api/schemas.py       (appended FundamentalsOut)
backend/app/api/router.py        (added fundamentals include)
```

**Frontend — added:**
```
frontend/src/components/CompanySnapshot.jsx
frontend/src/components/CompanyProfile.jsx
```

**Frontend — modified:**
```
frontend/src/api/client.js       (added getFundamentals)
frontend/src/api/hooks.js        (added useFundamentals)
frontend/src/pages/Stock.jsx     (rewritten to include new sections)
```

**Docs — added:**
```
docs/STAGE_06.md
```

**No changes** to any Stage 1–5 file outside the append-only additions
listed above. `features.py`, all ingest scripts from Stages 1–2, all
earlier routes, all earlier components are byte-identical.

---

## 6. Known limitations going into Stage 7

- ROE/ROA coverage is 26–28% across the universe. The frontend handles
  missing gracefully (the interpretation card falls back to
  `profit_margin`), but any future ML/NLP stage that wants to use ROE
  as a feature must tolerate widespread nulls or impute carefully.
- `debt_to_equity` from Yahoo is inconsistent in units. For TCS it's
  `10.21` (clearly a percent → 10.21%). For TMPV it's `70.36` → 70.36%.
  We display it raw and describe it qualitatively. A future stage could
  normalise, but that requires confirming units across all 50 tickers,
  which is beyond Stage 6's scope.
- `beta_yf` (Yahoo's beta, 0.17 for TCS) is very different from our
  computed `beta_60d` (0.96). Both are legitimate; they measure
  different things (different windows, different index methodology).
  The UI labels it "Beta (Yahoo)" to disambiguate. Do not merge them.
- Fundamentals are a snapshot, not a time series. Re-running the ingest
  replaces the row. We lose historical snapshots. That's fine for the
  current product — the stock page shows current fundamentals only. If
  we ever want fundamentals-over-time, a Stage 11 scheduler can append
  to a new table.
- yfinance's `.info` is not a stable contract. Yahoo changes the schema
  occasionally. The probe script exists so we can re-audit if a field
  goes missing. Stage 12 may add a contract test.
- `description` is truncated at 600 chars in the UI. No search within.
- No `<html>` meta description update per ticker. Every page title is
  still "Quantpulse".
- Employee count is displayed in Indian notation (`5,84,519`), which is
  correct for Indian users but ambiguous for others. No locale switcher
  yet.

---

## 7. Next stage entry point — Stage 7

**Stage 7 — News Pipeline + NLP**

Real news, real sentiment, real relevance scoring.

**New backend components:**

1. **News provider** — `backend/app/providers/news.py`, implementing
   the `NewsProvider` interface from `providers/base.py`. Source
   strategy:
   - Primary: RSS feeds (Moneycontrol, Economic Times Markets, Business
     Standard, LiveMint) — free, no API key
   - Fallback: any free aggregator with a stable endpoint
   - No paid APIs

2. **New table:** `news_articles` — id, ticker, title, url (unique),
   source, published_at, body, summary, fetched_at
   Plus: `sentiment_score`, `sentiment_label`, `relevance_score`,
   `importance_score` (all nullable — populated by the NLP layer)

3. **NLP layer** — `backend/app/nlp/sentiment.py`:
   - v1: VADER (pure Python, no model download, works offline)
   - v2 upgrade path: FinBERT-ONNX (quantized, CPU) — only if v1
     proves inadequate
   - `classify(title, body) -> {score: float, label: str}`
   - `relevance(title, body, ticker, company_name) -> float 0–1`
   - `importance(source, published_at, title) -> float 0–1`

4. **Ingestion script:** `backend/scripts/ingest_news.py`
   - `--ticker` and `--universe` modes
   - Deduplicate on URL
   - Per-ticker logging

5. **New endpoint:** `GET /api/securities/{ticker}/news?limit=20`
   - Returns articles newest-first
   - Each article includes title, source, url, published_at,
     sentiment_label, sentiment_score, relevance_score, importance_score

6. **Frontend component:** `NewsFeed.jsx`
   - List of cards, each with title, source, time-ago, sentiment chip
     (positive/neutral/negative colour), importance bar
   - Click through to source URL

7. **New section on stock page** between narrative and statistics (or
   between statistics and fundamentals — decide in the Stage 7 plan).

**Design rules:**

- Sentiment is labelled `positive` / `neutral` / `negative`, with a
  numeric score in the payload for future model use.
- Relevance is a float 0–1. Articles below 0.3 are dropped at ingest
  time — they don't belong to that ticker.
- Importance is a float 0–1. Combines source tier, recency decay, and
  a small set of market-impact keywords ("guidance", "downgrade",
  "acquisition", etc.).
- No fake precision in the UI. Sentiment is a chip, not `0.42`.
- No "AI generated summary" text yet — that's Stage 10.

**Out of scope for Stage 7:** forecasts, risk, explanations.

Deliverable: 30 days of news ingested for all 50 tickers, sentiment and
relevance scored, a working `/news` endpoint, and a news feed rendered
on the stock page.

---

## 8. Handoff prompt for the next chat

Copy this into a new conversation:

> Context: I'm building **Quantpulse**. Repo at `~/IDE/quantpulse`.
> Read `docs/architecture_handoff.md` and `docs/STAGE_01.md` through
> `docs/STAGE_06.md` — all in my repo — before starting. Then begin
> **Stage 7 — News Pipeline + NLP** exactly as scoped in section 7 of
> `docs/STAGE_06.md`.
>
> Environment: MacBook Air 2015, Intel i5, 8 GB RAM, Zorin OS 16
> (XFCE). Python 3.12.14 in `~/IDE/quantpulse/.venv` managed by `uv`.
> Node 20 + npm. Backend on `127.0.0.1:8000`, Vite on `localhost:5173`
> proxying `/api/*` to the backend.
>
> Rules: plan first, full-file replacements only, one test per chunk,
> no debug cycles, hand off as `docs/STAGE_07.md`.

---
