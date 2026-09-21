# Stage 07 — News Pipeline + NLP

**Status:** ✅ complete
**Completed:** 2026-09-21
**Repo:** `~/IDE/quantpulse`
**Depends on:** Stage 6
**Supersedes:** nothing

---

## 1. What this stage delivered

RSS news fetching, sentiment scoring, relevance filtering, importance
ranking, storage in SQLite, a `GET /news` endpoint, and a feed on the
stock page.

Concretely:

- Two dependencies added: `feedparser`, `vaderSentiment`
- New provider: `RSSNewsProvider` (Google News + Yahoo Finance RSS)
- New ORM table: `news_articles` (13 columns, composite unique on
  `(security_id, url)`)
- New NLP module: `app/nlp/sentiment.py` — three pure functions
- New ingest script: `backend/scripts/ingest_news.py`
- New API endpoint: `GET /api/securities/{ticker}/news`
- New Pydantic schemas: `NewsArticleOut`, `NewsFeedOut`
- New frontend component: `NewsFeed.jsx`
- New section on the stock page between Statistics and Company Snapshot

No ML, no forecasts, no explanations. Those come in Stages 8–10.

---

## 2. Backend additions (frozen)

### `backend/requirements.txt` (append-only)

Added:
- `feedparser>=6.0,<7`
- `vaderSentiment>=3.3,<4`

### `backend/scripts/probe_news_sources.py` (frozen)

One-off probe used to decide the source strategy. Kept for
reproducibility if we ever change providers.

### `backend/app/providers/news.py` (frozen)

`RSSNewsProvider` implementing the `NewsProvider` interface from
`providers/base.py`.

**Sources (merged, deduped):**
1. Google News RSS — quoted company name query (`"Tata Consultancy Services" when:30d`)
2. Google News RSS — symbol + India query (`"TCS" stock India when:30d`)
3. Yahoo Finance per-ticker RSS

**Dedup:** normalised title (lowercase, strip publisher suffix, collapse
punctuation, truncate at 120 chars).

**Publisher extraction:** `<source>` tag when present, else URL hostname.

**Failure isolation:** each source fetch is wrapped; if one fails,
others still contribute. If all fail, returns empty list.

### `backend/app/db/models.py` (append-only)

New `NewsArticleRow`:
- 13 columns: `id`, `security_id`, `title`, `url`, `source`,
  `published_at`, `summary`, `body`, `sentiment_score`,
  `sentiment_label`, `relevance_score`, `importance_score`, `fetched_at`
- `UNIQUE(security_id, url)` — the same article can appear under
  multiple tickers, each with its own per-ticker relevance score
- Indexes on `(security_id, published_at)` and
  `(security_id, importance_score)` for fast feed queries

### `backend/app/nlp/sentiment.py` (frozen)

Three pure functions:

**`analyze_sentiment(title, summary) -> (score, label)`**
- VADER on `title + title + summary` (title weighted 2×)
- Financial lexicon overlay:
  - 40+ finance-negative terms (`fall`, `plunge`, `downgrade`,
    `profit warning`, etc.) → `-0.35` each, unique
  - 30+ finance-positive terms (`win`, `rally`, `record`, `dividend`,
    etc.) → `+0.15` each, unique
  - Delta capped at `±0.5` to prevent domination by one term
- Final compound clamped to `[-1, 1]`
- Label: `positive` if ≥ 0.05, `negative` if ≤ −0.05, else `neutral`

The overlay corrects VADER's known weakness on financial headlines
("profit warning" is one negative concept, not "profit" + "warning").

**`compute_relevance(title, summary, ticker, company_name, sector) -> float`**
- Company name exact phrase: `+0.50`
- Symbol as whole word: `+0.40`
- First meaningful name word (skips generic terms like "Tata",
  "Reliance", "Bank"): `+0.20`
- Sector keyword: `+0.10`
- Financial context keyword (`stock`, `NSE`, `quarter`, etc.): `+0.05`
- Clamped to `[0, 1]`

**`compute_importance(title, summary, source, published_at) -> float`**
- Source tier: `+0.50` tier-1 (Reuters, ET, Mint, Moneycontrol…),
  `+0.30` tier-2 (Upstox, MarketsMojo, Trendingly…), `+0.10` unknown
- Recency: exponential decay, half-life 30 days → up to `+0.30`
- Impact keywords (up to 5 unique from `_IMPACT_TERMS`): `+0.08` each,
  max `+0.40`
- Clamped to `[0, 1]`

### `backend/scripts/ingest_news.py` (frozen)

CLI: `--ticker` or `--universe nifty50`, plus `--days` (default 30)
and `--limit` (default 50).

Per ticker:
1. Fetch via `RSSNewsProvider`
2. Score every article (sentiment, relevance, importance)
3. Drop articles with `relevance_score < 0.30`
4. Upsert on `(security_id, url)` — scores and summary refreshed on
   every run, new articles inserted

Every run logged to `ingest_log`.

### `backend/app/api/schemas.py` (append-only)

Added `NewsArticleOut` and `NewsFeedOut`. All prior schemas
byte-identical.

### `backend/app/api/routes/news.py` (frozen)

`GET /api/securities/{ticker}/news`

Query params:
- `limit` (1–100, default 20)
- `min_importance` (0.0–1.0, default 0.0)

Returns newest-first. 404 for unknown tickers. Cached 60 s under
`news:{ticker}:{limit}:{min_importance}`.

### `backend/app/api/router.py` (frozen)

Now includes 10 sub-routers (added `news`).

---

## 3. Frontend additions (frozen)

### `frontend/src/api/client.js` (append-only)

Added `getNews(ticker, limit, minImportance)`.

### `frontend/src/api/hooks.js` (append-only)

Added `useNews(ticker, limit, minImportance)`. Added `news` to
`queryKeys`.

### `frontend/src/components/NewsFeed.jsx` (frozen)

Renders a list of article cards:
- **Title** — publisher suffix stripped at render time
  (`" - MarketWatch"` etc.), so users don't see the publisher twice
- **Publisher** — small grey text
- **Time-ago** — appended `Z` to naive UTC timestamps before parsing
  (SQLite stores datetimes naive; without the fix, all times render
  ~5.5 hours off in IST)
- **Sentiment chip** — coloured dot + `POSITIVE` / `NEGATIVE` / `NEUTRAL`
- **Impact bar** — thin horizontal bar proportional to `importance_score`

Card is a full-width anchor; opens the source in a new tab.

### `frontend/src/pages/Stock.jsx` (rewritten)

Full-page order:
1. Back link
2. Header
3. Price block
4. Price history — TimeframeTabs + chart
5. How is {symbol} doing? — narrative
6. Statistics — StatsGrid
7. **Recent news — NewsFeed (new)**
8. Company snapshot — CompanySnapshot
9. About {symbol} — CompanyProfile
10. Today's session — OHLC row
11. Coming next — Stages 8–10 placeholder

---

## 4. Verification results

**Probe (Chunk A):** Three sources tested for TCS.NS. Google News
(full company name) returned 86 entries; Google News (symbol) returned
70; Yahoo Finance returned 12. Selected all three, merged and deduped.

**Provider (Chunk B):** TCS returned 15 articles sorted descending, no
duplicate normalised titles, all timezone-aware. RELIANCE worked with an
empty `name_map`. Unknown ticker returned 0 articles.

**DB (Chunk C):** `news_articles` created with the correct unique
constraint on `(security_id, url)`.

**NLP (Chunk D):** Sentiment: 10/10 hand-labelled cases pass including
the four edge cases that required the financial lexicon overlay. Initial
run showed VADER alone scored `"TCS shares fall after profit warning"`
as **positive** (+0.36). Overlay fixed it to negative (−0.14).

Relevance: exact-name matches score 1.0, symbol-only 0.45, unrelated
0.0. `Larsen & Toubro` (0.8) vs `L&T Finance` (0.05) for `LT.NS` —
correctly discriminates sister companies.

Importance: Reuters fresh = 0.88, unknown blog = 0.48, Moneycontrol
fresh = 0.88, Moneycontrol 25d old = 0.71, LatestLY 50d old = 0.36.

**Ingestion (Chunk E, corrected):**

Initial design used a global `UNIQUE(url)`, which caused an IT-sector
roundup mentioning four tickers to overwrite between tickers — the last
ticker to fetch owned the URL. Fixed by changing to
`UNIQUE(security_id, url)`. After the fix:

- Full universe: **949 articles** across 50 tickers in 122 seconds
- Sentiment distribution: 52% positive / 33% neutral / 14% negative
- Every ticker has at least 3 articles
- Lowest coverage: SUNPHARMA (3), ADANIPORTS (4), TATACONSUM (4)
- Highest coverage: HINDALCO, ITC, MARUTI (30 each)

**API (Chunk F):** All shape checks pass. Sorting descending, filter
works, clamps return 422, unknown ticker 404, cache < 2 ms.

**UI (Chunk G):** Screenshot verified — titles cleaned of suffix,
publisher shown once, time-ago correct (6h ago for a 10:33 UTC article
at 22:26 IST), sentiment chips colour-coded, impact bars visible.

**Build:**
```
✓ built in X.XXs
```

---

## 5. Repository deltas since Stage 6

**Backend — added:**
```
backend/scripts/probe_news_sources.py
backend/scripts/ingest_news.py
backend/app/providers/news.py
backend/app/nlp/sentiment.py
backend/app/api/routes/news.py
```

**Backend — modified:**
```
backend/requirements.txt         (added feedparser, vaderSentiment)
backend/app/db/models.py         (appended NewsArticleRow)
backend/app/api/schemas.py       (appended NewsArticleOut, NewsFeedOut)
backend/app/api/router.py        (added news include)
```

**Frontend — added:**
```
frontend/src/components/NewsFeed.jsx
```

**Frontend — modified:**
```
frontend/src/api/client.js       (added getNews)
frontend/src/api/hooks.js        (added useNews)
frontend/src/pages/Stock.jsx     (inserted News section)
```

**Docs — added:**
```
docs/STAGE_07.md
```

**No changes** to any Stage 1–6 file outside the append-only additions
listed above.

---

## 6. Known limitations going into Stage 8

- **Google News RSS URLs are redirects** (`news.google.com/rss/articles/...`).
  Clicking through works but adds one hop. Deferred — not user-visible.
- **Article bodies are not fetched.** Only titles and (short) summaries
  are stored. Adding body retrieval would require ~950 article fetches
  per ingest, most behind paywalls or JS-rendered. Not worth the cost.
- **`univest.in` and `scanx.trade` dominate the corpus** (90 + 86
  articles = ~19%). They're legitimate retail portals but tier-3 by
  default. The fix (moving them to tier-2 in `sentiment.py`) is in place
  but only takes effect on the next full ingest run (Stage 11's
  scheduler will trigger it). Current DB has them scored at tier-3.
- **Low-coverage tickers** (SUNPHARMA 3, ADANIPORTS 4, TATACONSUM 4,
  SBIN 5, DRREDDY 6) reflect what Google News actually published in the
  30-day window. Not a bug.
- **Only 30-day lookback** for news. Historical articles are not
  backfilled. If we want a longer window, run `--days 90`.
- **No per-source blacklist.** If a low-quality source becomes a
  problem, we filter in the tier mapping, not by excluding it.
- **Sentiment is title-weighted only.** Bodies would improve accuracy
  but we don't store them.
- **No deduplication across near-identical titles.** Two outlets
  publishing the same story with slightly different headlines both
  appear. Acceptable — they are different articles, and the user can
  see the source.
- **No translation.** Hindi/Tamil/regional-language articles are not
  fetched (Google News is queried with `hl=en-IN`).

---

## 7. Next stage entry point — Stage 8

**Stage 8 — Forecasting Engine**

The core ML stage. This is where the project stops being descriptive
and starts producing forward-looking probability distributions.

**Output shape (locked in Stage 4 plan):**

For each security, three horizons: 7-day, 15-day, 30-day.

For each horizon:
- `prob_up`, `prob_flat`, `prob_down` (three probabilities summing to 1)
- `expected_low`, `expected_high` (10th and 90th percentile price bands)
- `direction` label (`positive` / `neutral` / `negative`)

Probabilities must be **calibrated** — a 60% up probability should
correspond to roughly 60% of actual up moves in the backtest. If we
cannot demonstrate calibration, we do not ship the forecasts.

**Three-track approach:**

1. **Classical baseline** — histogram gradient boosting (LightGBM or
   sklearn HistGradientBoosting) on the 24 features from Stage 2, trained
   to predict next-N-day direction as a 3-class problem. Fast to train
   locally, gives us a benchmark.
2. **Sequence model** — LSTM or GRU in PyTorch. **Trained on Colab**
   (free GPU), exported to ONNX, inferenced locally via
   `onnxruntime`. The laptop does not train.
3. **Ensemble combiner** — weighted average of the two models plus a
   news-sentiment adjustment from Stage 7's `news_articles` table.
   Weights fitted on a validation split.

**New table:** `forecasts` — `security_id`, `date`, `horizon_days`,
`prob_up`, `prob_flat`, `prob_down`, `expected_low`, `expected_high`,
`direction`, `model_version`, `created_at`. Unique on
`(security_id, date, horizon_days, model_version)`.

**New script:** `backend/scripts/build_forecasts.py` — reads
`features_daily` + `news_articles`, trains or loads models, produces
forecasts for all 50 securities × 3 horizons, writes to `forecasts`.

**New endpoint:** `GET /api/securities/{ticker}/forecast` — returns
all three horizons for the latest available date.

**New frontend component:** `ForecastPanel.jsx` — three cards, one per
horizon. Each shows:
- Direction label with a directional glyph (↑ / → / ↓)
- Probability bars (three-segment: up / flat / down)
- Expected price range ("₹3,420 — ₹3,610")
- A footer line listing the evidence weights ("Momentum +++, News +, Volatility −")

**Backtest report** — required deliverable. Written to
`docs/STAGE_08_backtest.md`:
- 2-year walk-forward on all 50 securities
- Direction hit rate vs random (33%)
- Calibration curve for `prob_up`
- Mean absolute error of the expected range endpoints
- Honest performance summary, including where it's weak

**Design rules:**
- **No point predictions.** Ever. We ship distributions.
- **No future claims in the UI.** "The model estimates a 64% chance of
  an up move over the next 7 days," not "TCS will rise."
- **Calibration is a hard requirement.** If the model isn't calibrated,
  we don't ship it — we say so in the handoff.
- **Training runs on Colab.** No local GPU, no 8-hour laptop burns.
- **Inference runs locally via ONNX.** Must complete for 50 securities
  × 3 horizons in under 10 seconds total.

**Out of scope for Stage 8:** risk engine (Stage 9), explanations
(Stage 10), scheduled automation (Stage 11).

Deliverable: a working `/forecast` endpoint, a UI panel showing three
horizons per stock, and a backtest report honestly stating model
performance.

---

## 8. Handoff prompt for the next chat

Copy this into a new conversation:

> Context: I'm building **Quantpulse**. Repo at `~/IDE/quantpulse`.
> Read `docs/architecture_handoff.md` and `docs/STAGE_01.md` through
> `docs/STAGE_07.md` — all in my repo — before starting. Then begin
> **Stage 8 — Forecasting Engine** exactly as scoped in section 7 of
> `docs/STAGE_07.md`.
>
> Environment: MacBook Air 2015, Intel i5, 8 GB RAM, Zorin OS 16
> (XFCE). Python 3.12.14 in `~/IDE/quantpulse/.venv` managed by `uv`.
> Node 20 + npm. Backend on `127.0.0.1:8000`, Vite on `localhost:5173`
> proxying `/api/*`. Colab is available for training; the laptop does
> inference only.
>
> Rules: plan first, full-file replacements only, one test per chunk,
> no debug cycles, hand off as `docs/STAGE_08.md`.

---
